"""Persist normalized initial PTS for absolute audio timestamps."""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import BigInteger, Column

revision: str = "0003_audio_timeline"
down_revision: str | None = "0002_media_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audio_streams",
        Column("start_time_ms", BigInteger(), nullable=False, server_default="0"),
    )
    op.drop_constraint("ck_audio_values", "audio_streams", type_="check")
    op.create_check_constraint(
        "ck_audio_values",
        "audio_streams",
        "stream_index >= 0 AND sample_rate > 0 AND channels > 0 AND start_time_ms >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_audio_values", "audio_streams", type_="check")
    op.create_check_constraint(
        "ck_audio_values",
        "audio_streams",
        "stream_index >= 0 AND sample_rate > 0 AND channels > 0",
    )
    op.drop_column("audio_streams", "start_time_ms")
