"""Enforce one category per cause after the reviewed shared-cause split."""
from alembic import op
import sqlalchemy as sa

revision = "20261008_0023"
down_revision = "20261006_0022"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE app.failure_cause_category_link IN SHARE ROW EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT 1 FROM app.failure_cause_category_link GROUP BY failure_cause_id HAVING count(*)>1 LIMIT 1")).first():
        raise RuntimeError("Shared causes still exist. Run app.commands.split_category_causes with the completed review before upgrading to 20261008_0023.")
    op.create_unique_constraint("uq_failure_cause_category_link_cause", "failure_cause_category_link", ["failure_cause_id"], schema="app")


def downgrade():
    # Schema rollback does not reverse reviewed item assignments or reactivate retired causes.
    op.drop_constraint("uq_failure_cause_category_link_cause", "failure_cause_category_link", schema="app", type_="unique")
