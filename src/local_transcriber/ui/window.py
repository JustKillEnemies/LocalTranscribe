"""Russian desktop import/job window. All widgets stay on the Qt main thread."""

import time
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from local_transcriber.application.desktop import (
    DesktopEvent,
    DesktopRecord,
    JobChoices,
    available_actions,
)
from local_transcriber.application.maintenance import DeleteSession
from local_transcriber.ui.bridge import DesktopBridge


def duration(ms: int) -> str:
    seconds = max(0, ms) // 1000
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def status_text(status: str) -> str:
    return {
        "IMPORTED": "Готова к запуску",
        "PENDING": "В очереди",
        "ANALYZING": "Подготовка",
        "PROCESSING": "Распознавание",
        "PAUSED": "Приостановлено",
        "INTERRUPTED": "Прервано",
        "COMPLETED": "Завершено",
        "FAILED": "Ошибка",
        "CANCELLED": "Отменено",
    }.get(status, status)


class MainWindow(QMainWindow):
    def __init__(self, bridge: DesktopBridge) -> None:
        super().__init__()
        self.bridge = bridge
        self.records = {}
        self._received_at = {}
        self.queued = set()
        self.connected = False
        self._selected = None
        self._can_close = False
        self._closing = False
        self._result_windows = {}
        self.setWindowTitle("LocalTranscribe — локальная транскрибация")
        self.resize(1180, 760)
        self.setMinimumSize(880, 600)
        self.setAcceptDrops(True)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 16)
        heading = QLabel("LocalTranscribe")
        heading.setStyleSheet("font-size: 23px; font-weight: 600;")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Аудио и видео обрабатываются на вашем компьютере"))
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Добавить записи…")
        self.refresh_button = QPushButton("Обновить подключение")
        self.settings_button = QPushButton("Выбрать .env…")
        self.result_button = QPushButton("Открыть транскрипт")
        self.delete_button = QPushButton("Удалить историю…")
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addWidget(self.result_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addStretch()
        toolbar.addWidget(self.settings_button)
        layout.addLayout(toolbar)
        self.connection_label = QLabel("Подключение к PostgreSQL…")
        self.connection_label.setWordWrap(True)
        self.connection_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.connection_label)
        split = QSplitter()
        layout.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.addWidget(QLabel("Записи — перетащите сюда один или несколько файлов"))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Запись", "Длительность", "Состояние", "%", "Модель", "Время"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        left_layout.addWidget(self.table)
        self.details = QLabel("Выберите запись для настройки задания.")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        left_layout.addWidget(self.details)
        split.addWidget(left)
        right = QWidget()
        controls = QVBoxLayout(right)
        self.streams = QTableWidget(0, 6)
        self.streams.setHorizontalHeaderLabels(["✓", "Поток", "Кодек", "Каналы", "Гц", "Роль"])
        self.streams.verticalHeader().hide()
        self.streams.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.streams.setMinimumHeight(145)
        self.streams.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for column, width in enumerate((28, 46, 62, 54, 66)):
            self.streams.setColumnWidth(column, width)
        controls.addWidget(QLabel("Аудиодорожки · раздельная обработка"))
        controls.addWidget(self.streams)
        self.job_settings = QGroupBox("Распознавание")
        form = QFormLayout(self.job_settings)
        self.model = QComboBox()
        self.model.addItems(["large-v3-turbo", "medium", "large-v3"])
        self.device = QComboBox()
        self.device.addItem("NVIDIA GPU (CUDA)", "cuda")
        self.device.addItem("CPU", "cpu")
        self.quality = QComboBox()
        self.device.currentIndexChanged.connect(self._quality_options)
        self._quality_options()
        self.vad = QCheckBox("Пропускать тишину (Silero VAD)")
        self.vad.setChecked(True)
        self.keep_audio = QCheckBox("Сохранять промежуточное аудио")
        form.addRow("Модель", self.model)
        form.addRow("Язык", QLabel("Русский (ru)"))
        form.addRow("Устройство", self.device)
        form.addRow("Качество", self.quality)
        form.addRow(self.vad)
        form.addRow(self.keep_audio)
        controls.addWidget(self.job_settings)
        row = QHBoxLayout()
        self.start_button = QPushButton("Запустить")
        self.pause_button = QPushButton("Пауза")
        self.resume_button = QPushButton("Продолжить")
        self.cancel_button = QPushButton("Отменить")
        for button in (
            self.start_button,
            self.pause_button,
            self.resume_button,
            self.cancel_button,
        ):
            row.addWidget(button)
        controls.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        controls.addWidget(self.progress)
        self.activity = QLabel("Выберите запись и параметры распознавания.")
        self.activity.setWordWrap(True)
        self.activity.setTextFormat(Qt.TextFormat.PlainText)
        controls.addWidget(self.activity)
        self.disk = QLabel("Рабочий каталог: проверка…")
        self.disk.setWordWrap(True)
        self.disk.setTextFormat(Qt.TextFormat.PlainText)
        controls.addWidget(self.disk)
        controls.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right)
        scroll.setMinimumWidth(430)
        split.addWidget(scroll)
        split.setSizes([670, 460])
        layout.addWidget(QLabel("Диагностика и ошибки"))
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setMaximumBlockCount(200)
        self.errors.setMaximumHeight(100)
        layout.addWidget(self.errors)
        self.add_button.clicked.connect(self._choose_files)
        self.refresh_button.clicked.connect(lambda: self.bridge.submit("refresh"))
        self.settings_button.clicked.connect(self._choose_env)
        self.result_button.clicked.connect(self._open_result)
        self.delete_button.clicked.connect(self._delete_history)
        self.table.itemSelectionChanged.connect(self._selection)
        self.start_button.clicked.connect(self._start)
        for button, command in (
            (self.pause_button, "pause"),
            (self.resume_button, "resume"),
            (self.cancel_button, "cancel"),
        ):
            button.clicked.connect(lambda checked=False, c=command: self._control(c))
        self.bridge.event.connect(self._event, Qt.ConnectionType.QueuedConnection)
        self.bridge.closed.connect(self._closed, Qt.ConnectionType.QueuedConnection)
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._update_time)
        self._clock.start(1000)
        self._buttons()

    def _quality_options(self) -> None:
        self.quality.clear()
        for title, value in (
            [("Точность (float16)", "float16"), ("Меньше VRAM (int8_float16)", "int8_float16")]
            if self.device.currentData() == "cuda"
            else [("Точность (float32)", "float32"), ("Меньше RAM (int8)", "int8")]
        ):
            self.quality.addItem(title, value)

    def import_paths(self, paths: Sequence[Path]) -> None:
        for path in paths:
            self.bridge.submit("import", path)

    def _choose_files(self) -> None:
        from pathlib import Path

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите аудио или видео",
            "",
            "Медиа (*.mkv *.mp4 *.mov *.wav *.mp3 *.m4a *.flac *.webm)",
        )
        self.import_paths([Path(path) for path in files])

    def _choose_env(self) -> None:
        from pathlib import Path

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Локальные настройки PostgreSQL и каталогов",
            "",
            "Файл настроек (*.env);;Все файлы (*)",
        )
        if path:
            self.bridge.submit("settings", Path(path))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        from pathlib import Path

        if all(url.isLocalFile() for url in event.mimeData().urls()):
            self.import_paths([Path(url.toLocalFile()) for url in event.mimeData().urls()])
            event.acceptProposedAction()

    @Slot(object)
    def _event(self, event: DesktopEvent) -> None:
        if event.kind == "CONNECTED":
            self.connected = True
            self.connection_label.setText("PostgreSQL подключена · история и настройки доступны")
            self.model.setCurrentText(event.value.model_name)
            self.device.setCurrentIndex(0 if event.value.device == "cuda" else 1)
            quality_index = self.quality.findData(event.value.compute_type)
            if quality_index >= 0:
                self.quality.setCurrentIndex(quality_index)
            self.vad.setChecked(event.value.vad_enabled)
        elif event.kind == "CONNECTION_ERROR":
            self.connected = False
            self.connection_label.setText(
                "PostgreSQL недоступна. Проверьте локальный .env и миграции, затем обновите подключение."
            )
            self.errors.appendPlainText(str(event.value))
        elif event.kind == "RECORDS":
            for record in event.value:
                self._record(record)
        elif event.kind == "RECORD":
            self._record(event.value)
        elif event.kind == "REMOVED":
            self.records.pop(event.value, None)
            self._received_at.pop(event.value, None)
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == event.value:
                    self.table.removeRow(row)
                    break
            if self._selected == event.value:
                self._selected = None
            if self.table.rowCount():
                self.table.selectRow(0)
                self._selection()
            else:
                self._selected = None
                self.streams.setRowCount(0)
                self.details.setText("История пуста. Исходные записи сохранены.")
                self.progress.setValue(0)
        elif event.kind == "QUEUED":
            self.queued.add(event.value)
        elif event.kind == "DEQUEUED":
            self.queued.discard(event.value)
        elif event.kind in {"ERROR", "INFO"}:
            self.activity.setText(str(event.value))
            if event.kind == "ERROR":
                self.errors.appendPlainText(str(event.value))
        elif event.kind == "DISK":
            self.disk.setText(
                f"Свободно: {event.value['free'] / 1024**3:.1f} ГБ\n{event.value['path']}"
            )
            self.statusBar().showMessage(
                f"Рабочий диск: свободно {event.value['free'] / 1024**3:.1f} ГБ"
            )
        self._buttons()

    def _record(self, record: DesktopRecord) -> None:
        old = self.records.get(record.id)
        self.records[record.id] = record
        self._received_at[record.id] = time.monotonic()
        row = next(
            (
                i
                for i in range(self.table.rowCount())
                if self.table.item(i, 0).data(Qt.ItemDataRole.UserRole) == record.id
            ),
            None,
        )
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
        values = (
            record.media.filename,
            duration(record.media.duration_ms),
            status_text(record.status),
            f"{record.progress:.0f}",
            record.model,
            duration(record.elapsed_ms),
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, record.id)
                item.setToolTip(str(record.media.path))
            self.table.setItem(row, column, item)
        if self._selected == record.id:
            if old is None or old.roles != record.roles or old.media != record.media:
                self._details(record)
            self.progress.setValue(round(record.progress))
            if record.error:
                self.activity.setText(record.error)
            else:
                self.activity.setText(
                    f"{status_text(record.status)} · время {duration(record.elapsed_ms)}"
                )
        if self.table.currentRow() < 0:
            self.table.selectRow(row)

    def _selection(self) -> None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return
        key = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if key in self.records and key != self._selected:
            self._selected = key
            self._details(self.records[key])
        self._buttons()

    def _update_time(self) -> None:
        for row in range(self.table.rowCount()):
            key = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            record = self.records.get(key)
            if record and record.status in {"ANALYZING", "PROCESSING"}:
                elapsed = record.elapsed_ms + int(
                    (time.monotonic() - self._received_at[key]) * 1000
                )
                self.table.item(row, 5).setText(duration(elapsed))

    def _details(self, record: DesktopRecord) -> None:
        self.details.setText(
            f"{record.media.path}\n{record.media.container} · {record.media.size_bytes / 1024**3:.2f} ГБ · {len(record.media.audio_streams)} аудиопотока"
        )
        self.streams.setRowCount(len(record.media.audio_streams))
        selected = record.parameters.get("stream_indices", ())
        roles = dict(record.roles)
        for row, stream in enumerate(record.media.audio_streams):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(
                Qt.CheckState.Checked
                if stream.stream_index in selected or (not selected and row == 0)
                else Qt.CheckState.Unchecked
            )
            self.streams.setItem(row, 0, check)
            for column, value in enumerate(
                (stream.stream_index, stream.codec, stream.channels, stream.sample_rate), 1
            ):
                item = QTableWidgetItem(str(value))
                item.setToolTip(f"Язык: {stream.language or 'не указан'}; {stream.title or ''}")
                self.streams.setItem(row, column, item)
            role = QComboBox()
            role.setEditable(True)
            for text, value in (
                ("Без подписи", ""),
                ("Я", "Я"),
                ("Собеседник", "Собеседник"),
                ("Неизвестный", "Неизвестный"),
            ):
                role.addItem(text, value)
            if roles.get(stream.stream_index):
                role.setCurrentText(roles[stream.stream_index])
            self.streams.setCellWidget(row, 5, role)
        self.progress.setValue(round(record.progress))
        self.activity.setText(record.error or status_text(record.status))

    def _buttons(self) -> None:
        record = self.records.get(self._selected)
        actions = (
            available_actions(
                record.status, queued=record.id in self.queued and record.status == "PENDING"
            )
            if record
            else (False,) * 4
        )
        for button, enabled in zip(
            (self.start_button, self.pause_button, self.resume_button, self.cancel_button),
            actions,
            strict=True,
        ):
            button.setEnabled(enabled and self.connected and not self._closing)
        self.add_button.setEnabled(self.connected and not self._closing)
        self.job_settings.setEnabled(bool(record) and actions[0] and not self._closing)
        self.streams.setEnabled(bool(record) and actions[0] and not self._closing)
        self.settings_button.setEnabled(
            not self.queued and not self._result_windows and not self._closing
        )
        self.result_button.setEnabled(
            bool(record and record.job_id and record.status == "COMPLETED")
            and self.connected
            and not self._closing
        )
        self.delete_button.setEnabled(
            bool(
                record
                and record.id not in self.queued
                and record.status not in {"PENDING", "ANALYZING", "PROCESSING", "PAUSED"}
            )
            and self.connected
            and not self._closing
            and not self._result_windows
        )

    def _delete_history(self) -> None:
        if self._selected is None:
            return
        identifier = self._selected
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Удаление истории")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(
            "Удалить все задания, сегменты и версии этой записи? Исходный аудио/видеофайл сохраняется."
        )
        checkbox = QCheckBox("Также удалить зарегистрированное промежуточное аудио приложения")
        dialog.setCheckBox(checkbox)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        if dialog.exec() == QMessageBox.StandardButton.Yes:
            self.bridge.submit(
                "delete_session", DeleteSession(identifier, True, checkbox.isChecked())
            )

    def _open_result(self) -> None:
        from local_transcriber.ui.results import ResultsWindow

        record = self.records.get(self._selected)
        if record is None or record.job_id is None:
            return
        window = self._result_windows.get(record.job_id)
        if window is None:
            window = ResultsWindow(self.bridge, record.job_id, self)
            self._result_windows[record.job_id] = window
            window.finished.connect(lambda result, key=record.job_id: self._forget_result(key))
        window.show()
        self._buttons()
        window.raise_()
        window.activateWindow()

    def _forget_result(self, key) -> None:
        window = self._result_windows.pop(key, None)
        if window:
            window.deleteLater()
        self._buttons()

    def _start(self) -> None:
        record = self.records.get(self._selected)
        if record is None:
            return
        indices, roles = [], []
        for row, stream in enumerate(record.media.audio_streams):
            if self.streams.item(row, 0).checkState() == Qt.CheckState.Checked:
                indices.append(stream.stream_index)
                combo = self.streams.cellWidget(row, 5)
                text = combo.currentText()
                label = (
                    combo.currentData()
                    if combo.currentIndex() >= 0 and text == combo.itemText(combo.currentIndex())
                    else text
                )
                roles.append((stream.stream_index, label or ""))
        try:
            choices = JobChoices(
                tuple(indices),
                tuple(roles),
                self.model.currentText(),
                self.quality.currentData(),
                self.device.currentData(),
                self.vad.isChecked(),
                self.keep_audio.isChecked(),
            )
            self.bridge.submit("start", (record.id, choices))
        except ValueError as error:
            self.errors.appendPlainText(str(error))

    def _control(self, command: str) -> None:
        if self._selected is not None:
            self.bridge.submit(command, self._selected)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._can_close:
            event.accept()
        else:
            event.ignore()
            for window in tuple(self._result_windows.values()):
                if not window.close():
                    return
            self._closing = True
            self.activity.setText("Остановка worker и сохранение состояния…")
            self._buttons()
            self.bridge.request_close()

    @Slot()
    def _closed(self) -> None:
        self._can_close = True
        self.close()
