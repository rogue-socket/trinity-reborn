"""add mapping revisions

Revision ID: c1d0e9f8a7b6
Revises: b0c9d8e7f6a5
"""
from alembic import op
import sqlalchemy as sa


revision = "c1d0e9f8a7b6"
down_revision = "b0c9d8e7f6a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resolution_decisions",
        sa.Column("supersedes_decision_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_resolution_decisions_supersedes",
        "resolution_decisions",
        "resolution_decisions",
        ["supersedes_decision_id"],
        ["id"],
    )
    op.create_table(
        "mapping_revisions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("mapping_id", sa.UUID(), nullable=False),
        sa.Column("canonical_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_id", sa.UUID(), nullable=False),
        sa.Column("decision_id", sa.UUID(), nullable=False),
        sa.Column("supersedes_revision_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["decision_id"], ["resolution_decisions.id"]),
        sa.ForeignKeyConstraint(["mapping_id"], ["local_id_mappings.id"]),
        sa.ForeignKeyConstraint(["supersedes_revision_id"], ["mapping_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mapping_revisions_mapping_created",
        "mapping_revisions",
        ["mapping_id", "created_at"],
    )
    op.execute(
        """
        INSERT INTO mapping_revisions
            (mapping_id, canonical_type, canonical_id, decision_id, created_at)
        SELECT mapping.id,
               mapping.canonical_type,
               mapping.canonical_id,
               mapping.decision_id,
               decision.created_at
        FROM local_id_mappings AS mapping
        JOIN resolution_decisions AS decision ON decision.id = mapping.decision_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_mapping_revisions_mapping_created", table_name="mapping_revisions")
    op.drop_table("mapping_revisions")
    op.drop_constraint(
        "fk_resolution_decisions_supersedes",
        "resolution_decisions",
        type_="foreignkey",
    )
    op.drop_column("resolution_decisions", "supersedes_decision_id")
