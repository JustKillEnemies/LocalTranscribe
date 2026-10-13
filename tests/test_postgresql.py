"""Real PostgreSQL only; each test owns a random schema in a separate test DB."""

import os
import shutil
import subprocess
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
from local_transcriber.domain.media import AudioStreamInfo, MediaInfo
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
    MediaRepository,
    SegmentInput,
)
from local_transcriber.infrastructure.database.session import (
    PersistenceError,
    database_url,
    make_engine,
    session_factory,
    transaction,
)
from local_transcriber.infrastructure.media import MediaInspectionError, MediaInspector
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
                file_fingerprint=f"fixture:{media}",
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


def test_media_repository_is_idempotent_and_atomic(postgres, tmp_path: Path) -> None:
    engine, factory, config = postgres
    path = tmp_path / "OBS запись.mkv"
    path.write_bytes(b"source remains outside PostgreSQL")
    metadata = MediaInfo(
        path=path,
        filename=path.name,
        size_bytes=path.stat().st_size,
        duration_ms=1500,
        container="matroska,webm",
        fingerprint="v1:repository-test",
        audio_streams=(
            AudioStreamInfo(1, "aac", 48000, 2, "rus", "Микрофон"),
            AudioStreamInfo(4, "opus", 48000, 1, None, "Desktop Audio"),
        ),
    )
    repository = MediaRepository(factory)
    identifier, created = repository.save(metadata)
    repeated, repeated_created = repository.save(metadata)
    assert (repeated, repeated_created) == (identifier, False)
    assert created is True
    with transaction(factory) as session:
        stored = session.get(MediaFile, identifier)
        streams = session.scalars(
            select(AudioStream)
            .where(AudioStream.media_file_id == identifier)
            .order_by(AudioStream.stream_index)
        ).all()
        assert stored.file_path == str(path)
        assert stored.audio_streams_count == 2
        assert [(item.stream_index, item.language_tag, item.title) for item in streams] == [
            (1, "rus", "Микрофон"),
            (4, None, "Desktop Audio"),
        ]
    conflicting = MediaInfo(
        path=path,
        filename=path.name,
        size_bytes=metadata.size_bytes,
        duration_ms=999,
        container=metadata.container,
        fingerprint=metadata.fingerprint,
        audio_streams=metadata.audio_streams,
    )
    with pytest.raises(PersistenceError, match="Конфликт fingerprint"):
        repository.save(conflicting)
    with transaction(factory) as session:
        assert session.scalar(select(func.count()).select_from(MediaFile)) == 1
        assert session.scalar(select(func.count()).select_from(AudioStream)) == 2
    assert path.read_bytes() == b"source remains outside PostgreSQL"


def test_real_ffmpeg_two_audio_stream_inspect_and_import(postgres, tmp_path: Path) -> None:
    engine, factory, config = postgres
    ffmpeg = shutil.which(os.environ.get("LOCAL_TRANSCRIBER_FFMPEG_PATH", "ffmpeg"))
    ffprobe = shutil.which(os.environ.get("LOCAL_TRANSCRIBER_FFPROBE_PATH", "ffprobe"))
    if not ffmpeg or not ffprobe:
        unavailable("Real FFmpeg/ffprobe are not configured")
        return
    media = tmp_path / "OBS две дорожки с пробелами.mkv"
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:r=10:d=0.3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=0.3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=44100:duration=0.3",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:a:0",
            "-metadata:s:a:0",
            "language=rus",
            "-metadata:s:a:0",
            "title=Микрофон",
            "-metadata:s:a:1",
            "title=Desktop Audio",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(media),
        ],
        capture_output=True,
        timeout=15,
        check=False,
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0, "FFmpeg failed to generate the synthetic fixture"
    inspected = MediaInspector(ffprobe, timeout=10).inspect(media)
    assert [item.stream_index for item in inspected.audio_streams] == [1, 2]
    assert [item.sample_rate for item in inspected.audio_streams] == [48000, 44100]
    assert inspected.audio_streams[0].language == "rus"
    repository = MediaRepository(factory)
    identifier, created = repository.save(inspected)
    assert created is True
    assert repository.save(inspected) == (identifier, False)
    with transaction(factory) as session:
        streams = session.scalars(
            select(AudioStream)
            .where(AudioStream.media_file_id == identifier)
            .order_by(AudioStream.stream_index)
        ).all()
        assert [(item.stream_index, item.sample_rate) for item in streams] == [
            (1, 48000),
            (2, 44100),
        ]
    assert media.is_file() and media.stat().st_size > 0
    damaged = tmp_path / "повреждённый файл.mkv"
    damaged.write_bytes(b"not a Matroska stream")
    with pytest.raises(MediaInspectionError, match="повреждён или не поддерживается"):
        MediaInspector(ffprobe, timeout=10).inspect(damaged)
    with transaction(factory) as session:
        assert session.scalar(select(func.count()).select_from(MediaFile)) == 1


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


