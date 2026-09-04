"""Authenticated PDF upload registration with private object storage."""

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentOutboxEvent
from app.services.document_scanner import PDF_CREATED_SUBJECT
from app.services.storage import delete_private_object, put_private_object


class DuplicateDocumentError(Exception):
    def __init__(self, document: Document):
        self.document = document


@dataclass
class UploadedDocument:
    document: Document
    created: bool


def _safe_filename(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).name or "document.pdf"


def register_pdf_upload(db: Session, *, filename: str, content: bytes, content_type: str | None) -> UploadedDocument:
    """Store and enqueue a unique PDF. The database outbox is the queue boundary."""
    settings = get_settings()
    if not filename.lower().endswith(".pdf") or not content.lstrip().startswith(b"%PDF-"):
        raise ValueError("Only valid PDF files are accepted")
    if not 0 < len(content) <= settings.MAX_PDF_SIZE_BYTES:
        raise OverflowError("PDF exceeds configured size limit")

    content_hash = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(Document).where(Document.content_hash == content_hash))
    if existing is not None:
        raise DuplicateDocumentError(existing)

    safe_filename = _safe_filename(filename)
    object_key = f"incoming/{uuid4()}/{safe_filename}"
    put_private_object(object_key, content, "application/pdf")
    try:
        document = Document(
            bucket=settings.S3_BUCKET,
            object_key=object_key,
            original_filename=safe_filename,
            content_hash=content_hash,
            file_size_bytes=len(content),
            content_type="application/pdf",
            status="QUEUED",
        )
        db.add(document)
        db.flush()
        db.add(DocumentOutboxEvent(
            document_id=document.id,
            subject=PDF_CREATED_SUBJECT,
            payload={
                "document_id": document.id,
                "document_public_id": str(document.public_id),
                "bucket": document.bucket,
                "object_key": document.object_key,
            },
        ))
        db.commit()
        db.refresh(document)
        return UploadedDocument(document=document, created=True)
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(select(Document).where(Document.content_hash == content_hash))
        delete_private_object(object_key)
        if existing is not None:
            raise DuplicateDocumentError(existing) from exc
        raise
    except Exception:
        db.rollback()
        delete_private_object(object_key)
        raise
