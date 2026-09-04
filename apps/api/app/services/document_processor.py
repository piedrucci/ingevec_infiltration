"""Extract and conservatively match post-sale infiltration PDFs."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentPostventaItem, FailureCause, FailureCauseAlias, PostventaItem, Project
from app.services.storage import copy_private_object, delete_private_object, get_private_object


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-z0-9]+", " ", text.encode("ascii", "ignore").decode().lower()).strip()


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" :-\t\n")
    return cleaned or None


def _section(text: str, start: str, end: str | None = None) -> str | None:
    match = re.search(start, text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = text[match.end():]
    if end:
        next_section = re.search(end, value, flags=re.IGNORECASE | re.DOTALL)
        if next_section:
            value = value[:next_section.start()]
    return _clean(value)


def _field(text: str, labels: tuple[str, ...]) -> str | None:
    label_expression = "|".join(labels)
    match = re.search(
        rf"(?:{label_expression})\s*[:#-]\s*([^\n\r]+)",
        text,
        flags=re.IGNORECASE,
    )
    return _clean(match.group(1)) if match else None


def extract_pdf_details(content: bytes) -> dict[str, str | None]:
    """Extract the stable fields from the approved infiltration-report template."""
    reader = PdfReader(BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise ValueError("The PDF has no extractable text")

    project_reference = _section(
        text,
        r"Proyecto\s+en\s+que\s+se\s+detecta\s*",
        r"(?:\n\s*Tipo\s+de\s+filtraci[oó]n:)|(?:\n\s*Gerente\s+de\s+proyecto)",
    )
    project_number = _field(text, (r"N[°ºo]?\s*(?:de\s*)?obra", r"N[°ºo]?\s*proyecto"))
    project_name = _field(text, (r"Nombre\s+(?:del\s+)?proyecto", r"Proyecto"))
    if project_reference:
        project_number = re.match(r"\d+", project_reference).group(0) if re.match(r"\d+", project_reference) else project_number
        project_name = re.sub(r"^\d+\s*[-–]?\s*", "", project_reference) or project_name
    location = _field(text, (r"Lugar\s+de\s+la\s+filtraci[oó]n",))
    cause_section = _section(
        text,
        r"3\s*[.)-]?\s*AN[ÁA]LISIS\s+DE\s+CAUSA\s+DE\s+LA\s+FALLA",
        r"(?:\n\s*4\s*[.)-])|(?:\n\s*CONCLUSI[ÓO]N)",
    )
    cause = _field(cause_section or "", (r"Causa(?:\s+de\s+la\s+falla)?",)) or cause_section

    return {
        "project_number": _clean(project_number),
        "project_name": _clean(project_name),
        "infiltration_location": _clean(location),
        "failure_cause": _clean(cause),
    }


def _location_score(location: str, notes: str) -> float:
    expected = _normalized(location)
    observed = _normalized(notes)
    if not expected or not observed:
        return 0.0
    if expected == observed:
        return 1.0
    expected_unit = _unit_identifier(location)
    observed_unit = _unit_identifier(notes)
    if expected_unit and expected_unit == observed_unit:
        return 0.98
    if expected in observed or observed in expected:
        return 0.92
    expected_terms = set(expected.split())
    observed_terms = set(observed.split())
    return len(expected_terms & observed_terms) / len(expected_terms | observed_terms)


def _unit_identifier(value: str) -> str | None:
    match = re.search(r"\b([A-Z])\s*[- ]?\s*(\d{1,3})\b", value, flags=re.IGNORECASE)
    return f"{match.group(1).upper()}{match.group(2)}" if match else None


def _failure_cause(db: Session, value: str | None) -> FailureCause | None:
    """Resolve a raw PDF narrative to a reviewed, controlled cause.

    Unknown wording deliberately returns ``None`` instead of creating a new
    reporting dimension from free text. The document remains pending review.
    """
    if not value:
        return None
    normalized_value = _normalized(value)
    aliases = db.execute(
        select(FailureCauseAlias, FailureCause)
        .join(FailureCause, FailureCause.id == FailureCauseAlias.failure_cause_id)
        .where(FailureCause.is_active.is_(True))
    ).all()
    matches = [
        (alias.normalized_alias, cause)
        for alias, cause in aliases
        if alias.normalized_alias in normalized_value
    ]
    return max(matches, key=lambda match: len(match[0]))[1] if matches else None


def _destination_key(document: Document, folder: str) -> str:
    filename = PurePosixPath(document.original_filename).name
    return f"{folder}/{document.content_hash}/{filename}"


def _move_document(document: Document, folder: str) -> None:
    source_key = document.object_key
    destination_key = _destination_key(document, folder)
    if source_key == destination_key:
        return
    copy_private_object(source_key, destination_key)
    document.object_key = destination_key
    # The caller commits the database change before this best-effort source cleanup.


@dataclass
class ProcessingResult:
    document_id: int
    status: str
    matched_items: int


def process_document(db: Session, document_id: int) -> ProcessingResult:
    """Process one event idempotently and leave uncertain work for an administrator."""
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError(f"Document {document_id} does not exist")
    if document.status in {"MATCHED", "PENDING_REVIEW", "UNMATCHED", "FAILED", "QUARANTINED"}:
        return ProcessingResult(document.id, document.status, 0)

    source_key = document.object_key
    document.status = "PROCESSING"
    db.commit()

    try:
        details = extract_pdf_details(get_private_object(source_key))
        document.extracted_data = details
        document.extracted_failure_cause = details["failure_cause"]
        cause = _failure_cause(db, details["failure_cause"])

        project_number = details["project_number"]
        location = details["infiltration_location"]
        candidates = []
        if project_number and location:
            candidates = db.scalars(
                select(PostventaItem)
                .join(Project, Project.id == PostventaItem.project_id)
                .outerjoin(DocumentPostventaItem, DocumentPostventaItem.postventa_item_id == PostventaItem.id)
                .where(Project.id.like(f"{project_number}%"))
                .where(DocumentPostventaItem.document_id.is_(None))
            ).all()

        selected = [
            (item, _location_score(location, item.notes))
            for item in candidates
            if _location_score(location, item.notes) >= 0.90
        ] if location else []

        associated = 0
        for item, confidence in selected:
            # An unclassified cause requires a deliberate admin decision. Do not
            # consume the item with a partial automatic association.
            if cause is None:
                continue
            existing = db.scalar(
                select(DocumentPostventaItem).where(DocumentPostventaItem.postventa_item_id == item.id)
            )
            if existing is not None and existing.document_id != document.id:
                continue
            if existing is None:
                db.add(DocumentPostventaItem(
                    document_id=document.id,
                    postventa_item_id=item.id,
                    association_source="AUTOMATIC",
                    confidence=confidence,
                    rationale=f"Coincidencia de obra {project_number} y lugar de filtración",
                ))
            item.failure_cause_id = cause.id if cause else None
            associated += 1

        if associated and cause:
            document.status = "MATCHED"
            _move_document(document, "processed")
        else:
            document.status = "PENDING_REVIEW" if candidates else "UNMATCHED"
            _move_document(document, "pending-review")
        document.processing_error = None
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        try:
            delete_private_object(source_key)
        except Exception:
            # The canonical copy and its database path are already committed. A
            # later cleanup task can safely remove a leftover incoming object.
            pass
        return ProcessingResult(document.id, document.status, associated)
    except Exception as exc:
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            document.status = "FAILED"
            document.processing_error = str(exc)[:4000]
            db.commit()
        raise
