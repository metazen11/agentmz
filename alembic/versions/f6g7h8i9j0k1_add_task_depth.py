"""add_task_depth

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-01-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6g7h8i9j0k1"
down_revision: Union[str, Sequence[str], None] = "e5f6g7h8i9j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add depth column to tasks table for tracking delegation depth."""
    op.add_column(
        "tasks",
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Remove depth column from tasks table."""
    op.drop_column("tasks", "depth")
