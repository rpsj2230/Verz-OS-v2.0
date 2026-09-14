"""The materialised spend report: the same figures as the unmaterialised one, at the same reach.

Two halves. Without a server: the fold from view rows to a report narrows by the reader's grant,
refuses to call an unbuilt view a report of nothing, and puts the age of its figures on the
object. With one: `0034` to `0036` are run for real in a database this file creates, and the
view is compared against `spend_view.spend_report` over the same recorded runs for every
dimension and several readers, which is the only test that can catch the SQL copy of
`Actual.key_for` drifting from the Python one.

The security claim is tested from both sides: a reader scoped to one department is shown that
department's figures and no others, including for a key that also appears in another
department, and the table's read policy that the argument rests on is read back from the server.

Task ids: M36.1.3.1, M36.1.3.2
"""

from __future__ import annotations

import importlib.util
import types
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.console.spend_report_view import (
    REFRESH_EVERY,
    REPORT_HORIZON,
    STALE_AFTER,
    VIEW_GRAIN,
    MaterialisedReport,
    SpendDay,
    SpendReportViewError,
    freshness_of,
    spend_report_from_view,
    view_gaps,
)
from brain.console.spend_view import spend_report
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.gate.provenance import Freshness, StalenessHorizon, StatedFreshness
from brain.ops.controls import MISSED_RUN_GRACE
from brain.ops.spend import NO_AGENT, Actual, Dimension
from brain.ops.spend_store import (
    read_spend_daily,
    record,
    recorded,
    refresh_spend_daily,
    spend_actual_read_policies,
)
from tests.fixtures.scratch_postgres import (
    drop,
    engine,
    fresh,
    migrate,
    modelled,
    run,
    secured,
    shape,
    sql,
)

#: Far outside any plausible wall clock. The report is not about the present.
NOW = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)
DAY = NOW.date()
USAGE = Capability(value="read:usage")

WEB = "web"
HR = "hr"

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


@contextmanager
def built(database: str, head: str) -> Iterator[str]:
    """A fresh database with `0034` onwards run for real, dropped afterwards.

    `tests.fixtures.scratch_postgres.built` stamps at `0029` and runs everything after it, and
    `0033` replaces a function `0028` and `0029` install, so it cannot run there. The stamp is
    moved to `0033` here: none of the three migrations under test points at anything `0026` to
    `0033` built, and `0025` is run first because every database this fixture makes has it.
    """
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0024")
        migrate(database, "upgrade", "0025")
        migrate(database, "stamp", "0033")
        migrate(database, "upgrade", head)
        yield scratch
    finally:
        drop(database)


def migration_module_at(path: Path) -> types.ModuleType:
    """Import a migration as a module. Runs nothing: `upgrade` and `downgrade` are functions."""
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def a_reader(*departments: str) -> EntitlementSet:
    """Somebody holding the usage grant over these departments, or over none."""
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(Grant(capability=USAGE, scope=Scope.department(one)) for one in departments),
    )


def everybody() -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_admin", grants=(Grant(capability=USAGE, scope=Scope.unrestricted()),)
    )


def a_day(
    *,
    department: str,
    cost: int,
    key: str = "big",
    dimension: Dimension = Dimension.MODEL,
    day: date = DAY,
    kind: PrincipalKind = PrincipalKind.HUMAN,
    traffic: TrafficClass = TrafficClass.HUMAN_INTERACTIVE,
) -> SpendDay:
    return SpendDay(
        day=day,
        department=department,
        principal_kind=kind,
        traffic=traffic,
        dimension=dimension,
        key=key,
        cost_minor=cost,
    )


FRESH = NOW - timedelta(hours=3)


# ------------------------------------------------------------------- without a server
def test_a_reader_scoped_to_one_department_is_shown_only_that_departments_figures() -> None:
    """One key spent in two departments. The web reader sees web's part of it and nothing of
    hr's, in the line and in the total; the company-wide reader sees both.

    Delete this and the fold could skip `may_read_spend`, handing every reader the company's
    figure for every key, with every other test in this file still green."""
    days = (a_day(department=WEB, cost=100), a_day(department=HR, cost=900))

    web = spend_report_from_view(days, FRESH, a_reader(WEB), Dimension.MODEL, now=NOW).report
    whole = spend_report_from_view(days, FRESH, everybody(), Dimension.MODEL, now=NOW).report

    assert web is not None and whole is not None
    assert [(one.key, one.cost_minor) for one in web.lines] == [("big", 100)]
    assert web.total_minor == 100
    assert [(one.key, one.cost_minor) for one in whole.lines] == [("big", 1000)]


