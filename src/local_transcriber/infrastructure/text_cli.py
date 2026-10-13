"""Local text/dictionary CLI composition; no database or model import on --help."""

import argparse
from dataclasses import asdict
from pathlib import Path
from uuid import UUID


def add_text_commands(commands: argparse._SubParsersAction) -> None:
    text = commands.add_parser("text", help="версии транскрипта и читаемый текст", color=False)
    actions = text.add_subparsers(dest="text_action", required=True)
    for action in ("raw", "readable", "manual", "versions", "show"):
        parser = actions.add_parser(action, color=False)
        parser.add_argument("job_id", type=UUID)
        parser.add_argument("--env-file", type=Path)
        if action == "readable":
            parser.add_argument("--paragraph-gap-ms", type=int, default=2000)
            parser.add_argument("--paragraph-chars", type=int, default=800)
            parser.add_argument("--no-terms", action="store_true")
            parser.add_argument("--no-terminal-period", action="store_true")
        elif action == "manual":
            parser.add_argument("--base", type=UUID, required=True)
            parser.add_argument("--file", type=Path, required=True)
        elif action == "show":
            parser.add_argument("--version", type=UUID, required=True)
    terms = commands.add_parser("terms", help="пользовательский словарь", color=False)
    actions = terms.add_subparsers(dest="terms_action", required=True)
    for action in ("list", "add", "update", "delete", "import"):
        parser = actions.add_parser(action, color=False)
        parser.add_argument("--env-file", type=Path)
        if action in {"update", "delete"}:
            parser.add_argument("term_id", type=UUID)
        if action in {"add", "update"}:
            parser.add_argument("canonical")
            parser.add_argument("--variant", action="append", default=[])
            parser.add_argument("--disabled", action="store_true")
        if action == "import":
            parser.add_argument("file", type=Path)


def read_text_file(path: Path, *, limit: int = 16 * 1024 * 1024) -> str:
    with path.open("rb") as file:
        content = file.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Text file exceeds the permitted size")
    try:
        return content.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("Text file must use UTF-8 encoding") from None


def run_text_command(arguments: argparse.Namespace) -> dict[str, object]:
    from local_transcriber.application.transcript import TranscriptService, parse_terms
    from local_transcriber.domain.text import Term, TextRules
    from local_transcriber.infrastructure.database.session import make_engine, session_factory
    from local_transcriber.infrastructure.database.text_store import (
        PostgreSQLTranscriptStore,
        TermRepository,
    )
    from local_transcriber.infrastructure.settings import load_settings

    # Validate files/rules before starting any DB transaction.
    manual = None
    imported = ()
    term = None
    rules = TextRules()
    if arguments.command == "text" and arguments.text_action == "manual":
        manual = read_text_file(arguments.file)
    if arguments.command == "text" and arguments.text_action == "readable":
        rules = TextRules(
            arguments.paragraph_gap_ms,
            arguments.paragraph_chars,
            not arguments.no_terms,
            not arguments.no_terminal_period,
        )
    if arguments.command == "terms":
        if arguments.terms_action == "import":
            imported = parse_terms(read_text_file(arguments.file, limit=4 * 1024 * 1024))
        elif arguments.terms_action in {"add", "update"}:
            term = Term(arguments.canonical, tuple(arguments.variant), not arguments.disabled)
    engine = make_engine(load_settings(arguments.env_file))
    try:
        factory = session_factory(engine)
        terms = TermRepository(factory)
        if arguments.command == "terms":
            match arguments.terms_action:
                case "list":
                    return {
                        "terms": [{"id": str(row.id), **asdict(row.term)} for row in terms.list()]
                    }
                case "add":
                    return {"id": str(terms.create(term))}
                case "update":
                    terms.update(arguments.term_id, term)
                    return {"updated": str(arguments.term_id)}
                case "delete":
                    terms.delete(arguments.term_id)
                    return {"deleted": str(arguments.term_id)}
                case "import":
                    return {"imported": terms.import_terms(imported)}
        service = TranscriptService(PostgreSQLTranscriptStore(factory), terms)
        match arguments.text_action:
            case "raw":
                version = service.raw(arguments.job_id)
            case "readable":
                version = service.readable(arguments.job_id, rules)
            case "manual":
                version = service.manual(arguments.job_id, arguments.base, manual)
            case "versions":
                return {
                    "versions": [
                        {
                            "id": str(v.id),
                            "number": v.number,
                            "kind": v.kind.value,
                            "metadata": v.metadata,
                        }
                        for v in service.versions(arguments.job_id)
                    ]
                }
            case "show":
                version = next(
                    (v for v in service.versions(arguments.job_id) if v.id == arguments.version),
                    None,
                )
                if version is None:
                    raise ValueError("Version does not belong to this job")
        return {
            "id": str(version.id),
            "job_id": str(version.job_id),
            "number": version.number,
            "kind": version.kind.value,
            "content": version.content,
            "metadata": version.metadata,
        }
    finally:
        engine.dispose()
