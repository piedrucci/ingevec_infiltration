"""Add a filter-aware cause-level Pareto analytics view."""

from alembic import op


revision = "20261001_0020"
down_revision = "20260930_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE VIEW analytics.postventa_item_cause_pareto AS
        SELECT
            pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra,
            p.name AS proyecto,
            l.name AS ubicacion_proyecto,
            cl.name AS clasificacion,
            it.name AS tipo_item,
            pi.request_date AS fecha_solicitud,
            dm.id AS division_manager_id,
            dm.name AS gerente_divisional,
            pm.id AS project_manager_id,
            pm.name AS gerente_proyecto,
            fc.code AS codigo_causa_falla,
            fc.display_name_es AS causa_falla,
            fcc.code AS codigo_categoria_causa,
            fcc.display_name_es AS categoria_causa,
            fcg.code AS codigo_grupo_causa,
            fcg.display_name_es AS grupo_causa
        FROM app.postventa_item_failure_cause pifc
        JOIN app.postventa_item pi ON pi.id = pifc.postventa_item_id
        JOIN app.project p ON p.id = pi.project_id
        JOIN app.location l ON l.id = p.location_id
        JOIN app.classification cl ON cl.id = pi.classification_id
        JOIN app.item_type it ON it.id = pi.item_type_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.failure_cause fc ON fc.id = pifc.failure_cause_id
        LEFT JOIN app.failure_cause_category_link fccl
            ON fccl.failure_cause_id = fc.id
        LEFT JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
        LEFT JOIN app.failure_cause_category_group_link fccgl
            ON fccgl.category_id = fcc.id
        LEFT JOIN app.failure_cause_group fcg ON fcg.id = fccgl.group_id
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
                GRANT SELECT ON analytics.postventa_item_cause_pareto TO superset_reader;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_cause_pareto")
