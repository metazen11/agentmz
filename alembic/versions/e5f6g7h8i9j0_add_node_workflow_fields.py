"""add_node_workflow_fields

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6a7b8c9
Create Date: 2026-01-20 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f6g7h8i9j0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add workflow fields to task_nodes table."""
    # pre_hooks: JSON array of commands to run BEFORE agent
    op.add_column(
        "task_nodes",
        sa.Column("pre_hooks", sa.Text(), nullable=True),
    )

    # post_hooks: JSON array of commands to run AFTER agent
    op.add_column(
        "task_nodes",
        sa.Column("post_hooks", sa.Text(), nullable=True),
    )

    # pass_node_id: Route to this node on SUCCESS
    op.add_column(
        "task_nodes",
        sa.Column("pass_node_id", sa.BigInteger(), nullable=True),
    )

    # fail_node_id: Route to this node on FAILURE
    op.add_column(
        "task_nodes",
        sa.Column("fail_node_id", sa.BigInteger(), nullable=True),
    )

    # max_iterations: Max agent iterations (default 20)
    op.add_column(
        "task_nodes",
        sa.Column("max_iterations", sa.Integer(), nullable=True, server_default="20"),
    )

    # Add self-referential foreign keys with SET NULL on delete
    op.create_foreign_key(
        "fk_task_nodes_pass_node_id",
        "task_nodes",
        "task_nodes",
        ["pass_node_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_foreign_key(
        "fk_task_nodes_fail_node_id",
        "task_nodes",
        "task_nodes",
        ["fail_node_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove workflow fields from task_nodes table."""
    op.drop_constraint("fk_task_nodes_fail_node_id", "task_nodes", type_="foreignkey")
    op.drop_constraint("fk_task_nodes_pass_node_id", "task_nodes", type_="foreignkey")
    op.drop_column("task_nodes", "max_iterations")
    op.drop_column("task_nodes", "fail_node_id")
    op.drop_column("task_nodes", "pass_node_id")
    op.drop_column("task_nodes", "post_hooks")
    op.drop_column("task_nodes", "pre_hooks")
