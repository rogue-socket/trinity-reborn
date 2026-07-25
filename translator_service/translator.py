"""Gemini translation with per-language persistence and 429-only retries."""

import json
import os
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import status
from google import genai
from google.genai import errors
from pydantic import ValidationError

from story_generator_service.contracts import Episode

from .config import BLUEPRINT_DIR, EPISODE_DIR, GEMINI_MODEL


class TranslatorError(Exception):
    def __init__(self, status_code: int, error: str, message: str) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


def _read_json(path: Path, error_name: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranslatorError(status.HTTP_500_INTERNAL_SERVER_ERROR, error_name, f"Could not read valid JSON from {path}") from exc


def _episode_path(topic_id: str, character_id: str) -> Path:
    return EPISODE_DIR / topic_id / f"{character_id}.json"


def load_episode(topic_id: str, character_id: str) -> Episode:
    path = _episode_path(topic_id, character_id)
    if not path.is_file():
        raise TranslatorError(
            status.HTTP_409_CONFLICT,
            "episode_missing",
            f"Episode is missing for character_id '{character_id}'. Run story_generator_service first.",
        )
    try:
        episode = Episode.model_validate(_read_json(path, "invalid_episode"))
    except ValidationError as exc:
        raise TranslatorError(status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid_episode", "Episode does not match the required schema") from exc
    if not episode.story_text.get("en", "").strip():
        raise TranslatorError(
            status.HTTP_409_CONFLICT,
            "english_story_missing",
            "Episode has no English story text. Run story_generator_service first.",
        )
    return episode


def load_glossary(topic_id: str, character_id: str) -> list[str]:
    path = BLUEPRINT_DIR / topic_id / "blueprint.json"
    if not path.is_file():
        raise TranslatorError(
            status.HTTP_409_CONFLICT,
            "blueprint_missing",
            f"Blueprint is missing for topic_id '{topic_id}'. Run blueprint_assembler_service first.",
        )
    blueprint = _read_json(path, "invalid_blueprint")
    try:
        character = next(item for item in blueprint["characters"] if item["character_id"] == character_id)
        entity_names = [entry["fictional_name"] for entry in blueprint["world"]["entity_map"].values()]
        return list(dict.fromkeys([character["name"], *entity_names]))
    except (KeyError, StopIteration, TypeError) as exc:
        raise TranslatorError(status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid_blueprint", "Blueprint cannot provide the required translation glossary") from exc


def _write_episode(episode: Episode) -> None:
    path = _episode_path(episode.topic_id, episode.character_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(episode.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary_path.replace(path)


@lru_cache(maxsize=1)
def select_gemini_model() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise TranslatorError(status.HTTP_503_SERVICE_UNAVAILABLE, "gemini_not_configured", "GEMINI_API_KEY is required to translate episodes")
    client = genai.Client(api_key=api_key)
    available = {
        str(model.name).removeprefix("models/")
        for model in client.models.list()
        if "flash" in str(model.name).casefold()
        and "pro" not in str(model.name).casefold()
        and "generatecontent" in {str(action).casefold() for action in (getattr(model, "supported_actions", None) or [])}
    }
    configured = GEMINI_MODEL.removeprefix("models/")
    if configured in available and "flash" in configured.casefold() and "pro" not in configured.casefold():
        return configured
    for candidate in ("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.5-flash"):
        if candidate in available:
            return candidate
    raise TranslatorError(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "gemini_model_unavailable",
        "No Flash-tier Gemini model with generateContent support is available to this key",
    )


def _translation_prompt(english_story: str, language: str, glossary: list[str]) -> str:
    return (
        f"Translate the following English narration into {language}. Preserve its tone and spoken-narration register; do not make it stiff or literal. "
        "Keep every glossary term as a consistent transliteration, not a literal translation. Return only the translated narration.\n\n"
        f"Glossary (transliterate consistently): {json.dumps(glossary, ensure_ascii=False)}\n\n"
        f"English narration:\n{english_story}"
    )


def translate_language(english_story: str, language: str, glossary: list[str]) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise TranslatorError(status.HTTP_503_SERVICE_UNAVAILABLE, "gemini_not_configured", "GEMINI_API_KEY is required to translate episodes")
    client = genai.Client(api_key=api_key)
    model = select_gemini_model()
    prompt = _translation_prompt(english_story, language, glossary)
    # Initial request plus up to three rate-limit retries, waiting 1s, 2s, and 4s.
    for attempt in range(4):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            translated = (response.text or "").strip()
            if not translated:
                raise TranslatorError(status.HTTP_502_BAD_GATEWAY, "empty_gemini_response", f"Gemini returned no text for language '{language}'")
            return translated
        except errors.APIError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(2**attempt)
                continue
            raise TranslatorError(
                status.HTTP_502_BAD_GATEWAY,
                "gemini_translation_failed",
                f"Gemini translation failed for {language}: HTTP {exc.code} {exc.message or ''}".strip(),
            ) from exc


def translate_episode(topic_id: str, character_id: str, target_languages: list[str] | None, force: bool) -> Episode:
    episode = load_episode(topic_id, character_id)
    glossary = load_glossary(topic_id, character_id)
    languages = list(dict.fromkeys(target_languages)) if target_languages is not None else [language for language in episode.target_languages if language != "en"]
    for language in languages:
        if language == "en":
            continue
        if episode.story_text.get(language) and not force:
            # A stored translation represents success even if an older partial write left an error behind.
            if language in episode.translation_errors:
                episode.translation_errors.pop(language)
                episode.updated_at = datetime.now(UTC)
                _write_episode(episode)
            continue
        try:
            episode.story_text[language] = translate_language(episode.story_text["en"], language, glossary)
            episode.translation_errors.pop(language, None)
        except TranslatorError as exc:
            episode.translation_errors[language] = exc.message
        episode.updated_at = datetime.now(UTC)
        # Persist every language outcome immediately, including a failure, to preserve partial progress.
        _write_episode(episode)

    expected_translations = [language for language in episode.target_languages if language != "en"]
    desired_status = (
        "translated"
        if all(episode.story_text.get(language) and language not in episode.translation_errors for language in expected_translations)
        else "story_generated"
    )
    if episode.status != desired_status and episode.status != "audio_ready":
        episode.status = desired_status
        episode.updated_at = datetime.now(UTC)
        _write_episode(episode)
    return episode
