"""Layer 1 research functions adapted to the Layer 2 package contract."""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from hashlib import sha256
from collections.abc import Callable, Sequence
from typing import Literal
from urllib.parse import urlencode
from uuid import uuid4

import feedparser
import httpx
import newspaper
import trafilatura
from googlenewsdecoder import gnewsdecoder
from pydantic import BaseModel, Field, ValidationError, model_validator
from rapidfuzz.fuzz import token_sort_ratio


MINIMUM_BODY_LENGTH = 200
SIMILARITY_THRESHOLD = 55
logger = logging.getLogger(__name__)


class DiscoveryError(Exception):
    """Raised when a Google News feed cannot be read."""


class DiscoveredArticle(BaseModel):
    title: str
    publisher: str
    published_date: str | None = None
    url: str


class ExtractedArticle(BaseModel):
    url: str
    canonical_url: str | None = None
    title: str
    publisher: str | None = None
    published_date: str | None = None
    body: str
    extraction_method: Literal["trafilatura", "newspaper4k"]
    success: bool
    error: str | None = None

    @model_validator(mode="after")
    def successful_articles_have_content(self) -> "ExtractedArticle":
        if self.success and not self.body.strip():
            raise ValueError("successful extraction requires article content")
        return self


class ExtractionRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=50)


class ExtractionResponse(BaseModel):
    articles: list[ExtractedArticle]


class DeduplicationRequest(BaseModel):
    articles: list[ExtractedArticle] = Field(min_length=1)


class DeduplicatedArticle(BaseModel):
    url: str
    canonical_url: str | None = None
    title: str
    publisher: str | None = None
    published_date: str | None = None
    body: str
    duplicate_of: str | None = None


class DeduplicationGroup(BaseModel):
    representative: DeduplicatedArticle
    duplicates: list[DeduplicatedArticle]


class DeduplicationResponse(BaseModel):
    groups: list[DeduplicationGroup]


class PackageBuildRequest(BaseModel):
    topic_key: str = Field(min_length=1)
    articles: list[ExtractedArticle] = Field(min_length=1)


class PackageMetadata(BaseModel):
    title: str = Field(min_length=1)
    generated_at: datetime


class Source(BaseModel):
    source_id: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: str | None = None


class Article(BaseModel):
    article_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    canonical_url: str = Field(min_length=1)
    discovery_url: str | None = None
    publisher: str = Field(min_length=1)
    published_at: str | None = None
    content_hash: str = Field(min_length=1)
    content: str = Field(min_length=1)


class Evidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    article_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    language: str | None = None


class Entity(BaseModel):
    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class TemporalScope(BaseModel):
    start: datetime
    precision: Literal["exact", "approximate", "day", "month", "range", "unknown"]
    basis: Literal["reported", "inferred"]
    end: datetime | None = None


class Event(BaseModel):
    event_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str | None = None
    temporal: TemporalScope
    participant_entity_ids: list[str] = Field(default_factory=list)
    location_entity_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    related_claim_ids: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    event_id: str = Field(min_length=1)
    subject_ref: str = Field(min_length=1)
    predicate_candidate: str = Field(min_length=1)
    object_ref_or_value: str = Field(min_length=1)
    temporal_scope: TemporalScope
    asserted_by_entity_id: str | None = None
    epistemic_status: Literal[
        "observed", "reported", "attributed", "corroborated", "disputed",
        "inferred", "interpretive", "unknown", "retracted", "superseded",
    ]


class RelationshipCandidate(BaseModel):
    relationship_id: str = Field(min_length=1)
    subject_ref: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    source_relation_label: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    extraction_confidence: float = Field(ge=0, le=1)


class FactPayload(BaseModel):
    evidence: list[Evidence] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    relationships: list[RelationshipCandidate] = Field(default_factory=list)


class ResearchPackage(BaseModel):
    """The Layer 1 envelope accepted unchanged by ``POST /ingestions``."""

    schema_version: Literal["1.0"] = "1.0"
    package_id: str
    topic_key: str
    metadata: PackageMetadata
    sources: list[Source]
    articles: list[Article]
    evidence: list[Evidence] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    relationships: list[RelationshipCandidate] = Field(default_factory=list)
    timeline: list[dict] = Field(default_factory=list)
    uncertainties: list[dict] = Field(default_factory=list)
    themes: list[dict] = Field(default_factory=list)
    sentiment: list[dict] = Field(default_factory=list)


