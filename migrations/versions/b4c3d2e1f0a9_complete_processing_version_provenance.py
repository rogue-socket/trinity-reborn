"""complete processing version provenance

Revision ID: b4c3d2e1f0a9
Revises: 9ae431b75c5d
"""
from alembic import op
import sqlalchemy as sa


revision = "b4c3d2e1f0a9"
down_revision = "9ae431b75c5d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column("input_schema_version", sa.String(length=16), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "resolution_decisions",
        sa.Column("input_schema_version", sa.String(length=16), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "resolution_decisions",
        sa.Column("graph_model_version", sa.String(length=32), nullable=False, server_default="kg-model-0.1"),
    )
    op.alter_column("ingestion_runs", "input_schema_version", server_default=None)
    op.alter_column("resolution_decisions", "input_schema_version", server_default=None)
    op.alter_column("resolution_decisions", "graph_model_version", server_default=None)


def downgrade() -> None:
    op.drop_column("resolution_decisions", "graph_model_version")
    op.drop_column("resolution_decisions", "input_schema_version")
    op.drop_column("ingestion_runs", "input_schema_version")
