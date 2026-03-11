from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import pandas as pd

SLICE_SYMBOLS: Tuple[str, ...] = ("USO", "SPY", "TLT", "HYG", "LQD")


@dataclass
class SliceReport:
    strategy_table: pd.DataFrame
    delta_table: pd.DataFrame
    sample_table: pd.DataFrame


def _normalize_datetime_index(df: pd.DataFrame, date_col: str = "trade_date") -> pd.DataFrame:
    out = df.copy()
    if date_col in out.columns:
        out[date_col] = pd.to_datetime(out[date_col])
        out = out.set_index(date_col)
    else:
        out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    return out


def load_gold_eod_slice_features(
    root: Path,
    symbols: Sequence[str],
    date_from: str | pd.Timestamp,
    date_to: str | pd.Timestamp,
) -> pd.DataFrame:
    date_from = pd.Timestamp(date_from)
    date_to = pd.Timestamp(date_to)
    frames: List[pd.DataFrame] = []
    for symbol in symbols:
        sym_root = root / f"symbol={symbol}"
        if not sym_root.exists():
            continue
        parts = [pd.read_parquet(p, columns=["trade_date", "ret_20d", "vol_20d"]) for p in sorted(sym_root.rglob("*.parquet"))]
        if not parts:
            continue
        chunk = pd.concat(parts, ignore_index=True)
        chunk["trade_date"] = pd.to_datetime(chunk["trade_date"])
        chunk = chunk[(chunk["trade_date"] >= date_from) & (chunk["trade_date"] <= date_to)]
        if chunk.empty:
            continue
        chunk["symbol"] = symbol
        frames.append(chunk)
    if not frames:
        return pd.DataFrame(index=pd.DatetimeIndex([], name="trade_date"))
    merged = pd.concat(frames, ignore_index=True)
    ret_pivot = merged.pivot_table(index="trade_date", columns="symbol", values="ret_20d", aggfunc="last")
    ret_pivot.columns = [f"{c.lower()}_ret_20d" for c in ret_pivot.columns]
    vol_pivot = merged.pivot_table(index="trade_date", columns="symbol", values="vol_20d", aggfunc="last")
    vol_pivot.columns = [f"{c.lower()}_vol_20d" for c in vol_pivot.columns]
    pivot = ret_pivot.join(vol_pivot, how="outer")
    if {"hyg_ret_20d", "lqd_ret_20d"}.issubset(pivot.columns):
        pivot["credit_spread_20d"] = pivot["hyg_ret_20d"] - pivot["lqd_ret_20d"]
    return pivot.sort_index()


def load_strategy_stage(
    root: Path,
    stage_name: str,
    date_from: str | pd.Timestamp,
    date_to: str | pd.Timestamp,
) -> pd.DataFrame:
    date_from = pd.Timestamp(date_from)
    date_to = pd.Timestamp(date_to)
    stage_root = root / stage_name
    if not stage_root.exists():
        return pd.DataFrame(index=pd.DatetimeIndex([], name="trade_date"))
    latest_partition = sorted(stage_root.glob("decision_date=*"))[-1:]
    if not latest_partition:
        return pd.DataFrame(index=pd.DatetimeIndex([], name="trade_date"))
    files = sorted(latest_partition[0].glob("*.parquet"))
    if not files:
        return pd.DataFrame(index=pd.DatetimeIndex([], name="trade_date"))
    df = pd.read_parquet(files[-1])
    df = _normalize_datetime_index(df)
    return df[(df.index >= date_from) & (df.index <= date_to)].copy()


def _extract_breadth_spread(mid_detail_json: object) -> float | None:
    if mid_detail_json is None or pd.isna(mid_detail_json):
        return None
    if isinstance(mid_detail_json, dict):
        return mid_detail_json.get("breadth_spread")
    try:
        parsed = json.loads(str(mid_detail_json))
    except Exception:
        return None
    return parsed.get("breadth_spread")


