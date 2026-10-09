from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import Base, database_url
import app.models  # noqa: F401 - registers model metadata

config = context.config
def migration_database_url() -> str:
    return os.environ.get("MIGRATION_DATABASE_URL") or database_url()


config.set_main_option("sqlalchemy.url", migration_database_url())
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
# Existing deployments keep migration history in public, even when the
# application connection's search_path contains only app.
version_table_schema = "public"


def run_migrations_offline() -> None:
    context.configure(url=migration_database_url(), target_metadata=target_metadata, version_table_schema=version_table_schema, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        context.configure(
            connection=supplied_connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=version_table_schema,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_schemas=True, version_table_schema=version_table_schema)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
