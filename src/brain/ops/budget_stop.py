"""What happens when a budget is used up: somebody is told, and then nothing more runs.

`brain.ops.budgets` holds the ceilings and `brain.ops.spend` decides one request at a time.
Neither has anywhere to put a consequence that outlives a request, and a ceiling whose only
consequence is refusing the request that reached it refuses the next one just as freely: the
department finds out by being refused, one person at a time, all week, and nobody who could
raise the ceiling is ever told.

**This is the design that was argued against, and the argument is recorded here rather than
in a commit message nobody re-reads.** The recommendation was to refuse only the expensive
lanes and leave cheap answers working, because a hard stop at a budget turns a cost control
into an outage. The owner chose a warning followed by a hard stop until the next period, in
that order, and that is what is built. The argument against it has not gone away, so the
mitigation is visibility rather than a quietly softer rule: a `Stop` carries the instant it
ends, `brain.console.spend_view` shows an operator every budget currently refusing at their
own reach, and the operator record is `RefusalKind.QUOTA`, whose `OPERATOR_ACTION` is a
different sentence from a permission refusal's. What was rejected is silence. See
`THE_STOP_THE_OWNER_CHOSE_IS_MADE_VISIBLE_RATHER_THAN_SOFTENED`.

**"Until the next period" is a boundary, and it comes from the exhausted row's own period
floored in the install's time zone.** Nothing else in a budget says when its window rolls:
`BudgetPeriod` is the only field that carries a window at all, and the zone is a company
setting read once by `brain.locale.time_zone`, so it arrives here as a parameter for the
reason every other instant does. The two rolling periods are rows in `WINDOWS` rather than
arms of a branch: a period added to `BudgetPeriod` with no row here is reported by
`boundary_gaps` instead of falling into an `else` that computes a plausible instant a month
out. See `A_PERIOD_BOUNDARY_IS_A_ROW_AND_NOT_AN_ELSE`.

**A per-run ceiling has no next period, so it can never open a stop, and that is the sharpest
thing in this module.** Waiting does not refill a per-run ceiling, which is why
`brain.console.spend_view.pace` already refuses to pace one. A stop "until the next period"
applied to a per-run ceiling would therefore never end: a cost control would become a
permanent outage through a rule nobody wrote down. `consequence_of` returns nothing for one,
and `Stop` refuses to be constructed with one, so both the deciding path and the value it
would produce are closed. A per-run ceiling refuses the request that reached it and exhausts
nothing. See `A_PER_RUN_CEILING_HAS_NO_NEXT_PERIOD_AND_A_STOP_ON_ONE_NEVER_ENDS`.

**A budget stop ends with its period; a halt ends with a person.** `brain.ops.halt` argues at
length that a stop with an expiry is a lie, because it ends at a time chosen by whoever wrote
the default while everybody who was told still believes the system is stopped. The opposite is
true here and the difference is worth stating so nobody unifies the two: a halt is a decision
somebody made and only a person may unmake it, while a budget stop is an arithmetic
consequence of a ceiling, and it must end at the instant the ceiling refills or it is an
outage nobody chose and nobody is watching for. So `Halt` has no expiry field and `Stop` has
no resume. See `A_BUDGET_STOP_ENDS_WITH_ITS_PERIOD_AND_A_HALT_ENDS_WITH_A_PERSON`.

**Warn first, then refuse, and the order is a shape rather than a comment.** `Consequence`
carries both and neither is optional, so there is no constructor that opens a stop without a
warning, and it refuses a warning raised after the stop it precedes. A stop with no warning is
a department finding out by being refused, which is the failure the owner's ordering exists to
prevent. See `A_STOP_WITH_NO_WARNING_IS_A_DEPARTMENT_FINDING_OUT_BY_BEING_REFUSED`.

**Refusing to warn is not the same as not warning.** A department with no admin is the
ordinary case in a young install, not an error, and the tempting answer is to raise: it fails
loudly, it is easy to test, and it means the stop does not happen. The next tempting answer is
to return nothing, which means the stop happens and nobody hears. Neither is right. The
warning escalates one level wider, derived from `budgets.LEVEL_BREADTH` rather than written
out again, and only when nobody holds the authority there either is it `UNADDRESSED`, which is
a state a person has to be able to see rather than a silence. One hop and not a chain: a
warning that walked all the way to the top would report having found somebody when what it
found was that the level it was meant for is unstaffed. See
`REFUSING_TO_WARN_IS_NOT_THE_SAME_AS_NOT_WARNING`.

**An undeliverable warning does not suspend the ceiling.** The stop opens whether or not the
notice reached anybody, because a budget that stopped enforcing itself when the directory was
incomplete would be a ceiling that any misconfiguration switches off. See
`AN_UNDELIVERABLE_WARNING_DOES_NOT_SUSPEND_THE_CEILING`.

Rejected: a `resume` on `Stop`, so an administrator could lift one early. The way to lift a
budget stop is to raise the budget, which is a versioned row with an author on it, and a lift
here would be the same act with no author, no version and no history. `brain.ops.halt` is
where a person stops and starts things by hand.

Rejected: naming the recipients here. This module takes them already resolved, in the two
sequences `warn` asks for, exactly as `spend.preflight` takes allowances somebody else
fetched. A module that resolved its own recipients would own a directory client and could not
be asked what it would do when a department has nobody, which is the only case worth testing.

Rejected: a count of how many people were warned, on the notice. It is a headcount of an
authority, derived from the directory, and it travels wherever the notice does.

Scope: domain logic. Nothing here opens a connection, reads a clock or sends anything; every
instant, every recipient and the time zone arrive as parameters, for the reason
`brain.ops.limits` gives about policy that owns a client being untestable at the boundary
that matters.

**No leaf is claimed.** M27.4.3 is "budgets and spend limits, and what happens at the
ceiling", and it is a screen whose tool nobody has written; claiming it here would have the
traceability sweep counting a screen that cannot be opened. This is the policy the screen will
show, in the same position `brain.ops.halt` holds behind the stop button, and it claims
nothing for the same reason that module does.

Task ids: none
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final
from zoneinfo import ZoneInfo

from brain.core.entitlement import Capability
from brain.ops.admission import RefusalKind, refusal_record
from brain.ops.budgets import LEVEL_BREADTH, Allowance, BudgetKey, BudgetLevel, BudgetPeriod
from brain.ops.spend import Refusal

# ------------------------------------------------------------------ written-down reasons
#: Why the design that was argued against is built with a light on it rather than softened.
THE_STOP_THE_OWNER_CHOSE_IS_MADE_VISIBLE_RATHER_THAN_SOFTENED: Final = (
    "The recommendation was to refuse only the expensive lanes, because a hard stop at a "
    "budget turns a cost control into an outage. The owner chose a warning and then a hard "
    "stop until the next period. Quietly building something gentler would be the worst of "
    "the three outcomes: the ceiling would not do what the console says it does. So the "
    "chosen rule is built exactly, and what the argument bought instead is that the outage "
    "is never silent. A stop carries the instant it ends, an operator can see every budget "
    "currently refusing at their own reach, and the operator record is QUOTA rather than "
    "PERMISSION, which is a different sentence about what to do."
)

#: Why the two rolling periods are rows rather than arms of a branch.
A_PERIOD_BOUNDARY_IS_A_ROW_AND_NOT_AN_ELSE: Final = (
    "A branch on the period computes something for every period, including one added later "
    "that nobody thought about here, and what it computes is plausible: a boundary a month "
    "out, or tomorrow, arrived at by whichever arm fell through. A row per period turns the "
    "same mistake into an absent key, which boundary_gaps reports and consequence_of will "
    "not guess past. What each row holds is where a window starts and how far past that you "
    "have to step to land inside the next one, which is the whole of the arithmetic."
)

#: Why a per-run ceiling can never open a stop.
A_PER_RUN_CEILING_HAS_NO_NEXT_PERIOD_AND_A_STOP_ON_ONE_NEVER_ENDS: Final = (
    "Waiting does not refill a per-run ceiling, which is why spend_view.pace refuses to pace "
    "one and why BudgetPeriod.RUN exists as a member at all. A stop that lasts until the "
    "next period therefore has no end when the period is a run, and a cost control would "
    "become a permanent outage through a rule nobody wrote down. A per-run ceiling refuses "
    "the request that reached it and exhausts nothing, so there is nobody to warn and "
    "nothing to stop."
)

#: Why this expires and a halt does not.
A_BUDGET_STOP_ENDS_WITH_ITS_PERIOD_AND_A_HALT_ENDS_WITH_A_PERSON: Final = (
    "brain.ops.halt argues that a stop with an expiry is a lie, because it ends at a time "
    "chosen by whoever wrote the default while everybody who was told still believes the "
    "system is stopped. That is right about a halt and wrong here, and unifying the two "
    "would break whichever one was made to follow the other. A halt is a decision somebody "
    "took and only a person may untake it. A budget stop is an arithmetic consequence of a "
    "ceiling and it has to end at the instant the ceiling refills, or it is an outage "
    "nobody chose and nobody is watching for. Halt has no expiry field and Stop has no "
    "resume."
)

#: Why the notice is a field on the consequence rather than a separate call.
A_STOP_WITH_NO_WARNING_IS_A_DEPARTMENT_FINDING_OUT_BY_BEING_REFUSED: Final = (
    "The owner asked for both, in that order. An order kept by whoever wired the call sites "
    "up is an order that is kept until somebody adds a second call site, and the way it "
    "fails is that the stop happens and the warning does not, which is exactly the outcome "
    "the ordering exists to prevent. Consequence carries both and neither is optional, and "
    "it refuses a notice raised after the stop it is supposed to precede."
)

#: Why a department with no admin escalates rather than raising or returning nothing.
REFUSING_TO_WARN_IS_NOT_THE_SAME_AS_NOT_WARNING: Final = (
    "A department with no admin is the ordinary state of a young install rather than an "
    "error. Raising fails loudly and means the ceiling does not enforce itself; returning "
    "nothing means it does and nobody hears. So the warning goes one level wider, to "
    "whoever holds the authority over the budget above this one, and the notice says that "
    "is what happened. Only when nobody holds it there either is the notice UNADDRESSED, "
    "which is a state somebody has to be able to see. One hop rather than a chain, because "
    "a warning that walked to the top would report having found somebody when what it found "
    "was that the level it was meant for is unstaffed."
)

#: Why the stop opens even when the notice reached nobody.
AN_UNDELIVERABLE_WARNING_DOES_NOT_SUSPEND_THE_CEILING: Final = (
    "A ceiling that stopped enforcing itself when the directory was incomplete would be a "
    "budget any misconfiguration switches off, and the misconfiguration that switches it off "
    "is an empty admin list, which is what a new department looks like. The stop opens "
    "whether or not anybody was told, and the notice carries whether anybody was."
)


class BudgetStopError(Exception):
    """A stop, a boundary or a warning described in a shape that could not do its job.

    An authoring-time failure like `budgets.BudgetError`, and deliberately not part of the
    `brain.core.errors` taxonomy: what a person is told when a budget stop refuses them is
    `brain.console.spend_view.told_about`, which carries no figure and frequently carries no
    budget either.
    """


# ------------------------------------------------------------------- the period boundary
@dataclass(frozen=True)
class Window:
    """How one rolling period's window is found: where it starts, and how far to the next.

    A record per period rather than a branch per period. See
    `A_PERIOD_BOUNDARY_IS_A_ROW_AND_NOT_AN_ELSE`.

    `stride` is how far past a window's start you must step to land somewhere inside the next
    one, and the second flooring removes however far in it landed. That is why a month's
    stride is thirty-two days rather than a month: the longest month is thirty-one, so
    thirty-two lands inside the next window whatever the calendar does, and no arithmetic
    here has to know how long February is.
    """

    #: The day of the month a window starts on, or nothing when it starts on any day.
    starts_on_day: int | None
    #: How far past a window's start lands inside the next window, whatever the calendar does.
    stride: timedelta

    def __post_init__(self) -> None:
        if self.stride <= timedelta(0):
            msg = (
                f"a stride of {self.stride} lands in the window it started in, so the next "
                "period would begin at the same instant as this one and a stop would end "
                "before it began"
            )
            raise BudgetStopError(msg)
        if self.starts_on_day is not None and not 1 <= self.starts_on_day <= 28:
            msg = (
                f"a window starting on day {self.starts_on_day} does not exist in every "
                "month, so the boundary would move or fail depending on the calendar"
            )
            raise BudgetStopError(msg)


#: How each rolling period's window is found. Exhaustive over the periods that roll, and
#: `boundary_gaps` keeps it that way.
WINDOWS: Final[Mapping[BudgetPeriod, Window]] = MappingProxyType(
    {
        BudgetPeriod.DAY: Window(starts_on_day=None, stride=timedelta(days=1)),
        BudgetPeriod.MONTH: Window(starts_on_day=1, stride=timedelta(days=32)),
    }
)

#: The periods that do not roll, declared rather than inferred from the absence of a window.
#:
#: Without this, a rolling period added to `BudgetPeriod` and forgotten here would be
#: indistinguishable from a per-run ceiling: `consequence_of` would return nothing for it and
#: the budget would never stop anybody, silently. Declared, it is a finding.
DOES_NOT_ROLL: Final[frozenset[BudgetPeriod]] = frozenset({BudgetPeriod.RUN})


def _start_of(local: datetime, window: Window) -> datetime:
    """The start of the window this local wall-clock instant falls in.

    Wall clock rather than an aware instant, because the arithmetic a person means by "the
    first of next month" is calendar arithmetic and not a count of seconds. The zone is put
    back on at the end of `next_period_start`, so a period that contains a clock change is
    still a whole period and a stop still ends at local midnight rather than an hour either
    side of it.
    """
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if window.starts_on_day is None:
        return midnight
    return midnight.replace(day=window.starts_on_day)


def next_period_start(period: BudgetPeriod, at: datetime, *, zone: ZoneInfo) -> datetime:
    """When the window containing `at` rolls over, in the install's own time zone (M21.1.1).

    The zone is a parameter because it is a company setting: `brain.locale.time_zone` reads
    it, in the one place installation values are read, and hands it here. A boundary computed
    in UTC on a company that is not in UTC ends a month several hours early or late, which is
    a stop lifting at seven in the evening on the last day of the month.

    Refuses a period that does not roll. See
    `A_PER_RUN_CEILING_HAS_NO_NEXT_PERIOD_AND_A_STOP_ON_ONE_NEVER_ENDS`.
    """
    window = WINDOWS.get(period)
    if window is None:
        msg = (
            f"a {period.value} ceiling has no next period, so a stop until the next one "
            f"would never end. {A_PER_RUN_CEILING_HAS_NO_NEXT_PERIOD_AND_A_STOP_ON_ONE_NEVER_ENDS}"
        )
        raise BudgetStopError(msg)
    if at.tzinfo is None:
        msg = "a naive instant has no zone to be floored in, so the boundary would be a guess"
        raise BudgetStopError(msg)
    local = at.astimezone(zone).replace(tzinfo=None)
    following = _start_of(_start_of(local, window) + window.stride, window)
    return following.replace(tzinfo=zone)


def boundary_gaps() -> tuple[str, ...]:
    """Every budget period whose boundary nothing here could compute, or would compute wrongly.

    The same construction `budgets.level_gaps` uses. A period in neither table is the failure
    worth naming: `consequence_of` returns nothing for it, so the budget enforces its ceiling
    one request at a time for ever and nothing reports that the stop was never opened.
    """
    gaps: list[str] = []
    for period in BudgetPeriod:
        if period not in WINDOWS and period not in DOES_NOT_ROLL:
            gaps.append(
                f"{period.value} has no window and is not declared as a period that does not "
                "roll, so a budget at it opens no stop and nothing says why"
            )
        if period in WINDOWS and period in DOES_NOT_ROLL:
            gaps.append(
                f"{period.value} both rolls and does not, so a ceiling that cannot refill "
                "would open a stop with an end instant nothing will reach"
            )
    return tuple(gaps)


# ------------------------------------------------------------------------------ the stop
@dataclass(frozen=True)
class Stop:
    """One budget that is used up, and the questions it refuses until its window rolls.

    Addressed by the same `BudgetKey` a ceiling is, so a stop and the row it came from cannot
    drift into naming different things.

    **There is no way to end this early and no field an extension could live on.** A stop is
    lifted by raising the budget, which is a versioned row with an author on it; a lift here
    would be the same act with no author and no history. See
    `A_BUDGET_STOP_ENDS_WITH_ITS_PERIOD_AND_A_HALT_ENDS_WITH_A_PERSON`.
    """

    level: BudgetLevel
    subject: str
    period: BudgetPeriod
    since: datetime
    until: datetime

    def __post_init__(self) -> None:
        if not self.subject.strip():
            msg = f"a {self.level} stop naming no subject refuses everybody or nobody"
            raise BudgetStopError(msg)
        if self.period not in WINDOWS:
            msg = (
                f"a {self.period.value} ceiling cannot be stopped until the next period. "
                f"{A_PER_RUN_CEILING_HAS_NO_NEXT_PERIOD_AND_A_STOP_ON_ONE_NEVER_ENDS}"
            )
            raise BudgetStopError(msg)
        if self.since.tzinfo is None or self.until.tzinfo is None:
            msg = "a naive instant on a stop compares wrongly against an aware request time"
            raise BudgetStopError(msg)
        if self.until <= self.since:
            msg = (
                f"this stop ends at {self.until.isoformat()} and began at "
                f"{self.since.isoformat()}, so it refuses nothing and reads on a screen "
                "exactly like one that refuses everything"
            )
            raise BudgetStopError(msg)

    @property
    def key(self) -> BudgetKey:
        """The ceiling this stop belongs to, in `budgets`' own addressing."""
        return (self.level, self.subject, self.period)

    def in_force_at(self, at: datetime) -> bool:
        """Whether this stop is refusing at that instant.

        Half open: it refuses from the instant it began up to but not including the instant
        the period rolls, so the first request of the new period is served rather than being
        the one that discovers the boundary is inclusive.
        """
        return self.since <= at < self.until

    def log_record(self) -> Mapping[str, str]:
        """The operator-facing line. `QUOTA`, and the end instant is what makes it a stop.

        The same kind and the same subject as `spend.Refusal.log_record`, because it is the
        same thing happening: an allowance that belongs to the caller has run out. What
        separates the two on an operator's screen is that this one names when it ends, so a
        reader can tell a single refused request from a department that will be refused for
        the rest of the month.

        No subject beyond the budget's level and period, which is `refusal_record`'s own
        rule. Which department is stopped is on the console screen, at a reader's reach; a
        log line travels further than a screen does.
        """
        return refusal_record(
            RefusalKind.QUOTA,
            subject=f"budget:{self.level}:{self.period}",
            detail=f"used up; refusing until {self.until.isoformat()}",
        )


