"""Allow direct reconciliation of an item without a source document."""

from alembic import op


revision = "20260921_0015"
down_revision = "20260919_0014"
branch_labels = None
depends_on = None


def _dashboard_view(include_reconciliation_state: bool) -> str:
    state_columns = """
            , EXISTS (SELECT 1 FROM app.postventa_item_failure_cause pifc
                    WHERE pifc.postventa_item_id = pi.id) AS esta_conciliado
            , EXISTS (SELECT 1 FROM app.document_postventa_item dpi2
                    WHERE dpi2.postventa_item_id = pi.id) AS tiene_documento""" if include_reconciliation_state else ""
    return f"""\
        CREATE VIEW analytics.postventa_item_dashboard AS
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
            {state_columns}
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
    """


def upgrade() -> None:
    _replace_source_check("assignment_source IN ('AUTOMATIC', 'MANUAL', 'DIRECT_MANUAL', 'MIGRATED')")
    # PostgreSQL permits adding columns at the end through CREATE OR REPLACE,
    # keeping Superset's existing column order and types stable.
    op.execute(_dashboard_view(True).replace("CREATE VIEW", "CREATE OR REPLACE VIEW", 1))
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
                GRANT SELECT ON analytics.postventa_item_dashboard TO superset_reader;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    # Removing view columns requires a drop/recreate. Refuse to silently lose
    # the provenance distinction if direct reconciliations have been recorded.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM app.postventa_item_failure_cause
                WHERE assignment_source = 'DIRECT_MANUAL'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while DIRECT_MANUAL reconciliations exist';
            END IF;
        END
        $$;
    """)
    _replace_source_check("assignment_source IN ('AUTOMATIC', 'MANUAL', 'MIGRATED')")
    op.execute("DROP VIEW analytics.postventa_item_dashboard")
    op.execute(_dashboard_view(False))


def _replace_source_check(condition: str) -> None:
    """Replace the check even where Alembic's naming convention renamed it."""
    op.execute("""
        DO $$
        DECLARE constraint_name text;
        BEGIN
            FOR constraint_name IN
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'app.postventa_item_failure_cause'::regclass
                  AND contype = 'c'
                  AND pg_get_constraintdef(oid) ILIKE '%assignment_source%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE app.postventa_item_failure_cause DROP CONSTRAINT %I',
                    constraint_name
                );
            END LOOP;
        END
        $$;
    """)
    op.execute(
        "ALTER TABLE app.postventa_item_failure_cause "
        "ADD CONSTRAINT ck_postventa_item_failure_cause_source "
        f"CHECK ({condition})"
    )
