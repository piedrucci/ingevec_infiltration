"""Add an explicit terminal status for documents without candidates."""

from alembic import op


revision = "20260904_0010"
down_revision = "20260902_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_document_status", "document", schema="app", type_="check")
    op.create_check_constraint(
        "ck_document_status",
        "document",
        "status IN ('UPLOADING', 'QUEUED', 'PROCESSING', 'MATCHED', 'PENDING_REVIEW', 'UNMATCHED', 'FAILED', 'QUARANTINED')",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint("ck_document_status", "document", schema="app", type_="check")
    op.create_check_constraint(
        "ck_document_status",
        "document",
        "status IN ('UPLOADING', 'QUEUED', 'PROCESSING', 'MATCHED', 'PENDING_REVIEW', 'FAILED', 'QUARANTINED')",
        schema="app",
    )
