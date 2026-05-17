from __future__ import annotations

import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.contract

ROOT = Path(__file__).parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compose_runtime_paths_are_variable_driven() -> None:
    compose = _read("docker-compose.yml")

    assert "${PRETREND_POSTGRES_DATA_DIR:-./.local/postgres-data}:/var/lib/postgresql/data" in compose
    assert "${PRETREND_BACKUP_DIR:-./.local/backups}:/backups" in compose
    assert "${PRETREND_HOST_DATA_DIR:-./data}:/app/data" in compose
    assert "${PRETREND_HOST_LOG_DIR:-./logs}:/app/logs" in compose
    assert "${PRETREND_STATE_DIR:-./state}:/app/state" in compose
    assert "${PRETREND_CODEX_BIN_DIR:-./codex-bin}:/opt/pretrend/codex-bin:ro" in compose
    assert "${PRETREND_CODEX_HOME_DIR:-./codex-home}:/root/.codex" in compose
    assert "PRETREND_DATA_ROOT: /app/data" in compose
    assert "PRETREND_STATE_DB: ${PRETREND_STATE_DB:-/app/state/orchestrator.db}" in compose
    assert "PRETREND_CODEX_BIN: ${PRETREND_CODEX_BIN:-}" in compose
    assert "PRETREND_CODEX_BIN_DIR: /opt/pretrend/codex-bin" in compose


def test_compose_has_ops_worker_for_data_lake_backfill_mount() -> None:
    compose = _read("docker-compose.yml")

    assert "  worker:" in compose
    assert "dockerfile: docker/Dockerfile.dev" in compose
    assert "profiles:" in compose
    assert "- ops" in compose
    assert "PRETREND_ENV: ${PRETREND_ENV:-backfill}" in compose


def test_compose_has_one_shot_bootstrap_backfill_service() -> None:
    compose = _read("docker-compose.yml")

    assert "  backfill-once:" in compose
    assert "container_name: pretrend-backfill-once" in compose
    assert "- bootstrap" in compose
    assert "PRETREND_BACKFILL_ON_START: ${PRETREND_BACKFILL_ON_START:-1}" in compose
    assert "PRETREND_BACKFILL_START_DATE: ${PRETREND_BACKFILL_START_DATE:-2003-01-01}" in compose
    assert "PRETREND_GOLD_SYNC_FULL: ${PRETREND_GOLD_SYNC_FULL:-0}" in compose
    assert "PRETREND_GOLD_SYNC_START_DATE: ${PRETREND_GOLD_SYNC_START_DATE:-}" in compose
    assert "PRETREND_BACKFILL_MARKER_PATH: ${PRETREND_BACKFILL_MARKER_PATH:-/app/data/meta/bootstrap_backfill_once.json}" in compose
    assert 'command: ["python", "-m", "pretrend.ops.backfill_once"]' in compose


def test_cross_platform_reproduce_entrypoint_exists() -> None:
    wrapper = _read("reproduce.py")
    module = _read("src/pretrend/ops/reproduce_runtime.py")
    readme = _read("README.md")
    contract = _read("docs/operation/reproducible_runtime_contract.md")
    environment = _read("docs/environment.md")
    env_example = _read(".env.example")

    assert "from pretrend.ops.reproduce_runtime import main" in wrapper
    assert "argparse.ArgumentParser" in module
    assert "subprocess.run(" in module
    assert "shell=True" not in module
    assert '"docker", "compose"' in module
    assert "--skip-airflow" in module
    assert "--skip-backfill" in module
    assert "--restore-dump" in module
    assert "--dry-run" in module
    assert "python reproduce.py" in readme
    assert "python reproduce.py" in contract
    assert "python reproduce.py" in environment
    assert "FRED_API_KEY=DEMO_KEY" in env_example


def test_observability_dags_have_bootstrap_marker_guard() -> None:
    for dag_path in (
        "dags/macro_pipeline_dag.py",
        "dags/eod_pipeline_dag.py",
        "dags/gold_postgres_sync_dag.py",
    ):
        dag_source = _read(dag_path)
        assert "ensure_data_lake_bootstrap" in dag_source
        assert "run_backfill_once" in dag_source


