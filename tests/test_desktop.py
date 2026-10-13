"""Focused Qt event-loop tests. Doubles here never claim real GPU inference."""

import queue
import threading
import time
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDropEvent

from local_transcriber.application.desktop import (
    DesktopEvent,
    DesktopRecord,
    JobChoices,
    available_actions,
)
from local_transcriber.domain.audio import AudioBlock, DecodeRange
from local_transcriber.domain.media import AudioStreamInfo, MediaInfo
from local_transcriber.infrastructure.intermediate_audio import RecordingDecoder
from local_transcriber.infrastructure.settings import AppSettings
from local_transcriber.ui.bridge import DesktopBridge
from local_transcriber.ui.window import MainWindow


class FakeBackend:
    def __init__(self):
        self.settings = AppSettings(_env_file=None)
        self.events = queue.Queue()
        self.records = {}
        self.commands = []
        self.closed = False
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(self, command, payload=None):
        self.commands.append((command, payload, threading.get_ident()))
        if command == "refresh":
            return [DesktopEvent("CONNECTED", self.settings)]
        if command == "import":
            if Path(payload).name == "без аудио.mkv":
                raise ValueError("Файл не содержит аудиопотоков.")
            media = MediaInfo(
                Path(payload),
                Path(payload).name,
                2_000_000_000,
                3_600_000,
                "mkv",
                str(payload),
                (AudioStreamInfo(1, "aac", 48000, 2, "ru"), AudioStreamInfo(3, "opus", 48000, 2)),
            )
            record = DesktopRecord(uuid4(), media)
            self.records[record.id] = record
            return [DesktopEvent("RECORD", record)]
        if command == "start":
            identifier, choices = payload
            record = replace(self.records[identifier], status="PROCESSING", model=choices.model)
            self.records[identifier] = record
            self.started.set()
            return [DesktopEvent("QUEUED", identifier), DesktopEvent("RECORD", record)]
        return []

    def poll(self):
        try:
            return [self.events.get_nowait()]
        except queue.Empty:
            return []

    def close(self):
        self.closed = True


@pytest.fixture
def desktop(qtbot):
    backend = FakeBackend()
    bridge = DesktopBridge(lambda path: backend)
    window = MainWindow(bridge)
    qtbot.addWidget(window)
    window.show()
    bridge.start()
    qtbot.waitUntil(lambda: window.connected)
    yield window, backend, bridge
    bridge.request_close()
    qtbot.waitUntil(lambda: backend.closed)
    assert bridge.wait_closed()
    from shiboken6 import isValid

    if isValid(window):
        window._can_close = True
        window.close()


def test_window_import_multiple_cyrillic_and_no_audio(qtbot, desktop, tmp_path) -> None:
    window, backend, bridge = desktop
    paths = [tmp_path / "Запись с пробелами.mkv", tmp_path / "Другая запись.mp4"]
    window.import_paths(paths)
    qtbot.waitUntil(lambda: window.table.rowCount() == 2)
    assert len(window.records) == 2
    assert "Поток" in window.streams.horizontalHeaderItem(1).text()
    assert window.streams.item(0, 1).text() == "1"
    assert window.streams.item(1, 1).text() == "3"
    window.import_paths([tmp_path / "без аудио.mkv"])
    qtbot.waitUntil(lambda: "не содержит" in window.errors.toPlainText())
    assert window.table.rowCount() == 2
    assert all(identity != threading.get_ident() for _, _, identity in backend.commands)


def test_drag_drop_only_local_paths(qtbot, desktop, tmp_path) -> None:
    window, backend, bridge = desktop
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "Видео.mkv"))])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    qtbot.waitUntil(lambda: window.table.rowCount() == 1)
    assert event.isAccepted()
    mime.setUrls([QUrl("https://example.invalid/media.mp4")])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    assert not event.isAccepted()
    assert window.table.rowCount() == 1


def test_buttons_progress_error_and_no_freeze_during_mock_transcription(
    qtbot, desktop, tmp_path
) -> None:
    window, backend, bridge = desktop
    window.import_paths([tmp_path / "запись.mkv"])
    qtbot.waitUntil(lambda: window.start_button.isEnabled())
    assert not window.pause_button.isEnabled()
    assert not window.resume_button.isEnabled()
    counter = []
    timer = QTimer(window)
    timer.timeout.connect(lambda: counter.append(time.monotonic()))
    timer.start(10)
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.pause_button.isEnabled())
    assert not window.start_button.isEnabled()
    assert window.cancel_button.isEnabled()
    identifier = window._selected
    record = backend.records[identifier]
    backend.events.put(DesktopEvent("RECORD", replace(record, progress=40)))
    qtbot.waitUntil(lambda: window.progress.value() == 40)
    qtbot.waitUntil(lambda: len(counter) >= 5)
    backend.events.put(DesktopEvent("RECORD", replace(record, status="PAUSED", progress=40)))
    qtbot.waitUntil(lambda: window.resume_button.isEnabled())
    assert not window.pause_button.isEnabled()
    backend.events.put(DesktopEvent("DEQUEUED", identifier))
    backend.events.put(
        DesktopEvent("RECORD", replace(record, status="INTERRUPTED", error="Worker: CUDA error"))
    )
    backend.events.put(DesktopEvent("ERROR", "Worker: CUDA error", identifier))
    qtbot.waitUntil(lambda: "CUDA error" in window.errors.toPlainText())
    assert window.resume_button.isEnabled()
    assert not window.start_button.isEnabled()
    assert window.progress.value() == 0
    timer.stop()


