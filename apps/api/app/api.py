import logging
from zipfile import BadZipFile
from urllib.parse import quote
from uuid import UUID

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.core.config import get_settings
from app.models import (
    Classification,
    Document,
    DocumentPostventaItem,
    FailureCause,
    FailureCauseCategory,
    ItemType,
    Location,
    PostventaItem,
    PostventaItemFailureCause,
    Project,
    ProjectAdmin,
    ProjectManager,
    Subcontractor,
    Supervisor,
    Typology,
)
from app.schemas import (
    DashboardSummary,
    DocumentAssociationItem,
    DocumentCandidate,
    DocumentCandidateResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentSummary,
    ExcelImportResponse,
    FailureCauseSummary,
    FailureCauseOption,
    FailureCauseCategoryOption,
    CreateFailureCauseRequest,
    ManualDocumentAssociationRequest,
    PageMeta,
    PostventaItemFailureCauseUpdateRequest,
    PostventaItemListItem,
    PostventaItemListResponse,
    ProjectListItem,
    ProjectListResponse,
)
from app.services.dashboard import dashboard_summary
from app.services.dashboard_cache import invalidate_dashboard_summary
from app.services.document_candidates import find_document_candidates
from app.services.document_events import document_jetstream
from app.services.document_processor import _location_score, _move_document
from app.services.document_scanner import publish_pending_document_events
from app.services.document_upload import DuplicateDocumentError, register_pdf_upload
from app.services.failure_causes import create_failure_cause
from app.services.excel_importer import import_workbook
from app.services.storage import delete_private_object, get_private_object