def test_a_reader_with_no_usage_grant_is_shown_an_empty_report_and_not_a_refusal() -> None:
    """The DENIED and ABSENT rule: a reader who may see nothing gets a report with no lines,
    exactly what a company with no spend would produce.

    Delete this and a refusal naming the usage capability could come back instead, telling the
    reader a spend report exists and is being kept from them."""
    days = (a_day(department=WEB, cost=100),)
    found = spend_report_from_view(days, FRESH, a_reader(), Dimension.MODEL, now=NOW)

    assert found.report is not None
    assert found.report.lines == ()
    assert found.report.total_minor == 0


def test_a_view_nobody_has_refreshed_has_no_report_rather_than_a_report_of_nothing() -> None:
    """No refresh recorded: no report, no instant, and a freshness the provenance scale calls
    unstated, which renders as "read time not stated".

    Delete this and an unbuilt view renders as a company that spent nothing, which is a figure
    and a false one."""
    found = spend_report_from_view((), None, everybody(), Dimension.MODEL, now=NOW)

    assert found == MaterialisedReport(
        report=None, as_of=None, freshness=StatedFreshness(state=Freshness.UNSTATED)
    )
    assert found.freshness.render() == "read time not stated"


def test_the_age_of_the_figures_is_graded_on_the_provenance_scale_at_the_refresh_schedule() -> None:
    """Three hours old and exactly one refresh interval old are live, a second past it is ageing,
    exactly the grace is still ageing, and a second past the grace is stale. The report carries
    the provenance type and renders in provenance's words with the instant beside them.

    Delete this and the report's grade could be computed against a horizon nobody derived, or on
    a scale of its own that calls the same spend overdue while an answer calls it ageing."""
    fresh = spend_report_from_view((), FRESH, everybody(), Dimension.MODEL, now=NOW)
    assert fresh.as_of == FRESH
    assert fresh.freshness == StatedFreshness(state=Freshness.LIVE, fetched_at=FRESH.isoformat())
    assert fresh.freshness.render() == f"current, read {FRESH.isoformat()}"

    second = timedelta(seconds=1)
    assert freshness_of(NOW - REFRESH_EVERY, NOW).state is Freshness.LIVE
    assert freshness_of(NOW - REFRESH_EVERY - second, NOW).state is Freshness.AGEING
    assert freshness_of(NOW - STALE_AFTER, NOW).state is Freshness.AGEING
    assert freshness_of(NOW - STALE_AFTER - second, NOW).state is Freshness.STALE


def test_the_horizon_is_the_refresh_interval_and_the_controls_grace_over_it() -> None:
    """Asserted against another module's figure and a relation, not against itself: live for one
    refresh interval, stale after `MISSED_RUN_GRACE` of them, which is more than one, and the
    interval is the grain.

    Delete this and a refresh cadence could be tuned without its horizon following it, or the
    stale threshold dropped to one interval, which leaves no ageing band and grades a report
    that is a few minutes late as stale."""
    assert (
        StalenessHorizon(live_for=REFRESH_EVERY, stale_after=REFRESH_EVERY * MISSED_RUN_GRACE)
        == REPORT_HORIZON
    )
    assert STALE_AFTER > REFRESH_EVERY
    assert REFRESH_EVERY == VIEW_GRAIN == timedelta(days=1)


def test_a_refresh_recorded_after_the_reading_instant_is_unstated_and_never_live() -> None:
    """The figures are shown and their freshness is unstated, as provenance grades a read time
    from the future.

    Delete this and a clock disagreement between the database and the reader could grade the
    report live, which is the one staleness error that misleads."""
    ahead = NOW + timedelta(minutes=1)
    found = spend_report_from_view((), ahead, everybody(), Dimension.MODEL, now=NOW)

    assert found.report is not None
    assert found.freshness.state is Freshness.UNSTATED


