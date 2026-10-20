"""Assign each failure cause to at most one group of its category."""

from alembic import op
import sqlalchemy as sa


revision = "20261019_0025"
down_revision = "20261008_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("failure_cause_category_link", sa.Column("group_id", sa.Integer(), nullable=True), schema="app")
    # The composite key guarantees that a cause's group contains its category.
    # NULL keeps the cause unassigned (MATCH SIMPLE skips the check).
    op.create_foreign_key(
        "fk_failure_cause_category_link_category_group",
        "failure_cause_category_link",
        "failure_cause_category_group_link",
        ["category_id", "group_id"],
        ["category_id", "group_id"],
        source_schema="app",
        referent_schema="app",
        ondelete="RESTRICT",
    )
    op.create_index("ix_failure_cause_category_link_group_id", "failure_cause_category_link", ["group_id"], schema="app")
    # Causes with a group report only that group; unassigned causes keep the
    # previous category-derived groups, so this is safe before the data operation.
    op.execute(_cause_dashboard_sql(group_aware=True))
    op.execute(_cause_pareto_sql(group_aware=True))


def downgrade() -> None:
    op.execute(_cause_dashboard_sql(group_aware=False))
    op.execute(_cause_pareto_sql(group_aware=False))
    op.drop_index("ix_failure_cause_category_link_group_id", "failure_cause_category_link", schema="app")
    op.drop_constraint("fk_failure_cause_category_link_category_group", "failure_cause_category_link", schema="app", type_="foreignkey")
    op.drop_column("failure_cause_category_link", "group_id", schema="app")


def _group_join(group_aware: bool) -> str:
    condition = " AND (fccl.group_id IS NULL OR fccgl.group_id = fccl.group_id)" if group_aware else ""
    return f"""
        LEFT JOIN app.failure_cause_category_group_link fccgl
            ON fccgl.category_id = fcc.id{condition}
        LEFT JOIN app.failure_cause_group fcg ON fcg.id = fccgl.group_id
    """


def _cause_dashboard_sql(*, group_aware: bool) -> str:
    return f"""
        CREATE OR REPLACE VIEW analytics.postventa_item_cause_dashboard AS
        SELECT pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra, p.name AS proyecto,
            fc.code AS codigo_causa_falla, fc.display_name_es AS causa_falla,
            fcc.code AS codigo_categoria_causa, fcc.display_name_es AS categoria_causa,
            pifc.assignment_source AS origen_asignacion,
            pifc.assigned_at AS fecha_asignacion,
            dm.id AS division_manager_id, dm.name AS gerente_divisional,
            pm.id AS project_manager_id, pm.name AS gerente_proyecto,
            fcg.code AS codigo_grupo_causa,
            fcg.display_name_es AS grupo_causa
        FROM app.postventa_item_failure_cause pifc
        JOIN app.postventa_item pi ON pi.id = pifc.postventa_item_id
        JOIN app.project p ON p.id = pi.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.failure_cause fc ON fc.id = pifc.failure_cause_id
        LEFT JOIN app.failure_cause_category_link fccl ON fccl.failure_cause_id = fc.id
        LEFT JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
        {_group_join(group_aware)}
    """


def _cause_pareto_sql(*, group_aware: bool) -> str:
    return f"""
        CREATE OR REPLACE VIEW analytics.postventa_item_cause_pareto AS
        SELECT
            pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra,
            p.name AS proyecto,
            l.name AS ubicacion_proyecto,
            cl.name AS clasificacion,
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
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.failure_cause fc ON fc.id = pifc.failure_cause_id
        LEFT JOIN app.failure_cause_category_link fccl ON fccl.failure_cause_id = fc.id
        LEFT JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
        {_group_join(group_aware)}
    """