def define_slice_masks(
    gold_eod_df: pd.DataFrame,
    mid_df: pd.DataFrame,
    next_step_df: pd.DataFrame,
) -> Dict[str, pd.Series]:
    base = pd.DataFrame(index=gold_eod_df.index.union(mid_df.index).union(next_step_df.index).sort_values())
    base = base.join(gold_eod_df, how="left")

    if not mid_df.empty:
        mid_view = mid_df.copy()
        if "mid_detail_json" in mid_view.columns:
            mid_view["breadth_iwm_spy_spread"] = mid_view["mid_detail_json"].map(_extract_breadth_spread)
        cols = [c for c in ["mid_regime", "breadth_iwm_spy_spread"] if c in mid_view.columns]
        base = base.join(mid_view[cols], how="left")
    if not next_step_df.empty:
        cols = [c for c in ["transition_hazard_10d"] if c in next_step_df.columns]
        base = base.join(next_step_df[cols], how="left")

    oil_shock = base.get("uso_ret_20d", pd.Series(index=base.index, dtype=float)).gt(0.15).fillna(False)
    rate_shock = base.get("tlt_ret_20d", pd.Series(index=base.index, dtype=float)).lt(-0.05).fillna(False)
    credit_spread = base.get("credit_spread_20d", pd.Series(index=base.index, dtype=float))
    if credit_spread.notna().any():
        credit_stress = credit_spread.lt(-0.03).fillna(False)
    else:
        credit_stress = base.get("spy_vol_20d", pd.Series(index=base.index, dtype=float)).gt(0.025).fillna(False)
    concentration_extreme = (
        base.get("spy_ret_20d", pd.Series(index=base.index, dtype=float)).gt(0.0)
        & base.get("breadth_iwm_spy_spread", pd.Series(index=base.index, dtype=float)).lt(0.0)
    ).fillna(False)
    defensive_stress = base.get("mid_regime", pd.Series(index=base.index, dtype=object)).eq("RISK_OFF").fillna(False)
    transition_risk_high = base.get("transition_hazard_10d", pd.Series(index=base.index, dtype=float)).ge(0.95).fillna(False)

    masks = {
        "oil_shock": oil_shock.astype(bool),
        "rate_shock": rate_shock.astype(bool),
        "credit_stress": credit_stress.astype(bool),
        "concentration_extreme": concentration_extreme.astype(bool),
        "defensive_stress": defensive_stress.astype(bool),
        "transition_risk_high": transition_risk_high.astype(bool),
    }
    masks["oil_rate_shock"] = (masks["oil_shock"] & masks["rate_shock"]).astype(bool)
    masks["concentration_transition"] = (masks["concentration_extreme"] & masks["transition_risk_high"]).astype(bool)
    return masks


def extract_windows(mask: pd.Series, min_days: int = 3) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    if mask.empty:
        return []
    mask = mask.astype(bool).sort_index()
    windows: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    start = None
    prev = None
    for idx, is_true in mask.items():
        if is_true and start is None:
            start = idx
        if not is_true and start is not None and prev is not None:
            if len(mask.loc[start:prev]) >= min_days:
                windows.append((pd.Timestamp(start), pd.Timestamp(prev)))
            start = None
        prev = idx
    if start is not None and prev is not None and len(mask.loc[start:prev]) >= min_days:
        windows.append((pd.Timestamp(start), pd.Timestamp(prev)))
    return windows


def _window_mdd(nav: pd.Series) -> float:
    if nav.empty:
        return float("nan")
    roll_max = nav.cummax()
    dd = nav / roll_max - 1.0
    return float(dd.min())


def _forward_return(daily_log: pd.DataFrame, start: pd.Timestamp, horizon_days: int) -> float:
    if start not in daily_log.index:
        return float("nan")
    start_loc = daily_log.index.get_loc(start)
    if isinstance(start_loc, slice):
        start_loc = start_loc.start
    end_loc = start_loc + horizon_days
    if end_loc >= len(daily_log.index):
        return float("nan")
    start_nav = float(daily_log.iloc[start_loc]["nav"])
    end_nav = float(daily_log.iloc[end_loc]["nav"])
    if start_nav <= 0:
        return float("nan")
    return end_nav / start_nav - 1.0


