"""Re-export shim - moved to pretrend.observability.regime.horizon.long_engine (P19 / 2026-05-13)."""
import sys
from pretrend.observability.regime.horizon import long_engine as _long_engine
sys.modules[__name__] = _long_engine
