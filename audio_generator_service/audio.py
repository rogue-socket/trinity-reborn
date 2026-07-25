"""Voice inference, ElevenLabs validation/TTS, and immediate episode persistence."""

import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import status
from openai import APIConnectionError, APIError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import ValidationError

from story_generator_service.contracts import Episode

from .config import AUDIO_DIR, BLUEPRINT_DIR, ELEVENLABS_BASE_URL, EPISODE_DIR, OPENAI_MODEL
from .contracts import VoiceInference, VoiceProfile


logger = logging.getLogger(__name__)
_subscription: dict[str, int] = {"character_count": 0, "character_limit": 0}
_voices_cache: list[dict[str, Any]] | None = None


class AudioError(Exception):
    def __init__(self, status_code: int, error: str, message: str) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


def _elevenlabs_headers() -> dict[str, str]:
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise AudioError(status.HTTP_503_SERVICE_UNAVAILABLE, "elevenlabs_not_configured", "ELEVENLABS_API_KEY is required")
    return {"xi-api-key": key}


def validate_elevenlabs_key() -> dict[str, int]:
    try:
        response = httpx.get(f"{ELEVENLABS_BASE_URL}/v1/user", headers=_elevenlabs_headers(), timeout=15.0)
    except httpx.HTTPError as exc:
        raise AudioError(status.HTTP_503_SERVICE_UNAVAILABLE, "elevenlabs_unavailable", f"Could not validate ElevenLabs key: {exc}") from exc
    if not response.is_success:
        raise AudioError(status.HTTP_503_SERVICE_UNAVAILABLE, "elevenlabs_key_invalid", f"ElevenLabs key validation returned HTTP {response.status_code}")
    try:
        subscription = response.json().get("subscription", {})
        validated = {
            "character_count": int(subscription.get("character_count", 0)),
            "character_limit": int(subscription.get("character_limit", 0)),
        }
    except (ValueError, AttributeError) as exc:
        raise AudioError(status.HTTP_503_SERVICE_UNAVAILABLE, "elevenlabs_key_invalid", "ElevenLabs user response had no valid subscription data") from exc
    _subscription.update(validated)
    return validated


def subscription_snapshot() -> dict[str, int]:
    return dict(_subscription)


def _read_json(path: Path, error_name: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AudioError(status.HTTP_500_INTERNAL_SERVER_ERROR, error_name, f"Could not read valid JSON from {path}") from exc


def _episode_path(topic_id: str, character_id: str) -> Path:
    return EPISODE_DIR / topic_id / f"{character_id}.json"


def load_episode(topic_id: str, character_id: str) -> Episode:
    path = _episode_path(topic_id, character_id)
    if not path.is_file():
        raise AudioError(status.HTTP_409_CONFLICT, "episode_missing", "Episode is missing. Run story_generator_service first.")
    try:
        episode = Episode.model_validate(_read_json(path, "invalid_episode"))
    except ValidationError as exc:
        raise AudioError(status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid_episode", "Episode does not match the required schema") from exc
    if not episode.story_text:
        raise AudioError(status.HTTP_409_CONFLICT, "story_text_missing", "Episode has no story text. Run story_generator_service first.")
    return episode


def _write_episode(episode: Episode) -> None:
    path = _episode_path(episode.topic_id, episode.character_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(episode.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _profile_path(topic_id: str, character_id: str) -> Path:
    return AUDIO_DIR / topic_id / character_id / "voice_profile.json"


def _load_blueprint_character(topic_id: str, character_id: str) -> dict[str, Any]:
    path = BLUEPRINT_DIR / topic_id / "blueprint.json"
    if not path.is_file():
        raise AudioError(status.HTTP_409_CONFLICT, "blueprint_missing", "Blueprint is missing. Run blueprint_assembler_service first.")
    blueprint = _read_json(path, "invalid_blueprint")
    try:
        return next(character for character in blueprint["characters"] if character["character_id"] == character_id)
    except (KeyError, StopIteration, TypeError) as exc:
        raise AudioError(status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid_blueprint", "Blueprint does not contain the requested character profile") from exc


def _is_transient_openai_error(exc: APIError) -> bool:
    return isinstance(exc, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)) or (
        getattr(exc, "status_code", 0) is not None and getattr(exc, "status_code", 0) >= 500
    )


def infer_voice(character: dict[str, Any]) -> VoiceInference:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AudioError(status.HTTP_503_SERVICE_UNAVAILABLE, "openai_not_configured", "OPENAI_API_KEY is required to infer a voice profile")
    client = OpenAI(api_key=api_key)
    profile = {
        "personality": character.get("personality", []),
        "goals": character.get("goals", []),
        "fears": character.get("fears", []),
        "emotion_state": character.get("emotion_state", {}),
        "role": character.get("role"),
    }
    system_prompt = (
        "Infer a fictional narration voice from this character profile. Do not infer identity from any real-world nationality, ethnicity, or public figure. "
        "Return only the requested structured gender, accent_or_region, and age_range fields. Use neutral accent_or_region if the profile offers no safe cue."
    )
    for attempt in range(3):
        try:
            response = client.chat.completions.parse(
                model=OPENAI_MODEL,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": json.dumps(profile)}],
                response_format=VoiceInference,
            )
            inferred = response.choices[0].message.parsed
            if inferred is None:
                raise AudioError(status.HTTP_502_BAD_GATEWAY, "invalid_openai_response", "OpenAI returned no voice profile")
            return inferred
        except APIError as exc:
            if attempt < 2 and _is_transient_openai_error(exc):
                time.sleep(2**attempt)
                continue
            raise AudioError(status.HTTP_502_BAD_GATEWAY, "voice_inference_failed", f"OpenAI could not infer a voice profile: {exc}") from exc
        except ValidationError as exc:
            raise AudioError(status.HTTP_502_BAD_GATEWAY, "invalid_openai_response", "OpenAI returned an invalid voice profile") from exc
    raise AssertionError("retry loop should always return or raise")


def _voices() -> list[dict[str, Any]]:
    global _voices_cache
    if _voices_cache:
        return _voices_cache
    try:
        response = httpx.get(f"{ELEVENLABS_BASE_URL}/v2/voices", headers=_elevenlabs_headers(), params={"page_size": 100}, timeout=20.0)
        response.raise_for_status()
        _voices_cache = list(response.json().get("voices", []))
        return _voices_cache
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        # Left uncached so a transient failure does not pin every later character to the fallback voice.
        logger.warning("Could not fetch ElevenLabs voice list; using fallback voice: %s", exc)
        return []


def select_voice(inference: VoiceInference) -> str:
    voices = _voices()
    fallback = os.getenv("ELEVENLABS_FALLBACK_VOICE_ID", "")
    if not voices:
        if fallback:
            return fallback
        raise AudioError(status.HTTP_503_SERVICE_UNAVAILABLE, "elevenlabs_voice_unavailable", "Voice list is empty and ELEVENLABS_FALLBACK_VOICE_ID is not configured")
    gender_matches = [voice for voice in voices if str(voice.get("labels", {}).get("gender", "")).casefold() == inference.gender.casefold()]
    candidates = gender_matches or voices
    requested_accent = inference.accent_or_region.casefold()

    def accent_score(voice: dict[str, Any]) -> int:
        voice_accent = str(voice.get("labels", {}).get("accent", "")).casefold()
        return int(bool(voice_accent) and (requested_accent in voice_accent or voice_accent in requested_accent))

    candidates.sort(
        key=lambda voice: (
            -accent_score(voice),
            str(voice.get("voice_id", "")),
        )
    )
    voice_id = str(candidates[0].get("voice_id", ""))
    if voice_id:
        return voice_id
    if fallback:
        return fallback
    raise AudioError(status.HTTP_503_SERVICE_UNAVAILABLE, "elevenlabs_voice_unavailable", "No usable ElevenLabs voice ID was found")


def load_or_create_voice_profile(topic_id: str, character_id: str) -> VoiceProfile:
    path = _profile_path(topic_id, character_id)
    if path.is_file():
        try:
            return VoiceProfile.model_validate(_read_json(path, "invalid_voice_profile"))
        except ValidationError as exc:
            raise AudioError(status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid_voice_profile", "Cached voice profile does not match the required schema") from exc
    inferred = infer_voice(_load_blueprint_character(topic_id, character_id))
    profile = VoiceProfile(voice_id=select_voice(inferred), **inferred.model_dump())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(profile.model_dump(), indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(path)
    return profile


def synthesize(language: str, text: str, voice_id: str) -> bytes:
    payload = {"text": text, "model_id": "eleven_multilingual_v2"}
    for attempt in range(4):
        try:
            response = httpx.post(
                f"{ELEVENLABS_BASE_URL}/v1/text-to-speech/{voice_id}",
                headers={**_elevenlabs_headers(), "Content-Type": "application/json", "Accept": "audio/mpeg"},
                params={"output_format": "mp3_44100_128"},
                json=payload,
                timeout=90.0,
            )
        except httpx.HTTPError as exc:
            raise AudioError(status.HTTP_502_BAD_GATEWAY, "elevenlabs_tts_failed", f"ElevenLabs request failed for {language}: {exc}") from exc
        if response.is_success:
            return response.content
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < 3:
                time.sleep(2**attempt)
                continue
        raise AudioError(status.HTTP_502_BAD_GATEWAY, "elevenlabs_tts_failed", f"ElevenLabs TTS failed for {language}: HTTP {response.status_code}")
    raise AssertionError("retry loop should return or raise")


def narrate(topic_id: str, character_id: str, languages: list[str] | None, force: bool) -> Episode:
    episode = load_episode(topic_id, character_id)
    profile = load_or_create_voice_profile(topic_id, character_id)
    if episode.voice_id != profile.voice_id:
        episode.voice_id = profile.voice_id
        episode.updated_at = datetime.now(UTC)
        _write_episode(episode)
    requested_languages = list(dict.fromkeys(languages)) if languages is not None else list(episode.story_text.keys())
    for language in requested_languages:
        text = episode.story_text.get(language, "")
        if not text:
            episode.audio_errors[language] = f"No story text exists for language '{language}'"
            episode.updated_at = datetime.now(UTC)
            _write_episode(episode)
            continue
        if episode.audio.get(language) and not force:
            if language in episode.audio_errors:
                episode.audio_errors.pop(language, None)
                episode.updated_at = datetime.now(UTC)
                _write_episode(episode)
            continue
        try:
            audio_bytes = synthesize(language, text, profile.voice_id)
            audio_path = AUDIO_DIR / topic_id / character_id / f"{language}.mp3"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                audio_path.write_bytes(audio_bytes)
            except OSError as exc:
                raise AudioError(status.HTTP_500_INTERNAL_SERVER_ERROR, "audio_write_failed", f"Could not save {language} audio: {exc}") from exc
            episode.audio[language] = {"path": str(audio_path), "voice_id": profile.voice_id}
            episode.audio_errors.pop(language, None)
        except AudioError as exc:
            episode.audio_errors[language] = exc.message
        episode.voice_id = profile.voice_id
        episode.updated_at = datetime.now(UTC)
        _write_episode(episode)
    if all(language in episode.audio and language not in episode.audio_errors for language in episode.story_text):
        episode.status = "audio_ready"
        episode.updated_at = datetime.now(UTC)
        _write_episode(episode)
    return episode
