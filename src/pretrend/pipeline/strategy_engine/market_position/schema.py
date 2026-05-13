"""Re-export shim - moved to pretrend.observability.regime.position.schema (P20 / 2026-05-13)."""
import sys
from pretrend.observability.regime.position import schema as _schema
sys.modules[__name__] = _schema
