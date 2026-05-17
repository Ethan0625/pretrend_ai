from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


pytestmark = [pytest.mark.db, pytest.mark.slow, pytest.mark.invariant]

ROOT = Path(__file__).parents[2]
SAFE_TEST_DATABASE_RE = re.compile(r"^pretrend_test[A-Za-z0-9_]*$")

REQUIRED_TABLES = {
    "gold_macro_features",
    "gold_eod_features",
    "gold_market_state_similarity_feature",
    "similarity_regime",
    "similarity_gold",
    "explainability_cache",
}


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    database_url = _test_database_url()

    engine = create_engine(database_url)
    try:
        conn = engine.connect()
    except SQLAlchemyError as exc:
        pytest.skip(f"postgres unavailable for OFS-204 DB smoke: {exc}")

    with conn:
        _assert_test_db_is_at_alembic_head(conn)
        rows = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(:tables)
                """
            ),
            {"tables": sorted(REQUIRED_TABLES)},
        ).scalars()
        existing = set(rows)

    missing = REQUIRED_TABLES - existing
    if missing:
        pytest.fail(f"OFS-204 test DB tables are not migrated: {sorted(missing)}")
    return engine


def test_ofs_204_core_serving_tables_accept_synthetic_rows(pg_engine: Engine) -> None:
    """OFS-204: isolated test DB tables must accept minimal synthetic rows."""

    now = datetime.now(timezone.utc)
    with pg_engine.begin() as conn:
        _delete_synthetic_rows(conn)
        conn.execute(
            text(
                """
                INSERT INTO gold_macro_features
                  (indicator_id, trade_date, selected_observation_date, selected_value,
                   selected_release_date, delta_1m, delta_3m, delta_6m,
                   direction, regime, zscore_12m, release_source, is_assumption_based)
                VALUES
                  ('OFS204_SYNTH_MACRO', '1901-03-01', '1901-02-01', 1.0,
                   '1901-02-15', 0.1, 0.2, 0.3,
                   'up', 'easing', 0.4, 'econ_events', false)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO gold_eod_features
                  (symbol, trade_date, close, adj_close, ret_5d, ret_20d,
                   vol_20d, vol_60d, ma_ratio_5_20, rsi_14, volume_zscore_20d,
                   is_trading_day, is_missing_imputed, is_outlier, is_partial_day,
                   asset_group, asset_name, run_id_gold, ingestion_ts_gold)
                VALUES
                  ('OFS204_SYNTH_EOD', '1901-03-01', 100.0, 100.0, 0.01, 0.02,
                   0.1, 0.2, 1.01, 55.0, 0.0,
                   true, false, false, false,
                   'EQUITY_INDEX', 'SP500', 'ofs204', :now)
                """
            ),
            {"now": now},
        )
        conn.execute(
            text(
                """
                INSERT INTO gold_market_state_similarity_feature
                  (trade_date, long_phase_recovery, mid_regime_code,
                   short_signal_code, run_universe_flag, risk_gate_flag, built_at)
                VALUES
                  ('1901-03-01', 1, 1, 1, 1, 1, :now)
                """
            ),
            {"now": now},
        )
        for table_name in ["similarity_regime", "similarity_gold"]:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {table_name}
                      (query_date, neighbor_date, rank, score, gap_days, built_at)
                    VALUES
                      ('1901-03-01', '1901-01-20', 1, 0.75, 40, :now)
                    """
                ),
                {"now": now},
            )
        conn.execute(
            text(
                """
                INSERT INTO explainability_cache
                  (use_case, query_date, model_id, prompt_version,
                   report_json, output_hash, built_at)
                VALUES
                  ('similarity_regime', '1901-03-01', 'mock_ofs204', 'v1',
                   CAST(:report_json AS jsonb), :output_hash, :now)
                """
            ),
            {
                "report_json": json.dumps(
                    {
                        "query_date": "1901-03-01",
                        "view": "regime",
                        "summary": "synthetic DB smoke",
                        "neighbors": [],
                        "disclaimer": "observation only",
                    },
                    sort_keys=True,
                ),
                "output_hash": "ofs204_synthetic_hash",
                "now": now,
            },
        )

        counts = conn.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM gold_macro_features
                   WHERE indicator_id = 'OFS204_SYNTH_MACRO'),
                  (SELECT COUNT(*) FROM gold_eod_features
                   WHERE symbol = 'OFS204_SYNTH_EOD'),
                  (SELECT COUNT(*) FROM gold_market_state_similarity_feature
                   WHERE trade_date = '1901-03-01'),
                  (SELECT COUNT(*) FROM similarity_regime
                   WHERE query_date = '1901-03-01'),
                  (SELECT COUNT(*) FROM similarity_gold
                   WHERE query_date = '1901-03-01'),
                  (SELECT COUNT(*) FROM explainability_cache
                   WHERE model_id = 'mock_ofs204')
                """
            )
        ).one()
        assert tuple(counts) == (1, 1, 1, 1, 1, 1)

    with pg_engine.begin() as conn:
        _delete_synthetic_rows(conn)


def _test_database_url() -> str:
    raw_url = os.getenv("PRETREND_TEST_DATABASE_URL") or _dotenv_value(
        "PRETREND_TEST_DATABASE_URL"
    )
    if not raw_url:
        pytest.skip(
            "set PRETREND_TEST_DATABASE_URL to an isolated migrated DB "
            "whose database name starts with pretrend_test"
        )

    parsed = make_url(raw_url)
    database_name = parsed.database or ""
    if not SAFE_TEST_DATABASE_RE.fullmatch(database_name):
        pytest.fail(
            "PRETREND_TEST_DATABASE_URL must point to an isolated test DB "
            "named pretrend_test*. Refusing to insert synthetic rows into "
            f"{database_name!r}."
        )
    return raw_url


def _dotenv_value(key: str) -> str | None:
    dotenv_path = ROOT / ".env"
    if not dotenv_path.exists():
        return None
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        current_key, value = raw.split("=", 1)
        if current_key.strip() == key:
            return value.strip().strip("'\"")
    return None


def _assert_test_db_is_at_alembic_head(conn) -> None:
    expected_heads = set(
        ScriptDirectory.from_config(_alembic_config()).get_heads()
    )
    try:
        actual_heads = set(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )
    except SQLAlchemyError as exc:
        pytest.fail(f"OFS-204 test DB is not migrated with Alembic: {exc}")
    assert actual_heads == expected_heads


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


def _delete_synthetic_rows(conn) -> None:
    conn.execute(
        text(
            """
            DELETE FROM explainability_cache
            WHERE query_date = '1901-03-01'
               OR model_id = 'mock_ofs204'
            """
        )
    )
    conn.execute(text("DELETE FROM similarity_gold WHERE query_date = '1901-03-01'"))
    conn.execute(text("DELETE FROM similarity_regime WHERE query_date = '1901-03-01'"))
    conn.execute(
        text(
            "DELETE FROM gold_market_state_similarity_feature "
            "WHERE trade_date = '1901-03-01'"
        )
    )
    conn.execute(
        text(
            "DELETE FROM gold_eod_features "
            "WHERE symbol = 'OFS204_SYNTH_EOD' AND trade_date = '1901-03-01'"
        )
    )
    conn.execute(
        text(
            "DELETE FROM gold_macro_features "
            "WHERE indicator_id = 'OFS204_SYNTH_MACRO' AND trade_date = '1901-03-01'"
        )
    )
