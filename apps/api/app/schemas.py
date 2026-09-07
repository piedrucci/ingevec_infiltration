from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    environment: str


class DashboardBreakdown(BaseModel):
    name: str
    count: int


class DashboardAssociationBreakdown(BaseModel):
    name: str
    items: int
    associated_items: int
    pending_items: int
    association_rate: float


class DashboardTotals(BaseModel):
    items: int
    associated_items: int
    pending_items: int
    association_rate: float
    documents: int
    documents_by_status: dict[str, int]


class DashboardSummary(BaseModel):
    generated_at: datetime
    totals: DashboardTotals
    breakdowns: dict[str, list[DashboardBreakdown]]
    project_manager_association_progress: list[DashboardAssociationBreakdown]


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


class DocumentListItem(DocumentSummary):
    matching_confidence: float | None
    extracted_data: dict | None
    extracted_failure_cause: str | None
    processing_error: str | None
    association_count: int


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    page: PageMeta


class DocumentAssociationItem(BaseModel):
    postventa_item_public_id: UUID
    postventa_item_id: int
    project_id: str
    project_name: str
    notes: str
    association_source: str
    confidence: float | None
    rationale: str | None


class DocumentDetail(DocumentListItem):
    associations: list[DocumentAssociationItem]


class DocumentCandidate(BaseModel):
    postventa_item_public_id: UUID
    postventa_item_id: int
    project_id: str
    project_name: str
    notes: str
    score: float


class DocumentCandidateResponse(BaseModel):
    items: list[DocumentCandidate]


class FailureCauseOption(BaseModel):
    code: str
    display_name_es: str
    category_name_es: str


class FailureCauseCategoryOption(BaseModel):
    code: str
    display_name_es: str


class CreateFailureCauseRequest(BaseModel):
    code: str = Field(min_length=2, max_length=100)
    display_name_es: str = Field(min_length=2, max_length=255)
    category_code: str = Field(min_length=2, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class ManualDocumentAssociationRequest(BaseModel):
    postventa_item_public_ids: list[UUID]
    failure_cause_code: str


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
