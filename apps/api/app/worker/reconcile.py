"""One-shot recovery for document events and externally uploaded PDFs."""

import argparse
import asyncio
import logging

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.document_events import document_jetstream
from app.services.document_scanner import publish_pending_document_events, scan_incoming_documents


logging.basicConfig(level=get_settings().LOG_LEVEL)
logger = logging.getLogger(__name__)


async def reconcile(*, scan_storage: bool = False) -> None:
    with SessionLocal() as db:
        if scan_storage:
            result = scan_incoming_documents(db)
            logger.info(
                "PDF storage reconciliation completed: discovered=%s skipped=%s rejected=%s errors=%s",
                result.discovered,
                result.skipped,
                result.rejected,
                result.errors,
            )

        async with document_jetstream() as js:
            published = await publish_pending_document_events(db, js)
        logger.info("Document outbox reconciliation completed: published=%s", published)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-storage",
        action="store_true",
        help="also discover PDFs placed directly in the incoming/ storage prefix",
    )
    args = parser.parse_args()
    asyncio.run(reconcile(scan_storage=args.scan_storage))


if __name__ == "__main__":
    main()
