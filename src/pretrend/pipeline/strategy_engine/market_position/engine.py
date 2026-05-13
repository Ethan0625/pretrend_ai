"""Re-export shim - moved to pretrend.observability.regime.position.engine (P20 / 2026-05-13)."""
import sys
from pretrend.observability.regime.position import engine as _engine
sys.modules[__name__] = _engine
