from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.auth import require_admin
from app.db import get_db
from app.main import app
from app.services import failure_cause_groups


class FakeSession:
    def __init__(self, scalar_result=None, scalars_result=()):
        self.scalar_result = scalar_result
        self.scalars_result = list(scalars_result)
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_result

    def scalars(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: self.scalars_result)


def compiled(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_list_groups_orders_alphabetically():
    session = FakeSession(scalars_result=["group"])

    assert failure_cause_groups.list_groups(session) == ["group"]
    assert "ORDER BY app.failure_cause_group.display_name_es, app.failure_cause_group.code" in compiled(session.statements[0])


def test_list_group_categories_filters_by_group_link():
    session = FakeSession(scalar_result=7, scalars_result=["category"])

    assert failure_cause_groups.list_group_categories(session, "DISENO") == ["category"]
    sql = compiled(session.statements[1])
    assert "JOIN app.failure_cause_category_group_link" in sql
    assert "app.failure_cause_category_group_link.group_id = %(group_id_1)s" in sql
    assert "ORDER BY app.failure_cause_category.display_name_es" in sql


def test_list_group_categories_rejects_unknown_group():
    with pytest.raises(LookupError):
        failure_cause_groups.list_group_categories(FakeSession(scalar_result=None), "OTRO")


@pytest.fixture
def client():
    app.dependency_overrides[require_admin] = lambda: {"realm_access": {"roles": ["admin"]}}
    app.dependency_overrides[get_db] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_group_endpoints_return_groups_and_categories(client, monkeypatch):
    monkeypatch.setattr("app.api.list_groups", lambda db: [SimpleNamespace(code="DISENO", display_name_es="Diseño")])
    monkeypatch.setattr("app.api.list_group_categories", lambda db, code: [
        SimpleNamespace(code="VENTANA", display_name_es="Ventana", is_active=True),
        SimpleNamespace(code="FACHADA", display_name_es="Fachada", is_active=False),
    ])

    groups = client.get("/v1/failure-cause-groups")
    assert groups.status_code == 200
    assert groups.json() == [{"code": "DISENO", "display_name_es": "Diseño"}]
    categories = client.get("/v1/failure-cause-groups/DISENO/categories")
    assert categories.status_code == 200
    assert categories.json() == [
        {"code": "VENTANA", "display_name_es": "Ventana", "is_active": True},
        {"code": "FACHADA", "display_name_es": "Fachada", "is_active": False},
    ]


def test_group_categories_returns_404_for_unknown_group(client, monkeypatch):
    def missing(db, code):
        raise LookupError(code)

    monkeypatch.setattr("app.api.list_group_categories", missing)
    response = client.get("/v1/failure-cause-groups/OTRO/categories")
    assert response.status_code == 404


def test_group_endpoints_require_authentication():
    assert TestClient(app).get("/v1/failure-cause-groups").status_code == 401
