"""Windows build regressions and opt-in real executable deployment smoke."""

import ctypes
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from local_transcriber.infrastructure import doctor
from local_transcriber.infrastructure.database.models import (
    TranscriptionJob,
    TranscriptSegment,
    TranscriptVersion,
)
from local_transcriber.infrastructure.database.session import (
    database_url,
    make_engine,
    session_factory,
)
from local_transcriber.infrastructure.settings import AppSettings, load_settings

ROOT = Path(__file__).resolve().parents[1]


def build_module():
    spec = importlib.util.spec_from_file_location(
        "windows_build", ROOT / "scripts/build_windows.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_distribution_audit_rejects_private_data_and_keeps_files(tmp_path):
    audit = build_module().audit_bundle
    (tmp_path / "safe.txt").write_text("notices")
    assert audit(tmp_path)["bytes"] == 7
    for name in (".env", "recording.mp4", "model.bin", "direct_url.json", "RECORD"):
        target = tmp_path / name
        target.write_bytes(b"keep")
        with pytest.raises(RuntimeError):
            audit(tmp_path)
        assert target.read_bytes() == b"keep"
        target.unlink()
    (tmp_path / "token.txt").write_text("sk-" + "a" * 40)
    with pytest.raises(RuntimeError, match="Credential"):
        audit(tmp_path)


def test_frozen_doctor_does_not_relaunch_exe_as_python(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda _: object())
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "1", ""))
    monkeypatch.setattr(doctor, "_run", run)
    assert doctor._cuda(AppSettings(_env_file=None), False).status == doctor.Status.OK
    assert run.call_args.args[0] == [sys.executable, "--_cuda-count"]


def test_frozen_cuda_uses_bundled_dll_directory(tmp_path, monkeypatch):
    from local_transcriber.infrastructure import faster_whisper_engine as runtime

    folder = tmp_path / "nvidia/cudnn/bin"
    folder.mkdir(parents=True)
    (folder / "cudnn64_9.dll").write_bytes(b"fixture")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    add = Mock(return_value=object())
    load = Mock(return_value=object())
    monkeypatch.setattr(os, "add_dll_directory", add)
    monkeypatch.setattr(runtime.ctypes, "WinDLL", load)
    engine = runtime.FasterWhisperEngine(runtime.FasterWhisperConfig())
    engine._prepare_cuda_dlls()
    add.assert_called_once_with(str(folder))
    load.assert_called_once_with(str(folder / "cudnn64_9.dll"))


def _visible_windows(pid):
    user = ctypes.windll.user32
    result = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(window, _):
        process_id = ctypes.c_ulong()
        user.GetWindowThreadProcessId(ctypes.c_void_p(window), ctypes.byref(process_id))
        if process_id.value == pid and user.IsWindowVisible(ctypes.c_void_p(window)):
            result.append(window)
        return True

    callback = callback_type(visit)
    user.EnumWindows(callback, None)
    return result


