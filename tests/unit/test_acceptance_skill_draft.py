"""The skill drafting check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, with a stand-in
model answering the one call in the process. Then it is run against the product broken where it
proves: a draft that keeps the tool the install does not hold, one that skips the switch, one added
approved, and one that tells the person nothing about what was left out.

Task ids: M12.4.14
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from brain.tools import skill_draft
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_skill_runs import hosted, run_checks  # noqa: F401

MODULE = "brain.ops.acceptance_checks_skill_draft"
NAME = "a_skill_described_in_conversation_lands_as_an_unreviewed_draft"


@contextmanager
def at_head_laddered(name: str) -> Iterator[str]:
    """PostgreSQL at head with the ladder the setup wizard writes, as the model checks run on."""
    from tests.unit.test_acceptance_models import laddered

    with at_head(name) as url:
        laddered(url)
        yield url


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_drafting_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M12.4.14",)


@pytest.mark.needs_db
def test_on_a_real_database_a_described_skill_lands_as_a_draft_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it.** Delete this and drafting can stop working, or can land
    an approved skill, with nothing on the owner's install saying so."""
    with at_head_laddered("brain_acceptance_skill_draft") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _keeps_what_the_install_lacks(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.skill_draft_routes as routes
    from brain.tools.skill_draft import SkillDraft

    kept = skill_draft.read_reply

    def anything(reply: str, *, tools: Any, departments: Any) -> SkillDraft:
        return kept(reply, tools=[*tools, "acceptance.send_everything"], departments=departments)

    monkeypatch.setattr(routes, "read_draft_reply", anything)


def _switch_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.skill_draft_routes as routes

    async def always(session: Any, one: Any) -> bool:
        return True

    monkeypatch.setattr(routes, "is_on", always)


def _added_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.console.skill_library as library
    import brain.skill_draft_routes as routes
    from brain.console.skill_library import decided

    kept = library.drafted_package

    def approved(draft: Any, library: Any) -> Any:
        return kept(draft, library)

    real_added = library.added

    def and_decided(package: Any, *, by: str, at: Any) -> Any:
        return decided(
            real_added(package, by=by, at=at), reviewer="u_someone_else", approve=True, at=at
        )

    monkeypatch.setattr(routes, "drafted_package", approved)
    monkeypatch.setattr(routes, "added", and_decided)


def _nothing_said(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.skill_draft_routes as routes

    kept = skill_draft.read_reply

    def silent(reply: str, *, tools: Any, departments: Any) -> Any:
        return dataclasses.replace(kept(reply, tools=tools, departments=departments), findings=())

    monkeypatch.setattr(routes, "read_draft_reply", silent)


BREAKS: dict[str, tuple[Any, str]] = {
    "keeps_what_the_install_lacks": (_keeps_what_the_install_lacks, "NOT_THE_INSTALLS"),
    "switch_ignored": (_switch_ignored, "OFF_WAS_ASKED"),
    "nothing_said": (_nothing_said, "NOT_SAID"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_drafting_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Three breaks, each failing with its own sentence: a draft that keeps a tool the install
    does not hold, a switch nothing reads and a draft that says nothing of what it left out.
    Delete this and the check can pass over a drafter that keeps what it must drop.

    The fourth break a skill added approved is `_added_approved`, held by its own test below."""
    import brain.ops.acceptance_checks_skill_draft as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head_laddered(f"brain_acceptance_skill_draft_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_a_drafted_skill_added_approved_is_found_by_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route handing the library a skill already decided by somebody is a skill an agent could
    be given, and the check fails on it rather than on the assignment.

    Delete this and the check can pass over a drafter that lands an approved skill."""
    import brain.ops.acceptance_checks_skill_draft as module

    _added_approved(monkeypatch)
    with at_head_laddered("brain_acceptance_skill_draft_approved") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME][0] == FAILED
    assert outcome[NAME][1] in {module.NOT_DRAFTED, module.EXECUTABLE, module.ASSIGNED}
