"""Single entry point for the currently supported package commands."""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    """Show package information or diagnose the local environment."""
    parser = argparse.ArgumentParser(
        prog="local-transcriber",
        description="LocalTranscriber — локальное приложение для транскрибации OBS-записей.",
        epilog=(
            "Сейчас доступны справка, версия пакета и диагностика doctor. "
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
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