def test_docs_architecture_reference_docs_are_classified_and_moved() -> None:
    deleted_root_docs = {
        "docs/dev_plan.md",
        "docs/api_spec.md",
        "docs/strategy_architecture.md",
        "docs/strategy_engine_design.md",
        "docs/universe_design.md",
        "docs/data_ingest_datasources.md",
        "docs/data_requirements.md",
        "docs/market_structure_data_inventory.md",
        "docs/agent_adoption_notes.md",
        "docs/milestones.md",
    }
    for path in deleted_root_docs:
        assert not (ROOT / path).exists()

    moved_docs = {
        "docs/architecture/strategy_architecture.md": "Markers: architecture, legacy",
        "docs/architecture/strategy_engine_design.md": "Markers: architecture, contract, legacy",
        "docs/architecture/universe_design.md": "Markers: architecture, contract, legacy",
        "docs/data/data_ingest_datasources.md": "Markers: architecture, contract",
        "docs/data/data_requirements.md": "Markers: architecture, contract",
        "docs/data/market_structure_data_inventory.md": "Markers: architecture, contract",
        "docs/operation/agent_adoption_notes.md": "Markers: operation, agent",
        "docs/roadmap/milestones.md": "Markers: roadmap",
    }
    for path, marker in moved_docs.items():
        text = _read(path)
        assert marker in text
        assert re.search(r"(?m)^Status: (active|reference|legacy)$", text)

    old_references = {
        "docs/dev_plan.md",
        "docs/api_spec.md",
        "docs/strategy_architecture.md",
        "docs/strategy_engine_design.md",
        "docs/universe_design.md",
        "docs/data_ingest_datasources.md",
        "docs/data_requirements.md",
        "docs/market_structure_data_inventory.md",
        "docs/agent_adoption_notes.md",
        "docs/milestones.md",
    }
    scan_roots = [
        ROOT / "README.md",
        ROOT / ".agent",
        ROOT / "docs",
        ROOT / "src",
        ROOT / "tests",
    ]
    violations: list[str] = []
    for root in scan_roots:
        files = [root] if root.is_file() else root.rglob("*")
        for file_path in files:
            if file_path == Path(__file__):
                continue
            if not file_path.is_file() or file_path.suffix not in {".md", ".py", ".txt"}:
                continue
            text = file_path.read_text(encoding="utf-8")
            for old_ref in old_references:
                if old_ref in text:
                    violations.append(f"{file_path.relative_to(ROOT)}: {old_ref}")
    assert violations == []


def test_public_entry_docs_describe_current_runtime_not_internal_refactor_plan() -> None:
    readme = _read("README.md")
    system_overview = _read("docs/system_overview.md")
    project_summary = _read("docs/project_summary.md")
    milestones = _read("docs/roadmap/milestones.md")

    combined = "\n".join([readme, system_overview, project_summary, milestones])

    assert "Reproducible Market Data Platform" in combined
    assert "market data platform" in combined
    assert "P30 Reproducible Runtime | 완료" in milestones
    assert "현재 범위" in readme
    assert "보관된 strategy/backtest 구현 맥락" in readme
    assert ".agent/REFACTOR_2026Q2.md" not in readme
    assert "Two-Track 운영 원칙" not in readme
    assert "트랙 분리" not in readme


def test_data_model_document_covers_raw_to_serving_schema() -> None:
    data_model = _read("docs/data/data_model.md")
    readme = _read("README.md")

    assert "Markers: architecture, contract" in data_model
    assert "Status: active" in data_model
    assert "External raw source" in data_model
    assert "Bronze Parquet" in data_model
    assert "Gold Parquet SOT" in data_model
    assert "Postgres serving mirror/cache" in data_model
    assert "data/bronze/macro/econ_indicators" in data_model
    assert "data/bronze/eod/daily_prices" in data_model
    assert "data/silver/calendar/fred_vintages" in data_model
    assert "data/gold/macro/macro_features" in data_model
    assert "data/gold/eod/eod_features" in data_model
    assert "`gold_macro_features`" in data_model
    assert "`gold_eod_features`" in data_model
    assert "`gold_market_state_similarity_feature`" in data_model
    assert "`similarity_regime`" in data_model
    assert "`explainability_cache`" in data_model
    assert "selected_release_date < trade_date" in data_model
    assert "`/docs/data/data_model.md`" in readme


def test_compose_has_airflow_profile_for_scheduled_dags() -> None:
    compose = _read("docker-compose.yml")

    assert "  airflow-init:" in compose
    assert "  airflow-webserver:" in compose
    assert "  airflow-scheduler:" in compose
    assert "dockerfile: docker/Dockerfile.airflow" in compose
    assert "- airflow" in compose
    assert "AIRFLOW__CORE__EXECUTOR: SequentialExecutor" in compose
    assert "AIRFLOW__CORE__DAGS_FOLDER: /opt/airflow/dags" in compose
    assert "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: sqlite:////opt/airflow/local/airflow.db" in compose
    assert "AIRFLOW__WEBSERVER__WEB_SERVER_PORT: 8080" in compose
    assert "${PRETREND_HOST_DATA_DIR:-./data}:/app/data" in compose
    assert "${PRETREND_AIRFLOW_HOME_DIR:-./airflow_pretrend}:/opt/airflow/local" in compose
    assert "${PRETREND_AIRFLOW_LOG_DIR:-./airflow_pretrend/logs}:/opt/airflow/logs" in compose
    assert "${PRETREND_HOST_DAGS_DIR:-./dags}:/opt/airflow/dags:ro" in compose
    assert "PRETREND_REPORT_API_URL: ${PRETREND_REPORT_API_URL:-http://api:8000/api/v1/report/strategy/analyze}" in compose
    assert "AIRFLOW_ADMIN_USER: ${AIRFLOW_ADMIN_USER?AIRFLOW_ADMIN_USER must be declared in .env}" in compose
    assert "AIRFLOW_ADMIN_PASSWORD: ${AIRFLOW_ADMIN_PASSWORD?AIRFLOW_ADMIN_PASSWORD must be declared in .env}" in compose
    assert "AIRFLOW_ADMIN_USER:-airflow" not in compose
    assert "AIRFLOW_ADMIN_PASSWORD:-CHANGE_ME" not in compose
    assert "airflow users reset-password" in compose
    assert "condition: service_completed_successfully" in compose
    assert "command: webserver" in compose
    assert "command: scheduler" in compose


