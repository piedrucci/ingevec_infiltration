"""Extract and conservatively match post-sale infiltration PDFs."""

import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath

import pymupdf
import pytesseract
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentPostventaItem, FailureCause, FailureCauseAlias, PostventaItemFailureCause
from app.services.document_candidates import find_document_candidates
from app.services.storage import copy_private_object, delete_private_object, get_private_object
from app.services.dashboard_cache import invalidate_dashboard_summary


logger = logging.getLogger(__name__)


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


def _project_number(value: str | None) -> str | None:
    """Keep only the numeric obra identifier, preserving leading zeroes."""
    if not value:
        return None
    match = re.match(r"\s*(\d+)", value)
    return match.group(1) if match else _clean(value)


def _parse_pdf_text(text: str) -> dict[str, str | None]:
    """Parse stable fields from native or OCR text for the approved template."""
    project_reference = _section(
        text,
        r"Proyecto\s+en\s+que\s+se\s+detecta\s*",
        r"(?:\n\s*Tipo\s+de\s+filtraci[oó]n:)|(?:\n\s*Gerente\s+de\s+proyecto)",
    )
    project_number = _field(text, (r"N[°ºo2*?]?\s*(?:de\s*)?obra", r"N[°ºo2*?]?\s*proyecto"))
    if not project_number:
        number_match = re.search(
            r"N[°ºo2*?]?\s*(?:de\s*)?obra\s*[:#-]?\s*\(?\s*(\d+)",
            text,
            flags=re.IGNORECASE,
        )
        project_number = number_match.group(1) if number_match else None
    project_name = _field(text, (r"Nombre\s+(?:del\s+)?proyecto", r"Proyecto"))
    if project_reference:
        project_number = re.match(r"\d+", project_reference).group(0) if re.match(r"\d+", project_reference) else project_number
        project_name = re.sub(r"^\d+\s*[-–]?\s*", "", project_reference) or project_name
    if not project_name:
        detected_project = re.search(
            r"detecta(?:[ \t]*[:#-]?[ \t]*|\s*[\r\n]+\s*)([^\r\n]+)",
            text,
            flags=re.IGNORECASE,
        )
        if detected_project:
            project_name = re.split(
                r"\s+(?:TIPO\s+DE\s+FILTRACI[ÓO]N|INSTALACIONES|LOSA|BOW\s+WINDOWS)\b",
                detected_project.group(1),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
    location = _field(text, (r"Lugar\s+de\s+la\s+filtraci[oó]n",))
    cause_section = _section(
        text,
        r"3\s*[.)-]?\s*AN[ÁA]LISIS\s+DE\s+CAUSA\s+DE\s+LA\s+FALLA",
        r"(?:\n\s*4\s*(?:[.)-]|\n))|(?:\n\s*CONCLUSI[ÓO]N)",
    )
    cause = _field(cause_section or "", (r"Causa(?:\s+de\s+la\s+falla)?",)) or cause_section

    return {
        "project_number": _project_number(project_number),
        "project_name": _clean(project_name),
        "infiltration_location": _clean(location),
        "failure_cause": _clean(cause),
    }


def _extract_native_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _needs_ocr(details: dict[str, str | None]) -> bool:
    has_project = bool(details["project_number"] or details["project_name"])
    return not has_project or not details["infiltration_location"] or not details["failure_cause"]


def _ocr_pdf_text(content: bytes) -> str:
    settings = get_settings()
    started_at = time.monotonic()
    pages: list[str] = []
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError("The PDF could not be opened for OCR") from exc

    try:
        if document.page_count > settings.OCR_MAX_PAGES:
            raise ValueError(
                f"PDF has {document.page_count} pages; OCR is limited to {settings.OCR_MAX_PAGES} pages"
            )
        for page_number, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(dpi=settings.OCR_DPI, alpha=False)
            with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
                try:
                    page_text = pytesseract.image_to_string(
                        image,
                        lang=settings.OCR_LANGUAGE,
                        # Sparse-text mode handles the report's table layout much
                        # better than Tesseract's default page segmentation.
                        config="--psm 11",
                        timeout=settings.OCR_PAGE_TIMEOUT_SECONDS,
                    )
                except pytesseract.TesseractError as exc:
                    raise RuntimeError(f"Tesseract OCR failed on page {page_number}: {exc}") from exc
                except RuntimeError as exc:
                    raise TimeoutError(
                        f"OCR timed out on page {page_number} after "
                        f"{settings.OCR_PAGE_TIMEOUT_SECONDS} seconds"
                    ) from exc
            pages.append(page_text)
    finally:
        document.close()

    text = "\n".join(pages)
    logger.info(
        "OCR completed: pages=%s duration_seconds=%.3f language=%s",
        len(pages),
        time.monotonic() - started_at,
        settings.OCR_LANGUAGE,
    )
    return text


def extract_pdf_details(content: bytes) -> dict[str, str | None]:
    """Extract stable fields, using bounded local OCR when native text is incomplete."""
    native_text = _extract_native_text(content)
    native_details = _parse_pdf_text(native_text)
    if not _needs_ocr(native_details):
        return {**native_details, "extraction_method": "native"}

    logger.info("Native PDF extraction was incomplete; invoking local OCR")
    ocr_text = _ocr_pdf_text(content)
    if not native_text.strip() and not ocr_text.strip():
        raise ValueError("The PDF has no extractable or OCR-readable text")

    ocr_details = _parse_pdf_text(ocr_text)
    merged = {
        field: native_details[field] or ocr_details[field]
        for field in ("project_number", "project_name", "infiltration_location", "failure_cause")
    }
    merged["extraction_method"] = "hybrid" if native_text.strip() else "ocr"
    return merged


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


def _failure_causes(db: Session, value: str | None) -> list[FailureCause]:
    """Resolve a raw PDF narrative to a reviewed, controlled cause.

    Unknown wording deliberately returns an empty list instead of creating a
    new reporting dimension from free text. The document remains pending review.
    """
    if not value:
        return []
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
    causes: list[FailureCause] = []
    seen: set[int] = set()
    for _, cause in sorted(matches, key=lambda match: len(match[0]), reverse=True):
        if cause.id not in seen:
            causes.append(cause)
            seen.add(cause.id)
    return causes


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


def process_document(db: Session, document_id: int, *, force: bool = False) -> ProcessingResult:
    """Process one event idempotently, optionally reprocessing a terminal document."""
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError(f"Document {document_id} does not exist")
    if not force and document.status in {"MATCHED", "PENDING_REVIEW", "UNMATCHED", "FAILED", "QUARANTINED"}:
        return ProcessingResult(document.id, document.status, 0)

    source_key = document.object_key
    document.status = "PROCESSING"
    db.commit()

    try:
        details = extract_pdf_details(get_private_object(source_key))
        document.extracted_data = details
        document.extracted_failure_cause = details["failure_cause"]
        causes = _failure_causes(db, details["failure_cause"])

        project_number = details["project_number"]
        location = details["infiltration_location"]
        candidate_set = find_document_candidates(
            db,
            project_number=project_number,
            project_name=details.get("project_name"),
            location=location,
        )
        candidates = candidate_set.items

        selected = [
            (item, _location_score(location, item.notes))
            for item in candidates
            if _location_score(location, item.notes) >= 0.90
        ] if location else []

        associated = 0
        for item, confidence in selected:
            # An unclassified cause requires a deliberate admin decision. Do not
            # consume the item with a partial automatic association.
            if not causes:
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
            for cause in causes:
                assignment = db.get(PostventaItemFailureCause, (item.id, cause.id))
                if assignment is None:
                    db.add(PostventaItemFailureCause(
                        postventa_item_id=item.id,
                        failure_cause_id=cause.id,
                        source_document_id=document.id,
                        assignment_source="AUTOMATIC",
                    ))
                elif assignment.assignment_source != "DIRECT_MANUAL":
                    # A direct reconciliation is an explicit user decision. A
                    # later PDF may add another cause, but must not overwrite it.
                    assignment.source_document_id = document.id
                    assignment.assignment_source = "AUTOMATIC"
            # Keep the legacy field populated during the compatibility rollout.
            if item.failure_cause_id is None:
                item.failure_cause_id = causes[0].id
            associated += 1

        if associated and causes:
            document.status = "MATCHED"
            _move_document(document, "processed")
        else:
            document.status = "PENDING_REVIEW" if candidates else "UNMATCHED"
            _move_document(document, "pending-review")
        document.processing_error = None
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        invalidate_dashboard_summary()
        if source_key != document.object_key:
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
            invalidate_dashboard_summary()
        raise
