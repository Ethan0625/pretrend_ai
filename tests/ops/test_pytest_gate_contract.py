from __future__ import annotations

from pathlib import Path

from pretrend.testing.pytest_gates import (
    GATE_POLICIES,
    gate_matches,
    marker_names_for_path,
    normalize_gate,
)


ROOT = Path(__file__).parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_gate_policy_names_are_stable() -> None:
    assert set(GATE_POLICIES) == {
        "fast",
        "contracts",
        "runtime",
        "dags",
        "pre-dashboard",
        "personal",
        "all",
    }
    assert normalize_gate("contract") == "contracts"
    assert normalize_gate("dag") == "dags"
    assert normalize_gate("pre_dashboard") == "pre-dashboard"


def test_path_marker_classification_keeps_db_boundary_precise() -> None:
    assert marker_names_for_path("tests/models/test_gold_macro_model.py") == {"contract"}
    assert marker_names_for_path("tests/pipeline/sync/test_gold_postgres.py") == {
        "db",
        "invariant",
    }
    assert marker_names_for_path(
        "tests/pipeline/sync/test_gold_postgres_sync_scope.py"
    ) == {"invariant"}


def test_path_marker_classification_covers_operational_surfaces() -> None:
    assert marker_names_for_path("tests/api/test_meta.py") == {"contract"}
    assert marker_names_for_path("tests/dags/test_similarity_build_dag.py") == {
        "contract",
        "dag",
    }
    assert marker_names_for_path("tests/ops/test_backfill_once.py") == {
        "contract",
        "invariant",
    }
    assert marker_names_for_path("tests/archive/personal/test_bot/test_policy.py") == {
        "personal",
        "slow",
    }


def test_every_active_test_file_is_classified_for_a_gate() -> None:
    unclassified: list[str] = []
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("tests/archive/"):
            continue
        markers = marker_names_for_path(rel)
        if not markers & {"contract", "invariant", "db", "dag"}:
            unclassified.append(rel)

    assert unclassified == []


def test_gate_selection_semantics_are_guarded() -> None:
    assert gate_matches({"contract"}, "fast")
    assert gate_matches({"invariant"}, "contracts")
    assert gate_matches({"db", "invariant"}, "runtime")
    assert gate_matches({"dag", "contract"}, "dags")
    assert gate_matches({"contract"}, "pre-dashboard")
    assert gate_matches({"personal"}, "personal")

    assert not gate_matches({"db", "invariant"}, "fast")
    assert not gate_matches({"slow", "contract"}, "fast")
    assert not gate_matches({"personal"}, "pre-dashboard")
    assert not gate_matches({"contract"}, "personal")


def test_docs_and_ci_publish_named_pytest_gates() -> None:
    combined_docs = "\n".join(
        [
            _read("README.md"),
            _read("docs/testing/operational_invariant_test_contract.md"),
            _read("docs/project_summary.md"),
        ]
    )
    ci = _read(".github/workflows/ci.yaml")

    for gate in ("fast", "contracts", "runtime", "dags", "pre-dashboard"):
        assert f"pytest --gate {gate}" in combined_docs

    assert "pip install -r requirements/ci.txt" in ci
    assert "pytest --gate fast -q --tb=short" in ci
    assert "pytest -q" not in ci


def test_dev_docker_image_copies_pytest_gate_configuration() -> None:
    dockerfile = _read("docker/Dockerfile.dev")

    assert "COPY README.md pyproject.toml requirements.txt conftest.py reproduce.py ./" in dockerfile
    assert "COPY .github/ ./.github/" in dockerfile
    assert 'CMD ["pytest", "--gate", "fast", "-q", "--tb=short"]' in dockerfile