def test_pipeline_checkpoints_and_resume(postgres) -> None:
    from test_pipeline import Decoder, Recognizer, Segmenter, media

    from local_transcriber.application.pipeline import PipelineError, TranscriptionPipeline
    from local_transcriber.infrastructure.database.pipeline_store import PostgreSQLPipelineStore

    engine, factory, _ = postgres
    store, decoder, recognizer = PostgreSQLPipelineStore(factory), Decoder(), Recognizer()
    recognizer.fail_on = 3
    pipeline = TranscriptionPipeline(decoder, Segmenter(), recognizer, store, lambda: "fixture:v1")
    with pytest.raises(PipelineError):
        pipeline.execute(media(), (1,))
    with transaction(factory) as session:
        job = session.scalar(select(TranscriptionJob))
        job_id = job.id
        assert job.status == "FAILED"
        assert job.completed_chunks == 2
        assert session.scalar(select(func.count()).select_from(TranscriptSegment)) == 2
    recognizer.fail_on = None
    pipeline.execute(media(), (1,), resume=job_id)
    count = len(decoder.calls)
    pipeline.execute(media(), (1,), resume=job_id)
    assert len(decoder.calls) == count
    with transaction(factory) as session:
        job = session.get(TranscriptionJob, job_id)
        assert job.status == "COMPLETED"
        assert job.completed_chunks == job.total_chunks == 5
        assert session.scalar(select(func.count()).select_from(TranscriptSegment)) == 5
    assert decoder.active == 0


def test_pipeline_real_hour(postgres, capsys) -> None:
    import time
    from dataclasses import replace

    from local_transcriber.application.pipeline import PipelineConfig, TranscriptionPipeline
    from local_transcriber.infrastructure.database.pipeline_store import PostgreSQLPipelineStore
    from local_transcriber.infrastructure.faster_whisper_engine import (
        FasterWhisperConfig,
        FasterWhisperEngine,
    )
    from local_transcriber.infrastructure.ffmpeg_decoder import FFmpegMediaDecoder
    from local_transcriber.infrastructure.media import media_fingerprint
    from local_transcriber.infrastructure.silero_segmenter import SileroSpeechSegmenter

    source = os.environ.get("LOCAL_TRANSCRIBER_PIPELINE_SMOKE")
    if not source:
        pytest.skip("60-minute private-media gate requires LOCAL_TRANSCRIBER_PIPELINE_SMOKE")
    settings = load_settings()
    info = MediaInspector(settings.ffprobe_path, timeout=10).inspect(Path(source))
    assert info.duration_ms >= 3_600_000
    assert info.size_bytes > 1_000_000_000
    _, factory, _ = postgres
    before = Path(source).stat()
    runtime = FasterWhisperEngine(
        replace(FasterWhisperConfig.from_settings(settings), word_timestamps=True)
    )
    started = time.perf_counter()

    def progress(job, total, completed):
        with capsys.disabled():
            print(
                f"HOUR_SMOKE checkpoint={completed}/{total} elapsed={time.perf_counter() - started:.1f}s",
                flush=True,
            )

    pipeline = TranscriptionPipeline(
        FFmpegMediaDecoder(settings.ffmpeg_path),
        SileroSpeechSegmenter(),
        runtime,
        PostgreSQLPipelineStore(factory),
        lambda: media_fingerprint(info.path),
        config=PipelineConfig(end_ms=3_600_000),
        on_progress=progress,
    )
    job = pipeline.execute(info, (1,))
    with transaction(factory) as session:
        stored = session.get(TranscriptionJob, job)
        assert stored.status == "COMPLETED"
        assert stored.total_chunks == stored.completed_chunks == 12
        count = session.scalar(select(func.count()).select_from(TranscriptSegment))
        assert count > 0
        assert session.scalar(select(func.max(TranscriptSegment.end_ms))) <= 3_600_000
    assert runtime.active_compute_type == "float16"
    after = Path(source).stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    with capsys.disabled():
        print(
            f"HOUR_SMOKE PASS seconds={time.perf_counter() - started:.3f} segments={count} compute=float16",
            flush=True,
        )


