"""Add speciality and project associations for subcontractors."""

from alembic import op
import sqlalchemy as sa


revision = "20261006_0022"
down_revision = "20261005_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing subcontractor assignments came from the workbook and are being
    # remapped directly in the database under the new relationship model.
    op.drop_column("postventa_item", "subcontractor_id", schema="app")
    op.execute("TRUNCATE TABLE app.subcontractor RESTART IDENTITY")

    op.create_table(
        "speciality",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        schema="app",
    )
    op.add_column(
        "subcontractor",
        sa.Column("speciality_id", sa.Integer(), nullable=False),
        schema="app",
    )
    op.create_foreign_key(
        "fk_subcontractor_speciality_id_speciality",
        "subcontractor",
        "speciality",
        ["speciality_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
    )
    op.create_table(
        "project_subcontractor",
        sa.Column("project_id", sa.String(100), nullable=False),
        sa.Column("subcontractor_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["app.project.id"],
            name="fk_project_subcontractor_project_id_project",
            ondelete="CASCADE", onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subcontractor_id"], ["app.subcontractor.id"],
            name="fk_project_subcontractor_subcontractor_id_subcontractor",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "subcontractor_id"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("project_subcontractor", schema="app")
    op.drop_constraint(
        "fk_subcontractor_speciality_id_speciality", "subcontractor",
        schema="app", type_="foreignkey",
    )
    op.drop_column("subcontractor", "speciality_id", schema="app")
    op.drop_table("speciality", schema="app")
    op.add_column(
        "postventa_item",
        sa.Column("subcontractor_id", sa.Integer(), nullable=True),
        schema="app",
    )
    op.create_foreign_key(
        "fk_postventa_item_subcontractor_id_subcontractor",
        "postventa_item",
        "subcontractor",
        ["subcontractor_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
    )
