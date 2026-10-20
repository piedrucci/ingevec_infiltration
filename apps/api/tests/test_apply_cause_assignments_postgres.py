"""Opt-in: CAUSE_GROUP_TEST_DATABASE_URL must point to a disposable database named cause_group_test."""
import json
import os
import sys
from pathlib import Path

import pytest
from alembic import command as alembic
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.commands import apply_cause_assignments as command
from app.commands.import_category_causes import import_mapping
from app.models import (FailureCause, FailureCauseAlias, FailureCauseCategory, FailureCauseCategoryGroupLink,
                        FailureCauseCategoryLink, FailureCauseGroup, PostventaItem, PostventaItemFailureCause)

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get("CAUSE_GROUP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires a disposable PostgreSQL database")
    engine = create_engine(url)
    assert engine.url.database == "cause_group_test", "Integration tests require database named cause_group_test"
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS app CASCADE; DROP SCHEMA IF EXISTS analytics CASCADE; "
                                "DROP TABLE IF EXISTS public.alembic_version"))
    monkeypatch.setenv("MIGRATION_DATABASE_URL", url)
    alembic.upgrade(Config(str(ALEMBIC_INI)), "head")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(command, "SessionLocal", factory)
    monkeypatch.setattr(command, "invalidate_dashboard_summary", lambda: None)
    with factory.begin() as db:
        seed(db)
    yield engine, factory
    engine.dispose()


def seed(db):
    ids = {table: db.execute(text(f"INSERT INTO app.{table}(name) VALUES ('Test') RETURNING id")).scalar_one()
           for table in ("typology", "location", "supervisor", "classification")}
    db.execute(text("INSERT INTO app.project(id,name,typology_id,location_id,supervisor_id) VALUES ('712','PAM',:typology,:location,:supervisor)"), ids)
    groups = {g.code: g.id for g in db.scalars(select(FailureCauseGroup))}
    window = FailureCauseCategory(code="WINDOWS", display_name_es="Ventana")
    sheet = FailureCauseCategory(code="SHEET_METAL", display_name_es="Hojalateria")
    db.add_all([window, sheet])
    db.flush()
    db.add_all([FailureCauseCategoryGroupLink(category_id=window.id, group_id=groups["EJECUCION"]),
                FailureCauseCategoryGroupLink(category_id=window.id, group_id=groups["PROPIETARIO"]),
                FailureCauseCategoryGroupLink(category_id=sheet.id, group_id=groups["EJECUCION"])])
    seals = FailureCause(code="BROKEN_SEALS__WINDOWS", display_name_es="Sellos cortados")
    pvc = FailureCause(code="PVC", display_name_es="PVC inferior")
    db.add_all([seals, pvc])
    db.flush()
    db.add_all([FailureCauseCategoryLink(failure_cause_id=seals.id, category_id=window.id),
                FailureCauseCategoryLink(failure_cause_id=pvc.id, category_id=window.id),
                FailureCauseAlias(failure_cause_id=seals.id, normalized_alias="ventana sellos cortados")])
    items = [PostventaItem(project_id="712", classification_id=ids["classification"], notes=n, failure_cause_id=seals.id if n != "Depto C" else None)
             for n in ("Depto A", "Depto B", "Depto C")]
    db.add_all(items)
    db.flush()
    db.add_all([PostventaItemFailureCause(postventa_item_id=items[0].id, failure_cause_id=seals.id, assignment_source="MANUAL", assigned_by="tester"),
                PostventaItemFailureCause(postventa_item_id=items[1].id, failure_cause_id=seals.id, assignment_source="AUTOMATIC")])


ROWS = {"rows": [
    {"project_id": "712", "notes": "Depto A", "associated_causes": [{"group": "Ejecución", "category": "Ventana", "cause": "Sellos cortados"}]},
    {"project_id": "712", "notes": "Depto B", "associated_causes": [{"group": "Propietario", "category": "Ventana", "cause": "Sellos cortados"},
                                                                   {"group": "Propietario", "category": "Ventana", "cause": "PVC inferior"}]},
    {"project_id": "712", "notes": "Depto C", "associated_causes": [{"group": "Ejecución", "category": "Hojalatería", "cause": "Gárgola rota"}]},
]}


def run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["apply_cause_assignments", *map(str, args)])
    command.main()


