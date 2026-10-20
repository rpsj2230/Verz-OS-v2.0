"""A mover's automations are paused when their reach shrinks, and left alone when it does not.

`brain.ops.mover_automations` is the decision and `brain.ops.staff_sync_run` is the run that
asks it.
The first half of this file holds the decision over values: no server, and the real
`EntitlementSet.intersect`, because a stand-in for the central rule here would be a second copy of
it. The second half drives the scheduled run itself against a migrated PostgreSQL as the
application role, over the same company `tests/unit/test_starter_pack_sync.py` builds, so the
policies, the trigger that writes the ledger entry and the switch are the ones an install has.
**The second half skips where there is no server, and CI always has one.**

Task ids: M26.2.3
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.console.automation_gallery import BUILT_IN
from brain.core.department import department_scope
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops import mover_automations as subject
from brain.ops.automation_run import PausedBecause
from brain.ops.features import FEATURES
from brain.ops.features_declared.mover_pauses_automations import MOVER_PAUSES_AUTOMATIONS
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_starter_pack_sync import (
    GRANTOR,
    READ_AT,
    KatherineMoves,
    a_company,
    app_role,
    sync_as_the_application,
)

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)

READ = Capability(value="read:knowledge")
DOCUMENT = Capability(value="read:knowledge.document")


def reach(*held: tuple[Capability, Scope]) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_owner", grants=tuple(Grant(capability=c, scope=s) for c, s in held)
    )


# ------------------------------------------------------------------ the decision, over values
def test_an_owner_who_moves_to_another_department_has_lost_the_reach_the_automation_had() -> None:
    """Finance before, engineering after: what the automation read is no longer inside what it
    reads. Delete this and the one case the leaf exists for, a move between departments that
    leaves the capability held in a different scope, is not noticed by anything."""
    before = reach((READ, department_scope("finance")))
    after = reach((READ, department_scope("engineering")))

    assert subject.lost_reach(before, after, now=NOW) is True


def test_an_owner_whose_reach_is_unchanged_has_lost_nothing() -> None:
    """The positive sibling of every refusal here. Delete this and a `lost_reach` that answers
    True for everybody passes the test above and pauses every automation on every night."""
    same = reach((READ, department_scope("finance")), (DOCUMENT, department_scope("finance")))

    assert subject.lost_reach(same, same, now=NOW) is False


def test_an_owner_who_gains_reach_while_keeping_the_old_has_lost_nothing() -> None:
    """A promotion from one department to the whole company covers what it had. Delete this and a
    comparison by equality, which pauses a promoted person's automations, passes everything else
    in this file."""
    before = reach((READ, department_scope("finance")))
    wider = reach((READ, Scope.unrestricted()))

    assert subject.lost_reach(before, wider, now=NOW) is False


def test_an_owner_who_keeps_the_department_and_loses_a_capability_has_lost_reach() -> None:
    """A capability gone altogether is a loss in the same department. Delete this and only a
    change of scope is noticed, so a revoked read passes."""
    before = reach((READ, department_scope("finance")), (DOCUMENT, department_scope("finance")))
    after = reach((READ, department_scope("finance")))

    assert subject.lost_reach(before, after, now=NOW) is True


def test_an_owner_who_gains_a_capability_and_keeps_the_rest_has_lost_nothing() -> None:
    """Delete this and any change at all reads as a loss."""
    before = reach((READ, department_scope("finance")))
    after = reach((READ, department_scope("finance")), (DOCUMENT, department_scope("finance")))

    assert subject.lost_reach(before, after, now=NOW) is False


def test_an_automation_that_reached_nothing_cannot_lose_reach() -> None:
    """An empty reach before has nothing to lose. Delete this and an automation whose owner
    never held what it reads is paused by a move that changed nothing for it."""
    assert subject.lost_reach(reach(), reach((READ, department_scope("finance"))), now=NOW) is False


def test_a_reach_is_judged_at_the_instant_it_is_asked_about_and_not_at_the_wall_clock() -> None:
    """The reach before ends in 2020. Asked as at 2019 it is covered, asked as at 2021 it has
    lapsed and nothing of it can be held; both far from the wall clock, so a call that falls back
    to the process clock answers the same for both. Delete this and `lost_reach` can stop handing
    `now` to the intersection and to the survivor, which judge the right-hand side's expiry
    against whatever the process clock says (CLAUDE.md, the paragraph on the instant)."""
    scope = department_scope("finance")
    before = EntitlementSet(
        principal_id="u_owner",
        grants=(Grant(capability=READ, scope=scope),),
        not_after=datetime(2020, 1, 1, tzinfo=UTC),
    )
    after = reach((READ, scope))

    assert subject.lost_reach(before, after, now=datetime(2019, 6, 1, tzinfo=UTC)) is False
    assert subject.lost_reach(before, after, now=datetime(2021, 1, 1, tzinfo=UTC)) is True


def test_the_switch_is_declared_off_and_read_by_the_function_that_asks_it() -> None:
    """Delete this and the switch can be declared and read by nothing, which the reader check in
    `test_features` finds only for the tree it is run on."""
    assert MOVER_PAUSES_AUTOMATIONS in FEATURES
    assert MOVER_PAUSES_AUTOMATIONS.read_by == (
        f"{subject.__name__}:{subject.movers_pause_automations.__name__}",
    )


def test_the_pause_uses_the_reason_the_database_already_holds() -> None:
    """The reason written is a member of the closed vocabulary the table's constraint holds.
    Delete this and a new word for the same pause would need a migration nobody planned."""
    from brain.tables.automation_run import PAUSE_REASONS

    assert PausedBecause.OWNER_LOST_REACH.value in PAUSE_REASONS


# ------------------------------------------------------------------ with a server
AGENT = "quote_helper"
QUESTIONS = next(one for one in BUILT_IN if one.task == "automation.unanswered_questions")


def automations_for(url: str, *owners: str) -> None:
    """One agent admitting the starter pack's read, and one scheduled automation of each owner."""
    sql(
        url,
        "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
        " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
        " created_by) VALUES (%s, 'Quote helper', 'Answers briefly.', 'main', 'company',"
        " 'u_steward', NULL, '{\"clauses\": []}', %s, '{}', '{}', 'none', 'u_builder')",
        AGENT,
        ["read:knowledge", "read:knowledge.document"],
    )
    for owner in owners:
        sql(
            url,
            "INSERT INTO agent.automation (automation_id, agent_id, name, runs_as_id, task,"
            " next_run_at, guards, template_id, template_version, installed_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
            f"auto_{owner}",
            AGENT,
            QUESTIONS.name,
            owner,
            QUESTIONS.task,
            NOW,
            QUESTIONS.guards,
            QUESTIONS.template_id,
            owner,
        )


