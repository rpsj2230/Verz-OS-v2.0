"""Which claims in the administration and staff guides are checked against the code, and how.

`brain.ops.install_docs` holds the pages a client reads while installing. This holds the three
they read afterwards: the grant and scope cookbook an administrator writes access from, the page
that tells a member of staff how to ask, and a runbook per console screen. It is a sibling rather
than more of that module because the registers differ: an install guide is checked against
compose files and a plan, and these are checked against the permission model, the starter
questions and the screen registry. It reuses that module's table reader, so a checked table is
spelled the same way on every page in `docs/`.

**A cookbook whose examples are prose is a second permission model, and it is the one an
administrator believes.** The obvious cookbook is a page of grants with a sentence under each
saying who that lets in, and every sentence is a claim about `EntitlementSet.intersect`,
`Capability.covers` and `Scope.matches` that nothing ever runs. That model drifted three times in
one week here: wildcards through a ceiling reached nothing until 2026-09-14, a column grant with
no row grant reached nothing until 2026-09-08, and an expired ceiling was judged against the
process clock until 2026-09-08. A page written before any of those would have gone on saying the
old answer. So every example states its grants and its outcomes as tables, and `cookbook_gaps`
builds the grants with the product's own resolver, asks the product's own row plane, and refuses
the page wherever the answer differs. See
`AN_EXAMPLE_NOBODY_RUNS_IS_A_SECOND_PERMISSION_MODEL_IN_PROSE`.

**Every example is asked through the functions a request is asked through, never through a
restatement of them.** A person's grants go through `brain.identity.packs.resolve_entitlement`,
which is where a grant's own expiry is applied; a run through an agent is that result intersected
with a ceiling whose row reads `brain.agents.model.records_implied_by` derives, which is how
`entitlement_ceiling` builds one; a row read is `brain.knowledge.rows.row_scope_for` against the
record's stored fields, and a column read is `compile_projection` over the demo's own column
classification. The rejected alternative was a small evaluator here that calls `scope_for` and
`matches` directly. It is simpler and it is exactly the second implementation this repository
forbids, and it would have agreed with the page on the day the page was written and with nothing
afterwards.

**The rows are the demo's rows and the vocabulary is the demo's vocabulary.** An example over an
invented table proves the arithmetic and nothing about a capability anybody can hold, so each
outcome names a record `brain.demo.build_records` writes, each capability has to cover one the
demo's classification requires, and a holder who is a demo person has to hold exactly what the
demo grants them. The last is what makes the see-the-record-not-the-money example the demo's
coordinator rather than a character somebody wrote to make a point. The demo rather than the test
fixture, because this page ships to clients and `brain.demo` is the company the product is
allowed to show them. See `A_PERSONA_BORROWED_FROM_THE_DEMO_HOLDS_WHAT_THE_DEMO_GRANTS`.

**Examples of how to ask are chosen per department, from what indexed.** The page a member of
staff reads says how to ask well in general and shows each department its own questions, and the
questions are `brain.adoption.starter_questions` over the entities that actually came back with
rows. A list written once is a list about one company's records. The demo's departments are the
worked case on the page, and `asking_gaps` holds that table to the derivation in both
directions, including the department with nothing indexed, which is shown saying so rather than
padded. See `AN_EXAMPLE_FROM_ANOTHER_DEPARTMENT_TEACHES_THAT_THE_SYSTEM_CANNOT_ANSWER`.

**A runbook is held to the registry on every fact it quotes, and the prose is not held.** What a
screen is for, what an empty result means and what to do about an alarm are sentences written
from reading the module behind the screen, and there is nothing to check them against. What is
checked is what a reader acts on without reading the sentence: the key, the title, the capability
the screen needs, the console plane, whether a department admin is offered it, and whether its
tool exists at all. The last one matters most today, because no console tool is registered, and a
runbook that did not say so would be instructions for a screen nobody can open. When a tool is
registered its row goes red, which is the day the runbook's prose should be re-read. See
`A_RUNBOOK_FOR_A_SCREEN_NOBODY_CAN_OPEN_HAS_TO_SAY_SO`.

Rejected: generating the pages from the registers. It is `brain.ops.install_docs`' rejection and
for the same reason: the useful half of each page is the sentence nothing here can write.

Task ids: M34.3.2.2, M34.3.1.3, M34.3.2.1
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Final

from brain.adoption import ScopeCoverage, starter_questions
from brain.agents.model import CEILING_PRINCIPAL_PREFIX, records_implied_by
from brain.console.reads import audience, plane_capability
from brain.console.screens import SCREENS, WITHHELD_AT_DEPARTMENT_SCOPE, Axis, Screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.demo import DemoPerson, DemoRecord, stored_fields
from brain.identity.packs import SubjectGrant, resolve_entitlement
from brain.identity.roles import NoStandingEntitlement, Role
from brain.identity.teams import PrincipalSubject
from brain.knowledge.columns import TableClassification
from brain.knowledge.rows import compile_projection, row_scope_for
from brain.launch import screen_runbook_gaps
from brain.locale import MESSAGES
from brain.ops.install_docs import InstallDocsError, bare, sections, table_after

# ------------------------------------------------------------------ written-down reasons
#: Why the cookbook's examples are executed rather than read.
AN_EXAMPLE_NOBODY_RUNS_IS_A_SECOND_PERMISSION_MODEL_IN_PROSE: Final = (
    "A cookbook sentence saying who a grant lets in is a claim about intersect, covers and "
    "matches that nothing runs. The permission model changed three times in one week, and a "
    "page written before any of those changes would have gone on stating the old answer to "
    "the administrator who writes access from it. So each example states its grants and its "
    "outcomes as tables, the grants are resolved by the product's own resolver, the outcomes "
    "are asked of the product's own row plane, and the page is refused where they differ."
)

#: Why every example has to show somebody refused as well as somebody reaching.
AN_EXAMPLE_WITH_NO_REFUSAL_IS_SATISFIED_BY_A_SYSTEM_THAT_GRANTS_EVERYTHING: Final = (
    "An example that only says who reaches the record is true of a system with no permission "
    "model at all, and one that only says who is refused is true of a system that refuses "
    "everybody. A grant is only described once both halves are stated, so an example with "
    "only one of them is a finding rather than a shorter example."
)

#: Why a demo person in the cookbook has to hold exactly the demo's grants.
A_PERSONA_BORROWED_FROM_THE_DEMO_HOLDS_WHAT_THE_DEMO_GRANTS: Final = (
    "An example naming the demo's coordinator and giving her a grant the demo does not is an "
    "example about somebody else wearing her name, and the reader who opens the demo to try "
    "it finds a different answer. So a holder who is a demo person is held to the demo's "
    "grants for that person, row reads included, and an invented holder is named so that "
    "nobody mistakes them for one."
)

#: Why the questions offered to one department are never another department's.
AN_EXAMPLE_FROM_ANOTHER_DEPARTMENT_TEACHES_THAT_THE_SYSTEM_CANNOT_ANSWER: Final = (
    "A member of staff tries the example they are shown. An example about invoices shown to "
    "a department whose grants reach no invoice comes back with nothing, and what they learn "
    "on their first day is that the system cannot answer. So each department is shown the "
    "questions built from the records indexed for it, and a department with nothing indexed "
    "is told so rather than lent a question from somewhere else."
)

#: Why a runbook states whether its screen can be opened.
A_RUNBOOK_FOR_A_SCREEN_NOBODY_CAN_OPEN_HAS_TO_SAY_SO: Final = (
    "The screen registry declares every console screen before the tool behind it is written, "
    "deliberately. A runbook that describes such a screen without saying it cannot be opened "
    "is instructions for a page the reader will spend an afternoon looking for. So whether "
    "the tool is registered is a checked fact on every runbook, and it goes red on the day a "
    "tool is registered, which is the day the runbook's prose needs reading again."
)


class GuideDocsError(InstallDocsError):
    """Raised when a guide cannot be read as the thing its check is about."""


# ------------------------------------------------------------------ the cookbook (M34.3.2.2)
#: Where an example lists the grants it is about.
GRANTS_MARKER: Final = "<!-- checked: the grants in this example -->"

#: Where an example lists who reaches what under those grants.
OUTCOMES_MARKER: Final = "<!-- checked: who reaches what in this example -->"

#: The two outcomes a row of an example can state.
REACHES: Final = "reaches"
REFUSED: Final = "refused"

#: A scope cell for a grant written company-wide.
EVERYWHERE: Final = "everywhere"

#: An expiry cell for a grant with no end.
NO_END: Final = "no end"

#: A route cell for somebody asking as themselves.
DIRECTLY: Final = "directly"

#: How a holder or a route names an agent's ceiling rather than a person.
AGENT: Final = "agent "

#: When every cookbook grant was made. Pinned in 2000, well before any instant an example asks
#: about, for the reason `CLAUDE.md` gives about dates in fixtures: an example that expires is
#: about its own `not_after` and must not also be about the day the test happens to run.
GRANTED_AT: Final = datetime(2000, 1, 1, tzinfo=UTC)

#: The examples the cookbook has to carry, by heading. What the leaf and its briefing asked for.
COOKBOOK_EXAMPLES: Final[tuple[str, ...]] = (
    "A grant scoped to one department",
    "A wildcard narrowed by an agent's ceiling",
    "Reaching a row and reading a column are two grants",
    "A grant that expires",
    "Sees the client, never what it is worth",
)

#: One clause of a scope cell: `department = projects`, `department in a, b`,
#: `reference starts with INV`.
#:
#: The value may not contain `=`, and that is what refuses `department = a or department = b`:
#: without it the whole of `a or department = b` is read as one value, the clause matches no
#: row, and every refusal the example states comes out true for the wrong reason.
CLAUSE: Final = re.compile(r"^([a-z][a-z0-9_.]*) (=|in|starts with) ([^=]+)$")

_OPS: Final[Mapping[str, Op]] = {"=": Op.EQ, "in": Op.IN, "starts with": Op.PREFIX}


def scope_of(cell: str) -> Scope:
    """A scope cell as the `Scope` it names. Conjunction only, because `Scope` is.

    `and` is the only connective, and there is deliberately no spelling for `or`: a cookbook
    that could write a disjunction would be teaching a grant the product cannot hold.
    """
    text = bare(cell)
    if text == EVERYWHERE:
        return Scope.unrestricted()
    clauses: list[Clause] = []
    for part in text.split(" and "):
        found = CLAUSE.match(part.strip())
        if found is None:
            msg = (
                f"{part.strip()!r} is not a clause: write `field = value`, `field in a, b` "
                "or `field starts with x`"
            )
            raise GuideDocsError(msg)
        field, op, value = found.groups()
        clauses.append(
            Clause(
                field=field,
                op=_OPS[op],
                value=tuple(one.strip() for one in value.split(",")) if op == "in" else value,
            )
        )
    return Scope(clauses=tuple(clauses))


def instant_of(cell: str) -> datetime:
    """A date cell as midnight UTC on that day."""
    try:
        return datetime.combine(date.fromisoformat(bare(cell)), time(), tzinfo=UTC)
    except ValueError as exc:
        msg = f"{bare(cell)!r} is not a date written YYYY-MM-DD"
        raise GuideDocsError(msg) from exc


@dataclass(frozen=True)
class StatedGrant:
    """One row of an example's grants table, read."""

    holder: str
    capability: Capability
    scope: Scope
    not_after: datetime | None