def test_automated_traffic_is_excluded_by_default_through_the_same_lookup_as_a_run() -> None:
    """A human principal on automation traffic is a machine, as `is_automated` says, and is
    excluded unless asked for.

    Delete this and the view's rows could be judged by principal kind alone, putting a nightly
    report run under somebody's name back into the people's figures."""
    days = (
        a_day(department=WEB, cost=5, key="human"),
        a_day(department=WEB, cost=50, key="nightly", traffic=TrafficClass.AUTOMATION),
    )
    people = spend_report_from_view(days, FRESH, everybody(), Dimension.MODEL, now=NOW).report
    all_of = spend_report_from_view(
        days, FRESH, everybody(), Dimension.MODEL, now=NOW, include_machine=True
    ).report

    assert people is not None and all_of is not None
    assert [one.key for one in people.lines] == ["human"]
    assert people.machine_included is False
    assert [one.key for one in all_of.lines] == ["nightly", "human"]


def test_a_window_takes_its_first_day_and_not_its_last() -> None:
    """Inclusive since, exclusive until; a window that ends before it starts is refused.

    Delete this and a month's report could count the first of the next month, or an inverted
    window could come back empty and read as no spend."""
    days = (
        a_day(department=WEB, cost=1, day=DAY - timedelta(days=1), key="before"),
        a_day(department=WEB, cost=2, day=DAY, key="first"),
        a_day(department=WEB, cost=4, day=DAY + timedelta(days=1), key="last"),
    )
    found = spend_report_from_view(
        days,
        FRESH,
        everybody(),
        Dimension.MODEL,
        now=NOW,
        since=DAY,
        until=DAY + timedelta(days=1),
    ).report
    assert found is not None
    assert [one.key for one in found.lines] == ["first"]
    with pytest.raises(SpendReportViewError, match="holds no day"):
        spend_report_from_view(
            days, FRESH, everybody(), Dimension.MODEL, now=NOW, since=DAY, until=DAY
        )


def test_only_the_asked_dimension_is_summed() -> None:
    """Every run appears once per dimension in the view, so summing two dimensions doubles it.

    Delete this and the dimension filter could be dropped, and every total would be five times
    what was spent."""
    days = (
        a_day(department=WEB, cost=7, key="big", dimension=Dimension.MODEL),
        a_day(department=WEB, cost=7, key=WEB, dimension=Dimension.DEPARTMENT),
    )
    found = spend_report_from_view(days, FRESH, everybody(), Dimension.MODEL, now=NOW).report
    assert found is not None
    assert found.total_minor == 7


def test_a_report_its_instant_and_its_grade_cannot_be_built_apart() -> None:
    """An instant with no report is refused, and so is an unbuilt report graded live.

    Delete this and a renderer could be handed figures with no instant beside them, or an unbuilt
    report labelled current."""
    live = StatedFreshness(state=Freshness.LIVE, fetched_at=NOW.isoformat())
    with pytest.raises(SpendReportViewError, match="present together"):
        MaterialisedReport(report=None, as_of=NOW, freshness=live)
    with pytest.raises(SpendReportViewError, match="only honest grade is unstated"):
        MaterialisedReport(report=None, as_of=None, freshness=live)


def test_the_view_is_reported_wider_than_its_table_when_the_table_narrows() -> None:
    """`true` passes; a department predicate, or no read policy at all, is a finding.

    Delete this and a narrower policy on `ops.spend_actual` would leave the materialised view as
    the way round it, with nothing saying so."""
    assert view_gaps(("true",)) == ()
    narrowed = view_gaps(("true", "(department = current_setting('app.department'))"))
    assert len(narrowed) == 1 and "narrower than every row" in narrowed[0]
    assert "no read policy" in view_gaps(())[0]


def test_the_views_sql_keys_are_the_dimensions_actual_groups_by() -> None:
    """The one copy the migration makes of `Actual.key_for`: one entry per `Dimension`, the
    empty-agent key spelled as `NO_AGENT`, and each expression present in the view it builds.

    Delete this and a sixth dimension, or a renamed empty-agent bucket, leaves the view grouping
    by yesterday's vocabulary while the unmaterialised report uses today's."""
    migration = migration_module_at(VERSIONS / "0035_materialised_spend_report.py")
    keys = dict(migration.DIMENSION_KEYS)

    assert set(keys) == {one.value for one in Dimension}
    assert f"'{NO_AGENT}'" in keys["agent"]
    squashed = " ".join(migration.CREATE_VIEW.split())
    for name, expression in migration.DIMENSION_KEYS:
        assert f"('{name}', {expression})" in squashed


