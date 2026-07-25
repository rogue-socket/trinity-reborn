"""Gemini-backed, evidence-constrained information extraction."""

import asyncio
import logging
from dataclasses import dataclass

import google.generativeai as genai
from pydantic import BaseModel

from app.core.config import get_settings
from app.schemas.package import (
    Article,
    Claim,
    Entity,
    Event,
    Evidence,
    RelationshipCandidate,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "gemini-2.0-flash"
MAX_CONCURRENT_EXTRACTIONS = 3


class GeminiConfigurationError(RuntimeError):
    """Raised when Gemini-backed extraction is enabled without an API key."""


class ExtractionResult(BaseModel):
    """Validated facts extracted across a batch of package articles."""

    entities: list[Entity]
    events: list[Event]
    claims: list[Claim]
    evidence: list[Evidence]
    relationships: list[RelationshipCandidate]


class _ArticleExtractionPayload(BaseModel):
    """Model output before package-local identifiers are normalized."""

    entities: list[Entity]
    events: list[Event]
    claims: list[Claim]
    evidence: list[Evidence]
    relationships: list[RelationshipCandidate]


@dataclass(slots=True)
class _IdAllocator:
    """Allocate collision-free package-local identifiers by object type."""

    entity: int = 0
    event: int = 0
    claim: int = 0
    evidence: int = 0
    relationship: int = 0

    def next_entity_id(self) -> str:
        """Return the next package-local entity ID."""
        self.entity += 1
        return f"ent_{self.entity:03d}"

    def next_event_id(self) -> str:
        """Return the next package-local event ID."""
        self.event += 1
        return f"evt_{self.event:03d}"

    def next_claim_id(self) -> str:
        """Return the next package-local claim ID."""
        self.claim += 1
        return f"clm_{self.claim:03d}"

    def next_evidence_id(self) -> str:
        """Return the next package-local evidence ID."""
        self.evidence += 1
        return f"ev_{self.evidence:03d}"

    def next_relationship_id(self) -> str:
        """Return the next package-local relationship ID."""
        self.relationship += 1
        return f"rel_{self.relationship:03d}"


class InfoExtractionService:
    """Extract only evidence-backed facts from package articles with Gemini."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        """Configure the Gemini client and fail early when its key is absent."""
        settings = get_settings()
        if not settings.gemini_api_key:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY must be configured before starting info extraction."
            )

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(model_name)

    async def extract(self, articles: list[Article]) -> ExtractionResult:
        """Extract validated, evidence-backed facts without aborting the batch."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)
        article_payloads = await asyncio.gather(
            *(self._extract_article(article, semaphore) for article in articles)
        )

        allocator = _IdAllocator()
        result = ExtractionResult(
            entities=[], events=[], claims=[], evidence=[], relationships=[]
        )
        for article, payload in zip(articles, article_payloads, strict=True):
            if payload is None:
                continue
            self._append_with_package_ids(result, article, payload, allocator)

        logger.info(
            "Information extraction complete: articles=%d entities=%d events=%d "
            "claims=%d evidence=%d relationships=%d",
            len(articles),
            len(result.entities),
            len(result.events),
            len(result.claims),
            len(result.evidence),
            len(result.relationships),
        )
        return result

    async def _extract_article(
        self, article: Article, semaphore: asyncio.Semaphore
    ) -> _ArticleExtractionPayload | None:
        """Call Gemini for one article and discard invalid model output safely."""
        try:
            async with semaphore:
                response_text = await asyncio.to_thread(
                    self._generate_json, self._build_prompt(article)
                )
            payload = _ArticleExtractionPayload.model_validate_json(response_text)
            self._validate_evidence(article, payload.evidence)
            self._validate_references(payload)
        except Exception:
            logger.exception(
                "Information extraction failed: article_id=%s", article.article_id
            )
            return None

        logger.info(
            "Information extraction succeeded: article_id=%s", article.article_id
        )
        return payload

    def _generate_json(self, prompt: str) -> str:
        """Request JSON-only output from Gemini's structured-response mode."""
        response = self._model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            ),
        )
        return response.text

    @staticmethod
    def _build_prompt(article: Article) -> str:
        """Build a strict fact-extraction prompt for one immutable article."""
        return f"""Extract facts only from the article below. Do not infer, summarize,
speculate, add thematic or emotional analysis, or invent relationships. Return only
valid JSON with exactly these arrays: entities, events, claims, evidence, relationships.

Use temporary IDs consistently within this response (for example ent_local_1,
evt_local_1, clm_local_1, ev_local_1, rel_local_1); package-local IDs are assigned
after validation. Each entity has entity_id, label, type, aliases, evidence_ids.
Each event has event_id, type, title, description, temporal (start, precision, basis),
participant_entity_ids, location_entity_ids, evidence_ids, related_claim_ids. Each
claim has claim_id, text, evidence_ids, event_id, subject_ref, predicate_candidate,
object_ref_or_value, temporal_scope (start, precision, basis), asserted_by_entity_id,
epistemic_status. Each relationship has relationship_id, subject_ref, object_ref,
source_relation_label, evidence_ids, extraction_confidence. Each evidence item has
evidence_id, article_id, excerpt, start_offset, end_offset, language.

Every event and claim must cite evidence_ids. Every evidence item must use article_id
{article.article_id!r}; its offsets must select exactly its excerpt from the content.
If no supported facts exist, return all arrays empty.

ARTICLE CONTENT:
{article.content}"""

    @staticmethod
    def _validate_evidence(article: Article, evidence: list[Evidence]) -> None:
        """Ensure evidence refers to this article and exact immutable substrings."""
        for item in evidence:
            if item.article_id != article.article_id:
                raise ValueError(
                    "evidence article_id does not match the source article"
                )
            if not 0 <= item.start_offset <= item.end_offset <= len(article.content):
                raise ValueError("evidence offsets are outside article content")
            if article.content[item.start_offset : item.end_offset] != item.excerpt:
                raise ValueError("evidence excerpt does not match article content")

    @staticmethod
    def _validate_references(payload: _ArticleExtractionPayload) -> None:
        """Reject model output whose local references are not self-contained."""
        entity_ids = {entity.entity_id for entity in payload.entities}
        event_ids = {event.event_id for event in payload.events}
        claim_ids = {claim.claim_id for claim in payload.claims}
        evidence_ids = {evidence.evidence_id for evidence in payload.evidence}
        all_ids = entity_ids | event_ids | claim_ids

        for entity in payload.entities:
            if not set(entity.evidence_ids) <= evidence_ids:
                raise ValueError("entity references unknown evidence")
        for event in payload.events:
            if not set(event.participant_entity_ids) <= entity_ids:
                raise ValueError("event references unknown participants")
            if not set(event.location_entity_ids) <= entity_ids:
                raise ValueError("event references unknown locations")
            if not set(event.evidence_ids) <= evidence_ids:
                raise ValueError("event references unknown evidence")
            if not set(event.related_claim_ids) <= claim_ids:
                raise ValueError("event references unknown claims")
        for claim in payload.claims:
            if claim.event_id not in event_ids:
                raise ValueError("claim references an unknown event")
            if claim.subject_ref not in entity_ids:
                raise ValueError("claim references an unknown subject")
            if not set(claim.evidence_ids) <= evidence_ids:
                raise ValueError("claim references unknown evidence")
            if (
                claim.asserted_by_entity_id is not None
                and claim.asserted_by_entity_id not in entity_ids
            ):
                raise ValueError("claim references an unknown asserting entity")
        for relationship in payload.relationships:
            if relationship.subject_ref not in all_ids:
                raise ValueError("relationship references an unknown subject")
            if relationship.object_ref not in all_ids:
                raise ValueError("relationship references an unknown object")
            if not set(relationship.evidence_ids) <= evidence_ids:
                raise ValueError("relationship references unknown evidence")

    @staticmethod
    def _append_with_package_ids(
        result: ExtractionResult,
        article: Article,
        payload: _ArticleExtractionPayload,
        allocator: _IdAllocator,
    ) -> None:
        """Remap one article's temporary identifiers into package-local IDs."""
        entity_id_map = {
            entity.entity_id: allocator.next_entity_id() for entity in payload.entities
        }
        event_id_map = {
            event.event_id: allocator.next_event_id() for event in payload.events
        }
        claim_id_map = {
            claim.claim_id: allocator.next_claim_id() for claim in payload.claims
        }
        evidence_id_map = {
            evidence.evidence_id: allocator.next_evidence_id()
            for evidence in payload.evidence
        }
        relationship_id_map = {
            relationship.relationship_id: allocator.next_relationship_id()
            for relationship in payload.relationships
        }
        reference_map = entity_id_map | event_id_map | claim_id_map

        result.evidence.extend(
            evidence.model_copy(
                update={
                    "evidence_id": evidence_id_map[evidence.evidence_id],
                    "article_id": article.article_id,
                }
            )
            for evidence in payload.evidence
        )
        result.entities.extend(
            entity.model_copy(
                update={
                    "entity_id": entity_id_map[entity.entity_id],
                    "evidence_ids": [
                        evidence_id_map[evidence_id]
                        for evidence_id in entity.evidence_ids
                    ],
                }
            )
            for entity in payload.entities
        )
        result.events.extend(
            event.model_copy(
                update={
                    "event_id": event_id_map[event.event_id],
                    "participant_entity_ids": [
                        entity_id_map[entity_id]
                        for entity_id in event.participant_entity_ids
                    ],
                    "location_entity_ids": [
                        entity_id_map[entity_id]
                        for entity_id in event.location_entity_ids
                    ],
                    "evidence_ids": [
                        evidence_id_map[evidence_id]
                        for evidence_id in event.evidence_ids
                    ],
                    "related_claim_ids": [
                        claim_id_map[claim_id] for claim_id in event.related_claim_ids
                    ],
                }
            )
            for event in payload.events
        )
        result.claims.extend(
            claim.model_copy(
                update={
                    "claim_id": claim_id_map[claim.claim_id],
                    "evidence_ids": [
                        evidence_id_map[evidence_id]
                        for evidence_id in claim.evidence_ids
                    ],
                    "event_id": event_id_map[claim.event_id],
                    "subject_ref": entity_id_map[claim.subject_ref],
                    "object_ref_or_value": reference_map.get(
                        claim.object_ref_or_value, claim.object_ref_or_value
                    ),
                    "asserted_by_entity_id": (
                        entity_id_map[claim.asserted_by_entity_id]
                        if claim.asserted_by_entity_id is not None
                        else None
                    ),
                }
            )
            for claim in payload.claims
        )
        result.relationships.extend(
            relationship.model_copy(
                update={
                    "relationship_id": relationship_id_map[
                        relationship.relationship_id
                    ],
                    "subject_ref": reference_map[relationship.subject_ref],
                    "object_ref": reference_map[relationship.object_ref],
                    "evidence_ids": [
                        evidence_id_map[evidence_id]
                        for evidence_id in relationship.evidence_ids
                    ],
                }
            )
            for relationship in payload.relationships
        )
