from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


def lookup(
    engine: Engine,
    use_case: str,
    query_date: date,
    model_id: str,
    prompt_version: str,
) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT report_json
                FROM explainability_cache
                WHERE use_case = :use_case
                  AND query_date = :query_date
                  AND model_id = :model_id
                  AND prompt_version = :prompt_version
                """
            ),
            {
                "use_case": use_case,
                "query_date": query_date,
                "model_id": model_id,
                "prompt_version": prompt_version,
            },
        ).scalar_one_or_none()
    return row


def store(
    engine: Engine,
    use_case: str,
    query_date: date,
    model_id: str,
    prompt_version: str,
    report_json: dict[str, Any],
) -> dict[str, Any]:
    output_hash = hashlib.sha256(
        json.dumps(report_json, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    built_at = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO explainability_cache
                  (use_case, query_date, model_id, prompt_version, report_json, output_hash, built_at)
                VALUES
                  (:use_case, :query_date, :model_id, :prompt_version, CAST(:report_json AS jsonb), :output_hash, :built_at)
                ON CONFLICT (use_case, query_date, model_id, prompt_version)
                DO UPDATE SET
                  report_json = EXCLUDED.report_json,
                  output_hash = EXCLUDED.output_hash,
                  built_at = EXCLUDED.built_at
                """
            ),
            {
                "use_case": use_case,
                "query_date": query_date,
                "model_id": model_id,
                "prompt_version": prompt_version,
                "report_json": json.dumps(report_json, ensure_ascii=False, sort_keys=True),
                "output_hash": output_hash,
                "built_at": built_at,
            },
        )
    return {"output_hash": output_hash, "built_at": built_at}


def invalidate(
    engine: Engine,
    *,
    use_case: str | None = None,
    prompt_version: str | None = None,
) -> int:
    clauses = []
    params: dict[str, Any] = {}
    if use_case is not None:
        clauses.append("use_case = :use_case")
        params["use_case"] = use_case
    if prompt_version is not None:
        clauses.append("prompt_version = :prompt_version")
        params["prompt_version"] = prompt_version
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with engine.begin() as conn:
        result = conn.execute(text(f"DELETE FROM explainability_cache {where}"), params)
    return int(result.rowcount or 0)
