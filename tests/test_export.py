"""Golden formats and real local atomic file failures, without recognition."""

import errno
import json
import os
import stat
import subprocess
import threading
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from local_transcriber.application.export import (
    ExportCancelled,
    ExportCollision,
    ExportDocument,
    ExportError,
    ExportFormat,
    ExportOptions,
    ExportService,
    render_export,
    timestamp,
)
from local_transcriber.application.transcript import TextVersion
from local_transcriber.domain.text import TextSegment, VersionType, aggregate_raw, make_readable
from local_transcriber.infrastructure.export_files import AtomicExportWriter

GOLDEN = Path(__file__).parent / "fixtures/export"


def document() -> ExportDocument:
    job_id = UUID(int=100)
    rows = (
        TextSegment(UUID(int=1), 0, 3_600_001, 3_602_500, " Привет, мир!", "Микрофон"),
        TextSegment(UUID(int=2), 1, 3_600_100, 3_601_800, "English PostgreSQL", "Система"),
        TextSegment(UUID(int=3), 0, 3_605_000, 3_606_000, " 42,5", "Микрофон"),
        TextSegment(UUID(int=4), 1, 3_606_100, 3_606_200, ""),
    )
    processed = make_readable(rows)
    raw = TextVersion(UUID(int=10), job_id, 1, VersionType.RAW, aggregate_raw(rows), {})
    readable = TextVersion(
        UUID(int=11), job_id, 2, VersionType.READABLE, processed.content, processed.metadata
    )
    return ExportDocument(
        {"filename": "OBS запись.mkv", "file_path": "missing-source.mkv", "duration_ms": 3_610_000},
        {"id": str(job_id), "model_name": "large-v3-turbo", "language": "ru", "parameters": {}},
        (
            {"stream_index": 0, "role_label": "Микрофон"},
            {"stream_index": 1, "role_label": "Система"},
        ),
        rows,
        raw,
        readable,
        readable,
    )


@pytest.mark.parametrize("format", list(ExportFormat))
def test_golden_formats_utf8_overlap_and_hour_timestamps(format: ExportFormat) -> None:
    saved = document()
    if format is ExportFormat.SRT:
        saved = replace(saved, selected=saved.raw)
    if format is ExportFormat.JSON:
        # A simple saved metadata object keeps the serialization golden independent of rules internals.
        saved = replace(saved, selected=replace(saved.selected, metadata={"rules_version": "1"}))
    output = "".join(render_export(saved, ExportOptions(format, timestamps=True, roles=True)))
    assert output.encode("utf-8") == (GOLDEN / f"expected.{format.value}.golden").read_bytes()
    if format is ExportFormat.JSON:
        parsed = json.loads(output)
        assert isinstance(parsed["segments"][0]["start_ms"], int)
        assert parsed["text"]["raw"] == saved.raw.content
        assert parsed["text"]["readable"] == saved.readable.content
    assert saved.raw.content == document().raw.content


def test_plain_text_roles_optional_legacy_readable_and_manual_alignment() -> None:
    saved = document()
    text = "".join(render_export(saved, ExportOptions(ExportFormat.TXT)))
    assert text == "Привет, мир!\n\n42,5.\n\nEnglish PostgreSQL.\n\n"
    legacy_metadata = {
        key: value for key, value in saved.selected.metadata.items() if key != "paragraphs"
    }
    legacy = replace(saved, selected=replace(saved.selected, metadata=legacy_metadata))
    assert "".join(render_export(legacy, ExportOptions(ExportFormat.TXT))) == text
    manual = replace(saved.selected, kind=VersionType.MANUAL, content="Мои правки\r\n42,5\r\n")
    saved = replace(saved, selected=manual)
    assert "".join(render_export(saved, ExportOptions(ExportFormat.TXT))) == manual.content
    with pytest.raises(ExportError, match="привязки"):
        "".join(render_export(saved, ExportOptions(ExportFormat.TXT, timestamps=True)))
    with pytest.raises(ExportError, match="привязки"):
        "".join(render_export(saved, ExportOptions(ExportFormat.SRT)))


def test_empty_text_and_invalid_saved_metadata() -> None:
    saved = document()
    saved = replace(saved, segments=(), selected=replace(saved.raw, content=""))
    assert "".join(render_export(saved, ExportOptions(ExportFormat.TXT))) == ""
    assert "".join(render_export(saved, ExportOptions(ExportFormat.SRT))) == ""
    assert (
        json.loads("".join(render_export(saved, ExportOptions(ExportFormat.JSON))))["segments"]
        == []
    )
    saved = document()
    with pytest.raises(ExportError, match="не соответствует"):
        "".join(
            render_export(
                replace(saved, selected=replace(saved.selected, content="changed")),
                ExportOptions(ExportFormat.TXT),
            )
        )
    with pytest.raises(ExportError, match="повреждены"):
        metadata = {"processor": "conservative-text", "rules_version": "1"}
        "".join(
            render_export(
                replace(saved, selected=replace(saved.selected, metadata=metadata)),
                ExportOptions(ExportFormat.TXT),
            )
        )


def test_timestamp_integer_ms_over_24_hours() -> None:
    assert timestamp(0, srt=True) == "00:00:00,000"
    assert timestamp(3_600_001, srt=True) == "01:00:00,001"
    assert timestamp(90_000_999) == "25:00:00.999"
    for value in (-1, 1.2, True):
        with pytest.raises(ExportError):
            timestamp(value)


