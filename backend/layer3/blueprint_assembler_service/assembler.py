"""Pure deterministic assembly of Layer 2 context and World Bible data."""

import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from fastapi import status
from pydantic import ValidationError

from backend.shared.artifact_paths import atomic_write_text

from .config import BLUEPRINT_DIR, LAYER2_BASE_URL, WORLD_BIBLE_DIR
from .contracts import Blueprint, BlueprintCharacter, Character, DisputedThread, TimelineEntry, World


logger = logging.getLogger(__name__)
REQUIRED_CONTEXT_FIELDS = {"entities", "events", "claims", "timeline", "disputes"}
TARGET_LANGUAGES: list[Literal["en", "hi", "ta", "bn", "pa", "gu"]] = ["en", "hi", "ta", "bn", "pa", "gu"]


class BlueprintError(Exception):
    def __init__(self, status_code: int, error: str, message: str) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


def fetch_context(topic_id: str) -> dict[str, Any]:
    try:
        response = httpx.get(f"{LAYER2_BASE_URL}/topics/{topic_id}/context", timeout=15.0)
    except httpx.HTTPError as exc:
        raise BlueprintError(
            status.HTTP_502_BAD_GATEWAY,
            "layer2_unavailable",
            f"Could not reach Layer 2 at {LAYER2_BASE_URL}: {exc}",
        ) from exc
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise BlueprintError(
            status.HTTP_404_NOT_FOUND,
            "topic_not_found",
            f"Layer 2 does not contain topic_id '{topic_id}'",
        )
    if not response.is_success:
        raise BlueprintError(
            status.HTTP_502_BAD_GATEWAY,
            "layer2_error",
            f"Layer 2 returned HTTP {response.status_code} while fetching topic context",
        )
    try:
        context = response.json()
    except ValueError as exc:
        raise BlueprintError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 returned a non-JSON context response",
        ) from exc
    if not isinstance(context, dict):
        raise BlueprintError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 context must be a JSON object",
        )
    missing = sorted(REQUIRED_CONTEXT_FIELDS - context.keys())
    if missing:
        raise BlueprintError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            f"Layer 2 context is missing required fields: {', '.join(missing)}",
        )
    if any(not isinstance(context[field], list) or any(not isinstance(item, dict) for item in context[field]) for field in REQUIRED_CONTEXT_FIELDS):
        raise BlueprintError(
            status.HTTP_502_BAD_GATEWAY,
            "malformed_layer2_response",
            "Layer 2 context collections must be arrays of objects",
        )
    return context


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BlueprintError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "invalid_world_bible",
            f"Could not read valid JSON from {path}",
        ) from exc


def load_world_bible(topic_id: str) -> tuple[World, dict[str, Character]]:
    directory = WORLD_BIBLE_DIR / topic_id
    world_path = directory / "world.json"
    characters_path = directory / "characters.json"
    missing = [str(path.name) for path in (world_path, characters_path) if not path.is_file()]
    if missing:
        raise BlueprintError(
            status.HTTP_409_CONFLICT,
            "world_bible_incomplete",
            f"Missing {', '.join(missing)}. Run world_builder_service first.",
        )
    try:
        world = World.model_validate(_load_json(world_path))
        characters = {character_id: Character.model_validate(value) for character_id, value in _load_json(characters_path).items()}
        if world.topic_id != topic_id:
            raise ValueError("world topic_id does not match its directory")
        # Character IDs are keys in the persisted object and must remain valid UUIDs in the blueprint list.
        for character_id in characters:
            BlueprintCharacter(character_id=character_id, **characters[character_id].model_dump())
        return world, characters
    except (ValidationError, ValueError, AttributeError) as exc:
        raise BlueprintError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "invalid_world_bible",
            f"World Bible for topic_id '{topic_id}' does not match the required schema",
        ) from exc


