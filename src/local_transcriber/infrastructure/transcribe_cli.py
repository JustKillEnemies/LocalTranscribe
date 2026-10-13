"""CLI composition root; model and database remain local."""

import json
import logging
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path
from uuid import UUID

from local_transcriber.application.pipeline import (
    PipelineConfig,
    PipelineError,
    TranscriptionPipeline,
)
from local_transcriber.infrastructure.database.pipeline_store import PostgreSQLPipelineStore
from local_transcriber.infrastructure.database.session import (
    PersistenceError,
    make_engine,
    session_factory,
)
from local_transcriber.infrastructure.faster_whisper_engine import (
    FasterWhisperConfig,
    FasterWhisperEngine,
)
from local_transcriber.infrastructure.ffmpeg_decoder import FFmpegMediaDecoder
from local_transcriber.infrastructure.media import MediaInspector, media_fingerprint
from local_transcriber.infrastructure.settings import load_settings
from local_transcriber.infrastructure.silero_segmenter import (
    SegmentationConfig,
    SileroSpeechSegmenter,
)


def run_transcription(
    path: Path,
    *,
    indices: tuple[int, ...],
    env_file: Path | None,
    resume: UUID | None,
    chunk_ms: int,
    overlap_ms: int,
    end_ms: int | None,
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
        pipeline = TranscriptionPipeline(
            FFmpegMediaDecoder(settings.ffmpeg_path),
            SileroSpeechSegmenter(vad_cfg),
            FasterWhisperEngine(model_cfg),
            PostgreSQLPipelineStore(session_factory(database)),
            lambda: media_fingerprint(media.path),
            config=config,
            parameters=parameters,
            on_progress=lambda job, total, complete: print(
                json.dumps(
                    {
                        "job_id": str(job),
                        "completed_chunks": complete,
                        "total_chunks": total,
                    }
                ),
                flush=True,
            ),
        )
        result = pipeline.execute(media, indices, resume=resume)
        print(json.dumps({"job_id": str(result), "status": "COMPLETED"}))
        return result
    except PersistenceError:
        raise
    finally:
        if database is not None:
            database.dispose()
        logger.removeHandler(handler)
        handler.close()
