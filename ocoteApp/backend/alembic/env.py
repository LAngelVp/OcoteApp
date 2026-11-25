import re

from sqlalchemy import create_engine, pool, text

from alembic import context
from app.core.config import DATABASE_NAME, MigrationSettings


def migrate(connection, expected_database):
    if expected_database != DATABASE_NAME and not re.fullmatch(
        r"ocote_f2_(?:test|restore)_[0-9a-f]{32}", expected_database
    ):
        raise RuntimeError("Unapproved migration destination")
    identity = connection.execute(
        text(
            "SELECT current_database(), current_user, rolsuper, rolcreatedb, rolcreaterole, "
            "rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
    ).one()
    if identity[:2] != (expected_database, "ocote_migrador") or any(identity[2:]):
        raise RuntimeError("Unexpected database or migration role")
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=None,
        version_table_schema="public",
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Offline SQL is not supported; use a controlled online migration")
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        migrate(supplied, context.config.attributes.get("expected_database", ""))
        return
    settings = MigrationSettings()
    engine = create_engine(
        settings.migration_database_url.get_secret_value(),
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "application_name": "ocote-migrador",
            "options": "-c timezone=UTC -c lock_timeout=5000 -c statement_timeout=60000",
        },
    )
    try:
        with engine.connect() as connection:
            migrate(connection, DATABASE_NAME)
    finally:
        engine.dispose()


run_migrations()
