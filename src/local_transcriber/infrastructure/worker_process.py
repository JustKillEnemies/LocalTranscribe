"""Spawn entry point: CPU decode/VAD and one cached CUDA model, no SQLAlchemy."""

import gc
import os
import queue
import threading
from collections.abc import Callable
from dataclasses import asdict, replace
from typing import Any
from uuid import UUID

from local_transcriber.application.pipeline import PipelineCancelled, PipelineError
from local_transcriber.application.worker_protocol import (
    Command,
    StoreReply,
    StoreRequest,
    WorkerCommand,
    WorkerEvent,
    WorkerTask,
)


class WorkerIPCError(RuntimeError):
    pass


class RemoteStore:
    """Synchronous bounded RPC; persistence is exclusively executed by the parent."""

    METHODS = frozenset(
        {
            "prepare",
            "plan",
            "ready",
            "begin",
            "save",
            "tail",
            "progress",
            "finish",
            "fail",
            "pause",
            "resume",
            "cancel",
            "interrupt",
        }
    )

    def __init__(self, ticket: UUID, events: Any, replies: Any, timeout: float = 30) -> None:
        self.ticket, self.events, self.replies, self.timeout = ticket, events, replies, timeout
        self.sequence = 0
        self.job_id: UUID | None = None

    def __getattr__(self, method: str) -> Callable[..., Any]:
        if method not in self.METHODS:
            raise AttributeError(method)

        def call(*arguments: Any) -> Any:
            self.sequence += 1
            try:
                self.events.put(
                    StoreRequest(self.sequence, self.ticket, method, arguments),
                    timeout=self.timeout,
                )
                reply = self.replies.get(timeout=self.timeout)
            except queue.Full, queue.Empty, OSError, EOFError:
                raise WorkerIPCError("Worker IPC не отвечает.") from None
            if not isinstance(reply, StoreReply) or reply.sequence != self.sequence:
                raise WorkerIPCError("Нарушен порядок ответов IPC.")
            if reply.error == "CANCELLED":
                raise PipelineCancelled("Задание отменено до сохранения участка.")
            if reply.error:
                raise PipelineError(reply.error)
            if method == "prepare":
                self.job_id = reply.result.id
            return reply.result

        return call


class WorkerControl:
    def __init__(self, events: Any) -> None:
        self.events = events
        self.condition = threading.Condition()
        self.cancel = threading.Event()
        self.pause = False
        self.shutdown = False
        self.ticket: UUID | None = None
        self.store: RemoteStore | None = None

    def emit(self, kind: str, payload: Any = None) -> None:
        job = self.store.job_id if self.store else None
        try:
            self.events.put(WorkerEvent(kind, self.ticket, job, payload), timeout=5)
        except queue.Full, OSError:
            raise WorkerIPCError("Очередь событий IPC недоступна.") from None

    def is_set(self) -> bool:
        return self.cancel.is_set()

    def checkpoint(self, job: UUID) -> None:
        with self.condition:
            if self.cancel.is_set():
                raise PipelineCancelled("Остановлено на контрольной точке.")
            if self.pause:
                self.store.pause(job)
                self.emit("PAUSED")
                while self.pause and not self.cancel.is_set():
                    self.condition.wait(timeout=0.2)
                if self.cancel.is_set():
                    raise PipelineCancelled("Отменено во время паузы.")
                self.store.resume(job)
                self.emit("PROCESSING")

    def cancelled(self, job: UUID, stream: UUID | None, index: int | None) -> None:
        if self.shutdown:
            self.store.interrupt(job)
        else:
            self.store.cancel(job, stream, index)


