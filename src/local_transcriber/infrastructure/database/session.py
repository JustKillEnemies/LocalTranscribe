"""PostgreSQL configuration derived exclusively from AppSettings."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import unquote

from pydantic import PostgresDsn, TypeAdapter, ValidationError
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from local_transcriber.infrastructure.settings import AppSettings, ConfigurationError


class PersistenceError(RuntimeError):
    """Safe public database error; driver detail and SQL parameters stay private."""


def database_url(settings: AppSettings, *, test: bool = False) -> URL:
    """Build an escaped psycopg URL, refusing unsafe test targets."""
    host, port = settings.postgres_host, settings.postgres_port
    username, password = settings.postgres_user, settings.postgres_password.get_secret_value()
    database = settings.postgres_db
    if settings.postgres_dsn:
        try:
            dsn = TypeAdapter(PostgresDsn).validate_python(settings.postgres_dsn.get_secret_value())
            hosts = dsn.hosts()
            if (
                len(hosts) != 1
                or dsn.scheme not in {"postgres", "postgresql"}
                or dsn.query
                or dsn.fragment
            ):
                raise ValueError
            host = hosts[0]["host"].strip("[]").lower()
            port = hosts[0]["port"] if hosts[0]["port"] is not None else 5432
            username = unquote(hosts[0]["username"] or "")
            password = unquote(hosts[0]["password"] or "")
            database = unquote((dsn.path or "").lstrip("/"))
        except ValidationError, ValueError, TypeError, KeyError, AttributeError:
            raise ConfigurationError(
                "Неверная локальная строка PostgreSQL; значение скрыто."
            ) from None
    if (
        host not in {"localhost", "127.0.0.1", "::1"}
        or not 1 <= port <= 65535
        or not username
        or not database
    ):
        raise ConfigurationError("Проверьте локальные PostgreSQL host/port/user/db.")
    if test:
        target = settings.postgres_test_db
        if (
            target == database
            or target in {"postgres", "template0", "template1"}
            or not (target.endswith("_test") or target.startswith("test_"))
        ):
            raise ConfigurationError(
                "Тестовая БД должна быть отдельной и иметь имя *_test или test_*."
            )
        database = target
    return URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )


def make_engine(
    settings: AppSettings, *, test: bool = False, test_schema: str | None = None
) -> Engine:
    """Create a lazy local PostgreSQL engine; no automatic schema/DB creation."""
    connection_options = {
        "connect_timeout": settings.probe_timeout,
        "application_name": "local-transcriber",
    }
    if test_schema is not None:
        if not test or not re.fullmatch(r"lt_test_[0-9a-f]{32}", test_schema):
            raise ConfigurationError("Небезопасная тестовая схема.")
        connection_options["options"] = "-csearch_path=" + test_schema
    return create_engine(
        database_url(settings, test=test),
        pool_pre_ping=True,
        hide_parameters=True,
        echo=False,
        connect_args=connection_options,
    )


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit only a complete operation; rollback on any exception."""
    try:
        with factory.begin() as session:
            yield session
    except SQLAlchemyError:
        raise PersistenceError("Операция PostgreSQL не выполнена; транзакция отменена.") from None
