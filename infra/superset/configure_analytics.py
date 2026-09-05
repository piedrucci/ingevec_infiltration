"""Provision Superset's read-only Neon connection and dashboard dataset."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from superset.app import create_app


READER_ROLE = "superset_reader"
DATABASE_NAME = "Ingevec Postventa Analytics"
ANALYTICS_SCHEMA = "analytics"
ANALYTICS_VIEW = "postventa_item_dashboard"


def reader_uri(owner_uri: str) -> str:
    owner = make_url(owner_uri)
    return str(owner.set(username=READER_ROLE, password=os.environ["SUPERSET_ANALYTICS_DB_PASSWORD"], drivername="postgresql+psycopg2"))


def provision_reader(owner_uri: str) -> None:
    url = make_url(owner_uri)
    database_name = url.database
    if not database_name:
        raise RuntimeError("DATABASE_URL must contain a database name")
    engine = create_engine(owner_uri)
    with engine.begin() as connection:
        exists = connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": READER_ROLE})
        if not exists:
            connection.execute(text(f"CREATE ROLE {READER_ROLE} LOGIN PASSWORD :password"), {"password": os.environ["SUPERSET_ANALYTICS_DB_PASSWORD"]})
        connection.execute(text(f"GRANT CONNECT ON DATABASE {database_name} TO {READER_ROLE}"))
        connection.execute(text(f"GRANT USAGE ON SCHEMA {ANALYTICS_SCHEMA} TO {READER_ROLE}"))
        connection.execute(text(f"GRANT SELECT ON {ANALYTICS_SCHEMA}.{ANALYTICS_VIEW} TO {READER_ROLE}"))


def register_superset_database(uri: str) -> None:
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database

        database = db.session.query(Database).filter_by(database_name=DATABASE_NAME).one_or_none()
        if database is None:
            database = Database(database_name=DATABASE_NAME)
        database.sqlalchemy_uri = uri
        database.expose_in_sqllab = True
        database.allow_ctas = False
        database.allow_cvas = False
        database.allow_dml = False
        database.allow_file_upload = False
        db.session.add(database)
        db.session.commit()

        dataset = db.session.query(SqlaTable).filter_by(
            database_id=database.id,
            schema=ANALYTICS_SCHEMA,
            table_name=ANALYTICS_VIEW,
        ).one_or_none()
        if dataset is None:
            dataset = SqlaTable(
                table_name=ANALYTICS_VIEW,
                schema=ANALYTICS_SCHEMA,
                database=database,
            )
            db.session.add(dataset)
            db.session.commit()
        dataset.fetch_metadata()
        db.session.commit()


if __name__ == "__main__":
    owner_uri = os.environ["DATABASE_URL"]
    provision_reader(owner_uri)
    register_superset_database(reader_uri(owner_uri))
    print(f"Configured {DATABASE_NAME}: {ANALYTICS_SCHEMA}.{ANALYTICS_VIEW}")
