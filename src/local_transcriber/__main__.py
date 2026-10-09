"""Single entry point for the currently supported package commands."""

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    """Run the supported local CLI commands."""
    parser = argparse.ArgumentParser(
        prog="local-transcriber",
        description="LocalTranscriber — локальное приложение для транскрибации OBS-записей.",
        epilog=(
            "Доступны диагностика, инспекция и импорт метаданных медиа. "
            "Транскрибация и графический интерфейс появятся на следующих этапах."
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
    arguments = parser.parse_args(argv)
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
