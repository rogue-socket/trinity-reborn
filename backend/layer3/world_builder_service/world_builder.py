"""Layer 2 retrieval, fictionalization, validation, and durable world-bible storage."""

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import status
from openai import APIConnectionError, APIError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import ValidationError

from backend.shared.artifact_paths import atomic_write_text

from .config import LAYER2_BASE_URL, OPENAI_MODEL, WORLD_BIBLE_DIR
from .contracts import (
    BuildWorldResponse,
    Character,
    Characters,
    EntityMapEntry,
    GenerationPayload,
    Role,
    World,
)


CHARACTER_ENTITY_TYPES = {
    "person",
    "organization",
    "government_body",
    "government_agency",
    "political_party",
    "community_group",
    "media_outlet",
}
REQUIRED_CONTEXT_FIELDS = {"entities", "events", "claims", "disputes"}


class WorldBuilderError(Exception):
    def __init__(self, status_code: int, error: str, message: str) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


def fetch_context(topic_id: str) -> dict[str, Any]:
    url = f"{LAYER2_BASE_URL}/topics/{topic_id}/context"
    try:
        response = httpx.get(url, timeout=15.0)
    except httpx.HTTPError as exc:
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "layer2_unavailable",
            f"Could not reach Layer 2 at {LAYER2_BASE_URL}: {exc}",
        ) from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise WorldBuilderError(
            status.HTTP_404_NOT_FOUND,
            "topic_not_found",
            f"Layer 2 does not contain topic_id '{topic_id}'",
        )
    if not response.is_success:
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "layer2_error",
            f"Layer 2 returned HTTP {response.status_code} while fetching topic context",
        )
    try:
        context = response.json()
    except ValueError as exc:
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 returned a non-JSON context response",
        ) from exc

    if not isinstance(context, dict):
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 context must be a JSON object",
        )
    missing = sorted(field for field in REQUIRED_CONTEXT_FIELDS if field not in context)
    if missing:
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            f"Layer 2 context is missing required fields: {', '.join(missing)}",
        )
    if any(not isinstance(context[field], list) for field in REQUIRED_CONTEXT_FIELDS):
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 context has invalid collection fields",
        )
    if any(not isinstance(item, dict) for field in REQUIRED_CONTEXT_FIELDS for item in context[field]):
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 context collections must contain JSON objects",
        )
    if "topic" in context and not isinstance(context["topic"], dict):
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 context has an invalid topic object",
        )
    return context


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorldBuilderError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "invalid_world_bible",
            f"Could not read valid JSON from {path}",
        ) from exc


def load_existing_world(topic_id: str) -> tuple[World | None, Characters | None]:
    directory = WORLD_BIBLE_DIR / topic_id
    world_path = directory / "world.json"
    if not world_path.exists():
        return None, None
    try:
        world = World.model_validate(_load_json(world_path))
        if world.topic_id != topic_id:
            raise ValueError("world topic_id does not match its directory")
        character_path = directory / "characters.json"
        characters = Characters.model_validate(_load_json(character_path)) if character_path.exists() else Characters({})
        return world, characters
    except (ValidationError, ValueError) as exc:
        raise WorldBuilderError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "invalid_world_bible",
            f"Existing world bible for topic_id '{topic_id}' does not match the required schema",
        ) from exc


def _eligible_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entity for entity in entities if entity.get("type") in CHARACTER_ENTITY_TYPES and entity.get("entity_id")]


def calculate_roles(context: dict[str, Any], eligible_entities: list[dict[str, Any]]) -> dict[str, Role]:
    """Deterministically assign the contract's protagonist/antagonist/supporting roles."""
    eligible_ids = {entity["entity_id"] for entity in eligible_entities}
    if not eligible_ids:
        return {}
    claim_counts = Counter(
        claim.get("subject_ref") for claim in context["claims"] if claim.get("subject_ref") in eligible_ids
    )
    protagonist = min(eligible_ids, key=lambda entity_id: (-claim_counts[entity_id], entity_id))
    roles: dict[str, Role] = {entity_id: "supporting" for entity_id in eligible_ids}
    roles[protagonist] = "protagonist"

    disputed_claim_subjects = {
        claim.get("subject_ref")
        for claim in context["claims"]
        if claim.get("claim_id")
        in {claim_id for dispute in context["disputes"] for claim_id in dispute.get("related_claim_ids", [])}
    }
    opposition_counts: Counter[str] = Counter()
    for dispute in context["disputes"]:
        related = set(dispute.get("related_entity_ids", []))
        if protagonist in related:
            for entity_id in related & eligible_ids - {protagonist}:
                opposition_counts[entity_id] += 1
                if entity_id in disputed_claim_subjects:
                    opposition_counts[entity_id] += 1
    if opposition_counts:
        antagonist = min(
            opposition_counts,
            key=lambda entity_id: (-opposition_counts[entity_id], -claim_counts[entity_id], entity_id),
        )
        roles[antagonist] = "antagonist"
    return roles


