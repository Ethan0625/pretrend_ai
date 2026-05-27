from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = ROOT / "apps" / "web" / "src"


def _read(relative_path: str) -> str:
    return (WEB_SRC / relative_path).read_text(encoding="utf-8")


def test_similarity_replay_types_and_hook_are_registered() -> None:
    api_types = _read("api/types.ts")
    api_hooks = _read("api/hooks.ts")

    assert "export interface ReplayTrajectory" in api_types
    assert "export interface SimilarityReplayResponse" in api_types
    assert "export interface ReplayAssetPath" in api_types
    assert "export interface ReplayAssetRanking" in api_types
    assert "export interface ReplayAssetOverlay" in api_types
    assert "normalized_return: number | null;" in api_types
    assert "state_similarity_score: number;" in api_types
    assert "trajectory_similarity_score: number | null;" in api_types
    assert "compare_start: DateString;" in api_types
    assert "compare_end: DateString;" in api_types
    assert "current_path: ReplayAssetPath;" in api_types
    assert "historical_path: ReplayAssetPath;" in api_types
    assert "overlay_assets: ReplayAssetOverlay[];" in api_types
    assert "compare_days: number;" in api_types
    assert "forward_days: number;" in api_types
    assert "export function useSimilarityReplay" in api_hooks
    assert 'withQuery("/api/v1/similarity/replay"' in api_hooks
    assert "compare_days" in api_hooks
    assert "forward_days" in api_hooks
    assert "top_assets" in api_hooks
    assert "ranking_symbols" in api_hooks
    assert "symbol," in api_hooks


def test_similarity_replay_tab_is_separate_from_existing_views() -> None:
    similarity_page = _read("pages/Similarity.tsx")

    assert 'type SimilarityPageTab = "dates" | "events" | "replay";' in similarity_page
    assert 'useState<SimilarityView>("regime")' in similarity_page
    assert 'useState<SimilarityPageTab>("dates")' in similarity_page
    assert 'useState<"events" | SimilarityView>("events")' in similarity_page
    assert 'useState("SPY")' in similarity_page
    assert "유사 구간 궤적" in similarity_page
    assert 'pageTab === "replay"' in similarity_page
    assert "Asset Name" in similarity_page
    assert "Replay 기준" in similarity_page
    assert "REPLAY_COMPARE_DAYS = 60" in similarity_page
    assert "REPLAY_FORWARD_DAYS = 30" in similarity_page
    assert "REPLAY_TOP_ASSETS = 5" in similarity_page
    assert "ReplayOverlayTimeline" in similarity_page
    assert "onSelectAsset" in similarity_page
    assert "showViewSelector={pageTab === \"dates\"}" in similarity_page


def test_replay_timeline_marks_anchor_and_uses_eod_normalized_returns() -> None:
    replay_chart = _read("charts/ReplayTimeline.tsx")

    assert "ReferenceLine" in replay_chart
    assert "day_offset" in replay_chart
    assert "ReplayAssetPath" in replay_chart
    assert "normalized_return" in replay_chart
    assert "formatPercent" in replay_chart
    assert "currentPath" in replay_chart
    assert "historicalPath" in replay_chart
    assert "ReplayAssetOverlay" in replay_chart
    assert "toOverlayRows" in replay_chart
    assert "short_signal_code" not in replay_chart
    assert "transition_hazard_10d" not in replay_chart
    assert "bias_20d" not in replay_chart
