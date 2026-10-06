"""The skill-pin, model-pin and canary acceptance checks: registered, passing, and able to fail.

The database half builds PostgreSQL to head and runs the three checks as the worker would, with the
hosted profile so the model check plans its stand-ins, then runs each against the product broken
where it proves something: a run that follows an approved edit its agent was not pinned to
(M12.2.7), an executor that passes over an agent's pinned model (M5.7.3), a canary lane that tells
the asker holding nothing apart from an absence (M28.2.1), and a projection that offers every
persona every tool (M28.2.3). Each fails with its own sentence, and every table the checks write
holds afterwards what it held before.

Task ids: M12.2.7, M5.7.3, M28.2.1, M28.2.3, M13.2.5
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_hubspot import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_skill_pins"

SKILL = "each_agent_runs_the_skill_version_it_is_pinned_to"
MODEL = "an_agent_s_pinned_model_is_tried_first_with_its_level_behind"
CANARIES = "three_personas_are_told_one_absence_and_offered_their_own_tools"
KEYED = "an_assigned_skill_moves_the_key_an_answer_is_cached_under"

#: Each check, in page order, and the leaves it proves.
LEAVES = {
    SKILL: ("M12.2.7",),
    KEYED: ("M13.2.5",),
    MODEL: ("M5.7.3",),
    CANARIES: ("M28.2.1", "M28.2.3"),
}


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted profile, so the model check plans its stand-ins. No provider key is held."""
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")


def run_one(url: str, name: str) -> tuple[str, str]:
    return run_checks(url, (mine()[name],))[name]


def test_the_skill_pin_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task has,
    or M12.2.8 can be claimed here although no run on an install shows a skill's card."""
    assert {name: one.leaves for name, one in mine().items()} == LEAVES
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {one for named in LEAVES.values() for one in named} <= leaves
    assert "M12.2.8" not in {one for named in LEAVES.values() for one in named}


def test_the_skill_pin_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, from a module
    the suite finds. Delete this and a check can drop out of the module, or the module out of the
    suite, with the page simply listing fewer rows."""
    assert MODULE in check_modules()
    assert checks_in(MODULE) == list(LEAVES)


@pytest.mark.needs_db
def test_on_a_real_database_the_four_checks_pass_and_leave_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The four checks as the worker runs them on a hosted install, against PostgreSQL at
    head.** Each passes, and every table a check writes holds afterwards what it held before.
    Delete this and a version lock, a model pin or a canary could stop working on the owner's
    install with nothing there saying so."""
    hosted(monkeypatch)
    with at_head("brain_acceptance_skill_pins") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


@pytest.mark.needs_db
def test_on_an_install_keeping_text_at_home_the_model_check_is_not_run() -> None:
    """The local profile plans no stand-in, so the model check says it was not run rather than
    failing an install for keeping its text on its own hardware. Delete this and the full suite's
    own run, which has no hosted profile, could see the check fail instead."""
    with at_head("brain_acceptance_skill_pins_local") as url:
        outcome = run_one(url, MODEL)
    assert outcome == (
        NOT_RUN,
        "this install keeps text on its own hardware, so no provider is asked",
    )


