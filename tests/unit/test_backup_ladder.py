"""Which copies a retention ladder keeps, across month, ISO week and year boundaries.

`brain.ops.backup_ladder` decides and never deletes, so every case below is a list of copies and
an instant. The dates are 2018 to 2021 and all UTC. Nothing here is about the present, so the
fixtures are pinned years away from any wall clock this suite will run under, for the reason
`CLAUDE.md` gives about a fixture being a clock. 2020 is a leap year and is inside the range on
purpose.

The central test states what thirty daily, twelve weekly and twelve monthly copies are without
using the module's arithmetic: the last thirty days, the Sunday of each of the last eleven
finished weeks, and the last day of each of the last eleven finished months, plus today. It is
asked for every day across fifteen months, so every month length and two new years are crossed.

M30.3.5 is not claimed here and the leaf is named only to read its sentence: the ladder it asks
for is refused against the horizon every erasure certificate promises, and that refusal is the
first test.

Task ids: none
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from brain.ops.backup_ladder import (
    A_CHAIN_IS_NOT_PRUNED_BY_THE_CALENDAR,
    SELF_CONTAINED,
    Kept,
    Rung,
    Selection,
    count_for,
    period_of,
    select,
)
from brain.ops.recovery import (
    RETENTION_LADDER,
    Backup,
    Coverage,
    Ladder,
    Method,
    RecoveryError,
)
from brain.ops.retention import BACKUP_RETENTION_DAYS
from brain.status import leaf_sentences

REPO = Path(__file__).resolve().parents[2]

#: The horizon a caller has to state before the declared ladder may be selected to at all.
ADOPTED: int = RETENTION_LADDER.horizon_days()

#: When the nightly copy lands, as `ops/backup/brain-backup.timer` schedules it.
COPY_HOUR = 2


def copy(
    at: datetime,
    *,
    coverage: Coverage = Coverage.DATABASE,
    method: Method = Method.FULL,
) -> Backup:
    """One copy consistent to `at`. The identifier carries the instant, so ties are real ties."""
    return Backup(
        backup_id=f"{coverage.value}-{at.astimezone(UTC):%Y%m%dT%H%M%SZ}",
        coverage=coverage,
        method=method,
        destination="s3://copies",
        started_at=at - timedelta(minutes=5),
        finished_at=at,
        recoverable_to=at,
        size_bytes=4096,
    )


def nightly(first: date, last: date, *, every: int = 1) -> list[Backup]:
    """A copy at 02:00 UTC on every `every`th day from `first` to `last` inclusive."""
    days = (last - first).days
    return [
        copy(datetime(one.year, one.month, one.day, COPY_HOUR, tzinfo=UTC))
        for one in (first + timedelta(days=offset) for offset in range(0, days + 1, every))
    ]


def kept_days(selection: Selection) -> set[date]:
    return {one.backup.recoverable_to.date() for one in selection.kept}


def noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)


# ------------------------------------------------------------------ the declared ladder
_WORDS = {"thirty": 30, "twelve": 12}


def test_the_declared_ladder_is_the_one_the_leaf_names() -> None:
    """**The counts are asserted against the leaf sentence, not against themselves.**

    `RETENTION_LADDER` is imported by the module under test, so a test comparing a selection
    against it moves with it. The work breakdown's sentence is written somewhere else by
    somebody else, and it is the only thing that can say thirty rather than thirteen.

    Delete this and a one-word change to the ladder is green everywhere, including in the
    exhaustive test below, which is parameterised by the ladder it would be checking."""
    sentence = leaf_sentences(REPO / "docs" / "wbs.json")["M30.3.5"]
    found = re.fullmatch(r"Retention: (\w+) daily, (\w+) weekly, (\w+) monthly", sentence)

    assert found is not None
    daily, weekly, monthly = (_WORDS[word] for word in found.groups())
    assert Ladder(daily=daily, weekly=weekly, monthly=monthly) == RETENTION_LADDER


def test_the_declared_ladder_is_refused_against_the_horizon_every_certificate_promises() -> None:
    """**The refusal that stops M30.3.5 being adopted, made structural in the one function that
    could adopt it.** Thirty, twelve and twelve keep a copy up to 372 days and a certificate
    promises 35. Selecting with the defaults is the adoption, so the defaults refuse.

    Delete this and a pruner calling `select` with no arguments deletes nothing it should and
    keeps a year of copies every certificate says are gone."""
    copies = nightly(date(2019, 1, 1), date(2019, 3, 1))

    assert RETENTION_LADDER.horizon_days() > BACKUP_RETENTION_DAYS
    with pytest.raises(RecoveryError, match="beyond backup reach"):
        select(copies, now=noon(date(2019, 3, 1)))


def test_the_declared_ladder_selects_once_a_horizon_that_holds_it_is_stated() -> None:
    """The positive sibling. A refusal tested alone is satisfied by a function that refuses
    every ladder, which would also refuse the one a client configured inside the horizon.

    Delete this and `select` can raise unconditionally with the test above still green."""
    copies = nightly(date(2019, 1, 1), date(2019, 3, 1))

    assert select(copies, now=noon(date(2019, 3, 1)), horizon_days=ADOPTED).kept
    assert select(copies, now=noon(date(2019, 3, 1)), ladder=Ladder(7, 4, 1)).kept


# ------------------------------------------------------------------ the exhaustive property
def _expected_under_daily_copies(today: date, ladder: Ladder) -> set[date]:
    """What the ladder keeps with one copy a day, written without periods or `isocalendar`.

    Daily: the last `daily` days. Weekly: today, then the Sunday before today's week and one
    Sunday per week before that. Monthly: today, then the last day of the previous month and of
    each month before it. `date.weekday()` is Monday 0, so today's week began `weekday()` days
    ago and the Sunday before it one day earlier.
    """
    days = {today - timedelta(days=back) for back in range(ladder.daily)}
    sundays = [today] + [
        today - timedelta(days=today.weekday() + 1 + 7 * back) for back in range(ladder.weekly - 1)
    ]
    month_ends = [today]
    first = today.replace(day=1)
    for _ in range(ladder.monthly - 1):
        end = first - timedelta(days=1)
        month_ends.append(end)
        first = end.replace(day=1)
    return days | set(sundays[: ladder.weekly]) | set(month_ends[: ladder.monthly])


def test_with_a_copy_every_night_the_ladder_keeps_the_days_the_sundays_and_the_month_ends() -> None:
    """**Every day from December 2019 to February 2021 is `now` once.** That crosses two new
    years, an ISO week that straddles one, a leap day and every length of month, and each is
    compared against a statement of the ladder that shares no arithmetic with the module.

    It also proves `Ladder.horizon_days` is a real bound rather than a label: the age cap is set
    to exactly that horizon and removes nothing a rung keeps, for every one of those days.

    Delete this and the selection is tested at a handful of dates chosen by the person who
    wrote it, which is how an off-by-one at a month of thirty days ships."""
    copies = nightly(date(2018, 11, 1), date(2021, 2, 28))
    today = date(2019, 12, 1)
    asked = 0
    while today <= date(2021, 2, 28):
        present = [one for one in copies if one.recoverable_to <= noon(today)]
        chosen = select(present, now=noon(today), horizon_days=ADOPTED)

        assert kept_days(chosen) == _expected_under_daily_copies(today, RETENTION_LADDER), today
        asked += 1
        today += timedelta(days=1)
    assert asked == 456


def test_a_ladder_inside_the_horizon_keeps_exactly_what_its_rungs_count_across_new_year() -> None:
    """Worked by hand at 2 January 2020 with seven daily, four weekly and one monthly, which
    fits the 35 days a certificate promises and is selected with the defaults.

    ISO week 1 of 2020 runs from Monday 30 December, so its newest copy is today's. The three
    weeks before end on the 29th, 22nd and 15th of December. The newest copy of January is
    today's too. Delete this and the exhaustive test is the only evidence, and it is written in
    the same afternoon's terms as the module."""
    copies = nightly(date(2019, 11, 1), date(2020, 1, 2))

    chosen = select(copies, now=noon(date(2020, 1, 2)), ladder=Ladder(daily=7, weekly=4, monthly=1))

    assert kept_days(chosen) == {
        date(2019, 12, 15),
        date(2019, 12, 22),
        *(date(2019, 12, day) for day in range(27, 32)),
        date(2020, 1, 1),
        date(2020, 1, 2),
    }
    rungs = {one.backup.recoverable_to.date(): one.rungs for one in chosen.kept}
    assert rungs[date(2019, 12, 29)] == {Rung.DAILY, Rung.WEEKLY}
    assert rungs[date(2020, 1, 2)] == {Rung.DAILY, Rung.WEEKLY, Rung.MONTHLY}
    assert rungs[date(2019, 12, 15)] == {Rung.WEEKLY}


