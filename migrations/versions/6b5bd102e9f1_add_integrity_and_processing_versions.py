"""add integrity and processing versions

Revision ID: 6b5bd102e9f1
Revises: 77f47d76953c
Create Date: 2026-07-25 18:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6b5bd102e9f1"
down_revision: Union[str, Sequence[str], None] = "77f47d76953c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column("graph_model_version", sa.String(length=32), nullable=False, server_default="kg-model-0.1"),
    )
    op.add_column(
        "resolution_decisions",
        sa.Column("processing_version", sa.String(length=32), nullable=False, server_default="kg-pipeline-0.1"),
    )
    op.alter_column("ingestion_runs", "graph_model_version", server_default=None)
    op.alter_column("resolution_decisions", "processing_version", server_default=None)

    op.create_unique_constraint(
        "uq_raw_packages_package_schema_revision", "raw_packages", ["package_id", "schema_version", "revision"]
    )
    op.create_index("ix_raw_packages_package_schema_checksum", "raw_packages", ["package_id", "schema_version", "payload_checksum"])
    op.create_index("ix_raw_packages_topic_id", "raw_packages", ["topic_id"])
    op.create_index("ix_ingestion_runs_raw_package_id", "ingestion_runs", ["raw_package_id"])
    op.create_index("ix_canonical_events_topic_type", "canonical_events", ["topic_id", "event_type"])
    op.create_index("ix_claims_topic_status", "claims", ["topic_id", "status"])
    op.create_index("ix_resolution_decisions_ingestion_id", "resolution_decisions", ["ingestion_id"])
    op.create_index("ix_local_id_mappings_canonical", "local_id_mappings", ["canonical_type", "canonical_id"])
    op.create_index("ix_graph_relationships_topic_status", "graph_relationships", ["topic_id", "status"])
    op.create_index("ix_provenance_links_graph_object", "provenance_links", ["graph_object_type", "graph_object_id"])

    op.execute("""
        CREATE FUNCTION prevent_input_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'input packages are immutable';
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in ("raw_packages", "rejected_packages"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_input_mutation()"
        )


def downgrade() -> None:
    for table in ("raw_packages", "rejected_packages"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
    op.execute("DROP FUNCTION prevent_input_mutation()")

    op.drop_index("ix_provenance_links_graph_object", table_name="provenance_links")
    op.drop_index("ix_graph_relationships_topic_status", table_name="graph_relationships")
    op.drop_index("ix_local_id_mappings_canonical", table_name="local_id_mappings")
    op.drop_index("ix_resolution_decisions_ingestion_id", table_name="resolution_decisions")
    op.drop_index("ix_claims_topic_status", table_name="claims")
    op.drop_index("ix_canonical_events_topic_type", table_name="canonical_events")
    op.drop_index("ix_ingestion_runs_raw_package_id", table_name="ingestion_runs")
    op.drop_index("ix_raw_packages_topic_id", table_name="raw_packages")
    op.drop_index("ix_raw_packages_package_schema_checksum", table_name="raw_packages")
    op.drop_constraint("uq_raw_packages_package_schema_revision", "raw_packages", type_="unique")

    op.drop_column("resolution_decisions", "processing_version")
    op.drop_column("ingestion_runs", "graph_model_version")
