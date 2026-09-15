"""Who may be shown a service level reading, held to the rule that a refusal looks like nothing.

`brain.console.service_level_view` is the reader decision behind the Service levels screen. The
figures in a reading are `brain.ops.service_levels`' and are tested in
`tests/unit/test_service_levels.py`; what is tested here is only what a reader is handed.

Real `EntitlementSet`s and real readings from `against_target` throughout, so no test compares
the module against a reading it built for itself. The store read is exercised through a session
whose every query answers with rows in the shape `observed_between` selects, and which records
any write, so "writes nothing" is an assertion rather than a sentence.

Dates are in 2999, far outside any wall clock, for the reason `CLAUDE.md` gives about fixtures:
the expiry test holds both bounds in the future so a dropped `now` falls back to a real clock
inside the bound and fails rather than passing by accident.

Task ids: M30.5.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from brain.console.screens import screen
from brain.console.service_level_view import (
    READING_ROW,
    SCREEN_KEY,
    SERVICE_LEVEL_AUTHORITY,
    for_reader,
    may_read_service_levels,
    service_levels_for_reader,
)
from brain.console.spend_view import USAGE_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.scope import Clause, Op, Scope
from brain.ops.reliability import LANE_OBJECTIVES
from brain.ops.service_levels import Observation, ServiceLevelError, ServiceLevels, against_target
from brain.ops.telemetry import RequestStatus

START = datetime(2999, 6, 1, tzinfo=UTC)
END = START + timedelta(days=30)
NOW = END + timedelta(hours=1)

#: A bound between two instants both still in the future of any real clock.
BOUND = datetime(2999, 8, 1, tzinfo=UTC)
BEFORE_THE_BOUND = BOUND - timedelta(days=1)
AFTER_THE_BOUND = BOUND + timedelta(days=1)


def a_reader(*grants: Grant, not_after: datetime | None = None) -> EntitlementSet:
    return EntitlementSet(principal_id="u_reader", grants=grants, not_after=not_after)


def usage(scope: Scope) -> Grant:
    return Grant(capability=Capability(value="read:usage"), scope=scope)


def busy() -> list[Observation]:
    """Twenty-five fast requests and three answer ones, one of them failed."""
    fast = [
        Observation(
            lane=Lane.FAST,
            status=RequestStatus.ANSWERED,
            duration_ms=float(one),
            received_at=START + timedelta(minutes=one),
        )
        for one in range(1, 26)
    ]
    answer = [
        Observation(
            lane=Lane.ANSWER,
            status=status,
            duration_ms=900.0,
            received_at=START + timedelta(hours=one),
        )
        for one, status in enumerate(
            (RequestStatus.ANSWERED, RequestStatus.ANSWERED, RequestStatus.FAILED), start=1
        )
    ]
    return [*fast, *answer]


def reading(observations: Sequence[Observation] = ()) -> ServiceLevels:
    return against_target(observations, start=START, end=END)


# ------------------------------------------------------------------------ the capability
def test_a_reading_is_read_under_the_usage_screens_own_capability() -> None:
    """The screen's capability is read off the registry, so this holds it to the usage screen's
    from a second module and to the literal, rather than to itself.

    Delete this and the service level screen can move to a grant of its own, and a reader who
    may not see any department's usage reads the install's request volume off it."""
    assert SCREEN_KEY == "service_levels"
    assert screen(SCREEN_KEY).title == "Service levels"
    assert SERVICE_LEVEL_AUTHORITY == USAGE_AUTHORITY
    assert SERVICE_LEVEL_AUTHORITY.value == "read:usage"


def test_a_reading_offers_a_grants_scope_no_field_to_narrow_on() -> None:
    """The row form a scope is matched against is empty, which is what makes a department-scoped
    grant match nothing and an unrestricted one match the install. A clause that admits any
    value is unrestricted in effect and is admitted too, which is the positive sibling of the
    department refusal written as a scope rather than as no scope.

    Delete this and a field added to the row form lets a department-scoped grant match a
    reading that is every department's traffic."""
    assert dict(READING_ROW) == {}
    anything = Scope(clauses=(Clause(field="department", op=Op.ANY),))

    assert may_read_service_levels(a_reader(usage(anything)), now=NOW) is True
    assert may_read_service_levels(a_reader(usage(Scope.department("support"))), now=NOW) is False


# ------------------------------------------------------------------------ what is shown
def test_a_reader_holding_the_usage_grant_company_wide_is_shown_the_whole_reading() -> None:
    """The positive case, and the one every refusal below is measured against: the reading comes
    back unchanged, figures, lanes and shortfalls included.

    Delete this and a `for_reader` that refuses everybody passes every other test here."""
    levels = reading(busy())
    everybody = a_reader(usage(Scope.unrestricted()))

    shown = for_reader(levels, everybody, now=NOW)

    assert shown == levels
    assert [one.objective.lane for one in shown.lanes] == [Lane.FAST, Lane.ANSWER, Lane.TASK]
    assert shown.lanes[0].requests == 25


def test_a_usage_grant_narrowed_to_a_department_is_shown_nothing_rather_than_the_install() -> None:
    """A reading is a sum over every department. Shown to a reader whose usage grant names one,
    the install's count less their own department's is everybody else's traffic.

    Delete this and a department admin who opens the screen by its address reads the whole
    install's request volume beside their own."""
    levels = reading(busy())
    support = a_reader(usage(Scope.department("support")))

    shown = for_reader(levels, support, now=NOW)

    assert shown.lanes == ()
    assert (shown.start, shown.end) == (START, END)


