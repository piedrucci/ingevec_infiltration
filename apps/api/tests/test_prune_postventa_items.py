import hashlib
import io
import json
import os
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.commands import prune_postventa_items as command


def state():
    return {
        "items": [{"id": 1, "notes": " Keep "}, {"id": 2, "notes": "Remove"}],
        "causes": [
            {"postventa_item_id": 1, "source_document_id": 12},
            {"postventa_item_id": 2, "source_document_id": 12},
        ],
        "pdf_links": [
            {"postventa_item_id": 1, "document_id": 10},
            {"postventa_item_id": 2, "document_id": 10},
            {"postventa_item_id": 2, "document_id": 11},
            {"postventa_item_id": 2, "document_id": 12},
        ],
        "documents": [
            {"id": doc_id, "bucket": "private", "object_key": f"{doc_id}.pdf", "content_hash": hashlib.sha256(b"pdf").hexdigest()}
            for doc_id in (10, 11, 12, 13)
        ],
        "outbox": [],
    }


def test_preserves_shared_documents_and_cause_provenance():
    plan = command.plan_deletions(state(), [{"notes": "Keep"}])
    assert plan["apply_ready"]
    assert plan["delete_item_ids"] == [2]
    assert plan["delete_document_ids"] == [11]
    assert plan["preserved_shared_document_ids"] == [10, 12]
    assert plan["projected_reconciled"] == 1
    assert plan["projected_pending"] == 0
    assert plan["deleted_pdf_links"] == 3
    assert plan["deleted_cause_links"] == 1


def test_missing_and_duplicate_database_notes_block_apply():
    data = state()
    data["items"].append({"id": 3, "notes": "Keep"})
    plan = command.plan_deletions(data, [{"notes": "Keep"}, {"notes": "Missing"}])
    assert not plan["apply_ready"]
    assert plan["missing_notes"] == ["Missing"]
    assert plan["ambiguous_notes"] == {"Keep": [1, 3]}


def test_exact_matching_preserves_case_accents_and_internal_spaces():
    plan = command.plan_deletions(state(), [{"notes": "keep"}])
    assert plan["missing_notes"] == ["keep"]


def test_load_source_deduplicates_identical_rows_without_changing_original(tmp_path):
    source = tmp_path / "source.json"
    original = {"rows": [{"notes": " Keep ", "causes": ["One"]}] * 2}
    source.write_text(json.dumps(original))
    _, cleaned, _ = command.load_source(source)
    assert cleaned == [{"notes": "Keep", "causes": ["One"]}]
    assert json.loads(source.read_text()) == original


@pytest.mark.parametrize("rows", [[], [{"notes": " "}], [{"notes": None}], [
    {"notes": "Keep", "causes": ["One"]}, {"notes": "Keep", "causes": ["Two"]},
]])
def test_invalid_sources_are_rejected(tmp_path, rows):
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"rows": rows}))
    with pytest.raises(ValueError):
        command.load_source(path)


@pytest.mark.parametrize("field", ["source_sha256", "database_identity", "state_sha256", "cleaned_sha256", "plan"])
def test_stale_reports_are_rejected(field):
    current = {
        "source_sha256": "source", "database_identity": "db", "state_sha256": "state",
        "cleaned_sha256": "clean", "plan": {"apply_ready": True},
    }
    report = dict(current, kind="prune-preview", version=1)
    report[field] = "modified"
    with pytest.raises(ValueError, match="stale or modified"):
        command.validate_review(report, current)


def test_second_run_has_no_deletions():
    data = state()
    data["items"] = data["items"][:1]
    data["pdf_links"] = [row for row in data["pdf_links"] if row["postventa_item_id"] == 1]
    data["causes"] = data["causes"][:1]
    data["documents"] = [row for row in data["documents"] if row["id"] != 11]
    plan = command.plan_deletions(data, [{"notes": "Keep"}])
    assert plan["apply_ready"]
    assert plan["delete_item_ids"] == plan["delete_document_ids"] == []


def test_report_cannot_be_overwritten(tmp_path):
    path = tmp_path / "report.json"
    command.write_new(path, {"original": True})
    with pytest.raises(FileExistsError):
        command.write_new(path, {"modified": True})
    assert json.loads(path.read_text()) == {"original": True}


