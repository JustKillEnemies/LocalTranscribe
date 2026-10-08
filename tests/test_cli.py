"""Step 01: installed-package imports, real launchers and CLI failures."""

import os
import subprocess
import sys
import tomllib
from importlib.metadata import distribution
from pathlib import Path

import pytest

import local_transcriber
from local_transcriber.__main__ import main

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _launcher(kind: str) -> list[str]:
    if kind == "module":
        return [sys.executable, "-I", "-X", "utf8", "-m", "local_transcriber"]
    if kind == "wrapper":
        return [sys.executable, str(PROJECT_ROOT / "src/main.py")]
    executable = Path(sys.executable).parent / (
        "local-transcriber.exe" if os.name == "nt" else "local-transcriber"
    )
    assert executable.is_file(), f"Console script is not installed: {executable}"
    return [str(executable)]


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )


def test_installed_metadata_matches_project() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    metadata = distribution("local-transcriber")
    assert metadata.version == project["project"]["version"]
    assert metadata.requires is None
    scripts = {
        entry.name: entry.value
        for entry in metadata.entry_points
        if entry.group == "console_scripts"
    }
    assert scripts["local-transcriber"] == "local_transcriber.__main__:main"
    assert local_transcriber.__file__ is not None


def test_isolated_import_smoke_has_no_output_or_heavy_imports(tmp_path: Path) -> None:
    code = (
        "import sys; import local_transcriber; import local_transcriber.__main__; "
        "assert not any(name in sys.modules for name in "
        "('torch', 'ctranslate2', 'faster_whisper', 'silero_vad', "
        "'onnxruntime', 'PySide6', 'sqlalchemy'))"
    )
    result = _run([sys.executable, "-I", "-B", "-c", code], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["module", "wrapper", "console"])
def test_version_from_all_launchers(kind: str) -> None:
    result = _run([*_launcher(kind), "--version"], PROJECT_ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"local-transcriber {distribution('local-transcriber').version}\n"
    assert result.stderr == ""


@pytest.mark.parametrize("kind", ["module", "wrapper", "console"])
@pytest.mark.parametrize("arguments", [[], ["--help"], ["-h"]])
def test_help_and_default_command(kind: str, arguments: list[str]) -> None:
    result = _run([*_launcher(kind), *arguments], PROJECT_ROOT)
    assert result.returncode == 0, result.stderr
    assert "--help" in result.stdout
    assert "--version" in result.stdout
    assert "следующих этапах" in result.stdout
    assert result.stderr == ""
    assert "\x1b[" not in result.stdout


@pytest.mark.parametrize("kind", ["module", "wrapper", "console"])
@pytest.mark.parametrize("argument", ["--unknown-option", "--vers", "doctor"])
def test_invalid_command_reports_error_without_changing_files(
    kind: str, argument: str, tmp_path: Path
) -> None:
    sentinel = tmp_path / "запись.mkv"
    original = b"synthetic media preservation sentinel"
    sentinel.write_bytes(original)
    result = _run([*_launcher(kind), argument], tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert argument in result.stderr
    assert "usage:" in result.stderr
    assert "Traceback" not in result.stderr
    assert sentinel.read_bytes() == original
    assert list(tmp_path.iterdir()) == [sentinel]


@pytest.mark.parametrize("kind", ["module", "wrapper", "console"])
def test_launch_from_cyrillic_directory_with_spaces(kind: str, tmp_path: Path) -> None:
    directory = tmp_path / "Проверка запуска с пробелами"
    directory.mkdir()
    result = _run([*_launcher(kind), "--version"], directory)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"local-transcriber {distribution('local-transcriber').version}\n"
    assert result.stderr == ""
    assert list(directory.iterdir()) == []


def test_main_with_explicit_empty_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "--help" in captured.out
    assert captured.err == ""


def test_main_rejects_unknown_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--not-supported"])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "--not-supported" in captured.err
    assert captured.out == ""
