"""Add indexes for substring search and common project-manager filters.

Revision ID: 20260929_0018
Revises: 20260929_0017
"""

from alembic import op


revision = "20260929_0018"
down_revision = "20260929_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm enables GIN indexes to accelerate ILIKE '%term%' searches.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_index(
        "ix_postventa_item_project_id",
        "postventa_item",
        ["project_id"],
        schema="app",
    )
    op.create_index(
        "ix_project_project_admin_id",
        "project",
        ["project_admin_id"],
        schema="app",
    )
    op.create_index(
        "ix_project_admin_project_manager_id",
        "project_admin",
        ["project_manager_id"],
        schema="app",
    )
    op.create_index(
        "ix_project_manager_division_manager_id",
        "project_manager",
        ["division_manager_id"],
        schema="app",
    )

    op.create_index(
        "ix_postventa_item_notes_trgm",
        "postventa_item",
        ["notes"],
        schema="app",
        postgresql_using="gin",
        postgresql_ops={"notes": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_project_name_trgm",
        "project",
        ["name"],
        schema="app",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_project_id_trgm",
        "project",
        ["id"],
        schema="app",
        postgresql_using="gin",
        postgresql_ops={"id": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_project_id_trgm", table_name="project", schema="app")
    op.drop_index("ix_project_name_trgm", table_name="project", schema="app")
    op.drop_index("ix_postventa_item_notes_trgm", table_name="postventa_item", schema="app")
    op.drop_index("ix_project_manager_division_manager_id", table_name="project_manager", schema="app")
    op.drop_index("ix_project_admin_project_manager_id", table_name="project_admin", schema="app")
    op.drop_index("ix_project_project_admin_id", table_name="project", schema="app")
    op.drop_index("ix_postventa_item_project_id", table_name="postventa_item", schema="app")
