"""Expose project coordinates and address in the item analytics view for maps."""

from alembic import op


revision = "20261020_0026"
down_revision = "20261019_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Appending columns keeps the existing columns, dataset metrics, charts and grants intact.
    op.execute(_postventa_item_dashboard_sql(create="CREATE OR REPLACE VIEW", map_columns=True))


def downgrade() -> None:
    # PostgreSQL cannot remove view columns with CREATE OR REPLACE VIEW.
    op.execute("DROP VIEW analytics.postventa_item_dashboard")
    op.execute(_postventa_item_dashboard_sql(create="CREATE VIEW", map_columns=False))
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
                GRANT SELECT ON analytics.postventa_item_dashboard TO superset_reader;
            END IF;
        END
        $$;
    """)


def _postventa_item_dashboard_sql(*, create: str, map_columns: bool) -> str:
    map_select = """,
            p.latitude::double precision AS latitud,
            p.longitude::double precision AS longitud,
            p.address AS direccion""" if map_columns else ""
    return f"""
        {create} analytics.postventa_item_dashboard AS
        SELECT pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra, p.name AS proyecto,
            l.name AS ubicacion_proyecto, c.name AS clasificacion,
            pi.notes AS observacion, pi.request_date AS fecha_solicitud,
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
                    WHERE dpi2.postventa_item_id = pi.id) AS tiene_documento{map_select}
        FROM app.postventa_item pi
        JOIN app.project p ON p.id = pi.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.location l ON l.id = p.location_id
        JOIN app.classification c ON c.id = pi.classification_id
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
    """
