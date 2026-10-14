# Locked Windows x64 onedir build; explicit inputs, no project-directory recursion.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
staging = Path(os.environ["LOCAL_TRANSCRIBER_BUILD_STAGING"])
excluded = ("local_transcriber.infrastructure.benchmark", "local_transcriber.infrastructure.public_benchmark")
hidden = collect_submodules("local_transcriber", filter=lambda name: not name.startswith(excluded))
hidden += ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtMultimedia",
           "PySide6.QtMultimediaWidgets", "psycopg_binary", "sqlalchemy.dialects.postgresql.psycopg"]
datas = [(str(staging / "licenses"), "licenses"),
         (str(root / ".env.example"), "examples"), (str(staging / "build-manifest.json"), ".")]
for path in (root / "migrations").rglob("*"):
    if path.is_file() and path.suffix in {".py", ".mako"} and "__pycache__" not in path.parts:
        datas.append((str(path), path.parent.relative_to(root).as_posix()))
for name in ("local-transcriber", "faster-whisper", "ctranslate2", "nvidia-cublas-cu12", "nvidia-cudnn-cu12"):
    for source, destination in copy_metadata(name):
        for path in Path(source).rglob("*"):
            if path.is_file() and path.name not in {"direct_url.json", "RECORD"}:
                datas.append((str(path), str(Path(destination) / path.parent.relative_to(source))))
datas += collect_data_files("faster_whisper")
datas += collect_data_files("alembic")
binaries = collect_dynamic_libs("ctranslate2")
import sysconfig
purelib = Path(sysconfig.get_paths()["purelib"])
for folder in ("cublas/bin", "cudnn/bin", "cuda_nvrtc/bin"):
    for library in (purelib / "nvidia" / folder).glob("*.dll"):
        binaries.append((str(library), "nvidia/" + folder))
a = Analysis([str(root / "bundling/entry.py")], pathex=[str(root / "src")],
             binaries=binaries, datas=datas, hiddenimports=hidden,
             hookspath=[], runtime_hooks=[str(root / "bundling/offline_audit.py")],
             excludes=["torch", "tensorflow", "jax", "pytest", "psutil", "PySide6.QtWebEngineCore",
                       "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick"],
             noarchive=False)
# Automatic package hooks may re-add metadata directories after explicit copy_metadata.
a.datas = [entry for entry in a.datas if Path(entry[0]).name not in {"direct_url.json", "RECORD"}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LocalTranscribe",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LocalTranscribe")
