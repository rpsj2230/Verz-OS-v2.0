"""The card-changes install check: what it names, passing on PostgreSQL and leaving nothing, and
made to fail with the product broken where each statement of its sentence rests.

The database half builds PostgreSQL at head and runs the module as the worker does. Each failure is
a single product defect, injected by replacing the function the check's readers call, and the check
must fail with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M19.7.2, M19.9.2
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_checks_browser_changes as module
from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser_changes"
CHECK = "a_card_says_what_changed_since_the_last_approved_run"


def test_the_module_declares_the_check_and_the_leaves_it_names() -> None:
    """Delete this and the check can lose a leaf with the page showing the same row, or sit
    outside the keys this package was given, where it would collide with another package's."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (CHECK, ("M19.7.2", "M19.9.2"))
    ]
    assert checks_in(MODULE) == [CHECK]
    assert 2300 <= module.CHECK_ORDER <= 2399


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser_changes") as url:
        yield url


@pytest.fixture(autouse=True)
def _install_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def outcome(url: str) -> tuple[str, str]:
    return run_checks(url, registered((MODULE,)))[CHECK]


def fails_with(install: str, sentence: str) -> None:
    result = outcome(install)
    assert result[0] == FAILED and result[1] == sentence, result


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing_it_wrote(install: str) -> None:
    """**The module as the worker runs it.** It passes, and no table the suite counts holds a row
    it wrote. Delete this and a check that cannot pass on the real schema, or one that commits a
    run or a card to a client's install, reaches the owner first."""
    before = counts(install)

    assert outcome(install) == (PASSED, "")
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_lookup_that_finds_nothing_says_first_for_every_card_and_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a driver that stopped reading the last approved run, so every card says it
    is the first, passes."""
    from brain.browsing import driver

    async def none(session: Any, *, asked_by: str, agent_id: str, target: str) -> None:
        return None

    monkeypatch.setattr(driver, "last_approved_parts", none)

    fails_with(install, module.A_REPEAT_WAS_REPORTED_AS_A_CHANGE)


@pytest.mark.needs_db
def test_a_lookup_that_reads_any_run_and_not_only_an_approved_one_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a card compared with a run nobody approved passes. The pending run is the
    newest, so a lookup that ignores the state returns it."""
    from sqlalchemy import select

    from brain.browsing import driver
    from brain.tables.browsing import BrowserEnvelopeRow

    async def newest(session: Any, *, asked_by: str, agent_id: str, target: str) -> Any:
        result = await session.execute(
            select(BrowserEnvelopeRow.__table__)
            .where(
                BrowserEnvelopeRow.asked_by == asked_by,
                BrowserEnvelopeRow.agent_id == agent_id,
                BrowserEnvelopeRow.target == target,
            )
            .order_by(BrowserEnvelopeRow.run_id.desc())
            .limit(1)
        )
        row = result.mappings().one_or_none()
        return None if row is None else dict(row["sealed"])

    monkeypatch.setattr(driver, "last_approved_parts", newest)

    fails_with(install, module.A_PENDING_RUN_WAS_COMPARED_WITH)


@pytest.mark.needs_db
def test_a_lookup_that_reads_another_askers_history_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a person's first card compared with a run somebody else asked for passes."""
    from brain.browsing import driver
    from brain.browsing.envelope_store import last_approved_parts

    async def anyones(session: Any, *, asked_by: str, agent_id: str, target: str) -> Any:
        from sqlalchemy import select

        from brain.tables.browsing import BrowserEnvelopeRow

        del asked_by
        result = await session.execute(
            select(BrowserEnvelopeRow.asked_by)
            .where(BrowserEnvelopeRow.agent_id == agent_id, BrowserEnvelopeRow.target == target)
            .limit(1)
        )
        asker = result.scalar_one_or_none()
        if asker is None:
            return None
        return await last_approved_parts(session, asked_by=asker, agent_id=agent_id, target=target)

    monkeypatch.setattr(driver, "last_approved_parts", anyones)

    fails_with(install, module.ANOTHER_PERSONS_HISTORY_WAS_READ)


@pytest.mark.needs_db
def test_a_card_that_always_says_nothing_differs_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a difference that is computed as empty for everyone, first card included,
    passes."""
    from brain.browsing import approval

    monkeypatch.setattr(
        approval, "envelope_changes", lambda previous, envelope: approval.NOTHING_CHANGED
    )

    fails_with(install, module.THE_FIRST_CARD_WAS_NOT_THE_FIRST)


@pytest.mark.needs_db
def test_a_card_that_never_names_what_was_added_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a difference that reports no addition passes the repeat and the first."""
    from brain.browsing import approval

    real = approval.envelope_changes

    def blind(previous: Any, envelope: Any) -> str:
        said = real(previous, envelope)
        return approval.NOTHING_CHANGED if said.startswith("since the last approved run") else said

    monkeypatch.setattr(approval, "envelope_changes", blind)

    fails_with(install, module.A_NEW_WRITE_WAS_NOT_REPORTED)


@pytest.mark.needs_db
def test_a_card_that_says_first_for_a_repeat_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a card that says every run is the first passes the first card's check."""
    from brain.browsing import approval

    monkeypatch.setattr(
        approval, "envelope_changes", lambda previous, envelope: approval.FIRST_APPROVAL
    )

    fails_with(install, module.A_REPEAT_WAS_REPORTED_AS_A_CHANGE)
