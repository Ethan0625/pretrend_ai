from __future__ import annotations

import argparse
import glob
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

VIX_STEPS = [
    (0.0, 15.0, "LOW"),
    (15.0, 20.0, "NORMAL"),
    (20.0, 25.0, "ELEVATED"),
    (25.0, 30.0, "HIGH"),
    (30.0, 35.0, "STRESS"),
    (35.0, 999.0, "EXTREME"),
]
STEP_ORDER = [label for _, _, label in VIX_STEPS]
HIGH_STEPS = {"HIGH", "STRESS", "EXTREME"}
ELEVATED_OR_LOWER = {"LOW", "NORMAL", "ELEVATED"}


@dataclass(frozen=True)
class EventSpec:
    label: str
    date: str
    note: str


def _load_gold_symbol(gold_root: Path, symbol: str, columns: Iterable[str]) -> pd.DataFrame:
    files = sorted(glob.glob(str(gold_root / f"symbol={symbol}" / "**/*.parquet"), recursive=True))
    if not files:
        raise FileNotFoundError(f"No gold parquet found for {symbol}")
    frames = []
    required = set(columns) | {"trade_date"}
    for file in files:
        df = pd.read_parquet(file, columns=[c for c in required if c in pd.read_parquet(file, columns=None).columns])
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    return out


def _load_gold_symbol_fast(gold_root: Path, symbol: str) -> pd.DataFrame:
    files = sorted(glob.glob(str(gold_root / f"symbol={symbol}" / "**/*.parquet"), recursive=True))
    if not files:
        raise FileNotFoundError(f"No gold parquet found for {symbol}")
    frames = [pd.read_parquet(file) for file in files]
    out = pd.concat(frames, ignore_index=True)
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    return out


def _load_axis_history(strategy_root: Path) -> pd.DataFrame:
    files = sorted(glob.glob(str(strategy_root / "axis_horizon_state" / "decision_date=*/*.parquet")))
    if not files:
        raise FileNotFoundError("No axis_horizon_state snapshots found")
    df = pd.read_parquet(files[-1], columns=["trade_date", "short_signal"])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df.sort_values("trade_date").drop_duplicates("trade_date", keep="last")


def _assign_step(vix: pd.Series) -> pd.Series:
    labels = pd.Series(index=vix.index, dtype="object")
    for low, high, label in VIX_STEPS:
        labels[(vix >= low) & (vix < high)] = label
    return labels.fillna("UNKNOWN")


def _format_pct(val: float | None) -> str:
    if val is None or pd.isna(val):
        return "N/A"
    return f"{val * 100:.2f}%"


def _format_num(val: float | None) -> str:
    if val is None or pd.isna(val):
        return "N/A"
    return f"{val:.2f}"


def _to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "| (empty) |\n| --- |"
    cols = list(df.columns)
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = []
    for _, row in df.iterrows():
        vals = []
        for col in cols:
            val = row[col]
            vals.append("" if pd.isna(val) else str(val))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join([header, sep, *rows])


def build_analysis_frame(strategy_root: Path, gold_root: Path) -> pd.DataFrame:
    vix = _load_gold_symbol_fast(gold_root, "^VIX")[["trade_date", "adj_close", "ma_5"]].rename(
        columns={"adj_close": "vix_close", "ma_5": "vix_ma5"}
    )
    spy = _load_gold_symbol_fast(gold_root, "SPY")[["trade_date", "adj_close", "ret_1d", "vol_20d", "vol_60d"]].rename(
        columns={"adj_close": "spy_close", "ret_1d": "spy_ret_1d", "vol_20d": "spy_vol_20d", "vol_60d": "spy_vol_60d"}
    )
    tlt = _load_gold_symbol_fast(gold_root, "TLT")[["trade_date", "ret_1d"]].rename(columns={"ret_1d": "tlt_ret_1d"})
    iau = _load_gold_symbol_fast(gold_root, "IAU")[["trade_date", "ret_1d"]].rename(columns={"ret_1d": "iau_ret_1d"})
    axis = _load_axis_history(strategy_root)

    df = vix.merge(spy, on="trade_date", how="inner")
    df = df.merge(tlt, on="trade_date", how="left")
    df = df.merge(iau, on="trade_date", how="left")
    df = df.merge(axis, on="trade_date", how="left")
    df = df.sort_values("trade_date").reset_index(drop=True)

    for horizon in (1, 5, 20):
        df[f"spy_next_{horizon}d_return"] = df["spy_close"].shift(-horizon) / df["spy_close"] - 1.0
    df["spy_next_1d_down"] = df["spy_next_1d_return"] < 0
    df["vol_spike_proxy"] = (df["spy_vol_20d"] / df["spy_vol_60d"]).gt(1.5)
    df["flight_to_safety_proxy"] = df["tlt_ret_1d"].gt(0.003) & df["iau_ret_1d"].gt(0.003)
    df["vix_below_ma5"] = df["vix_close"].lt(df["vix_ma5"])
    df["vix_step"] = _assign_step(df["vix_close"])
    df["prev_step"] = df["vix_step"].shift(1)
    df["transition_pair"] = df["prev_step"].fillna("NONE") + "→" + df["vix_step"]
    return df


