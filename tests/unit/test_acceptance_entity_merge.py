"""The merge and unmerge acceptance checks: registered, passing on PostgreSQL, and able to fail.

The pure half holds the five checks to their leaves, their page order, and the sentences and
reasons the Install page shows. The database half builds PostgreSQL to head once for the module
and runs the checks as the worker would: they pass and every table they write to holds, row for
row, what it held before. Then each property is broken, one at a time, where the product holds it
(`BREAKS`), and the check proving it fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M14.5.1, M14.5.2, M14.5.3, M14.5.4, M14.5.5
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import inspect
import json
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, Final

import pytest

import brain.ops.acceptance_checks_entity_merge as module
from brain.ops.acceptance import (
    FAILED,
    PASSED,
    REASON_CHARS,
    SENTENCE_CHARS,
    Check,
    check_modules,
    registered,
)
from brain.resolution import merge_store
from brain.settings import settings_from
from tests.unit.test_acceptance import WRITTEN_BY_CHECKS, at_head, checks_in

ROOT = Path(__file__).resolve().parents[2]
MODULE: Final = "brain.ops.acceptance_checks_entity_merge"

PRE_IMAGE: Final = "a_merge_keeps_every_affected_row_as_it_stood_before_the_change"
POINTER: Final = "a_merge_moves_one_pointer_and_changes_no_record_or_child_row"
UNMERGE: Final = "an_unmerge_restores_the_pre_image_and_an_old_id_still_resolves"
AUDIT: Final = "the_audit_names_who_when_and_on_what_evidence_of_both_acts"
INVALIDATION: Final = "a_merge_tells_every_surface_every_id_of_both_families"

#: Every table the checks write to, which must hold afterwards exactly what it held before.
WRITTEN: Final = (
    "er.canonical",
    "er.link",
    "er.alias",
    "er.identifier",
    "er.merge",
    "er.unmerge",
    "proj.record",
    "obs.audit_entry",
)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


# ------------------------------------------------------------------------ without a server
def test_each_check_proves_the_leaf_its_property_is_and_nothing_else() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        PRE_IMAGE: ("M14.5.1",),
        POINTER: ("M14.5.2",),
        UNMERGE: ("M14.5.3",),
        AUDIT: ("M14.5.4",),
        INVALIDATION: ("M14.5.5",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    every = {one for entry in wbs["modules"] for one in entry["leaf_ids"]}
    assert {leaf for one in mine().values() for leaf in one.leaves} <= every


def test_the_merge_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [PRE_IMAGE, POINTER, UNMERGE, AUDIT, INVALIDATION]
    assert MODULE in check_modules()


def test_every_sentence_and_every_reason_fits_the_page() -> None:
    """Every reason is a named constant of the module that fits the result's column, and each
    sentence fits the page's. Delete this and a reason is cut off mid-word on the Install page."""
    assert all(len(one.sentence) <= SENTENCE_CHARS for one in mine().values())
    assert all(len(name) <= 64 for name in mine())
    reasons = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "CheckFailedError":
            [argument] = node.args
            assert isinstance(argument, ast.Name), ast.unparse(node)
            reasons.append(getattr(module, argument.id))
    assert len(set(reasons)) == 10
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


def test_every_table_the_merge_checks_write_is_one_the_suite_measures() -> None:
    """Delete this and a table the checks write can be left out of the suite's count, so a row a
    check committed by mistake is never noticed."""
    assert set(WRITTEN) <= set(WRITTEN_BY_CHECKS)


# --------------------------------------------------------------------------- a real run
def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for the module: every check rolls back, so they can share it."""
    with at_head("brain_acceptance_entity_merge") as url:
        yield url


def contents(url: str) -> dict[str, tuple[int, str]]:
    """Every row of every table the checks write to, as a count and a digest of the rows."""
    from tests.fixtures.scratch_postgres import sql

    held: dict[str, tuple[int, str]] = {}
    for table in WRITTEN:
        # The names are this module's constants, never input.
        [(count, digest)] = sql(
            url,
            f"SELECT count(*), coalesce(md5(string_agg(t::text, ',' ORDER BY t::text)), '')"  # noqa: S608
            f" FROM {table} t",
        )
        held[table] = (int(count), str(digest))
    return held


@pytest.mark.needs_db
def test_on_a_real_database_the_merge_checks_pass_and_leave_nothing_behind(database: str) -> None:
    """**The five checks as the worker runs them, against PostgreSQL at head.** Each passes, and
    every table they wrote to holds row for row what it held before. Delete this and a check that
    cannot pass on the real schema, or one that commits, reaches the owner's server first."""
    before = contents(database)
    outcomes = run_checks(database, tuple(mine().values()))
    assert contents(database) == before
    assert outcomes == dict.fromkeys(mine(), (PASSED, ""))