def _model_input(context: dict[str, Any], entities_for_map: list[dict[str, Any]], characters_to_add: list[dict[str, Any]], roles: dict[str, Role]) -> str:
    """Deliberately exclude topic metadata and source labels from the prompt."""
    entity_descriptors = [
        {"entity_id": item["entity_id"], "source_type": item.get("type")}
        for item in entities_for_map
    ]
    character_descriptors = [
        {
            "source_entity_id": item["entity_id"],
            "source_type": item.get("type"),
            "assigned_role": roles[item["entity_id"]],
        }
        for item in characters_to_add
    ]
    # Events, claims, and disputes provide story pressure without exposing source wording, labels, or topic metadata.
    event_signals = []
    for event in context["events"]:
        temporal = event.get("temporal")
        event_signals.append(
            {"type": event.get("type"), "temporal_precision": temporal.get("precision") if isinstance(temporal, dict) else None}
        )
    story_signals = {
        "events": event_signals,
        "claims": [
            {"event_id": claim.get("event_id"), "epistemic_status": claim.get("epistemic_status")}
            for claim in context["claims"]
        ],
        "disputes": [{"has_related_claims": bool(dispute.get("related_claim_ids"))} for dispute in context["disputes"]],
    }
    return json.dumps(
        {
            "entities_to_fictionalize": entity_descriptors,
            "characters_to_create": character_descriptors,
            "story_signals": story_signals,
        },
        ensure_ascii=False,
    )


def _is_transient_openai_error(exc: APIError) -> bool:
    return isinstance(exc, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)) or (
        getattr(exc, "status_code", 0) is not None and getattr(exc, "status_code", 0) >= 500
    )


