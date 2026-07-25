import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import (
    ArticleVersion,
    ClaimMention,
    EntityMention,
    EventMention,
    EvidenceMention,
    RawPackage,
    RelationshipMention,
    SourceMention,
    TopicAnnotation,
)


def persist_accepted_mentions(
    session: Session, raw_package: RawPackage, payload: dict[str, Any], report: dict[str, Any]
) -> None:
    accepted = {
        (result["local_type"], result["local_id"])
        for result in report["object_results"]
        if result["status"] in {"accepted", "accepted_with_warnings"}
    }

    sources: dict[str, SourceMention] = {}
    for item in payload.get("sources", []):
        if ("source", item["source_id"]) not in accepted:
            continue
        source = SourceMention(raw_package_id=raw_package.id, local_id=item["source_id"], payload=item)
        session.add(source)
        sources[item["source_id"]] = source
    session.flush()

    articles: dict[str, ArticleVersion] = {}
    for item in payload.get("articles", []):
        if ("article", item["article_id"]) not in accepted:
            continue
        canonical_url = item.get("canonical_url") or item.get("url")
        source_payload = sources[item["source_id"]].payload
        publisher = source_payload.get("publisher") or source_payload.get("publisher_name")
        published_at = item.get("published_at") or source_payload.get("published_at")
        fingerprint_fields = {
            "publisher": publisher,
            "canonical_url": canonical_url,
            "published_at": published_at,
        }
        article_fingerprint = (
            hashlib.sha256(
                json.dumps(
                    fingerprint_fields, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            if any(fingerprint_fields.values())
            else None
        )
        content_hash = hashlib.sha256(item["content"].encode()).hexdigest()
        previous = None
        if article_fingerprint:
            previous = session.scalar(
                select(ArticleVersion)
                .join(RawPackage, RawPackage.id == ArticleVersion.raw_package_id)
                .where(ArticleVersion.article_fingerprint == article_fingerprint)
                .order_by(RawPackage.received_at.desc(), ArticleVersion.id.desc())
            )
        article = ArticleVersion(
            raw_package_id=raw_package.id,
            source_mention_id=sources[item["source_id"]].id,
            canonical_url=canonical_url,
            previous_version_id=(
                previous.id if previous and previous.content_hash != content_hash else None
            ),
            duplicate_of_id=(
                previous.id if previous and previous.content_hash == content_hash else None
            ),
            article_fingerprint=article_fingerprint,
            local_id=item["article_id"],
            content_hash=content_hash,
            content=item["content"],
            payload=item,
        )
        session.add(article)
        articles[item["article_id"]] = article
    session.flush()

    for item in payload.get("evidence", []):
        if ("evidence", item["evidence_id"]) not in accepted:
            continue
        session.add(
            EvidenceMention(
                raw_package_id=raw_package.id,
                article_version_id=articles[item["article_id"]].id,
                local_id=item["evidence_id"],
                excerpt=item["excerpt"],
                start_offset=item["start_offset"],
                end_offset=item["end_offset"],
                payload=item,
            )
        )

    for item in payload.get("entities", []):
        if ("entity", item["entity_id"]) in accepted:
            session.add(
                EntityMention(
                    raw_package_id=raw_package.id,
                    local_id=item["entity_id"],
                    label=item["name"],
                    source_type=item["type"],
                    payload=item,
                )
            )

    for item in payload.get("events", []):
        if ("event", item["event_id"]) in accepted:
            session.add(
                EventMention(
                    raw_package_id=raw_package.id,
                    local_id=item["event_id"],
                    original_title=item["title"],
                    original_description=item.get("description"),
                    payload=item,
                )
            )

    for item in payload.get("claims", []):
        if ("claim", item["claim_id"]) in accepted:
            session.add(
                ClaimMention(
                    raw_package_id=raw_package.id,
                    local_id=item["claim_id"],
                    original_text=item["text"],
                    payload=item,
                )
            )

    for item in payload.get("relationships", []):
        if ("relationship", item["relationship_id"]) in accepted:
            session.add(
                RelationshipMention(
                    raw_package_id=raw_package.id,
                    local_id=item["relationship_id"],
                    payload=item,
                )
            )

    for kind in ("uncertainties", "themes", "sentiment"):
        for item in payload.get(kind, []):
            if isinstance(item, dict):
                session.add(
                    TopicAnnotation(
                        topic_id=raw_package.topic_id,
                        raw_package_id=raw_package.id,
                        kind=kind,
                        payload=item,
                    )
                )
