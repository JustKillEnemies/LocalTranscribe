"""Bounded FFmpeg adapter for one selected audio stream."""

import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Final

from local_transcriber.application.media_decode import CancellationToken
from local_transcriber.domain.audio import (
    PCM_SAMPLE_RATE,
    PCM_SAMPLE_WIDTH,
    AudioBlock,
    DecodeRange,
)

_EOF: Final = object()


class MediaDecodeError(RuntimeError):
    """Safe diagnostic for an unavailable source, stream, or failed decoder."""


class MediaDecodeCancelled(MediaDecodeError):
    """Raised after requested cancellation and complete child cleanup."""


class _ReaderFailure:
    def __init__(self, error: BaseException) -> None:
        self.error = error


class FFmpegMediaDecoder:
    """Decode s16le blocks through a bounded producer queue and a managed child."""

    def __init__(
        self,
        ffmpeg_path: str,
        *,
        block_ms: int = 1000,
        queue_capacity: int = 2,
        inactivity_timeout: float = 30.0,
        shutdown_timeout: float = 2.0,
    ) -> None:
        if not 20 <= block_ms <= 5000:
            raise ValueError("block_ms must be between 20 and 5000")
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be positive")
        if inactivity_timeout <= 0 or shutdown_timeout <= 0:
            raise ValueError("timeouts must be positive")
        samples = PCM_SAMPLE_RATE * block_ms // 1000
        if samples < 1:
            raise ValueError("block_ms is too small for the PCM sample rate")
        self._ffmpeg_path = ffmpeg_path
        self.block_bytes = samples * PCM_SAMPLE_WIDTH
        self.queue_capacity = queue_capacity
        self.inactivity_timeout = inactivity_timeout
        self.shutdown_timeout = shutdown_timeout

    @property
    def buffered_pcm_limit(self) -> int:
        """Maximum Python-side PCM retained by the producer queue plus current block."""
        return self.block_bytes * (self.queue_capacity + 1)

    @contextmanager
    def decode(
        self,
        source: Path,
        *,
        stream_index: int,
        decode_range: DecodeRange,
        stream_start_ms: int = 0,
        cancel: CancellationToken | None = None,
    ) -> Iterator[Iterator[AudioBlock]]:
        path = self._source(source)
        if type(stream_index) is not int or stream_index < 0:
            raise ValueError("stream_index must be a non-negative integer")
        if type(stream_start_ms) is not int or stream_start_ms < 0:
            raise ValueError("stream_start_ms must be a non-negative integer")

        effective_start = max(decode_range.start_ms, stream_start_ms)
        effective_end = decode_range.end_ms
        if effective_start >= effective_end:
            yield iter(())
            return

        executable = self._executable()
        duration_ms = effective_end - effective_start
        arguments = [
            executable,
            "-v",
            "error",
            "-nostdin",
            "-ss",
            _seconds(effective_start),
            "-i",
            str(path),
            "-map",
            f"0:{stream_index}",
            "-t",
            _seconds(duration_ms),
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            "1",
            "-ar",
            str(PCM_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            "-f",
            "s16le",
            "pipe:1",
        ]
        with tempfile.TemporaryFile() as stderr:
            try:
                process = subprocess.Popen(
                    arguments,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except OSError:
                raise MediaDecodeError("Не удалось запустить FFmpeg.") from None
            if process.stdout is None:
                self._stop_process(process)
                raise MediaDecodeError("FFmpeg не предоставил аудиопоток.")
            stop = threading.Event()
            output: queue.Queue[bytes | object | _ReaderFailure] = queue.Queue(
                maxsize=self.queue_capacity
            )
            reader = threading.Thread(
                target=_read_stdout,
                args=(process.stdout, self.block_bytes, output, stop),
                name="ffmpeg-pcm-reader",
                daemon=True,
            )
            reader.start()
            blocks = self._blocks(
                process,
                output,
                effective_start,
                effective_end,
                cancel,
            )
            try:
                yield blocks
            finally:
                blocks.close()
                stop.set()
                self._stop_process(process)
                process.stdout.close()
                reader.join(timeout=self.shutdown_timeout)

    def _blocks(
        self,
        process: subprocess.Popen[bytes],
        output: queue.Queue[bytes | object | _ReaderFailure],
        timeline_start_ms: int,
        timeline_end_ms: int,
        cancel: CancellationToken | None,
    ) -> Iterator[AudioBlock]:
        emitted_samples = 0
        pending = bytearray()
        deadline = time.monotonic() + self.inactivity_timeout
        while True:
            if cancel is not None and cancel.is_set():
                raise MediaDecodeCancelled("Декодирование отменено.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MediaDecodeError("FFmpeg не выдаёт данные: истёк тайм-аут.")
            try:
                item = output.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            deadline = time.monotonic() + self.inactivity_timeout
            if isinstance(item, _ReaderFailure):
                raise MediaDecodeError("Не удалось прочитать вывод FFmpeg.") from item.error
            if item is _EOF:
                break
            pending.extend(item)
            complete = len(pending) - len(pending) % PCM_SAMPLE_WIDTH
            while complete >= self.block_bytes:
                pcm = bytes(pending[: self.block_bytes])
                del pending[: self.block_bytes]
                complete -= self.block_bytes
                yield _audio_block(pcm, timeline_start_ms, emitted_samples, timeline_end_ms)
                emitted_samples += len(pcm) // PCM_SAMPLE_WIDTH

        if len(pending) % PCM_SAMPLE_WIDTH:
            raise MediaDecodeError("FFmpeg вернул усечённый PCM-сэмпл.")
        if pending:
            pcm = bytes(pending)
            yield _audio_block(pcm, timeline_start_ms, emitted_samples, timeline_end_ms)
        try:
            return_code = process.wait(timeout=self.shutdown_timeout)
        except subprocess.TimeoutExpired:
            raise MediaDecodeError("FFmpeg не завершился после окончания потока.") from None
        if return_code != 0:
            raise MediaDecodeError("FFmpeg не смог декодировать выбранную аудиодорожку.")

    def _source(self, source: Path) -> Path:
        try:
            path = source.expanduser().resolve(strict=True)
        except OSError:
            raise MediaDecodeError("Исходный медиафайл недоступен.") from None
        if not path.is_file():
            raise MediaDecodeError("Исходный путь не является файлом.")
        return path

    def _executable(self) -> str:
        if os.name == "nt" and Path(self._ffmpeg_path).suffix.lower() in {
            ".bat",
            ".cmd",
            ".ps1",
        }:
            raise MediaDecodeError("FFmpeg должен быть исполняемым файлом.")
        executable = shutil.which(self._ffmpeg_path)
        if executable is None:
            raise MediaDecodeError("FFmpeg не найден. Укажите LOCAL_TRANSCRIBER_FFMPEG_PATH.")
        return executable

    def _stop_process(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self.shutdown_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _read_stdout(
    stdout: BinaryIO,
    block_bytes: int,
    output: queue.Queue[bytes | object | _ReaderFailure],
    stop: threading.Event,
) -> None:
    try:
        while not stop.is_set():
            data = stdout.read(block_bytes)
            if not data:
                _bounded_put(output, _EOF, stop)
                return
            if not _bounded_put(output, data, stop):
                return
    except BaseException as error:
        _bounded_put(output, _ReaderFailure(error), stop)


def _bounded_put(
    output: queue.Queue[bytes | object | _ReaderFailure],
    item: bytes | object | _ReaderFailure,
    stop: threading.Event,
) -> bool:
    while not stop.is_set():
        try:
            output.put(item, timeout=0.05)
            return True
        except queue.Full:
            continue
    return False


def _seconds(milliseconds: int) -> str:
    return f"{milliseconds // 1000}.{milliseconds % 1000:03d}"


def _audio_block(
    pcm: bytes, timeline_start_ms: int, sample_offset: int, timeline_end_ms: int
) -> AudioBlock:
    start_ms = timeline_start_ms + sample_offset * 1000 // PCM_SAMPLE_RATE
    sample_end = sample_offset + len(pcm) // PCM_SAMPLE_WIDTH
    end_ms = min(
        timeline_end_ms,
        max(start_ms + 1, timeline_start_ms + sample_end * 1000 // PCM_SAMPLE_RATE),
    )
    return AudioBlock(start_ms, end_ms, pcm)
