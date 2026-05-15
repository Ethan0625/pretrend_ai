from __future__ import annotations

from typing import Any


class FakeResult:
    def __init__(
        self,
        *,
        scalar: Any = None,
        scalars: list[Any] | None = None,
        one: tuple[Any, ...] | None = None,
        all_rows: list[Any] | None = None,
    ) -> None:
        self._scalar = scalar
        self._scalars = scalars or []
        self._one = one
        self._all_rows = all_rows

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list[Any]:
        return self._all_rows if self._all_rows is not None else self._scalars

    def one(self) -> tuple[Any, ...]:
        if self._one is None:
            raise AssertionError("FakeResult.one() was called without a configured row")
        return self._one


class FakeSession:
    def __init__(self, *results: FakeResult) -> None:
        self.results = list(results)
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        if not self.results:
            raise AssertionError(f"unexpected SQL execution: {statement}")
        return self.results.pop(0)
