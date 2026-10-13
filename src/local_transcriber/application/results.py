"""Typed requests for saved results; no Qt, SQL or recognition dependencies."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from local_transcriber.application.export import ExportOptions


@dataclass(frozen=True)
class ResultRequest:
    request_id: UUID
    job_id: UUID
    base_id: UUID | None = None
    content: str = ""
    destination: Path | None = None
    options: ExportOptions | None = None
