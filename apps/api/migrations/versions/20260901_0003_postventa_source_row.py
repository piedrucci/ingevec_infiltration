"""Link each postventa item to one Excel source row."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260901_0003"
down_revision = "20260901_0002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("postventa_item", sa.Column("source_row_id", postgresql.UUID(as_uuid=True), nullable=True), schema="app")
    op.create_foreign_key("fk_postventa_item_source_row_id", "postventa_item", "excel_source_row", ["source_row_id"], ["id"], source_schema="app", referent_schema="app", ondelete="CASCADE")
    op.create_unique_constraint("uq_postventa_item_source_row_id", "postventa_item", ["source_row_id"], schema="app")

def downgrade() -> None:
    op.drop_constraint("uq_postventa_item_source_row_id", "postventa_item", schema="app", type_="unique")
    op.drop_constraint("fk_postventa_item_source_row_id", "postventa_item", schema="app", type_="foreignkey")
    op.drop_column("postventa_item", "source_row_id", schema="app")