# ------------------------------------------------------------------ periods
def test_the_week_holding_new_year_is_one_week_and_keeps_one_copy() -> None:
    """`A_WEEK_IS_AN_ISO_WEEK`. Monday 31 December 2018 and Sunday 6 January 2019 are the same
    ISO week. A week keyed by calendar year splits it and keeps the 31st as a second weekly copy.

    Delete this and the weekly rung can be keyed by `(year, week)` with nothing objecting until
    a new year's pruning run keeps one copy too many and one week too few."""
    monday = datetime(2018, 12, 31, COPY_HOUR, tzinfo=UTC)
    sunday = datetime(2019, 1, 6, COPY_HOUR, tzinfo=UTC)
    copies = [copy(datetime(2018, 12, 30, COPY_HOUR, tzinfo=UTC)), copy(monday), copy(sunday)]

    assert period_of(monday, Rung.WEEKLY) == period_of(sunday, Rung.WEEKLY) == (2019, 1)
    chosen = select(copies, now=noon(date(2019, 1, 6)), ladder=Ladder(daily=0, weekly=2, monthly=0))
    assert kept_days(chosen) == {date(2018, 12, 30), date(2019, 1, 6)}


def test_a_period_is_taken_in_utc_whatever_offset_the_copy_was_stamped_with() -> None:
    """`A_PERIOD_IS_A_UTC_PERIOD`. Half past midnight on 1 February at +08:00 is 16:30 on 31
    January in UTC, so it shares January with a copy taken at 20:00 UTC that evening, and the
    later of the two is January's.

    Delete this and periods can be read in the stamp's own zone, where the first copy is
    February's, is the newest month, and is kept in place of the copy that is actually newer."""
    stamped = copy(datetime(2019, 2, 1, 0, 30, tzinfo=timezone(timedelta(hours=8))))
    evening = copy(datetime(2019, 1, 31, 20, 0, tzinfo=UTC))

    assert period_of(stamped.recoverable_to, Rung.MONTHLY) == (2019, 1)
    assert period_of(stamped.recoverable_to, Rung.DAILY) == (2019, 1, 31)
    chosen = select(
        [stamped, evening],
        now=datetime(2019, 1, 31, 23, tzinfo=UTC),
        ladder=Ladder(daily=0, weekly=0, monthly=1),
    )
    assert [one.backup for one in chosen.kept] == [evening]
    assert chosen.pruned == (stamped,)


