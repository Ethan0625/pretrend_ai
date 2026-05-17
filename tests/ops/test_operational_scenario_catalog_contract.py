from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.contract

ROOT = Path(__file__).parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operational_failure_scenario_catalog_is_published() -> None:
    catalog = _read("docs/testing/operational_failure_scenario_catalog.md")
    fixture_readme = _read("tests/fixtures/operational_scenarios/README.md")
    invariant_contract = _read("docs/testing/operational_invariant_test_contract.md")
    readme = _read("README.md")

    assert "Markers: testing, contract" in catalog
    assert "Status: active" in catalog
    assert "synthetic test data" in catalog
    assert "`tests/fixtures/operational_scenarios/<scenario-id>/`" in catalog
    assert "docs/testing/operational_failure_scenario_catalog.md" in readme
    assert "operational_failure_scenario_catalog.md" in invariant_contract
    assert "production dump" in fixture_readme
    assert "실제 API 응답 원본" in fixture_readme


def test_operational_scenarios_have_stable_ids_and_anchors() -> None:
    catalog = _read("docs/testing/operational_failure_scenario_catalog.md")

    required = {
        "OFS-001": "historical backfill",
        "OFS-002": "bootstrap marker",
        "OFS-003": "NaN",
        "OFS-004": "relative_strength",
        "OFS-005": "partial snapshot",
        "OFS-006": "selected_release_date < trade_date",
        "OFS-007": "Docker compose",
        "OFS-008": "FastAPI",
        "OFS-101": "serving mirror",
        "OFS-102": "Airflow DAG task graph",
        "OFS-103": "explanation/report text",
        "OFS-104": "Calendar/FRED vintage coverage",
        "OFS-201": "shadow Postgres DB",
        "OFS-202": "market-state similarity feature",
        "OFS-203": "provider quota/rate limit/error",
        "OFS-204": "synthetic row",
    }

    for scenario_id, expected_text in required.items():
        assert f"`{scenario_id}`" in catalog
        assert expected_text in catalog

    for path in (
        "tests/pipeline/sync/test_gold_postgres_sync_scope.py",
        "tests/ops/test_backfill_once.py",
        "tests/dags/test_data_lake_bootstrap_dag_contract.py",
        "tests/pipeline/strategy_engine/test_json_safety.py",
        "tests/pipeline/strategy_engine/test_universe.py",
        "tests/pipeline/strategy_engine/test_report_context_env.py",
        "tests/pipeline/test_eod_silver_writer_idempotency.py",
        "tests/pipeline/test_gold_eod_features.py",
        "tests/pipeline/test_gold_macro_feature_v1.py",
        "tests/ops/test_reproducible_runtime_contract.py",
        "tests/api/test_report.py",
        "tests/ops/test_serving_freshness.py",
        "tests/observability/explainability/test_invariant_filter.py",
        "tests/ops/test_restore_shadow_db.py",
        "tests/ops/test_observability_chain_smoke.py",
        "tests/ops/test_db_synthetic_data_contract.py",
        "tests/pipeline/text/test_text_failopen.py",
    ):
        assert path in catalog


def test_existing_regression_tests_name_the_operational_failure_they_guard() -> None:
    guarded_files = {
        "tests/pipeline/sync/test_gold_postgres_sync_scope.py": "OFS-001",
        "tests/ops/test_backfill_once.py": "OFS-002",
        "tests/dags/test_data_lake_bootstrap_dag_contract.py": "OFS-002",
        "tests/pipeline/strategy_engine/test_json_safety.py": "OFS-003",
        "tests/api/test_report.py": "OFS-003",
        "tests/pipeline/strategy_engine/test_universe.py": "OFS-004",
        "tests/pipeline/strategy_engine/test_report_context_env.py": "OFS-004",
        "tests/ops/test_serving_freshness.py": "OFS-101",
        "tests/observability/explainability/test_invariant_filter.py": "OFS-103",
        "tests/pipeline/test_gold_macro_feature_v1.py": "OFS-104",
        "tests/ops/test_restore_shadow_db.py": "OFS-201",
        "tests/ops/test_observability_chain_smoke.py": "OFS-202",
        "tests/pipeline/test_ingest_macro.py": "OFS-203",
        "tests/pipeline/text/test_text_failopen.py": "OFS-203",
        "tests/ops/test_db_synthetic_data_contract.py": "OFS-204",
    }

    for path, scenario_id in guarded_files.items():
        assert scenario_id in _read(path)
