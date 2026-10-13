"""Explicit history deletion through ports, with source preservation and cleanup reporting."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class DeleteSession:
    media_id: UUID
    confirmed: bool = False
    remove_derived: bool = False


@dataclass(frozen=True)
class DeletedSession:
    media_id: UUID
    job_ids: tuple[UUID, ...]
    protected_paths: tuple[Path, ...]


@dataclass(frozen=True)
class DeletionResult:
    media_id: UUID
    jobs_deleted: int
    files_deleted: int
    cleanup_pending: bool


class HistoryStore(Protocol):
    def delete_session(
        self, media_id: UUID, before_delete: Callable[[DeletedSession], None]
    ) -> DeletedSession: ...


class CleanupCounts(Protocol):
    deleted: int
    skipped: int
    failed: int


class DerivedFiles(Protocol):
    def protect_sources(self, sources: tuple[Path, ...]) -> None: ...

    def cleanup_job(
        self, job_id: UUID, *, include_retained: bool, protected: tuple[Path, ...]
    ) -> CleanupCounts: ...


class DeleteHistory:
    def __init__(self, history: HistoryStore, files: DerivedFiles) -> None:
        self.history, self.files = history, files

    def execute(self, request: DeleteSession) -> DeletionResult:
        if request.confirmed is not True:
            raise ValueError("Удаление требует явного подтверждения.")
        snapshot = self.history.delete_session(
            request.media_id, lambda snapshot: self.files.protect_sources(snapshot.protected_paths)
        )
        deleted, pending = 0, False
        # DB cascade commits first. Filesystem cannot share that transaction: a failed
        # cleanup is reported and retryable; source paths are never passed to unlink.
        if request.remove_derived:
            for job_id in snapshot.job_ids:
                try:
                    report = self.files.cleanup_job(
                        job_id, include_retained=True, protected=snapshot.protected_paths
                    )
                    deleted += report.deleted
                    pending |= bool(report.failed or report.skipped)
                except OSError, ValueError:
                    pending = True
        return DeletionResult(request.media_id, len(snapshot.job_ids), deleted, pending)
