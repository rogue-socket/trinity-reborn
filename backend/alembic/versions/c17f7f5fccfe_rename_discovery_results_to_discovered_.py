"""rename discovery results to discovered articles

Revision ID: c17f7f5fccfe
Revises: 20260725_01
Create Date: 2026-07-25 18:14:58.697987

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c17f7f5fccfe"
down_revision: str | None = "20260725_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("discovery_results", "discovered_articles")
    op.execute(
        "ALTER INDEX ix_discovery_results_discovery_request_id "
        "RENAME TO ix_discovered_articles_discovery_request_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER INDEX ix_discovered_articles_discovery_request_id "
        "RENAME TO ix_discovery_results_discovery_request_id"
    )
    op.rename_table("discovered_articles", "discovery_results")
