"""Step 05 bounded decoder unit tests and real FFmpeg integration."""

import io
import os
import shutil
import subprocess
from array import array
from pathlib import Path
from threading import Event
from typing import Any

import pytest

import local_transcriber.infrastructure.ffmpeg_decoder as decoder_module
from local_transcriber.domain.audio import AudioBlock, DecodeRange
from local_transcriber.infrastructure.ffmpeg_decoder import (
    FFmpegMediaDecoder,
    MediaDecodeCancelled,
    MediaDecodeError,
)


class _FakeProcess:
    def __init__(self, output: bytes, return_code: int) -> None:
        self.stdout = io.BytesIO(output)
        self.returncode: int | None = None
        self._final_return_code = return_code

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = self._final_return_code
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = self._final_return_code

    def kill(self) -> None:
        self.returncode = self._final_return_code


def _fake_decoder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: bytes,
    return_code: int,
) -> tuple[FFmpegMediaDecoder, Path]:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"media")
    monkeypatch.setattr(shutil, "which", lambda _value: "C:/tools/ffmpeg.exe")
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: _FakeProcess(output, return_code),
    )
    return FFmpegMediaDecoder("ffmpeg", block_ms=20), source


def test_decode_rejects_nonzero_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    decoder, source = _fake_decoder(tmp_path, monkeypatch, b"", 7)
    with decoder.decode(source, stream_index=8, decode_range=DecodeRange(0, 100)) as blocks:
        with pytest.raises(MediaDecodeError, match="выбранную аудиодорожку"):
            list(blocks)


def test_decode_rejects_truncated_pcm_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decoder, source = _fake_decoder(tmp_path, monkeypatch, b"\x00", 0)
    with decoder.decode(source, stream_index=0, decode_range=DecodeRange(0, 100)) as blocks:
        with pytest.raises(MediaDecodeError, match="усечённый PCM"):
            list(blocks)


def test_decode_range_and_buffer_limits_are_enforced() -> None:
    with pytest.raises(ValueError, match="15-minute"):
        DecodeRange(0, 900_001)
    with pytest.raises(ValueError, match="positive interval"):
        DecodeRange(10, 10)
    decoder = FFmpegMediaDecoder("ffmpeg", block_ms=100, queue_capacity=2)
    assert decoder.block_bytes == 3200
    assert decoder.buffered_pcm_limit == 9600


def test_range_before_stream_start_is_empty_without_child(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"media")
    decoder = FFmpegMediaDecoder("definitely-not-needed")
    with decoder.decode(
        source,
        stream_index=0,
        decode_range=DecodeRange(0, 500),
        stream_start_ms=1000,
    ) as blocks:
        assert list(blocks) == []


def test_missing_source_has_safe_diagnostic(tmp_path: Path) -> None:
    decoder = FFmpegMediaDecoder("ffmpeg")
    with pytest.raises(MediaDecodeError, match="недоступен"):
        with decoder.decode(
            tmp_path / "missing.mkv", stream_index=0, decode_range=DecodeRange(0, 100)
        ):
            pass


def test_inactivity_timeout_stops_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    decoder, source = _fake_decoder(tmp_path, monkeypatch, b"", 0)
    decoder.inactivity_timeout = 0.02
    monkeypatch.setattr(decoder_module, "_read_stdout", lambda *_args: None)
    with decoder.decode(source, stream_index=0, decode_range=DecodeRange(0, 100)) as blocks:
        with pytest.raises(MediaDecodeError, match="тайм-аут"):
            list(blocks)


def _real_ffmpeg() -> str | None:
    configured = os.environ.get("LOCAL_TRANSCRIBER_FFMPEG_PATH", "ffmpeg")
    executable = shutil.which(configured)
    if executable is None and os.environ.get("PYTEST_REQUIRE_FFMPEG") == "1":
        pytest.fail("PYTEST_REQUIRE_FFMPEG=1 but real FFmpeg is unavailable")
    return executable


def _make_two_track_media(ffmpeg: str, path: Path, *, duration: int = 3) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-itsoffset",
            "1",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=880:sample_rate=44100:duration={max(1, duration - 1)}",
            "-map",
            "0:a",
            "-map",
            "1:a",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(path),
        ],
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        shell=False,
    )


def _frequency(blocks: list[AudioBlock]) -> float:
    samples = array("h")
    for block in blocks:
        samples.frombytes(block.pcm)
    if os.sys.byteorder != "little":
        samples.byteswap()
    crossings = sum(a <= 0 < b for a, b in zip(samples, samples[1:], strict=False))
    return crossings * 16_000 / len(samples)


@pytest.mark.integration
def test_real_ffmpeg_keeps_tracks_separate_and_absolute_timeline(tmp_path: Path) -> None:
    ffmpeg = _real_ffmpeg()
    if ffmpeg is None:
        pytest.skip("real FFmpeg is unavailable")
    media = tmp_path / "two tracks.mkv"
    _make_two_track_media(ffmpeg, media)
    decoder = FFmpegMediaDecoder(ffmpeg, block_ms=100)

    decoded: list[list[AudioBlock]] = []
    for stream_index, stream_start_ms in ((0, 0), (1, 1000)):
        with decoder.decode(
            media,
            stream_index=stream_index,
            decode_range=DecodeRange(1000, 1500),
            stream_start_ms=stream_start_ms,
        ) as blocks:
            decoded.append(list(blocks))

    frequencies = [_frequency(blocks) for blocks in decoded]
    assert frequencies[0] == pytest.approx(440, abs=3)
    assert frequencies[1] == pytest.approx(880, abs=3)
    for blocks in decoded:
        assert sum(len(block.pcm) for block in blocks) == pytest.approx(16_000, abs=32)
        assert blocks[0].start_ms == 1000
        assert blocks[-1].end_ms in {1499, 1500}
        assert all(len(block.pcm) % 2 == 0 for block in blocks)


@pytest.mark.integration
def test_nonexistent_real_track_is_an_error(tmp_path: Path) -> None:
    ffmpeg = _real_ffmpeg()
    if ffmpeg is None:
        pytest.skip("real FFmpeg is unavailable")
    media = tmp_path / "tracks.mkv"
    _make_two_track_media(ffmpeg, media)
    original = media.read_bytes()
    decoder = FFmpegMediaDecoder(ffmpeg)
    with decoder.decode(media, stream_index=99, decode_range=DecodeRange(0, 500)) as blocks:
        with pytest.raises(MediaDecodeError, match="выбранную аудиодорожку"):
            list(blocks)
    assert media.read_bytes() == original


@pytest.mark.integration
def test_cancellation_reaps_real_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ffmpeg = _real_ffmpeg()
    if ffmpeg is None:
        pytest.skip("real FFmpeg is unavailable")
    media = tmp_path / "long.mkv"
    _make_two_track_media(ffmpeg, media, duration=20)
    real_popen = subprocess.Popen
    children: list[subprocess.Popen[bytes]] = []

    def capturing_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", capturing_popen)
    cancel = Event()
    decoder = FFmpegMediaDecoder(ffmpeg, block_ms=20, queue_capacity=1)
    with pytest.raises(MediaDecodeCancelled):
        with decoder.decode(
            media,
            stream_index=0,
            decode_range=DecodeRange(0, 15_000),
            cancel=cancel,
        ) as blocks:
            next(blocks)
            cancel.set()
            next(blocks)
    assert len(children) == 1
    assert children[0].poll() is not None
