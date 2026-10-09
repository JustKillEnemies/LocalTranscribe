"""Pure types for bounded PCM decoding on the normalized media timeline."""

from dataclasses import dataclass

PCM_SAMPLE_RATE = 16_000
PCM_CHANNELS = 1
PCM_SAMPLE_WIDTH = 2
PCM_BYTES_PER_SECOND = PCM_SAMPLE_RATE * PCM_CHANNELS * PCM_SAMPLE_WIDTH
DEFAULT_WORK_RANGE_MS = 5 * 60 * 1000
MAX_WORK_RANGE_MS = 15 * 60 * 1000


@dataclass(frozen=True)
class DecodeRange:
    """Absolute half-open interval on the normalized media timeline."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("Decode range must use integer milliseconds")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("Decode range must be a positive interval")
        if self.end_ms - self.start_ms > MAX_WORK_RANGE_MS:
            raise ValueError("Decode range exceeds the 15-minute safety limit")


@dataclass(frozen=True)
class AudioBlock:
    """One aligned s16le, mono, 16 kHz PCM block with absolute timestamps."""

    start_ms: int
    end_ms: int
    pcm: bytes

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("Audio block has an invalid interval")
        if not self.pcm or len(self.pcm) % PCM_SAMPLE_WIDTH:
            raise ValueError("Audio block must contain complete PCM samples")

    @property
    def sample_count(self) -> int:
        return len(self.pcm) // PCM_SAMPLE_WIDTH
