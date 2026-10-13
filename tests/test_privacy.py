"""Focused privacy/ownership regressions, with synthetic data and real Windows ACL/FFmpeg."""

import errno
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import wave
from collections import deque
from pathlib import Path
from uuid import uuid4

import pytest

from local_transcriber.application.export import ExportFormat, export_filename
from local_transcriber.application.maintenance import DeleteHistory, DeleteSession
from local_transcriber.domain.audio import DecodeRange
from local_transcriber.infrastructure.diagnostics import AuditEvent, DiagnosticLog, audit
from local_transcriber.infrastructure.ffmpeg_decoder import FFmpegMediaDecoder
from local_transcriber.infrastructure.media import MediaInspector
from local_transcriber.infrastructure.privacy import (
    PrivateStorageError,
    child_environment,
    private_directory,
)
from local_transcriber.infrastructure.temp_storage import (
    ManagedTempFiles,
    WorkspaceBusy,
)


def registered(storage, job, extension="tmp", state="temporary"):
    name = "stream-0-0-1000-" + uuid4().hex + "." + extension
    with storage.lease(job, create=True) as directory:
        storage.register(directory, job, {name: state})
        path = directory / name
        path.write_bytes(b"synthetic artifact")
    return path


def test_log_discards_secrets_transcripts_and_traceback_even_on_disk_full(
    tmp_path, monkeypatch, capsys
):
    secret = "synthetic-password-never-real"
    phrase = "Частный тестовый текст транскрипта"
    monkeypatch.setenv("PGPASSWORD", secret)
    job = uuid4()
    log = DiagnosticLog(tmp_path / "logs")
    try:
        audit(AuditEvent.OPERATION_FAILED, job)
        try:
            raise RuntimeError(secret + phrase)
        except RuntimeError:
            logging.getLogger("local_transcriber.test").exception("%s %s", secret, phrase)
        path = tmp_path / "logs/managed-v1/diagnostics.jsonl"
        ticket = uuid4()
        logging.getLogger("local_transcriber.test").error(
            "worker_event kind=%s job_id=%s ticket=%s", "ERROR", None, ticket
        )
        content = path.read_text(encoding="utf-8")
        assert secret not in content and phrase not in content and "Traceback" not in content
        assert json.loads(content.splitlines()[0])["job_id"] == str(job)
        assert json.loads(content.splitlines()[-1])["job_id"] is None
        assert str(ticket) not in content

        def fail_write(text):
            raise OSError(errno.ENOSPC, secret + phrase)

        monkeypatch.setattr(log.handler.stream, "write", fail_write)
        logging.getLogger("local_transcriber.test").error("%s", secret + phrase)
        captured = capsys.readouterr()
        assert secret not in captured.err and phrase not in captured.err
        assert "журнал" in captured.err
    finally:
        log.close()


def test_cleanup_retention_owner_unknown_retained_and_active_lease(tmp_path):
    storage = ManagedTempFiles(tmp_path)
    job = uuid4()
    stale = registered(storage, job)
    fresh = registered(storage, job)
    retained = registered(storage, job, "wav", "retained")
    unknown = stale.parent / "source.mp4"
    unknown.write_bytes(b"never delete")
    os.utime(stale, (time.time() - 90_000, time.time() - 90_000))
    with storage.lease(job):
        assert storage.cleanup_job(job).skipped == 1
        with pytest.raises(WorkspaceBusy):
            with storage.lease(job):
                pass
    report = storage.cleanup()
    assert report.deleted == 1 and not stale.exists()
    assert fresh.exists() and retained.exists() and unknown.exists()
    storage.cleanup_job(job, include_retained=True, protected=(retained,))
    assert retained.exists() and unknown.exists() and not fresh.exists()
    storage.cleanup_job(job, include_retained=True)
    assert retained.exists() and unknown.read_bytes() == b"never delete"
    assert "source" in (retained.parent / "artifacts.json").read_text()


def test_corrupt_registry_traversal_refuses_all_deletion_and_hardlinks_preserve_source(tmp_path):
    storage = ManagedTempFiles(tmp_path)
    job = uuid4()
    registered(storage, job)
    source = tmp_path / "source.wav"
    source.write_bytes(b"user original")
    alias = registered(storage, job, "wav", "retained")
    alias.unlink()
    os.link(source, alias)
    report = storage.cleanup_job(job, include_retained=True)
    assert report.skipped == 1 and alias.exists() and source.exists()
    owned = registered(storage, job)
    manifest = alias.parent / "artifacts.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "job_id": str(job),
                "files": {owned.name: "temporary", "../../source.wav": "temporary"},
            }
        ),
        encoding="utf-8",
    )
    assert storage.cleanup_job(job, include_retained=True).failed == 1
    assert source.read_bytes() == b"user original" and alias.exists() and owned.exists()
    # Unknown existing directory is never adopted/chmodded/deleted.
    other = tmp_path / "unmanaged"
    other.mkdir()
    with pytest.raises(PrivateStorageError):
        private_directory(other)


