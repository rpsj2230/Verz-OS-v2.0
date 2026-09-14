"""The administration and staff guides, held to the permission model, the starter questions and
the screen registry.

Three pages under `docs/` state something a machine can check, and this is the check. Delete this
file and each of them goes on reading as correct while the product moves underneath it: the
cookbook goes on saying who a grant lets in after the intersection changes, the asking guide goes
on showing a department questions about records it no longer has, and a runbook goes on quoting a
capability the screen stopped needing.

**The cookbook is executed, not compared.** Every outcome row on the page is resolved and asked
of the product by `brain.ops.guide_docs.cookbook_gaps`, so the test of the real page is a test of
the permission model on five worked cases as well as a test of the page. Each refusal the check
can make is also produced here from a page built to fail, with a sibling proving the real page
does not, which is `tests/unit/test_install_docs.py`' discipline carried over.

Task ids: M34.3.2.2, M34.3.1.3, M34.3.2.1
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from brain.adoption import ScopeCoverage
from brain.console.screens import SCREEN_COUNT, SCREENS, screen
from brain.core.entitlement import Capability
from brain.core.scope import Clause, Op, Scope
from brain.demo import (
    DEMO_SOURCE,
    DEPARTMENTS,
    SEEDED_AT,
    build_people,
    build_records,
    row_classifications,
)
from brain.launch import screen_runbook_gaps
from brain.ops.guide_docs import (
    AN_EXAMPLE_WITH_NO_REFUSAL_IS_SATISFIED_BY_A_SYSTEM_THAT_GRANTS_EVERYTHING as BOTH,
)
from brain.ops.guide_docs import (
    COOKBOOK_EXAMPLES,
    GRANTS_MARKER,
    NO_EXAMPLES_YET,
    NOWHERE_TO_CHECK,
    OUTCOMES_MARKER,
    RUNBOOK_SECTIONS,
    GuideDocsError,
    asking_examples,
    asking_gaps,
    cookbook_gaps,
    examples_marker,
    indexed_coverage,
    instant_of,
    runbook_facts,
    runbook_gaps,
    scope_of,
)
from brain.tools.startup import build_registry

REPO = Path(__file__).resolve().parents[2]
GUIDES = REPO / "docs" / "guides"
RUNBOOKS = REPO / "docs" / "console" / "runbooks"
CHECKABLE = frozenset({DEMO_SOURCE})
ON = "2999-01-01"


# ------------------------------------------------------------------------------ the registers
def cookbook(page: str) -> tuple[str, ...]:
    """The cookbook check over the demo, which is what the real page is written against."""
    return cookbook_gaps(
        page,
        people=build_people(),
        records=build_records(),
        classifications=row_classifications(),
    )


def coverage() -> tuple[ScopeCoverage, ...]:
    """The demo's indexed coverage, one row per department, from the records the demo writes."""
    return indexed_coverage(
        [(one.department, one.entity) for one in build_records()],
        departments=DEPARTMENTS,
        source=DEMO_SOURCE,
        synced_at=SEEDED_AT,
    )


def registered() -> frozenset[str]:
    """The tool names the application registers, from the builder the application calls."""
    return frozenset(build_registry(source=DEMO_SOURCE).names())


def runbooks() -> dict[str, str]:
    return {one.stem: one.read_text(encoding="utf-8") for one in RUNBOOKS.glob("*.md")}


def guide(name: str) -> str:
    return (GUIDES / name).read_text(encoding="utf-8")