def test_atomic_write_collision_overwrite_and_cyrillic_path(tmp_path: Path) -> None:
    destination = tmp_path / "Экспорт с пробелами.txt"
    writer = AtomicExportWriter()
    writer.write(destination, ("Привет", "\n"))
    assert destination.read_bytes() == "Привет\n".encode()
    with pytest.raises(ExportCollision):
        writer.write(destination, ("changed",))
    assert destination.read_bytes() == "Привет\n".encode()
    writer.write(destination, ("new",), overwrite=True)
    assert destination.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [destination]


def test_atomic_collision_race_never_replaces_user_file(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "result.txt"
    method = "rename" if os.name == "nt" else "link"
    original = getattr(os, method)

    def racing_publish(source, target):
        destination.write_bytes(b"created by user during export")
        return original(source, target)

    monkeypatch.setattr(os, method, racing_publish)
    with pytest.raises(ExportCollision):
        AtomicExportWriter().write(destination, ("our export",))
    assert destination.read_bytes() == b"created by user during export"
    assert list(tmp_path.iterdir()) == [destination]


def test_cancel_before_during_and_before_publish_preserves_destination(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "result.txt"
    destination.write_bytes(b"previous")
    cancel = threading.Event()
    cancel.set()
    writer = AtomicExportWriter()
    with pytest.raises(ExportCancelled):
        writer.write(destination, ("new",), overwrite=True, cancel=cancel)
    cancel.clear()

    def fragments():
        yield "first fragment"
        cancel.set()
        yield "second fragment"

    with pytest.raises(ExportCancelled):
        writer.write(destination, fragments(), overwrite=True, cancel=cancel)
    cancel.clear()
    sync = os.fsync

    def sync_then_cancel(descriptor):
        sync(descriptor)
        cancel.set()

    monkeypatch.setattr(os, "fsync", sync_then_cancel)
    with pytest.raises(ExportCancelled):
        writer.write(destination, ("new",), overwrite=True, cancel=cancel)
    assert destination.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize(
    "failure", [PermissionError(errno.EACCES, "denied"), OSError(errno.ENOSPC, "full")]
)
def test_disk_errors_and_permission_denied_clean_own_temp(
    tmp_path: Path, monkeypatch, failure
) -> None:
    destination = tmp_path / "old.txt"
    destination.write_bytes(b"old")

    def fail_sync(descriptor):
        raise failure

    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(ExportError):
        AtomicExportWriter().write(destination, ("new",), overwrite=True)
    assert destination.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [destination]


def test_windows_readonly_file_is_not_destroyed(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows read-only replacement behavior")
    destination = tmp_path / "readonly.txt"
    destination.write_bytes(b"old")
    destination.chmod(stat.S_IREAD)
    try:
        with pytest.raises(ExportError, match="доступа"):
            AtomicExportWriter().write(destination, ("new",), overwrite=True)
        assert destination.read_bytes() == b"old"
        assert list(tmp_path.iterdir()) == [destination]
    finally:
        destination.chmod(stat.S_IWRITE | stat.S_IREAD)


def test_keyboard_interrupt_missing_folder_and_reserved_windows_filename(tmp_path: Path) -> None:
    destination = tmp_path / "old.txt"
    destination.write_bytes(b"old")

    def interrupted():
        yield "new"
        raise KeyboardInterrupt

    writer = AtomicExportWriter()
    with pytest.raises(KeyboardInterrupt):
        writer.write(destination, interrupted(), overwrite=True)
    with pytest.raises(ExportError):
        writer.write(tmp_path / "missing" / "result.txt", ("new",))
    if os.name == "nt":
        with pytest.raises(ExportError, match="имя"):
            writer.write(tmp_path / "CON.txt", ("new",))
    assert destination.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [destination]


def test_service_source_protection_and_cancel(tmp_path: Path) -> None:
    saved = document()
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source sentinel")
    saved = replace(saved, media={**saved.media, "file_path": str(source)})

    class Source:
        def load(self, job_id, version_id=None):
            return saved

    service = ExportService(Source(), AtomicExportWriter())
    with pytest.raises(ExportError, match="Исходный"):
        service.export(saved.raw.job_id, source, ExportOptions(ExportFormat.TXT, overwrite=True))
    assert source.read_bytes() == b"source sentinel"
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ExportCancelled):
        service.export(
            saved.raw.job_id,
            tmp_path / "result.txt",
            ExportOptions(ExportFormat.TXT),
            cancel=cancel,
        )


@pytest.mark.integration
def test_srt_opens_in_real_ffprobe(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    probe = Path(
        os.environ.get(
            "LOCAL_TRANSCRIBER_FFPROBE_PATH",
            str(root / "tmp/step04-tools/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe"),
        )
    )
    if not probe.is_file():
        if os.environ.get("PYTEST_REQUIRE_FFMPEG") == "1":
            pytest.fail("Real ffprobe missing")
        pytest.skip("Real ffprobe unavailable")
    path = tmp_path / "Русские субтитры.srt"
    AtomicExportWriter().write(
        path, ((GOLDEN / "expected.srt.golden").read_text(encoding="utf-8"),)
    )
    result = subprocess.run(
        [str(probe), "-v", "error", "-f", "srt", "-i", str(path), "-show_packets", "-of", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    packets = json.loads(result.stdout)["packets"]
    assert len(packets) == 3
    assert packets[0]["pts_time"] == "3600.001000"
