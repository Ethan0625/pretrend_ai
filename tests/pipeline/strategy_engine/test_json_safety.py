from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from pretrend.pipeline.strategy_engine.json_safety import make_json_safe


def test_make_json_safe_replaces_non_finite_floats() -> None:
    """OFS-003: report payload의 NaN/Inf 값은 JSON 500 장애 전에 null로 낮춘다."""
    payload = {
        "ok": 1.25,
        "nan": float("nan"),
        "inf": float("inf"),
        "nested": [{"neg_inf": float("-inf")}],
    }

    safe = make_json_safe(payload)

    assert safe == {
        "ok": 1.25,
        "nan": None,
        "inf": None,
        "nested": [{"neg_inf": None}],
    }
    json.dumps(safe, allow_nan=False)


def test_make_json_safe_handles_common_boundary_types() -> None:
    payload = {
        "when": date(2026, 5, 16),
        "decimal": Decimal("1.5"),
        "bad_decimal": Decimal("NaN"),
        "tags": {"a", "b"},
        1: "numeric key",
    }

    safe = make_json_safe(payload)

    assert safe["when"] == "2026-05-16"
    assert safe["decimal"] == 1.5
    assert safe["bad_decimal"] is None
    assert sorted(safe["tags"]) == ["a", "b"]
    assert safe["1"] == "numeric key"
    json.dumps(safe, allow_nan=False)


def test_make_json_safe_handles_numpy_like_scalars() -> None:
    class _Scalar:
        def item(self) -> float:
            return float("nan")

    safe = make_json_safe({"value": _Scalar()})

    assert safe == {"value": None}
    json.dumps(safe, allow_nan=False)
