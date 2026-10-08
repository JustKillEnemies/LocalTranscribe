"""Step 02: independent checks, subprocess contracts and read-only CLI integration."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from local_transcriber.infrastructure import doctor
from local_transcriber.infrastructure.settings import AppSettings


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    for key in tuple(os.environ):
        if key.upper().startswith("LOCAL_TRANSCRIBER_"):
            monkeypatch.delenv(key)
    return AppSettings(data_dir=tmp_path / "Папки приложения с пробелами", _env_file=None)


def _by_name(results: tuple[doctor.CheckResult, ...]) -> dict[str, doctor.CheckResult]:
    return {item.name: item for item in results}


def _result(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "private-password")


def test_missing_tools_and_model_do_not_crash(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda _: None)
    results = _by_name(doctor.run_doctor(settings))
    for name in ("ffmpeg", "ffprobe", "PostgreSQL", "NVIDIA-драйвер", "CUDA/CTranslate2", "Модель"):
        assert results[name].status is doctor.Status.MISSING
    assert len(results) == 9


def test_dry_run_has_no_subprocess_or_directory_writes(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Mock(side_effect=AssertionError("No subprocess allowed"))
    monkeypatch.setattr(doctor, "_run", run)
    results = _by_name(doctor.run_doctor(settings, dry_run=True))
    run.assert_not_called()
    assert not settings.data_dir.exists()
    assert results["ffmpeg"].status is doctor.Status.SKIP
    assert results["PostgreSQL"].status is doctor.Status.SKIP


@pytest.mark.parametrize("command", ["ffmpeg", "ffprobe"])
def test_tool_version_and_unicode_path(
    command: str, settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = str(settings.data_dir / "Инструменты/ffmpeg.exe")
    monkeypatch.setattr(doctor.shutil, "which", lambda _: path)
    run = Mock(return_value=_result(f"{command} version 7.1-test\n"))
    monkeypatch.setattr(doctor, "_run", run)
    result = doctor._tool(command, path, ["-version"], 5)
    assert result.status is doctor.Status.OK
    run.assert_called_once_with([path, "-version"], 5)


@pytest.mark.parametrize(
    ("effect", "message"),
    [
        (subprocess.TimeoutExpired("test", 1), "тайм-аут"),
        (PermissionError("private-password"), "запустить"),
        (OSError("private-password"), "запустить"),
    ],
)
def test_tool_failures_are_safe(
    effect: Exception, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "tool.exe")
    monkeypatch.setattr(doctor, "_run", Mock(side_effect=effect))
    result = doctor._tool("ffmpeg", "tool", ["-version"], 1)
    assert result.status is doctor.Status.ERROR
    assert message in result.message
    assert "private-password" not in result.message


@pytest.mark.parametrize("stdout,code", [("unexpected", 0), ("", 1)])
def test_invalid_tool_response(stdout: str, code: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "tool.exe")
    monkeypatch.setattr(doctor, "_run", Mock(return_value=_result(stdout, code)))
    assert doctor._tool("ffmpeg", "tool", ["-version"], 1).status is doctor.Status.ERROR


@pytest.mark.parametrize(
    "dsn",
    [
        "not-a-dsn-private-password",
        "postgresql://user:private-password@external.example/database",
        "postgresql://user:private-password@localhost/",
        "postgresql://user:private-password@localhost/database?host=external.example",
        "postgresql://user:private-password@localhost,external.example/database",
    ],
)
def test_bad_database_dsn_is_error_and_does_not_probe(
    dsn: str, settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(data_dir=settings.data_dir, postgres_dsn=dsn, _env_file=None)
    run = Mock(side_effect=AssertionError("Must not contact database"))
    monkeypatch.setattr(doctor, "_run", run)
    result = doctor._postgres(settings, False)
    assert result.status is doctor.Status.ERROR
    assert "private-password" not in result.message
    run.assert_not_called()


@pytest.mark.parametrize(
    "code,status",
    [
        (0, doctor.Status.OK),
        (1, doctor.Status.ERROR),
        (2, doctor.Status.ERROR),
        (3, doctor.Status.ERROR),
    ],
)
def test_postgres_readiness_codes_and_no_credentials(
    code: int, status: doctor.Status, settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = AppSettings(
        data_dir=settings.data_dir,
        postgres_dsn="postgresql://test:private-password@localhost:5433/test",
        _env_file=None,
    )
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "pg_isready.exe")
    run = Mock(return_value=_result(returncode=code))
    monkeypatch.setattr(doctor, "_run", run)
    result = doctor._postgres(configured, False)
    assert result.status is status
    command = run.call_args.args[0]
    assert "5433" in command
    assert "private-password" not in str(command)
    assert "private-password" not in result.message


@pytest.mark.parametrize(
    "count,status",
    [
        ("1", doctor.Status.OK),
        ("0", doctor.Status.MISSING),
        ("broken", doctor.Status.ERROR),
        ("true", doctor.Status.ERROR),
    ],
)
def test_cuda_isolated_probe(
    count: str, status: doctor.Status, settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda _: object())
    run = Mock(return_value=_result(count))
    monkeypatch.setattr(doctor, "_run", run)
    result = doctor._cuda(settings, False)
    assert result.status is status
    assert "-I" in run.call_args.args[0]


def test_cuda_import_failure_timeout_and_cpu(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(doctor, "_run", Mock(return_value=_result(returncode=1)))
    assert doctor._cuda(settings, False).status is doctor.Status.ERROR
    monkeypatch.setattr(doctor, "_run", Mock(side_effect=subprocess.TimeoutExpired("test", 1)))
    assert doctor._cuda(settings, False).status is doctor.Status.ERROR
    assert (
        doctor._cuda(settings.model_copy(update={"device": "cpu"}), False).status
        is doctor.Status.SKIP
    )


def test_model_manifest_and_corruption(settings: AppSettings) -> None:
    path = settings.model_path
    path.mkdir(parents=True)
    assert doctor._model(settings).status is doctor.Status.ERROR
    (path / "model.bin").write_bytes(b"synthetic fixture, not real model")
    for name in ("config.json", "tokenizer.json"):
        (path / name).write_text("{}", encoding="utf-8")
    assert doctor._model(settings).status is doctor.Status.OK
    (path / "config.json").write_text("bad JSON", encoding="utf-8")
    assert doctor._model(settings).status is doctor.Status.ERROR
    assert (path / "model.bin").read_bytes() == b"synthetic fixture, not real model"


def test_directories_explicit_creation_and_conflict(settings: AppSettings, tmp_path: Path) -> None:
    assert doctor._directories(settings, True).status is doctor.Status.OK
    assert all(path.is_dir() for path in settings.directories())
    sentinel = settings.logs_dir / "user.log"
    sentinel.write_bytes(b"preserve")
    assert doctor._directories(settings, True).status is doctor.Status.OK
    assert sentinel.read_bytes() == b"preserve"
    conflict = tmp_path / "file"
    conflict.write_bytes(b"preserve")
    configured = settings.model_copy(update={"temp_dir": conflict})
    assert doctor._directories(configured, True).status is doctor.Status.ERROR
    assert conflict.read_bytes() == b"preserve"
    with pytest.raises(ValueError):
        doctor.run_doctor(settings, dry_run=True, create_dirs=True)


def test_run_contract_no_shell_or_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_TRANSCRIBER_POSTGRES_PASSWORD", "private-password")
    monkeypatch.setenv("PGPASSWORD", "private-password")
    run = Mock(return_value=_result())
    monkeypatch.setattr(doctor.subprocess, "run", run)
    doctor._run(["tool.exe", "argument with spaces"], 5)
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["timeout"] == 5
    assert "LOCAL_TRANSCRIBER_POSTGRES_PASSWORD" not in run.call_args.kwargs["env"]
    assert "PGPASSWORD" not in run.call_args.kwargs["env"]


@pytest.mark.skipif(os.name != "nt", reason="Windows executable policy")
def test_windows_shell_scripts_rejected() -> None:
    for name in ("unsafe.cmd", "unsafe.BAT", "unsafe.ps1"):
        with pytest.raises(ValueError):
            doctor._executable(name)


def test_real_subprocess_unicode_arguments(tmp_path: Path) -> None:
    script = tmp_path / "Проверка с пробелами.py"
    script.write_text("print('real subprocess')\n", encoding="utf-8")
    result = doctor._run([sys.executable, "-B", str(script)], 5)
    assert result.returncode == 0
    assert result.stdout.strip() == "real subprocess"


@pytest.mark.parametrize("arguments", [["doctor"], ["doctor", "--dry-run"]])
def test_cli_doctor_without_gpu_is_read_only(arguments: list[str], tmp_path: Path) -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("LOCAL_TRANSCRIBER_")
    }
    env["LOCALAPPDATA"] = str(tmp_path / "Профиль Windows")
    env["LOCAL_TRANSCRIBER_NVIDIA_SMI_PATH"] = str(tmp_path / "missing-nvidia.exe")
    env["LOCAL_TRANSCRIBER_FFMPEG_PATH"] = str(tmp_path / "missing-ffmpeg.exe")
    env["LOCAL_TRANSCRIBER_FFPROBE_PATH"] = str(tmp_path / "missing-ffprobe.exe")
    env["LOCAL_TRANSCRIBER_POSTGRES_PROBE_PATH"] = str(tmp_path / "missing-pg.exe")
    env["PYTHONIOENCODING"] = "utf-8"
    sentinel = tmp_path / "Запись.mkv"
    sentinel.write_bytes(b"preserve")
    result = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-m", "local_transcriber", *arguments],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    for name in (
        "Python",
        "Windows",
        "ffmpeg",
        "ffprobe",
        "PostgreSQL",
        "NVIDIA-драйвер",
        "CUDA/CTranslate2",
        "Модель",
    ):
        assert name + ":" in result.stdout
    assert "Traceback" not in result.stderr
    assert sentinel.read_bytes() == b"preserve"
    assert list(tmp_path.iterdir()) == [sentinel]


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://user:private-password@localhost:0/db",
        "postgresql://user:private-password@localhost/db#fragment",
    ],
)
def test_postgres_port_zero_and_fragment_regression(dsn: str, settings: AppSettings) -> None:
    configured = AppSettings(data_dir=settings.data_dir, postgres_dsn=dsn, _env_file=None)
    assert doctor._postgres(configured, True).status is doctor.Status.ERROR


@pytest.mark.parametrize(
    "exception", [subprocess.TimeoutExpired("secret", 1), PermissionError("secret")]
)
def test_postgres_process_failures(
    exception: Exception, settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "pg_isready.exe")
    monkeypatch.setattr(doctor, "_run", Mock(side_effect=exception))
    result = doctor._postgres(settings, False)
    assert result.status is doctor.Status.ERROR
    assert "secret" not in result.message


@pytest.mark.parametrize(
    "output,status",
    [
        ("555.99\n", doctor.Status.OK),
        ("", doctor.Status.MISSING),
        ("unexpected", doctor.Status.ERROR),
    ],
)
def test_nvidia_driver_response(
    output: str, status: doctor.Status, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "nvidia-smi.exe")
    monkeypatch.setattr(doctor, "_run", Mock(return_value=_result(output)))
    assert doctor._tool("NVIDIA-драйвер", "nvidia-smi", [], 5).status is status


def test_directory_permission_error_is_reported(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "mkdir", Mock(side_effect=PermissionError("private-password")))
    result = doctor._directories(settings, True)
    assert result.status is doctor.Status.ERROR
    assert "private-password" not in result.message


@pytest.mark.parametrize("scenario", ["bad-dsn", "invalid-setting", "missing-env"])
def test_cli_safe_configuration_errors(scenario: str, tmp_path: Path) -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("LOCAL_TRANSCRIBER_")
    }
    environment["LOCALAPPDATA"] = str(tmp_path / "profile")
    environment["PYTHONIOENCODING"] = "utf-8"
    arguments = ["doctor", "--dry-run"]
    if scenario == "bad-dsn":
        environment["LOCAL_TRANSCRIBER_POSTGRES_DSN"] = (
            "postgresql://test:secret-cli-password@external.example/db"
        )
        expected = 0
    elif scenario == "invalid-setting":
        environment["LOCAL_TRANSCRIBER_POSTGRES_PORT"] = "secret-cli-password"
        expected = 2
    else:
        arguments.extend(["--env-file", str(tmp_path / "missing.env")])
        expected = 2
    result = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-m", "local_transcriber", *arguments],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == expected
    assert "ERROR" in result.stdout + result.stderr
    assert "secret-cli-password" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["console", "wrapper"])
def test_doctor_from_preserved_launchers(kind: str, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    if kind == "console":
        command = [str(Path(sys.executable).parent / "local-transcriber.exe")]
    else:
        command = [sys.executable, str(root / "src/main.py")]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [*command, "doctor", "--dry-run"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "PostgreSQL:" in result.stdout
