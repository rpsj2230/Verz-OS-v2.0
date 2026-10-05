"""The range a figure tool is asked with: a closed grammar, sixteen months, and plain refusals.

`brain.connectors.date_range` turns a period or a first and last day into one window against a day
handed in, so every date here is far from any wall clock and nothing changes answer at midnight.

Task ids: M11.7.1
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Final

import pytest
from pydantic import ValidationError

from brain.connectors.date_range import (
    A_PERIOD_IS_ONE_OF_THE_NAMED_FORMS,
    A_RANGE_ENDS_BY_TODAY,
    A_RANGE_ENDS_ON_OR_AFTER_ITS_START,
    A_RANGE_IS_NAMED_ONE_WAY,
    A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS,
    MONTHS_GOOGLE_KEEPS,
    DateWindow,
    RangeRefusedError,
    RangeRequest,
    earliest_start,
    months_before,
)

#: The day every range is asked on. Far from any wall clock, deliberately.
TODAY: Final = date(2999, 3, 15)


def window(**asked: Any) -> DateWindow:
    return RangeRequest(**asked).window(today=TODAY)


@pytest.mark.parametrize(
    ("asked", "start", "end"),
    [
        (
            {"start": date(2999, 1, 1), "end": date(2999, 1, 31)},
            date(2999, 1, 1),
            date(2999, 1, 31),
        ),
        ({"period": "last month"}, date(2999, 2, 1), date(2999, 2, 28)),
        ({"period": "Last_Month"}, date(2999, 2, 1), date(2999, 2, 28)),
        ({"period": "since 2998-12-01"}, date(2998, 12, 1), TODAY),
        ({"period": "yesterday"}, date(2999, 3, 14), date(2999, 3, 14)),
        ({"period": "today"}, TODAY, TODAY),
        ({"period": "this month"}, date(2999, 3, 1), TODAY),
        ({"period": "last 30 days"}, date(2999, 2, 13), date(2999, 3, 14)),
        ({"period": "last_7_days"}, date(2999, 3, 8), date(2999, 3, 14)),
    ],
)
def test_every_form_of_the_grammar_resolves_to_its_days_on_the_day_asked(
    asked: dict[str, Any], start: date, end: date
) -> None:
    """The positive case of every form: a first and last day, last month, since a date, and the
    named periods, each in any case and with underscores, resolved against the day asked.

    Delete this and "last month" could end on the first of this one, or "last 30 days" count
    thirty-one."""
    assert window(**asked) == DateWindow(start=start, end=end)


def test_a_range_may_start_sixteen_months_back_and_not_a_day_further() -> None:
    """`A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS`, at its edge in both directions: sixteen calendar
    months back is the earliest start, and the day before it is refused with the sentence, which
    names the limit and repeats nothing that was asked.

    Delete this and a range Google does not hold could be asked for and answered with noughts."""
    edge = earliest_start(TODAY)
    assert edge == date(2997, 11, 15) == months_before(TODAY, MONTHS_GOOGLE_KEEPS)
    assert window(start=edge, end=TODAY).start == edge
    with pytest.raises(RangeRefusedError) as refused:
        window(start=edge - timedelta(days=1), end=TODAY)
    assert refused.value.public_message == A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS
    assert "sixteen months" in A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS
    assert "2997" not in refused.value.public_message
    with pytest.raises(RangeRefusedError):
        window(period=f"since {(edge - timedelta(days=1)).isoformat()}")


def test_a_range_ending_before_it_starts_is_refused_and_one_day_is_a_range() -> None:
    """`A_RANGE_ENDS_ON_OR_AFTER_ITS_START`, with its sibling: a range of one day is a range.

    Delete this and a reversed range could reach Google, which answers it with an error that reads
    as the source being unwell."""
    with pytest.raises(RangeRefusedError) as refused:
        window(start=date(2999, 2, 2), end=date(2999, 2, 1))
    assert refused.value.public_message == A_RANGE_ENDS_ON_OR_AFTER_ITS_START
    assert window(start=date(2999, 2, 1), end=date(2999, 2, 1)).end == date(2999, 2, 1)


def test_a_range_ending_after_today_is_refused_and_one_ending_today_is_not() -> None:
    """`A_RANGE_ENDS_BY_TODAY`, with its sibling. Delete this and a range into next week reads as
    a week with no traffic."""
    with pytest.raises(RangeRefusedError) as refused:
        window(start=TODAY, end=TODAY + timedelta(days=1))
    assert refused.value.public_message == A_RANGE_ENDS_BY_TODAY
    assert window(start=TODAY, end=TODAY).end == TODAY


@pytest.mark.parametrize(
    "asked",
    [
        {"period": "the quarter before last"},
        {"period": "since the launch"},
        {"period": "since 2999-02-30"},
        {"period": "last 0 days"},
        {"period": "last month; drop table"},
        {"period": "last month", "start": date(2999, 1, 1), "end": date(2999, 1, 2)},
        {"start": date(2999, 1, 1)},
        {},
    ],
)
def test_a_request_outside_the_grammar_is_refused_when_it_is_built(asked: dict[str, Any]) -> None:
    """A period that is not one of the forms, a date that is not a day, and a request naming its
    range two ways or none are refused before any index is read, in this module's own words and
    never the value typed. The positive siblings are every form above.

    Delete this and a free-text range could be guessed at, and the guess answered confidently."""
    with pytest.raises(ValidationError) as refused:
        RangeRequest(**asked)
    words = str(refused.value)
    assert A_PERIOD_IS_ONE_OF_THE_NAMED_FORMS in words or A_RANGE_IS_NAMED_ONE_WAY in words
    assert "drop table" not in A_PERIOD_IS_ONE_OF_THE_NAMED_FORMS


def test_a_window_travels_as_text_this_module_writes_and_reads_nothing_else() -> None:
    """The window is a live read's filter between the tool and the report: written and read back
    exactly, and anything else, including a reversed window, is not a window.

    Delete this and a filter written by hand could reach a report as a range nobody checked."""
    one = DateWindow(start=date(2999, 1, 1), end=date(2999, 1, 31))
    assert one.text() == "2999-01-01..2999-01-31"
    assert DateWindow.parsed(one.text()) == one
    for text in ("2999-01-31..2999-01-01", "2999-01-01", "last month", "2999-01-01..2999-02-30"):
        with pytest.raises(ValueError):
            DateWindow.parsed(text)


def test_sixteen_months_before_a_day_the_month_lacks_is_that_month_s_last_day() -> None:
    """Counting back from the thirty-first lands on a month's last day rather than raising.

    Delete this and a question asked on the last day of a long month fails for everybody."""
    assert months_before(date(2999, 7, 31), 16) == date(2998, 3, 31)
    assert months_before(date(2999, 6, 30), 16) == date(2998, 2, 28)
    assert months_before(date(2999, 1, 15), 13) == date(2997, 12, 15)
