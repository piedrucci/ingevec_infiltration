import asyncio
import json
import logging

from nats.aio.client import Client as NATS
from nats.errors import TimeoutError

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.document_scanner import publish_pending_document_events, scan_incoming_documents
from app.services.document_processor import process_document

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
    subscription = await js.pull_subscribe(
        "documents.pdf.created.v1",
        durable="pdf-processor-v1",
        stream="DOCUMENTS",
    )
    logger.info("PDF worker connected; scanning incoming/ every %s seconds", settings.PDF_SCAN_INTERVAL_SECONDS)
    next_scan = 0.0
    while True:
        now = asyncio.get_running_loop().time()
        if now >= next_scan:
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
            next_scan = now + settings.PDF_SCAN_INTERVAL_SECONDS

        try:
            messages = await subscription.fetch(1, timeout=1)
        except TimeoutError:
            continue

        for message in messages:
            try:
                payload = json.loads(message.data.decode("utf-8"))
                with SessionLocal() as db:
                    result = process_document(db, int(payload["document_id"]))
                logger.info(
                    "PDF processed: document_id=%s status=%s matched_items=%s",
                    result.document_id,
                    result.status,
                    result.matched_items,
                )
            except Exception:
                # Invalid or unreadable reports become FAILED/PENDING_REVIEW in
                # the service; acknowledge to avoid an infinite redelivery loop.
                logger.exception("Could not process PDF event")
            await message.ack()


if __name__ == "__main__":
    asyncio.run(main())
