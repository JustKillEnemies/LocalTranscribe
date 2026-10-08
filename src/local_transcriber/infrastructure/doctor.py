"""Read-only, offline environment diagnostics; no model loading or DB mutations."""

import importlib.util
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import PostgresDsn, TypeAdapter, ValidationError

from local_transcriber.infrastructure.settings import AppSettings


class Status(StrEnum):
    OK = "OK"
    MISSING = "MISSING"
    ERROR = "ERROR"
    SKIP = "SKIP"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    message: str


def _run(arguments: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("LOCAL_TRANSCRIBER_", "PG"))
    }
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def _executable(value: str) -> str | None:
    # Reject shell scripts on Windows, even when shell=False.
    if os.name == "nt" and Path(value).suffix.lower() in {".bat", ".cmd", ".ps1"}:
        raise ValueError("An executable is required")
    return shutil.which(value)


def _tool(name: str, executable: str, arguments: list[str], timeout: int) -> CheckResult:
    try:
        path = _executable(executable)
        if path is None:
            return CheckResult(name, Status.MISSING, "Не найден. Укажите путь к инструменту.")
        result = _run([path, *arguments], timeout)
        if result.returncode != 0:
            return CheckResult(name, Status.ERROR, "Инструмент завершился с ошибкой.")
        if name in {"ffmpeg", "ffprobe"}:
            match = re.match(rf"{name} version ([\w.+-]+)", result.stdout)
            if not match:
                return CheckResult(name, Status.ERROR, "Неожиданный ответ инструмента.")
            return CheckResult(name, Status.OK, "Версия " + match[1])
        if not result.stdout.strip():
            return CheckResult(name, Status.MISSING, "GPU не обнаружена.")
        driver = result.stdout.strip().splitlines()[0]
        if not re.fullmatch(r"\d+(?:\.\d+)+", driver):
            return CheckResult(name, Status.ERROR, "Неожиданный ответ NVIDIA-драйвера.")
        return CheckResult(name, Status.OK, f"Драйвер {driver}; inference не проверялся.")
    except subprocess.TimeoutExpired:
        return CheckResult(name, Status.ERROR, "Истёк тайм-аут проверки.")
    except OSError, ValueError:
        return CheckResult(name, Status.ERROR, "Не удалось запустить инструмент.")


