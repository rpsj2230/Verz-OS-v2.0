"""The permission canaries run as every reach an install holds; a red run reaches only the alert.

Three halves. Without a server: both checks over the real answer lane and the real projection,
with row sources that behave and row sources that leak, and the verdict a run is recorded with.
Against a server, the reaches: every live principal through the one resolver, one asker per
distinct reach, and the asker the directory does not hold first. And through the worker's tick
against a real `ops.control_run`: a red run is recorded as failed with nothing it found in the
stored detail, and what it found is written to the operator's stream.

The clock is 2999, for the reason CLAUDE.md records.

Task ids: M27.7.19, M28.2.4
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.api_routes import field_policies, row_readers
from brain.core.entitlement import EntitlementSet
from brain.knowledge.rows import RowQuery
from brain.ops import canary_run as module
from brain.ops import schedule_runner, worker
from brain.ops.canaries import CanaryFinding, Finding
from brain.ops.canary_run import (
    ABSENT_VALUE_PREFIX,
    NOBODY,
    RED_RUN_DETAIL,
    UNFINISHED_RUN_DETAIL,
    CanariesFoundError,
    CanaryRun,
    CanaryRunError,
    absent_question,
    ask_every_reach,
    distinct_reaches,
    minted_value,
    projection_check,
    reaches_on_this_install,
    run_canaries,
    run_canaries_now,
    verdict,
)
from brain.ops.schedule_runner import A_CANARY_RUN_IN_REPORT_ONLY_MODE_ASKS_NOTHING
from brain.ops.worker import Ticked
from brain.session import make_session_factory
from brain.tools.startup import build_registry
from tests.fixtures.scratch_postgres import add_modelled, run, sql
from tests.unit.test_answer_route import HOURS
from tests.unit.test_api_routes import GRANTS, SEEDED_ROWS, SOURCE
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_entitlement_store import a_grant, a_principal, resolver
from tests.unit.test_worker_schedule import Starts, control_runs, recorded, tick

NOW = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)

#: The minted value, fixed for the tests that are not about minting it.
VALUE = "QZ0A1B2C3D4E"


def reach(principal_id: str, holds: str | None = None) -> EntitlementSet:
    """A reach holding what `holds` holds in `tests.unit.test_api_routes.GRANTS`, or nothing."""
    grants = () if holds is None else GRANTS[holds]
    return EntitlementSet(principal_id=principal_id, grants=grants)


#: The asker holding nothing, then three live reaches: one seeing every price column, one seeing
#: the price in one prefix, and one reaching the entity in a scope no row satisfies.
REACHES = (
    reach(NOBODY),
    reach("u_narrow", "u_narrow"),
    reach("u_prefix", "u_prefix"),
    reach("u_elsewhere", "u_elsewhere"),
)


class NoRows:
    """A source holding nothing, which is what a value nothing holds finds on a correct install."""

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        return ()


class IgnoresTheFilter:
    """A source that answers every statement with one seeded row, whatever it was asked.

    The defect a canary exists to catch: a read that drops the asker's term, so a value nothing
    holds is answered for whichever reaches can read the column.
    """

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        return SEEDED_ROWS[:1]


class Breaks:
    """A source that raises, so a reach that reads it faults while a reach that does not is told
    nothing was found."""

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        msg = "price_list.cost could not be read"
        raise RuntimeError(msg)


def asked(
    source: object, reaches: Sequence[EntitlementSet] = REACHES, rules: Any = (HOURS,)
) -> CanaryRun:
    registry = build_registry(source=SOURCE, records=source)  # type: ignore[arg-type]
    return asyncio.run(
        ask_every_reach(
            reaches,
            definitions=registry.definitions(),
            rules=rules,
            readers=row_readers(registry),
            policies=field_policies(registry),
            now=NOW,
            value=VALUE,
        )
    )


# ----------------------------------------------------------------------- without a server
def test_a_correct_install_passes_and_the_verdict_says_a_refusal_was_compared() -> None:
    """The positive case for every red one below: four reaches, one rule, a source holding
    nothing, and no finding.

    Delete this and a run that reports every reach as a defect passes every test of a defect."""
    run_ = asked(NoRows())

    assert run_ == CanaryRun(findings=(), rules_asked=(HOURS.rule_id,))
    assert verdict(run_).startswith("passed: every reach was offered exactly the tools it holds")


def test_a_read_that_answers_a_value_nothing_holds_is_found_for_each_reach_it_answered() -> None:
    """The source drops the filter, so the two reaches reading the price are answered and the
    asker holding nothing and the reach whose scope admits no row are told nothing was found.

    Delete this and a canary that compared nothing, or compared every reach with itself, passes."""
    found = asked(IgnoresTheFilter()).findings

    assert found == (
        CanaryFinding(
            kind=Finding.REFUSAL_DISTINGUISHABLE,
            asker="u_narrow",
            question_id=HOURS.rule_id,
            subject="refusal is not the absence sentence",
        ),
        CanaryFinding(
            kind=Finding.REFUSAL_DISTINGUISHABLE,
            asker="u_prefix",
            question_id=HOURS.rule_id,
            subject="refusal is not the absence sentence",
        ),
    )


def test_a_reach_whose_question_faults_is_found_as_having_no_answer() -> None:
    """A fault for one reach and a sentence for another is a refusal that differs by being a
    fault, and it is a finding rather than the end of the run.

    Delete this and a reader raising for one reach either stops every other comparison or is
    passed over as though it had answered."""
    found = asked(Breaks()).findings

    assert {one.asker for one in found} == {"u_narrow", "u_prefix", "u_elsewhere"}
    assert {one.subject for one in found} == {"no answer was recorded"}


def test_every_reach_is_asked_the_rules_own_question_about_the_minted_value() -> None:
    """The question is the template with the value in the slot, and the value is a single word
    the matcher accepts, so the rule is really asked rather than matching nothing for everybody.

    Delete this and a question no rule matches passes every comparison for the wrong reason."""
    minted = minted_value()

    assert minted.startswith(ABSENT_VALUE_PREFIX)
    assert minted != minted_value()
    assert absent_question(HOURS, VALUE) == f"what is the price of {VALUE}"
    assert asked(IgnoresTheFilter()).findings, "the rule must match the minted value to be asked"


def test_the_asker_holding_nothing_is_offered_no_tool_and_one_holding_a_grant_is_found() -> None:
    """For the asker the directory does not hold, admissible is empty by definition, so a
    resolver that handed it a grant is caught against a fact the system did not supply.

    Delete this and an unknown principal resolved to somebody's grants passes the projection."""
    registry = build_registry(source=SOURCE, records=NoRows())
    definitions = registry.definitions()

    assert projection_check(reach(NOBODY), definitions, now=NOW) == ()
    widened = projection_check(reach(NOBODY, "u_narrow"), definitions, now=NOW)
    assert {one.kind for one in widened} == {Finding.PROJECTION_TOO_WIDE}
    assert {one.asker for one in widened} == {NOBODY}
    assert {one.subject for one in widened} == {"local.read_price_list"}


