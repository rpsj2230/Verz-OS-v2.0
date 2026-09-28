"""The Automations module's decisions over values: what an automation is now, and who may pause,
resume, reschedule, remove or adopt it.

`tests/unit/test_automations_routes.py` drives the same decisions through the routes, and
`tests/unit/test_automation_change_store.py` what the store writes and the runner then does.

Task ids: M27.12.3, M27.15.37, M39.6.1.5
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from brain.console.agent_automations import Automation
from brain.console.automation_gallery import Cadence, Every
from brain.console.automations import AutomationsError as Refused
from brain.console.automations import (
    Change,
    ChangeKind,
    State,
    folded,
    may_adopt,
    may_pause,
    may_remove,
    may_reschedule,
    may_resume,
    rescheduled_next_run,
    shown,
    state_of,
)
from brain.ops.automation_run import next_run_after
from brain.tables import automation_change as table
from tests.unit.test_automation_schedule_routes import (
    NOW,
    QUESTIONS,
    READING_AGENT,
    an_automation,
    reach,
)

MONDAYS = Cadence(every=Every.WEEK, hour_utc=7, weekday=0)
RUNNING = NOW + timedelta(hours=1)


def test_the_table_restates_the_domains_kinds_and_cadences_exactly() -> None:
    """Delete this and a kind added to the domain would be refused by the database at the first
    write, or a cadence the gallery offers would not fit the column."""
    assert set(table.CHANGE_KINDS) == {one.value for one in ChangeKind}
    assert set(table.EVERY) == {one.value for one in Every}
    assert Every.WEEK.value == table.WEEK
    assert (
        ChangeKind.PAUSED.value,
        ChangeKind.RESUMED.value,
        ChangeKind.RESCHEDULED.value,
        ChangeKind.REMOVED.value,
        ChangeKind.ADOPTED.value,
    ) == (table.PAUSED, table.RESUMED, table.RESCHEDULED, table.REMOVED, table.ADOPTED)


def test_the_fold_takes_the_newest_owner_and_cadence_and_one_removal_is_final() -> None:
    """Read out of order on purpose: the fold sorts by instant, not by the order it was handed.

    Delete this and an automation adopted twice could run as its first adopter, or a removed one
    read as live because a later change was folded over the removal."""
    changes = [
        Change(kind=ChangeKind.ADOPTED, at=NOW + timedelta(2), changed_by="u_b", runs_as_id="u_b"),
        Change(kind=ChangeKind.ADOPTED, at=NOW + timedelta(1), changed_by="u_a", runs_as_id="u_a"),
        Change(kind=ChangeKind.RESCHEDULED, at=NOW, changed_by="u_admin", cadence=MONDAYS),
    ]
    now_is = folded(installed_as="u_gone", template_cadence=QUESTIONS.cadence, changes=changes)
    assert (now_is.owner_id, now_is.cadence, now_is.removed) == ("u_b", MONDAYS, False)
    assert [one.at for one in now_is.changes] == sorted(one.at for one in changes)

    untouched = folded(installed_as="u_gone", template_cadence=QUESTIONS.cadence, changes=())
    assert (untouched.owner_id, untouched.cadence) == ("u_gone", QUESTIONS.cadence)

    ended = folded(
        installed_as="u_gone",
        template_cadence=QUESTIONS.cadence,
        changes=[
            Change(kind=ChangeKind.REMOVED, at=NOW, changed_by="u_admin"),
            Change(kind=ChangeKind.RESCHEDULED, at=RUNNING, changed_by="u_x", cadence=MONDAYS),
        ],
    )
    assert ended.removed


def test_a_change_carries_exactly_what_its_kind_changed() -> None:
    """Delete this and a row could say it was a pause and name a cadence, or an adoption could
    hand an automation to somebody other than the adopter."""
    Change(kind=ChangeKind.ADOPTED, at=NOW, changed_by="u_a", runs_as_id="u_a")
    with pytest.raises(Refused, match="adopter's own name"):
        Change(kind=ChangeKind.ADOPTED, at=NOW, changed_by="u_a", runs_as_id="u_b")
    with pytest.raises(Refused, match="carries its cadence"):
        Change(kind=ChangeKind.PAUSED, at=NOW, changed_by="u_a", cadence=MONDAYS)
    with pytest.raises(Refused, match="leaves no next run"):
        Change(kind=ChangeKind.REMOVED, at=NOW, changed_by="u_a", next_run_at=RUNNING)
    with pytest.raises(Refused, match="a resume leaves"):
        Change(kind=ChangeKind.RESUMED, at=NOW, changed_by="u_a")


def test_the_state_is_removed_then_ownerless_then_the_next_run() -> None:
    """Delete this and a removed automation could read as paused, which invites a resume, or an
    ownerless one as running because its schedule has not been reached yet."""
    running = an_automation(next_run_at=RUNNING)
    assert state_of(running, removed=False, owner_live=True) is State.RUNNING
    assert state_of(an_automation(), removed=False, owner_live=True) is State.PAUSED
    assert state_of(running, removed=False, owner_live=False) is State.OWNERLESS
    assert state_of(running, removed=True, owner_live=False) is State.REMOVED


def test_pausing_and_removing_are_the_owners_and_the_authoritys_and_never_a_removed_ones() -> None:
    """The fail-safe acts: the owner and the authority may, a colleague who can only see it may
    not, and nothing may touch a removed automation.

    Delete this and a pause would need an approver, or a removed automation could be paused again,
    which writes a ledger entry about something that no longer exists."""
    running = an_automation(next_run_at=RUNNING)
    assert may_pause(running, reach("u_narrow"), removed=False, now=NOW)
    assert may_pause(running, reach("u_admin"), removed=False, now=NOW)
    assert not may_pause(running, reach("u_elsewhere"), removed=False, now=NOW)
    assert not may_pause(running, reach("u_admin"), removed=True, now=NOW)
    paused = an_automation()
    assert may_remove(paused, reach("u_narrow"), removed=False, now=NOW)
    assert may_remove(paused, reach("u_admin"), removed=False, now=NOW)
    assert not may_remove(paused, reach("u_elsewhere"), removed=False, now=NOW)
    assert not may_remove(paused, reach("u_prefix"), removed=False, now=NOW)
    assert not may_remove(paused, reach("u_admin"), removed=True, now=NOW)


def test_a_resume_needs_an_owner_who_is_here_and_the_authority_held_by_somebody_else() -> None:
    """Delete this and an ownerless automation could be resumed to be refused at its first run, or
    its own owner could approve its own resume."""

    def resumable(one: Automation, pid: str, *, owner_live: bool) -> bool:
        return may_resume(
            one,
            reach(pid),
            agent=READING_AGENT,
            cadence=QUESTIONS.cadence,
            removed=False,
            owner_live=owner_live,
            now=NOW,
        )

    paused = an_automation()
    assert resumable(paused, "u_admin", owner_live=True)
    assert not resumable(paused, "u_admin", owner_live=False)
    assert not resumable(paused, "u_narrow", owner_live=True)
    assert not resumable(an_automation(owner="u_admin"), "u_admin", owner_live=True)


def test_a_schedule_change_is_gated_whether_it_runs_or_not_and_leaves_a_paused_one_paused() -> None:
    """Delete this and the owner could move when their own automation runs unwatched, or a
    schedule change could resume a paused automation nobody approved."""
    running = an_automation(next_run_at=RUNNING)
    assert may_reschedule(running, reach("u_admin"), becomes=MONDAYS, removed=False, now=NOW)
    assert may_reschedule(
        an_automation(), reach("u_admin"), becomes=MONDAYS, removed=False, now=NOW
    )
    assert not may_reschedule(running, reach("u_narrow"), becomes=MONDAYS, removed=False, now=NOW)
    assert not may_reschedule(running, reach("u_prefix"), becomes=MONDAYS, removed=False, now=NOW)
    own = an_automation(owner="u_admin", next_run_at=RUNNING)
    assert not may_reschedule(own, reach("u_admin"), becomes=MONDAYS, removed=False, now=NOW)
    assert rescheduled_next_run(running, becomes=MONDAYS, now=NOW) == next_run_after(MONDAYS, NOW)
    assert rescheduled_next_run(an_automation(), becomes=MONDAYS, now=NOW) is None


def test_only_an_ownerless_automation_is_adopted_and_only_by_somebody_who_could_install_it() -> (
    None
):
    """Delete this and a running automation could be taken from a person who is still here, or
    adopted by somebody with no authority over its agent, who would lend it a reach nobody chose."""
    gone = an_automation(owner="u_gone")
    assert may_adopt(gone, reach("u_admin"), removed=False, owner_live=False, now=NOW)
    assert not may_adopt(gone, reach("u_admin"), removed=False, owner_live=True, now=NOW)
    assert not may_adopt(gone, reach("u_elsewhere"), removed=False, owner_live=False, now=NOW)
    assert not may_adopt(gone, reach("u_prefix"), removed=False, owner_live=False, now=NOW)
    assert not may_adopt(gone, reach("u_admin"), removed=True, owner_live=False, now=NOW)


def test_the_confirmation_moves_with_the_owner_the_cadence_the_next_run_and_removal() -> None:
    """Delete this and a pause confirmed over an automation that was adopted in the meantime would
    be written against the new owner nobody was shown."""
    one = an_automation()
    base = shown(one, cadence=QUESTIONS.cadence, removed=False)
    assert base == shown(an_automation(), cadence=QUESTIONS.cadence, removed=False)
    assert base != shown(an_automation(owner="u_admin"), cadence=QUESTIONS.cadence, removed=False)
    assert base != shown(one, cadence=MONDAYS, removed=False)
    assert base != shown(
        an_automation(next_run_at=RUNNING), cadence=QUESTIONS.cadence, removed=False
    )
    assert base != shown(one, cadence=QUESTIONS.cadence, removed=True)
