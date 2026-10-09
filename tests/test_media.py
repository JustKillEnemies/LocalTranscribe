"""Step 04 media inspection unit tests with saved ffprobe responses."""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from local_transcriber.__main__ import main
from local_transcriber.application.media_import import ImportMedia, ImportResult
from local_transcriber.domain.media import AudioStreamInfo, MediaInfo
from local_transcriber.infrastructure.media import (
    MAX_PROBE_OUTPUT,
    SUPPORTED_EXTENSIONS,
    MediaInspectionError,
    MediaInspector,
    media_fingerprint,
    parse_probe,
)

FIXTURES = Path(__file__).parent / "fixtures/ffprobe"


def test_supported_extensions_match_step_04() -> None:
    assert SUPPORTED_EXTENSIONS == {
        ".mkv",
        ".mp4",
        ".mov",
        ".wav",
        ".mp3",
        ".m4a",
        ".flac",
        ".webm",
    }


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def media_file(tmp_path: Path, name: str = "OBS запись с пробелами.MKV") -> Path:
    path = tmp_path / name
    path.write_bytes(b"synthetic media")
    return path


def test_parse_mixed_streams_preserves_real_indices_and_labels(tmp_path: Path) -> None:
    path = media_file(tmp_path)
    result = parse_probe(fixture("mixed_streams.json"), path, "v1:test")
    assert result.duration_ms == 12346
    assert result.container == "matroska,webm"
    assert [stream.stream_index for stream in result.audio_streams] == [1, 4]
    assert result.audio_streams[0].language == "rus"
    assert result.audio_streams[0].title == "Микрофон"
    assert result.audio_streams[1].title == "Desktop Audio"


def test_no_audio_is_explainable(tmp_path: Path) -> None:
    with pytest.raises(MediaInspectionError, match="нет аудиодорожек"):
        parse_probe(fixture("no_audio.json"), media_file(tmp_path, "video.mp4"), "v1:test")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"format": {}, "streams": []},
        {"format": {"format_name": "mkv", "duration": "NaN"}, "streams": []},
    ],
)
def test_invalid_probe_structures_are_rejected(tmp_path: Path, payload: object) -> None:
    with pytest.raises(MediaInspectionError):
        parse_probe(payload, media_file(tmp_path), "v1:test")


def test_fingerprint_is_bounded_stable_and_sensitive_to_metadata(tmp_path: Path) -> None:
    path = tmp_path / "large.mkv"
    path.write_bytes(b"A" * (3 * 1024 * 1024))
    first = media_fingerprint(path)
    assert media_fingerprint(path) == first
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert media_fingerprint(path) != first
    assert first.startswith("v1:3145728:")


class FakeProcess:
    def __init__(self, arguments, **kwargs) -> None:
        self.arguments = arguments
        self.returncode = 0
        kwargs["stdout"].write(json.dumps(fixture("mixed_streams.json")).encode())

    def wait(self, timeout=None) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def test_inspector_passes_unicode_path_as_one_argument_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = media_file(tmp_path)
    processes: list[FakeProcess] = []

    def start(arguments, **kwargs):
        process = FakeProcess(arguments, **kwargs)
        processes.append(process)
        assert kwargs["shell"] is False
        return process

    monkeypatch.setattr("shutil.which", lambda value: "C:/tools/ffprobe.exe")
    monkeypatch.setattr("subprocess.Popen", start)
    result = MediaInspector("ffprobe", timeout=2).inspect(path)
    assert result.path == path.resolve()
    assert processes[0].arguments[-1] == str(path.resolve())
    assert processes[0].arguments[-2:] == ["json", str(path.resolve())]


def test_timeout_kills_ffprobe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = media_file(tmp_path)

    class TimedOut(FakeProcess):
        def wait(self, timeout=None) -> int:
            if self.returncode == 0:
                raise subprocess.TimeoutExpired(self.arguments, timeout)
            return self.returncode

    process = None

    def start(arguments, **kwargs):
        nonlocal process
        process = TimedOut(arguments, **kwargs)
        return process

    monkeypatch.setattr("shutil.which", lambda value: "C:/tools/ffprobe.exe")
    monkeypatch.setattr("subprocess.Popen", start)
    with pytest.raises(MediaInspectionError, match="тайм-аут"):
        MediaInspector("ffprobe", timeout=1).inspect(path)
    assert process is not None and process.returncode == -9


