"""add article version lineage

Revision ID: ef5a9c0321d4
Revises: 9d42be5170a3
Create Date: 2026-07-25 19:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ef5a9c0321d4"
down_revision: Union[str, Sequence[str], None] = "9d42be5170a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("article_versions", sa.Column("canonical_url", sa.String(), nullable=True))
    op.add_column("article_versions", sa.Column("previous_version_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_article_versions_previous_version", "article_versions", "article_versions", ["previous_version_id"], ["id"])
    op.create_index("ix_article_versions_canonical_url", "article_versions", ["canonical_url"])

def downgrade() -> None:
    op.drop_index("ix_article_versions_canonical_url", table_name="article_versions")
    op.drop_constraint("fk_article_versions_previous_version", "article_versions", type_="foreignkey")
    op.drop_column("article_versions", "previous_version_id")
    op.drop_column("article_versions", "canonical_url")
