"""add_rag_vector_and_ingestion

Revision ID: 692ae78a1fd7
Revises: edb70f27be69
Create Date: 2026-09-30 10:43:55.571561
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = '692ae78a1fd7'
down_revision: Union[str, None] = 'edb70f27be69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rag_ingestion_jobs',
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('document_id', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('job_id'),
    )
    op.create_index(op.f('ix_rag_ingestion_jobs_document_id'), 'rag_ingestion_jobs', ['document_id'], unique=False)
    op.create_index(op.f('ix_rag_ingestion_jobs_source_id'), 'rag_ingestion_jobs', ['source_id'], unique=False)

    op.execute('ALTER TABLE rag_chunks ADD COLUMN embedding vector(1024)')
    op.execute("ALTER TABLE rag_chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', chunk_text)) STORED")
    op.execute('CREATE INDEX ix_rag_chunks_embedding_hnsw ON rag_chunks USING hnsw (embedding vector_cosine_ops)')
    op.execute('CREATE INDEX ix_rag_chunks_tsv_gin ON rag_chunks USING gin (tsv)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_rag_chunks_tsv_gin')
    op.execute('DROP INDEX IF EXISTS ix_rag_chunks_embedding_hnsw')
    op.execute('ALTER TABLE rag_chunks DROP COLUMN IF EXISTS tsv')
    op.execute('ALTER TABLE rag_chunks DROP COLUMN IF EXISTS embedding')
    op.drop_index(op.f('ix_rag_ingestion_jobs_source_id'), table_name='rag_ingestion_jobs')
    op.drop_index(op.f('ix_rag_ingestion_jobs_document_id'), table_name='rag_ingestion_jobs')
    op.drop_table('rag_ingestion_jobs')
