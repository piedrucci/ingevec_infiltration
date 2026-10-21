"""Add the project-level analytics view (one row per project)."""

from alembic import op


revision = "20261020_0029"
down_revision = "20261020_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(_project_dashboard_sql())
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
                GRANT SELECT ON analytics.postventa_project_dashboard TO superset_reader;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW analytics.postventa_project_dashboard")


def _project_dashboard_sql() -> str:
    # Grain: one row per project, so project values (e.g. months to the first item) can be
    # averaged across projects without weighting by item count. Projects without items
    # list with 0 items and NULL dates. Months are full months (AGE, rounded down);
    # negative when the first item predates the municipal reception.
    return """
        CREATE VIEW analytics.postventa_project_dashboard AS
        SELECT
            p.id AS numero_obra,
            p.name AS proyecto,
            l.name AS ubicacion_proyecto,
            dm.id AS division_manager_id,
            dm.name AS gerente_divisional,
            pm.id AS project_manager_id,
            pm.name AS gerente_proyecto,
            p.municipal_reception_date AS fecha_recepcion_municipal,
            items.fecha_primera_incidencia,
            (EXTRACT(YEAR FROM AGE(items.fecha_primera_incidencia, p.municipal_reception_date)) * 12
                + EXTRACT(MONTH FROM AGE(items.fecha_primera_incidencia, p.municipal_reception_date)))::int
                AS meses_hasta_primera_incidencia,
            COALESCE(items.incidencias, 0) AS incidencias,
            COALESCE(items.conciliadas, 0) AS conciliadas,
            COALESCE(items.incidencias - items.conciliadas, 0) AS pendientes
        FROM app.project p
        JOIN app.location l ON l.id = p.location_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        LEFT JOIN LATERAL (
            SELECT
                min(pi.request_date) AS fecha_primera_incidencia,
                count(*)::int AS incidencias,
                count(*) FILTER (WHERE EXISTS (
                    SELECT 1 FROM app.postventa_item_failure_cause pifc
                    WHERE pifc.postventa_item_id = pi.id
                ))::int AS conciliadas
            FROM app.postventa_item pi
            WHERE pi.project_id = p.id
        ) items ON TRUE
    """
