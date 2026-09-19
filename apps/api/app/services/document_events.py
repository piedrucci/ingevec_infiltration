"""NATS helpers for the document processing pipeline."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from nats.aio.client import Client as NATS

from app.core.config import get_settings


DOCUMENT_STREAM = "DOCUMENTS"
DOCUMENT_SUBJECTS = ["documents.pdf.*.v1"]


@asynccontextmanager
async def document_jetstream() -> AsyncIterator[object]:
    """Yield a JetStream context and always close its short-lived connection."""
    settings = get_settings()
    nc = NATS()
    await nc.connect(settings.NATS_URL, connect_timeout=2)
    try:
        js = nc.jetstream()
        try:
            await js.stream_info(DOCUMENT_STREAM)
        except Exception:
            # A fresh environment may not have the stream yet. If another
            # process creates it concurrently, verify it instead of failing.
            try:
                await js.add_stream(name=DOCUMENT_STREAM, subjects=DOCUMENT_SUBJECTS)
            except Exception:
                await js.stream_info(DOCUMENT_STREAM)
        yield js
    finally:
        if nc.is_connected:
            await nc.drain()
        else:
            await nc.close()
