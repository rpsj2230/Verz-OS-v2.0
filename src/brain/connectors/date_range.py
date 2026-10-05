"""A date range a person or an agent names, read against a closed grammar and sixteen months.

Google Analytics and Search Console both answer "for a named date range", and on Ask a question
can name only the ranges a question shape carries (yesterday, the last 7, 28 or 90 days). A
workflow such as the monthly SEO report needs any range: last month, since the start of a campaign,
the first of March to the fifteenth. So the Google sources' figure tools take a range as an
argument, and this is the argument: either a `start` and an `end`, or a `period` in a small
grammar, resolved against the day it is asked on into one `DateWindow`, and that window is what the
report is asked for.

**The grammar is closed and has no free text.** A period is `yesterday`, `today`, `last N days`,
`this month`, `last month` or `since YYYY-MM-DD`, in any case and with underscores or spaces, and
nothing else is a period; `start` and `end` are ISO dates. What was typed is checked when the
request is built and never quoted back: every refusal is one of this module's sentences, which name
the rule and not the value. See `A_RANGE_IS_REFUSED_IN_ITS_OWN_WORDS_AND_NEVER_IN_THE_ASKER_S`.

**Sixteen months, and not a day more.** Search Console keeps sixteen months of search data and
says so, and a range reaching further back asks it for data it does not hold. Google Analytics'
reports can reach further, and the same cap is held for both on purpose: a range starting before
the day sixteen calendar months before today is refused in a sentence naming the limit, rather
than sent and answered with a quiet nought by one source and not the other. See
`A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS`. A range ending before it starts, or after today, is refused
the same way.

**Resolved against a day handed in.** `window` takes `today` rather than reading a clock, so a test
of "last month" is not a test that changes answer at midnight on the first.

Rejected: parsing natural language ("the quarter before last", "since the launch"). A parser that
guesses reads a range nobody asked for and answers it confidently; a closed grammar refuses and
says which forms it takes. Rejected: a longer cap for Analytics alone. Two sources with two caps is
a rule a person has to know which source they are asking to follow, and the monthly SEO report
reads both for one range.

Scope: domain logic. Nothing here reads a clock or opens a connection.

Task ids: M11.7.1
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from brain.core.errors import Failed

# ------------------------------------------------------------------ written-down reasons
#: What a range reaching further back than sixteen months is told, and why it is the rule.
A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS: Final = (
    "A range can start no earlier than sixteen months before today, which is as far back as "
    "Google keeps search figures."
)

#: Why a refusal names the rule and never the value.
A_RANGE_IS_REFUSED_IN_ITS_OWN_WORDS_AND_NEVER_IN_THE_ASKER_S: Final = (
    "What was typed as a range may be anything, and a refusal is shown to a person and kept in a "
    "run's record. So a refusal is one of this module's own sentences, naming the rule the range "
    "broke, and never repeats what was typed."
)

#: What a range ending before it starts is told.
A_RANGE_ENDS_ON_OR_AFTER_ITS_START: Final = "A range has to end on or after the day it starts."

#: What a range ending after today is told.
A_RANGE_ENDS_BY_TODAY: Final = "A range has to end by today; there are no figures for later days."

#: What a period outside the grammar is told.
A_PERIOD_IS_ONE_OF_THE_NAMED_FORMS: Final = (
    "Name the range as yesterday, today, last N days, this month, last month or since a date "
    "written as YYYY-MM-DD, or give its first and last day."
)

#: What a request naming both a period and days, or neither, is told.
A_RANGE_IS_NAMED_ONE_WAY: Final = (
    "Name the range either as a period or as a first and last day, not both and not neither."
)

# ------------------------------------------------------------------------ the figures
#: Google's limit, in calendar months back from today.
MONTHS_GOOGLE_KEEPS: Final = 16

#: The longest period text read. Every form of the grammar fits well inside it.
MAX_PERIOD_CHARS: Final = 40

#: The separator a window is written with when it travels as a live read's filter.
WINDOW_SEPARATOR: Final = ".."

_DAY: Final = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
_LAST_N_DAYS: Final = re.compile(r"^last ([1-9][0-9]{0,3}) days?$")
_SINCE: Final = re.compile(rf"^since ({_DAY})$")
_WINDOW: Final = re.compile(rf"^({_DAY})\.\.({_DAY})$")
_NAMED: Final = frozenset({"yesterday", "today", "this month", "last month"})


class RangeRefusedError(Failed):
    """A range this will not ask for. Its public message is one of this module's sentences."""