def next_runs(url: str) -> dict[str, datetime | None]:
    return {
        str(auto): at
        for auto, at in sql(
            url, "SELECT automation_id, next_run_at FROM agent.automation ORDER BY automation_id"
        )
    }


def turned_on(url: str) -> None:
    from brain.ops.features import switch

    async def go() -> None:
        engine = app_role(url)
        try:
            async with make_session_factory(engine)() as session, session.begin():
                await switch(session, MOVER_PAUSES_AUTOMATIONS, on=True, by="u_owner")
        finally:
            await engine.dispose()

    run(go)


def schedule_rows(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT automation_id, reason, changed_by, next_run_at FROM agent.automation_schedule"
        " ORDER BY automation_id",
    )


def first_night(url: str) -> None:
    """The first night gives every person the pack over their department, and an administrator
    gives Priya a finance pack by hand, which no sync touches."""
    from tests.unit.test_staff_sync_run import Directory

    sync_as_the_application(url, at=READ_AT, fetch=Directory())
    sql(
        url,
        "INSERT INTO gate.capability_pack_assignment"
        " (principal_id, pack_id, scope, granted_by, reason)"
        " SELECT 'p_priya', id, %s, 'u_admin', 'assigned by hand' FROM gate.capability_pack"
        " WHERE name = 'starter'",
        json.dumps(department_scope("finance").model_dump(mode="json")),
    )


def second_night(url: str) -> None:
    """The automations are installed, and the second night moves Katherine from finance to
    engineering."""
    automations_for(url, "p_katherine", "p_priya")
    sync_as_the_application(url, at=READ_AT + timedelta(days=1), fetch=KatherineMoves([]))


def two_nights(url: str) -> None:
    first_night(url)
    second_night(url)


@pytest.mark.needs_db
def test_the_run_that_moves_a_person_pauses_their_automation_and_nobody_elses() -> None:
    """**The leaf, end to end through the scheduled run.** Katherine owns an automation and Priya
    owns one; the second night moves Katherine from finance to engineering and leaves Priya, whose
    pack an administrator assigned, where she was. With the switch on Katherine's has no next run,
    a schedule row says it stopped because her reach changed, by the roster and not by a person,
    and the ledger records the detachment under the roster's actor; Priya's is still scheduled.

    Delete this and a mover's automation goes on running at the department they moved to, with
    nothing on any page saying so, which is narrowing by a side effect."""
    with a_company("brain_mover_automations_pause") as url:
        turned_on(url)
        two_nights(url)
        runs = next_runs(url)
        rows = schedule_rows(url)
        entries = sql(
            url,
            "SELECT actor_id, details FROM obs.audit_entry"
            " WHERE details ->> 'reference' = 'auto_p_katherine' ORDER BY seq",
        )

    assert runs["auto_p_katherine"] is None
    assert runs["auto_p_priya"] == NOW
    assert rows == [("auto_p_katherine", PausedBecause.OWNER_LOST_REACH.value, GRANTOR, None)]
    assert [(actor, details["direction"]) for actor, details in entries] == [
        ("p_katherine", "attached"),
        (GRANTOR, "detached"),
    ]
    assert entries[-1][1]["reason_code"] == PausedBecause.OWNER_LOST_REACH.value


