"""Add normalized failure causes and Spanish analytics view."""

from alembic import op
import sqlalchemy as sa


revision = "20260902_0006"
down_revision = "20260902_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failure_cause",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("display_name_es", sa.String(length=255), nullable=False),
        sa.Column("category_code", sa.String(length=100), nullable=False),
        sa.Column("category_name_es", sa.String(length=255), nullable=False),
        sa.Column("description_es", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("code", name="uq_failure_cause_code"),
        schema="app",
    )
    op.add_column("postventa_item", sa.Column("failure_cause_id", sa.Integer(), nullable=True), schema="app")
    op.create_foreign_key(
        "fk_postventa_item_failure_cause_id",
        "postventa_item",
        "failure_cause",
        ["failure_cause_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
        ondelete="RESTRICT",
    )
    op.create_index("ix_postventa_item_failure_cause_id", "postventa_item", ["failure_cause_id"], schema="app")

    op.add_column("document", sa.Column("extracted_failure_cause", sa.Text(), nullable=True), schema="app")
    op.drop_index(
        "ix_document_postventa_item_postventa_item_id",
        table_name="document_postventa_item",
        schema="app",
    )
    op.create_unique_constraint(
        "uq_document_postventa_item_postventa_item_id",
        "document_postventa_item",
        ["postventa_item_id"],
        schema="app",
    )

    op.execute(
        """
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
            fc.category_code AS codigo_categoria_causa,
            fc.category_name_es AS categoria_causa,
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
        LEFT JOIN app.document_postventa_item dpi ON dpi.postventa_item_id = pi.id
        LEFT JOIN app.document d ON d.id = dpi.document_id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.postventa_item_dashboard")
    op.drop_constraint(
        "uq_document_postventa_item_postventa_item_id",
        "document_postventa_item",
        schema="app",
        type_="unique",
    )
    op.create_index(
        "ix_document_postventa_item_postventa_item_id",
        "document_postventa_item",
        ["postventa_item_id"],
        schema="app",
    )
    op.drop_column("document", "extracted_failure_cause", schema="app")
    op.drop_index("ix_postventa_item_failure_cause_id", table_name="postventa_item", schema="app")
    op.drop_constraint(
        "fk_postventa_item_failure_cause_id",
        "postventa_item",
        schema="app",
        type_="foreignkey",
    )
    op.drop_column("postventa_item", "failure_cause_id", schema="app")
    op.drop_table("failure_cause", schema="app")
