"""Pure speech-to-text result types with relative integer timestamps."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptionWord:
    start_ms: int
    end_ms: int
    text: str
    probability: float | None = None

    def __post_init__(self) -> None:
        _validate_content(self.start_ms, self.end_ms, self.text)
        if self.probability is not None and not 0 <= self.probability <= 1:
            raise ValueError("Word probability must be between 0 and 1")


@dataclass(frozen=True)
class TranscriptionSegment:
    """Recognized text relative to the beginning of one submitted PCM range."""

    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    words: tuple[TranscriptionWord, ...] = ()

    def __post_init__(self) -> None:
        _validate_content(self.start_ms, self.end_ms, self.text)
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Segment confidence must be between 0 and 1")


@dataclass(frozen=True)
class TranscriptionEngineInfo:
    model_name: str
    device: str
    compute_type: str
    language: str
    beam_size: int


def _validate_content(start_ms: int, end_ms: int, text: str) -> None:
    if type(start_ms) is not int or type(end_ms) is not int:
        raise TypeError("Timestamps must use integer milliseconds")
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Item must have a positive relative interval")
    if not text.strip():
        raise ValueError("Text must not be blank")
