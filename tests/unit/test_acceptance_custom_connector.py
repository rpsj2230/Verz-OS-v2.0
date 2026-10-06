"""The acceptance check for a connector added from the console: registered, passing, able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: an API made up
for the run is submitted, refused its submitter's approval, approved by a second person, connected
with a key, read by the worker from a recorded answer and asked about through the answer route's own
parts, and every table it writes holds afterwards what it held before. Then it is run against the
product broken where it proves, and each break fails with its own sentence.

Task ids: M11.7.8
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, SENTENCE_CHARS, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_laravel import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_custom_connector"
NAME = "an_api_added_from_the_console_is_read_after_a_second_review"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = (
    "ops.custom_connector",
    "proj.record",
    "ops.connector_connection",
    "ops.connector_sync",
    "obs.audit_entry",
)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.7.8",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves
    assert checks_in(MODULE) == [NAME]


def test_the_check_s_sentence_and_every_reason_it_can_give_fit_the_page() -> None:
    """The sentence fits the Install page's column and every reason is a literal that fits the
    result's. Delete this and a reason can carry a client's name or be cut off mid-word."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_custom_connector as module

    assert len(mine()[NAME].sentence) <= SENTENCE_CHARS
    reasons = [
        node.args[0].value
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") in {"CheckFailedError", "CheckNotRunError"}
        and isinstance(node.args[0], ast.Constant)
    ]
    assert len(reasons) >= 10
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


@pytest.mark.needs_db
def test_on_a_real_database_a_reviewed_connector_answers_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    it wrote to, the ledger included, holds what it held before. Delete this and the path from a
    pasted specification to an answer on Ask can break with nothing on an install saying so, or a
    check that commits a definition can reach the owner's server."""
    with at_head("brain_acceptance_custom_connector") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("self", "a definition's submitter approved their own"),
        ("unreviewed", "an unreviewed definition was offered or given a tool"),
        ("changed", "a definition changed after approval did not wait for review"),
    ],
)
def test_the_check_fails_where_the_review_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, one per property the review holds: the store letting a submitter approve
    their own (with the database's own refusal lifted by approving as nobody), the catalogue
    reading every definition rather than the approved ones, and a change that keeps the approval.
    Each fails the check with its own sentence. Delete this and the check can pass with the review
    gone."""
    import brain.ops.custom_connector_store as store

    if broken == "self":

        async def nobody_checks(self: Any, name: str, **kwargs: Any) -> Any:
            from brain.ops.custom_connector import ReviewState

            found = await self.one(name)
            from dataclasses import replace

            return replace(found, state=ReviewState.APPROVED, reviewed_by=kwargs["by"])

        monkeypatch.setattr(store.StoredCustomConnectors, "decide", nobody_checks)
    elif broken == "unreviewed":
        from sqlalchemy import select

        from brain.tables.custom_connector import CustomConnectorRow

        async def every(session: Any) -> Any:
            rows = (await session.execute(select(CustomConnectorRow))).scalars().all()
            from brain.ops.custom_connector import declaration_of

            return {row.name: declaration_of(store.definition_of(row)) for row in rows}

        monkeypatch.setattr(store, "approved_in", every)
    else:
        original = store.StoredCustomConnectors.change

        async def keeps(self: Any, definition: Any, **kwargs: Any) -> Any:
            from dataclasses import replace

            from brain.ops.custom_connector import ReviewState

            kept = await original(self, definition, **kwargs)
            return replace(kept, state=ReviewState.APPROVED)

        monkeypatch.setattr(store.StoredCustomConnectors, "change", keeps)
    with at_head(f"brain_acceptance_custom_connector_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before