def _canonical_hash(context: dict[str, Any], world: World, characters: dict[str, Character]) -> str:
    payload = {"context": context, "world": world.model_dump(mode="json"), "characters": {key: value.model_dump(mode="json") for key, value in characters.items()}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _fictionalize(text: str, entities: list[dict[str, Any]], world: World) -> str:
    """Swap known entity labels in Layer 2 prose for their fictional counterparts.

    This reduces exposure rather than eliminating it: a real noun that Layer 1 never
    extracted as an entity has no mapping and survives. Prose is only carried over where
    the substance is the point, such as the central conflict.
    """
    replacements = sorted(
        (
            (str(entity["label"]), world.entity_map[entity["entity_id"]].fictional_name)
            for entity in entities
            if entity.get("entity_id") in world.entity_map and entity.get("label")
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for source_name, fictional_name in replacements:
        text = re.sub(re.escape(source_name), fictional_name, text, flags=re.IGNORECASE)
    return text


def _fictional_event_label(event: dict[str, Any], world: World) -> str:
    """Name the event from its fictional participants and its generic type.

    The real title is deliberately not used. It routinely carries real place, policy,
    and organisation names that appear nowhere in the entity list, so replacing known
    entity labels inside it cannot make it safe to publish.
    """
    kind = str(event.get("type", "")).replace("_", " ").strip() or "development"
    participants = [
        world.entity_map[entity_id].fictional_name
        for entity_id in event.get("participant_entity_ids", [])
        if entity_id in world.entity_map
    ]
    if participants:
        return f"{kind.capitalize()}: {', '.join(participants)}"
    return kind.capitalize()


def _epistemic_note(claims: list[dict[str, Any]]) -> str:
    statuses = [claim.get("epistemic_status") for claim in claims if isinstance(claim.get("epistemic_status"), str)]
    if "disputed" in statuses:
        return "contains a disputed claim"
    if not statuses:
        return "no linked claims"
    counts = Counter(statuses)
    common_status, count = min(counts.items(), key=lambda item: (-item[1], item[0]))
    return f"{common_status} by {count} claim" + ("s" if count != 1 else "")


def _character_ids_by_source(characters: dict[str, Character]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    for character_id, character in characters.items():
        if character.source_entity_id is not None:
            mapping[character.source_entity_id].append(character_id)
    return {source_id: sorted(character_ids) for source_id, character_ids in mapping.items()}


def assemble_blueprint(topic_id: str) -> Blueprint:
    context = fetch_context(topic_id)
    world, characters_by_id = load_world_bible(topic_id)
    input_hash = _canonical_hash(context, world, characters_by_id)
    blueprint_id = uuid5(NAMESPACE_URL, f"echoes-story-blueprint:{input_hash}")
    # A content-derived timestamp preserves the required deterministic output property.
    generated_at = datetime.fromtimestamp(int(input_hash[:8], 16), tz=UTC)

    events_by_id = {event.get("event_id"): event for event in context["events"] if event.get("event_id")}
    claims_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in context["claims"]:
        if claim.get("event_id"):
            claims_by_event[claim["event_id"]].append(claim)
    source_to_characters = _character_ids_by_source(characters_by_id)

    timeline: list[TimelineEntry] = []
    for timeline_item in sorted(context["timeline"], key=lambda item: (item.get("order", 0), str(item.get("event_id", "")))):
        event_id = timeline_item.get("event_id")
        event = events_by_id.get(event_id)
        if event is None:
            logger.warning("Skipping timeline event %r because it is missing from events", event_id)
            continue
        participant_ids: list[str] = []
        for entity_id in event.get("participant_entity_ids", []):
            participant_ids.extend(source_to_characters.get(entity_id, []))
        timeline.append(
            TimelineEntry(
                event_id=event_id,
                fictional_label=_fictional_event_label(event, world),
                order=int(timeline_item.get("order", 0)),
                status=str(event.get("status", "")),
                participant_character_ids=participant_ids,
                epistemic_note=_epistemic_note(claims_by_event.get(event_id, [])),
            )
        )

    disputes = context["disputes"]
    if disputes:
        central_conflict = str(disputes[0].get("description", ""))
    else:
        central_conflict = str(context.get("summary", {}).get("text", ""))[:200]
    central_conflict = _fictionalize(central_conflict, context["entities"], world)
    disputed_threads = [
        DisputedThread(
            description=_fictionalize(str(dispute.get("description", "")), context["entities"], world),
            related_character_ids=[
                character_id
                for entity_id in dispute.get("related_entity_ids", [])
                for character_id in source_to_characters.get(entity_id, [])
            ],
            use_as="plot tension, not resolved fact",
        )
        for dispute in disputes
    ]
    characters = [
        BlueprintCharacter(character_id=UUID(character_id), **character.model_dump())
        for character_id, character in sorted(characters_by_id.items())
    ]
    blueprint = Blueprint(
        blueprint_id=blueprint_id,
        topic_id=topic_id,
        generated_at=generated_at,
        world=world,
        characters=characters,
        timeline=timeline,
        central_conflict=central_conflict,
        themes=[str(interpretation.get("text", "")) for interpretation in context.get("interpretations", [])],
        disputed_threads=disputed_threads,
        perspectives_to_generate=[str(character.character_id) for character in characters],
        target_languages=TARGET_LANGUAGES,
    )
    return blueprint


def write_blueprint(blueprint: Blueprint) -> None:
    directory = BLUEPRINT_DIR / blueprint.topic_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "blueprint.json"
    atomic_write_text(path, json.dumps(blueprint.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")
