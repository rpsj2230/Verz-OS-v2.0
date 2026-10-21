"""The switch on the per-department coverage statement and the champion's shopping list.

Off because a coverage statement is new information about a department: how many records a
connected source holds for it and when it was last read, which no screen said before. It is read
behind the grant the Adoption figures are read behind, so no reader is told about a department they
could not already see adoption for, but an install should choose the day its departments start
being shown their own coverage. `brain.adoption_coverage_routes` asks the switch before it answers
and a switch turned off removes a read, so nothing a person did is trapped by it.

Task ids: M34.1.2.1, M34.1.2.2, M34.1.2.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

ADOPTION_COVERAGE: Final = Feature(
    name="adoption_coverage",
    title="Show each department what is connected for it, and what to connect next",
    what=(
        "The Adoption page gains a coverage statement per department: for each source connected "
        "for the department, how many records it holds and when it was last read, or an explicit "
        "note that nothing is connected for it. A shopping list beside it names the next things a "
        "champion could do, ordered by what people asked and could not be answered. It is shown "
        "only for the departments the reader may already read usage for, and carries no total, "
        "no percentage and no count of departments the reader is not shown."
    ),
    while_off=(
        "The Adoption page shows its usage figures as before and no coverage statement or "
        "shopping list. Nothing recorded is lost: the statement is read from the connections and "
        "records the install already holds."
    ),
    read_by=("brain.adoption_coverage_routes:coverage_is_on",),
)
