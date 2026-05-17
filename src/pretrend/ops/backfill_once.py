from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable


logger = logging.getLogger(__name__)

DEFAULT_START_DATE = date(2010, 1, 1)


@dataclass(frozen=True)
class BackfillSettings:
    enabled: bool
    force: bool
    start_date: date
    end_date: date
    marker_path: Path
    run_macro: bool
    run_eod: bool
    sync_postgres: bool
    symbols: list[str] | None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_date(value: str, *, name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD, got {value!r}") from exc


def _previous_weekday(today: date | None = None) -> date:
    current = today or date.today()
    candidate = current - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _parse_symbols(value: str | None) -> list[str] | None:
    if not value:
        return None
    symbols = [part.strip().upper() for part in value.split(",") if part.strip()]
    return symbols or None


def _default_marker_path() -> Path:
    data_root = Path(os.getenv("PRETREND_DATA_ROOT", os.getenv("PRETREND_DATA_DIR", "data")))
    return data_root / "meta" / "bootstrap_backfill_once.json"


def settings_from_env() -> BackfillSettings:
    start_raw = os.getenv("PRETREND_BACKFILL_START_DATE")
    end_raw = os.getenv("PRETREND_BACKFILL_END_DATE")
    marker_raw = os.getenv("PRETREND_BACKFILL_MARKER_PATH")

    start_date = (
        _parse_date(start_raw, name="PRETREND_BACKFILL_START_DATE")
        if start_raw
        else DEFAULT_START_DATE
    )
    end_date = (
        _parse_date(end_raw, name="PRETREND_BACKFILL_END_DATE")
        if end_raw
        else _previous_weekday()
    )
    marker_path = Path(marker_raw) if marker_raw else _default_marker_path()

    return BackfillSettings(
        enabled=_env_bool("PRETREND_BACKFILL_ON_START", True),
        force=_env_bool("PRETREND_BACKFILL_FORCE", False),
        start_date=start_date,
        end_date=end_date,
        marker_path=marker_path,
        run_macro=_env_bool("PRETREND_BACKFILL_RUN_MACRO", True),
        run_eod=_env_bool("PRETREND_BACKFILL_RUN_EOD", True),
        sync_postgres=_env_bool("PRETREND_BACKFILL_SYNC_POSTGRES", True),
        symbols=_parse_symbols(os.getenv("PRETREND_BACKFILL_SYMBOLS")),
    )


def _row_count(value: Any, attr: str) -> int | None:
    task_result = getattr(value, attr, None)
    if task_result is None:
        return None
    row_count = getattr(task_result, "row_count", None)
    return int(row_count) if row_count is not None else None


def _macro_summary(result: Any) -> dict[str, Any]:
    return {
        "run_id": getattr(result, "run_id", None),
        "bronze_rows": _row_count(result, "bronze_result"),
        "silver_rows": _row_count(result, "silver_result"),
        "gold_rows": _row_count(result, "gold_macro_result"),
    }


def _eod_summary(result: Any) -> dict[str, Any]:
    return {
        "run_id": getattr(result, "run_id", None),
        "bronze_rows": _row_count(result, "bronze_result"),
        "silver_rows": _row_count(result, "silver_result"),
        "gold_rows": _row_count(result, "gold_result"),
    }


def _write_marker(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _default_macro_runner() -> Any:
    from pretrend.pipeline.macro_job import MacroJobConfig, MacroJobRunner, RunMode

    return MacroJobRunner(MacroJobConfig.from_env(run_mode=RunMode.INCREMENTAL))


def _default_eod_runner() -> Any:
    from pretrend.pipeline.eod_job import EodJobConfig, EodJobRunner

    return EodJobRunner(EodJobConfig.from_env())


def _default_sync_gold_macro() -> dict[str, Any]:
    from pretrend.pipeline.sync.gold_postgres import sync_gold_macro

    return sync_gold_macro()


def _default_sync_gold_eod() -> dict[str, Any]:
    from pretrend.pipeline.sync.gold_postgres import sync_gold_eod

    return sync_gold_eod()


def run_backfill_once(
    settings: BackfillSettings | None = None,
    *,
    macro_runner_factory: Callable[[], Any] = _default_macro_runner,
    eod_runner_factory: Callable[[], Any] = _default_eod_runner,
    sync_macro_func: Callable[[], dict[str, Any]] = _default_sync_gold_macro,
    sync_eod_func: Callable[[], dict[str, Any]] = _default_sync_gold_eod,
) -> dict[str, Any]:
    settings = settings or settings_from_env()

    if not settings.enabled:
        logger.info("[BootstrapBackfill] disabled by PRETREND_BACKFILL_ON_START=0")
        return {"status": "skipped_disabled", "marker_path": str(settings.marker_path)}

    if settings.end_date < settings.start_date:
        raise ValueError(
            "PRETREND_BACKFILL_END_DATE must be on or after "
            "PRETREND_BACKFILL_START_DATE"
        )

    if settings.marker_path.exists() and not settings.force:
        logger.info("[BootstrapBackfill] marker exists, skipping: %s", settings.marker_path)
        return {"status": "skipped_marker", "marker_path": str(settings.marker_path)}

    logger.info(
        "[BootstrapBackfill] start=%s end=%s macro=%s eod=%s sync=%s symbols=%s",
        settings.start_date,
        settings.end_date,
        settings.run_macro,
        settings.run_eod,
        settings.sync_postgres,
        settings.symbols,
    )

    payload: dict[str, Any] = {
        "status": "completed",
        "started_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "start_date": settings.start_date.isoformat(),
        "end_date": settings.end_date.isoformat(),
        "marker_path": str(settings.marker_path),
        "symbols": settings.symbols,
        "macro": None,
        "eod": None,
        "postgres_sync": None,
    }

    if settings.run_macro:
        macro_result = macro_runner_factory().run(settings.start_date, settings.end_date)
        payload["macro"] = _macro_summary(macro_result)

    if settings.run_eod:
        eod_result = eod_runner_factory().run(
            settings.start_date,
            settings.end_date,
            symbols=settings.symbols,
        )
        payload["eod"] = _eod_summary(eod_result)

    if settings.sync_postgres:
        payload["postgres_sync"] = {
            "macro": sync_macro_func() if settings.run_macro else None,
            "eod": sync_eod_func() if settings.run_eod else None,
        }

    payload["finished_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _write_marker(settings.marker_path, payload)
    logger.info("[BootstrapBackfill] completed marker=%s", settings.marker_path)
    return payload


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    result = run_backfill_once()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
