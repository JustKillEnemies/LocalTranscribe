"""Validated local settings with deterministic Windows user-data defaults."""

import os
from pathlib import Path
from typing import Literal, Self

from dotenv.parser import parse_stream
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError


def default_data_dir() -> Path:
    """Resolve a Windows user directory without creating it."""
    for variable in ("LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(variable)
        if value:
            base = Path(value).expanduser()
            if not base.is_absolute():
                raise ValueError(f"{variable} must be an absolute path")
            return base / "LocalTranscriber"
    return Path.home() / "AppData" / "Local" / "LocalTranscriber"


class AppSettings(BaseSettings):
    """Environment > explicit/user dotenv > defaults; no filesystem writes."""

    model_config = SettingsConfigDict(
        env_prefix="LOCAL_TRANSCRIBER_",
        env_ignore_empty=True,
        env_file_encoding="utf-8-sig",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    data_dir: Path = Field(default_factory=default_data_dir)
    cache_dir: Path | None = None
    models_dir: Path | None = None
    logs_dir: Path | None = None
    temp_dir: Path | None = None
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    postgres_probe_path: str = "pg_isready"
    nvidia_smi_path: str = "nvidia-smi"
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "local_transcriber"
    postgres_test_db: str = "local_transcriber_test"
    postgres_user: str = Field(default="", repr=False)
    postgres_password: SecretStr = Field(default=SecretStr(""), repr=False)
    postgres_dsn: SecretStr | None = Field(default=None, repr=False)
    device: Literal["cuda", "cpu"] = "cuda"
    gpu_index: int = Field(default=0, ge=0)
    model_name: Literal["large-v3-turbo", "medium", "large-v3"] = "large-v3-turbo"
    model_path: Path | None = None
    compute_type: Literal["float16", "int8_float16", "int8", "float32"] = "float16"
    probe_timeout: int = Field(default=5, ge=1, le=30)

    @field_validator("data_dir", "cache_dir", "models_dir", "logs_dir", "temp_dir", "model_path")
    @classmethod
    def absolute_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return value
        if any(ord(character) < 32 for character in str(value)):
            raise ValueError("Control characters are not allowed in paths")
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError("Use an absolute path")
        return value.resolve()

    @field_validator("postgres_host")
    @classmethod
    def local_database(cls, value: str) -> str:
        if value.lower() not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("PostgreSQL must be local")
        return value.lower()

    @field_validator("ffmpeg_path", "ffprobe_path", "postgres_probe_path", "nvidia_smi_path")
    @classmethod
    def executable_name(cls, value: str) -> str:
        if not value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("Specify an executable name or path, not a command line")
        return value

    @model_validator(mode="after")
    def directory_defaults(self) -> Self:
        for name, child in (
            ("cache_dir", "cache"),
            ("models_dir", "models"),
            ("logs_dir", "logs"),
            ("temp_dir", "temp"),
        ):
            if getattr(self, name) is None:
                object.__setattr__(self, name, self.data_dir / child)
        if self.model_path is None:
            object.__setattr__(self, "model_path", self.models_dir / self.model_name)
        return self

    def directories(self) -> tuple[Path, ...]:
        """Return configured data directories, never the source media directory."""
        return (self.data_dir, self.cache_dir, self.models_dir, self.logs_dir, self.temp_dir)


class ConfigurationError(ValueError):
    """Safe settings error; never contains input values or credentials."""


def load_settings(env_file: Path | None = None) -> AppSettings:
    """Load an explicit file or the user-data .env, never an implicit cwd .env."""
    try:
        if env_file is not None and not env_file.is_file():
            raise ConfigurationError("Файл настроек недоступен.")
        source = env_file if env_file is not None else default_data_dir() / ".env"
        if source.exists():
            if not source.is_file() or source.stat().st_size > 1024 * 1024:
                raise ConfigurationError("Файл настроек недоступен или превышает 1 MiB.")
            with source.open(encoding="utf-8-sig") as stream:
                if any(binding.error for binding in parse_stream(stream)):
                    raise ConfigurationError(
                        "Некорректный формат .env; проверьте кавычки и присваивания."
                    )
        return AppSettings(_env_file=source)
    except ValidationError as error:
        fields = sorted(
            {
                str(item["loc"][0]) if item["loc"] else "configuration"
                for item in error.errors(include_input=False)
            }
        )
        hint = (
            ". Для путей в .env используйте / или одинарные кавычки."
            if any(field.endswith(("_dir", "_path")) for field in fields)
            else ""
        )
        raise ConfigurationError("Неверные настройки: " + ", ".join(fields) + hint) from None
    except (SettingsError, OSError, UnicodeError, ValueError) as error:
        if isinstance(error, ConfigurationError):
            raise
        raise ConfigurationError(
            "Не удалось прочитать настройки. Проверьте файл и окружение."
        ) from None
