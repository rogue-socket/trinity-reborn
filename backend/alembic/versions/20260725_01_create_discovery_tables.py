"""Create discovery request and result tables.

Revision ID: 20260725_01
Revises:
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260725_01"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create tables for persisted Google News discovery runs."""
    op.create_table(
        "discovery_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "discovery_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("discovery_request_id", sa.Uuid(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=False),
        sa.Column("published_date", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["discovery_request_id"], ["discovery_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_discovery_results_discovery_request_id",
        "discovery_results",
        ["discovery_request_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the discovery persistence tables."""
    op.drop_index("ix_discovery_results_discovery_request_id", "discovery_results")
    op.drop_table("discovery_results")
    op.drop_table("discovery_requests")
