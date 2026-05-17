from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
PLACEHOLDER_VALUES = {"", "CHANGE_ME", "DEMO_KEY", "<CHANGE_ME>"}


@dataclass(frozen=True)
class RuntimeOptions:
    dry_run: bool
    no_build: bool
    skip_backfill: bool
    force_backfill: bool
    skip_sync: bool
    skip_api: bool
    skip_airflow: bool
    skip_smoke: bool
    allow_placeholder_secrets: bool
    restore_dump: str | None
    backfill_start_date: str | None
    backfill_end_date: str | None
    backfill_marker_path: str | None
    gold_sync_start_date: str | None


def _parse_args(argv: Sequence[str] | None = None) -> RuntimeOptions:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap the Pretrend reproducible Docker runtime with one "
            "cross-platform command."
        )
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument("--no-build", action="store_true", help="Do not pass --build to compose up.")
    parser.add_argument("--skip-backfill", action="store_true", help="Skip the backfill-once bootstrap service.")
    parser.add_argument("--force-backfill", action="store_true", help="Run backfill even when the marker exists.")
    parser.add_argument("--skip-sync", action="store_true", help="Skip the Gold Parquet to Postgres sync safety pass.")
    parser.add_argument("--skip-api", action="store_true", help="Do not start the FastAPI service.")
    parser.add_argument("--skip-airflow", action="store_true", help="Do not initialize or start Airflow.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip final health checks.")
    parser.add_argument(
        "--allow-placeholder-secrets",
        action="store_true",
        help="Allow CHANGE_ME/DEMO_KEY placeholder values in .env.",
    )
    parser.add_argument(
        "--restore-dump",
        help=(
            "Optional Postgres dump to restore from /backups before backfill. "
            "Pass either a /backups/... path or a filename mounted under PRETREND_BACKUP_DIR."
        ),
    )
    parser.add_argument("--backfill-start-date", help="Override PRETREND_BACKFILL_START_DATE.")
    parser.add_argument("--backfill-end-date", help="Override PRETREND_BACKFILL_END_DATE.")
    parser.add_argument("--backfill-marker-path", help="Override PRETREND_BACKFILL_MARKER_PATH.")
    parser.add_argument(
        "--gold-sync-start-date",
        help="Override PRETREND_GOLD_SYNC_START_DATE for historical prepend sync.",
    )
    args = parser.parse_args(argv)
    return RuntimeOptions(**vars(args))


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _merged_env(dotenv_values: Mapping[str, str], options: RuntimeOptions) -> dict[str, str]:
    env = os.environ.copy()
    for key, value in dotenv_values.items():
        env.setdefault(key, value)

    if options.force_backfill:
        env["PRETREND_BACKFILL_FORCE"] = "1"
    if options.backfill_start_date:
        env["PRETREND_BACKFILL_START_DATE"] = options.backfill_start_date
    if options.backfill_end_date:
        env["PRETREND_BACKFILL_END_DATE"] = options.backfill_end_date
    if options.backfill_marker_path:
        env["PRETREND_BACKFILL_MARKER_PATH"] = options.backfill_marker_path
    if options.gold_sync_start_date:
        env["PRETREND_GOLD_SYNC_START_DATE"] = options.gold_sync_start_date
    elif options.force_backfill:
        start_date = env.get("PRETREND_BACKFILL_START_DATE")
        if start_date:
            env["PRETREND_GOLD_SYNC_START_DATE"] = start_date

    return env


