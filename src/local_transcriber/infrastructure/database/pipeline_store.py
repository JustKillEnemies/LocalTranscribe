"""PostgreSQL checkpoint adapter reusing the existing atomic chunk repository."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from local_transcriber.application.pipeline import (
    PipelineError,
    PipelineRun,
    PipelineStream,
    StoredSegment,
)
from local_transcriber.domain.jobs import JobStatus
from local_transcriber.domain.media import MediaInfo
from local_transcriber.infrastructure.database.models import (
    AudioStream,
    MediaFile,
    ProcessingChunk,
    TranscriptionJob,
    TranscriptSegment,
)
from local_transcriber.infrastructure.database.repositories import (
    ChunkRepository,
    JobRepository,
    MediaRepository,
    SegmentInput,
)
from local_transcriber.infrastructure.database.session import PersistenceError, transaction


class PostgreSQLPipelineStore:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory
        self.chunks = ChunkRepository(factory)
        self.jobs = JobRepository(factory)

    def prepare(
        self,
        media: MediaInfo,
        indices: tuple[int, ...],
        parameters: dict[str, Any],
        resume: UUID | None,
    ) -> PipelineRun:
        if resume is None:
            media_id, _ = MediaRepository(self.factory).save(media)
            resume = self.jobs.create(
                media_id,
                model_name=parameters["engine"]["model_name"],
                parameters=parameters,
            )
        with transaction(self.factory) as session:
            job = session.get(TranscriptionJob, resume)
            if job is None:
                raise PipelineError("Задание для возобновления не найдено.")
            stored = session.get(MediaFile, job.media_file_id)
            if stored.file_fingerprint != media.fingerprint:
                raise PipelineError("Fingerprint файла изменился; resume заблокирован.")
            if job.parameters != parameters:
                raise PipelineError(
                    "Параметры модели/VAD/участков изменились; resume заблокирован."
                )
            if job.status == "CANCELLED":
                raise PipelineError("Отменённое задание нельзя возобновить.")
            streams = session.scalars(
                select(AudioStream)
                .where(
                    AudioStream.media_file_id == job.media_file_id,
                    AudioStream.stream_index.in_(indices),
                )
                .order_by(AudioStream.stream_index)
            ).all()
            if len(streams) != len(indices):
                raise PipelineError("Метаданные выбранных дорожек неполны; resume заблокирован.")
            return PipelineRun(
                job.id,
                tuple(PipelineStream(x.id, x.stream_index, x.start_time_ms) for x in streams),
                job.status == "COMPLETED",
            )

    def plan(self, job: UUID, stream: UUID, index: int, start: int, end: int) -> None:
        self.chunks.plan_chunk(job, stream, index, start, end)

    def ready(self, job: UUID, stream: UUID, index: int) -> bool:
        with transaction(self.factory) as session:
            return (
                session.scalar(
                    select(ProcessingChunk.status).where(
                        ProcessingChunk.job_id == job,
                        ProcessingChunk.stream_id == stream,
                        ProcessingChunk.chunk_index == index,
                    )
                )
                == "COMPLETED"
            )

    def begin(self, job: UUID) -> None:
        with transaction(self.factory) as session:
            row = session.get(TranscriptionJob, job)
            status = JobStatus(row.status)
        if status == JobStatus.FAILED:
            self.jobs.transition(job, JobStatus.PENDING)
            status = JobStatus.PENDING
        if status == JobStatus.PENDING:
            self.jobs.transition(job, JobStatus.ANALYZING)
        self.jobs.transition(job, JobStatus.PROCESSING)

    def save(
        self,
        job: UUID,
        stream: UUID,
        index: int,
        start: int,
        end: int,
        segments: Sequence[StoredSegment],
    ) -> None:
        with transaction(self.factory) as session:
            row = session.get(TranscriptionJob, job)
            audio_stream = session.get(AudioStream, stream)
            roles = row.parameters.get("parameters", {}).get("roles", {})
            label = roles.get(str(audio_stream.stream_index)) or None
        self.chunks.save_result(
            job,
            stream,
            index,
            start,
            end,
            [SegmentInput(x.start_ms, x.end_ms, x.text, label) for x in segments],
        )

    def tail(self, job: UUID, stream: UUID, before_ms: int) -> Sequence[StoredSegment]:
        with transaction(self.factory) as session:
            rows = session.scalars(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.job_id == job,
                    TranscriptSegment.stream_id == stream,
                    TranscriptSegment.end_ms >= max(0, before_ms - 10_000),
                    TranscriptSegment.start_ms < before_ms,
                )
                .order_by(TranscriptSegment.start_ms.desc())
                .limit(32)
            ).all()
            return [StoredSegment(x.start_ms, x.end_ms, x.raw_text) for x in rows]

    def progress(self, job: UUID) -> tuple[int, int]:
        progress = self.jobs.progress(job)
        return progress.total, progress.completed

    def finish(self, job: UUID) -> None:
        progress = self.jobs.progress(job)
        if progress.total != progress.completed:
            raise PersistenceError("Не все участки подтверждены; завершение запрещено.")
        self.jobs.transition(job, JobStatus.COMPLETED)

    def fail(self, job: UUID, stream: UUID, index: int, message: str) -> None:
        with transaction(self.factory) as session:
            row = session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == job).with_for_update()
            )
            row.status, row.error_message = "FAILED", message
            row.finished_at = datetime.now(UTC)
            chunk = session.scalar(
                select(ProcessingChunk).where(
                    ProcessingChunk.job_id == job,
                    ProcessingChunk.stream_id == stream,
                    ProcessingChunk.chunk_index == index,
                )
            )
            if chunk is not None and chunk.status != "COMPLETED":
                chunk.status, chunk.error_message = "FAILED", message

    def pause(self, job: UUID) -> None:
        self.jobs.transition(job, JobStatus.PAUSED)

    def resume(self, job: UUID) -> None:
        self.jobs.transition(job, JobStatus.PROCESSING)

    def cancel(self, job: UUID, stream: UUID | None, index: int | None) -> None:
        self._stop(job, "CANCELLED", "Отменено пользователем.", stream, index)

    def interrupt(self, job: UUID) -> None:
        self._stop(job, "INTERRUPTED", "Worker прерван; доступно возобновление.", None, None)

    def _stop(
        self, job: UUID, status: str, message: str, stream: UUID | None, index: int | None
    ) -> None:
        with transaction(self.factory) as session:
            row = session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == job).with_for_update()
            )
            if row is None or row.status in {"COMPLETED", "CANCELLED"}:
                return
            row.status, row.error_message = status, message
            row.finished_at = datetime.now(UTC) if status == "CANCELLED" else None
            statement = select(ProcessingChunk).where(
                ProcessingChunk.job_id == job,
                ProcessingChunk.status != "COMPLETED",
            )
            if stream is not None:
                statement = statement.where(
                    ProcessingChunk.stream_id == stream, ProcessingChunk.chunk_index == index
                )
            for chunk in session.scalars(statement):
                chunk.status, chunk.error_message = "FAILED", message
