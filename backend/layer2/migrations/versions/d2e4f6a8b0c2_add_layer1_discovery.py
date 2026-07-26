"""add Layer 1 discovery persistence

Revision ID: d2e4f6a8b0c2
Revises: c1d0e9f8a7b6
"""

from alembic import op
import sqlalchemy as sa


revision = "d2e4f6a8b0c2"
down_revision = "c1d0e9f8a7b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("topic_key", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("requested_limit", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "discovered_articles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("discovery_request_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=False),
        sa.Column("published_date", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["discovery_request_id"], ["discovery_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovered_articles_request", "discovered_articles", ["discovery_request_id"])


def downgrade() -> None:
    op.drop_index("ix_discovered_articles_request", table_name="discovered_articles")
    op.drop_table("discovered_articles")
    op.drop_table("discovery_requests")
