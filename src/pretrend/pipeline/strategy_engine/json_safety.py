from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def make_json_safe(value: Any) -> Any:
    """Return a JSON-compliant copy of a nested payload.

    The Airflow `requests.post(json=...)` path uses `allow_nan=False`, so any
    NaN/Infinity inside nested report payloads must be normalized before the
    request body is prepared.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, Decimal):
        as_float = float(value)
        return as_float if math.isfinite(as_float) else None

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Mapping):
        return {str(key): make_json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set, frozenset)):
        return [make_json_safe(item) for item in value]

    # numpy scalar values expose `.item()`; keep this optional to avoid adding
    # numpy as an import requirement for this small boundary helper.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return make_json_safe(item())
        except Exception:
            pass

    # pandas.NA and similar sentinels are not JSON-serializable and may raise
    # on boolean checks; stringifying them is less useful than omitting value.
    if type(value).__module__.startswith("pandas."):
        return None

    return str(value)