def test_cleanup_permission_denied_is_retryable(tmp_path, monkeypatch):
    storage = ManagedTempFiles(tmp_path)
    job = uuid4()
    path = registered(storage, job)
    original = Path.unlink

    def blocked(self, *args, **kwargs):
        if self == path:
            raise PermissionError(errno.EACCES, "test private detail")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", blocked)
    assert storage.cleanup_job(job, include_retained=True).failed == 1
    assert path.exists()
    monkeypatch.setattr(Path, "unlink", original)
    assert storage.cleanup_job(job, include_retained=True).deleted == 1


def test_deletion_confirmation_happens_before_store_calls():
    class Untouched:
        def delete_session(self, identifier):
            raise AssertionError("must not call without confirmation")

    with pytest.raises(ValueError, match="подтверждения"):
        DeleteHistory(Untouched(), None).execute(DeleteSession(uuid4()))


def test_cli_no_confirmation_does_not_require_database(capsys):
    from local_transcriber.__main__ import main

    assert main(["maintenance", "delete", str(uuid4())]) == 2
    assert "confirm-delete" in capsys.readouterr().err
    assert main(["maintenance", "cleanup", "--remove-derived"]) == 2
    assert "--job" in capsys.readouterr().err


def test_export_filename_sanitizes_suggestions_and_worker_terminal_events_survive():
    assert export_filename("NUL.mp4", ExportFormat.TXT) == "_NUL.txt"
    assert export_filename("NUL .part.mp4", ExportFormat.TXT) == "_NUL .part.txt"
    assert "/" not in export_filename("../bad:video\n.mp4", ExportFormat.JSON)
    assert export_filename("Запись с пробелами.mkv", ExportFormat.SRT) == "Запись с пробелами.srt"
    from local_transcriber.application.worker_protocol import WorkerEvent
    from local_transcriber.infrastructure.worker_manager import WorkerManager

    manager = WorkerManager.__new__(WorkerManager)
    manager._lock, manager._wake = threading.RLock(), threading.Event()
    manager._events = deque(maxlen=128)
    terminal = WorkerEvent("COMPLETED", uuid4(), uuid4())
    manager._emit(terminal)
    for index in range(300):
        manager._emit(WorkerEvent("PROGRESS", terminal.ticket, terminal.job_id, index))
    events = manager.poll()
    assert terminal in events and len(events) <= 128


