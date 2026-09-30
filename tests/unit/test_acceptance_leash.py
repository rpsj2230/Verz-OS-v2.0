"""The leash acceptance check: registered, passing on a real schema, and able to fail.

The pure half holds the check to its leaf and holds the rungs it writes out against the registry's
own mapping, so the owner's reading of the rule and the code cannot drift apart unnoticed. The
database half builds PostgreSQL to head once and runs the check as the worker would: it passes and
leaves nothing behind. Then the check is run against the install broken once for each property its
sentence states: the run no longer held to what a tool's side effect allows, the hold applied to a
tool that only reads, the page shown the held leash instead of the configured one, and a run that
carries the configured leash to its steps. Each is a failed check with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M12.1.3, M38.5.1
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_tools import run_checks, tool_counts

MODULE = "brain.ops.acceptance_checks_tools"
LEASH = "a_tool_s_side_effect_holds_the_rung_an_agent_runs_at"


def the_check() -> Check:
    return {one.name: one for one in registered((MODULE,))}[LEASH]


# ------------------------------------------------------------------------ without a server
def test_the_leash_check_is_registered_for_the_side_effect_leaf() -> None:
    """The check names M12.1.3 and nothing else. Delete this and it can close a leaf it does not
    exercise, or stop naming the one it proves."""
    assert the_check().leaves == ("M12.1.3",)


def test_the_rungs_the_check_writes_out_are_the_registry_s_own() -> None:
    """`HELD_AT` is written out so a change to `default_rung` fails the check rather than moving
    with it; this holds the two together, so the day they disagree is a red test naming both,
    rather than an install check failing with nobody knowing which side changed. Every side effect
    but none is covered, so a sixth cannot arrive unheld. Delete this and the check can prove a
    rule the registry no longer applies."""
    from brain.core.envelope import SideEffect
    from brain.ops.acceptance_checks_tools import CONFIGURED, HELD_AT
    from brain.tools.registry import default_rung

    assert {effect for effect, _, _ in HELD_AT} == {one.value for one in SideEffect} - {"none"}
    for effect, _, rung in HELD_AT:
        assert default_rung(SideEffect(effect)).name.lower() == rung, effect
    assert default_rung(SideEffect.NONE).name.lower() == CONFIGURED


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for every run here; each check's writes are rolled back."""
    with at_head("brain_acceptance_leash") as url:
        yield url


@pytest.mark.needs_db
def test_on_a_real_database_the_leash_check_passes_and_leaves_nothing_behind(
    database: str,
) -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes with no reason,
    and the people, the grants, the ledger and the tool tables hold what they held before. Delete
    this and a check that cannot pass on the real schema reaches the owner's server first."""
    before = (counts(database), tool_counts(database))
    outcome = run_checks(database, (the_check(),))
    after = (counts(database), tool_counts(database))

    assert outcome == {LEASH: (PASSED, "")}
    assert after == before


def _unheld(self: Any, leash: Any) -> Any:
    """`ToolRegistry.tighten` doing nothing: the configured leash, unmoved, as before 2026-09-30."""
    del self
    return leash


def _held_everywhere(effect: Any) -> Any:
    """`default_rung` holding every tool at Assisted, reads included."""
    from brain.gate.injection import AutonomyTier

    del effect
    return AutonomyTier.ASSISTED


def _shown_held(install: Any, registry: Any) -> Any:
    """`leash_of` with the hold moved onto the page, which is where it must not be."""
    from brain.agents.install import bind_tools, bound_leash

    return registry.tighten(
        bound_leash(install.leash, bind_tools(install.declared_tools, registry))
    )


def _carrying_the_configured_leash() -> Callable[..., Any]:
    """`invoke` returning a run whose steps would be governed by the leash it was handed."""
    import brain.gate.invoke as gate_invoke

    real = gate_invoke.invoke

    def invoke(**kwargs: Any) -> Any:
        return dataclasses.replace(real(**kwargs), leash=kwargs["leash"])

    return invoke


def _registry_class() -> Any:
    from brain.tools.registry import ToolRegistry

    return ToolRegistry


def _module(name: str) -> Callable[[], Any]:
    import importlib

    return lambda: importlib.import_module(name)


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("owner", "attribute", "broken", "reason"),
    [
        (
            _registry_class,
            "tighten",
            lambda: _unheld,
            "a leash set to Autonomous on a tool that acts ran above the rung its side effect "
            "allows",
        ),
        (
            _module("brain.tools.registry"),
            "default_rung",
            lambda: _held_everywhere,
            "the install's own read tool set to Autonomous did not run Autonomous",
        ),
        (
            _module("brain.agent_routes"),
            "leash_of",
            lambda: _shown_held,
            "the leash an agent's page shows is not the one configured for it",
        ),
        (
            _module("brain.gate.invoke"),
            "invoke",
            _carrying_the_configured_leash,
            "a run carries a leash that lets a step on a tool that acts run above its side "
            "effect's rung",
        ),
    ],
    ids=["unheld", "reads_held", "page_shows_held", "steps_unheld"],
)
def test_the_leash_check_fails_when_the_install_breaks_what_it_says(
    monkeypatch: pytest.MonkeyPatch,
    database: str,
    owner: Callable[[], Any],
    attribute: str,
    broken: Callable[[], Any],
    reason: str,
) -> None:
    """The check shown able to fail, once per property it states: the run no longer held, the
    hold reaching a read, the page shown the held leash, and a run carrying the configured leash
    to its steps. Delete this and any of the four can go with the check still green."""
    monkeypatch.setattr(owner(), attribute, broken())
    outcome = run_checks(database, (the_check(),))

    assert outcome[LEASH] == (FAILED, reason)
