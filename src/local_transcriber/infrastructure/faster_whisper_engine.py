"""Offline-first faster-whisper adapter for bounded 16 kHz PCM ranges."""

from __future__ import annotations

import ctypes
import gc
import os
import sysconfig
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from local_transcriber.domain.audio import MAX_WORK_RANGE_MS, PCM_BYTES_PER_SECOND
from local_transcriber.domain.transcription import (
    TranscriptionEngineInfo,
    TranscriptionSegment,
    TranscriptionWord,
)

if TYPE_CHECKING:
    from local_transcriber.infrastructure.settings import AppSettings

ModelName = Literal["large-v3-turbo", "medium", "large-v3"]
ComputeType = Literal["float16", "int8_float16", "int8", "float32"]


class TranscriptionError(RuntimeError):
    """Safe local recognition failure without private audio or internal paths."""


class ModelUnavailableError(TranscriptionError):
    """The configured local model or runtime cannot be loaded."""


class CudaUnavailableError(TranscriptionError):
    """CUDA recognition failed and no configured fallback succeeded."""


class _WhisperModel(Protocol):
    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Iterable[Any], Any]: ...


ModelFactory = Callable[..., _WhisperModel]


@dataclass(frozen=True)
class FasterWhisperConfig:
    model_name: ModelName = "large-v3-turbo"
    model_path: Path | None = None
    device: Literal["cuda", "cpu"] = "cuda"
    device_index: int = 0
    compute_type: ComputeType = "float16"
    fallback_compute_type: Literal["int8_float16"] | None = "int8_float16"
    beam_size: int = 5
    word_timestamps: bool = False
    allow_download: bool = False
    download_root: Path | None = None

    def __post_init__(self) -> None:
        if self.device_index < 0:
            raise ValueError("device_index must be non-negative")
        if self.beam_size < 1:
            raise ValueError("beam_size must be positive")
        if self.device == "cpu" and self.compute_type == "float16":
            raise ValueError("float16 is only supported by the CUDA configuration")
        if self.fallback_compute_type == self.compute_type:
            raise ValueError("fallback compute type must differ from the primary type")

    @classmethod
    def from_settings(cls, settings: AppSettings) -> FasterWhisperConfig:
        """Build the offline default; enabling downloads requires an explicit override."""
        return cls(
            model_name=settings.model_name,
            model_path=settings.model_path,
            device=settings.device,
            device_index=settings.gpu_index,
            compute_type=settings.compute_type,
            fallback_compute_type="int8_float16" if settings.device == "cuda" else None,
            download_root=settings.models_dir,
            allow_download=False,
        )


