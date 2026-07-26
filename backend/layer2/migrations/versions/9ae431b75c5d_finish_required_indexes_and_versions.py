"""finish required indexes and versions

Revision ID: 9ae431b75c5d
Revises: 7cbb1f4d20a9
"""
from alembic import op
import sqlalchemy as sa

revision = "9ae431b75c5d"
down_revision = "7cbb1f4d20a9"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("ingestion_runs", sa.Column("ontology_version", sa.String(length=32), nullable=False, server_default="kg-ontology-0.1"))
    op.add_column("resolution_decisions", sa.Column("ontology_version", sa.String(length=32), nullable=False, server_default="kg-ontology-0.1"))
    op.alter_column("ingestion_runs", "ontology_version", server_default=None)
    op.alter_column("resolution_decisions", "ontology_version", server_default=None)
    op.drop_index("ix_raw_packages_topic_id", table_name="raw_packages")
    op.create_index("ix_raw_packages_topic_received", "raw_packages", ["topic_id", "received_at"])
    op.drop_index("ix_resolution_decisions_ingestion_id", table_name="resolution_decisions")
    op.create_index("ix_resolution_decisions_ingestion_type", "resolution_decisions", ["ingestion_id", "incoming_type"])
    op.drop_index("ix_graph_relationships_topic_status", table_name="graph_relationships")
    op.create_index("ix_graph_relationships_topic_type_status", "graph_relationships", ["topic_id", "relationship_type", "status"])

def downgrade():
    pass
