from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.auth import current_claims, require_admin
from app.main import app
from app.services import analytics_embedding


def test_scoped_roles_build_union_from_valid_groups():
    is_global, clause = analytics_embedding.analytics_scope({
        "realm_access": {"roles": ["superset_viewer"]},
        "groups": ["/superset/division/12", "/superset/project/OBRA-7", "/other/99"],
    })
    assert not is_global
    assert clause == "(division_manager_id IN (12) OR numero_obra IN ('OBRA-7'))"


def test_analytics_admin_receives_explicit_global_clause():
    is_global, clause = analytics_embedding.analytics_scope({"realm_access": {"roles": ["superset_admin"]}})
    assert is_global
    assert clause == "1 = 1"


@pytest.mark.parametrize("claims", [
    {"realm_access": {"roles": ["admin"]}, "groups": ["/superset/project/1"]},
    {"realm_access": {"roles": ["superset_viewer"]}, "groups": []},
    {"realm_access": {"roles": ["superset_viewer"]}, "groups": ["/superset/division/not-a-number"]},
    {"realm_access": {"roles": ["superset_viewer"]}, "groups": ["/superset/project/P-1' OR 1=1 --"]},
    {"realm_access": {"roles": ["superset_viewer"]}, "groups": "not-a-list"},
])
def test_invalid_or_unscoped_claims_fail_closed(claims):
    with pytest.raises(HTTPException) as error:
        analytics_embedding.analytics_scope(claims)
    assert error.value.status_code == 403


def test_excessive_scope_is_denied():
    claims = {
        "realm_access": {"roles": ["superset_viewer"]},
        "groups": [f"/superset/project/P{i}" for i in range(101)],
    }
    with pytest.raises(HTTPException, match="too large"):
        analytics_embedding.analytics_scope(claims)


def test_embedding_configuration_rejects_non_origin_values():
    settings = SimpleNamespace(
        SUPERSET_EMBEDDING_ENABLED=True,
        SUPERSET_PUBLIC_URL="https://bi.example.test/dashboard",
        SUPERSET_EMBEDDED_DASHBOARD_UUID="embed-uuid",
        SUPERSET_EMBED_SERVICE_USERNAME="issuer",
        SUPERSET_EMBED_SERVICE_PASSWORD="password",
        SUPERSET_EMBED_ALLOWED_ORIGINS="https://app.example.test/path",
    )
    assert analytics_embedding.embed_configuration(settings)["enabled"] is False


def test_token_broker_uses_fixed_dashboard_and_scope(monkeypatch):
    settings = SimpleNamespace(
        SUPERSET_EMBEDDING_ENABLED=True,
        SUPERSET_PUBLIC_URL="https://bi.example.test",
        SUPERSET_INTERNAL_URL="http://superset:8088",
        SUPERSET_EMBEDDED_DASHBOARD_UUID="embed-uuid",
        SUPERSET_EMBED_ALLOWED_ORIGINS="https://app.example.test",
        SUPERSET_EMBED_SERVICE_USERNAME="issuer",
        SUPERSET_EMBED_SERVICE_PASSWORD="long-password-value",
        SUPERSET_GUEST_TOKEN_TTL_SECONDS=300,
    )
    monkeypatch.setattr(analytics_embedding, "get_settings", lambda: settings)
    broker = analytics_embedding.SupersetTokenBroker()
    responses = iter([
        {"access_token": "private-access", "expires_in": 300},
        {"result": "csrf"},
        {"token": "private-guest-token"},
    ])
    calls = []
    def mocked_request(url, headers, payload, method=None):
        calls.append((url, headers, payload, method))
        return next(responses)
    monkeypatch.setattr(broker, "_request", mocked_request)

    token, ttl = broker.issue("numero_obra IN ('P-1')")

    assert (token, ttl) == ("private-guest-token", 300)
    assert calls[2][2]["resources"] == [{"type": "dashboard", "id": "embed-uuid"}]
    assert calls[2][2]["rls"] == [{"clause": "numero_obra IN ('P-1')"}] * 3


