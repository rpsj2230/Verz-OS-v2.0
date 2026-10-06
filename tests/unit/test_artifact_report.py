"""A report an agent produces, held to the rule that it never holds more than its run may read.

Real `EntitlementSet`s, a real `FieldPolicy`, a real `AgentRecord` and the real `run_reach`, so a
row or a column reaching the file is the redactor's decision at `E_run(caller, agent)` and nothing
written here. The CSV is parsed back rather than searched, so a value appearing in a heading or a
neighbouring cell cannot satisfy an assertion about the cell it should be in.

Task ids: M39.5.1.1, M39.5.1.4
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.console.agent_output import ArtifactError
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification, policy_from_rows
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.ops.artifact_report import (
    A_FIELD_IS_DATA_AND_A_SPREADSHEET_WOULD_RUN_IT,
    FORMULA_LEADS,
    NOTHING_THIS_RUN_MAY_READ_IS_A_REPORT,
    Records,
    cell,
    rendered,
)

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
ENTITY = "price"
SALES, SUPPORT = "sales", "support"
READ = f"read:{ENTITY}"
COST = f"read:{ENTITY}.cost"
DEPARTMENT = f"read:{ENTITY}.department"

POLICY = policy_from_rows(
    [
        (ENTITY, "name", READ, Classification.INTERNAL),
        (ENTITY, "sell_price", READ, Classification.INTERNAL),
        (ENTITY, "cost", COST, Classification.RESTRICTED),
        (ENTITY, "department", DEPARTMENT, Classification.INTERNAL),
    ]
)

ROWS = (
    {"name": "design", "department": SALES, "sell_price": "900", "cost": "400", "note": "x"},
    {"name": "build", "department": SALES, "sell_price": "1200", "cost": "700", "note": "y"},
    {"name": "audit", "department": SUPPORT, "sell_price": "300", "cost": "100", "note": "z"},
)

RECORDS = Records(
    entity=ENTITY,
    rows=ROWS,
    policy=POLICY,
    read_as=Capability(value=READ),
    source="price_list",
)


def agent(*capabilities: str, scope: Scope | None = None) -> AgentRecord:
    return AgentRecord(
        agent_id="quoting",
        display_name="Quoting",
        persona="Quotes from the price list.",
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id="p_steward", department=SALES),
        authority=AgentAuthority(
            scope=Scope.department(SALES) if scope is None else scope,
            capabilities=tuple(Capability(value=one) for one in capabilities),
        ),
        created_by="p_steward",
    )


def person(*capabilities: str) -> EntitlementSet:
    """A caller holding these capabilities company-wide."""
    return EntitlementSet(
        principal_id="p_asker",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


def table(body: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body.decode("utf-8"))))


QUOTING = agent(READ, COST, DEPARTMENT)


def test_a_report_holds_the_rows_and_fields_the_run_may_read_and_nothing_else() -> None:
    """**M39.5.1.4.** A caller holding the price list and not its cost is given a report with the
    names and sell prices of the agent's department's rows, no cost column and no other
    department's row, and a caller holding the cost too is given the cost. An unclassified field
    is never in the file for either.

    Delete this and the report is the rows as read, which is every column the connector returned
    to a person the record screen would have shown a lock."""
    without = table(rendered(RECORDS, caller=person(READ), agent=QUOTING, now=NOW).body)
    withheld = table(rendered(RECORDS, caller=person(READ, COST), agent=QUOTING, now=NOW).body)

    assert without == [["name", "sell_price"], ["design", "900"], ["build", "1200"]]
    assert withheld == [
        ["name", "sell_price", "cost"],
        ["design", "900", "400"],
        ["build", "1200", "700"],
    ]


def test_the_agents_ceiling_narrows_a_caller_who_holds_more() -> None:
    """The lens half of the rule: a caller holding the cost company-wide, through an agent whose
    ceiling does not name it, is given no cost. Delete this and the report is built at the
    caller's own reach, and an agent stops being a lens the moment it writes a file."""
    narrow = agent(READ, DEPARTMENT)

    got = table(rendered(RECORDS, caller=person(READ, COST), agent=narrow, now=NOW).body)

    assert got[0] == ["name", "sell_price"]


def test_the_grants_a_report_drew_on_are_the_rows_grant_and_each_columns_as_the_run_held_them() -> (
    None
):
    """What a re-download is later checked against. The row grant and the cost grant, each at the
    run's scope (the agent's department), and nothing for a column that did not reach the file.
    Delete this and a report records no grants, so its re-download asks nothing of the content."""
    made = rendered(RECORDS, caller=person(READ, COST), agent=QUOTING, now=NOW)
    without = rendered(RECORDS, caller=person(READ), agent=QUOTING, now=NOW)

    assert {(one.capability.value, one.scope) for one in made.drew_on} == {
        (READ, Scope.department(SALES)),
        (COST, Scope.department(SALES)),
    }
    assert {one.capability.value for one in without.drew_on} == {READ}


def test_a_cell_a_spreadsheet_would_run_is_written_as_text() -> None:
    """Delete this and a record's field reading `=HYPERLINK(...)` is a formula in the file somebody
    opens, run with their spreadsheet's rights."""
    assert [cell(f"{lead}1+1") for lead in FORMULA_LEADS] == [
        f"'{lead}1+1" for lead in FORMULA_LEADS
    ]
    assert (cell("plain"), cell(12), cell(None), cell(-5)) == ("plain", "12", "", "-5")
    rows = ({"name": "=SUM(A1)", "department": SALES, "sell_price": "1"},)
    got = table(
        rendered(
            Records(ENTITY, rows, POLICY, Capability(value=READ), "price_list"),
            caller=person(READ),
            agent=QUOTING,
            now=NOW,
        ).body
    )
    assert got[1][0] == "'=SUM(A1)"
    assert "apostrophe" in A_FIELD_IS_DATA_AND_A_SPREADSHEET_WOULD_RUN_IT


def test_a_report_of_nothing_the_run_may_read_is_refused_rather_than_written_empty() -> None:
    """Nobody holding the row grant, and rows none of which are in the agent's department, are
    both refused. Delete this and an empty file with a heading reads as a report that found no
    prices."""
    elsewhere = tuple(row for row in ROWS if row["department"] == SUPPORT)

    with pytest.raises(ArtifactError, match="no report"):
        rendered(RECORDS, caller=person(), agent=QUOTING, now=NOW)
    with pytest.raises(ArtifactError, match="no report"):
        rendered(
            Records(ENTITY, elsewhere, POLICY, Capability(value=READ), "price_list"),
            caller=person(READ),
            agent=QUOTING,
            now=NOW,
        )
    assert NOTHING_THIS_RUN_MAY_READ_IS_A_REPORT.startswith("No row or no field")
