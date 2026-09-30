"""The owner's rule, held for every connector that ships: a minimal index, and every value live.

Connectors never bulk-sync (`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`). These run on
every push, over every connector found by its declaration, so a connector added later is held to
the rule by existing. Each drives the connector's own code from its recordings, plants a canary
minted for the run in the values the connector must never keep, and looks for it in what the code
kept; and each proves the harness can see, by planting the same kind of string where the index
does keep it.

The database half, that a real sync leaves the canary in no table and no log, is
`tests/unit/test_connector_sync_run.py`, because it needs a database built through every migration.

Task ids: M11.9.1, M11.8.2
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import replace

import pytest

from brain.connectors import declaration, xero
from brain.connectors.declaration import SourceReading, ViewReading, declaration_gaps, shipped
from brain.connectors.minimal_index import (
    CANARY_MARK,
    assert_minimal_index,
    fresh_canary,
    plant,
    sightings,
)
from brain.ops import connector_sync, connector_sync_run, connector_sync_store
from tests.fixtures.cassettes import FILES, Cassette, Expect

pytestmark = pytest.mark.invariant

#: The outcomes after which a replay has kept whatever it was going to keep.
ANSWERED = frozenset({Expect.ANSWERED, Expect.MORE_TO_READ})


def kept_from(name: str) -> list[Cassette]:
    """Every recording of this connector whose replay keeps index entries."""
    recorded = FILES[name]
    return [
        one
        for one in recorded.cassettes
        if one.projects
        and one.expect in ANSWERED
        and one.projects not in recorded.projection_not_replayable
    ]


def test_every_connector_module_says_it_keeps_a_minimal_index_and_reads_every_value_live() -> None:
    """The owner's words, in every declared connector's docstring, and every connector declared.
    Delete this and a connector can ship without its author having written the rule down, which
    is how the document leg arrived: correct, argued, and against the rule."""
    assert shipped(), "no connector was found, so this checked nothing"
    assert declaration_gaps() == ()


@pytest.mark.parametrize("name", sorted(shipped()))
def test_what_a_connector_keeps_from_its_recordings_is_its_minimal_index_and_holds_no_canary(
    name: str,
) -> None:
    """**M11.9.1 and M11.8.2, per connector, from the connector's own code.** Every recording whose
    rows the connector keeps is replayed with a canary minted for this run planted wherever the
    recording marks a value that must be read live. What the code kept must be inside the minimal
    index its manifest declares, and must not hold the canary anywhere.

    A connector that keeps records must have a recording carrying a marker, so the canary is
    planted somewhere rather than nowhere; one whose manifest projects nothing must keep nothing.

    Delete this and a connector can start keeping a body, an amount or a note, and every test that
    checks one named field stays green."""
    recorded = FILES[name]
    manifest = recorded.manifest()
    canary = fresh_canary(name)
    planted_somewhere = False
    for one in kept_from(name):
        body, count = plant(one.body, canary)
        planted_somewhere = planted_somewhere or count > 0
        kept = recorded.replay(replace(one, body=body)).kept
        assert kept, f"{one.cid} feeds a projection and kept nothing"
        assert_minimal_index(manifest, kept)
        assert sightings(canary, kept) == (), f"{one.cid} kept a value that is read live"
    if kept_from(name):
        assert planted_somewhere, (
            f"no recording {name} keeps rows from marks a value with {CANARY_MARK}, so the canary "
            "would be planted nowhere and every check above would pass by default"
        )
    else:
        assert not manifest.projections or all(
            entity in recorded.projection_not_replayable
            for entity in (p.entity for p in manifest.projections)
        ), f"{name} projects entities and no recording keeps any of them"


def test_the_harness_sees_a_canary_planted_where_the_index_does_keep_it() -> None:
    """**The positive case.** The same canary planted in an invoice's number, which is an index
    field, is found in what Xero's code keeps. Delete this and a `sightings` that saw nothing, or
    a replay that kept nothing, would make every connector above pass."""
    recorded = FILES[xero.CONNECTOR_NAME]
    invoices = next(one for one in recorded.cassettes if one.cid == "XERO-200-invoices")
    canary = fresh_canary("indexed")
    body = {"Invoices": [{**row, "InvoiceNumber": canary} for row in invoices.body["Invoices"]]}

    kept = recorded.replay(replace(invoices, body=body)).kept

    assert sightings(canary, kept)


def test_the_scheduled_sync_hands_nothing_to_the_knowledge_corpus() -> None:
    """**The document leg stays removed.** No module on the sync's path imports anything from
    `brain.knowledge`, and a reading, a REST source's or a database's views', declares no method
    that could return a document. Read from the source rather than from a flag, so it cannot be
    satisfied by a comment.

    Delete this and the leg that embedded every body a source held into `know.chunk` can come
    back through one import, which is the bulk sync the owner has ruled out twice."""
    for module in (connector_sync, connector_sync_run, connector_sync_store, declaration):
        tree = ast.parse(inspect.getsource(module))
        imported = {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not {one for one in imported if one.startswith("brain.knowledge")}, module.__name__
    for protocol in (SourceReading, ViewReading):
        methods = {
            name
            for name, member in inspect.getmembers(protocol)
            if inspect.isfunction(member) and not name.startswith("_")
        }
        assert "projected" in methods, "the protocol was not read, so this checked nothing"
        assert not {one for one in methods if "document" in one or "item" in one}, protocol
