"""Add missing failure-cause group/category links from the María Platias JSON."""

from __future__ import annotations

import argparse
import json
import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import FailureCauseCategory, FailureCauseCategoryGroupLink, FailureCauseGroup


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupCategorySummary:
    rows_processed: int
    rows_missing_group: int
    mappings_requested: int
    unique_mappings: int
    duplicate_mappings: int
    existing_mappings: int
    mappings_to_insert: int
    missing_groups: tuple[str, ...]
    missing_categories: tuple[str, ...]
    ambiguous_groups: tuple[str, ...]
    ambiguous_categories: tuple[str, ...]
    normalized_label_matches: tuple[str, ...]


def normalize_label(label: str) -> str:
    """Normalize case and diacritics for Spanish display-label matching."""
    decomposed = unicodedata.normalize("NFKD", label.strip().casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Load and validate group/category rows; null/blank groups are allowed."""
    with path.open(encoding="utf-8") as source:
        payload: Any = json.load(source)
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError("The JSON root must contain a 'rows' array")

    validated: list[dict[str, Any]] = []
    for row_number, row in enumerate(payload["rows"], start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Row {row_number} must be an object")
        group = row.get("group")
        if group is not None and not isinstance(group, str):
            raise ValueError(f"Row {row_number} group must be a string or null")
        categories = row.get("categories")
        if not isinstance(categories, list) or not all(
            isinstance(category, str) and category.strip() for category in categories
        ):
            raise ValueError(f"Row {row_number} categories must be an array of non-empty strings")
        validated.append({"group": group.strip() if group else None, "categories": [c.strip() for c in categories]})
    return validated


def collect_pairs(rows: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], int, int, int]:
    """Return unique label pairs, occurrence count, missing-group rows, and duplicates."""
    pairs: set[tuple[str, str]] = set()
    mappings_requested = 0
    rows_missing_group = 0
    for row in rows:
        group = row["group"]
        if not group:
            rows_missing_group += 1
            continue
        for category in row["categories"]:
            mappings_requested += 1
            pairs.add((group, category))
    return pairs, mappings_requested, rows_missing_group, mappings_requested - len(pairs)


def import_rows(db: Session, rows: list[dict[str, Any]], *, dry_run: bool = False) -> GroupCategorySummary:
    """Insert missing group/category links without deleting or changing existing links."""
    requested_pairs, mappings_requested, rows_missing_group, duplicate_mappings = collect_pairs(rows)
    group_labels = {group for group, _ in requested_pairs}
    category_labels = {category for _, category in requested_pairs}

    # Catalogs are deliberately small. Load their labels before normalization so
    # accented JSON labels can resolve to legacy unaccented stored labels.
    group_rows = db.execute(
        select(FailureCauseGroup.id, FailureCauseGroup.display_name_es)
    ).all() if group_labels else []
    category_rows = db.execute(
        select(FailureCauseCategory.id, FailureCauseCategory.display_name_es)
    ).all() if category_labels else []

    groups_by_label: dict[str, list[tuple[int, str]]] = {}
    for group_id, label in group_rows:
        groups_by_label.setdefault(normalize_label(label), []).append((group_id, label))
    categories_by_label: dict[str, list[tuple[int, str]]] = {}
    for category_id, label in category_rows:
        categories_by_label.setdefault(normalize_label(label), []).append((category_id, label))

    missing_groups = tuple(sorted(label for label in group_labels if normalize_label(label) not in groups_by_label))
    missing_categories = tuple(sorted(label for label in category_labels if normalize_label(label) not in categories_by_label))
    ambiguous_groups = tuple(sorted(
        label for label in group_labels if len(groups_by_label.get(normalize_label(label), [])) > 1
    ))
    ambiguous_categories = tuple(sorted(
        label for label in category_labels if len(categories_by_label.get(normalize_label(label), [])) > 1
    ))

    resolved_pairs = {
        (
            groups_by_label[normalize_label(group)][0][0],
            categories_by_label[normalize_label(category)][0][0],
        )
        for group, category in requested_pairs
        if len(groups_by_label.get(normalize_label(group), [])) == 1
        and len(categories_by_label.get(normalize_label(category), [])) == 1
    }
    normalized_label_matches_set: set[str] = set()
    for label in group_labels:
        candidates = groups_by_label.get(normalize_label(label), [])
        if len(candidates) == 1 and label != candidates[0][1]:
            normalized_label_matches_set.add(f"{label} -> {candidates[0][1]}")
    for label in category_labels:
        candidates = categories_by_label.get(normalize_label(label), [])
        if len(candidates) == 1 and label != candidates[0][1]:
            normalized_label_matches_set.add(f"{label} -> {candidates[0][1]}")
    normalized_label_matches = tuple(sorted(normalized_label_matches_set))
    existing_pairs: set[tuple[int, int]] = set()
    group_ids = {group_id for group_id, _ in resolved_pairs}
    category_ids = {category_id for _, category_id in resolved_pairs}
    if resolved_pairs:
        existing_pairs = {
            (group_id, category_id)
            for group_id, category_id in db.execute(
                select(FailureCauseCategoryGroupLink.group_id, FailureCauseCategoryGroupLink.category_id).where(
                    FailureCauseCategoryGroupLink.group_id.in_(group_ids),
                    FailureCauseCategoryGroupLink.category_id.in_(category_ids),
                )
            ).all()
            if (group_id, category_id) in resolved_pairs
        }

    pairs_to_insert = resolved_pairs - existing_pairs
    inserted = len(pairs_to_insert)
    if not dry_run and pairs_to_insert:
        statement = insert(FailureCauseCategoryGroupLink).values([
            {"group_id": group_id, "category_id": category_id}
            for group_id, category_id in sorted(pairs_to_insert)
        ]).on_conflict_do_nothing(index_elements=["category_id", "group_id"])
        result = db.execute(statement.returning(
            FailureCauseCategoryGroupLink.group_id,
            FailureCauseCategoryGroupLink.category_id,
        ))
        inserted = len(result.all())
        db.commit()

    return GroupCategorySummary(
        rows_processed=len(rows),
        rows_missing_group=rows_missing_group,
        mappings_requested=mappings_requested,
        unique_mappings=len(requested_pairs),
        duplicate_mappings=duplicate_mappings,
        existing_mappings=len(existing_pairs),
        mappings_to_insert=inserted,
        missing_groups=missing_groups,
        missing_categories=missing_categories,
        ambiguous_groups=ambiguous_groups,
        ambiguous_categories=ambiguous_categories,
        normalized_label_matches=normalized_label_matches,
    )


def log_summary(summary: GroupCategorySummary, *, dry_run: bool) -> None:
    action = "would add" if dry_run else "added"
    logger.info(
        "Group/category import %s links: rows=%s skipped_missing_group=%s requested=%s unique=%s "
        "duplicates_in_json=%s already_present=%s %s=%s",
        action,
        summary.rows_processed,
        summary.rows_missing_group,
        summary.mappings_requested,
        summary.unique_mappings,
        summary.duplicate_mappings,
        summary.existing_mappings,
        "to_insert" if dry_run else "inserted",
        summary.mappings_to_insert,
    )
    if summary.missing_groups:
        logger.warning("Skipped unknown group labels: %s", ", ".join(summary.missing_groups))
    if summary.missing_categories:
        logger.warning("Skipped unknown category labels: %s", ", ".join(summary.missing_categories))
    if summary.ambiguous_groups:
        logger.warning("Skipped ambiguous group labels: %s", ", ".join(summary.ambiguous_groups))
    if summary.ambiguous_categories:
        logger.warning("Skipped ambiguous category labels: %s", ", ".join(summary.ambiguous_categories))
    if summary.normalized_label_matches:
        logger.info("Matched labels after case/accent normalization: %s", "; ".join(summary.normalized_label_matches))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path, help="JSON rows with group and categories labels")
    parser.add_argument("--dry-run", action="store_true", help="summarize without changing associations")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = load_rows(args.json_file)
    with SessionLocal() as db:
        summary = import_rows(db, rows, dry_run=args.dry_run)
    log_summary(summary, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
