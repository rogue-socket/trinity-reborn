"""add reconciliation candidate indexes

Revision ID: ce6ac1db7402
Revises: 6b5bd102e9f1
Create Date: 2026-07-25 19:10:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "ce6ac1db7402"
down_revision: Union[str, Sequence[str], None] = "6b5bd102e9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_canonical_entities_type_label", "canonical_entities", ["entity_type", "canonical_label"])
    op.create_index(
        "ix_canonical_events_topic_type_title",
        "canonical_events",
        ["topic_id", "event_type", "display_title"],
    )
    op.create_index("ix_claims_topic_text", "claims", ["topic_id", "original_text"])
    op.create_index(
        "ix_claim_assertions_subject_predicate",
        "claim_assertions",
        ["subject_type", "subject_id", "predicate"],
    )


def downgrade() -> None:
    op.drop_index("ix_claim_assertions_subject_predicate", table_name="claim_assertions")
    op.drop_index("ix_claims_topic_text", table_name="claims")
    op.drop_index("ix_canonical_events_topic_type_title", table_name="canonical_events")
    op.drop_index("ix_canonical_entities_type_label", table_name="canonical_entities")
