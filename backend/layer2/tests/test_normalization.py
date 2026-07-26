from backend.layer2.services.normalization import claim_values_conflict, normalize_claim_value


def test_overlapping_quantity_ranges_are_not_contradictions() -> None:
    scope = {"start": "2026-07-20", "precision": "day", "basis": "reported"}
    first = normalize_claim_value(
        {
            "type": "quantity",
            "original_text": "about 500 people",
            "value": 500,
            "unit": "people",
            "bounds": {"lower": 450, "upper": 550},
            "approximate": True,
            "population": "displaced residents",
            "measurement_scope": "individual people",
        },
        scope,
    )
    second = normalize_claim_value(
        {
            "type": "quantity",
            "original_text": "between 525 and 600 people",
            "unit": " PEOPLE ",
            "lower_bound": 525,
            "upper_bound": 600,
            "population": "Displaced Residents",
            "measurement_scope": "Individual People",
        },
        scope,
    )

    assert first["original_text"] == "about 500 people"
    assert first["temporal_scope"] == scope
    assert claim_values_conflict(first, second) is False
