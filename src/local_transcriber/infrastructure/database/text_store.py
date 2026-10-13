"""Append-only transcript versions and transactional custom dictionary."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from local_transcriber.application.transcript import RawTranscript, TextVersion
from local_transcriber.domain.text import (
    ProcessedText,
    Term,
    TextSegment,
    VersionType,
    aggregate_raw,
    source_digest,
)
from local_transcriber.infrastructure.database.models import (
    AudioStream,
    CustomTerm,
    ProcessingChunk,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptVersion,
)
from local_transcriber.infrastructure.database.session import PersistenceError, transaction


def _version(row: TranscriptVersion) -> TextVersion:
    return TextVersion(
        row.id,
        row.job_id,
        row.version_number,
        VersionType(row.version_type),
        row.content,
        dict(row.processing_metadata),
    )


def _job_lock(session: Session, job_id: UUID) -> TranscriptionJob:
    job = session.scalar(
        select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()
    )
    if job is None:
        raise PersistenceError("Задание не найдено.")
    return job


def _append(
    session: Session, job_id: UUID, kind: VersionType, content: str, metadata: dict[str, object]
) -> TextVersion:
    number = (
        session.scalar(
            select(func.max(TranscriptVersion.version_number)).where(
                TranscriptVersion.job_id == job_id
            )
        )
        or 0
    )
    row = TranscriptVersion(
        job_id=job_id,
        version_number=number + 1,
        version_type=kind.value,
        content=content,
        processing_metadata=metadata,
    )
    session.add(row)
    session.flush()
    return _version(row)


class PostgreSQLTranscriptStore:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def raw(self, job_id: UUID) -> RawTranscript:
        with transaction(self._factory) as session:
            job = _job_lock(session, job_id)
            if job.status != "COMPLETED":
                raise ValueError(
                    "RAW version requires a completed job; checkpoints remain available"
                )
            if (
                session.scalar(
                    select(ProcessingChunk.id)
                    .where(ProcessingChunk.job_id == job_id, ProcessingChunk.status != "COMPLETED")
                    .limit(1)
                )
                is not None
            ):
                raise ValueError("Job has unfinished processing chunks")
            rows = session.execute(
                select(TranscriptSegment, AudioStream.stream_index, ProcessingChunk.chunk_index)
                .join(AudioStream, TranscriptSegment.stream_id == AudioStream.id)
                .join(ProcessingChunk, TranscriptSegment.chunk_id == ProcessingChunk.id)
                .where(TranscriptSegment.job_id == job_id)
                .order_by(
                    AudioStream.stream_index,
                    TranscriptSegment.start_ms,
                    ProcessingChunk.chunk_index,
                    TranscriptSegment.segment_index,
                    TranscriptSegment.id,
                )
                .execution_options(yield_per=1000)
            )
            segments = tuple(
                TextSegment(
                    row.id,
                    stream_index,
                    row.start_ms,
                    row.end_ms,
                    row.raw_text,
                    row.speaker_label,
                    chunk_index,
                    row.segment_index,
                )
                for row, stream_index, chunk_index in rows
            )
            digest = source_digest(segments)
            previous = session.scalars(
                select(TranscriptVersion).where(
                    TranscriptVersion.job_id == job_id, TranscriptVersion.version_type == "RAW"
                )
            ).all()
            if previous:
                if (
                    len(previous) != 1
                    or previous[0].processing_metadata.get("source_digest") != digest
                ):
                    raise ValueError(
                        "Existing RAW differs from the source snapshot; no overwrite allowed"
                    )
                version = _version(previous[0])
            else:
                version = _append(
                    session,
                    job_id,
                    VersionType.RAW,
                    aggregate_raw(segments),
                    {
                        "processor": "raw-aggregation",
                        "rules_version": "1",
                        "mode": "verbatim",
                        "source_digest": digest,
                        "segment_count": len(segments),
                        "order": "stream_index/start_ms/chunk_index/segment_index/id",
                    },
                )
            return RawTranscript(version, segments)

    def save_readable(self, job_id: UUID, raw_id: UUID, result: ProcessedText) -> TextVersion:
        with transaction(self._factory) as session:
            _job_lock(session, job_id)
            raw = session.get(TranscriptVersion, raw_id)
            if raw is None or raw.job_id != job_id or raw.version_type != "RAW":
                raise ValueError("Readable source must be this job's RAW version")
            if result.metadata.get("source_digest") != raw.processing_metadata.get("source_digest"):
                raise ValueError("Readable source snapshot does not match RAW")
            return _append(
                session,
                job_id,
                VersionType.READABLE,
                result.content,
                {
                    **result.metadata,
                    "raw_version_id": str(raw_id),
                },
            )

    def save_manual(self, job_id: UUID, base_id: UUID, content: str) -> TextVersion:
        if not isinstance(content, str) or "\0" in content:
            raise ValueError("Manual content must be text without NUL characters")
        with transaction(self._factory) as session:
            _job_lock(session, job_id)
            base = session.get(TranscriptVersion, base_id)
            if base is None or base.job_id != job_id:
                raise ValueError("Manual base version does not belong to this job")
            raw_id = (
                str(base.id)
                if base.version_type == "RAW"
                else base.processing_metadata.get("raw_version_id")
            )
            if raw_id is None:
                raise ValueError("Manual base has no RAW source reference")
            return _append(
                session,
                job_id,
                VersionType.MANUAL,
                content,
                {
                    "processor": "user",
                    "mode": "manual",
                    "base_version_id": str(base_id),
                    "raw_version_id": raw_id,
                },
            )

    def versions(self, job_id: UUID) -> tuple[TextVersion, ...]:
        with transaction(self._factory) as session:
            if session.get(TranscriptionJob, job_id) is None:
                raise PersistenceError("Задание не найдено.")
            return tuple(
                _version(row)
                for row in session.scalars(
                    select(TranscriptVersion)
                    .where(TranscriptVersion.job_id == job_id)
                    .order_by(TranscriptVersion.version_number)
                )
            )


@dataclass(frozen=True)
class StoredTerm:
    id: UUID
    term: Term


class TermRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def list(self) -> tuple[StoredTerm, ...]:
        with transaction(self._factory) as session:
            return tuple(
                StoredTerm(row.id, Term(row.canonical_form, tuple(row.variants), row.enabled))
                for row in session.scalars(select(CustomTerm).order_by(CustomTerm.canonical_form))
            )

    def enabled_terms(self) -> tuple[Term, ...]:
        return tuple(row.term for row in self.list() if row.term.enabled)

    def create(self, term: Term) -> UUID:
        with transaction(self._factory) as session:
            row = CustomTerm(
                canonical_form=term.canonical, variants=list(term.variants), enabled=term.enabled
            )
            session.add(row)
            session.flush()
            return row.id

    def update(self, term_id: UUID, term: Term) -> None:
        with transaction(self._factory) as session:
            row = session.get(CustomTerm, term_id, with_for_update=True)
            if row is None:
                raise ValueError("Term not found")
            row.canonical_form, row.variants, row.enabled = (
                term.canonical,
                list(term.variants),
                term.enabled,
            )

    def delete(self, term_id: UUID) -> None:
        with transaction(self._factory) as session:
            if session.execute(delete(CustomTerm).where(CustomTerm.id == term_id)).rowcount != 1:
                raise ValueError("Term not found")

    def import_terms(self, terms: tuple[Term, ...]) -> int:
        if len({term.canonical.casefold() for term in terms}) != len(terms):
            raise ValueError("Duplicate canonical form in import")
        # All-or-nothing import, including updates; never leave a partially imported dictionary.
        with transaction(self._factory) as session:
            for term in terms:
                statement = insert(CustomTerm).values(
                    canonical_form=term.canonical,
                    variants=list(term.variants),
                    enabled=term.enabled,
                )
                session.execute(
                    statement.on_conflict_do_update(
                        constraint="uq_term_canonical",
                        set_={
                            "variants": statement.excluded.variants,
                            "enabled": statement.excluded.enabled,
                        },
                    )
                )
        return len(terms)
