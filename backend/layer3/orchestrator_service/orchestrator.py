"""Call Echoes services in order and persist a concise run report."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import status

from backend.shared.artifact_paths import atomic_write_text

from .config import (
    AUDIO_URL,
    BLUEPRINT_URL,
    DOWNSTREAM_TIMEOUT_SECONDS,
    RUN_HISTORY_DIR,
    STORY_GEN_URL,
    TRANSLATOR_URL,
    WORLD_BUILDER_URL,
)
from .contracts import CharacterRunOutcome, RunReport


class OrchestratorError(Exception):
    def __init__(self, status_code: int, error: str, message: str) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(UTC)


def _upstream_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("detail") or payload.get("error") or payload)
    return str(payload)


def _post(client: httpx.Client, service_name: str, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        # Client already carries DOWNSTREAM_TIMEOUT_SECONDS; pass it per-call so a future
        # client without a default cannot silently hang the demo.
        response = client.post(url, json=payload, timeout=client.timeout)
    except httpx.HTTPError as exc:
        raise OrchestratorError(
            status.HTTP_502_BAD_GATEWAY,
            "downstream_unreachable",
            f"{service_name} could not be reached: {exc}",
        ) from exc
    if not response.is_success:
        code = response.status_code if 400 <= response.status_code < 600 else status.HTTP_502_BAD_GATEWAY
        raise OrchestratorError(code, "downstream_failed", f"{service_name} failed: {_upstream_message(response)}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise OrchestratorError(
            status.HTTP_502_BAD_GATEWAY,
            "invalid_downstream_response",
            f"{service_name} returned invalid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise OrchestratorError(
            status.HTTP_502_BAD_GATEWAY,
            "invalid_downstream_response",
            f"{service_name} returned a JSON value other than an object",
        )
    return payload


def _write_report(report: RunReport) -> Path:
    destination = RUN_HISTORY_DIR / report.topic_id / f"{report.run_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(report.model_dump(mode="json"), indent=2) + "\n")
    return destination


def _errors(payload: dict[str, Any], name: str) -> dict[str, str]:
    values = payload.get(name, {})
    if not isinstance(values, dict):
        return {"_upstream": f"The upstream {name} field was malformed"}
    return {str(key): str(value) for key, value in values.items()}


def _outcome_after_story_failure(narrate: bool) -> CharacterRunOutcome:
    return CharacterRunOutcome(
        story_status="failed",
        translation_status="failed",
        translation_errors={"_orchestrator": "Story generation failed; translation was not attempted."},
        audio_status="failed" if narrate else "skipped",
        audio_errors={"_orchestrator": "Story generation failed; narration was not attempted."} if narrate else {},
    )


def _run_character(client: httpx.Client, topic_id: str, character_id: str, languages: list[str], narrate: bool) -> CharacterRunOutcome:
    try:
        _post(client, "story_generator_service", f"{STORY_GEN_URL}/episodes", {"topic_id": topic_id, "character_id": character_id})
    except OrchestratorError:
        return _outcome_after_story_failure(narrate)

    try:
        translation = _post(
            client,
            "translator_service",
            f"{TRANSLATOR_URL}/translate",
            {"topic_id": topic_id, "character_id": character_id, "target_languages": languages},
        )
        translation_errors = _errors(translation, "translation_errors")
        translation_status: Literal["ok", "partial", "failed"] = "partial" if translation_errors else "ok"
    except OrchestratorError as exc:
        translation_errors = {"_upstream": exc.message}
        translation_status = "failed"

    if not narrate:
        return CharacterRunOutcome(
            story_status="ok",
            translation_status=translation_status,
            translation_errors=translation_errors,
            audio_status="skipped",
        )

    try:
        audio = _post(
            client,
            "audio_generator_service",
            f"{AUDIO_URL}/narrate",
            {"topic_id": topic_id, "character_id": character_id, "languages": languages},
        )
        audio_errors = _errors(audio, "audio_errors")
        audio_status: Literal["ok", "partial", "failed"] = "partial" if audio_errors else "ok"
    except OrchestratorError as exc:
        audio_errors = {"_upstream": exc.message}
        audio_status = "failed"

    return CharacterRunOutcome(
        story_status="ok",
        translation_status=translation_status,
        translation_errors=translation_errors,
        audio_status=audio_status,
        audio_errors=audio_errors,
    )


def run_topic(topic_id: str, character_ids: list[str] | None, languages: list[str] | None, narrate: bool) -> RunReport:
    """Run the five work services in dependency order; no generation happens here."""
    started_at = _now()
    with httpx.Client(timeout=httpx.Timeout(DOWNSTREAM_TIMEOUT_SECONDS)) as client:
        _post(client, "world_builder_service", f"{WORLD_BUILDER_URL}/build-world", {"topic_id": topic_id})
        blueprint = _post(client, "blueprint_assembler_service", f"{BLUEPRINT_URL}/build-blueprint", {"topic_id": topic_id})

        resolved_characters = list(dict.fromkeys(character_ids)) if character_ids is not None else blueprint.get("perspectives_to_generate")
        resolved_languages = list(dict.fromkeys(languages)) if languages is not None else blueprint.get("target_languages")
        if not isinstance(resolved_characters, list) or not all(isinstance(value, str) and value for value in resolved_characters):
            raise OrchestratorError(status.HTTP_502_BAD_GATEWAY, "invalid_blueprint", "Blueprint did not supply valid perspectives_to_generate")
        if not isinstance(resolved_languages, list) or not all(isinstance(value, str) and value for value in resolved_languages):
            raise OrchestratorError(status.HTTP_502_BAD_GATEWAY, "invalid_blueprint", "Blueprint did not supply valid target_languages")

        outcomes = {
            character_id: _run_character(client, topic_id, character_id, resolved_languages, narrate)
            for character_id in resolved_characters
        }

    report = RunReport(
        run_id=uuid4(),
        topic_id=topic_id,
        narrate_requested=narrate,
        started_at=started_at,
        finished_at=_now(),
        world_status="ok",
        blueprint_status="ok",
        characters=outcomes,
    )
    _write_report(report)
    return report
