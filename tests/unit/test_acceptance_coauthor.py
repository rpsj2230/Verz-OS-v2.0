"""The co-author's acceptance check: registered, passing on a real schema, and able to fail.

Task ids: M20.1.3
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_coauthor"
COAUTHOR = "the_coauthor_proposes_and_nothing_changes_until_taken"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted profile, so the stand-in is planned. No provider key is held."""
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")


def test_the_coauthor_check_is_listed_and_names_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of its module, or close a leaf it does not
    exercise, with the Install page simply listing one row fewer."""
    assert checks_in(MODULE) == [COAUTHOR]
    assert MODULE in check_modules()
    assert mine()[COAUTHOR].leaves == ("M20.1.3",)


@pytest.mark.needs_db
def test_on_a_real_database_the_coauthor_check_passes_and_leaves_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The check as the worker runs it on a hosted install, against PostgreSQL at head.** Delete
    this and the co-author could stop proposing through the install's executor with nothing there
    saying so."""
    hosted(monkeypatch)
    with at_head("brain_acceptance_coauthor") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {COAUTHOR: (PASSED, "")}
    assert after == before


def broken_and_run(monkeypatch: pytest.MonkeyPatch, label: str, setup: Any) -> Any:
    hosted(monkeypatch)
    setup(monkeypatch)
    with at_head(f"brain_acceptance_coauthor_{label}") as url:
        return run_checks(url, tuple(mine().values()))[COAUTHOR]


def _takes_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_coauthor_routes as routes
    from brain.builder.coauthor import accept as kept

    def all_of_it(store: Any, proposal: Any, paths: Any, **rest: Any) -> Any:
        return kept(store, proposal, [one.path for one in proposal.hunks], **rest)

    monkeypatch.setattr(routes, "accept", all_of_it)


def _no_withheld_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.builder.coauthor as coauthor

    monkeypatch.setattr(coauthor, "path_refusal", lambda path: None)


BREAKS: dict[str, tuple[Any, str]] = {
    "takes_everything": (_takes_everything, "TOOK_MORE"),
    "reach_not_withheld": (_no_withheld_paths, "NOT_PROPOSED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_coauthor_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: taking every proposed
    change when one was named, and a path that decides what an agent may reach proposed to its
    author. Delete this and the check can pass with either gone."""
    import brain.ops.acceptance_checks_coauthor as module

    setup, reason = BREAKS[broken]
    assert broken_and_run(monkeypatch, broken, setup) == (FAILED, getattr(module, reason))
