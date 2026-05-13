"""Re-export shim - moved to pretrend.observability.regime.horizon.builder (P19 / 2026-05-13)."""
import sys
from pretrend.observability.regime.horizon import builder as _builder
sys.modules[__name__] = _builder
