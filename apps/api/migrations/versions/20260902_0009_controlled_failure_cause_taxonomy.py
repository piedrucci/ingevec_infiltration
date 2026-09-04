"""Introduce controlled failure-cause categories and aliases.

Raw text remains on ``document.extracted_failure_cause`` for traceability; it
must not become a reporting code or display value.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_0009"
down_revision = "20260902_0008"
branch_labels = None
depends_on = None


def _dashboard_view() -> str:
    return """
        CREATE OR REPLACE VIEW analytics.postventa_item_dashboard AS
        SELECT
            pi.public_id AS postventa_item_public_id,
            p.id AS numero_obra,
            p.name AS proyecto,
            l.name AS ubicacion_proyecto,
            c.name AS clasificacion,
            it.name AS tipo_item,
            pi.notes AS observacion,
            pi.request_date AS fecha_solicitud,
            fc.code AS codigo_causa_falla,
            fc.display_name_es AS causa_falla,
            fcc.code AS codigo_categoria_causa,
            fcc.display_name_es AS categoria_causa,
            d.public_id AS documento_public_id,
            d.original_filename AS nombre_documento,
            CASE d.status
                WHEN 'UPLOADING' THEN 'Cargando'
                WHEN 'QUEUED' THEN 'En cola'
                WHEN 'PROCESSING' THEN 'Procesando'
                WHEN 'MATCHED' THEN 'Vinculado'
                WHEN 'PENDING_REVIEW' THEN 'Revisión manual pendiente'
                WHEN 'FAILED' THEN 'Error de procesamiento'
                WHEN 'QUARANTINED' THEN 'En cuarentena'
                ELSE NULL
            END AS estado_documento,
            d.extracted_failure_cause AS causa_extraida_pdf,
            d.uploaded_at AS fecha_carga_documento
        FROM app.postventa_item pi
        JOIN app.project p ON p.id = pi.project_id
        JOIN app.location l ON l.id = p.location_id
        JOIN app.classification c ON c.id = pi.classification_id
        JOIN app.item_type it ON it.id = pi.item_type_id
        LEFT JOIN app.failure_cause fc ON fc.id = pi.failure_cause_id
        LEFT JOIN app.failure_cause_category fcc ON fcc.id = fc.category_id
        LEFT JOIN app.document_postventa_item dpi ON dpi.postventa_item_id = pi.id
        LEFT JOIN app.document d ON d.id = dpi.document_id
    """


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_dashboard")
    op.create_table(
        "failure_cause_category",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("display_name_es", sa.String(length=255), nullable=False),
        sa.Column("description_es", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("code", name="uq_failure_cause_category_code"),
        schema="app",
    )
    op.execute(
        """
        INSERT INTO app.failure_cause_category (code, display_name_es) VALUES
            ('WINDOWS_AND_SEALS', 'Ventanas y sellos'),
            ('WATERPROOFING', 'Impermeabilización'),
            ('DRAINAGE', 'Drenajes y evacuación de aguas'),
            ('INSTALLATION', 'Instalación y ejecución'),
            ('STRUCTURAL_DAMAGE', 'Daño estructural'),
            ('UNCLASSIFIED', 'Sin clasificar')
        """
    )
    op.add_column("failure_cause", sa.Column("category_id", sa.Integer(), nullable=True), schema="app")
    op.execute(
        """
        INSERT INTO app.failure_cause_category (code, display_name_es)
        SELECT DISTINCT category_code, category_name_es
        FROM app.failure_cause
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE app.failure_cause fc
        SET category_id = fcc.id
        FROM app.failure_cause_category fcc
        WHERE fcc.code = fc.category_code
        """
    )
    op.execute(
        """
        UPDATE app.failure_cause
        SET
            code = 'BROKEN_SEALS',
            display_name_es = 'Sellos cortados',
            category_id = (SELECT id FROM app.failure_cause_category WHERE code = 'WINDOWS_AND_SEALS')
        WHERE id = 1
        """
    )
    op.alter_column("failure_cause", "category_id", nullable=False, schema="app")
    op.create_foreign_key(
        "fk_failure_cause_category_id",
        "failure_cause",
        "failure_cause_category",
        ["category_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
        ondelete="RESTRICT",
    )
    op.create_index("ix_failure_cause_category_id", "failure_cause", ["category_id"], schema="app")
    op.drop_column("failure_cause", "category_name_es", schema="app")
    op.drop_column("failure_cause", "category_code", schema="app")

    op.create_table(
        "failure_cause_alias",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("failure_cause_id", sa.Integer(), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["failure_cause_id"], ["app.failure_cause.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("normalized_alias", name="uq_failure_cause_alias_normalized_alias"),
        schema="app",
    )
    op.create_index("ix_failure_cause_alias_failure_cause_id", "failure_cause_alias", ["failure_cause_id"], schema="app")
    op.execute(
        """
        INSERT INTO app.failure_cause_alias (failure_cause_id, normalized_alias)
        SELECT id, alias.normalized_alias
        FROM app.failure_cause
        CROSS JOIN (VALUES
            ('sellos cortados'),
            ('sellos rotos'),
            ('sellos danados')
        ) AS alias(normalized_alias)
        WHERE code = 'BROKEN_SEALS'
        """
    )
    op.execute(_dashboard_view())


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_dashboard")
    op.drop_index("ix_failure_cause_alias_failure_cause_id", table_name="failure_cause_alias", schema="app")
    op.drop_table("failure_cause_alias", schema="app")
    op.add_column("failure_cause", sa.Column("category_code", sa.String(length=100), nullable=True), schema="app")
    op.add_column("failure_cause", sa.Column("category_name_es", sa.String(length=255), nullable=True), schema="app")
    op.execute(
        """
        UPDATE app.failure_cause fc
        SET category_code = fcc.code, category_name_es = fcc.display_name_es
        FROM app.failure_cause_category fcc
        WHERE fcc.id = fc.category_id
        """
    )
    op.alter_column("failure_cause", "category_code", nullable=False, schema="app")
    op.alter_column("failure_cause", "category_name_es", nullable=False, schema="app")
    op.drop_index("ix_failure_cause_category_id", table_name="failure_cause", schema="app")
    op.drop_constraint("fk_failure_cause_category_id", "failure_cause", schema="app", type_="foreignkey")
    op.drop_column("failure_cause", "category_id", schema="app")
    op.drop_table("failure_cause_category", schema="app")
    op.execute(
        """
        CREATE OR REPLACE VIEW analytics.postventa_item_dashboard AS
        SELECT
            pi.public_id AS postventa_item_public_id, p.id AS numero_obra, p.name AS proyecto,
            l.name AS ubicacion_proyecto, c.name AS clasificacion, it.name AS tipo_item,
            pi.notes AS observacion, pi.request_date AS fecha_solicitud,
            fc.code AS codigo_causa_falla, fc.display_name_es AS causa_falla,
            fc.category_code AS codigo_categoria_causa, fc.category_name_es AS categoria_causa,
            d.public_id AS documento_public_id, d.original_filename AS nombre_documento,
            d.status AS estado_documento, d.extracted_failure_cause AS causa_extraida_pdf,
            d.uploaded_at AS fecha_carga_documento
        FROM app.postventa_item pi
        JOIN app.project p ON p.id = pi.project_id
        JOIN app.location l ON l.id = p.location_id
        JOIN app.classification c ON c.id = pi.classification_id
        JOIN app.item_type it ON it.id = pi.item_type_id
        LEFT JOIN app.failure_cause fc ON fc.id = pi.failure_cause_id
        LEFT JOIN app.document_postventa_item dpi ON dpi.postventa_item_id = pi.id
        LEFT JOIN app.document d ON d.id = dpi.document_id
        """
    )
