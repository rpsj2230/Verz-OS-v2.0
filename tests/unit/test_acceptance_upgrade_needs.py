"""The upgrade-needs acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: an agent
behind a version that declares a tool, a connector and a question this install cannot hold is
reviewed and accepted through the routes' own functions, and a second agent behind a version that
needs nothing is accepted too. Then it runs the check against the product broken where it proves:
a review that names no new question, an acceptance that leaves the agent running, one that does
not say what is missing, a review that invents needs, an acceptance that does not move the pin and
one that is refused. Each fails with its own sentence.

Task ids: M13.8.11
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import (
    FAILED,
    PASSED,
    REASON_CHARS,
    SENTENCE_CHARS,
    Check,
    check_modules,
    registered,
)
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_upgrade_needs"
NAME = "accepting_a_version_runs_the_checks_an_install_runs"
#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("agent.agent", "agent.template_version", "agent.template_instance")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


def test_the_upgrade_needs_check_is_registered_with_the_leaf_it_proves() -> None:
    """One leaf, which the work breakdown holds. Delete this and the check can close a leaf it
    does not exercise or name an id no task has."""
    assert mine()[NAME].leaves == ("M13.8.11",)
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert "M13.8.11" in {one for module in wbs["modules"] for one in module["leaf_ids"]}


def test_the_upgrade_needs_check_is_listed_in_its_page_order() -> None:
    """The one check this module registers, found by the suite. Delete this and the check can drop
    out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()


def test_the_check_s_sentence_and_every_reason_it_can_give_fit_the_page() -> None:
    """The sentence fits the Install page's column and every reason is a named literal that fits
    the result's. Delete this and a reason can be cut off mid-word on the page."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_upgrade_needs as module

    assert len(mine()[NAME].sentence) <= SENTENCE_CHARS
    reasons = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {
            "CheckFailedError",
            "CheckNotRunError",
        }:
            [argument] = node.args
            value = (
                getattr(module, argument.id)
                if isinstance(argument, ast.Name)
                else ast.literal_eval(argument)
            )
            reasons.append(value)
    assert len(reasons) >= 7
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


@pytest.mark.needs_db
def test_on_a_real_database_an_accepted_version_is_checked_as_an_install_is_and_nothing_stays() -> (
    None
):
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the agents,
    versions and instances hold what they held before. Delete this and the upgrade can stop
    running the install's checks with nothing on the owner's install saying so, or a check that
    commits an agent can reach his server."""
    with at_head("brain_acceptance_upgrade_needs") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _fails_with(name: str, reason: str, url_name: str) -> None:
    import brain.ops.acceptance_checks_upgrade_needs as module

    with at_head(url_name) as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason)), name


@pytest.mark.needs_db
def test_a_review_that_names_no_new_question_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The review and the acceptance not seeing a question the version adds. Delete this and a
    version can ask something new and run on a blank, with the page saying nothing is needed."""
    import brain.agents.upgrade as upgrade

    monkeypatch.setattr(upgrade, "newly_required_placeholders", lambda reviewed: ())
    _fails_with("a new question", "NOT_NAMED", "brain_acceptance_upgrade_needs_question")


@pytest.mark.needs_db
def test_an_acceptance_that_leaves_the_agent_running_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The acceptance reporting the upgraded agent complete, so it is left switched on. Delete
    this and an agent can run on a tool, a connector and a question nothing here provides."""
    import dataclasses

    from brain.agents.install import Completeness, InstallBadge
    from brain.agents.upgrade import accept as real

    def ready(*args: Any, **kwargs: Any) -> Any:
        return dataclasses.replace(
            real(*args, **kwargs), completeness=Completeness(badge=InstallBadge.READY, missing=())
        )

    monkeypatch.setattr("brain.agent_upgrade_routes.accept", ready)
    _fails_with("left running", "LEFT_RUNNING", "brain_acceptance_upgrade_needs_running")


@pytest.mark.needs_db
def test_an_acceptance_that_does_not_say_what_is_missing_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The answer to an accepted version carrying no list, though the agent was switched off.
    Delete this and a person finds the agent off and is told nothing about why."""
    import brain.agent_upgrade_routes as routes

    real = routes.need_views
    calls = itertools.count()

    def silent_after(found: Any) -> Any:
        # The first call is the review's; the second is the acceptance's answer.
        return real(found) if next(calls) == 0 else []

    monkeypatch.setattr(routes, "need_views", silent_after)
    _fails_with("not told", "NOT_TOLD", "brain_acceptance_upgrade_needs_told")


@pytest.mark.needs_db
def test_a_review_that_invents_needs_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The review naming something missing for a version that needs nothing. Delete this and the
    page lists needs for every version, which a person learns to ignore."""
    from brain.agents.install import Completeness, InstallBadge, Missing, MissingKind
    from brain.agents.upgrade import needs_after as real

    calls = itertools.count()

    def invented(*args: Any, **kwargs: Any) -> Any:
        if next(calls) == 0:
            return real(*args, **kwargs)
        return Completeness(
            badge=InstallBadge.INCOMPLETE, missing=(Missing(kind=MissingKind.TOOL, name="x.read"),)
        )

    monkeypatch.setattr("brain.agent_upgrade_routes.needs_after", invented)
    _fails_with(
        "invented", "NEEDS_WHEN_NOTHING_IS_NEEDED", "brain_acceptance_upgrade_needs_made_up"
    )


@pytest.mark.needs_db
def test_an_acceptance_that_switches_off_an_agent_that_needs_nothing_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second acceptance leaving the agent incomplete though nothing is missing. Delete this
    and the guard above is satisfied by an upgrade that switches every agent off."""
    import dataclasses

    from brain.agents.install import Completeness, InstallBadge, Missing, MissingKind
    from brain.agents.upgrade import accept as real

    calls = itertools.count()

    def off(*args: Any, **kwargs: Any) -> Any:
        upgraded = real(*args, **kwargs)
        if next(calls) == 0:
            return upgraded
        return dataclasses.replace(
            upgraded,
            completeness=Completeness(
                badge=InstallBadge.INCOMPLETE,
                missing=(Missing(kind=MissingKind.TOOL, name="x.read"),),
            ),
        )

    monkeypatch.setattr("brain.agent_upgrade_routes.accept", off)
    _fails_with("switched off", "SWITCHED_OFF_WITHOUT_NEED", "brain_acceptance_upgrade_needs_off")


@pytest.mark.needs_db
def test_an_acceptance_that_does_not_move_the_agent_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The store reporting a write it did not make. Delete this and an upgrade that moves nothing
    reads as done."""
    from brain.agent_upgrade_routes import StoredAgentUpgrades

    async def pretend(self: Any, *args: Any, **kwargs: Any) -> bool:
        del self, args, kwargs
        return True

    monkeypatch.setattr(StoredAgentUpgrades, "accept", pretend)
    _fails_with("not moved", "NOT_MOVED", "brain_acceptance_upgrade_needs_stay")


@pytest.mark.needs_db
def test_an_acceptance_the_route_refuses_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The store losing every race, so the route answers that nothing was changed. Delete this and
    an administrator who cannot accept a version reads as a check that passed."""
    from brain.agent_upgrade_routes import StoredAgentUpgrades

    async def lose(self: Any, *args: Any, **kwargs: Any) -> bool:
        del self, args, kwargs
        return False

    monkeypatch.setattr(StoredAgentUpgrades, "accept", lose)
    _fails_with("refused", "NOT_ACCEPTED", "brain_acceptance_upgrade_needs_refused")
