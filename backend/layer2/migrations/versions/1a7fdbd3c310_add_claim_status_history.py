"""add claim status history

Revision ID: 1a7fdbd3c310
Revises: ce6ac1db7402
Create Date: 2026-07-25 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1a7fdbd3c310"
down_revision: Union[str, Sequence[str], None] = "ce6ac1db7402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "claim_status_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("claim_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["ingestion_id"], ["ingestion_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claim_status_history_claim_effective", "claim_status_history", ["claim_id", "effective_at"])


def downgrade() -> None:
    op.drop_index("ix_claim_status_history_claim_effective", table_name="claim_status_history")
    op.drop_table("claim_status_history")
