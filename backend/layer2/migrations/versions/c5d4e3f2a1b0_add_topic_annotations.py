"""add topic annotations

Revision ID: c5d4e3f2a1b0
Revises: b4c3d2e1f0a9
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c5d4e3f2a1b0"
down_revision = "b4c3d2e1f0a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_annotations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("raw_package_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["raw_package_id"], ["raw_packages.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topic_annotations_topic_kind", "topic_annotations", ["topic_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_topic_annotations_topic_kind", table_name="topic_annotations")
    op.drop_table("topic_annotations")