@pytest.mark.needs_db
def test_a_run_that_follows_an_approved_edit_fails_the_version_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M12.2.7: a run handed the approved edit of a skill its agent is pinned to, rather than the
    pinned version, which is the procedure the agent was never tested with. The check fails at the
    first agent it asks about. Delete this and the version lock could follow every edit."""
    from brain.gate import model_lane

    def following(agent: Any, *, caller: Any, now: Any) -> tuple[Any, ...]:
        del caller, now
        handed = []
        for pin in agent.pins:
            rows = {one.digest: one for one in agent.library if one.name == pin.skill_name}
            newer = next(
                (
                    one
                    for one in rows.values()
                    if getattr(one, "edited_from", None) == pin.digest
                    and one.imported.is_executable()
                ),
                rows.get(pin.digest),
            )
            if newer is not None:
                handed.append(newer.imported)
        return tuple(handed)

    monkeypatch.setattr(model_lane, "skills_offered", following)
    with at_head("brain_acceptance_skill_pins_follows") as url:
        before = counts(url)
        outcome = run_one(url, SKILL)
        after = counts(url)
    assert outcome == (
        FAILED,
        "a run followed an approved edit its agent was not pinned to",
    )
    assert after == before


@pytest.mark.needs_db
def test_an_executor_that_passes_over_a_pin_fails_the_model_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M5.7.3: the executor finds no step for an agent's pin, so the agent answers from its level
    whatever an administrator pinned. The check fails at the pinned question. Delete this and a
    pin could be stored, shown and never tried."""
    from brain.models.calls import ModelCalls

    def passed_over(self: Any, *args: Any, **kwargs: Any) -> None:
        del self, args, kwargs

    hosted(monkeypatch)
    monkeypatch.setattr(ModelCalls, "_pinned", passed_over)
    with at_head("brain_acceptance_skill_pins_unpinned") as url:
        outcome = run_one(url, MODEL)
    assert outcome == (FAILED, "an agent's pinned model was not tried first")


@pytest.mark.needs_db
def test_a_refusal_told_apart_from_an_absence_fails_the_canaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M28.2.1: the lane adds a word for the asker holding nothing, so a refusal reads differently
    from an absence, which is DENIED and ABSENT come apart. The canaries' diff finds it and the
    check fails. Delete this and a canary run that compares nothing could stay green."""
    from brain.gate.answer import answer_lane as original
    from brain.ops import canary_run

    async def telling(question: str, **kwargs: Any) -> Any:
        answered = await original(question, **kwargs)
        if kwargs["entitlement"].principal_id == canary_run.NOBODY:
            frames: Sequence[str] = (*answered.frames, "event: text\ndata: refused\n\n")
            return type(answered)(**{**answered.__dict__, "frames": tuple(frames)})
        return answered

    monkeypatch.setattr(canary_run, "answer_lane", telling)
    with at_head("brain_acceptance_skill_pins_told") as url:
        outcome = run_one(url, CANARIES)
    assert outcome == (
        FAILED,
        "the canaries told one persona's refusal apart from an absence",
    )


@pytest.mark.needs_db
def test_a_projection_that_offers_every_tool_fails_the_canaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M28.2.3: the catalogue projected for each persona is every tool, whatever it holds, so the
    asker holding nothing is offered the price list. The projection assertion finds it and the
    check fails. Delete this and a catalogue that ignores grants could pass every canary run."""
    from brain.ops import canary_run

    class Everything:
        def __init__(self, definitions: Any) -> None:
            self.names = tuple(one.name for one in definitions)

    def everything(definitions: Any, *args: Any, **kwargs: Any) -> Everything:
        del args, kwargs
        return Everything(definitions)

    monkeypatch.setattr(canary_run, "project", everything)
    with at_head("brain_acceptance_skill_pins_projected") as url:
        outcome = run_one(url, CANARIES)
    assert outcome == (
        FAILED,
        "a persona was offered a tool its grants do not admit, or not one",
    )


@pytest.mark.needs_db
def test_a_roster_keyed_on_the_record_alone_fails_the_key_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M13.2.5: the roster hashes the agent record and ignores the install's stored hash, which is
    how `/answer` keyed its cache until 2026-10-06. Assigning a skill then leaves the key where it
    was and the check fails. Delete this and a key that cannot see a skill could pass the
    install."""
    from brain.gate import roster

    original = roster.setup_of

    def record_only(record: Any, tool_names: Any, install_hash: Any = None) -> Any:
        del install_hash
        return original(record, tool_names)

    monkeypatch.setattr(roster, "setup_of", record_only)
    with at_head("brain_acceptance_skill_pins_keyed") as url:
        outcome = run_one(url, KEYED)
    assert outcome == (
        FAILED,
        "assigning a skill left the key an answer is cached under where it was",
    )
