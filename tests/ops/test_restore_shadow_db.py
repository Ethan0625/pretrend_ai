from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from pretrend.ops.restore_shadow import (
    SHADOW_DATABASE_PREFIX,
    build_pg_restore_shadow_commands,
    is_safe_shadow_database_name,
    shadow_database_url,
)


ACTIVE_URL = "postgresql+psycopg2://pretrend:secret@localhost:5432/pretrend"


def test_ofs_201_shadow_database_name_requires_disposable_prefix() -> None:
    """OFS-201: restore verification must not accept an active DB name."""

    assert is_safe_shadow_database_name("pretrend_restore_check_ci_20260517")
    assert not is_safe_shadow_database_name("pretrend")
    assert not is_safe_shadow_database_name("pretrend_restore_check_ci;DROP DATABASE pretrend")
    assert not is_safe_shadow_database_name("pretrend_restore_check_")


def test_ofs_201_shadow_database_url_strips_sqlalchemy_driver() -> None:
    """OFS-201: pg_restore commands need libpq URLs, not SQLAlchemy driver URLs."""

    url = shadow_database_url(ACTIVE_URL, "pretrend_restore_check_ci")

    assert url == "postgresql://pretrend:secret@localhost:5432/pretrend_restore_check_ci"
    assert "+psycopg2" not in url


def test_ofs_201_restore_plan_never_targets_active_database(tmp_path: Path) -> None:
    """OFS-201: dump restore checks are planned against a shadow DB only."""

    dump_path = tmp_path / "pretrend.dump"
    plan = build_pg_restore_shadow_commands(
        active_database_url=ACTIVE_URL,
        dump_path=dump_path,
        shadow_database="pretrend_restore_check_ci",
    )

    assert plan.admin_database_url == "postgresql://pretrend:secret@localhost:5432/pretrend"
    assert plan.shadow_database_url.endswith("/pretrend_restore_check_ci")
    assert plan.create[-1] == 'CREATE DATABASE "pretrend_restore_check_ci";'
    assert plan.restore[plan.restore.index("--dbname") + 1] == plan.shadow_database_url
    assert plan.restore[-1] == str(dump_path)
    assert plan.verify[1] == plan.shadow_database_url
    assert plan.drop[-1] == 'DROP DATABASE IF EXISTS "pretrend_restore_check_ci";'
    assert "pretrend_restore_check_ci" in " ".join(plan.restore)
    assert "postgresql://pretrend:secret@localhost:5432/pretrend " not in " ".join(plan.restore)


def test_ofs_201_rejects_active_or_unsafe_shadow_names() -> None:
    """OFS-201: restore checks fail closed when the target DB is unsafe."""

    with pytest.raises(ValueError, match="shadow database must differ"):
        shadow_database_url(
            "postgresql+psycopg2://pretrend:secret@localhost:5432/pretrend_restore_check_ci",
            "pretrend_restore_check_ci",
        )

    with pytest.raises(ValueError, match=SHADOW_DATABASE_PREFIX):
        shadow_database_url(ACTIVE_URL, "postgres")


@pytest.mark.db
@pytest.mark.slow
def test_ofs_201_restore_dump_into_shadow_database_when_configured() -> None:
    """OFS-201: an optional live dump restore check runs only against a shadow DB."""

    dump = os.getenv("PRETREND_RESTORE_CHECK_DUMP")
    if not dump:
        pytest.skip("set PRETREND_RESTORE_CHECK_DUMP to run live shadow restore check")
    dump_path = Path(dump)
    if not dump_path.exists():
        pytest.skip(f"restore check dump does not exist: {dump_path}")
    for binary in ["psql", "pg_restore"]:
        if shutil.which(binary) is None:
            pytest.skip(f"{binary} is required for live shadow restore check")

    try:
        from pretrend.config import get_settings
    except Exception as exc:
        pytest.skip(f"postgres settings unavailable for restore check: {exc}")

    shadow_database = f"{SHADOW_DATABASE_PREFIX}{uuid.uuid4().hex[:12]}"
    plan = build_pg_restore_shadow_commands(
        active_database_url=get_settings().database_url,
        dump_path=dump_path,
        shadow_database=shadow_database,
    )

    try:
        _run(plan.drop)
        _run(plan.create)
        _run(plan.restore)
        result = _run(plan.verify)
        assert int(result.stdout.strip()) >= 1
    finally:
        _run(plan.drop, check=False)


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, capture_output=True, text=True)
