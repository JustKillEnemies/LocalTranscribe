"""Compact pipeline integration using explicit test doubles, no fake production APIs."""

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from local_transcriber.application.pipeline import (
    PipelineConfig,
    PipelineError,
    PipelineRun,
    PipelineStream,
    StoredSegment,
    TranscriptionPipeline,
    is_duplicate,
    owned_segments,
)
from local_transcriber.domain.audio import AudioBlock
from local_transcriber.domain.media import AudioStreamInfo, MediaInfo
from local_transcriber.domain.speech import SpeechChunk
from local_transcriber.domain.transcription import (
    TranscriptionEngineInfo,
    TranscriptionSegment,
    TranscriptionWord,
)


class Decoder:
    def __init__(self):
        self.calls = []
        self.active = 0

    @contextmanager
    def decode(self, path, *, stream_index, decode_range, stream_start_ms=0, cancel=None):
        self.calls.append((stream_index, decode_range))
        self.active += 1
        try:
            # Sample small synthetic PCM at logical timestamps, no allocation of 25-min audio.
            yield iter([AudioBlock(decode_range.start_ms, decode_range.end_ms, b"\0\0" * 512)])
        finally:
            self.active -= 1


class Segmenter:
    def segment(self, blocks):
        for item in blocks:
            yield SpeechChunk(item.start_ms, item.end_ms, item.start_ms, item.end_ms, item.pcm)


class Recognizer:
    info = TranscriptionEngineInfo("medium", "cpu", "float32", "ru", 5)

    def __init__(self):
        self.calls = 0
        self.fail_on = None

    def transcribe(self, pcm):
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("private error")
        return (
            TranscriptionSegment(
                2000, 3000, " Повтор", words=(TranscriptionWord(2000, 3000, " Повтор", 0.9),)
            ),
        )


class MemoryStore:
    def __init__(self):
        self.run = PipelineRun(uuid4(), (PipelineStream(uuid4(), 1, 0),))
        self.signature = None
        self.planned = {}
        self.saved = {}
        self.completed = False
        self.failures = []

    def prepare(self, media, indices, parameters, resume):
        if self.signature is None:
            self.signature = parameters
        elif self.signature != parameters:
            raise PipelineError("Fingerprint или параметры изменились")
        return replace(self.run, completed=self.completed)

    def plan(self, job, stream, index, start, end):
        self.planned[index] = (start, end)

    def ready(self, job, stream, index):
        return index in self.saved

    def begin(self, job):
        pass

    def save(self, job, stream, index, start, end, segments):
        assert index not in self.saved
        self.saved[index] = list(segments)

    def tail(self, job, stream, before):
        return [item for group in self.saved.values() for item in group if item.end_ms <= before][
            -32:
        ]

    def progress(self, job):
        return len(self.planned), len(self.saved)

    def finish(self, job):
        assert len(self.planned) == len(self.saved)
        self.completed = True

    def fail(self, job, stream, index, message):
        self.failures.append(index)


def media(duration=25 * 60 * 1000):
    return MediaInfo(
        Path("synthetic.mkv"),
        "synthetic.mkv",
        100,
        duration,
        "mkv",
        "fixture:v1",
        (AudioStreamInfo(1, "pcm", 16000, 1),),
    )


def test_25min_crash_after_two_chunks_resume_and_double_run():
    store, decoder, engine = MemoryStore(), Decoder(), Recognizer()
    engine.fail_on = 3
    pipeline = TranscriptionPipeline(decoder, Segmenter(), engine, store, lambda: "fixture:v1")
    with pytest.raises(PipelineError, match="подтверждённые результаты"):
        pipeline.execute(media(), (1,))
    assert list(store.saved) == [0, 1]
    assert decoder.active == 0
    engine.fail_on = None
    job = pipeline.execute(media(), (1,), resume=store.run.id)
    assert len(store.saved) == 5
    assert all(len(group) == 1 for group in store.saved.values())
    assert decoder.calls[1][1].start_ms == 299_000
    count = len(decoder.calls)
    assert pipeline.execute(media(), (1,), resume=job) == job
    assert len(decoder.calls) == count
    assert decoder.active == 0