@pytest.mark.needs_db
def test_with_the_switch_off_a_move_pauses_nothing() -> None:
    """The same two nights with the switch left at its default. Delete this and the switch gates
    nothing, so an install that has not agreed to it has automations stopped by a nightly read."""
    with a_company("brain_mover_automations_off") as url:
        two_nights(url)
        runs = next_runs(url)
        rows = schedule_rows(url)

    assert runs == {"auto_p_katherine": NOW, "auto_p_priya": NOW}
    assert rows == []


@pytest.mark.needs_db
def test_a_second_night_that_moves_nobody_pauses_nothing() -> None:
    """Two nights with nobody moved, the switch on. Delete this and every night pauses every
    automation, which a test with only a mover in it cannot tell from the pause working."""
    from tests.unit.test_staff_sync_run import Directory

    with a_company("brain_mover_automations_still") as url:
        turned_on(url)
        sync_as_the_application(url, at=READ_AT, fetch=Directory())
        automations_for(url, "p_katherine", "p_ada")
        sync_as_the_application(url, at=READ_AT + timedelta(days=1), fetch=Directory())
        runs = next_runs(url)
        rows = schedule_rows(url)

    assert runs == {"auto_p_ada": NOW, "auto_p_katherine": NOW}
    assert rows == []


@pytest.mark.needs_db
def test_a_paused_mover_automation_is_listed_with_the_reason_and_who_paused_it() -> None:
    """After the pause the automation's own page reads it with no next run, the reason on the
    newest schedule row and the roster as the one who wrote it. The owner is the person it runs
    as, so `may_see` lists it on their page; a person with the schedule screen's grant sees it
    through that. Delete this and the pause can be invisible on the page it is meant to be
    listed on, so nobody knows an automation stopped."""
    from brain.ops.automation_run_store import StoredAutomationSchedules

    with a_company("brain_mover_automations_listed") as url:
        turned_on(url)
        two_nights(url)

        async def listed() -> Any:
            engine = app_role(url)
            try:
                return await StoredAutomationSchedules(make_session_factory(engine)).one(
                    "auto_p_katherine"
                )
            finally:
                await engine.dispose()

        detail = run(listed)

    assert detail is not None
    one = detail.listed
    assert one.automation.next_run_at is None
    assert one.automation.runs_as.id == "p_katherine"
    assert one.stopped_because == PausedBecause.OWNER_LOST_REACH.value
    assert detail.schedule[-1].changed_by == GRANTOR


# ------------------------------------------------------------------ what the watch leaves alone
STOP_KATHERINES = "UPDATE agent.automation SET next_run_at = NULL WHERE runs_as_id = 'p_katherine'"
REMOVE_KATHERINES = (
    "INSERT INTO agent.automation_change (automation_id, agent_id, kind, changed_by, at)"
    " VALUES ('auto_p_katherine', %s, 'removed', 'u_admin', now())"
)
ORPHAN_PRIYAS = "UPDATE agent.automation SET agent_id = 'gone_agent' WHERE runs_as_id = 'p_priya'"


def _second_night_with(url: str, before: str, *params: object) -> None:
    """The second night, after `before` has been run against the database as the test's set-up."""
    first_night(url)
    automations_for(url, "p_katherine", "p_priya")
    sql(url, before, *params)
    sync_as_the_application(url, at=READ_AT + timedelta(days=1), fetch=KatherineMoves([]))


@pytest.mark.needs_db
def test_an_automation_already_stopped_is_not_paused_again_and_leaves_no_second_row() -> None:
    """Katherine's automation was stopped by a person before the move. The move writes nothing for
    it: no schedule row, and the next run stays empty. Delete this and a stopped automation is
    paused again every night its owner's reach shrinks, each time a new ledger entry claiming the
    roster stopped it."""
    with a_company("brain_mover_automations_stopped") as url:
        turned_on(url)
        _second_night_with(url, STOP_KATHERINES)
        rows = schedule_rows(url)

    assert rows == []


@pytest.mark.needs_db
def test_a_removed_automation_is_never_paused() -> None:
    """A removal is final and keeps its history. Delete this and the roster writes a pause against
    an automation somebody removed, which the removal's own rule says never runs again."""
    with a_company("brain_mover_automations_removed") as url:
        turned_on(url)
        _second_night_with(url, REMOVE_KATHERINES, AGENT)
        rows = schedule_rows(url)

    assert rows == []