@pytest.mark.parametrize("holds", [None, "u_narrow", "u_admin"])
def test_a_live_reach_is_offered_exactly_what_its_grants_admit(holds: str | None) -> None:
    """Holding nothing, holding the price columns, and holding an admin capability as well.

    Delete this and a projection judged against an admission that always says yes, or always
    says no, passes for one of the three."""
    registry = build_registry(source=SOURCE, records=NoRows())
    definitions = registry.definitions()
    live = reach("u_live", holds)

    assert projection_check(live, definitions, now=NOW) == ()


def test_the_projection_half_runs_for_every_reach_and_not_only_the_first() -> None:
    """A widened asker holding nothing is found when it is first and a run is asked.

    Delete this and `ask_every_reach` could judge the projection of no reach at all."""
    reaches = (reach(NOBODY, "u_narrow"), reach("u_narrow", "u_narrow"))

    found = asked(NoRows(), reaches=reaches, rules=()).findings

    assert found
    assert {one.asker for one in found} == {NOBODY}


def test_a_run_with_no_asker_holding_nothing_first_is_refused() -> None:
    """Delete this and a run whose absence sentence came from a reach that reads the entity
    compares every refusal with an answer, or with nothing."""
    with pytest.raises(CanaryRunError, match="no asker holding nothing"):
        asked(NoRows(), reaches=REACHES[1:])