@pytest.mark.parametrize("change", ["fingerprint", "parameters"])
def test_resume_mismatch_preserves_confirmed_results(change):
    store = MemoryStore()
    pipeline = TranscriptionPipeline(
        Decoder(), Segmenter(), Recognizer(), store, lambda: "fixture:v1"
    )
    pipeline.execute(media(), (1,))
    before = dict(store.saved)
    if change == "fingerprint":
        pipeline.fingerprint = lambda: "changed"
    else:
        pipeline.parameters = {"beam": 1}
    with pytest.raises(PipelineError):
        pipeline.execute(media(), (1,), resume=store.run.id)
    assert store.saved == before


def test_boundary_dedup_keeps_genuine_repeated_words():
    a = StoredSegment(1000, 1400, "Да!")
    assert is_duplicate(StoredSegment(1010, 1410, "да"), a)
    assert not is_duplicate(StoredSegment(1400, 1800, "да"), a)
    assert not is_duplicate(StoredSegment(1010, 1410, "нет"), a)
    speech = SpeechChunk(29_800, 30_600, 30_000, 30_400, b"\0\0" * 100)
    words = (TranscriptionWord(50, 150, " контекст"), TranscriptionWord(250, 350, " да"))
    result = owned_segments(
        (TranscriptionSegment(50, 350, "контекст да", words=words),), speech, 30_000, 60_000
    )
    assert [x.text for x in result] == [" да"]
    assert result[0].start_ms == 30_050


def test_limits_and_unknown_track_do_not_start_decoder():
    with pytest.raises(ValueError):
        PipelineConfig(chunk_ms=30_000)
    decoder = Decoder()
    pipeline = TranscriptionPipeline(
        decoder, Segmenter(), Recognizer(), MemoryStore(), lambda: "fixture:v1"
    )
    with pytest.raises(PipelineError, match="отсутствует"):
        pipeline.execute(media(), (9,))
    assert decoder.calls == []


def test_abrupt_interrupt_keeps_two_checkpoints_and_closes_decoder():
    class Interrupted(BaseException):
        pass

    class InterruptingRecognizer(Recognizer):
        def transcribe(self, pcm):
            if self.calls == 2:
                raise Interrupted()
            return super().transcribe(pcm)

    store, decoder, engine = MemoryStore(), Decoder(), InterruptingRecognizer()
    pipeline = TranscriptionPipeline(decoder, Segmenter(), engine, store, lambda: "fixture:v1")
    with pytest.raises(Interrupted):
        pipeline.execute(media(), (1,))
    assert len(store.saved) == 2
    assert decoder.active == 0
    resumed = TranscriptionPipeline(decoder, Segmenter(), Recognizer(), store, lambda: "fixture:v1")
    resumed.execute(media(), (1,), resume=store.run.id)
    assert len(store.saved) == 5


def test_transcribe_cli_routes_explicit_streams_and_resume(monkeypatch):
    from local_transcriber.__main__ import main

    called = {}
    job = uuid4()

    def run(path, **kwargs):
        called.update(path=path, **kwargs)
        return job

    monkeypatch.setattr("local_transcriber.infrastructure.transcribe_cli.run_transcription", run)
    assert (
        main(
            [
                "transcribe",
                "source.mkv",
                "--stream-index",
                "1",
                "--stream-index",
                "2",
                "--resume",
                str(job),
            ]
        )
        == 0
    )
    assert called["indices"] == (1, 2)
    assert called["resume"] == job
    assert called["chunk_ms"] == 300_000


def test_logical_15minute_chunk_decodes_bounded_subranges():
    decoder = Decoder()
    pipeline = TranscriptionPipeline(
        decoder,
        Segmenter(),
        Recognizer(),
        MemoryStore(),
        lambda: "fixture:v1",
        config=PipelineConfig(chunk_ms=900_000),
    )
    pipeline.execute(media(1_800_000), (1,))
    assert all(x.end_ms - x.start_ms <= 900_000 for _, x in decoder.calls)