# ------------------------------------------------------------------------ the breaks
def _without_aliases(kept: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def broken(pre: Any) -> dict[str, Any]:
        return {**kept(pre), "aliases": []}

    return broken


def _rewriting_links(kept: Callable[..., Any]) -> Callable[..., Any]:
    """The lock also points the merged entity's links at the survivor: a merge that rewrites child
    rows, which `merge` has no field for and a store could still do on its own."""
    from sqlalchemy import text

    async def broken(session: Any, pair: Sequence[str]) -> None:
        await kept(session, pair)
        survivor, merged = tuple(pair)
        await session.execute(
            text("UPDATE er.link SET entity_id = :survivor WHERE entity_id = :merged").bindparams(
                survivor=survivor, merged=merged
            )
        )

    return broken


def _keeping_the_pointer(kept: Callable[..., Any]) -> Callable[..., Any]:
    """An unmerge whose restoration carries the merged entity as it is now, pointer and all."""

    def broken(pre: Any, **kwargs: Any) -> Any:
        restoration = kept(pre, **kwargs)
        current = kwargs["entities"][pre.merged.entity_id]
        return dataclasses.replace(
            restoration,
            entities=tuple(
                current if one.entity_id == current.entity_id else one
                for one in restoration.entities
            ),
        )

    return broken


def _survivors_family_only(kept: Callable[..., Any]) -> Callable[..., Any]:
    """Each surface told the survivor's family and not the merged one's: the natural mistake."""

    def broken(invalidations: Any) -> Any:
        return {
            surface: frozenset(one for one in ids if "_gone" not in one)
            for surface, ids in kept(invalidations).items()
        }

    return broken


#: Each break to the product under one check, the attribute it replaces, and the sentence the
#: check must fail with. Monkeypatched in this process; nothing is changed in any install.
BREAKS: dict[str, tuple[str, Any, str, Callable[[Any], Any], str]] = {
    "pre_image_drops_aliases": (
        PRE_IMAGE,
        merge_store,
        "pre_image_document",
        _without_aliases,
        "NOT_EVERY_ROW_BEFORE",
    ),
    "merge_rewrites_links": (
        POINTER,
        merge_store,
        "_lock",
        _rewriting_links,
        "A_ROW_MOVED",
    ),
    "unmerge_keeps_the_pointer": (
        UNMERGE,
        merge_store,
        "unmerge",
        _keeping_the_pointer,
        "NOT_RESTORED",
    ),
    "invalidation_forgets_the_merged_family": (
        INVALIDATION,
        merge_store,
        "by_surface",
        _survivors_family_only,
        "NOT_EVERY_SURFACE_TOLD",
    ),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_each_check_fails_with_its_own_sentence_where_the_product_is_broken(
    database: str, broken: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-image missing the aliases (M14.5.1), a merge that rewrites a link (M14.5.2), an
    unmerge that leaves the pointer (M14.5.3) and an invalidation that forgets the merged family
    (M14.5.5). Each fails its check with that check's own sentence. Delete this and a check can
    pass with the property it names gone."""
    name, target, attribute, breaking, reason = BREAKS[broken]
    monkeypatch.setattr(target, attribute, breaking(getattr(target, attribute)))
    outcome = run_checks(database, (mine()[name],))
    assert outcome[name] == (FAILED, getattr(module, reason))


#: The ledger trigger's function, broken one half at a time: `0104`'s, which names no merge, and
#: `0183`'s with the unmerge branch never taken, which records no unmerge at all.
TRIGGER_BREAKS: dict[str, tuple[Callable[[Any], str], str]] = {
    "names_no_merge": (lambda m: m.PREVIOUS_ENTITY_MERGE_TRIGGER_FUNCTION, "MERGE_NOT_AUDITED"),
    "records_no_unmerge": (
        lambda m: m.ENTITY_MERGE_TRIGGER_FUNCTION.replace(
            "IF OLD.merged_into IS NOT NULL AND OLD.merged_into IS DISTINCT FROM NEW.merged_into",
            "IF false",
        ),
        "UNMERGE_NOT_AUDITED",
    ),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(TRIGGER_BREAKS))
def test_the_audit_check_fails_where_the_ledger_trigger_is_broken(
    database: str, broken: str
) -> None:
    """A merge entry that names no merge, and an unmerge that reaches no ledger (M14.5.4), each
    failing with its own sentence; the trigger is put back whatever happened. Delete this and the
    audit check can pass on an install whose ledger cannot say which merge an entry was, or that a
    merge was ever reversed."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_tables import VERSIONS, migration_module

    merges = migration_module(VERSIONS / "0183_entity_merges.py")
    function, reason = TRIGGER_BREAKS[broken]
    assert function(merges) != merges.ENTITY_MERGE_TRIGGER_FUNCTION
    sql(database, function(merges))
    try:
        outcome = run_checks(database, (mine()[AUDIT],))
    finally:
        sql(database, merges.ENTITY_MERGE_TRIGGER_FUNCTION)
    assert outcome[AUDIT] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_the_invalidation_check_fails_when_a_table_outside_resolution_is_keyed_by_an_entity(
    database: str,
) -> None:
    """A memory table growing an entity id that no invalidator evicts (M14.5.5). Delete this and
    the check passes on an install where a merge leaves such rows answering from before it."""
    from tests.fixtures.scratch_postgres import sql

    sql(database, "ALTER TABLE mem.persistent ADD COLUMN entity_id varchar(128)")
    try:
        outcome = run_checks(database, (mine()[INVALIDATION],))
    finally:
        sql(database, "ALTER TABLE mem.persistent DROP COLUMN entity_id")
    assert outcome[INVALIDATION] == (FAILED, module.AN_ENTITY_KEY_NOBODY_EVICTS)
