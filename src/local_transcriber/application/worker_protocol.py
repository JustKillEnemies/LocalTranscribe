"""Small serializable commands/events for one local GPU worker."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from local_transcriber.application.pipeline import PipelineConfig


class WorkerCommand(StrEnum):
    START = "START_JOB"
    START_JOB = "START_JOB"
    PAUSE = "PAUSE_JOB"
    PAUSE_JOB = "PAUSE_JOB"
    RESUME = "RESUME_JOB"
    RESUME_JOB = "RESUME_JOB"
    CANCEL = "CANCEL_JOB"
    CANCEL_JOB = "CANCEL_JOB"
    SHUTDOWN = "SHUTDOWN"


@dataclass(frozen=True)
class WorkerTask:
    ticket: UUID
    path: Path
    indices: tuple[int, ...]
    config: PipelineConfig
    parameters: dict[str, Any]
    ffmpeg_path: str
    ffprobe_path: str
    model_config: dict[str, Any]
    vad_config: dict[str, Any]
    resume: UUID | None = None


@dataclass(frozen=True)
class Command:
    kind: WorkerCommand
    ticket: UUID | None = None
    task: WorkerTask | None = None


@dataclass(frozen=True)
class WorkerEvent:
    kind: str
    ticket: UUID | None = None
    job_id: UUID | None = None
    payload: Any = None

    @property
    def name(self) -> str:
        """Canonical event names from the original specification."""
        return {
            "STARTED": "JOB_STARTED",
            "PROGRESS": "PROGRESS_UPDATED",
            "PAUSED": "JOB_PAUSED",
            "COMPLETED": "JOB_COMPLETED",
            "ERROR": "JOB_FAILED",
        }.get(self.kind, self.kind)


@dataclass(frozen=True)
class StoreRequest:
    sequence: int
    ticket: UUID
    method: str
    arguments: tuple[Any, ...]


@dataclass(frozen=True)
class StoreReply:
    sequence: int
    result: Any = None
    error: str | None = None
