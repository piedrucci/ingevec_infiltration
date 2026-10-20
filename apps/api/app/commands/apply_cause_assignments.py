"""Assign causes to one group/category and replace item causes from the exported JSON (dry-run first).

Workflow (reports are private business data and are never overwritten):
  --dry-run --report <new>                                  plan against the current database
  --apply --reviewed-report <dry-run report> --report <new> apply only if the database is unchanged
  --rollback <applied report> --report <new>                undo an apply if nothing changed since
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (FailureCause, FailureCauseAlias, FailureCauseCategory, FailureCauseCategoryGroupLink,
                        FailureCauseCategoryLink, FailureCauseGroup, PostventaItem, PostventaItemFailureCause)
from app.services.dashboard_cache import invalidate_dashboard_summary
from app.services.failure_causes import canonical_code, normalized_alias

LOCKED_TABLES = (
    "app.postventa_item, app.postventa_item_failure_cause, app.failure_cause, app.failure_cause_alias, "
    "app.failure_cause_category, app.failure_cause_category_link, app.failure_cause_group, "
    "app.failure_cause_category_group_link"
)


@dataclass
class Snapshot:
    items: dict[int, dict[str, Any]]
    groups: dict[int, dict[str, Any]]
    categories: dict[int, dict[str, Any]]
    junction: set[tuple[int, int]]
    causes: dict[int, dict[str, Any]]
    aliases: dict[str, int]
    links: dict[int, dict[int, dict[str, Any]]]

    def fingerprint(self) -> str:
        payload = {
            "items": self.items, "groups": self.groups, "categories": self.categories,
            "junction": sorted(self.junction), "causes": self.causes, "aliases": self.aliases,
            "links": {item: dict(sorted(causes.items())) for item, causes in sorted(self.links.items())},
        }
        encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass
class Plan:
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_matches: list[str] = field(default_factory=list)
    group_updates: list[dict[str, Any]] = field(default_factory=list)
    creations: list[dict[str, Any]] = field(default_factory=list)
    retirements: list[dict[str, Any]] = field(default_factory=list)
    item_changes: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


def load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError("The JSON root must contain a 'rows' array")
    rows, seen = [], set()
    for number, row in enumerate(payload["rows"], start=1):
        if not isinstance(row, dict) or not isinstance(row.get("notes"), str) or not row["notes"].strip():
            raise ValueError(f"Row {number} needs non-empty notes")
        if not isinstance(row.get("project_id"), str) or not row["project_id"].strip():
            raise ValueError(f"Row {number} needs a project_id string")
        causes = row.get("associated_causes")
        if not isinstance(causes, list):
            raise ValueError(f"Row {number} associated_causes must be an array")
        for cause in causes:
            if (not isinstance(cause, dict) or not all(isinstance(cause.get(key), str) and cause[key].strip() for key in ("category", "cause"))
                    or not (cause.get("group") is None or isinstance(cause["group"], str) and cause["group"].strip())):
                raise ValueError(f"Row {number} has an invalid association: {cause!r}")
        notes = row["notes"].strip()
        if notes in seen:
            raise ValueError(f"Duplicate notes in JSON: {notes}")
        seen.add(notes)
        rows.append({"project_id": row["project_id"].strip(), "notes": notes, "associated_causes": [
            {"group": c["group"].strip() if c.get("group") else None, "category": c["category"].strip(), "cause": c["cause"].strip()}
            for c in causes]})
    return rows


def load_snapshot(db: Session) -> Snapshot:
    items = {i: {"project_id": p, "notes": n.strip(), "primary": f}
             for i, p, n, f in db.execute(select(PostventaItem.id, PostventaItem.project_id, PostventaItem.notes, PostventaItem.failure_cause_id))}
    groups = {g.id: {"code": g.code, "name": g.display_name_es} for g in db.scalars(select(FailureCauseGroup))}
    categories = {c.id: {"code": c.code, "name": c.display_name_es, "active": c.is_active} for c in db.scalars(select(FailureCauseCategory))}
    junction = {(c, g) for c, g in db.execute(select(FailureCauseCategoryGroupLink.category_id, FailureCauseCategoryGroupLink.group_id))}
    causes = {c.id: {"code": c.code, "name": c.display_name_es, "description": c.description_es, "active": c.is_active,
                     "category_id": None, "group_id": None} for c in db.scalars(select(FailureCause))}
    for link in db.scalars(select(FailureCauseCategoryLink)):
        causes[link.failure_cause_id].update(category_id=link.category_id, group_id=link.group_id)
    aliases = {a: c for c, a in db.execute(select(FailureCauseAlias.failure_cause_id, FailureCauseAlias.normalized_alias))}
    links: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    for link in db.scalars(select(PostventaItemFailureCause)):
        links[link.postventa_item_id][link.failure_cause_id] = _provenance(link)
    return Snapshot(items, groups, categories, junction, causes, aliases, dict(links))


def _provenance(link: PostventaItemFailureCause) -> dict[str, Any]:
    return {"assignment_source": link.assignment_source, "assigned_at": link.assigned_at.isoformat(),
            "assigned_by": link.assigned_by, "source_document_id": link.source_document_id}


def _lookup(entries: dict[int, dict[str, Any]], label: str) -> list[int]:
    key = normalized_alias(label)
    return [i for i, e in entries.items() if key in (normalized_alias(e["name"]), normalized_alias(e["code"]))]


def plan_assignments(snap: Snapshot, rows: list[dict[str, Any]]) -> Plan:
    """Compute the full change set without touching the database."""
    plan = Plan()
    by_note: dict[str, list[int]] = defaultdict(list)
    for item_id, item in snap.items.items():
        by_note[item["notes"]].append(item_id)
    codes = {c["code"] for c in snap.causes.values()}
    aliases = dict(snap.aliases)
    matched_items: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        ids = by_note.get(row["notes"], [])
        if not ids:
            plan.warnings.append(f"unmatched note skipped: {row['notes']}")
            continue
        if len(ids) > 1:
            plan.blockers.append(f"note matches {len(ids)} items: {row['notes']}")
            continue
        if snap.items[ids[0]]["project_id"] != row["project_id"]:
            plan.blockers.append(f"project mismatch for note (JSON {row['project_id']}, DB {snap.items[ids[0]]['project_id']}): {row['notes']}")
            continue
        matched_items[ids[0]] = row["associated_causes"]

    # Resolve every association to (category, group, family of candidate causes).
    families: dict[tuple, dict[str, Any]] = {}
    item_requests: dict[int, list[tuple[tuple, int | None]]] = defaultdict(list)
    active = {i: c for i, c in snap.causes.items() if c["active"] and c["category_id"] is not None}
    for item_id, associations in matched_items.items():
        for assoc in associations:
            group_id = None
            if assoc["group"]:
                found = _lookup(snap.groups, assoc["group"])
                if len(found) != 1:
                    plan.blockers.append(f"group not found or ambiguous: {assoc['group']}")
                    continue
                group_id = found[0]
            found = _lookup(snap.categories, assoc["category"])
            if len(found) != 1 or not snap.categories[found[0]]["active"]:
                plan.blockers.append(f"category not found, ambiguous or inactive: {assoc['category']}")
                continue
            category_id = found[0]
            category = snap.categories[category_id]
            if category["name"] != assoc["category"]:
                plan.normalized_matches.append(f"category {assoc['category']!r} -> {category['name']!r}")
            if group_id is not None and (category_id, group_id) not in snap.junction:
                plan.blockers.append(f"group {snap.groups[group_id]['name']} does not contain category {category['name']}")
                continue
            label = normalized_alias(assoc["cause"])
            candidates = {i for i, c in active.items() if c["category_id"] == category_id and normalized_alias(c["name"]) == label}
            for alias in (label, normalized_alias(f"{category['name']} · {assoc['cause']}")):
                owner = snap.aliases.get(alias)
                if owner in active and active[owner]["category_id"] == category_id:
                    candidates.add(owner)
            key = (category_id, frozenset(candidates)) if candidates else (category_id, label)
            family = families.setdefault(key, {"category_id": category_id, "label": assoc["cause"], "candidates": sorted(candidates), "groups": set()})
            family["groups"].add(group_id)
            for cause_id in candidates:
                if snap.causes[cause_id]["name"] != assoc["cause"]:
                    plan.normalized_matches.append(f"cause {assoc['cause']!r} -> {snap.causes[cause_id]['name']!r}")
            item_requests[item_id].append((key, group_id))

    # Decide the target cause code for every (family, group).
    targets: dict[tuple[tuple, int | None], str] = {}
    split_origin: dict[str, int] = {}

    def create(name: str, category_id: int, group_id: int | None, code: str, alias_label: str, split_from: int | None, description=None):
        alias = normalized_alias(alias_label)
        if code in codes or len(code) > 100:
            plan.blockers.append(f"cause code already exists or is too long: {code}")
        if alias in aliases:
            plan.blockers.append(f"alias already exists: {alias}")
        codes.add(code)
        aliases[alias] = -1
        plan.creations.append({"code": code, "name": name.strip(), "description": description, "category_id": category_id,
                               "group_id": group_id, "alias": alias, "split_from": split_from})
        if split_from is not None:
            split_origin[code] = split_from

    for key, family in families.items():
        category_id, label = family["category_id"], family["label"]
        category = snap.categories[category_id]
        requested = sorted(g for g in family["groups"] if g is not None)
        wants_none = None in family["groups"]
        if wants_none and requested:
            plan.blockers.append(f"{category['name']} · {label}: used both with and without a group")
            continue
        existing = [snap.causes[i] | {"id": i} for i in family["candidates"]]
        ungrouped = [c for c in existing if c["group_id"] is None]
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for cause in existing:
            if cause["group_id"] is not None:
                grouped[cause["group_id"]].append(cause)
        if any(len(v) > 1 for v in grouped.values()) or len(ungrouped) > 1:
            plan.blockers.append(f"{category['name']} · {label}: several active causes for the same group")
            continue
        group_code = lambda g: snap.groups[g]["code"]
        if len(existing) == 1 and ungrouped:
            cause = ungrouped[0]
            if len(requested) == 1:
                plan.group_updates.append({"cause_id": cause["id"], "code": cause["code"], "group_id": requested[0]})
                targets[(key, requested[0])] = cause["code"]
            elif len(requested) > 1:
                plan.retirements.append({"cause_id": cause["id"], "code": cause["code"], "category_id": category_id})
                for g in requested:
                    code = f"{cause['code']}__{group_code(g)}"
                    create(cause["name"], category_id, g, code, f"{snap.groups[g]['name']} · {category['name']} · {cause['name']}",
                           cause["id"], cause["description"])
                    targets[(key, g)] = code
            else:
                targets[(key, None)] = cause["code"]
            continue
        base = canonical_code(label)
        if not existing:
            if len(requested) <= 1:
                code = base if base not in codes else f"{base}__{category['code']}"
                create(label, category_id, requested[0] if requested else None, code, f"{category['name']} · {label}", None)
                targets[(key, requested[0] if requested else None)] = code
            else:
                for g in requested:
                    code = f"{base}__{group_code(g)}"
                    create(label, category_id, g, code, f"{snap.groups[g]['name']} · {category['name']} · {label}", None)
                    targets[(key, g)] = code
            continue
        # Already grouped family (e.g. a previous run): reuse each group's cause, create missing groups.
        for g in requested:
            if grouped.get(g):
                targets[(key, g)] = grouped[g][0]["code"]
            else:
                code = f"{base}__{group_code(g)}"
                create(label, category_id, g, code, f"{snap.groups[g]['name']} · {category['name']} · {label}", None)
                targets[(key, g)] = code
        if wants_none:
            if ungrouped:
                targets[(key, None)] = ungrouped[0]["code"]
            else:
                plan.blockers.append(f"{category['name']} · {label}: no unassigned cause for associations without a group")

    # Item cause replacement (JSON is the source of truth for matched items).
    code_to_id = {c["code"]: i for i, c in snap.causes.items()}
    retired_ids = {r["cause_id"] for r in plan.retirements}
    for item_id in sorted(matched_items):
        desired = sorted({targets[(key, g)] for key, g in item_requests.get(item_id, []) if (key, g) in targets})
        before = snap.links.get(item_id, {})
        after, kept, consumed = [], set(), set()
        for code in desired:
            cause_id = code_to_id.get(code)
            if cause_id in before:
                after.append({"code": code, "action": "keep", "from_cause_id": cause_id})
                kept.add(cause_id)
            elif split_origin.get(code) in before and split_origin[code] not in consumed:
                # The split cause's link moves to its group cause with the original provenance.
                after.append({"code": code, "action": "repoint", "from_cause_id": split_origin[code]})
                consumed.add(split_origin[code])
            else:
                after.append({"code": code, "action": "add", "from_cause_id": None})
        removed = sorted(set(before) - kept)
        stale_primary = snap.items[item_id]["primary"] != (min(before) if before else None)
        if removed or stale_primary or any(a["action"] != "keep" for a in after):
            plan.item_changes.append({"item_id": item_id, "remove": removed, "after": after})
    for item_id, causes in snap.links.items():
        if item_id not in matched_items and (set(causes) & retired_ids or snap.items[item_id]["primary"] in retired_ids):
            plan.blockers.append(f"item {item_id} is not in the JSON but uses a cause that would be split")

    assigned = {c for c, info in active.items() if info["group_id"] is not None}
    referenced = {i for f in families.values() for i in f["candidates"]}
    unreferenced = sorted(active[i]["code"] for i in set(active) - referenced - assigned)
    if unreferenced:
        plan.warnings.append(f"active causes not referenced by the JSON stay without a group: {', '.join(unreferenced)}")
    plan.normalized_matches = sorted(set(plan.normalized_matches))
    plan.summary = {
        "json_rows": len(rows), "matched_items": len(matched_items),
        "unmatched_rows": sum(1 for w in plan.warnings if w.startswith("unmatched note")),
        "database_items_not_in_json": len(set(snap.items) - set(matched_items)),
        "causes_assigned_group": len(plan.group_updates),
        "causes_split": len(plan.retirements),
        "causes_created_by_split": sum(1 for c in plan.creations if c["split_from"] is not None),
        "causes_created_new": sum(1 for c in plan.creations if c["split_from"] is None),
        "items_changed": len(plan.item_changes),
        "links_added": sum(1 for c in plan.item_changes for a in c["after"] if a["action"] == "add"),
        "links_repointed": sum(1 for c in plan.item_changes for a in c["after"] if a["action"] == "repoint"),
        "links_removed": sum(len(c["remove"]) - sum(1 for a in c["after"] if a["action"] == "repoint") for c in plan.item_changes),
        "blockers": len(plan.blockers),
    }
    return plan


def apply_plan(db: Session, snap: Snapshot, plan: Plan, source_label: str) -> dict[str, Any]:
    """Write the plan and return the rollback manifest (state before and after)."""
    created: dict[str, int] = {}
    for spec in plan.creations:
        cause = FailureCause(code=spec["code"], display_name_es=spec["name"], description_es=spec["description"], is_active=True)
        db.add(cause)
        db.flush()
        created[spec["code"]] = cause.id
        db.add(FailureCauseCategoryLink(failure_cause_id=cause.id, category_id=spec["category_id"], group_id=spec["group_id"]))
        db.add(FailureCauseAlias(failure_cause_id=cause.id, normalized_alias=spec["alias"]))
    for spec in plan.group_updates:
        db.execute(update(FailureCauseCategoryLink).where(FailureCauseCategoryLink.failure_cause_id == spec["cause_id"]).values(group_id=spec["group_id"]))
    code_to_id = {c["code"]: i for i, c in snap.causes.items()} | created
    before_items = {}
    for change in plan.item_changes:
        item_id = change["item_id"]
        before_items[item_id] = {"links": {str(k): v for k, v in snap.links.get(item_id, {}).items()}, "primary": snap.items[item_id]["primary"]}
        db.execute(delete(PostventaItemFailureCause).where(PostventaItemFailureCause.postventa_item_id == item_id,
                                                           PostventaItemFailureCause.failure_cause_id.in_(change["remove"])))
        for target in change["after"]:
            if target["action"] == "keep":
                continue
            provenance = (snap.links[item_id][target["from_cause_id"]] if target["action"] == "repoint"
                          else {"assignment_source": "MIGRATED", "assigned_at": None, "assigned_by": source_label, "source_document_id": None})
            link = PostventaItemFailureCause(postventa_item_id=item_id, failure_cause_id=code_to_id[target["code"]],
                                             assignment_source=provenance["assignment_source"], assigned_by=provenance["assigned_by"],
                                             source_document_id=provenance["source_document_id"])
            if provenance["assigned_at"]:
                link.assigned_at = datetime.fromisoformat(provenance["assigned_at"])
            db.add(link)
    db.flush()
    for spec in plan.retirements:
        db.execute(delete(FailureCauseCategoryLink).where(FailureCauseCategoryLink.failure_cause_id == spec["cause_id"]))
        db.execute(update(FailureCause).where(FailureCause.id == spec["cause_id"]).values(is_active=False))
    after_items = {}
    for change in plan.item_changes:
        item_id = change["item_id"]
        links = {link.failure_cause_id: _provenance(link) for link in db.scalars(
            select(PostventaItemFailureCause).where(PostventaItemFailureCause.postventa_item_id == item_id))}
        primary = min(links) if links else None
        db.execute(update(PostventaItem).where(PostventaItem.id == item_id).values(failure_cause_id=primary))
        after_items[item_id] = {"links": {str(k): v for k, v in links.items()}, "primary": primary}
    db.flush()
    return {
        "created": created,
        "group_updates": [{"cause_id": s["cause_id"], "group_before": snap.causes[s["cause_id"]]["group_id"], "group_after": s["group_id"]}
                          for s in plan.group_updates],
        "retired": [{"cause_id": s["cause_id"], "category_id": snap.causes[s["cause_id"]]["category_id"],
                     "group_id": snap.causes[s["cause_id"]]["group_id"]} for s in plan.retirements],
        "items_before": before_items,
        "items_after": after_items,
    }


def rollback_manifest(db: Session, manifest: dict[str, Any]) -> dict[str, int]:
    """Restore the pre-apply state, refusing if anything changed after the apply."""
    snap = load_snapshot(db)
    created = {int(i) for i in manifest["created"].values()}
    for item_id, state in manifest["items_after"].items():
        current = snap.links.get(int(item_id), {})
        if {str(k): v for k, v in current.items()} != state["links"] or snap.items[int(item_id)]["primary"] != state["primary"]:
            raise ValueError(f"Item {item_id} changed after apply; refusing rollback")
    changed_items = {int(i) for i in manifest["items_after"]}
    for item_id, causes in snap.links.items():
        if item_id not in changed_items and set(causes) & created:
            raise ValueError(f"Item {item_id} uses a created cause outside the apply; refusing rollback")
    for spec in manifest["group_updates"]:
        if snap.causes[spec["cause_id"]]["group_id"] != spec["group_after"]:
            raise ValueError(f"Group of cause {spec['cause_id']} changed after apply; refusing rollback")
    for spec in manifest["retired"]:
        if snap.causes[spec["cause_id"]]["active"] or snap.causes[spec["cause_id"]]["category_id"] is not None:
            raise ValueError(f"Retired cause {spec['cause_id']} changed after apply; refusing rollback")
    if any(i not in snap.causes or not snap.causes[i]["active"] for i in created):
        raise ValueError("A created cause is missing or inactive; refusing rollback")

    for item_id, state in manifest["items_before"].items():
        db.execute(delete(PostventaItemFailureCause).where(PostventaItemFailureCause.postventa_item_id == int(item_id)))
    db.flush()
    for spec in manifest["retired"]:
        db.execute(update(FailureCause).where(FailureCause.id == spec["cause_id"]).values(is_active=True))
        db.add(FailureCauseCategoryLink(failure_cause_id=spec["cause_id"], category_id=spec["category_id"], group_id=spec["group_id"]))
    for spec in manifest["group_updates"]:
        db.execute(update(FailureCauseCategoryLink).where(FailureCauseCategoryLink.failure_cause_id == spec["cause_id"]).values(group_id=spec["group_before"]))
    db.flush()
    for item_id, state in manifest["items_before"].items():
        for cause_id, provenance in state["links"].items():
            db.add(PostventaItemFailureCause(postventa_item_id=int(item_id), failure_cause_id=int(cause_id),
                                             assignment_source=provenance["assignment_source"], assigned_by=provenance["assigned_by"],
                                             source_document_id=provenance["source_document_id"],
                                             assigned_at=datetime.fromisoformat(provenance["assigned_at"])))
        db.execute(update(PostventaItem).where(PostventaItem.id == int(item_id)).values(failure_cause_id=state["primary"]))
    db.flush()
    if created:
        db.execute(delete(FailureCauseAlias).where(FailureCauseAlias.failure_cause_id.in_(created)))
        db.execute(delete(FailureCauseCategoryLink).where(FailureCauseCategoryLink.failure_cause_id.in_(created)))
        db.execute(delete(FailureCause).where(FailureCause.id.in_(created)))
    db.flush()
    return {"items_restored": len(manifest["items_before"]), "causes_removed": len(created),
            "causes_reactivated": len(manifest["retired"]), "groups_reset": len(manifest["group_updates"])}


def _write(report, audit: dict[str, Any]) -> None:
    report.seek(0)
    json.dump(audit, report, ensure_ascii=False, indent=2, default=str)
    report.truncate()
    report.flush()
    os.fsync(report.fileno())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("json_file", type=Path, nargs="?")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", type=Path, metavar="APPLIED_REPORT")
    parser.add_argument("--reviewed-report", type=Path, help="Dry-run report reviewed before --apply")
    parser.add_argument("--report", type=Path, required=True, help="New private report (never overwritten)")
    args = parser.parse_args()
    if (args.dry_run or args.apply) and args.json_file is None:
        parser.error("json_file is required for --dry-run and --apply")
    if args.apply and args.reviewed_report is None:
        parser.error("--apply requires --reviewed-report")

    audit: dict[str, Any] = {"status": "pending", "generated_at": datetime.now(timezone.utc).isoformat()}
    if args.rollback:
        applied = json.loads(args.rollback.read_text(encoding="utf-8"))
        if applied.get("status") != "applied":
            raise SystemExit("Rollback needs a report with status 'applied'")
        audit.update(mode="rollback", applied_report_sha256=hashlib.sha256(args.rollback.read_bytes()).hexdigest())
    else:
        rows = load_rows(args.json_file)
        audit.update(mode="apply" if args.apply else "dry_run", input=str(args.json_file),
                     input_sha256=hashlib.sha256(args.json_file.read_bytes()).hexdigest())
        if args.apply:
            reviewed = json.loads(args.reviewed_report.read_text(encoding="utf-8"))
            if reviewed.get("status") != "dry_run" or reviewed.get("input_sha256") != audit["input_sha256"]:
                raise SystemExit("Reviewed report is not a dry-run of this exact JSON file")
            if reviewed["plan"]["blockers"]:
                raise SystemExit("Reviewed dry-run has blockers")

    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as report:
        _write(report, audit)
        with SessionLocal() as db, db.begin():
            if args.dry_run:
                db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            else:
                # Block concurrent item and catalog edits until validation and changes commit.
                db.execute(text("SET LOCAL lock_timeout = '15s'"))
                db.execute(text(f"LOCK TABLE {LOCKED_TABLES} IN SHARE ROW EXCLUSIVE MODE"))
            if args.rollback:
                audit["summary"] = rollback_manifest(db, applied["manifest"])
            else:
                snap = load_snapshot(db)
                plan = plan_assignments(snap, rows)
                audit.update(snapshot_sha256=snap.fingerprint(), plan=asdict(plan))
                if args.apply:
                    if snap.fingerprint() != reviewed["snapshot_sha256"] or asdict(plan) != reviewed["plan"]:
                        raise SystemExit("Database changed since the reviewed dry-run; run a new dry-run and review it")
                    audit["manifest"] = apply_plan(db, snap, plan, f"cause_assignments:{args.json_file.name}"[:255])
        audit["status"] = {"dry_run": "dry_run", "apply": "applied", "rollback": "rolled_back"}[audit["mode"]]
        _write(report, audit)
    if not args.dry_run:
        invalidate_dashboard_summary()
    summary = audit.get("summary") or audit["plan"]["summary"]
    print(json.dumps({"status": audit["status"], "report": str(args.report), **summary}, ensure_ascii=False, indent=2))
    if args.dry_run and audit["plan"]["blockers"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