@pytest.mark.needs_db
def test_an_orphaned_automation_does_not_stop_the_others_being_paused() -> None:
    """Priya's automation is moved to an agent the table does not hold, and Katherine's is still
    paused. Delete this and one orphaned automation makes the whole watch fail, so no mover's
    automation is paused on an install that has one."""
    with a_company("brain_mover_automations_orphan") as url:
        turned_on(url)
        _second_night_with(url, ORPHAN_PRIYAS)
        runs = next_runs(url)

    assert runs["auto_p_katherine"] is None
    assert runs["auto_p_priya"] == NOW


@pytest.mark.needs_db
def test_a_leaver_s_automation_is_left_for_the_runner_to_pause_as_owner_gone() -> None:
    """Ada leaves on the second night and her automation is not paused by the roster as a lost
    reach. Delete this and a leaver's automation is recorded as stopped because their reach
    changed, which is the wrong word for it and would hide that it now awaits an owner."""
    with a_company("brain_mover_automations_leaver") as url:
        turned_on(url)
        first_night(url)
        automations_for(url, "p_katherine", "p_ada")
        sync_as_the_application(url, at=READ_AT + timedelta(days=1), fetch=KatherineMoves([]))
        rows = schedule_rows(url)

    assert [row[0] for row in rows] == ["auto_p_katherine"]


def test_a_failure_reading_the_automations_leaves_the_run_applied_and_pauses_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The watch raises. It returns nothing and the pack step goes on; the pause step is given
    nothing and writes nothing. Delete this and a database error in an observer takes the staff
    list's packs with it, on every install, for as long as the switch is on."""
    import asyncio

    from brain.ops.automation_run_store import StoredAutomationSchedules

    async def raises(self: object) -> tuple[()]:
        msg = "the table was unreadable"
        raise RuntimeError(msg)

    async def on(_: object) -> bool:
        return True

    monkeypatch.setattr(StoredAutomationSchedules, "every", raises)
    monkeypatch.setattr(subject, "movers_pause_automations", on)
    nothing: Any = object()
    assert asyncio.run(subject.watch(nothing, now=NOW)) == ()
    paused = subject.pause_what_lost_reach(nothing, (), source="x", trace_id="t", now=NOW)
    assert asyncio.run(paused) == ()


@pytest.mark.needs_db
def test_a_stop_that_wins_the_race_is_neither_overwritten_nor_reported() -> None:
    """Katherine's automation is stopped by a person between the watch and the pause. The pause
    writes nothing for it and does not say it paused it. Delete this and the roster claims, in the
    ledger and in its report, to have stopped something a person had already stopped."""
    import asyncio

    async def go(url: str) -> tuple[str, ...]:
        engine = app_role(url)
        try:
            sessions = make_session_factory(engine)
            watched = await subject.watch(sessions, now=READ_AT)
            sql(url, STOP_KATHERINES)
            sql(
                url,
                "UPDATE gate.capability_pack_assignment SET scope = %s WHERE principal_id ="
                " 'p_katherine' AND deleted_at IS NULL",
                json.dumps(department_scope("engineering").model_dump(mode="json")),
            )
            return await subject.pause_what_lost_reach(
                sessions, watched, source="lark", trace_id="t", now=READ_AT
            )
        finally:
            await engine.dispose()

    with a_company("brain_mover_automations_race") as url:
        turned_on(url)
        first_night(url)
        automations_for(url, "p_katherine", "p_priya")
        paused = asyncio.run(go(url))
        rows = schedule_rows(url)

    assert paused == ()
    assert rows == []


@pytest.mark.needs_db
def test_a_person_who_leaves_between_the_watch_and_the_pause_is_not_paused_as_a_mover() -> None:
    """Ada's automation is watched while she is here, she is disabled before the pause, and the
    pause writes nothing for her: a leaver's automation is awaiting an owner, and the runner
    pauses it as `owner_gone` when it is due. Delete this and a leaver's automation is recorded as
    stopped because their reach changed, which is the wrong word for it and hides that it now
    awaits an owner."""
    import asyncio

    async def go(url: str) -> tuple[str, ...]:
        engine = app_role(url)
        try:
            sessions = make_session_factory(engine)
            watched = await subject.watch(sessions, now=READ_AT)
            sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = 'p_ada'")
            sql(
                url,
                "UPDATE gate.capability_pack_assignment SET deleted_at = now() WHERE principal_id"
                " = 'p_ada' AND deleted_at IS NULL",
            )
            return await subject.pause_what_lost_reach(
                sessions, watched, source="lark", trace_id="t", now=READ_AT
            )
        finally:
            await engine.dispose()

    with a_company("brain_mover_automations_leaves") as url:
        turned_on(url)
        first_night(url)
        automations_for(url, "p_ada")
        paused = asyncio.run(go(url))
        rows = schedule_rows(url)

    assert paused == ()
    assert rows == []
