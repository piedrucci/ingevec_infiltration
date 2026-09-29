"""Make failure causes belong to many categories."""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0016"
down_revision = "20260921_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The analytics view depends on the old category_id column.
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_cause_dashboard")
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_dashboard")
    op.create_table(
        "failure_cause_category_link",
        sa.Column("failure_cause_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["failure_cause_id"], ["app.failure_cause.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["app.failure_cause_category.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("failure_cause_id", "category_id"),
        schema="app",
    )
    op.execute("""
        INSERT INTO app.failure_cause_category_link (failure_cause_id, category_id)
        SELECT id, category_id FROM app.failure_cause
        ON CONFLICT DO NOTHING
    """)
    op.drop_index("ix_failure_cause_category_id", table_name="failure_cause", schema="app")
    op.drop_constraint("fk_failure_cause_category_id", "failure_cause", schema="app", type_="foreignkey")
    op.drop_column("failure_cause", "category_id", schema="app")
    _create_dashboard_view()
    _create_cause_view()


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_cause_dashboard")
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_dashboard")
    op.add_column("failure_cause", sa.Column("category_id", sa.Integer(), nullable=True), schema="app")
    op.execute("""
        UPDATE app.failure_cause fc
        SET category_id = links.category_id
        FROM (
            SELECT failure_cause_id, min(category_id) AS category_id
            FROM app.failure_cause_category_link
            GROUP BY failure_cause_id
        ) links
        WHERE links.failure_cause_id = fc.id
    """)
    op.alter_column("failure_cause", "category_id", nullable=False, schema="app")
    op.create_foreign_key("fk_failure_cause_category_id", "failure_cause", "failure_cause_category", ["category_id"], ["id"], source_schema="app", referent_schema="app", ondelete="RESTRICT")
    op.create_index("ix_failure_cause_category_id", "failure_cause", ["category_id"], schema="app")
    op.drop_table("failure_cause_category_link", schema="app")


def _create_dashboard_view() -> None:
    op.execute("""
        CREATE VIEW analytics.postventa_item_dashboard AS
        SELECT pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra, p.name AS proyecto,
            l.name AS ubicacion_proyecto, c.name AS clasificacion,
            it.name AS tipo_item, pi.notes AS observacion,
            pi.request_date AS fecha_solicitud,
            causes.codigo_causa_falla, causes.causa_falla,
            causes.codigo_categoria_causa, causes.categoria_causa,
            d.public_id AS documento_public_id, d.original_filename AS nombre_documento,
            CASE d.status WHEN 'UPLOADING' THEN 'Cargando' WHEN 'QUEUED' THEN 'En cola'
                WHEN 'PROCESSING' THEN 'Procesando' WHEN 'MATCHED' THEN 'Vinculado'
                WHEN 'PENDING_REVIEW' THEN 'Revisión manual pendiente'
                WHEN 'UNMATCHED' THEN 'Sin asociación' WHEN 'FAILED' THEN 'Error de procesamiento'
                WHEN 'QUARANTINED' THEN 'En cuarentena' ELSE NULL END AS estado_documento,
            d.extracted_failure_cause AS causa_extraida_pdf,
            d.uploaded_at AS fecha_carga_documento,
            dm.id AS division_manager_id, dm.name AS gerente_divisional,
            pm.id AS project_manager_id, pm.name AS gerente_proyecto,
            causes.codigo_causas, causes.causas_falla,
            causes.codigo_categorias, causes.categorias_causa,
            causes.cantidad_causas,
            EXISTS (SELECT 1 FROM app.postventa_item_failure_cause pifc
                    WHERE pifc.postventa_item_id = pi.id) AS esta_conciliado,
            EXISTS (SELECT 1 FROM app.document_postventa_item dpi2
                    WHERE dpi2.postventa_item_id = pi.id) AS tiene_documento
        FROM app.postventa_item pi
        JOIN app.project p ON p.id = pi.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.location l ON l.id = p.location_id
        JOIN app.classification c ON c.id = pi.classification_id
        JOIN app.item_type it ON it.id = pi.item_type_id
        LEFT JOIN LATERAL (
            SELECT min(fc.code)::varchar(100) AS codigo_causa_falla,
                min(fc.display_name_es)::varchar(255) AS causa_falla,
                min(fcc.code)::varchar(100) AS codigo_categoria_causa,
                min(fcc.display_name_es)::varchar(255) AS categoria_causa,
                string_agg(fc.code, ', ' ORDER BY fc.code)::text AS codigo_causas,
                string_agg(fc.display_name_es, ', ' ORDER BY fc.display_name_es)::text AS causas_falla,
                string_agg(DISTINCT fcc.code, ', ' ORDER BY fcc.code)::text AS codigo_categorias,
                string_agg(DISTINCT fcc.display_name_es, ', ' ORDER BY fcc.display_name_es)::text AS categorias_causa,
                count(DISTINCT fc.id)::int AS cantidad_causas
            FROM app.postventa_item_failure_cause pifc
            JOIN app.failure_cause fc ON fc.id = pifc.failure_cause_id
            LEFT JOIN app.failure_cause_category_link fccl ON fccl.failure_cause_id = fc.id
            LEFT JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
            WHERE pifc.postventa_item_id = pi.id
        ) causes ON TRUE
        LEFT JOIN app.document_postventa_item dpi ON dpi.postventa_item_id = pi.id
        LEFT JOIN app.document d ON d.id = dpi.document_id
    """)


def _create_cause_view() -> None:
    op.execute("""
        CREATE VIEW analytics.postventa_item_cause_dashboard AS
        SELECT pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra, p.name AS proyecto,
            fc.code AS codigo_causa_falla, fc.display_name_es AS causa_falla,
            fcc.code AS codigo_categoria_causa, fcc.display_name_es AS categoria_causa,
            pifc.assignment_source AS origen_asignacion,
            pifc.assigned_at AS fecha_asignacion,
            dm.id AS division_manager_id, dm.name AS gerente_divisional,
            pm.id AS project_manager_id, pm.name AS gerente_proyecto
        FROM app.postventa_item_failure_cause pifc
        JOIN app.postventa_item pi ON pi.id = pifc.postventa_item_id
        JOIN app.project p ON p.id = pi.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.failure_cause fc ON fc.id = pifc.failure_cause_id
        LEFT JOIN app.failure_cause_category_link fccl ON fccl.failure_cause_id = fc.id
        LEFT JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
    """)
