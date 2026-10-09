from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from starlette.concurrency import run_in_threadpool

from app.auth import require_admin
from app.core.config import get_settings
from app.schemas import EmbeddedDashboardMetadata, GuestTokenResponse
from app.services.analytics_embedding import analytics_scope, embed_configuration, require_analytics_admin, token_broker

analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])


@analytics_router.get("/dashboard", response_model=EmbeddedDashboardMetadata)
def dashboard_metadata(claims: dict = Depends(require_admin)) -> EmbeddedDashboardMetadata:
    require_analytics_admin(claims)
    settings = get_settings()
    configuration = embed_configuration(settings)
    if not configuration["enabled"]:
        return EmbeddedDashboardMetadata(enabled=False)
    return EmbeddedDashboardMetadata(
        enabled=True,
        dashboard_uuid=settings.SUPERSET_EMBEDDED_DASHBOARD_UUID,
        superset_url=settings.SUPERSET_PUBLIC_URL.rstrip("/"),
        title="Analítica",
    )


@analytics_router.post("/guest-token", response_model=GuestTokenResponse)
async def guest_token(request: Request, response: Response, claims: dict = Depends(require_admin)) -> GuestTokenResponse:
    require_analytics_admin(claims)
    if request.query_params or (await request.body()).strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dashboard and scope are fixed by the server")
    settings = get_settings()
    if not embed_configuration(settings)["enabled"]:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Analytics embedding is unavailable")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    _, clause = analytics_scope(claims)
    token, ttl = await run_in_threadpool(token_broker.issue, clause or "1 = 0")
    return GuestTokenResponse(token=token, expires_in=ttl)