def test_a_summed_row_or_an_instant_that_cannot_be_read_is_refused_at_construction() -> None:
    """A row with no key and a negative cost are refused; a naive refresh instant grades as
    unstated and a naive reading instant is refused, both by provenance's own rules.

    Delete this and a summed row keyed by nothing would total into a line no reader can be
    admitted to, and a naive instant would make every age wrong by the host's offset."""
    with pytest.raises(SpendReportViewError, match="no department or no key"):
        a_day(department=WEB, cost=1, key=" ")
    with pytest.raises(SpendReportViewError, match="less than nothing"):
        a_day(department=WEB, cost=-1)
    assert freshness_of(datetime(2999, 1, 1), NOW).state is Freshness.UNSTATED
    with pytest.raises(ValueError, match="timezone-aware"):
        freshness_of(FRESH, datetime(2999, 1, 1))


# ------------------------------------------------------------------------ with a server
def a_run(
    *,
    department: str,
    cost: int,
    principal: str = "u_asker",
    agent: str | None = "a_helper",
    model: str = "big",
    lane: Lane = Lane.ANSWER,
    kind: PrincipalKind = PrincipalKind.HUMAN,
    traffic: TrafficClass = TrafficClass.HUMAN_INTERACTIVE,
    at: datetime = NOW,
) -> Actual:
    return Actual(
        principal_id=principal,
        principal_kind=kind,
        traffic=traffic,
        department=department,
        agent_id=agent,
        model=model,
        lane=lane,
        cost_minor=cost,
        at=at,
    )


#: Runs chosen so every dimension has a key shared across departments, an empty agent, and a
#: machine row, and so two runs either side of midnight UTC land on different days.
RUNS: tuple[Actual, ...] = (
    a_run(department=WEB, cost=100, principal="u_both", model="big"),
    a_run(department=HR, cost=900, principal="u_both", model="big"),
    a_run(department=WEB, cost=30, agent=None, model="small", lane=Lane.FAST),
    a_run(department=HR, cost=7, agent=None, model="small", lane=Lane.TASK),
    a_run(
        department=WEB,
        cost=5000,
        principal="svc_sync",
        kind=PrincipalKind.SERVICE,
        traffic=TrafficClass.SYSTEM,
    ),
    a_run(department=WEB, cost=11, at=datetime(2999, 6, 14, 23, 59, 59, tzinfo=UTC)),
    a_run(department=WEB, cost=13, at=datetime(2999, 6, 15, 0, 0, 1, tzinfo=UTC)),
)


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    with built("brain_spend_report_view_check", "0036") as url:
        run(lambda: _record_all(url, RUNS))
        yield url


async def _record_all(url: str, runs: Sequence[Actual]) -> None:
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session, session.begin():
            for one in runs:
                await record(session, one)
    finally:
        await made.dispose()


async def _refresh(url: str) -> datetime:
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session, session.begin():
            return await refresh_spend_daily(session)
    finally:
        await made.dispose()


async def _read(url: str) -> tuple[datetime | None, tuple[SpendDay, ...], tuple[Actual, ...]]:
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session:
            freshness, days = await read_spend_daily(session)
            return freshness, days, await recorded(session)
    finally:
        await made.dispose()


async def _policies(url: str) -> tuple[str | None, ...]:
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session:
            return await spend_actual_read_policies(session)
    finally:
        await made.dispose()


def test_the_view_gives_the_figures_the_unmaterialised_report_gives_for_every_reader(
    server: str,
) -> None:
    """Every dimension, with and without machine traffic, for a web reader, an hr reader, both,
    nobody and the whole company: the report from the view equals `spend_report` over the
    recorded runs, line for line and total for total.

    Delete this and the SQL grouping could drift from `Actual.key_for`, or lose the department
    from its key, and every test above would still pass because none of them runs the SQL."""
    run(lambda: _refresh(server))
    freshness, days, actuals = run(lambda: _read(server))
    assert len(actuals) == len(RUNS)

    readers = (a_reader(WEB), a_reader(HR), a_reader(WEB, HR), a_reader(), everybody())
    for reader in readers:
        for dimension in Dimension:
            for machine in (False, True):
                expected = spend_report(
                    actuals, reader, dimension, now=NOW, include_machine=machine
                )
                found = spend_report_from_view(
                    days, freshness, reader, dimension, now=NOW, include_machine=machine
                )
                assert found.report == expected, (reader.principal_id, dimension, machine)


