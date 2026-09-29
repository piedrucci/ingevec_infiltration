"""Prune items using a reviewed JSON allowlist and resume exclusive PDF cleanup."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import delete, select, text

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import (
    Document, DocumentOutboxEvent, DocumentPostventaItem,
    PostventaItem, PostventaItemFailureCause,
)
from app.services.dashboard_cache import invalidate_dashboard_summary
from app.services.storage import s3_client

logger = logging.getLogger(__name__)
TABLES = {
    "items": PostventaItem,
    "causes": PostventaItemFailureCause,
    "pdf_links": DocumentPostventaItem,
    "documents": Document,
    "outbox": DocumentOutboxEvent,
}
VERSION = 1


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def recovery_checksum(manifest: dict) -> str:
    return digest({key: manifest[key] for key in ("database_identity", "plan", "snapshot")})


def load_source(path: Path) -> tuple[dict, list[dict], str]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list) or not payload["rows"]:
        raise ValueError("JSON must contain a non-empty rows array")
    by_note: dict[str, dict] = {}
    for index, row in enumerate(payload["rows"], 1):
        if not isinstance(row, dict) or not isinstance(row.get("notes"), str) or not row["notes"].strip():
            raise ValueError(f"Row {index} must have non-blank string notes")
        cleaned = dict(row, notes=row["notes"].strip())
        note = cleaned["notes"]
        if note in by_note and by_note[note] != cleaned:
            raise ValueError(f"Conflicting duplicate JSON note: {note}")
        by_note.setdefault(note, cleaned)
    return payload, list(by_note.values()), hashlib.sha256(raw).hexdigest()


def write_new(path: Path, payload: dict) -> None:
    """Create a private, durable artifact without overwriting another report."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(encoded(payload) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    sync_directory(path.parent)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def update_manifest(path: Path, payload: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".prune-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(encoded(payload) + b"\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def identity(db) -> str:
    settings = get_settings()
    return digest({
        "database": db.get_bind().url.render_as_string(hide_password=True),
        "environment": settings.APP_ENV,
        "storage": str(settings.S3_ENDPOINT_URL),
    })


def snapshot(db) -> dict[str, list[dict]]:
    result = {}
    for name, model in TABLES.items():
        table = model.__table__
        rows = db.execute(select(table).order_by(*table.primary_key.columns)).mappings()
        result[name] = json.loads(encoded([dict(row) for row in rows]))
    return result


def plan_deletions(state: dict, rows: list[dict]) -> dict:
    by_note: dict[str, list[int]] = defaultdict(list)
    for item in state["items"]:
        by_note[item["notes"].strip()].append(item["id"])
    expected = {row["notes"] for row in rows}
    missing = sorted(note for note in expected if not by_note[note])
    ambiguous = {note: by_note[note] for note in sorted(expected) if len(by_note[note]) > 1}
    retained = {item_id for note in expected for item_id in by_note[note]}
    removed = {item["id"] for item in state["items"]} - retained
    references = state["pdf_links"] + [
        {"postventa_item_id": row["postventa_item_id"], "document_id": row["source_document_id"]}
        for row in state["causes"] if row["source_document_id"] is not None
    ]
    candidates = {row["document_id"] for row in references if row["postventa_item_id"] in removed}
    shared = {row["document_id"] for row in references if row["postventa_item_id"] in retained}
    document_ids = candidates - shared
    documents = [row for row in state["documents"] if row["id"] in document_ids]
    # A bucket/key reused by any other document must also remain available.
    protected_keys = {(row["bucket"], row["object_key"]) for row in state["documents"] if row["id"] not in document_ids}
    objects = [
        {"document_id": row["id"], "bucket": row["bucket"], "key": row["object_key"], "content_hash": row["content_hash"]}
        for row in documents if (row["bucket"], row["object_key"]) not in protected_keys
    ]
    reconciled = {row["postventa_item_id"] for row in state["causes"]} & retained
    return {
        "target_items": len(rows), "current_items": len(state["items"]),
        "retained_ids": sorted(retained), "delete_item_ids": sorted(removed),
        "delete_document_ids": sorted(document_ids), "preserved_shared_document_ids": sorted(candidates & shared),
        "storage_objects": objects, "missing_notes": missing, "ambiguous_notes": ambiguous,
        "deleted_cause_links": sum(row["postventa_item_id"] in removed for row in state["causes"]),
        "deleted_pdf_links": sum(row["postventa_item_id"] in removed for row in state["pdf_links"]),
        "projected_reconciled": len(reconciled), "projected_pending": len(retained) - len(reconciled),
        "apply_ready": not missing and not ambiguous and len(retained) == len(rows),
    }


def reviewed_report(db, source: Path, cleaned_path: Path) -> dict:
    original, rows, source_hash = load_source(source)
    state = snapshot(db)
    return {
        "version": VERSION, "kind": "prune-preview", "created_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": source_hash, "source_rows": len(original["rows"]),
        "cleaned_json": str(cleaned_path.resolve()), "cleaned_sha256": digest({"rows": rows}),
        "database_identity": identity(db), "state_sha256": digest(state),
        "plan": plan_deletions(state, rows), "snapshot": state,
    }


def log_plan(plan: dict) -> None:
    logger.info(
        "Pruning: current=%s target=%s delete_items=%s delete_documents=%s delete_objects=%s "
        "reconciled=%s pending=%s apply_ready=%s",
        plan["current_items"], plan["target_items"], len(plan["delete_item_ids"]),
        len(plan["delete_document_ids"]), len(plan["storage_objects"]),
        plan["projected_reconciled"], plan["projected_pending"], plan["apply_ready"],
    )
    if plan["missing_notes"]:
        logger.error("Missing notes: %s", plan["missing_notes"])
    if plan["ambiguous_notes"]:
        logger.error("Ambiguous database notes: %s", plan["ambiguous_notes"])


def validate_review(report: dict, current: dict) -> None:
    if report.get("version") != VERSION or report.get("kind") != "prune-preview":
        raise ValueError("Unsupported dry-run report")
    for field in ("source_sha256", "database_identity", "state_sha256", "cleaned_sha256", "plan"):
        if report.get(field) != current[field]:
            raise ValueError(f"Dry-run report is stale or modified ({field}); generate and review a fresh report")
    if not current["plan"]["apply_ready"]:
        raise ValueError("Missing or ambiguous notes block pruning")


def apply_review(source: Path, report_path: Path, manifest_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cleaned_path = Path(report["cleaned_json"])
    if digest(json.loads(cleaned_path.read_text(encoding="utf-8"))) != report["cleaned_sha256"]:
        raise ValueError("Cleaned JSON changed after preview")
    with SessionLocal() as db:
        with db.begin():
            db.execute(text("SET LOCAL lock_timeout = '15s'"))
            db.execute(text(
                "LOCK TABLE app.postventa_item, app.postventa_item_failure_cause, "
                "app.document_postventa_item, app.document, app.document_outbox_event "
                "IN SHARE ROW EXCLUSIVE MODE"
            ))
            current = reviewed_report(db, source, cleaned_path)
            validate_review(report, current)
            plan = current["plan"]
            log_plan(plan)
            manifest = dict(current, kind="prune-recovery", phase="prepared", cleanup=[])
            manifest["recovery_checksum"] = recovery_checksum(manifest)
            # Persist recovery data before the destructive transaction commits.
            write_new(manifest_path, manifest)
            if plan["delete_item_ids"]:
                db.execute(delete(PostventaItem).where(PostventaItem.id.in_(plan["delete_item_ids"])))
            if plan["delete_document_ids"]:
                db.execute(delete(Document).where(Document.id.in_(plan["delete_document_ids"])))
            actual = db.execute(select(PostventaItem.id, PostventaItem.notes)).all()
            _, source_rows, latest_hash = load_source(source)
            if latest_hash != current["source_sha256"]:
                raise ValueError("Source JSON changed during apply")
            expected_notes = {row["notes"] for row in source_rows}
            if len(actual) != plan["target_items"] or Counter(note.strip() for _, note in actual) != Counter(expected_notes):
                raise ValueError("Final item count or note set differs from the cleaned JSON")
    invalidate_dashboard_summary()
    manifest["phase"] = "database_committed"
    update_manifest(manifest_path, manifest)
    logger.info("Database pruning committed; recovery manifest: %s", manifest_path)
    resume_cleanup(manifest_path)


def resume_cleanup(path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or manifest.get("kind") != "prune-recovery":
        raise ValueError("Unsupported recovery manifest")
    if manifest.get("recovery_checksum") != recovery_checksum(manifest):
        raise ValueError("Recovery manifest deletion plan or snapshot was modified")
    with SessionLocal() as db:
        if identity(db) != manifest["database_identity"]:
            raise ValueError("Recovery manifest belongs to another database/storage environment")
        # A crash between commit and manifest update is resolved by checking DB state.
        item_ids = set(db.scalars(select(PostventaItem.id)))
        document_ids = set(db.scalars(select(Document.id)))
        plan = manifest["plan"]
        if item_ids & set(plan["delete_item_ids"]) or document_ids & set(plan["delete_document_ids"]):
            raise ValueError("Database deletions are not complete; refusing storage cleanup")
        current_objects = set(db.execute(select(Document.bucket, Document.object_key)).all())
    invalidate_dashboard_summary()
    results = {(row["bucket"], row["key"]): row for row in manifest["cleanup"]}
    failures = 0
    try:
        client = s3_client() if plan["storage_objects"] else None
    except Exception as exc:
        manifest["phase"] = "storage_pending"
        update_manifest(path, manifest)
        raise ValueError(f"Database pruning committed; storage setup failed; resume using {path}") from exc
    for obj in plan["storage_objects"]:
        key = (obj["bucket"], obj["key"])
        if results.get(key, {}).get("status") == "deleted":
            continue
        result = dict(obj)
        try:
            if key in current_objects:
                raise ValueError("Storage object is referenced by a current document")
            # Use the recorded bucket, rather than the configured default bucket.
            try:
                response = client.get_object(Bucket=obj["bucket"], Key=obj["key"])
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                    raise
            else:
                body = response["Body"]
                content_hash = hashlib.sha256()
                try:
                    for chunk in iter(lambda: body.read(65536), b""):
                        content_hash.update(chunk)
                finally:
                    body.close()
                if content_hash.hexdigest() != obj["content_hash"]:
                    raise ValueError("Stored PDF content differs from the reviewed document hash")
                client.delete_object(Bucket=obj["bucket"], Key=obj["key"])
            result["status"] = "deleted"
        except Exception as exc:
            failures += 1
            result.update(status="failed", error=str(exc))
            logger.error("PDF cleanup failed for %s/%s: %s", *key, exc)
        results[key] = result
        manifest["cleanup"] = list(results.values())
        update_manifest(path, manifest)
    manifest["phase"] = "storage_pending" if failures else "complete"
    update_manifest(path, manifest)
    if failures:
        raise ValueError(f"Database pruning committed; {failures} PDFs need --resume-cleanup {path}")
    logger.info("Pruning complete: retained=%s removed=%s PDF_objects_deleted=%s", plan["target_items"], len(plan["delete_item_ids"]), len(results))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", nargs="?", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--resume-cleanup", type=Path, metavar="MANIFEST")
    parser.add_argument("--report", type=Path, help="new preview report or reviewed report for apply")
    parser.add_argument("--cleaned-json", type=Path, help="new cleaned JSON output, required for dry-run")
    parser.add_argument("--manifest", type=Path, help="new durable recovery manifest, required for apply")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.resume_cleanup:
            if args.json_file or args.report or args.cleaned_json or args.manifest:
                parser.error("--resume-cleanup takes only a manifest")
            resume_cleanup(args.resume_cleanup)
            return
        if not args.json_file or not args.report:
            parser.error("json_file and --report are required")
        if args.dry_run:
            if not args.cleaned_json or args.manifest:
                parser.error("--dry-run requires --cleaned-json and does not accept --manifest")
            if args.cleaned_json.resolve() == args.report.resolve():
                parser.error("--report and --cleaned-json must use different paths")
            for output in (args.cleaned_json, args.report):
                if output.exists():
                    raise ValueError(f"Output already exists: {output}; use a new filename")
            # One consistent snapshot, even while the application is running.
            with SessionLocal() as db, db.begin():
                db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                report = reviewed_report(db, args.json_file, args.cleaned_json)
            _, rows, _ = load_source(args.json_file)
            if hashlib.sha256(args.json_file.read_bytes()).hexdigest() != report["source_sha256"]:
                raise ValueError("Source JSON changed during preview")
            write_new(args.cleaned_json, {"rows": rows})
            write_new(args.report, report)
            log_plan(report["plan"])
            if not report["plan"]["apply_ready"]:
                raise SystemExit(1)
        else:
            if not args.manifest or args.cleaned_json:
                parser.error("--apply requires --manifest and does not accept --cleaned-json")
            apply_review(args.json_file, args.report, args.manifest)
    except (ValueError, OSError) as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
