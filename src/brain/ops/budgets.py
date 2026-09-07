"""Who may spend how much, written as rows nobody edits.

`brain.ops.limits` answers "may this caller ask again yet". This answers the question that
arrives beside it and has a different remedy. A caller over a rate limit waits a few seconds
and is then served; a caller over a budget waits until somebody decides to fund them. Telling
an operator the wrong one of those sends them to the wrong system, so the two are separate
modules with separate refusals, exactly as capacity and quota are separate in
`brain.ops.admission`.

Six things are load-bearing.

**A budget row is superseded, never edited.** Every row carries a version, an author and the
instant it takes effect, and the only sanctioned way to change one is `superseded_by`, which
returns a new row at the next version and refuses an effective time that is not strictly
later. The cheaper design is a mutable row with an `updated_at`, and what it loses is the
only question anybody ever asks after an overspend: what was the ceiling at the time. A
column that has been overwritten cannot answer it, and the audit log then has to carry the
whole history of a table that already had somewhere to put it. See
`A_BUDGET_ROW_IS_SUPERSEDED_NEVER_EDITED`.

**An alert threshold is not a ceiling, and a ceiling is always hard.** There is no soft
ceiling here and no field that could become one: a budget either admits the spend or it does
not. What a soft ceiling would have been is an alert fraction, which fires strictly before
the refusal and changes nothing about it. Fractions at or above 1.0 are refused for that
reason: an alert that fires at the moment of the refusal has told nobody anything they were
not about to find out. See `AN_ALERT_IS_NOT_A_CEILING`.

**A department's share cannot silently borrow from another's.** `admits` is a conjunction
over the allowances handed to it, so another department's headroom sitting in the same list
cannot help; the only thing that raises a department's ceiling is `apply_transfers`, which
names both sides, an author and a reason, and writes a new version of both rows. There is no
implicit overflow and, more usefully, there is nowhere to put one: no function here takes the
company's remaining headroom and hands it to a department. See
`NO_IMPLICIT_OVERFLOW_BETWEEN_DEPARTMENTS`.

**Both of a person's allowances apply, always.** The daily one catches a loop today. The
monthly one catches the steady overspend that no single day would ever look wrong for, and
which is the more common shape by far. Neither subsumes the other, and the arithmetic keeps
it that way: spending the daily allowance every day of the month overruns the monthly one
several times over, so the monthly ceiling still binds. This is `limits.BOTH_LIMITS_APPLY`
in the money dimension and it is checked rather than assumed. See `BOTH_ALLOWANCES_APPLY`.

**An agent's ceiling only narrows.** An agent is a lens, never a principal, and that is the
repository's one invariant. In the money dimension it means an agent's per-run and per-day
ceilings are added to the caller's allowances rather than substituted for them, so a run
costs the caller's budget as well as the agent's. This is not a second implementation of
`intersect`: entitlements are sets and these are integers, and the intersection here is that
`admits` is an `all`. See `AN_AGENT_CEILING_ONLY_NARROWS`.

**When two budgets are equally short, the wider one is named.** Raising a person's allowance
while their department's is exhausted changes nothing, and somebody sent to their department
head who is then refused again has been sent to the wrong place twice. So the tie is broken
towards the budget whose relief is a precondition for the others. See
`THE_WIDEST_OF_TWO_EXHAUSTED_BUDGETS_IS_THE_ONE_NAMED`.

Nothing here opens a connection and nothing here persists anything. **The persistence half is
unbuilt**: there is no table, no migration and no store, so a `BudgetHistory` is a sequence
somebody else kept, exactly as `limits.LimiterState` is. Said plainly because "versioned,
audited rows" reads as a table, and what is here is the shape a table would have to hold.
`brain.ops.spend` is the enforcement half and holds no rows.

Task ids: M21.1.1, M21.1.2, M21.1.3, M21.1.4, M21.1.5
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

# ------------------------------------------------------------------ written-down reasons
#: Why money is counted in whole minor units and never in a float.
MONEY_IS_COUNTED_IN_MINOR_UNITS = (
    "Every figure here is an integer count of the currency's minor unit, and there is no "
    "float anywhere a total can accumulate in. A budget is a running sum over thousands of "
    "small charges, which is the one arithmetic shape binary floating point is worst at: "
    "the error is invisible per charge and unbounded over a month, and the first symptom is "
    "a department reported at 99.9997% of a ceiling it has actually crossed. Rounding "
    "happens once, on the way in, and it rounds up."
)

#: Why a row is replaced rather than updated.
A_BUDGET_ROW_IS_SUPERSEDED_NEVER_EDITED = (
    "A ceiling that is overwritten cannot answer the only question anybody asks after an "
    "overspend, which is what the ceiling was at the time. So every row carries a version, "
    "an author and an effective-from instant, `superseded_by` is the only sanctioned way to "
    "change one, and it refuses an effective time that is not strictly later than the row it "
    "replaces. Two rows claiming the same version is a history that cannot be ordered, and "
    "`BudgetHistory` refuses one."
)

#: Why there is no soft ceiling, only alerts strictly below a hard one.
AN_ALERT_IS_NOT_A_CEILING = (
    "A ceiling either admits the spend or it does not, and there is no field here that could "
    "become a soft one. What a soft ceiling would have been is an alert fraction: it fires "
    "strictly before the refusal and changes nothing about it. A fraction at or above 1.0 is "
    "refused, because an alert that fires at the instant of the refusal tells nobody "
    "anything they were not about to be told anyway, while looking in the console exactly "
    "like an early warning that is working."
)

#: Why a department cannot draw on another department's unspent budget.
NO_IMPLICIT_OVERFLOW_BETWEEN_DEPARTMENTS = (
    "`admits` is a conjunction, so another department's headroom in the same list cannot "
    "raise this one's, and no function here takes the company's remaining budget and hands "
    "it to a department. The only thing that moves a ceiling is `apply_transfers`, which "
    "names the source, the destination, an author and a reason, and writes a new version of "
    "both rows. Implicit overflow is the feature everybody asks for in month one: it makes "
    "the shared budget invisible again, so the department that spends first spends "
    "everybody's, and nothing anywhere records that it happened."
)

#: Why a person has two allowances rather than one.
BOTH_ALLOWANCES_APPLY = (
    "The daily allowance catches a loop today. The monthly one catches the steady overspend "
    "that no single day looks wrong for, which is much the more common shape. Neither "
    "subsumes the other and the arithmetic keeps it that way: spending the daily allowance "
    "every day of a month overruns the monthly one several times over, so the monthly "
    "ceiling still binds on the last week. This is `limits.BOTH_LIMITS_APPLY` in the money "
    "dimension."
)

#: Why an agent's ceiling is added to the caller's rather than substituted for it.
AN_AGENT_CEILING_ONLY_NARROWS = (
    "An agent is a lens, never a principal. Its per-run and per-day ceilings are appended to "
    "the caller's allowances, so a run spends the caller's budget as well as the agent's and "
    "cannot spend more than either. Substituting the agent's ceiling for the caller's is the "
    "shape that makes an agent a way round a budget, which is the money spelling of the one "
    "invariant this repository has. There is no second implementation of `intersect` here: "
    "entitlements are sets and these are integers, and the intersection is that `admits` is "
    "an `all`."
)

#: Why the wider of two equally exhausted budgets is the one reported.
THE_WIDEST_OF_TWO_EXHAUSTED_BUDGETS_IS_THE_ONE_NAMED = (
    "Raising somebody's own allowance while their department's is exhausted changes nothing, "
    "and a person sent to their department head who is then refused again has been sent to "
    "the wrong place twice. So a tie is broken towards the budget whose relief is a "
    "precondition for every narrower one. The non-tied case is unaffected: the tightest "
    "allowance is the one that actually bound, whatever level it sits at."
)


class BudgetError(Exception):
    """A budget row, an allocation or a transfer that cannot mean what it says.

    An authoring-time failure, like `department.DepartmentError`, and deliberately not part
    of the `brain.core.errors` taxonomy: those five outcomes describe an answer to somebody,
    and this describes a refusal to write a row. What a person is told when a budget binds is
    `brain.ops.spend.Refusal`, which carries no figure.
    """


# --------------------------------------------------------------------------- the levels
class BudgetLevel(enum.StrEnum):
    """Whose money is being counted.

    Four levels rather than one number per principal, because the four fail differently. The
    company's is the only one that cannot be relieved from inside the system. A department's
    is a share of it. A person's is a share of a department's. An agent's is a ceiling on a
    tool, which narrows whoever runs it and belongs to nobody.
    """

    COMPANY = "company"
    DEPARTMENT = "department"
    USER = "user"
    AGENT = "agent"


class BudgetPeriod(enum.StrEnum):
    """The window a ceiling covers.

    `RUN` is the odd one and it is the reason this is not a number of seconds. A per-run
    ceiling does not roll: waiting does not refill it, so the degradation ladder in
    `brain.ops.spend` must not offer a queue against one. A duration in seconds could not
    express that difference without a sentinel.
    """

    RUN = "run"
    DAY = "day"
    MONTH = "month"


#: How wide each level is, smallest number widest. Exhaustive over `BudgetLevel` by test.
#:
#: Written as data rather than derived from the enum's declaration order, so that reordering
#: the enum cannot silently reorder the tie-break. See
#: `THE_WIDEST_OF_TWO_EXHAUSTED_BUDGETS_IS_THE_ONE_NAMED`.
LEVEL_BREADTH: Mapping[BudgetLevel, int] = MappingProxyType(
    {
        BudgetLevel.COMPANY: 0,
        BudgetLevel.DEPARTMENT: 1,
        BudgetLevel.USER: 2,
        BudgetLevel.AGENT: 3,
    }
)

#: A row is addressed by its level, its subject and the period it covers. The period is part
#: of the key because one subject legitimately has several: a person is a day *and* a month,
#: an agent is a run *and* a day, and both of each bind.
BudgetKey = tuple[BudgetLevel, str, BudgetPeriod]


# ------------------------------------------------------------------------------- the row
@dataclass(frozen=True)
class BudgetRow:
    """One ceiling: whose, how much, over what window, written by whom and from when.

    Frozen, and frozen is not the whole of the rule: `dataclasses.replace` would happily
    hand back a second row at the same version, which is a history that cannot be ordered.
    `superseded_by` is the sanctioned edit and `BudgetHistory` refuses the duplicate.
    """

    level: BudgetLevel
    subject: str
    period: BudgetPeriod
    ceiling_minor: int
    version: int
    author: str
    effective_from: datetime
    reason: str = ""
    #: Fractions of the ceiling at which somebody is told, strictly increasing and strictly
    #: below 1.0. See `AN_ALERT_IS_NOT_A_CEILING`.
    alert_fractions: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.subject:
            msg = f"a {self.level} budget needs a subject; an unkeyed row counts everybody"
            raise BudgetError(msg)
        if self.ceiling_minor < 1:
            # Zero is how somebody switches a principal off by editing a number, and it
            # reads in the console as a funded budget rather than as a suspension. The same
            # argument `limits.Limit` makes about a limit of zero, and the same remedy:
            # suspending somebody is a different change and belongs where it can be seen.
            msg = (
                f"budget {self.level}:{self.subject} is {self.ceiling_minor}; a ceiling of "
                "nothing is a suspension wearing a budget's clothes, and the minimum is 1"
            )
            raise BudgetError(msg)
        if self.version < 1:
            msg = f"budget {self.level}:{self.subject} has version {self.version}; rows start at 1"
            raise BudgetError(msg)
        if not self.author:
            msg = (
                f"budget {self.level}:{self.subject} has no author; an unattributed row is "
                "not an audited row"
            )
            raise BudgetError(msg)
        if self.effective_from.tzinfo is None:
            msg = (
                f"budget {self.level}:{self.subject} takes effect at a naive instant, which "
                "compares wrongly against an aware one"
            )
            raise BudgetError(msg)
        self._check_alerts()

    def _check_alerts(self) -> None:
        previous = 0.0
        for fraction in self.alert_fractions:
            if not 0.0 < fraction < 1.0:
                msg = (
                    f"alert fraction {fraction} on {self.level}:{self.subject} is outside "
                    "(0, 1); at or above the ceiling it fires when the refusal does, which "
                    "is not a warning"
                )
                raise BudgetError(msg)
            if fraction <= previous:
                msg = (
                    f"alert fractions on {self.level}:{self.subject} are not strictly "
                    "increasing; a repeated threshold fires twice for one crossing"
                )
                raise BudgetError(msg)
            previous = fraction

    @property
    def key(self) -> BudgetKey:
        return (self.level, self.subject, self.period)

    def superseded_by(
        self,
        *,
        ceiling_minor: int,
        author: str,
        effective_from: datetime,
        reason: str = "",
        alert_fractions: tuple[float, ...] | None = None,
    ) -> BudgetRow:
        """The next version of this row. The only sanctioned way to change a ceiling.

        Refuses an effective time that is not strictly after this row's, because two rows
        effective at the same instant leave `in_force_at` picking one by list order, and the
        order a list happens to be in is not a fact about what the ceiling was.
        """
        if effective_from <= self.effective_from:
            msg = (
                f"a new version of {self.level}:{self.subject} must take effect strictly "
                f"after {self.effective_from.isoformat()}; two rows at one instant cannot "
                "be ordered"
            )
            raise BudgetError(msg)
        return BudgetRow(
            level=self.level,
            subject=self.subject,
            period=self.period,
            ceiling_minor=ceiling_minor,
            version=self.version + 1,
            author=author,
            effective_from=effective_from,
            reason=reason,
            alert_fractions=(self.alert_fractions if alert_fractions is None else alert_fractions),
        )

    def headroom_minor(self, spent_minor: int) -> int:
        """What is left. Never negative: an overspent budget has no room, not negative room."""
        if spent_minor < 0:
            msg = "spend is a total and cannot be negative"
            raise BudgetError(msg)
        return max(0, self.ceiling_minor - spent_minor)

    def alerts_crossed(self, spent_minor: int) -> tuple[float, ...]:
        """Every alert fraction this spend has reached. Empty is the ordinary answer."""
        if spent_minor < 0:
            msg = "spend is a total and cannot be negative"
            raise BudgetError(msg)
        return tuple(f for f in self.alert_fractions if spent_minor >= self.ceiling_minor * f)


@dataclass(frozen=True)
class BudgetHistory:
    """Every version of one ceiling, oldest first. The audited half of M21.1.5.

    A sequence somebody else kept, exactly as `limits.LimiterState` is: there is no table
    behind this and no store, and saying so is more useful than a `save` method that does
    not exist. What it does own is the ordering rules, which are the part a table's columns
    cannot express.
    """

    rows: tuple[BudgetRow, ...]

    def __post_init__(self) -> None:
        if not self.rows:
            msg = "a budget history with no rows is not a budget; it is an absent one"
            raise BudgetError(msg)
        first = self.rows[0]
        for row in self.rows:
            if row.key != first.key:
                msg = (
                    f"a history holds one ceiling; {row.key} is not {first.key}, and two "
                    "subjects in one history make 'the row in force' ambiguous"
                )
                raise BudgetError(msg)
        for earlier, later in zip(self.rows, self.rows[1:], strict=False):
            if later.version <= earlier.version:
                msg = (
                    f"{first.level}:{first.subject} has version {later.version} after "
                    f"{earlier.version}; versions only go forwards"
                )
                raise BudgetError(msg)
            if later.effective_from <= earlier.effective_from:
                msg = (
                    f"{first.level}:{first.subject} version {later.version} takes effect no "
                    "later than the version before it, so the history cannot be ordered"
                )
                raise BudgetError(msg)

    @property
    def key(self) -> BudgetKey:
        return self.rows[0].key

    def in_force_at(self, at: datetime) -> BudgetRow | None:
        """The row that governed at that instant, or None when none did yet.

        **None is not an unlimited budget**, and it is not the first row either. Returning
        the earliest row for an instant before it took effect back-dates a ceiling that
        nobody had agreed to yet, which is how a spend from last quarter gets judged against
        this quarter's number. The caller decides what an absent row means; there is nothing
        here that can decide it for them, in the same way `department.CrossDepartmentPlan`
        gives the empty case a value of its own type rather than one that means everything.
        """
        if at.tzinfo is None:
            msg = "a naive instant compares wrongly against an aware effective-from"
            raise BudgetError(msg)
        governing: BudgetRow | None = None
        for row in self.rows:
            if row.effective_from <= at:
                governing = row
        return governing


# ------------------------------------------------------------------------- what is left
@dataclass(frozen=True)
class Allowance:
    """One ceiling and what has already gone against it.

    The pair rather than a bare number, because a refusal has to name which budget bound and
    a number cannot. Spend arrives from outside: nothing here counts anything, for the reason
    `limits` gives about a limiter that owns its own counters.
    """

    row: BudgetRow
    spent_minor: int = 0

    def __post_init__(self) -> None:
        if self.spent_minor < 0:
            msg = f"spend against {self.row.level}:{self.row.subject} cannot be negative"
            raise BudgetError(msg)

    @property
    def headroom_minor(self) -> int:
        return self.row.headroom_minor(self.spent_minor)

    @property
    def alerts(self) -> tuple[float, ...]:
        return self.row.alerts_crossed(self.spent_minor)


def admits(allowances: Sequence[Allowance], cost_minor: int) -> bool:
    """Whether every allowance has room for this. All of them, never any of them.

    The conjunction is the whole of `NO_IMPLICIT_OVERFLOW_BETWEEN_DEPARTMENTS` and of
    `AN_AGENT_CEILING_ONLY_NARROWS`: adding an allowance to the list can only ever reduce
    what is admitted, so another department's headroom sitting in the same sequence does
    nothing, and an agent's ceiling narrows its caller rather than replacing them.

    An empty sequence admits, which is unlimited by configuration and is the same answer
    `limits.check` gives to an empty limit list. It is the honest reading of "no budget row
    exists" and it is why `BudgetHistory.in_force_at` refuses to invent one.
    """
    if cost_minor < 0:
        msg = "a cost cannot be negative"
        raise BudgetError(msg)
    return all(allowance.headroom_minor >= cost_minor for allowance in allowances)


def tightest(allowances: Sequence[Allowance], cost_minor: int) -> Allowance | None:
    """The allowance that bound, or None when none did.

    Least headroom first, because that is the one that actually stopped the request. Ties go
    to the widest level: see `THE_WIDEST_OF_TWO_EXHAUSTED_BUDGETS_IS_THE_ONE_NAMED`. The
    final tie-break is the subject and period, so that two runs of the same request name the
    same budget and an operator comparing two refusals is comparing two facts.
    """
    over = [one for one in allowances if one.headroom_minor < cost_minor]
    if not over:
        return None
    return min(
        over,
        key=lambda one: (
            one.headroom_minor,
            LEVEL_BREADTH[one.row.level],
            one.row.subject,
            str(one.row.period),
        ),
    )


def narrowed_by_agent(
    caller: Sequence[Allowance], agent: Sequence[Allowance]
) -> tuple[Allowance, ...]:
    """The allowances a run is judged against: the caller's, plus the agent's ceilings.

    Concatenation, and concatenation is the intersection here because `admits` is an `all`.
    Written as a named function rather than left to the call site so that the alternative,
    which is passing the agent's allowances *instead of* the caller's, has to be spelled out
    by somebody rather than reached by dropping an argument. See `AN_AGENT_CEILING_ONLY_NARROWS`.
    """
    return (*caller, *agent)


# ---------------------------------------------------------------- the company ceiling
#: What a company budget warns at by default: three quarters, then nine tenths. Two rather
#: than one, because a single threshold gives whoever reads it no sense of the rate: 75%
#: on the tenth of the month and 75% on the twenty-eighth are the same alert and completely
#: different situations, and the second alert is what separates them. Both are strictly
#: below the ceiling by construction, which `BudgetRow` refuses to let anybody change.
DEFAULT_ALERT_FRACTIONS: tuple[float, ...] = (0.75, 0.9)


def company_budget(
    *,
    company_id: str,
    ceiling_minor: int,
    author: str,
    effective_from: datetime,
    period: BudgetPeriod = BudgetPeriod.MONTH,
    alert_fractions: tuple[float, ...] = DEFAULT_ALERT_FRACTIONS,
    reason: str = "",
) -> BudgetRow:
    """The company's hard ceiling and the fractions it warns at (M21.1.1).

    A ceiling rather than a target: nothing below it is refused and nothing above it is
    admitted. There is no per-run exception and no override flag, because an override on the
    one budget that cannot be relieved from inside the system is a budget that does not
    exist.
    """
    return BudgetRow(
        level=BudgetLevel.COMPANY,
        subject=company_id,
        period=period,
        ceiling_minor=ceiling_minor,
        version=1,
        author=author,
        effective_from=effective_from,
        reason=reason or "the company's hard ceiling for the period",
        alert_fractions=alert_fractions,
    )


# ------------------------------------------------------------- departments and transfers
@dataclass(frozen=True)
class DepartmentShare:
    """One department's share of the company ceiling, as a fraction.

    A fraction rather than an amount, so that raising the company budget raises every
    department's in the same proportion without anybody editing eight rows and getting one
    of them wrong. The amount is derived once, at `allocate`, and from then on it is an
    ordinary versioned row: a department's ceiling does not silently follow the company's
    afterwards, because a share that tracks would move a ceiling with no author and no
    effective-from, which is exactly the edit-in-place this module refuses.
    """

    department: str
    share: float

    def __post_init__(self) -> None:
        if not self.department:
            msg = "a share belongs to a named department"
            raise BudgetError(msg)
        if not 0.0 < self.share <= 1.0:
            msg = (
                f"{self.department} has a share of {self.share}, which is outside (0, 1]; a "
                "share of nothing is a department that cannot ask a question"
            )
            raise BudgetError(msg)


#: Floating-point slack allowed when the declared shares are summed. Shares are written by
#: people as decimals, and 0.3 + 0.3 + 0.4 is 1.0000000000000002 in binary floating point,
#: so an exact comparison refuses an allocation that is correct. The slack is a millionth of
#: the company budget, which is far below one minor unit at any budget anybody would set.
SHARE_SUM_SLACK = 1e-6


def allocate(
    company: BudgetRow,
    shares: Sequence[DepartmentShare],
    *,
    author: str,
    effective_from: datetime,
) -> tuple[BudgetRow, ...]:
    """Department ceilings from the company's, one row each (M21.1.2).

    The shares must sum to at most one. Above one, the departments together may spend more
    than the company ceiling, which is implicit overflow written in the allocation instead of
    at the point of spending, and it is harder to see there: every individual row looks
    reasonable and the total is nowhere on the page.

    Under one is allowed and is the useful case. What is left is the company's own reserve,
    which is the pool a transfer can be funded from without taking it off a department, and a
    company running at exactly 1.0 has no answer to a mid-quarter request except taking from
    somebody.

    Amounts round down, so the parts never exceed the whole. A share that rounds to nothing
    is refused rather than clamped to one unit: a department funded a penny is configuration
    that reads as funded and behaves as suspended.
    """
    if not shares:
        msg = "an allocation over no departments is not an allocation"
        raise BudgetError(msg)
    seen: set[str] = set()
    for share in shares:
        if share.department in seen:
            msg = f"{share.department} appears twice in one allocation"
            raise BudgetError(msg)
        seen.add(share.department)

    total = math.fsum(share.share for share in shares)
    if total > 1.0 + SHARE_SUM_SLACK:
        msg = (
            f"the declared shares total {total:.4f} of {company.subject}'s budget; above 1.0 "
            "the departments together may spend more than the company ceiling, which is "
            "implicit overflow written into the allocation"
        )
        raise BudgetError(msg)

    rows: list[BudgetRow] = []
    for share in shares:
        amount = math.floor(company.ceiling_minor * share.share)
        if amount < 1:
            msg = (
                f"{share.department}'s share of {company.subject} rounds to nothing; a "
                "department funded with less than one unit reads as funded and behaves as "
                "suspended"
            )
            raise BudgetError(msg)
        rows.append(
            BudgetRow(
                level=BudgetLevel.DEPARTMENT,
                subject=share.department,
                period=company.period,
                ceiling_minor=amount,
                version=1,
                author=author,
                effective_from=effective_from,
                reason=(
                    f"{share.share:.0%} of {company.subject}'s {company.period} budget, "
                    "allocated at version 1 and moved only by a recorded transfer"
                ),
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class Transfer:
    """Money moved from one department's ceiling to another's, on the record.

    Both sides are named, an author signs it and a reason is required, because the question
    asked about a transfer three months later is never how much: it is who agreed and why.
    A transfer with an optional reason is a transfer with no reason, on the afternoon it
    matters.
    """

    from_department: str
    to_department: str
    amount_minor: int
    author: str
    at: datetime
    reason: str

    def __post_init__(self) -> None:
        if self.from_department == self.to_department:
            msg = (
                f"{self.from_department} cannot transfer to itself; a transfer with one side "
                "is an edit to a ceiling with a transfer's paperwork on it"
            )
            raise BudgetError(msg)
        if not self.from_department or not self.to_department:
            msg = "a transfer names both departments; one side is not a transfer"
            raise BudgetError(msg)
        if self.amount_minor < 1:
            msg = f"a transfer of {self.amount_minor} moves nothing"
            raise BudgetError(msg)
        if not self.author:
            msg = "a transfer with no author cannot be reviewed by anybody"
            raise BudgetError(msg)
        if not self.reason:
            msg = "a transfer with no reason is the one nobody can explain three months later"
            raise BudgetError(msg)
        if self.at.tzinfo is None:
            msg = "a naive transfer instant compares wrongly against an aware effective-from"
            raise BudgetError(msg)


def apply_transfers(
    rows: Sequence[BudgetRow], transfers: Sequence[Transfer]
) -> tuple[BudgetRow, ...]:
    """Apply recorded transfers, producing the next version of both sides (M21.1.2).

    The total is conserved: whatever leaves one ceiling arrives at another, so the sum over
    the departments is the same before and after. That is what makes this a transfer rather
    than a raise, and it is the property a test pins, because the obvious slip is to credit
    the destination and forget the debit, which reads as generosity and is an overspend.

    A transfer that would take the source below one unit is refused. Draining a department to
    zero suspends it, and a suspension has an author, an announcement and a different form;
    it is not something a budget move should be able to do as a side effect.

    Nothing here knows what has been spent, so a transfer can leave a department below its
    own spend to date. That is honest rather than hidden: the row is the agreement, the
    overspend is then visible in the next report, and a function that silently declined the
    move would leave two people believing different things about the same agreement.
    """
    current = {row.key: row for row in rows}
    if len(current) != len(rows):
        msg = "two rows for one ceiling were passed in; a transfer needs one current version"
        raise BudgetError(msg)

    for transfer in transfers:
        source = _department_row(current, transfer.from_department)
        destination = _department_row(current, transfer.to_department)
        remaining = source.ceiling_minor - transfer.amount_minor
        if remaining < 1:
            msg = (
                f"{transfer.from_department} cannot give up {transfer.amount_minor} of "
                f"{source.ceiling_minor}; that suspends it, and a suspension is a different "
                "change with a different author"
            )
            raise BudgetError(msg)
        note = (
            f"transfer of {transfer.amount_minor} between {transfer.from_department} and "
            f"{transfer.to_department}, authorised by {transfer.author}: {transfer.reason}"
        )
        current[source.key] = source.superseded_by(
            ceiling_minor=remaining,
            author=transfer.author,
            effective_from=transfer.at,
            reason=note,
        )
        current[destination.key] = destination.superseded_by(
            ceiling_minor=destination.ceiling_minor + transfer.amount_minor,
            author=transfer.author,
            effective_from=transfer.at,
            reason=note,
        )
    return tuple(current.values())


def _department_row(current: Mapping[BudgetKey, BudgetRow], department: str) -> BudgetRow:
    for key, row in current.items():
        if key[0] is BudgetLevel.DEPARTMENT and key[1] == department:
            return row
    msg = (
        f"{department} has no budget row in this allocation, so there is nothing to move; "
        "a transfer cannot create a department's budget out of another's"
    )
    raise BudgetError(msg)


# ------------------------------------------------------------------ a person's allowance
#: The most of a department's budget any one person may hold. A quarter, for the reason
#: `limits.PRINCIPAL_FAIR_SHARE` is a quarter: it takes four heavy callers to exhaust a
#: department rather than one, and a backfill started by one person leaves three quarters for
#: everybody's questions. Must stay strictly below 1.0, and strictly below it even for a
#: department of one, because a department's budget also funds its agents and its
#: automations, and a sole member who can spend all of it leaves those unfunded with nothing
#: reporting why. An invariant test pins that.
USER_FAIR_SHARE = 0.25

#: How many times the even split a person is allowed. An even split is the obvious rule and
#: it is wrong in the direction that costs the most: most people ask nothing most months, so
#: an even split leaves the department's budget unspent while the three people doing the work
#: are refused. Three times the even split funds the working third properly and still leaves
#: the fair-share cap binding above nine people, which is where the cap starts to matter.
ALLOWANCE_GENEROSITY = 3.0

#: Days a monthly budget is divided over. Thirty, not the actual length of the month: a
#: person's daily allowance changing between February and March is a support question every
#: February and buys nothing, because the monthly ceiling is what actually binds.
DAYS_IN_BUDGET_MONTH = 30

#: How much of a month's allowance one day may take, as a multiple of an even thirtieth.
#: Work is bursty and a person who spends four ordinary days' worth on the day a report is
#: due is working, not looping. Must stay strictly above 1.0, or an ordinary busy day is
#: refused, and strictly below `DAYS_IN_BUDGET_MONTH`, or a loop can spend the month before
#: lunch and the daily allowance has stopped catching the thing it exists for.
DAILY_BURST = 4.0


def user_allowances(
    department: BudgetRow,
    *,
    principal_id: str,
    headcount: int,
    author: str,
    effective_from: datetime,
) -> tuple[BudgetRow, BudgetRow]:
    """One person's daily and monthly allowance, capped at a fair share (M21.1.3).

    Returned as a pair and always both, because a caller that can ask for one of them is a
    caller that will eventually check only that one. See `BOTH_ALLOWANCES_APPLY`.

    The monthly figure is the more generous of nothing and a multiple of the even split,
    clamped to `USER_FAIR_SHARE` of the department. The daily figure is a burst multiple of
    an even thirtieth of that, which is deliberately far above a thirtieth and deliberately
    far below the whole: the daily allowance is there to catch a loop within the day, and the
    monthly one is what catches a person who is simply spending too much.
    """
    if department.level is not BudgetLevel.DEPARTMENT:
        msg = f"a person's allowance is a share of a department, not of {department.level}"
        raise BudgetError(msg)
    if department.period is not BudgetPeriod.MONTH:
        msg = (
            f"{department.subject}'s budget is per {department.period}; a monthly allowance "
            "cannot be derived from it without pretending the periods are the same"
        )
        raise BudgetError(msg)
    if headcount < 1:
        msg = "a department with no members has nobody to give an allowance to"
        raise BudgetError(msg)

    fair_cap = math.floor(department.ceiling_minor * USER_FAIR_SHARE)
    if fair_cap < 1:
        msg = (
            f"{department.subject}'s budget of {department.ceiling_minor} cannot be shared; "
            "one person's fair share rounds to nothing, so any allowance at all would be the "
            "whole department's budget"
        )
        raise BudgetError(msg)

    even_split = math.floor(department.ceiling_minor * ALLOWANCE_GENEROSITY / headcount)
    monthly_minor = max(1, min(even_split, fair_cap))
    daily_minor = max(1, math.floor(monthly_minor * DAILY_BURST / DAYS_IN_BUDGET_MONTH))

    monthly = BudgetRow(
        level=BudgetLevel.USER,
        subject=principal_id,
        period=BudgetPeriod.MONTH,
        ceiling_minor=monthly_minor,
        version=1,
        author=author,
        effective_from=effective_from,
        reason=(
            f"{ALLOWANCE_GENEROSITY:.0f}x an even split across {headcount}, capped at "
            f"{USER_FAIR_SHARE:.0%} of {department.subject}"
        ),
    )
    daily = BudgetRow(
        level=BudgetLevel.USER,
        subject=principal_id,
        period=BudgetPeriod.DAY,
        ceiling_minor=daily_minor,
        version=1,
        author=author,
        effective_from=effective_from,
        reason=(
            f"{DAILY_BURST:.0f}x an even day of the monthly allowance, so a busy day is "
            "ordinary and a loop is not"
        ),
    )
    return (daily, monthly)


# --------------------------------------------------------------------- an agent's ceiling
def agent_ceilings(
    *,
    agent_id: str,
    per_run_minor: int,
    per_day_minor: int,
    author: str,
    effective_from: datetime,
) -> tuple[BudgetRow, BudgetRow]:
    """An agent's per-run and per-day ceilings (M21.1.4).

    A run ceiling above the day ceiling is refused, because it can never bind: the day
    ceiling would stop the run first, and a configured number that cannot have an effect is
    the kind of setting somebody later reads as protection they do not have.

    Both ceilings narrow whoever runs the agent and neither replaces them. See
    `AN_AGENT_CEILING_ONLY_NARROWS`.
    """
    if per_run_minor > per_day_minor:
        msg = (
            f"{agent_id} may spend {per_run_minor} in one run and {per_day_minor} in a day; "
            "the run ceiling can never bind, so it is protection nobody has"
        )
        raise BudgetError(msg)
    per_run = BudgetRow(
        level=BudgetLevel.AGENT,
        subject=agent_id,
        period=BudgetPeriod.RUN,
        ceiling_minor=per_run_minor,
        version=1,
        author=author,
        effective_from=effective_from,
        reason="the most one run of this agent may cost, whoever called it",
    )
    per_day = BudgetRow(
        level=BudgetLevel.AGENT,
        subject=agent_id,
        period=BudgetPeriod.DAY,
        ceiling_minor=per_day_minor,
        version=1,
        author=author,
        effective_from=effective_from,
        reason="everything this agent may cost in a day, across everybody using it",
    )
    return (per_run, per_day)


def level_gaps() -> tuple[str, ...]:
    """Every budget level with no breadth, and every breadth for a level that does not exist.

    The same construction `memory.tiers.tier_gaps` uses. A level missing from `LEVEL_BREADTH`
    would raise on the tie-break at the moment two budgets are equally exhausted, which is
    the worst moment for a lookup to fail, and it would pass every test that never produced a
    tie.
    """
    declared = set(BudgetLevel)
    gaps: list[str] = []
    for missing in sorted(one.value for one in declared - set(LEVEL_BREADTH)):
        gaps.append(f"{missing} has no breadth, so a tie between two budgets cannot be broken")
    for extra in sorted(one.value for one in set(LEVEL_BREADTH) - declared):
        gaps.append(f"{extra} has a breadth and is not a budget level")
    if len(set(LEVEL_BREADTH.values())) != len(LEVEL_BREADTH):
        gaps.append("two budget levels share a breadth, so the tie-break is decided by nothing")
    return tuple(gaps)
