"""Export composition root imports no GPU/media engine."""

import argparse
from pathlib import Path
from uuid import UUID


def add_export_command(commands: argparse._SubParsersAction) -> None:
    parser = commands.add_parser("export", help="экспорт сохранённого текста", color=False)
    parser.add_argument("job_id", type=UUID)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--format", choices=("txt", "srt", "json", "md"))
    parser.add_argument("--version", type=UUID, help="конкретная сохранённая версия")
    parser.add_argument("--timestamps", action="store_true", help="таймкоды TXT/Markdown")
    parser.add_argument("--roles", action="store_true", help="подписи TXT/SRT/Markdown")
    parser.add_argument("--overwrite", action="store_true", help="явно разрешить замену файла")
    parser.add_argument("--env-file", type=Path)


def run_export(arguments: argparse.Namespace) -> Path:
    from local_transcriber.application.export import (
        ExportError,
        ExportFormat,
        ExportOptions,
        ExportService,
    )
    from local_transcriber.infrastructure.database.export_store import PostgreSQLExportSource
    from local_transcriber.infrastructure.database.session import make_engine, session_factory
    from local_transcriber.infrastructure.diagnostics import AuditEvent, DiagnosticLog, audit
    from local_transcriber.infrastructure.export_files import AtomicExportWriter
    from local_transcriber.infrastructure.settings import load_settings

    try:
        format = ExportFormat(arguments.format or arguments.destination.suffix.lower().lstrip("."))
    except ValueError:
        raise ExportError(
            "Укажите --format txt/srt/json/md или соответствующее расширение файла."
        ) from None
    settings = load_settings(arguments.env_file)
    engine = make_engine(settings)
    diagnostics = None
    try:
        diagnostics = DiagnosticLog(settings.logs_dir)
        return ExportService(
            PostgreSQLExportSource(session_factory(engine)), AtomicExportWriter()
        ).export(
            arguments.job_id,
            arguments.destination,
            ExportOptions(format, arguments.timestamps, arguments.roles, arguments.overwrite),
            version_id=arguments.version,
        )
    except Exception:
        audit(AuditEvent.OPERATION_FAILED, arguments.job_id)
        raise
    finally:
        engine.dispose()
        if diagnostics:
            diagnostics.close()
