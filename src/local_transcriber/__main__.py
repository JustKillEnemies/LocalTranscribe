"""Single entry point for the currently supported package commands."""

import argparse
from collections.abc import Sequence
from importlib.metadata import version


def main(argv: Sequence[str] | None = None) -> int:
    """Show package information; invalid arguments exit with status 2."""
    parser = argparse.ArgumentParser(
        prog="local-transcriber",
        description="LocalTranscriber — локальное приложение для транскрибации OBS-записей.",
        epilog=(
            "Сейчас доступны справка и версия пакета. "
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
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
