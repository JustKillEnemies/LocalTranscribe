"""Text use cases independent of PostgreSQL and future GUI."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from local_transcriber.domain.text import (
    ProcessedText,
    Term,
    TextRules,
    TextSegment,
    VersionType,
    make_readable,
)


@dataclass(frozen=True)
class TextVersion:
    id: UUID
    job_id: UUID
    number: int
    kind: VersionType
    content: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class RawTranscript:
    version: TextVersion
    segments: tuple[TextSegment, ...]


class TranscriptStore(Protocol):
    def raw(self, job_id: UUID) -> RawTranscript: ...

    def save_readable(self, job_id: UUID, raw_id: UUID, result: ProcessedText) -> TextVersion: ...

    def save_manual(self, job_id: UUID, base_id: UUID, content: str) -> TextVersion: ...

    def versions(self, job_id: UUID) -> tuple[TextVersion, ...]: ...


class TermSource(Protocol):
    def enabled_terms(self) -> tuple[Term, ...]: ...


class TranscriptService:
    def __init__(self, store: TranscriptStore, terms: TermSource) -> None:
        self._store, self._terms = store, terms

    def raw(self, job_id: UUID) -> TextVersion:
        """Verbatim mode: retain the immutable assembled source."""
        return self._store.raw(job_id).version

    def readable(self, job_id: UUID, rules: TextRules | None = None) -> TextVersion:
        raw = self._store.raw(job_id)
        result = make_readable(raw.segments, rules=rules, terms=self._terms.enabled_terms())
        return self._store.save_readable(job_id, raw.version.id, result)

    def manual(self, job_id: UUID, base_id: UUID, content: str) -> TextVersion:
        """Append a user revision, never replace a RAW/READABLE/MANUAL version."""
        if not isinstance(content, str) or "\0" in content:
            raise ValueError("Manual content must be text without NUL characters")
        return self._store.save_manual(job_id, base_id, content)

    def versions(self, job_id: UUID) -> tuple[TextVersion, ...]:
        return self._store.versions(job_id)


def parse_terms(content: str) -> tuple[Term, ...]:
    """UTF-8 file content: canonical<TAB>variant|variant; blank lines/# comments allowed."""
    result: list[Term] = []
    seen: set[str] = set()
    for line_number, line in enumerate(content.lstrip("\ufeff").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) > 2:
            raise ValueError(f"Invalid term file format at line {line_number}")
        canonical = fields[0].strip()
        variants = tuple(part.strip() for part in fields[1].split("|")) if len(fields) == 2 else ()
        try:
            term = Term(canonical, variants)
        except ValueError:
            raise ValueError(f"Invalid term at line {line_number}") from None
        key = canonical.casefold()
        if key in seen:
            raise ValueError(f"Duplicate canonical form at line {line_number}")
        seen.add(key)
        result.append(term)
        if len(result) > 10_000:
            raise ValueError("Term import exceeds 10000 entries")
    return tuple(result)