@pytest.mark.parametrize("name", ["missing.mkv", "media.exe", "folder.mkv"])
def test_unavailable_or_unsupported_input_is_rejected(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    if name == "folder.mkv":
        path.mkdir()
    elif name == "media.exe":
        path.write_bytes(b"not media")
    with pytest.raises(MediaInspectionError):
        MediaInspector("missing-ffprobe", timeout=1).inspect(path)


def test_invalid_json_and_output_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = media_file(tmp_path)

    class BadProcess(FakeProcess):
        def __init__(self, arguments, **kwargs) -> None:
            self.arguments = arguments
            self.returncode = 0
            kwargs["stdout"].write(b"{" + b"x" * MAX_PROBE_OUTPUT)

    monkeypatch.setattr("shutil.which", lambda value: "C:/tools/ffprobe.exe")
    monkeypatch.setattr("subprocess.Popen", BadProcess)
    with pytest.raises(MediaInspectionError, match="лимит"):
        MediaInspector("ffprobe", timeout=1).inspect(path)


def test_invalid_json_and_ffprobe_failure_are_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = media_file(tmp_path)

    class InvalidJson(FakeProcess):
        def __init__(self, arguments, **kwargs) -> None:
            self.arguments = arguments
            self.returncode = 0
            kwargs["stdout"].write(b"not-json")

    monkeypatch.setattr("shutil.which", lambda value: "C:/tools/ffprobe.exe")
    monkeypatch.setattr("subprocess.Popen", InvalidJson)
    with pytest.raises(MediaInspectionError, match="некорректный JSON"):
        MediaInspector("ffprobe", timeout=1).inspect(path)

    class Failed(FakeProcess):
        def __init__(self, arguments, **kwargs) -> None:
            self.arguments = arguments
            self.returncode = 1
            kwargs["stderr"].write(b"private source details")

    monkeypatch.setattr("subprocess.Popen", Failed)
    with pytest.raises(MediaInspectionError) as error:
        MediaInspector("ffprobe", timeout=1).inspect(path)
    assert "private source details" not in str(error.value)


def test_cli_inspect_prints_machine_readable_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = media_file(tmp_path)
    metadata = MediaInfo(
        path=path,
        filename=path.name,
        size_bytes=15,
        duration_ms=1234,
        container="matroska,webm",
        fingerprint="v1:test",
        audio_streams=(AudioStreamInfo(3, "opus", 48000, 2, "rus", "Микрофон"),),
    )
    monkeypatch.setattr(MediaInspector, "inspect", lambda self, source: metadata)
    assert main(["inspect", str(path)]) == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["audio_streams"][0]["stream_index"] == 3
    assert output["audio_streams"][0]["language"] == "rus"
    assert captured.err == ""


def test_cli_inspect_reports_safe_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        MediaInspector,
        "inspect",
        lambda self, source: (_ for _ in ()).throw(MediaInspectionError("Файл повреждён.")),
    )
    assert main(["inspect", str(tmp_path / "broken.mkv")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Файл повреждён" in captured.err
    assert "Traceback" not in captured.err


def test_cli_import_reports_id_and_repeat_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = media_file(tmp_path)
    metadata = MediaInfo(
        path=path,
        filename=path.name,
        size_bytes=15,
        duration_ms=100,
        container="matroska,webm",
        fingerprint="v1:test",
        audio_streams=(AudioStreamInfo(1, "opus", 48000, 2),),
    )
    identifier = uuid4()

    class FakeEngine:
        def dispose(self) -> None:
            pass

    monkeypatch.setattr(
        "local_transcriber.infrastructure.database.session.make_engine",
        lambda settings: FakeEngine(),
    )
    monkeypatch.setattr(
        "local_transcriber.infrastructure.database.session.session_factory",
        lambda engine: object(),
    )
    monkeypatch.setattr(
        ImportMedia,
        "execute",
        lambda self, source: ImportResult(identifier, False, metadata),
    )
    assert main(["import", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["media_id"] == str(identifier)
    assert output["created"] is False