def worker_main(commands: Any, events: Any, replies: Any, executor: Any = None) -> None:
    """Module-level target is spawn-safe; imports never start a process."""
    if os.name != "nt":
        os.setsid()
    control = WorkerControl(events)
    incoming: queue.Queue[WorkerTask | None] = queue.Queue(maxsize=1)
    stopped = threading.Event()

    def listen() -> None:
        try:
            while not stopped.is_set():
                try:
                    command = commands.get(timeout=0.2)
                except queue.Empty:
                    continue
                if not isinstance(command, Command):
                    control.emit("IPC_ERROR", "Неверная команда IPC.")
                    continue
                with control.condition:
                    if command.kind == WorkerCommand.START:
                        if command.task is None:
                            control.emit("IPC_ERROR", "START не содержит задания.")
                            continue
                        control.ticket = command.ticket
                        control.pause = False
                        control.cancel.clear()
                        incoming.put(command.task, timeout=5)
                    elif command.kind == WorkerCommand.SHUTDOWN:
                        control.shutdown = True
                        control.cancel.set()
                        control.condition.notify_all()
                        try:
                            incoming.put_nowait(None)
                        except queue.Full:
                            pass
                        return
                    elif command.ticket == control.ticket:
                        if command.kind == WorkerCommand.PAUSE:
                            control.pause = True
                            control.emit("PAUSE_DEFERRED")
                        elif command.kind == WorkerCommand.RESUME:
                            control.pause = False
                            control.condition.notify_all()
                        elif command.kind == WorkerCommand.CANCEL:
                            control.cancel.set()
                            control.condition.notify_all()
        except Exception:
            control.cancel.set()
            control.shutdown = True
            try:
                control.emit("IPC_ERROR", "Канал команд worker прерван.")
            except WorkerIPCError:
                pass

    listener = threading.Thread(target=listen, name="worker-control", daemon=True)
    listener.start()
    cache: dict[str, Any] = {}
    events.put(WorkerEvent("READY"), timeout=5)
    try:
        while not control.shutdown:
            try:
                task = incoming.get(timeout=0.2)
            except queue.Empty:
                continue
            if task is None:
                break
            control.store = RemoteStore(task.ticket, events, replies)
            try:
                control.emit("STARTED")
                result = (executor or execute_task)(task, control.store, control, cache)
                control.emit("COMPLETED", str(result))
            except PipelineCancelled:
                control.emit("INTERRUPTED" if control.shutdown else "CANCELLED")
            except Exception as error:
                message = (
                    str(error)
                    if isinstance(error, PipelineError)
                    else f"Worker: {type(error).__name__}; доступно возобновление."
                )
                control.emit("ERROR", message[:2000])
            finally:
                with control.condition:
                    control.store = None
                    if control.ticket == task.ticket:
                        control.ticket = None
    finally:
        stopped.set()
        listener.join(timeout=1)


def execute_task(task: WorkerTask, store: RemoteStore, control: WorkerControl, cache: dict) -> UUID:
    # All ML imports and the FFmpeg child belong to the spawned worker.
    from local_transcriber.application.pipeline import TranscriptionPipeline
    from local_transcriber.infrastructure.faster_whisper_engine import (
        FasterWhisperConfig,
        FasterWhisperEngine,
    )
    from local_transcriber.infrastructure.ffmpeg_decoder import FFmpegMediaDecoder
    from local_transcriber.infrastructure.media import MediaInspector, media_fingerprint
    from local_transcriber.infrastructure.silero_segmenter import (
        SegmentationConfig,
        SileroSpeechSegmenter,
    )

    model_config = FasterWhisperConfig(**task.model_config)
    if cache.get("model_config") != model_config:
        # Release the old CUDA owner before constructing a different model.
        cache.clear()
        gc.collect()
        cache.update(model_config=model_config, engine=FasterWhisperEngine(model_config))
        control.emit(
            "MODEL_SELECTED", {"model": model_config.model_name, "device": model_config.device}
        )
    media = MediaInspector(task.ffprobe_path, timeout=30).inspect(task.path)
    engine = cache["engine"]
    decoder = FFmpegMediaDecoder(task.ffmpeg_path)
    audio = task.parameters.get("intermediate_audio", {})
    if audio.get("enabled"):
        from pathlib import Path

        from local_transcriber.infrastructure.intermediate_audio import RecordingDecoder
        from local_transcriber.infrastructure.temp_storage import ManagedTempFiles

        managed = ManagedTempFiles(Path(audio["directory"]).parent)
        decoder = RecordingDecoder(
            decoder,
            lambda: Path(audio["directory"]) / str(store.job_id),
            managed=managed,
            job_id=lambda: store.job_id,
        )
    pipeline = TranscriptionPipeline(
        decoder,
        SileroSpeechSegmenter(SegmentationConfig(**task.vad_config)),
        engine,
        store,
        lambda: media_fingerprint(media.path),
        config=task.config,
        parameters=task.parameters,
        control=control,
        engine_signature=asdict(replace(engine.info, compute_type=model_config.compute_type)),
        on_progress=lambda job, total, completed: control.emit(
            "PROGRESS", {"total": total, "completed": completed}
        ),
    )
    return pipeline.execute(media, task.indices, resume=task.resume)
