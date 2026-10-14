"""Installed and frozen upgrade composition, sharing the existing Alembic scripts."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util import CommandError
from sqlalchemy.exc import SQLAlchemyError

from local_transcriber.infrastructure.database.session import PersistenceError, make_engine
from local_transcriber.infrastructure.settings import AppSettings


def upgrade_database(settings: AppSettings, *, test: bool = False) -> None:
    """Apply head on a configured local DB; never create DBs/users/services."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[4]))
    scripts = root / "migrations"
    if not (scripts / "env.py").is_file():
        raise PersistenceError("Файлы миграций недоступны; проверьте комплект поставки.")
    config = Config()
    config.set_main_option("script_location", str(scripts).replace("%", "%%"))
    config.attributes.update(settings=settings, test_database=test)
    engine = make_engine(settings, test=test)
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    except SQLAlchemyError, CommandError, OSError:
        raise PersistenceError(
            "Миграции PostgreSQL не применены; проверьте доступ и схему."
        ) from None
    finally:
        engine.dispose()
