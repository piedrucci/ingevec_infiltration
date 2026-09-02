import asyncio
import logging

from nats.aio.client import Client as NATS

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.document_scanner import publish_pending_document_events, scan_incoming_documents

logging.basicConfig(level=get_settings().LOG_LEVEL)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    nc = NATS()
    await nc.connect(settings.NATS_URL)
    js = nc.jetstream()
    try:
        await js.add_stream(name="DOCUMENTS", subjects=["documents.pdf.*.v1"])
    except Exception:  # Stream already exists is safe during restarts.
        pass
    logger.info("PDF worker connected; scanning incoming/ every %s seconds", settings.PDF_SCAN_INTERVAL_SECONDS)
    while True:
        with SessionLocal() as db:
            result = scan_incoming_documents(db)
            published = await publish_pending_document_events(db, js)
        if result.discovered or result.rejected or result.errors or published:
            logger.info(
                "PDF scan completed: discovered=%s skipped=%s rejected=%s errors=%s events_published=%s",
                result.discovered,
                result.skipped,
                result.rejected,
                result.errors,
                published,
            )
        await asyncio.sleep(settings.PDF_SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
