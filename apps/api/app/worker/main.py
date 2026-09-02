import asyncio
import logging

from nats.aio.client import Client as NATS

from app.core.config import get_settings

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
    logger.info("PDF worker connected; concurrency is intentionally one")
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())

