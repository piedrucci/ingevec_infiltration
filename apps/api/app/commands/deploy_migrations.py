"""Inspect pending production migrations and apply only reviewed compatible revisions."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.db import database_url


LOCK_ID = 7_261_026_100_800_024
DEFAULT_LOCK_TIMEOUT_SECONDS = 60
MAX_LOCK_TIMEOUT_SECONDS = 300
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "alembic.ini"
DEFAULT_POLICY = Path(__file__).resolve().parents[2] / "migrations" / "migration_policy.json"


class MigrationGateError(RuntimeError):
    """Raised when the release cannot safely migrate the current database."""


def _revision_exists(script: ScriptDirectory, revision: str) -> bool:
    try:
        return script.get_revision(revision) is not None
    except CommandError:
        return False


def load_policy(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationGateError(f"Cannot read migration review policy at {path.name}.") from exc
    if not isinstance(value, dict):
        raise MigrationGateError("Migration review policy must be a JSON object.")
    automatic = value.get("auto_apply")
    manual = value.get("manual")
    if (
        not isinstance(automatic, list)
        or any(not isinstance(revision, str) or not revision for revision in automatic)
        or not isinstance(manual, dict)
        or any(
            not isinstance(revision, str)
            or not revision
            or not isinstance(reason, str)
            or not reason
            for revision, reason in manual.items()
        )
    ):
        raise MigrationGateError("Migration policy must contain auto_apply revisions and manual reasons.")
    automatic_set = set(automatic)
    if len(automatic_set) != len(automatic) or automatic_set.intersection(manual):
        raise MigrationGateError("Migration policy has duplicate or conflicting revision classifications.")
    return {"auto_apply": automatic_set, "manual": manual}


def plan_pending_revisions(
    script: ScriptDirectory,
    current_heads: tuple[str, ...],
    policy: dict[str, Any],
) -> tuple[str, list[str]]:
    """Return the sole script head and pending revisions after validating history and policy."""
    heads = script.get_heads()
    if len(heads) != 1:
        raise MigrationGateError(f"Expected one migration head; found {len(heads)}.")
    if len(current_heads) > 1:
        raise MigrationGateError("Database has multiple current revisions; resolve migration history manually.")
    current = current_heads[0] if current_heads else None
    if current is not None and not _revision_exists(script, current):
        raise MigrationGateError(f"Database revision {current} is unknown to this release.")

    known_revisions = policy["auto_apply"] | set(policy["manual"])
    unknown_policy = sorted(revision for revision in known_revisions if not _revision_exists(script, revision))
    if unknown_policy:
        raise MigrationGateError(
            f"Migration policy refers to revisions missing from this release: {', '.join(unknown_policy)}."
        )

    try:
        revisions = list(script.iterate_revisions(heads[0], current))
    except Exception as exc:
        raise MigrationGateError("Database revision is not an ancestor of this release head.") from exc
    pending = list(reversed([
        revision.revision for revision in revisions if revision.revision != current
    ]))
    if not pending:
        return heads[0], []

    known = policy["auto_apply"] | set(policy["manual"])
    unknown = [revision for revision in pending if script.get_revision(revision) is None]
    if unknown:
        raise MigrationGateError(f"Migration chain contains unknown revisions: {', '.join(unknown)}.")
    manual = [revision for revision in pending if revision in policy["manual"]]
    unreviewed = [revision for revision in pending if revision not in known]
    if manual or unreviewed:
        reasons = [f"{revision}: {policy['manual'][revision]}" for revision in manual]
        reasons.extend(f"{revision}: no automatic approval recorded" for revision in unreviewed)
        raise MigrationGateError(
            "Automatic migration blocked before applying any revision. " + "; ".join(reasons)
        )
    return heads[0], pending


def _current_heads(connection) -> tuple[str, ...]:
    context = MigrationContext.configure(
        connection,
        opts={"version_table_schema": "public"},
    )
    return tuple(context.get_current_heads())


def _acquire_lock(connection, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        locked = connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": LOCK_ID}
        ).scalar_one()
        connection.commit()
        if locked:
            return
        if time.monotonic() >= deadline:
            raise MigrationGateError(f"Timed out waiting {timeout_seconds}s for the migration lock.")
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def run_migrations(
    *,
    apply: bool = False,
    config_path: Path = DEFAULT_CONFIG,
    policy_path: Path = DEFAULT_POLICY,
    url: str | None = None,
    lock_timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not 1 <= lock_timeout_seconds <= MAX_LOCK_TIMEOUT_SECONDS:
        raise MigrationGateError(
            f"Lock timeout must be between 1 and {MAX_LOCK_TIMEOUT_SECONDS} seconds."
        )
    policy = load_policy(policy_path)
    config = Config(str(config_path))
    script = ScriptDirectory.from_config(config)

    migration_url = url or os.environ.get("MIGRATION_DATABASE_URL")
    if not migration_url:
        if os.environ.get("APP_ENV") == "production":
            raise MigrationGateError("MIGRATION_DATABASE_URL must point to a session-capable PostgreSQL endpoint.")
        migration_url = database_url()
    parsed_url = make_url(migration_url)
    if parsed_url.get_backend_name() != "postgresql":
        raise MigrationGateError("Production migration runner requires PostgreSQL.")
    engine = create_engine(
        migration_url,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": 10,
            "options": "-c lock_timeout=5000 -c statement_timeout=600000",
        },
    )
    try:
        with engine.connect() as connection:
            locked = False
            try:
                _acquire_lock(connection, lock_timeout_seconds)
                locked = True
                current_heads = _current_heads(connection)
                target, pending = plan_pending_revisions(script, current_heads, policy)
                current_revision = current_heads[0] if current_heads else None
                if not pending:
                    return {
                        "status": "current",
                        "from_revision": current_revision,
                        "revision": target,
                        "pending": [],
                    }
                if not apply:
                    return {
                        "status": "preview",
                        "from_revision": current_revision,
                        "revision": target,
                        "pending": pending,
                    }

                connection.commit()
                config.attributes["connection"] = connection
                command.upgrade(config, target)
                if connection.in_transaction():
                    connection.commit()
                result_heads = _current_heads(connection)
                if result_heads != (target,):
                    raise MigrationGateError(
                        "Migration command completed, but the database did not reach the release head."
                    )
                return {
                    "status": "applied",
                    "from_revision": current_revision,
                    "revision": target,
                    "pending": pending,
                }
            finally:
                if locked:
                    if connection.in_transaction():
                        connection.rollback()
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": LOCK_ID}
                    )
                    connection.commit()
    except SQLAlchemyError as exc:
        # Keep driver diagnostics out of deployment logs; they may contain connection details.
        raise MigrationGateError(
            f"Database operation failed ({type(exc).__name__}); check the migration connection and database logs."
        ) from None
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply the reviewed pending migration chain")
    parser.add_argument("--lock-timeout-seconds", type=int, default=DEFAULT_LOCK_TIMEOUT_SECONDS)
    args = parser.parse_args()
    try:
        result = run_migrations(apply=args.apply, lock_timeout_seconds=args.lock_timeout_seconds)
    except MigrationGateError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, indent=2), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": type(exc).__name__}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
