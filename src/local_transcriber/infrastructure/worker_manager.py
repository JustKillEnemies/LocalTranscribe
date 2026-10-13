"""Asynchronous parent supervisor: FIFO scheduling and serialized persistence/RPC."""

import logging
import multiprocessing as mp
import queue
import threading
from collections import deque
from typing import Any, Self
from uuid import UUID

from local_transcriber.application.pipeline import PipelineError
from local_transcriber.application.worker_protocol import (
    Command,
    StoreReply,
    StoreRequest,
    WorkerCommand,
    WorkerEvent,
    WorkerTask,
)
from local_transcriber.infrastructure.process_job import ProcessJob
from local_transcriber.infrastructure.worker_process import RemoteStore, WorkerIPCError, worker_main


class WorkerManager:
    """submit/control/poll do not run inference or SQL on the caller/UI thread."""

    def __init__(self, store: Any, *, executor: Any = None, queue_capacity: int = 16) -> None:
        if not 1 <= queue_capacity <= 64:
            raise ValueError("Worker queue capacity must be 1–64")
        self.store, self.executor, self.capacity = store, executor, queue_capacity
        self._lock = threading.RLock()
        self._events: deque[WorkerEvent] = deque(maxlen=128)
        self._pending: deque[WorkerTask] = deque()
        self._pending_stops: deque[tuple[str, WorkerTask]] = deque()
        self._active: WorkerTask | None = None
        self._job: UUID | None = None
        self._cancel_mode: str | None = None
        self._ready = False
        self._closing = False
        self._accepting = True
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._process = None
        self._job_object = None
        self._start_process()
        self._thread = threading.Thread(target=self._serve, name="worker-supervisor", daemon=True)
        self._thread.start()

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    def _start_process(self) -> None:
        context = mp.get_context("spawn")
        self._commands = context.Queue(maxsize=self.capacity)
        self._incoming = context.Queue(maxsize=self.capacity)
        self._replies = context.Queue(maxsize=self.capacity)
        self._process = context.Process(
            target=worker_main,
            args=(self._commands, self._incoming, self._replies, self.executor),
            name="local-transcriber-gpu",
        )
        self._process.start()
        try:
            self._job_object = ProcessJob(self._process.pid)
        except Exception:
            self._process.terminate()
            self._process.join(timeout=5)
            self._close_queues()
            raise
        self._ready = False
        self._accepting = True

    def submit(self, task: WorkerTask) -> UUID:
        with self._lock:
            if self._closing or not self._accepting or not self._process.is_alive():
                raise WorkerIPCError("Worker недоступен; выполните restart.")
            if len(self._pending) >= self.capacity:
                raise WorkerIPCError("FIFO очередь заданий заполнена.")
            if (self._active and self._active.ticket == task.ticket) or any(
                x.ticket == task.ticket for x in self._pending
            ):
                raise ValueError("Duplicate task ticket")
            self._pending.append(task)
            self._emit(WorkerEvent("QUEUED", task.ticket, task.resume))
            self._wake.set()
        return task.ticket

    def command(self, kind: WorkerCommand, ticket: UUID | None = None) -> None:
        with self._lock:
            if kind == WorkerCommand.START:
                raise ValueError("Use submit for START")
            if kind == WorkerCommand.SHUTDOWN:
                raise ValueError("Use shutdown")
            if kind == WorkerCommand.CANCEL:
                for task in tuple(self._pending):
                    if task.ticket == ticket:
                        if len(self._pending_stops) >= self.capacity:
                            raise WorkerIPCError("Очередь команд остановки заполнена.")
                        self._pending.remove(task)
                        self._pending_stops.append(("CANCELLED", task))
                        self._wake.set()
                        return
                self._cancel_mode = (
                    "CANCELLED"
                    if self._active and self._active.ticket == ticket
                    else self._cancel_mode
                )
            if not self._active or self._active.ticket != ticket:
                raise WorkerIPCError("Команда не относится к активному заданию.")
            self._send(Command(kind, ticket))

    def poll(self) -> list[WorkerEvent]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def _emit(self, event: WorkerEvent) -> None:
        with self._lock:
            self._events.append(event)
        self._wake.set()

    def wait(self, timeout: float = 0.2) -> None:
        self._wake.wait(timeout)
        self._wake.clear()

    def _send(self, command: Command) -> None:
        try:
            self._commands.put_nowait(command)
        except queue.Full, OSError, ValueError:
            raise WorkerIPCError("Канал команд worker недоступен.") from None

    def _serve(self) -> None:
        while not self._stop.is_set():
            # Pending jobs never enter inference; update their persisted resume state off the UI thread.
            with self._lock:
                stopping = self._pending_stops.popleft() if self._pending_stops else None
            if stopping:
                kind, task = stopping
                try:
                    if task.resume:
                        if kind == "CANCELLED":
                            self.store.cancel(task.resume, None, None)
                        else:
                            self.store.interrupt(task.resume)
                    self._emit(WorkerEvent(kind, task.ticket, task.resume))
                except Exception:
                    self._emit(
                        WorkerEvent(
                            "ERROR",
                            task.ticket,
                            task.resume,
                            "Не удалось сохранить остановку queued job.",
                        )
                    )
                self._wake.set()
                continue
            try:
                message = self._incoming.get(timeout=0.05)
            except queue.Empty:
                message = None
            except OSError, ValueError, EOFError:
                self._recover("Ошибка канала IPC.")
                return
            try:
                if not self._process.is_alive():
                    if isinstance(message, WorkerEvent):
                        self._handle_event(message)
                    # Drain terminal notifications, but never save stale RPC after worker death.
                    for _ in range(self.capacity):
                        try:
                            pending = self._incoming.get_nowait()
                        except queue.Empty:
                            break
                        if isinstance(pending, WorkerEvent):
                            self._handle_event(pending)
                    self._recover("Worker аварийно завершился.")
                    self._wake.set()
                    return
                if isinstance(message, StoreRequest):
                    self._store_call(message)
                elif isinstance(message, WorkerEvent):
                    self._handle_event(message)
                elif message is not None:
                    self._recover("Неверное сообщение IPC.")
                    return
                with self._lock:
                    if self._ready and self._active is None and self._pending and not self._closing:
                        self._active = self._pending.popleft()
                        self._job = self._active.resume
                        self._cancel_mode = None
                        self._send(Command(WorkerCommand.START, self._active.ticket, self._active))
            except Exception:
                self._recover("Операция IPC или сохранения не выполнена.")
                return
            if message is not None:
                self._wake.set()

    def _store_call(self, request: StoreRequest) -> None:
        if not self._active or request.ticket != self._active.ticket:
            return
        result, error = None, None
        try:
            if request.method not in RemoteStore.METHODS:
                raise ValueError("Unknown RPC")
            if request.method == "save":
                segments = request.arguments[-1]
                if len(segments) > 50_000 or sum(len(x.text) for x in segments) > 1_000_000:
                    raise ValueError("Result batch too large")
            mode = self._cancel_mode
            if mode and request.method in {"save", "finish"}:
                if mode == "INTERRUPTED":
                    self.store.interrupt(request.arguments[0])
                else:
                    self.store.cancel(request.arguments[0], None, None)
                error = "CANCELLED"
            else:
                result = getattr(self.store, request.method)(*request.arguments)
                if request.method == "save":
                    self._emit(
                        WorkerEvent(
                            "CHUNK_COMPLETED",
                            request.ticket,
                            self._job,
                            {"chunk_index": request.arguments[2]},
                        )
                    )
                if request.method == "prepare":
                    self._job = result.id
                    self._emit(WorkerEvent("JOB_CREATED", request.ticket, self._job))
        except Exception as exception:
            error = (
                str(exception)
                if isinstance(exception, PipelineError)
                else f"Операция {request.method} не выполнена: {type(exception).__name__}."
            )
        self._replies.put(StoreReply(request.sequence, result, error), timeout=5)

    def _handle_event(self, event: WorkerEvent) -> None:
        if event.kind in {"ERROR", "INTERRUPTED", "IPC_ERROR"}:
            logging.getLogger("local_transcriber.application.pipeline").error(
                "worker_event kind=%s job_id=%s ticket=%s", event.kind, event.job_id, event.ticket
            )
        if event.kind == "READY":
            self._ready = True
        if event.kind in {"COMPLETED", "CANCELLED", "INTERRUPTED", "ERROR"}:
            if self._active and event.ticket == self._active.ticket:
                if event.kind == "ERROR" and self._job:
                    self.store.interrupt(self._job)
                self._active, self._job = None, None
        self._emit(event)

    def _recover(self, message: str) -> None:
        with self._lock:
            self._accepting = False
            self._pending_stops.extend(("INTERRUPTED", task) for task in self._pending)
            self._pending.clear()
        while self._pending_stops:
            kind, task = self._pending_stops.popleft()
            if task.resume:
                try:
                    if kind == "CANCELLED":
                        self.store.cancel(task.resume, None, None)
                    else:
                        self.store.interrupt(task.resume)
                except Exception:
                    kind = "ERROR"
            self._emit(WorkerEvent(kind, task.ticket, task.resume))
        if self._active:
            logging.getLogger("local_transcriber.application.pipeline").error(
                "worker_recovery job_id=%s ticket=%s", self._job, self._active.ticket
            )
            if self._job:
                try:
                    self.store.interrupt(self._job)
                except Exception:
                    message += (
                        " БД недоступна; требуется recovery после восстановления подключения."
                    )
            self._emit(WorkerEvent("INTERRUPTED", self._active.ticket, self._job, message))
            self._active, self._job = None, None
        if self._process.is_alive():
            self._process.terminate()
        self._process.join(timeout=2)
        if self._job_object:
            self._job_object.close()
        self._ready = False

    def restart(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise WorkerIPCError("Supervisor ещё завершает операцию БД.")
        with self._lock:
            self._recover("Worker перезапущен.")
            self._close_queues()
            self._stop.clear()
            self._start_process()
        self._thread = threading.Thread(target=self._serve, name="worker-supervisor", daemon=True)
        self._thread.start()

    def shutdown(self, timeout: float = 10) -> None:
        with self._lock:
            self._closing = True
            for task in self._pending:
                self._pending_stops.append(("INTERRUPTED", task))
            self._pending.clear()
            self._cancel_mode = "INTERRUPTED"
            if self._process.is_alive():
                try:
                    self._send(Command(WorkerCommand.SHUTDOWN))
                except WorkerIPCError:
                    self._process.terminate()
        self._process.join(timeout=timeout)
        self._stop.set()
        self._thread.join(timeout=5)
        with self._lock:
            self._recover("Worker остановлен.")
            self._close_queues()

    def _close_queues(self) -> None:
        for channel in (self._commands, self._incoming, self._replies):
            channel.cancel_join_thread()
            channel.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args) -> None:
        self.shutdown()
