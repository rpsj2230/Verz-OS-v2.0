"""The learned-changes acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: an agent is
given a learned change through the door, read on the Prompts screen as the agent's own learning,
given back, set by an administrator, refused a second learned change, and given back again with the
switch off. Then it runs the check against the product broken where it proves, each failing with
its own sentence.

Task ids: M16.7.1
"""

from __future__ import annotations

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
from tests.unit.test_acceptance_templates import run_checks, written

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_learned_changes"
NAME = "what_an_agent_taught_itself_is_marked_and_can_be_given_back"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_learned_changes_check_is_registered_with_the_leaf_it_proves() -> None:
    """One leaf, which the work breakdown holds. Delete this and the check can close a leaf it
    does not exercise or name an id no task has."""
    assert mine()[NAME].leaves == ("M16.7.1",)
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert "M16.7.1" in {one for module in wbs["modules"] for one in module["leaf_ids"]}


def test_the_learned_changes_check_is_listed_in_its_page_order() -> None:
    """The one check this module registers, found by the suite. Delete this and the check can drop
    out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()


def test_the_check_s_sentence_and_every_reason_it_can_give_fit_the_page() -> None:
    """The sentence fits the Install page's column and every reason is a named literal that fits
    the result's. Delete this and a reason can be cut off mid-word on the page."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_learned_changes as module

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
    assert len(reasons) >= 9
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


def _fails_with(reason: str, name: str) -> None:
    import brain.ops.acceptance_checks_learned_changes as module

    with at_head(name) as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_on_a_real_database_a_learned_change_is_marked_listed_given_back_and_nothing_stays() -> (
    None
):
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the agents,
    versions and instances hold what they held before. Delete this and what an agent taught itself
    can stop being marked with nothing on the owner's install saying so, or a check that commits an
    agent can reach his server."""
    with at_head("brain_acceptance_learned_changes") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
def test_a_learned_change_written_while_the_switch_is_off_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The door treating the switch as on. Delete this and what an agent learns is written into it
    on an install that never turned that on."""
    import brain.learned_instruction_store as store

    async def on(session: Any, one: object) -> bool:
        del session, one
        return True

    monkeypatch.setattr(store, "is_on", on)
    _fails_with("WRITTEN_WHILE_OFF", "brain_acceptance_learned_off")


@pytest.mark.needs_db
def test_an_approval_drawn_against_instructions_that_moved_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The door ignoring the hash the approver was shown. Delete this and an approval given for
    one set of instructions is applied to another."""
    from sqlalchemy import select

    import brain.learned_instruction_store as store
    from brain.tables.template import TemplateInstanceRow

    real = store.apply_learned_instructions

    async def ignoring(sessions: Any, **given: Any) -> Any:
        async with sessions() as session:
            current = (
                await session.execute(
                    select(TemplateInstanceRow.effective_hash).where(
                        TemplateInstanceRow.id == given["agent_id"]
                    )
                )
            ).scalar_one()
        return await real(sessions, **{**given, "expected_hash": current})

    monkeypatch.setattr(store, "apply_learned_instructions", ignoring)
    _fails_with("STALE_WRITTEN", "brain_acceptance_learned_stale")


@pytest.mark.needs_db
def test_a_learned_change_that_carries_no_mark_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The door writing the change as an ordinary edit. Delete this and what the agent taught
    itself cannot be told from what an administrator set, so nothing can list it."""
    import brain.learned_instruction_store as store
    from brain.agents.template import set_field

    def plain(instance: Any, path: str, value: Any, *, approved_by: str, at: Any) -> Any:
        return set_field(instance, path, value, by=approved_by, at=at)

    monkeypatch.setattr(store, "learn_field", plain)
    _fails_with("NOT_MARKED", "brain_acceptance_learned_unmarked")


@pytest.mark.needs_db
def test_a_learned_change_that_does_not_reach_the_ledger_fails_the_check() -> None:
    """The database not recording an instructions change. Delete this and a learned change can be
    written with nobody's name against it."""
    import brain.ops.acceptance_checks_learned_changes as module
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_learned_ledger") as url:
        sql(url, "DROP TRIGGER instructions_are_audited ON agent.template_instance")
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, module.NOT_ON_THE_LEDGER)


@pytest.mark.needs_db
def test_instructions_given_back_that_are_not_the_templates_fail_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The give-back changing nothing. Delete this and a person who gives back what the agent
    taught itself is told it was done while the instructions stay."""
    import brain.prompt_routes as routes

    monkeypatch.setattr(routes, "clear_field", lambda instance, path: instance)
    _fails_with("GIVE_BACK_FAILED", "brain_acceptance_learned_back")


@pytest.mark.needs_db
def test_a_learned_change_that_says_what_the_instructions_already_say_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The door writing words identical to the ones in force. Delete this and what an agent learns
    can turn the template's own instructions into a change marked as learned, which lists
    something the agent taught itself that changed nothing."""
    import brain.learned_instruction_store as store

    monkeypatch.setattr(store, "instruction_refusal", lambda text, current: "")
    _fails_with("SAME_WORDS_WRITTEN", "brain_acceptance_learned_same")


@pytest.mark.needs_db
def test_a_learned_change_that_replaces_what_a_person_set_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The door writing over instructions an administrator set. Delete this and giving a learned
    change back can destroy an administrator's decision."""
    import brain.learned_instruction_store as store
    from brain.agents.template import FieldSource, set_field

    def over(instance: Any, path: str, value: Any, *, approved_by: str, at: Any) -> Any:
        return set_field(instance, path, value, by=approved_by, at=at, source=FieldSource.LEARNED)

    monkeypatch.setattr(store, "learn_field", over)
    _fails_with("OVERWROTE_A_PERSON", "brain_acceptance_learned_over")


@pytest.mark.needs_db
def test_instructions_an_administrator_set_that_are_marked_as_learned_fail_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A person's edit carrying the learned mark. Delete this and what an administrator typed is
    listed, and given back, as the agent's own learning."""
    import brain.prompt_routes as routes
    from brain.agents.template import FieldSource, set_field

    def marked(*args: Any, **kwargs: Any) -> Any:
        return set_field(*args, **kwargs, source=FieldSource.LEARNED)

    monkeypatch.setattr(routes, "set_field", marked)
    _fails_with("MARKED_WHAT_A_PERSON_SET", "brain_acceptance_learned_typed")


@pytest.mark.needs_db
def test_a_switch_turned_off_that_traps_a_learned_change_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The last give-back, made while the switch is off, refused. Delete this and turning the
    switch off leaves what it let in with nothing able to remove it."""
    import brain.prompt_routes as routes
    from brain.agents.template import TemplateError, clear_field

    calls = iter(range(10))

    def refusing_the_last(instance: Any, path: str) -> Any:
        if next(calls) == 2:
            msg = "refused"
            raise TemplateError(msg)
        return clear_field(instance, path)

    monkeypatch.setattr(routes, "clear_field", refusing_the_last)
    _fails_with("TRAPPED", "brain_acceptance_learned_trapped")