def in_force(stops: Sequence[Stop], *, at: datetime) -> tuple[Stop, ...]:
    """Every stop refusing at that instant, widest budget first.

    Widest first because that is the order somebody acts in: relieving a person's allowance
    while their department is stopped changes nothing, which is
    `budgets.THE_WIDEST_OF_TWO_EXHAUSTED_BUDGETS_IS_THE_ONE_NAMED` read from the other end.

    A stop whose window has passed is simply absent from the answer. Nothing clears one, and
    nothing has to: a stop that outlived its period would be the expiring halt this module
    argues against, arrived at by leaving a row in a table.
    """
    return tuple(
        sorted(
            (one for one in stops if one.in_force_at(at)),
            key=lambda one: (LEVEL_BREADTH[one.level], one.subject, str(one.period)),
        )
    )


def stopped(allowances: Sequence[Allowance], stops: Sequence[Stop], *, at: datetime) -> Stop | None:
    """The stop refusing this request, or None when none is.

    Matched on the ceiling's own key rather than on a level and a subject compared by hand,
    so a stop against a department's monthly budget cannot refuse a request judged against
    that department's daily one.

    The widest is returned when several bind, for the reason `budgets.tightest` breaks its
    own tie that way: the person sent to relieve a narrower budget while a wider one is
    stopped has been sent to the wrong place.
    """
    keys = {one.row.key for one in allowances}
    binding = [one for one in in_force(stops, at=at) if one.key in keys]
    return binding[0] if binding else None


