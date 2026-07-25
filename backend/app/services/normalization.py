import re
import unicodedata
from typing import Any, TypeGuard


def normalize_text(value: str) -> str:
    compatible = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", compatible).split())


def _text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = normalize_text(str(value))
    return normalized or None


def normalize_claim_value(value: Any, temporal_scope: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") != "quantity":
        return {"type": "literal", "value": value}

    raw_bounds = value.get("bounds")
    bounds: dict[str, Any] = raw_bounds if isinstance(raw_bounds, dict) else {}
    return {
        "type": "quantity",
        "original_text": str(value.get("original_text", "")),
        "value": value.get("value"),
        "unit": _text(value.get("unit")),
        "currency": str(value["currency"]).upper() if value.get("currency") else None,
        "lower_bound": value.get("lower_bound", bounds.get("lower")),
        "upper_bound": value.get("upper_bound", bounds.get("upper")),
        "approximate": bool(value.get("approximate", False)),
        "population": _text(value.get("population")),
        "measurement_scope": _text(value.get("measurement_scope")),
        "temporal_scope": temporal_scope,
    }


def claim_values_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("type") != "quantity" or right.get("type") != "quantity":
        return left.get("type") == right.get("type") and left != right

    same_currency = left.get("currency") is not None and left.get("currency") == right.get("currency")
    same_unit = left.get("unit") is not None and left.get("unit") == right.get("unit")
    if not (same_currency or same_unit):
        return False
    if (
        left.get("population") is None
        or left.get("population") != right.get("population")
        or left.get("measurement_scope") is None
        or left.get("measurement_scope") != right.get("measurement_scope")
    ):
        return False

    left_interval = _quantity_interval(left)
    right_interval = _quantity_interval(right)
    if left_interval is None or right_interval is None:
        return False
    return left_interval[1] < right_interval[0] or right_interval[1] < left_interval[0]


def _quantity_interval(value: dict[str, Any]) -> tuple[float, float] | None:
    lower = value.get("lower_bound")
    upper = value.get("upper_bound")
    if lower is not None or upper is not None:
        if not _number(lower) or not _number(upper) or lower > upper:
            return None
        return float(lower), float(upper)
    exact = value.get("value")
    if value.get("approximate") or not _number(exact):
        return None
    return float(exact), float(exact)


def _number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
