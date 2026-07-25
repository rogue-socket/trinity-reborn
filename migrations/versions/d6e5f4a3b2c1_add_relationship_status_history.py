"""add relationship status history

Revision ID: d6e5f4a3b2c1
Revises: c5d4e3f2a1b0
"""
from alembic import op
import sqlalchemy as sa


revision = "d6e5f4a3b2c1"
down_revision = "c5d4e3f2a1b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relationship_status_history",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("relationship_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "effective_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ingestion_id"], ["ingestion_runs.id"]),
        sa.ForeignKeyConstraint(["relationship_id"], ["graph_relationships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_relationship_status_history_relationship_effective",
        "relationship_status_history",
        ["relationship_id", "effective_at"],
    )
    op.execute(
        """
        INSERT INTO relationship_status_history
            (relationship_id, ingestion_id, status, reason, effective_at)
        SELECT id, NULL, status, 'Backfilled current status.', created_at
        FROM graph_relationships
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_relationship_status_history_relationship_effective",
        table_name="relationship_status_history",
    )
    op.drop_table("relationship_status_history")