def test_a_ladder_counts_its_rungs_from_the_ladder_itself() -> None:
    """Delete this and `count_for` can hand every rung the daily count, which the declared ladder
    hides because its weekly and monthly counts are equal to each other."""
    ladder = Ladder(daily=3, weekly=5, monthly=7)

    assert [count_for(ladder, rung) for rung in Rung] == [3, 5, 7]


def test_the_newest_copy_in_a_period_is_the_one_kept_and_an_identifier_breaks_a_tie() -> None:
    """Two copies on one day are one daily copy, and it is the one reaching further forward.

    Delete this and a morning run and an afternoon rerun leave whichever the listing returned
    first, which is the older one exactly as often as it is not."""
    morning = copy(datetime(2019, 5, 1, 2, tzinfo=UTC))
    afternoon = copy(datetime(2019, 5, 1, 14, tzinfo=UTC))
    daily = Ladder(daily=1, weekly=0, monthly=0)

    assert [
        one.backup
        for one in select([afternoon, morning], now=noon(date(2019, 5, 2)), ladder=daily).kept
    ] == [afternoon]
    assert [
        one.backup
        for one in select([morning, afternoon], now=noon(date(2019, 5, 2)), ladder=daily).kept
    ] == [afternoon]

    tied = Backup(
        backup_id="database-zz",
        coverage=Coverage.DATABASE,
        method=Method.FULL,
        destination="s3://copies",
        started_at=afternoon.started_at,
        finished_at=afternoon.finished_at,
        recoverable_to=afternoon.recoverable_to,
        size_bytes=1,
    )
    assert [
        one.backup
        for one in select([tied, afternoon], now=noon(date(2019, 5, 2)), ladder=daily).kept
    ] == [tied]
    assert [
        one.backup
        for one in select([afternoon, tied], now=noon(date(2019, 5, 2)), ladder=daily).kept
    ] == [tied]


