"""Job states and transitions from the project specification."""

from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    PROCESSING = "PROCESSING"
    PAUSED = "PAUSED"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    """Allow retries/resume explicitly; terminal success/cancellation cannot restart."""
    allowed = {
        JobStatus.PENDING: {JobStatus.ANALYZING, JobStatus.CANCELLED, JobStatus.FAILED},
        JobStatus.ANALYZING: {
            JobStatus.PROCESSING,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.INTERRUPTED,
        },
        JobStatus.PROCESSING: {
            JobStatus.PAUSED,
            JobStatus.INTERRUPTED,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        },
        JobStatus.PAUSED: {JobStatus.PROCESSING, JobStatus.CANCELLED, JobStatus.INTERRUPTED},
        JobStatus.INTERRUPTED: {
            JobStatus.PENDING,
            JobStatus.PROCESSING,
            JobStatus.CANCELLED,
            JobStatus.FAILED,
        },
        JobStatus.FAILED: {JobStatus.PENDING, JobStatus.CANCELLED},
        JobStatus.COMPLETED: set(),
        JobStatus.CANCELLED: set(),
    }
    if target != current and target not in allowed[current]:
        raise ValueError(f"Invalid job transition: {current} -> {target}")
