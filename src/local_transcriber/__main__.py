"""Single entry point for the currently supported package commands."""

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from uuid import UUID


def main(argv: Sequence[str] | None = None) -> int:
    """Run the supported local CLI commands."""
    parser = argparse.ArgumentParser(
        prog="local-transcriber",
        description="LocalTranscriber — локальное приложение для транскрибации OBS-записей.",
        epilog=(
            "Доступны диагностика, импорт и локальная транскрибация с чекпойнтами. "
            "GUI: команда gui; просмотр RAW/READABLE/MANUAL, редактор, экспорт и воспроизведение."
        ),
        allow_abbrev=False,
        color=False,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('local-transcriber')}",
        help="показать версию установленного пакета и завершить работу",
    )
    commands = parser.add_subparsers(dest="command")
    gui = commands.add_parser("gui", help="открыть графический интерфейс", color=False)
    gui.add_argument("--env-file", type=Path)
    doctor = commands.add_parser(
        "doctor", help="проверить настройки и локальные инструменты", color=False
    )
    doctor.add_argument("--env-file", type=Path, help="явный путь к локальному .env (UTF-8)")
    mode = doctor.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="без внешних процессов и создания каталогов"
    )
    mode.add_argument(
        "--create-dirs", action="store_true", help="создать только настроенные каталоги приложения"
    )
    for name, help_text in (
        ("inspect", "показать метаданные медиа через ffprobe"),
        ("import", "импортировать метаданные медиа в PostgreSQL"),
    ):
        command = commands.add_parser(name, help=help_text, color=False)
        command.add_argument("path", type=Path, help="локальный путь к медиафайлу")
        command.add_argument("--env-file", type=Path, help="явный путь к локальному .env")
    transcribe = commands.add_parser(
        "transcribe", help="локально распознать выбранные дорожки", color=False
    )
    transcribe.add_argument("path", type=Path)
    transcribe.add_argument("--stream-index", type=int, action="append", required=True)
    transcribe.add_argument("--env-file", type=Path)
    transcribe.add_argument("--resume", type=UUID, help="UUID ранее созданного задания")
    transcribe.add_argument("--chunk-ms", type=int, default=300_000)
    transcribe.add_argument("--overlap-ms", type=int, default=1000)
    transcribe.add_argument(
        "--interactive", action="store_true", help="stdin-команды pause/resume/cancel"
    )
    transcribe.add_argument(
        "--end-ms", type=int, help="конец обрабатываемого диапазона от начала файла"
    )
    from local_transcriber.infrastructure.export_cli import add_export_command
    from local_transcriber.infrastructure.text_cli import add_text_commands

    add_text_commands(commands)
    add_export_command(commands)
    arguments = parser.parse_args(argv)
    if arguments.command == "gui":
        from local_transcriber.ui.bootstrap import run_gui

        return run_gui(arguments.env_file)
    if arguments.command == "export":
        from local_transcriber.application.export import ExportCancelled, ExportError
        from local_transcriber.infrastructure.database.session import PersistenceError
        from local_transcriber.infrastructure.export_cli import run_export
        from local_transcriber.infrastructure.settings import ConfigurationError

        try:
            print(json.dumps({"exported": str(run_export(arguments))}, ensure_ascii=False))
            return 0
        except ExportCancelled, KeyboardInterrupt:
            print("Экспорт отменён.", file=sys.stderr)
            return 130
        except PersistenceError as error:
            print(f"Ошибка PostgreSQL: {error}", file=sys.stderr)
            return 3
        except (ExportError, ConfigurationError, ValueError) as error:
            print(f"Ошибка экспорта: {error}", file=sys.stderr)
            return 2
        except OSError:
            print("Ошибка экспорта: локальный файл недоступен.", file=sys.stderr)
            return 2
    if arguments.command in {"text", "terms"}:
        from local_transcriber.infrastructure.database.session import PersistenceError
        from local_transcriber.infrastructure.settings import ConfigurationError
        from local_transcriber.infrastructure.text_cli import run_text_command

        try:
            print(json.dumps(run_text_command(arguments), ensure_ascii=False, indent=2))
            return 0
        except PersistenceError as error:
            print(f"Ошибка PostgreSQL: {error}", file=sys.stderr)
            return 3
        except (ConfigurationError, ValueError) as error:
            print(f"Ошибка: {error}", file=sys.stderr)
            return 2
        except OSError:
            print("Ошибка: локальный текстовый файл недоступен.", file=sys.stderr)
            return 2
    if arguments.command == "transcribe":
        from local_transcriber.application.pipeline import PipelineError
        from local_transcriber.infrastructure.database.session import PersistenceError
        from local_transcriber.infrastructure.media import MediaInspectionError
        from local_transcriber.infrastructure.settings import ConfigurationError
        from local_transcriber.infrastructure.transcribe_cli import run_transcription

        try:
            run_transcription(
                arguments.path,
                indices=tuple(arguments.stream_index),
                env_file=arguments.env_file,
                resume=arguments.resume,
                chunk_ms=arguments.chunk_ms,
                overlap_ms=arguments.overlap_ms,
                end_ms=arguments.end_ms,
                interactive=arguments.interactive,
            )
            return 0
        except PersistenceError as error:
            print(f"Ошибка PostgreSQL: {error}", file=sys.stderr)
            return 3
        except (PipelineError, ConfigurationError, MediaInspectionError, ValueError) as error:
            print(f"Ошибка: {error}", file=sys.stderr)
            return 2
        except OSError:
            print("Ошибка: локальный файл или каталог недоступен.", file=sys.stderr)
            return 2
    if arguments.command == "doctor":
        from local_transcriber.infrastructure.doctor import run_doctor
        from local_transcriber.infrastructure.settings import ConfigurationError, load_settings

        try:
            settings = load_settings(arguments.env_file)
        except ConfigurationError as error:
            print(f"Настройки: ERROR — {error}", file=sys.stderr)
            return 2
        for result in run_doctor(
            settings, dry_run=arguments.dry_run, create_dirs=arguments.create_dirs
        ):
            print(f"{result.name}: {result.status} — {result.message}")
        return 0
    if arguments.command in {"inspect", "import"}:
        from local_transcriber.infrastructure.media import MediaInspectionError, MediaInspector
        from local_transcriber.infrastructure.settings import ConfigurationError, load_settings

        try:
            settings = load_settings(arguments.env_file)
            inspector = MediaInspector(settings.ffprobe_path, timeout=settings.probe_timeout)
            if arguments.command == "inspect":
                media = inspector.inspect(arguments.path)
                output = _media_output(media)
            else:
                from local_transcriber.application.media_import import ImportMedia
                from local_transcriber.infrastructure.database.repositories import MediaRepository
                from local_transcriber.infrastructure.database.session import (
                    PersistenceError,
                    make_engine,
                    session_factory,
                )

                try:
                    engine = make_engine(settings)
                    try:
                        result = ImportMedia(
                            inspector, MediaRepository(session_factory(engine))
                        ).execute(arguments.path)
                    finally:
                        engine.dispose()
                except PersistenceError as error:
                    print(f"Ошибка PostgreSQL: {error}", file=sys.stderr)
                    return 3
                output = _media_output(result.media)
                output.update(media_id=str(result.media_id), created=result.created)
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
        except (ConfigurationError, MediaInspectionError) as error:
            print(f"Ошибка: {error}", file=sys.stderr)
            return 2
    parser.print_help()
    return 0


def _media_output(media: object) -> dict[str, object]:
    from local_transcriber.domain.media import MediaInfo

    if not isinstance(media, MediaInfo):
        raise TypeError("Expected MediaInfo")
    return {
        "path": str(media.path),
        "filename": media.filename,
        "size_bytes": media.size_bytes,
        "duration_ms": media.duration_ms,
        "container": media.container,
        "fingerprint": media.fingerprint,
        "audio_streams": [
            {
                "stream_index": stream.stream_index,
                "codec": stream.codec,
                "sample_rate": stream.sample_rate,
                "channels": stream.channels,
                "language": stream.language,
                "title": stream.title,
            }
            for stream in media.audio_streams
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
