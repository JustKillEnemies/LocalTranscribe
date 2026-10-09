"""Add idempotent media fingerprint and ffprobe labels."""

import sqlalchemy as sa
from alembic import context, op

revision = "0002_media_import"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_media_fingerprint", "media_files", ["file_fingerprint"])
    op.add_column("audio_streams", sa.Column("language_tag", sa.String(), nullable=True))
    op.add_column("audio_streams", sa.Column("title", sa.Text(), nullable=True))


def downgrade() -> None:
    config = context.config
    if (
        not config.attributes.get("test_database")
        and context.get_x_argument(as_dictionary=True).get("test") != "true"
    ):
        raise RuntimeError("Downgrade is restricted to a separate test database")
    op.drop_column("audio_streams", "title")
    op.drop_column("audio_streams", "language_tag")
    op.drop_constraint("uq_media_fingerprint", "media_files", type_="unique")
