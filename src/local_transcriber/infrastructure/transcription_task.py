"""Shared offline task composition for CLI and hardware benchmarks."""

import json
from dataclasses import asdict, replace
from importlib.metadata import version
from uuid import UUID, uuid4

from local_transcriber.application.pipeline import PipelineConfig, PipelineError
from local_transcriber.application.worker_protocol import WorkerTask
from local_transcriber.domain.media import MediaInfo
from local_transcriber.infrastructure.faster_whisper_engine import FasterWhisperConfig
from local_transcriber.infrastructure.media import media_fingerprint
from local_transcriber.infrastructure.settings import AppSettings
from local_transcriber.infrastructure.silero_segmenter import SegmentationConfig


def prepare_task(
    settings: AppSettings,
    media: MediaInfo,
    indices: tuple[int, ...],
    config: PipelineConfig,
    resume: UUID | None = None,
) -> WorkerTask:
    """Freeze the same local model/VAD identity used for checkpoint validation."""
    if not indices or len(set(indices)) != len(indices):
        raise PipelineError("Выберите неповторяющиеся индексы аудиодорожек.")
    if not set(indices) <= {stream.stream_index for stream in media.audio_streams}:
        raise PipelineError("Выбранная аудиодорожка отсутствует.")
    model = replace(FasterWhisperConfig.from_settings(settings), word_timestamps=True)
    if not model.model_path.is_dir():
        raise PipelineError("Локальная модель не найдена; автоматическая загрузка отключена.")
    vad = SegmentationConfig.from_settings(settings)
    if vad.enabled and config.overlap_ms < vad.min_silence_ms + vad.padding_ms:
        raise PipelineError(
            "Overlap должен покрывать min_silence_ms + padding_ms для выбранного VAD."
        )
    parameters = {
        "vad": asdict(vad),
        "model_config": json.loads(json.dumps(asdict(model), default=str)),
        "model_files": {
            name: media_fingerprint(model.model_path / name)
            for name in ("model.bin", "config.json", "tokenizer.json")
        },
        "runtime": {name: version(name) for name in ("faster-whisper", "ctranslate2")},
    }
    return WorkerTask(
        uuid4(),
        media.path,
        indices,
        config,
        parameters,
        settings.ffmpeg_path,
        settings.ffprobe_path,
        asdict(model),
        asdict(vad),
        resume,
    )
