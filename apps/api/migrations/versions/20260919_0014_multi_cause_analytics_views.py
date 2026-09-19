"""Expose aggregated and cause-level analytics for multi-cause items."""

from alembic import op


revision = "20260919_0014"
down_revision = "20260919_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW analytics.postventa_item_dashboard AS
        SELECT pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra, p.name AS proyecto,
            l.name AS ubicacion_proyecto, c.name AS clasificacion,
            it.name AS tipo_item, pi.notes AS observacion,
            pi.request_date AS fecha_solicitud,
            causes.codigo_causa_falla,
            causes.causa_falla,
            causes.codigo_categoria_causa,
            causes.categoria_causa,
            d.public_id AS documento_public_id,
            d.original_filename AS nombre_documento,
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
            causes.cantidad_causas
        FROM app.postventa_item pi
        JOIN app.project p ON p.id = pi.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.location l ON l.id = p.location_id
        JOIN app.classification c ON c.id = pi.classification_id
        JOIN app.item_type it ON it.id = pi.item_type_id
        LEFT JOIN LATERAL (
            SELECT
                min(fc.code)::varchar(100) AS codigo_causa_falla,
                min(fc.display_name_es)::varchar(255) AS causa_falla,
                min(fcc.code)::varchar(100) AS codigo_categoria_causa,
                min(fcc.display_name_es)::varchar(255) AS categoria_causa,
                string_agg(fc.code, ', ' ORDER BY fc.code)::text AS codigo_causas,
                string_agg(fc.display_name_es, ', ' ORDER BY fc.display_name_es)::text AS causas_falla,
                string_agg(DISTINCT fcc.code, ', ' ORDER BY fcc.code)::text AS codigo_categorias,
                string_agg(DISTINCT fcc.display_name_es, ', ' ORDER BY fcc.display_name_es)::text AS categorias_causa,
                count(*)::int AS cantidad_causas
            FROM app.postventa_item_failure_cause pifc
            JOIN app.failure_cause fc ON fc.id = pifc.failure_cause_id
            JOIN app.failure_cause_category fcc ON fcc.id = fc.category_id
            WHERE pifc.postventa_item_id = pi.id
        ) causes ON TRUE
        LEFT JOIN app.document_postventa_item dpi ON dpi.postventa_item_id = pi.id
        LEFT JOIN app.document d ON d.id = dpi.document_id
    """)
    op.execute("""
        CREATE OR REPLACE VIEW analytics.postventa_item_cause_dashboard AS
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
        JOIN app.failure_cause_category fcc ON fcc.id = fc.category_id
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
                GRANT USAGE ON SCHEMA analytics TO superset_reader;
                GRANT SELECT ON analytics.postventa_item_dashboard TO superset_reader;
                GRANT SELECT ON analytics.postventa_item_cause_dashboard TO superset_reader;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_cause_dashboard")
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_dashboard")
    op.execute("""
        CREATE VIEW analytics.postventa_item_dashboard AS
        SELECT pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra, p.name AS proyecto,
            l.name AS ubicacion_proyecto, c.name AS clasificacion,
            it.name AS tipo_item, pi.notes AS observacion,
            pi.request_date AS fecha_solicitud,
            fc.code AS codigo_causa_falla,
            fc.display_name_es AS causa_falla,
            fcc.code AS codigo_categoria_causa,
            fcc.display_name_es AS categoria_causa,
            d.public_id AS documento_public_id,
            d.original_filename AS nombre_documento,
            CASE d.status WHEN 'UPLOADING' THEN 'Cargando' WHEN 'QUEUED' THEN 'En cola'
                WHEN 'PROCESSING' THEN 'Procesando' WHEN 'MATCHED' THEN 'Vinculado'
                WHEN 'PENDING_REVIEW' THEN 'Revisión manual pendiente'
                WHEN 'UNMATCHED' THEN 'Sin asociación' WHEN 'FAILED' THEN 'Error de procesamiento'
                WHEN 'QUARANTINED' THEN 'En cuarentena' ELSE NULL END AS estado_documento,
            d.extracted_failure_cause AS causa_extraida_pdf,
            d.uploaded_at AS fecha_carga_documento,
            dm.id AS division_manager_id, dm.name AS gerente_divisional,
            pm.id AS project_manager_id, pm.name AS gerente_proyecto
        FROM app.postventa_item pi
        JOIN app.project p ON p.id = pi.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.location l ON l.id = p.location_id
        JOIN app.classification c ON c.id = pi.classification_id
        JOIN app.item_type it ON it.id = pi.item_type_id
        LEFT JOIN app.failure_cause fc ON fc.id = pi.failure_cause_id
        LEFT JOIN app.failure_cause_category fcc ON fcc.id = fc.category_id
        LEFT JOIN app.document_postventa_item dpi ON dpi.postventa_item_id = pi.id
        LEFT JOIN app.document d ON d.id = dpi.document_id
    """)
