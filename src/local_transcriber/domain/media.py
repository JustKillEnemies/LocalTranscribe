"""Pure media metadata exchanged between inspection and persistence."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioStreamInfo:
    stream_index: int
    codec: str
    sample_rate: int
    channels: int
    language: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    filename: str
    size_bytes: int
    duration_ms: int
    container: str
    fingerprint: str
    audio_streams: tuple[AudioStreamInfo, ...]
