"""Initial PostgreSQL schema; frozen DDL, independent of future ORM changes."""

from alembic import context, op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE custom_terms (
            id UUID NOT NULL,
            canonical_form VARCHAR NOT NULL,
            variants JSONB DEFAULT '[]' NOT NULL,
            enabled BOOLEAN DEFAULT 'true' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_term_canonical UNIQUE (canonical_form),
            CONSTRAINT ck_term_values CHECK (length(btrim(canonical_form)) > 0 AND jsonb_typeof(variants) = 'array')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE media_files (
            id UUID NOT NULL,
            file_path TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_size_bytes BIGINT NOT NULL,
            duration_ms BIGINT NOT NULL,
            container_format VARCHAR NOT NULL,
            audio_streams_count INTEGER NOT NULL,
            file_fingerprint VARCHAR NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT ck_media_sizes CHECK (file_size_bytes >= 0 AND duration_ms >= 0 AND audio_streams_count >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audio_streams (
            id UUID NOT NULL,
            media_file_id UUID NOT NULL,
            stream_index INTEGER NOT NULL,
            codec VARCHAR NOT NULL,
            sample_rate INTEGER NOT NULL,
            channels INTEGER NOT NULL,
            role_label VARCHAR,
            PRIMARY KEY (id),
            CONSTRAINT uq_audio_media_index UNIQUE (media_file_id, stream_index),
            CONSTRAINT uq_audio_id_media UNIQUE (id, media_file_id),
            CONSTRAINT ck_audio_values CHECK (stream_index >= 0 AND sample_rate > 0 AND channels > 0),
            FOREIGN KEY(media_file_id) REFERENCES media_files (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_audio_streams_media_file_id ON audio_streams (media_file_id)
        """
    )
    op.execute(
        """
        CREATE TABLE transcription_jobs (
            id UUID NOT NULL,
            media_file_id UUID NOT NULL,
            status VARCHAR DEFAULT 'PENDING' NOT NULL,
            model_name VARCHAR NOT NULL,
            language VARCHAR NOT NULL,
            parameters JSONB DEFAULT '{}' NOT NULL,
            progress_percent NUMERIC(5, 2) DEFAULT '0' NOT NULL,
            total_chunks INTEGER DEFAULT '0' NOT NULL,
            completed_chunks INTEGER DEFAULT '0' NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE,
            finished_at TIMESTAMP WITH TIME ZONE,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_job_id_media UNIQUE (id, media_file_id),
            CONSTRAINT ck_job_status CHECK (status IN ('PENDING','ANALYZING','PROCESSING','PAUSED','INTERRUPTED','COMPLETED','FAILED','CANCELLED')),
            CONSTRAINT ck_job_progress CHECK (total_chunks >= 0 AND completed_chunks >= 0 AND completed_chunks <= total_chunks AND progress_percent BETWEEN 0 AND 100),
            CONSTRAINT ck_job_parameters CHECK (jsonb_typeof(parameters) = 'object'),
            FOREIGN KEY(media_file_id) REFERENCES media_files (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_transcription_jobs_media_file_id ON transcription_jobs (media_file_id)
        """
    )
    op.execute(
        """
        CREATE TABLE processing_chunks (
            id UUID NOT NULL,
            job_id UUID NOT NULL,
            stream_id UUID NOT NULL,
            media_file_id UUID NOT NULL,
            chunk_index INTEGER NOT NULL,
            start_ms BIGINT NOT NULL,
            end_ms BIGINT NOT NULL,
            status VARCHAR DEFAULT 'PENDING' NOT NULL,
            attempt_count INTEGER DEFAULT '0' NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            error_message TEXT,
            PRIMARY KEY (id),
            CONSTRAINT uq_chunk_job_stream_index UNIQUE (job_id, stream_id, chunk_index),
            CONSTRAINT uq_chunk_identity UNIQUE (id, job_id, stream_id),
            CONSTRAINT fk_chunk_job_media FOREIGN KEY(job_id, media_file_id) REFERENCES transcription_jobs (id, media_file_id) ON DELETE CASCADE,
            CONSTRAINT fk_chunk_stream_media FOREIGN KEY(stream_id, media_file_id) REFERENCES audio_streams (id, media_file_id) ON DELETE CASCADE,
            CONSTRAINT ck_chunk_values CHECK (chunk_index >= 0 AND start_ms >= 0 AND end_ms > start_ms AND attempt_count >= 0),
            CONSTRAINT ck_chunk_status CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED')),
            CONSTRAINT ck_chunk_completion CHECK ((status = 'COMPLETED') = (completed_at IS NOT NULL))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_processing_chunks_job_id ON processing_chunks (job_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_processing_chunks_stream_id ON processing_chunks (stream_id)
        """
    )
    op.execute(
        """
        CREATE TABLE transcript_versions (
            id UUID NOT NULL,
            job_id UUID NOT NULL,
            version_number INTEGER NOT NULL,
            version_type VARCHAR NOT NULL,
            content TEXT NOT NULL,
            processing_metadata JSONB DEFAULT '{}' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_version_job_number UNIQUE (job_id, version_number),
            CONSTRAINT ck_version_values CHECK (version_number > 0 AND version_type IN ('RAW','READABLE','MANUAL')),
            CONSTRAINT ck_version_metadata CHECK (jsonb_typeof(processing_metadata) = 'object'),
            FOREIGN KEY(job_id) REFERENCES transcription_jobs (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_transcript_versions_job_id ON transcript_versions (job_id)
        """
    )
    op.execute(
        """
        CREATE TABLE transcript_segments (
            id UUID NOT NULL,
            job_id UUID NOT NULL,
            chunk_id UUID NOT NULL,
            stream_id UUID NOT NULL,
            start_ms BIGINT NOT NULL,
            end_ms BIGINT NOT NULL,
            raw_text TEXT NOT NULL,
            speaker_label VARCHAR,
            segment_index INTEGER NOT NULL,
            metadata JSONB DEFAULT '{}' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_segment_chunk_scope FOREIGN KEY(chunk_id, job_id, stream_id) REFERENCES processing_chunks (id, job_id, stream_id) ON DELETE CASCADE,
            CONSTRAINT uq_segment_chunk_index UNIQUE (chunk_id, segment_index),
            CONSTRAINT ck_segment_values CHECK (start_ms >= 0 AND end_ms > start_ms AND segment_index >= 0),
            CONSTRAINT ck_segment_metadata CHECK (jsonb_typeof(metadata) = 'object')
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_segment_job_start ON transcript_segments (job_id, start_ms)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_transcript_segments_chunk_id ON transcript_segments (chunk_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_transcript_segments_job_id ON transcript_segments (job_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_transcript_segments_stream_id ON transcript_segments (stream_id)
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_raw_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_TABLE_NAME = 'transcript_segments' THEN RAISE EXCEPTION 'RAW segments are immutable'; ELSIF OLD.version_type = 'RAW' THEN RAISE EXCEPTION 'RAW versions are immutable'; END IF; RETURN NEW; END; $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_segment_immutable BEFORE UPDATE ON transcript_segments FOR EACH ROW EXECUTE FUNCTION protect_raw_update()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_raw_version_immutable BEFORE UPDATE ON transcript_versions FOR EACH ROW EXECUTE FUNCTION protect_raw_update()
        """
    )


def downgrade() -> None:
    config = context.config
    if (
        not config.attributes.get("test_database")
        and context.get_x_argument(as_dictionary=True).get("test") != "true"
    ):
        raise RuntimeError("Downgrade is restricted to a separate test database")
    op.drop_table("transcript_segments")
    op.drop_table("transcript_versions")
    op.drop_table("processing_chunks")
    op.drop_table("transcription_jobs")
    op.drop_table("audio_streams")
    op.drop_table("media_files")
    op.drop_table("custom_terms")
    op.execute("DROP FUNCTION protect_raw_update()")