# ------------------------------------------------------------------ counting and the horizon
def test_an_outage_of_the_taker_does_not_age_out_the_last_good_copies() -> None:
    """`A_LADDER_COUNTS_DAYS_THAT_HOLD_A_COPY_NOT_DAYS_ON_THE_CALENDAR`. The taker stopped on
    31 March and it is 20 April. Thirty daily copies are the thirty last days that have one, not
    the ten of them inside the last thirty calendar days.

    Delete this and the calendar reading passes every test that takes a copy every night, and
    deletes the last good copies during the one fortnight they matter."""
    copies = nightly(date(2019, 1, 1), date(2019, 3, 31))

    chosen = select(copies, now=noon(date(2019, 4, 20)), ladder=Ladder(30, 0, 0), horizon_days=60)

    assert kept_days(chosen) == {date(2019, 3, 31) - timedelta(days=back) for back in range(30)}


def test_no_copy_is_kept_once_it_reaches_the_horizon_whatever_a_rung_counted() -> None:
    """`NO_COPY_IS_KEPT_PAST_THE_HORIZON_WHATEVER_A_RUNG_COUNTED`. Thirty daily copies taken
    every third day reach 87 days back, and a horizon of 60 keeps the twenty younger than 60.

    Delete this and irregular copies are kept past the date a certificate states they are gone."""
    copies = nightly(date(2019, 1, 1), date(2019, 3, 31), every=3)
    now = datetime(2019, 3, 31, COPY_HOUR, tzinfo=UTC)

    counted = select(copies, now=now, ladder=Ladder(30, 0, 0), horizon_days=ADOPTED)
    capped = select(copies, now=now, ladder=Ladder(30, 0, 0), horizon_days=60)

    assert len(counted.kept) == 30
    assert len(capped.kept) == 20
    assert all(now - one.backup.recoverable_to < timedelta(days=60) for one in capped.kept)


