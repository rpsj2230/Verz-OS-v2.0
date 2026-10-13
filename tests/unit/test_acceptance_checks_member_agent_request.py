"""The member agent request install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.2.2.5
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_agent_request"
REQUEST = "a_member_asks_the_department_for_an_agent_they_cannot_run_yet"


def test_the_module_declares_its_leaf_and_sits_in_its_range() -> None:
    """One check closing M40.2.2.5 inside the range this package was given. Delete this and the
    check can lose its leaf with the page showing the same row, or share a key with another."""
    from brain.ops import acceptance_checks_member_agent_request as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(REQUEST, ("M40.2.2.5",))]
    assert checks_in(MODULE) == [REQUEST]
    assert 1900 <= module.CHECK_ORDER <= 1999


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_request") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str) -> str:
    [(outcome, reason)] = run(url).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_request_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits a request, ships."""
    before = counts(install)
    assert run(install) == {REQUEST: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_agent_the_member_could_already_run_asked_for_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The already-runnable refusal dropped. Delete this and M40.2.2.5 closes on a form that files
    a decision about access somebody already has."""
    from brain import member_agent_request_routes as routes

    def anything_visible(agent_id: str, records: Any, **kwargs: Any) -> Any:
        from brain.member_activity import AgentRequest, MemberError

        found = next((one for one in records if one.agent_id == agent_id), None)
        if found is None:
            raise MemberError("no such agent")

        return AgentRequest(
            agent_id=agent_id,
            requested_by=kwargs["principal_id"],
            department=found.audience.department or "x",
            at=kwargs["at"],
        )

    monkeypatch.setattr(routes, "request_agent", anything_visible)
    assert "answered differently" in _failed(install)


@pytest.mark.needs_db
def test_a_lead_told_every_time_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The once-only key dropped. Delete this and M40.2.2.5 closes on a lead told again for each
    press of the button."""
    from brain.ops.agent_request_store import StoredAgentRequests

    async def always_first(self: Any, one: Any) -> bool:
        return True

    monkeypatch.setattr(StoredAgentRequests, "record", always_first)
    assert _failed(install)
