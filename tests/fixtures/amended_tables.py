"""A table as the migration that created it built it, before a later migration added columns.

The creating migration's DDL is compared against the model in several test files, and the model
describes the database as it is now. A later migration that adds a column (`0097` adds one to
`ops.model_attempt` and two to `agent.agent`) makes that comparison fail for being accurate. So
the comparison is made against a copy of the model without the columns a later migration added,
and without the checks that read them, and the adding migration's own test holds it to adding
exactly these. A column in the model and in neither migration is still caught.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from sqlalchemy import Table
from sqlalchemy.engine import Dialect
from sqlalchemy.schema import CreateTable

#: Columns a later migration added to a table another migration created, by the table.
ADDED_LATER: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "ops.model_attempt": ("data_categories",),
        "agent.agent": ("model_pin_provider", "model_pin_model"),
    }
)


def created_ddl(original: Table, dialect: Dialect) -> str:
    """The CREATE TABLE for `original` without the columns a later migration added.

    Cut from the compiled statement line by line rather than from a copied table, because a copy
    reorders the constraints and the comparison is on text: each column and constraint is one
    line of the compiled statement, and the lines naming an added column are the ones dropped.
    """
    compiled = str(CreateTable(original).compile(dialect=dialect))
    added = ADDED_LATER.get(original.fullname, ())
    if not added:
        return compiled
    head, _, rest = compiled.partition(OPEN)
    body, _, tail = rest.rpartition(CLOSE)
    kept = [
        line
        for line in body.split(BETWEEN)
        if not any(line.startswith(f"{name} ") for name in added)
        and not (line.startswith("CONSTRAINT") and any(name in line for name in added))
    ]
    return head + OPEN + BETWEEN.join(kept) + CLOSE + tail


#: How SQLAlchemy lays out a CREATE TABLE: one column or constraint per tab-indented line.
OPEN = "(\n\t"
BETWEEN = ", \n\t"
CLOSE = "\n)"
