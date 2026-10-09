"""Step 06 STT contract and faster-whisper adapter unit tests."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import local_transcriber.infrastructure.faster_whisper_engine as engine_module
from local_transcriber.domain.transcription import TranscriptionSegment, TranscriptionWord
from local_transcriber.infrastructure.faster_whisper_engine import (
    CudaUnavailableError,
    FasterWhisperConfig,
    FasterWhisperEngine,
    ModelUnavailableError,
    TranscriptionError,
    _cuda_dll_directories,
    _cuda_preload_libraries,
)
from local_transcriber.infrastructure.settings import AppSettings

PCM_ONE_SECOND = b"\x00\x00" * 16_000


class FakeModel:
    def __init__(self, state: dict[str, Any], segments: list[Any] | None = None) -> None:
        self.state = state
        self.segments = segments or [SimpleNamespace(start=0.125, end=0.75, text=" Тест ")]

    def transcribe(self, _audio: Any, **kwargs: Any) -> tuple[Any, object]:
        self.state["kwargs"] = kwargs

        def lazy() -> Any:
            yield from self.segments
            self.state["consumed"] = True

        return lazy(), object()


def local_config(model_dir: Path, **overrides: Any) -> FasterWhisperConfig:
    values: dict[str, Any] = {"model_path": model_dir}
    values.update(overrides)
    return FasterWhisperConfig(**values)


def test_segment_dto_validates_relative_milliseconds() -> None:
    segment = TranscriptionSegment(10, 20, "текст", 0.75)
    assert segment.confidence == 0.75
    with pytest.raises(ValueError, match="positive relative"):
        TranscriptionSegment(20, 20, "текст")
    with pytest.raises(ValueError, match="confidence"):
        TranscriptionSegment(10, 20, "текст", 1.1)


def test_settings_create_offline_cuda_defaults(tmp_path: Path) -> None:
    settings = AppSettings(data_dir=tmp_path)
    config = FasterWhisperConfig.from_settings(settings)
    assert config.model_name == "large-v3-turbo"
    assert config.model_path == tmp_path / "models/large-v3-turbo"
    assert config.compute_type == "float16"
    assert config.fallback_compute_type == "int8_float16"
    assert config.allow_download is False


def test_cuda_dll_directories_only_return_installed_packages(tmp_path: Path) -> None:
    cublas = tmp_path / "nvidia/cublas/bin"
    cudnn = tmp_path / "nvidia/cudnn/bin"
    cublas.mkdir(parents=True)
    cudnn.mkdir(parents=True)
    assert _cuda_dll_directories(tmp_path) == (cublas, cudnn)


def test_cuda_preload_order_places_cublas_lt_before_cublas(tmp_path: Path) -> None:
    cublas = tmp_path / "nvidia/cublas/bin"
    cudnn = tmp_path / "nvidia/cudnn/bin"
    cublas.mkdir(parents=True)
    cudnn.mkdir(parents=True)
    lt = cublas / "cublasLt64_12.dll"
    main = cublas / "cublas64_12.dll"
    cudnn_main = cudnn / "cudnn64_9.dll"
    for library in (lt, main, cudnn_main):
        library.touch()
    assert _cuda_preload_libraries(tmp_path) == (lt, main, cudnn_main)


def test_engine_consumes_generator_and_reuses_one_model(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    state: dict[str, Any] = {"loads": 0}

    def factory(source: str, **kwargs: Any) -> FakeModel:
        state["loads"] += 1
        state["source"] = source
        state["factory_kwargs"] = kwargs
        return FakeModel(state)

    engine = FasterWhisperEngine(local_config(model_dir), model_factory=factory)
    first = engine.transcribe(PCM_ONE_SECOND)
    second = engine.transcribe(PCM_ONE_SECOND)

    assert first == second == (TranscriptionSegment(125, 750, " Тест "),)
    assert state["consumed"] is True
    assert state["loads"] == 1
    assert state["source"] == str(model_dir)
    assert state["factory_kwargs"]["local_files_only"] is True
    assert state["kwargs"] == {
        "language": "ru",
        "task": "transcribe",
        "beam_size": 5,
        "temperature": 0.0,
        "word_timestamps": False,
        "vad_filter": False,
    }
    assert engine.active_compute_type == "float16"
    assert engine.info.model_name == "large-v3-turbo"
    assert engine.info.compute_type == "float16"


def test_optional_word_timestamps_are_mapped(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    source = SimpleNamespace(
        start=0.1,
        end=0.8,
        text=" слово",
        words=[SimpleNamespace(start=0.12, end=0.5, word=" слово", probability=0.9)],
    )
    engine = FasterWhisperEngine(
        local_config(model_dir, word_timestamps=True),
        model_factory=lambda *_args, **_kwargs: FakeModel({}, [source]),
    )
    segment = engine.transcribe(PCM_ONE_SECOND)[0]
    assert segment.words == (TranscriptionWord(120, 500, " слово", 0.9),)


def test_missing_local_model_never_calls_factory_or_downloads(tmp_path: Path) -> None:
    called = False

    def factory(_source: str, **_kwargs: Any) -> FakeModel:
        nonlocal called
        called = True
        return FakeModel({})

    engine = FasterWhisperEngine(
        local_config(tmp_path / "absent", allow_download=False), model_factory=factory
    )
    with pytest.raises(ModelUnavailableError, match="автоматическая загрузка отключена"):
        engine.transcribe(PCM_ONE_SECOND)
    assert called is False


def test_download_requires_explicit_config_switch(tmp_path: Path) -> None:
    received: dict[str, Any] = {}

    def factory(source: str, **kwargs: Any) -> FakeModel:
        received.update(source=source, **kwargs)
        return FakeModel({})

    engine = FasterWhisperEngine(
        local_config(tmp_path / "absent", allow_download=True), model_factory=factory
    )
    assert engine.transcribe(PCM_ONE_SECOND)
    assert received["source"] == "large-v3-turbo"
    assert received["local_files_only"] is False


def test_explicit_cuda_fallback_is_used(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    attempts: list[str] = []
    state: dict[str, Any] = {}

    def factory(_source: str, **kwargs: Any) -> FakeModel:
        attempts.append(kwargs["compute_type"])
        if kwargs["compute_type"] == "float16":
            raise RuntimeError("CUDA compute type float16 is unavailable")
        return FakeModel(state)

    engine = FasterWhisperEngine(local_config(model_dir), model_factory=factory)
    assert engine.transcribe(PCM_ONE_SECOND)[0].text.strip() == "Тест"
    assert attempts == ["float16", "int8_float16"]
    assert engine.active_compute_type == "int8_float16"


def test_cuda_error_is_safe_when_fallback_fails(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    def factory(_source: str, **_kwargs: Any) -> FakeModel:
        raise RuntimeError("cuDNN DLL is missing at a private path")

    engine = FasterWhisperEngine(local_config(model_dir), model_factory=factory)
    with pytest.raises(CudaUnavailableError, match="runtime") as captured:
        engine.transcribe(PCM_ONE_SECOND)
    assert "private path" not in str(captured.value)


def test_missing_cuda_library_does_not_load_second_model(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    loads = 0

    class MissingLibraryModel(FakeModel):
        def transcribe(self, _audio: Any, **_kwargs: Any) -> tuple[Any, object]:
            raise RuntimeError("Library cublas64_12.dll is not found")

    def factory(_source: str, **_kwargs: Any) -> FakeModel:
        nonlocal loads
        loads += 1
        return MissingLibraryModel({})

    engine = FasterWhisperEngine(local_config(model_dir), model_factory=factory)
    with pytest.raises(CudaUnavailableError, match="недоступно"):
        engine.transcribe(PCM_ONE_SECOND)
    assert loads == 1


def test_inference_cuda_failure_reloads_once_with_fallback(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    attempts: list[str] = []

    class FailingModel(FakeModel):
        def transcribe(self, _audio: Any, **_kwargs: Any) -> tuple[Any, object]:
            raise RuntimeError("CUDA out of memory")

    def factory(_source: str, **kwargs: Any) -> FakeModel:
        attempts.append(kwargs["compute_type"])
        if kwargs["compute_type"] == "float16":
            return FailingModel({})
        return FakeModel({})

    engine = FasterWhisperEngine(local_config(model_dir), model_factory=factory)
    assert engine.transcribe(PCM_ONE_SECOND)
    assert attempts == ["float16", "int8_float16"]


def test_invalid_engine_timestamps_are_diagnosed(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    bad = [SimpleNamespace(start=0.5, end=0.5, text="ошибка")]
    engine = FasterWhisperEngine(
        local_config(model_dir), model_factory=lambda *_args, **_kwargs: FakeModel({}, bad)
    )
    with pytest.raises(TranscriptionError, match="временные метки"):
        engine.transcribe(PCM_ONE_SECOND)


@pytest.mark.parametrize("pcm", [b"", b"\x00"])
def test_pcm_contract_rejects_empty_and_truncated_input(tmp_path: Path, pcm: bytes) -> None:
    engine = FasterWhisperEngine(local_config(tmp_path))
    with pytest.raises(ValueError):
        engine.transcribe(pcm)


def test_pcm_contract_rejects_overlong_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine_module, "PCM_BYTES_PER_SECOND", 2)
    engine = FasterWhisperEngine(local_config(tmp_path))
    with pytest.raises(ValueError, match="15-minute"):
        engine.transcribe(b"\x00\x00" * 900_001)
