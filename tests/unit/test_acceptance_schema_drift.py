"""The schema-drift acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a helpdesk made
up for the run connected, read as it was and then read with the ticket's status renamed. It passes,
and every table it writes holds afterwards what it held before. Then it is run against the product
broken where it proves, and each break fails it with its own sentence.

Task ids: M11.8.7, M11.8.9
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
MODULE = "brain.ops.acceptance_schema_drift"
NAME = "a_field_the_source_renamed_is_seen_shown_and_not_answered"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.8.7", "M11.8.9")}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for m in wbs["modules"] for one in m["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_a_renamed_field_is_seen_shown_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before. Delete this and the schema check can break on a real
    schema with nothing on the install saying so."""
    with at_head("brain_acceptance_schema_drift") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("seen", "a renamed field was not shown on the source's health by name"),
        ("answered", "a question over a source that lost a field was answered from it"),
        ("everything", "a question's live read did not reach a source with nothing lost"),
    ],
)
def test_the_check_fails_where_the_schema_check_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks: the run never calling a field lost, the answer lane ignoring what the run
    found, and the lane refusing every source whatever was lost. Each fails the check with its own
    sentence. Delete this and the check can pass with the property gone."""
    import brain.ops.connector_sync_run as run
    import brain.ops.live_records as live_records

    if broken == "seen":
        monkeypatch.setattr(run, "lost_fields", lambda entity, **kwargs: ())
    elif broken == "answered":
        real = live_records.SourceRecords.__init__

        def without(self: Any, *args: Any, **kwargs: Any) -> None:
            kwargs["lost"] = None
            real(self, *args, **kwargs)

        monkeypatch.setattr(live_records.SourceRecords, "__init__", without)
    else:

        async def everything() -> Any:
            return {"freshdesk": frozenset({"ticket.anything"})}

        real_init = live_records.SourceRecords.__init__

        def always(self: Any, *args: Any, **kwargs: Any) -> None:
            kwargs["lost"] = everything
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(live_records.SourceRecords, "__init__", always)
    with at_head(f"brain_acceptance_schema_drift_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
