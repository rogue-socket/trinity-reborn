import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TopicLifecycleTransition(Base):
    __tablename__ = "topic_lifecycle_transitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False)
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=True
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RawPackage(Base):
    __tablename__ = "raw_packages"
    __table_args__ = (
        UniqueConstraint("package_id", "schema_version", "revision"),
        Index("ix_raw_packages_package_schema_checksum", "package_id", "schema_version", "payload_checksum"),
        Index("ix_raw_packages_topic_received", "topic_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TopicAnnotation(Base):
    __tablename__ = "topic_annotations"
    __table_args__ = (Index("ix_topic_annotations_topic_kind", "topic_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RejectedPackage(Base):
    __tablename__ = "rejected_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    schema_version: Mapped[str | None] = mapped_column(String(16))
    topic_key: Mapped[str | None] = mapped_column(String(128))
    payload_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (Index("ix_ingestion_runs_raw_package_id", "raw_package_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    graph_model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    ontology_version: Mapped[str] = mapped_column(String(32), nullable=False)
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceMention(Base):
    __tablename__ = "source_mentions"
    __table_args__ = (UniqueConstraint("raw_package_id", "local_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    local_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ArticleVersion(Base):
    __tablename__ = "article_versions"
    __table_args__ = (
        UniqueConstraint("raw_package_id", "local_id"),
        Index("ix_article_versions_canonical_url", "canonical_url"),
        Index("ix_article_versions_fingerprint", "article_fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    source_mention_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_mentions.id"), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String, nullable=True)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("article_versions.id"), nullable=True
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("article_versions.id"), nullable=True
    )
    article_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_id: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class EvidenceMention(Base):
    __tablename__ = "evidence_mentions"
    __table_args__ = (UniqueConstraint("raw_package_id", "local_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    article_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article_versions.id"), nullable=False)
    local_id: Mapped[str] = mapped_column(String(128), nullable=False)
    excerpt: Mapped[str] = mapped_column(nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (UniqueConstraint("raw_package_id", "local_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    local_id: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class EventMention(Base):
    __tablename__ = "event_mentions"
    __table_args__ = (UniqueConstraint("raw_package_id", "local_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    local_id: Mapped[str] = mapped_column(String(128), nullable=False)
    original_title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_description: Mapped[str | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ClaimMention(Base):
    __tablename__ = "claim_mentions"
    __table_args__ = (UniqueConstraint("raw_package_id", "local_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    local_id: Mapped[str] = mapped_column(String(128), nullable=False)
    original_text: Mapped[str] = mapped_column(nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class RelationshipMention(Base):
    __tablename__ = "relationship_mentions"
    __table_args__ = (UniqueConstraint("raw_package_id", "local_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    local_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class CanonicalEntity(Base):
    __tablename__ = "canonical_entities"
    __table_args__ = (Index("ix_canonical_entities_type_label", "entity_type", "canonical_label"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_label: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    global_eligible: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CanonicalEvent(Base):
    __tablename__ = "canonical_events"
    __table_args__ = (
        Index("ix_canonical_events_topic_type", "topic_id", "event_type"),
        Index("ix_canonical_events_topic_type_title", "topic_id", "event_type", "display_title"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False)
    display_title: Mapped[str] = mapped_column(String(512), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventResolutionContext(Base):
    __tablename__ = "event_resolution_contexts"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_events.id"), primary_key=True
    )
    temporal_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    participant_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    location_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_topic_status", "topic_id", "status"),
        Index("ix_claims_topic_text", "topic_id", "original_text"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False)
    original_text: Mapped[str] = mapped_column(nullable=False)
    epistemic_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    canonical_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("canonical_events.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ClaimAssertion(Base):
    __tablename__ = "claim_assertions"
    __table_args__ = (Index("ix_claim_assertions_subject_predicate", "subject_type", "subject_id", "predicate"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    predicate: Mapped[str] = mapped_column(String(128), nullable=False)
    object_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    temporal_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    derivation_method: Mapped[str] = mapped_column(String(128), nullable=False)
    input_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False)
    processing_version: Mapped[str] = mapped_column(String(32), nullable=False)
    resolution_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resolution_decisions.id"), nullable=True
    )


class ClaimStatusHistory(Base):
    __tablename__ = "claim_status_history"
    __table_args__ = (Index("ix_claim_status_history_claim_effective", "claim_id", "effective_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False)
    ingestion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResolutionDecision(Base):
    __tablename__ = "resolution_decisions"
    __table_args__ = (Index("ix_resolution_decisions_ingestion_type", "ingestion_id", "incoming_type"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingestion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    incoming_type: Mapped[str] = mapped_column(String(32), nullable=False)
    incoming_id: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(nullable=False)
    signals_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    graph_model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    processing_version: Mapped[str] = mapped_column(String(32), nullable=False)
    ontology_version: Mapped[str] = mapped_column(String(32), nullable=False)
    supersedes_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resolution_decisions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LocalIdMapping(Base):
    __tablename__ = "local_id_mappings"
    __table_args__ = (
        UniqueConstraint("raw_package_id", "local_type", "local_id"),
        Index("ix_local_id_mappings_canonical", "canonical_type", "canonical_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)
    local_type: Mapped[str] = mapped_column(String(32), nullable=False)
    local_id: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resolution_decisions.id"), nullable=False)


class MappingRevision(Base):
    __tablename__ = "mapping_revisions"
    __table_args__ = (
        Index("ix_mapping_revisions_mapping_created", "mapping_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mapping_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("local_id_mappings.id"), nullable=False
    )
    canonical_type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resolution_decisions.id"), nullable=False
    )
    supersedes_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mapping_revisions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GraphRelationship(Base):
    __tablename__ = "graph_relationships"
    __table_args__ = (Index("ix_graph_relationships_topic_type_status", "topic_id", "relationship_type", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    temporal_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RelationshipAssertion(Base):
    __tablename__ = "relationship_assertions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    relationship_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("graph_relationships.id"), nullable=False)
    assertion_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    rationale: Mapped[str] = mapped_column(nullable=False)
    derivation_method: Mapped[str] = mapped_column(String(128), nullable=False)
    input_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False)
    processing_version: Mapped[str] = mapped_column(String(32), nullable=False)
    resolution_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resolution_decisions.id"), nullable=True
    )


class RelationshipStatusHistory(Base):
    __tablename__ = "relationship_status_history"
    __table_args__ = (
        Index(
            "ix_relationship_status_history_relationship_effective",
            "relationship_id",
            "effective_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_relationships.id"), nullable=False
    )
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProvenanceLink(Base):
    __tablename__ = "provenance_links"
    __table_args__ = (Index("ix_provenance_links_graph_object", "graph_object_type", "graph_object_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    graph_object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    graph_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_mention_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_mentions.id"))
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"), nullable=True)
    raw_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_packages.id"), nullable=False)


class ConfidenceAssessment(Base):
    __tablename__ = "confidence_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(nullable=False)
    assessed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(128), nullable=False)
    model_or_rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    supporting_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DiscoveryRequest(Base):
    __tablename__ = "discovery_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    requested_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoveredArticleRecord(Base):
    __tablename__ = "discovered_articles"
    __table_args__ = (Index("ix_discovered_articles_request", "discovery_request_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discovery_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_requests.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    published_date: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
