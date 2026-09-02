"""Add transactional outbox records for PDF discovery events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260902_0007"
down_revision = "20260902_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_outbox_event",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["app.document.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "subject", name="uq_document_outbox_event_document_subject"),
        schema="app",
    )
    op.create_index(
        "ix_document_outbox_event_pending",
        "document_outbox_event",
        ["published_at", "created_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index("ix_document_outbox_event_pending", table_name="document_outbox_event", schema="app")
    op.drop_table("document_outbox_event", schema="app")
