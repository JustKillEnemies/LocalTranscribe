"""Step 02: reproducible Windows settings and safe configuration failures."""

import os
from pathlib import Path

import pytest

from local_transcriber.infrastructure.settings import (
    ConfigurationError,
    default_data_dir,
    load_settings,
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in tuple(os.environ):
        if key.upper().startswith("LOCAL_TRANSCRIBER_") or key.upper() in {
            "LOCALAPPDATA",
            "APPDATA",
        }:
            monkeypatch.delenv(key)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Локальные данные"))


def test_defaults_do_not_create_files(tmp_path: Path) -> None:
    settings = load_settings()
    assert settings.data_dir == tmp_path / "Локальные данные/LocalTranscriber"
    assert settings.cache_dir == settings.data_dir / "cache"
    assert settings.models_dir == settings.data_dir / "models"
    assert settings.logs_dir == settings.data_dir / "logs"
    assert settings.temp_dir == settings.data_dir / "temp"
    assert settings.model_path == settings.models_dir / "large-v3-turbo"
    assert settings.device == "cuda"
    assert settings.compute_type == "float16"
    assert list(tmp_path.iterdir()) == []


def test_appdata_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert default_data_dir() == tmp_path / "Roaming/LocalTranscriber"


def test_home_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert default_data_dir() == tmp_path / "AppData/Local/LocalTranscriber"


def test_env_override_and_blank_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    directory = tmp_path / "Рабочие данные с пробелами"
    monkeypatch.setenv("LOCAL_TRANSCRIBER_DATA_DIR", str(directory))
    monkeypatch.setenv("LOCAL_TRANSCRIBER_MODELS_DIR", "")
    monkeypatch.setenv("LOCAL_TRANSCRIBER_DEVICE", "cpu")
    settings = load_settings()
    assert settings.data_dir == directory
    assert settings.models_dir == directory / "models"
    assert settings.device == "cpu"


def test_dotenv_utf8_bom_env_priority_and_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "Настройки с пробелами.env"
    source.write_text(
        f'LOCAL_TRANSCRIBER_DATA_DIR="{(tmp_path / "Из файла").as_posix()}"\n'
        "LOCAL_TRANSCRIBER_MODEL_NAME=medium\n"
        "LOCAL_TRANSCRIBER_POSTGRES_PASSWORD=private-test-password\n",
        encoding="utf-8-sig",
    )
    monkeypatch.setenv("LOCAL_TRANSCRIBER_MODEL_NAME", "large-v3")
    settings = load_settings(source)
    assert settings.data_dir == tmp_path / "Из файла"
    assert settings.model_name == "large-v3"
    assert settings.postgres_password.get_secret_value() == "private-test-password"
    assert "private-test-password" not in repr(settings)
    assert "private-test-password" not in settings.model_dump_json()


def test_default_user_file_loaded_but_cwd_file_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = default_data_dir()
    root.mkdir(parents=True)
    (root / ".env").write_text("LOCAL_TRANSCRIBER_DEVICE=cpu\n", encoding="utf-8")
    (tmp_path / ".env").write_text("LOCAL_TRANSCRIBER_DEVICE=invalid\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert load_settings().device == "cpu"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("POSTGRES_PORT", "not-a-port-private-password"),
        ("POSTGRES_PORT", "0"),
        ("POSTGRES_PORT", "65536"),
        ("GPU_INDEX", "-1"),
        ("DEVICE", "private-invalid-device"),
        ("MODEL_NAME", "../outside"),
        ("DATA_DIR", "relative"),
        ("TEMP_DIR", "relative"),
        ("PROBE_TIMEOUT", "0"),
        ("POSTGRES_HOST", "external.example"),
    ],
)
def test_invalid_env_is_reported_without_values(
    key: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_TRANSCRIBER_" + key, value)
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert key.lower() in str(error.value)
    assert value not in str(error.value)


def test_explicit_missing_or_corrupt_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Файл настроек недоступен"):
        load_settings(tmp_path / "missing.env")
    source = tmp_path / "bad.env"
    source.write_bytes(b"\xff\xfe")
    with pytest.raises(ConfigurationError, match="Не удалось прочитать"):
        load_settings(source)
    assert source.read_bytes() == b"\xff\xfe"


def test_relative_appdata_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", "relative-private-value")
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert "relative-private-value" not in str(error.value)


def test_example_can_be_loaded_without_creating_dirs() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / ".env.example")
    assert settings.postgres_password.get_secret_value() == ""
    assert settings.postgres_test_db != settings.postgres_db


def test_single_quoted_windows_path_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "single.env"
    directory = tmp_path / "Каталог с пробелами"
    source.write_text(f"LOCAL_TRANSCRIBER_DATA_DIR='{directory}'\n", encoding="utf-8")
    assert load_settings(source).data_dir == directory


@pytest.mark.skipif(os.name != "nt", reason="Windows dotenv backslash regression")
def test_escaped_windows_path_is_rejected_without_creating_files(tmp_path: Path) -> None:
    source = tmp_path / "double.env"
    source.write_text('LOCAL_TRANSCRIBER_DATA_DIR="C:\\temp\\new"\n', encoding="utf-8")
    original = source.read_bytes()
    with pytest.raises(ConfigurationError, match="одинарные кавычки"):
        load_settings(source)
    assert source.read_bytes() == original
    assert list(tmp_path.iterdir()) == [source]


def test_malformed_dotenv_is_not_partially_accepted(tmp_path: Path) -> None:
    source = tmp_path / "malformed.env"
    source.write_text(
        'LOCAL_TRANSCRIBER_DEVICE=cpu\nLOCAL_TRANSCRIBER_POSTGRES_PASSWORD="unclosed-secret\n',
        encoding="utf-8",
    )
    original = source.read_bytes()
    with pytest.raises(ConfigurationError, match="Некорректный формат") as error:
        load_settings(source)
    assert "unclosed-secret" not in str(error.value)
    assert source.read_bytes() == original


def test_dotenv_size_is_bounded(tmp_path: Path) -> None:
    source = tmp_path / "large.env"
    source.write_bytes(b"#" * (1024 * 1024 + 1))
    with pytest.raises(ConfigurationError, match="1 MiB"):
        load_settings(source)
