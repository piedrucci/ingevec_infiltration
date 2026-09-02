"""Add document-processing records and postventa associations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260902_0005"
down_revision = "20260901_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'UPLOADING'"), nullable=False),
        sa.Column("matching_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB(), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("file_size_bytes > 0 AND file_size_bytes <= 5242880", name="ck_document_file_size_bytes"),
        sa.CheckConstraint("status IN ('UPLOADING', 'QUEUED', 'PROCESSING', 'MATCHED', 'PENDING_REVIEW', 'FAILED', 'QUARANTINED')", name="ck_document_status"),
        sa.CheckConstraint("matching_confidence IS NULL OR matching_confidence BETWEEN 0 AND 1", name="ck_document_matching_confidence"),
        sa.UniqueConstraint("public_id", name="uq_document_public_id"),
        sa.UniqueConstraint("content_hash", name="uq_document_content_hash"),
        sa.UniqueConstraint("object_key", name="uq_document_object_key"),
        schema="app",
    )
    op.create_index("ix_document_status_uploaded_at", "document", ["status", "uploaded_at"], schema="app")

    op.create_table(
        "document_postventa_item",
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("app.document.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("postventa_item_id", sa.Integer(), sa.ForeignKey("app.postventa_item.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("association_source", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("associated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("association_source IN ('AUTOMATIC', 'MANUAL')", name="ck_document_postventa_item_association_source"),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_document_postventa_item_confidence"),
        schema="app",
    )
    op.create_index(
        "ix_document_postventa_item_postventa_item_id",
        "document_postventa_item",
        ["postventa_item_id"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index("ix_document_postventa_item_postventa_item_id", table_name="document_postventa_item", schema="app")
    op.drop_table("document_postventa_item", schema="app")
    op.drop_index("ix_document_status_uploaded_at", table_name="document", schema="app")
    op.drop_table("document", schema="app")
