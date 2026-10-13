"""Step 10 conservative rules, source preservation and CLI file failures."""

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import pytest

from local_transcriber.__main__ import main
from local_transcriber.application.transcript import parse_terms
from local_transcriber.domain.text import (
    Term,
    TextRules,
    TextSegment,
    aggregate_raw,
    make_readable,
    source_digest,
)
from local_transcriber.infrastructure.text_cli import read_text_file


def segment(text: str, start: int = 0, stream: int = 0, speaker: str | None = None) -> TextSegment:
    return TextSegment(uuid4(), stream, start, start + 100, text, speaker)


def test_raw_preserves_every_source_character_and_track_order() -> None:
    first = segment("  да  да\t\n", 0, 1)
    second = segment(" 42,5 ", 200, 1)
    other = segment("English", 0, 0)
    rows = (second, first, other)
    original = tuple(asdict(row) for row in rows)
    raw = aggregate_raw(rows).encode("utf-8")
    assert raw == "English\n\n  да  да\t\n 42,5 ".encode()
    readable = make_readable(rows)
    assert readable.content == "[Дорожка 0] English.\n\n[Дорожка 1] да да 42,5."
    assert aggregate_raw(rows).encode("utf-8") == raw
    assert tuple(asdict(row) for row in rows) == original
    assert source_digest(rows) == source_digest(tuple(reversed(rows)))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("я я ну и не хочу", "я я ну и не хочу."),
        ("Он сказал : «не удаляй 3.14 и 42,5!»", "Он сказал: «не удаляй 3.14 и 42,5!»"),
        ('SELECT "name" FROM users', 'SELECT "name" FROM users.'),
        ("Python asyncio FastAPI CI/CD", "Python asyncio FastAPI CI/CD."),
        ("цена 1 234,50 версия v2.0 IP 127.0.0.1", "цена 1 234,50 версия v2.0 IP 127.0.0.1."),
        ("числа 3 , 14 и 2 . 5", "числа 3 , 14 и 2 . 5."),
        ("готово?", "готово?"),
        ("  \n\t", ""),
    ],
)
def test_conservative_rules(source: str, expected: str) -> None:
    assert make_readable((segment(source),)).content == expected


def test_paragraphs_without_punctuation_and_two_speaker_labels() -> None:
    rows = (
        segment("первая фраза", 0, speaker="Микрофон"),
        segment("ответ", 200, speaker="Системный звук"),
        segment("дальше", 4000, speaker="Системный звук"),
    )
    assert make_readable(rows).content == (
        "Микрофон: первая фраза.\n\nСистемный звук: ответ.\n\nСистемный звук: дальше."
    )
    assert make_readable(rows, rules=TextRules(5000, 800, False, False)).content.endswith(
        "ответ дальше"
    )
    assert make_readable((segment(""),)).content == ""
    assert make_readable(()).content == ""


def test_terms_whole_word_longest_match_ambiguity_disabled_and_no_cascading() -> None:
    terms = (
        Term("PostgreSQL", ("постгрес", "postgres")),
        Term("SQLAlchemy", ("sql alchemy",)),
        Term("Docker", ("докер", "общий")),
        Term("Redis", ("общий",)),
        Term("Ignored", ("unused",), False),
        Term("Other", ("PostgreSQL",)),
    )
    rows = (segment("постгрес postgres PostgreSQL postgresqlish sql alchemy общий unused докер"),)
    result = make_readable(rows, terms=terms)
    assert (
        result.content
        == "PostgreSQL PostgreSQL PostgreSQL postgresqlish SQLAlchemy общий unused Docker."
    )
    assert result.metadata["rules_version"] == "1"
    assert result.metadata["dictionary"]
    assert make_readable(
        rows, terms=terms, rules=TextRules(normalize_terms=False)
    ).content.startswith("постгрес")
    # Ambiguous long phrases must block shorter replacements inside the phrase.
    ambiguous = (Term("A", ("foo bar",)), Term("B", ("foo bar",)), Term("C", ("foo",)))
    assert make_readable((segment("foo bar"),), terms=ambiguous).content == "foo bar."


def test_rules_length_limit_and_empty_segments_do_not_hide_speaker_or_pause() -> None:
    rows = (segment("one"), segment("  ", 100), segment("two", 200))
    assert make_readable(rows, rules=TextRules(paragraph_chars=3)).content == "one.\n\ntwo."
    assert source_digest(rows) != source_digest(rows[:-1])
    for kwargs in ({"paragraph_gap_ms": -1}, {"paragraph_chars": 0}, {"normalize_terms": 1}):
        with pytest.raises(ValueError):
            TextRules(**kwargs)
    with pytest.raises(ValueError):
        TextSegment(uuid4(), 0, True, 100, "bad")


def test_dictionary_import_format_and_negative_cases() -> None:
    assert parse_terms("\ufeff# dictionary\nPostgreSQL\tпостгрес|postgres\nPython\n\n") == (
        Term("PostgreSQL", ("постгрес", "postgres")),
        Term("Python"),
    )
    for content in ("\tvariant", "PG\t", "PG\tx|", "PG\tx\ty", "PG\npg", "PG\0"):
        with pytest.raises(ValueError):
            parse_terms(content)


def test_cli_utf8_files_missing_invalid_encoding_and_size(tmp_path: Path, capsys) -> None:
    source = tmp_path / "Словарь с пробелами.txt"
    source.write_text("\ufeffPostgreSQL\tпостгрес", encoding="utf-8")
    assert read_text_file(source) == "PostgreSQL\tпостгрес"
    before = source.read_bytes()
    with pytest.raises(ValueError, match="size"):
        read_text_file(source, limit=2)
    assert source.read_bytes() == before
    source.write_bytes(b"\xff")
    assert main(["terms", "import", str(source)]) == 2
    assert "UTF-8" in capsys.readouterr().err
    source.write_text("PG\tx|", encoding="utf-8")
    assert main(["terms", "import", str(source)]) == 2
    assert "Invalid term" in capsys.readouterr().err
    assert (
        main(
            [
                "text",
                "manual",
                str(uuid4()),
                "--base",
                str(uuid4()),
                "--file",
                str(tmp_path / "missing"),
            ]
        )
        == 2
    )
    assert "недоступен" in capsys.readouterr().err
    assert main(["text", "readable", str(uuid4()), "--paragraph-gap-ms", "-1"]) == 2
    assert "nonnegative" in capsys.readouterr().err
