"""Preview or atomically replace item/cause links from the María Platias JSON."""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import case, delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    ExcelSourceRow,
    FailureCause,
    FailureCauseAlias,
    PostventaItem,
    PostventaItemFailureCause,
)
from app.services.dashboard_cache import invalidate_dashboard_summary
from app.services.failure_causes import normalized_alias


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewSummary:
    source_rows: int
    rows_missing_notes: int
    rows_with_empty_causes: int
    repeated_note_rows: int
    unique_source_notes: int
    database_items: int
    current_link_rows: int
    current_reconciled_items: int
    current_pending_items: int
    legacy_direct_cause_items: int
    resolved_note_groups: int
    unmatched_notes: tuple[str, ...]
    ambiguous_notes: tuple[str, ...]
    ambiguous_note_matches: tuple[str, ...]
    verified_duplicate_note_matches: tuple[str, ...]
    matched_notes_without_causes: tuple[str, ...]
    missing_causes: tuple[str, ...]
    ambiguous_causes: tuple[str, ...]
    normalized_cause_matches: tuple[str, ...]
    planned_link_rows: int
    planned_assignments: tuple[tuple[int, int], ...]
    projected_reconciled_items: int | None
    projected_pending_items: int | None
    apply_ready: bool


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        payload: Any = json.load(source)
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError("The JSON root must contain a 'rows' array")

    rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(payload["rows"], start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Row {row_number} must be an object")
        notes = row.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ValueError(f"Row {row_number} notes must be a string or null")
        causes = row.get("causes")
        if not isinstance(causes, list) or not all(
            isinstance(cause, str) and cause.strip() for cause in causes
        ):
            raise ValueError(f"Row {row_number} causes must be an array of non-empty strings")
        rows.append({
            "notes": notes.strip() if notes and notes.strip() else None,
            "causes": [cause.strip() for cause in causes],
        })
    return rows


def preview_replacement(db: Session, rows: list[dict[str, Any]]) -> PreviewSummary:
    """Calculate a full-replacement preview without writing to the database."""
    source_note_counts: Counter[str] = Counter()
    causes_by_note: dict[str, set[str]] = defaultdict(set)
    cause_sets_by_note: dict[str, list[frozenset[str]]] = defaultdict(list)
    rows_missing_notes = 0
    rows_with_empty_causes = 0
    for row in rows:
        note = row["notes"]
        if note is None:
            rows_missing_notes += 1
            continue
        source_note_counts[note] += 1
        if not row["causes"]:
            rows_with_empty_causes += 1
        causes_by_note[note].update(row["causes"])
        cause_sets_by_note[note].append(frozenset(row["causes"]))

    item_rows = db.execute(
        select(
            PostventaItem.id,
            PostventaItem.notes,
            PostventaItem.failure_cause_id,
            ExcelSourceRow.row_hash,
        ).outerjoin(ExcelSourceRow, ExcelSourceRow.id == PostventaItem.source_row_id)
    ).all()
    items_by_note: dict[str, list[tuple[int, int | None, str | None]]] = defaultdict(list)
    all_item_ids: set[int] = set()
    legacy_direct_cause_items = 0
    for item_id, notes, direct_cause_id, row_hash in item_rows:
        all_item_ids.add(item_id)
        if direct_cause_id is not None:
            legacy_direct_cause_items += 1
        items_by_note[notes.strip()].append((item_id, direct_cause_id, row_hash))

    cause_rows = db.execute(select(FailureCause.id, FailureCause.display_name_es)).all()
    cause_names_by_id = {cause_id: label for cause_id, label in cause_rows}
    causes_by_normalized_label: dict[str, dict[int, str]] = defaultdict(dict)
    for cause_id, label in cause_rows:
        causes_by_normalized_label[normalized_alias(label)][cause_id] = label
    alias_rows = db.execute(
        select(FailureCauseAlias.failure_cause_id, FailureCauseAlias.normalized_alias)
    ).all()
    for cause_id, alias in alias_rows:
        causes_by_normalized_label[normalized_alias(alias)][cause_id] = cause_names_by_id[cause_id]

    source_notes = set(source_note_counts)
    unmatched_notes = tuple(sorted(note for note in source_notes if not items_by_note.get(note)))
    resolved_items_by_note: dict[str, tuple[int, ...]] = {}
    ambiguous_notes_set: set[str] = set()
    verified_duplicate_note_matches: list[str] = []
    for note in source_notes:
        matches = items_by_note.get(note, [])
        if not matches:
            continue
        if len(matches) == 1:
            resolved_items_by_note[note] = (matches[0][0],)
            continue

        source_hashes = [row_hash for _, _, row_hash in matches]
        source_cause_sets = cause_sets_by_note[note]
        same_source_rows = all(source_hashes) and len(set(source_hashes)) == 1
        same_json_causes = (
            source_note_counts[note] > 1
            and len(source_cause_sets) == source_note_counts[note]
            and len(set(source_cause_sets)) == 1
        )
        if same_source_rows and same_json_causes:
            resolved_items_by_note[note] = tuple(sorted(item_id for item_id, _, _ in matches))
            verified_duplicate_note_matches.append(
                f"{note} => item_ids={','.join(map(str, resolved_items_by_note[note]))}"
            )
        else:
            ambiguous_notes_set.add(note)

    ambiguous_notes = tuple(sorted(ambiguous_notes_set))
    ambiguous_note_matches = tuple(
        f"{note} => item_ids={','.join(str(item_id) for item_id, _, _ in sorted(items_by_note[note]))}"
        for note in ambiguous_notes
    )
    matched_notes_without_causes = tuple(sorted(
        note for note, causes in causes_by_note.items()
        if note in resolved_items_by_note and not causes
    ))

    all_cause_labels = {cause for causes in causes_by_note.values() for cause in causes}
    missing_causes = tuple(sorted(
        label for label in all_cause_labels
        if normalized_alias(label) not in causes_by_normalized_label
    ))
    ambiguous_causes = tuple(sorted(
        label for label in all_cause_labels
        if len(causes_by_normalized_label.get(normalized_alias(label), {})) > 1
    ))
    normalized_cause_matches = tuple(sorted({
        f"{label} -> {next(iter(candidates.values()))}"
        for label in all_cause_labels
        if len(candidates := causes_by_normalized_label.get(normalized_alias(label), {})) == 1
        and label != next(iter(candidates.values()))
    }))

    planned_assignments: set[tuple[int, int]] = set()
    matched_cause_errors: set[str] = set(missing_causes) | set(ambiguous_causes)
    for note, item_ids in resolved_items_by_note.items():
        labels = causes_by_note.get(note, set())
        if not labels or any(label in matched_cause_errors for label in labels):
            continue
        for label in labels:
            cause_id = next(iter(causes_by_normalized_label[normalized_alias(label)]))
            planned_assignments.update((item_id, cause_id) for item_id in item_ids)

    current_links = db.execute(
        select(PostventaItemFailureCause.postventa_item_id, PostventaItemFailureCause.failure_cause_id)
    ).all()
    currently_reconciled_ids = {item_id for item_id, _ in current_links}
    can_project = not ambiguous_notes and not missing_causes and not ambiguous_causes
    projected_reconciled = (
        len({item_id for item_id, _ in planned_assignments}) if can_project else None
    )
    projected_pending = (
        len(all_item_ids) - projected_reconciled if projected_reconciled is not None else None
    )

    return PreviewSummary(
        source_rows=len(rows),
        rows_missing_notes=rows_missing_notes,
        rows_with_empty_causes=rows_with_empty_causes,
        repeated_note_rows=sum(count - 1 for count in source_note_counts.values()),
        unique_source_notes=len(source_notes),
        database_items=len(all_item_ids),
        current_link_rows=len(current_links),
        current_reconciled_items=len(currently_reconciled_ids),
        current_pending_items=len(all_item_ids) - len(currently_reconciled_ids),
        legacy_direct_cause_items=legacy_direct_cause_items,
        resolved_note_groups=len(resolved_items_by_note),
        unmatched_notes=unmatched_notes,
        ambiguous_notes=ambiguous_notes,
        ambiguous_note_matches=ambiguous_note_matches,
        verified_duplicate_note_matches=tuple(sorted(verified_duplicate_note_matches)),
        matched_notes_without_causes=matched_notes_without_causes,
        missing_causes=missing_causes,
        ambiguous_causes=ambiguous_causes,
        normalized_cause_matches=normalized_cause_matches,
        planned_link_rows=len(planned_assignments),
        planned_assignments=tuple(sorted(planned_assignments)),
        projected_reconciled_items=projected_reconciled,
        projected_pending_items=projected_pending,
        apply_ready=can_project,
    )


def log_summary(summary: PreviewSummary) -> None:
    logger.info(
        "Cause replacement preflight: source_rows=%s rows_missing_notes=%s rows_with_empty_causes=%s "
        "repeated_note_rows=%s unique_notes=%s database_items=%s",
        summary.source_rows,
        summary.rows_missing_notes,
        summary.rows_with_empty_causes,
        summary.repeated_note_rows,
        summary.unique_source_notes,
        summary.database_items,
    )
    logger.info(
        "Current: links=%s reconciled_items=%s pending_items=%s legacy_direct_cause_items=%s",
        summary.current_link_rows,
        summary.current_reconciled_items,
        summary.current_pending_items,
        summary.legacy_direct_cause_items,
    )
    logger.info(
        "Planned: resolved_note_groups=%s planned_links=%s projected_reconciled=%s "
        "projected_pending=%s apply_ready=%s",
        summary.resolved_note_groups,
        summary.planned_link_rows,
        summary.projected_reconciled_items,
        summary.projected_pending_items,
        summary.apply_ready,
    )
    if summary.unmatched_notes:
        logger.warning("Notes with no item match (%s): %s", len(summary.unmatched_notes), " | ".join(summary.unmatched_notes))
    if summary.ambiguous_notes:
        logger.error("Notes matching multiple items (%s): %s",
                     len(summary.ambiguous_notes), " | ".join(summary.ambiguous_note_matches))
    if summary.verified_duplicate_note_matches:
        logger.info("Verified duplicate source notes; mapping causes to each identical item row (%s): %s",
                    len(summary.verified_duplicate_note_matches), " | ".join(summary.verified_duplicate_note_matches))
    if summary.matched_notes_without_causes:
        logger.info("Matched notes with no causes; these items project as pending: %s",
                    len(summary.matched_notes_without_causes))
    if summary.missing_causes:
        logger.error("Cause labels not found (%s): %s", len(summary.missing_causes), " | ".join(summary.missing_causes))
    if summary.ambiguous_causes:
        logger.error("Cause labels matching multiple catalog rows (%s): %s",
                     len(summary.ambiguous_causes), " | ".join(summary.ambiguous_causes))
    if summary.normalized_cause_matches:
        logger.info("Matched cause labels through normalized catalog names/aliases: %s",
                    "; ".join(summary.normalized_cause_matches))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path, help="JSON rows containing notes and cause labels")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true",
                        help="calculate replacement and reconciliation counts without database writes")
    action.add_argument("--apply", action="store_true",
                        help="atomically replace all item/cause links and primary-cause pointers")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = load_rows(args.json_file)
    with SessionLocal() as db:
        if args.dry_run:
            summary = preview_replacement(db, rows)
            log_summary(summary)
            if not summary.apply_ready:
                raise SystemExit(1)
            return

        with db.begin():
            # Prevent concurrent item/cause edits while validating and replacing.
            db.execute(text(
                "LOCK TABLE app.postventa_item, app.postventa_item_failure_cause "
                "IN SHARE ROW EXCLUSIVE MODE"
            ))
            summary = preview_replacement(db, rows)
            log_summary(summary)
            if not summary.apply_ready:
                raise ValueError("Refusing to apply: resolve all ambiguous notes and cause labels first")

            # The junction is authoritative for reconciled status. Keep the legacy
            # single-cause field aligned with its lowest-ID selected cause.
            db.execute(delete(PostventaItemFailureCause))
            db.execute(update(PostventaItem).values(failure_cause_id=None))
            item_causes: dict[int, list[int]] = defaultdict(list)
            for item_id, cause_id in summary.planned_assignments:
                item_causes[item_id].append(cause_id)
            if summary.planned_assignments:
                db.execute(insert(PostventaItemFailureCause), [
                    {
                        "postventa_item_id": item_id,
                        "failure_cause_id": cause_id,
                        "assignment_source": "MIGRATED",
                        "assigned_by": "AGUAS_LLUVIAS_2026_MARIA_PLATIAS",
                    }
                    for item_id, cause_id in summary.planned_assignments
                ])
                primary_cause_by_item = {
                    item_id: min(cause_ids) for item_id, cause_ids in item_causes.items()
                }
                db.execute(update(PostventaItem).values(
                    failure_cause_id=case(
                        primary_cause_by_item,
                        value=PostventaItem.id,
                        else_=None,
                    )
                ))

    invalidate_dashboard_summary()
    logger.info(
        "Cause replacement applied: links=%s reconciled_items=%s pending_items=%s; "
        "document/item associations were not modified",
        summary.planned_link_rows,
        summary.projected_reconciled_items,
        summary.projected_pending_items,
    )


if __name__ == "__main__":
    main()
