"""Add Excel import and source-row staging tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260901_0002"
down_revision = "20260901_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "excel_import",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'RECEIVED'")),
        sa.Column("source_sheet", sa.String(128), nullable=False, server_default=sa.text("'Año 2026'")),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="app",
    )
    op.create_table(
        "excel_source_row",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("excel_import_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.excel_import.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sheet_name", sa.String(128), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_cells", postgresql.JSONB(), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("normalization_status", sa.String(32), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("normalization_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("excel_import_id", "sheet_name", "row_number", name="uq_excel_source_row_position"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("excel_source_row", schema="app")
    op.drop_table("excel_import", schema="app")
