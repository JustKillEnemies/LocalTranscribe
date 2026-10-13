"""Bounded background command actor delivering queued Qt signals to the window."""

import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from local_transcriber.application.desktop import DesktopBackend, DesktopEvent


class DesktopBridge(QObject):
    event = Signal(object)
    closed = Signal()

    def __init__(
        self, factory: Callable[[Path | None], DesktopBackend], env_file: Path | None = None
    ) -> None:
        super().__init__()
        self._factory, self._env_file = factory, env_file
        self._commands: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="desktop-services", daemon=False)

    def start(self) -> None:
        self._thread.start()
        self.submit("refresh")

    def submit(self, command: str, payload: Any = None) -> None:
        if self._stop.is_set():
            return
        try:
            self._commands.put_nowait((command, payload))
        except queue.Full:
            self.event.emit(
                DesktopEvent(
                    "ERROR",
                    "Очередь команд заполнена. Дождитесь текущих операций.",
                    getattr(payload, "request_id", None),
                )
            )

    def request_close(self) -> None:
        self._stop.set()

    def wait_closed(self, timeout: float = 20) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        backend = None
        try:
            while not self._stop.is_set():
                try:
                    command, payload = self._commands.get(timeout=0.05)
                except queue.Empty:
                    command = None
                    payload = None
                try:
                    if command:
                        if backend is None:
                            if command == "settings":
                                self._env_file = payload
                            backend = self._factory(self._env_file)
                            if command == "settings":
                                command = "refresh"
                        for event in backend.execute(command, payload):
                            self.event.emit(event)
                    if backend:
                        for event in backend.poll():
                            self.event.emit(event)
                except Exception as error:
                    from local_transcriber.infrastructure.diagnostics import AuditEvent, audit

                    audit(AuditEvent.OPERATION_FAILED, getattr(payload, "job_id", None))
                    # Known application exceptions contain safe messages; unexpected exceptions
                    # don't expose SQL, settings, raw probe output or transcript via str(error).
                    from local_transcriber.application.export import ExportError
                    from local_transcriber.infrastructure.database.session import PersistenceError
                    from local_transcriber.infrastructure.media import MediaInspectionError
                    from local_transcriber.infrastructure.settings import ConfigurationError
                    from local_transcriber.infrastructure.worker_process import WorkerIPCError

                    if isinstance(
                        error,
                        (
                            PersistenceError,
                            ExportError,
                            MediaInspectionError,
                            ConfigurationError,
                            ValueError,
                            WorkerIPCError,
                        ),
                    ):
                        message = str(error)
                    elif isinstance(error, OSError):
                        message = (
                            "Локальный файл/модель/каталог недоступен. Проверьте пути и права."
                        )
                    else:
                        message = f"Фоновая операция не выполнена ({type(error).__name__})."
                    kind = "CONNECTION_ERROR" if command in {"refresh", "settings"} else "ERROR"
                    self.event.emit(
                        DesktopEvent(kind, message, getattr(payload, "request_id", None))
                    )
        finally:
            if backend:
                try:
                    backend.close()
                except Exception:
                    self.event.emit(
                        DesktopEvent(
                            "ERROR", "Не удалось полностью остановить worker; проверьте журнал."
                        )
                    )
            self.closed.emit()
