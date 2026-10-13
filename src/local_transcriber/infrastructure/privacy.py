"""Private application-owned directories and secret-free subprocess environments."""

import csv
import ctypes
import os
import re
import subprocess
from pathlib import Path


class PrivateStorageError(ValueError):
    """Safe diagnostic: no user paths or subprocess output."""


def child_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("LOCAL_TRANSCRIBER_", "PG"))
        and not any(part in key.upper() for part in ("PASSWORD", "SECRET", "TOKEN", "API_KEY"))
        and key.upper() != "DATABASE_URL"
    }


def is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def private_directory(path: Path) -> Path:
    """Protect only a dedicated owned child; never chmod a configured user directory."""
    marker = path / ".local-transcriber-owned"
    created = False
    try:
        if not path.is_absolute():
            raise PrivateStorageError("Каталог приложения должен быть абсолютным.")
        if is_link(path) or is_link(marker):
            raise PrivateStorageError("Каталог приложения не может быть ссылкой/junction.")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.mkdir(mode=0o700)
            created = True
        except FileExistsError:
            if (
                not path.is_dir()
                or marker.stat().st_size != 26
                or marker.read_bytes() != b"LocalTranscriber owned v1\n"
            ):
                raise PrivateStorageError(
                    "Каталог уже существует без признака владения приложения."
                ) from None
        if created:
            if os.name == "nt":
                _windows_acl(path)
            else:
                path.chmod(0o700)
            with marker.open("xb") as file:
                file.write(b"LocalTranscriber owned v1\n")
        return path
    except (OSError, subprocess.SubprocessError, PrivateStorageError) as error:
        if created:
            try:
                # Only the empty directory we just created; never recursive cleanup/adoption.
                path.rmdir()
            except OSError:
                pass
        if isinstance(error, PrivateStorageError):
            raise
        raise PrivateStorageError("Не удалось подготовить защищённый каталог приложения.") from None


def _windows_acl(path: Path) -> None:
    system = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(system, len(system)):
        raise PrivateStorageError("Системные инструменты прав доступа недоступны.")
    options = dict(
        capture_output=True,
        timeout=10,
        shell=False,
        env=child_environment(),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    user = subprocess.run(
        [str(Path(system.value) / "whoami.exe"), "/user", "/fo", "csv", "/nh"], **options
    )
    # SID is ASCII even if the account's name is localized.
    sid = next(
        (
            field
            for row in csv.reader(user.stdout.decode("ascii", errors="replace").splitlines())
            for field in row
            if re.fullmatch(r"S-1-[0-9-]+", field)
        ),
        None,
    )
    if user.returncode or sid is None:
        raise PrivateStorageError("Не удалось определить права текущего пользователя.")
    result = subprocess.run(
        [
            str(Path(system.value) / "icacls.exe"),
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"*{sid}:(OI)(CI)F",
            "*S-1-5-18:(OI)(CI)F",
            "*S-1-5-32-544:(OI)(CI)F",
        ],
        **options,
    )
    if result.returncode:
        raise PrivateStorageError("Не удалось ограничить ACL каталога приложения.")