def test_roles_options_and_empty_selection(qtbot, desktop, tmp_path) -> None:
    window, backend, bridge = desktop
    window.import_paths([tmp_path / "recording.mkv"])
    qtbot.waitUntil(lambda: window.start_button.isEnabled())
    window.streams.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    assert "Выберите" in window.errors.toPlainText()
    window.streams.item(0, 0).setCheckState(Qt.CheckState.Checked)
    window.streams.item(1, 0).setCheckState(Qt.CheckState.Checked)
    window.streams.cellWidget(0, 5).setCurrentText("Я")
    window.keep_audio.setChecked(True)
    window.device.setCurrentIndex(1)
    assert window.quality.currentData() == "float32"
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: backend.started.is_set())
    choices = next(payload[1] for command, payload, _ in backend.commands if command == "start")
    assert choices.indices == (1, 3)
    assert choices.roles == ((1, "Я"), (3, ""))
    assert choices.keep_audio and choices.device == "cpu"


def test_missing_database_diagnostic_opens_window_without_gpu(qtbot) -> None:
    from local_transcriber.infrastructure.desktop_backend import DesktopService

    bridge = DesktopBridge(
        lambda path: DesktopService(
            settings=AppSettings(postgres_user="", postgres_dsn=None, _env_file=None)
        )
    )
    window = MainWindow(bridge)
    qtbot.addWidget(window)
    window.show()
    bridge.start()
    qtbot.waitUntil(lambda: "недоступна" in window.connection_label.text())
    assert not window.start_button.isEnabled()
    assert window.refresh_button.isEnabled()
    assert window.isVisible()
    assert "PostgreSQL" in window.errors.toPlainText()
    window.close()
    qtbot.waitUntil(lambda: window._can_close)
    assert bridge.wait_closed()


def test_slow_backend_does_not_block_close_or_event_loop(qtbot) -> None:
    backend = FakeBackend()
    gate = threading.Event()
    original = backend.execute

    def slow(command, payload=None):
        if command == "refresh":
            backend.started.set()
            gate.wait(3)
        return original(command, payload)

    backend.execute = slow
    bridge = DesktopBridge(lambda path: backend)
    window = MainWindow(bridge)
    qtbot.addWidget(window)
    window.show()
    bridge.start()
    qtbot.waitUntil(lambda: backend.started.is_set())
    counter = []
    timer = QTimer(window)
    timer.timeout.connect(lambda: counter.append(1))
    timer.start(10)
    window.close()
    qtbot.waitUntil(lambda: len(counter) >= 3)
    assert not window._can_close
    gate.set()
    qtbot.waitUntil(lambda: window._can_close)
    assert bridge.wait_closed()


def test_fsm_choices_and_bounded_capture(tmp_path) -> None:
    assert available_actions("COMPLETED") == (True, False, False, False)
    assert available_actions("PROCESSING") == (False, True, False, True)
    assert available_actions("PAUSED") == (False, False, True, True)
    assert available_actions("PENDING", queued=True) == (False, False, False, True)
    with pytest.raises(ValueError):
        JobChoices(())
    with pytest.raises(ValueError):
        JobChoices((1,), compute="float16", device="cpu")

    class Decoder:
        @contextmanager
        def decode(self, source: Path, **kwargs) -> Iterator:
            yield iter([AudioBlock(0, 100, b"\0\0" * 1600), AudioBlock(100, 200, b"\0\0" * 1600)])

    recorder = RecordingDecoder(Decoder(), lambda: tmp_path)
    kwargs = {"stream_index": 1, "decode_range": DecodeRange(0, 200)}
    with recorder.decode(Path("source.mkv"), **kwargs) as blocks:
        assert len(list(blocks)) == 2
    files = list(tmp_path.glob("*.wav"))
    assert len(files) == 1
    with wave.open(str(files[0]), "rb") as source:
        assert source.getnframes() == 3200
        assert source.getframerate() == 16000
    with recorder.decode(Path("source.mkv"), **kwargs) as blocks:
        next(blocks)  # Incomplete/cancelled decode must not publish a partial WAV.
    assert list(tmp_path.glob("*.wav")) == files
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.integration
def test_gui_bootstrap_shutdown_in_fresh_windows_process(tmp_path) -> None:
    import os
    import subprocess
    import sys

    if os.name != "nt":
        pytest.skip("Native Windows GUI shutdown regression")
    code = """
from pathlib import Path
from PySide6.QtCore import QTimer
from local_transcriber.ui.window import MainWindow
from local_transcriber.ui.bootstrap import run_gui
original = MainWindow.__init__
def init(self, bridge):
    original(self, bridge)
    QTimer.singleShot(300, self.close)
MainWindow.__init__ = init
raise SystemExit(run_gui(Path('missing-local-settings.env')))
"""
    environment = {**os.environ, "QT_QPA_PLATFORM": "windows", "QT_SCALE_FACTOR": "1.2"}
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
