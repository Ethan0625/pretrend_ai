"""Re-export shim - moved to pretrend.observability.explainability.legacy_report.analyzer (P27-0)."""
from pretrend.observability.explainability.legacy_report import analyzer as _legacy

globals().update({name: value for name, value in vars(_legacy).items() if not name.startswith("__")})
__all__ = [name for name in globals() if not name.startswith("__") and name != "_legacy"]
