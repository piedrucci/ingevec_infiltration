"""Discover PDF uploads and reliably hand work to the document pipeline."""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentOutboxEvent
from app.services.storage import s3_client


INCOMING_PREFIX = "incoming/"
PDF_CREATED_SUBJECT = "documents.pdf.created.v1"
logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    discovered: int = 0
    skipped: int = 0
    rejected: int = 0
    errors: int = 0


def _object_hash(client, bucket: str, key: str) -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: body.read(1024 * 1024), b""):
            digest.update(chunk)
    finally:
        body.close()
    return digest.hexdigest()


def scan_incoming_documents(db: Session, client=None) -> ScanResult:
    """Register new PDFs found in ``incoming/`` and enqueue their creation event.

    The database row and outbox event share one transaction. Re-running the scan is
    safe: already-known object keys and content hashes are skipped.
    """
    settings = get_settings()
    client = client or s3_client()
    result = ScanResult()
    paginator = client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=settings.S3_BUCKET, Prefix=INCOMING_PREFIX):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith("/") or not key.lower().endswith(".pdf"):
                result.skipped += 1
                continue

            size = item["Size"]
            if not 0 < size <= settings.MAX_PDF_SIZE_BYTES:
                logger.warning("Rejecting PDF outside size limit: key=%s size=%s", key, size)
                result.rejected += 1
                continue

            try:
                known_key = db.scalar(select(Document.id).where(Document.object_key == key))
                if known_key is not None:
                    result.skipped += 1
                    continue

                content_hash = _object_hash(client, settings.S3_BUCKET, key)
                duplicate_id = db.scalar(select(Document.id).where(Document.content_hash == content_hash))
                if duplicate_id is not None:
                    logger.warning(
                        "Rejecting duplicate PDF upload: key=%s existing_document_id=%s",
                        key,
                        duplicate_id,
                    )
                    result.rejected += 1
                    continue

                metadata = client.head_object(Bucket=settings.S3_BUCKET, Key=key)
                document = Document(
                    bucket=settings.S3_BUCKET,
                    object_key=key,
                    original_filename=PurePosixPath(key).name,
                    content_hash=content_hash,
                    file_size_bytes=size,
                    content_type=metadata.get("ContentType") or "application/pdf",
                    status="QUEUED",
                )
                db.add(document)
                db.flush()
                db.add(
                    DocumentOutboxEvent(
                        document_id=document.id,
                        subject=PDF_CREATED_SUBJECT,
                        payload={
                            "document_id": document.id,
                            "document_public_id": str(document.public_id),
                            "bucket": document.bucket,
                            "object_key": document.object_key,
                        },
                    )
                )
                db.commit()
                result.discovered += 1
                logger.info("Discovered PDF document_id=%s key=%s", document.id, key)
            except IntegrityError:
                # A concurrent scanner may have discovered the exact object first.
                db.rollback()
                result.skipped += 1
            except Exception:
                db.rollback()
                result.errors += 1
                logger.exception("Could not scan PDF key=%s", key)

    return result


async def publish_pending_document_events(db: Session, js, limit: int = 100) -> int:
    """Publish pending outbox records with at-least-once delivery semantics."""
    events = db.scalars(
        select(DocumentOutboxEvent)
        .where(DocumentOutboxEvent.published_at.is_(None))
        .order_by(DocumentOutboxEvent.created_at, DocumentOutboxEvent.id)
        .limit(limit)
    ).all()
    published = 0

    for event in events:
        try:
            await js.publish(event.subject, json.dumps(event.payload).encode("utf-8"))
            event.published_at = datetime.now(timezone.utc)
            event.publish_attempts += 1
            event.last_error = None
            db.commit()
            published += 1
        except Exception as exc:
            db.rollback()
            event = db.get(DocumentOutboxEvent, event.id)
            if event is not None:
                event.publish_attempts += 1
                event.last_error = str(exc)[:2000]
                db.commit()
            logger.exception("Could not publish document event id=%s", event.id if event else "unknown")

    return published