def test_docker_ignore_files_exclude_secrets_data_and_runtime_outputs() -> None:
    required_patterns = {
        ".env",
        ".env.*",
        ".local/",
        "airflow_pretrend/",
        "data/",
        "logs/",
        "result/",
        "state/",
        "codex-bin/",
        "codex-home/",
    }
    for ignore_file in (
        ".dockerignore",
        "docker/Dockerfile.api.dockerignore",
        "docker/Dockerfile.dev.dockerignore",
        "docker/Dockerfile.airflow.dockerignore",
    ):
        patterns = set(_read(ignore_file).splitlines())
        missing = sorted(required_patterns - patterns)
        assert missing == [], f"{ignore_file} missing {missing}"


def test_api_and_dev_dockerfiles_keep_runtime_roles_separate() -> None:
    api_dockerfile = _read("docker/Dockerfile.api")
    dev_dockerfile = _read("docker/Dockerfile.dev")
    airflow_dockerfile = _read("docker/Dockerfile.airflow")

    assert "requirements/api.txt" in api_dockerfile
    assert "requirements/ci.txt" not in api_dockerfile
    assert "COPY tests/" not in api_dockerfile
    assert "COPY docs/" not in api_dockerfile

    assert "requirements/ci.txt" in dev_dockerfile
    assert "COPY tests/ ./tests/" in dev_dockerfile
    assert "COPY docs/ ./docs/" in dev_dockerfile
    assert "COPY docker/ ./docker/" in dev_dockerfile
    assert "COPY requirements/ ./requirements/" in dev_dockerfile

    assert "apache/airflow:${AIRFLOW_VERSION}-python3.11" in airflow_dockerfile
    assert "ARG AIRFLOW_VERSION=2.10.5" in airflow_dockerfile
    assert "requirements/airflow.txt" in airflow_dockerfile
    assert "requirements/api.txt" not in airflow_dockerfile
    assert "requirements/ci.txt" not in airflow_dockerfile
    assert "COPY --chown=airflow:0 dags/ ./dags/" in airflow_dockerfile
    assert "COPY tests/" not in airflow_dockerfile
    assert "COPY docs/" not in airflow_dockerfile

    if not (ROOT / "scripts").exists():
        assert "COPY scripts/" not in api_dockerfile
        assert "COPY scripts/" not in dev_dockerfile
        assert "COPY scripts/" not in airflow_dockerfile


def test_readme_and_runtime_contract_include_p30_verification_gate() -> None:
    readme = _read("README.md")
    contract = _read("docs/operation/reproducible_runtime_contract.md")

    required_snippets = [
        "docker compose config --quiet",
        "docker compose build",
        "docker compose up -d postgres api",
        "docker build -t pretrend-dev -f docker/Dockerfile.dev .",
        "docker run --rm pretrend-dev pytest --gate fast -q --tb=short",
        "pg_dump -U",
        "pg_restore -l",
        "pretrend_restore_check",
        "Backfill은 최신 dump가 없거나 오래된 경우에만 사용한다",
        "docker compose --profile bootstrap up --build backfill-once",
        "신규 clone / 새 머신",
        "copy .env.example .env",
        "docker compose --profile airflow up airflow-init",
        "`airflow-init`은 1회성 initializer",
    ]
    combined = f"{readme}\n{contract}"
    missing = [snippet for snippet in required_snippets if snippet not in combined]
    assert missing == []


def test_env_example_keeps_secret_like_values_as_placeholders() -> None:
    allowed_values = {"", "CHANGE_ME", "DEMO_KEY"}
    violations: list[str] = []

    for line in _read(".env.example").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        if re.search(r"(API_KEY|TOKEN|PASSWORD|SECRET)$", key):
            if value not in allowed_values:
                violations.append(key)

    assert violations == []


def test_default_requirements_do_not_install_gpu_runtime_stack() -> None:
    requirements = _read("requirements.txt")
    def active_lines(text: str) -> str:
        return "\n".join(
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    combined_runtime_requirements = "\n".join(
        [
            active_lines(requirements),
            active_lines(_read("requirements/api.txt")),
            active_lines(_read("requirements/ci.txt")),
            active_lines(_read("requirements/airflow.txt")),
        ]
    ).lower()

    assert "-r requirements/ci.txt" in requirements
    assert "-r api.txt" in _read("requirements/ci.txt")
    for forbidden in (
        "cuda",
        "cupy",
        "nvidia-",
        "torch",
        "vllm",
        "xformers",
        "triton",
    ):
        assert forbidden not in combined_runtime_requirements
