from dataclasses import dataclass
import json
import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.commands.deploy_migrations import (
    LOCK_ID,
    MigrationGateError,
    load_policy,
    plan_pending_revisions,
    run_migrations,
)


@dataclass(frozen=True)
class FakeRevision:
    revision: str


class FakeScript:
    def __init__(self, revisions, heads):
        self.revisions = set(revisions)
        self.heads = heads

    def get_heads(self):
        return self.heads

    def get_revision(self, revision):
        return FakeRevision(revision) if revision in self.revisions else None

    def iterate_revisions(self, upper, lower):
        if upper not in self.revisions or (lower is not None and lower not in self.revisions):
            raise ValueError("revision not found")
        if lower == upper:
            return iter([FakeRevision(upper)])
        if lower is None:
            chain = sorted(self.revisions)
        else:
            chain = sorted(revision for revision in self.revisions if revision >= lower)
        return iter(FakeRevision(revision) for revision in reversed(chain))


def policy(auto=(), manual=None):
    return {"auto_apply": set(auto), "manual": manual or {}}


def test_policy_reads_reviewed_revisions(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(
        '{"auto_apply":["rev2"],"manual":{"rev3":"requires maintenance"}}',
        encoding="utf-8",
    )
    loaded = load_policy(path)
    assert loaded == {"auto_apply": {"rev2"}, "manual": {"rev3": "requires maintenance"}}


def test_no_pending_revisions_is_a_noop_plan():
    script = FakeScript({"rev1", "rev2"}, ["rev2"])
    assert plan_pending_revisions(script, ("rev2",), policy(auto=("rev2",))) == ("rev2", [])


def test_all_pending_revisions_must_be_approved_before_any_apply():
    script = FakeScript({"rev1", "rev2", "rev3"}, ["rev3"])
    with pytest.raises(MigrationGateError, match="blocked before applying any revision"):
        plan_pending_revisions(script, ("rev1",), policy(auto=("rev2",)))


def test_reviewed_chain_is_ordered_oldest_first():
    script = FakeScript({"rev1", "rev2", "rev3"}, ["rev3"])
    assert plan_pending_revisions(
        script, ("rev1",), policy(auto=("rev2", "rev3"))
    ) == ("rev3", ["rev2", "rev3"])


def test_manual_revision_blocks_the_full_pending_chain():
    script = FakeScript({"rev1", "rev2", "rev3"}, ["rev3"])
    with pytest.raises(MigrationGateError, match="rev2: requires maintenance"):
        plan_pending_revisions(
            script,
            ("rev1",),
            policy(auto=("rev3",), manual={"rev2": "requires maintenance"}),
        )


def test_unreviewed_revision_fails_closed():
    script = FakeScript({"rev1", "rev2"}, ["rev2"])
    with pytest.raises(MigrationGateError, match="no automatic approval recorded"):
        plan_pending_revisions(script, ("rev1",), policy())


def test_unknown_or_multiple_database_revisions_fail_closed():
    script = FakeScript({"rev1", "rev2"}, ["rev2"])
    with pytest.raises(MigrationGateError, match="unknown to this release"):
        plan_pending_revisions(script, ("rev9",), policy())
    with pytest.raises(MigrationGateError, match="multiple current revisions"):
        plan_pending_revisions(script, ("rev1", "rev2"), policy())


def test_multiple_script_heads_fail_closed():
    script = FakeScript({"rev1", "rev2"}, ["rev1", "rev2"])
    with pytest.raises(MigrationGateError, match="Expected one migration head"):
        plan_pending_revisions(script, (), policy())


def test_revision_ahead_of_or_off_the_release_branch_fails_closed():
    class NonAncestorScript(FakeScript):
        def iterate_revisions(self, upper, lower):
            raise ValueError("revision is ahead of target")

    script = NonAncestorScript({"rev1", "rev2"}, ["rev1"])
    with pytest.raises(MigrationGateError, match="not an ancestor"):
        plan_pending_revisions(script, ("rev2",), policy())


def test_actual_release_blocks_the_manual_item_type_drop():
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    real_policy = load_policy(api_root / "migrations" / "migration_policy.json")

    with pytest.raises(MigrationGateError, match="20261008_0024"):
        plan_pending_revisions(script, ("20261008_0023",), real_policy)

    assert plan_pending_revisions(script, ("20261008_0024",), real_policy) == (
        "20261008_0024",
        [],
    )


def test_runner_postgresql_integration(tmp_path):
    database_url = os.environ.get("MIGRATION_RUNNER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set MIGRATION_RUNNER_TEST_DATABASE_URL to a disposable migration_test_* database.")
    parsed = make_url(database_url)
    if not parsed.database or not parsed.database.startswith("migration_test_"):
        pytest.fail("Integration test refuses database names not prefixed migration_test_.")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS public.migration_runner_probe CASCADE"))
        connection.execute(text("DROP TABLE IF EXISTS public.alembic_version CASCADE"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
        safe_database_name = parsed.database.replace('"', '""')
        connection.exec_driver_sql(f'ALTER DATABASE "{safe_database_name}" SET search_path TO app, public')
    engine.dispose()

    migrations = tmp_path / "migrations"
    versions = migrations / "versions"
    versions.mkdir(parents=True)
    (migrations / "env.py").write_text(
        '''from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

def run(connection):
    context.configure(connection=connection, version_table_schema="public")
    with context.begin_transaction():
        context.run_migrations()

connection = config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    engine = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        run(connection)
''',
        encoding="utf-8",
    )
    (migrations / "script.py.mako").write_text(
        "%(up_revision)s", encoding="utf-8"
    )
    (migrations / "alembic.ini").write_text(
        f"""[alembic]
script_location = {migrations}
sqlalchemy.url = placeholder

[loggers]
keys = root
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)s: %(message)s
""",
        encoding="utf-8",
    )
    (versions / "r1_create_probe.py").write_text(
        '''from alembic import op
import sqlalchemy as sa

revision = "r1"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("migration_runner_probe", sa.Column("id", sa.Integer(), primary_key=True), schema="public")

def downgrade():
    op.drop_table("migration_runner_probe", schema="public")
''',
        encoding="utf-8",
    )
    (versions / "r2_add_value.py").write_text(
        '''from alembic import op
import sqlalchemy as sa

revision = "r2"
down_revision = "r1"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("migration_runner_probe", sa.Column("value", sa.String(), nullable=True), schema="public")

def downgrade():
    op.drop_column("migration_runner_probe", "value", schema="public")
''',
        encoding="utf-8",
    )
    policy_file = tmp_path / "migration_policy.json"
    policy_file.write_text(
        json.dumps({"auto_apply": ["r1", "r2"], "manual": {}}),
        encoding="utf-8",
    )
    config_path = migrations / "alembic.ini"

    assert run_migrations(
        config_path=config_path, policy_path=policy_file, url=database_url
    ) == {"status": "preview", "from_revision": None, "revision": "r2", "pending": ["r1", "r2"]}

    blocker = create_engine(database_url)
    with blocker.connect() as connection:
        assert connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": LOCK_ID}
        ).scalar_one()
        connection.commit()
        with pytest.raises(MigrationGateError, match="Timed out waiting"):
            run_migrations(
                config_path=config_path,
                policy_path=policy_file,
                url=database_url,
                lock_timeout_seconds=1,
            )
        connection.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": LOCK_ID}
        )
        connection.commit()
    blocker.dispose()

    (versions / "r3_failure.py").write_text(
        '''revision = "r3"
down_revision = "r2"
branch_labels = None
depends_on = None

def upgrade():
    raise RuntimeError("intentional disposable migration failure")

def downgrade():
    pass
''',
        encoding="utf-8",
    )
    policy_file.write_text(
        json.dumps({"auto_apply": ["r1", "r2"], "manual": {"r3": "test manual revision"}}),
        encoding="utf-8",
    )
    # The manual r3 blocks the whole chain before any DDL is applied.
    with pytest.raises(MigrationGateError, match="r3: test manual revision"):
        run_migrations(apply=True, config_path=config_path, policy_path=policy_file, url=database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar_one() is None

    policy_file.write_text(json.dumps({"auto_apply": ["r1", "r2", "r3"], "manual": {}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="intentional disposable migration failure"):
        run_migrations(apply=True, config_path=config_path, policy_path=policy_file, url=database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('public.migration_runner_probe')")).scalar_one() is None
        assert connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar_one() is None

    (versions / "r3_failure.py").unlink()
    policy_file.write_text(json.dumps({"auto_apply": ["r1", "r2"], "manual": {}}), encoding="utf-8")
    applied = run_migrations(apply=True, config_path=config_path, policy_path=policy_file, url=database_url)
    assert applied["status"] == "applied"
    assert applied["from_revision"] is None
    assert applied["revision"] == "r2"
    assert run_migrations(
        apply=True, config_path=config_path, policy_path=policy_file, url=database_url
    )["status"] == "current"

    with engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar_one() is not None
        assert connection.execute(text("SELECT to_regclass('app.alembic_version')")).scalar_one() is None
        connection.execute(text("UPDATE public.alembic_version SET version_num = 'unknown'"))
        connection.commit()
    with pytest.raises(MigrationGateError, match="unknown to this release"):
        run_migrations(config_path=config_path, policy_path=policy_file, url=database_url)
    engine.dispose()
