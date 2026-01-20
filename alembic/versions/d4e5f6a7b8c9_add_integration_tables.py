"""add_integration_tables

Revision ID: d4e5f6a7b8c9
Revises: b7f1c0e2a9e6
Create Date: 2026-01-19 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "b7f1c0e2a9e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create integration tables and seed providers."""
    # 1. integration_providers - available providers
    op.create_table(
        "integration_providers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("auth_type", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # 2. integration_credentials - encrypted API tokens
    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False, default=True),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["integration_providers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integration_credentials_provider_id",
        "integration_credentials",
        ["provider_id"],
    )

    # 3. project_integrations - links local project to external project
    op.create_table(
        "project_integrations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("credential_id", sa.BigInteger(), nullable=False),
        sa.Column("external_project_id", sa.String(length=255), nullable=False),
        sa.Column("external_project_name", sa.String(length=500), nullable=True),
        sa.Column("sync_direction", sa.String(length=20), nullable=False, default="import"),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["integration_credentials.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_integrations_project_id",
        "project_integrations",
        ["project_id"],
    )
    op.create_index(
        "ix_project_integrations_credential_id",
        "project_integrations",
        ["credential_id"],
    )

    # 4. task_external_links - maps local task to external task ID
    op.create_table(
        "task_external_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("integration_id", sa.BigInteger(), nullable=False),
        sa.Column("external_task_id", sa.String(length=255), nullable=False),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("sync_status", sa.String(length=20), nullable=False, default="synced"),
        sa.Column("sync_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["project_integrations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_external_links_task_id",
        "task_external_links",
        ["task_id"],
    )
    op.create_index(
        "ix_task_external_links_integration_id",
        "task_external_links",
        ["integration_id"],
    )
    op.create_index(
        "ix_task_external_links_external_task_id",
        "task_external_links",
        ["external_task_id"],
    )

    # Seed default providers
    conn = op.get_bind()
    providers = [
        ("asana", "Asana", "pat"),
        ("jira", "Jira", "api_key"),
        ("linear", "Linear", "api_key"),
        ("github_issues", "GitHub Issues", "pat"),
    ]
    for name, display_name, auth_type in providers:
        conn.execute(
            sa.text(
                """
                INSERT INTO integration_providers (name, display_name, auth_type, enabled, created_at)
                VALUES (:name, :display_name, :auth_type, true, NOW())
                """
            ),
            {"name": name, "display_name": display_name, "auth_type": auth_type},
        )


def downgrade() -> None:
    """Drop integration tables."""
    op.drop_index("ix_task_external_links_external_task_id", table_name="task_external_links")
    op.drop_index("ix_task_external_links_integration_id", table_name="task_external_links")
    op.drop_index("ix_task_external_links_task_id", table_name="task_external_links")
    op.drop_table("task_external_links")

    op.drop_index("ix_project_integrations_credential_id", table_name="project_integrations")
    op.drop_index("ix_project_integrations_project_id", table_name="project_integrations")
    op.drop_table("project_integrations")

    op.drop_index("ix_integration_credentials_provider_id", table_name="integration_credentials")
    op.drop_table("integration_credentials")

    op.drop_table("integration_providers")
