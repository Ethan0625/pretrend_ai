"""Re-export shim - moved to pretrend.observability.regime.horizon.schema (P19 / 2026-05-13)."""
import sys
from pretrend.observability.regime.horizon import schema as _schema
sys.modules[__name__] = _schema
