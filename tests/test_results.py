"""Focused editor tests; in-memory adapter is explicitly a test double."""

import time
import wave
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox
from test_desktop import FakeBackend

from local_transcriber.application.desktop import DesktopEvent
from local_transcriber.application.export import ExportDocument, ExportFormat, ExportOptions
from local_transcriber.application.transcript import TextVersion
from local_transcriber.domain.text import TextSegment, VersionType, aggregate_raw
from local_transcriber.ui.bridge import DesktopBridge
from local_transcriber.ui.results import ResultsWindow


def saved_document(path: Path, count: int = 1000) -> ExportDocument:
    job = uuid4()
    segments = tuple(
        TextSegment(
            uuid4(),
            index % 2,
            index * 100,
            index * 100 + 90,
            f"😀 PostgreSQL термин {index}",
            "Я" if index % 2 else "Собеседник",
        )
        for index in range(count)
    )
    raw = TextVersion(uuid4(), job, 1, VersionType.RAW, aggregate_raw(segments), {})
    readable = TextVersion(uuid4(), job, 2, VersionType.READABLE, "Читаемый PostgreSQL текст.", {})
    return ExportDocument(
        {"filename": path.name, "file_path": str(path), "duration_ms": 100_000},
        {"id": str(job), "model_name": "unused"},
        (),
        segments,
        raw,
        readable,
        raw,
    )


class ResultBackend(FakeBackend):
    def __init__(self, document):
        super().__init__()
        self.document = document
        self.fail_save = False

    def execute(self, command, payload=None):
        if command == "result_load":
            return [DesktopEvent("RESULT_LOADED", self.document, payload.request_id)]
        if command == "result_manual":
            if self.fail_save:
                raise ValueError("Тест: база недоступна")
            version = TextVersion(
                uuid4(), payload.job_id, 3, VersionType.MANUAL, payload.content, {}
            )
            self.document = replace(self.document, selected=version)
            return [DesktopEvent("MANUAL_SAVED", version, payload.request_id)]
        if command == "result_export":
            # The real writer/service/DB export is tested separately with PostgreSQL.
            assert payload.base_id == self.document.selected.id
            payload.destination.write_text(self.document.selected.content, encoding="utf-8")
            return [DesktopEvent("RESULT_EXPORTED", payload.destination, payload.request_id)]
        return super().execute(command, payload)


@pytest.fixture
def editor(qtbot, tmp_path):
    document = saved_document(tmp_path / "пропавшая запись.mkv")
    backend = ResultBackend(document)
    bridge = DesktopBridge(lambda path: backend)
    window = ResultsWindow(bridge, document.raw.job_id)
    qtbot.addWidget(window)
    window.show()
    bridge.start()
    qtbot.waitUntil(lambda: window.document is not None)
    yield window, backend, bridge
    window._dirty = False
    window._saving = False
    window.close()
    bridge.request_close()
    assert bridge.wait_closed()


def test_thousand_segments_search_filter_seek_and_heartbeat(qtbot, editor):
    window, backend, bridge = editor
    ticks = []
    timer = QTimer(window)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start(10)
    opened = time.monotonic()
    window.load_document(backend.document)
    assert time.monotonic() - opened < 0.5
    assert window.model.rowCount() == 1000
    window.search.setText("термин 998")
    qtbot.waitUntil(lambda: window.proxy.rowCount() == 1)
    assert window.highlighter.pattern is not None
    assert window.model.data(window.model.index(998, 4), Qt.ItemDataRole.BackgroundRole)
    window._seek_segment(window.proxy.index(0, 0))
    assert window.position_ms == 99_800
    assert window.model.active == {998}
    assert "00:01:39.800" in window.time_label.text()
    window.stream.setCurrentIndex(window.stream.findData(1))
    assert window.proxy.rowCount() == 0
    window.stream.setCurrentIndex(0)
    window.search.clear()
    qtbot.waitUntil(lambda: window.proxy.rowCount() == 1000)
    window.speaker.setCurrentIndex(window.speaker.findData("Я"))
    assert window.proxy.rowCount() == 500
    qtbot.waitUntil(lambda: len(ticks) >= 5)
    timer.stop()


