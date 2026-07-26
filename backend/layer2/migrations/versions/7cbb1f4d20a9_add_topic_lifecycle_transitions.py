"""add topic lifecycle transitions

Revision ID: 7cbb1f4d20a9
Revises: ef5a9c0321d4
Create Date: 2026-07-25 20:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "7cbb1f4d20a9"
down_revision: Union[str, Sequence[str], None] = "ef5a9c0321d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table("topic_lifecycle_transitions", sa.Column("id", sa.UUID(), nullable=False), sa.Column("topic_id", sa.UUID(), nullable=False), sa.Column("from_status", sa.String(length=32), nullable=False), sa.Column("to_status", sa.String(length=32), nullable=False), sa.Column("reason", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]), sa.PrimaryKeyConstraint("id"))

def downgrade() -> None:
    op.drop_table("topic_lifecycle_transitions")
