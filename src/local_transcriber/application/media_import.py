"""Media inspection and persistence use case."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from local_transcriber.domain.media import MediaInfo


class MediaInspectorPort(Protocol):
    def inspect(self, source: Path) -> MediaInfo: ...


class MediaRepositoryPort(Protocol):
    def save(self, media: MediaInfo) -> tuple[UUID, bool]: ...


@dataclass(frozen=True)
class ImportResult:
    media_id: UUID
    created: bool
    media: MediaInfo


class ImportMedia:
    def __init__(self, inspector: MediaInspectorPort, repository: MediaRepositoryPort) -> None:
        self._inspector = inspector
        self._repository = repository

    def execute(self, path: Path) -> ImportResult:
        media = self._inspector.inspect(path)
        identifier, created = self._repository.save(media)
        return ImportResult(identifier, created, media)
