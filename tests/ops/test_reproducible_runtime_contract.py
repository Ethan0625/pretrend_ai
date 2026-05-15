from __future__ import annotations

import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.contract

ROOT = Path(__file__).parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_compose_runtime_paths_are_variable_driven() -> None:
    compose = _read("docker-compose.yml")

    assert "${PRETREND_POSTGRES_DATA_DIR:-./.local/postgres-data}:/var/lib/postgresql/data" in compose
    assert "${PRETREND_BACKUP_DIR:-./.local/backups}:/backups" in compose
    assert "${PRETREND_HOST_DATA_DIR:-./data}:/app/data" in compose
    assert "${PRETREND_HOST_LOG_DIR:-./logs}:/app/logs" in compose


def test_docker_ignore_files_exclude_secrets_data_and_runtime_outputs() -> None:
    required_patterns = {
        ".env",
        ".env.*",
        ".local/",
        "airflow_pretrend/",
        "data/",
        "logs/",
        "result/",
    }
    for ignore_file in (
        ".dockerignore",
        "Dockerfile.api.dockerignore",
        "Dockerfile.dev.dockerignore",
    ):
        patterns = set(_read(ignore_file).splitlines())
        missing = sorted(required_patterns - patterns)
        assert missing == [], f"{ignore_file} missing {missing}"


def test_api_and_dev_dockerfiles_keep_runtime_roles_separate() -> None:
    api_dockerfile = _read("Dockerfile.api")
    dev_dockerfile = _read("Dockerfile.dev")

    assert "requirements_api.txt" in api_dockerfile
    assert "requirements_ci.txt" not in api_dockerfile
    assert "COPY tests/" not in api_dockerfile
    assert "COPY docs/" not in api_dockerfile

    assert "requirements_ci.txt" in dev_dockerfile
    assert "COPY tests/ ./tests/" in dev_dockerfile
    assert "COPY docs/ ./docs/" in dev_dockerfile


def test_readme_and_runtime_contract_include_p30_verification_gate() -> None:
    readme = _read("README.md")
    contract = _read("docs/operation/reproducible_runtime_contract.md")

    required_snippets = [
        "docker compose config --quiet",
        "docker compose build",
        "docker compose up -d postgres api",
        "docker build -t pretrend-dev -f Dockerfile.dev .",
        "docker run --rm pretrend-dev pytest -q --tb=short",
        "pg_dump -U",
        "pg_restore -l",
        "pretrend_restore_check",
        "backfill only when",
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
