from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from sqlalchemy.engine import URL, make_url


SHADOW_DATABASE_PREFIX = "pretrend_restore_check_"
_SAFE_SHADOW_DATABASE_RE = re.compile(r"^pretrend_restore_check_[A-Za-z0-9_]{1,37}$")


@dataclass(frozen=True)
class RestoreShadowCommandPlan:
    """Commands for restoring a dump into a disposable shadow database."""

    admin_database_url: str
    shadow_database_url: str
    create: list[str]
    restore: list[str]
    verify: list[str]
    drop: list[str]

    @property
    def commands(self) -> tuple[Sequence[str], ...]:
        return (self.create, self.restore, self.verify, self.drop)


def is_safe_shadow_database_name(database_name: str) -> bool:
    """OFS-201: restore checks must only target disposable shadow databases."""

    return bool(_SAFE_SHADOW_DATABASE_RE.fullmatch(database_name))


def shadow_database_url(active_database_url: str, shadow_database: str) -> str:
    """Return a libpq-compatible URL for a safe disposable restore database."""

    active = make_url(active_database_url)
    if not is_safe_shadow_database_name(shadow_database):
        raise ValueError(
            f"shadow database must match {SHADOW_DATABASE_PREFIX}<safe_suffix>: "
            f"{shadow_database!r}"
        )
    if active.database == shadow_database:
        raise ValueError("shadow database must differ from the active database")
    return _as_libpq_url(active.set(database=shadow_database))


def build_pg_restore_shadow_commands(
    *,
    active_database_url: str,
    dump_path: str | Path,
    shadow_database: str,
) -> RestoreShadowCommandPlan:
    """OFS-201: build a restore verification plan that never restores into active DB."""

    active = make_url(active_database_url)
    admin_url = _as_libpq_url(active)
    shadow_url = shadow_database_url(active_database_url, shadow_database)
    dump = str(Path(dump_path))

    return RestoreShadowCommandPlan(
        admin_database_url=admin_url,
        shadow_database_url=shadow_url,
        create=[
            "psql",
            admin_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f'CREATE DATABASE "{shadow_database}";',
        ],
        restore=[
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            shadow_url,
            dump,
        ],
        verify=[
            "psql",
            shadow_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-Atc",
            "SELECT COUNT(*) FROM alembic_version;",
        ],
        drop=[
            "psql",
            admin_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f'DROP DATABASE IF EXISTS "{shadow_database}";',
        ],
    )


def _as_libpq_url(url: URL) -> str:
    return url.set(drivername=url.get_backend_name()).render_as_string(hide_password=False)
