"""Alembic binds only to the PostgreSQL configuration from AppSettings."""

import re
from pathlib import Path

from alembic import context
from sqlalchemy import Connection, text

from local_transcriber.infrastructure.database.models import Base
from local_transcriber.infrastructure.database.session import database_url, make_engine
from local_transcriber.infrastructure.settings import ConfigurationError, load_settings

config = context.config
settings = config.attributes.get("settings")
if settings is None:
    source = context.get_x_argument(as_dictionary=True).get("env_file")
    settings = load_settings(Path(source) if source else None)
test_mode = (
    bool(config.attributes.get("test_database", False))
    or context.get_x_argument(as_dictionary=True).get("test") == "true"
)
schema = config.attributes.get("test_schema")
if schema is not None and (not test_mode or not re.fullmatch(r"lt_test_[0-9a-f]{32}", schema)):
    raise ConfigurationError("Небезопасная тестовая схема.")
url = database_url(settings, test=test_mode)
target_metadata = Base.metadata


def migrate(connection: Connection) -> None:
    if test_mode:
        actual = connection.scalar(text("SELECT current_database()"))
        if actual != url.database:
            raise ConfigurationError("Подключение не соответствует отдельной test DB.")
    if schema:
        connection.execute(text('SET search_path TO "' + schema + '"'))
    if test_mode or schema:
        # Finish preflight autobegin so Alembic owns and commits its transaction.
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # search_path exposes our schema as default too; never diff Alembic's ledger.
        include_object=lambda obj, name, type_, reflected, compare_to: (
            type_ != "table" or name != "alembic_version"
        ),
        version_table_schema=schema,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=schema,
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    engine = make_engine(settings, test=test_mode)
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