def test_a_web_reader_cannot_learn_hrs_figures_through_the_view(server: str) -> None:
    """The view holds hr's rows, because a materialised view carries no row-level security, and
    the web reader's report still carries none of hr's cost in any dimension, including the
    person and the model both departments share.

    Delete this and the view's security argument has no test on a real server."""
    run(lambda: _refresh(server))
    freshness, days, _ = run(lambda: _read(server))
    assert any(one.department == HR for one in days)

    web_spend = sum(one.cost_minor for one in RUNS if one.department == WEB and not one.machine)
    for dimension in Dimension:
        found = spend_report_from_view(days, freshness, a_reader(WEB), dimension, now=NOW)
        assert found.report is not None
        assert found.report.total_minor == web_spend, dimension
    by_person = spend_report_from_view(days, freshness, a_reader(WEB), Dimension.PRINCIPAL, now=NOW)
    assert by_person.report is not None
    assert {one.key: one.cost_minor for one in by_person.report.lines}["u_both"] == 100


def test_a_refresh_brings_in_what_was_recorded_since_and_moves_the_instant(server: str) -> None:
    """Record a run after a refresh: the view does not have it and its instant has not moved.
    Refresh again: it has it, and the instant is later.

    Delete this and a refresh that rebuilt nothing, or rebuilt without writing its timestamp,
    would pass every test that only refreshes once."""
    first = run(lambda: _refresh(server))
    before, days_before, _ = run(lambda: _read(server))
    run(lambda: _record_all(server, (a_run(department=WEB, cost=1, model="late"),)))

    unchanged, days_unchanged, _ = run(lambda: _read(server))
    assert unchanged == before == first
    assert days_unchanged == days_before
    assert not any(one.key == "late" for one in days_unchanged)

    second = run(lambda: _refresh(server))
    after, days_after, _ = run(lambda: _read(server))
    assert after == second
    assert second > first
    assert any(one.key == "late" and one.dimension is Dimension.MODEL for one in days_after)


def test_runs_either_side_of_midnight_utc_land_on_different_days(server: str) -> None:
    """The grain `REFRESH_EVERY` is derived from, measured on the server rather than assumed.

    Delete this and the view could group by the server's local date, or by month, and the
    refresh schedule would be derived from a grain the view does not have."""
    run(lambda: _refresh(server))
    _, days, _ = run(lambda: _read(server))
    web_days = {one.day for one in days if one.department == WEB}
    assert {date(2999, 6, 14), date(2999, 6, 15)} <= web_days


def test_the_tables_read_policy_is_the_one_the_view_argument_rests_on(server: str) -> None:
    """Read back from `pg_policies`: the application role reads every row of `ops.spend_actual`.

    Delete this and a narrower policy on the table could ship while the view stays granted, and
    nothing on a real server would say the view had become the way round it."""
    policies = run(lambda: _policies(server))
    assert policies == ("true",)
    assert view_gaps(policies) == ()


def test_a_view_nobody_has_refreshed_is_read_as_unbuilt_without_touching_it() -> None:
    """A fresh migration: no refresh record, no rows, and no error from reading an unpopulated
    view, because it is never selected.

    Delete this and the first console load after an install raises PostgreSQL's refusal to read
    an unpopulated materialised view."""
    with built("brain_spend_report_unbuilt", "0036") as url:
        freshness, days, _ = run(lambda: _read(url))
        assert freshness is None
        assert days == ()


