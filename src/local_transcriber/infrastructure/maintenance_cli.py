"""Explicit local maintenance commands; no deletion without a confirmation flag."""

import argparse
from dataclasses import asdict
from pathlib import Path
from uuid import UUID


def add_maintenance_command(commands: argparse._SubParsersAction) -> None:
    parser = commands.add_parser("maintenance", help="история и временные файлы", color=False)
    operations = parser.add_subparsers(dest="operation", required=True)
    delete = operations.add_parser("delete", help="удалить историю одной записи", color=False)
    delete.add_argument("media_id", type=UUID)
    delete.add_argument("--confirm-delete", action="store_true")
    delete.add_argument("--remove-derived", action="store_true")
    cleanup = operations.add_parser("cleanup", help="очистить зарегистрированные temp", color=False)
    cleanup.add_argument("--job", type=UUID)
    cleanup.add_argument("--remove-derived", action="store_true")
    cleanup.add_argument("--confirm-delete", action="store_true")
    for command in (delete, cleanup):
        command.add_argument("--env-file", type=Path)


def run_maintenance(arguments: argparse.Namespace) -> dict[str, object]:
    from local_transcriber.application.maintenance import DeleteHistory, DeleteSession
    from local_transcriber.infrastructure.database.history_store import PostgreSQLHistoryStore
    from local_transcriber.infrastructure.database.session import make_engine, session_factory
    from local_transcriber.infrastructure.diagnostics import AuditEvent, DiagnosticLog, audit
    from local_transcriber.infrastructure.settings import load_settings
    from local_transcriber.infrastructure.temp_storage import ManagedTempFiles

    if arguments.operation == "delete" and not arguments.confirm_delete:
        raise ValueError("Удаление требует --confirm-delete.")
    if (
        arguments.operation == "cleanup"
        and arguments.remove_derived
        and (not arguments.confirm_delete or arguments.job is None)
    ):
        raise ValueError("Удаление retained audio требует --job UUID и --confirm-delete.")
    settings = load_settings(arguments.env_file)
    database = make_engine(settings)
    diagnostics = None
    try:
        diagnostics = DiagnosticLog(settings.logs_dir)
        history, files = (
            PostgreSQLHistoryStore(session_factory(database)),
            ManagedTempFiles(settings.temp_dir),
        )
        if arguments.operation == "delete":
            result = DeleteHistory(history, files).execute(
                DeleteSession(arguments.media_id, True, arguments.remove_derived)
            )
            audit(AuditEvent.SESSION_DELETED)
        else:
            protected = history.protected_sources()
            if arguments.job is not None:
                if arguments.remove_derived and not history.cleanup_allowed(arguments.job):
                    raise ValueError("Нельзя удалять файлы активного задания.")
                result = files.cleanup_job(
                    arguments.job,
                    include_retained=arguments.remove_derived,
                    protected=protected,
                    ttl_hours=settings.temp_retention_hours,
                )
            else:
                result = files.cleanup(protected=protected, ttl_hours=settings.temp_retention_hours)
            audit(AuditEvent.TEMP_CLEANED, arguments.job)
        return asdict(result)
    except Exception:
        audit(AuditEvent.OPERATION_FAILED, getattr(arguments, "job", None))
        raise
    finally:
        database.dispose()
        if diagnostics:
            diagnostics.close()
