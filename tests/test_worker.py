"""Windows spawn integration with deterministic fake inference and bounded waits."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

from local_transcriber.application.pipeline import PipelineCancelled, PipelineConfig, PipelineRun
from local_transcriber.application.worker_protocol import WorkerCommand, WorkerTask
from local_transcriber.infrastructure.worker_manager import WorkerManager
from local_transcriber.infrastructure.worker_process import WorkerIPCError


class Store:
    def __init__(self):
        self.states = {}
        self.saved = {}

    def prepare(self, path, indices, parameters, resume):
        self.states.setdefault(resume, "PENDING")
        self.saved.setdefault(resume, [])
        return PipelineRun(resume, ())

    def begin(self, job):
        self.states[job] = "PROCESSING"

    def save(self, job, stream, index, start, end, segments):
        self.saved[job].append(index)

    def finish(self, job):
        self.states[job] = "COMPLETED"

    def pause(self, job):
        self.states[job] = "PAUSED"

    def resume(self, job):
        self.states[job] = "PROCESSING"

    def cancel(self, job, stream, index):
        self.states[job] = "CANCELLED"

    def interrupt(self, job):
        if self.states.get(job) not in {"COMPLETED", "CANCELLED"}:
            self.states[job] = "INTERRUPTED"


def fake_executor(task, store, control, cache):
    job = store.prepare(task.path, task.indices, {}, task.resume or task.ticket).id
    store.begin(job)
    if task.path.name == "die":
        os._exit(17)
    for index in range(2):
        try:
            control.checkpoint(job)
            control.emit("CHUNK_ACTIVE", index)
            if index == 0 and task.path.name in {"gate", "cancel", "shutdown"}:
                # Wait for an actual control command, never guess with a sleep.
                with control.condition:
                    deadline = time.monotonic() + 10
                    while not control.pause and not control.is_set():
                        if time.monotonic() >= deadline:
                            raise TimeoutError("test gate")
                        control.condition.wait(0.1)
            if control.is_set():
                raise PipelineCancelled()
            store.save(job, job, index, index * 1000, (index + 1) * 1000, [])
            control.emit("PROGRESS", {"completed": index + 1, "total": 2})
        except PipelineCancelled:
            control.cancelled(job, job, index)
            raise
    control.checkpoint(job)
    store.finish(job)
    return job


def fake_pipeline_executor(task, store, control, cache):
    from test_pipeline import Decoder, Recognizer, Segmenter, media

    from local_transcriber.application.pipeline import TranscriptionPipeline

    class GateEngine(Recognizer):
        def transcribe(self, pcm):
            control.emit("CHUNK_ACTIVE")
            if self.calls == 0 and task.path.name == "gate":
                with control.condition:
                    deadline = time.monotonic() + 10
                    while not control.pause and not control.is_set():
                        if time.monotonic() >= deadline:
                            raise TimeoutError("test gate")
                        control.condition.wait(0.1)
            return super().transcribe(pcm)

    pipeline = TranscriptionPipeline(
        Decoder(), Segmenter(), GateEngine(), store, lambda: "fixture:v1", control=control
    )
    return pipeline.execute(media(), (1,), resume=task.resume)


def child_executor(task, store, control, cache):
    job = store.prepare(task.path, task.indices, {}, task.ticket).id
    store.begin(job)
    process = subprocess.Popen(
        [
            task.ffmpeg_path,
            "-v",
            "error",
            "-re",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=600",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        control.emit("CHILD_PROCESS", process.pid)
        assert control.cancel.wait(10)
        raise PipelineCancelled()
    finally:
        process.terminate()
        process.wait(timeout=5)
        control.cancelled(job, None, None)


def task(mode="fifo", resume=None):
    return WorkerTask(
        uuid4(), Path(mode), (1,), PipelineConfig(), {}, "ffmpeg", "ffprobe", {}, {}, resume
    )


def until(manager, kind, ticket=None, timeout=15):
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        manager.wait(0.1)
        for event in manager.poll():
            seen.append(event)
            if event.kind == kind and (ticket is None or event.ticket == ticket):
                return event, seen
    raise AssertionError(f"Timed out waiting for {kind}: {[x.kind for x in seen]}")


def test_fifo_and_graceful_child_cleanup():
    store = Store()
    manager = WorkerManager(store, executor=fake_executor)
    first, second = task(), task()
    try:
        manager.submit(first)
        manager.submit(second)
        _, events = until(manager, "COMPLETED", second.ticket)
        assert [x.ticket for x in events if x.kind == "STARTED"] == [first.ticket, second.ticket]
        assert store.saved[first.ticket] == store.saved[second.ticket] == [0, 1]
    finally:
        manager.shutdown()
    assert not manager._process.is_alive()


def test_pause_is_deferred_until_checkpoint_then_resume():
    store = Store()
    with WorkerManager(store, executor=fake_executor) as manager:
        item = task("gate")
        manager.submit(item)
        until(manager, "CHUNK_ACTIVE", item.ticket)
        manager.command(WorkerCommand.PAUSE, item.ticket)
        _, events = until(manager, "PAUSED", item.ticket)
        assert any(x.kind == "PAUSE_DEFERRED" for x in events)
        assert store.saved[item.ticket] == [0]
        assert store.states[item.ticket] == "PAUSED"
        manager.command(WorkerCommand.RESUME, item.ticket)
        until(manager, "COMPLETED", item.ticket)
        assert store.saved[item.ticket] == [0, 1]


def test_cancel_discards_current_chunk_and_preserves_fifo():
    store = Store()
    with WorkerManager(store, executor=fake_executor) as manager:
        first, second = task("cancel"), task()
        manager.submit(first)
        manager.submit(second)
        until(manager, "CHUNK_ACTIVE", first.ticket)
        manager.command(WorkerCommand.CANCEL, first.ticket)
        until(manager, "COMPLETED", second.ticket)
        assert store.states[first.ticket] == "CANCELLED"
        assert store.saved[first.ticket] == []
        assert store.saved[second.ticket] == [0, 1]


def test_cancel_queued_resume_never_starts_inference():
    store = Store()
    with WorkerManager(store, executor=fake_executor) as manager:
        first = task("gate")
        prior = uuid4()
        store.states[prior] = "INTERRUPTED"
        queued = task(resume=prior)
        manager.submit(first)
        until(manager, "CHUNK_ACTIVE", first.ticket)
        manager.submit(queued)
        manager.command(WorkerCommand.CANCEL, queued.ticket)
        until(manager, "CANCELLED", queued.ticket)
        assert store.states[prior] == "CANCELLED"
        assert prior not in store.saved
        manager.command(WorkerCommand.CANCEL, first.ticket)
        until(manager, "CANCELLED", first.ticket)


def test_worker_crash_recovery_and_restart():
    store = Store()
    with WorkerManager(store, executor=fake_executor) as manager:
        item = task("die")
        manager.submit(item)
        until(manager, "INTERRUPTED", item.ticket)
        assert store.states[item.ticket] == "INTERRUPTED"
        manager.restart()
        resumed = task(resume=item.ticket)
        manager.submit(resumed)
        until(manager, "COMPLETED", resumed.ticket)
        assert store.states[item.ticket] == "COMPLETED"


def test_worker_startup_failure_notifies_queued_ticket():
    store = Store()
    manager = WorkerManager(store, executor=fake_executor)
    item = task()
    try:
        # Hold dispatch briefly, then simulate death before READY is handled.
        with manager._lock:
            manager.submit(item)
            manager._process.kill()
        until(manager, "INTERRUPTED", item.ticket)
        assert item.ticket not in store.saved
    finally:
        manager.shutdown()


def test_shutdown_during_chunk_is_interrupted():
    store = Store()
    manager = WorkerManager(store, executor=fake_executor)
    item = task("shutdown")
    manager.submit(item)
    until(manager, "CHUNK_ACTIVE", item.ticket)
    manager.shutdown()
    assert store.states[item.ticket] == "INTERRUPTED"
    assert not manager._process.is_alive()


def test_bad_ipc_message_and_closed_command_channel():
    with WorkerManager(Store(), executor=fake_executor) as manager:
        until(manager, "READY")
        manager._commands.put("malformed")
        until(manager, "IPC_ERROR")
        item = task("gate")
        manager.submit(item)
        until(manager, "CHUNK_ACTIVE", item.ticket)
        manager._commands.close()
        with pytest.raises(WorkerIPCError, match="недоступен"):
            manager.command(WorkerCommand.PAUSE, item.ticket)


@pytest.mark.integration
def test_windows_job_object_reaps_ffmpeg_after_worker_kill():
    if os.name != "nt":
        pytest.skip("Windows Job Object regression")
    ffmpeg = shutil.which(os.environ.get("LOCAL_TRANSCRIBER_FFMPEG_PATH", "ffmpeg"))
    if not ffmpeg:
        pytest.skip("requires real FFmpeg")
    import ctypes
    from ctypes import wintypes
    from dataclasses import replace

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    with WorkerManager(Store(), executor=child_executor) as manager:
        item = replace(task(), ffmpeg_path=ffmpeg)
        manager.submit(item)
        child, _ = until(manager, "CHILD_PROCESS", item.ticket)
        handle = kernel.OpenProcess(0x100000, False, child.payload)
        assert handle
        try:
            assert kernel.WaitForSingleObject(handle, 0) == 0x102  # running
            manager._process.kill()
            until(manager, "INTERRUPTED", item.ticket)
            assert kernel.WaitForSingleObject(handle, 5000) == 0
        finally:
            kernel.CloseHandle(handle)