# ---------------------------------------------------------------------------- the warning
#: What somebody must hold to be told a budget is used up, and to be able to do anything
#: about it.
#:
#: One capability with a scope rather than one per level, because the level is already in the
#: budget's own place: whoever holds this over one department is that department's budget
#: admin and whoever holds it unrestricted owns the company's. `brain.ops.alerting` routes to
#: a capability for the same reason, which it states as
#: `AN_ALERT_ROUTES_TO_A_ROLE_AND_NEVER_TO_A_PERSON`: a named recipient is a row that goes
#: stale the week somebody changes job, and the failure is silent.
#:
#: Deliberately not `admin:halt` and not `approve:grant`. Stopping the system and recertifying
#: grants are different authorities from funding a department, and a budget warning that
#: landed on everybody who can press the stop button is a budget warning people filter.
BUDGET_AUTHORITY: Final[Capability] = Capability(value="admin:budget")


class Addressing(enum.StrEnum):
    """How a warning found its recipients. Three, and the third is a finding rather than a state.

    A closed vocabulary rather than a sentence, because a console counts these and a
    free-text reason cannot be counted. The sentences are in the constants above.
    """

    #: Somebody holds the authority over this budget itself.
    OWN_ADMIN = "own_admin"
    #: Nobody does, so whoever holds the authority one level wider was told instead.
    ESCALATED = "escalated"
    #: Nobody holds it here or one level wider. The stop still opens.
    UNADDRESSED = "unaddressed"


