"""Step 03 unit checks; offline DDL compilation is not a DB integration test."""

import io
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from mako.template import Template
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from local_transcriber.domain.jobs import JobStatus, validate_transition
from local_transcriber.infrastructure.database.models import Base
from local_transcriber.infrastructure.database.repositories import (
    ChunkRepository,
    JobProgress,
    SegmentInput,
)
from local_transcriber.infrastructure.database.session import database_url, make_engine
from local_transcriber.infrastructure.settings import AppSettings, ConfigurationError


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key.upper().startswith("LOCAL_TRANSCRIBER_"):
            monkeypatch.delenv(key)


@pytest.mark.parametrize("current", list(JobStatus))
@pytest.mark.parametrize("target", list(JobStatus))
def test_job_transitions(current: JobStatus, target: JobStatus) -> None:
    allowed = {
        "PENDING": {"ANALYZING", "CANCELLED", "FAILED"},
        "ANALYZING": {"PROCESSING", "FAILED", "CANCELLED", "INTERRUPTED"},
        "PROCESSING": {"PAUSED", "INTERRUPTED", "COMPLETED", "FAILED", "CANCELLED"},
        "PAUSED": {"PROCESSING", "CANCELLED", "INTERRUPTED"},
        "INTERRUPTED": {"PENDING", "PROCESSING", "CANCELLED", "FAILED"},
        "FAILED": {"PENDING", "CANCELLED"},
        "COMPLETED": set(),
        "CANCELLED": set(),
    }
    if current == target or target in allowed[current.value]:
        validate_transition(current, target)
    else:
        with pytest.raises(ValueError, match="Invalid job transition"):
            validate_transition(current, target)


def test_database_url_uses_existing_settings_and_escapes_secrets() -> None:
    settings = AppSettings(postgres_user="user", postgres_password="p@ss/word:%", _env_file=None)
    url = database_url(settings)
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss/word:%"
    assert "p@ss" not in str(url)
    assert database_url(settings, test=True).database == settings.postgres_test_db


@pytest.mark.parametrize("target", ["local_transcriber", "postgres", "template0", "random"])
def test_test_db_guard_prevents_production_and_system_targets(target: str) -> None:
    settings = AppSettings(postgres_user="user", postgres_test_db=target, _env_file=None)
    with pytest.raises(ConfigurationError):
        database_url(settings, test=True)


def test_dsn_production_name_used_for_test_guard() -> None:
    settings = AppSettings(
        postgres_dsn="postgresql://user:hidden@localhost/other_test",
        postgres_test_db="other_test",
        _env_file=None,
    )
    with pytest.raises(ConfigurationError):
        database_url(settings, test=True)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://user:private-secret@outside/db",
        "invalid-private-secret",
        "postgresql://user:private-secret@localhost:0/db",
    ],
)
def test_invalid_dsn_safe_error(dsn: str) -> None:
    settings = AppSettings(postgres_dsn=dsn, _env_file=None)
    with pytest.raises(ConfigurationError) as error:
        database_url(settings)
    assert "private-secret" not in str(error.value)


def test_schema_guard_and_lazy_engine() -> None:
    settings = AppSettings(postgres_user="user", _env_file=None)
    with pytest.raises(ConfigurationError):
        make_engine(settings, test_schema="public")
    with pytest.raises(ConfigurationError):
        make_engine(settings, test=True, test_schema="public")
    engine = make_engine(settings, test=True, test_schema="lt_test_" + uuid4().hex)
    assert engine.dialect.name == "postgresql"
    assert engine.hide_parameters
    engine.dispose()


def test_seven_tables_and_postgresql_types() -> None:
    assert set(Base.metadata.tables) == {
        "media_files",
        "audio_streams",
        "transcription_jobs",
        "processing_chunks",
        "transcript_segments",
        "transcript_versions",
        "custom_terms",
    }
    ddl = "\n".join(
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for table in Base.metadata.sorted_tables
    )
    for expected in (
        "UUID",
        "JSONB",
        "BIGINT",
        "TIMESTAMP WITH TIME ZONE",
        "NUMERIC(5, 2)",
        "uq_chunk_job_stream_index",
        "fk_segment_chunk_scope",
    ):
        assert expected in ddl
    assert "BYTEA" not in ddl


def test_offline_alembic_sql_and_template() -> None:
    root = Path(__file__).resolve().parents[1]
    output = io.StringIO()
    config = Config(str(root / "alembic.ini"), output_buffer=output)
    config.attributes["settings"] = AppSettings(
        postgres_user="offline", postgres_password="never-print-this", _env_file=None
    )
    config.attributes["test_database"] = True
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    for name in Base.metadata.tables:
        assert "CREATE TABLE " + name in sql
    assert "CREATE TRIGGER" in sql
    assert "never-print-this" not in sql
    output.seek(0)
    output.truncate()
    command.downgrade(config, "0001_initial:base", sql=True)
    assert "DROP TABLE processing_chunks" in output.getvalue()
    rendered = Template(filename=str(root / "migrations/script.py.mako")).render(
        message="template test",
        imports="",
        up_revision="next",
        down_revision="0001_initial",
        branch_labels=None,
        depends_on=None,
        upgrades="pass",
        downgrades="pass",
    )
    compile(rendered, "<alembic-template>", "exec")


def test_progress_includes_planned_unfinished_work() -> None:
    assert JobProgress(2, 1).percent == 50
    assert JobProgress(0, 0).percent == 0


@pytest.mark.parametrize(
    "bounds", [(-1, 0, 10), (0, -1, 10), (0, 10, 10), (0, 0.5, 10), (False, 0, 10)]
)
def test_invalid_chunk_rejected_before_database(bounds: tuple) -> None:
    class NoDatabase:
        def begin(self):
            raise AssertionError("Must not use a database for invalid input")

    repository = ChunkRepository(NoDatabase())
    with pytest.raises(ValueError):
        repository.save_result(uuid4(), uuid4(), *bounds, [])


def test_invalid_segment_rejected_before_database() -> None:
    repository = ChunkRepository(None)
    with pytest.raises(ValueError):
        repository.save_result(uuid4(), uuid4(), 0, 0, 100, [SegmentInput(90, 110, "raw")])
