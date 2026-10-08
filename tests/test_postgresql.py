"""Real PostgreSQL only; each test owns a random schema in a separate test DB."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, inspect, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from local_transcriber.domain.jobs import JobStatus
from local_transcriber.infrastructure.database.models import (
    AudioStream,
    Base,
    CustomTerm,
    MediaFile,
    ProcessingChunk,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptVersion,
)
from local_transcriber.infrastructure.database.repositories import (
    ChunkRepository,
    JobRepository,
    SegmentInput,
)
from local_transcriber.infrastructure.database.session import (
    PersistenceError,
    database_url,
    make_engine,
    session_factory,
    transaction,
)
from local_transcriber.infrastructure.settings import ConfigurationError, load_settings

pytestmark = pytest.mark.integration


def unavailable(reason: str) -> None:
    if os.environ.get("PYTEST_REQUIRE_POSTGRES") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
def postgres() -> Iterator[tuple[Engine, sessionmaker[Session], Config]]:
    settings = load_settings()
    try:
        url = database_url(settings, test=True)
    except ConfigurationError:
        if not settings.postgres_user and not settings.postgres_dsn:
            unavailable("Real PostgreSQL test DB access is not configured in AppSettings")
        pytest.fail("Unsafe/invalid separate test DB settings; no database changed")
    probe = make_engine(settings, test=True)
    try:
        with probe.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == url.database
    except SQLAlchemyError:
        probe.dispose()
        unavailable(
            "Real separate PostgreSQL test DB unavailable: check user/password/database/permissions; secrets hidden"
        )
    schema = "lt_test_" + uuid4().hex
    with probe.begin() as connection:
        connection.execute(text('CREATE SCHEMA "' + schema + '"'))
    engine = make_engine(settings, test=True, test_schema=schema)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes.update(settings=settings, test_database=True, test_schema=schema)
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        config.attributes.pop("connection")
        yield engine, session_factory(engine), config
    finally:
        engine.dispose()
        with probe.begin() as connection:
            connection.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
        probe.dispose()


def seed(
    factory: sessionmaker[Session], source: str = "synthetic.mkv"
) -> tuple[UUID, tuple[UUID, UUID], tuple[UUID, UUID]]:
    media = uuid4()
    streams = uuid4(), uuid4()
    with transaction(factory) as session:
        session.add(
            MediaFile(
                id=media,
                file_path=source,
                filename="synthetic.mkv",
                file_size_bytes=100,
                duration_ms=1000,
                container_format="mkv",
                audio_streams_count=2,
                file_fingerprint="fixture",
            )
        )
        session.flush()
        session.add_all(
            [
                AudioStream(
                    id=identifier,
                    media_file_id=media,
                    stream_index=index,
                    codec="pcm",
                    sample_rate=16000,
                    channels=1,
                )
                for index, identifier in enumerate(streams)
            ]
        )
    jobs = JobRepository(factory)
    return (
        media,
        streams,
        (jobs.create(media, model_name="medium"), jobs.create(media, model_name="medium")),
    )


def test_migration_upgrade_repeat_downgrade_upgrade(postgres) -> None:
    engine, factory, config = postgres
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "base")
    assert not set(Base.metadata.tables) & set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())


def test_chunk_atomic_idempotence_two_streams_two_jobs_and_sorting(postgres) -> None:
    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    repository = ChunkRepository(factory)
    repository.plan_chunk(jobs[0], streams[0], 0, 0, 500)
    repository.plan_chunk(jobs[0], streams[1], 0, 0, 500)
    segments = [SegmentInput(200, 250, "later"), SegmentInput(10, 50, "first")]
    identifier = repository.save_result(jobs[0], streams[0], 0, 0, 500, segments)
    assert repository.save_result(jobs[0], streams[0], 0, 0, 500, segments) == identifier
    assert JobRepository(factory).progress(jobs[0]).percent == 50
    repository.save_result(jobs[0], streams[1], 0, 0, 500, [SegmentInput(100, 150, "other track")])
    repository.save_result(jobs[1], streams[0], 0, 0, 500, [SegmentInput(20, 60, "other job")])
    assert [row.start_ms for row in repository.iter_segments(jobs[0], batch_size=1)] == [
        10,
        100,
        200,
    ]
    with transaction(factory) as session:
        assert session.scalar(select(func.count()).select_from(ProcessingChunk)) == 3
        assert session.scalar(select(func.count()).select_from(TranscriptSegment)) == 4
        job = session.get(TranscriptionJob, jobs[0])
        assert (job.total_chunks, job.completed_chunks, job.progress_percent) == (2, 2, 100)


def test_atomic_rollback_after_segment_flush_failure(postgres) -> None:
    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    repository = ChunkRepository(factory)
    repository.plan_chunk(jobs[0], streams[0], 0, 0, 500)
    with pytest.raises(PersistenceError):
        repository.save_result(
            jobs[0],
            streams[0],
            0,
            0,
            500,
            [SegmentInput(10, 20, "valid"), SegmentInput(30, 40, None)],
        )
    with transaction(factory) as session:
        assert session.scalar(select(func.count()).select_from(TranscriptSegment)) == 0
        chunk = session.scalar(select(ProcessingChunk))
        assert chunk.status == "PENDING" and chunk.completed_at is None and chunk.attempt_count == 0
        assert session.get(TranscriptionJob, jobs[0]).completed_chunks == 0


def test_conflicting_retry_preserves_confirmed_raw(postgres) -> None:
    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    repository = ChunkRepository(factory)
    repository.save_result(jobs[0], streams[0], 0, 0, 500, [SegmentInput(10, 20, "original")])
    with pytest.raises(ValueError, match="completed RAW"):
        repository.save_result(jobs[0], streams[0], 0, 0, 500, [SegmentInput(10, 20, "changed")])
    assert [row.raw_text for row in repository.iter_segments(jobs[0])] == ["original"]


def test_unique_chunk_and_invalid_fk_constraints(postgres) -> None:
    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    repository = ChunkRepository(factory)
    repository.plan_chunk(jobs[0], streams[0], 0, 0, 500)
    with pytest.raises(PersistenceError):
        with transaction(factory) as session:
            session.add(
                ProcessingChunk(
                    job_id=jobs[0],
                    stream_id=streams[0],
                    media_file_id=media,
                    chunk_index=0,
                    start_ms=0,
                    end_ms=500,
                )
            )
    with pytest.raises(PersistenceError):
        with transaction(factory) as session:
            session.add(
                AudioStream(
                    media_file_id=uuid4(),
                    stream_index=0,
                    codec="pcm",
                    sample_rate=16000,
                    channels=1,
                )
            )


def test_cross_media_and_cross_job_segment_rejected(postgres) -> None:
    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    other_media, other_streams, other_jobs = seed(factory)
    repository = ChunkRepository(factory)
    with pytest.raises(ValueError):
        repository.plan_chunk(jobs[0], other_streams[0], 0, 0, 100)
    with pytest.raises(PersistenceError):
        with transaction(factory) as session:
            session.add(
                ProcessingChunk(
                    job_id=jobs[0],
                    stream_id=other_streams[0],
                    media_file_id=media,
                    chunk_index=0,
                    start_ms=0,
                    end_ms=100,
                )
            )
    chunk = repository.plan_chunk(jobs[0], streams[0], 0, 0, 100)
    with pytest.raises(PersistenceError):
        with transaction(factory) as session:
            session.add(
                TranscriptSegment(
                    job_id=jobs[1],
                    stream_id=streams[0],
                    chunk_id=chunk,
                    start_ms=1,
                    end_ms=10,
                    segment_index=0,
                    raw_text="wrong scope",
                )
            )


@pytest.mark.parametrize(
    "kind", ["time", "status", "json", "term", "version", "progress", "completion", "segment_time"]
)
def test_checks_reject_invalid_data(postgres, kind: str) -> None:
    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    with pytest.raises(PersistenceError):
        with transaction(factory) as session:
            if kind == "time":
                session.add(
                    ProcessingChunk(
                        job_id=jobs[0],
                        stream_id=streams[0],
                        media_file_id=media,
                        chunk_index=0,
                        start_ms=10,
                        end_ms=0,
                    )
                )
            elif kind == "status":
                session.execute(
                    update(TranscriptionJob)
                    .where(TranscriptionJob.id == jobs[0])
                    .values(status="UNKNOWN")
                )
            elif kind == "json":
                session.execute(
                    update(TranscriptionJob)
                    .where(TranscriptionJob.id == jobs[0])
                    .values(parameters=[])
                )
            elif kind == "term":
                session.add(CustomTerm(canonical_form=" ", variants=[]))
            elif kind == "progress":
                session.execute(
                    update(TranscriptionJob)
                    .where(TranscriptionJob.id == jobs[0])
                    .values(total_chunks=0, completed_chunks=1, progress_percent=101)
                )
            elif kind == "completion":
                session.add(
                    ProcessingChunk(
                        job_id=jobs[0],
                        stream_id=streams[0],
                        media_file_id=media,
                        chunk_index=0,
                        start_ms=0,
                        end_ms=100,
                        status="COMPLETED",
                        completed_at=None,
                    )
                )
            elif kind == "segment_time":
                chunk = ChunkRepository(factory).plan_chunk(jobs[0], streams[0], 0, 0, 100)
                session.add(
                    TranscriptSegment(
                        job_id=jobs[0],
                        chunk_id=chunk,
                        stream_id=streams[0],
                        segment_index=0,
                        start_ms=-1,
                        end_ms=10,
                        raw_text="invalid time",
                    )
                )
            else:
                session.add(
                    TranscriptVersion(
                        job_id=jobs[0], version_number=0, version_type="RAW", content="test"
                    )
                )


def test_raw_immutable_delete_job_preserves_original(postgres, tmp_path: Path) -> None:
    engine, factory, config = postgres
    original = tmp_path / "recording.mkv"
    original.write_bytes(b"preserve user file")
    media, streams, jobs = seed(factory, str(original))
    repository = ChunkRepository(factory)
    repository.save_result(jobs[0], streams[0], 0, 0, 100, [SegmentInput(1, 10, "RAW")])
    with transaction(factory) as session:
        version = TranscriptVersion(
            job_id=jobs[0], version_number=1, version_type="RAW", content="RAW"
        )
        session.add(version)
    for statement in (
        update(TranscriptSegment)
        .where(TranscriptSegment.job_id == jobs[0])
        .values(raw_text="changed"),
        update(TranscriptVersion)
        .where(TranscriptVersion.job_id == jobs[0])
        .values(content="changed"),
    ):
        with pytest.raises(PersistenceError):
            with transaction(factory) as session:
                session.execute(statement)
    JobRepository(factory).delete(jobs[0])
    with transaction(factory) as session:
        assert session.get(MediaFile, media) is not None
        assert session.get(TranscriptionJob, jobs[1]) is not None
        assert session.scalar(select(func.count()).select_from(TranscriptSegment)) == 0
        assert session.scalar(select(func.count()).select_from(TranscriptVersion)) == 0
    assert original.read_bytes() == b"preserve user file"


def test_concurrent_same_chunk_is_idempotent(postgres) -> None:
    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    repository = ChunkRepository(factory)

    def save():
        return repository.save_result(jobs[0], streams[0], 0, 0, 100, [SegmentInput(1, 10, "RAW")])

    with ThreadPoolExecutor(max_workers=2) as executor:
        identifiers = list(executor.map(lambda _: save(), range(2)))
    assert identifiers[0] == identifiers[1]
    assert len(list(repository.iter_segments(jobs[0]))) == 1


def test_transaction_rollback_non_database_exception(postgres) -> None:
    engine, factory, config = postgres
    with pytest.raises(RuntimeError, match="abort"):
        with transaction(factory) as session:
            session.add(CustomTerm(canonical_form="rollback-term", variants=[]))
            session.flush()
            raise RuntimeError("abort")
    with transaction(factory) as session:
        assert session.scalar(select(func.count()).select_from(CustomTerm)) == 0


def test_repository_job_transitions(postgres) -> None:
    engine, factory, config = postgres
    media, streams, identifiers = seed(factory)
    jobs = JobRepository(factory)
    jobs.transition(identifiers[0], JobStatus.ANALYZING)
    jobs.transition(identifiers[0], JobStatus.PROCESSING)
    jobs.transition(identifiers[0], JobStatus.COMPLETED)
    with pytest.raises(ValueError):
        jobs.transition(identifiers[0], JobStatus.PROCESSING)
    with transaction(factory) as session:
        assert session.get(TranscriptionJob, identifiers[0]).status == "COMPLETED"


@pytest.mark.parametrize("kind", ["audio", "segment", "version", "term"])
def test_additional_uniqueness_constraints(postgres, kind: str) -> None:
    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    chunk = ChunkRepository(factory).save_result(
        jobs[0], streams[0], 0, 0, 100, [SegmentInput(1, 10, "RAW")]
    )
    with transaction(factory) as session:
        session.add(
            TranscriptVersion(
                job_id=jobs[0], version_number=1, version_type="READABLE", content="readable"
            )
        )
        session.add(CustomTerm(canonical_form="OBS", variants=["обс"]))
    with pytest.raises(PersistenceError):
        with transaction(factory) as session:
            if kind == "audio":
                session.add(
                    AudioStream(
                        media_file_id=media,
                        stream_index=0,
                        codec="pcm",
                        sample_rate=16000,
                        channels=1,
                    )
                )
            elif kind == "segment":
                session.add(
                    TranscriptSegment(
                        job_id=jobs[0],
                        chunk_id=chunk,
                        stream_id=streams[0],
                        segment_index=0,
                        start_ms=20,
                        end_ms=30,
                        raw_text="duplicate index",
                    )
                )
            elif kind == "version":
                session.add(
                    TranscriptVersion(
                        job_id=jobs[0],
                        version_number=1,
                        version_type="MANUAL",
                        content="duplicate number",
                    )
                )
            else:
                session.add(CustomTerm(canonical_form="OBS", variants=[]))
    with transaction(factory) as session:
        assert session.scalar(select(func.count()).select_from(TranscriptSegment)) == 1
        assert session.scalar(select(func.count()).select_from(TranscriptVersion)) == 1
        assert session.scalar(select(func.count()).select_from(CustomTerm)) == 1
