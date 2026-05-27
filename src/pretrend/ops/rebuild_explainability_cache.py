from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from typing import Literal

from pretrend.observability.explainability.event_similarity_explainer import (
    explain_similarity_events,
)
from pretrend.observability.explainability.llm_client import (
    ApiCodexProvider,
    LLMProvider,
    get_provider,
)
from pretrend.observability.explainability.macro_explainer import explain_macro
from pretrend.observability.explainability.regime_explainer import explain_regime
from pretrend.observability.explainability.similarity_explainer import explain_similarity
from pretrend.observability.similarity.producer import _get_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine


UseCase = Literal["similarity_events", "similarity_regime", "similarity_gold", "regime", "macro"]


def main() -> int:
    args = _parse_args()
    provider = _provider(args)
    if not provider.health_check():
        raise RuntimeError(f"provider health check failed: {provider.model_id}")

    db_engine = _get_engine()
    query_dates = _query_dates(args.query_date, args.days_back, args.start_date, args.end_date)
    use_cases = _use_cases(args.use_case)
    for query_date in query_dates:
        print(f"[ExplainabilityCache] query_date={query_date.isoformat()}")
        if "similarity_events" in use_cases:
            if args.skip_missing_source and not _has_source_data(db_engine, "similarity_events", query_date):
                print("  similarity_events skipped missing source data")
            else:
                report = explain_similarity_events(
                    query_date,
                    engine=db_engine,
                    provider=provider,
                    force_refresh=args.force,
                )
                print(f"  similarity_events model={provider.model_id} ok events={len(report.events)}")
        if "similarity_regime" in use_cases:
            if args.skip_missing_source and not _has_source_data(db_engine, "similarity_regime", query_date):
                print("  similarity_regime skipped missing source data")
            else:
                report = explain_similarity(
                    query_date,
                    "regime",
                    engine=db_engine,
                    provider=provider,
                    force_refresh=args.force,
                )
                print(f"  similarity_regime model={provider.model_id} ok summary_len={len(report.summary)}")
        if "similarity_gold" in use_cases:
            if args.skip_missing_source and not _has_source_data(db_engine, "similarity_gold", query_date):
                print("  similarity_gold skipped missing source data")
            else:
                report = explain_similarity(
                    query_date,
                    "gold",
                    engine=db_engine,
                    provider=provider,
                    force_refresh=args.force,
                )
                print(f"  similarity_gold model={provider.model_id} ok summary_len={len(report.summary)}")
        if "regime" in use_cases:
            if args.skip_missing_source and not _has_source_data(db_engine, "regime", query_date):
                print("  regime skipped missing source data")
            else:
                report = explain_regime(
                    query_date,
                    engine=db_engine,
                    provider=provider,
                    force_refresh=args.force,
                )
                print(f"  regime model={provider.model_id} ok summary_len={len(report.ahs_summary)}")
        if "macro" in use_cases:
            if args.skip_missing_source and not _has_source_data(db_engine, "macro", query_date):
                print("  macro skipped missing source data")
            else:
                report = explain_macro(
                    query_date,
                    engine=db_engine,
                    provider=provider,
                    force_refresh=args.force,
                )
                print(f"  macro model={provider.model_id} ok indicators={len(report.indicators)}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild explainability cache rows.")
    parser.add_argument("--query-date", default=None, help="Latest query date in YYYY-MM-DD format.")
    parser.add_argument("--start-date", default=None, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", default=None, help="End date in YYYY-MM-DD format.")
    parser.add_argument("--days-back", type=int, default=1, help="Number of calendar dates to rebuild.")
    parser.add_argument(
        "--provider",
        default="api_vscode_codex",
        help="LLM provider name. Use api_vscode_codex for FastAPI Codex proxy.",
    )
    parser.add_argument("--api-url", default=None, help="Override ApiCodexProvider API URL.")
    parser.add_argument("--health-url", default=None, help="Override ApiCodexProvider health URL.")
    parser.add_argument(
        "--use-case",
        action="append",
        choices=["similarity_events", "similarity_regime", "similarity_gold", "regime", "macro", "all"],
        default=None,
        help="Use case to rebuild. Repeatable. Defaults to current dashboard surfaces.",
    )
    parser.add_argument("--force", action="store_true", help="Refresh even if cache row already exists.")
    parser.add_argument(
        "--skip-missing-source",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip use-case/date pairs whose source table has no row. Default: true.",
    )
    return parser.parse_args()


def _provider(args: argparse.Namespace) -> LLMProvider:
    if args.provider in {"api_vscode_codex", "report_api_vscode_codex"}:
        return ApiCodexProvider(api_url=args.api_url, health_url=args.health_url)
    return get_provider(args.provider)


def _query_dates(
    query_date: str | None,
    days_back: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[date]:
    if start_date or end_date:
        if not start_date or not end_date:
            raise ValueError("--start-date and --end-date must be provided together")
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        if start > end:
            raise ValueError("--start-date must be before or equal to --end-date")
        return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]

    if query_date is None:
        raise ValueError("--query-date or --start-date/--end-date is required")
    end = datetime.strptime(query_date, "%Y-%m-%d").date()
    count = max(days_back, 1)
    start = end - timedelta(days=count - 1)
    return [start + timedelta(days=offset) for offset in range(count)]


def _use_cases(values: list[str] | None) -> set[UseCase]:
    if not values or "all" in values:
        return {"similarity_events", "regime", "macro"}
    return set(values)  # type: ignore[return-value]


def _has_source_data(engine: Engine, use_case: UseCase, query_date: date) -> bool:
    if use_case == "similarity_events":
        table_name = "gold_market_state_similarity_feature"
        date_column = "trade_date"
    elif use_case == "similarity_regime":
        table_name = "similarity_regime"
        date_column = "query_date"
    elif use_case == "similarity_gold":
        table_name = "similarity_gold"
        date_column = "query_date"
    elif use_case == "regime":
        table_name = "gold_market_state_similarity_feature"
        date_column = "trade_date"
    else:
        table_name = "gold_macro_features"
        date_column = "trade_date"

    with engine.connect() as conn:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE {date_column} = :query_date"),
            {"query_date": query_date},
        ).scalar_one()
    return int(count or 0) > 0


if __name__ == "__main__":
    raise SystemExit(main())
