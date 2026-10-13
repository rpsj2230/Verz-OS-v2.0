"""The member preference install checks, each passing on PostgreSQL at head and each failing.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_preferences"
LEARNING = "a_person_who_switches_learning_off_has_nothing_more_formed"
REACH = "a_person_chooses_where_they_are_reached_and_it_is_kept_whole"
DIGEST = "a_digest_is_held_by_quiet_hours_and_by_a_channel_that_omits_it"
APPROVAL = "an_approver_who_chose_the_console_is_sent_no_card"


def test_the_module_declares_the_leaves_each_flow_proves() -> None:
    """Four checks, each closing the leaves its flow exercises. Delete this and a leaf can lose
    its check with the page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (LEARNING, ("M40.4.1.4",)),
        (REACH, ("M40.5.2.1", "M40.5.2.2")),
        (DIGEST, ("M40.5.2.4",)),
        (APPROVAL, ("M40.5.2.3",)),
    ]
    assert checks_in(MODULE) == [LEARNING, REACH, DIGEST, APPROVAL]


def test_the_module_places_itself_inside_its_range() -> None:
    """Held to the range this package was given. Delete this and two modules can share a key."""
    from brain.ops import acceptance_checks_member_preferences as module

    assert 1900 <= module.CHECK_ORDER <= 1999


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_preferences") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str, *names: str) -> dict[str, tuple[str, str]]:
    return run_check(url, [one for one in registered((MODULE,)) if not names or one.name in names])


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_member_preference_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: all four pass and nothing is left behind. Delete this and
    a check that cannot pass on a real schema, or one that commits a setting, ships."""
    before = counts(install)
    outcomes = run(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 4
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_person_learnt_from_after_switching_it_off_fails_the_learning_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The opt-out ignored where a memory is formed. Delete this and M40.4.1.4 closes on a switch
    that changes a row and nothing else."""
    from brain.member.preferences import parse
    from brain.ops import memory_store

    async def nobody_opts_out(session: Any, ids: Any) -> Any:
        return {one: parse(one, {}) for one in ids}

    monkeypatch.setattr(memory_store, "preferences_in", nobody_opts_out)
    assert "switched learning off" in _failed(install, LEARNING)


@pytest.mark.needs_db
def test_a_setting_kept_for_a_channel_nobody_is_bound_on_fails_the_reach_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every channel treated as bound. Delete this and M40.5.2.1 closes on a primary nobody
    proved, which fails on the first message."""
    from brain import member_preference_routes
    from brain.gate.context import Channel

    async def all_of_them(request: Any, principal_id: str) -> Any:
        return tuple(Channel)

    monkeypatch.setattr(member_preference_routes, "_bound", all_of_them)
    assert _failed(install, REACH)


@pytest.mark.needs_db
def test_a_digest_sent_inside_quiet_hours_fails_the_held_digest_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing ever holding a message back. Delete this and M40.5.2.4 closes on hours that are
    kept and never honoured."""
    from brain import tell_later

    monkeypatch.setattr(tell_later, "held_by", lambda *args, **kwargs: None)
    assert "quiet hours" in _failed(install, DIGEST)


@pytest.mark.needs_db
def test_a_card_sent_to_an_approver_who_chose_the_console_fails_the_approval_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The choice not read where cards are sent. Delete this and M40.5.2.3 closes on a routing
    preference that routes nothing."""
    from brain.member.preferences import Preferences

    monkeypatch.setattr(Preferences, "lets_an_approval_go_to", lambda self, channel: True)
    assert "chose the console" in _failed(install, APPROVAL)
