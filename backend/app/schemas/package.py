"""Layer 1 research-package schemas for Layer 2 ingestion."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.extraction import ExtractedArticle

EntityType = Literal[
    "person",
    "organization",
    "government_body",
    "government_agency",
    "military_unit",
    "armed_group",
    "political_party",
    "community_group",
    "media_outlet",
    "international_organization",
    "country",
    "administrative_region",
    "city_or_locality",
    "neighborhood",
    "geographic_feature",
    "facility_or_site",
    "border_or_route",
    "document",
    "law_or_policy",
    "court_case",
    "agreement",
    "infrastructure",
    "vehicle_or_equipment",
    "weapon_system",
    "digital_account_or_channel",
    "unknown",
]
EpistemicStatus = Literal[
    "observed",
    "reported",
    "attributed",
    "corroborated",
    "disputed",
    "inferred",
    "interpretive",
    "unknown",
    "retracted",
    "superseded",
]


class PackageMetadata(BaseModel):
    """Human-readable metadata for one Layer 1 delivery."""

    title: str
    generated_at: str


class Source(BaseModel):
    """Source metadata retained for Layer 2 provenance."""

    source_id: str
    publisher: str
    url: str
    published_at: str | None = None


class Article(BaseModel):
    """Immutable article text and the inputs used for its fingerprint."""

    article_id: str
    source_id: str
    canonical_url: str
    publisher: str
    published_at: str | None = None
    content_hash: str
    content: str
    language: str | None = None


class Evidence(BaseModel):
    """An exact supporting excerpt from an article's immutable content."""

    evidence_id: str
    article_id: str
    excerpt: str
    start_offset: int
    end_offset: int
    language: str


class Entity(BaseModel):
    """A package-local source-derived entity candidate."""

    entity_id: str
    label: str
    type: EntityType
    aliases: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class TemporalScope(BaseModel):
    """Source-derived temporal information and its stated precision."""

    start: str
    precision: str
    basis: str


class Event(BaseModel):
    """A package-local bounded happening or state change."""

    event_id: str
    type: str
    title: str
    description: str
    temporal: TemporalScope
    participant_entity_ids: list[str]
    location_entity_ids: list[str]
    evidence_ids: list[str]
    related_claim_ids: list[str]


class Claim(BaseModel):
    """An evidence-backed source-derived claim and extraction hints."""

    claim_id: str
    text: str
    evidence_ids: list[str]
    event_id: str
    subject_ref: str
    predicate_candidate: str
    object_ref_or_value: str
    temporal_scope: TemporalScope
    asserted_by_entity_id: str | None
    epistemic_status: EpistemicStatus


class RelationshipCandidate(BaseModel):
    """A source-derived relationship candidate for Layer 2 normalization."""

    relationship_id: str
    subject_ref: str
    object_ref: str
    source_relation_label: str
    evidence_ids: list[str]
    extraction_confidence: float


class ResearchPackage(BaseModel):
    """The complete Layer 1 delta envelope consumed by Layer 2."""

    schema_version: Literal["1.0"]
    package_id: str
    topic_key: str
    metadata: PackageMetadata
    sources: list[Source]
    articles: list[Article]
    evidence: list[Evidence]
    entities: list[Entity]
    events: list[Event]
    claims: list[Claim]
    relationships: list[RelationshipCandidate] = Field(default_factory=list)
    timeline: list[object] = Field(default_factory=list)
    uncertainties: list[object] = Field(default_factory=list)
    themes: list[object] = Field(default_factory=list)
    sentiment: list[object] = Field(default_factory=list)


class PackageBuildRequest(BaseModel):
    """Extracted articles to deduplicate and assemble into a research package."""

    topic_key: str
    articles: list[ExtractedArticle]
