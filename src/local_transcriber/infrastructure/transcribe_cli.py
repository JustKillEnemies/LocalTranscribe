"""CLI composition root; model and database remain local."""

import json
import sys
import threading
from pathlib import Path
from uuid import UUID

from local_transcriber.application.pipeline import (
    PipelineConfig,
    PipelineError,
)
from local_transcriber.application.transcript import TranscriptService
from local_transcriber.application.worker_protocol import WorkerCommand
from local_transcriber.infrastructure.database.history_store import PostgreSQLHistoryStore
from local_transcriber.infrastructure.database.pipeline_store import PostgreSQLPipelineStore
from local_transcriber.infrastructure.database.session import (
    PersistenceError,
    make_engine,
    session_factory,
)
from local_transcriber.infrastructure.database.text_store import (
    PostgreSQLTranscriptStore,
    TermRepository,
)
from local_transcriber.infrastructure.diagnostics import DiagnosticLog
from local_transcriber.infrastructure.media import MediaInspector
from local_transcriber.infrastructure.settings import load_settings
from local_transcriber.infrastructure.temp_storage import ManagedTempFiles
from local_transcriber.infrastructure.transcription_task import prepare_task
from local_transcriber.infrastructure.worker_manager import WorkerManager
from local_transcriber.infrastructure.worker_process import WorkerIPCError


def run_transcription(
    path: Path,
    *,
    indices: tuple[int, ...],
    env_file: Path | None,
    resume: UUID | None,
    chunk_ms: int,
    overlap_ms: int,
    end_ms: int | None,
    interactive: bool = False,
) -> UUID:
    settings = load_settings(env_file)
    media = MediaInspector(settings.ffprobe_path, timeout=settings.probe_timeout).inspect(path)
    config = PipelineConfig(chunk_ms, overlap_ms, end_ms)
    task = prepare_task(settings, media, indices, config, resume)
    diagnostics = DiagnosticLog(settings.logs_dir)
    database = None
    try:
        database = make_engine(settings)
        store = PostgreSQLPipelineStore(session_factory(database))
        ManagedTempFiles(settings.temp_dir).cleanup(
            protected=PostgreSQLHistoryStore(session_factory(database)).protected_sources(),
            ttl_hours=settings.temp_retention_hours,
        )
        with WorkerManager(store) as manager:
            manager.submit(task)
            if interactive:

                def input_commands() -> None:
                    for line in sys.stdin:
                        kind = {
                            "pause": WorkerCommand.PAUSE,
                            "resume": WorkerCommand.RESUME,
                            "cancel": WorkerCommand.CANCEL,
                        }.get(line.strip().lower())
                        if kind is not None:
                            try:
                                manager.command(kind, task.ticket)
                            except WorkerIPCError:
                                pass

                threading.Thread(target=input_commands, name="cli-commands", daemon=True).start()
            while True:
                try:
                    manager.wait(0.2)
                except KeyboardInterrupt:
                    manager.command(WorkerCommand.CANCEL, task.ticket)
                for event in manager.poll():
                    print(
                        json.dumps(
                            {
                                "status": event.kind,
                                "event": event.name,
                                "job_id": str(event.job_id) if event.job_id else None,
                                "ticket": str(event.ticket) if event.ticket else None,
                                "detail": event.payload,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    if event.ticket != task.ticket:
                        continue
                    if event.kind == "COMPLETED":
                        factory = session_factory(database)
                        text_service = TranscriptService(
                            PostgreSQLTranscriptStore(factory), TermRepository(factory)
                        )
                        readable = text_service.readable(event.job_id)
                        print(
                            json.dumps(
                                {
                                    "status": "TEXT_COMPLETED",
                                    "job_id": str(event.job_id),
                                    "version_id": str(readable.id),
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                        return event.job_id
                    if event.kind in {"ERROR", "INTERRUPTED", "CANCELLED", "IPC_ERROR"}:
                        raise PipelineError(f"Задание {event.job_id or task.ticket}: {event.kind}.")
    except PersistenceError:
        raise
    except WorkerIPCError as error:
        raise PipelineError(str(error)) from None
    finally:
        if database is not None:
            database.dispose()
        diagnostics.close()