def wider_than(level: BudgetLevel) -> BudgetLevel | None:
    """The level a warning escalates to, or None at the widest.

    Derived from `budgets.LEVEL_BREADTH` rather than written out again, so the escalation and
    the tie-break between two exhausted budgets cannot disagree about which of two levels is
    the wider one. The company's is the widest and escalates nowhere, which is why an
    unaddressed company warning is the loudest thing this module can produce: nobody in the
    install holds the authority over the one budget that cannot be relieved from inside it.
    """
    breadth = LEVEL_BREADTH[level]
    wider = [one for one, width in LEVEL_BREADTH.items() if width < breadth]
    if not wider:
        return None
    return max(wider, key=lambda one: LEVEL_BREADTH[one])


@dataclass(frozen=True)
class Notice:
    """The warning that goes out before the stop, and who it actually reached.

    Carries no figure and no headroom, for the reason `spend.A_REFUSAL_CARRIES_NO_FIGURE`
    gives about the refusal: two notices a fortnight apart, each naming what was left,
    subtract into everybody else's spending. It names the budget, because the recipient is
    the person who can raise that budget, and it names nobody who was refused.

    `addressing` and `to` are held in step by the constructor: an unaddressed notice with
    recipients, or an addressed one with none, is a report that would read as a warning
    having been delivered.
    """

    level: BudgetLevel
    subject: str
    period: BudgetPeriod
    at: datetime
    #: The principals this was addressed to, already resolved from the directory.
    to: tuple[str, ...]
    addressing: Addressing

    def __post_init__(self) -> None:
        if not self.subject.strip():
            msg = "a warning about a budget with no subject names nothing anybody can raise"
            raise BudgetStopError(msg)
        if self.at.tzinfo is None:
            msg = "a naive instant on a warning cannot be ordered against the stop it precedes"
            raise BudgetStopError(msg)
        if (self.addressing is Addressing.UNADDRESSED) != (not self.to):
            msg = (
                f"this warning is {self.addressing.value} and names {len(self.to)} "
                "recipient(s); an unaddressed warning reached nobody and an addressed one "
                f"reached somebody. {REFUSING_TO_WARN_IS_NOT_THE_SAME_AS_NOT_WARNING}"
            )
            raise BudgetStopError(msg)
        if len(set(self.to)) != len(self.to):
            msg = "one recipient is named twice, so a delivery count would be wrong"
            raise BudgetStopError(msg)

    @property
    def budget(self) -> str:
        """Which budget this is about, in `spend`'s words rather than in a second set.

        The recipient is being told about somebody else's ceiling rather than their own, so
        the second person in `BUDGET_PHRASE` reads oddly for them. It is still the right
        call: a second phrasing table is a second thing to keep in step with `BudgetLevel`,
        and the one that drifts is whichever nobody has a test for.
        """
        return Refusal(level=self.level, period=self.period).budget

    @property
    def unaddressed(self) -> bool:
        """Whether this warning reached nobody at all. The finding, not the ordinary case."""
        return self.addressing is Addressing.UNADDRESSED