def test_dry_run_apply_and_rollback_round_trip(database, monkeypatch, tmp_path):
    engine, factory = database
    source = tmp_path / "rows.json"
    source.write_text(json.dumps(ROWS, ensure_ascii=False), encoding="utf-8")
    with factory() as db:
        original = command.load_snapshot(db).fingerprint()

    run(monkeypatch, source, "--dry-run", "--report", tmp_path / "dry.json")
    with factory() as db:
        assert command.load_snapshot(db).fingerprint() == original
    dry = json.loads((tmp_path / "dry.json").read_text())
    assert dry["status"] == "dry_run" and dry["plan"]["blockers"] == []
    assert (tmp_path / "dry.json").stat().st_mode & 0o777 == 0o600

    run(monkeypatch, source, "--apply", "--reviewed-report", tmp_path / "dry.json", "--report", tmp_path / "applied.json")
    with factory() as db:
        causes = {c.code: c for c in db.scalars(select(FailureCause))}
        groups = {link.failure_cause_id: link.group_id for link in db.scalars(select(FailureCauseCategoryLink))}
        group_ids = {g.code: g.id for g in db.scalars(select(FailureCauseGroup))}
        assert not causes["BROKEN_SEALS__WINDOWS"].is_active and causes["BROKEN_SEALS__WINDOWS"].id not in groups
        assert groups[causes["BROKEN_SEALS__WINDOWS__EJECUCION"].id] == group_ids["EJECUCION"]
        assert groups[causes["BROKEN_SEALS__WINDOWS__PROPIETARIO"].id] == group_ids["PROPIETARIO"]
        assert groups[causes["PVC"].id] == group_ids["PROPIETARIO"]
        assert groups[causes["GARGOLA_ROTA"].id] == group_ids["EJECUCION"]
        items = {i.notes: i for i in db.scalars(select(PostventaItem))}
        link_a = db.scalar(select(PostventaItemFailureCause).where(PostventaItemFailureCause.postventa_item_id == items["Depto A"].id))
        assert (link_a.failure_cause_id, link_a.assignment_source, link_a.assigned_by) == (causes["BROKEN_SEALS__WINDOWS__EJECUCION"].id, "MANUAL", "tester")
        assert items["Depto C"].failure_cause_id == causes["GARGOLA_ROTA"].id
        assert items["Depto B"].failure_cause_id == min(causes["PVC"].id, causes["BROKEN_SEALS__WINDOWS__PROPIETARIO"].id)
        rows = db.execute(text("SELECT codigo_causa_falla, codigo_grupo_causa FROM analytics.postventa_item_cause_pareto ORDER BY 1, 2")).all()
        assert rows == [("BROKEN_SEALS__WINDOWS__EJECUCION", "EJECUCION"), ("BROKEN_SEALS__WINDOWS__PROPIETARIO", "PROPIETARIO"),
                        ("GARGOLA_ROTA", "EJECUCION"), ("PVC", "PROPIETARIO")]

    # A second plan against the applied state has nothing left to do.
    with factory() as db:
        again = command.plan_assignments(command.load_snapshot(db), command.load_rows(source))
    assert (again.blockers, again.creations, again.group_updates, again.retirements, again.item_changes) == ([], [], [], [], [])

    run(monkeypatch, "--rollback", tmp_path / "applied.json", "--report", tmp_path / "rollback.json")
    with factory() as db:
        assert command.load_snapshot(db).fingerprint() == original
    assert json.loads((tmp_path / "rollback.json").read_text())["status"] == "rolled_back"


def test_apply_rejects_stale_review(database, monkeypatch, tmp_path):
    _, factory = database
    source = tmp_path / "rows.json"
    source.write_text(json.dumps(ROWS, ensure_ascii=False), encoding="utf-8")
    run(monkeypatch, source, "--dry-run", "--report", tmp_path / "dry.json")
    with factory.begin() as db:
        db.execute(text("UPDATE app.postventa_item SET notes = 'Depto A' WHERE notes = 'Depto A'"))
        db.execute(text("UPDATE app.postventa_item_failure_cause SET assigned_by = 'someone else' WHERE assigned_by = 'tester'"))
    with pytest.raises(SystemExit, match="Database changed"):
        run(monkeypatch, source, "--apply", "--reviewed-report", tmp_path / "dry.json", "--report", tmp_path / "applied.json")
    with factory() as db:
        assert db.scalar(select(FailureCause).where(FailureCause.code == "GARGOLA_ROTA")) is None


def test_rollback_refuses_after_later_edits(database, monkeypatch, tmp_path):
    _, factory = database
    source = tmp_path / "rows.json"
    source.write_text(json.dumps(ROWS, ensure_ascii=False), encoding="utf-8")
    run(monkeypatch, source, "--dry-run", "--report", tmp_path / "dry.json")
    run(monkeypatch, source, "--apply", "--reviewed-report", tmp_path / "dry.json", "--report", tmp_path / "applied.json")
    with factory.begin() as db:
        db.execute(text("DELETE FROM app.postventa_item_failure_cause WHERE assigned_by = 'tester'"))
    with pytest.raises(ValueError, match="changed after apply"):
        run(monkeypatch, "--rollback", tmp_path / "applied.json", "--report", tmp_path / "rollback.json")


def test_category_import_keeps_groups_of_unchanged_causes(database):
    _, factory = database
    with factory() as db:
        group_id = db.scalar(select(FailureCauseGroup.id).where(FailureCauseGroup.code == "EJECUCION"))
        db.execute(text("UPDATE app.failure_cause_category_link SET group_id = :g"), {"g": group_id})
        db.commit()
        summary = import_mapping(db, {"WINDOWS": ["BROKEN_SEALS__WINDOWS"], "SHEET_METAL": ["PVC"]})
        groups = {code: group for code, group in db.execute(select(FailureCause.code, FailureCauseCategoryLink.group_id)
                  .join(FailureCauseCategoryLink, FailureCauseCategoryLink.failure_cause_id == FailureCause.id))}
    assert groups == {"BROKEN_SEALS__WINDOWS": group_id, "PVC": None}
    assert summary.groups_cleared == ("PVC",)