def test_worker_pause_cancel_and_crash_preserve_checkpoints(postgres) -> None:
    from test_worker import fake_pipeline_executor, task, until

    from local_transcriber.application.worker_protocol import WorkerCommand
    from local_transcriber.infrastructure.database.pipeline_store import PostgreSQLPipelineStore
    from local_transcriber.infrastructure.worker_manager import WorkerManager

    _, factory, _ = postgres
    with WorkerManager(
        PostgreSQLPipelineStore(factory), executor=fake_pipeline_executor
    ) as manager:
        item = task("gate")
        manager.submit(item)
        active, _ = until(manager, "CHUNK_ACTIVE", item.ticket)
        job = active.job_id
        manager.command(WorkerCommand.PAUSE, item.ticket)
        until(manager, "PAUSED", item.ticket)
        with transaction(factory) as session:
            row = session.get(TranscriptionJob, job)
            assert row.status == "PAUSED"
            assert row.completed_chunks == 1
        manager._process.kill()  # owned worker only; supervisor must recover durable state
        until(manager, "INTERRUPTED", item.ticket)
        with transaction(factory) as session:
            assert session.get(TranscriptionJob, job).status == "INTERRUPTED"
            assert session.scalar(select(func.count()).select_from(TranscriptSegment)) == 1
        manager.restart()
        resumed = task("gate", resume=job)
        manager.submit(resumed)
        until(manager, "CHUNK_ACTIVE", resumed.ticket)
        manager.command(WorkerCommand.CANCEL, resumed.ticket)
        until(manager, "CANCELLED", resumed.ticket)
        with transaction(factory) as session:
            row = session.get(TranscriptionJob, job)
            assert row.status == "CANCELLED"
            assert row.completed_chunks == 1
            assert session.scalar(select(func.count()).select_from(TranscriptSegment)) == 1


def test_real_gpu_worker_short_smoke(postgres, capsys) -> None:
    import time
    from dataclasses import asdict, replace

    from test_worker import until

    from local_transcriber.application.pipeline import PipelineConfig
    from local_transcriber.application.worker_protocol import WorkerTask
    from local_transcriber.infrastructure.database.pipeline_store import PostgreSQLPipelineStore
    from local_transcriber.infrastructure.faster_whisper_engine import FasterWhisperConfig
    from local_transcriber.infrastructure.silero_segmenter import SegmentationConfig
    from local_transcriber.infrastructure.worker_manager import WorkerManager

    source = os.environ.get("LOCAL_TRANSCRIBER_WORKER_SMOKE")
    if not source:
        pytest.skip("set LOCAL_TRANSCRIBER_WORKER_SMOKE for offline real GPU worker validation")
    settings = load_settings()
    _, factory, _ = postgres
    model = replace(FasterWhisperConfig.from_settings(settings), word_timestamps=True)
    started = time.perf_counter()
    with WorkerManager(PostgreSQLPipelineStore(factory)) as manager:
        item = WorkerTask(
            uuid4(),
            Path(source),
            (1,),
            PipelineConfig(end_ms=45_000),
            {},
            settings.ffmpeg_path,
            settings.ffprobe_path,
            asdict(model),
            asdict(SegmentationConfig()),
        )
        manager.submit(item)
        completed, events = until(manager, "COMPLETED", item.ticket, timeout=60)
        assert any(x.kind == "MODEL_SELECTED" for x in events)
        with transaction(factory) as session:
            assert session.get(TranscriptionJob, completed.job_id).status == "COMPLETED"
            count = session.scalar(select(func.count()).select_from(TranscriptSegment))
            assert count > 0
        with capsys.disabled():
            print(
                f"GPU_WORKER PASS seconds={time.perf_counter() - started:.3f} words={count} pid={manager.pid}",
                flush=True,
            )