def compute_slice_metrics(daily_log: pd.DataFrame, windows: List[Tuple[pd.Timestamp, pd.Timestamp]]) -> Dict[str, object]:
    if daily_log.empty or not windows:
        return {
            "obs_days": 0,
            "n_windows": 0,
            "n_days": 0,
            "date_from": None,
            "date_to": None,
            "slice_nav_return": float("nan"),
            "slice_mdd": float("nan"),
            "avg_invested_ratio": float("nan"),
            "avg_schd_weight": float("nan"),
            "post_20d_return": float("nan"),
            "post_60d_return": float("nan"),
            "hit_rate": float("nan"),
        }

    x = _normalize_datetime_index(daily_log)
    if "schd_weight" not in x.columns:
        x["schd_weight"] = 0.0

    nav_returns: List[float] = []
    mdds: List[float] = []
    post20: List[float] = []
    post60: List[float] = []
    slices: List[pd.DataFrame] = []

    for start, end in windows:
        window_df = x.loc[start:end]
        if window_df.empty:
            continue
        slices.append(window_df)
        start_nav = float(window_df.iloc[0]["nav"])
        end_nav = float(window_df.iloc[-1]["nav"])
        nav_returns.append(end_nav / start_nav - 1.0 if start_nav > 0 else float("nan"))
        mdds.append(_window_mdd(window_df["nav"]))
        post20.append(_forward_return(x, pd.Timestamp(start), 20))
        post60.append(_forward_return(x, pd.Timestamp(start), 60))

    if not slices:
        return {
            "obs_days": 0,
            "n_windows": 0,
            "n_days": 0,
            "date_from": None,
            "date_to": None,
            "slice_nav_return": float("nan"),
            "slice_mdd": float("nan"),
            "avg_invested_ratio": float("nan"),
            "avg_schd_weight": float("nan"),
            "post_20d_return": float("nan"),
            "post_60d_return": float("nan"),
            "hit_rate": float("nan"),
        }

    combined = pd.concat(slices).sort_index()
    valid_post20 = pd.Series(post20, dtype=float).dropna()
    valid_post60 = pd.Series(post60, dtype=float).dropna()
    return {
        "obs_days": int(sum(len(df) for df in slices)),
        "n_windows": len(slices),
        "n_days": int(sum(len(df) for df in slices)),
        "date_from": min(start for start, _ in windows).date().isoformat(),
        "date_to": max(end for _, end in windows).date().isoformat(),
        "slice_nav_return": float(pd.Series(nav_returns, dtype=float).mean()),
        "slice_mdd": float(pd.Series(mdds, dtype=float).mean()),
        "avg_invested_ratio": float(combined["invested_ratio"].mean()),
        "avg_schd_weight": float(combined["schd_weight"].mean()),
        "post_20d_return": float(valid_post20.mean()) if not valid_post20.empty else float("nan"),
        "post_60d_return": float(valid_post60.mean()) if not valid_post60.empty else float("nan"),
        "hit_rate": float((valid_post20 > 0).mean()) if not valid_post20.empty else float("nan"),
    }


def run_slice_comparison(
    result_base_daily_log: pd.DataFrame,
    result_floor_daily_log: pd.DataFrame,
    slice_masks: Dict[str, pd.Series],
) -> SliceReport:
    strategy_rows: List[Dict[str, object]] = []
    delta_rows: List[Dict[str, object]] = []
    sample_rows: List[Dict[str, object]] = []

    for slice_name, mask in slice_masks.items():
        windows = extract_windows(mask, min_days=3)
        lock_metrics = compute_slice_metrics(result_base_daily_log, windows)
        floor_metrics = compute_slice_metrics(result_floor_daily_log, windows)
        warning = "*" if lock_metrics["n_windows"] < 5 else ""
        label = f"{slice_name}{warning}"

        sample_rows.append({
            "slice": label,
            "n_windows": lock_metrics["n_windows"],
            "n_days": lock_metrics["n_days"],
            "date_from": lock_metrics["date_from"],
            "date_to": lock_metrics["date_to"],
        })

        for strategy_name, metrics in (("v3.4.1", lock_metrics), ("v3.4.1-schd-floor-20", floor_metrics)):
            strategy_rows.append({
                "slice": label,
                "strategy": strategy_name,
                "obs_days": metrics["obs_days"],
                "nav_return": metrics["slice_nav_return"],
                "mdd": metrics["slice_mdd"],
                "post_20d": metrics["post_20d_return"],
                "post_60d": metrics["post_60d_return"],
                "hit_rate": metrics["hit_rate"],
                "avg_schd_weight": metrics["avg_schd_weight"],
                "avg_invested_ratio": metrics["avg_invested_ratio"],
            })

        delta_rows.append({
            "slice": label,
            "delta_nav_return": floor_metrics["slice_nav_return"] - lock_metrics["slice_nav_return"],
            "delta_mdd": floor_metrics["slice_mdd"] - lock_metrics["slice_mdd"],
            "delta_post_20d": floor_metrics["post_20d_return"] - lock_metrics["post_20d_return"],
            "delta_post_60d": floor_metrics["post_60d_return"] - lock_metrics["post_60d_return"],
            "delta_avg_schd_weight": floor_metrics["avg_schd_weight"] - lock_metrics["avg_schd_weight"],
        })

    return SliceReport(
        strategy_table=pd.DataFrame(strategy_rows),
        delta_table=pd.DataFrame(delta_rows),
        sample_table=pd.DataFrame(sample_rows),
    )


