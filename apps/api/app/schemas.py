from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    environment: str


class ExcelImportResponse(BaseModel):
    import_id: UUID
    status: str
    row_count: int
    created: bool


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class ProjectListItem(BaseModel):
    id: str
    public_id: UUID
    name: str
    typology: str
    location: str
    municipal_reception_date: date | None
    supervisor: str
    project_manager: str | None
    project_admin: str | None


class ProjectListResponse(BaseModel):
    items: list[ProjectListItem]
    page: PageMeta


class FailureCauseSummary(BaseModel):
    code: str
    display_name_es: str
    category_code: str
    category_name_es: str


class DocumentSummary(BaseModel):
    public_id: UUID
    original_filename: str
    status: str
    uploaded_at: datetime
    processed_at: datetime | None


class PostventaItemListItem(BaseModel):
    id: int
    public_id: UUID
    project_id: str
    project_name: str
    classification: str
    item_type: str
    notes: str
    request_date: date | None
    subcontractor: str | None
    handled_by: str | None
    failure_cause: FailureCauseSummary | None
    document: DocumentSummary | None


class PostventaItemListResponse(BaseModel):
    items: list[PostventaItemListItem]
    page: PageMeta
