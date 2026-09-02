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