def test_failed_upstream_response_does_not_expose_response_body(monkeypatch, caplog):
    settings = SimpleNamespace(
        SUPERSET_EMBEDDING_ENABLED=True,
        SUPERSET_PUBLIC_URL="https://bi.example.test",
        SUPERSET_INTERNAL_URL="http://superset:8088",
        SUPERSET_EMBEDDED_DASHBOARD_UUID="embed-uuid",
        SUPERSET_EMBED_ALLOWED_ORIGINS="https://app.example.test",
        SUPERSET_EMBED_SERVICE_USERNAME="issuer",
        SUPERSET_EMBED_SERVICE_PASSWORD="long-password-value",
        SUPERSET_GUEST_TOKEN_TTL_SECONDS=300,
    )
    monkeypatch.setattr(analytics_embedding, "get_settings", lambda: settings)
    broker = analytics_embedding.SupersetTokenBroker()
    broker._request = Mock(side_effect=RuntimeError("private-response-body"))
    with pytest.raises(HTTPException) as error:
        broker.issue("1 = 0")
    assert error.value.status_code == 503
    assert "private-response-body" not in caplog.text


def test_connection_failure_is_sanitized_and_returns_unavailable(monkeypatch, caplog):
    settings = SimpleNamespace(
        SUPERSET_EMBEDDING_ENABLED=True, SUPERSET_PUBLIC_URL="https://bi.example.test",
        SUPERSET_INTERNAL_URL="http://superset:8088", SUPERSET_EMBEDDED_DASHBOARD_UUID="embed-uuid",
        SUPERSET_EMBED_ALLOWED_ORIGINS="https://app.example.test", SUPERSET_EMBED_SERVICE_USERNAME="private-issuer",
        SUPERSET_EMBED_SERVICE_PASSWORD="private-password-value", SUPERSET_GUEST_TOKEN_TTL_SECONDS=300,
    )
    monkeypatch.setattr(analytics_embedding, "get_settings", lambda: settings)
    broker = analytics_embedding.SupersetTokenBroker()
    broker._request = Mock(side_effect=httpx.ConnectError("private-host-and-query"))
    with pytest.raises(HTTPException) as error:
        broker.issue("1 = 0")
    assert error.value.status_code == 503
    assert "private-host-and-query" not in caplog.text
    assert "private-issuer" not in caplog.text
    assert "private-password-value" not in caplog.text


def test_expired_issuer_session_is_reauthenticated_once(monkeypatch):
    settings = SimpleNamespace(
        SUPERSET_EMBEDDING_ENABLED=True, SUPERSET_PUBLIC_URL="https://bi.example.test",
        SUPERSET_INTERNAL_URL="http://superset:8088", SUPERSET_EMBEDDED_DASHBOARD_UUID="embed-uuid",
        SUPERSET_EMBED_ALLOWED_ORIGINS="https://app.example.test", SUPERSET_EMBED_SERVICE_USERNAME="issuer",
        SUPERSET_EMBED_SERVICE_PASSWORD="long-password-value", SUPERSET_GUEST_TOKEN_TTL_SECONDS=300,
    )
    monkeypatch.setattr(analytics_embedding, "get_settings", lambda: settings)
    broker = analytics_embedding.SupersetTokenBroker()
    calls = []
    unauthorized = httpx.HTTPStatusError("unauthorized", request=httpx.Request("POST", "http://superset/guest"), response=httpx.Response(401))
    responses = iter([
        {"access_token": "old-access", "expires_in": 300}, {"result": "csrf"}, unauthorized,
        {"access_token": "new-access", "expires_in": 300}, {"result": "csrf"}, {"token": "new-guest"},
    ])
    def mocked_request(url, headers, payload, method=None):
        calls.append((url, headers, payload))
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(broker, "_request", mocked_request)

    assert broker.issue("scope") == ("new-guest", 300)
    assert len([call for call in calls if call[0].endswith("/login")]) == 2


