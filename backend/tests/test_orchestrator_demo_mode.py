"""Orchestrator demo-mode defaults are a foot-gun if they silently change production."""

from uuid import uuid4

import orchestrator_service.main as orchestrator_main
from orchestrator_service.contracts import RunTopicRequest


def test_demo_mode_defaults_narrate_when_omitted(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_topic(topic_id, character_ids, languages, narrate):
        captured["narrate"] = narrate
        from datetime import UTC, datetime

        from orchestrator_service.contracts import RunReport

        return RunReport(
            run_id=uuid4(),
            topic_id=topic_id,
            narrate_requested=narrate,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            world_status="ok",
            blueprint_status="ok",
            characters={},
        )

    monkeypatch.setattr(orchestrator_main, "DEMO_MODE", True)
    monkeypatch.setattr(orchestrator_main, "run_topic", fake_run_topic)
    request = RunTopicRequest(topic_id=uuid4())
    orchestrator_main.run_topic_endpoint(request)
    assert captured["narrate"] is True


def test_demo_mode_respects_explicit_narrate_false(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_topic(topic_id, character_ids, languages, narrate):
        captured["narrate"] = narrate
        from datetime import UTC, datetime

        from orchestrator_service.contracts import RunReport

        return RunReport(
            run_id=uuid4(),
            topic_id=topic_id,
            narrate_requested=narrate,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            world_status="ok",
            blueprint_status="ok",
            characters={},
        )

    monkeypatch.setattr(orchestrator_main, "DEMO_MODE", True)
    monkeypatch.setattr(orchestrator_main, "run_topic", fake_run_topic)
    request = RunTopicRequest(topic_id=uuid4(), narrate=False)
    orchestrator_main.run_topic_endpoint(request)
    assert captured["narrate"] is False
