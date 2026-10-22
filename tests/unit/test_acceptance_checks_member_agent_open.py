"""The member agent page install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.2.2.2, M40.2.2.3
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_agent_open"
OPENS = "a_member_opens_their_agent_and_sees_only_their_tabs"
OWN = "a_member_s_own_agent_in_their_reach_goes_out_on_their_word"


def test_the_module_declares_its_leaf_and_sits_in_its_range() -> None:
    """One check for each leaf inside the range this package was given. Delete this and a check
    can lose its leaf with the page showing the same row, or share a key with another."""
    from brain.ops import acceptance_checks_member_agent_open as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (OPENS, ("M40.2.2.2",)),
        (OWN, ("M40.2.2.3",)),
    ]
    assert checks_in(MODULE) == [OPENS, OWN]
    assert 1900 <= module.CHECK_ORDER <= 1999


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_agent_open") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str, which: str = OPENS) -> str:
    outcome, reason = run(url)[which]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_agent_page_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits an agent, ships."""
    before = counts(install)
    assert run(install) == {OPENS: (PASSED, ""), OWN: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_page_that_shows_every_tab_to_a_member_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The strip no longer follows the reader's grants. Delete this and M40.2.2.2 closes on a page
    that shows a member the tabs and the Profile of their agent that an administrator's grant
    alone should open."""
    from brain import agent_routes
    from brain.console.workspace import TABS

    def everything(entitlement: Any, *, populated: Any = (), now: Any = None) -> Any:
        return TABS

    monkeypatch.setattr(agent_routes, "tab_strip", everything)
    assert "tab or a block they hold no grant for" in _failed(install)


@pytest.mark.needs_db
def test_a_page_that_shows_a_member_holding_the_grant_no_tab_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive sibling: a strip that is always empty. Delete this and a page refusing every
    tab to everyone satisfies the check that only looks for tabs shown by mistake."""
    from brain import agent_routes

    def nothing(entitlement: Any, *, populated: Any = (), now: Any = None) -> Any:
        return ()

    monkeypatch.setattr(agent_routes, "tab_strip", nothing)
    assert "Settings grant was not shown" in _failed(install)


@pytest.mark.needs_db
def test_a_page_that_opens_a_colleague_s_agent_to_a_grant_holder_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audience stops deciding before the grant does. Delete this and M40.2.2.2 closes on a
    page where holding the Settings grant opens somebody else's personal agent."""
    from brain import agent_routes

    def everyone(records: Any, viewer: Any) -> Any:
        return frozenset(one.agent_id for one in records)

    monkeypatch.setattr(agent_routes, "visible_agent_ids", everyone)
    assert "refused differently" in _failed(install)


@pytest.mark.needs_db
def test_an_agent_within_its_authors_reach_that_waits_fails_the_own_agent_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exemption removed, so every capability a personal agent names waits for a second
    person. Delete this and M40.2.2.3 closes on a builder that still asks somebody before a person
    may have the agent they asked for."""
    from brain import agent_builder_routes

    monkeypatch.setattr(agent_builder_routes, "_owners_own_within_their_reach", lambda *a: False)
    assert "was not published at once" in _failed(install, OWN)


@pytest.mark.needs_db
def test_an_agent_beyond_its_authors_reach_that_publishes_fails_the_own_agent_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exemption widened to every personal agent. Delete this and M40.2.2.3 closes on a
    builder that publishes a ceiling wider than its author's reach on that author's word."""
    from brain import agent_builder_routes

    monkeypatch.setattr(agent_builder_routes, "_owners_own_within_their_reach", lambda *a: True)
    assert "was not held" in _failed(install, OWN)


@pytest.mark.needs_db
def test_a_colleague_who_can_open_a_members_own_agent_fails_the_own_agent_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audience stops deciding, so a colleague opens the agent a member published on their own
    word. Delete this and M40.2.2.3 closes on an agent published at once that anybody can open."""
    from brain import agent_routes

    def everyone(records: Any, viewer: Any) -> Any:
        return frozenset(one.agent_id for one in records)

    monkeypatch.setattr(agent_routes, "visible_agent_ids", everyone)
    assert "a colleague opened a member's own agent" in _failed(install, OWN)
