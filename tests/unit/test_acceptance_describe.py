"""The describe-an-agent check: registered, passing on a real schema, and able to fail (M20.5.3).

The breaks put back a route that works with its switch off, one that applies what the model said
before anybody took it, one that suggests what an agent may reach, and one that says nothing about
what it did not draft.

Task ids: M20.5.3
"""

from __future__ import annotations

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

MODULE = "brain.ops.acceptance_checks_describe"
NAME = "describing_an_agent_starts_a_draft_and_applies_nothing"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_describe_check_is_listed_with_the_leaf_it_proves() -> None:
    """The one check this module registers, naming M20.5.3 alone and found by the suite, with a
    sentence that fits the Install page. Delete this and the check can drop out of its module or
    close a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M20.5.3",)
    assert len(mine()[NAME].sentence) <= SENTENCE_CHARS


def test_every_reason_the_describe_check_can_give_is_a_named_literal_that_fits_the_page() -> None:
    """Each failure sentence is a module constant that fits the result's column. Delete this and a
    reason can be cut off on the page, or built from a row the check read."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_describe as module

    reasons = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "CheckFailedError":
            [argument] = node.args
            assert isinstance(argument, ast.Name)
            reasons.append(getattr(module, argument.id))
    assert len(set(reasons)) == 7
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


def hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted profile, so the stand-in is planned. No provider key is held."""
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")


@pytest.mark.needs_db
def test_on_a_real_database_a_description_starts_a_draft_and_nothing_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The check as the worker runs it.** It passes over the install's own executor with a
    stand-in answering, and the drafts, people and switch it made are gone. Delete this and
    describing can stop working on an install with nothing saying so."""
    hosted(monkeypatch)
    with at_head("brain_acceptance_describe") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _works_while_off(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    async def always(sessions: Any) -> bool:
        return True

    monkeypatch.setattr(routes, "describe_is_on", always)


def _applies_what_the_model_said(monkeypatch: pytest.MonkeyPatch) -> None:
    """The persona is taken into the draft as the answer returns, with nobody having chosen it."""
    import json

    import brain.agent_coauthor_routes as coauthor
    from brain.agent_coauthor_routes import HunkSent, SuggestionTaken, take_suggestions

    real = coauthor.suggest_changes

    async def applying(request: Any, draft_id: str, body: Any, asked: Any) -> Any:
        answered = await real(request, draft_id, body, asked)
        proposal = json.loads(bytes(answered.body))
        await take_suggestions(
            request,
            draft_id,
            SuggestionTaken(
                revision=proposal["revision"],
                base_digest=proposal["base_digest"],
                hunks=[
                    HunkSent(path=one["path"], before=one["before"], after=one["after"])
                    for one in proposal["hunks"]
                ],
                take=["persona"],
            ),
            asked,
        )
        return answered

    monkeypatch.setattr("brain.agent_describe_routes.suggest_changes", applying)


def _says_nothing_of_what_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_describe_routes as routes

    monkeypatch.setattr(routes, "NOT_DRAFTED", ())


def _no_withheld_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.builder.coauthor as coauthor

    monkeypatch.setattr(coauthor, "path_refusal", lambda path: None)


BREAKS: dict[str, tuple[Any, str]] = {
    "works_while_off": (_works_while_off, "MADE_WHILE_OFF"),
    "applies_untaken": (_applies_what_the_model_said, "NOT_STARTED"),
    "says_nothing": (_says_nothing_of_what_is_missing, "NOT_SAID"),
    "reach_not_withheld": (_no_withheld_paths, "NOT_SUGGESTED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_describe_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Four breaks, each failing with its own sentence: the switch ignored, the answer applied
    before anybody took it, the account of what was not drafted gone, and a change to what an agent
    may reach no longer withheld. Delete this and the check can pass with any of them."""
    import brain.ops.acceptance_checks_describe as module

    hosted(monkeypatch)
    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_describe_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