def test_a_run_that_loads_no_rule_says_it_compared_no_refusal() -> None:
    """Delete this and a run that asked nothing passes in the words of a run that asked."""
    run_ = asked(NoRows(), rules=())

    assert run_.rules_asked == ()
    assert verdict(run_) == (
        "passed on the projection alone: every reach was offered exactly the tools it holds, "
        "and no answer rule is loaded, so no refusal was compared"
    )


def test_one_asker_is_asked_per_distinct_reach_and_the_asker_holding_nothing_leads() -> None:
    """Two people holding the same grants are one asker named by the first id, and a live reach
    holding nothing is the asker holding nothing already.

    Delete this and a run asks a thousand identical questions, or drops a distinct reach."""
    nobody = reach(NOBODY)

    found = distinct_reaches(
        [reach("u_b", "u_narrow"), reach("u_a", "u_narrow"), reach("u_c"), reach("u_d", "u_wide")],
        nobody=nobody,
    )

    assert [one.principal_id for one in found] == [NOBODY, "u_a", "u_d"]


def test_a_red_verdict_names_nothing_in_its_text_and_everything_in_its_alert() -> None:
    """`str()` of the exception is what the worker keeps as the run's detail.

    Delete this and a field name reaches `ops.control_run.detail`, which more screens read and
    which is kept for longer than an alert."""
    run_ = CanaryRun(
        findings=(
            CanaryFinding(
                kind=Finding.LEAKED,
                asker="u_narrow",
                question_id="price_list_sell_price",
                subject="price_list.cost",
            ),
        ),
        rules_asked=("price_list_sell_price",),
    )

    with pytest.raises(CanariesFoundError) as raised:
        verdict(run_)

    assert str(raised.value) == RED_RUN_DETAIL
    assert raised.value.alert == ("leaked: u_narrow on price_list_sell_price, price_list.cost",)
    for word in ("u_narrow", "price_list"):
        assert word not in str(raised.value)


def test_a_red_run_writes_its_lines_to_the_alert_and_raises_with_nothing_in_its_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through `run_canaries_now`, with the gatherer replaced, because the database half is below.

    Delete this and a red run could raise without anybody on call being told what it found."""

    async def red(*_: object, **__: object) -> CanaryRun:
        return CanaryRun(
            findings=(
                CanaryFinding(
                    kind=Finding.PROJECTION_TOO_WIDE,
                    asker=NOBODY,
                    question_id="projection",
                    subject="read_price_list",
                ),
            ),
            rules_asked=(),
        )

    monkeypatch.setattr(module, "run_canaries", red)
    stream = io.StringIO()

    with pytest.raises(CanariesFoundError) as raised:
        run_canaries_now(
            "postgresql://nobody@127.0.0.1:1/none", now=NOW, tool_source=SOURCE, stream=stream
        )

    assert "read_price_list" in stream.getvalue()
    assert stream.getvalue().startswith("  ! canary_run projection_too_wide:")
    assert "read_price_list" not in str(raised.value)


def test_a_run_that_cannot_finish_says_why_in_the_alert_and_nothing_in_its_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception from underneath can quote a column, so it is carried to the alert and the run
    is raised with the sentence that names nothing.

    Delete this and a database error naming a restricted column is kept as the run's detail."""

    async def broken(*_: object, **__: object) -> CanaryRun:
        msg = "column price_list.cost does not exist"
        raise RuntimeError(msg)

    monkeypatch.setattr(module, "run_canaries", broken)
    stream = io.StringIO()

    with pytest.raises(CanaryRunError) as raised:
        run_canaries_now(
            "postgresql://nobody@127.0.0.1:1/none", now=NOW, tool_source=SOURCE, stream=stream
        )

    assert str(raised.value) == UNFINISHED_RUN_DETAIL
    assert "price_list.cost" in stream.getvalue()


def test_the_canary_runner_asked_for_a_report_asks_nothing_and_reaches_no_database() -> None:
    """Delete this and a runner could ignore the mode it was handed."""
    said = schedule_runner.start_control(
        "canary_run", now=NOW, report_only=True, database_url="postgresql://nobody@127.0.0.1:1/none"
    )

    assert said.startswith("report only: the permission canaries asked nothing.")
    assert A_CANARY_RUN_IN_REPORT_ONLY_MODE_ASKS_NOTHING in said