@pytest.mark.integration
def test_real_special_char_paths_ffmpeg_and_secret_free_children(tmp_path, monkeypatch):
    ffmpeg = shutil.which(os.environ.get("LOCAL_TRANSCRIBER_FFMPEG_PATH", "ffmpeg"))
    ffprobe = shutil.which(os.environ.get("LOCAL_TRANSCRIBER_FFPROBE_PATH", "ffprobe"))
    assert ffmpeg and ffprobe, "Set local FFmpeg/ffprobe paths for this integration test"
    source = tmp_path / "Запись & $() ; '.wav"
    with wave.open(str(source), "wb") as output:
        output.setparams((1, 2, 16000, 1600, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 1600)
    original = source.read_bytes()
    monkeypatch.setenv("PGPASSWORD", "synthetic password")
    monkeypatch.setenv("LOCAL_TRANSCRIBER_POSTGRES_PASSWORD", "synthetic password")
    monkeypatch.setenv("HF_TOKEN", "synthetic token")
    children = []
    real = subprocess.Popen

    def launch(arguments, **kwargs):
        children.append(kwargs)
        assert kwargs["shell"] is False
        assert not set(child_environment()) & {
            "PGPASSWORD",
            "LOCAL_TRANSCRIBER_POSTGRES_PASSWORD",
            "HF_TOKEN",
        }
        assert "PGPASSWORD" not in kwargs["env"]
        return real(arguments, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", launch)
    info = MediaInspector(ffprobe, timeout=5).inspect(source)
    assert len(info.audio_streams) == 1
    from local_transcriber.infrastructure.intermediate_audio import RecordingDecoder

    storage = ManagedTempFiles(tmp_path / "owned-temp")
    job = uuid4()
    decoder = RecordingDecoder(
        FFmpegMediaDecoder(ffmpeg), lambda: tmp_path / "unused", managed=storage, job_id=lambda: job
    )
    with decoder.decode(source, stream_index=0, decode_range=DecodeRange(0, 100)) as blocks:
        assert sum(len(block.pcm) for block in blocks) == 3200
    assert len(children) >= 2 and source.read_bytes() == original
    artifacts = list((storage.root / str(job)).glob("*.wav"))
    assert len(artifacts) == 1
    with wave.open(str(artifacts[0]), "rb") as recorded:
        assert recorded.getnframes() == 1600
    assert "retained" in (artifacts[0].parent / "artifacts.json").read_text()


@pytest.mark.integration
def test_windows_acl_on_owned_directory(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows ACL test")
    path = private_directory(tmp_path / "private")
    subprocess.run(
        ["icacls", str(path), "/save", str(tmp_path / "acl.txt")],
        capture_output=True,
        shell=False,
        check=True,
    )
    acl = (tmp_path / "acl.txt").read_text(encoding="utf-16-le")
    assert "D:P" in acl
    assert "WD" not in acl and "BU" not in acl and "AU" not in acl
    assert "SY" in acl and "BA" in acl
    # A failed ACL setup must not leave an empty unowned directory blocking a safe retry.
    from local_transcriber.infrastructure import privacy

    real_acl = privacy._windows_acl
    calls = []

    def fail_once(path):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError("synthetic ACL failure")
        return real_acl(path)

    monkeypatch.setattr(privacy, "_windows_acl", fail_once)
    retry = tmp_path / "retry-private"
    with pytest.raises(PrivateStorageError):
        private_directory(retry)
    assert not retry.exists()
    assert private_directory(retry) == retry


def test_delete_gui_requires_dialog_confirmation(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from test_desktop import FakeBackend

    from local_transcriber.application.desktop import DesktopEvent
    from local_transcriber.ui.bridge import DesktopBridge
    from local_transcriber.ui.window import MainWindow

    backend = FakeBackend()
    bridge = DesktopBridge(lambda path: backend)
    window = MainWindow(bridge)
    qtbot.addWidget(window)
    window.show()
    bridge.start()
    try:
        qtbot.waitUntil(lambda: window.connected)
        window.import_paths([tmp_path / "source.mp4"])
        qtbot.waitUntil(lambda: window.table.rowCount() == 1)
        monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.No)
        window._delete_history()
        assert not any(cmd == "delete_session" for cmd, payload, tid in backend.commands)
        original_selection = window._selected

        def confirm_with_pending_selection_change(self):
            window._selected = uuid4()
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "exec", confirm_with_pending_selection_change)
        window._delete_history()
        qtbot.waitUntil(
            lambda: any(cmd == "delete_session" for cmd, payload, tid in backend.commands)
        )
        request = next(payload for cmd, payload, tid in backend.commands if cmd == "delete_session")
        assert request.confirmed and not request.remove_derived
        assert request.media_id == original_selection
        window._event(DesktopEvent("REMOVED", request.media_id))
        assert window.table.rowCount() == 0 and not window.records
    finally:
        bridge.request_close()
        assert bridge.wait_closed()
        window._can_close = True
        window.close()


@pytest.mark.integration
def test_native_qt_media_metadata_and_opaque_messages_are_not_logged(tmp_path):
    import sys

    if os.name != "nt":
        pytest.skip("Native Windows Qt privacy test")
    phrase = "synthetic-private-password-and-transcript"
    path = tmp_path / (phrase + ".wav")
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 16000, 1600, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 1600)
    code = """
import sys
from pathlib import Path
from local_transcriber.ui.bootstrap import run_gui
from local_transcriber.ui.window import MainWindow
original = MainWindow.__init__
loaded = []
def init(self, bridge):
    original(self, bridge)
    from PySide6.QtCore import QTimer, QUrl, qWarning
    from PySide6.QtMultimedia import QMediaPlayer
    qWarning("synthetic-private-password-and-transcript")
    self.probe_player = QMediaPlayer(self)
    self.probe_player.durationChanged.connect(lambda value: loaded.append(value))
    self.probe_player.setSource(QUrl.fromLocalFile(sys.argv[1]))
    QTimer.singleShot(700, self.close)
MainWindow.__init__ = init
result = run_gui(Path('missing-local-settings.env'))
raise SystemExit(result if loaded else 3)
"""
    environment = {
        **os.environ,
        "QT_QPA_PLATFORM": "windows",
        "QT_FFMPEG_DEBUG": "1",
        "QT_LOGGING_RULES": "*.multimedia.*=true",
    }
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", code, str(path)],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert phrase not in result.stderr and phrase not in result.stdout
    assert "Input #0" not in result.stderr
