"""Registered artifacts with per-job OS leases; cleanup never traverses user directories."""

import json
import os
import re
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from local_transcriber.infrastructure.privacy import PrivateStorageError, is_link, private_directory


class WorkspaceBusy(ValueError):
    pass


@dataclass(frozen=True)
class CleanupReport:
    deleted: int = 0
    skipped: int = 0
    failed: int = 0

    def __add__(self, other: CleanupReport) -> CleanupReport:
        return CleanupReport(
            self.deleted + other.deleted, self.skipped + other.skipped, self.failed + other.failed
        )


class ManagedTempFiles:
    def __init__(self, temp_dir: Path) -> None:
        if not temp_dir.is_absolute():
            raise ValueError("Рабочий каталог должен быть абсолютным.")
        self.root = temp_dir / "managed-v1"

    @contextmanager
    def lease(self, job_id: UUID, *, create: bool = False) -> Iterator[Path | None]:
        directory = self.root / str(job_id)
        if create:
            private_directory(self.root)
            private_directory(directory)
        elif not directory.exists():
            yield None
            return
        if (
            is_link(self.root)
            or is_link(directory)
            or directory.resolve().parent != self.root.resolve()
        ):
            raise PrivateStorageError("Недопустимый путь рабочего каталога.")
        for owned in (self.root, directory):
            marker = owned / ".local-transcriber-owned"
            if (
                is_link(marker)
                or marker.stat().st_size != 26
                or marker.read_bytes() != b"LocalTranscriber owned v1\n"
            ):
                raise PrivateStorageError("Нет подтверждения владения временными файлами.")
        lock = directory / ".lease"
        if is_link(lock) or (lock.exists() and lock.stat().st_nlink > 1):
            raise PrivateStorageError("Недопустимый файл блокировки.")
        with lock.open("a+b") as file:
            if file.tell() == 0:
                file.write(b"0")
                file.flush()
            file.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise WorkspaceBusy("Рабочие файлы используются другим процессом.") from None
            try:
                yield directory
            finally:
                file.seek(0)
                if os.name == "nt":
                    msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(file.fileno(), fcntl.LOCK_UN)

    def register(self, directory: Path, job_id: UUID, names: dict[str, str]) -> None:
        """Called under a lease, before any artifact is created; reserve exact unique names."""
        records = self._read(directory, job_id)
        for name, kind in names.items():
            self._name(name, kind)
            if name in records or (directory / name).exists() or is_link(directory / name):
                raise PrivateStorageError("Имя рабочего файла уже занято.")
        records.update(names)
        self._write(directory, job_id, records)

    def _read(self, directory: Path, job_id: UUID) -> dict[str, str]:
        manifest = directory / "artifacts.json"
        if not manifest.exists() and not is_link(manifest):
            return {}
        if is_link(manifest) or manifest.stat().st_size > 1_048_576 or manifest.stat().st_nlink > 1:
            raise PrivateStorageError("Недопустимый реестр рабочих файлов.")
        try:
            content = json.loads(manifest.read_text(encoding="utf-8"))
            if content.get("job_id") != str(job_id) or content.get("version") != 1:
                raise ValueError
            files = content["files"]
            if not isinstance(files, dict) or len(files) > 4096:
                raise ValueError
            for name, kind in files.items():
                self._name(name, kind)
            return files
        except ValueError, KeyError, TypeError, AttributeError:
            raise PrivateStorageError(
                "Реестр рабочих файлов повреждён; очистка запрещена."
            ) from None

    @staticmethod
    def _name(name: str, kind: str) -> None:
        if not isinstance(name, str) or not re.fullmatch(
            r"stream-\d+-\d+-\d+-[0-9a-f]{32}\.(tmp|wav)", name
        ):
            raise PrivateStorageError("В реестре найден недопустимый путь.")
        if kind not in {"temporary", "retained", "source"} or (
            kind == "temporary"
        ) != name.endswith(".tmp"):
            raise PrivateStorageError("В реестре найден недопустимый тип файла.")

    def protect_sources(self, sources: Sequence[Path]) -> None:
        """An owned WAV imported as source stays protected after history is erased."""
        if not self.root.exists():
            return
        for source in sources:
            try:
                relative = source.resolve().relative_to(self.root.resolve())
                if len(relative.parts) != 2:
                    continue
                job_id = UUID(relative.parts[0])
            except ValueError:
                continue
            with self.lease(job_id) as directory:
                if directory is None:
                    continue
                records = self._read(directory, job_id)
                if relative.name in records and records[relative.name] != "source":
                    records[relative.name] = "source"
                    self._write(directory, job_id, records)

    def _write(self, directory: Path, job_id: UUID, records: dict[str, str]) -> None:
        temporary = directory / (".manifest-" + uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as file:
                json.dump({"version": 1, "job_id": str(job_id), "files": records}, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, directory / "artifacts.json")
        finally:
            temporary.unlink(missing_ok=True)

    def cleanup_job(
        self,
        job_id: UUID,
        *,
        include_retained: bool = False,
        protected: Sequence[Path] = (),
        ttl_hours: int = 24,
    ) -> CleanupReport:
        if type(ttl_hours) is not int or ttl_hours < 1:
            raise ValueError("Срок временных файлов должен быть не менее часа.")
        deleted = skipped = failed = 0
        protected_resolved = {source.resolve() for source in protected}
        try:
            with self.lease(job_id) as directory:
                if directory is None:
                    return CleanupReport()
                records = self._read(directory, job_id)
                remaining = dict(records)
                for name, kind in records.items():
                    path = directory / name
                    try:
                        if is_link(path) or path.resolve().parent != directory.resolve():
                            skipped += 1
                            continue
                        if not path.exists():
                            remaining.pop(name)
                            continue
                        stat = path.stat()
                        if kind == "source":
                            skipped += 1
                            continue
                        if path.resolve() in protected_resolved and name.endswith(".wav"):
                            remaining[name] = "source"
                        if (
                            not path.is_file()
                            or stat.st_nlink > 1
                            or path.resolve() in protected_resolved
                        ):
                            skipped += 1
                            continue
                        if not include_retained and (
                            kind == "retained" or stat.st_mtime > time.time() - ttl_hours * 3600
                        ):
                            skipped += 1
                            continue
                        path.unlink()
                        remaining.pop(name)
                        deleted += 1
                    except OSError:
                        failed += 1
                self._write(directory, job_id, remaining)
        except WorkspaceBusy:
            return CleanupReport(skipped=1)
        except OSError, PrivateStorageError:
            return CleanupReport(failed=1, deleted=deleted, skipped=skipped)
        return CleanupReport(deleted, skipped, failed)

    def cleanup(self, *, protected: Sequence[Path] = (), ttl_hours: int = 24) -> CleanupReport:
        if type(ttl_hours) is not int or ttl_hours < 1:
            raise ValueError("Срок временных файлов должен быть не менее часа.")
        if not self.root.exists() or is_link(self.root):
            return CleanupReport()
        report = CleanupReport()
        # Bounded flat scan; never recurse or delete arbitrary matching files.
        try:
            with os.scandir(self.root) as entries:
                for count, entry in enumerate(entries):
                    if count >= 5000:
                        break
                    try:
                        job_id = UUID(entry.name)
                    except ValueError:
                        continue
                    if str(job_id) == entry.name:
                        report += self.cleanup_job(job_id, protected=protected, ttl_hours=ttl_hours)
        except OSError:
            return report + CleanupReport(failed=1)
        return report
