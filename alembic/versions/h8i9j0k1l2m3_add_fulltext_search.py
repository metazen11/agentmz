"""Add full-text search (tsvector) to project_knowledge.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-02-05

Adds PostgreSQL full-text search capabilities alongside vector embeddings
for hybrid search (fast keyword + semantic similarity).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tsvector column for full-text search
    op.execute("""
        ALTER TABLE project_knowledge
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(summary, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(file_path, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(content, '')), 'C')
        ) STORED
    """)

    # Create GIN index for fast full-text search
    op.execute("""
        CREATE INDEX ix_project_knowledge_search_vector
        ON project_knowledge USING GIN (search_vector)
    """)

    # Convert embedding column from double precision[] to vector type
    # First drop any existing data (we'll regenerate embeddings)
    op.execute("UPDATE project_knowledge SET embedding = NULL")

    # Change column type to proper pgvector vector type (768 dims for nomic-embed-text)
    op.execute("""
        ALTER TABLE project_knowledge
        ALTER COLUMN embedding TYPE vector(768)
        USING embedding::vector(768)
    """)

    # Create HNSW index for fast vector similarity search
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_project_knowledge_embedding
        ON project_knowledge USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_project_knowledge_embedding")
    op.execute("DROP INDEX IF EXISTS ix_project_knowledge_search_vector")
    op.execute("ALTER TABLE project_knowledge DROP COLUMN IF EXISTS search_vector")