def _truthy(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _host_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def _backfill_marker_exists(env: Mapping[str, str]) -> bool:
    marker = env.get("PRETREND_BACKFILL_MARKER_PATH") or "/app/data/meta/bootstrap_backfill_once.json"
    if marker.startswith("/app/data/"):
        host_data = _host_path(env.get("PRETREND_HOST_DATA_DIR") or "./data")
        relative_marker = marker[len("/app/data/") :]
        return (host_data / relative_marker).exists()
    return _host_path(marker).exists()


def _validate_env(env: Mapping[str, str], options: RuntimeOptions) -> list[str]:
    required = [
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_PORT",
    ]
    if not options.skip_api:
        required.append("PRETREND_API_KEY")
    if not options.skip_airflow:
        required.extend(["AIRFLOW_ADMIN_USER", "AIRFLOW_ADMIN_PASSWORD", "AIRFLOW_ADMIN_EMAIL"])
    if (
        not options.skip_backfill
        and not _backfill_marker_exists(env)
        and _truthy(env.get("PRETREND_BACKFILL_RUN_MACRO"), True)
    ):
        required.append("FRED_API_KEY")

    problems: list[str] = []
    for key in required:
        value = env.get(key, "")
        if not value:
            problems.append(f"{key} is required in .env")
        elif not options.allow_placeholder_secrets and value in PLACEHOLDER_VALUES:
            problems.append(f"{key} still has a placeholder value")
    return problems


def _command_text(command: Sequence[str]) -> str:
    return shlex.join(command)


def _run(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    dry_run: bool,
    timeout: int | None = None,
) -> None:
    print(f"\n$ {_command_text(command)}", flush=True)
    if dry_run:
        return
    subprocess.run(
        list(command),
        cwd=ROOT,
        env=dict(env),
        check=True,
        timeout=timeout,
    )


def _compose_command(dry_run: bool) -> list[str]:
    candidates: list[list[str]] = []
    if shutil.which("docker"):
        candidates.append(["docker", "compose"])
    if shutil.which("docker-compose"):
        candidates.append(["docker-compose"])

    if dry_run:
        return candidates[0] if candidates else ["docker", "compose"]

    for candidate in candidates:
        try:
            subprocess.run(
                candidate + ["version"],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return candidate
        except (OSError, subprocess.CalledProcessError):
            continue
    raise RuntimeError("Docker Compose was not found. Install Docker Desktop or Docker Engine with Compose.")


def _compose_up_args(
    services: Sequence[str],
    *,
    detached: bool,
    build: bool,
    force_recreate: bool = False,
) -> list[str]:
    args = ["up"]
    if detached:
        args.append("-d")
    if build:
        args.append("--build")
    if force_recreate:
        args.append("--force-recreate")
    args.extend(services)
    return args


def _run_gold_sync(compose: Sequence[str], env: Mapping[str, str], options: RuntimeOptions) -> None:
    code = (
        "from pretrend.pipeline.sync.gold_postgres import sync_gold_macro, sync_gold_eod; "
        "print(sync_gold_macro()); print(sync_gold_eod())"
    )
    _run(
        list(compose)
        + [
            "--profile",
            "ops",
            "run",
            "--rm",
            "worker",
            "python",
            "-c",
            code,
        ],
        env=env,
        dry_run=options.dry_run,
    )


def _restore_dump(compose: Sequence[str], env: Mapping[str, str], options: RuntimeOptions) -> None:
    if not options.restore_dump:
        return
    dump_path = options.restore_dump
    if not dump_path.startswith("/backups/"):
        dump_path = f"/backups/{Path(dump_path).name}"
    restore_command = (
        f'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
        f"--no-owner --no-privileges {shlex.quote(dump_path)}"
    )
    _run(
        list(compose) + ["exec", "-T", "postgres", "sh", "-c", restore_command],
        env=env,
        dry_run=options.dry_run,
    )


def _smoke_check(options: RuntimeOptions) -> None:
    if options.skip_smoke or options.dry_run:
        return
    if not options.skip_api:
        deadline = time.time() + 60
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:8000/health", timeout=5) as response:
                    if 200 <= response.status < 300:
                        print("\nAPI health ok: http://localhost:8000/health")
                        break
            except Exception as exc:  # pragma: no cover - depends on local Docker runtime
                last_error = exc
                time.sleep(2)
        else:
            raise RuntimeError(f"API health check failed: {last_error}")
    if not options.skip_airflow:
        print("Airflow UI: http://localhost:8080")


def run(options: RuntimeOptions) -> int:
    env_path = ROOT / ".env"
    if not env_path.exists():
        print(
            ".env was not found. Create it from .env.example and fill local secrets first:\n"
            "  cp .env.example .env",
            file=sys.stderr,
        )
        return 2

    dotenv_values = _read_dotenv(env_path)
    env = _merged_env(dotenv_values, options)
    problems = _validate_env(env, options)
    if problems:
        print("Runtime environment is not ready:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    compose = _compose_command(options.dry_run)
    build = not options.no_build

    _run(list(compose) + ["config", "--quiet"], env=env, dry_run=options.dry_run)
    _run(list(compose) + _compose_up_args(["postgres"], detached=True, build=False), env=env, dry_run=options.dry_run)
    _restore_dump(compose, env, options)

    if not options.skip_backfill:
        _run(
            list(compose)
            + ["--profile", "bootstrap"]
            + _compose_up_args(["backfill-once"], detached=False, build=build, force_recreate=True),
            env=env,
            dry_run=options.dry_run,
        )

    if not options.skip_sync:
        _run_gold_sync(compose, env, options)

    if not options.skip_api:
        _run(list(compose) + _compose_up_args(["api"], detached=True, build=build), env=env, dry_run=options.dry_run)

    if not options.skip_airflow:
        _run(
            list(compose)
            + ["--profile", "airflow"]
            + _compose_up_args(["airflow-init"], detached=False, build=build, force_recreate=True),
            env=env,
            dry_run=options.dry_run,
        )
        _run(
            list(compose)
            + ["--profile", "airflow"]
            + _compose_up_args(["airflow-webserver", "airflow-scheduler"], detached=True, build=build),
            env=env,
            dry_run=options.dry_run,
        )

    _run(list(compose) + ["ps", "-a"], env=env, dry_run=options.dry_run)
    _smoke_check(options)
    print("\nPretrend reproducible runtime is ready.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    options = _parse_args(argv)
    try:
        return run(options)
    except subprocess.CalledProcessError as exc:
        print(f"\nCommand failed with exit code {exc.returncode}: {_command_text(exc.cmd)}", file=sys.stderr)
        return exc.returncode
    except Exception as exc:
        print(f"\nRuntime reproduction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