@dataclass(frozen=True)
class StatedOutcome:
    """One row of an example's outcomes table, read."""

    who: str
    through: str
    reads: Capability
    record: str
    at: datetime
    stated: str


def _grant_row(cells: Sequence[str]) -> StatedGrant:
    until = bare(cells[3])
    return StatedGrant(
        holder=bare(cells[0]),
        capability=Capability(value=bare(cells[1])),
        scope=scope_of(cells[2]),
        not_after=None if until == NO_END else instant_of(until),
    )


def _outcome_row(cells: Sequence[str]) -> StatedOutcome:
    return StatedOutcome(
        who=bare(cells[0]),
        through=bare(cells[1]),
        reads=Capability(value=bare(cells[2])),
        record=bare(cells[3]),
        at=instant_of(cells[4]),
        stated=bare(cells[5]),
    )


def reach_of(who: str, through: str, grants: Sequence[StatedGrant], at: datetime) -> EntitlementSet:
    """What `who` reaches at `at`, asking as themselves or through one agent.

    A person's grants are resolved by `resolve_entitlement`, which is where a grant's own
    `not_after` is applied. A ceiling is built the way `brain.agents.model.entitlement_ceiling`
    builds one: every capability bound to the agent's one scope, with the row reads its column
    reads imply, and no expiry. Then the one intersection.
    """
    principal = Principal(
        id=who, kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name=who
    )
    held = resolve_entitlement(
        principal,
        grants=tuple(
            SubjectGrant(
                subject=PrincipalSubject(principal_id=who),
                capability=one.capability,
                scope=one.scope,
                granted_by="cookbook",
                reason="a worked example in the grant and scope cookbook",
                granted_at=GRANTED_AT,
                not_after=one.not_after,
            )
            for one in grants
            if one.holder == who
        ),
        now=at,
    )
    if isinstance(held, NoStandingEntitlement):  # pragma: no cover - a staff principal
        msg = f"{who} resolved to no standing entitlement, which only a partner does"
        raise GuideDocsError(msg)
    if through == DIRECTLY:
        return held
    name = through.removeprefix(AGENT)
    declared = [one for one in grants if one.holder == through]
    scopes = {one.scope for one in declared}
    if len(scopes) != 1:
        msg = f"{through} declares {len(scopes)} scopes, and an agent's authority has one"
        raise GuideDocsError(msg)
    (scope,) = scopes
    if any(one.not_after is not None for one in declared):
        msg = f"{through} carries an expiry, and an agent ceiling has none"
        raise GuideDocsError(msg)
    capabilities = tuple(one.capability for one in declared)
    ceiling = EntitlementSet(
        principal_id=f"{CEILING_PRINCIPAL_PREFIX}{name}",
        grants=tuple(
            Grant(capability=capability, scope=scope)
            for capability in (*capabilities, *records_implied_by(capabilities))
        ),
    )
    # Through `audience`, the console's pinned route into the one intersection, rather than a
    # call of our own: `tests/invariants/test_single_implementation.py` pins every place the
    # central rule is applied, and a cookbook check is not a new place it should be. No instant
    # is lost by it. The ceiling carries no expiry, so there is nothing on its side to judge, and
    # each grant's own end was applied at `at` by `resolve_entitlement` above.
    return audience(held, ceiling)


