"""Allowlisted diagnostics: never format arbitrary messages, arguments or tracebacks."""

import json
import logging
import sys
from datetime import UTC, datetime
from enum import StrEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import UUID

from local_transcriber.infrastructure.privacy import private_directory


class AuditEvent(StrEnum):
    OPERATION_FAILED = "operation_failed"
    CONNECTED = "connected"
    WORKER = "worker_event"
    SESSION_DELETED = "session_deleted"
    TEMP_CLEANED = "temp_cleaned"
    DIAGNOSTIC = "diagnostic"


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Intentionally ignore msg/args/exception text/stack/source path, even for third-party
        # or accidental logging.exception calls under this namespace.
        event = getattr(record, "audit_event", AuditEvent.DIAGNOSTIC)
        if not isinstance(event, AuditEvent):
            event = AuditEvent.DIAGNOSTIC
        job = getattr(record, "job_id", None)
        if not hasattr(record, "job_id") and isinstance(record.args, tuple):
            positions = {
                "pipeline_failure job_id=%s stream=%s chunk=%s": 0,
                "checkpoint_status_unavailable job_id=%s": 0,
                "worker_event kind=%s job_id=%s ticket=%s": 1,
                "worker_recovery job_id=%s ticket=%s": 0,
            }
            position = positions.get(record.msg) if isinstance(record.msg, str) else None
            if position is not None and position < len(record.args):
                job = record.args[position]
        return json.dumps(
            {
                "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "event": event.value,
                "level": "ERROR" if record.levelno >= logging.ERROR else "INFO",
                "job_id": str(job) if isinstance(job, UUID) else None,
            },
            ensure_ascii=True,
        )


def audit(event: AuditEvent, job_id: UUID | None = None) -> None:
    logging.getLogger("local_transcriber").info("", extra={"audit_event": event, "job_id": job_id})


class DiagnosticLog:
    """One composition-root lifecycle; scoped handler, no global basicConfig/root changes."""

    def __init__(self, logs_dir: Path) -> None:
        directory = private_directory(logs_dir / "managed-v1")
        filename = directory / "diagnostics.jsonl"
        from local_transcriber.infrastructure.privacy import is_link

        for target in (
            filename,
            *(directory / f"diagnostics.jsonl.{number}" for number in range(1, 4)),
        ):
            if is_link(target) or (target.exists() and target.stat().st_nlink > 1):
                raise ValueError("Журнал не может быть ссылкой или hardlink.")
        self.handler = PrivateLogHandler(
            filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        self.handler.setFormatter(SafeFormatter())
        self.logger = logging.getLogger("local_transcriber")
        self.previous_level, self.previous_propagate = self.logger.level, self.logger.propagate
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

    def close(self) -> None:
        self.logger.removeHandler(self.handler)
        try:
            self.handler.close()
        except OSError:
            self.handler.handleError(None)
        finally:
            self.logger.setLevel(self.previous_level)
            self.logger.propagate = self.previous_propagate


class PrivateLogHandler(RotatingFileHandler):
    _reported = False

    def handleError(self, record: logging.LogRecord | None) -> None:
        # logging's default handleError dumps msg/args/traceback on disk-full/access errors.
        if not self._reported:
            self._reported = True
            try:
                print(
                    "Не удалось записать диагностический журнал; проверьте диск и права.",
                    file=sys.stderr,
                )
            except OSError:
                # A broken console cannot justify dumping the original private record.
                pass
