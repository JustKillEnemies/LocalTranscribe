"""SQLAlchemy mappings; PostgreSQL owns referential and data integrity."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MediaFile(Base):
    __tablename__ = "media_files"
    __table_args__ = (
        UniqueConstraint("file_fingerprint", name="uq_media_fingerprint"),
        CheckConstraint(
            "file_size_bytes >= 0 AND duration_ms >= 0 AND audio_streams_count >= 0",
            name="ck_media_sizes",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_path: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    duration_ms: Mapped[int] = mapped_column(BigInteger)
    container_format: Mapped[str] = mapped_column(String)
    audio_streams_count: Mapped[int] = mapped_column(Integer)
    file_fingerprint: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AudioStream(Base):
    __tablename__ = "audio_streams"
    __table_args__ = (
        UniqueConstraint("media_file_id", "stream_index", name="uq_audio_media_index"),
        UniqueConstraint("id", "media_file_id", name="uq_audio_id_media"),
        CheckConstraint(
            "stream_index >= 0 AND sample_rate > 0 AND channels > 0", name="ck_audio_values"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    media_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("media_files.id", ondelete="CASCADE"), index=True
    )
    stream_index: Mapped[int] = mapped_column(Integer)
    codec: Mapped[str] = mapped_column(String)
    sample_rate: Mapped[int] = mapped_column(Integer)
    channels: Mapped[int] = mapped_column(Integer)
    role_label: Mapped[str | None] = mapped_column(String)
    language_tag: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(Text)


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"
    __table_args__ = (
        UniqueConstraint("id", "media_file_id", name="uq_job_id_media"),
        CheckConstraint(
            "status IN ('PENDING','ANALYZING','PROCESSING','PAUSED','INTERRUPTED','COMPLETED','FAILED','CANCELLED')",
            name="ck_job_status",
        ),
        CheckConstraint(
            "total_chunks >= 0 AND completed_chunks >= 0 AND completed_chunks <= total_chunks AND progress_percent BETWEEN 0 AND 100",
            name="ck_job_progress",
        ),
        CheckConstraint("jsonb_typeof(parameters) = 'object'", name="ck_job_parameters"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    media_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("media_files.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String, default="PENDING", server_default="PENDING")
    model_name: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    progress_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, server_default="0")
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_chunks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingChunk(Base):
    __tablename__ = "processing_chunks"
    __table_args__ = (
        UniqueConstraint("job_id", "stream_id", "chunk_index", name="uq_chunk_job_stream_index"),
        UniqueConstraint("id", "job_id", "stream_id", name="uq_chunk_identity"),
        ForeignKeyConstraint(
            ["job_id", "media_file_id"],
            ["transcription_jobs.id", "transcription_jobs.media_file_id"],
            name="fk_chunk_job_media",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["stream_id", "media_file_id"],
            ["audio_streams.id", "audio_streams.media_file_id"],
            name="fk_chunk_stream_media",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "chunk_index >= 0 AND start_ms >= 0 AND end_ms > start_ms AND attempt_count >= 0",
            name="ck_chunk_values",
        ),
        CheckConstraint(
            "status IN ('PENDING','PROCESSING','COMPLETED','FAILED')", name="ck_chunk_status"
        ),
        CheckConstraint(
            "(status = 'COMPLETED') = (completed_at IS NOT NULL)", name="ck_chunk_completion"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(index=True)
    stream_id: Mapped[UUID] = mapped_column(index=True)
    media_file_id: Mapped[UUID] = mapped_column()
    chunk_index: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(BigInteger)
    end_ms: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String, default="PENDING", server_default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "job_id", "stream_id"],
            ["processing_chunks.id", "processing_chunks.job_id", "processing_chunks.stream_id"],
            name="fk_segment_chunk_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint("chunk_id", "segment_index", name="uq_segment_chunk_index"),
        CheckConstraint(
            "start_ms >= 0 AND end_ms > start_ms AND segment_index >= 0", name="ck_segment_values"
        ),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="ck_segment_metadata"),
        Index("ix_segment_job_start", "job_id", "start_ms"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(index=True)
    chunk_id: Mapped[UUID] = mapped_column(index=True)
    stream_id: Mapped[UUID] = mapped_column(index=True)
    start_ms: Mapped[int] = mapped_column(BigInteger)
    end_ms: Mapped[int] = mapped_column(BigInteger)
    raw_text: Mapped[str] = mapped_column(Text)
    speaker_label: Mapped[str | None] = mapped_column(String)
    segment_index: Mapped[int] = mapped_column(Integer)
    segment_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TranscriptVersion(Base):
    __tablename__ = "transcript_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "version_number", name="uq_version_job_number"),
        CheckConstraint(
            "version_number > 0 AND version_type IN ('RAW','READABLE','MANUAL')",
            name="ck_version_values",
        ),
        CheckConstraint("jsonb_typeof(processing_metadata) = 'object'", name="ck_version_metadata"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("transcription_jobs.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    version_type: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    processing_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomTerm(Base):
    __tablename__ = "custom_terms"
    __table_args__ = (
        UniqueConstraint("canonical_form", name="uq_term_canonical"),
        CheckConstraint(
            "length(btrim(canonical_form)) > 0 AND jsonb_typeof(variants) = 'array'",
            name="ck_term_values",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_form: Mapped[str] = mapped_column(String)
    variants: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