def reaches(
    outcome: StatedOutcome,
    grants: Sequence[StatedGrant],
    *,
    records: Mapping[str, DemoRecord],
    classifications: Mapping[str, TableClassification],
) -> bool:
    """Whether the product lets this outcome's reader read what it names, on that record.

    A row read is `read:<entity>` and is the record's own scope matched by the reader's row
    scope. A column read is a row read and the column being in the projection the row plane
    compiles for that reader, which is the two-grant model exactly as a query applies it.
    """
    record = records[outcome.record]
    reach = reach_of(outcome.who, outcome.through, grants, outcome.at)
    rows = row_scope_for(record.entity, reach, outcome.at)
    if rows is None or not rows.matches(stored_fields(record)):
        return False
    _, dot, column = outcome.reads.value.partition(".")
    if not dot:
        return True
    return column in compile_projection(
        classifications[record.entity], entitlement=reach, rows=rows, now=outcome.at
    )


def vocabulary(classifications: Collection[TableClassification]) -> frozenset[Capability]:
    """Every capability the demo's columns and rows require. The words a grant may use."""
    return frozenset(
        {Capability(value=f"read:{one.entity}") for one in classifications}
        | {rule.required_capability for one in classifications for rule in one.rules}
    )


def cookbook_gaps(
    page: str,
    *,
    people: Sequence[DemoPerson],
    records: Sequence[DemoRecord],
    classifications: Sequence[TableClassification],
) -> tuple[str, ...]:
    """Every way the cookbook and the permission model disagree (M34.3.2.2).

    Arguments rather than imports of the demo, so the check can be shown a demo with a person or
    a record the page has never heard of. See the module docstring for why each example is
    asked of the product rather than of a restatement.
    """
    examples = [(heading, body) for heading, body in sections(page) if GRANTS_MARKER in body]
    stated = [heading for heading, _ in examples]
    findings = [
        f"{name!r}: the cookbook has no example of it"
        for name in COOKBOOK_EXAMPLES
        if name not in stated
    ]
    context = _Context(
        people={one.principal.id: one for one in people},
        records={one.source_id: one for one in records},
        classifications={one.entity: one for one in classifications},
    )
    for heading, body in examples:
        findings.extend(f"{heading!r}: {one}" for one in _example_gaps(body, context))
    return tuple(findings)