def google_news_search_url(topic: str) -> str:
    return f"https://news.google.com/rss/search?{urlencode({'q': topic, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})}"


def discover(topic: str, limit: int) -> list[DiscoveredArticle]:
    """Fetch normalized Google News RSS metadata without reading article pages."""
    url = google_news_search_url(topic)
    try:
        response = httpx.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise DiscoveryError(f"could not fetch Google News RSS: {error}") from error
    feed = feedparser.parse(response.content)
    entries = feed.get("entries", [])
    if feed.get("bozo") and not entries:
        raise DiscoveryError(str(feed.get("bozo_exception", "unable to parse feed")))
    return [
        DiscoveredArticle(
            title=entry.get("title", ""),
            publisher=(entry.get("source", {}) or {}).get("title") or entry.get("author", "Unknown"),
            published_date=entry.get("published") or entry.get("updated"),
            url=entry["link"],
        )
        for entry in entries
        if entry.get("link")
    ][:limit]


def _decode_google_news_url(url: str) -> str:
    result = gnewsdecoder(url)
    decoded = result.get("decoded_url") if result.get("status") is True else None
    if not isinstance(decoded, str) or not decoded:
        raise ValueError(result.get("message", "decoder returned no URL"))
    return decoded


def _extract_with_trafilatura(url: str) -> tuple[str, str | None, str | None, str]:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError("could not download URL")
    body = trafilatura.extract(downloaded, include_comments=False)
    if not body:
        raise ValueError("did not return article text")
    metadata = trafilatura.extract_metadata(downloaded)
    return metadata.title or url, metadata.sitename, metadata.date, body


def _extract_with_newspaper(url: str) -> tuple[str, str | None, str | None, str]:
    article = newspaper.Article(url)
    article.download()
    article.parse()
    if not article.text:
        raise ValueError("did not return article text")
    date = article.publish_date.isoformat() if article.publish_date else None
    return article.title or url, article.meta_site_name, date, article.text


def _extract_one(url: str) -> ExtractedArticle:
    canonical_url = url
    if url.startswith("https://news.google.com/rss/articles/"):
        try:
            canonical_url = _decode_google_news_url(url)
        except Exception as error:
            return ExtractedArticle(
                url=url, canonical_url=url, title="", body="", publisher=None,
                extraction_method="trafilatura", success=False, error=f"Google News decode failed: {error}",
            )
    errors: list[str] = []
    extractors: tuple[
        tuple[Literal["trafilatura", "newspaper4k"], Callable[[str], tuple[str, str | None, str | None, str]]],
        ...,
    ] = (("trafilatura", _extract_with_trafilatura), ("newspaper4k", _extract_with_newspaper))
    for method, extractor in extractors:
        try:
            title, publisher, published_date, body = extractor(canonical_url)
            if len(body.strip()) < MINIMUM_BODY_LENGTH:
                errors.append(f"{method} returned fewer than {MINIMUM_BODY_LENGTH} characters")
                continue
            return ExtractedArticle(
                url=url, canonical_url=canonical_url, title=title, publisher=publisher,
                published_date=published_date, body=body, extraction_method=method, success=True,
            )
        except Exception as error:
            errors.append(f"{method} failed: {error}")
    return ExtractedArticle(
        url=url, canonical_url=canonical_url, title="", body="", publisher=None,
        extraction_method="newspaper4k", success=False, error="; ".join(errors),
    )


def _canonical_url(article: ExtractedArticle) -> str:
    return article.canonical_url or article.url


async def extract(urls: list[str]) -> list[ExtractedArticle]:
    """Extract a bounded batch without failing every article on one error."""
    semaphore = asyncio.Semaphore(5)

    async def bounded(url: str) -> ExtractedArticle:
        async with semaphore:
            return await asyncio.to_thread(_extract_one, url)

    return await asyncio.gather(*(bounded(url) for url in urls))