def setup_cleanup(monkeypatch, tmp_path, *, deleted_items=(), deleted_docs=(), current_objects=()):
    db = MagicMock()
    db.scalars.side_effect = [list(deleted_items), list(deleted_docs)]
    db.execute.return_value.all.return_value = list(current_objects)
    factory = MagicMock()
    factory.return_value.__enter__.return_value = db
    monkeypatch.setattr(command, "SessionLocal", factory)
    monkeypatch.setattr(command, "identity", lambda db: "test-db")
    monkeypatch.setattr(command, "invalidate_dashboard_summary", lambda: None)
    manifest = {
        "kind": "prune-recovery", "version": 1, "database_identity": "test-db", "phase": "prepared",
        "plan": command.plan_deletions(state(), [{"notes": "Keep"}]), "cleanup": [], "snapshot": state(),
    }
    manifest["recovery_checksum"] = command.recovery_checksum(manifest)
    path = tmp_path / "manifest.json"
    command.write_new(path, manifest)
    return path, db


def test_resume_refuses_cleanup_when_transaction_did_not_commit(monkeypatch, tmp_path):
    path, _ = setup_cleanup(monkeypatch, tmp_path, deleted_items=[2], deleted_docs=[11])
    client = MagicMock()
    monkeypatch.setattr(command, "s3_client", lambda: client)
    with pytest.raises(ValueError, match="deletions are not complete"):
        command.resume_cleanup(path)
    client.delete_object.assert_not_called()


def test_modified_recovery_manifest_cannot_delete_objects(monkeypatch, tmp_path):
    path, _ = setup_cleanup(monkeypatch, tmp_path)
    manifest = json.loads(path.read_text())
    manifest["plan"]["storage_objects"][0]["key"] = "unreviewed.pdf"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="was modified"):
        command.resume_cleanup(path)


def test_storage_failure_can_be_resumed(monkeypatch, tmp_path):
    path, db = setup_cleanup(monkeypatch, tmp_path)
    client = MagicMock()
    client.get_object.return_value = {"Body": io.BytesIO(b"pdf")}
    client.delete_object.side_effect = RuntimeError("storage unavailable")
    monkeypatch.setattr(command, "s3_client", lambda: client)
    with pytest.raises(ValueError, match="resume-cleanup"):
        command.resume_cleanup(path)
    assert json.loads(path.read_text())["phase"] == "storage_pending"
    db.scalars.side_effect = [[], []]
    client.get_object.return_value = {"Body": io.BytesIO(b"pdf")}
    client.delete_object.side_effect = None
    command.resume_cleanup(path)
    assert json.loads(path.read_text())["phase"] == "complete"


@pytest.mark.parametrize("reason", ["referenced", "replaced"])
def test_cleanup_protects_referenced_or_overwritten_objects(monkeypatch, tmp_path, reason):
    path, _ = setup_cleanup(monkeypatch, tmp_path, current_objects=[("private", "11.pdf")] if reason == "referenced" else [])
    client = MagicMock()
    client.get_object.return_value = {"Body": io.BytesIO(b"different pdf")}
    monkeypatch.setattr(command, "s3_client", lambda: client)
    with pytest.raises(ValueError, match="resume-cleanup"):
        command.resume_cleanup(path)
    client.delete_object.assert_not_called()


def test_absent_object_is_successful_cleanup(monkeypatch, tmp_path):
    path, _ = setup_cleanup(monkeypatch, tmp_path)
    client = MagicMock()
    client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
    monkeypatch.setattr(command, "s3_client", lambda: client)
    command.resume_cleanup(path)
    assert json.loads(path.read_text())["phase"] == "complete"
    client.delete_object.assert_not_called()