@dataclass(frozen=True)
class _Context:
    people: Mapping[str, DemoPerson]
    records: Mapping[str, DemoRecord]
    classifications: Mapping[str, TableClassification]


def _example_gaps(body: str, context: _Context) -> tuple[str, ...]:
    """One example's findings: its grants, its vocabulary, its demo people and its outcomes."""
    findings: list[str] = []
    grants: list[StatedGrant] = []
    for cells in table_after(body, GRANTS_MARKER):
        if len(cells) < 4:
            findings.append(
                f"a grant row with {len(cells)} cell(s) reads {cells}; every row states the "
                "holder, the capability, the scope and when it ends"
            )
            continue
        try:
            grants.append(_grant_row(cells))
        except (ValueError, GuideDocsError) as exc:
            findings.append(f"the grant row {cells} cannot be read: {exc}")
    # Reads only. A read is a word about the demo's records and has to name one of them; the
    # other verbs, `invoke:agent` among them, are about the platform rather than any record and
    # are checked by `Capability`'s own grammar and closed verb set.
    known = vocabulary(context.classifications.values())
    findings.extend(
        f"{one.capability.value} covers nothing the demo's records require, so it is a "
        "capability nobody can use"
        for one in grants
        if one.capability.verb == "read" and not any(one.capability.covers(word) for word in known)
    )
    findings.extend(_persona_gaps(grants, context.people))
    outcomes: list[StatedOutcome] = []
    for cells in table_after(body, OUTCOMES_MARKER):
        if len(cells) < 6:
            findings.append(
                f"an outcome row with {len(cells)} cell(s) reads {cells}; every row states "
                "who, through what, reading what, on which record, when, and the outcome"
            )
            continue
        try:
            outcomes.append(_outcome_row(cells))
        except (ValueError, GuideDocsError) as exc:
            findings.append(f"the outcome row {cells} cannot be read: {exc}")
    said = {one.stated for one in outcomes}
    if not {REACHES, REFUSED} <= said:
        findings.append(
            "the example does not state both somebody reaching and somebody refused. "
            f"{AN_EXAMPLE_WITH_NO_REFUSAL_IS_SATISFIED_BY_A_SYSTEM_THAT_GRANTS_EVERYTHING}"
        )
    for one in outcomes:
        findings.extend(_outcome_gaps(one, grants, context))
    return tuple(findings)


