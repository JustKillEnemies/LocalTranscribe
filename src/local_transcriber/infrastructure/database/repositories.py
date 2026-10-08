"""Transactional PostgreSQL adapters; no decoding or transcription."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from local_transcriber.domain.jobs import JobStatus, validate_transition
from local_transcriber.infrastructure.database.models import (
    AudioStream,
    ProcessingChunk,
    TranscriptionJob,
    TranscriptSegment,
)
from local_transcriber.infrastructure.database.session import PersistenceError, transaction


@dataclass(frozen=True)
class SegmentInput:
    start_ms: int
    end_ms: int
    raw_text: str
    speaker_label: str | None = None


@dataclass(frozen=True)
class SegmentRecord:
    id: UUID
    stream_id: UUID
    start_ms: int
    end_ms: int
    raw_text: str
    speaker_label: str | None


@dataclass(frozen=True)
class JobProgress:
    total: int
    completed: int

    @property
    def percent(self) -> Decimal:
        return Decimal(self.completed * 100) / self.total if self.total else Decimal(0)


class JobRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create(
        self,
        media_file_id: UUID,
        *,
        model_name: str,
        language: str = "ru",
        parameters: dict[str, Any] | None = None,
    ) -> UUID:
        identifier = uuid4()
        with transaction(self._factory) as session:
            session.add(
                TranscriptionJob(
                    id=identifier,
                    media_file_id=media_file_id,
                    model_name=model_name,
                    language=language,
                    parameters=parameters or {},
                )
            )
        return identifier

    def transition(self, job_id: UUID, target: JobStatus) -> None:
        with transaction(self._factory) as session:
            job = session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()
            )
            if job is None:
                raise PersistenceError("Задание не найдено.")
            validate_transition(JobStatus(job.status), target)
            job.status = target.value
            if target is JobStatus.PROCESSING and job.started_at is None:
                job.started_at = datetime.now(UTC)
            if target in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
                job.finished_at = datetime.now(UTC)
            else:
                job.finished_at = None

    def progress(self, job_id: UUID) -> JobProgress:
        with transaction(self._factory) as session:
            if session.get(TranscriptionJob, job_id) is None:
                raise PersistenceError("Задание не найдено.")
            total, completed = session.execute(
                select(
                    func.count(), func.count().filter(ProcessingChunk.status == "COMPLETED")
                ).where(ProcessingChunk.job_id == job_id)
            ).one()
            return JobProgress(total, completed)

    def delete(self, job_id: UUID) -> None:
        """Explicit DB-only deletion; source media and filesystem stay untouched."""
        with transaction(self._factory) as session:
            session.execute(delete(TranscriptionJob).where(TranscriptionJob.id == job_id))


class ChunkRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def plan_chunk(
        self, job_id: UUID, stream_id: UUID, chunk_index: int, start_ms: int, end_ms: int
    ) -> UUID:
        """Register an expected chunk so DB progress includes unfinished work."""
        if (
            any(type(value) is not int for value in (chunk_index, start_ms, end_ms))
            or chunk_index < 0
            or start_ms < 0
            or end_ms <= start_ms
        ):
            raise ValueError("Invalid chunk index or integer millisecond interval")
        with transaction(self._factory) as session:
            job = session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()
            )
            if job is None:
                raise PersistenceError("Задание не найдено.")
            stream = session.get(AudioStream, stream_id)
            if stream is None or stream.media_file_id != job.media_file_id:
                raise ValueError("Stream does not belong to the job's media file")
            session.execute(
                insert(ProcessingChunk)
                .values(
                    id=uuid4(),
                    job_id=job_id,
                    stream_id=stream_id,
                    media_file_id=job.media_file_id,
                    chunk_index=chunk_index,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
                .on_conflict_do_nothing(constraint="uq_chunk_job_stream_index")
            )
            chunk = session.scalar(
                select(ProcessingChunk).where(
                    ProcessingChunk.job_id == job_id,
                    ProcessingChunk.stream_id == stream_id,
                    ProcessingChunk.chunk_index == chunk_index,
                )
            )
            if (chunk.start_ms, chunk.end_ms) != (start_ms, end_ms):
                raise ValueError("Plan changes an existing chunk interval")
            total, completed = session.execute(
                select(
                    func.count(), func.count().filter(ProcessingChunk.status == "COMPLETED")
                ).where(ProcessingChunk.job_id == job_id)
            ).one()
            job.total_chunks, job.completed_chunks = total, completed
            job.progress_percent = JobProgress(total, completed).percent
            return chunk.id

    def save_result(
        self,
        job_id: UUID,
        stream_id: UUID,
        chunk_index: int,
        start_ms: int,
        end_ms: int,
        segments: Sequence[SegmentInput],
    ) -> UUID:
        """Atomically persist RAW segments + completion; identical retries are no-ops."""
        if (
            any(type(value) is not int for value in (chunk_index, start_ms, end_ms))
            or chunk_index < 0
            or start_ms < 0
            or end_ms <= start_ms
        ):
            raise ValueError("Invalid chunk index or integer millisecond interval")
        for segment in segments:
            if (
                type(segment.start_ms) is not int
                or type(segment.end_ms) is not int
                or not start_ms <= segment.start_ms < segment.end_ms <= end_ms
            ):
                raise ValueError("Segment must use integer milliseconds inside its chunk")
        with transaction(self._factory) as session:
            # Serialize changes to one job (including races on the same new chunk).
            job = session.scalar(
                select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()
            )
            if job is None:
                raise PersistenceError("Задание не найдено.")
            stream = session.get(AudioStream, stream_id)
            if stream is None or stream.media_file_id != job.media_file_id:
                raise ValueError("Stream does not belong to the job's media file")
            session.execute(
                insert(ProcessingChunk)
                .values(
                    id=uuid4(),
                    job_id=job_id,
                    stream_id=stream_id,
                    media_file_id=job.media_file_id,
                    chunk_index=chunk_index,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
                .on_conflict_do_nothing(constraint="uq_chunk_job_stream_index")
            )
            chunk = session.scalar(
                select(ProcessingChunk)
                .where(
                    ProcessingChunk.job_id == job_id,
                    ProcessingChunk.stream_id == stream_id,
                    ProcessingChunk.chunk_index == chunk_index,
                )
                .with_for_update()
            )
            if (chunk.start_ms, chunk.end_ms) != (start_ms, end_ms):
                raise ValueError("Retry changes an existing chunk interval")
            if chunk.status == "COMPLETED":
                stored = session.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.chunk_id == chunk.id)
                    .order_by(TranscriptSegment.segment_index)
                ).all()
                previous = [
                    SegmentInput(row.start_ms, row.end_ms, row.raw_text, row.speaker_label)
                    for row in stored
                ]
                if previous != list(segments):
                    raise ValueError("Retry changes a completed RAW result")
                return chunk.id
            session.execute(delete(TranscriptSegment).where(TranscriptSegment.chunk_id == chunk.id))
            for index, segment in enumerate(segments):
                session.add(
                    TranscriptSegment(
                        job_id=job_id,
                        chunk_id=chunk.id,
                        stream_id=stream_id,
                        segment_index=index,
                        start_ms=segment.start_ms,
                        end_ms=segment.end_ms,
                        raw_text=segment.raw_text,
                        speaker_label=segment.speaker_label,
                    )
                )
            session.flush()
            chunk.status = "COMPLETED"
            chunk.completed_at = datetime.now(UTC)
            chunk.attempt_count += 1
            chunk.error_message = None
            session.flush()
            total, completed = session.execute(
                select(
                    func.count(), func.count().filter(ProcessingChunk.status == "COMPLETED")
                ).where(ProcessingChunk.job_id == job_id)
            ).one()
            job.total_chunks, job.completed_chunks = total, completed
            job.progress_percent = JobProgress(total, completed).percent
            return chunk.id

    def iter_segments(self, job_id: UUID, *, batch_size: int = 1000) -> Iterator[SegmentRecord]:
        """Read ordered segments with bounded driver/ORM batches."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        with transaction(self._factory) as session:
            statement = (
                select(TranscriptSegment)
                .where(TranscriptSegment.job_id == job_id)
                .order_by(
                    TranscriptSegment.start_ms,
                    TranscriptSegment.stream_id,
                    TranscriptSegment.segment_index,
                    TranscriptSegment.id,
                )
                .execution_options(yield_per=batch_size)
            )
            for row in session.scalars(statement):
                yield SegmentRecord(
                    row.id, row.stream_id, row.start_ms, row.end_ms, row.raw_text, row.speaker_label
                )
