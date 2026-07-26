"""add article fingerprint and duplicates

Revision ID: a9b8c7d6e5f4
Revises: f8a7b6c5d4e3
"""
from alembic import op
import sqlalchemy as sa


revision = "a9b8c7d6e5f4"
down_revision = "f8a7b6c5d4e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "article_versions",
        sa.Column("article_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "article_versions",
        sa.Column("duplicate_of_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_article_versions_duplicate",
        "article_versions",
        "article_versions",
        ["duplicate_of_id"],
        ["id"],
    )
    op.create_index(
        "ix_article_versions_fingerprint",
        "article_versions",
        ["article_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index("ix_article_versions_fingerprint", table_name="article_versions")
    op.drop_constraint(
        "fk_article_versions_duplicate",
        "article_versions",
        type_="foreignkey",
    )
    op.drop_column("article_versions", "duplicate_of_id")
    op.drop_column("article_versions", "article_fingerprint")