def test_manual_save_raw_immutable_export_and_draft_switch(qtbot, editor, tmp_path):
    window, backend, bridge = editor
    original = window.editor.toPlainText()
    window.mode.setCurrentIndex(2)
    window.editor.setPlainText("Ручная правка PostgreSQL 😀")
    window.mode.setCurrentIndex(0)
    assert window.editor.isReadOnly()
    assert window.editor.toPlainText() == original
    window.mode.setCurrentIndex(2)
    assert window.editor.toPlainText() == "Ручная правка PostgreSQL 😀"
    destination = tmp_path / "результат.txt"
    window.export_to(destination, ExportOptions(ExportFormat.TXT))
    assert not destination.exists()
    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window._saving)
    assert window.versions[VersionType.MANUAL].content == "Ручная правка PostgreSQL 😀"
    window.export_to(destination, ExportOptions(ExportFormat.TXT))
    qtbot.waitUntil(destination.exists)
    assert destination.read_text(encoding="utf-8") == "Ручная правка PostgreSQL 😀"
    window.mode.setCurrentIndex(0)
    assert window.editor.toPlainText() == original == backend.document.raw.content


def test_failed_save_keeps_draft_and_close_escape_guard(qtbot, editor, monkeypatch):
    window, backend, bridge = editor
    window.mode.setCurrentIndex(2)
    window.editor.setPlainText("Не терять правки")
    backend.fail_save = True
    window.save_manual()
    qtbot.waitUntil(lambda: not window._saving)
    assert window._dirty and window.editor.toPlainText() == "Не терять правки"
    assert "база недоступна" in window.info.text()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    window.reject()
    assert window.isVisible()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.close()
    assert not window.isVisible()


def test_missing_source_codec_error_and_empty_transcript(qtbot, editor, tmp_path):
    window, backend, bridge = editor
    assert not window.play_button.isEnabled()
    assert "недоступен" in window.media_info.text()
    window.load_document(saved_document(tmp_path / "нет.wav", count=0))
    assert window.model.rowCount() == 0
    assert window.editor.toPlainText() == ""
    assert "Пустой" in window.info.text()
    window._media_error(QMediaPlayer.Error.FormatError, "untrusted codec detail")
    assert "FormatError" in window.media_info.text()
    assert window.export_button.isEnabled()
    assert window.editor.isReadOnly()
    broken = tmp_path / "поврежденный.mp4"
    broken.write_bytes(b"this is not a media container")
    window.load_document(saved_document(broken, count=3))
    qtbot.waitUntil(lambda: window._media_failed, timeout=10000)
    assert window.editor.toPlainText() == window.document.raw.content
    assert window.export_button.isEnabled() and not window.play_button.isEnabled()


@pytest.mark.integration
def test_real_qt_wave_playback_and_seek(qtbot, tmp_path):
    path = tmp_path / "реальный звук.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 16000, 16000 * 3, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 16000 * 3)
    backend = ResultBackend(saved_document(path, count=3))
    bridge = DesktopBridge(lambda path: backend)
    window = ResultsWindow(bridge, backend.document.raw.job_id)
    qtbot.addWidget(window)
    window.show()
    bridge.start()
    try:
        qtbot.waitUntil(lambda: window.player.duration() == 3000, timeout=10000)
        window.audio.setMuted(True)
        window.seek(1500)
        qtbot.waitUntil(lambda: abs(window.player.position() - 1500) < 100)
        window._play()
        qtbot.waitUntil(lambda: window.player.position() > 1600, timeout=5000)
        assert window.position_ms == window.player.position()
        window._play()
        assert window.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    finally:
        window.close()
        bridge.request_close()
        assert bridge.wait_closed()


def test_main_window_result_button_and_dirty_shutdown_guard(qtbot, tmp_path, monkeypatch):
    from local_transcriber.application.desktop import DesktopRecord
    from local_transcriber.domain.media import MediaInfo
    from local_transcriber.ui.window import MainWindow

    document = saved_document(tmp_path / "missing.mp4", count=3)
    backend = ResultBackend(document)
    bridge = DesktopBridge(lambda path: backend)
    main = MainWindow(bridge)
    qtbot.addWidget(main)
    main.show()
    bridge.start()
    try:
        qtbot.waitUntil(lambda: main.connected)
        record = DesktopRecord(
            uuid4(),
            MediaInfo(tmp_path / "missing.mp4", "missing.mp4", 1, 1000, "mp4", "test", ()),
            document.raw.job_id,
            "COMPLETED",
        )
        main._record(record)
        main._buttons()
        assert main.result_button.isEnabled()
        qtbot.mouseClick(main.result_button, Qt.MouseButton.LeftButton)
        result = main._result_windows[document.raw.job_id]
        qtbot.waitUntil(lambda: result.document is not None)
        result.mode.setCurrentIndex(2)
        result.editor.setPlainText("Unsaved")
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
        assert not main.close()
        assert not bridge._stop.is_set() and result.isVisible()
        result._dirty = False
        result.close()
    finally:
        bridge.request_close()
        assert bridge.wait_closed()
        from shiboken6 import isValid

        if isValid(main):
            main._can_close = True
            main.close()
