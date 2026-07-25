"""add derivation provenance fields

Revision ID: e7f6a5b4c3d2
Revises: d6e5f4a3b2c1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e7f6a5b4c3d2"
down_revision = "d6e5f4a3b2c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("claim_assertions", "relationship_assertions"):
        op.add_column(
            table_name,
            sa.Column(
                "derivation_method",
                sa.String(length=128),
                nullable=False,
                server_default="legacy",
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "input_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
        op.add_column(
            table_name,
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
        )
        op.add_column(
            table_name,
            sa.Column(
                "processing_version",
                sa.String(length=32),
                nullable=False,
                server_default="kg-pipeline-0.1",
            ),
        )
        op.add_column(
            table_name,
            sa.Column("resolution_decision_id", sa.UUID(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_resolution_decision",
            table_name,
            "resolution_decisions",
            ["resolution_decision_id"],
            ["id"],
        )

    op.add_column(
        "confidence_assessments",
        sa.Column(
            "model_or_rule_version",
            sa.String(length=32),
            nullable=False,
            server_default="kg-pipeline-0.1",
        ),
    )
    op.add_column(
        "confidence_assessments",
        sa.Column(
            "supporting_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("confidence_assessments", "supporting_ids")
    op.drop_column("confidence_assessments", "model_or_rule_version")
    for table_name in ("relationship_assertions", "claim_assertions"):
        op.drop_constraint(
            f"fk_{table_name}_resolution_decision",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "resolution_decision_id")
        op.drop_column(table_name, "processing_version")
        op.drop_column(table_name, "confidence")
        op.drop_column(table_name, "input_ids")
        op.drop_column(table_name, "derivation_method")
