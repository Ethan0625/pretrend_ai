"""Re-export shim - moved to pretrend.observability.regime.horizon.short_engine (P19 / 2026-05-13)."""
import sys
from pretrend.observability.regime.horizon import short_engine as _short_engine
sys.modules[__name__] = _short_engine