def warn(
    *,
    level: BudgetLevel,
    subject: str,
    period: BudgetPeriod,
    at: datetime,
    admins: Sequence[str],
    above: Sequence[str],
) -> Notice:
    """Tell whoever can raise this budget that it is used up, or record that nobody could be.

    `admins` is whoever holds `BUDGET_AUTHORITY` over this budget's own place and `above` is
    whoever holds it over the place of the level `wider_than` names. Both arrive resolved:
    see the module docstring for why this does not resolve them itself.

    Never raises for an empty directory. See `REFUSING_TO_WARN_IS_NOT_THE_SAME_AS_NOT_WARNING`.
    """
    if admins:
        return Notice(
            level=level,
            subject=subject,
            period=period,
            at=at,
            to=tuple(dict.fromkeys(admins)),
            addressing=Addressing.OWN_ADMIN,
        )
    if above:
        return Notice(
            level=level,
            subject=subject,
            period=period,
            at=at,
            to=tuple(dict.fromkeys(above)),
            addressing=Addressing.ESCALATED,
        )
    return Notice(
        level=level,
        subject=subject,
        period=period,
        at=at,
        to=(),
        addressing=Addressing.UNADDRESSED,
    )


# ------------------------------------------------------------- both, and in that order
@dataclass(frozen=True)
class Consequence:
    """Everything that follows a budget being used up, in the order the owner chose.

    Both fields and neither optional, which is
    `A_STOP_WITH_NO_WARNING_IS_A_DEPARTMENT_FINDING_OUT_BY_BEING_REFUSED` written as a shape.
    The constructor holds the two to one budget and to the stated order, so a caller cannot
    pair a warning about one department with a stop on another, and cannot record a warning
    raised after the refusals it was supposed to precede.
    """

    notice: Notice
    stop: Stop

    def __post_init__(self) -> None:
        if (self.notice.level, self.notice.subject, self.notice.period) != self.stop.key:
            msg = (
                f"this warning is about {self.notice.level}:{self.notice.subject} and the "
                f"stop is on {self.stop.level}:{self.stop.subject}, so somebody was told "
                "about a budget that is not the one refusing"
            )
            raise BudgetStopError(msg)
        if self.notice.at > self.stop.since:
            msg = (
                f"the warning was raised at {self.notice.at.isoformat()} and the stop began "
                f"at {self.stop.since.isoformat()}; the owner asked for both in the other "
                "order, and a warning that arrives after the refusals is a receipt"
            )
            raise BudgetStopError(msg)


