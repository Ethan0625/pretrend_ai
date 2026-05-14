"""Re-export shim - moved to pretrend.observability.explainability.legacy_report.context (P27-0)."""
from pretrend.observability.explainability.legacy_report import context as _legacy

globals().update({name: value for name, value in vars(_legacy).items() if not name.startswith("__")})


def generate_llm_analysis(*args, **kwargs):
    for name in (
        "generate_report_via_analyzer",
        "_get_report_ollama_client",
        "_call_gemini",
    ):
        if name in globals():
            setattr(_legacy, name, globals()[name])
    return _legacy.generate_llm_analysis(*args, **kwargs)


__all__ = [name for name in globals() if not name.startswith("__") and name != "_legacy"]
