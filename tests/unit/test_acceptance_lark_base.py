"""The Lark Base acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a Base made
up for the run is indexed from recorded answers, its schema read as a question reads it, and a
record asked about through the answer route's own lane, and every table the check writes holds
afterwards what it held before. Then it is run against the product broken where it proves: a live
read that is never made, every field of a table readable by whoever may find its records, and a
table's grants never offered. Each fails with its own sentence.

Task ids: M11.6.3
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_lark_base"
NAME = "a_lark_base_answers_on_ask_from_its_index_and_lark"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("proj.record", "gate.capability_registry")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_lark_base_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.6.3",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_on_a_real_database_a_lark_base_answers_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the index,
    the capability registry and the ledger hold what they held before. Delete this and the path
    from a switched-on Base to Ask can break with nothing on the owner's install saying so, or a
    check that commits a made-up Base's rows can reach his server."""
    with at_head("brain_acceptance_lark_base") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("live", "a Base record's value was not read from Lark for a reader granted it"),
        ("fields", "a Base record's value was told to a reader not granted its fields"),
        ("words", "the index did not offer the table's grants on the grants screen"),
    ],
)
def test_the_lark_base_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, one per property: a live reader that never reads, a table whose every field
    is readable by whoever may find its records, and an index that registers no grant for the
    table. Each fails the check with its own sentence. Delete this and the check can pass with the
    property gone."""
    import brain.knowledge.lark_base_rows as lark_base_rows
    import brain.ops.lark_base_index as lark_base_index
    import brain.ops.live_records as live_records
    from brain.core.entitlement import Capability
    from brain.core.field_policy import Classification
    from brain.knowledge.columns import ColumnRule, TableClassification

    if broken == "live":

        async def never(self: Any, result: Any, **kwargs: Any) -> Any:
            del self, result, kwargs
            return None

        monkeypatch.setattr(live_records.SourceRecords, "refresh", never)
    elif broken == "fields":

        def whole(table: Any) -> TableClassification:
            row = Capability(value=f"read:{table.entity}")
            return TableClassification(
                entity=table.entity,
                rules=(
                    *(
                        ColumnRule(
                            column=one.target,
                            required_capability=row,
                            classification=Classification.INTERNAL,
                        )
                        for one in table.bindings
                    ),
                    ColumnRule(
                        column=lark_base_index.BASE_ID_FIELD,
                        required_capability=row,
                        classification=Classification.INTERNAL,
                    ),
                ),
            )

        monkeypatch.setattr(lark_base_rows, "classification_of", whole)
    else:
        monkeypatch.setattr(lark_base_index, "vocabulary_of", lambda tables: ())
    with at_head(f"brain_acceptance_lark_base_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before
