"""CLI composition root; model and database remain local."""

import json
import logging
import sys
import threading
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path
from uuid import UUID, uuid4

from local_transcriber.application.pipeline import (
    PipelineConfig,
    PipelineError,
)
from local_transcriber.application.transcript import TranscriptService
from local_transcriber.application.worker_protocol import WorkerCommand, WorkerTask
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
from local_transcriber.infrastructure.faster_whisper_engine import (
    FasterWhisperConfig,
)
from local_transcriber.infrastructure.media import MediaInspector, media_fingerprint
from local_transcriber.infrastructure.settings import load_settings
from local_transcriber.infrastructure.silero_segmenter import (
    SegmentationConfig,
)
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
    if not set(indices) <= {stream.stream_index for stream in media.audio_streams}:
        raise PipelineError("Выбранная аудиодорожка отсутствует.")
    model_cfg = replace(FasterWhisperConfig.from_settings(settings), word_timestamps=True)
    if not model_cfg.model_path.is_dir():
        raise PipelineError("Локальная модель не найдена; автоматическая загрузка отключена.")
    vad_cfg = SegmentationConfig.from_settings(settings)
    if vad_cfg.enabled and config.overlap_ms < vad_cfg.min_silence_ms + vad_cfg.padding_ms:
        raise PipelineError(
            "Overlap должен покрывать min_silence_ms + padding_ms для выбранного VAD."
        )
    # Bind configuration and local model identity, not mutable effective fallback state.
    parameters = {
        "vad": asdict(vad_cfg),
        "model_config": json.loads(json.dumps(asdict(model_cfg), default=str)),
        "model_files": {
            name: media_fingerprint(model_cfg.model_path / name)
            for name in ("model.bin", "config.json", "tokenizer.json")
        },
        "runtime": {name: version(name) for name in ("faster-whisper", "ctranslate2")},
    }
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(settings.logs_dir / "pipeline-errors.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("local_transcriber.application.pipeline")
    logger.addHandler(handler)
    database = None
    try:
        database = make_engine(settings)
        store = PostgreSQLPipelineStore(session_factory(database))
        task = WorkerTask(
            uuid4(),
            media.path,
            indices,
            config,
            parameters,
            settings.ffmpeg_path,
            settings.ffprobe_path,
            asdict(model_cfg),
            asdict(vad_cfg),
            resume,
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
        logger.removeHandler(handler)
        handler.close()
