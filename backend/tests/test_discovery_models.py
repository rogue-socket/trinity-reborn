"""Tests for discovery persistence models."""

from app.models.discovery import DiscoveryRequest, DiscoveryResult


def test_discovery_models_define_request_and_result_tables() -> None:
    assert DiscoveryRequest.__tablename__ == "discovery_requests"
    assert DiscoveryResult.__tablename__ == "discovered_articles"
    assert set(DiscoveryRequest.__table__.columns.keys()) == {
        "id",
        "source_url",
        "status",
        "created_at",
        "completed_at",
    }
    assert set(DiscoveryResult.__table__.columns.keys()) == {
        "id",
        "discovery_request_id",
        "headline",
        "publisher",
        "published_date",
        "url",
    }
