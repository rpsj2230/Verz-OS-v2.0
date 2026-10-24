"""The mover memory install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M26.2.5
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_mover_memory"
MOVER = "a_mover_is_not_told_the_memories_of_the_reach_they_left"


def test_the_module_declares_its_leaf_and_runs_before_the_roll_ups_that_read_it() -> None:
    """One check closing M26.2.5, placed before the roll-ups that wait for it. Delete this and the
    check can lose its leaf with the page showing the same row, or sit after the roll-up, which
    then reads nothing of it and stays not run for ever."""
    from brain.ops import acceptance_checks_jml_roll_up as roll_up
    from brain.ops import acceptance_checks_mover_memory as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(MOVER, ("M26.2.5",))]
    assert checks_in(MODULE) == [MOVER]
    assert module.CHECK_ORDER < roll_up.CHECK_ORDER
    assert roll_up.CLAUSES["a mover's memories of the old reach are not replayed"] == ("M26.2.5",)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_mover_memory") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str) -> str:
    outcome, reason = run(url)[MOVER]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_mover_memory_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits a memory, ships."""
    before = counts(install)
    assert run(install) == {MOVER: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_recall_that_ignores_where_a_memory_was_formed_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recall compares capability names and not the place they were held over. Delete this and
    M26.2.5 closes on a recall that shows a mover the old department's memory in the new one, which
    is the disclosure the leaf exists to prevent."""
    from brain.memory import formation

    real = formation.requirement

    def by_name_only(one: Any) -> Any:
        wide = real(one)
        return wide.model_copy(
            update={
                "grants": tuple(
                    grant.model_copy(update={"scope": type(grant.scope).unrestricted()})
                    for grant in wide.grants
                )
            }
        )

    monkeypatch.setattr(formation, "requirement", by_name_only)
    reason = _failed(install)
    assert "still shown a memory" in reason or "still be told a mover's memory" in reason


@pytest.mark.needs_db
def test_a_move_that_deletes_the_memory_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive sibling: after the move the person's memories are gone from the tables. Delete
    this and a mover who is told nothing because everything was purged satisfies the check that
    only looks at what is shown."""
    from brain.ops import acceptance_checks_memory as memory

    real = memory.memories_of
    asked: list[int] = []

    async def purged_after_the_first_look(h: Any, principal_id: str) -> Any:
        asked.append(1)
        return await real(h, principal_id) if len(asked) == 1 else []

    monkeypatch.setattr(memory, "memories_of", purged_after_the_first_look)
    assert "rewrote or removed a memory" in _failed(install)


def _on_the_nth_call(module: Any, name: str, which: int, replacement: Any) -> Any:
    """Wrap `module.name` so that its `which`th call (counting from one) answers `replacement`."""
    real = getattr(module, name)
    calls: list[int] = []

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) == which:
            return replacement
        return await real(*args, **kwargs)

    return wrapped


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("name", "which", "replacement", "sentence"),
    [
        ("shown_about", 2, "stale", "still shown a memory"),
        ("shown_about", 3, {}, "not shown again"),
        ("memories_of", 3, [], "changed across a move"),
    ],
)
def test_each_reading_the_check_makes_across_the_move_is_held_to_what_it_should_say(
    install: str,
    issuer: None,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    which: int,
    replacement: Any,
    sentence: str,
) -> None:
    """The Memory screen's reading is stale after the move, the memory is not shown again once the
    move is undone, and the row differs after the undo. Delete this and any one of those three
    readings can be dropped from the check while the check goes on passing."""
    from brain.ops import acceptance_checks_memory as memory

    if replacement == "stale":
        real = memory.shown_about
        seen: list[dict[str, float]] = []

        async def stale(*args: Any, **kwargs: Any) -> dict[str, float]:
            found = await real(*args, **kwargs)
            seen.append(found)
            return seen[0] if len(seen) == 2 else found

        monkeypatch.setattr(memory, name, stale)
    else:
        monkeypatch.setattr(memory, name, _on_the_nth_call(memory, name, which, replacement))
    assert sentence in _failed(install)
