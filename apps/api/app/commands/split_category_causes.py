"""Split shared causes using a completed private assignment review (dry-run by default)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select, text

from app.db import SessionLocal
from app.models import (FailureCause, FailureCauseAlias, FailureCauseCategory,
                        FailureCauseCategoryLink, PostventaItem, PostventaItemFailureCause, Project)
from app.services.dashboard_cache import invalidate_dashboard_summary
from app.services.failure_causes import normalized_alias


def load_review(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    catalog = data.get("catalog", [])
    rows = data.get("rows", [])
    if not catalog or not rows:
        raise ValueError("Review must contain catalog and rows")
    causes = {c["id"]: c for c in catalog}
    if len(causes) != len(catalog):
        raise ValueError("Duplicate catalog cause")
    keys = set()
    for row in rows:
        key = (row["item_id"], row["current_cause_id"])
        if key in keys:
            raise ValueError(f"Duplicate assignment: {key}")
        keys.add(key)
        cause = causes[row["current_cause_id"]]
        if (row["current_cause_code"] != cause["code"] or
                row["current_cause_name"] != cause["name"] or
                row["available_categories"] != cause["categories"]):
            raise ValueError(f"Changed catalog reference for item {row['item_id']}")
        allowed = {c["code"] for c in cause["categories"]}
        codes = row.get("selected_category_codes")
        if (not isinstance(codes, list) or not codes or
                any(not isinstance(c, str) or c not in allowed for c in codes) or
                len(codes) != len(set(codes))):
            raise ValueError(f"Missing, duplicate or invalid category selection for item {row['item_id']}")
    return data


def validate_database(db, data):
    """Require complete coverage and an unchanged snapshot before any mutation."""
    causes = {}
    categories = {}
    for entry in data["catalog"]:
        cause = db.get(FailureCause, entry["id"])
        if cause is None or (cause.code, cause.display_name_es, cause.is_active) != (entry["code"], entry["name"], True):
            raise ValueError(f"Source cause changed or already retired: {entry['code']}")
        actual = db.scalars(select(FailureCauseCategory).join(
            FailureCauseCategoryLink, FailureCauseCategoryLink.category_id == FailureCauseCategory.id
        ).where(FailureCauseCategoryLink.failure_cause_id == cause.id)).all()
        expected = {(c["id"], c["code"], c["name"]) for c in entry["categories"]}
        if {(c.id, c.code, c.display_name_es) for c in actual} != expected or len(actual) < 2:
            raise ValueError(f"Category mapping changed for {cause.code}")
        for category in actual:
            if not category.is_active:
                raise ValueError(f"Inactive target category: {category.code}")
            code = f"{cause.code}__{category.code}"
            if len(code) > 100 or db.scalar(select(FailureCause.id).where(FailureCause.code == code)):
                raise ValueError(f"Destination code already exists or is too long: {code}")
            alias = normalized_alias(f"{category.display_name_es} · {cause.display_name_es}")
            if db.scalar(select(FailureCauseAlias.id).where(FailureCauseAlias.normalized_alias == alias)):
                raise ValueError(f"Destination alias already exists: {alias}")
            categories[category.code] = category
        causes[cause.id] = cause
    links = db.scalars(select(PostventaItemFailureCause).where(
        PostventaItemFailureCause.failure_cause_id.in_(causes))).all()
    by_key = {(l.postventa_item_id, l.failure_cause_id): l for l in links}
    reviewed = {(r["item_id"], r["current_cause_id"]) for r in data["rows"]}
    if set(by_key) != reviewed:
        raise ValueError("Review coverage differs from current shared-cause assignments; regenerate/review the missing items")
    legacy_ids = set(db.scalars(select(PostventaItem.id).where(PostventaItem.failure_cause_id.in_(causes))))
    if legacy_ids - {r["item_id"] for r in data["rows"]}:
        raise ValueError("Legacy primary-cause references exist outside reviewed items")
    item_ids = {r["item_id"] for r in data["rows"]}
    items = {i.id: i for i in db.scalars(select(PostventaItem).where(PostventaItem.id.in_(item_ids)))}
    projects = {p.id: p for p in db.scalars(select(Project).where(Project.id.in_({r["project_id"] for r in data["rows"]})))}
    actual_by_item = {}
    for item_id, cause in db.execute(select(PostventaItemFailureCause.postventa_item_id, FailureCause).join(
        FailureCause, FailureCause.id == PostventaItemFailureCause.failure_cause_id
    ).where(PostventaItemFailureCause.postventa_item_id.in_(item_ids))):
        actual_by_item.setdefault(item_id, set()).add((cause.id, cause.code, cause.display_name_es))
    for row in data["rows"]:
        item = items.get(row["item_id"])
        project = projects.get(row["project_id"])
        if (item is None or project is None or str(item.public_id) != row["item_public_id"] or
                item.project_id != row["project_id"] or item.notes != row["observation"] or
                project.name != row["project_name"]):
            raise ValueError(f"Item/project snapshot changed: {row['item_id']}")
        if actual_by_item.get(item.id, set()) != {
            (c['id'],c['code'],c['name']) for c in row['all_current_causes']
        }:
            raise ValueError(f"Assigned causes changed for item {item.id}")
        link = by_key[(item.id, row["current_cause_id"])]
        for field in ("assignment_source", "assigned_by", "source_document_id"):
            if getattr(link, field) != row[field]:
                raise ValueError(f"Assignment provenance changed: item {item.id}, {field}")
        if link.assigned_at != datetime.fromisoformat(row["assigned_at"]):
            raise ValueError(f"Assignment timestamp changed for item {item.id}")
    return causes, categories, by_key


def execute_review(db, data, *, apply=False):
    if apply:
        # Block concurrent item edits and catalog changes until validation + replacement commits.
        db.execute(text("SET LOCAL lock_timeout = '15s'"))
        db.execute(text("LOCK TABLE app.project, app.postventa_item, app.postventa_item_failure_cause, "
                        "app.failure_cause, app.failure_cause_alias, app.failure_cause_category, "
                        "app.failure_cause_category_link IN SHARE ROW EXCLUSIVE MODE"))
    causes, categories, links = validate_database(db, data)
    summary = {
        "affected_items": len({r["item_id"] for r in data["rows"]}),
        "replaced_assignments": len(links),
        "new_assignments": sum(len(r["selected_category_codes"]) for r in data["rows"]),
        "retired_causes": len(causes),
        "created_causes": sum(len(c["categories"]) for c in data["catalog"]),
        "destinations": [f"{c['code']}__{cat['code']}" for c in data['catalog'] for cat in c['categories']],
    }
    if not apply:
        return summary
    targets = {}
    for entry in data["catalog"]:
        old = causes[entry["id"]]
        for cat in entry["categories"]:
            category = categories[cat["code"]]
            new = FailureCause(code=f"{old.code}__{category.code}", display_name_es=old.display_name_es,
                               description_es=old.description_es, is_active=True)
            db.add(new)
            db.flush()
            targets[(old.id, category.code)] = new.id
            db.add(FailureCauseCategoryLink(failure_cause_id=new.id, category_id=category.id))
            # Unqualified aliases remain on retired causes: never guess the category from a shared name.
            db.add(FailureCauseAlias(failure_cause_id=new.id,
                                    normalized_alias=normalized_alias(f"{category.display_name_es} · {new.display_name_es}")))
        old.is_active = False
    for row in data["rows"]:
        old = links[(row["item_id"], row["current_cause_id"])]
        for code in row["selected_category_codes"]:
            db.add(PostventaItemFailureCause(
                postventa_item_id=old.postventa_item_id,
                failure_cause_id=targets[(old.failure_cause_id, code)],
                assignment_source=old.assignment_source, assigned_at=old.assigned_at,
                assigned_by=old.assigned_by, source_document_id=old.source_document_id,
            ))
        db.delete(old)
    db.execute(delete(FailureCauseCategoryLink).where(FailureCauseCategoryLink.failure_cause_id.in_(causes)))
    db.flush()
    item_ids = {r["item_id"] for r in data["rows"]}
    primary = {}
    for item_id, cause_id in db.execute(select(PostventaItemFailureCause.postventa_item_id, PostventaItemFailureCause.failure_cause_id).where(PostventaItemFailureCause.postventa_item_id.in_(item_ids))):
        primary[item_id] = min(primary.get(item_id, cause_id), cause_id)
    for item in db.scalars(select(PostventaItem).where(PostventaItem.id.in_(item_ids))):
        item.failure_cause_id = primary[item.id]
    db.flush()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, required=True, help="New private audit file (never overwritten)")
    args = parser.parse_args()
    data = load_review(args.json_file)
    audit = {"status": "pending", "generated_at": datetime.now(timezone.utc).isoformat(),
             "input_sha256": hashlib.sha256(args.json_file.read_bytes()).hexdigest(), "review": data}
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as report:
        # Keep the full pre-change snapshot and decisions even if the process is interrupted.
        json.dump(audit, report, ensure_ascii=False, indent=2)
        report.flush()
        os.fsync(report.fileno())
        with SessionLocal() as db:
            with db.begin():
                if not args.apply:
                    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                summary = execute_review(db, data, apply=args.apply)
        audit.update(status="applied" if args.apply else "dry_run", summary=summary)
        report.seek(0)
        json.dump(audit, report, ensure_ascii=False, indent=2)
        report.truncate()
        report.flush()
        os.fsync(report.fileno())
    if args.apply:
        invalidate_dashboard_summary()
    print(json.dumps({"status": audit['status'], **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
