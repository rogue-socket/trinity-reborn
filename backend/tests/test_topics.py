import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.main import app
from app.models import TopicLifecycleTransition


def test_registers_a_layer_2_owned_topic() -> None:
    topic_key = f"example-topic-{uuid.uuid4().hex}"
    payload = {
        "topic_key": topic_key,
        "display_name": "Example bounded situation",
        "scope": {
            "description": "A bounded implementation test topic.",
            "geography": ["Example City"],
            "start": "2026-07-01",
            "end": None,
        },
    }

    with TestClient(app) as client:
        response = client.post("/topics", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["topic_key"] == topic_key
    assert body["status"] == "active"
    assert body["topic_id"]


def test_lists_registered_topics() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/topics",
            json={
                "topic_key": f"list-topic-{uuid.uuid4().hex}",
                "display_name": "Listed topic",
                "scope": {
                    "description": "A bounded implementation test topic.",
                    "geography": [],
                    "start": "2026-07-01",
                    "end": None,
                },
            },
        )
        topics = client.get("/topics")

    assert topics.status_code == 200
    body = topics.json()
    assert created.json()["topic_id"] in {topic["topic_id"] for topic in body}
    listed = next(topic for topic in body if topic["topic_id"] == created.json()["topic_id"])
    assert listed["display_name"] == "Listed topic"


def test_paginates_the_topic_list() -> None:
    with TestClient(app) as client:
        created_ids = []
        for index in range(3):
            response = client.post(
                "/topics",
                json={
                    "topic_key": f"page-topic-{index}-{uuid.uuid4().hex}",
                    "display_name": f"Page topic {index}",
                    "scope": {
                        "description": "A bounded implementation test topic.",
                        "geography": [],
                        "start": "2026-07-01",
                        "end": None,
                    },
                },
            )
            assert response.status_code == 201
            created_ids.append(response.json()["topic_id"])

        page = client.get("/topics", params={"limit": 2, "offset": 0})
        next_page = client.get("/topics", params={"limit": 2, "offset": 2})

    assert page.status_code == 200
    assert len(page.json()) == 2
    assert int(page.headers["X-Total-Count"]) >= 3
    assert len(next_page.json()) >= 1
    assert {topic["topic_id"] for topic in page.json()}.isdisjoint(
        {topic["topic_id"] for topic in next_page.json()}
    )


def test_records_topic_lifecycle_transitions_and_allows_reopening() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/topics",
            json={
                "topic_key": f"lifecycle-topic-{uuid.uuid4().hex}",
                "display_name": "Lifecycle topic",
                "scope": {
                    "description": "A bounded lifecycle test topic.",
                    "geography": [],
                    "start": "2026-07-01",
                    "end": None,
                },
            },
        )
        topic_id = created.json()["topic_id"]
        closed = client.post(
            f"/topics/{topic_id}/lifecycle",
            json={"status": "closed", "reason": "Coverage is complete."},
        )
        reopened = client.post(
            f"/topics/{topic_id}/lifecycle",
            json={"status": "active", "reason": "New reporting requires monitoring."},
        )

    assert closed.status_code == 200
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "active"
    with Session(get_engine()) as session:
        transitions = list(
            session.scalars(
                select(TopicLifecycleTransition)
                .where(TopicLifecycleTransition.topic_id == uuid.UUID(topic_id))
                .order_by(TopicLifecycleTransition.created_at)
            )
        )
    assert [(item.from_status, item.to_status, item.reason) for item in transitions] == [
        ("active", "closed", "Coverage is complete."),
        ("closed", "active", "New reporting requires monitoring."),
    ]


def test_rejects_invalid_topic_lifecycle_status() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/topics",
            json={
                "topic_key": f"invalid-lifecycle-{uuid.uuid4().hex}",
                "display_name": "Invalid lifecycle topic",
                "scope": {
                    "description": "A bounded lifecycle test topic.",
                    "geography": [],
                    "start": "2026-07-01",
                    "end": None,
                },
            },
        )
        response = client.post(
            f"/topics/{created.json()['topic_id']}/lifecycle",
            json={"status": "paused", "reason": "Not a supported lifecycle state."},
        )

    assert response.status_code == 422


def test_new_package_reopens_a_closed_topic_with_an_audit_record() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/topics",
            json={
                "topic_key": f"reopen-topic-{uuid.uuid4().hex}",
                "display_name": "Reopened topic",
                "scope": {"description": "A bounded lifecycle test topic.", "geography": [], "start": "2026-07-01"},
            },
        )
        topic_id = created.json()["topic_id"]
        closed = client.post(f"/topics/{topic_id}/lifecycle", json={"status": "closed", "reason": "Initial coverage complete."})
        reopened = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0", "package_id": str(uuid.uuid4()), "topic_key": created.json()["topic_key"],
                "metadata": {"title": "New reporting", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [{"source_id": "src-1"}], "articles": [], "evidence": [], "entities": [], "events": [], "claims": [],
            },
        )

    assert closed.status_code == 200
    assert reopened.status_code == 201
    with Session(get_engine()) as session:
        transitions = list(
            session.scalars(
                select(TopicLifecycleTransition)
                .where(TopicLifecycleTransition.topic_id == uuid.UUID(topic_id))
                .order_by(TopicLifecycleTransition.created_at)
            )
        )
    assert [(item.from_status, item.to_status, item.reason) for item in transitions] == [
        ("active", "closed", "Initial coverage complete."),
        ("closed", "active", "New Layer 1 package received."),
    ]
    assert transitions[0].ingestion_id is None
    assert transitions[1].ingestion_id == uuid.UUID(reopened.json()["ingestion_id"])
