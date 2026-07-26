from backend.layer2.policy import (
    CANDIDATE_LIMIT,
    ONTOLOGY_VERSION,
    PIPELINE_VERSION,
    RECONCILIATION_POLICY_VERSION,
    RELATIONSHIP_ONTOLOGY,
    THRESHOLDS,
)


def test_reconciliation_policy_and_relationship_ontology_are_versioned() -> None:
    assert PIPELINE_VERSION == "kg-pipeline-0.2"
    assert RECONCILIATION_POLICY_VERSION == "exhaustive-v3"
    assert ONTOLOGY_VERSION == "kg-ontology-0.2"
    assert CANDIDATE_LIMIT is None
    assert THRESHOLDS == {
        "entity_auto_resolve": 0.90,
        "event_auto_resolve": 0.92,
        "possible_match": 0.70,
        "contradiction_confirmation": 0.90,
    }
    assert {
        "PARTICIPATED_IN",
        "ORGANIZED",
        "ANNOUNCED",
        "RESPONDED_TO",
        "AFFECTED_BY",
        "LOCATED_AT",
        "TARGETED",
        "REPRESENTED_BY",
        "BEFORE",
        "AFTER",
        "DURING",
        "PART_OF",
        "FOLLOWS",
        "RESPONDS_TO",
        "ESCALATES",
        "DEESCALATES",
        "CONTRIBUTES_TO",
        "SUPPORTS",
        "CONTRADICTS",
        "CLARIFIES",
        "CORRECTS",
        "RETRACTS",
        "SUPERSEDES",
        "DUPLICATES",
        "SAME_AS",
        "POSSIBLY_SAME_AS",
        "ALIAS_OF",
        "SUBSET_OF",
        "RELATED_TO",
    } == set(RELATIONSHIP_ONTOLOGY)
    assert all(
        {
            "subject_types",
            "object_types",
            "inverse",
            "symmetric",
            "transitive",
            "may_infer",
            "evidence_requirement",
            "temporal_behavior",
            "source_labels",
        }.issubset(spec)
        for spec in RELATIONSHIP_ONTOLOGY.values()
    )
