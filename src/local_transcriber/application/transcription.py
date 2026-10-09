"""Application port for local speech recognition."""

from typing import Protocol

from local_transcriber.domain.transcription import TranscriptionEngineInfo, TranscriptionSegment


class TranscriptionEngine(Protocol):
    @property
    def info(self) -> TranscriptionEngineInfo: ...

    def transcribe(self, pcm_s16le: bytes) -> tuple[TranscriptionSegment, ...]:
        """Consume one bounded mono 16 kHz PCM range and return relative segments."""
        ...
