"""The member account install checks, each passing on PostgreSQL at head and each failing.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.1.1.3, M40.4.2.4, M40.3.3.1, M40.4.2.1
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_account"
DEVICES = "a_member_sees_and_ends_their_own_sign_ins_and_nobody_elses"
READS = "a_member_sees_who_read_their_record_and_not_what_was_shown"
ARTIFACTS = "a_member_sees_what_agents_made_for_them_and_no_colleague_s"
STORED = "a_member_is_told_everywhere_data_about_them_is_kept"


def test_the_module_declares_one_check_per_page_and_names_its_leaf() -> None:
    """One check for each of the four pages, each closing its own leaf. Delete this and a check
    can lose its leaf with the page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (DEVICES, ("M40.1.1.3",)),
        (READS, ("M40.4.2.4",)),
        (ARTIFACTS, ("M40.3.3.1",)),
        (STORED, ("M40.4.2.1",)),
    ]
    assert checks_in(MODULE) == [DEVICES, READS, ARTIFACTS, STORED]


def test_the_module_places_itself_inside_its_range() -> None:
    """Held to the range this package was given. Delete this and two modules can share a key."""
    from brain.ops import acceptance_checks_member_account as module

    assert 1900 <= module.CHECK_ORDER <= 1999


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_account") as url:
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
def test_every_member_account_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: all four pass and nothing is left behind. Delete this and
    a check that cannot pass on a real schema, or one that commits a row, ships."""
    before = counts(install)
    outcomes = run(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 4
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_device_list_of_everybody_s_sign_ins_fails_the_devices_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The statement not narrowed by the person. Delete this and M40.1.1.3 closes on a list that
    shows a member every sign-in on the install."""
    from brain.identity import session_store

    monkeypatch.setattr(
        session_store,
        "live_sessions_of",
        lambda principal_id, now, limit: session_store.live_sessions(now, limit),
    )
    assert "exactly their own" in _failed(install, DEVICES)


@pytest.mark.needs_db
def test_ending_anybody_s_sign_in_fails_the_devices_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ownership question answered yes for every session. Delete this and a member can sign a
    colleague out with their session id."""
    from brain.identity.session_store import StoredSessions

    real = StoredSessions.end

    async def anybody(self: Any, session_id: str, *, may: Any, **kwargs: Any) -> Any:
        return await real(self, session_id, may=lambda one: True, **kwargs)

    monkeypatch.setattr(StoredSessions, "end", anybody)
    assert "not theirs" in _failed(install, DEVICES)


@pytest.mark.needs_db
def test_reads_listed_for_every_reader_fail_the_reads_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The subject narrowing dropped at the ledger and in the view, so a colleague is shown reads
    of somebody else's record. Delete this and M40.4.2.4 closes on a page that lists them."""
    from brain import audit_routes, member_self_routes
    from brain.member_activity import ReadsOfMyRecord, RecordRead

    real = audit_routes.ledger_of

    class Anybody:
        def __init__(self, ledger: Any) -> None:
            self._ledger = ledger

        async def window(self, criteria: Any, *, subject: Any = None, **kwargs: Any) -> Any:
            return await self._ledger.window(criteria, subject=None, **kwargs)

    def everybody(entries: Any, **kwargs: Any) -> Any:
        return ReadsOfMyRecord(
            subject_id="x",
            reads=tuple(RecordRead(one.at, one.actor_id, "", "personnel") for one in entries),
            next_cursor=None,
        )

    monkeypatch.setattr(member_self_routes, "ledger_of", lambda request: Anybody(real(request)))
    monkeypatch.setattr(member_self_routes, "who_read_my_record", everybody)
    assert "somebody else's record" in _failed(install, READS)


@pytest.mark.needs_db
def test_artifacts_made_for_anybody_fail_the_artifacts_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list not narrowed to the person. Delete this and M40.3.3.1 closes on a page that shows
    what was made for a colleague."""
    from brain import member_self_routes

    monkeypatch.setattr(
        member_self_routes, "produced_for_me", lambda entries, **kwargs: tuple(entries)
    )
    assert "every agent made for them" in _failed(install, ARTIFACTS)


@pytest.mark.needs_db
def test_a_store_left_off_the_page_fails_the_stored_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first store dropped from what the page iterates. Delete this and M40.4.2.1 closes on a
    page that says everything while leaving a place out."""
    from brain import member_self_routes

    class Fewer:
        def __iter__(self) -> Any:
            from brain.ops.retention import Store

            return iter(list(Store)[1:])

    monkeypatch.setattr(member_self_routes, "Store", Fewer())
    assert "left off" in _failed(install, STORED)
