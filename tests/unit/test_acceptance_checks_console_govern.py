"""The install checks for what governance says about refusals, passing on PostgreSQL at head,
leaving nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.3.11, M27.13.6
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_govern"
FRICTION = "refusals_are_shown_by_shape_and_the_canaries_last_run_is_shown"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The check and the leaves it closes. Delete this and a check can lose a leaf, or gain one it
    does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        FRICTION: ("M27.3.11", "M27.13.6")
    }
    assert checks_in(MODULE) == [FRICTION]


def test_the_authority_the_check_holds_is_the_routes_own() -> None:
    """The evaluation read the check's reader holds, held against the Quality screen's own. Delete
    this and a renamed authority fails the check on every install with nothing wrong."""
    from brain.console.screens import screen
    from brain.ops.acceptance_checks_console_govern import READS_EVALUATION

    assert screen("quality").read.requires.value == READS_EVALUATION


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_govern") as url:
        yield url


def _failed(url: str) -> str:
    outcome, reason = run_module(url, MODULE)[FRICTION]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no person, grant, ledger entry or
    canary run. Delete this and a check that commits, or one that cannot pass on a real schema,
    reaches the owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {FRICTION: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_pattern_that_names_the_person_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refusal shapes that carry the person's name. Delete this and M27.3.11 closes on a screen
    that says who keeps hitting a boundary."""
    from brain import audit_statistics_routes as routes

    real = routes.RefusalShapeView

    def naming(*, shape: str, reads_as: str, occurrences: int) -> object:
        return real(shape=shape, reads_as=f"{reads_as} acceptance.", occurrences=occurrences)

    monkeypatch.setattr(routes, "RefusalShapeView", naming)
    assert "words the product does not hold" in _failed(install)
