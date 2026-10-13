"""Deterministic transcript assembly and conservative text rules; no I/O or AI."""

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum
from uuid import UUID


class VersionType(StrEnum):
    RAW = "RAW"
    READABLE = "READABLE"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class TextSegment:
    id: UUID
    stream_index: int
    start_ms: int
    end_ms: int
    raw_text: str
    speaker_label: str | None = None
    chunk_index: int = 0
    segment_index: int = 0

    def __post_init__(self) -> None:
        values = (
            self.stream_index,
            self.start_ms,
            self.end_ms,
            self.chunk_index,
            self.segment_index,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Segment indices and times must be nonnegative integer values")
        if self.end_ms <= self.start_ms or not isinstance(self.raw_text, str):
            raise ValueError("Invalid segment interval or text")


@dataclass(frozen=True)
class Term:
    canonical: str
    variants: tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.variants, tuple):
            raise ValueError("Term variants must be an immutable tuple")
        forms = (self.canonical, *self.variants)
        if any(
            not isinstance(form, str) or not form.strip() or any(c in form for c in "\n\r\0")
            for form in forms
        ):
            raise ValueError("Term forms must be nonempty single-line strings")
        if self.canonical != self.canonical.strip() or type(self.enabled) is not bool:
            raise ValueError("Invalid canonical form or enabled flag")


@dataclass(frozen=True)
class TextRules:
    paragraph_gap_ms: int = 2000
    paragraph_chars: int = 800
    normalize_terms: bool = True
    terminal_period: bool = True

    def __post_init__(self) -> None:
        if type(self.paragraph_gap_ms) is not int or self.paragraph_gap_ms < 0:
            raise ValueError("paragraph_gap_ms must be a nonnegative integer")
        if type(self.paragraph_chars) is not int or self.paragraph_chars < 1:
            raise ValueError("paragraph_chars must be a positive integer")
        if any(type(value) is not bool for value in (self.normalize_terms, self.terminal_period)):
            raise ValueError("Text rule switches must be boolean")


@dataclass(frozen=True)
class ProcessedText:
    content: str
    metadata: dict[str, object]


def ordered_segments(segments: Iterable[TextSegment]) -> tuple[TextSegment, ...]:
    return tuple(
        sorted(
            segments,
            key=lambda s: (s.stream_index, s.start_ms, s.chunk_index, s.segment_index, s.id.int),
        )
    )


def _append_text(previous: str, current: str) -> str:
    # Assembly adds only a separator when model fragments have no boundary whitespace.
    if previous and current and not previous[-1].isspace() and not current[0].isspace():
        return previous + " " + current
    return previous + current


def aggregate_raw(segments: Iterable[TextSegment]) -> str:
    """Keep every source character; separate tracks without mixing simultaneous speech."""
    tracks: list[str] = []
    pieces: list[str] = []
    last = ""
    stream: int | None = None
    for segment in ordered_segments(segments):
        if stream is not None and segment.stream_index != stream:
            tracks.append("".join(pieces))
            pieces = []
            last = ""
        stream = segment.stream_index
        text = segment.raw_text
        if last and text and not last.isspace() and not text[0].isspace():
            pieces.append(" ")
        pieces.append(text)
        if text:
            last = text[-1]
    if stream is not None:
        tracks.append("".join(pieces))
    return "\n\n".join(tracks)


def source_digest(segments: Iterable[TextSegment]) -> str:
    digest = hashlib.sha256()
    for segment in ordered_segments(segments):
        digest.update(json.dumps(asdict(segment), default=str, ensure_ascii=False).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _term_replacer(terms: tuple[Term, ...]) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    choices: dict[str, set[str]] = {}
    for term in terms:
        if term.enabled:
            for form in (term.canonical, *term.variants):
                key = re.sub(r"\s+", " ", form.strip()).casefold()
                choices.setdefault(key, set()).add(term.canonical)
    # Keep ambiguous alternatives in the regex so a shorter substring cannot replace them.
    pattern = (
        re.compile(
            r"(?<!\w)(?:"
            + "|".join(re.escape(key) for key in sorted(choices, key=lambda k: (-len(k), k)))
            + r")(?!\w)",
            re.IGNORECASE,
        )
        if choices
        else None
    )
    safe = {key: next(iter(forms)) for key, forms in choices.items() if len(forms) == 1}
    return pattern, safe


def make_readable(
    segments: Iterable[TextSegment], *, rules: TextRules | None = None, terms: tuple[Term, ...] = ()
) -> ProcessedText:
    """Preserve words, repeats, stop words, numbers and case; do not infer commas or facts."""
    rules = rules if rules is not None else TextRules()
    ordered = ordered_segments(segments)
    pattern, replacements = _term_replacer(terms) if rules.normalize_terms else (None, {})
    paragraphs: list[str] = []
    aligned: list[dict[str, object]] = []
    buffer = ""
    previous: TextSegment | None = None
    speaker: str | None = None
    multiple_streams = len({s.stream_index for s in ordered}) > 1
    stream: int | None = None
    first_ms = last_ms = 0

    def flush() -> None:
        nonlocal buffer
        text = re.sub(r"\s+", " ", buffer).strip()
        if text:
            # Formatting only: don't turn spaced decimal/list numbers into different values.
            text = re.sub(r"(?<=[^\d\s]) +([,.;:!?])", r"\1", text)
            if pattern:
                text = pattern.sub(lambda m: replacements.get(m[0].casefold(), m[0]), text)
            if rules.terminal_period and not text.rstrip("\"'»”)]}").endswith((".", "?", "!", "…")):
                text += "."
            prefix = f"[Дорожка {stream}] " if multiple_streams else ""
            if speaker:
                prefix += f"{speaker}: "
            paragraphs.append(prefix + text)
            aligned.append(
                {
                    "text": text,
                    "start_ms": first_ms,
                    "end_ms": last_ms,
                    "stream_index": stream,
                    "speaker_label": speaker,
                }
            )
        buffer = ""

    for segment in ordered:
        if not segment.raw_text.strip():
            continue
        if previous is not None and (
            segment.stream_index != previous.stream_index
            or segment.speaker_label != previous.speaker_label
            or segment.start_ms - previous.end_ms >= rules.paragraph_gap_ms
            or len(buffer) >= rules.paragraph_chars
        ):
            flush()
        speaker, stream = segment.speaker_label, segment.stream_index
        if not buffer:
            first_ms, last_ms = segment.start_ms, segment.end_ms
        else:
            last_ms = max(last_ms, segment.end_ms)
        buffer = _append_text(buffer, segment.raw_text)
        previous = segment
    flush()
    dictionary = [
        {"canonical": term.canonical, "variants": list(term.variants), "enabled": term.enabled}
        for term in sorted(terms, key=lambda t: (t.canonical, t.variants))
    ]
    return ProcessedText(
        "\n\n".join(paragraphs),
        {
            "processor": "conservative-text",
            "rules_version": "1",
            "mode": "readable",
            "rules": asdict(rules),
            "dictionary": dictionary,
            "source_digest": source_digest(ordered),
            "paragraphs": aligned,
        },
    )