def consequence_of(
    binding: Allowance,
    *,
    at: datetime,
    zone: ZoneInfo,
    admins: Sequence[str],
    above: Sequence[str],
) -> Consequence | None:
    """Warn, then stop, for the budget that bound. None when that ceiling does not roll.

    `binding` is what `budgets.tightest` returned, so the budget warned about and stopped is
    the one that actually refused rather than the first one in a list.

    None is the per-run case and it is not a failure: a per-run ceiling refuses the request
    that reached it and exhausts nothing, so there is nobody to warn and nothing to stop. See
    `A_PER_RUN_CEILING_HAS_NO_NEXT_PERIOD_AND_A_STOP_ON_ONE_NEVER_ENDS`.

    The stop opens whether or not the notice reached anybody. See
    `AN_UNDELIVERABLE_WARNING_DOES_NOT_SUSPEND_THE_CEILING`.
    """
    row = binding.row
    if row.period in DOES_NOT_ROLL:
        return None
    until = next_period_start(row.period, at, zone=zone)
    return Consequence(
        notice=warn(
            level=row.level,
            subject=row.subject,
            period=row.period,
            at=at,
            admins=admins,
            above=above,
        ),
        stop=Stop(
            level=row.level,
            subject=row.subject,
            period=row.period,
            since=at,
            until=until,
        ),
    )
