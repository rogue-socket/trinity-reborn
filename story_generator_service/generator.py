"""Blueprint loading, safe prompt construction, OpenAI generation, and episode persistence."""

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import status
from openai import APIConnectionError, APIError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import ValidationError

from .config import BLUEPRINT_DIR, EPISODE_DIR, OPENAI_MODEL
from .contracts import Episode, GeneratedNarrative


class EpisodeError(Exception):
    def __init__(self, status_code: int, error: str, message: str) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


class GenerationFailed(EpisodeError):
    def __init__(self, episode: Episode) -> None:
        self.episode = episode
        super().__init__(status.HTTP_502_BAD_GATEWAY, "story_generation_failed", episode.error or "Story generation failed")


PROHIBITED_REAL_WORLD_NAMES = {
    "india",
    "delhi",
    "mumbai",
    "london",
    "paris",
    "new york",
    "washington",
    "beijing",
    "tokyo",
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "invalid_blueprint",
            f"Could not read valid JSON from {path}",
        ) from exc


def load_blueprint(topic_id: str) -> dict[str, Any]:
    path = BLUEPRINT_DIR / topic_id / "blueprint.json"
    if not path.is_file():
        raise EpisodeError(
            status.HTTP_409_CONFLICT,
            "blueprint_missing",
            f"Blueprint is missing for topic_id '{topic_id}'. Run blueprint_assembler_service first.",
        )
    blueprint = _read_json(path)
    required = {"blueprint_id", "world", "characters", "timeline", "central_conflict", "themes", "disputed_threads", "perspectives_to_generate", "target_languages"}
    if not isinstance(blueprint, dict) or required - blueprint.keys():
        raise EpisodeError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "invalid_blueprint",
            "Blueprint does not contain the required Story Blueprint fields",
        )
    if not isinstance(blueprint["characters"], list) or not isinstance(blueprint["timeline"], list):
        raise EpisodeError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "invalid_blueprint",
            "Blueprint characters and timeline must be arrays",
        )
    return blueprint


def _episode_path(topic_id: str, character_id: str) -> Path:
    return EPISODE_DIR / topic_id / f"{character_id}.json"


def _load_cached_episode(topic_id: str, character_id: str) -> Episode | None:
    path = _episode_path(topic_id, character_id)
    if not path.is_file():
        return None
    try:
        return Episode.model_validate(_read_json(path))
    except ValidationError as exc:
        raise EpisodeError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "invalid_episode_cache",
            f"Cached episode for character_id '{character_id}' does not match the required schema",
        ) from exc


def _character(blueprint: dict[str, Any], character_id: str) -> dict[str, Any]:
    if character_id not in blueprint["perspectives_to_generate"]:
        raise EpisodeError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_character_perspective",
            f"character_id '{character_id}' is not available in perspectives_to_generate",
        )
    target = next((character for character in blueprint["characters"] if character.get("character_id") == character_id), None)
    if target is None:
        raise EpisodeError(
            status.HTTP_400_BAD_REQUEST,
            "character_not_found",
            f"character_id '{character_id}' does not exist in the blueprint",
        )
    return target


def _relevant_world_entries(blueprint: dict[str, Any], character: dict[str, Any], timeline: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    entity_map = blueprint["world"].get("entity_map", {})
    labels = " ".join(str(entry.get("fictional_label", "")) for entry in timeline).casefold()
    relevant = {
        entity_id: entry
        for entity_id, entry in entity_map.items()
        if str(entry.get("fictional_name", "")).casefold() in labels
        or entity_id == character.get("source_entity_id")
    }
    return relevant


def build_prompt(blueprint: dict[str, Any], character: dict[str, Any]) -> str:
    timeline = [entry for entry in blueprint["timeline"] if character["character_id"] in entry.get("participant_character_ids", [])]
    relevant_entries = _relevant_world_entries(blueprint, character, timeline)
    prompt_data = {
        "world_name": blueprint["world"].get("name"),
        "relevant_world_entities": relevant_entries,
        "character": {
            "name": character.get("name"),
            "goals": character.get("goals"),
            "fears": character.get("fears"),
            "personality": character.get("personality"),
            "emotion_state": character.get("emotion_state"),
        },
        "central_conflict": blueprint["central_conflict"],
        "themes": blueprint["themes"],
        "unresolved_tensions": [
            {
                "description": thread.get("description"),
                "instruction": "This is unresolved tension, not settled fact.",
            }
            for thread in blueprint["disputed_threads"]
            if character["character_id"] in thread.get("related_character_ids", [])
        ],
        "character_timeline": timeline,
    }
    return json.dumps(prompt_data, ensure_ascii=False)


def _is_transient(exc: APIError) -> bool:
    return isinstance(exc, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)) or (
        getattr(exc, "status_code", 0) is not None and getattr(exc, "status_code", 0) >= 500
    )


