from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_destructive_db_tests_use_isolated_test_database() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "tests").rglob("test_*.py")) + sorted(
        (ROOT / "tests").rglob("conftest.py")
    ):
        text = path.read_text(encoding="utf-8")
        if "TRUNCATE" not in text and "DELETE FROM" not in text:
            continue
        if "isolated_test_engine" in text or "SAFE_TEST_DATABASE_RE" in text:
            continue
        offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []
