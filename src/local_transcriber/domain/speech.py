"""Speech PCM with source timestamps and non-overlapping ownership intervals."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeechChunk:
    start_ms: int
    end_ms: int
    core_start_ms: int
    core_end_ms: int
    pcm: bytes

    def __post_init__(self) -> None:
        times = (self.start_ms, self.end_ms, self.core_start_ms, self.core_end_ms)
        if any(type(value) is not int for value in times):
            raise TypeError("Speech timestamps must be integer milliseconds")
        if not 0 <= self.start_ms <= self.core_start_ms < self.core_end_ms <= self.end_ms:
            raise ValueError("Invalid speech/ownership interval")
        if not self.pcm or len(self.pcm) % 2:
            raise ValueError("Speech PCM must contain complete s16le samples")