def generate_narrative(prompt: str) -> GeneratedNarrative:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EpisodeError(status.HTTP_503_SERVICE_UNAVAILABLE, "openai_not_configured", "OPENAI_API_KEY is required to generate an episode")
    options: dict[str, str] = {"api_key": api_key}
    if base_url := os.getenv("OPENAI_BASE_URL"):
        options["base_url"] = base_url
    client = OpenAI(**options)
    system_prompt = (
        "Write a self-contained 500-800 word English narrative episode in first-person or close-third perspective. "
        "Use only the fictional names supplied in the user data. Do not invent named real-world countries, cities, public figures, "
        "or institutions, even as a metaphor; do not introduce any proper noun outside the supplied fictional names. Treat every unresolved tension as uncertain: the character may be worried, hopeful, or doubtful, but must "
        "not present a disputed matter as settled fact. Return JSON only with a concise title and the full story_text."
    )
    for attempt in range(3):
        try:
            completion = client.chat.completions.parse(
                model=OPENAI_MODEL,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                response_format=GeneratedNarrative,
            )
            narrative = completion.choices[0].message.parsed
            if narrative is None:
                raise EpisodeError(status.HTTP_502_BAD_GATEWAY, "invalid_openai_response", "OpenAI did not return a schema-valid episode")
            return narrative
        except APIError as exc:
            if attempt < 2 and _is_transient(exc):
                time.sleep(2**attempt)
                continue
            raise EpisodeError(status.HTTP_502_BAD_GATEWAY, "openai_generation_failed", f"OpenAI could not generate the episode: {exc}") from exc
        except ValidationError as exc:
            raise EpisodeError(status.HTTP_502_BAD_GATEWAY, "invalid_openai_response", "OpenAI returned a story outside the required schema or length") from exc
        except EpisodeError:
            raise
        except Exception as exc:
            raise EpisodeError(status.HTTP_502_BAD_GATEWAY, "invalid_openai_response", "OpenAI returned an unreadable episode") from exc
    raise AssertionError("retry loop should always return or raise")


def _write_episode(episode: Episode) -> None:
    path = _episode_path(episode.topic_id, episode.character_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(episode.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _failed_episode(blueprint: dict[str, Any], topic_id: str, character_id: str, error: str) -> Episode:
    now = datetime.now(UTC)
    return Episode(
        episode_id=uuid4(),
        blueprint_id=str(blueprint["blueprint_id"]),
        topic_id=topic_id,
        character_id=character_id,
        title="",
        status="failed",
        story_text={},
        audio={},
        target_languages=list(blueprint["target_languages"]),
        created_at=now,
        updated_at=now,
        error=error,
    )


def create_episode(topic_id: str, character_id: str, force: bool = False) -> Episode:
    blueprint = load_blueprint(topic_id)
    character = _character(blueprint, character_id)
    cached = _load_cached_episode(topic_id, character_id)
    if cached is not None and cached.status in {"story_generated", "translated", "audio_ready"} and not force:
        return cached
    try:
        narrative = generate_narrative(build_prompt(blueprint, character))
        now = datetime.now(UTC)
        episode = Episode(
            episode_id=uuid4(),
            blueprint_id=str(blueprint["blueprint_id"]),
            topic_id=topic_id,
            character_id=character_id,
            title=narrative.title,
            status="story_generated",
            story_text={"en": narrative.story_text},
            audio={},
            target_languages=list(blueprint["target_languages"]),
            created_at=now,
            updated_at=now,
            error=None,
        )
        prohibited_pattern = r"\b(?:" + "|".join(re.escape(name) for name in PROHIBITED_REAL_WORLD_NAMES) + r")\b"
        if re.search(prohibited_pattern, narrative.story_text, flags=re.IGNORECASE):
            raise EpisodeError(status.HTTP_502_BAD_GATEWAY, "insufficiently_fictionalized_output", "Generated story contained a prohibited real-world name")
        _write_episode(episode)
        return episode
    except EpisodeError as exc:
        failed = _failed_episode(blueprint, topic_id, character_id, exc.message)
        _write_episode(failed)
        raise GenerationFailed(failed) from exc