def deduplicate(articles: list[ExtractedArticle]) -> list[DeduplicationGroup]:
    """Group successful articles by title/body similarity without dropping inputs."""
    successful = [article for article in articles if article.success]
    parents = list(range(len(successful)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for first, article in enumerate(successful):
        for second in range(first + 1, len(successful)):
            score = 0.6 * token_sort_ratio(article.title, successful[second].title) + 0.4 * token_sort_ratio(article.body, successful[second].body)
            if score > SIMILARITY_THRESHOLD:
                first_root, second_root = find(first), find(second)
                if first_root != second_root:
                    parents[second_root] = first_root

    groups: dict[int, list[ExtractedArticle]] = {}
    for index, article in enumerate(successful):
        groups.setdefault(find(index), []).append(article)
    result: list[DeduplicationGroup] = []
    for group in groups.values():
        longest_body = max(len(item.body) for item in group)
        close_to_longest = [
            item for item in group if len(item.body) >= longest_body * 0.95
        ]
        representative = min(
            close_to_longest,
            key=lambda item: (
                item.published_date is None,
                item.published_date or "",
                -len(item.body),
                _canonical_url(item),
            ),
        )

        def output(item: ExtractedArticle, duplicate_of: str | None) -> DeduplicatedArticle:
            return DeduplicatedArticle(
                url=item.url,
                canonical_url=item.canonical_url,
                title=item.title,
                publisher=item.publisher,
                published_date=item.published_date,
                body=item.body,
                duplicate_of=duplicate_of,
            )

        result.append(
            DeduplicationGroup(
                representative=output(representative, None),
                duplicates=[
                    output(item, representative.url)
                    for item in group
                    if item is not representative
                ],
            )
        )
    return result


def build_package(request: PackageBuildRequest) -> ResearchPackage:
    """Build an L2-compatible, provenance-complete package from extracted articles."""
    articles = [article for article in request.articles if article.success]
    sources: list[Source] = []
    source_ids: dict[str, str] = {}
    for article in articles:
        publisher = article.publisher or "Unknown publisher"
        if publisher not in source_ids:
            source_id = f"src_{len(sources) + 1:03d}"
            source_ids[publisher] = source_id
            sources.append(
                Source(
                    source_id=source_id,
                    publisher=publisher,
                    url=_canonical_url(article),
                    published_at=article.published_date,
                )
            )
    return ResearchPackage(
        package_id=str(uuid4()),
        topic_key=request.topic_key,
        metadata=PackageMetadata(title=request.topic_key, generated_at=datetime.now(UTC)),
        sources=sources,
        articles=[
            Article(
                article_id=f"art_{index:03d}",
                source_id=source_ids[article.publisher or "Unknown publisher"],
                canonical_url=_canonical_url(article),
                discovery_url=article.url,
                publisher=article.publisher or "Unknown publisher",
                published_at=article.published_date,
                content_hash=sha256(
                    "\n".join(
                        [
                            _canonical_url(article),
                            article.publisher or "Unknown publisher",
                            article.published_date or "",
                            article.body,
                        ]
                    ).encode()
                ).hexdigest(),
                content=article.body,
            )
            for index, article in enumerate(articles, start=1)
        ],
    )


class PackageValidationError(ValueError):
    """Raised when Layer 1 cannot produce a package Layer 2 will accept."""

    def __init__(self, report: dict) -> None:
        super().__init__("Layer 1 package contains rejected objects")
        self.report = report


def _fact_prompt(article: Article) -> str:
    return f"""Extract only evidence-backed facts from this article. Return JSON with
entities, events, claims, evidence, and relationships arrays. Entities must have
entity_id, name, type, aliases, and evidence_ids. Events must have event_id, type,
title, description, temporal, participant_entity_ids, location_entity_ids,
evidence_ids, and related_claim_ids. Claims must have claim_id, text, evidence_ids,
event_id, subject_ref, predicate_candidate, object_ref_or_value, temporal_scope,
asserted_by_entity_id, and epistemic_status. Evidence must cite article_id
{article.article_id!r} and use exact offsets. Do not infer or invent facts.

ARTICLE CONTENT:
{article.content}"""


def _skipped(kind: str, local_id: str, reason: str) -> None:
    logger.warning("Layer 1 skipped %s %r: %s", kind, local_id, reason)


def _normalize_facts(article: Article, payload: dict, sequence: int) -> FactPayload:
    """Validate one model response and give its local IDs package-wide names.

    A malformed response is still rejected outright, but an individual fact that cites
    something the model never extracted is dropped on its own so the rest of the
    article's facts survive.
    """
    adjusted_payload = dict(payload)
    adjusted_payload["entities"] = [
        {**item, "name": item.get("name", item.get("label"))}
        for item in payload.get("entities", [])
        if isinstance(item, dict)
    ]
    facts = FactPayload.model_validate(adjusted_payload)
    evidence = facts.evidence
    entities = facts.entities
    events = facts.events
    claims = facts.claims
    relationships = facts.relationships
    prefix = f"{sequence:03d}"

    def ids(items: Sequence[BaseModel], field: str, kind: str) -> dict[str, str]:
        """Map each unambiguous local ID to a package-wide name.

        A duplicated ID is left out entirely, so every object claiming it is skipped
        below rather than being silently merged into whichever one came last.
        """
        raw = [getattr(item, field) for item in items]
        duplicated = {value for value in raw if raw.count(value) > 1}
        return {
            value: f"{kind}_{prefix}_{index:03d}"
            for index, value in enumerate(raw, start=1)
            if value not in duplicated
        }

    evidence_ids = ids(evidence, "evidence_id", "ev")
    entity_ids = ids(entities, "entity_id", "ent")
    event_ids = ids(events, "event_id", "evt")
    claim_ids = ids(claims, "claim_id", "clm")
    relationship_ids = ids(relationships, "relationship_id", "rel")
    reference_ids = entity_ids | event_ids | claim_ids

    normalized_evidence: list[Evidence] = []
    surviving_evidence_ids: dict[str, str] = {}
    for item in evidence:
        if item.evidence_id not in evidence_ids:
            continue
        if item.article_id != article.article_id:
            _skipped("evidence", item.evidence_id, "cites another article")
            continue
        if item.end_offset < item.start_offset or item.end_offset > len(article.content):
            _skipped("evidence", item.evidence_id, "offsets are outside the article content")
            continue
        if article.content[item.start_offset:item.end_offset] != item.excerpt:
            _skipped("evidence", item.evidence_id, "offsets do not select the excerpt")
            continue
        surviving_evidence_ids[item.evidence_id] = evidence_ids[item.evidence_id]
        normalized_evidence.append(
            item.model_copy(update={"evidence_id": evidence_ids[item.evidence_id]})
        )
    evidence_ids = surviving_evidence_ids

    def remap(values: list[str], mapping: dict[str, str]) -> list[str]:
        """Keep the references that survived normalization and drop the rest."""
        return [mapping[value] for value in values if value in mapping]

    normalized_entities: list[Entity] = []
    for item in entities:
        if item.entity_id not in entity_ids:
            continue
        normalized_entities.append(
            item.model_copy(
                update={
                    "entity_id": entity_ids[item.entity_id],
                    "evidence_ids": remap(item.evidence_ids, evidence_ids),
                }
            )
        )

    normalized_events: list[Event] = []
    for item in events:
        if item.event_id not in event_ids:
            continue
        normalized_events.append(
            item.model_copy(
                update={
                    "event_id": event_ids[item.event_id],
                    "participant_entity_ids": remap(item.participant_entity_ids, entity_ids),
                    "location_entity_ids": remap(item.location_entity_ids, entity_ids),
                    "evidence_ids": remap(item.evidence_ids, evidence_ids),
                    "related_claim_ids": remap(item.related_claim_ids, claim_ids),
                }
            )
        )

    normalized_claims: list[Claim] = []
    for item in claims:
        if item.claim_id not in claim_ids:
            continue
        asserted_by = item.asserted_by_entity_id
        if item.event_id not in event_ids or item.subject_ref not in reference_ids:
            _skipped("claim", item.claim_id, "cites an event or subject that was not extracted")
            continue
        if asserted_by is not None and asserted_by not in entity_ids:
            _skipped("claim", item.claim_id, "attributes the claim to an entity that was not extracted")
            continue
        normalized_claims.append(
            item.model_copy(
                update={
                    "claim_id": claim_ids[item.claim_id],
                    "event_id": event_ids[item.event_id],
                    "subject_ref": reference_ids[item.subject_ref],
                    "object_ref_or_value": reference_ids.get(
                        item.object_ref_or_value, item.object_ref_or_value
                    ),
                    "asserted_by_entity_id": entity_ids[asserted_by] if asserted_by is not None else None,
                    "evidence_ids": remap(item.evidence_ids, evidence_ids),
                }
            )
        )

    normalized_relationships: list[RelationshipCandidate] = []
    for item in relationships:
        if item.relationship_id not in relationship_ids:
            continue
        if item.subject_ref not in reference_ids or item.object_ref not in reference_ids:
            _skipped("relationship", item.relationship_id, "links an object that was not extracted")
            continue
        normalized_relationships.append(
            item.model_copy(
                update={
                    "relationship_id": relationship_ids[item.relationship_id],
                    "subject_ref": reference_ids[item.subject_ref],
                    "object_ref": reference_ids[item.object_ref],
                    "evidence_ids": remap(item.evidence_ids, evidence_ids),
                }
            )
        )
    return FactPayload(
        evidence=normalized_evidence,
        entities=normalized_entities,
        events=normalized_events,
        claims=normalized_claims,
        relationships=normalized_relationships,
    )


def _validate_for_delivery(package: ResearchPackage) -> ResearchPackage:
    """Deliver everything Layer 2 would accept, dropping only the objects it would reject.

    ``validate_objects`` already rejects dependents of a rejected object, so filtering on
    its report cannot leave a dangling reference behind.
    """
    from app.services.validation import LOCAL_TYPES, REQUIRED_FIELDS, validate_objects

    result = validate_objects(package.model_dump(mode="json"))
    rejected = {
        (item["local_type"], item["local_id"])
        for item in result.report["object_results"]
        if item["status"] == "rejected"
    }
    if not rejected:
        return package
    if result.status == "rejected":
        raise PackageValidationError(result.report)
    retained = {}
    for collection, required_fields in REQUIRED_FIELDS.items():
        local_type, id_field = LOCAL_TYPES[collection], required_fields[0]
        retained[collection] = [
            item
            for item in getattr(package, collection)
            if (local_type, getattr(item, id_field, None)) not in rejected
        ]
    logger.warning(
        "Layer 1 dropped %d object(s) Layer 2 would reject: %s",
        len(rejected),
        sorted(f"{local_type}:{local_id}" for local_type, local_id in rejected),
    )
    return package.model_copy(update=retained)


async def build_full_package(
    request: PackageBuildRequest,
    fact_generator: Callable[[Article], dict | None] | None = None,
) -> ResearchPackage:
    """Build a package, adding validated Gemini facts only when explicitly configured."""
    package = build_package(request)
    api_key = os.getenv("GEMINI_API_KEY")
    if not package.articles:
        return _validate_for_delivery(package)
    if fact_generator is None and not api_key:
        return _validate_for_delivery(package)

    if fact_generator is None:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        def fact_generator(article: Article) -> dict | None:
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=_fact_prompt(article),
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                return json.loads(response.text or "{}")
            except Exception:
                logger.exception(
                    "Layer 1 fact extraction failed for article_id=%s", article.article_id
                )
                return None

    representatives = {
        group.representative.url for group in deduplicate(request.articles)
    }
    fact_articles = [
        article for article in package.articles if article.discovery_url in representatives
    ]
    semaphore = asyncio.Semaphore(3)

    async def generate(article: Article) -> dict | None:
        async with semaphore:
            return await asyncio.to_thread(fact_generator, article)

    payloads = await asyncio.gather(*(generate(article) for article in fact_articles))
    facts = FactPayload()
    for sequence, (article, payload) in enumerate(zip(fact_articles, payloads, strict=True), start=1):
        if payload is None:
            continue
        try:
            normalized = _normalize_facts(article, payload, sequence)
        except (ValidationError, ValueError) as error:
            logger.warning(
                "Layer 1 fact output was invalid for article_id=%s: %s",
                article.article_id,
                error,
            )
            continue
        facts.evidence.extend(normalized.evidence)
        facts.entities.extend(normalized.entities)
        facts.events.extend(normalized.events)
        facts.claims.extend(normalized.claims)
        facts.relationships.extend(normalized.relationships)
    return _validate_for_delivery(
        package.model_copy(
            update={
                "evidence": facts.evidence,
                "entities": facts.entities,
                "events": facts.events,
                "claims": facts.claims,
                "relationships": facts.relationships,
            }
        )
    )
