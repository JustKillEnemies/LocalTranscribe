"""CPU Silero ONNX inference and bounded streaming speech segmentation."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from local_transcriber.domain.audio import AudioBlock
from local_transcriber.domain.speech import SpeechChunk

if TYPE_CHECKING:
    from local_transcriber.infrastructure.settings import AppSettings

FRAME_SAMPLES = 512
SAMPLES_PER_MS = 16
MAX_INPUT_BLOCK_BYTES = 160_000


class SegmentationError(RuntimeError):
    """Safe diagnostic; source audio is never changed."""


@dataclass(frozen=True)
class SegmentationConfig:
    enabled: bool = True
    threshold: float = 0.5
    min_silence_ms: int = 500
    padding_ms: int = 200
    max_speech_ms: int = 30_000

    @classmethod
    def from_settings(cls, settings: AppSettings) -> SegmentationConfig:
        return cls(
            enabled=settings.vad_enabled,
            threshold=settings.vad_threshold,
            min_silence_ms=settings.vad_min_silence_ms,
            padding_ms=settings.vad_padding_ms,
            max_speech_ms=settings.vad_max_speech_ms,
        )

    def __post_init__(self) -> None:
        if not math.isfinite(self.threshold) or not 0 < self.threshold < 1:
            raise ValueError("VAD threshold must be between 0 and 1")
        for value in (self.min_silence_ms, self.padding_ms, self.max_speech_ms):
            if type(value) is not int:
                raise TypeError("VAD durations must use integer milliseconds")
        if not 32 <= self.min_silence_ms <= 5000 or not 0 <= self.padding_ms <= 1000:
            raise ValueError("Invalid VAD silence or padding")
        if not 1000 <= self.max_speech_ms <= 60_000:
            raise ValueError("Speech core limit must be 1–60 seconds")


class _SileroScorer:
    """State belongs to one stream; no cached mutable model state shared across calls."""

    def __init__(self) -> None:
        try:
            import numpy as np
            import onnxruntime as ort
            from faster_whisper.utils import get_assets_path

            path = Path(get_assets_path()) / "silero_vad_v6.onnx"
            options = ort.SessionOptions()
            options.intra_op_num_threads = options.inter_op_num_threads = 1
            self.session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
            self.h = np.zeros((1, 1, 128), dtype=np.float32)
            self.c = np.zeros((1, 1, 128), dtype=np.float32)
            self.context = np.zeros(64, dtype=np.float32)
        except Exception:
            raise SegmentationError("Локальная Silero ONNX-модель недоступна.") from None

    def __call__(self, pcm: bytes) -> float:
        import numpy as np

        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if len(audio) < FRAME_SAMPLES:
            audio = np.pad(audio, (0, FRAME_SAMPLES - len(audio)))
        features = np.concatenate((self.context, audio))[None, :]
        try:
            output, self.h, self.c = self.session.run(
                None, {"input": features, "h": self.h, "c": self.c}
            )
        except Exception:
            raise SegmentationError("Silero VAD не смог обработать аудио.") from None
        self.context = audio[-64:].copy()
        return float(output.reshape(-1)[0])


class SileroSpeechSegmenter:
    def __init__(
        self,
        config: SegmentationConfig | None = None,
        *,
        scorer_factory: Callable[[], Callable[[bytes], float]] | None = None,
    ) -> None:
        self.config = config or SegmentationConfig()
        self._scorer_factory = scorer_factory or _SileroScorer

    @property
    def working_pcm_limit(self) -> int:
        cfg = self.config
        return (cfg.max_speech_ms + cfg.min_silence_ms + 2 * cfg.padding_ms + 64) * 32

    def segment(self, blocks: Iterable[AudioBlock]) -> Iterator[SpeechChunk]:
        cfg = self.config
        scorer = self._scorer_factory() if cfg.enabled else None
        pad = cfg.padding_ms * SAMPLES_PER_MS
        silence = cfg.min_silence_ms * SAMPLES_PER_MS
        maximum = cfg.max_speech_ms * SAMPLES_PER_MS
        buffer = bytearray()
        buffer_start = 0
        cursor = 0
        core_start: int | None = None
        silence_start: int | None = None
        origin_ms: int | None = None

        def chunk(start: int, end: int) -> SpeechChunk:
            left = max(buffer_start, start - pad)
            right = min(cursor, end + pad)
            return SpeechChunk(
                origin_ms + left // 16,
                origin_ms + (right + 15) // 16,
                origin_ms + start // 16,
                origin_ms + (end + 15) // 16,
                bytes(buffer[(left - buffer_start) * 2 : (right - buffer_start) * 2]),
            )

        for frame_origin_ms, pcm in _frames(blocks):
            if origin_ms is None:
                origin_ms = frame_origin_ms
            frame_start = cursor
            buffer.extend(pcm)
            cursor += len(pcm) // 2
            probability = scorer(pcm) if scorer is not None else 1.0
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise SegmentationError("VAD вернул некорректную вероятность речи.")
            positive = probability >= cfg.threshold
            negative = probability < max(0.01, cfg.threshold - 0.15)
            if core_start is None and positive:
                core_start = frame_start
            if core_start is not None:
                if positive:
                    silence_start = None
                elif negative and silence_start is None:
                    silence_start = frame_start
                if silence_start is not None and cursor - silence_start >= max(silence, pad):
                    if silence_start > core_start:
                        yield chunk(core_start, silence_start)
                    core_start = None
                    silence_start = None
                elif cursor - core_start >= maximum + pad:
                    boundary = core_start + maximum
                    yield chunk(core_start, boundary)
                    core_start = boundary
            keep_from = max(0, (core_start if core_start is not None else cursor) - pad)
            discard = max(0, keep_from - buffer_start)
            del buffer[: discard * 2]
            buffer_start += discard

        if core_start is not None:
            end = silence_start if silence_start is not None else cursor
            while end - core_start > maximum:
                yield chunk(core_start, core_start + maximum)
                core_start += maximum
            if end > core_start:
                yield chunk(core_start, end)


def _frames(blocks: Iterable[AudioBlock]) -> Iterator[tuple[int, bytes]]:
    pending = bytearray()
    origin_ms: int | None = None
    consumed_samples = 0
    for block in blocks:
        if len(block.pcm) > MAX_INPUT_BLOCK_BYTES:
            raise SegmentationError("Входной PCM-блок превышает лимит 5 секунд.")
        if origin_ms is None:
            origin_ms = block.start_ms
        expected = origin_ms + consumed_samples // 16
        if abs(block.start_ms - expected) > 1:
            raise SegmentationError("PCM-блоки имеют разрыв или повтор временной шкалы.")
        consumed_samples += len(block.pcm) // 2
        pending.extend(block.pcm)
        while len(pending) >= FRAME_SAMPLES * 2:
            frame = bytes(pending[: FRAME_SAMPLES * 2])
            del pending[: FRAME_SAMPLES * 2]
            yield origin_ms, frame
    if pending:
        yield origin_ms, bytes(pending)
