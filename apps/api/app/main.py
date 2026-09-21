from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import dashboard_router, documents_router, imports_router, postventa_items_router, projects_router
from app.core.config import get_settings
from app.schemas import HealthResponse

settings = get_settings()
app = FastAPI(title=settings.APP_NAME, version="0.1.0")
allowed_origins = [origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.include_router(imports_router, prefix=settings.API_PREFIX)
app.include_router(documents_router, prefix=settings.API_PREFIX)
app.include_router(projects_router, prefix=settings.API_PREFIX)
app.include_router(postventa_items_router, prefix=settings.API_PREFIX)
app.include_router(dashboard_router, prefix=settings.API_PREFIX)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.APP_ENV)
