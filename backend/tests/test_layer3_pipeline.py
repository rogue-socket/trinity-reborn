"""The Layer 2 to Layer 3 seam, exercised without any API keys.

Only the model call is faked. The context fetch, role assignment, fictionalisation
guard, persistence, and blueprint assembly all run for real, so a regression in the
context contract fails here rather than at demo time.
"""

import json
import uuid
from collections import Counter
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

import blueprint_assembler_service.assembler as assembler
import world_builder_service.world_builder as world_builder
from app.main import app as layer2_app
from world_builder_service.contracts import (
    CharacterDraft,
    EmotionState,
    EntityMapDraft,
    GenerationPayload,
)


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_CONTEXT = Path(__file__).resolve().parents[2] / "prds" / "fixture-topic-context.json"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FakeModel:
    """Stands in for OpenAI, echoing back exactly the entries the world builder asked for."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, context, entities_for_map, characters_to_add, roles) -> GenerationPayload:
        self.calls += 1
        return GenerationPayload(
            world_name="The Lantern Coast",
            entity_map=[
                EntityMapDraft(
                    source_entity_id=entity["entity_id"],
                    fictional_name=f"Fictional {entity['entity_id']}",
                    fictional_type=(
                        "place" if entity.get("type") not in world_builder.CHARACTER_ENTITY_TYPES else "faction"
                    ),
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


@pytest.fixture
def artefacts(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(world_builder, "WORLD_BIBLE_DIR", tmp_path / "world_bible")
    monkeypatch.setattr(assembler, "WORLD_BIBLE_DIR", tmp_path / "world_bible")
    monkeypatch.setattr(assembler, "BLUEPRINT_DIR", tmp_path / "blueprints")
    return tmp_path


@pytest.fixture
def model(monkeypatch) -> FakeModel:
    fake = FakeModel()
    monkeypatch.setattr(world_builder, "generate_fictional_content", fake)
    return fake


@pytest.fixture
def seeded_topic_id(monkeypatch) -> str:
    """Serve the golden three-delta graph over the same call the services make in production."""
    topic = deepcopy(load_fixture("topic.json"))
    topic["topic_key"] = f"{topic['topic_key']}-{uuid.uuid4().hex}"
    deltas = [
        load_fixture("delta-01-initial.json"),
        load_fixture("delta-02-update.json"),
        load_fixture("delta-03-conflict.json"),
    ]
    for delta in deltas:
        delta["topic_key"] = topic["topic_key"]
        delta["package_id"] = str(uuid.uuid4())

    with TestClient(layer2_app) as client:
        topic_response = client.post("/topics", json=topic)
        assert topic_response.status_code == 201
        topic_id = topic_response.json()["topic_id"]
        for delta in deltas:
            assert client.post("/ingestions", json=delta).status_code == 201

        monkeypatch.setattr(httpx, "get", lambda url, **_: client.get(urlsplit(url).path))
        yield topic_id


@pytest.fixture
def demo_topic_id(monkeypatch) -> str:
    """Serve the richer demo corpus, which casts a full ensemble rather than one character."""
    topic = deepcopy(load_fixture("demo/topic.json"))
    topic["topic_key"] = f"{topic['topic_key']}-{uuid.uuid4().hex}"
    deltas = [
        load_fixture("demo/delta-01-initial.json"),
        load_fixture("demo/delta-02-escalation.json"),
        load_fixture("demo/delta-03-denial.json"),
    ]
    for delta in deltas:
        delta["topic_key"] = topic["topic_key"]
        delta["package_id"] = str(uuid.uuid4())

    with TestClient(layer2_app) as client:
        topic_response = client.post("/topics", json=topic)
        assert topic_response.status_code == 201
        topic_id = topic_response.json()["topic_id"]
        for delta in deltas:
            response = client.post("/ingestions", json=delta)
            assert response.status_code == 201
            assert response.json()["summary"]["rejected"] == 0, response.json()

        monkeypatch.setattr(httpx, "get", lambda url, **_: client.get(urlsplit(url).path))
        yield topic_id


@pytest.fixture
def fixture_topic_id(monkeypatch) -> str:
    context = json.loads(FIXTURE_CONTEXT.read_text())
    monkeypatch.setattr(httpx, "get", lambda url, **_: httpx.Response(200, json=context))
    return context["topic"]["topic_id"]


def test_the_golden_graph_becomes_a_blueprint(seeded_topic_id, artefacts, model) -> None:
    world = world_builder.build_world(seeded_topic_id)
    assert model.calls == 1
    assert world.characters.root, "the graph's political party should be castable"

    blueprint = assembler.assemble_blueprint(seeded_topic_id)
    assert blueprint.perspectives_to_generate, "the orchestrator iterates this to generate episodes"
    assert blueprint.timeline, "the golden corpus contains an event"
    assert blueprint.central_conflict


def test_a_graph_contradiction_survives_as_a_plot_thread(seeded_topic_id, artefacts, model) -> None:
    world_builder.build_world(seeded_topic_id)
    blueprint = assembler.assemble_blueprint(seeded_topic_id)

    assert blueprint.disputed_threads, "the third delta contradicts the second"
    thread = blueprint.disputed_threads[0]
    assert thread.description
    assert thread.use_as == "plot tension, not resolved fact"


def test_the_blueprint_never_repeats_the_real_topic(seeded_topic_id, artefacts, model) -> None:
    world_builder.build_world(seeded_topic_id)
    blueprint = assembler.assemble_blueprint(seeded_topic_id)

    rendered = json.dumps(blueprint.model_dump(mode="json")).casefold()
    assert "labour party" not in rendered
    assert "uk general election results" not in rendered, (
        "the real event title reached the blueprint; it names a real country and contest "
        "that no entity label covers, so scrubbing entity names out of it is not enough"
    )
    for character in blueprint.characters:
        assert character.name.startswith("Character ")


def test_the_demo_corpus_casts_an_ensemble_with_opposed_leads(demo_topic_id, artefacts, model) -> None:
    result = world_builder.build_world(demo_topic_id)
    characters = result.characters.root

    assert len(characters) == 5, "the capital city is a place; the other five are castable"
    roles = Counter(character.role for character in characters.values())
    assert roles["protagonist"] == 1
    assert roles["antagonist"] == 1, (
        "without an antagonist the story has no opposition; the dispute must name both sides"
    )

    blueprint = assembler.assemble_blueprint(demo_topic_id)
    assert len(blueprint.timeline) == 3, "allegations, organising, then the march"
    assert blueprint.disputed_threads, "the ministry's denial contradicts the leak claim"
    assert len(blueprint.perspectives_to_generate) == 5, "one episode per character"


def test_the_demo_blueprint_does_not_name_the_real_actors(demo_topic_id, artefacts, model) -> None:
    world_builder.build_world(demo_topic_id)
    blueprint = assembler.assemble_blueprint(demo_topic_id)

    rendered = json.dumps(blueprint.model_dump(mode="json")).casefold()
    for label in (
        "student demonstrators",
        "education ministry",
        "city police",
        "opposition coalition",
        "independent news desk",
        "capital city",
        "parliament",
        "india",
    ):
        assert label not in rendered, f"the real label {label!r} reached the blueprint"


def test_roles_are_assigned_from_claims_and_disputes(fixture_topic_id, artefacts, model) -> None:
    result = world_builder.build_world(fixture_topic_id)

    assert len(result.world.entity_map) == 6
    characters = result.characters.root
    assert len(characters) == 5, "the locality is a place, not a character"
    by_role = {character.role: character.source_entity_id for character in characters.values()}
    assert by_role["protagonist"] == "ent_001", "the protagonist is the most-claimed entity"
    assert by_role["antagonist"] == "ent_003", "the antagonist opposes it in the recorded dispute"


def test_an_existing_world_is_reused_rather_than_regenerated(fixture_topic_id, artefacts, model) -> None:
    first = world_builder.build_world(fixture_topic_id)
    directory = artefacts / "world_bible" / fixture_topic_id
    assert (directory / "world.json").exists()
    assert (directory / "characters.json").exists()

    second = world_builder.build_world(fixture_topic_id)
    assert model.calls == 1, "a second build must not spend another model call"
    assert second.world.world_id == first.world.world_id


def test_a_context_missing_collections_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **_: httpx.Response(200, json={"entities": [], "events": [], "claims": []}),
    )
    with pytest.raises(world_builder.WorldBuilderError) as error:
        world_builder.fetch_context("malformed-topic")
    assert error.value.status_code == 502
    assert error.value.error == "malformed_layer2_response"
