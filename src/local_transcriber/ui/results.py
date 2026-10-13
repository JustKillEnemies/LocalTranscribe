"""Saved transcript editor and local Qt Multimedia playback, independent of STT."""

import re
from pathlib import Path
from uuid import UUID, uuid4

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from local_transcriber.application.desktop import DesktopEvent
from local_transcriber.application.export import (
    ExportDocument,
    ExportFormat,
    ExportOptions,
    export_filename,
    timestamp,
)
from local_transcriber.application.results import ResultRequest
from local_transcriber.application.transcript import TextVersion
from local_transcriber.domain.text import TextSegment, VersionType
from local_transcriber.ui.bridge import DesktopBridge


class SegmentModel(QAbstractTableModel):
    """Virtual table: no individual widgets/items for each saved segment."""

    headers = ("Начало (ms)", "Конец (ms)", "Дорожка", "Роль", "Исходный текст")

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.segments: tuple[TextSegment, ...] = ()
        self.active: set[int] = set()
        self.query = ""

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.segments)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.headers)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        segment = self.segments[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                f"{timestamp(segment.start_ms)} ({segment.start_ms})",
                f"{timestamp(segment.end_ms)} ({segment.end_ms})",
                str(segment.stream_index),
                segment.speaker_label or "—",
                segment.raw_text,
            )[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return segment.raw_text
        if role == Qt.ItemDataRole.BackgroundRole:
            if index.row() in self.active:
                return QColor("#285987")
            if index.column() == 4 and self.query and self.query in segment.raw_text.casefold():
                return QColor("#705818")
        return None

    def load(self, segments: tuple[TextSegment, ...]) -> None:
        self.beginResetModel()
        self.segments = tuple(
            sorted(segments, key=lambda s: (s.start_ms, s.stream_index, s.id.int))
        )
        self.active.clear()
        self.endResetModel()

    def position(self, milliseconds: int) -> None:
        active = {
            row for row, s in enumerate(self.segments) if s.start_ms <= milliseconds < s.end_ms
        }
        changed = active ^ self.active
        self.active = active
        for row in changed:
            self.dataChanged.emit(self.index(row, 0), self.index(row, 4))


class SegmentFilter(QSortFilterProxyModel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.stream: int | None = None
        self.speaker: str | None = None
        self.query = ""

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        segment = self.sourceModel().segments[row]
        return (
            (self.stream is None or segment.stream_index == self.stream)
            and (self.speaker is None or (segment.speaker_label or "") == self.speaker)
            and (not self.query or self.query in segment.raw_text.casefold())
        )

    def refresh(self) -> None:
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)


class SearchHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self.pattern: re.Pattern | None = None
        self.style = QTextCharFormat()
        self.style.setBackground(QColor("#ffe08a"))
        self.style.setForeground(QColor("#171717"))

    def highlightBlock(self, text: str) -> None:
        if self.pattern:
            for match in self.pattern.finditer(text):
                # QTextCursor/highlighter offsets count UTF-16 units, unlike Python strings.
                offset = len(text[: match.start()].encode("utf-16-le")) // 2
                length = len(match.group().encode("utf-16-le")) // 2
                self.setFormat(offset, length, self.style)

    def search(self, text: str) -> None:
        self.pattern = re.compile(re.escape(text), re.IGNORECASE) if text else None
        self.rehighlight()


class ResultsWindow(QDialog):
    def __init__(self, bridge: DesktopBridge, job_id: UUID, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge, self.job_id = bridge, job_id
        self.document: ExportDocument | None = None
        self.versions: dict[VersionType, TextVersion] = {}
        self._requests: dict[UUID, str] = {}
        self._draft: str | None = None
        self._base_id: UUID | None = None
        self._dirty = False
        self._saving = False
        self._setting_text = False
        self.position_ms = 0
        self._pending_seek: int | None = None
        self._media_failed = False
        self._duration_ms = 0
        self.setWindowTitle("LocalTranscribe — результат")
        self.resize(1220, 800)
        self.setMinimumSize(900, 600)
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("RAW · дословный", VersionType.RAW)
        self.mode.addItem("READABLE · читаемый", VersionType.READABLE)
        self.mode.addItem("MANUAL · ручные правки", VersionType.MANUAL)
        self.save_button = QPushButton("Сохранить новую MANUAL")
        self.export_button = QPushButton("Экспорт…")
        toolbar.addWidget(self.mode)
        toolbar.addWidget(self.save_button)
        toolbar.addStretch()
        toolbar.addWidget(self.export_button)
        layout.addLayout(toolbar)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск в тексте и сегментах…")
        self.stream = QComboBox()
        self.speaker = QComboBox()
        self.stream.setMinimumWidth(125)
        self.speaker.setMinimumWidth(145)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.stream)
        filters.addWidget(self.speaker)
        layout.addLayout(filters)
        self.info = QLabel("Загрузка сохранённого транскрипта…")
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        split = QSplitter(Qt.Orientation.Vertical)
        upper = QSplitter()
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.highlighter = SearchHighlighter(self.editor.document())
        upper.addWidget(self.editor)
        media = QWidget()
        media_layout = QVBoxLayout(media)
        media_layout.setContentsMargins(0, 0, 0, 0)
        self.video = QVideoWidget()
        self.video.setMinimumSize(250, 150)
        media_layout.addWidget(self.video, 1)
        self.media_info = QLabel("Источник ещё не загружен.")
        self.media_info.setTextFormat(Qt.TextFormat.PlainText)
        self.media_info.setWordWrap(True)
        media_layout.addWidget(self.media_info)
        playback = QHBoxLayout()
        self.play_button = QPushButton("▶ Воспроизвести")
        self.time_label = QLabel(timestamp(0))
        playback.addWidget(self.play_button)
        playback.addWidget(self.time_label)
        media_layout.addLayout(playback)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1_000_000)
        media_layout.addWidget(self.slider)
        self.follow = QCheckBox("Следовать за воспроизведением")
        self.follow.setChecked(True)
        media_layout.addWidget(self.follow)
        self.audio_track = QComboBox()
        self.audio_track.setToolTip("Звуковая дорожка плеера; нумерация Qt отличается от ffprobe")
        self.audio_track.currentIndexChanged.connect(
            lambda index: self.player.setActiveAudioTrack(index) if index >= 0 else None
        )
        media_layout.addWidget(self.audio_track)
        upper.addWidget(media)
        upper.setSizes([740, 400])
        split.addWidget(upper)
        self.table = QTableView()
        self.model = SegmentModel(self)
        self.proxy = SegmentFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate((190, 190, 65, 100)):
            self.table.setColumnWidth(column, width)
        split.addWidget(self.table)
        split.setSizes([450, 280])
        layout.addWidget(split, 1)
        layout.addWidget(
            QLabel(
                "Таблица — исходные сегменты; MANUAL не имеет автоматической привязки правок к времени."
            )
        )
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(self._duration)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._media_error)
        self.player.playbackStateChanged.connect(self._play_state)
        self.player.tracksChanged.connect(self._tracks)
        self.play_button.clicked.connect(self._play)
        self.slider.sliderReleased.connect(
            lambda: self.seek(self.slider.value() * self._duration_ms // 1_000_000)
        )
        self.table.clicked.connect(self._seek_segment)
        self.mode.currentIndexChanged.connect(self._version)
        self.editor.textChanged.connect(self._edited)
        self.save_button.clicked.connect(self.save_manual)
        self.export_button.clicked.connect(self._choose_export)
        self.stream.currentIndexChanged.connect(self._filter)
        self.speaker.currentIndexChanged.connect(self._filter)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(150)
        self.search_timer.timeout.connect(self._filter)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.bridge.event.connect(self._event, Qt.ConnectionType.QueuedConnection)
        self._buttons()
        self._request("result_load")

    def _request(self, command: str, **kwargs) -> None:
        request = ResultRequest(uuid4(), self.job_id, **kwargs)
        self._requests[request.request_id] = command
        self.bridge.submit(command, request)

    def _event(self, event: DesktopEvent) -> None:
        if event.record_id not in self._requests:
            return
        command = self._requests.pop(event.record_id)
        if event.kind == "ERROR":
            self.info.setText(str(event.value))
            if command == "result_manual":
                self._saving = False
            # Keep the draft and loaded text on failed save/export/connection.
        elif event.kind == "RESULT_LOADED":
            self.load_document(event.value)
        elif event.kind == "MANUAL_SAVED":
            self.versions[VersionType.MANUAL] = event.value
            self._base_id = event.value.id
            self._dirty = False
            self._saving = False
            self.info.setText(f"MANUAL №{event.value.number} сохранена. RAW не изменён.")
        elif event.kind == "RESULT_EXPORTED":
            self.info.setText(f"Экспорт сохранён: {event.value}")
        self._buttons()

    def load_document(self, document: ExportDocument) -> None:
        self.document = document
        self.setWindowTitle(f"LocalTranscribe — {document.media['filename']}")
        self.versions = {
            v.kind: v for v in (document.raw, document.readable, document.selected) if v
        }
        self.model.load(document.segments)
        self.stream.blockSignals(True)
        self.speaker.blockSignals(True)
        self.stream.clear()
        self.speaker.clear()
        self.stream.addItem("Все дорожки", None)
        self.speaker.addItem("Все роли", None)
        for index in sorted({s.stream_index for s in document.segments}):
            self.stream.addItem(f"Дорожка {index}", index)
        for label in sorted({s.speaker_label or "" for s in document.segments}):
            self.speaker.addItem(label or "Без подписи", label)
        self.stream.blockSignals(False)
        self.speaker.blockSignals(False)
        self.mode.setCurrentIndex(self.mode.findData(document.selected.kind))
        self._version()
        self._filter()
        self._duration(int(document.media.get("duration_ms") or 0))
        self._source(Path(str(document.media["file_path"])))
        self._buttons()

    def _version(self) -> None:
        if self.document is None:
            return
        kind = self.mode.currentData()
        if kind == VersionType.MANUAL:
            if self._draft is None:
                base = (
                    self.versions.get(kind)
                    or self.versions.get(VersionType.READABLE)
                    or self.document.raw
                )
                self._draft, self._base_id = base.content, base.id
            content = self._draft
        else:
            version = self.versions.get(kind)
            content = version.content if version else ""
        self._setting_text = True
        self.editor.setPlainText(content)
        self.editor.setReadOnly(kind != VersionType.MANUAL or self._saving)
        self._setting_text = False
        self._filter()
        self._buttons()

    def _edited(self) -> None:
        if not self._setting_text and self.mode.currentData() == VersionType.MANUAL:
            self._draft = self.editor.toPlainText()
            self._dirty = True
            self._buttons()

    def _buttons(self) -> None:
        kind = self.mode.currentData()
        self.save_button.setEnabled(
            bool(self.document) and kind == VersionType.MANUAL and not self._saving
        )
        self.export_button.setEnabled(bool(self.document) and not self._saving)
        self.mode.setEnabled(not self._saving)
        self.editor.setReadOnly(kind != VersionType.MANUAL or self._saving)
        self.play_button.setEnabled(bool(self.document) and not self._media_failed)
        self.slider.setEnabled(bool(self.document) and not self._media_failed)

    def _filter(self) -> None:
        query = self.search.text().strip()
        self.proxy.query = self.model.query = query.casefold()
        self.proxy.stream, self.proxy.speaker = (
            self.stream.currentData(),
            self.speaker.currentData(),
        )
        self.proxy.refresh()
        self.highlighter.search(query)
        self.table.viewport().update()
        if self.document and not self._dirty and not self._saving:
            count = (
                len(re.findall(re.escape(query), self.editor.toPlainText(), re.IGNORECASE))
                if query
                else 0
            )
            self.info.setText(
                f"Сегментов: {self.proxy.rowCount()} / {self.model.rowCount()} · совпадений в тексте: {count}"
                + (" · Пустой транскрипт" if not self.document.segments else "")
                + (
                    " · Версия отсутствует"
                    if self.mode.currentData() not in self.versions
                    and self.mode.currentData() != VersionType.MANUAL
                    else ""
                )
            )

    def save_manual(self) -> None:
        if self.document is None or self._saving or self.mode.currentData() != VersionType.MANUAL:
            return
        self._saving = True
        self.info.setText("Сохранение новой версии…")
        self._buttons()
        self._request("result_manual", base_id=self._base_id, content=self._draft or "")

    def export_to(self, path: Path, options: ExportOptions) -> None:
        if self.document is None:
            return
        if self.mode.currentData() == VersionType.MANUAL and (
            self._dirty or VersionType.MANUAL not in self.versions
        ):
            self.info.setText("Сначала сохраните MANUAL; экспортируется только сохранённая версия.")
            return
        version = self.versions.get(self.mode.currentData())
        if version is None:
            self.info.setText("Выбранная версия отсутствует.")
            return
        self._request("result_export", base_id=version.id, destination=path, options=options)

    def _choose_export(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Параметры экспорта")
        layout = QVBoxLayout(dialog)
        format_box = QComboBox()
        for fmt in ExportFormat:
            format_box.addItem(fmt.value.upper(), fmt)
        times = QCheckBox("Добавить таймкоды (TXT/Markdown)")
        roles = QCheckBox("Добавить подписи (TXT/Markdown)")
        save = QPushButton("Выбрать файл…")
        for widget in (format_box, times, roles, save):
            layout.addWidget(widget)
        save.clicked.connect(dialog.accept)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fmt = format_box.currentData()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт транскрипта",
            export_filename(str(self.document.media["filename"]), fmt),
            f"{fmt.value.upper()} (*.{fmt.value})",
        )
        if path:
            # QFileDialog confirms replacement; writer still protects against unconfirmed races.
            exists = Path(path).exists()
            if (
                exists
                and QMessageBox.question(
                    self, "Замена файла", "Заменить существующий файл экспорта?"
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.export_to(
                Path(path), ExportOptions(fmt, times.isChecked(), roles.isChecked(), exists)
            )

    def _source(self, path: Path) -> None:
        self._media_failed = False
        try:
            with path.open("rb"):
                pass
        except OSError:
            self._media_failed = True
            self.media_info.setText(
                "Исходник недоступен. Текст, правки и экспорт остаются доступны."
            )
            self.player.setSource(QUrl())
            return
        self.media_info.setText(str(path))
        self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))

    def seek(self, milliseconds: int) -> None:
        milliseconds = max(0, int(milliseconds))
        self._pending_seek = milliseconds
        self._position(milliseconds)
        if not self._media_failed:
            self.player.setPosition(milliseconds)
            if self.player.isSeekable():
                self._pending_seek = None

    def _seek_segment(self, index: QModelIndex) -> None:
        row = self.proxy.mapToSource(index).row()
        if row >= 0:
            self.seek(self.model.segments[row].start_ms)

    def _position(self, milliseconds: int) -> None:
        self.position_ms = milliseconds
        self.time_label.setText(timestamp(milliseconds))
        if not self.slider.isSliderDown():
            self.slider.setValue(
                min(1_000_000, milliseconds * 1_000_000 // max(1, self._duration_ms))
            )
        self.model.position(milliseconds)
        if self.follow.isChecked():
            for row in sorted(self.model.active):
                index = self.proxy.mapFromSource(self.model.index(row, 0))
                if index.isValid():
                    self.table.scrollTo(index)
                    break

    def _duration(self, milliseconds: int) -> None:
        if milliseconds > 0:
            self._duration_ms = milliseconds

    def _media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in {QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia}:
            if self._pending_seek is not None and self.player.isSeekable():
                pending, self._pending_seek = self._pending_seek, None
                self.player.setPosition(pending)

    def _media_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        self._media_failed = True
        self.media_info.setText(
            f"Источник или кодек недоступен ({error.name}). Текст и экспорт доступны."
        )
        self._buttons()

    def _tracks(self) -> None:
        # The player uses audio-track ordinals; ffprobe stream indices include video tracks.
        # Do not guess a mapping or silently switch to an unrelated track.
        self.audio_track.blockSignals(True)
        self.audio_track.clear()
        for ordinal, metadata in enumerate(self.player.audioTracks()):
            title = metadata.stringValue(QMediaMetaData.Key.Title)
            language = metadata.stringValue(QMediaMetaData.Key.Language)
            self.audio_track.addItem(
                f"Звук плеера {ordinal + 1} · {title or language or 'без подписи'}"
            )
        self.audio_track.setCurrentIndex(self.player.activeAudioTrack())
        self.audio_track.blockSignals(False)

    def _play(self) -> None:
        if self._media_failed:
            return
        source = Path(self.player.source().toLocalFile())
        if not source.is_file():
            self._media_error(QMediaPlayer.Error.ResourceError, "")
        elif self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _play_state(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText(
            "Ⅱ Пауза" if state == QMediaPlayer.PlaybackState.PlayingState else "▶ Воспроизвести"
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._saving:
            self.info.setText("Дождитесь завершения сохранения.")
            event.ignore()
            return
        if (
            self._dirty
            and QMessageBox.question(
                self, "Несохранённые правки", "Закрыть окно и отбросить несохранённые правки?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            event.ignore()
            return
        self.player.stop()
        self.player.setSource(QUrl())
        event.accept()

    def reject(self) -> None:
        # Escape must use the same dirty/saving guard as the window close button.
        self.close()
