"""add claim provenance link

Revision ID: f8a7b6c5d4e3
Revises: e7f6a5b4c3d2
"""
from alembic import op
import sqlalchemy as sa


revision = "f8a7b6c5d4e3"
down_revision = "e7f6a5b4c3d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provenance_links", sa.Column("claim_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_provenance_links_claim",
        "provenance_links",
        "claims",
        ["claim_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_provenance_links_claim", "provenance_links", type_="foreignkey")
    op.drop_column("provenance_links", "claim_id")