def _format_value(col: str, value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    if col in {"nav_return", "mdd", "post_20d", "post_60d", "hit_rate", "avg_schd_weight", "avg_invested_ratio",
               "delta_nav_return", "delta_mdd", "delta_post_20d", "delta_post_60d", "delta_avg_schd_weight"}:
        return f"{float(value):+.2%}"
    return str(value)


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(_format_value(col, row[col]) for col in cols) + " |")
    return "\n".join(lines)


def print_slice_report(report: SliceReport) -> None:
    print("## 표 1. 슬라이스별 전략 비교")
    print(dataframe_to_markdown(report.strategy_table))
    print("\n## 표 2. 전략 차이표 (floor - lock)")
    print(dataframe_to_markdown(report.delta_table))
    print("\n## 표 3. 샘플 수 체크")
    print(dataframe_to_markdown(report.sample_table))


def save_slice_report(report: SliceReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = "## 표 1. 슬라이스별 전략 비교\n" + dataframe_to_markdown(report.strategy_table)
    text += "\n\n## 표 2. 전략 차이표 (floor - lock)\n" + dataframe_to_markdown(report.delta_table)
    text += "\n\n## 표 3. 샘플 수 체크\n" + dataframe_to_markdown(report.sample_table) + "\n"
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _find_latest_daily_log(result_dir: Path) -> Path:
    candidates = [
        p for p in result_dir.glob("*.parquet")
        if not p.name.endswith(("_daily_nav.parquet", "_diagnostics.parquet", "_final_positions.parquet", "_summary_metrics.parquet", "_trades.parquet"))
    ]
    if not candidates:
        raise FileNotFoundError(f"No backtest daily log parquet found under {result_dir}")
    return sorted(candidates)[-1]


def load_result_daily_log(result_dir: Path) -> pd.DataFrame:
    df = pd.read_parquet(_find_latest_daily_log(result_dir))
    return _normalize_datetime_index(df)


def build_slice_report(
    strategy_root: Path,
    gold_root: Path,
    base_result_dir: Path,
    floor_result_dir: Path,
) -> SliceReport:
    base_daily_log = load_result_daily_log(base_result_dir)
    floor_daily_log = load_result_daily_log(floor_result_dir)
    date_from = min(base_daily_log.index.min(), floor_daily_log.index.min())
    date_to = max(base_daily_log.index.max(), floor_daily_log.index.max())

    gold = load_gold_eod_slice_features(gold_root, SLICE_SYMBOLS, date_from, date_to)
    mid_df = load_strategy_stage(strategy_root, "axis_horizon_state", date_from, date_to)
    next_step_df = load_strategy_stage(strategy_root, "next_step_signal", date_from, date_to)
    masks = define_slice_masks(gold, mid_df, next_step_df)
    return run_slice_comparison(base_daily_log, floor_daily_log, masks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Conditional slice analysis for backtest presets")
    parser.add_argument("--strategy-root", default="data/strategy")
    parser.add_argument("--gold-root", default="data/gold/eod/eod_features")
    parser.add_argument("--base-result-dir", required=True)
    parser.add_argument("--floor-result-dir", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report = build_slice_report(
        strategy_root=Path(args.strategy_root),
        gold_root=Path(args.gold_root),
        base_result_dir=Path(args.base_result_dir),
        floor_result_dir=Path(args.floor_result_dir),
    )
    print_slice_report(report)
    if args.output:
        save_slice_report(report, Path(args.output))


if __name__ == "__main__":
    main()
