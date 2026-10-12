"""Small targeted suite: synthetic scoring is not claimed as real speech detection."""

import os
from pathlib import Path

import pytest

from local_transcriber.domain.audio import AudioBlock, DecodeRange
from local_transcriber.infrastructure.ffmpeg_decoder import FFmpegMediaDecoder
from local_transcriber.infrastructure.settings import AppSettings
from local_transcriber.infrastructure.silero_segmenter import (
    SegmentationConfig,
    SegmentationError,
    SileroSpeechSegmenter,
    _SileroScorer,
)


def blocks(duration_ms: int, origin: int = 1000) -> list[AudioBlock]:
    return [
        AudioBlock(
            origin + start,
            origin + min(duration_ms, start + 1000),
            b"\x00\x00" * (min(1000, duration_ms - start) * 16),
        )
        for start in range(0, duration_ms, 1000)
    ]


@pytest.mark.parametrize("speech", [False, True])
def test_silence_or_continuous_speech_has_bounded_disjoint_cores(speech: bool) -> None:
    segmenter = SileroSpeechSegmenter(scorer_factory=lambda: lambda _: float(speech))
    chunks = list(segmenter.segment(blocks(65_000)))
    if not speech:
        assert chunks == []
        return
    assert len(chunks) == 3
    assert chunks[0].core_start_ms == 1000
    assert chunks[-1].core_end_ms == 66_000
    for left, right in zip(chunks, chunks[1:], strict=False):
        assert left.core_end_ms == right.core_start_ms
        assert left.end_ms > right.start_ms  # explicit context overlap, no core duplication
    assert all(len(item.pcm) <= segmenter.working_pcm_limit for item in chunks)


def test_boundary_short_speech_and_pauses_keep_padding_and_offsets() -> None:
    scores = iter([1.0] * 3 + [0.0] * 20 + [1.0] * 2 + [0.0] * 20 + [1.0] * 20)
    segmenter = SileroSpeechSegmenter(scorer_factory=lambda: lambda _: next(scores))
    chunks = list(segmenter.segment(blocks(2080, origin=600_000)))
    assert len(chunks) == 3
    assert chunks[0].start_ms == 600_000
    assert chunks[-1].end_ms == 602_080
    assert all(a.end_ms <= b.start_ms for a, b in zip(chunks, chunks[1:], strict=False))
    assert chunks[0].core_end_ms - chunks[0].core_start_ms == 96


def test_bypass_never_loads_model_and_covers_whole_stream() -> None:
    def forbidden():
        raise AssertionError("bypass loaded VAD")

    config = SegmentationConfig(enabled=False)
    segmenter = SileroSpeechSegmenter(config, scorer_factory=forbidden)
    chunks = list(segmenter.segment(blocks(31_000)))
    assert [(x.core_start_ms, x.core_end_ms) for x in chunks] == [(1000, 31_000), (31_000, 32_000)]


def test_discontinuous_or_invalid_probability_is_safe() -> None:
    source = blocks(2000)
    source[1] = AudioBlock(5000, 6000, source[1].pcm)
    segmenter = SileroSpeechSegmenter(scorer_factory=lambda: lambda _: 0.0)
    with pytest.raises(SegmentationError, match="разрыв"):
        list(segmenter.segment(source))
    bad = SileroSpeechSegmenter(scorer_factory=lambda: lambda _: float("nan"))
    with pytest.raises(SegmentationError, match="вероятность"):
        list(bad.segment(blocks(1000)))


def test_settings_and_validation(tmp_path) -> None:
    cfg = SegmentationConfig.from_settings(AppSettings(data_dir=tmp_path, vad_enabled=False))
    assert cfg == SegmentationConfig(enabled=False)
    with pytest.raises(ValueError):
        SegmentationConfig(threshold=1.0)


def test_missing_onnx_model_has_safe_diagnostic(monkeypatch) -> None:
    import onnxruntime

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("private model path")

    monkeypatch.setattr(onnxruntime, "InferenceSession", unavailable)
    with pytest.raises(SegmentationError, match="модель недоступна") as error:
        _SileroScorer()
    assert "private" not in str(error.value)


def test_block_boundaries_do_not_reset_vad_or_drop_partial_samples() -> None:
    stream = blocks(2081, origin=0)
    whole = AudioBlock(0, 2081, b"".join(item.pcm for item in stream))
    segmenter = SileroSpeechSegmenter(scorer_factory=lambda: lambda _: 1.0)
    assert list(segmenter.segment(stream)) == list(segmenter.segment([whole]))


@pytest.mark.integration
def test_real_silero_silence_and_partial_last_frame() -> None:
    assert list(SileroSpeechSegmenter().segment(blocks(1017))) == []


@pytest.mark.integration
def test_real_russian_fixture() -> None:
    source = os.environ.get("LOCAL_TRANSCRIBER_VAD_FIXTURE")
    if not source:
        pytest.skip("set LOCAL_TRANSCRIBER_VAD_FIXTURE to a local Russian video fixture")
    decoder = FFmpegMediaDecoder(os.environ.get("LOCAL_TRANSCRIBER_FFMPEG_PATH", "ffmpeg"))
    with decoder.decode(
        Path(source), stream_index=1, decode_range=DecodeRange(600_000, 645_000)
    ) as stream:
        chunks = list(SileroSpeechSegmenter().segment(stream))
    assert chunks
    assert all(600_000 <= item.start_ms < item.end_ms <= 645_000 for item in chunks)
    assert all(a.core_end_ms <= b.core_start_ms for a, b in zip(chunks, chunks[1:], strict=False))