def _persona_gaps(
    grants: Sequence[StatedGrant], people: Mapping[str, DemoPerson]
) -> tuple[str, ...]:
    """A demo person on the page holds exactly the demo's grants. See the reason constant."""
    findings: list[str] = []
    for holder in dict.fromkeys(one.holder for one in grants):
        person = people.get(holder)
        if person is None:
            continue
        written = {
            (one.capability, one.scope, one.not_after) for one in grants if one.holder == holder
        }
        demo = {(one.capability, one.scope, person.principal.not_after) for one in person.grants}
        if written != demo:
            findings.append(
                f"{holder} is a demo person and the page gives them "
                f"{sorted(one[0].value for one in written)} where the demo grants "
                f"{sorted(one[0].value for one in demo)}. "
                f"{A_PERSONA_BORROWED_FROM_THE_DEMO_HOLDS_WHAT_THE_DEMO_GRANTS}"
            )
    return tuple(findings)


def _outcome_gaps(
    one: StatedOutcome, grants: Sequence[StatedGrant], context: _Context
) -> tuple[str, ...]:
    """One stated outcome against what the product answers."""
    if one.stated not in (REACHES, REFUSED):
        return (
            f"{one.who}: the outcome reads {one.stated!r}, which is neither "
            f"{REACHES!r} nor {REFUSED!r}",
        )
    if one.record not in context.records:
        return (f"{one.who}: {one.record} is not a record the demo writes",)
    if one.through != DIRECTLY and not any(grant.holder == one.through for grant in grants):
        return (
            f"{one.who}: {one.through!r} holds no grant in this example, so it is not a ceiling",
        )
    record = context.records[one.record]
    if one.reads.noun != record.entity:
        return (f"{one.who}: reads {one.reads.value} on {one.record}, which is a {record.entity}",)
    if one.reads not in vocabulary((context.classifications[record.entity],)):
        return (f"{one.who}: {one.reads.value} is not a row or a column the demo classifies",)
    try:
        answer = reaches(
            one, grants, records=context.records, classifications=context.classifications
        )
    except GuideDocsError as exc:
        return (f"{one.who}: {exc}",)
    actual = REACHES if answer else REFUSED
    if actual == one.stated:
        return ()
    # A one-element tuple, and the trailing comma is the whole of that. Without it the
    # parentheses are only grouping, `extend` walks the sentence a character at a time, and the
    # one finding this check exists to make arrives as sixty findings of one letter each.
    return (
        f"{one.who} {DIRECTLY if one.through == DIRECTLY else 'through ' + one.through} reading "
        f"{one.reads.value} on {one.record} at {one.at.date().isoformat()}: the page says "
        f"{one.stated!r} and the product says {actual!r}",
    )


