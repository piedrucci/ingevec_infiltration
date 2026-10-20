"""Link failure-cause categories to specialities and add the subcontractor analytics view."""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0028"
down_revision = "20261020_0027"
branch_labels = None
depends_on = None

# Category code -> speciality name. Specialities match ignoring case, outer
# whitespace and accents (production spells "Impermeabilizacion").
CATEGORY_SPECIALITIES = {
    "WINDOWS": "Ventana",
    "FACADE": "Fachada",
    "SHEET_METAL": "Hojalateria",
    "WATERPROOFING": "Impermeabilizacion",
    "INSTALLATIONS": "Sanitario",
}
NORMALIZED = "translate(lower(btrim({})), 'áéíóúüñ', 'aeiouun')"


def upgrade() -> None:
    op.add_column("failure_cause_category", sa.Column("speciality_id", sa.Integer(), nullable=True), schema="app")
    op.create_foreign_key(
        "fk_failure_cause_category_speciality_id_speciality",
        "failure_cause_category",
        "speciality",
        ["speciality_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
        ondelete="RESTRICT",
    )
    op.create_index("ix_failure_cause_category_speciality_id", "failure_cause_category", ["speciality_id"], schema="app")

    mapping = ", ".join(f"('{code}', '{speciality}')" for code, speciality in CATEGORY_SPECIALITIES.items())
    # Abort instead of linking partially when a category or speciality is missing.
    op.execute(f"""
        DO $$
        DECLARE missing text;
        BEGIN
            SELECT string_agg(m.code || ' -> ' || m.speciality, ', ') INTO missing
            FROM (VALUES {mapping}) AS m(code, speciality)
            WHERE NOT EXISTS (SELECT 1 FROM app.failure_cause_category c WHERE c.code = m.code)
               OR NOT EXISTS (SELECT 1 FROM app.speciality s WHERE {NORMALIZED.format('s.name')} = {NORMALIZED.format('m.speciality')});
            IF missing IS NOT NULL THEN
                RAISE EXCEPTION 'Missing category or speciality for: %', missing;
            END IF;
        END
        $$;
    """)
    op.execute(f"""
        UPDATE app.failure_cause_category c
        SET speciality_id = s.id
        FROM (VALUES {mapping}) AS m(code, speciality)
        JOIN app.speciality s ON {NORMALIZED.format('s.name')} = {NORMALIZED.format('m.speciality')}
        WHERE c.code = m.code
    """)
    op.execute(_subcontractor_dashboard_sql())
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_reader') THEN
                GRANT SELECT ON analytics.postventa_item_subcontractor_dashboard TO superset_reader;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW analytics.postventa_item_subcontractor_dashboard")
    op.drop_index("ix_failure_cause_category_speciality_id", "failure_cause_category", schema="app")
    op.drop_constraint("fk_failure_cause_category_speciality_id_speciality", "failure_cause_category", schema="app", type_="foreignkey")
    op.drop_column("failure_cause_category", "speciality_id", schema="app")


def _subcontractor_dashboard_sql() -> str:
    # Grain: one row per item-cause and credited subcontractor (the item's project
    # subcontractor whose speciality matches the cause's category), plus one row per
    # project assignment without such item-causes so it lists with 0 items.
    # Item-causes without a speciality or a matching subcontractor keep NULL
    # subcontractor columns. Count items with COUNT(DISTINCT postventa_item_public_id).
    return """
        CREATE VIEW analytics.postventa_item_subcontractor_dashboard AS
        SELECT
            pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra,
            p.name AS proyecto,
            dm.id AS division_manager_id,
            dm.name AS gerente_divisional,
            pm.id AS project_manager_id,
            pm.name AS gerente_proyecto,
            pi.request_date AS fecha_solicitud,
            fcg.code AS codigo_grupo_causa,
            fcg.display_name_es AS grupo_causa,
            fcc.code AS codigo_categoria_causa,
            fcc.display_name_es AS categoria_causa,
            fc.code AS codigo_causa_falla,
            fc.display_name_es AS causa_falla,
            sp.id AS especialidad_id,
            sp.name AS especialidad,
            sc.id AS subcontratista_id,
            sc.name AS subcontratista
        FROM app.postventa_item_failure_cause pifc
        JOIN app.postventa_item pi ON pi.id = pifc.postventa_item_id
        JOIN app.project p ON p.id = pi.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        JOIN app.failure_cause fc ON fc.id = pifc.failure_cause_id
        LEFT JOIN app.failure_cause_category_link fccl ON fccl.failure_cause_id = fc.id
        LEFT JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
        LEFT JOIN app.failure_cause_group fcg ON fcg.id = fccl.group_id
        LEFT JOIN app.speciality sp ON sp.id = fcc.speciality_id
        LEFT JOIN (
            app.project_subcontractor ps
            JOIN app.subcontractor sc ON sc.id = ps.subcontractor_id
        ) ON ps.project_id = p.id AND sc.speciality_id = fcc.speciality_id
        UNION ALL
        SELECT
            NULL::uuid,
            p.id,
            p.name,
            dm.id,
            dm.name,
            pm.id,
            pm.name,
            NULL::date,
            NULL, NULL, NULL, NULL, NULL, NULL,
            sp.id,
            sp.name,
            sc.id,
            sc.name
        FROM app.project_subcontractor ps
        JOIN app.subcontractor sc ON sc.id = ps.subcontractor_id
        JOIN app.speciality sp ON sp.id = sc.speciality_id
        JOIN app.project p ON p.id = ps.project_id
        LEFT JOIN app.project_admin pa ON pa.id = p.project_admin_id
        LEFT JOIN app.project_manager pm ON pm.id = pa.project_manager_id
        LEFT JOIN app.division_manager dm ON dm.id = pm.division_manager_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM app.postventa_item pi
            JOIN app.postventa_item_failure_cause pifc ON pifc.postventa_item_id = pi.id
            JOIN app.failure_cause_category_link fccl ON fccl.failure_cause_id = pifc.failure_cause_id
            JOIN app.failure_cause_category fcc ON fcc.id = fccl.category_id
            WHERE pi.project_id = ps.project_id AND fcc.speciality_id = sc.speciality_id
        )
    """