def _completed_text_job(factory):
    media, streams, jobs = seed(factory)
    chunks = ChunkRepository(factory)
    chunks.save_result(jobs[0], streams[1], 0, 0, 1000, [SegmentInput(10, 20, "English", "System")])
    chunks.save_result(
        jobs[0],
        streams[0],
        0,
        0,
        1000,
        [
            SegmentInput(200, 300, "  постгрес", "Mic"),
            SegmentInput(10, 20, "я я", "Mic"),
        ],
    )
    repository = JobRepository(factory)
    for state in (JobStatus.ANALYZING, JobStatus.PROCESSING, JobStatus.COMPLETED):
        repository.transition(jobs[0], state)
    return jobs, streams


def test_text_versions_preserve_raw_and_manual_after_reprocessing(postgres) -> None:
    from local_transcriber.application.transcript import TranscriptService
    from local_transcriber.domain.text import Term, TextRules, VersionType
    from local_transcriber.infrastructure.database.text_store import (
        PostgreSQLTranscriptStore,
        TermRepository,
    )

    engine, factory, config = postgres
    jobs, streams = _completed_text_job(factory)
    terms = TermRepository(factory)
    terms.create(Term("PostgreSQL", ("постгрес",)))
    service = TranscriptService(PostgreSQLTranscriptStore(factory), terms)
    raw = service.raw(jobs[0])
    assert raw.content == "я я  постгрес\n\nEnglish"
    original = raw.content.encode("utf-8")
    assert service.raw(jobs[0]).id == raw.id
    readable = service.readable(jobs[0])
    assert readable.content == "[Дорожка 0] Mic: я я PostgreSQL.\n\n[Дорожка 1] System: English."
    assert readable.metadata["raw_version_id"] == str(raw.id)
    assert readable.metadata["processor"] == "conservative-text"
    manual = service.manual(jobs[0], readable.id, "Моя точная редакция: 42,5\n")
    second = service.readable(jobs[0], TextRules(normalize_terms=False, terminal_period=False))
    assert "постгрес" in second.content
    assert [v.number for v in service.versions(jobs[0])] == [1, 2, 3, 4]
    assert [v.kind for v in service.versions(jobs[0])] == [
        VersionType.RAW,
        VersionType.READABLE,
        VersionType.MANUAL,
        VersionType.READABLE,
    ]
    assert service.versions(jobs[0])[2] == manual
    assert service.raw(jobs[0]).content.encode("utf-8") == original
    assert sorted(
        row.raw_text for row in ChunkRepository(factory).iter_segments(jobs[0])
    ) == sorted(
        [
            "я я",
            "English",
            "  постгрес",
        ]
    )
    with pytest.raises(PersistenceError):
        with transaction(factory) as session:
            session.execute(
                update(TranscriptVersion)
                .where(TranscriptVersion.id == raw.id)
                .values(content="overwrite")
            )
    assert service.raw(jobs[0]).content.encode("utf-8") == original


def test_text_foreign_base_incomplete_job_and_bad_snapshot_rollback(postgres) -> None:
    from local_transcriber.application.transcript import TranscriptService
    from local_transcriber.domain.text import ProcessedText
    from local_transcriber.infrastructure.database.text_store import (
        PostgreSQLTranscriptStore,
        TermRepository,
    )

    engine, factory, config = postgres
    jobs, streams = _completed_text_job(factory)
    store = PostgreSQLTranscriptStore(factory)
    service = TranscriptService(store, TermRepository(factory))
    with pytest.raises(ValueError, match="completed job"):
        service.raw(jobs[1])
    raw = service.raw(jobs[0])
    with pytest.raises(ValueError, match="belong"):
        service.manual(jobs[1], raw.id, "foreign")
    with pytest.raises(ValueError, match="NUL"):
        service.manual(jobs[0], raw.id, "bad\0text")
    with pytest.raises(ValueError, match="snapshot"):
        store.save_readable(jobs[0], raw.id, ProcessedText("bad", {"source_digest": "wrong"}))
    with pytest.raises(PersistenceError, match="не найдено"):
        service.raw(uuid4())
    assert len(service.versions(jobs[0])) == 1
    assert service.versions(jobs[1]) == ()
    assert service.manual(jobs[0], raw.id, "").content == ""


