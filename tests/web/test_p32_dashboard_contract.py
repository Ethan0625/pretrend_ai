from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = ROOT / "apps" / "web" / "src"


def _read(relative_path: str) -> str:
    return (WEB_SRC / relative_path).read_text(encoding="utf-8")


def test_regime_timeline_uses_real_feature_fields() -> None:
    regime_page = _read("pages/Regime.tsx")
    timeline_chart = _read("charts/RegimeTimeline.tsx")

    assert "buildRegimeTimelinePlaceholder" not in regime_page
    assert "buildRegimeTimelinePlaceholder" not in timeline_chart
    assert "bias_20d" not in regime_page
    assert "bias_20d" not in timeline_chart
    assert "mid_regime_code" in regime_page
    assert "sojourn_prob_10d" in regime_page
    assert "short_signal_code" in regime_page
    assert "transition_hazard_10d" in regime_page
    assert "type=\"stepAfter\"" in timeline_chart
    assert "domain={[0, 1]}" in timeline_chart
    assert "10일 유지 확률" in timeline_chart


def test_similarity_events_are_separate_from_similarity_view() -> None:
    screen_types = _read("types/screen.ts")
    similarity_page = _read("pages/Similarity.tsx")

    assert 'export type SimilarityView = "regime" | "gold";' in screen_types
    assert 'type SimilarityPageTab = "dates" | "events" | "replay";' in similarity_page
    assert 'useState<SimilarityView>("regime")' in similarity_page
    assert 'useState<SimilarityPageTab>("dates")' in similarity_page


def test_p32_api_types_and_hooks_are_present() -> None:
    api_types = _read("api/types.ts")
    api_hooks = _read("api/hooks.ts")

    assert "latest_available?: DateString | null;" in api_types
    assert "export interface RegimeTimelineResponse" in api_types
    assert "export interface EventSimilarityResponse" in api_types
    assert '"similarity_events"' in api_types
    assert 'withQuery("/api/v1/regime/timeline"' in api_hooks
    assert 'withQuery("/api/v1/similarity/events"' in api_hooks
    assert 'withQuery("/api/v1/similarity/events/explain"' in api_hooks


def test_similarity_explain_uses_event_similarity_cache() -> None:
    similarity_page = _read("pages/Similarity.tsx")
    explain_page = _read("pages/Explain.tsx")

    assert "useSimilarityEventsExplain" in similarity_page
    assert "/api/v1/similarity/events/explain" in similarity_page
    assert "useSimilarityEventsExplain" in explain_page
    assert "/api/v1/similarity/events/explain" in explain_page
