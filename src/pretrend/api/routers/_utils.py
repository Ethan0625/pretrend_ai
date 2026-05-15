from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def row_to_dict(row: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    exclude = exclude or set()
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in exclude
    }


def not_found(resource: str, query: dict[str, Any]) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "detail": "Not found",
            "resource": resource,
            "query": query,
        },
    )


def validate_timeline_range(start, end) -> None:
    if start > end:
        raise HTTPException(status_code=422, detail="start must be before or equal to end")
    if (end - start).days > 730:
        raise HTTPException(status_code=422, detail="Range exceeds 2 years")