@pytest.mark.integration
def test_real_packaged_fresh_config_readonly_gpu_postgresql_offline(tmp_path):
    value = os.environ.get("LOCAL_TRANSCRIBER_PACKAGED_EXE")
    if not value or os.environ.get("LOCAL_TRANSCRIBER_OWNED_TEST_CLUSTER") != "1":
        pytest.skip("Run check_postgresql.py --packaged-exe PATH for owned-cluster packaged smoke")
    executable = Path(value).resolve()
    bundle = executable.parent
    assert bundle.is_relative_to((ROOT / "dist").resolve())
    assert (bundle / "_internal/build-manifest.json").is_file()
    assert not list(bundle.rglob("direct_url.json"))
    assert not list(bundle.rglob("RECORD"))
    settings = load_settings()
    assert settings.model_path.is_dir()
    data = ROOT / "tmp/fleurs-ru-test-32"
    provenance = json.loads((data / "provenance.json").read_text())
    source = tmp_path / "OBS & Кириллица (sample).wav"
    shutil.copy2(data / provenance["samples"][0]["filename"], source)
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    source.chmod(stat.S_IREAD)
    profile = tmp_path / "fresh profile"
    profile.mkdir()
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("LOCAL_TRANSCRIBER_", "PYTHON", "PYTEST"))
        and k
        not in {"VIRTUAL_ENV", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"}
    }
    url = database_url(settings, test=True).set(drivername="postgresql")
    environment.update(
        LOCALAPPDATA=str(profile / "LocalAppData"),
        APPDATA=str(profile / "Roaming"),
        USERPROFILE=str(profile),
        QT_QPA_PLATFORM="windows",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        LOCAL_TRANSCRIBER_DATA_DIR=str(profile / "данные"),
        LOCAL_TRANSCRIBER_MODEL_PATH=str(settings.model_path),
        LOCAL_TRANSCRIBER_FFMPEG_PATH=settings.ffmpeg_path,
        LOCAL_TRANSCRIBER_FFPROBE_PATH=settings.ffprobe_path,
        LOCAL_TRANSCRIBER_POSTGRES_PROBE_PATH="C:/Program Files/PostgreSQL/18/bin/pg_isready.exe",
        LOCAL_TRANSCRIBER_NVIDIA_SMI_PATH=shutil.which("nvidia-smi") or "nvidia-smi",
        LOCAL_TRANSCRIBER_POSTGRES_DSN=url.render_as_string(hide_password=False),
        LOCAL_TRANSCRIBER_OFFLINE_AUDIT=str(profile / "offline-audit.txt"),
        PATH=os.environ["SystemRoot"] + "/System32",
    )

    def run(*arguments, env=None):
        result = subprocess.run(
            [str(executable), *map(str, arguments)],
            env=env or environment,
            cwd=profile,
            capture_output=True,
            timeout=150,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")[-1000:]
        return result.stdout.decode("utf-8", errors="replace")

    sid_output = subprocess.run(
        [os.environ["SystemRoot"] + "/System32/whoami.exe", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
    )
    import re

    sid = "*" + re.search(r"S-1-[0-9-]+", sid_output.stdout).group()
    icacls = os.environ["SystemRoot"] + "/System32/icacls.exe"
    original_files = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
    denied = False
    try:
        subprocess.run(
            [icacls, str(bundle), "/deny", sid + ":(OI)(CI)(WD,AD,WEA,WA,DC)"],
            check=True,
            capture_output=True,
        )
        denied = True
        probe = bundle / ("owned-write-probe-" + uuid4().hex)
        try:
            with pytest.raises(PermissionError):
                probe.write_bytes(b"probe")
        finally:
            if probe.exists():
                probe.unlink()
        assert "0.0.1" in run("--version")
        assert "transcribe" in run("--help")
        run("doctor", "--dry-run")
        assert "CUDA" in run("doctor")
        run("db-upgrade")
        run("db-upgrade")
        inspected = json.loads(run("inspect", source))
        assert inspected["audio_streams"][0]["stream_index"] == 0
        assert inspected["path"] == str(source.resolve())
        assert inspected["filename"] == source.name
        run("import", source)
        lines = run("transcribe", source, "--stream-index", "0", "--end-ms", "8000")
        events = [json.loads(line) for line in lines.splitlines() if line.startswith("{")]
        job = UUID(next(e["job_id"] for e in events if e["status"] == "COMPLETED"))
        engine = make_engine(settings, test=True)
        try:
            with session_factory(engine)() as session:
                assert session.get(TranscriptionJob, job).status == "COMPLETED"
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(TranscriptSegment)
                        .where(TranscriptSegment.job_id == job)
                    )
                    > 0
                )
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(TranscriptVersion)
                        .where(TranscriptVersion.job_id == job)
                    )
                    == 2
                )
        finally:
            engine.dispose()
        run("export", str(job), profile / "result.txt")
        assert (profile / "result.txt").stat().st_size > 0
        # Actual native Qt top-level window; close through WM_CLOSE, not forced termination.
        with (profile / "gui.log").open("wb") as log:
            gui = subprocess.Popen(
                [str(executable), "gui"],
                env=environment,
                cwd=profile,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                deadline = time.monotonic() + 25
                windows = []
                while time.monotonic() < deadline and gui.poll() is None:
                    windows = _visible_windows(gui.pid)
                    if windows:
                        break
                    time.sleep(0.1)
                assert windows, "Native packaged GUI did not display a window"
                for window in windows:
                    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(window), 0x0010, 0, 0)
                assert gui.wait(timeout=20) == 0
            finally:
                if gui.poll() is None:
                    gui.terminate()
                    gui.wait(timeout=10)
        missing = environment | {"LOCAL_TRANSCRIBER_MODEL_PATH": str(profile / "missing-model")}
        failure = subprocess.run(
            [str(executable), "transcribe", str(source), "--stream-index", "0"],
            cwd=profile,
            env=missing,
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert failure.returncode != 0
        assert url.password.encode() not in failure.stderr
        assert "REMOTE_ATTEMPT" not in (profile / "offline-audit.txt").read_text()
        assert "ACTIVE" in (profile / "offline-audit.txt").read_text()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == fingerprint
        assert original_files == {
            p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()
        }
    finally:
        if denied:
            subprocess.run([icacls, str(bundle), "/remove:d", sid], check=True, capture_output=True)
        source.chmod(stat.S_IREAD | stat.S_IWRITE)
