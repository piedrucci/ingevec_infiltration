from fastapi import FastAPI

from app.api import dashboard_router, documents_router, imports_router, postventa_items_router, projects_router
from app.core.config import get_settings
from app.schemas import HealthResponse

settings = get_settings()
app = FastAPI(title=settings.APP_NAME, version="0.1.0")
app.include_router(imports_router, prefix=settings.API_PREFIX)
app.include_router(documents_router, prefix=settings.API_PREFIX)
app.include_router(projects_router, prefix=settings.API_PREFIX)
app.include_router(postventa_items_router, prefix=settings.API_PREFIX)
app.include_router(dashboard_router, prefix=settings.API_PREFIX)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.APP_ENV)
