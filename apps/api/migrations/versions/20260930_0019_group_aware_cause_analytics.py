"""Expose failure-cause groups in the cause-level analytics view."""

from alembic import op


revision = "20260930_0019"
down_revision = "20260929_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(_cause_view_sql(include_groups=True, replace=True))
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
                GRANT USAGE ON SCHEMA analytics TO superset_reader;
                GRANT SELECT ON analytics.postventa_item_cause_dashboard TO superset_reader;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    # Recreate to remove the appended group fields while retaining the view
    # shape available at revision 0018.
    op.execute("DROP VIEW analytics.postventa_item_cause_dashboard")
    op.execute(_cause_view_sql(include_groups=False, replace=False))
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
                GRANT USAGE ON SCHEMA analytics TO superset_reader;
                GRANT SELECT ON analytics.postventa_item_cause_dashboard TO superset_reader;
            END IF;
        END
        $$;
    """)


def _cause_view_sql(*, include_groups: bool, replace: bool) -> str:
    create = "CREATE OR REPLACE VIEW" if replace else "CREATE VIEW"
    group_columns = ",\n            fcg.code AS codigo_grupo_causa,\n            fcg.display_name_es AS grupo_causa" if include_groups else ""
    group_joins = """
        LEFT JOIN app.failure_cause_category_group_link fccgl
            ON fccgl.category_id = fcc.id
        LEFT JOIN app.failure_cause_group fcg ON fcg.id = fccgl.group_id
    """ if include_groups else ""

    return f"""
        {create} analytics.postventa_item_cause_dashboard AS
        SELECT pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra, p.name AS proyecto,
            fc.code AS codigo_causa_falla, fc.display_name_es AS causa_falla,
            fcc.code AS codigo_categoria_causa, fcc.display_name_es AS categoria_causa,
            pifc.assignment_source AS origen_asignacion,
            pifc.assigned_at AS fecha_asignacion,
            dm.id AS division_manager_id, dm.name AS gerente_divisional,
            pm.id AS project_manager_id, pm.name AS gerente_proyecto{group_columns}
        FROM app.postventa_item_failure_cause pifc
        JOIN app.postventa_item pi ON pi.id = pifc.postventa_item_id
        JOIN app.project p ON p.id = pi.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.failure_cause fc ON fc.id = pifc.failure_cause_id
        LEFT JOIN app.failure_cause_category_link fccl ON fccl.failure_cause_id = fc.id
        LEFT JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
        {group_joins}
    """