def _refused(sentence: str) -> RangeRefusedError:
    return RangeRefusedError(sentence, public_message=sentence)


def months_before(day: date, months: int) -> date:
    """The same day of the month `months` calendar months earlier, or that month's last day."""
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    last = (date(year + (month + 1) // 12, (month + 1) % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month + 1, min(day.day, last))


def earliest_start(today: date) -> date:
    """The first day a range may start on. See `A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS`."""
    return months_before(today, MONTHS_GOOGLE_KEEPS)


@dataclass(frozen=True)
class DateWindow:
    """One range of days, first and last included, already held to the rules above."""

    start: date
    end: date

    def text(self) -> str:
        """How the window travels in a live read's filter: `YYYY-MM-DD..YYYY-MM-DD`."""
        return f"{self.start.isoformat()}{WINDOW_SEPARATOR}{self.end.isoformat()}"

    @classmethod
    def parsed(cls, text: str) -> Self:
        """A window written by `text`, or a `ValueError` for anything else."""
        found = _WINDOW.match(text)
        if found is None:
            msg = "not a window this module wrote"
            raise ValueError(msg)
        start, end = date.fromisoformat(found.group(1)), date.fromisoformat(found.group(2))
        if end < start:
            raise ValueError(A_RANGE_ENDS_ON_OR_AFTER_ITS_START)
        return cls(start=start, end=end)


def checked(start: date, end: date, *, today: date) -> DateWindow:
    """A window from these two days, or the refusal naming the rule it broke."""
    if end < start:
        raise _refused(A_RANGE_ENDS_ON_OR_AFTER_ITS_START)
    if end > today:
        raise _refused(A_RANGE_ENDS_BY_TODAY)
    if start < earliest_start(today):
        raise _refused(A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS)
    return DateWindow(start=start, end=end)


def normalised(period: str) -> str:
    """A period as the grammar reads it: lower case, underscores as spaces, one space between."""
    return " ".join(period.replace("_", " ").casefold().split())


def is_a_period(period: str) -> bool:
    """Whether a period is in the grammar at all, before any day is known."""
    text = normalised(period)
    if text in _NAMED or _LAST_N_DAYS.match(text):
        return True
    found = _SINCE.match(text)
    if found is None:
        return False
    try:
        date.fromisoformat(found.group(1))
    except ValueError:
        return False
    return True


def window_of(period: str, *, today: date) -> DateWindow:
    """The window a period names on `today`, or the refusal naming the rule it broke.

    `last N days` ends yesterday, because today's figures are still arriving; `this month` and
    `since` end today.
    """
    text = normalised(period)
    yesterday = today - timedelta(days=1)
    if text == "yesterday":
        return checked(yesterday, yesterday, today=today)
    if text == "today":
        return checked(today, today, today=today)
    if text == "this month":
        return checked(today.replace(day=1), today, today=today)
    if text == "last month":
        end = today.replace(day=1) - timedelta(days=1)
        return checked(end.replace(day=1), end, today=today)
    counted = _LAST_N_DAYS.match(text)
    if counted is not None:
        return checked(today - timedelta(days=int(counted.group(1))), yesterday, today=today)
    since = _SINCE.match(text)
    if since is not None and is_a_period(text):
        return checked(date.fromisoformat(since.group(1)), today, today=today)
    raise _refused(A_PERIOD_IS_ONE_OF_THE_NAMED_FORMS)


class RangeRequest(BaseModel):
    """What a figure tool is asked with: a period in the grammar, or a first and a last day.

    The shape is checked when the request is built, so a period outside the grammar is refused
    before any index is read; the days are checked against today by `window`, which the tool calls
    with the instant it was asked at.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: str | None = Field(default=None, min_length=1, max_length=MAX_PERIOD_CHARS)
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        days = self.start is not None and self.end is not None
        some_days = self.start is not None or self.end is not None
        if (self.period is not None) == some_days or (some_days and not days):
            raise ValueError(A_RANGE_IS_NAMED_ONE_WAY)
        if self.period is not None and not is_a_period(self.period):
            raise ValueError(A_PERIOD_IS_ONE_OF_THE_NAMED_FORMS)
        return self

    def window(self, *, today: date) -> DateWindow:
        """The window asked for, on `today`, or the refusal naming the rule it broke."""
        if self.period is not None:
            return window_of(self.period, today=today)
        assert self.start is not None and self.end is not None  # the validator holds this
        return checked(self.start, self.end, today=today)
