"""Who is told what: the list of notices held to the source, and the switch held to what it stops.

The list makes claims about code, so each is asserted against the code: every composer is a
function that exists, every notice said to be sent names a sender that asks the switch and is
started by the worker's schedule, and a notice said to be unsent is not called from anything that
is. The switch is followed through the one sender that exists: switched off, a re-verification run
records nothing, against a database; switched on again, it records the request.

Task ids: M27.8.11, M27.7.12
"""

from __future__ import annotations

import ast
import importlib
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.notices import (
    A_NOTICE_SHIPS_ON,
    A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH,
    NOTICES,
    Notice,
    NoticeError,
    NoticeKind,
    notice,
    switched_off_in,
)
from brain.ops.setting_store import SettingState

LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)


def state(value: object, value_type: str = "boolean") -> SettingState:
    return SettingState("notice.x", value_type, value, "u_admin", LONG_AGO)


def _function(symbol: str) -> object:
    module, _, name = symbol.partition(":")
    return getattr(importlib.import_module(module), name)


# ------------------------------------------------------------------------ the list
def test_every_kind_has_exactly_one_notice_and_every_composer_exists() -> None:
    """Delete this and a notice naming a renamed composer goes on telling an administrator about a
    function that is gone, and a kind with no row is a notice nobody can switch."""
    assert [one.kind for one in NOTICES] == list(NoticeKind)
    for one in NOTICES:
        assert callable(_function(one.composed_by)), one.composed_by


def test_a_notice_said_to_be_sent_names_a_sender_that_asks_the_switch_about_it() -> None:
    """**What makes "sent" and the switch true.** The sender is read for a call to `notice_is_on`
    naming this notice's kind, and it is started by the worker's schedule.

    Delete this and a sender added for a notice can skip the switch, so the screen offers to stop
    something the switch never reaches."""
    from brain.ops.controls import Invocation, control

    sent = [one for one in NOTICES if one.sent_by]
    assert [one.kind for one in sent] == [NoticeKind.REVERIFICATION_REQUEST]
    for one in sent:
        tree = ast.parse(inspect.getsource(_function(one.sent_by)))  # type: ignore[arg-type]
        asks = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "notice_is_on"
            and any(
                isinstance(arg, ast.Attribute) and arg.attr == one.kind.name for arg in node.args
            )
        ]
        assert asks, f"{one.sent_by} does not ask whether {one.kind.value} is on"
    assert control("knowledge_reverification").invoked_by is Invocation.IN_PROCESS


def test_a_notice_said_to_be_unsent_has_a_composer_nothing_the_schedule_starts_calls() -> None:
    """The other direction, one hop. Delete this and a notice wired to a sender reads as unsent,
    and nobody offers the switch that would stop it."""
    from brain.ops.controls import call_sites

    scheduled = {"brain.ops.schedule_runner", "brain.ops.worker", "brain.knowledge.item_store"}
    for one in NOTICES:
        if one.sent_by:
            continue
        assert not set(call_sites(one.composed_by)) & scheduled, one.composed_by


def test_the_notices_with_no_switch_are_the_ones_that_report_misuse_or_a_mechanism_failing() -> (
    None
):
    """Named rather than counted. Delete this and a notice of emergency access gains a switch in a
    tidy-up, which is a way to take the access and not be seen taking it."""
    fixed = {one.kind for one in NOTICES if not one.switchable}
    assert fixed == {
        NoticeKind.CONTROL_NOT_RUN,
        NoticeKind.BACKUP_EXPOSURE,
        NoticeKind.EMERGENCY_ACCESS,
        NoticeKind.SELF_GRANT,
        NoticeKind.AUTOMATION_PAUSED,
    }
    assert all(
        one.fixed_because == A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH
        for one in NOTICES
        if not one.switchable
    )


def test_a_notice_that_does_not_say_who_is_told_is_refused() -> None:
    """Delete this and a row can be added that says nothing a person could judge."""
    with pytest.raises(NoticeError, match="told"):
        Notice(NoticeKind.SELF_GRANT, "t", " ", "a", "h", "brain.x:y")
    assert notice("self_grant").kind is NoticeKind.SELF_GRANT
    with pytest.raises(NoticeError):
        notice("made_up")


