"""What each department's connected sources hold, counted from the index and nothing else.

`brain.adoption.coverage_report` wants a number of records per department and source, and the
only place that number exists is `proj.record`, where a source whose visibility rule names a
department stores that department in the row's own `fields` (see
`brain.ops.connector_sync.stored_fields`). This is the one statement that reads it, and it decides
nothing: which departments a reader may be told about is decided before the statement runs, by
the caller, and the statement is bounded to them.

**The departments are a parameter and the statement never groups across the rest.** A count
grouped over every department and filtered afterwards would be computed by the database for
departments the reader may not see, which is harmless to the reader and a trap for the next
caller who forgets the filter. Handing the reachable set in as the `WHERE` clause means the
statement cannot produce a row about a department it was not asked about, so the guarantee does
not rest on a later loop remembering to drop one.

**Counts, never values.** The statement selects the source, the entity and the department, and
`count(*)`. It reads no field a record holds beyond the department it filters on, and a connector
keeps only a small index in any case (`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`),
so this is a count of ids the install keeps, not a count of everything the source holds.

**Retired rows are not counted.** The application role's policy on `proj.record` hides a row a
sync retired, and the statement says so as well (`deleted_at IS NULL`), so the figure is the same
under the owner's login as under the application's.

Task ids: M34.1.2.1
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from types import MappingProxyType
from typing import Final

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

#: The field a source's visibility rule stores its department in. Read from the one place that
#: names it so a change of the field's name is a change in one module.
DEPARTMENT_KEY: Final = "department"

#: The statement. A text statement because the grouping key is a JSON field of the row, and
#: written out in full so a reader can see that nothing but a count leaves it.
COUNTS_SQL: Final = text(
    "SELECT source, entity, fields->>'department' AS department, count(*) AS records "
    "FROM proj.record "
    "WHERE deleted_at IS NULL AND fields->>'department' IN :departments "
    "GROUP BY source, entity, fields->>'department'"
).bindparams(bindparam("departments", expanding=True))

#: The empty answer, shared so a caller with no reachable department allocates nothing.
NOTHING_COUNTED: Final[Mapping[tuple[str, str, str], int]] = MappingProxyType({})


async def record_counts(
    session: AsyncSession, departments: Collection[str]
) -> Mapping[tuple[str, str, str], int]:
    """Live records per `(source, department, entity)`, for these departments and no others.

    An empty set of departments is answered without a statement: `IN ()` is a syntax error in
    some dialects and a wasted round trip in all of them, and there is nothing to count.
    """
    wanted = sorted(set(departments))
    if not wanted:
        return NOTHING_COUNTED
    found = await session.execute(COUNTS_SQL, {"departments": wanted})
    return MappingProxyType(
        {(str(row.source), str(row.department), str(row.entity)): int(row.records) for row in found}
    )
