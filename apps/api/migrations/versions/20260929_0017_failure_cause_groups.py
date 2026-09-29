"""Add fixed failure-cause groups and category associations."""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0017"
down_revision = "20260929_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failure_cause_group",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("display_name_es", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("code", name="uq_failure_cause_group_code"),
        sa.CheckConstraint(
            "code IN ('EJECUCION', 'PROPIETARIO', 'DISENO')",
            name="ck_failure_cause_group_code",
        ),
        schema="app",
    )
    op.create_table(
        "failure_cause_category_group_link",
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["app.failure_cause_category.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["app.failure_cause_group.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("category_id", "group_id"),
        schema="app",
    )
    op.execute(
        """
        INSERT INTO app.failure_cause_group (code, display_name_es)
        VALUES
            ('EJECUCION', 'Ejecución'),
            ('PROPIETARIO', 'Propietario'),
            ('DISENO', 'Diseño')
        """
    )


def downgrade() -> None:
    op.drop_table("failure_cause_category_group_link", schema="app")
    op.drop_table("failure_cause_group", schema="app")
