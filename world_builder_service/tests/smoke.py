"""Run a fully local POST /build-world smoke test against a live Layer 2 service."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import world_builder_service.world_builder as world_builder
from world_builder_service.contracts import CharacterDraft, EmotionState, EntityMapDraft, GenerationPayload
from world_builder_service.main import app

generation_calls = 0


def fake_generation(context, entities_for_map, characters_to_add, roles):
    global generation_calls
    generation_calls += 1
    return GenerationPayload(
        world_name="The Lantern Coast",
        entity_map=[
            EntityMapDraft(
                source_entity_id=entity["entity_id"],
                fictional_name=f"Fictional {entity['entity_id']}",
                fictional_type="place" if entity.get("type") in {"city_or_locality", "country"} else "faction",
                description="A wholly fictional setting element.",
            )
            for entity in entities_for_map
        ],
        characters=[
            CharacterDraft(
                source_entity_id=entity["entity_id"],
                name=f"Character {entity['entity_id']}",
                goals=["Protect a fictional community"],
                fears=["Losing trust"],
                personality=["resilient"],
                emotion_state=EmotionState(primary="determined", secondary="wary"),
            )
            for entity in characters_to_add
        ],
    )


def main() -> None:
    temporary_bible = Path(tempfile.mkdtemp(prefix="world_builder_smoke_"))
    original_directory = world_builder.WORLD_BIBLE_DIR
    original_generation = world_builder.generate_fictional_content
    try:
        world_builder.WORLD_BIBLE_DIR = temporary_bible
        world_builder.generate_fictional_content = fake_generation
        client = TestClient(app)
        response = client.post(
            "/build-world", json={"topic_id": "3f7a1b2c-0001-4a10-9c11-000000000001"}
        )
        response.raise_for_status()
        payload = response.json()
        assert len(payload["world"]["entity_map"]) == 6
        assert len(payload["characters"]) == 5
        assert {character["role"] for character in payload["characters"].values()} == {
            "protagonist",
            "antagonist",
            "supporting",
        }
        topic_directory = temporary_bible / "3f7a1b2c-0001-4a10-9c11-000000000001"
        assert (topic_directory / "world.json").exists()
        assert (topic_directory / "characters.json").exists()
        second_response = client.post(
            "/build-world", json={"topic_id": "3f7a1b2c-0001-4a10-9c11-000000000001"}
        )
        second_response.raise_for_status()
        assert generation_calls == 1
        assert second_response.json()["world"]["world_id"] == payload["world"]["world_id"]
        malformed_response = Mock(status_code=200, is_success=True)
        malformed_response.json.return_value = {"entities": [], "events": [], "claims": []}
        with patch("world_builder_service.world_builder.httpx.get", return_value=malformed_response):
            try:
                world_builder.fetch_context("malformed-topic")
                raise AssertionError("Malformed Layer 2 context should be rejected")
            except world_builder.WorldBuilderError as error:
                assert error.status_code == 502
                assert error.error == "malformed_layer2_response"
        print("POST /build-world smoke test passed (6 maps, 5 characters, persisted files, reuse verified).")
    finally:
        world_builder.WORLD_BIBLE_DIR = original_directory
        world_builder.generate_fictional_content = original_generation
        shutil.rmtree(temporary_bible, ignore_errors=True)


if __name__ == "__main__":
    main()
