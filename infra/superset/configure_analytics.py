"""Provision Superset's read-only Neon connection and dashboard dataset."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from superset.app import create_app


READER_ROLE = "superset_reader"
DATABASE_NAME = "Ingevec Postventa Analytics"
ANALYTICS_SCHEMA = "analytics"
ANALYTICS_VIEWS = (
    "postventa_item_dashboard",
    "postventa_item_cause_dashboard",
    "postventa_item_cause_pareto",
)
VIEWER_ROLE = "Ingevec Viewer"
BUILDER_ROLE = "Ingevec Dashboard Builder"

# Superset's stock Gamma role includes chart/dashboard write and Explore
# permissions. Keep ordinary viewers read-only and grant authoring separately.
VIEWER_PERMISSIONS = {
    ("can_csv", "Superset"),
    ("can_read", "Chart"),
    ("can_read", "Dashboard"),
    ("can_read", "DashboardFilterStateRestApi"),
    ("can_read", "DashboardPermalinkRestApi"),
    ("can_read", "Database"),
    ("can_read", "Dataset"),
    ("can_read", "EmbeddedDashboard"),
    ("can_read", "Tag"),
    ("can_write", "DashboardFilterStateRestApi"),
    ("can_write", "DashboardPermalinkRestApi"),
}
BUILDER_PERMISSIONS = VIEWER_PERMISSIONS | {
    ("can_explore", "Superset"),
    ("can_read", "Explore"),
    ("can_read", "ExploreFormDataRestApi"),
    ("can_read", "ExplorePermalinkRestApi"),
    ("can_write", "Chart"),
    ("can_write", "Dashboard"),
    ("can_write", "ExploreFormDataRestApi"),
    ("can_write", "ExplorePermalinkRestApi"),
}

DATASET_METRICS = {
    "postventa_item_dashboard": {
        "items_distinct": (
            "Ítems",
            "COUNT(DISTINCT postventa_item_public_id)",
            "Distinct item count; safe if associated documents create multiple rows.",
        ),
        "items_reconciled_distinct": (
            "Ítems conciliados",
            "COUNT(DISTINCT CASE WHEN esta_conciliado THEN postventa_item_public_id END)",
            "Distinct items with at least one assigned failure cause.",
        ),
        "items_pending_distinct": (
            "Ítems pendientes",
            "COUNT(DISTINCT CASE WHEN NOT esta_conciliado THEN postventa_item_public_id END)",
            "Distinct items with no assigned failure cause.",
        ),
    },
    "postventa_item_cause_dashboard": {
        "items_with_cause_distinct": (
            "Ítems con causa",
            "COUNT(DISTINCT postventa_item_public_id)",
            "Distinct reconciled items represented in the cause-level dataset.",
        ),
        "item_cause_pairs_distinct": (
            "Asignaciones ítem–causa",
            "COUNT(DISTINCT (postventa_item_public_id, codigo_causa_falla))",
            "Distinct item/cause pairs, deduplicated across category and group memberships.",
        ),
    },
    "postventa_item_cause_pareto": {
        "items_per_cause": (
            "Ítems por causa",
            "COUNT(DISTINCT postventa_item_public_id)",
            "Distinct items assigned to each cause; category and group joins do not inflate the count.",
        ),
        "cumulative_share": (
            "Participación acumulada",
            "100.0 * SUM(COUNT(DISTINCT postventa_item_public_id)) OVER "
            "(ORDER BY COUNT(DISTINCT postventa_item_public_id) DESC "
            "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) / "
            "NULLIF(SUM(COUNT(DISTINCT postventa_item_public_id)) OVER (), 0)",
            "Cumulative share of distinct item/cause pairs after chart filters are applied.",
        ),
    },
}


def reader_uri(owner_uri: str) -> str:
    owner = make_url(owner_uri)
    return str(owner.set(username=READER_ROLE, password=os.environ["SUPERSET_ANALYTICS_DB_PASSWORD"], drivername="postgresql+psycopg2"))


def provision_reader(owner_uri: str) -> None:
    url = make_url(owner_uri)
    database_name = url.database
    if not database_name:
        raise RuntimeError("DATABASE_URL must contain a database name")
    engine = create_engine(owner_uri)
    with engine.begin() as connection:
        exists = connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": READER_ROLE})
        if not exists:
            connection.execute(text(f"CREATE ROLE {READER_ROLE} LOGIN PASSWORD :password"), {"password": os.environ["SUPERSET_ANALYTICS_DB_PASSWORD"]})
        connection.execute(text(f"GRANT CONNECT ON DATABASE {database_name} TO {READER_ROLE}"))
        connection.execute(text(f"GRANT USAGE ON SCHEMA {ANALYTICS_SCHEMA} TO {READER_ROLE}"))
        views = ", ".join(f"{ANALYTICS_SCHEMA}.{view}" for view in ANALYTICS_VIEWS)
        connection.execute(text(f"GRANT SELECT ON {views} TO {READER_ROLE}"))


def register_superset_database(uri: str) -> None:
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database

        database = db.session.query(Database).filter_by(database_name=DATABASE_NAME).one_or_none()
        if database is None:
            database = Database(database_name=DATABASE_NAME)
        database.sqlalchemy_uri = uri
        database.expose_in_sqllab = True
        database.allow_ctas = False
        database.allow_cvas = False
        database.allow_dml = False
        database.allow_file_upload = False
        db.session.add(database)
        db.session.commit()

        security_manager = app.appbuilder.sm
        viewer = security_manager.find_role(VIEWER_ROLE) or security_manager.add_role(VIEWER_ROLE)
        builder = security_manager.find_role(BUILDER_ROLE) or security_manager.add_role(BUILDER_ROLE)
        _replace_role_permissions(security_manager, viewer, VIEWER_PERMISSIONS)
        _replace_role_permissions(security_manager, builder, BUILDER_PERMISSIONS)

        for view_name in ANALYTICS_VIEWS:
            dataset = db.session.query(SqlaTable).filter_by(
                database_id=database.id,
                schema=ANALYTICS_SCHEMA,
                table_name=view_name,
            ).one_or_none()
            if dataset is None:
                dataset = SqlaTable(
                    table_name=view_name,
                    schema=ANALYTICS_SCHEMA,
                    database=database,
                )
                db.session.add(dataset)
                db.session.commit()
            dataset.fetch_metadata()
            db.session.commit()
            _configure_metrics(dataset, view_name)

            # Both custom roles are confined to curated datasets. Row scope is
            # enforced server-side by KeycloakSecurityManager for each view.
            for role in (viewer, builder):
                permission = security_manager.find_permission_view_menu("datasource_access", dataset.get_perm())
                if permission is None:
                    permission = security_manager.add_permission_view_menu("datasource_access", dataset.get_perm())
                security_manager.add_permission_role(role, permission)
                db.session.commit()


def _replace_role_permissions(security_manager, role, definitions: set[tuple[str, str]]) -> None:
    """Synchronize permissions for the app-managed viewer and builder roles."""
    for permission in list(role.permissions):
        security_manager.del_permission_role(role, permission)
    for action, view_menu in sorted(definitions):
        permission = security_manager.find_permission_view_menu(action, view_menu)
        if permission is None:
            permission = security_manager.add_permission_view_menu(action, view_menu)
        security_manager.add_permission_role(role, permission)


def _configure_metrics(dataset, view_name: str) -> None:
    from superset import db
    from superset.connectors.sqla.models import SqlMetric

    for metric_name, (verbose_name, expression, description) in DATASET_METRICS[view_name].items():
        metric = db.session.query(SqlMetric).filter_by(
            table_id=dataset.id,
            metric_name=metric_name,
        ).one_or_none()
        if metric is None:
            metric = SqlMetric(table_id=dataset.id, metric_name=metric_name)
        metric.verbose_name = verbose_name
        metric.expression = expression
        metric.description = description
        metric.metric_type = "expression" if metric_name == "cumulative_share" else "count"
        db.session.add(metric)
    db.session.commit()


if __name__ == "__main__":
    owner_uri = os.environ["DATABASE_URL"]
    provision_reader(owner_uri)
    register_superset_database(reader_uri(owner_uri))
    print(f"Configured {DATABASE_NAME}: " + ", ".join(f"{ANALYTICS_SCHEMA}.{view}" for view in ANALYTICS_VIEWS))
