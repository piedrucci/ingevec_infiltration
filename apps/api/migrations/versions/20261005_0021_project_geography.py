"""Add project coordinates and geographic zones to locations."""

from alembic import op
import sqlalchemy as sa


revision = "20261005_0021"
down_revision = "20261001_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project", sa.Column("address", sa.Text(), nullable=True), schema="app")
    op.add_column("project", sa.Column("latitude", sa.Numeric(10, 7), nullable=True), schema="app")
    op.add_column("project", sa.Column("longitude", sa.Numeric(10, 7), nullable=True), schema="app")
    op.add_column("location", sa.Column("geographic_zone", sa.String(255), nullable=True), schema="app")


def downgrade() -> None:
    op.drop_column("location", "geographic_zone", schema="app")
    op.drop_column("project", "longitude", schema="app")
    op.drop_column("project", "latitude", schema="app")
    op.drop_column("project", "address", schema="app")
