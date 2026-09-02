"""Definitive Ingevec relational schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260901_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")
    def ident(): return sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True)
    def name(): return sa.Column("name", sa.String(255), nullable=False)
    op.create_table("division_manager", ident(), name(), schema="app")
    op.create_table("project_manager", ident(), sa.Column("division_manager_id", sa.Integer(), sa.ForeignKey("app.division_manager.id"), nullable=False), name(), schema="app")
    op.create_table("project_admin", ident(), sa.Column("project_manager_id", sa.Integer(), sa.ForeignKey("app.project_manager.id"), nullable=False), name(), schema="app")
    for table in ("typology", "location", "supervisor", "classification", "item_type", "subcontractor"):
        op.create_table(table, ident(), name(), schema="app")
    op.create_table("project", sa.Column("id", sa.String(100), primary_key=True), sa.Column("public_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, unique=True), name(), sa.Column("typology_id", sa.Integer(), sa.ForeignKey("app.typology.id"), nullable=False), sa.Column("location_id", sa.Integer(), sa.ForeignKey("app.location.id"), nullable=False), sa.Column("municipal_reception_date", sa.Date()), sa.Column("supervisor_id", sa.Integer(), sa.ForeignKey("app.supervisor.id"), nullable=False), schema="app")
    op.create_table("postventa_item", ident(), sa.Column("public_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False, unique=True), sa.Column("project_id", sa.String(100), sa.ForeignKey("app.project.id"), nullable=False), sa.Column("classification_id", sa.Integer(), sa.ForeignKey("app.classification.id"), nullable=False), sa.Column("item_type_id", sa.Integer(), sa.ForeignKey("app.item_type.id"), nullable=False), sa.Column("notes", sa.Text(), nullable=False), sa.Column("request_date", sa.Date()), sa.Column("subcontractor_id", sa.Integer(), sa.ForeignKey("app.subcontractor.id")), sa.Column("handled_by", sa.String(255)), schema="app")

def downgrade() -> None:
    for table in ("postventa_item", "project", "subcontractor", "item_type", "classification", "supervisor", "location", "typology", "project_admin", "project_manager", "division_manager"):
        op.drop_table(table, schema="app")
    op.execute("DROP SCHEMA IF EXISTS analytics")
    op.execute("DROP SCHEMA IF EXISTS app")