def generate_fictional_content(context: dict[str, Any], entities_for_map: list[dict[str, Any]], characters_to_add: list[dict[str, Any]], roles: dict[str, Role]) -> GenerationPayload:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise WorldBuilderError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "openai_not_configured",
            "OPENAI_API_KEY is required to build a world",
        )

    client = OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None)
    prompt = _model_input(context, entities_for_map, characters_to_add, roles)
    system_prompt = (
        "You are the Echoes world builder. Create wholly fictional setting and character details from abstract story signals. "
        "Never repeat, mention, infer, or allude to the source topic's name, key, display name, place names, institutions, "
        "people, or labels. Do not use any entity label because it has intentionally not been supplied. "
        "Return JSON only in the supplied schema. Create exactly one entity_map entry and character entry for every requested "
        "source_entity_id; use each "
        "character's assigned role as narrative guidance. All place-like or other non-character entities must be fictional_type 'place'."
    )
    for attempt in range(3):
        try:
            completion = client.chat.completions.parse(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format=GenerationPayload,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                raise WorldBuilderError(
                    status.HTTP_502_BAD_GATEWAY,
                    "invalid_openai_response",
                    "OpenAI did not return a schema-valid world-building response",
                )
            return parsed
        except APIError as exc:
            if attempt < 2 and _is_transient_openai_error(exc):
                time.sleep(2**attempt)
                continue
            raise WorldBuilderError(
                status.HTTP_502_BAD_GATEWAY,
                "openai_generation_failed",
                f"OpenAI could not generate the world: {exc}",
            ) from exc
        except ValidationError as exc:
            raise WorldBuilderError(
                status.HTTP_502_BAD_GATEWAY,
                "invalid_openai_response",
                "OpenAI returned content that failed world-builder schema validation",
            ) from exc
        except WorldBuilderError:
            raise
        except Exception as exc:
            raise WorldBuilderError(
                status.HTTP_502_BAD_GATEWAY,
                "invalid_openai_response",
                "OpenAI returned an unreadable world-building response",
            ) from exc
    raise AssertionError("retry loop should always return or raise")


def _by_source_id(items: list[Any]) -> dict[str, Any]:
    return {item.source_entity_id: item for item in items}


def _validate_generated_keys(
    generated: GenerationPayload, expected_map_ids: set[str], expected_character_ids: set[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    entity_map_by_source = _by_source_id(generated.entity_map)
    characters_by_source = _by_source_id(generated.characters)
    if (
        len(entity_map_by_source) != len(generated.entity_map)
        or len(characters_by_source) != len(generated.characters)
        or set(entity_map_by_source) != expected_map_ids
        or set(characters_by_source) != expected_character_ids
    ):
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "invalid_openai_response",
            "OpenAI response did not contain exactly the requested entity and character entries",
        )
    return entity_map_by_source, characters_by_source


def _validate_place_mappings(entities: list[dict[str, Any]], entity_map_by_source: dict[str, Any]) -> None:
    for entity in entities:
        if entity.get("type") not in CHARACTER_ENTITY_TYPES and entity_map_by_source[entity["entity_id"]].fictional_type != "place":
            raise WorldBuilderError(
                status.HTTP_502_BAD_GATEWAY,
                "invalid_openai_response",
                "OpenAI must map non-character entities as fictional places",
            )


def _assert_fictionalized(value: Any, topic: dict[str, Any]) -> None:
    forbidden = [str(topic.get(key, "")).strip().casefold() for key in ("display_name", "topic_key")]
    text = json.dumps(value, ensure_ascii=False).casefold()
    if any(name and name in text for name in forbidden):
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "insufficiently_fictionalized_output",
            "Generated output repeated the source topic name and was not written",
        )


def _write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def build_world(topic_id: str) -> BuildWorldResponse:
    context = fetch_context(topic_id)
    existing_world, existing_characters = load_existing_world(topic_id)
    entities = context["entities"]
    if any(not isinstance(entity, dict) or not entity.get("entity_id") for entity in entities):
        raise WorldBuilderError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 context contains an entity without entity_id",
        )

    entity_map = dict(existing_world.entity_map) if existing_world else {}
    characters = dict(existing_characters.root) if existing_characters else {}
    missing_entities = [entity for entity in entities if entity["entity_id"] not in entity_map]
    eligible = _eligible_entities(entities)
    roles = calculate_roles(context, eligible)
    represented_character_sources = {character.source_entity_id for character in characters.values()}
    characters_to_add = [entity for entity in eligible if entity["entity_id"] not in represented_character_sources]

    if existing_world is None or missing_entities or characters_to_add:
        generated = generate_fictional_content(context, missing_entities, characters_to_add, roles)
        entity_map_by_source, characters_by_source = _validate_generated_keys(
            generated,
            {entity["entity_id"] for entity in missing_entities},
            {entity["entity_id"] for entity in characters_to_add},
        )
        _validate_place_mappings(missing_entities, entity_map_by_source)
        entity_map.update(
            {
                source_entity_id: EntityMapEntry.model_validate(draft.model_dump(exclude={"source_entity_id"}))
                for source_entity_id, draft in entity_map_by_source.items()
            }
        )
        for source_entity_id, draft in characters_by_source.items():
            characters[str(uuid4())] = Character(
                source_entity_id=source_entity_id,
                role=roles[source_entity_id],
                name=draft.name,
                goals=draft.goals,
                fears=draft.fears,
                personality=draft.personality,
                emotion_state=draft.emotion_state,
            )
        world = World(
            topic_id=topic_id,
            world_id=existing_world.world_id if existing_world else uuid4(),
            name=existing_world.name if existing_world else generated.world_name,
            entity_map=entity_map,
        )
    else:
        world = existing_world

    result = BuildWorldResponse(world=world, characters=Characters(characters))
    _assert_fictionalized(result.model_dump(mode="json"), context.get("topic", {}))
    output_directory = WORLD_BIBLE_DIR / topic_id
    output_directory.mkdir(parents=True, exist_ok=True)
    _write_json(output_directory / "world.json", result.world.model_dump(mode="json"))
    _write_json(output_directory / "characters.json", result.characters.model_dump(mode="json"))
    return result
