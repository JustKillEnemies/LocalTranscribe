"""Bounded local media inspection through ffprobe; no decoding."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from local_transcriber.domain.media import AudioStreamInfo, MediaInfo

SUPPORTED_EXTENSIONS = frozenset({".mkv", ".mp4", ".mov", ".wav", ".mp3", ".m4a", ".flac", ".webm"})
FINGERPRINT_BLOCK_SIZE = 1024 * 1024
MAX_PROBE_OUTPUT = 4 * 1024 * 1024


class MediaInspectionError(RuntimeError):
    """Safe user-facing failure without raw ffprobe output."""


def _executable(value: str) -> str:
    if os.name == "nt" and Path(value).suffix.lower() in {".bat", ".cmd", ".ps1"}:
        raise MediaInspectionError("FFprobe должен быть исполняемым файлом.")
    executable = shutil.which(value)
    if executable is None:
        raise MediaInspectionError("FFprobe не найден. Укажите LOCAL_TRANSCRIBER_FFPROBE_PATH.")
    return executable


def media_fingerprint(path: Path) -> str:
    """Hash bounded samples plus size/mtime; detect changes during the read."""
    before = path.stat()
    digest = hashlib.blake2b(digest_size=32)
    digest.update(b"local-transcriber-fingerprint-v1\0")
    digest.update(str(before.st_size).encode("ascii"))
    digest.update(b"\0")
    digest.update(str(before.st_mtime_ns).encode("ascii"))
    with path.open("rb") as source:
        digest.update(source.read(FINGERPRINT_BLOCK_SIZE))
        if before.st_size > FINGERPRINT_BLOCK_SIZE:
            source.seek(max(0, before.st_size - FINGERPRINT_BLOCK_SIZE))
            digest.update(source.read(FINGERPRINT_BLOCK_SIZE))
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise MediaInspectionError("Файл изменился во время чтения; повторите импорт.")
    return f"v1:{before.st_size}:{before.st_mtime_ns}:{digest.hexdigest()}"


def _milliseconds(value: object) -> int:
    try:
        duration = Decimal(str(value))
    except InvalidOperation, ValueError:
        raise MediaInspectionError("FFprobe вернул некорректную длительность.") from None
    if not duration.is_finite() or duration < 0:
        raise MediaInspectionError("FFprobe вернул некорректную длительность.")
    return int((duration * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _positive_int(value: object, field: str) -> int:
    try:
        parsed = int(str(value))
    except TypeError, ValueError:
        raise MediaInspectionError(f"FFprobe не указал корректное поле {field}.") from None
    if parsed <= 0:
        raise MediaInspectionError(f"FFprobe не указал корректное поле {field}.")
    return parsed


def parse_probe(payload: object, path: Path, fingerprint: str) -> MediaInfo:
    """Validate saved or live ffprobe JSON into immutable metadata."""
    if not isinstance(payload, dict):
        raise MediaInspectionError("FFprobe вернул JSON неожиданной структуры.")
    format_data = payload.get("format")
    streams_data = payload.get("streams")
    if not isinstance(format_data, dict) or not isinstance(streams_data, list):
        raise MediaInspectionError("FFprobe не вернул метаданные формата и потоков.")
    format_name = format_data.get("format_name")
    if not isinstance(format_name, str) or not format_name.strip():
        raise MediaInspectionError("FFprobe не определил контейнер.")
    streams: list[AudioStreamInfo] = []
    for stream in streams_data:
        if not isinstance(stream, dict) or stream.get("codec_type") != "audio":
            continue
        index = stream.get("index")
        codec = stream.get("codec_name")
        if type(index) is not int or index < 0 or not isinstance(codec, str) or not codec:
            raise MediaInspectionError("FFprobe вернул некорректную аудиодорожку.")
        tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
        language = tags.get("language") if isinstance(tags.get("language"), str) else None
        title = tags.get("title") if isinstance(tags.get("title"), str) else None
        streams.append(
            AudioStreamInfo(
                stream_index=index,
                codec=codec,
                sample_rate=_positive_int(stream.get("sample_rate"), "sample_rate"),
                channels=_positive_int(stream.get("channels"), "channels"),
                language=language,
                title=title,
            )
        )
    if not streams:
        raise MediaInspectionError("В файле нет аудиодорожек.")
    if len({item.stream_index for item in streams}) != len(streams):
        raise MediaInspectionError("FFprobe вернул повторяющиеся индексы потоков.")
    stat = path.stat()
    return MediaInfo(
        path=path,
        filename=path.name,
        size_bytes=stat.st_size,
        duration_ms=_milliseconds(format_data.get("duration")),
        container=format_name,
        fingerprint=fingerprint,
        audio_streams=tuple(streams),
    )


class MediaInspector:
    def __init__(self, ffprobe_path: str, *, timeout: int) -> None:
        self._ffprobe_path = ffprobe_path
        self._timeout = timeout

    def inspect(self, source: Path) -> MediaInfo:
        """Inspect one supported local file without reading or decoding its contents in full."""
        try:
            path = source.expanduser().resolve(strict=True)
            if not path.is_file():
                raise MediaInspectionError("Указанный путь не является файлом.")
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise MediaInspectionError("Неподдерживаемое расширение файла.")
            fingerprint = media_fingerprint(path)
            executable = _executable(self._ffprobe_path)
            arguments = [
                executable,
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration:stream=index,codec_type,codec_name,sample_rate,channels:stream_tags=language,title",
                "-of",
                "json",
                str(path),
            ]
            with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                process = subprocess.Popen(
                    arguments,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                try:
                    process.wait(timeout=self._timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise MediaInspectionError("Истёк тайм-аут FFprobe.") from None
                if process.returncode != 0:
                    raise MediaInspectionError(
                        "FFprobe не смог прочитать файл: формат повреждён или не поддерживается."
                    )
                if stdout.tell() > MAX_PROBE_OUTPUT:
                    raise MediaInspectionError("Ответ FFprobe превышает безопасный лимит.")
                stdout.seek(0)
                try:
                    payload: Any = json.load(stdout)
                except json.JSONDecodeError, UnicodeDecodeError:
                    raise MediaInspectionError("FFprobe вернул некорректный JSON.") from None
            result = parse_probe(payload, path, fingerprint)
            if media_fingerprint(path) != fingerprint:
                raise MediaInspectionError("Файл изменился во время анализа; повторите импорт.")
            return result
        except MediaInspectionError:
            raise
        except OSError, PermissionError:
            raise MediaInspectionError("Файл недоступен для чтения.") from None
