"""add_memory_embeddings_and_evidence_metadata

Revision ID: 32934a2e2f05
Revises: 692ae78a1fd7
Create Date: 2026-09-30 14:35:36.427805
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = '32934a2e2f05'
down_revision: Union[str, None] = '692ae78a1fd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('memory_evidence', sa.Column('evidence_type', sa.String(length=64), nullable=False, server_default='explicit_statement'))
    op.add_column('memory_evidence', sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'))
    op.add_column('memory_items', sa.Column('embedding', Vector(1024), nullable=True))
    op.add_column('memory_items', sa.Column('embedding_text', sa.Text(), nullable=True))
    op.execute('CREATE INDEX ix_memory_items_embedding_hnsw ON memory_items USING hnsw (embedding vector_cosine_ops)')
    op.execute('CREATE INDEX ix_memory_items_user_type_status ON memory_items (user_id, memory_type, status)')
    op.execute('CREATE INDEX ix_memory_items_user_scope_status ON memory_items (user_id, scope, status)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_memory_items_user_scope_status')
    op.execute('DROP INDEX IF EXISTS ix_memory_items_user_type_status')
    op.execute('DROP INDEX IF EXISTS ix_memory_items_embedding_hnsw')
    op.drop_column('memory_items', 'embedding_text')
    op.drop_column('memory_items', 'embedding')
    op.drop_column('memory_evidence', 'confidence')
    op.drop_column('memory_evidence', 'evidence_type')
