"""rename discovered article headline to title

Revision ID: 34fc83b69468
Revises: c17f7f5fccfe
Create Date: 2026-07-25 19:04:51.912318

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '34fc83b69468'
down_revision: str | Sequence[str] | None = 'c17f7f5fccfe'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("discovered_articles", "headline", new_column_name="title")


def downgrade() -> None:
    op.alter_column("discovered_articles", "title", new_column_name="headline")