def test_a_reader_with_no_usage_grant_is_shown_nothing_whatever_else_they_hold() -> None:
    """Nothing held, and a company-wide grant of the nearer-sounding incident capability, are
    both refused. The second is the capability this screen was deliberately not put behind.

    Delete this and a reader holding only operational grants reaches traffic figures."""
    levels = reading(busy())

    assert for_reader(levels, a_reader(), now=NOW).lanes == ()
    incident = Grant(capability=Capability(value="read:incident"), scope=Scope.unrestricted())
    assert for_reader(levels, a_reader(incident), now=NOW).lanes == ()


def test_a_reading_is_refused_once_the_readers_entitlement_has_expired() -> None:
    """The decision is taken at the instant passed in. Both instants are in the future, so a
    `now` dropped anywhere on the way to `scope_for` falls back to a real clock that sits before
    the bound, and the refusal half fails.

    Delete this and a contractor keeps reading the install's traffic after their last day."""
    levels = reading(busy())
    bounded = a_reader(usage(Scope.unrestricted()), not_after=BOUND)

    assert for_reader(levels, bounded, now=BEFORE_THE_BOUND) == levels
    assert for_reader(levels, bounded, now=AFTER_THE_BOUND).lanes == ()


def test_a_refused_reading_is_the_reading_of_an_install_that_promises_nothing() -> None:
    """DENIED and ABSENT, as equal objects. A refused reader of a busy install is handed exactly
    what a permitted reader of an install declaring no objectives is handed over a quiet window,
    and exactly what a refused reader of an idle install is handed. No count, no lane, no
    sentence survives the refusal.

    Delete this and the refused answer can carry a count or a lane, and a department admin
    learns from the difference between two refusals whether anybody else was busy."""
    everybody = a_reader(usage(Scope.unrestricted()))
    support = a_reader(usage(Scope.department("support")))
    promises_nothing = against_target([], start=START, end=END, objectives=())

    refused_busy = for_reader(reading(busy()), support, now=NOW)
    refused_idle = for_reader(reading(), support, now=NOW)
    absent = for_reader(promises_nothing, everybody, now=NOW)

    assert refused_busy == refused_idle == absent


# ------------------------------------------------------------------------ the store read
class _Ledger(AsyncSession):
    """A session whose every query answers with the four columns `observed_between` selects."""

    def __init__(self, observations: Sequence[Observation]) -> None:
        self.rows = [
            (one.lane.value, one.status.value, one.duration_ms, one.received_at)
            for one in observations
        ]
        self.queries = 0
        self.writes: list[str] = []

    async def execute(self, statement: Any, params: Any = None, **_: Any) -> Any:
        self.queries += 1
        return _Answer(self.rows)

    def add(self, instance: Any, _warn: bool = True) -> None:
        self.writes.append("add")

    async def flush(self, objects: Sequence[Any] | None = None) -> None:
        self.writes.append("flush")

    async def commit(self) -> None:
        self.writes.append("commit")


class _Answer:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return self._rows


def test_the_store_read_folds_the_ledger_and_narrows_it_for_the_reader_writing_nothing() -> None:
    """Through `telemetry_store.service_levels_between`, the reading a permitted reader is handed
    is `against_target` over the ledger's rows, and a refused reader over the same ledger is
    handed the empty reading. Neither writes.

    Delete this and the console read can build its reading some other way than the store query
    the ledger was written for, or start writing, and nothing notices."""
    everybody = a_reader(usage(Scope.unrestricted()))
    support = a_reader(usage(Scope.department("support")))

    ledger = _Ledger(busy())
    shown = asyncio.run(service_levels_for_reader(ledger, everybody, start=START, end=END, now=NOW))
    assert shown == reading(busy())

    refused = asyncio.run(service_levels_for_reader(ledger, support, start=START, end=END, now=NOW))
    assert refused.lanes == ()
    assert ledger.writes == []

    # The objectives an install declares reach the fold, rather than being replaced by the
    # defaults on the way through.
    without_task = [one for one in LANE_OBJECTIVES if one.lane is not Lane.TASK]
    trimmed = asyncio.run(
        service_levels_for_reader(
            _Ledger(busy()), everybody, start=START, end=END, now=NOW, objectives=without_task
        )
    )
    assert [one.objective.lane for one in trimmed.lanes] == [Lane.FAST, Lane.ANSWER]


def test_a_refused_read_does_the_same_work_and_fails_the_same_way_as_a_permitted_one() -> None:
    """The store is read for a refused reader too, and a window holding no time is refused for
    them exactly as it is for a permitted one. Deciding first would make the refused reader the
    one whose malformed request succeeds.

    Delete this and the decision can move in front of the query, and a refused read becomes
    recognisable by being the one that never fails."""
    everybody = a_reader(usage(Scope.unrestricted()))
    support = a_reader(usage(Scope.department("support")))

    for who in (everybody, support):
        ledger = _Ledger(busy())
        asyncio.run(service_levels_for_reader(ledger, who, start=START, end=END, now=NOW))
        assert ledger.queries == 1

        with pytest.raises(ServiceLevelError, match="holds no time"):
            asyncio.run(service_levels_for_reader(_Ledger([]), who, start=END, end=START, now=NOW))