imports_router = APIRouter(prefix="/imports", tags=["imports"])
projects_router = APIRouter(prefix="/projects", tags=["projects"])
postventa_items_router = APIRouter(prefix="/postventa-items", tags=["postventa-items"])
documents_router = APIRouter(prefix="/documents", tags=["documents"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


def _actor_name(claims: dict) -> str:
    return str(claims.get("email") or claims.get("preferred_username") or claims.get("sub") or "admin")[:255]


def _failure_cause_summaries(db: Session, item_ids: list[int]) -> dict[int, list[FailureCauseSummary]]:
    causes_by_item: dict[int, list[FailureCauseSummary]] = {item_id: [] for item_id in item_ids}
    if not item_ids:
        return causes_by_item
    cause_rows = db.execute(
        select(PostventaItemFailureCause.postventa_item_id, FailureCause, FailureCauseCategory)
        .join(FailureCause, FailureCause.id == PostventaItemFailureCause.failure_cause_id)
        .join(FailureCauseCategory, FailureCauseCategory.id == FailureCause.category_id)
        .where(PostventaItemFailureCause.postventa_item_id.in_(item_ids))
        .order_by(PostventaItemFailureCause.postventa_item_id, FailureCause.display_name_es)
    ).all()
    for item_id, cause, category in cause_rows:
        causes_by_item[item_id].append(FailureCauseSummary(
            code=cause.code,
            display_name_es=cause.display_name_es,
            category_code=category.code,
            category_name_es=category.display_name_es,
        ))
    return causes_by_item


def _document_list_item(document: Document, association_count: int, projects: list[str] | None = None) -> DocumentListItem:
    return DocumentListItem(
        public_id=document.public_id,
        original_filename=document.original_filename,
        status=document.status,
        uploaded_at=document.uploaded_at,
        processed_at=document.processed_at,
        matching_confidence=float(document.matching_confidence) if document.matching_confidence is not None else None,
        extracted_data=document.extracted_data,
        extracted_failure_cause=document.extracted_failure_cause,
        processing_error=document.processing_error,
        association_count=association_count,
        projects=projects or [],
    )


@imports_router.post("/excel", response_model=ExcelImportResponse, status_code=status.HTTP_201_CREATED)
async def import_excel(file: UploadFile = File(...), _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(415, "Only .xlsx files are accepted")
    content = await file.read()
    if len(content) > get_settings().MAX_EXCEL_SIZE_BYTES:
        raise HTTPException(413, "Excel file exceeds configured size limit")
    try:
        imported, created = import_workbook(db, content, file.filename)
    except (BadZipFile, InvalidFileException, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        invalidate_dashboard_summary()
    return ExcelImportResponse(import_id=imported.id, status=imported.status, row_count=imported.row_count, created=created)


@documents_router.post("/upload", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...), _: dict = Depends(require_admin), db: Session = Depends(get_db)) -> DocumentSummary:
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required")
    content = await file.read()
    try:
        uploaded = register_pdf_upload(db, filename=file.filename, content=content, content_type=file.content_type)
    except OverflowError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except DuplicateDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_DOCUMENT",
                "document_public_id": str(exc.document.public_id),
                "original_filename": exc.document.original_filename,
                "status": exc.document.status,
            },
        ) from exc
    try:
        async with document_jetstream() as js:
            await publish_pending_document_events(db, js)
    except Exception:
        # The committed outbox row is the recovery boundary. An unavailable
        # NATS server must not turn an otherwise valid upload into an error.
        logger.exception(
            "PDF stored but immediate event publication failed; reconciliation will retry document_id=%s",
            uploaded.document.id,
        )
    document = uploaded.document
    invalidate_dashboard_summary()
    return DocumentSummary(
        public_id=document.public_id,
        original_filename=document.original_filename,
        status=document.status,
        uploaded_at=document.uploaded_at,
        processed_at=document.processed_at,
    )


@documents_router.get("", response_model=DocumentListResponse)
def list_documents(
    document_status: str | None = Query(default=None, max_length=32),
    search: str | None = Query(default=None, min_length=1, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="project_id", max_length=32),
    sort_direction: str = Query(default="asc", max_length=4),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    filters = []
    if document_status:
        filters.append(Document.status == document_status)
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Document.original_filename.ilike(term),
                Project.id.ilike(term),
                Project.name.ilike(term),
                Document.extracted_data["project_number"].astext.ilike(term),
            )
        )
    total = db.scalar(
        select(func.count(func.distinct(Document.id)))
        .select_from(Document)
        .outerjoin(DocumentPostventaItem, DocumentPostventaItem.document_id == Document.id)
        .outerjoin(PostventaItem, PostventaItem.id == DocumentPostventaItem.postventa_item_id)
        .outerjoin(Project, Project.id == PostventaItem.project_id)
        .where(*filters)
    ) or 0
    rows = db.execute(
        select(
            Document,
            func.count(DocumentPostventaItem.postventa_item_id).label("association_count"),
            func.array_agg(aggregate_order_by(Project.id.distinct(), Project.id)).filter(Project.id.is_not(None)).label("projects"),
        )
        .outerjoin(DocumentPostventaItem, DocumentPostventaItem.document_id == Document.id)
        .outerjoin(PostventaItem, PostventaItem.id == DocumentPostventaItem.postventa_item_id)
        .outerjoin(Project, Project.id == PostventaItem.project_id)
        .where(*filters)
        .group_by(Document.id)
        .order_by(func.min(Project.id).nulls_last(), Document.uploaded_at.desc(), Document.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return DocumentListResponse(
        items=[_document_list_item(document, association_count, projects) for document, association_count, projects in rows],
        page=PageMeta(total=total, limit=limit, offset=offset),
    )


@documents_router.get("/failure-causes", response_model=list[FailureCauseOption])
def list_failure_causes(_: dict = Depends(require_admin), db: Session = Depends(get_db)) -> list[FailureCauseOption]:
    rows = db.execute(
        select(FailureCause, FailureCauseCategory)
        .join(FailureCauseCategory, FailureCauseCategory.id == FailureCause.category_id)
        .where(FailureCause.is_active.is_(True))
        .order_by(FailureCauseCategory.display_name_es, FailureCause.display_name_es)
    ).all()
    return [FailureCauseOption(code=cause.code, display_name_es=cause.display_name_es, category_name_es=category.display_name_es) for cause, category in rows]


@documents_router.get("/failure-cause-categories", response_model=list[FailureCauseCategoryOption])
def list_failure_cause_categories(_: dict = Depends(require_admin), db: Session = Depends(get_db)) -> list[FailureCauseCategoryOption]:
    rows = db.scalars(
        select(FailureCauseCategory)
        .where(FailureCauseCategory.is_active.is_(True))
        .order_by(FailureCauseCategory.display_name_es)
    ).all()
    return [FailureCauseCategoryOption(code=category.code, display_name_es=category.display_name_es) for category in rows]


@documents_router.post("/failure-causes", response_model=FailureCauseOption, status_code=status.HTTP_201_CREATED)
def create_new_failure_cause(
    payload: CreateFailureCauseRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FailureCauseOption:
    try:
        cause = create_failure_cause(
            db,
            code=payload.code,
            display_name_es=payload.display_name_es,
            category_code=payload.category_code,
            aliases=payload.aliases,
        )
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The failure cause or one of its aliases already exists") from exc
    category = db.get(FailureCauseCategory, cause.category_id)
    return FailureCauseOption(code=cause.code, display_name_es=cause.display_name_es, category_name_es=category.display_name_es)


@documents_router.get("/{document_public_id}", response_model=DocumentDetail)
def get_document_detail(document_public_id: UUID, _: dict = Depends(require_admin), db: Session = Depends(get_db)) -> DocumentDetail:
    document = db.scalar(select(Document).where(Document.public_id == document_public_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    rows = db.execute(
        select(DocumentPostventaItem, PostventaItem, Project)
        .join(PostventaItem, PostventaItem.id == DocumentPostventaItem.postventa_item_id)
        .join(Project, Project.id == PostventaItem.project_id)
        .where(DocumentPostventaItem.document_id == document.id)
        .order_by(PostventaItem.id)
    ).all()
    item = _document_list_item(document, len(rows))
    return DocumentDetail(**item.model_dump(), associations=[
        DocumentAssociationItem(
            postventa_item_public_id=postventa_item.public_id,
            postventa_item_id=postventa_item.id,
            project_id=project.id,
            project_name=project.name,
            notes=postventa_item.notes,
            association_source=association.association_source,
            confidence=float(association.confidence) if association.confidence is not None else None,
            rationale=association.rationale,
        ) for association, postventa_item, project in rows
    ])


@documents_router.delete("/{document_public_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_public_id: UUID, _: dict = Depends(require_admin), db: Session = Depends(get_db)) -> Response:
    document = db.scalar(select(Document).where(Document.public_id == document_public_id).with_for_update())
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        delete_private_object(document.object_key)
    except Exception as exc:
        logger.exception("Could not delete stored PDF document_id=%s", document.id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Document storage is unavailable") from exc

    db.delete(document)
    db.commit()
    invalidate_dashboard_summary()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@documents_router.get("/{document_public_id}/candidates", response_model=DocumentCandidateResponse)
def list_document_candidates(document_public_id: UUID, _: dict = Depends(require_admin), db: Session = Depends(get_db)) -> DocumentCandidateResponse:
    document = db.scalar(select(Document).where(Document.public_id == document_public_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    details = document.extracted_data or {}
    location = details.get("infiltration_location") or ""
    candidate_set = find_document_candidates(
        db,
        project_number=details.get("project_number"),
        project_name=details.get("project_name"),
        location=location,
    )
    candidates = [
        DocumentCandidate(
            postventa_item_public_id=item.public_id,
            postventa_item_id=item.id,
            project_id=item.project_id,
            project_name=candidate_set.project_names[item.project_id],
            notes=item.notes,
            score=_location_score(location, item.notes),
        ) for item in candidate_set.items
    ]
    return DocumentCandidateResponse(
        items=sorted(candidates, key=lambda candidate: candidate.score, reverse=True),
        project_match_method=candidate_set.project_match_method,
        project_match_score=candidate_set.project_match_score,
        project_match_message=candidate_set.project_match_message,
    )


@documents_router.post("/{document_public_id}/associations", response_model=DocumentDetail)
def create_manual_associations(
    document_public_id: UUID,
    payload: ManualDocumentAssociationRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    selected_ids = list(dict.fromkeys(payload.postventa_item_public_ids))
    if not selected_ids:
        raise HTTPException(status_code=422, detail="Select at least one postventa item")
    document = db.scalar(select(Document).where(Document.public_id == document_public_id).with_for_update())
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status not in {"PENDING_REVIEW", "UNMATCHED"}:
        raise HTTPException(status_code=409, detail="Document is not awaiting manual review")
    cause_codes = list(dict.fromkeys(payload.failure_cause_codes))
    causes = db.scalars(select(FailureCause).where(FailureCause.code.in_(cause_codes), FailureCause.is_active.is_(True))).all()
    causes_by_code = {cause.code: cause for cause in causes}
    if len(causes_by_code) != len(cause_codes):
        raise HTTPException(status_code=422, detail="One or more failure causes are inactive or do not exist")
    items = db.scalars(select(PostventaItem).where(PostventaItem.public_id.in_(selected_ids)).with_for_update()).all()
    if len(items) != len(selected_ids):
        raise HTTPException(status_code=422, detail="One or more selected postventa items do not exist")
    existing = db.scalars(select(DocumentPostventaItem).where(DocumentPostventaItem.postventa_item_id.in_([item.id for item in items]))).all()
    if any(association.document_id != document.id for association in existing):
        raise HTTPException(status_code=409, detail="One or more selected postventa items already have a document")
    source_key = document.object_key
    try:
        for item in items:
            if not any(association.postventa_item_id == item.id for association in existing):
                db.add(DocumentPostventaItem(
                    document_id=document.id,
                    postventa_item_id=item.id,
                    association_source="MANUAL",
                    confidence=None,
                    rationale="Asociación confirmada manualmente por administración",
                ))
            for cause in causes:
                assignment = db.get(PostventaItemFailureCause, (item.id, cause.id))
                if assignment is None:
                    db.add(PostventaItemFailureCause(
                        postventa_item_id=item.id,
                        failure_cause_id=cause.id,
                        source_document_id=document.id,
                        assignment_source="MANUAL",
                    ))
                elif assignment.assignment_source != "DIRECT_MANUAL":
                    assignment.source_document_id = document.id
                    assignment.assignment_source = "MANUAL"
            if item.failure_cause_id is None:
                item.failure_cause_id = causes[0].id
        document.status = "MATCHED"
        _move_document(document, "processed")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An item was associated concurrently") from exc
    try:
        delete_private_object(source_key)
    except Exception:
        pass
    invalidate_dashboard_summary()
    return get_document_detail(document_public_id, db=db)


@dashboard_router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(_: dict = Depends(require_admin), db: Session = Depends(get_db)) -> DashboardSummary:
    """Cached administrative KPIs; falls back to Neon when Redis is unavailable."""
    return dashboard_summary(db)


@documents_router.get("/{document_public_id}/content", responses={404: {"description": "Document not found"}})
def get_document_content(
    document_public_id: UUID,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Return a PDF without exposing its private object-storage location."""
    document = db.scalar(select(Document).where(Document.public_id == document_public_id))
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        content = get_private_object(document.object_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NoSuchObject"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found") from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Document storage is unavailable") from exc

    filename = quote(document.original_filename, safe="")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "Cache-Control": "private, no-store",
        },
    )


@projects_router.get("", response_model=ProjectListResponse)
def list_projects(
    search: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="id", max_length=32),
    sort_direction: str = Query(default="asc", max_length=4),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    filters = []
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(Project.id.ilike(term), Project.name.ilike(term)))

    total = db.scalar(select(func.count()).select_from(Project).where(*filters)) or 0
    sort_columns = {
        "id": Project.id,
        "name": Project.name,
        "typology": Typology.name,
        "location": Location.name,
        "supervisor": Supervisor.name,
        "project_manager": ProjectManager.name,
        "project_admin": ProjectAdmin.name,
    }
    if sort_by not in sort_columns:
        raise HTTPException(status_code=422, detail="Invalid project sort column")
    if sort_direction not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid project sort direction")
    sort_column = sort_columns[sort_by]
    sort_order = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
    rows = db.execute(
        select(
            Project,
            Typology.name.label("typology"),
            Location.name.label("location"),
            Supervisor.name.label("supervisor"),
            ProjectManager.name.label("project_manager"),
            ProjectAdmin.name.label("project_admin"),
        )
        .join(Typology, Typology.id == Project.typology_id)
        .join(Location, Location.id == Project.location_id)
        .join(Supervisor, Supervisor.id == Project.supervisor_id)
        .outerjoin(ProjectAdmin, ProjectAdmin.id == Project.project_admin_id)
        .outerjoin(ProjectManager, ProjectManager.id == ProjectAdmin.project_manager_id)
        .where(*filters)
        .order_by(sort_order, Project.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return ProjectListResponse(
        items=[
            ProjectListItem(
                id=project.id,
                public_id=project.public_id,
                name=project.name,
                typology=typology,
                location=location,
                municipal_reception_date=project.municipal_reception_date,
                supervisor=supervisor,
                project_manager=project_manager,
                project_admin=project_admin,
            )
            for project, typology, location, supervisor, project_manager, project_admin in rows
        ],
        page=PageMeta(total=total, limit=limit, offset=offset),
    )


@postventa_items_router.get("", response_model=PostventaItemListResponse)
def list_postventa_items(
    project_id: str | None = Query(default=None, max_length=100),
    project_manager_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    document_status: str | None = Query(default=None, max_length=32),
    reconciliation_status: str | None = Query(default=None, max_length=16),
    has_document: bool | None = Query(default=None),
    unassociated: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="project_id", max_length=32),
    sort_direction: str = Query(default="asc", max_length=4),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PostventaItemListResponse:
    cause_exists = select(PostventaItemFailureCause.postventa_item_id).where(
        PostventaItemFailureCause.postventa_item_id == PostventaItem.id
    ).correlate(PostventaItem).exists()
    document_exists = select(DocumentPostventaItem.postventa_item_id).where(
        DocumentPostventaItem.postventa_item_id == PostventaItem.id
    ).correlate(PostventaItem).exists()
    filters = []
    if project_id:
        filters.append(PostventaItem.project_id == project_id)
    if project_manager_id is not None:
        filters.append(ProjectManager.id == project_manager_id)
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(PostventaItem.notes.ilike(term), Project.name.ilike(term), Project.id.ilike(term)))
    if document_status:
        filters.append(Document.status == document_status)
    if reconciliation_status:
        normalized_status = reconciliation_status.upper()
        if normalized_status not in {"PENDING", "RECONCILED"}:
            raise HTTPException(status_code=422, detail="Reconciliation status must be PENDING or RECONCILED")
        filters.append(cause_exists if normalized_status == "RECONCILED" else ~cause_exists)
    if has_document is not None:
        filters.append(document_exists if has_document else ~document_exists)
    if unassociated:
        filters.append(~document_exists)

    reconciliation_label = case((cause_exists, "RECONCILED"), else_="PENDING")
    sort_columns = {
        "project_id": PostventaItem.project_id,
        "notes": PostventaItem.notes,
        "reconciliation_status": reconciliation_label,
    }
    if sort_by not in sort_columns:
        raise HTTPException(status_code=422, detail="Invalid postventa item sort column")
    if sort_direction not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid postventa item sort direction")
    sort_column = sort_columns[sort_by]
    sort_order = sort_column.asc() if sort_direction == "asc" else sort_column.desc()

    base = (
        select(PostventaItem)
        .join(Project, Project.id == PostventaItem.project_id)
        .outerjoin(ProjectAdmin, ProjectAdmin.id == Project.project_admin_id)
        .outerjoin(ProjectManager, ProjectManager.id == ProjectAdmin.project_manager_id)
        .outerjoin(DocumentPostventaItem, DocumentPostventaItem.postventa_item_id == PostventaItem.id)
        .outerjoin(Document, Document.id == DocumentPostventaItem.document_id)
        .where(*filters)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        select(
            PostventaItem,
            Project.name.label("project_name"),
            Classification.name.label("classification"),
            ItemType.name.label("item_type"),
            Subcontractor.name.label("subcontractor"),
            Document,
            cause_exists.label("is_reconciled"),
            document_exists.label("has_document"),
        )
        .join(Project, Project.id == PostventaItem.project_id)
        .outerjoin(ProjectAdmin, ProjectAdmin.id == Project.project_admin_id)
        .outerjoin(ProjectManager, ProjectManager.id == ProjectAdmin.project_manager_id)
        .join(Classification, Classification.id == PostventaItem.classification_id)
        .join(ItemType, ItemType.id == PostventaItem.item_type_id)
        .outerjoin(Subcontractor, Subcontractor.id == PostventaItem.subcontractor_id)
        .outerjoin(DocumentPostventaItem, DocumentPostventaItem.postventa_item_id == PostventaItem.id)
        .outerjoin(Document, Document.id == DocumentPostventaItem.document_id)
        .where(*filters)
        .order_by(sort_order, PostventaItem.id)
        .limit(limit)
        .offset(offset)
    ).all()
    item_ids = [item.id for item, *_ in rows]
    causes_by_item = _failure_cause_summaries(db, item_ids)
    return PostventaItemListResponse(
        items=[
            PostventaItemListItem(
                id=item.id,
                public_id=item.public_id,
                project_id=item.project_id,
                project_name=project_name,
                classification=classification,
                item_type=item_type,
                notes=item.notes,
                request_date=item.request_date,
                subcontractor=subcontractor,
                handled_by=item.handled_by,
                failure_causes=causes_by_item.get(item.id, []),
                reconciliation_status="RECONCILED" if is_reconciled else "PENDING",
                has_document=has_document,
                document=DocumentSummary(
                    public_id=document.public_id,
                    original_filename=document.original_filename,
                    status=document.status,
                    uploaded_at=document.uploaded_at,
                    processed_at=document.processed_at,
                ) if document else None,
            )
            for item, project_name, classification, item_type, subcontractor, document, is_reconciled, has_document in rows
        ],
        page=PageMeta(total=total, limit=limit, offset=offset),
    )


def _postventa_item_detail(db: Session, public_id: UUID) -> PostventaItemListItem:
    cause_exists = select(PostventaItemFailureCause.postventa_item_id).where(
        PostventaItemFailureCause.postventa_item_id == PostventaItem.id
    ).correlate(PostventaItem).exists()
    document_exists = select(DocumentPostventaItem.postventa_item_id).where(
        DocumentPostventaItem.postventa_item_id == PostventaItem.id
    ).correlate(PostventaItem).exists()
    row = db.execute(
        select(
            PostventaItem,
            Project.name.label("project_name"),
            Classification.name.label("classification"),
            ItemType.name.label("item_type"),
            Subcontractor.name.label("subcontractor"),
            Document,
            cause_exists.label("is_reconciled"),
            document_exists.label("has_document"),
        )
        .join(Project, Project.id == PostventaItem.project_id)
        .join(Classification, Classification.id == PostventaItem.classification_id)
        .join(ItemType, ItemType.id == PostventaItem.item_type_id)
        .outerjoin(Subcontractor, Subcontractor.id == PostventaItem.subcontractor_id)
        .outerjoin(DocumentPostventaItem, DocumentPostventaItem.postventa_item_id == PostventaItem.id)
        .outerjoin(Document, Document.id == DocumentPostventaItem.document_id)
        .where(PostventaItem.public_id == public_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Postventa item not found")
    item, project_name, classification, item_type, subcontractor, document, is_reconciled, has_document = row
    causes = _failure_cause_summaries(db, [item.id])[item.id]
    return PostventaItemListItem(
        id=item.id,
        public_id=item.public_id,
        project_id=item.project_id,
        project_name=project_name,
        classification=classification,
        item_type=item_type,
        notes=item.notes,
        request_date=item.request_date,
        subcontractor=subcontractor,
        handled_by=item.handled_by,
        failure_causes=causes,
        reconciliation_status="RECONCILED" if is_reconciled else "PENDING",
        has_document=has_document,
        document=DocumentSummary(
            public_id=document.public_id,
            original_filename=document.original_filename,
            status=document.status,
            uploaded_at=document.uploaded_at,
            processed_at=document.processed_at,
        ) if document else None,
    )


@postventa_items_router.get("/{public_id}", response_model=PostventaItemListItem)
def get_postventa_item(public_id: UUID, _: dict = Depends(require_admin), db: Session = Depends(get_db)) -> PostventaItemListItem:
    return _postventa_item_detail(db, public_id)


@postventa_items_router.put("/{public_id}/failure-causes", response_model=PostventaItemListItem)
def replace_postventa_item_failure_causes(
    public_id: UUID,
    payload: PostventaItemFailureCauseUpdateRequest,
    claims: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PostventaItemListItem:
    cause_codes = list(dict.fromkeys(payload.failure_cause_codes))
    causes = db.scalars(
        select(FailureCause)
        .where(FailureCause.code.in_(cause_codes), FailureCause.is_active.is_(True))
        .order_by(FailureCause.code)
    ).all() if cause_codes else []
    if len(causes) != len(cause_codes):
        raise HTTPException(status_code=422, detail="One or more failure causes are inactive or do not exist")

    item = db.scalar(select(PostventaItem).where(PostventaItem.public_id == public_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Postventa item not found")

    selected_cause_ids = {cause.id for cause in causes}
    current = db.scalars(
        select(PostventaItemFailureCause)
        .where(PostventaItemFailureCause.postventa_item_id == item.id)
        .with_for_update()
    ).all()
    current_by_cause_id = {assignment.failure_cause_id: assignment for assignment in current}
    for assignment in current:
        if assignment.failure_cause_id not in selected_cause_ids:
            db.delete(assignment)
    for cause in causes:
        if cause.id not in current_by_cause_id:
            db.add(PostventaItemFailureCause(
                postventa_item_id=item.id,
                failure_cause_id=cause.id,
                assignment_source="DIRECT_MANUAL",
                assigned_by=_actor_name(claims),
            ))
    item.failure_cause_id = causes[0].id if causes else None
    db.commit()
    invalidate_dashboard_summary()
    return _postventa_item_detail(db, public_id)


@postventa_items_router.delete("/{public_id}/documents/{document_public_id}", response_model=PostventaItemListItem)
def remove_postventa_item_document(
    public_id: UUID,
    document_public_id: UUID,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PostventaItemListItem:
    """Detach a PDF without deleting its private object or direct reconciliation."""
    item = db.scalar(select(PostventaItem).where(PostventaItem.public_id == public_id).with_for_update())
    document = db.scalar(select(Document).where(Document.public_id == document_public_id).with_for_update())
    if item is None or document is None:
        raise HTTPException(status_code=404, detail="Postventa item or document not found")
    association = db.get(DocumentPostventaItem, (document.id, item.id))
    if association is None:
        raise HTTPException(status_code=404, detail="The document is not associated with this item")

    source_key = document.object_key
    db.delete(association)
    # Causes explicitly assigned from the evaluation page are independent of a
    # PDF. Causes derived from this PDF cease to apply when it is detached.
    sourced_causes = db.scalars(
        select(PostventaItemFailureCause)
        .where(
            PostventaItemFailureCause.postventa_item_id == item.id,
            PostventaItemFailureCause.source_document_id == document.id,
            PostventaItemFailureCause.assignment_source.in_(("AUTOMATIC", "MANUAL")),
        )
    ).all()
    for cause in sourced_causes:
        db.delete(cause)
    db.flush()

    remaining_cause_ids = db.scalars(
        select(PostventaItemFailureCause.failure_cause_id)
        .where(PostventaItemFailureCause.postventa_item_id == item.id)
        .order_by(PostventaItemFailureCause.failure_cause_id)
    ).all()
    item.failure_cause_id = remaining_cause_ids[0] if remaining_cause_ids else None

    remaining_document_links = db.scalar(
        select(func.count()).select_from(DocumentPostventaItem)
        .where(DocumentPostventaItem.document_id == document.id)
    ) or 0
    if remaining_document_links == 0:
        document.status = "PENDING_REVIEW"
        _move_document(document, "pending-review")
    db.commit()
    if remaining_document_links == 0 and source_key != document.object_key:
        try:
            delete_private_object(source_key)
        except Exception:
            logger.warning("Could not remove old object after disassociating document_id=%s", document.id)
    invalidate_dashboard_summary()
    return _postventa_item_detail(db, public_id)
