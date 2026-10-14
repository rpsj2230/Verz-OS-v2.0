"""The member share install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.3.3.3
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_share"
SHARE = "a_member_hands_a_file_to_a_colleague_who_can_already_open_it"


def test_the_module_declares_its_leaf_and_sits_in_its_range() -> None:
    """One check closing M40.3.3.3, inside the range this package was given. Delete this and the
    check can lose its leaf with the page showing the same row, or share a key with another."""
    from brain.ops import acceptance_checks_member_share as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(SHARE, ("M40.3.3.3",))]
    assert checks_in(MODULE) == [SHARE]
    assert 1900 <= module.CHECK_ORDER <= 1999


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_share") as url:
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
def test_the_share_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits a share, ships."""
    before = counts(install)
    assert run(install) == {SHARE: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_share_with_somebody_who_cannot_open_it_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The colleague's own reach not asked. Delete this and M40.3.3.3 closes on sharing that
    makes a file reachable by whoever is named."""
    from brain import member_share_routes
    from brain.member_library import Share

    def asks_nobody(one: Any, *, sharer: Any, colleague: Any, now: Any) -> Share:
        return Share(
            artifact_id=one.artifact_id,
            shared_by=sharer.principal_id,
            shared_with=colleague.principal_id,
            at=now,
        )

    monkeypatch.setattr(member_share_routes, "share", asks_nobody)
    assert "could not open it" in _failed(install)


@pytest.mark.needs_db
def test_a_share_that_is_itself_the_permission_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verdict at the read replaced by the existence of the row. Delete this and M40.3.3.3
    closes on a share that outlives the colleague's reach."""
    from brain import member_share_routes

    monkeypatch.setattr(member_share_routes, "open_share", lambda *args, **kwargs: True)
    assert "no longer reach" in _failed(install)