class FasterWhisperEngine:
    """Load one model lazily and fully consume each faster-whisper generator."""

    def __init__(
        self,
        config: FasterWhisperConfig,
        *,
        model_factory: ModelFactory | None = None,
    ) -> None:
        self.config = config
        self._factory = model_factory
        self._model: _WhisperModel | None = None
        self._active_compute_type: ComputeType | None = None
        self._lock = threading.RLock()
        self._dll_handles: list[Any] = []

    @property
    def active_compute_type(self) -> ComputeType | None:
        return self._active_compute_type

    @property
    def info(self) -> TranscriptionEngineInfo:
        return TranscriptionEngineInfo(
            model_name=self.config.model_name,
            device=self.config.device,
            compute_type=self._active_compute_type or self.config.compute_type,
            language="ru",
            beam_size=self.config.beam_size,
        )

    def transcribe(self, pcm_s16le: bytes) -> tuple[TranscriptionSegment, ...]:
        """Recognize one bounded range; returned timestamps are relative to its start."""
        duration_ms = _validate_pcm(pcm_s16le)
        audio = _pcm_to_float32(pcm_s16le)
        with self._lock:
            model = self._get_model()
            try:
                return self._consume(model, audio, duration_ms)
            except Exception as error:
                if self._can_fallback(error):
                    model = self._load_fallback()
                    try:
                        return self._consume(model, audio, duration_ms)
                    except Exception as fallback_error:
                        if _is_cuda_error(fallback_error):
                            raise CudaUnavailableError(
                                "CUDA-распознавание не удалось с выбранным fallback."
                            ) from None
                        raise TranscriptionError(
                            "Локальное распознавание завершилось ошибкой."
                        ) from None
                if _is_cuda_error(error):
                    raise CudaUnavailableError("CUDA-распознавание недоступно.") from None
                if isinstance(error, TranscriptionError):
                    raise
                raise TranscriptionError("Локальное распознавание завершилось ошибкой.") from None

    def _consume(
        self, model: _WhisperModel, audio: Any, duration_ms: int
    ) -> tuple[TranscriptionSegment, ...]:
        lazy_segments, _info = model.transcribe(
            audio,
            language="ru",
            task="transcribe",
            beam_size=self.config.beam_size,
            temperature=0.0,
            word_timestamps=self.config.word_timestamps,
            vad_filter=False,
        )
        results: list[TranscriptionSegment] = []
        for item in lazy_segments:
            start_ms = max(0, round(float(item.start) * 1000))
            end_ms = min(duration_ms, round(float(item.end) * 1000))
            if end_ms <= start_ms:
                raise TranscriptionError("Движок вернул некорректные временные метки.")
            results.append(
                TranscriptionSegment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=str(item.text),
                    confidence=None,
                    words=self._words(item, duration_ms),
                )
            )
        return tuple(results)

    def _words(self, item: Any, duration_ms: int) -> tuple[TranscriptionWord, ...]:
        if not self.config.word_timestamps:
            return ()
        words: list[TranscriptionWord] = []
        for word in getattr(item, "words", None) or ():
            start_ms = max(0, round(float(word.start) * 1000))
            end_ms = min(duration_ms, round(float(word.end) * 1000))
            if end_ms <= start_ms:
                raise TranscriptionError("Движок вернул некорректные таймкоды слова.")
            probability = getattr(word, "probability", None)
            words.append(
                TranscriptionWord(
                    start_ms,
                    end_ms,
                    str(word.word),
                    float(probability) if probability is not None else None,
                )
            )
        return tuple(words)

    def _get_model(self) -> _WhisperModel:
        if self._model is None:
            try:
                self._model = self._create_model(self.config.compute_type)
                self._active_compute_type = self.config.compute_type
            except Exception as error:
                if self._can_fallback(error):
                    return self._load_fallback()
                if _is_cuda_error(error):
                    raise CudaUnavailableError(
                        "CUDA runtime для faster-whisper недоступен."
                    ) from None
                if isinstance(error, ModelUnavailableError):
                    raise
                raise ModelUnavailableError("Не удалось загрузить локальную модель.") from None
        return self._model

    def _create_model(self, compute_type: ComputeType) -> _WhisperModel:
        source: str
        if self.config.model_path is not None and self.config.model_path.is_dir():
            source = str(self.config.model_path.resolve())
        elif self.config.allow_download:
            source = self.config.model_name
        else:
            raise ModelUnavailableError(
                "Локальная модель не найдена; автоматическая загрузка отключена."
            )
        if self._factory is None:
            self._prepare_cuda_dlls()
        factory = self._factory or _default_model_factory()
        return factory(
            source,
            device=self.config.device,
            device_index=self.config.device_index,
            compute_type=compute_type,
            download_root=(
                str(self.config.download_root.resolve())
                if self.config.download_root is not None
                else None
            ),
            local_files_only=not self.config.allow_download,
        )

    def _prepare_cuda_dlls(self) -> None:
        if self.config.device != "cuda" or os.name != "nt" or self._dll_handles:
            return
        purelib = Path(sysconfig.get_paths()["purelib"])
        for directory in _cuda_dll_directories(purelib):
            self._dll_handles.append(os.add_dll_directory(str(directory)))
        for library in _cuda_preload_libraries(purelib):
            self._dll_handles.append(ctypes.WinDLL(str(library)))

    def _can_fallback(self, error: BaseException) -> bool:
        return (
            self.config.device == "cuda"
            and self.config.fallback_compute_type is not None
            and self._active_compute_type != self.config.fallback_compute_type
            and _is_fallback_eligible(error)
        )

    def _load_fallback(self) -> _WhisperModel:
        fallback = self.config.fallback_compute_type
        if fallback is None:
            raise CudaUnavailableError("CUDA fallback не настроен.")
        self._model = None
        gc.collect()
        try:
            self._model = self._create_model(fallback)
        except Exception:
            raise CudaUnavailableError(
                "CUDA runtime или настроенный compute fallback недоступен."
            ) from None
        self._active_compute_type = fallback
        return self._model


def _default_model_factory() -> ModelFactory:
    try:
        from faster_whisper import WhisperModel
    except ImportError, OSError:
        raise ModelUnavailableError("faster-whisper runtime не установлен или повреждён.") from None
    return WhisperModel


def _validate_pcm(pcm_s16le: bytes) -> int:
    if not isinstance(pcm_s16le, bytes) or not pcm_s16le:
        raise ValueError("PCM input must be non-empty bytes")
    if len(pcm_s16le) % 2:
        raise ValueError("PCM input contains a truncated s16le sample")
    duration_ms = len(pcm_s16le) * 1000 // PCM_BYTES_PER_SECOND
    if duration_ms < 1:
        raise ValueError("PCM input is shorter than one millisecond")
    if duration_ms > MAX_WORK_RANGE_MS:
        raise ValueError("PCM input exceeds the 15-minute safety limit")
    return duration_ms


def _pcm_to_float32(pcm_s16le: bytes) -> Any:
    try:
        import numpy as np
    except ImportError, OSError:
        raise ModelUnavailableError("NumPy runtime для faster-whisper недоступен.") from None
    return np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0


def _is_cuda_error(error: BaseException) -> bool:
    message = str(error).casefold()
    markers = (
        "cuda",
        "cublas",
        "cudnn",
        "driver version",
        "out of memory",
        "compute type float16",
    )
    return any(marker in message for marker in markers)


def _is_fallback_eligible(error: BaseException) -> bool:
    message = str(error).casefold()
    return "out of memory" in message or (
        "compute type" in message and ("float16" in message or "unsupported" in message)
    )


def _cuda_dll_directories(purelib: Path) -> tuple[Path, ...]:
    root = purelib / "nvidia"
    candidates = (
        root / "cublas/bin",
        root / "cudnn/bin",
        root / "cuda_nvrtc/bin",
    )
    return tuple(path for path in candidates if path.is_dir())


def _cuda_preload_libraries(purelib: Path) -> tuple[Path, ...]:
    root = purelib / "nvidia"
    candidates = (
        root / "cublas/bin/cublasLt64_12.dll",
        root / "cublas/bin/cublas64_12.dll",
        root / "cudnn/bin/cudnn64_9.dll",
    )
    return tuple(path for path in candidates if path.is_file())