@pytest.fixture
def disposable_database(monkeypatch):
    """Opt-in integration fixture, restricted to the dedicated disposable DB."""
    url = os.environ.get("PRUNE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires a disposable PostgreSQL database")
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import (
        Classification, ExcelImport, ExcelSourceRow, FailureCause, ItemType,
        Location, Project, Supervisor, Typology,
    )
    engine = create_engine(url)
    assert engine.url.database == "prune_test", "Integration tests require database named prune_test"
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        connection.execute(text("CREATE SCHEMA app"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(command, "SessionLocal", factory)
    monkeypatch.setattr(command, "invalidate_dashboard_summary", lambda: None)
    client = MagicMock()
    client.get_object.side_effect = lambda **kwargs: {"Body": io.BytesIO(b"pdf")}
    monkeypatch.setattr(command, "s3_client", lambda: client)
    with factory.begin() as db:
        db.add_all([model(id=1, name="catalog") for model in (Classification, ItemType, Location, Supervisor, Typology)])
        db.flush()
        db.add(Project(id="one", name="project", typology_id=1, location_id=1, supervisor_id=1))
        imported = ExcelImport(original_filename="source.xlsx", file_hash="hash", status="COMPLETED", row_count=2)
        db.add(imported)
        db.flush()
        sources = [ExcelSourceRow(excel_import_id=imported.id, sheet_name="Año 2026", row_number=i, raw_cells={"notes": note}, row_hash=str(i), normalization_status="NORMALIZED") for i, note in ((1, "Keep"), (2, "Remove"))]
        db.add_all(sources)
        db.flush()
        db.add_all([command.PostventaItem(id=i, notes=note, source_row_id=source.id, project_id="one", classification_id=1, item_type_id=1, failure_cause_id=None) for i, note, source in zip((1, 2), ("Keep", "Remove"), sources)])
        db.add(FailureCause(id=1, code="CAUSE", display_name_es="Cause"))
        db.add_all([command.Document(id=i, bucket="test", object_key=f"{i}.pdf", original_filename=f"{i}.pdf", content_hash=hashlib.sha256(b"pdf").hexdigest() if i == 11 else str(i), file_size_bytes=3, content_type="application/pdf", status="MATCHED") for i in (10, 11, 12)])
        db.flush()
        db.add_all([command.DocumentPostventaItem(document_id=doc, postventa_item_id=item, association_source="MANUAL") for doc, item in ((10, 1), (10, 2), (11, 2))])
        db.add(command.PostventaItemFailureCause(postventa_item_id=1, failure_cause_id=1, source_document_id=12, assignment_source="MIGRATED"))
        db.add(command.DocumentOutboxEvent(document_id=11, subject="event", payload={}))
    try:
        yield engine, factory, client
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA app CASCADE"))
        engine.dispose()


def integration_report(factory, tmp_path):
    source, cleaned, report = [tmp_path / name for name in ("source.json", "cleaned.json", "report.json")]
    source.write_text(json.dumps({"rows": [{"notes": "Keep"}]}))
    with factory() as db:
        preview = command.reviewed_report(db, source, cleaned)
    command.write_new(cleaned, {"rows": [{"notes": "Keep"}]})
    command.write_new(report, preview)
    return source, report, tmp_path / "manifest.json"


def test_postgres_apply_cascades_and_preserves_retained_data(disposable_database, tmp_path):
    from sqlalchemy import select
    from app.models import ExcelSourceRow
    _, factory, client = disposable_database
    source, report, manifest = integration_report(factory, tmp_path)
    command.apply_review(source, report, manifest)
    with factory() as db:
        assert list(db.scalars(select(command.PostventaItem.id))) == [1]
        assert set(db.scalars(select(command.Document.id))) == {10, 12}
        assert len(db.scalars(select(ExcelSourceRow)).all()) == 2
        assert len(db.scalars(select(command.DocumentPostventaItem)).all()) == 1
        assert len(db.scalars(select(command.PostventaItemFailureCause)).all()) == 1
        assert not db.scalars(select(command.DocumentOutboxEvent)).all()
        plan = command.plan_deletions(command.snapshot(db), [{"notes": "Keep"}])
        assert plan["delete_item_ids"] == plan["delete_document_ids"] == []
    client.delete_object.assert_called_once_with(Bucket="test", Key="11.pdf")
    assert json.loads(manifest.read_text())["phase"] == "complete"


def test_postgres_transaction_rolls_back_before_storage_deletion(disposable_database, tmp_path):
    from sqlalchemy import event, select
    engine, factory, client = disposable_database
    source, report, manifest = integration_report(factory, tmp_path)
    def fail_document_delete(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM app.document "):
            raise RuntimeError("simulated DB failure")
    event.listen(engine, "before_cursor_execute", fail_document_delete)
    try:
        with pytest.raises(RuntimeError, match="simulated"):
            command.apply_review(source, report, manifest)
    finally:
        event.remove(engine, "before_cursor_execute", fail_document_delete)
    with factory() as db:
        assert set(db.scalars(select(command.PostventaItem.id))) == {1, 2}
        assert set(db.scalars(select(command.Document.id))) == {10, 11, 12}
        assert len(db.scalars(select(command.DocumentPostventaItem)).all()) == 3
    client.delete_object.assert_not_called()
    assert json.loads(manifest.read_text())["phase"] == "prepared"
    with pytest.raises(ValueError, match="deletions are not complete"):
        command.resume_cleanup(manifest)