def test_a_copy_exactly_the_horizon_old_is_not_kept_and_one_a_second_younger_is() -> None:
    """The boundary, in the direction a certificate reads it: on the horizon the copy is gone.

    Delete this and `<` can become `<=`, which keeps a copy for one instant on the date a
    certificate says it is beyond reach, and rounds a legal claim the wrong way."""
    now = datetime(2019, 6, 1, COPY_HOUR, tzinfo=UTC)
    on = copy(now - timedelta(days=BACKUP_RETENTION_DAYS))
    inside = copy(now - timedelta(days=BACKUP_RETENTION_DAYS) + timedelta(seconds=1))

    fits = Ladder(daily=BACKUP_RETENTION_DAYS, weekly=0, monthly=0)

    # Two selections rather than one, because both copies fall in the same period of every rung
    # and a single selection would keep the younger whether or not the cap were there.
    assert select([on], now=now, ladder=fits).pruned == (on,)
    assert [one.backup for one in select([inside], now=now, ladder=fits).kept] == [inside]


def test_each_coverage_is_laddered_on_its_own() -> None:
    """A database dump and an object store snapshot from one day are two copies of two things.

    Delete this and the coverages can share periods, so the snapshot taken a minute after the
    dump is the day's only kept copy and the database has none."""
    at = datetime(2019, 7, 1, COPY_HOUR, tzinfo=UTC)
    dump = copy(at)
    snapshot = copy(
        at + timedelta(minutes=1), coverage=Coverage.OBJECT_STORE, method=Method.SNAPSHOT
    )

    chosen = select([dump, snapshot], now=noon(date(2019, 7, 1)), ladder=Ladder(1, 0, 0))

    assert [one.backup for one in chosen.kept] == [dump, snapshot]


# ------------------------------------------------------------------ refusals
def test_a_chained_copy_is_refused_rather_than_selected_by_date() -> None:
    """`A_CHAIN_IS_NOT_PRUNED_BY_THE_CALENDAR`. Delete this and a ladder deletes the full under
    twelve kept incrementals, which go on being listed as kept and restore nothing."""
    at = datetime(2019, 8, 1, COPY_HOUR, tzinfo=UTC)
    for method in (Method.INCREMENTAL, Method.CONTINUOUS_WAL):
        with pytest.raises(RecoveryError, match="nothing a copy records names that base"):
            select([copy(at, method=method)], now=noon(date(2019, 8, 1)), ladder=Ladder(1, 0, 0))
    assert "base" in A_CHAIN_IS_NOT_PRUNED_BY_THE_CALENDAR


def test_the_copies_a_ladder_may_select_include_what_the_nightly_taker_writes() -> None:
    """**`SELF_CONTAINED` against something outside itself: the taker's own manifest.** The
    nightly script writes one method, and a ladder that refused it would refuse every copy this
    product takes.

    Delete this and `FULL` can leave the set with the refusal test above still green, because
    that test only asks about the chained methods."""
    taker = (REPO / "ops" / "backup" / "brain-backup").read_text(encoding="utf-8")
    written = re.findall(r'"method": "([a-z_]+)"', taker)

    assert written == ["full"]
    assert {Method(one) for one in written} <= SELF_CONTAINED
    assert Method.SNAPSHOT in SELF_CONTAINED
    assert not {Method.INCREMENTAL, Method.CONTINUOUS_WAL} & SELF_CONTAINED


def test_a_copy_from_the_future_a_naive_now_and_one_identifier_twice_are_refused() -> None:
    """Three selections that would delete the wrong thing and report success. Delete this and a
    clock disagreement gives a copy a negative age that no horizon removes, and a listing that
    returns an object twice has the duplicate pruned by the identifier the kept one shares."""
    at = datetime(2019, 9, 1, COPY_HOUR, tzinfo=UTC)
    daily = Ladder(1, 0, 0)

    with pytest.raises(RecoveryError, match="has not happened"):
        select([copy(at)], now=at - timedelta(seconds=1), ladder=daily)
    with pytest.raises(RecoveryError, match="naive"):
        select([copy(at)], now=datetime(2019, 9, 2), ladder=daily)
    with pytest.raises(RecoveryError, match="naive"):
        period_of(datetime(2019, 9, 2), Rung.DAILY)
    with pytest.raises(RecoveryError, match="twice"):
        select([copy(at), copy(at)], now=noon(date(2019, 9, 1)), ladder=daily)
    assert select([copy(at)], now=at, ladder=daily).kept


