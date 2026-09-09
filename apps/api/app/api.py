from zipfile import BadZipFile
from urllib.parse import quote
from uuid import UUID

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import func, or_, select
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
    PostventaItemListItem,
    PostventaItemListResponse,
    ProjectListItem,
    ProjectListResponse,
)
from app.services.dashboard import dashboard_summary
from app.services.dashboard_cache import invalidate_dashboard_summary
from app.services.document_candidates import find_document_candidates
from app.services.document_processor import _location_score, _move_document
from app.services.document_upload import DuplicateDocumentError, register_pdf_upload
from app.services.failure_causes import create_failure_cause
from app.services.excel_importer import import_workbook
from app.services.storage import delete_private_object, get_private_object

imports_router = APIRouter(prefix="/imports", tags=["imports"])
projects_router = APIRouter(prefix="/projects", tags=["projects"])
postventa_items_router = APIRouter(prefix="/postventa-items", tags=["postventa-items"])
documents_router = APIRouter(prefix="/documents", tags=["documents"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _document_list_item(document: Document, association_count: int) -> DocumentListItem:
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
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    filters = []
    if document_status:
        filters.append(Document.status == document_status)
    if search:
        filters.append(Document.original_filename.ilike(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(Document).where(*filters)) or 0
    rows = db.execute(
        select(Document, func.count(DocumentPostventaItem.postventa_item_id).label("association_count"))
        .outerjoin(DocumentPostventaItem, DocumentPostventaItem.document_id == Document.id)
        .where(*filters)
        .group_by(Document.id)
        .order_by(Document.uploaded_at.desc(), Document.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return DocumentListResponse(
        items=[_document_list_item(document, association_count) for document, association_count in rows],
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
    cause = db.scalar(select(FailureCause).where(FailureCause.code == payload.failure_cause_code, FailureCause.is_active.is_(True)))
    if cause is None:
        raise HTTPException(status_code=422, detail="Failure cause is not active or does not exist")
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
            item.failure_cause_id = cause.id
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
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    filters = []
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(Project.id.ilike(term), Project.name.ilike(term)))

    total = db.scalar(select(func.count()).select_from(Project).where(*filters)) or 0
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
        .order_by(Project.id)
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
    search: str | None = Query(default=None, min_length=1, max_length=100),
    document_status: str | None = Query(default=None, max_length=32),
    unassociated: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PostventaItemListResponse:
    filters = []
    if project_id:
        filters.append(PostventaItem.project_id == project_id)
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(PostventaItem.notes.ilike(term), Project.name.ilike(term), Project.id.ilike(term)))
    if document_status:
        filters.append(Document.status == document_status)
    if unassociated:
        filters.append(DocumentPostventaItem.document_id.is_(None))

    base = (
        select(PostventaItem)
        .join(Project, Project.id == PostventaItem.project_id)
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
            FailureCause,
            FailureCauseCategory,
            Document,
        )
        .join(Project, Project.id == PostventaItem.project_id)
        .join(Classification, Classification.id == PostventaItem.classification_id)
        .join(ItemType, ItemType.id == PostventaItem.item_type_id)
        .outerjoin(Subcontractor, Subcontractor.id == PostventaItem.subcontractor_id)
        .outerjoin(FailureCause, FailureCause.id == PostventaItem.failure_cause_id)
        .outerjoin(FailureCauseCategory, FailureCauseCategory.id == FailureCause.category_id)
        .outerjoin(DocumentPostventaItem, DocumentPostventaItem.postventa_item_id == PostventaItem.id)
        .outerjoin(Document, Document.id == DocumentPostventaItem.document_id)
        .where(*filters)
        .order_by(PostventaItem.id)
        .limit(limit)
        .offset(offset)
    ).all()
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
                failure_cause=FailureCauseSummary(
                    code=cause.code,
                    display_name_es=cause.display_name_es,
                    category_code=category.code,
                    category_name_es=category.display_name_es,
                ) if cause and category else None,
                document=DocumentSummary(
                    public_id=document.public_id,
                    original_filename=document.original_filename,
                    status=document.status,
                    uploaded_at=document.uploaded_at,
                    processed_at=document.processed_at,
                ) if document else None,
            )
            for item, project_name, classification, item_type, subcontractor, cause, category, document in rows
        ],
        page=PageMeta(total=total, limit=limit, offset=offset),
    )
