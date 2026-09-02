from zipfile import BadZipFile
from urllib.parse import quote
from uuid import UUID

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.core.config import get_settings
from app.models import (
    Classification,
    Document,
    DocumentPostventaItem,
    FailureCause,
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
    DocumentSummary,
    ExcelImportResponse,
    FailureCauseSummary,
    PageMeta,
    PostventaItemListItem,
    PostventaItemListResponse,
    ProjectListItem,
    ProjectListResponse,
)
from app.services.excel_importer import import_workbook
from app.services.storage import get_private_object

imports_router = APIRouter(prefix="/imports", tags=["imports"])
projects_router = APIRouter(prefix="/projects", tags=["projects"])
postventa_items_router = APIRouter(prefix="/postventa-items", tags=["postventa-items"])
documents_router = APIRouter(prefix="/documents", tags=["documents"])


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
    return ExcelImportResponse(import_id=imported.id, status=imported.status, row_count=imported.row_count, created=created)


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
            Document,
        )
        .join(Project, Project.id == PostventaItem.project_id)
        .join(Classification, Classification.id == PostventaItem.classification_id)
        .join(ItemType, ItemType.id == PostventaItem.item_type_id)
        .outerjoin(Subcontractor, Subcontractor.id == PostventaItem.subcontractor_id)
        .outerjoin(FailureCause, FailureCause.id == PostventaItem.failure_cause_id)
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
                    category_code=cause.category_code,
                    category_name_es=cause.category_name_es,
                ) if cause else None,
                document=DocumentSummary(
                    public_id=document.public_id,
                    original_filename=document.original_filename,
                    status=document.status,
                    uploaded_at=document.uploaded_at,
                    processed_at=document.processed_at,
                ) if document else None,
            )
            for item, project_name, classification, item_type, subcontractor, cause, document in rows
        ],
        page=PageMeta(total=total, limit=limit, offset=offset),
    )