def test_a_copy_kept_by_no_rung_is_refused() -> None:
    """Delete this and a `Kept` with no rungs can be constructed, which a report renders as kept
    for no reason and a reader believes."""
    one = copy(datetime(2019, 9, 1, COPY_HOUR, tzinfo=UTC))

    with pytest.raises(RecoveryError, match="kept by no rung"):
        Kept(backup=one, rungs=frozenset())
    assert Kept(backup=one, rungs=frozenset({Rung.DAILY})).rungs


# ------------------------------------------------------------------ properties over any cadence
_START = datetime(2019, 1, 1, tzinfo=UTC)

_irregular = st.lists(
    st.integers(min_value=0, max_value=800 * 24 * 60),
    min_size=1,
    max_size=120,
    unique=True,
).map(lambda minutes: [copy(_START + timedelta(minutes=one)) for one in minutes])

_ladders = st.builds(
    Ladder,
    daily=st.integers(min_value=0, max_value=40),
    weekly=st.integers(min_value=0, max_value=14),
    monthly=st.integers(min_value=1, max_value=13),
)


@settings(max_examples=300, deadline=None)
@given(copies=_irregular, ladder=_ladders, extra_hours=st.integers(min_value=0, max_value=2000))
def test_any_selection_partitions_its_copies_is_stable_and_keeps_the_newest_young_copy(
    copies: list[Backup], ladder: Ladder, extra_hours: int
) -> None:
    """Four properties for any cadence, any ladder and any instant after the last copy.

    Every copy is kept or pruned and never both. Selecting again from what was kept keeps all of
    it, so a nightly pruner does not erode the ladder one run at a time. The newest copy is kept
    unless it has reached the horizon. And no rung keeps more copies than it counts.

    Delete this and the hand-picked cases above are the only evidence about cadences nobody
    thought to write, which is every cadence a taker produces when it misses a night."""
    now = max(one.recoverable_to for one in copies) + timedelta(hours=extra_hours)
    horizon = ladder.horizon_days() + 30
    chosen = select(copies, now=now, ladder=ladder, horizon_days=horizon)

    kept = [one.backup for one in chosen.kept]
    assert sorted(one.backup_id for one in [*kept, *chosen.pruned]) == sorted(
        one.backup_id for one in copies
    )
    assert not {one.backup_id for one in kept} & {one.backup_id for one in chosen.pruned}

    again = select(kept, now=now, ladder=ladder, horizon_days=horizon)
    assert [one.backup for one in again.kept] == kept
    assert again.pruned == ()

    newest = max(copies, key=lambda one: (one.recoverable_to, one.backup_id))
    if now - newest.recoverable_to < timedelta(days=horizon):
        assert newest in kept
    for rung in Rung:
        assert sum(rung in one.rungs for one in chosen.kept) <= count_for(ladder, rung)


@settings(max_examples=150, deadline=None)
@given(copies=_irregular, ladder=_ladders)
def test_a_longer_ladder_keeps_everything_a_shorter_one_kept(
    copies: list[Backup], ladder: Ladder
) -> None:
    """Lengthening a rung never prunes a copy. Delete this and a change to the ladder can drop a
    copy it should have added to, which is a deletion made by somebody asking to keep more."""
    now = max(one.recoverable_to for one in copies)
    longer = Ladder(ladder.daily + 1, ladder.weekly + 1, ladder.monthly + 1)
    horizon = longer.horizon_days()

    shorter_kept = {
        one.backup.backup_id
        for one in select(copies, now=now, ladder=ladder, horizon_days=horizon).kept
    }
    longer_kept = {
        one.backup.backup_id
        for one in select(copies, now=now, ladder=longer, horizon_days=horizon).kept
    }

    assert shorter_kept <= longer_kept
