import json
import uuid
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_three_delta_demo_matches_the_golden_graph_shape() -> None:
    topic = load_fixture("topic.json")
    deltas = [
        load_fixture("delta-01-initial.json"),
        load_fixture("delta-02-update.json"),
        load_fixture("delta-03-conflict.json"),
    ]
    expected_ingestions = load_fixture("expected/ingestion-reports.json")
    expected_context = load_fixture("expected/final-context.json")
    expected_timeline = load_fixture("expected/final-timeline.json")
    expected_raw_export = load_fixture("expected/final-raw-export.json")
    topic = deepcopy(topic)
    topic["topic_key"] = f"{topic['topic_key']}-{uuid.uuid4().hex}"
    for delta in deltas:
        delta["topic_key"] = topic["topic_key"]
        delta["package_id"] = str(uuid.uuid4())

    with TestClient(app) as client:
        topic_response = client.post("/topics", json=topic)
        assert topic_response.status_code == 201
        topic_id = topic_response.json()["topic_id"]
        responses = [client.post("/ingestions", json=delta) for delta in deltas]
        context = client.get(f"/topics/{topic_id}/context")
        raw_export = client.get(f"/topics/{topic_id}/raw-export")

    for response, outcome in zip(responses, expected_ingestions["ingestions"], strict=True):
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == outcome["status"]
        assert body["summary"]["created"] == outcome["created"]
        assert body["summary"]["matched"] == outcome["matched"]
        assert body["summary"]["contradictions"] == outcome["contradictions"]

    assert context.status_code == 200
    body = context.json()
    for field, count in expected_context["counts"].items():
        assert len(body[field]) == count
    assert [
        {"label": item["label"], "status": item["status"]}
        for item in body["entities"]
    ] == expected_context["entities"]
    assert sorted(relationship["type"] for relationship in body["relationships"]) == expected_context["relationship_types"]
    assert [
        {"title": item["title"], "start": item["temporal"]["start"]}
        for item in body["timeline"]
    ] == expected_timeline["events"]
    assert [
        {"raw_text": item["raw_text"], "status": item["status"]}
        for item in raw_export.json()["items"]
    ] == expected_raw_export["items"]
    assert {"topic", "timeline", "entities", "events", "claims", "relationships", "disputes", "coverage"}.issubset(body)
    assert [item["event_id"] for item in body["timeline"]] == [item["event_id"] for item in body["events"]]
    assert [item["order"] for item in body["timeline"]] == list(range(1, len(body["events"]) + 1))
    assert body["coverage"]["truncated"] is False
    assert all({"claim_id", "status", "raw_text", "evidence"}.issubset(item) for item in raw_export.json()["items"])
    assert "package_id" not in raw_export.text
    assert "source_id" not in raw_export.text
