"""Superset guest token brokerage and verified Keycloak scope construction."""

import json
import logging
import re
import threading
import time
from urllib.parse import urlsplit

import httpx

from fastapi import HTTPException, status

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)
ANALYTICS_ROLES = {"superset_admin", "superset_viewer", "superset_dashboard_builder"}
CURATED_DATASETS = (
    "analytics.postventa_item_dashboard",
    "analytics.postventa_item_cause_dashboard",
    "analytics.postventa_item_cause_pareto",
)
GROUP_RE = re.compile(r"^/superset/(division|project)/([A-Za-z0-9_-]{1,64})$")
MAX_SCOPES = 100


def analytics_scope(claims: dict) -> tuple[bool, str | None]:
    """Return global-admin status and a fail-closed clause from signed groups."""
    realm_access = claims.get("realm_access", {})
    roles_value = realm_access.get("roles", []) if isinstance(realm_access, dict) else None
    if not isinstance(roles_value, list) or any(not isinstance(role, str) for role in roles_value):
        raise HTTPException(status_code=403, detail="Invalid analytics role claims")
    roles = set(roles_value)
    if not roles.intersection(ANALYTICS_ROLES):
        raise HTTPException(status_code=403, detail="Analytics role required")
    if "superset_admin" in roles:
        return True, "1 = 1"

    groups = claims.get("groups", [])
    if not isinstance(groups, list) or any(not isinstance(group, str) for group in groups):
        raise HTTPException(status_code=403, detail="Invalid analytics scope")
    divisions: set[str] = set()
    projects: set[str] = set()
    for group in groups:
        match = GROUP_RE.fullmatch(group)
        if not match and group.startswith(("/superset/division/", "/superset/project/")):
            raise HTTPException(status_code=403, detail="Invalid analytics scope")
        if match:
            kind, value = match.groups()
            if kind == "division":
                if not value.isdigit():
                    raise HTTPException(status_code=403, detail="Invalid analytics scope")
                divisions.add(value)
            else:
                projects.add(value)
    if len(divisions) + len(projects) > MAX_SCOPES:
        raise HTTPException(status_code=403, detail="Analytics scope is too large")
    clauses = []
    if divisions:
        clauses.append("division_manager_id IN (" + ",".join(sorted(divisions, key=int)) + ")")
    if projects:
        quoted = ",".join("'" + project.replace("'", "''") + "'" for project in sorted(projects))
        clauses.append(f"numero_obra IN ({quoted})")
    if not clauses:
        raise HTTPException(status_code=403, detail="Analytics scope required")
    return False, "(" + " OR ".join(clauses) + ")"


def require_analytics_admin(claims: dict) -> dict:
    """Require app administrator plus a separate analytics entitlement."""
    realm_access = claims.get("realm_access", {})
    realm_roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    resource_access = claims.get("resource_access", {})
    resource = resource_access.get(get_settings().OIDC_AUDIENCE, {}) if isinstance(resource_access, dict) else {}
    resource_roles = resource.get("roles", []) if isinstance(resource, dict) else []
    if (
        not isinstance(realm_roles, list)
        or any(not isinstance(role, str) for role in realm_roles)
        or not isinstance(resource_roles, list)
        or any(not isinstance(role, str) for role in resource_roles)
    ):
        raise HTTPException(status_code=403, detail="Invalid role claims")
    if "admin" not in set(realm_roles) | set(resource_roles):
        raise HTTPException(status_code=403, detail="Admin role required")
    # Build and validate the exact scope before making any upstream request.
    analytics_scope(claims)
    return claims


def embed_configuration(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    origins = [origin.strip().rstrip("/") for origin in settings.SUPERSET_EMBED_ALLOWED_ORIGINS.split(",") if origin.strip()]
    valid_origins = all(_is_origin(origin) for origin in origins)
    return {
        "enabled": bool(
            settings.SUPERSET_EMBEDDING_ENABLED
            and _is_origin(settings.SUPERSET_PUBLIC_URL.rstrip("/"))
            and settings.SUPERSET_PUBLIC_URL
            and settings.SUPERSET_EMBEDDED_DASHBOARD_UUID
            and settings.SUPERSET_EMBED_SERVICE_USERNAME
            and settings.SUPERSET_EMBED_SERVICE_PASSWORD
            and origins
            and valid_origins
        ),
        "origins": origins,
    }


def _is_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and not parsed.username
        and not parsed.password
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


class SupersetTokenBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._client = httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0))

    def issue(self, clause: str) -> tuple[str, int]:
        settings = get_settings()
        if not embed_configuration(settings)["enabled"] or not settings.SUPERSET_EMBED_SERVICE_USERNAME or not settings.SUPERSET_EMBED_SERVICE_PASSWORD:
            raise HTTPException(status_code=503, detail="Analytics embedding is unavailable")
        payload = {
            "user": {"username": "ingevec-embedded-viewer", "first_name": "Ingevec", "last_name": "Viewer"},
            "resources": [{"type": "dashboard", "id": settings.SUPERSET_EMBEDDED_DASHBOARD_UUID}],
            "rls": [{"clause": clause} for _ in CURATED_DATASETS],
        }
        with self._lock:
            for attempt in range(2):
                try:
                    token = self._issuer_token(settings)
                    csrf = self._csrf_token(settings, token)
                    response = self._request(
                        settings.SUPERSET_INTERNAL_URL.rstrip("/") + "/api/v1/security/guest_token/",
                        {"Authorization": f"Bearer {token}", "X-CSRFToken": csrf},
                        payload,
                    )
                    guest = response.get("token")
                    if not isinstance(guest, str) or not guest:
                        raise RuntimeError("Superset did not return a guest token")
                    return guest, settings.SUPERSET_GUEST_TOKEN_TTL_SECONDS
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 401 and attempt == 0:
                        self._access_token = None
                        continue
                    logger.warning("Superset guest-token request failed with status %s", exc.response.status_code)
                    break
                except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                    logger.warning("Superset guest-token service is unavailable (%s)", type(exc).__name__)
                    break
        raise HTTPException(status_code=503, detail="Analytics embedding is temporarily unavailable")

    def _issuer_token(self, settings: Settings) -> str:
        if self._access_token and time.monotonic() < self._expires_at - 20:
            return self._access_token
        result = self._request(
            settings.SUPERSET_INTERNAL_URL.rstrip("/") + "/api/v1/security/login",
            {},
            {"username": settings.SUPERSET_EMBED_SERVICE_USERNAME, "password": settings.SUPERSET_EMBED_SERVICE_PASSWORD, "provider": "db", "refresh": False},
        )
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Superset issuer authentication failed")
        expires_in = result.get("expires_in", 300)
        self._access_token = token
        self._expires_at = time.monotonic() + (expires_in if isinstance(expires_in, int) else 300)
        return token

    def _csrf_token(self, settings: Settings, access_token: str) -> str:
        try:
            result = self._request(
                settings.SUPERSET_INTERNAL_URL.rstrip("/") + "/api/v1/security/csrf_token/",
                {"Authorization": f"Bearer {access_token}"},
                None,
                method="GET",
            )
            return str(result.get("result", ""))
        except Exception as exc:
            logger.warning("Superset CSRF token request failed (%s)", type(exc).__name__)
            return ""

    def _request(self, url: str, headers: dict, payload: dict | None, method: str | None = None) -> dict:
        response = self._client.request(method or ("POST" if payload is not None else "GET"), url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


token_broker = SupersetTokenBroker()
