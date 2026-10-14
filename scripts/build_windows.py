"""Build a fresh Windows onedir from the locked project; never overwrite user output."""

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from packaging.requirements import Requirement


def runtime_distributions() -> list[str]:
    pending = ["local-transcriber", "psycopg-binary", "nvidia-cuda-nvrtc-cu12", "pyinstaller"]
    found = set()
    while pending:
        name = pending.pop().lower().replace("_", "-")
        if name in found:
            continue
        distribution = metadata.distribution(name)
        found.add(name)
        for value in distribution.requires or []:
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return sorted(found)


def prepare_notices(root: Path, staging: Path) -> list[dict]:
    notices = staging / "licenses"
    notices.mkdir()
    shutil.copytree(root / "bundling/licenses", notices / "upstream")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    shutil.copy2(python_license, notices / "Python-LICENSE.txt")
    inventory = []
    for name in runtime_distributions():
        if name == "local-transcriber":
            continue  # No project licence is assigned on the owner's behalf.
        distribution = metadata.distribution(name)
        paths = []
        for file in distribution.files or []:
            if any(
                term in str(file).lower() for term in ("license", "licence", "copying", "notice")
            ):
                source = distribution.locate_file(file)
                if source.is_file() and source.suffix != ".py":
                    destination = notices / name / Path(str(file)).name
                    destination.parent.mkdir(exist_ok=True)
                    # Keep identically named notices from vendored subcomponents separately.
                    destination = destination.with_name(
                        hashlib.sha256(str(file).encode()).hexdigest()[:8] + "-" + destination.name
                    )
                    shutil.copy2(source, destination)
                    paths.append(destination.relative_to(staging).as_posix())
        upstream = notices / "upstream" / (name + ".txt")
        if not paths and upstream.is_file():
            paths.append(upstream.relative_to(staging).as_posix())
        if not paths:
            raise RuntimeError("Missing third-party licence: " + name)
        inventory.append(
            {
                "distribution": name,
                "version": distribution.version,
                "expression": distribution.metadata.get("License-Expression")
                or distribution.metadata.get("License"),
                "notices": paths,
            }
        )
    return inventory


def audit_bundle(bundle: Path) -> dict:
    """Check allowed artifacts; no source/media/.env/model directory is collected implicitly."""
    forbidden = {
        ".mp4",
        ".mkv",
        ".wav",
        ".flac",
        ".mp3",
        ".srt",
        ".vtt",
        ".pt",
        ".pth",
        ".safetensors",
        ".bin",
    }
    text_suffixes = {".txt", ".json", ".ini", ".cfg", ".toml", ".py", ".md", ".yaml"}
    credentials = re.compile(
        r"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|AKIA[0-9A-Z]{16})"
    )
    inventory = []
    for path in sorted(bundle.rglob("*")):
        relative = path.relative_to(bundle)
        if path.is_symlink() or path.is_junction():
            raise RuntimeError("Link found in Windows distribution")
        if not path.is_file() or relative.as_posix() == "dist-inventory.json":
            continue
        if (
            any(
                part.lower() in {".git", ".venv", "__pycache__", "recordings", "transcripts"}
                for part in relative.parts
            )
            or path.suffix.lower() in forbidden
            or path.name in {"direct_url.json", "RECORD"}
            or (path.name.startswith(".env") and not path.name.endswith(".example"))
        ):
            raise RuntimeError("Forbidden data/configuration in distribution")
        if path.suffix.lower() == ".onnx" and "faster_whisper/assets/" not in relative.as_posix():
            raise RuntimeError("Unexpected model weights in distribution")
        if path.suffix.lower() in text_suffixes and path.stat().st_size <= 4 * 1024 * 1024:
            if credentials.search(path.read_text(encoding="utf-8", errors="replace")):
                raise RuntimeError("Credential-like data in distribution")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        inventory.append(
            {"path": relative.as_posix(), "size": path.stat().st_size, "sha256": digest.hexdigest()}
        )
    return {"files": inventory, "bytes": sum(row["size"] for row in inventory)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="New dist root; never replace an existing directory"
    )
    args = parser.parse_args()
    if (
        os.name != "nt"
        or sys.version_info[:2] != (3, 14)
        or struct.calcsize("P") != 8
        or not sys._is_gil_enabled()
    ):
        parser.error("Requires CPython 3.14 x64 GIL on Windows")
    root = Path(__file__).resolve().parents[1]
    output = (args.output or root / "dist" / ("windows-" + uuid4().hex[:10])).resolve()
    if output.exists():
        parser.error("Output already exists; choose a new directory")
    work = root / "tmp" / ("windows-build-" + uuid4().hex)
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    notices = prepare_notices(root, work)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    stamp = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    sources = [
        *(root / "src/local_transcriber").rglob("*.py"),
        *(root / "bundling").rglob("*"),
        root / "pyproject.toml",
        root / "uv.lock",
    ]
    manifest = {
        "project": "LocalTranscribe",
        "version": metadata.version("local-transcriber"),
        "python": sys.version,
        "pyinstaller": metadata.version("pyinstaller"),
        "hooks": metadata.version("pyinstaller-hooks-contrib"),
        "git_commit": commit,
        "source_date_epoch": int(stamp),
        "dependency_notices": notices,
        "external": [
            "FFmpeg/ffprobe",
            "PostgreSQL server/tools",
            "Whisper model",
            "user .env/data",
        ],
        "inputs": {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(sources)
            if p.is_file() and "__pycache__" not in p.parts
        },
    }
    (work / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        LOCAL_TRANSCRIBER_BUILD_STAGING=str(work), SOURCE_DATE_EPOCH=stamp, PYTHONHASHSEED="0"
    )
    log = work / "pyinstaller.log"
    with log.open("wb") as stream:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--distpath",
                str(output),
                "--workpath",
                str(work / "work"),
                str(root / "bundling/LocalTranscribe.spec"),
            ],
            cwd=root,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    if process.returncode:
        print("BUILD FAILED; inspect", log)
        return process.returncode
    bundle = output / "LocalTranscribe"
    audit = audit_bundle(bundle)
    (bundle / "dist-inventory.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print("BUILD:", bundle / "LocalTranscribe.exe")
    print("SIZE BYTES:", audit["bytes"], "FILES:", len(audit["files"]))
    print("LOG:", log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