# ------------------------------------------------------------------------ the switch
def test_a_notice_is_on_until_a_row_holds_false() -> None:
    """**Absent means on.** Delete this and every notice ships silenced, or a string "false" written
    at a prompt silences one nobody chose to."""
    kind = NoticeKind.REVERIFICATION_REQUEST.value
    assert switched_off_in({}) == frozenset()
    assert switched_off_in({kind: state(True)}) == frozenset()
    assert switched_off_in({kind: state("false", "string")}) == frozenset()
    assert switched_off_in({kind: state(None)}) == frozenset()
    assert switched_off_in({kind: state(False)}) == {NoticeKind.REVERIFICATION_REQUEST}
    assert "no row means on" in A_NOTICE_SHIPS_ON


def test_a_row_holding_false_for_a_notice_with_no_switch_silences_nothing() -> None:
    """Delete this and a row written at a database prompt silences a notice of emergency access."""
    assert switched_off_in({NoticeKind.EMERGENCY_ACCESS.value: state(False)}) == frozenset()


def test_switching_a_notice_with_no_switch_is_refused_before_anything_is_written() -> None:
    """Delete this and a route that forgot to ask writes the row the reader then ignores, and the
    screen says the notice is off."""
    import asyncio

    from brain.ops.notices import switch

    class Refusing:
        async def execute(self, *_: object, **__: object) -> None:
            raise AssertionError("nothing should be written")

    with pytest.raises(NoticeError, match="has no switch"):
        asyncio.run(
            switch(Refusing(), notice("emergency_access"), on=False, by="u_admin")  # type: ignore[arg-type]
        )


def test_switched_off_a_re_verification_run_records_nothing_and_switched_on_it_does() -> None:
    """**The switch, followed to the behaviour it changes.** One lapsed item whose owner still
    reads it: with the notice switched off the run records no event and says why; switched on
    again, the same run records the request.

    Delete this and the switch writes its row and the next run asks nobody, so the screen says a
    notice is off while every subscriber goes on being told."""
    from brain.knowledge.item import KnowledgeItem
    from brain.knowledge.item_store import NagRun, run_reverification_now
    from brain.knowledge.visibility import KnowledgeVisibility
    from brain.ops.notices import switch
    from brain.ops.worker import _loop_factory
    from brain.session import make_app_engine, make_session_factory
    from tests.fixtures.knowledge_items import a_person, a_reader, knowledge_items, nags, put
    from tests.fixtures.scratch_postgres import run

    now = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)
    lapsed = now - timedelta(days=1)
    item = KnowledgeItem(
        item_id="kb.renewals",
        content="What the document says.",
        title="Renewal pricing",
        visibility=KnowledgeVisibility.of_department("web", owner_id="u_owner"),
        owner_id="u_owner",
    ).verified(by="u_verifier", at=lapsed - timedelta(days=365), review_by=lapsed)

    def turn(url: str, *, on: bool) -> None:
        async def write() -> None:
            engine = make_app_engine(url)
            try:
                async with make_session_factory(engine)() as session, session.begin():
                    await switch(session, notice("reverification_request"), on=on, by="u_admin")
            finally:
                await engine.dispose()

        run(write)

    with knowledge_items("brain_notice_switch") as url:
        a_person(url, "u_owner")
        a_reader(url, "u_owner", "web")
        put(url, item)
        turn(url, on=False)
        silenced = run_reverification_now(url, now=now, loop_factory=_loop_factory())
        nothing = nags(url)
        turn(url, on=True)
        asked = run_reverification_now(url, now=now, loop_factory=_loop_factory())
        recorded = nags(url)

    assert silenced == NagRun(switched_off=True)
    assert "switched this notice off" in silenced.summary(now)
    assert nothing == []
    assert asked.recorded is True
    assert [one[0] for one in recorded] == ["kb.renewals"]
