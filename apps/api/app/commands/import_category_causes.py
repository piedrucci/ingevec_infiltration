"""Replace failure-cause/category associations from a JSON mapping."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import FailureCause, FailureCauseCategory, FailureCauseCategoryLink
from app.services.dashboard_cache import invalidate_dashboard_summary


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportSummary:
    categories_processed: int
    mappings_requested: int
    valid_mappings: int
    duplicate_mappings: int
    missing_categories: tuple[str, ...]
    missing_causes: tuple[str, ...]


def load_mapping(path: Path) -> dict[str, list[str]]:
    """Load and validate the category-to-cause JSON mapping."""
    with path.open(encoding="utf-8") as source:
        payload: Any = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("The JSON root must be an object mapping category codes to arrays")

    mapping: dict[str, list[str]] = {}
    for category_code, cause_codes in payload.items():
        if not isinstance(category_code, str) or not category_code:
            raise ValueError("Every category key must be a non-empty string")
        if not isinstance(cause_codes, list) or not all(isinstance(code, str) and code for code in cause_codes):
            raise ValueError(f"Category {category_code!r} must contain an array of non-empty cause-code strings")
        mapping[category_code] = cause_codes
    return mapping


def import_mapping(db: Session, mapping: dict[str, list[str]], *, dry_run: bool = False) -> ImportSummary:
    """Replace associations, skipping unknown codes and preserving one transaction."""
    owners: dict[str, str] = {}
    for category, codes in mapping.items():
        for code in codes:
            if code in owners and owners[code] != category:
                raise ValueError(f"Cause {code} cannot belong to both {owners[code]} and {category}")
            owners[code] = category
    category_codes = set(mapping)
    cause_codes = {cause_code for causes in mapping.values() for cause_code in causes}
    categories = {
        category.code: category
        for category in db.execute(
            select(FailureCauseCategory).where(FailureCauseCategory.code.in_(category_codes))
        ).scalars()
    }
    causes = {
        cause.code: cause
        for cause in db.execute(select(FailureCause).where(FailureCause.code.in_(cause_codes))).scalars()
    }
    missing_categories = tuple(sorted(category_codes - categories.keys()))
    missing_causes = tuple(sorted(cause_codes - causes.keys()))

    requested_pairs = {
        (category_code, cause_code)
        for category_code, codes in mapping.items()
        for cause_code in codes
    }
    valid_pairs = {
        (category_code, cause_code)
        for category_code, cause_code in requested_pairs
        if category_code in categories and cause_code in causes
    }
    duplicate_mappings = sum(len(codes) for codes in mapping.values()) - len(requested_pairs)

    if not dry_run:
        with db.begin_nested():
            db.execute(delete(FailureCauseCategoryLink))
            db.add_all([
                FailureCauseCategoryLink(
                    failure_cause_id=causes[cause_code].id,
                    category_id=categories[category_code].id,
                )
                for category_code, cause_code in sorted(valid_pairs)
            ])
        db.commit()
        invalidate_dashboard_summary()

    return ImportSummary(
        categories_processed=len(mapping),
        mappings_requested=sum(len(codes) for codes in mapping.values()),
        valid_mappings=len(valid_pairs),
        duplicate_mappings=duplicate_mappings,
        missing_categories=missing_categories,
        missing_causes=missing_causes,
    )


def log_summary(summary: ImportSummary, *, dry_run: bool) -> None:
    action = "would replace" if dry_run else "replaced"
    result_label = "valid" if dry_run else "inserted"
    logger.info(
        "Category/cause import %s associations: categories=%s requested=%s %s=%s duplicates=%s",
        action,
        summary.categories_processed,
        summary.mappings_requested,
        result_label,
        summary.valid_mappings,
        summary.duplicate_mappings,
    )
    if summary.missing_categories:
        logger.warning("Skipped missing categories: %s", ", ".join(summary.missing_categories))
    if summary.missing_causes:
        logger.warning("Skipped missing causes: %s", ", ".join(summary.missing_causes))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path, help="JSON file mapping category codes to cause-code arrays")
    parser.add_argument("--dry-run", action="store_true", help="validate and summarize without changing associations")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    mapping = load_mapping(args.json_file)
    with SessionLocal() as db:
        summary = import_mapping(db, mapping, dry_run=args.dry_run)
    log_summary(summary, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