def test_metadata_and_guest_token_endpoints_are_authorized_and_no_store(monkeypatch):
    settings = SimpleNamespace(
        OIDC_AUDIENCE="ingevec-api", SUPERSET_EMBEDDING_ENABLED=True,
        SUPERSET_PUBLIC_URL="https://bi.example.test", SUPERSET_INTERNAL_URL="http://superset:8088",
        SUPERSET_EMBEDDED_DASHBOARD_UUID="embed-uuid", SUPERSET_EMBED_ALLOWED_ORIGINS="https://app.example.test",
        SUPERSET_EMBED_SERVICE_USERNAME="issuer", SUPERSET_EMBED_SERVICE_PASSWORD="long-password-value",
        SUPERSET_GUEST_TOKEN_TTL_SECONDS=300,
    )
    monkeypatch.setattr("app.analytics_api.get_settings", lambda: settings)
    monkeypatch.setattr(analytics_embedding, "get_settings", lambda: settings)
    monkeypatch.setattr("app.analytics_api.token_broker.issue", lambda clause: ("one-time-token", 300))
    claims = {"realm_access": {"roles": ["admin", "superset_viewer"]}, "groups": ["/superset/project/OBRA-1"]}
    app.dependency_overrides[require_admin] = lambda: claims
    try:
        client = TestClient(app)
        metadata = client.get("/v1/analytics/dashboard")
        assert metadata.status_code == 200
        assert metadata.json()["dashboard_uuid"] == "embed-uuid"
        token = client.post("/v1/analytics/guest-token")
        assert token.status_code == 200
        assert token.headers["cache-control"] == "no-store"
        assert token.headers["pragma"] == "no-cache"
        assert token.json() == {"token": "one-time-token", "expires_in": 300}
        claims["realm_access"]["roles"] = ["admin"]
        assert client.get("/v1/analytics/dashboard").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_analytics_endpoints_require_app_and_analytics_roles(monkeypatch):
    monkeypatch.setattr("app.analytics_api.get_settings", lambda: SimpleNamespace(
        OIDC_AUDIENCE="ingevec-api", SUPERSET_EMBEDDING_ENABLED=False,
        SUPERSET_PUBLIC_URL="", SUPERSET_EMBEDDED_DASHBOARD_UUID="",
        SUPERSET_EMBED_ALLOWED_ORIGINS="", SUPERSET_EMBED_SERVICE_USERNAME="",
        SUPERSET_EMBED_SERVICE_PASSWORD="",
    ))
    claims = {"realm_access": {"roles": ["admin", "superset_viewer"]}, "groups": ["/superset/project/OBRA-1"]}
    app.dependency_overrides[require_admin] = lambda: claims
    try:
        client = TestClient(app)
        response = client.get("/v1/analytics/dashboard")
        assert response.status_code == 200
        assert response.json() == {"enabled": False, "dashboard_uuid": None, "superset_url": None, "title": None}
        rejected = client.post("/v1/analytics/guest-token", json={"project_id": "other"})
        assert rejected.status_code == 422
        assert "scope are fixed" in rejected.json()["detail"]
        unavailable = client.post("/v1/analytics/guest-token")
        assert unavailable.status_code == 503
        claims["realm_access"]["roles"] = ["admin"]
        denied = client.get("/v1/analytics/dashboard")
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()
    assert TestClient(app).get("/v1/analytics/dashboard").status_code == 401


def test_signed_keycloak_claims_are_verified_before_analytics_authorization(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = SimpleNamespace(
        OIDC_AUDIENCE="ingevec-api",
        OIDC_ISSUER="https://auth.example.test/realms/ingevec",
    )
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.jwks_client", lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key()),
    ))
    payload = {
        "sub": "user-1", "iss": settings.OIDC_ISSUER, "aud": settings.OIDC_AUDIENCE,
        "iat": 1_750_000_000, "exp": 1_900_000_000,
        "realm_access": {"roles": ["admin", "superset_viewer"]},
        "groups": ["/superset/project/OBRA-1"],
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    verified = current_claims(credentials)
    assert require_admin(verified) == verified
    monkeypatch.setattr(analytics_embedding, "get_settings", lambda: settings)
    assert analytics_embedding.require_analytics_admin(verified) == verified

    invalid = jwt.encode(payload, rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256")
    with pytest.raises(HTTPException) as error:
        current_claims(HTTPAuthorizationCredentials(scheme="Bearer", credentials=invalid))
    assert error.value.status_code == 401

    payload["realm_access"]["roles"] = ["admin"]
    app_admin = jwt.encode(payload, private_key, algorithm="RS256")
    app_admin_claims = current_claims(HTTPAuthorizationCredentials(scheme="Bearer", credentials=app_admin))
    with pytest.raises(HTTPException) as denied:
        analytics_embedding.require_analytics_admin(app_admin_claims)
    assert denied.value.status_code == 403
