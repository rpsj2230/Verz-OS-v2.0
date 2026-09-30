"""The Lark Wiki acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the application would: a space
made up for the run is declared, read back and searched through the answer lane's passage search
from recorded answers, and every table the check writes holds afterwards what it held before.
Then it is run against the product broken where it proves: a page's permission settings read as
following whatever they say, the declared reach not applied, and a reader with no read of the
knowledge plane walked into Lark anyway. Each fails with its own sentence.

Task ids: M11.6.4
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_lark_wiki"
NAME = "a_lark_wiki_page_is_told_only_to_a_reader_its_space_admits"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("ops.setting", "proj.record")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_lark_wiki_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.6.4",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_lark_wiki_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here
    since 2026-09-30, so a package adding a check edits its own file and never a list every
    package appends to. Delete this and a check can drop out of the module with the page simply
    listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_lark_wiki") == [
        "a_lark_wiki_page_is_told_only_to_a_reader_its_space_admits",
    ]


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_on_a_real_database_a_wiki_page_is_told_within_its_reach_and_nothing_is_kept() -> None:
    """**The check as the application runs it, against PostgreSQL at head.** It passes, and the
    settings, the index and the ledger hold what they held before. Delete this and the path from
    a declared space to Ask can break with nothing on the owner's install saying so, or a check
    that commits a made-up space's declaration can reach his server."""
    with at_head("brain_acceptance_lark_wiki") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("lock", "a page restricted in Lark was read for an answer"),
        ("reach", "a wiki page was told to a reader outside its space's reach"),
        ("walk", "the Wiki was read for a reader who reads no knowledge"),
    ],
)
def test_the_lark_wiki_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, one per property: every page read as following its space, every reader
    told every page, and a reader with no knowledge read walked into Lark. Each fails the check
    with its own sentence. Delete this and the check can pass with the property gone."""
    import brain.connectors.lark_wiki as lark_wiki
    import brain.ops.lark_wiki_live as lark_wiki_live

    if broken == "lock":
        monkeypatch.setattr(
            lark_wiki, "permission_of", lambda reply: lark_wiki.NodeRestriction.INHERITS
        )
    elif broken == "reach":
        monkeypatch.setattr(lark_wiki_live, "told_to", lambda document, entitlement, now: True)
    else:

        async def walking(self: Any, question: str, *, entitlement: Any, now: Any) -> Any:
            # The search without its first guard: every question walks the declared spaces.
            from brain.core.envelope import TypedResult
            from brain.knowledge.document_tools import KnowledgePassage

            declared = await self._spaces()
            found = await asyncio.to_thread(
                self.read, lark_wiki_live.words_of(question), declared, now
            )
            told = tuple(
                lark_wiki_live.passage_of(one, now=now)
                for one in found
                if lark_wiki_live.told_to(one, entitlement, now)
            )
            return TypedResult[KnowledgePassage](
                records=told, source="lark_wiki", fetched_at=now.isoformat()
            )

        monkeypatch.setattr(lark_wiki_live.WikiPassages, "passages", walking)
    with at_head(f"brain_acceptance_lark_wiki_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before
