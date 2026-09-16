"""Usage and cost, as one reader may be shown it: who asked, from where, and what is not measured.

`brain.console.usage_view` has decided since M27.4.2 which of the four axes a reader may break
usage down by and which rows the usage grant admits, and it decides both over `UsageRow`, a row
carrying a model and a token count. Measured on 2026-09-16, no ledger on any install holds one.
`ops.spend_actual` is written by nothing: `brain.ops.spend_store.record` has no caller. And
`obs.request_telemetry`, which is written for every request the answer lane finishes, leaves
`tokens_in`, `tokens_out`, `model` and `agent_version` empty on every row, because no model is
called anywhere in this repository and no agent runs on the one live request path;
`brain.ops.telemetry.UNFILLABLE_TODAY` names each of those fields and says why. So the screen
M27.4.2 describes has one real figure behind it today, and this module is where that figure and
the three missing ones are decided for a reader.

**The figure that exists is questions, by person and by department.** `ops.question_asked` holds
one row per question with the asker and the department the directory gave them when they asked,
written where the answer lane finishes. That is the department travelling with the row, which
is `usage_view.THE_DEPARTMENT_TRAVELS_WITH_THE_ROW_AND_IS_NEVER_LOOKED_UP_HERE` satisfied by a
ledger that already exists rather than by a join. No join is made here and none is needed: the
person and the department are both on the question row. See
`QUESTIONS_ARE_THE_ONE_USAGE_FIGURE_A_LEDGER_HOLDS_TODAY`.

**Both tables are drawn from one tuple, and that is the whole of the disclosure argument.**
`brain.adoption.questions_in_reach` chooses the questions once, under the directory's
departments the usage grant admits, with machine traffic removed and the window applied, and the
department lines and the person lines are two groupings of that tuple. So the two tables and the
total above them agree by construction, which is `usage_view.
TWO_TABLES_OF_ONE_ROW_SET_SUBTRACT_INTO_NOTHING` kept on a second row type. `UsageScreen` asserts
it in its constructor, because a renderer that adds the lines up itself is the one that will one
day be handed a list it did not draw all of. See
`THE_PERSON_AND_DEPARTMENT_TABLES_ARE_ONE_POPULATION_GROUPED_TWICE`.

**Whether an axis is offered is `usage_view.may_break_down_by` and nothing written here.** The
person and department axes are read behind the usage grant for the reasons `usage_view` sets
out; an axis a reader may not have is absent rather than empty, and so is the total, which has
nothing under it to reconcile against when neither table is offered.

**A measure no ledger fills is a sentence, never a column of zeros.** Tokens, the model and the
agent are named in `not_measured` when the reader may be offered them and the ledger cannot fill
them, read off `UNFILLABLE_TODAY` rather than written here, so the day a model call fills the
token columns this module stops saying so without anybody editing it. `usage_screen_gaps` then
reports the screen as having nowhere to show the figure, which is the failure that would
otherwise arrive as a screen quietly dropping a sentence. See
`A_MEASURE_NOTHING_FILLS_IS_A_SENTENCE_AND_NEVER_A_ZERO`.

**Cost is the spend screen's, and this screen names it rather than repeating it.**
`brain.console.spend_report_view` reads the materialised report under the same usage grant; a
second copy of those figures here would be a second place for them to drift.

What was rejected.

*Filling `UsageRow` from the question ledger with an empty model.* It would put every question
under one model key that names nothing, and `usage_view.UsageRow` refuses a blank model for
exactly that reason.

*Joining `obs.request_telemetry` to `ops.question_asked` on the trace to carry tokens by
department.* Every token column on that ledger is empty today, so the join would produce figures
that look measured and are None, and choosing how tokens reach a department is a decision that
becomes real on the day a model is called rather than one to take against an empty table.

*A count of automated questions beside the figure.* The design's overview draws one. It is a
count of what was excluded, which `usage_view.COUNTING_NAMES` refuses by name, so the screen says
in words that automation is not counted and says no number.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything; the
rows, the departments and `now` are parameters. Nothing here writes.

The screen this serves does not yet show tokens, a model or an agent, so M27.7.14 is claimed here
for the half it can show and is not closed by it.

Task ids: M27.7.14
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.adoption import Asked, DepartmentAdoption, department_lines, questions_in_reach
from brain.console.adoption_view import reachable_departments
from brain.console.usage_view import Axis, may_break_down_by
from brain.core.entitlement import EntitlementSet
from brain.ops.telemetry import REQUEST_FIELDS, UNFILLABLE_TODAY


class UsageScreenError(Exception):
    """Raised when the usage screen would state a figure its own tables cannot support."""


# ------------------------------------------------------------------ written-down reasons
#: Why questions are the figure this screen shows.
QUESTIONS_ARE_THE_ONE_USAGE_FIGURE_A_LEDGER_HOLDS_TODAY: Final = (
    "The usage screen is asked for questions and tokens by person, department, model and agent. "
    "The question ledger holds the asker and their department for every question the answer "
    "lane finished, and it is written on every install. The token, model and agent columns of "
    "the request ledger are empty on every row because nothing calls a model, and the cost "
    "ledger has no writer at all. So questions by person and by department are shown, and the "
    "rest are named as not measured rather than drawn as zero."
)

#: Why the two tables cannot be told apart by subtraction.
THE_PERSON_AND_DEPARTMENT_TABLES_ARE_ONE_POPULATION_GROUPED_TWICE: Final = (
    "The questions are chosen once, under the departments the usage grant admits, and the "
    "department lines and the person lines are two groupings of that one tuple. A person table "
    "filtered by something other than the department table's filter would make the difference "
    "between their totals a count of questions the reader may not see, with every line on both "
    "tables correct. One tuple makes that difference zero by construction."
)

#: Why a measure nothing fills is named rather than shown.
A_MEASURE_NOTHING_FILLS_IS_A_SENTENCE_AND_NEVER_A_ZERO: Final = (
    "A token column of zeros says nobody used any tokens, which is a figure and a false one. "
    "brain.ops.telemetry already records why each empty field is empty, so this screen reads "
    "that record and says the measure is not taken, and it stops saying so on the day the "
    "ledger fills the field."
)

#: Why automation is not counted and no count of it is shown.
AUTOMATION_IS_REMOVED_BEFORE_ANYTHING_IS_COUNTED: Final = (
    "brain.adoption.questions_in_reach removes machine traces before either table is grouped, "
    "so a nightly schedule never appears as the busiest person in a department. The screen "
    "says so in words and shows no number of what was removed, because a count of excluded "
    "rows beside a filtered figure is the hidden count with a label on it."
)

#: The screen this module is the reader decision for.
SCREEN_KEY: Final = "usage"

#: Whether automated traffic is counted on this screen. It is not, and the route carries this
#: onto the response so the page's sentence is drawn from the answer rather than from its own
#: assumption. See `AUTOMATION_IS_REMOVED_BEFORE_ANYTHING_IS_COUNTED`.
AUTOMATION_IS_COUNTED: Final = False


# ------------------------------------------------------------------------ the measures
class Measure(enum.StrEnum):
    """What the usage screen is asked for that the question ledger cannot supply.

    Three members, one per missing thing in M27.4.2's wording: the token counts, and the model
    and agent axes. Questions are not a member, because questions are measured.
    """

    TOKENS = "tokens"
    MODEL = "model"
    AGENT = "agent"


#: The request ledger fields each measure would be read from. A measure is taken once none of
#: its fields is in `brain.ops.telemetry.UNFILLABLE_TODAY`.
MEASURED_BY: Final[Mapping[Measure, tuple[str, ...]]] = MappingProxyType(
    {
        Measure.TOKENS: ("tokens_in", "tokens_out"),
        Measure.MODEL: ("model",),
        Measure.AGENT: ("agent_version",),
    }
)

#: The axis whose grant each measure would be read behind.
#:
#: Tokens are a figure on every axis rather than an axis of their own, so they are read behind
#: the department axis, which is the usage grant's own vocabulary. The model and the agent are
#: axes and are read behind their own, so a reader who may not learn which agents exist is not
#: told that which agent answered is unmeasured either.
READ_BEHIND: Final[Mapping[Measure, Axis]] = MappingProxyType(
    {
        Measure.TOKENS: Axis.DEPARTMENT,
        Measure.MODEL: Axis.MODEL,
        Measure.AGENT: Axis.AGENT,
    }
)


def not_measured(
    entitlement: EntitlementSet,
    *,
    now: datetime | None = None,
    unfillable: Mapping[str, str] = UNFILLABLE_TODAY,
) -> tuple[Measure, ...]:
    """The measures this reader may be offered that no ledger fills, in `Measure`'s order.

    A measure the reader may not be offered is not named, for the reason
    `usage_view.AN_AXIS_IS_OFFERED_WHOLE_OR_NOT_AT_ALL` gives about an axis: saying that a
    withheld axis is unmeasured still says the axis is there. See
    `A_MEASURE_NOTHING_FILLS_IS_A_SENTENCE_AND_NEVER_A_ZERO`.
    """
    return tuple(
        measure
        for measure in Measure
        if may_break_down_by(READ_BEHIND[measure], entitlement, now=now)
        and any(field in unfillable for field in MEASURED_BY[measure])
    )


# ----------------------------------------------------------------------------- the lines
@dataclass(frozen=True)
class PersonLine:
    """How many questions one person asked in the window.

    A line exists only for somebody who asked, so a zero is refused: a person line with nothing
    on it would name somebody from outside the question ledger, and the only list that could
    have come from is a directory the usage grant does not open.
    """

    person: str
    questions: int

    def __post_init__(self) -> None:
        if not self.person.strip():
            msg = "a person line with no person groups questions under a name nobody has"
            raise UsageScreenError(msg)
        if self.questions < 1:
            msg = f"{self.person} is listed with {self.questions} questions, and asked none"
            raise UsageScreenError(msg)


def person_lines(questions: Sequence[Asked]) -> tuple[PersonLine, ...]:
    """The questions already chosen, grouped by who asked, most first and then by name.

    Takes questions `brain.adoption.questions_in_reach` has chosen and chooses nothing itself,
    which is `THE_PERSON_AND_DEPARTMENT_TABLES_ARE_ONE_POPULATION_GROUPED_TWICE`: a filter here
    would be a second answer to which questions this reader may know about.
    """
    counted: dict[str, int] = {}
    for one in questions:
        counted[one.principal_id] = counted.get(one.principal_id, 0) + 1
    return tuple(
        sorted(
            (PersonLine(person=person, questions=asked) for person, asked in counted.items()),
            key=lambda line: (-line.questions, line.person),
        )
    )


# ---------------------------------------------------------------------------- the screen
@dataclass(frozen=True)
class UsageScreen:
    """Everything the usage screen may show one reader over one window.

    `departments` and `people` are None when the reader may not break usage down that way, and
    `questions` is None when neither is offered: a total with no table under it is a figure
    nobody can reconcile. Where a table is offered its lines sum to `questions`, asserted here,
    so there is no version of this object whose total says more than its lines.
    """

    start: datetime
    end: datetime
    departments: tuple[DepartmentAdoption, ...] | None
    people: tuple[PersonLine, ...] | None
    questions: int | None
    not_measured: tuple[Measure, ...]

    def __post_init__(self) -> None:
        offered = self.departments is not None or self.people is not None
        if offered != (self.questions is not None):
            msg = (
                f"a total of {self.questions} beside tables offered={offered} is either a "
                "figure with nothing under it or tables with no total to reconcile against"
            )
            raise UsageScreenError(msg)
        by_department = (
            None if self.departments is None else sum(one.questions for one in self.departments)
        )
        by_person = None if self.people is None else sum(one.questions for one in self.people)
        for name, shown in (("department", by_department), ("person", by_person)):
            if shown is not None and shown != self.questions:
                msg = (
                    f"the {name} lines sum to {shown} under a total of {self.questions}, so the "
                    "difference is a figure about questions this reader was not shown. "
                    f"{THE_PERSON_AND_DEPARTMENT_TABLES_ARE_ONE_POPULATION_GROUPED_TWICE}"
                )
                raise UsageScreenError(msg)


def usage_for_reader(
    asked: Sequence[Asked],
    departments: Iterable[str],
    entitlement: EntitlementSet,
    *,
    start: datetime,
    end: datetime,
    now: datetime,
) -> UsageScreen:
    """The usage screen for one reader over `[start, end)` (M27.7.14, the questions half).

    `departments` is every department the directory holds, as `adoption_view` takes it, and
    `asked` is every question recorded in the window. The questions are chosen before either
    axis is decided, so a reader offered nothing does the same work and a malformed window is
    refused for everybody alike.
    """
    reachable = reachable_departments(departments, entitlement, now=now)
    chosen = questions_in_reach(asked, reachable, start=start, end=end)
    by_department = (
        department_lines(chosen, reachable)
        if may_break_down_by(Axis.DEPARTMENT, entitlement, now=now)
        else None
    )
    by_person = (
        person_lines(chosen) if may_break_down_by(Axis.PERSON, entitlement, now=now) else None
    )
    offered = by_department is not None or by_person is not None
    return UsageScreen(
        start=start,
        end=end,
        departments=by_department,
        people=by_person,
        questions=len(chosen) if offered else None,
        not_measured=not_measured(entitlement, now=now),
    )


# ------------------------------------------------------------------------------ the gaps
def usage_screen_gaps(
    unfillable: Mapping[str, str] = UNFILLABLE_TODAY,
    measured_by: Mapping[Measure, tuple[str, ...]] = MEASURED_BY,
    read_behind: Mapping[Measure, Axis] = READ_BEHIND,
    ledger_fields: Iterable[str] = REQUEST_FIELDS,
) -> tuple[str, ...]:
    """Everything that would let this screen say something untrue about what is measured.

    Three checks, and the parameters default to this module's own for the reason
    `usage_view.usage_gaps` gives: a diagnostic nobody has watched find something is one
    nobody knows can.
    """
    gaps: list[str] = []
    known = set(ledger_fields)
    for measure in Measure:
        fields = measured_by.get(measure, ())
        if not fields or measure not in read_behind:
            gaps.append(
                f"{measure.value} has no ledger field or no axis declared, so nobody decided "
                "where it would be read from or who may be told it is missing"
            )
            continue
        for field in fields:
            if field not in known:
                gaps.append(
                    f"{measure.value} is read from {field}, which the request ledger does not "
                    "have, so saying it is not measured is a claim about nothing"
                )
        if not any(field in unfillable for field in fields):
            gaps.append(
                f"the request ledger now fills {', '.join(fields)}, so {measure.value} is "
                "measured and this screen has nowhere to show it; it will simply stop saying "
                "the measure is missing"
            )
    return tuple(gaps)
