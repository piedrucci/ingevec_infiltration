"""Safely reprocess terminal PDF documents after matching rules change."""

import argparse
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Document
from app.services.document_processor import process_document


logging.basicConfig(level=get_settings().LOG_LEVEL)
logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("PENDING_REVIEW", "UNMATCHED", "MATCHED", "FAILED", "QUARANTINED")


def _documents(*, document_ids: list[int], statuses: list[str], limit: int | None) -> list[int]:
    with SessionLocal() as db:
        query = select(Document.id).where(Document.status.in_(statuses)).order_by(Document.id)
        if document_ids:
            query = query.where(Document.id.in_(document_ids))
        if limit is not None:
            query = query.limit(limit)
        return list(db.scalars(query))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status",
        action="append",
        choices=TERMINAL_STATUSES,
        dest="statuses",
        help="status to include; repeat to include more than one (default: PENDING_REVIEW and UNMATCHED)",
    )
    parser.add_argument("--document-id", type=int, action="append", default=[], help="only reprocess this document ID; repeatable")
    parser.add_argument("--limit", type=int, help="maximum number of documents to select")
    parser.add_argument("--execute", action="store_true", help="actually process documents; without this flag only list them")
    args = parser.parse_args()

    statuses = args.statuses or ["PENDING_REVIEW", "UNMATCHED"]
    document_ids = _documents(document_ids=args.document_id, statuses=statuses, limit=args.limit)
    logger.info("Selected %s document(s): %s", len(document_ids), document_ids)
    if not args.execute:
        logger.info("Dry run only. Add --execute to process the selected documents.")
        return

    succeeded = 0
    failed = 0
    for document_id in document_ids:
        try:
            with SessionLocal() as db:
                result = process_document(db, document_id, force=True)
            logger.info(
                "Reprocessed document_id=%s status=%s matched_items=%s",
                result.document_id,
                result.status,
                result.matched_items,
            )
            succeeded += 1
        except Exception:
            failed += 1
            logger.exception("Could not reprocess document_id=%s", document_id)
    logger.info("Reprocessing completed: succeeded=%s failed=%s", succeeded, failed)


if __name__ == "__main__":
    main()
