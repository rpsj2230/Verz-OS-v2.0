"""What was consumed, broken down four ways, by somebody who may not see all of it.

`brain.console.spend_view` is the neighbour, and the split is which question each answers.
That one asks what a run cost in money and reads `brain.ops.spend`. This one asks what was
consumed, in questions asked and in tokens, which is the figure somebody reads before anybody
has agreed a price list. Both are filtered through the same `may_read_spend`, imported rather
than re-implemented, because a reader who may be told what a department spent and may not be
told how many questions it asked can work the second out from the first.

**The four axes are four different kinds of thing, and that is a permission question rather
than a layout one.** A person is a principal. A department is a scope, which is the vocabulary
the reader's own grant is written in. A model is a vendor's fact and says nothing about this
company at all. An agent is a lens, and `brain.agents.model.AUDIENCE_IS_NOT_AUTHORITY` says
that who may know a lens exists is decided separately from everything else about it. So
`AXIS_DISCLOSURE` gives each axis the grant it is read behind, and three of them share one
answer for three different reasons rather than because they were treated as one axis with four
labels. See `THE_FOUR_AXES_ARE_FOUR_DIFFERENT_DISCLOSURES`.

**The leak on this screen is between two tables and not inside either one.** A single
breakdown whose total is the sum of its own lines discloses nothing: it is arithmetic a
renderer could do. Four breakdowns of what a reader believes is one row set are different. If
the agent table were filtered per key, by the agent's own audience, every line on it would be
correct and the difference between its total and the department table's total would be the
tokens spent through agents this reader may not be told exist. Nothing on either table would
be wrong, nothing would say a row had been dropped, and the disclosure is a subtraction across
two correct tables. So **every axis is computed over one `Admitted` row set, the filtering
happens once in `admit`, and an axis a reader may not have is absent rather than narrowed**.
See `TWO_TABLES_OF_ONE_ROW_SET_SUBTRACT_INTO_NOTHING` and
`AN_AXIS_IS_OFFERED_WHOLE_OR_NOT_AT_ALL`.

**A total is shown, and it is the sum of the lines on the screen and nothing else.**
`UsageReport` asserts that in its constructor, exactly as `spend_view.Report` does, and for the
same reason: a renderer that adds the lines up itself will one day be handed a truncated list.
There is no company total, no figure over rows the reader did not see, no residual bucket and
no share of anything this report did not print, because a denominator the reader cannot see is
the subtraction with a percent sign on it. The property that makes the total safe here is
stronger than one report can state, so a test states it: two axes of one `Admitted` carry
identical totals, and a reader offered three axes sees the same totals a reader offered four
does.

**The department travels with the row and is never looked up here.** This is the objection
that stopped M27.4.2 being claimed on 2026-09-11, and it is a real one:
`brain.ops.spend.Actual` carries a department and a cost and no token counts, while
`brain.ops.telemetry.RequestTelemetry` carries tokens attributable by principal, agent version,
lane and model and carries no department. Assembling a tokens-by-department column at read time
means a reporting path asking a directory which department somebody is in, and the wrong copy
of that answer then decides who appears in a report. `UsageRow` therefore takes the department
as a field the caller supplies at the point the run completes, where it is already known, in
the same way `spend_view.Setback` is assembled from a `Preflight` and a department. **No
function here takes a directory, a roster or a lookup, and `usage_gaps` reads the signatures
for one.** See `THE_DEPARTMENT_TRAVELS_WITH_THE_ROW_AND_IS_NEVER_LOOKED_UP_HERE`.

What that costs, said rather than left to be discovered: there is no constructor here pairing
an `Actual` with a `RequestTelemetry`, because nothing says the two describe the same run.
`Actual` carries no trace id, and the trace id is the join key the whole of
`brain.ops.telemetry` is built around. Until it does, a `UsageRow` is written where both halves
are already in hand and never reassembled afterwards from two ledgers.

**Machine traffic is excluded by default and the report says so**, on `spend_view`'s argument,
quoted rather than written a second time. It binds harder here than it does there: a nightly
sync's share of the token count is larger than its share of anything else on a console, so a
usage report that included it silently would answer "who uses this most" with the name of a
schedule.

**A reader's own run is not an exception.** `spend_view.told_about` admits somebody to their
own allowance whatever they may read of a department, and that is right for a refusal about
one person's ceiling. It would be wrong here, and the reason is the multi-axis shape again: a
row admitted because it is the reader's own carries a department, and that department then
appears as a key on the department table for somebody with no grant over it. One row's worth
of tokens is not the disclosure; the department's name is. See
`A_READERS_OWN_RUN_IS_NOT_AN_EXCEPTION_ON_A_MULTI_AXIS_REPORT`.

What else was rejected.

*Filtering the agent axis by `brain.agents.model.visible_agent_ids`.* It is the obvious reading
of `A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER` and it is the cross-table subtraction
above. The audience predicate is the right question about a listing of agents and the wrong one
about a breakdown that has to reconcile with three others.

*Reusing `brain.ops.spend.Dimension`.* It has five members and M27.4.2 names four: `LANE` is a
cost-accounting dimension nobody here has decided a disclosure for, and a fifth axis arriving
by import is a fifth axis whose permission nobody argued. `Axis` has exactly the leaf's four,
`usage_gaps` fails if one of them has no declared grant, and `_key` is an `assert_never` match
so a fifth is a type error rather than an empty column.

*A `department` or `person` parameter, so a reader could narrow the report themselves.* The
narrowing a reader gets is their grant. A parameter naming an area is a value somebody chose,
and the only list it can honestly be chosen from is `brain.console.screens.offerable`, which
intersects the options against what the caller already reaches; taking the name straight into
the filter moves that intersection out to whoever populated the dropdown, which is
`brain.console.screens.A_FILTER_LIST_IS_A_LISTING_OF_EVERYTHING_IT_OFFERS`. `spend_view`
refused the same parameter on the same screen, and this is that refusal kept rather than
restated.

*A count of rows dropped, an "others" bucket, and a note saying an axis was withheld.* All
three are the hidden count with a label on it, and the last is the one that looks like honesty.

*Checking the plane here as well as the capability.* `brain.console.reads.permitted` asks for
both, and it is the right question for opening a screen rather than for filtering a row: it is
what `screens.navigation` already asks before this module is reached at all, and asking it
again per row would put a second copy of the plane rule in the one place it is least visible.
`spend_view` makes the same call over the same rows and the same grant, and two console
modules disagreeing about whether a row read is also a plane read would be worse than either
answer.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter throughout, for the reason `brain.ops.limits` gives about policy that owns a client
being untestable at the boundary that is always wrong. Nothing here writes.

Task ids: M27.4.2
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from types import MappingProxyType
from typing import Final, assert_never

from brain.console.screens import screen
from brain.console.spend_view import (
    MACHINE_TRAFFIC_IS_EXCLUDED_BY_DEFAULT_AND_THE_REPORT_SAYS_SO,
    USAGE_AUTHORITY,
    may_read_spend,
)
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import PrincipalKind
from brain.gate.context import TrafficClass
from brain.ops.limits import is_automated
from brain.ops.spend import NO_AGENT


class UsageViewError(Exception):
    """Raised when a usage report would state something the rows it holds cannot support."""


# ------------------------------------------------------------------ written-down reasons

#: Why the four axes get four separate decisions even where three reach the same answer.
THE_FOUR_AXES_ARE_FOUR_DIFFERENT_DISCLOSURES: Final = (
    "A person is a principal, so a line on that axis names somebody. A department is a scope, "
    "so every key on that axis is a value the reader's own grant already admits and the axis "
    "is the grant's own vocabulary read back. A model is a vendor's fact: the key discloses "
    "nothing about this company, and the number beside it discloses everything, which is why "
    "the axis is free and the rows are not. An agent is a lens, and "
    "brain.agents.model.AUDIENCE_IS_NOT_AUTHORITY keeps who may know a lens exists apart from "
    "everything else about it, so that axis is the one read behind a grant of its own. Four "
    "decisions, written down separately, rather than one decision with four labels on it."
)

#: Why the totals rule on this screen is about two tables rather than one.
TWO_TABLES_OF_ONE_ROW_SET_SUBTRACT_INTO_NOTHING: Final = (
    "A breakdown whose total is the sum of its own lines discloses nothing, because it is "
    "arithmetic the reader could do. Four breakdowns of what looks like one row set are a "
    "different object. Filter the agent table per key and every line on it is correct, no "
    "line says anything was dropped, and the gap between its total and the department "
    "table's is the tokens spent through agents this reader may not be told exist. So the "
    "filtering happens once, in admit, and every axis groups the same rows: any two tables a "
    "reader can hold subtract into nothing."
)

#: Why an axis is offered whole or withheld whole, and never narrowed.
AN_AXIS_IS_OFFERED_WHOLE_OR_NOT_AT_ALL: Final = (
    "The tempting middle is an axis narrowed to the keys this reader may see, which looks "
    "like a privacy improvement and is the subtraction above. It is the same shape "
    "brain.console.reach_view refuses when it shows a ceiling whole or replaces it with a "
    "lock. An axis a reader may not break usage down by is absent from the screen, carries no "
    "note saying so and leaves no gap in the figures, because the axes that remain were "
    "computed over exactly the rows the withheld one would have been."
)

#: Why the department is a field on the row rather than something this module works out.
THE_DEPARTMENT_TRAVELS_WITH_THE_ROW_AND_IS_NEVER_LOOKED_UP_HERE: Final = (
    "brain.ops.spend.Actual carries a department and no tokens; "
    "brain.ops.telemetry.RequestTelemetry carries tokens and no department. A column joining "
    "the two at read time asks a directory which department somebody is in, on a reporting "
    "path, and the wrong copy of that answer decides who appears in a report and who does "
    "not. The department is therefore supplied on the row by whoever records the run, where "
    "it is already known, and no function here takes a directory, a roster or a lookup it "
    "could ask instead."
)

#: Why machine traffic is excluded here too, in the words the spend screen already used.
MACHINE_TRAFFIC_IS_EXCLUDED_HERE_FOR_THE_SAME_REASON: Final = (
    "Tokens make this bind harder than money does: a schedule's share of a token count is "
    "larger than its share of almost anything else on a console, so a usage report that "
    "included automation silently would answer the question 'who uses this most' with the "
    "name of a nightly job. The argument is the spend screen's and is quoted rather than "
    "written again: " + MACHINE_TRAFFIC_IS_EXCLUDED_BY_DEFAULT_AND_THE_REPORT_SAYS_SO
)

#: Why there is no "but it is my own run" admission on this screen.
A_READERS_OWN_RUN_IS_NOT_AN_EXCEPTION_ON_A_MULTI_AXIS_REPORT: Final = (
    "spend_view.told_about admits a person to a refusal about their own allowance whatever "
    "they may read of a department, and that is right: their ceiling is a fact about them. "
    "Here the same exception leaks something else entirely. A row admitted because the reader "
    "is its principal still carries a department, and that department then appears as a key "
    "on the department table for somebody holding no grant over it. The tokens are theirs; "
    "the department's name is not."
)


# ------------------------------------------------------------------------------ the axes
class Axis(enum.StrEnum):
    """The four ways M27.4.2 asks for usage to be broken down, in the order it names them.

    Exactly four members and deliberately not `brain.ops.spend.Dimension`, which has five: a
    lane is a cost-accounting dimension and nobody here has decided what disclosure breaking
    usage down by it would be. A fifth member added to this enum fails `usage_gaps` until it
    has an entry in `AXIS_DISCLOSURE`, and is a type error in `_key` until somebody says what
    it groups by.
    """

    #: A principal. Every key is somebody, which is true of the default report and not of
    #: the enum: a principal is a person or a service account, and it is the machine filter
    #: rather than this axis that keeps the heading honest.
    PERSON = "person"
    #: A scope. Every key is a value the reader's own grant admits.
    DEPARTMENT = "department"
    #: A vendor's fact. The key says nothing about this company; the figure says a lot.
    MODEL = "model"
    #: A lens. Who may know one exists is a separate decision from what it did.
    AGENT = "agent"


#: The capability the agent axis is read behind: the Agents screen's own requirement.
#:
#: Written out rather than read off `brain.console.screens`, for the reason
#: `brain.console.reach_view.CEILING_DISCLOSURE` is: derived, the comparison in `usage_gaps`
#: would be a constant against itself and repointing either would move both. Written out, the
#: two are compared and a drift is a finding.
#:
#: The Agents screen is described as every agent, its ceiling and its leash state, so a reader
#: holding this has already been decided to be somebody who may learn which agents exist. A
#: usage table naming agents to somebody without it would be that screen's listing arriving
#: through a report, which is the retrieval leak `CLAUDE.md` names wearing a different noun.
AGENT_VOCABULARY: Final[Capability] = Capability(value="read:agent")

#: Which grant each axis is read behind. Three share one and the fourth does not.
#:
#: The three that share `USAGE_AUTHORITY` reach it for three separate reasons, set out in
#: `THE_FOUR_AXES_ARE_FOUR_DIFFERENT_DISCLOSURES`. The person axis in particular is on the row
#: grant because `brain.console.spend_view.spend_report` already groups the same rows by
#: principal behind exactly this capability: deciding it differently here would leave two
#: console modules with two answers to one question, and the one that drifts is whichever a
#: later reader happens to open.
AXIS_DISCLOSURE: Final[Mapping[Axis, Capability]] = MappingProxyType(
    {
        Axis.PERSON: USAGE_AUTHORITY,
        Axis.DEPARTMENT: USAGE_AUTHORITY,
        Axis.MODEL: USAGE_AUTHORITY,
        Axis.AGENT: AGENT_VOCABULARY,
    }
)


def may_break_down_by(
    axis: Axis, entitlement: EntitlementSet, *, now: datetime | None = None
) -> bool:
    """Whether this reader may have this axis at all.

    `scope_for` alone, and not `scope_for` followed by `Scope.matches`, which is the whole
    difference between this question and `may_read_spend`. A row is admitted by a scope
    matching a place; an axis is not a row and has no place to match, so what is asked here is
    whether the reader holds the grant the axis is read behind. A reader whose usage grant
    names one department still gets the department axis, and it has one key on it.

    A direct subscript, and there is deliberately no guard for an axis missing from
    `AXIS_DISCLOSURE`. `Axis` is closed and `usage_gaps` reports an omission, so a fallback
    here would be a branch no test could reach, which is the defect this repository keeps
    finding in validators; `brain.console.spend_view.pace` records removing one for the same
    reason. It is the construction `brain.ops.spend.Refusal.budget` uses against
    `BUDGET_PHRASE` with `budget_gaps` beside it: loud on the day somebody adds a member,
    rather than an axis silently withheld from everybody for a reason nobody wrote down.
    """
    return entitlement.scope_for(AXIS_DISCLOSURE[axis], now) is not None


def axes_for(entitlement: EntitlementSet, *, now: datetime | None = None) -> tuple[Axis, ...]:
    """Every axis this reader may break usage down by, in the leaf's own order.

    Returns the axes and no second value. A count of what was withheld is the subtraction
    `brain.console.screens.navigation` refuses for the same reason at the level of a menu.
    """
    return tuple(axis for axis in Axis if may_break_down_by(axis, entitlement, now=now))


# ------------------------------------------------------------------------------- the rows
@dataclass(frozen=True)
class UsageRow:
    """One completed run: who asked, where they sit, what answered and what it consumed.

    The department is a field rather than something derived, and that is the load-bearing
    decision in this module. See
    `THE_DEPARTMENT_TRAVELS_WITH_THE_ROW_AND_IS_NEVER_LOOKED_UP_HERE`.

    Whether this was a machine is derived rather than stored, through
    `brain.ops.limits.is_automated`, exactly as `brain.ops.spend.Actual.machine` is. There is
    no boolean a caller could set, so there is no second answer to disagree with the first.

    Carries no question, no answer and no record id, on `Actual`'s own argument: a usage
    ledger holding them is a second copy of the business activity under its own retention.
    """

    principal_id: str
    principal_kind: PrincipalKind
    traffic: TrafficClass
    department: str
    model: str
    agent_id: str | None
    tokens_in: int
    tokens_out: int
    at: datetime

    def __post_init__(self) -> None:
        if not self.principal_id.strip() or not self.department.strip() or not self.model.strip():
            msg = "a usage row needs a principal, a department and a model to group by"
            raise UsageViewError(msg)
        if self.agent_id is not None and not self.agent_id.strip():
            msg = (
                "an agent id of whitespace buckets under a key nobody can name and is not the "
                f"no-agent bucket; a run through no agent carries None and groups under "
                f"{NO_AGENT!r}"
            )
            raise UsageViewError(msg)
        if self.tokens_in < 0 or self.tokens_out < 0:
            # A negative count is a subtraction that went the wrong way, and the usual source
            # of one is a figure derived from something withheld. Refused here rather than
            # summed into a total somebody then cannot reconcile.
            msg = f"tokens are counts; {self.tokens_in} in and {self.tokens_out} out is neither"
            raise UsageViewError(msg)
        if self.at.tzinfo is None:
            msg = "a naive instant lands in the wrong period at either end of a day"
            raise UsageViewError(msg)

    @property
    def machine(self) -> bool:
        """Whether nobody was asking. A lookup through `is_automated`, never a guess."""
        return is_automated(self.principal_kind, self.traffic)

    @property
    def tokens(self) -> int:
        """In and out together, for ordering. Never shown instead of the two."""
        return self.tokens_in + self.tokens_out


@dataclass(frozen=True)
class Admitted:
    """The rows one reader may see, filtered once, for every axis to be grouped from.

    Holding one of these is what makes two breakdowns comparable: they were computed from the
    same tuple, so their totals agree by construction rather than by a caller remembering to
    pass the same filter twice. See `TWO_TABLES_OF_ONE_ROW_SET_SUBTRACT_INTO_NOTHING`.

    The constructor refuses a machine row on a set that says it excluded them, so a
    hand-assembled `Admitted` cannot put automation back into a report whose qualifier says it
    is not there.
    """

    reader_id: str
    rows: tuple[UsageRow, ...]
    machine_included: bool

    def __post_init__(self) -> None:
        if not self.machine_included and any(one.machine for one in self.rows):
            msg = (
                "this row set says it excludes automation and holds a machine row, so every "
                f"report built from it carries a qualifier that is false. "
                f"{MACHINE_TRAFFIC_IS_EXCLUDED_HERE_FOR_THE_SAME_REASON}"
            )
            raise UsageViewError(msg)


def admit(
    rows: Sequence[UsageRow],
    entitlement: EntitlementSet,
    *,
    now: datetime | None = None,
    include_machine: bool = False,
) -> Admitted:
    """The rows this reader's usage grant admits, filtered once for the whole screen (M27.4.2).

    One question per row, through `brain.console.spend_view.may_read_spend`, which is the
    single statement in this package of whether a reader's usage grant admits a department's
    rows. Imported rather than restated: two copies would drift on the afternoon somebody
    widens one report, and the copy that drifts decides who appears in the other.

    Machine traffic is dropped here rather than at the point of grouping, so that every axis
    sees the same rows and the qualifier on the report is a fact about the set rather than a
    caption. There is no self-exception: see
    `A_READERS_OWN_RUN_IS_NOT_AN_EXCEPTION_ON_A_MULTI_AXIS_REPORT`.

    A reader holding nothing is admitted to nothing and finds that out as an empty set rather
    than as a refusal, because a refusal naming the capability would tell them a usage report
    exists.
    """
    return Admitted(
        reader_id=entitlement.principal_id,
        rows=tuple(
            one
            for one in rows
            if (include_machine or not one.machine)
            and may_read_spend(one.department, entitlement, now=now)
        ),
        machine_included=include_machine,
    )


# --------------------------------------------------------------------------- the breakdown
@dataclass(frozen=True)
class UsageLine:
    """One bucket of one breakdown: what it is called, and what was consumed under it.

    Questions and tokens rather than a single figure, because M27.4.2 asks for both and
    because they answer different questions: a thousand cheap questions and one long task are
    the same token count and a very different week.

    Tokens in and out are kept apart for the same reason `brain.ops.telemetry` keeps them
    apart. They are priced differently by every provider, so one number is a figure that
    reconciles against no invoice anybody will ever receive.
    """

    key: str
    runs: int
    tokens_in: int
    tokens_out: int

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass(frozen=True)
class UsageReport:
    """Usage in one axis, at one reader's reach.

    Every total is the sum of `lines` and is asserted to be, which is `spend_view.Report`'s
    rule and its reason: a renderer that adds them up itself will one day be handed a
    truncated list and will print the figure nobody can reconcile.

    There is no field here for a company total, a share, a rank, a residual bucket or a count
    of anything absent, and that is not a rule about what a renderer may print. It is the
    absence of anything to print.
    """

    axis: Axis
    lines: tuple[UsageLine, ...]
    machine_included: bool
    total_runs: int
    total_tokens_in: int
    total_tokens_out: int

    def __post_init__(self) -> None:
        stated = (self.total_runs, self.total_tokens_in, self.total_tokens_out)
        shown = (
            sum(one.runs for one in self.lines),
            sum(one.tokens_in for one in self.lines),
            sum(one.tokens_out for one in self.lines),
        )
        if stated != shown:
            msg = (
                f"the totals are {stated} over lines summing to {shown}, in runs, tokens in "
                "and tokens out, so a difference is a figure about rows this reader was not "
                f"shown. {TWO_TABLES_OF_ONE_ROW_SET_SUBTRACT_INTO_NOTHING}"
            )
            raise UsageViewError(msg)

    @property
    def total_tokens(self) -> int:
        return self.total_tokens_in + self.total_tokens_out


def _key(row: UsageRow, axis: Axis) -> str:
    """This row's bucket on one axis.

    `assert_never` rather than a mapping with a default, for the reason
    `brain.ops.spend.Actual.key_for` gives: a fifth axis is a type error until somebody decides
    what it groups by, where a default would produce an empty column that reads as no usage.

    A run with no agent buckets under `brain.ops.spend.NO_AGENT`, imported rather than spelled
    again, so the agent axis totals to the same figure as the other three. Dropping those rows
    instead would make the agent table quietly smaller than the department table, which is the
    cross-table subtraction this module is built to avoid arriving through the back door.
    """
    match axis:
        case Axis.PERSON:
            return row.principal_id
        case Axis.DEPARTMENT:
            return row.department
        case Axis.MODEL:
            return row.model
        case Axis.AGENT:
            return row.agent_id or NO_AGENT
        case _:  # pragma: no cover - unreachable while Axis has four members
            assert_never(axis)


def usage_by(
    admitted: Admitted,
    axis: Axis,
    entitlement: EntitlementSet,
    *,
    now: datetime | None = None,
) -> UsageReport | None:
    """Usage in one axis over an already-admitted row set (M27.4.2).

    `None` when this reader may not break usage down this way. Not an empty report and not a
    refusal: an empty report would say there was no usage, and a refusal would say there was an
    axis. Absence says neither.

    **The entitlement decides whether the axis is offered and never which rows it covers.**
    That is the property no signature can prove and a test does: two readers holding the same
    axis disclosure and different department scopes, handed one `Admitted`, get identical
    reports. The filtering already happened, once, in `admit`.

    **A row set is grouped for the reader it was admitted for and for nobody else.** That is
    the one way the filtering and the grouping can come apart: a caller holding a wide
    reader's `Admitted` and a narrow reader's grants would render a table at one person's
    reach under another person's name, with every line on it arithmetically correct. Refused
    rather than silently honoured, because the two objects arrive from different places in a
    request and the mismatch is not visible in anything the table prints.

    Lines are ordered by tokens, largest first, with the key as the tie-break so two readings
    of one report do not disagree about the order of two equal figures.
    """
    if admitted.reader_id != entitlement.principal_id:
        msg = (
            f"this row set was admitted for {admitted.reader_id!r} and is being grouped for "
            f"{entitlement.principal_id!r}, so the table would be rendered at one person's "
            "reach under another person's name"
        )
        raise UsageViewError(msg)
    if not may_break_down_by(axis, entitlement, now=now):
        return None
    counted: dict[str, tuple[int, int, int]] = {}
    for row in admitted.rows:
        key = _key(row, axis)
        runs, tokens_in, tokens_out = counted.get(key, (0, 0, 0))
        counted[key] = (runs + 1, tokens_in + row.tokens_in, tokens_out + row.tokens_out)
    lines = tuple(
        sorted(
            (
                UsageLine(key=key, runs=runs, tokens_in=tokens_in, tokens_out=tokens_out)
                for key, (runs, tokens_in, tokens_out) in counted.items()
            ),
            key=lambda one: (-one.tokens, one.key),
        )
    )
    return UsageReport(
        axis=axis,
        lines=lines,
        machine_included=admitted.machine_included,
        total_runs=sum(one.runs for one in lines),
        total_tokens_in=sum(one.tokens_in for one in lines),
        total_tokens_out=sum(one.tokens_out for one in lines),
    )


def breakdowns(
    admitted: Admitted,
    entitlement: EntitlementSet,
    *,
    now: datetime | None = None,
) -> tuple[UsageReport, ...]:
    """Every breakdown this reader may have, from one row set, in the leaf's order (M27.4.2).

    The screen. One `Admitted` goes in, so the tables that come out cannot have been computed
    over different filters, which is the failure `TWO_TABLES_OF_ONE_ROW_SET_SUBTRACT_INTO_NOTHING`
    describes and the one no individual table would reveal.

    Returns the reports and no second value saying how many axes were withheld.
    """
    found = [usage_by(admitted, axis, entitlement, now=now) for axis in Axis]
    return tuple(one for one in found if one is not None)


# ------------------------------------------------------------------------------- the gaps
#: Field names that would put a figure about rows this reader was not shown onto a value here.
#:
#: `brain.console.reach_view.COUNTING_NAMES` restated for this module's shapes rather than
#: imported, and the difference is `total`. A total here is the sum of the lines on the screen
#: and is asserted to be by `UsageReport.__post_init__`, so forbidding the word would forbid
#: the one figure this module argues is safe. What is forbidden is a figure whose denominator
#: or residual is something the reader did not see, and those have their own names.
COUNTING_NAMES: Final[frozenset[str]] = frozenset(
    {
        "company_total",
        "dropped",
        "excluded",
        "grand_total",
        "hidden",
        "hidden_count",
        "more",
        "of_total",
        "others",
        "remaining",
        "residual",
        "share_of_company",
        "showing",
        "unfiltered_total",
        "withheld",
    }
)

#: Parameter names through which a department could be worked out rather than carried.
#:
#: The enforcement of `THE_DEPARTMENT_TRAVELS_WITH_THE_ROW_AND_IS_NEVER_LOOKED_UP_HERE`. The
#: rule is not that somebody must remember it: it is that the only way to break it is to add a
#: parameter, and a parameter is a thing a reviewer and this check both see.
LOOKUP_NAMES: Final[frozenset[str]] = frozenset(
    {"department_of", "departments", "directory", "lookup", "members", "roster", "staff"}
)

#: Parameter names through which a report could be computed at more than the reader's reach,
#: or narrowed to an area the reader asked for rather than one their grant derives.
WIDENING_NAMES: Final[frozenset[str]] = frozenset(
    {"also", "department", "extra", "include", "override", "person", "union", "widen"}
)

#: Parameter names through which a second row set could reach a function that must not filter.
SECOND_ROW_SET: Final[frozenset[str]] = frozenset(
    {"actuals", "all_rows", "records", "rows", "unfiltered", "usage"}
)

#: The one function here that legitimately takes rows, because it is where filtering happens.
#:
#: Named rather than compared by identity so that a surface handed in for testing is checked
#: the same way this module's own is, and so that repointing the exemption is a visible change.
THE_FILTER: Final = "admit"

#: The functions a forbidden parameter could arrive on.
USAGE_SURFACE: Final[tuple[Callable[..., object], ...]] = (
    admit,
    usage_by,
    breakdowns,
    axes_for,
    may_break_down_by,
)

#: The values a forbidden field could arrive on.
USAGE_MODELS: Final[tuple[type, ...]] = (UsageRow, Admitted, UsageLine, UsageReport)


def usage_gaps(
    functions: Sequence[Callable[..., object]] | None = None,
    models: Sequence[type] | None = None,
    disclosure: Mapping[Axis, Capability] | None = None,
) -> tuple[str, ...]:
    """Everything about this module that would let a usage table say more than it should.

    Five checks. Every one is a review comment that would otherwise survive exactly as long as
    the reviewer remembers it, and every one is about an edit somebody would make for a good
    reason.

    All three inputs are parameters defaulting to this module's own, for the reason
    `brain.ops.telemetry.telemetry_gaps` takes two: a diagnostic that can only be pointed at
    code known to be clean is a diagnostic nobody has watched produce a finding, and nobody
    knows whether it can.
    """
    gaps: list[str] = []
    declared = AXIS_DISCLOSURE if disclosure is None else disclosure

    # 1. An axis nobody decided a grant for. `may_break_down_by` subscripts this mapping
    # directly and raises, which is loud and late; this is the same omission found early.
    for axis in Axis:
        if axis not in declared:
            gaps.append(
                f"the {axis.value} axis has no declared disclosure, so nobody decided what "
                "breaking usage down that way tells a reader and the screen fails on the "
                "request rather than in review"
            )

    # 2. The agent axis drifting off the screen whose vocabulary it borrows. Compared rather
    # than derived: see `AGENT_VOCABULARY`.
    agents = screen("agents").read.requires
    if declared.get(Axis.AGENT) != agents:
        gaps.append(
            f"the agent axis is read behind {declared.get(Axis.AGENT)} and the Agents screen "
            f"requires {agents.value}, so a usage table names agents to a reader who cannot "
            "open the screen that lists them, or withholds them from one who can"
        )

    # 3. A way to ask which department somebody is in, or to widen what a report covers.
    for function in USAGE_SURFACE if functions is None else tuple(functions):
        taken = set(inspect.signature(function).parameters)
        for forbidden in sorted(taken & (LOOKUP_NAMES | WIDENING_NAMES)):
            gaps.append(
                f"{function.__name__} takes {forbidden}, so this module either works out "
                "which department somebody is in or is told which one to report on, and "
                "neither is a question a reporting path may answer"
            )

    # 4. A second row set reaching anything but the filter, which is how two tables on one
    # screen come to have been computed over two different reaches.
    for function in USAGE_SURFACE if functions is None else tuple(functions):
        if function.__name__ == THE_FILTER:
            continue
        taken = set(inspect.signature(function).parameters)
        for forbidden in sorted(taken & SECOND_ROW_SET):
            gaps.append(
                f"{function.__name__} takes {forbidden}, so it can group rows the filter "
                "never saw and its total no longer agrees with the other axes of the same "
                "screen, which is the one disclosure here that no single table shows"
            )

    # 5. A figure about rows the reader was not shown, arriving as a field.
    for model in USAGE_MODELS if models is None else tuple(models):
        for declared_field in fields(model):
            if declared_field.name in COUNTING_NAMES:
                gaps.append(
                    f"{model.__name__} carries {declared_field.name}, which beside a filtered "
                    "figure is the size of what this reader may not see"
                )

    return tuple(gaps)
