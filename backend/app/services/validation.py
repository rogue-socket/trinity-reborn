from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.policy import EPISTEMIC_STATUSES, relationship_spec


@dataclass
class ValidationResult:
    status: str
    report: dict[str, Any]


REQUIRED_FIELDS = {
    "sources": ("source_id",),
    "articles": ("article_id", "source_id", "content"),
    "evidence": ("evidence_id", "article_id", "excerpt", "start_offset", "end_offset"),
    "entities": ("entity_id", "type", "name"),
    "events": ("event_id", "type", "title"),
    "claims": ("claim_id", "text"),
    "relationships": ("relationship_id", "subject_ref", "object_ref", "source_relation_label"),
}

LOCAL_TYPES = {
    "sources": "source",
    "articles": "article",
    "evidence": "evidence",
    "entities": "entity",
    "events": "event",
    "claims": "claim",
    "relationships": "relationship",
}

TEMPORAL_PRECISIONS = {"exact", "approximate", "day", "month", "range", "unknown"}
TEMPORAL_BASES = {"reported", "inferred"}
def _invalid_temporal(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    if value.get("precision") not in TEMPORAL_PRECISIONS or value.get("basis") not in TEMPORAL_BASES:
        return True
    parsed: dict[str, datetime] = {}
    for field in ("start", "end"):
        if value.get(field) is not None:
            try:
                parsed[field] = datetime.fromisoformat(
                    str(value[field]).replace("Z", "+00:00")
                )
            except ValueError:
                return True
    if value.get("end") is not None and value.get("start") is None:
        return True
    try:
        return "end" in parsed and parsed["end"] < parsed["start"]
    except TypeError:
        return True


def _local_ids(objects: list[dict[str, Any]], field: str) -> set[str]:
    return {str(item[field]) for item in objects if field in item}


def validate_objects(payload: dict[str, Any]) -> ValidationResult:
    object_results: list[dict[str, Any]] = []
    valid_ids: dict[str, set[str]] = {}
    errors_by_object: dict[tuple[str, int], list[str]] = {}

    for collection, required_fields in REQUIRED_FIELDS.items():
        objects = payload.get(collection, [])
        id_field = required_fields[0]
        id_counts = {
            str(item[id_field]): sum(str(other.get(id_field)) == str(item[id_field]) for other in objects)
            for item in objects
            if item.get(id_field) is not None
        }
        for index, item in enumerate(objects):
            errors = [
                f"missing required field: {field}"
                for field in required_fields
                if field not in item
                or item[field] is None
                or isinstance(item[field], str) and not item[field]
            ]
            local_id = str(item.get(id_field, f"{collection}[{index}]"))
            if id_counts.get(local_id, 0) > 1:
                errors.append(f"duplicate local ID: {local_id}")
            if errors:
                errors_by_object[collection, index] = errors
        valid_ids[collection] = {
            str(item[id_field])
            for index, item in enumerate(objects)
            if (collection, index) not in errors_by_object and id_field in item
        }

    reference_collections = ("entities", "events", "claims")
    reference_counts: dict[str, int] = {}
    for collection in reference_collections:
        id_field = REQUIRED_FIELDS[collection][0]
        for item in payload.get(collection, []):
            if item.get(id_field) is not None:
                local_id = str(item[id_field])
                reference_counts[local_id] = reference_counts.get(local_id, 0) + 1
    for collection in reference_collections:
        id_field = REQUIRED_FIELDS[collection][0]
        for index, item in enumerate(payload.get(collection, [])):
            if reference_counts.get(str(item.get(id_field)), 0) > 1:
                errors_by_object.setdefault((collection, index), []).append(
                    f"ambiguous cross-type local ID: {item.get(id_field)}"
                )

    for collection, required_fields in REQUIRED_FIELDS.items():
        id_field = required_fields[0]
        valid_ids[collection] = {
            str(item[id_field])
            for index, item in enumerate(payload.get(collection, []))
            if (collection, index) not in errors_by_object and id_field in item
        }

    source_ids = valid_ids["sources"]
    article_ids = valid_ids["articles"]
    entity_ids = valid_ids["entities"]
    event_ids = valid_ids["events"]
    claim_ids = valid_ids["claims"]
    evidence_ids = valid_ids["evidence"]
    reference_ids = entity_ids | event_ids | claim_ids

    for index, article in enumerate(payload.get("articles", [])):
        if article.get("source_id") not in source_ids:
            errors_by_object.setdefault(("articles", index), []).append("unknown source_id")

    article_ids = _local_ids(
        [
            item
            for index, item in enumerate(payload.get("articles", []))
            if ("articles", index) not in errors_by_object
        ],
        "article_id",
    )

    for index, evidence in enumerate(payload.get("evidence", [])):
        article = next(
            (item for item in payload.get("articles", []) if item.get("article_id") == evidence.get("article_id")),
            None,
        )
        start, end, excerpt = evidence.get("start_offset"), evidence.get("end_offset"), evidence.get("excerpt")
        if article is None or evidence.get("article_id") not in article_ids:
            errors_by_object.setdefault(("evidence", index), []).append("unknown article_id")
        elif not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
            errors_by_object.setdefault(("evidence", index), []).append("invalid evidence offsets")
        elif end > len(article["content"]) or article["content"][start:end] != excerpt:
            errors_by_object.setdefault(("evidence", index), []).append("evidence offsets do not select excerpt")

    evidence_ids = _local_ids(
        [
            item
            for index, item in enumerate(payload.get("evidence", []))
            if ("evidence", index) not in errors_by_object
        ],
        "evidence_id",
    )

    for index, event in enumerate(payload.get("events", [])):
        if "temporal" in event and _invalid_temporal(event["temporal"]):
            errors_by_object.setdefault(("events", index), []).append("invalid temporal value")
        for field in ("participant_entity_ids", "location_entity_ids"):
            unknown = set(event.get(field, [])) - entity_ids
            if unknown:
                errors_by_object.setdefault(("events", index), []).append(f"unknown {field}: {sorted(unknown)}")
        for field, allowed in (("evidence_ids", evidence_ids), ("related_claim_ids", claim_ids)):
            unknown = set(event.get(field, [])) - allowed
            if unknown:
                errors_by_object.setdefault(("events", index), []).append(f"unknown {field}: {sorted(unknown)}")

    for index, claim in enumerate(payload.get("claims", [])):
        if "temporal_scope" in claim and _invalid_temporal(claim["temporal_scope"]):
            errors_by_object.setdefault(("claims", index), []).append("invalid temporal value")
        if claim.get("epistemic_status", "unknown") not in EPISTEMIC_STATUSES:
            errors_by_object.setdefault(("claims", index), []).append(
                "invalid epistemic_status"
            )
        confidence = claim.get("confidence")
        if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            errors_by_object.setdefault(("claims", index), []).append("invalid confidence")
        for field, allowed in (("evidence_ids", evidence_ids),):
            unknown = set(claim.get(field, [])) - allowed
            if unknown:
                errors_by_object.setdefault(("claims", index), []).append(f"unknown {field}: {sorted(unknown)}")
        for field, allowed in (("event_id", event_ids), ("subject_ref", reference_ids), ("asserted_by_entity_id", entity_ids)):
            value = claim.get(field)
            if value is not None and value not in allowed:
                errors_by_object.setdefault(("claims", index), []).append(f"unknown {field}")
        for field in ("corrects_claim_ref", "retracts_claim_ref"):
            value = claim.get(field)
            if value is not None and value not in claim_ids:
                errors_by_object.setdefault(("claims", index), []).append(f"unknown {field}")

    for index, relationship in enumerate(payload.get("relationships", [])):
        for field in ("subject_ref", "object_ref"):
            if relationship.get(field) not in reference_ids:
                errors_by_object.setdefault(("relationships", index), []).append(f"unknown {field}")
        unknown_evidence = set(relationship.get("evidence_ids", [])) - evidence_ids
        if unknown_evidence:
            errors_by_object.setdefault(("relationships", index), []).append(
                f"unknown evidence_ids: {sorted(unknown_evidence)}"
            )
        spec = relationship_spec(str(relationship.get("source_relation_label", "")))
        if spec is not None:
            subject_type = next(
                (kind for kind, ids in (("entity", entity_ids), ("event", event_ids), ("claim", claim_ids)) if relationship.get("subject_ref") in ids),
                None,
            )
            object_type = next(
                (kind for kind, ids in (("entity", entity_ids), ("event", event_ids), ("claim", claim_ids)) if relationship.get("object_ref") in ids),
                None,
            )
            if (
                subject_type not in spec["subject_types"]
                or object_type not in spec["object_types"]
            ):
                errors_by_object.setdefault(("relationships", index), []).append("relationship endpoints violate ontology")

    while True:
        accepted_ids = {
            collection: {
                str(item[required_fields[0]])
                for index, item in enumerate(payload.get(collection, []))
                if (collection, index) not in errors_by_object and required_fields[0] in item
            }
            for collection, required_fields in REQUIRED_FIELDS.items()
        }
        accepted_references = (
            accepted_ids["entities"] | accepted_ids["events"] | accepted_ids["claims"]
        )
        changed = False

        def reject_dependency(
            collection: str, index: int, field: str, local_id: Any
        ) -> None:
            nonlocal changed
            errors_by_object.setdefault((collection, index), []).append(
                f"{field} depends on rejected object: {local_id}"
            )
            changed = True

        for index, event in enumerate(payload.get("events", [])):
            if ("events", index) in errors_by_object:
                continue
            for field in ("participant_entity_ids", "location_entity_ids"):
                rejected = set(event.get(field, [])) - accepted_ids["entities"]
                if rejected:
                    reject_dependency("events", index, field, sorted(rejected))
                    break
            else:
                for field, allowed in (
                    ("evidence_ids", accepted_ids["evidence"]),
                    ("related_claim_ids", accepted_ids["claims"]),
                ):
                    rejected = set(event.get(field, [])) - allowed
                    if rejected:
                        reject_dependency("events", index, field, sorted(rejected))
                        break

        for index, claim in enumerate(payload.get("claims", [])):
            if ("claims", index) in errors_by_object:
                continue
            rejected_evidence = set(claim.get("evidence_ids", [])) - accepted_ids["evidence"]
            if rejected_evidence:
                reject_dependency("claims", index, "evidence_ids", sorted(rejected_evidence))
                continue
            for field, allowed in (
                ("event_id", accepted_ids["events"]),
                ("subject_ref", accepted_references),
                ("asserted_by_entity_id", accepted_ids["entities"]),
                ("corrects_claim_ref", accepted_ids["claims"]),
                ("retracts_claim_ref", accepted_ids["claims"]),
            ):
                local_id = claim.get(field)
                if local_id is not None and local_id not in allowed:
                    reject_dependency("claims", index, field, local_id)
                    break

        for index, relationship in enumerate(payload.get("relationships", [])):
            if ("relationships", index) in errors_by_object:
                continue
            for field in ("subject_ref", "object_ref"):
                local_id = relationship.get(field)
                if local_id not in accepted_references:
                    reject_dependency("relationships", index, field, local_id)
                    break
            else:
                rejected_evidence = (
                    set(relationship.get("evidence_ids", [])) - accepted_ids["evidence"]
                )
                if rejected_evidence:
                    reject_dependency(
                        "relationships", index, "evidence_ids", sorted(rejected_evidence)
                    )

        if not changed:
            break

    warnings_by_object: dict[tuple[str, int], list[str]] = {}
    for collection in ("claims", "relationships"):
        for index, item in enumerate(payload.get(collection, [])):
            if not item.get("evidence_ids"):
                warnings_by_object[collection, index] = [
                    "no evidence_ids supplied; high-confidence promotion is disabled"
                ]

    for collection, required_fields in REQUIRED_FIELDS.items():
        id_field = required_fields[0]
        for index, item in enumerate(payload.get(collection, [])):
            errors = errors_by_object.get((collection, index), [])
            warnings = [] if errors else warnings_by_object.get((collection, index), [])
            object_results.append(
                {
                    "local_type": LOCAL_TYPES[collection],
                    "local_id": item.get(id_field),
                    "status": (
                        "rejected"
                        if errors
                        else "accepted_with_warnings"
                        if warnings
                        else "accepted"
                    ),
                    "errors": errors,
                    "warnings": warnings,
                }
            )

    accepted = sum(result["status"] != "rejected" for result in object_results)
    rejected = len(object_results) - accepted
    report_warnings = [
        {
            "local_type": result["local_type"],
            "local_id": result["local_id"],
            "message": warning,
        }
        for result in object_results
        for warning in result["warnings"]
    ]
    status = (
        "rejected"
        if not accepted
        else "partially_accepted"
        if rejected
        else "accepted_with_warnings"
        if report_warnings
        else "accepted"
    )
    return ValidationResult(
        status=status,
        report={
            "summary": {
                "accepted": accepted,
                "rejected": rejected,
                "created": 0,
                "matched": 0,
                "possible_matches": 0,
                "contradictions": 0,
            },
            "object_results": object_results,
            "warnings": report_warnings,
            "errors": [],
        },
    )