# ---------------------------------------------------------------- how to ask well (M34.3.1.3)
#: The language the guides in `docs/` are written in, and so the one their examples render in.
GUIDE_LANGUAGE: Final = "en"

#: What a department with nothing indexed is shown in place of examples.
NO_EXAMPLES_YET: Final = "nothing has indexed for this department yet"

#: The second cell of that row, spelled rather than left blank for `NO_CEILING`'s reason in
#: `brain.ops.install_docs`: an empty cell reads as one somebody forgot.
NOWHERE_TO_CHECK: Final = "nowhere yet"


def examples_marker(department: str) -> str:
    """Where the asking guide lists one department's examples."""
    return f"<!-- checked: examples from {department} -->"


#: Any department's examples marker, so a table for a department that is not there is found.
EXAMPLES_MARKER: Final = re.compile(r"<!-- checked: examples from ([a-z][a-z0-9_]*) -->")


@dataclass(frozen=True)
class AskingExample:
    """One question a department is shown, as a person reads it, and where to check it."""

    department: str
    question: str
    check_in: str


def indexed_coverage(
    indexed: Sequence[tuple[str, str]],
    *,
    departments: Sequence[str],
    source: str,
    synced_at: datetime,
) -> tuple[ScopeCoverage, ...]:
    """One coverage row per department, from the (department, entity) of every indexed record.

    Every department named gets a row, including one nothing indexed for, because that
    department is shown saying so rather than left out. Entities are ordered most populated
    first, which is the order `starter_questions` reads them in.
    """
    rows: list[ScopeCoverage] = []
    for department in departments:
        counted: dict[str, int] = {}
        for placed, entity in indexed:
            if placed == department:
                counted[entity] = counted.get(entity, 0) + 1
        rows.append(
            ScopeCoverage(
                department=department,
                source=source,
                connected=True,
                records=sum(counted.values()),
                last_sync=synced_at,
                entities=tuple(sorted(counted.items(), key=lambda one: (-one[1], one[0]))),
            )
        )
    return tuple(rows)


def asking_examples(
    rows: Sequence[ScopeCoverage], department: str, *, checkable: frozenset[str]
) -> tuple[AskingExample, ...]:
    """The questions one department is shown, rendered the way a person reads them.

    `starter_questions` decides which, and it reads only the rows for this department, which
    is the whole of `AN_EXAMPLE_FROM_ANOTHER_DEPARTMENT_TEACHES_THAT_THE_SYSTEM_CANNOT_ANSWER`.
    The sentence is the catalogue's, in `GUIDE_LANGUAGE`, with the entity in the source's own
    word.
    """
    return tuple(
        AskingExample(
            department=department,
            question=MESSAGES[one.shape][GUIDE_LANGUAGE].format(entity=one.entity),
            check_in=one.check_in,
        )
        for one in starter_questions(rows, department, checkable=checkable)
    )


def asking_gaps(
    page: str,
    *,
    rows: Sequence[ScopeCoverage],
    departments: Sequence[str],
    checkable: frozenset[str],
) -> tuple[str, ...]:
    """Every way the asking guide's worked examples and the derivation disagree (M34.3.1.3).

    Exact, in order, per department, and both directions: a department with no table, a table
    for a department that is not there, and a table whose questions are not the ones the
    department's own records produce.
    """
    findings: list[str] = []
    tabled = set(EXAMPLES_MARKER.findall(page))
    findings.extend(
        f"{name}: a table of examples for a department that is not there, which reads as coverage"
        for name in sorted(tabled - set(departments))
    )
    for department in departments:
        if department not in tabled:
            findings.append(f"{department}: no examples, so its staff are shown somebody else's")
            continue
        stated: list[tuple[str, str]] = []
        for cells in table_after(page, examples_marker(department)):
            if len(cells) < 2:
                findings.append(
                    f"{department}: a row with {len(cells)} cell(s) reads {cells}; every row "
                    "states the question and where to check it"
                )
                continue
            stated.append((bare(cells[0]), bare(cells[1])))
        derived = [
            (one.question, one.check_in)
            for one in asking_examples(rows, department, checkable=checkable)
        ] or [(NO_EXAMPLES_YET, NOWHERE_TO_CHECK)]
        if stated != derived:
            findings.append(
                f"{department}: the page shows {stated} and the department's own records "
                f"produce {derived}"
            )
    return tuple(findings)