def summarize_steps(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dist_rows = []
    react_rows = []
    proxy_rows = []
    total_days = len(df)
    for low, high, label in VIX_STEPS:
        step_df = df[df["vix_step"] == label]
        count = len(step_df)
        dist_rows.append({
            "Step": label,
            "VIX 범위": f"[{low:.0f}, {high:.0f})" if high < 999 else f">= {low:.0f}",
            "거래일 수": count,
            "비율": _format_pct(count / total_days if total_days else None),
        })
        react_rows.append({
            "Step": label,
            "spy_next_1d_mean": _format_pct(step_df["spy_next_1d_return"].mean()),
            "spy_next_1d_median": _format_pct(step_df["spy_next_1d_return"].median()),
            "spy_next_5d_mean": _format_pct(step_df["spy_next_5d_return"].mean()),
            "spy_next_5d_median": _format_pct(step_df["spy_next_5d_return"].median()),
            "spy_next_20d_mean": _format_pct(step_df["spy_next_20d_return"].mean()),
            "spy_next_20d_median": _format_pct(step_df["spy_next_20d_return"].median()),
            "하락 비율": _format_pct(step_df["spy_next_1d_down"].mean()),
        })
        proxy_rows.append({
            "Step": label,
            "vol_spike_proxy%": _format_pct(step_df["vol_spike_proxy"].mean()),
            "flight_to_safety_proxy%": _format_pct(step_df["flight_to_safety_proxy"].mean()),
            "PANIC 비율": _format_pct((step_df["short_signal"] == "PANIC").mean()),
            "RELIEF 비율": _format_pct((step_df["short_signal"] == "RELIEF").mean()),
        })
    return pd.DataFrame(dist_rows), pd.DataFrame(react_rows), pd.DataFrame(proxy_rows)


def summarize_relief(df: pd.DataFrame) -> pd.DataFrame:
    transitions = ["HIGH→ELEVATED", "STRESS→ELEVATED", "EXTREME→STRESS"]
    rows = []
    for transition in transitions:
        group = df[df["transition_pair"] == transition].copy()
        rows.append({
            "전환": transition,
            "건수": len(group),
            "vix_below_ma5 비율": _format_pct(group["vix_below_ma5"].mean() if not group.empty else None),
            "spy_next_5d_mean": _format_pct(group["spy_next_5d_return"].mean() if not group.empty else None),
            "spy_next_20d_mean": _format_pct(group["spy_next_20d_return"].mean() if not group.empty else None),
        })
    extra_mask = df["prev_step"].isin(HIGH_STEPS) & df["vix_step"].isin(ELEVATED_OR_LOWER)
    extra = df.loc[extra_mask & ~df["transition_pair"].isin(transitions)]
    for transition, group in extra.groupby("transition_pair"):
        rows.append({
            "전환": transition,
            "건수": len(group),
            "vix_below_ma5 비율": _format_pct(group["vix_below_ma5"].mean()),
            "spy_next_5d_mean": _format_pct(group["spy_next_5d_return"].mean()),
            "spy_next_20d_mean": _format_pct(group["spy_next_20d_return"].mean()),
        })
    if not rows:
        return pd.DataFrame(columns=["전환", "건수", "vix_below_ma5 비율", "spy_next_5d_mean", "spy_next_20d_mean"])
    return pd.DataFrame(rows).sort_values(["건수", "전환"], ascending=[False, True])


def summarize_candidates(df: pd.DataFrame) -> pd.DataFrame:
    panic_rows = []
    for low, high, label in VIX_STEPS:
        step_df = df[df["vix_step"] == label]
        panic_rows.append({
            "Step": label,
            "PANIC 후보": "YES" if step_df["spy_next_1d_down"].mean() > 0.60 else "NO",
            "다음날 하락 비율": _format_pct(step_df["spy_next_1d_down"].mean()),
            "spy_next_1d_mean": _format_pct(step_df["spy_next_1d_return"].mean()),
        })
    relief_mask = df["prev_step"].isin(HIGH_STEPS) & df["vix_step"].isin(ELEVATED_OR_LOWER)
    relief_df = df.loc[relief_mask]
    relief_score = None
    if not relief_df.empty:
        relief_score = (relief_df["vix_below_ma5"].mean() + (relief_df["spy_next_5d_return"].mean() > 0)) / 2.0
    candidate_df = pd.DataFrame(panic_rows)
    candidate_df.attrs["relief_score"] = relief_score
    return candidate_df


def summarize_events(df: pd.DataFrame) -> pd.DataFrame:
    specs = [
        EventSpec("GFC 피크", "2009-03-09", "bear market trough"),
        EventSpec("COVID 피크", "2020-03-18", "liquidity panic"),
    ]
    rows = []
    for spec in specs:
        row = df[df["trade_date"] == pd.Timestamp(spec.date)]
        if row.empty:
            continue
        rows.append({
            "이벤트": spec.label,
            "날짜": spec.date,
            "VIX": _format_num(row.iloc[0]["vix_close"]),
            "Step": row.iloc[0]["vix_step"],
            "비고": spec.note,
        })
    june_2022 = df[(df["trade_date"] >= pd.Timestamp("2022-06-01")) & (df["trade_date"] <= pd.Timestamp("2022-06-30"))]
    if not june_2022.empty:
        peak = june_2022.sort_values("vix_close", ascending=False).iloc[0]
        rows.append({
            "이벤트": "Rate Hike 2022",
            "날짜": peak["trade_date"].date().isoformat(),
            "VIX": _format_num(peak["vix_close"]),
            "Step": peak["vix_step"],
            "비고": "2022-06 monthly VIX peak",
        })
    return pd.DataFrame(rows)


def summarize_short_signal_cross(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sub = df[df["short_signal"].isin(["PANIC", "RELIEF", "STABLE"])]
    for signal in ["PANIC", "RELIEF", "STABLE"]:
        group = sub[sub["short_signal"] == signal]
        if group.empty:
            continue
        step_mode = group["vix_step"].mode()
        rows.append({
            "short_signal": signal,
            "obs": len(group),
            "mean_vix": _format_num(group["vix_close"].mean()),
            "median_vix": _format_num(group["vix_close"].median()),
            "modal_step": step_mode.iloc[0] if not step_mode.empty else "N/A",
        })
    return pd.DataFrame(rows)


def render_report(df: pd.DataFrame) -> str:
    dist_df, react_df, proxy_df = summarize_steps(df)
    relief_df = summarize_relief(df)
    candidate_df = summarize_candidates(df)
    events_df = summarize_events(df)
    signal_df = summarize_short_signal_cross(df)
    relief_score = candidate_df.attrs.get("relief_score")
    panic_candidates = ", ".join(candidate_df[candidate_df["PANIC 후보"] == "YES"]["Step"].tolist()) or "없음"
    relief_text = "N/A" if relief_score is None else f"{relief_score:.2f} (1.0에 가까울수록 유효)"

    parts = [
        f"# VIX Step 분석 ({df['trade_date'].min().date()} ~ {df['trade_date'].max().date()})",
        "",
        "## VIX Step 분포 (전체 기간 2004~2026)",
        _to_markdown(dist_df),
        "",
        "## Step별 시장 반응",
        _to_markdown(react_df),
        "",
        "## Step별 보조 신호/기존 Short Signal 교차",
        _to_markdown(proxy_df),
        "",
        "## 기존 Short Signal 이벤트별 VIX 분포",
        _to_markdown(signal_df),
        "",
        "## RELIEF 전환 구간 분석",
        _to_markdown(relief_df) if not relief_df.empty else "전환 구간 없음",
        "",
        "## 임계값 후보 (자동 도출, 최종 결정은 사람이 수행)",
        f"- PANIC 후보 step: {panic_candidates}",
        f"- RELIEF 후보 점수 (VIX < ma5 + 이후 5D 수익률): {relief_text}",
        _to_markdown(candidate_df),
        "",
        "## 주요 이벤트 교차 확인",
        _to_markdown(events_df),
    ]
    return "\n".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze VIX step behavior and write markdown report.")
    parser.add_argument("--strategy-root", default="data/strategy")
    parser.add_argument("--gold-root", default="data/gold/eod/eod_features")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    strategy_root = Path(args.strategy_root)
    gold_root = Path(args.gold_root)
    df = build_analysis_frame(strategy_root, gold_root)
    report = render_report(df)
    output = Path(args.output) if args.output else Path("result/research") / f"vix_step_analysis_{pd.Timestamp.now(tz='Asia/Seoul'):%Y%m%d}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
