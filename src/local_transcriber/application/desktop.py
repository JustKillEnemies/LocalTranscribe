"""Immutable GUI messages and job choices; no Qt, SQL or recognition runtime."""

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from local_transcriber.domain.jobs import JobStatus
from local_transcriber.domain.media import MediaInfo


@dataclass(frozen=True)
class JobChoices:
    indices: tuple[int, ...]
    roles: tuple[tuple[int, str], ...] = ()
    model: str = "large-v3-turbo"
    compute: str = "float16"
    device: str = "cuda"
    vad: bool = True
    keep_audio: bool = False

    def __post_init__(self) -> None:
        if not self.indices or len(set(self.indices)) != len(self.indices):
            raise ValueError("Выберите одну или несколько разных аудиодорожек.")
        if any(type(i) is not int or i < 0 for i in self.indices):
            raise ValueError("Неверные номера дорожек.")
        if self.model not in {"large-v3-turbo", "medium", "large-v3"}:
            raise ValueError("Неизвестная модель.")
        if self.device not in {"cuda", "cpu"} or self.compute not in (
            {"float16", "int8_float16"} if self.device == "cuda" else {"float32", "int8"}
        ):
            raise ValueError("Неизвестный режим качества устройства.")
        if any(index not in self.indices or len(label) > 200 for index, label in self.roles):
            raise ValueError("Неверные подписи выбранных дорожек.")


@dataclass(frozen=True)
class DesktopRecord:
    id: UUID
    media: MediaInfo
    job_id: UUID | None = None
    status: str = "IMPORTED"
    model: str = ""
    progress: float = 0
    elapsed_ms: int = 0
    error: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    roles: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class DesktopEvent:
    kind: str
    value: Any = None
    record_id: UUID | None = None


class DesktopBackend(Protocol):
    def execute(self, command: str, payload: Any = None) -> list[DesktopEvent]: ...
    def poll(self) -> list[DesktopEvent]: ...
    def close(self) -> None: ...


def available_actions(status: str, *, queued: bool = False) -> tuple[bool, bool, bool, bool]:
    """Start/pause/resume/cancel availability follows persisted FSM + pending FIFO."""
    start = status in {"IMPORTED", JobStatus.COMPLETED, JobStatus.CANCELLED}
    pause = status == JobStatus.PROCESSING and not queued
    resume = status in {JobStatus.PAUSED, JobStatus.INTERRUPTED, JobStatus.FAILED} and not queued
    cancel = queued or status in {
        JobStatus.PENDING,
        JobStatus.ANALYZING,
        JobStatus.PROCESSING,
        JobStatus.PAUSED,
        JobStatus.INTERRUPTED,
        JobStatus.FAILED,
    }
    return start and not queued, pause, resume, cancel
