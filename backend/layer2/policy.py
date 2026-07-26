import re
import unicodedata
from typing import Any


PIPELINE_VERSION = "kg-pipeline-0.2"
GRAPH_MODEL_VERSION = "kg-model-0.1"
ONTOLOGY_VERSION = "kg-ontology-0.2"
RECONCILIATION_POLICY_VERSION = "exhaustive-v3"
CANDIDATE_LIMIT: None = None
THRESHOLDS = {
    "entity_auto_resolve": 0.90,
    "event_auto_resolve": 0.92,
    "possible_match": 0.70,
    "contradiction_confirmation": 0.90,
}

ENTITY_TYPES = frozenset(
    {
        "person",
        "organization",
        "government_body",
        "government_agency",
        "military_unit",
        "armed_group",
        "political_party",
        "community_group",
        "media_outlet",
        "international_organization",
        "country",
        "administrative_region",
        "city_or_locality",
        "neighborhood",
        "geographic_feature",
        "facility_or_site",
        "border_or_route",
        "document",
        "law_or_policy",
        "court_case",
        "agreement",
        "infrastructure",
        "vehicle_or_equipment",
        "weapon_system",
        "digital_account_or_channel",
        "unknown",
    }
)

EPISTEMIC_STATUSES = frozenset(
    {
        "observed",
        "reported",
        "attributed",
        "corroborated",
        "disputed",
        "inferred",
        "interpretive",
        "unknown",
        "retracted",
        "superseded",
    }
)


def canonical_entity_type(source_type: str) -> str:
    normalized = source_type.casefold().strip()
    return normalized if normalized in ENTITY_TYPES else "unknown"


def _relation(
    subject_types: set[str],
    object_types: set[str],
    *,
    inverse: str | None = None,
    symmetric: bool = False,
    transitive: bool = False,
    may_infer: bool = False,
    evidence_requirement: str = "required_for_high_confidence",
    temporal_behavior: str = "scoped",
    source_labels: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "subject_types": frozenset(subject_types),
        "object_types": frozenset(object_types),
        "inverse": inverse,
        "symmetric": symmetric,
        "transitive": transitive,
        "may_infer": may_infer,
        "evidence_requirement": evidence_requirement,
        "temporal_behavior": temporal_behavior,
        "source_labels": source_labels,
    }


_GRAPH_TYPES = {"entity", "event", "claim"}
RELATIONSHIP_ONTOLOGY = {
    "PARTICIPATED_IN": _relation({"entity"}, {"event"}, source_labels=("participated in",)),
    "ORGANIZED": _relation({"entity"}, {"event"}, source_labels=("organized",)),
    "ANNOUNCED": _relation({"entity"}, {"event", "claim"}, source_labels=("announced",)),
    "RESPONDED_TO": _relation(
        {"entity", "event"}, _GRAPH_TYPES, source_labels=("responded to",)
    ),
    "AFFECTED_BY": _relation(_GRAPH_TYPES, _GRAPH_TYPES, source_labels=("affected by",)),
    "LOCATED_AT": _relation({"event"}, {"entity"}, source_labels=("located at",)),
    "TARGETED": _relation(
        {"entity", "event"}, {"entity", "event"}, source_labels=("targeted",)
    ),
    "REPRESENTED_BY": _relation({"entity"}, {"entity"}, source_labels=("represented by",)),
    "BEFORE": _relation(
        {"event"},
        {"event"},
        inverse="AFTER",
        transitive=True,
        may_infer=True,
        temporal_behavior="event_time",
        source_labels=("before",),
    ),
    "AFTER": _relation(
        {"event"},
        {"event"},
        inverse="BEFORE",
        transitive=True,
        may_infer=True,
        temporal_behavior="event_time",
        source_labels=("after",),
    ),
    "DURING": _relation(
        {"event"},
        {"event"},
        may_infer=True,
        temporal_behavior="event_time",
        source_labels=("during",),
    ),
    "PART_OF": _relation(
        {"event"},
        {"event"},
        transitive=True,
        temporal_behavior="event_time",
        source_labels=("part of",),
    ),
    "FOLLOWS": _relation(
        {"event", "claim"},
        {"event", "claim"},
        may_infer=True,
        temporal_behavior="event_time",
        source_labels=("follows",),
    ),
    "RESPONDS_TO": _relation({"event"}, {"event"}, source_labels=("responds to",)),
    "ESCALATES": _relation({"event"}, {"event"}, source_labels=("escalates",)),
    "DEESCALATES": _relation({"event"}, {"event"}, source_labels=("deescalates",)),
    "CONTRIBUTES_TO": _relation({"event"}, {"event"}, source_labels=("contributes to",)),
    "SUPPORTS": _relation({"claim"}, {"claim"}, source_labels=("supports",)),
    "CONTRADICTS": _relation(
        {"claim"}, {"claim"}, symmetric=True, source_labels=("contradicts",)
    ),
    "CLARIFIES": _relation({"claim"}, {"claim"}, source_labels=("clarifies",)),
    "CORRECTS": _relation({"claim"}, {"claim"}, source_labels=("corrects",)),
    "RETRACTS": _relation({"claim"}, {"claim"}, source_labels=("retracts",)),
    "SUPERSEDES": _relation({"claim"}, {"claim"}, source_labels=("supersedes",)),
    "DUPLICATES": _relation(
        _GRAPH_TYPES,
        _GRAPH_TYPES,
        symmetric=True,
        may_infer=True,
        source_labels=("duplicates",),
    ),
    "SAME_AS": _relation(
        _GRAPH_TYPES,
        _GRAPH_TYPES,
        symmetric=True,
        transitive=True,
        source_labels=("same as",),
    ),
    "POSSIBLY_SAME_AS": _relation(
        _GRAPH_TYPES,
        _GRAPH_TYPES,
        symmetric=True,
        may_infer=True,
        evidence_requirement="derived_signals_allowed",
        source_labels=("possibly same as",),
    ),
    "ALIAS_OF": _relation({"entity"}, {"entity"}, source_labels=("alias of",)),
    "SUBSET_OF": _relation(
        {"entity"}, {"entity"}, transitive=True, source_labels=("subset of",)
    ),
    "RELATED_TO": _relation(
        _GRAPH_TYPES,
        _GRAPH_TYPES,
        symmetric=True,
        source_labels=("related to",),
    ),
}


def _relationship_label(value: str) -> str:
    compatible = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[_\W]+", " ", compatible).split())


def relationship_type_for_label(source_label: str) -> str | None:
    normalized = _relationship_label(source_label)
    for relationship_type, spec in RELATIONSHIP_ONTOLOGY.items():
        labels = {
            _relationship_label(relationship_type),
            *(_relationship_label(label) for label in spec["source_labels"]),
        }
        if normalized in labels:
            return relationship_type
    return None


def relationship_spec(source_label: str) -> dict[str, Any] | None:
    relationship_type = relationship_type_for_label(source_label)
    return RELATIONSHIP_ONTOLOGY.get(relationship_type) if relationship_type else None