# ------------------------------------------------------------------------- against a server
def test_every_live_reach_is_loaded_through_the_resolver_once_per_distinct_set() -> None:
    """Four principals: two holding the same grant, one holding another, one disabled and holding
    a third. The asker the directory does not hold comes first and holds nothing.

    Delete this and a disabled principal is asked as, or two identical reaches are asked twice,
    or the asker holding nothing is loaded from somewhere other than the resolver."""
    with resolver("brain_canary_reaches") as url:
        for one in ("u_a", "u_b", "u_c", "u_off"):
            a_principal(url, one)
        a_grant(url, "u_a", "read:price_list")
        a_grant(url, "u_b", "read:price_list")
        a_grant(url, "u_c", "read:client.name")
        a_grant(url, "u_off", "read:invoice")
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = 'u_off'")

        async def go() -> tuple[EntitlementSet, ...]:
            engine = app_engine(url)
            try:
                return await reaches_on_this_install(make_session_factory(engine), now=NOW)
            finally:
                await engine.dispose()

        found = run(go)

    assert [one.principal_id for one in found] == [NOBODY, "u_a", "u_c"]
    assert found[0].grants == ()
    assert [g.capability.value for g in found[1].grants] == ["read:price_list"]


def test_a_run_over_a_real_install_loads_its_rules_and_reaches_and_passes() -> None:
    """`run_canaries` over the resolver and the rule table, with no rule loaded: every reach is
    projected and nothing is compared, and a run that could not read either would raise.

    Delete this and the gatherer can be wired to a store that does not exist on an install."""
    with resolver("brain_canary_real_run") as url:
        add_modelled(url, ("gate.fast_path_rule",))
        a_principal(url, "u_a")
        a_grant(url, "u_a", "read:price_list")

        async def go() -> CanaryRun:
            from brain.session import make_app_engine

            engine = make_app_engine(url)
            try:
                return await run_canaries(
                    make_session_factory(engine), tool_source=SOURCE, now=NOW, value=VALUE
                )
            finally:
                await engine.dispose()

        found = run(go)

    assert found == CanaryRun(findings=(), rules_asked=())


def test_a_red_run_started_by_the_tick_is_recorded_failed_with_nothing_it_found_in_the_detail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """**The leaf, end to end.** The tick starts `canary_run` through the real `start_control` and
    the real runner, whose gatherer finds a leak: the run is recorded as failed, the stored detail
    is the sentence naming nothing, and the field is on the operator's stream. A second tick half a
    day later finds nothing and is recorded as passed in the words of a run that compared nothing.

    Delete this and a red run could be recorded as ok, or recorded failed with the field it found
    kept in the detail column every run screen reads."""
    real = schedule_runner.start_control
    others = Starts()

    def started(name: str, *, now: datetime, report_only: bool, database_url: str) -> str:
        if name == "canary_run":
            return real(name, now=now, report_only=report_only, database_url=database_url)
        return others(name, now=now, report_only=report_only, database_url=database_url)

    findings: list[tuple[CanaryFinding, ...]] = [
        (
            CanaryFinding(
                kind=Finding.LEAKED,
                asker="u_narrow",
                question_id="price_list_sell_price",
                subject="price_list.cost",
            ),
        ),
        (),
    ]

    async def gathered(*_: object, **__: object) -> CanaryRun:
        return CanaryRun(findings=findings.pop(0), rules_asked=())

    monkeypatch.setattr(worker, "start_control", started)
    monkeypatch.setattr(module, "run_canaries", gathered)
    with control_runs("brain_canary_tick") as url:
        red = tick(url, at=NOW)
        later = tick(url, at=NOW.replace(hour=21, minute=1))
        runs = [(row[1], row[3]) for row in recorded(url) if row[0] == "canary_run"]

    assert {one.name: one.ticked for one in red}["canary_run"] is Ticked.FAILED
    assert {one.name: one.ticked for one in later}["canary_run"] is Ticked.RAN
    assert runs == [
        ("failed", f"CanariesFoundError: {RED_RUN_DETAIL}"),
        (
            "ok",
            "passed on the projection alone: every reach was offered exactly the tools it "
            "holds, and no answer rule is loaded, so no refusal was compared",
        ),
    ]
    assert "price_list.cost" in capsys.readouterr().err