def test_the_application_role_may_refresh_and_read_and_may_not_forge_the_age(server: str) -> None:
    """As `brain_app`: the refresh function runs and the view is readable; writing the refresh
    record directly is refused, and so is editing a recorded cost. The fast lane reads neither
    and cannot run the refresh, which is what `0036` relies on in place of a revoke from PUBLIC.

    Delete this and a grant widened to INSERT on `ops.report_refresh` lets the application write
    whatever age it likes beside figures it did not rebuild."""
    with psycopg.connect(server) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT ops.refresh_spend_daily()")
        assert conn.execute("SELECT count(*) FROM ops.spend_daily").fetchone() is not None
        conn.commit()
        conn.execute("SET ROLE brain_app")
        for forged in (
            "INSERT INTO ops.report_refresh (view_name, refreshed_at) "
            "VALUES ('ops.spend_daily', now())",
            "UPDATE ops.spend_actual SET cost_minor = 0",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(forged)
            conn.rollback()
            conn.execute("SET ROLE brain_app")
    with psycopg.connect(server) as conn:
        conn.execute("SET ROLE brain_fastlane")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count(*) FROM ops.spend_daily")
    with psycopg.connect(server) as conn:
        conn.execute("SET ROLE brain_fastlane")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT ops.refresh_spend_daily()")


def test_the_view_is_a_materialised_view_that_row_level_security_cannot_be_put_on(
    server: str,
) -> None:
    """The premise of the module docstring, measured: `ops.spend_daily` is `relkind = 'm'`, which
    `sweep_rls` does not inspect, and PostgreSQL refuses to enable row-level security on it.

    Delete this and the argument that the view's safety must come from its shape rests on a
    claim about PostgreSQL nobody here has run."""
    assert sql(server, "SELECT relkind FROM pg_class WHERE oid = 'ops.spend_daily'::regclass") == [
        ("m",)
    ]
    with pytest.raises(psycopg.errors.WrongObjectType):
        sql(server, "ALTER TABLE ops.spend_daily ENABLE ROW LEVEL SECURITY")


def test_row_level_security_is_on_for_both_tables(server: str) -> None:
    """Delete this and a table created without its ENABLE statement is found by CI only."""
    both = ("ops.spend_actual", "ops.report_refresh")
    assert secured(server, both) == dict.fromkeys(both, True)


def test_the_migrations_build_exactly_what_the_models_declare(server: str) -> None:
    """Every constraint by name and definition, every index and every column, for both tables.

    Delete this and the migration and the model can disagree about a constraint's name, which is
    the thing a later migration dropping it has to get right."""
    both = ("ops.spend_actual", "ops.report_refresh")
    with modelled("brain_spend_report_modelled", both) as from_models:
        assert shape(server, both) == shape(from_models, both)


def test_the_migrations_come_down_and_go_back_up() -> None:
    """Up to `0036`, down to `0033`, up again, asking after the tables, the view and the function.

    Delete this and a downgrade that left the view or the function behind fails the next upgrade
    on `CREATE`, on the day somebody rolls a release forward again."""
    present = (
        "SELECT to_regclass('ops.spend_actual') IS NOT NULL, "
        "to_regclass('ops.report_refresh') IS NOT NULL, "
        "to_regclass('ops.spend_daily') IS NOT NULL, "
        "to_regprocedure('ops.refresh_spend_daily()') IS NOT NULL"
    )
    with built("brain_spend_report_round_trip", "0036") as url:
        assert sql(url, present) == [(True, True, True, True)]
        migrate("brain_spend_report_round_trip", "downgrade", "0033")
        assert sql(url, present) == [(False, False, False, False)]
        migrate("brain_spend_report_round_trip", "upgrade", "0036")
        assert sql(url, present) == [(True, True, True, True)]


def test_a_refresh_does_not_wait_for_a_reader_holding_the_view(server: str) -> None:
    """A reader's open transaction holds the view, and a refresh under a two second lock timeout
    still completes, which a plain REFRESH taking an exclusive lock could not.

    Delete this and the function could drop CONCURRENTLY, and every console load during a
    rebuild would queue behind it, with every other test here green because none of them holds
    a read open across a refresh."""
    run(lambda: _refresh(server))
    with psycopg.connect(server) as reader, psycopg.connect(server) as writer:
        reader.execute("SELECT count(*) FROM ops.spend_daily").fetchone()
        writer.execute("SET lock_timeout = '2s'")
        writer.execute("SELECT ops.refresh_spend_daily()")
        writer.commit()
        reader.rollback()
