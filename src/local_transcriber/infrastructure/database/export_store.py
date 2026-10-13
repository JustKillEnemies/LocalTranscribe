"""Read-only PostgreSQL export snapshot, independent of media/model availability."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from local_transcriber.application.export import ExportDocument, ExportError
from local_transcriber.application.transcript import TextVersion
from local_transcriber.domain.text import TextSegment, VersionType, source_digest
from local_transcriber.infrastructure.database.models import (
    AudioStream,
    MediaFile,
    ProcessingChunk,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptVersion,
)
from local_transcriber.infrastructure.database.session import transaction


def _version(row: TranscriptVersion) -> TextVersion:
    return TextVersion(
        row.id,
        row.job_id,
        row.version_number,
        VersionType(row.version_type),
        row.content,
        dict(row.processing_metadata),
    )


class PostgreSQLExportSource:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def load(self, job_id: UUID, version_id: UUID | None = None) -> ExportDocument:
        with transaction(self._factory) as session:
            # Consistent metadata/versions/segments even if another user revision is appended.
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            job = session.get(TranscriptionJob, job_id)
            if job is None:
                raise ExportError("Задание не найдено.")
            media = session.get(MediaFile, job.media_file_id)

            def latest(kind: str) -> TranscriptVersion | None:
                return session.scalar(
                    select(TranscriptVersion)
                    .where(
                        TranscriptVersion.job_id == job_id, TranscriptVersion.version_type == kind
                    )
                    .order_by(TranscriptVersion.version_number.desc())
                    .limit(1)
                )

            raw, readable, manual = latest("RAW"), latest("READABLE"), latest("MANUAL")
            if raw is None:
                raise ExportError(
                    "Сохранённый RAW отсутствует; сначала выполните text raw/readable."
                )
            selected = (
                session.get(TranscriptVersion, version_id)
                if version_id
                else manual or readable or raw
            )
            if selected is None or selected.job_id != job_id:
                raise ExportError("Выбранная версия не принадлежит заданию.")
            streams = session.scalars(
                select(AudioStream)
                .where(
                    AudioStream.id.in_(
                        select(ProcessingChunk.stream_id).where(ProcessingChunk.job_id == job_id)
                    )
                )
                .order_by(AudioStream.stream_index)
            ).all()
            rows = session.execute(
                select(TranscriptSegment, AudioStream.stream_index, ProcessingChunk.chunk_index)
                .join(AudioStream, TranscriptSegment.stream_id == AudioStream.id)
                .join(ProcessingChunk, TranscriptSegment.chunk_id == ProcessingChunk.id)
                .where(TranscriptSegment.job_id == job_id)
                .order_by(
                    AudioStream.stream_index,
                    TranscriptSegment.start_ms,
                    ProcessingChunk.chunk_index,
                    TranscriptSegment.segment_index,
                    TranscriptSegment.id,
                )
                .execution_options(yield_per=1000)
            )
            segments = tuple(
                TextSegment(
                    row.id,
                    index,
                    row.start_ms,
                    row.end_ms,
                    row.raw_text,
                    row.speaker_label,
                    chunk,
                    row.segment_index,
                )
                for row, index, chunk in rows
            )
            if source_digest(segments) != raw.processing_metadata.get("source_digest"):
                raise ExportError("RAW не соответствует исходным сегментам; экспорт остановлен.")
            return ExportDocument(
                {
                    "id": str(media.id),
                    "file_path": media.file_path,
                    "filename": media.filename,
                    "file_size_bytes": media.file_size_bytes,
                    "duration_ms": media.duration_ms,
                    "container_format": media.container_format,
                    "file_fingerprint": media.file_fingerprint,
                },
                {
                    "id": str(job.id),
                    "status": job.status,
                    "model_name": job.model_name,
                    "language": job.language,
                    "parameters": dict(job.parameters),
                    "created_at": job.created_at.isoformat(),
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                },
                tuple(
                    {
                        "id": str(s.id),
                        "stream_index": s.stream_index,
                        "codec": s.codec,
                        "sample_rate": s.sample_rate,
                        "channels": s.channels,
                        "start_time_ms": s.start_time_ms,
                        "role_label": s.role_label,
                        "language_tag": s.language_tag,
                        "title": s.title,
                    }
                    for s in streams
                ),
                segments,
                _version(raw),
                _version(readable) if readable else None,
                _version(selected),
            )
