"""Relate one project admin to many projects."""
from alembic import op
import sqlalchemy as sa

revision = "20260901_0004"
down_revision = "20260901_0003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("project", sa.Column("project_admin_id", sa.Integer(), nullable=True), schema="app")
    op.create_foreign_key("fk_project_project_admin_id", "project", "project_admin", ["project_admin_id"], ["id"], source_schema="app", referent_schema="app")

def downgrade() -> None:
    op.drop_constraint("fk_project_project_admin_id", "project", schema="app", type_="foreignkey")
    op.drop_column("project", "project_admin_id", schema="app")
