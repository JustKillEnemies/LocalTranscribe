"""Publish UTF-8 files atomically; only our own temporary file is cleaned up."""

import errno
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from local_transcriber.application.export import (
    Cancellation,
    ExportCollision,
    ExportError,
    check_cancel,
)


class AtomicExportWriter:
    def write(
        self,
        destination: Path,
        fragments: Iterable[str],
        *,
        overwrite: bool = False,
        cancel: Cancellation | None = None,
    ) -> Path:
        destination = destination.absolute()
        name = destination.name
        if any(ord(character) < 32 for character in name):
            raise ExportError("Имя файла содержит управляющие символы.")
        if os.name == "nt" and (
            any(character in name for character in '<>:"|?*')
            or name.endswith((".", " "))
            or name.split(".")[0].rstrip(" .").upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                "CONIN$",
                "CONOUT$",
                *(f"COM{i}" for i in "¹²³"),
                *(f"LPT{i}" for i in "¹²³"),
                *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10)),
            }
        ):
            raise ExportError("Недопустимое имя файла Windows.")
        check_cancel(cancel)
        temporary: Path | None = None
        try:
            if destination.is_dir():
                raise ExportError("Путь экспорта указывает на каталог.")
            if not overwrite and (destination.exists() or destination.is_symlink()):
                raise ExportCollision("Файл уже существует; подтвердите замену через --overwrite.")
            descriptor, filename = tempfile.mkstemp(
                prefix=".local-transcriber-", suffix=".tmp", dir=destination.parent
            )
            temporary = Path(filename)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                for fragment in fragments:
                    check_cancel(cancel)
                    file.write(fragment)
                check_cancel(cancel)
                file.flush()
                os.fsync(file.fileno())
            check_cancel(cancel)
            if overwrite:
                os.replace(temporary, destination)
            elif os.name == "nt":
                # Windows rename refuses an existing name, including one created after preflight.
                os.rename(temporary, destination)
            else:
                # POSIX rename overwrites; exclusive hard-link publication prevents that race.
                os.link(temporary, destination)
            return destination
        except FileExistsError:
            raise ExportCollision("Файл появился во время экспорта; замена не выполнена.") from None
        except PermissionError:
            raise ExportError(
                "Нет доступа к записи экспорта; проверьте права и блокировку файла."
            ) from None
        except OSError as error:
            message = (
                "Недостаточно места на диске."
                if error.errno == errno.ENOSPC
                else "Файл экспорта не записан; проверьте каталог и диск."
            )
            raise ExportError(message) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
