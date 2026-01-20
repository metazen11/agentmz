"""add_task_nodes_and_runs

Revision ID: b7f1c0e2a9e6
Revises: a2c1d9b8e4f1
Create Date: 2026-01-20 02:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7f1c0e2a9e6"
down_revision: Union[str, Sequence[str], None] = "a2c1d9b8e4f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "task_nodes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("agent_prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "task_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("node_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tests_run", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("screenshots", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["node_id"], ["task_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_runs_task_id_started_at", "task_runs", ["task_id", "started_at"])

    op.add_column("tasks", sa.Column("node_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_tasks_node_id", "tasks", "task_nodes", ["node_id"], ["id"])
    op.create_index("ix_tasks_node_id", "tasks", ["node_id"])

    conn = op.get_bind()
    node_rows = [
        ("pm", "You are a project planner. Clarify scope, break down work, and outline risks."),
        ("dev", "You are a developer. Implement the requested feature or fix."),
        (
            "qa",
            "You are a QA engineer. Verify acceptance criteria and run end-to-end tests "
            "using Playwright or relevant frameworks. Report tests and screenshots as task comments.",
        ),
        (
            "security",
            "You are a security reviewer. Check for best practices, edge cases, and regressions.",
        ),
        (
            "documentation",
            "You are a technical writer. Document changes, tests run, and how to verify.",
        ),
    ]
    for name, prompt in node_rows:
        conn.execute(
            sa.text(
                """
                INSERT INTO task_nodes (name, agent_prompt, created_at, updated_at)
                VALUES (:name, :prompt, NOW(), NOW())
                """
            ),
            {"name": name, "prompt": prompt},
        )

    dev_id = conn.execute(sa.text("SELECT id FROM task_nodes WHERE name = 'dev'")).scalar()
    qa_id = conn.execute(sa.text("SELECT id FROM task_nodes WHERE name = 'qa'")).scalar()
    pm_id = conn.execute(sa.text("SELECT id FROM task_nodes WHERE name = 'pm'")).scalar()
    docs_id = conn.execute(sa.text("SELECT id FROM task_nodes WHERE name = 'documentation'")).scalar()

    if qa_id:
        conn.execute(sa.text("UPDATE tasks SET node_id = :node_id WHERE stage = 'qa'"), {"node_id": qa_id})
    if pm_id:
        conn.execute(sa.text("UPDATE tasks SET node_id = :node_id WHERE stage = 'review'"), {"node_id": pm_id})
    if docs_id:
        conn.execute(sa.text("UPDATE tasks SET node_id = :node_id WHERE stage = 'complete'"), {"node_id": docs_id})
    if dev_id:
        conn.execute(sa.text("UPDATE tasks SET node_id = :node_id WHERE node_id IS NULL"), {"node_id": dev_id})

    op.alter_column("tasks", "node_id", nullable=False)
    op.drop_column("tasks", "stage")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("tasks", sa.Column("stage", sa.String(length=20), nullable=True))
    op.drop_index("ix_tasks_node_id", table_name="tasks")
    op.drop_constraint("fk_tasks_node_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "node_id")

    op.drop_index("ix_task_runs_task_id_started_at", table_name="task_runs")
    op.drop_table("task_runs")
    op.drop_table("task_nodes")
