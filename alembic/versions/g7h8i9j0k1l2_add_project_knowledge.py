"""Add project_knowledge table with pgvector embeddings.

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-02-01

Phase 3: Project Memory - stores code snippets and documentation with
embeddings for semantic search.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'g7h8i9j0k1l2'
down_revision = 'f6g7h8i9j0k1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create project_knowledge table
    op.create_table(
        'project_knowledge',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('content_type', sa.String(50), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        # Vector column for embeddings (1536 dims for OpenAI ada-002)
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index on project_id for fast lookups
    op.create_index('ix_project_knowledge_project_id', 'project_knowledge', ['project_id'])

    # Create index on content_type for filtering
    op.create_index('ix_project_knowledge_content_type', 'project_knowledge', ['content_type'])

    # Note: Vector similarity index should be added after data is populated
    # Example: CREATE INDEX ON project_knowledge USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);


def downgrade() -> None:
    op.drop_index('ix_project_knowledge_content_type', table_name='project_knowledge')
    op.drop_index('ix_project_knowledge_project_id', table_name='project_knowledge')
    op.drop_table('project_knowledge')
    # Note: We don't drop the vector extension as other tables might use it
