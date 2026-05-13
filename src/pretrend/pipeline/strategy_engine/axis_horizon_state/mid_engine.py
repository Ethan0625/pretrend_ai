"""Re-export shim - moved to pretrend.observability.regime.horizon.mid_engine (P19 / 2026-05-13)."""
import sys
from pretrend.observability.regime.horizon import mid_engine as _mid_engine
sys.modules[__name__] = _mid_engine
