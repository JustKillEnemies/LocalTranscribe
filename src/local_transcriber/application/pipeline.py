"""Sequential bounded decode/VAD/STT pipeline with durable logical checkpoints."""

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Protocol
from uuid import UUID

from local_transcriber.application.media_decode import MediaDecoder
from local_transcriber.application.segmentation import SpeechSegmenter
from local_transcriber.application.transcription import TranscriptionEngine
from local_transcriber.domain.audio import DecodeRange
from local_transcriber.domain.media import MediaInfo
from local_transcriber.domain.speech import SpeechChunk
from local_transcriber.domain.transcription import TranscriptionSegment


class PipelineError(RuntimeError):
    """Public pipeline failure without source paths, transcript or credentials."""


@dataclass(frozen=True)
class PipelineConfig:
    chunk_ms: int = 300_000
    overlap_ms: int = 1000
    end_ms: int | None = None

    def __post_init__(self) -> None:
        if type(self.chunk_ms) is not int or not 60_000 <= self.chunk_ms <= 900_000:
            raise ValueError("Logical chunks must be between 1 and 15 minutes")
        if type(self.overlap_ms) is not int or not 200 <= self.overlap_ms <= 5000:
            raise ValueError("Overlap must be between 200 and 5000 milliseconds")
        if self.end_ms is not None and (type(self.end_ms) is not int or self.end_ms <= 0):
            raise ValueError("end_ms must be a positive integer")


@dataclass(frozen=True)
class PipelineStream:
    id: UUID
    index: int
    start_ms: int


@dataclass(frozen=True)
class PipelineRun:
    id: UUID
    streams: tuple[PipelineStream, ...]
    completed: bool = False


@dataclass(frozen=True)
class StoredSegment:
    start_ms: int
    end_ms: int
    text: str


class PipelineStore(Protocol):
    def prepare(
        self,
        media: MediaInfo,
        indices: tuple[int, ...],
        parameters: dict[str, Any],
        resume: UUID | None,
    ) -> PipelineRun: ...
    def plan(self, job: UUID, stream: UUID, index: int, start: int, end: int) -> None: ...
    def ready(self, job: UUID, stream: UUID, index: int) -> bool: ...
    def begin(self, job: UUID) -> None: ...
    def save(
        self,
        job: UUID,
        stream: UUID,
        index: int,
        start: int,
        end: int,
        segments: Sequence[StoredSegment],
    ) -> None: ...
    def tail(self, job: UUID, stream: UUID, before_ms: int) -> Sequence[StoredSegment]: ...
    def progress(self, job: UUID) -> tuple[int, int]: ...
    def finish(self, job: UUID) -> None: ...
    def fail(self, job: UUID, stream: UUID, index: int, message: str) -> None: ...


