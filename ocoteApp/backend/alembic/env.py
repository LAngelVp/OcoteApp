from sqlalchemy import create_engine, pool, text

from alembic import context
from app.core.config import DATABASE_NAME, MigrationSettings


def run_migrations() -> None:
    settings = MigrationSettings()
    if context.is_offline_mode():
        raise RuntimeError("Offline SQL is not supported; use a controlled online migration")
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
            identity = connection.execute(
                text(
                    "SELECT current_database(), rolsuper, rolcreatedb, rolcreaterole, "
                    "rolreplication, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                )
            ).one()
            if identity[0] != DATABASE_NAME or any(identity[1:]):
                raise RuntimeError("Migration requires the exact database and a nonprivileged role")
            connection.rollback()
            context.configure(
                connection=connection,
                target_metadata=None,
                version_table_schema="public",
                transaction_per_migration=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run_migrations()
