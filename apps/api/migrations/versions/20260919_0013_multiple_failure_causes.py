"""Allow each postventa item to have multiple controlled failure causes."""

from alembic import op
import sqlalchemy as sa


revision = "20260919_0013"
down_revision = "20260907_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "postventa_item_failure_cause",
        sa.Column("postventa_item_id", sa.Integer(), nullable=False),
        sa.Column("failure_cause_id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("assignment_source", sa.String(length=16), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_by", sa.String(length=255), nullable=True),
        sa.CheckConstraint("assignment_source IN ('AUTOMATIC', 'MANUAL', 'MIGRATED')", name="ck_postventa_item_failure_cause_source"),
        sa.ForeignKeyConstraint(["postventa_item_id"], ["app.postventa_item.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["failure_cause_id"], ["app.failure_cause.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_document_id"], ["app.document.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("postventa_item_id", "failure_cause_id"),
        schema="app",
    )
    op.create_index(
        "ix_postventa_item_failure_cause_failure_cause_id",
        "postventa_item_failure_cause",
        ["failure_cause_id"],
        schema="app",
    )
    op.execute("""
        INSERT INTO app.postventa_item_failure_cause
            (postventa_item_id, failure_cause_id, assignment_source)
        SELECT id, failure_cause_id, 'MIGRATED'
        FROM app.postventa_item
        WHERE failure_cause_id IS NOT NULL
        ON CONFLICT (postventa_item_id, failure_cause_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_postventa_item_failure_cause_failure_cause_id", table_name="postventa_item_failure_cause", schema="app")
    op.drop_table("postventa_item_failure_cause", schema="app")
