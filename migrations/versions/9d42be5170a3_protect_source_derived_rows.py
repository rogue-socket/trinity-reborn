"""protect source derived rows

Revision ID: 9d42be5170a3
Revises: 1a7fdbd3c310
Create Date: 2026-07-25 19:40:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "9d42be5170a3"
down_revision: Union[str, Sequence[str], None] = "1a7fdbd3c310"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (
    "source_mentions",
    "article_versions",
    "evidence_mentions",
    "entity_mentions",
    "event_mentions",
    "claim_mentions",
    "relationship_mentions",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_input_mutation()"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
