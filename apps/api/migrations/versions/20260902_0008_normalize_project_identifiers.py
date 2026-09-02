"""Normalize numeric Excel project identifiers without a trailing decimal."""

from alembic import op


revision = "20260902_0008"
down_revision = "20260902_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_postventa_item_project_id_project",
        "postventa_item",
        schema="app",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_postventa_item_project_id_project",
        "postventa_item",
        "project",
        ["project_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
        onupdate="CASCADE",
    )
    op.execute(
        """
        UPDATE app.project
        SET id = regexp_replace(id, '\\.0+$', '')
        WHERE id ~ '^[0-9]+\\.0+$'
        """
    )


def downgrade() -> None:
    # The data cleanup is intentionally not reversed: a plain numeric identifier
    # may have originated as text, so restoring a decimal suffix would corrupt it.
    op.drop_constraint(
        "fk_postventa_item_project_id_project",
        "postventa_item",
        schema="app",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_postventa_item_project_id_project",
        "postventa_item",
        "project",
        ["project_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
    )
