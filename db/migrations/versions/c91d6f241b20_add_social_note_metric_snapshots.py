"""add social note metadata and metric snapshots

Revision ID: c91d6f241b20
Revises: 32934a2e2f05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91d6f241b20"
down_revision: Union[str, None] = "32934a2e2f05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_notes",
        sa.Column("social_note_id", sa.String(length=96), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("external_note_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("author_hash", sa.String(length=128), nullable=True),
        sa.Column("note_type", sa.String(length=32), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("image_urls", sa.JSON(), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("themes", sa.JSON(), nullable=True),
        sa.Column("crawl_query", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.document_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("social_note_id"),
        sa.UniqueConstraint("document_id"),
        sa.UniqueConstraint("platform", "external_note_id", name="uq_social_note_platform_external"),
    )
    op.create_index("ix_social_notes_city", "social_notes", ["city"])
    op.create_index("ix_social_notes_city_platform", "social_notes", ["city", "platform"])
    op.create_table(
        "social_metric_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("social_note_id", sa.String(length=96), nullable=False),
        sa.Column("likes", sa.BigInteger(), nullable=False),
        sa.Column("collects", sa.BigInteger(), nullable=False),
        sa.Column("comments", sa.BigInteger(), nullable=False),
        sa.Column("shares", sa.BigInteger(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["social_note_id"], ["social_notes.social_note_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index("ix_social_metric_snapshots_social_note_id", "social_metric_snapshots", ["social_note_id"])
    op.create_index("ix_social_metric_note_captured", "social_metric_snapshots", ["social_note_id", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_social_metric_note_captured", table_name="social_metric_snapshots")
    op.drop_index("ix_social_metric_snapshots_social_note_id", table_name="social_metric_snapshots")
    op.drop_table("social_metric_snapshots")
    op.drop_index("ix_social_notes_city_platform", table_name="social_notes")
    op.drop_index("ix_social_notes_city", table_name="social_notes")
    op.drop_table("social_notes")
