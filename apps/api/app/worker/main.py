import asyncio
import json
import logging

from nats.errors import TimeoutError

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.document_events import DOCUMENT_STREAM, document_jetstream
from app.services.document_processor import process_document

logging.basicConfig(level=get_settings().LOG_LEVEL)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with document_jetstream() as js:
        subscription = await js.pull_subscribe(
            "documents.pdf.created.v1",
            durable="pdf-processor-v1",
            stream=DOCUMENT_STREAM,
        )
        logger.info("PDF worker connected; waiting for JetStream events")
        while True:
            try:
                messages = await subscription.fetch(1, timeout=30)
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
