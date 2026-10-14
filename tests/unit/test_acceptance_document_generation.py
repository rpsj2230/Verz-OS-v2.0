"""The document generation acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a template added
by a steward, an agent that may use the tool, the switch pressed both ways through the Features
route, and a file made for a member of acceptance_a that a member of acceptance_b cannot fetch. It
passes, and every table it writes holds afterwards what it held before. Then it is run against the
product broken where it proves.

Task ids: M12.3.5
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_document_generation"
NAME = "an_approved_template_is_filled_for_its_asker_alone"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M12.3.5",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for m in wbs["modules"] for one in m["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_a_template_is_filled_for_its_asker_alone() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before, the artifact record, the template and the feature row
    included. Delete this and filling a template can break on a real schema with nothing on the
    install saying so, or a check can leave a person's file or a switched feature behind on the
    owner's server."""
    from tests.fixtures.scratch_postgres import sql

    def kept(url: str) -> dict[str, int]:
        # The names are this module's constants, never input.
        return {
            one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
            for one in ("agent.artifact", "ops.setting", "know.item")
        }

    with at_head("brain_acceptance_document_generation") as url:
        before = counts(url), kept(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url), kept(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("anything_is_approved", "a template nobody had verified was filled"),
        ("the_switch_is_ignored", "a file was produced while document generation was switched off"),
        (
            "holes_are_filled",
            "a placeholder left without a value was filled or the refusal named a value",
        ),
        ("anybody_may_fetch", "a member of another department was let fetch the file"),
    ],
)
def test_the_check_fails_where_generation_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Four breaks: any template counting as approved, the switch not being asked, a placeholder
    with no value being let through, and a file that anybody may fetch. Each fails the check with
    its own sentence. Delete this and the check can pass with the property gone."""
    import brain.console.agent_output as output
    import brain.tools.document_generation as generation

    if broken == "anything_is_approved":
        monkeypatch.setattr(generation, "is_approved_template", lambda facts, *, now: True)
    elif broken == "the_switch_is_ignored":

        async def always(sessions: Any) -> bool:
            del sessions
            return True

        monkeypatch.setattr(generation, "generation_is_on", always)
    elif broken == "holes_are_filled":
        monkeypatch.setattr(generation, "missing_values", lambda blocks, values: ())
    else:
        monkeypatch.setattr(output, "may_download", lambda one, requester, now: True)
    with at_head(f"brain_acceptance_document_generation_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