# ------------------------------------------------------------ a runbook per screen (M34.3.2.1)
#: Where a runbook states what the registry says about its screen.
RUNBOOK_FACTS_MARKER: Final = "<!-- checked: what the registry says about this screen -->"

#: The four sections every runbook carries, in this order.
RUNBOOK_SECTIONS: Final[tuple[str, ...]] = (
    "What it is for",
    "Who may see it",
    "When it is empty or refuses",
    "When it shows an alarm",
)


def yes_or_no(value: bool) -> str:
    """How a runbook states a yes-or-no fact. Spelled, never a tick."""
    return "yes" if value else "no"


def runbook_facts(
    screen: Screen, *, registered_tools: Collection[str]
) -> tuple[tuple[str, str], ...]:
    """What a runbook's facts table has to say about this screen, read off the registry."""
    return (
        ("Key", screen.key),
        ("Title", screen.title),
        ("Group", screen.group.value),
        ("Tool", screen.read.tool),
        ("Needs", screen.read.requires.value),
        ("Console plane", plane_capability(screen.read.plane).value),
        ("Narrowed by", ", ".join(axis.value for axis in Axis if axis in screen.axes)),
        (
            "Offered to a department admin",
            yes_or_no(screen.key not in WITHHELD_AT_DEPARTMENT_SCOPE),
        ),
        ("Designed for", ", ".join(role.value for role in Role if role in screen.intended_for)),
        ("Can be opened today", yes_or_no(screen.read.tool in registered_tools)),
    )


def runbook_gaps(
    runbooks: Mapping[str, str],
    *,
    registered_tools: Collection[str],
    screens: Sequence[Screen] = SCREENS,
) -> tuple[str, ...]:
    """Every way the runbooks and the screen registry disagree (M34.3.2.1).

    `brain.launch.screen_runbook_gaps` first, which is completeness in both directions and a
    blank runbook. Then, per runbook that exists: its title, every fact in its table as a value
    and in both directions, and its four sections in order with something under each.
    """
    findings = list(screen_runbook_gaps(runbooks, screens=screens))
    for screen in screens:
        text = runbooks.get(screen.key, "")
        if not text.strip():
            continue
        findings.extend(
            f"{screen.key}: {one}" for one in _runbook_gaps(screen, text, registered_tools)
        )
    return tuple(findings)


def _runbook_gaps(screen: Screen, text: str, registered_tools: Collection[str]) -> tuple[str, ...]:
    findings: list[str] = []
    first = text.strip().splitlines()[0]
    if first != f"# {screen.title}":
        findings.append(f"the runbook opens {first!r} and the screen is called {screen.title!r}")
    stated: dict[str, str] = {}
    for cells in table_after(text, RUNBOOK_FACTS_MARKER):
        if len(cells) < 2:
            findings.append(f"a fact row with {len(cells)} cell(s) reads {cells}")
            continue
        stated[bare(cells[0])] = bare(cells[1])
    declared = dict(runbook_facts(screen, registered_tools=registered_tools))
    findings.extend(
        f"{name}: the runbook does not state it" for name in declared if name not in stated
    )
    findings.extend(
        f"{name}: a fact the registry does not declare, which reads as one it does"
        for name in stated
        if name not in declared
    )
    findings.extend(
        f"{name}: the runbook says {stated[name]!r} and the registry says {declared[name]!r}"
        for name in declared
        if name in stated and stated[name] != declared[name]
    )
    found = sections(text)
    headings = [heading for heading, _ in found]
    if headings != list(RUNBOOK_SECTIONS):
        findings.append(
            f"the sections read {headings} and every runbook has {list(RUNBOOK_SECTIONS)}"
        )
    findings.extend(
        f"{heading!r}: a section with nothing under it"
        for heading, body in found
        if not body.strip()
    )
    return tuple(findings)
