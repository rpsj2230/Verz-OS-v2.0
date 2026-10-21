"""The member deletion install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.4.2.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_deletion"
ASKING = "a_member_asks_to_be_deleted_and_nothing_is_deleted_by_asking"


def test_the_module_declares_its_leaf_and_sits_where_it_was_placed() -> None:
    """One check closing M40.4.2.3, at the order this module was given. Delete this and the check
    can lose its leaf with the page showing the same row, or share a position."""
    from brain.ops import acceptance_checks_member_deletion as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(ASKING, ("M40.4.2.3",))]
    assert checks_in(MODULE) == [ASKING]
    assert module.CHECK_ORDER == 2790


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_deletion") as url:
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
def test_the_deletion_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits an ask, ships."""
    before = counts(install)
    assert run(install) == {ASKING: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_ask_that_files_an_erasure_in_the_queue_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ask filing straight into the queue the worker carries out. Delete this and M40.4.2.3
    closes on a button that is an erase."""
    from brain import member_deletion_routes
    from brain.ops.erasure_store import StoredErasures

    original = member_deletion_routes.deletion_requests_of

    def filing(request: Any) -> Any:
        real = original(request)
        sessions = request.app.state.db_sessions

        class Both:
            async def ask(self, subject_id: str, *, at: datetime) -> Any:
                made = await real.ask(subject_id, at=at)
                if made[1]:
                    await StoredErasures(sessions).file(
                        subject_id=subject_id,
                        reason_reference="SELF",
                        actor=subject_id,
                        ent_hash="",
                        trace_id="t",
                        at=at,
                    )
                return made

            def __getattr__(self, name: str) -> Any:
                return getattr(real, name)

        return Both()

    monkeypatch.setattr(member_deletion_routes, "deletion_requests_of", filing)

    assert "erasure" in _failed(install)


@pytest.mark.needs_db
def test_an_ask_taken_with_the_switch_off_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch ignored. Delete this and M40.4.2.3 closes on a capability that ships on."""
    from brain import member_deletion_routes

    async def always(request: Any) -> bool:
        return True

    monkeypatch.setattr(member_deletion_routes, "deletion_requests_are_on", always)

    assert "switch" in _failed(install)


@pytest.mark.needs_db
def test_a_waiting_list_shown_to_a_reader_without_the_authority_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority over everything not asked. Delete this and M40.4.2.3 closes on a list of who
    asked to be erased that any reader of the screen can read."""
    from brain import member_deletion_routes

    monkeypatch.setattr(member_deletion_routes, "may_erase", lambda reach, now: True)

    assert "authority" in _failed(install)