class TranscriptionPipeline:
    def __init__(
        self,
        decoder: MediaDecoder,
        segmenter: SpeechSegmenter,
        engine: TranscriptionEngine,
        store: PipelineStore,
        fingerprint: Callable[[], str],
        *,
        config: PipelineConfig | None = None,
        parameters: dict[str, Any] | None = None,
        on_progress: Callable[[UUID, int, int], None] | None = None,
    ) -> None:
        self.decoder, self.segmenter, self.engine, self.store = decoder, segmenter, engine, store
        self.fingerprint = fingerprint
        self.config = config or PipelineConfig()
        self.parameters = parameters or {}
        self._engine_signature = asdict(engine.info)
        self.on_progress = on_progress

    def execute(
        self,
        media: MediaInfo,
        stream_indices: tuple[int, ...],
        *,
        resume: UUID | None = None,
    ) -> UUID:
        if not stream_indices or len(set(stream_indices)) != len(stream_indices):
            raise PipelineError("Выберите неповторяющиеся индексы аудиодорожек.")
        available = {item.stream_index for item in media.audio_streams}
        if not set(stream_indices) <= available:
            raise PipelineError("Выбранная аудиодорожка отсутствует.")
        duration = min(media.duration_ms, self.config.end_ms or media.duration_ms)
        if duration <= 0:
            raise PipelineError("Невозможно обработать запись нулевой длительности.")
        self._check_source(media)
        signature = {
            "pipeline_version": 1,
            "pipeline": asdict(self.config),
            "engine": self._engine_signature,
            "parameters": self.parameters,
            "stream_indices": list(stream_indices),
            "fingerprint": media.fingerprint,
            "duration_ms": media.duration_ms,
        }
        run = self.store.prepare(media, stream_indices, signature, resume)
        if run.completed:
            return run.id
        for stream in run.streams:
            for index, start in enumerate(range(0, duration, self.config.chunk_ms)):
                self.store.plan(
                    run.id, stream.id, index, start, min(start + self.config.chunk_ms, duration)
                )
        self.store.begin(run.id)
        for stream in run.streams:
            for index, start in enumerate(range(0, duration, self.config.chunk_ms)):
                end = min(start + self.config.chunk_ms, duration)
                if self.store.ready(run.id, stream.id, index):
                    continue
                try:
                    self._check_source(media)
                    results = self._process(run.id, media, stream, start, end, duration)
                    self._check_source(media)
                    self.store.save(run.id, stream.id, index, start, end, results)
                    if self.on_progress:
                        total, completed = self.store.progress(run.id)
                        self.on_progress(run.id, total, completed)
                except Exception as error:
                    message = f"Сбой {type(error).__name__}. Участок не завершён; подтверждённые результаты сохранены."
                    logging.getLogger(__name__).error(
                        "pipeline_failure job_id=%s stream=%s chunk=%s", run.id, stream.index, index
                    )
                    try:
                        self.store.fail(run.id, stream.id, index, message)
                    except Exception:
                        logging.getLogger(__name__).error(
                            "checkpoint_status_unavailable job_id=%s", run.id
                        )
                    raise PipelineError(f"Задание {run.id}: {message}") from None
        self.store.finish(run.id)
        return run.id

    def _check_source(self, media: MediaInfo) -> None:
        try:
            current = self.fingerprint()
        except OSError:
            raise PipelineError("Исходный файл недоступен; возобновление остановлено.") from None
        if current != media.fingerprint:
            raise PipelineError("Fingerprint файла изменился; возобновление заблокировано.")

    def _process(
        self,
        job_id: UUID,
        media: MediaInfo,
        stream: PipelineStream,
        start: int,
        end: int,
        duration: int,
    ) -> list[StoredSegment]:
        left, right = (
            max(0, start - self.config.overlap_ms),
            min(duration, end + self.config.overlap_ms),
        )
        # FFmpeg ranges remain <=15 minutes even for a 15-minute core plus context.
        boundaries = range(left, right, 900_000)

        def blocks():
            for offset in boundaries:
                with self.decoder.decode(
                    media.path,
                    stream_index=stream.index,
                    decode_range=DecodeRange(offset, min(offset + 900_000, right)),
                    stream_start_ms=stream.start_ms,
                ) as decoded:
                    yield from decoded

        result: list[StoredSegment] = []
        recent = list(self.store.tail(job_id, stream.id, start))
        source_blocks = blocks()
        speech_iterator = self.segmenter.segment(source_blocks)
        try:
            for speech in speech_iterator:
                if speech.core_end_ms <= start or speech.core_start_ms >= end:
                    continue
                for item in owned_segments(self.engine.transcribe(speech.pcm), speech, start, end):
                    if not any(is_duplicate(item, prior) for prior in (recent + result[-32:])):
                        result.append(item)
        finally:
            close = getattr(speech_iterator, "close", None)
            if close is not None:
                close()
            source_blocks.close()
        return [StoredSegment(max(start, x.start_ms), min(end, x.end_ms), x.text) for x in result]


def owned_segments(
    segments: Sequence[TranscriptionSegment],
    speech: SpeechChunk,
    start: int,
    end: int,
) -> list[StoredSegment]:
    left, right = max(start, speech.core_start_ms), min(end, speech.core_end_ms)
    output = []
    for segment in segments:
        units = [(word.start_ms, word.end_ms, word.text) for word in segment.words]
        if not units:
            units = [(segment.start_ms, segment.end_ms, segment.text)]
        for relative_start, relative_end, text in units:
            absolute_start = speech.start_ms + relative_start
            absolute_end = speech.start_ms + relative_end
            midpoint = (absolute_start + absolute_end) // 2
            if left <= midpoint < right:
                clipped_start, clipped_end = (
                    max(speech.start_ms, absolute_start),
                    min(speech.end_ms, absolute_end),
                )
                if clipped_end > clipped_start:
                    output.append(StoredSegment(clipped_start, clipped_end, text))
    return output


def is_duplicate(candidate: StoredSegment, previous: StoredSegment) -> bool:
    overlap = min(candidate.end_ms, previous.end_ms) - max(candidate.start_ms, previous.start_ms)
    shortest = min(candidate.end_ms - candidate.start_ms, previous.end_ms - previous.start_ms)
    if overlap <= 0 or overlap / shortest < 0.5:
        return False

    def normalize(value: str) -> str:
        return " ".join(re.findall(r"\w+", value.casefold()))

    a, b = normalize(candidate.text), normalize(previous.text)
    return bool(a and b) and SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.92