def test_text_parallel_version_numbers_are_unique(postgres) -> None:
    from local_transcriber.application.transcript import TranscriptService
    from local_transcriber.infrastructure.database.text_store import (
        PostgreSQLTranscriptStore,
        TermRepository,
    )

    engine, factory, config = postgres
    jobs, streams = _completed_text_job(factory)
    service = TranscriptService(PostgreSQLTranscriptStore(factory), TermRepository(factory))
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions = list(pool.map(lambda _: service.raw(jobs[0]), range(4)))
        assert len({v.id for v in versions}) == 1
        created = list(pool.map(lambda _: service.readable(jobs[0]), range(6)))
    assert sorted(v.number for v in created) == list(range(2, 8))
    assert len(service.versions(jobs[0])) == 7


def test_term_crud_import_updates_and_atomic_rollback(postgres) -> None:
    from local_transcriber.application.transcript import parse_terms
    from local_transcriber.domain.text import Term
    from local_transcriber.infrastructure.database.text_store import TermRepository

    engine, factory, config = postgres
    repository = TermRepository(factory)
    identifier = repository.create(Term("PostgreSQL", ("postgres",)))
    repository.update(identifier, Term("PostgreSQL", ("постгрес",), False))
    assert repository.enabled_terms() == ()
    assert repository.import_terms(parse_terms("PostgreSQL\tpostgres|постгрес\nPython")) == 2
    assert repository.list()[0].id == identifier
    assert len(repository.enabled_terms()) == 2
    with pytest.raises(PersistenceError):
        repository.create(Term("PostgreSQL"))
    before = repository.list()
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE custom_terms ADD CONSTRAINT test_reject_term CHECK (canonical_form <> 'Rejected')"
            )
        )
    with pytest.raises(PersistenceError):
        repository.import_terms((Term("PostgreSQL", ("changed",)), Term("Rejected")))
    assert repository.list() == before
    with pytest.raises(ValueError, match="Duplicate"):
        repository.import_terms((Term("PG"), Term("pg")))
    assert repository.list() == before
    repository.delete(identifier)
    assert [row.term.canonical for row in repository.list()] == ["Python"]
    with pytest.raises(ValueError, match="not found"):
        repository.update(identifier, Term("PG"))
    with pytest.raises(ValueError, match="not found"):
        repository.delete(identifier)


def test_empty_completed_transcript_versions(postgres) -> None:
    from local_transcriber.application.transcript import TranscriptService
    from local_transcriber.infrastructure.database.text_store import (
        PostgreSQLTranscriptStore,
        TermRepository,
    )

    engine, factory, config = postgres
    media, streams, jobs = seed(factory)
    ChunkRepository(factory).save_result(jobs[0], streams[0], 0, 0, 1000, [])
    for status in (JobStatus.ANALYZING, JobStatus.PROCESSING, JobStatus.COMPLETED):
        JobRepository(factory).transition(jobs[0], status)
    service = TranscriptService(PostgreSQLTranscriptStore(factory), TermRepository(factory))
    assert service.raw(jobs[0]).content == service.readable(jobs[0]).content == ""
    assert len(service.versions(jobs[0])) == 2


def test_text_cli_real_database_versions_and_manual_file(
    postgres, tmp_path, monkeypatch, capsys
) -> None:
    import json

    from local_transcriber.__main__ import main
    from local_transcriber.infrastructure.database import session as sessions

    engine, factory, config = postgres
    jobs, streams = _completed_text_job(factory)
    # Redirect composition to this test's real PostgreSQL schema, never to the working DB.
    monkeypatch.setattr(sessions, "make_engine", lambda settings: engine)
    assert main(["text", "raw", str(jobs[0])]) == 0
    raw = json.loads(capsys.readouterr().out)
    path = tmp_path / "Ручная версия.txt"
    path.write_text("Мои правки\n", encoding="utf-8")
    assert main(["text", "manual", str(jobs[0]), "--base", raw["id"], "--file", str(path)]) == 0
    manual = json.loads(capsys.readouterr().out)
    assert manual["content"] == path.read_bytes().decode("utf-8")
    assert main(["text", "show", str(jobs[0]), "--version", manual["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["content"] == path.read_bytes().decode("utf-8")
    assert main(["text", "versions", str(jobs[0])]) == 0
    assert len(json.loads(capsys.readouterr().out)["versions"]) == 2
    assert main(["terms", "add", "PostgreSQL", "--variant", "постгрес"]) == 0
    term = json.loads(capsys.readouterr().out)
    assert main(["terms", "delete", term["id"]]) == 0
    capsys.readouterr()
    assert main(["text", "show", str(jobs[0]), "--version", str(uuid4())]) == 2
    assert "does not belong" in capsys.readouterr().err
