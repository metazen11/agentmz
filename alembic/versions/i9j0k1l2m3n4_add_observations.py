"""Add observations table for agent memory system.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-02-07

Stores tool attempt observations for agent learning:
- Hook inserts raw observations (embedding=NULL)
- Background worker classifies and embeds
- Retrieval via cosine similarity for context injection
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create observations table
    op.execute("""
        CREATE TABLE observations (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT NOW(),

            -- Context: where this observation happened
            project_id BIGINT REFERENCES projects(id) ON DELETE SET NULL,
            task_id BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
            file_path TEXT,

            -- External system references (Asana, Jira, GitHub, etc.)
            -- Example: {"asana": {"task_id": "123"}, "github": {"pr": 456}}
            external_refs JSONB,

            -- Raw tool data (inserted by hook)
            tool TEXT NOT NULL,
            args_summary TEXT,
            output_summary TEXT,
            exit_code INTEGER,
            success BOOLEAN NOT NULL,
            duration_ms INTEGER,

            -- Classification (added by worker, NULL until processed)
            obs_type TEXT,
            title TEXT,
            tokens INTEGER,

            -- Embedding (768-dim for nomic-embed-text, NULL until processed)
            embedding vector(768),

            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Index for finding unprocessed observations (worker query)
    op.execute("""
        CREATE INDEX ix_obs_unprocessed ON observations (id)
        WHERE embedding IS NULL
    """)

    # Index for session grouping
    op.execute("""
        CREATE INDEX ix_obs_session ON observations (session_id)
    """)

    # Index for filtering by type
    op.execute("""
        CREATE INDEX ix_obs_type ON observations (obs_type)
        WHERE obs_type IS NOT NULL
    """)

    # Index for context lookups
    op.execute("""
        CREATE INDEX ix_obs_project ON observations (project_id)
        WHERE project_id IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX ix_obs_task ON observations (task_id)
        WHERE task_id IS NOT NULL
    """)

    # GIN index for JSONB external_refs queries
    op.execute("""
        CREATE INDEX ix_obs_external_refs ON observations
        USING GIN (external_refs)
        WHERE external_refs IS NOT NULL
    """)

    # HNSW index for vector similarity search (only on processed rows)
    op.execute("""
        CREATE INDEX ix_obs_embedding ON observations
        USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS observations CASCADE")