def bodies(page: str) -> dict[str, str]:
    """Every level-two heading of a page and the text under it."""
    return dict(re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", page, re.M | re.S))


def row(*cells: str) -> str:
    """One markdown table row."""
    return "| " + " | ".join(cells) + " |\n"


def example(heading: str, grants: str, outcomes: str) -> str:
    """One cookbook example in the page's own shape, for a page built to fail."""
    return (
        f"## {heading}\n\n{GRANTS_MARKER}\n\n"
        + row("Holder", "Capability", "Scope", "Until")
        + row("---", "---", "---", "---")
        + f"{grants}\n{OUTCOMES_MARKER}\n\n"
        + row("Who", "Through", "Reads", "Record", "On", "Outcome")
        + row("---", "---", "---", "---", "---", "---")
        + f"{outcomes}\n"
    )


#: A correct example over an invented holder, so each refusal below is one edit away from it.
REVIEWER_GRANTS = row("reviewer", "read:client", "department = operations", "no end") + row(
    "reviewer", "read:client.name", "department = operations", "no end"
)
REVIEWER_OUTCOMES = row(
    "reviewer", "directly", "read:client.name", "demo_client_ashgrove", ON, "reaches"
) + row("reviewer", "directly", "read:client.name", "demo_client_brightpier", ON, "refused")


def whole_cookbook(extra: str = "") -> str:
    """Every required example as the correct reviewer example, plus whatever is being tested."""
    return (
        "".join(example(name, REVIEWER_GRANTS, REVIEWER_OUTCOMES) for name in COOKBOOK_EXAMPLES)
        + extra
    )


# ==================================================================== cookbook_gaps (M34.3.2.2)
def test_every_example_in_the_cookbook_is_what_the_product_answers() -> None:
    """**M34.3.2.2.** Each grant on the page is resolved by the product's resolver and each
    outcome asked of its row plane, over the demo's records and columns.

    Delete this and the cookbook an administrator writes access from can state an answer the
    permission model stopped giving, which is the drift the page exists to be safe from."""
    assert cookbook(guide("grants-and-scopes.md")) == ()


def test_the_cookbook_carries_every_example_the_leaf_asks_for_and_each_is_executed() -> None:
    """The five headings are present on the real page and each carries both tables, so none of
    them is prose the check walks past. Each is also held to the rule its heading names.

    Delete this and an example can lose its marker and become a paragraph nothing runs, while
    the page still reads as having five worked examples."""
    found = bodies(guide("grants-and-scopes.md"))

    for name in COOKBOOK_EXAMPLES:
        assert GRANTS_MARKER in found[name]
        assert OUTCOMES_MARKER in found[name]
    assert "`agent " in found["A wildcard narrowed by an agent's ceiling"]
    assert ".*`" in found["A wildcard narrowed by an agent's ceiling"]
    assert re.search(r"\| 2999-\d\d-\d\d \|\n", found["A grant that expires"])
    assert "`demo_projects_coord`" in found["Sees the client, never what it is worth"]


def test_a_correct_example_raises_nothing() -> None:
    """The positive sibling. Delete this and a check refusing every example passes every
    refusal test below."""
    assert cookbook(whole_cookbook()) == ()


def test_an_outcome_the_product_does_not_give_is_a_finding() -> None:
    """The finding the check exists for. The reviewer reaches an Operations client's name and
    the page is edited to say refused.

    Delete this and `cookbook_gaps` can stop comparing the answer with the page and still pass
    the real page, because the real page is right."""
    wrong = REVIEWER_OUTCOMES.replace(f"{ON} | reaches", f"{ON} | refused", 1)

    found = cookbook(whole_cookbook(example("Edited", REVIEWER_GRANTS, wrong)))

    assert found == (
        f"'Edited': the example does not state both somebody reaching and somebody refused. {BOTH}",
        "'Edited': reviewer directly reading read:client.name on demo_client_ashgrove at "
        "2999-01-01: the page says 'refused' and the product says 'reaches'",
    )


def test_a_missing_example_is_a_finding() -> None:
    """Delete this and the cookbook can lose the expiring-grant example and still pass."""
    page = "".join(
        example(name, REVIEWER_GRANTS, REVIEWER_OUTCOMES) for name in COOKBOOK_EXAMPLES[1:]
    )

    assert cookbook(page) == (f"{COOKBOOK_EXAMPLES[0]!r}: the cookbook has no example of it",)


def test_an_example_stating_only_who_is_refused_is_a_finding() -> None:
    """Delete this and an example can describe a grant by its refusals alone, which is true of a
    system that refuses everybody."""
    only = REVIEWER_OUTCOMES.splitlines(keepends=True)[1]

    found = cookbook(whole_cookbook(example("Only half", REVIEWER_GRANTS, only)))

    assert len(found) == 1
    assert found[0].startswith("'Only half': the example does not state both somebody reaching")


def test_a_read_nobody_can_use_is_a_finding_and_a_platform_verb_is_not() -> None:
    """A read has to name a row or a column the demo holds; `invoke:agent` is about the platform
    and is not held to that. Delete this and the page can teach a capability no record requires,
    or the check can start refusing every demo person, all of whom hold `invoke:agent`."""
    grants = (
        REVIEWER_GRANTS
        + row("reviewer", "read:contract.value", "department = operations", "no end")
        + row("reviewer", "invoke:agent", "department = operations", "no end")
    )

    found = cookbook(whole_cookbook(example("Vocabulary", grants, REVIEWER_OUTCOMES)))

    assert found == (
        "'Vocabulary': read:contract.value covers nothing the demo's records require, so it is a "
        "capability nobody can use",
    )


def test_a_demo_person_given_other_grants_than_the_demos_is_a_finding() -> None:
    """The coordinator is given the contract value she does not hold in the demo.

    Delete this and the see-the-record-not-the-money example can be about somebody wearing her
    name, and whoever tries it in the demo gets a different answer."""
    coordinator = next(one for one in build_people() if one.principal.id == "demo_projects_coord")
    as_demo = "".join(
        row("demo_projects_coord", one.capability.value, "department = projects", "no end")
        for one in coordinator.grants
    )
    widened = as_demo + row(
        "demo_projects_coord", "read:client.contract_value", "department = projects", "no end"
    )
    outcomes = row(
        "demo_projects_coord", "directly", "read:client", "demo_client_brightpier", ON, "reaches"
    ) + row("demo_projects_coord", "directly", "read:client", "demo_client_ashgrove", ON, "refused")

    assert cookbook(whole_cookbook(example("As the demo", as_demo, outcomes))) == ()
    found = cookbook(whole_cookbook(example("Widened", widened, outcomes)))
    assert len(found) == 1
    assert found[0].startswith("'Widened': demo_projects_coord is a demo person")


def test_an_expiring_grant_is_asked_at_the_instant_the_row_names() -> None:
    """The day before the end reaches and the day of the end is refused. This tests that the
    check passes the row's instant through to the resolver as much as it tests the page.

    Delete this and a check asking at the wall clock passes every example dated 2999, because
    every such grant is live today."""
    grants = row("surveyor", "read:job", "department = operations", "2999-06-30") + row(
        "surveyor", "read:job.summary", "department = operations", "2999-06-30"
    )
    right = row(
        "surveyor", "directly", "read:job.summary", "demo_job_2411", "2999-06-29", "reaches"
    ) + row("surveyor", "directly", "read:job.summary", "demo_job_2411", "2999-06-30", "refused")
    wrong = right.replace("2999-06-30 | refused", "2999-06-30 | reaches")

    assert cookbook(whole_cookbook(example("Expiry", grants, right))) == ()
    assert cookbook(whole_cookbook(example("Expiry", grants, wrong))) == (
        f"'Expiry': the example does not state both somebody reaching and somebody refused. {BOTH}",
        "'Expiry': surveyor directly reading read:job.summary on demo_job_2411 at 2999-06-30: "
        "the page says 'reaches' and the product says 'refused'",
    )


def test_an_agent_is_asked_through_its_ceiling_and_a_wildcard_is_narrowed_not_dropped() -> None:
    """The lead's wildcard reaches the contract value directly and the name through a ceiling
    naming only the name, and is refused the contract value through it.

    Delete this and the check can ignore the route column, answer every agent row as though it
    were asked directly, and still pass a page whose agent rows happen to agree."""
    grants = (
        row("lead", "read:client.*", "department = projects", "no end")
        + row("lead", "read:client", "department = projects", "no end")
        + row("agent names", "read:client.name", "department = projects", "no end")
    )
    client = "demo_client_brightpier"
    outcomes = (
        row("lead", "directly", "read:client.contract_value", client, ON, "reaches")
        + row("lead", "agent names", "read:client.name", client, ON, "reaches")
        + row("lead", "agent names", "read:client.contract_value", client, ON, "refused")
    )
    as_direct = outcomes.replace(f"{ON} | refused", f"{ON} | reaches")

    assert cookbook(whole_cookbook(example("Lens", grants, outcomes))) == ()
    found = cookbook(whole_cookbook(example("Lens", grants, as_direct)))
    assert found[-1] == (
        "'Lens': lead through agent names reading read:client.contract_value on "
        "demo_client_brightpier at 2999-01-01: the page says 'reaches' and the product says "
        "'refused'"
    )


def test_a_column_grant_with_no_row_grant_reaches_neither() -> None:
    """The two-grant model as the check asks it. Delete this and a check that treats a column
    read as reaching its row passes a page claiming the opposite of what the row plane does."""
    grants = REVIEWER_GRANTS + row(
        "column_only", "read:client.contract_value", "department = operations", "no end"
    )
    ashgrove = "demo_client_ashgrove"
    outcomes = row(
        "column_only", "directly", "read:client.contract_value", ashgrove, ON, "refused"
    ) + row("reviewer", "directly", "read:client.name", ashgrove, ON, "reaches")
    claimed = outcomes.replace(f"{ON} | refused", f"{ON} | reaches")

    assert cookbook(whole_cookbook(example("Two grants", grants, outcomes))) == ()
    assert cookbook(whole_cookbook(example("Two grants", grants, claimed)))[-1] == (
        "'Two grants': column_only directly reading read:client.contract_value on "
        "demo_client_ashgrove at 2999-01-01: the page says 'reaches' and the product says "
        "'refused'"
    )


def test_an_outcome_that_cannot_be_asked_says_why_rather_than_passing() -> None:
    """A record the demo does not write, a route through an agent with no ceiling, a read on the
    wrong entity, a column nothing classifies, an outcome that is neither word, and rows too
    short to read.

    Delete this and any of those rows is silently skipped, and an example made of them reads as
    checked."""
    ashgrove = "demo_client_ashgrove"
    outcomes = (
        row("reviewer", "directly", "read:client.name", ashgrove, ON, "reaches")
        + row("reviewer", "directly", "read:client.name", "demo_client_nowhere", ON, "refused")
        + row("reviewer", "agent ghost", "read:client.name", ashgrove, ON, "reaches")
        + row("reviewer", "directly", "read:invoice.status", ashgrove, ON, "refused")
        + row("reviewer", "directly", "read:client.shoe_size", ashgrove, ON, "refused")
        + row("reviewer", "directly", "read:client.name", ashgrove, ON, "maybe")
        + row("reviewer", "directly", "read:client.name")
    )
    grants = REVIEWER_GRANTS + row("reviewer", "read:client")

    found = cookbook(whole_cookbook(example("Unaskable", grants, outcomes)))

    assert found == (
        "'Unaskable': a grant row with 2 cell(s) reads ('reviewer', 'read:client'); every row "
        "states the holder, the capability, the scope and when it ends",
        "'Unaskable': an outcome row with 3 cell(s) reads ('reviewer', 'directly', "
        "'read:client.name'); every row states who, through what, reading what, on which "
        "record, when, and the outcome",
        "'Unaskable': reviewer: demo_client_nowhere is not a record the demo writes",
        "'Unaskable': reviewer: 'agent ghost' holds no grant in this example, so it is not a "
        "ceiling",
        "'Unaskable': reviewer: reads read:invoice.status on demo_client_ashgrove, which is a "
        "client",
        "'Unaskable': reviewer: read:client.shoe_size is not a row or a column the demo classifies",
        "'Unaskable': reviewer: the outcome reads 'maybe', which is neither 'reaches' nor "
        "'refused'",
    )


def test_a_cell_that_cannot_be_read_is_a_finding_and_not_an_exception() -> None:
    """A capability outside the grammar, a scope with a disjunction in it and a date nobody can
    parse. Delete this and one bad cell raises out of the whole check, and every other example on
    the page goes unasked on the day somebody mistypes one."""
    grants = REVIEWER_GRANTS + row("reviewer", "delete:client", "department = operations", "no end")
    grants += row("reviewer", "read:job", "department = a or department = b", "no end")
    outcomes = REVIEWER_OUTCOMES + row(
        "reviewer", "directly", "read:client.name", "demo_client_ashgrove", "soon", "reaches"
    )

    found = cookbook(whole_cookbook(example("Unreadable", grants, outcomes)))

    assert len(found) == 3
    assert found[0].startswith("'Unreadable': the grant row ('reviewer', 'delete:client'")
    assert "unknown verb 'delete'" in found[0]
    assert found[1].startswith("'Unreadable': the grant row ('reviewer', 'read:job'")
    assert "is not a clause" in found[1]
    assert found[2].startswith("'Unreadable': the outcome row")
    assert "YYYY-MM-DD" in found[2]


def test_an_agent_ceiling_with_two_scopes_or_an_expiry_is_refused_as_unaskable() -> None:
    """An agent's authority has one scope and no end, which is how `entitlement_ceiling` builds
    it. Delete this and the page can describe a ceiling no agent can hold and have it evaluated as
    though one could."""
    two = (
        REVIEWER_GRANTS
        + row("agent wide", "read:client.name", "department = operations", "no end")
        + row("agent wide", "read:client.status", "department = projects", "no end")
    )
    ending = REVIEWER_GRANTS + row(
        "agent wide", "read:client.name", "department = operations", "2999-06-30"
    )
    outcomes = REVIEWER_OUTCOMES + row(
        "reviewer", "agent wide", "read:client.name", "demo_client_ashgrove", ON, "reaches"
    )

    assert cookbook(whole_cookbook(example("Scopes", two, outcomes))) == (
        "'Scopes': reviewer: agent wide declares 2 scopes, and an agent's authority has one",
    )
    assert cookbook(whole_cookbook(example("Ending", ending, outcomes))) == (
        "'Ending': reviewer: agent wide carries an expiry, and an agent ceiling has none",
    )


def test_a_scope_cell_reads_as_the_scope_it_names_and_refuses_what_a_scope_cannot_hold() -> None:
    """Each spelling to the `Scope` it means, and a disjunction refused. Delete this and
    `department in a, b` can be read as one department called "a, b", which matches nothing and
    turns every refusal on the page true for the wrong reason."""
    assert scope_of("`everywhere`") == Scope.unrestricted()
    assert scope_of("`department = projects and reference starts with INV`") == Scope(
        clauses=(
            Clause(field="department", op=Op.EQ, value="projects"),
            Clause(field="reference", op=Op.PREFIX, value="INV"),
        )
    )
    assert scope_of("department in projects, accounts") == Scope(
        clauses=(Clause(field="department", op=Op.IN, value=("projects", "accounts")),)
    )
    with pytest.raises(GuideDocsError, match="is not a clause"):
        scope_of("department = projects or department = accounts")
    with pytest.raises(GuideDocsError, match="YYYY-MM-DD"):
        instant_of("30 June 2999")


def test_every_capability_the_cookbook_teaches_is_one_the_demo_classifies() -> None:
    """The vocabulary is taken from the code rather than from the page. The money column the
    persona example withholds is a column the demo really classifies, so the example is about a
    real column. Delete this and the persona example can withhold a column nothing has."""
    classified = {rule.required_capability for one in row_classifications() for rule in one.rules}
    taught = set(re.findall(r"`(read:[a-z_]+(?:\.[a-z_]+)?)`", guide("grants-and-scopes.md")))

    assert Capability(value="read:client.contract_value") in classified
    assert taught
    assert {Capability(value=one) for one in taught if "." in one} <= classified


# ======================================================================= asking_gaps (M34.3.1.3)
def test_the_asking_guide_shows_each_department_the_questions_its_own_records_produce() -> None:
    """**M34.3.1.3.** Every department's table, exactly and in order, against the derivation.

    Delete this and the page's worked examples can be edited into questions no department's
    records answer, which is the first-day failure the page is written to prevent."""
    page = guide("asking-well.md")

    assert asking_gaps(page, rows=coverage(), departments=DEPARTMENTS, checkable=CHECKABLE) == ()


def test_each_department_is_shown_only_questions_about_its_own_records() -> None:
    """Accounts indexed invoices and a client; Operations a client and a job; People nothing.
    Each is shown questions only about its own entities, and People is shown none rather than
    somebody else's.

    Delete this and `asking_examples` can read every department's rows, and the page would still
    pass while two departments happened to hold the same entities."""
    rows = coverage()
    entities = {"client", "job", "invoice"}
    indexed = {
        department: {one.entity for one in build_records() if one.department == department}
        for department in DEPARTMENTS
    }

    for department in DEPARTMENTS:
        shown = asking_examples(rows, department, checkable=CHECKABLE)
        assert all(one.department == department for one in shown)
        about = {word for one in shown for word in re.findall(r"[a-z]+", one.question)}
        assert about & entities <= indexed[department]
    assert asking_examples(rows, "people", checkable=CHECKABLE) == ()
    assert {
        word
        for one in asking_examples(rows, "accounts", checkable=CHECKABLE)
        for word in re.findall(r"[a-z]+", one.question)
    } & entities == {"invoice", "client"}


def test_a_source_nobody_can_open_contributes_no_example() -> None:
    """Delete this and a department can be shown a question it has nowhere to check, which is
    the starter questions' own refusal lost one layer up."""
    assert asking_examples(coverage(), "accounts", checkable=frozenset()) == ()


def test_indexed_coverage_counts_each_department_on_its_own_and_most_populated_first() -> None:
    """Delete this and the order the questions come in stops being the order of what indexed, and
    a department's count can include another department's records."""
    rows = {one.department: one for one in coverage()}

    assert rows["accounts"].entities == (("invoice", 2), ("client", 1))
    assert rows["accounts"].records == 3
    assert rows["operations"].entities == (("client", 1), ("job", 1))
    assert rows["people"].entities == ()
    assert rows["people"].records == 0


def test_a_missing_table_an_extra_table_and_a_wrong_question_are_all_findings() -> None:
    """All three directions. Delete this and a department's table can be removed, invented or
    edited, with the real page still passing."""
    rows = coverage()

    def table(department: str, cells: str) -> str:
        header = row("Ask", "Check it in") + row("---", "---")
        return f"{examples_marker(department)}\n\n{header}{cells}\n"

    good = {
        department: "".join(
            row(one.question, f"`{one.check_in}`")
            for one in asking_examples(rows, department, checkable=CHECKABLE)
        )
        or row(NO_EXAMPLES_YET, NOWHERE_TO_CHECK)
        for department in DEPARTMENTS
    }
    whole = "".join(table(department, good[department]) for department in DEPARTMENTS)
    broken = (
        table("operations", good["operations"].replace("job", "invoice"))
        + table("projects", good["projects"])
        + table("accounts", good["accounts"])
        + table("warehouse", good["accounts"])
    )

    assert asking_gaps(whole, rows=rows, departments=DEPARTMENTS, checkable=CHECKABLE) == ()
    found = asking_gaps(broken, rows=rows, departments=DEPARTMENTS, checkable=CHECKABLE)
    assert found[0] == (
        "warehouse: a table of examples for a department that is not there, which reads as coverage"
    )
    assert found[1].startswith("operations: the page shows [('How many client are there?'")
    assert "Which invoice is the most recent?" in found[1]
    assert found[2] == "people: no examples, so its staff are shown somebody else's"
    assert len(found) == 3


def test_an_example_row_too_short_to_read_is_a_finding_and_not_skipped() -> None:
    """Delete this and a row that lost its second cell is dropped before the comparison, so the
    table is reported as wrong for a reason nobody can see in it."""
    rows = coverage()
    header = row("Ask", "Check it in") + row("---", "---")
    page = (
        f"{examples_marker('people')}\n\n{header}"
        f"{row(NO_EXAMPLES_YET, NOWHERE_TO_CHECK)}{row('stray')}\n"
    )

    assert asking_gaps(page, rows=rows, departments=("people",), checkable=CHECKABLE) == (
        "people: a row with 1 cell(s) reads ('stray',); every row states the question and where "
        "to check it",
    )


def test_a_department_with_nothing_indexed_is_shown_saying_so_and_not_left_blank() -> None:
    """Delete this and the People table can be emptied of its one row and a department with
    nothing indexed reads as a department nobody wrote examples for."""
    rows = coverage()
    lent = (
        f"{examples_marker('people')}\n\n{row('Ask', 'Check it in')}{row('---', '---')}"
        f"{row('How many client are there?', 'demo')}\n"
    )

    assert asking_gaps(lent, rows=rows, departments=("people",), checkable=CHECKABLE) == (
        "people: the page shows [('How many client are there?', 'demo')] and the department's "
        f"own records produce [({NO_EXAMPLES_YET!r}, {NOWHERE_TO_CHECK!r})]",
    )


# ====================================================================== runbook_gaps (M34.3.2.1)
def test_every_console_screen_has_a_runbook_and_every_runbook_agrees_with_the_registry() -> None:
    """**M34.3.2.1.** One runbook per screen, both directions, and every fact each one quotes
    held to the registry and to the tools the application registers.

    Delete this and a runbook can go on quoting a capability or a department answer the screen
    stopped having, or go on saying a screen cannot be opened on the day it can."""
    books = runbooks()

    assert len(books) == SCREEN_COUNT
    assert screen_runbook_gaps(books) == ()
    assert runbook_gaps(books, registered_tools=registered()) == ()


def test_a_runbook_says_whether_its_screen_can_be_opened_and_goes_red_when_that_changes() -> None:
    """Today no console tool is registered, so every runbook says no. Registering one makes
    that runbook's row a finding, which is the day its prose needs re-reading.

    Delete this and the one fact that tells a reader not to go looking for the page can be wrong
    in either direction without anything noticing."""
    halt = screen("halt")

    assert dict(runbook_facts(halt, registered_tools=registered()))["Can be opened today"] == "no"
    assert runbook_gaps(runbooks(), registered_tools=registered() | {halt.read.tool}) == (
        "halt: Can be opened today: the runbook says 'no' and the registry says 'yes'",
    )


def test_a_wrong_fact_a_missing_fact_an_invented_fact_and_a_wrong_title_are_findings() -> None:
    """Delete this and the facts table can drift, lose a row or gain one the registry does not
    declare, and the runbook still passes."""
    books = runbooks()
    books["people"] = (
        books["people"]
        .replace("| Needs | `read:grant` |", "| Needs | `read:client` |")
        .replace("| Console plane | `read:console.configuration` |\n", "")
        .replace("| Key | `people` |", "| Key | `people` |\n| Colour | `blue` |")
        .replace("# People and grants", "# People")
    )

    assert runbook_gaps(books, registered_tools=registered()) == (
        "people: the runbook opens '# People' and the screen is called 'People and grants'",
        "people: Console plane: the runbook does not state it",
        "people: Colour: a fact the registry does not declare, which reads as one it does",
        "people: Needs: the runbook says 'read:client' and the registry says 'read:grant'",
    )


def test_the_department_admin_fact_is_read_off_the_withheld_list() -> None:
    """Rate limits is the one screen a department admin is not offered. Delete this and the
    runbook fact can be computed from something else and agree with the registry by accident on
    every screen but that one."""
    offered = {
        one.key: dict(runbook_facts(one, registered_tools=()))["Offered to a department admin"]
        for one in SCREENS
    }

    assert offered.pop("limits") == "no"
    assert set(offered.values()) == {"yes"}


def test_a_runbook_missing_a_section_or_with_an_empty_one_is_a_finding() -> None:
    """Delete this and a runbook can drop what to do about an alarm, which is the section somebody
    opens it for."""
    books = runbooks()
    books["recovery"] = books["recovery"][: books["recovery"].index("## When it shows an alarm")]
    books["limits"] = re.sub(
        r"(## When it is empty or refuses\n)(.*?)(?=## )", r"\1\n", books["limits"], flags=re.S
    )

    assert runbook_gaps(books, registered_tools=registered()) == (
        f"recovery: the sections read {list(RUNBOOK_SECTIONS[:3])} and every runbook has "
        f"{list(RUNBOOK_SECTIONS)}",
        "limits: 'When it is empty or refuses': a section with nothing under it",
    )


def test_a_missing_runbook_and_one_for_no_screen_are_reported_through_the_launch_check() -> None:
    """`runbook_gaps` builds on `brain.launch.screen_runbook_gaps` rather than repeating it.
    Delete this and the two could disagree about which screens need a runbook."""
    books = runbooks()
    del books["quality"]
    books["renamed"] = "# Renamed\n"

    found = runbook_gaps(books, registered_tools=registered())

    assert found == screen_runbook_gaps(books)
    assert len(found) == 2


def test_a_fact_row_too_short_to_read_is_a_finding() -> None:
    """Delete this and a row that lost its value cell is skipped and its fact reported only as
    missing, which sends somebody to add a row that is already there."""
    books = runbooks()
    books["usage"] = books["usage"].replace("| Tool | `console.usage` |", "| Tool |")

    assert runbook_gaps(books, registered_tools=registered()) == (
        "usage: a fact row with 1 cell(s) reads ('Tool',)",
        "usage: Tool: the runbook does not state it",
    )


def test_every_constant_or_member_a_guide_quotes_exists_in_the_source() -> None:
    """The runbooks were written from reading each screen's module, and every name they quote in
    code is one a reader will search for. Delete this and a renamed constant, or one misremembered
    while writing, leaves a runbook sending somebody to look for something that is not there."""
    source = "\n".join(
        one.read_text(encoding="utf-8") for one in (REPO / "src" / "brain").rglob("*.py")
    )
    known = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", source))
    pages = [*RUNBOOKS.glob("*.md"), *GUIDES.glob("*.md")]
    quoted = {
        part
        for page in pages
        for span in re.findall(r"`([^`]+)`", page.read_text(encoding="utf-8"))
        for part in re.split(r"[.()\s:<>]", span)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", part)
    }

    assert pages
    assert quoted
    assert sorted(quoted - known) == []


def test_the_three_leaves_are_the_three_the_work_breakdown_names() -> None:
    """The leaf texts are held rather than restated. Delete this and the ids in the module's claim
    can be repointed at other leaves by an insertion in the work breakdown with nothing noticing."""
    texts = {
        leaf: text
        for module in json.loads((REPO / "docs" / "wbs.json").read_text(encoding="utf-8"))[
            "modules"
        ]
        for leaf, text in zip(module["leaf_ids"], module["leaf_texts"], strict=True)
    }

    assert texts["M34.3.2.2"] == "Grant and scope cookbook with worked examples"
    assert texts["M34.3.1.3"] == "How to ask well, with examples from their own department"
    assert texts["M34.3.2.1"] == "Runbook per console screen"
    assert {one.key for one in SCREENS} == set(runbooks())
