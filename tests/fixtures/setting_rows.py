"""`ops.setting` held in memory, answering the two statements a console switch makes.

`brain.ops.setting_store` makes one select over a namespace and one upsert, and the routes behind
the Features, Scheduled jobs and Prompts screens reach the table only through those. A stub that
answers exactly those two, by the columns the select names and the table the insert targets, lets
a route test watch a switch land in the row and the next read see it, without a database this
machine cannot start. Any other statement is the caller's to answer.

The upsert is read back from the statement's own compiled parameters rather than from arguments
the test supplies, so a route that wrote the wrong key or value is caught here rather than agreed
with.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.sql.dml import Insert
from sqlalchemy.sql.selectable import Select

from brain.ops.setting_store import SettingState

#: The columns `brain.ops.setting_store.namespace_rows` selects, in order.
NAMESPACE_COLUMNS = ["key", "value_type", "value", "updated_by", "updated_at"]


class Result:
    """Enough of a SQLAlchemy result for every read the console routes make."""

    def __init__(self, rows: Iterable[Any]) -> None:
        self._rows = list(rows)

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalars(self) -> Result:
        return self

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class Row(tuple[Any, ...]):
    """A result row readable as a tuple and, like SQLAlchemy's, by `_tuple()`."""

    def _tuple(self) -> tuple[Any, ...]:
        return tuple(self)


class SettingRows:
    """The live rows of `ops.setting`, by key, and every write made to them."""

    def __init__(self) -> None:
        self.rows: dict[str, SettingState] = {}
        self.writes: list[dict[str, Any]] = []

    def hold(self, key: str, value: Any, *, value_type: str, by: str = "u_someone") -> None:
        """A row as if somebody had written it before the test began."""
        self.rows[key] = SettingState(
            key=key,
            value_type=value_type,
            value=value,
            updated_by=by,
            updated_at=datetime(2019, 1, 1, tzinfo=UTC),
        )

    def answer(self, statement: Any) -> Result | None:
        """The result for a settings statement, or None for one that is not about this table."""
        if isinstance(statement, Select):
            columns = [one["name"] for one in statement.column_descriptions]
            if columns != NAMESPACE_COLUMNS:
                return None
            prefix = str(statement.compile().params["key_1"]).replace("/", "")
            return Result(
                Row((s.key, s.value_type, s.value, s.updated_by, s.updated_at))
                for key, s in sorted(self.rows.items())
                if key.startswith(prefix)
            )
        if isinstance(statement, Insert) and statement.table.name == "setting":
            values = statement.compile().params
            written = {
                "key": values["key"],
                "value_type": values["value_type"],
                "value": values["value"],
                "updated_by": values["updated_by"],
            }
            self.writes.append(written)
            self.rows[written["key"]] = SettingState(
                key=written["key"],
                value_type=written["value_type"],
                value=written["value"],
                updated_by=written["updated_by"],
                updated_at=datetime.now(UTC),
            )
            return Result([])
        return None
