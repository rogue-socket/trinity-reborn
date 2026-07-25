"""add lifecycle ingestion provenance

Revision ID: b0c9d8e7f6a5
Revises: a9b8c7d6e5f4
"""
from alembic import op
import sqlalchemy as sa


revision = "b0c9d8e7f6a5"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "topic_lifecycle_transitions",
        sa.Column("ingestion_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_topic_lifecycle_transitions_ingestion",
        "topic_lifecycle_transitions",
        "ingestion_runs",
        ["ingestion_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_topic_lifecycle_transitions_ingestion",
        "topic_lifecycle_transitions",
        type_="foreignkey",
    )
    op.drop_column("topic_lifecycle_transitions", "ingestion_id")