def _postgres(settings: AppSettings, dry_run: bool) -> CheckResult:
    name = "PostgreSQL"
    host, port = settings.postgres_host, settings.postgres_port
    if settings.postgres_dsn is not None:
        try:
            dsn = TypeAdapter(PostgresDsn).validate_python(settings.postgres_dsn.get_secret_value())
            hosts = dsn.hosts()
            if (
                dsn.scheme not in {"postgres", "postgresql"}
                or len(hosts) != 1
                or hosts[0]["host"].lower() not in {"localhost", "127.0.0.1", "::1", "[::1]"}
                or dsn.query
                or dsn.fragment
                or not dsn.path
                or dsn.path == "/"
            ):
                raise ValueError("Local single-host DSN required")
            host = hosts[0]["host"].strip("[]")
            port = hosts[0]["port"] if hosts[0]["port"] is not None else 5432
            if not 1 <= port <= 65535:
                raise ValueError("Invalid port")
        except ValidationError, ValueError, TypeError, KeyError, AttributeError:
            return CheckResult(
                name, Status.ERROR, "Неверная локальная строка подключения; значение скрыто."
            )
    if dry_run:
        return CheckResult(name, Status.SKIP, "Проверка сервера отключена в dry-run.")
    try:
        executable = _executable(settings.postgres_probe_path)
        if executable is None:
            return CheckResult(
                name, Status.MISSING, "pg_isready не найден. Укажите путь из PostgreSQL/bin."
            )
        result = _run(
            [executable, "-h", host, "-p", str(port), "-t", str(settings.probe_timeout), "-q"],
            settings.probe_timeout + 1,
        )
        if result.returncode == 0:
            return CheckResult(
                name, Status.OK, "Сервер принимает подключения; пароль, БД и схема не проверялись."
            )
        return CheckResult(
            name,
            Status.ERROR,
            "Сервер не отвечает или отклоняет подключения. Проверьте службу Windows.",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(name, Status.ERROR, "Истёк тайм-аут PostgreSQL.")
    except OSError, ValueError:
        return CheckResult(name, Status.ERROR, "Не удалось запустить pg_isready.")


def _cuda(settings: AppSettings, dry_run: bool) -> CheckResult:
    name = "CUDA/CTranslate2"
    if dry_run or settings.device == "cpu":
        return CheckResult(name, Status.SKIP, "Проверка CUDA отключена (dry-run или CPU).")
    try:
        if importlib.util.find_spec("ctranslate2") is None:
            return CheckResult(
                name, Status.MISSING, "CTranslate2 не установлен. Автоматической установки нет."
            )
        code = "import json,ctranslate2; print(json.dumps(ctranslate2.get_cuda_device_count()))"
        result = _run(
            [sys.executable, "-I", "-B", "-X", "utf8", "-c", code], settings.probe_timeout
        )
        if result.returncode != 0:
            return CheckResult(
                name,
                Status.ERROR,
                "Импорт/runtime CTranslate2 недоступен. Проверьте CUDA/cuDNN/DLL.",
            )
        count = json.loads(result.stdout)
        if type(count) is not int or count < 0:
            raise ValueError("Invalid device count")
        if count <= settings.gpu_index:
            return CheckResult(name, Status.MISSING, "Выбранная GPU недоступна для CUDA runtime.")
        return CheckResult(
            name, Status.OK, "CUDA видит выбранную GPU; модель и inference не проверялись."
        )
    except subprocess.TimeoutExpired:
        return CheckResult(name, Status.ERROR, "Истёк тайм-аут CUDA.")
    except OSError, ValueError, ImportError:
        return CheckResult(name, Status.ERROR, "Не удалось проверить CUDA runtime.")


def _model(settings: AppSettings) -> CheckResult:
    try:
        path = settings.model_path
        if not path.is_dir():
            return CheckResult(
                "Модель",
                Status.MISSING,
                "Локальный каталог модели не найден; загрузка не выполнялась.",
            )
        required = ("model.bin", "config.json", "tokenizer.json")
        if any(
            not (path / name).is_file() or (path / name).stat().st_size == 0 for name in required
        ):
            return CheckResult(
                "Модель",
                Status.ERROR,
                "Неполный каталог CTranslate2: model.bin/config.json/tokenizer.json.",
            )
        for name in ("config.json", "tokenizer.json"):
            candidate = path / name
            if candidate.stat().st_size > 64 * 1024 * 1024:
                return CheckResult(
                    "Модель", Status.ERROR, "JSON модели превышает лимит диагностики 64 MiB."
                )
            with candidate.open(encoding="utf-8") as source:
                if not isinstance(json.load(source), dict):
                    return CheckResult(
                        "Модель", Status.ERROR, "JSON модели должен содержать объект."
                    )
        return CheckResult(
            "Модель",
            Status.OK,
            "Локальные файлы присутствуют; веса не загружались, inference не проверялся.",
        )
    except OSError, ValueError, UnicodeError:
        return CheckResult("Модель", Status.ERROR, "Файлы модели недоступны или JSON повреждён.")


def _directories(settings: AppSettings, create: bool) -> CheckResult:
    try:
        for path in settings.directories():
            if path.exists() and not path.is_dir():
                return CheckResult("Каталоги", Status.ERROR, "Один из путей занят файлом.")
        if create:
            for path in settings.directories():
                path.mkdir(parents=True, exist_ok=True)
            return CheckResult(
                "Каталоги", Status.OK, "Пользовательские каталоги созданы/сохранены."
            )
        return CheckResult(
            "Каталоги", Status.OK, "Пути проверены; запись и создание каталогов не выполнялись."
        )
    except OSError:
        return CheckResult(
            "Каталоги",
            Status.ERROR,
            "Каталоги недоступны. Проверьте права и пользовательские пути.",
        )


def run_doctor(
    settings: AppSettings, *, dry_run: bool = False, create_dirs: bool = False
) -> tuple[CheckResult, ...]:
    """Return independent results; missing optional tools are never fatal."""
    if dry_run and create_dirs:
        raise ValueError("dry-run cannot create directories")
    python_ok = (
        sys.version_info[:2] == (3, 14) and struct.calcsize("P") == 8 and sys._is_gil_enabled()
    )
    results = [
        CheckResult("Python", Status.OK if python_ok else Status.ERROR, platform.python_version()),
        CheckResult(
            "Windows", Status.OK if sys.platform == "win32" else Status.ERROR, platform.system()
        ),
        _directories(settings, create_dirs),
    ]
    for name, executable, arguments in (
        ("ffmpeg", settings.ffmpeg_path, ["-version"]),
        ("ffprobe", settings.ffprobe_path, ["-version"]),
        (
            "NVIDIA-драйвер",
            settings.nvidia_smi_path,
            ["--query-gpu=driver_version", "--format=csv,noheader"],
        ),
    ):
        results.append(
            CheckResult(name, Status.SKIP, "Запуск инструмента отключён в dry-run.")
            if dry_run
            else _tool(name, executable, arguments, settings.probe_timeout)
        )
    results.extend((_postgres(settings, dry_run), _cuda(settings, dry_run), _model(settings)))
    return tuple(results)
