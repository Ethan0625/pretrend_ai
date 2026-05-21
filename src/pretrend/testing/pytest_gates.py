"""Named pytest gate policies for operational invariant checks."""
from __future__ import annotations


GATE_MARKERS = frozenset({"contract", "invariant", "db", "dag", "slow", "personal"})

GATE_POLICIES = {
    "fast": "Exclude slow, db, and personal tests.",
    "contracts": "Run public contract and operational invariant tests.",
    "runtime": "Run backend/runtime contract, invariant, and db tests.",
    "dags": "Run Airflow DAG import and scheduling contract tests.",
    "pre-dashboard": "Run every non-personal test before dashboard work.",
    "personal": "Run frozen Personal Track regression tests only.",
    "all": "Run pytest collection without gate deselection.",
}

GATE_ALIASES = {
    "contract": "contracts",
    "contracts": "contracts",
    "invariant": "contracts",
    "invariants": "contracts",
    "runtime": "runtime",
    "backend": "runtime",
    "dag": "dags",
    "dags": "dags",
    "pre-dashboard": "pre-dashboard",
    "predashboard": "pre-dashboard",
    "dashboard": "pre-dashboard",
    "personal": "personal",
    "archive": "personal",
    "fast": "fast",
    "all": "all",
}


def normalize_gate(gate: str | None) -> str | None:
    if gate is None:
        return None
    normalized = gate.strip().lower().replace("_", "-")
    if not normalized:
        return None
    try:
        return GATE_ALIASES[normalized]
    except KeyError as exc:
        choices = ", ".join(sorted(GATE_POLICIES))
        raise ValueError(f"Unknown pytest gate '{gate}'. Choose one of: {choices}") from exc


def marker_names_for_path(rel_path: str) -> set[str]:
    """Return project-owned markers implied by a test file path."""
    rel = rel_path.replace("\\", "/")
    markers: set[str] = set()

    if rel.startswith("tests/archive/personal/"):
        return {"personal", "slow"}

    if rel.startswith("tests/api/"):
        markers.add("contract")

    if rel.startswith("tests/dags/"):
        markers.update({"dag", "contract"})

    if rel.startswith("tests/models/"):
        markers.add("contract")

    if rel.startswith("tests/ops/"):
        markers.add("contract")
        if "backfill" in rel:
            markers.add("invariant")

    if rel.startswith("tests/web/"):
        markers.add("contract")

    if rel.startswith("tests/observability/"):
        markers.add("invariant")
        if rel in {
            "tests/observability/test_boundary_imports.py",
            "tests/observability/regime/test_strategy_shim_exports.py",
        }:
            markers.add("contract")

    if rel.startswith("tests/pipeline/sync/test_gold_postgres.py"):
        markers.update({"db", "invariant"})
    elif rel.startswith("tests/pipeline/sync/"):
        markers.add("invariant")
    elif rel.startswith("tests/pipeline/text/test_text_dag.py"):
        markers.update({"dag", "contract"})
    elif rel.startswith("tests/pipeline/"):
        markers.add("invariant")
        if "contract" in rel or rel.startswith("tests/pipeline/strategy_engine/"):
            markers.add("contract")

    if rel in {
        "tests/test_config.py",
        "tests/test_models_base.py",
        "tests/test_smoke.py",
    }:
        markers.add("contract")

    return markers


def gate_matches(marker_names: set[str], gate: str | None) -> bool:
    normalized = normalize_gate(gate)
    if normalized is None or normalized == "all":
        return True
    if normalized == "fast":
        return not bool(marker_names & {"slow", "db", "personal"})
    if normalized == "contracts":
        return bool(marker_names & {"contract", "invariant"})
    if normalized == "runtime":
        return bool(marker_names & {"db", "contract", "invariant"})
    if normalized == "dags":
        return "dag" in marker_names
    if normalized == "pre-dashboard":
        return "personal" not in marker_names
    if normalized == "personal":
        return "personal" in marker_names
    raise AssertionError(f"Unhandled pytest gate: {normalized}")
