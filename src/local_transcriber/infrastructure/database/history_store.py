"""Transactional session deletion: foreign-key cascades only, never source filesystem I/O."""

from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from local_transcriber.application.maintenance import DeletedSession
from local_transcriber.infrastructure.database.models import MediaFile, TranscriptionJob
from local_transcriber.infrastructure.database.session import transaction


class PostgreSQLHistoryStore:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def protected_sources(self) -> tuple[Path, ...]:
        with transaction(self.factory) as session:
            return tuple(Path(value) for value in session.scalars(select(MediaFile.file_path)))

    def delete_session(
        self, media_id: UUID, before_delete: Callable[[DeletedSession], None]
    ) -> DeletedSession:
        with transaction(self.factory) as session:
            media = session.scalar(
                select(MediaFile).where(MediaFile.id == media_id).with_for_update()
            )
            if media is None:
                raise ValueError("Запись не найдена; история не изменена.")
            jobs = session.scalars(
                select(TranscriptionJob)
                .where(TranscriptionJob.media_file_id == media_id)
                .with_for_update()
            ).all()
            if any(job.status in {"PENDING", "ANALYZING", "PROCESSING", "PAUSED"} for job in jobs):
                raise ValueError(
                    "Сначала остановите задания записи; удаление активной сессии запрещено."
                )
            protected = tuple(Path(value) for value in session.scalars(select(MediaFile.file_path)))
            job_ids = tuple(job.id for job in jobs)
            snapshot = DeletedSession(media_id, job_ids, protected)
            # Persist source protection while metadata still exists. Callback only classifies
            # owned artifacts; it never removes files, so a later DB rollback remains safe.
            before_delete(snapshot)
            session.execute(delete(MediaFile).where(MediaFile.id == media_id))
            return snapshot

    def cleanup_allowed(self, job_id: UUID) -> bool:
        with transaction(self.factory) as session:
            job = session.get(TranscriptionJob, job_id)
            return job is None or job.status not in {"PENDING", "ANALYZING", "PROCESSING", "PAUSED"}
