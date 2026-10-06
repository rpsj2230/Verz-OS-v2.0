"""A merge is one pointer and one audit row in one transaction, and an unmerge puts back only that.

The first half needs no server: `0183` held to the model and to `0104`, the ledger's widened list,
the trigger's keys held to the recorder's, the pre-image's round trip, the invalidators and the
claim each of them rests on. The second half builds a database at head and drives
`brain.resolution.merge_store` as the application role: a reviewed merge moves one pointer, keeps
every row of both families in its pre-image, writes its row and two ledger entries naming the
reviewer and the merge; an automatic merge waits for its switch; an unmerge clears the pointer,
writes its row and its own two entries, and is refused for any merge not in force; every id of
both families reaches every surface. **It skips when there is no server**, and CI always has one.

Task ids: M14.5.1, M14.5.2, M14.5.3, M14.5.4, M14.5.5
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import psycopg
import pytest
from sqlalchemy.schema import CreateIndex

from brain.audit.ledger import IDENTIFIER, AuditAction, AuditChain
from brain.audit.record import AuditRecorder
from brain.db import metadata
from brain.gate.cache_key import CachedAnswer, CacheKeyParts
from brain.ops.features import FEATURES, UNATTENDED_ENTITY_MERGE, switch
from brain.resolution import merge_store
from brain.resolution.canonical import (
    Alias,
    CanonicalEntity,
    EntityType,
    Identifier,
    IdentifierKind,
    Link,
    ResolutionError,
    SourceRef,
)
from brain.resolution.cascade import Decision, Observation, cascade
from brain.resolution.guardrails import Evidence
from brain.resolution.merge import (
    AutomaticMerge,
    InvalidatedSurface,
    Invalidation,
    MoneyBearing,
    MoneyCheck,
    PreImage,
    ReviewedMerge,
)
from brain.resolution.merge_store import (
    ENTITY_KEYED_COLUMNS,
    ENTITY_KEYS_OUTSIDE_RESOLUTION,
    INVALIDATORS,
    MergeRefusedError,
    by_surface,
    invalidate,
    merge_entities,
    pre_image_document,
    pre_image_from,
    unmerge_entities,
)
from brain.resolution.normalise import normalise_name
from brain.session import make_session_factory
from brain.tables.entity_merge import (
    EVIDENCE_IS_NAMES_AND_WEIGHTS,
    PRE_IMAGE_KEYS_ARE_DIGESTS,
    RECORD_ID_PATTERN,
)
from brain.tables.identity import one_of
from brain.tables.resolution import CONFIDENCE_IS_A_SHARE
from tests.fixtures.amended_tables import created_ddl
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import DIALECT, VERSIONS, migration_module, rendered, squash

MIGRATION: Final = VERSIONS / "0183_entity_merges.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

DIGEST_A: Final = "a" * 64
DIGEST_B: Final = "b" * 64

#: The one name two entities both observed, which is the case a recompute cannot untangle.
SHARED_NAME: Final = "Kandang Kerbau Holdings Pte Ltd"

NOT_CHECKED: Final = MoneyCheck(left=MoneyBearing.NOT_CHECKED, right=MoneyBearing.NOT_CHECKED)
NO_MONEY: Final = MoneyCheck(
    left=MoneyBearing.NO_FINANCIAL_RECORDS_FOUND, right=MoneyBearing.NO_FINANCIAL_RECORDS_FOUND
)


def ref(record: str, source: str = "freshdesk") -> SourceRef:
    return SourceRef(source=source, entity="company", source_id=record)


def reviewed(reviewer: str = "u_reviewer", ref_: str = "rev-1") -> ReviewedMerge:
    return ReviewedMerge(
        reviewer_id=reviewer,
        review_ref=ref_,
        money=NOT_CHECKED,
        evidence=(Evidence(field="uen", weight=10.0), Evidence(field="name", weight=3.5)),
    )


def automatic() -> AutomaticMerge:
    left = Observation(
        record=ref("1"),
        name=normalise_name("Acme Trading Pte Ltd"),
        identifiers={IdentifierKind.UEN: DIGEST_A},
    )
    right = Observation(
        record=ref("2", "xero"),
        name=normalise_name("Acme Trading Pte Ltd"),
        identifiers={IdentifierKind.UEN: DIGEST_A},
    )
    result = cascade(left, right)
    assert result.decision is Decision.MATCHED
    return AutomaticMerge(decision=result, money=NO_MONEY, performed_by="resolver-job")


# ------------------------------------------------------------ the migration and the model
def test_the_migration_copies_the_grammars_it_holds_from_the_code_that_owns_them() -> None:
    """Delete this and `0183` can build a table that refuses an id, an actor, a confidence or a
    money answer the store writes, or admits one the domain never would."""
    m = migration_module(MIGRATION)
    assert m.RECORD_ID_PATTERN == RECORD_ID_PATTERN
    assert m.IDENTIFIER == IDENTIFIER
    assert m.CONFIDENCE_IS_A_SHARE == CONFIDENCE_IS_A_SHARE
    assert one_of("money_left", MoneyBearing) == m.MONEY_LEFT_IN
    assert one_of("money_right", MoneyBearing) == m.MONEY_RIGHT_IN
    assert m.PRE_IMAGE_KEYS_ARE_DIGESTS == PRE_IMAGE_KEYS_ARE_DIGESTS
    assert m.EVIDENCE_IS_NAMES_AND_WEIGHTS == EVIDENCE_IS_NAMES_AND_WEIGHTS
    # A merge id the store mints is one the column admits, and one the ledger keeps as a digest.
    assert re.fullmatch(RECORD_ID_PATTERN, merge_store.new_record_id())


@pytest.mark.parametrize("qualified", ("er.merge", "er.unmerge"))
def test_the_migration_builds_each_table_exactly_as_the_model_declares_it(qualified: str) -> None:
    """Compared on rendered DDL, so a width, a nullability, a key or a constraint that differs
    between the model and `0183` is caught. Delete this and the model the store writes through
    can describe a table the database never built."""
    up = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables[qualified]
    assert squash(created_ddl(table, DIALECT)) in up
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in up


def test_the_tables_are_secured_granted_select_and_insert_and_dropped_on_the_way_back() -> None:
    """Audit rows: SELECT and INSERT for the application, nothing for the fast lane, policies
    that pin the row to the transaction's actor. Delete this and a grant of UPDATE lets a merge's
    evidence be rewritten after the fact, or a missing policy leaves the table open."""
    m = migration_module(MIGRATION)
    up = squash(rendered("upgrade", MIGRATION))
    down = squash(rendered("downgrade", MIGRATION))
    assert m.GRANTS == (
        "GRANT SELECT, INSERT ON er.merge TO brain_app",
        "GRANT SELECT, INSERT ON er.unmerge TO brain_app",
    )
    assert "brain_fastlane" not in up
    for table in ("er.merge", "er.unmerge"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in up
        assert f"DROP TABLE {table}" in down
    assert "WITH CHECK (decided_by = current_setting('brain.actor_id', true))" in up
    assert "WITH CHECK (performed_by = current_setting('brain.actor_id', true))" in up


def test_0183_widens_the_ledger_by_entity_unmerge_alone_from_0150s_list() -> None:
    """The list replaced is `0150`'s, the last to widen it, and the list written is the enum's.
    Delete this and the trigger appends an action the database refuses, and the unmerge fails."""
    m = migration_module(MIGRATION)
    browsing = migration_module(VERSIONS / "0150_trace_store_and_browser_session.py")
    assert m.NARROWER_ACTIONS == browsing.WIDENED_ACTIONS
    assert one_of("action", AuditAction) == m.WIDENED_ACTIONS
    assert m.NARROWER_ACTIONS.replace("'entity_merge', ", "'entity_merge', 'entity_unmerge', ") == (
        m.WIDENED_ACTIONS
    )
    assert m.SUPERSEDES == {m.NARROWER_ACTIONS: m.WIDENED_ACTIONS}
    assert squash(f"CHECK ({m.NARROWER_ACTIONS}) NOT VALID") in squash(
        rendered("downgrade", MIGRATION)
    )


def test_the_downgrade_puts_back_exactly_the_function_0104_wrote() -> None:
    """Delete this and the downgrade's copy of `0104`'s function can drift from the original, so
    rolling back leaves a merge trigger nobody wrote."""
    m = migration_module(MIGRATION)
    original = migration_module(VERSIONS / "0104_compliance_record_and_decision_entries.py")
    assert (
        original.ENTITY_MERGE_TRIGGER_FUNCTION.replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"
        )
    ) == m.PREVIOUS_ENTITY_MERGE_TRIGGER_FUNCTION
    assert squash(m.ENTITY_MERGE_TRIGGER_FUNCTION) in squash(rendered("upgrade", MIGRATION))
    assert squash(m.PREVIOUS_ENTITY_MERGE_TRIGGER_FUNCTION) in squash(
        rendered("downgrade", MIGRATION)
    )


def test_the_trigger_writes_the_keys_the_recorder_writes_for_a_merge_and_an_unmerge() -> None:
    """The database and a chain in memory have to agree on what an entry looks like. Delete this
    and the trigger can name the merge under a key the recorder never writes, and the audit view
    renders the database's entries differently from every chain held in memory."""
    m = migration_module(MIGRATION)
    record = AuditRecorder(
        AuditChain(),
        actor_id="u_actor",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: LONG_AGO,
    )
    merged = record.entity_merge(kept_entity_id="e1", merged_entity_id="e2", merge_id="a" * 32)
    unmerged = record.entity_unmerge(
        kept_entity_id="e1", restored_entity_id="e2", merge_id="a" * 32, unmerge_id="b" * 32
    )
    assert [dict(one.details) for one in merged] == [{"merge_id": "a" * 32}] * 2
    assert [dict(one.details) for one in unmerged] == [
        {"merge_id": "a" * 32, "unmerge_id": "b" * 32}
    ] * 2
    assert [one.subject for one in unmerged] == ["entity:e1", "entity:e2"]
    for entry in (*merged, *unmerged):
        for key in entry.details:
            assert f"'{key}'" in m.ENTITY_MERGE_TRIGGER_FUNCTION
    assert "'entity_unmerge'" in m.ENTITY_MERGE_TRIGGER_FUNCTION
    # Neither id half-written: a merge with no store row and an unmerge with one id write none.
    lone = record.entity_unmerge(kept_entity_id="e1", restored_entity_id="e2", merge_id="a" * 32)
    assert all(dict(one.details) == {} for one in lone)


# ---------------------------------------------------------------------- the pre-image
def a_pre_image() -> PreImage:
    survivor = CanonicalEntity(
        entity_id="e_kept",
        entity_type=EntityType.COMPANY,
        created_at=LONG_AGO,
        created_by="a-backfill",
        created_from=ref("1"),
    )
    merged = dataclasses.replace(survivor, entity_id="e_gone", created_from=ref("2", "xero"))
    return PreImage(
        survivor=survivor,
        merged=merged,
        links=(
            Link(entity_id="e_kept", source=ref("1"), confidence=1.0, linked_at=LONG_AGO),
            Link(entity_id="e_gone", source=ref("2", "xero"), confidence=0.75, linked_at=LONG_AGO),
        ),
        aliases=(
            Alias(
                entity_id="e_gone",
                name=SHARED_NAME,
                source=ref("2", "xero"),
                first_seen_at=LONG_AGO,
            ),
            Alias(entity_id="e_kept", name=SHARED_NAME, source=ref("1"), first_seen_at=LONG_AGO),
        ),
        identifiers=(
            Identifier(
                entity_id="e_kept",
                kind=IdentifierKind.UEN,
                key_hash=DIGEST_A,
                source=ref("1"),
                first_seen_at=LONG_AGO,
            ),
        ),
    )


def test_a_pre_image_reads_back_as_the_pre_image_that_was_stored() -> None:
    """Every row, every key and every instant, including two entities sharing one observed name.
    Delete this and an unmerge can restore from a pre-image that lost a row on the way through the
    column, and nothing would say so."""
    pre = a_pre_image()
    assert pre_image_from(pre_image_document(pre)) == pre


def test_a_stored_pre_image_holding_anything_but_a_digest_is_refused_on_the_way_back() -> None:
    """The domain's constructors read the document back, so a row that could not have been
    captured cannot be restored from. Delete this and a hand-edited pre-image holding a raw
    address reads back as a join key."""
    document = pre_image_document(a_pre_image())
    document["identifiers"][0]["key_hash"] = "someone@example.com"
    with pytest.raises(ResolutionError):
        pre_image_from(document)


# ------------------------------------------------------------------------ invalidation
def test_every_surface_merge_names_has_an_invalidator_and_nothing_else_does() -> None:
    """Delete this and a fourth surface added to `InvalidatedSurface` is told of no merge, with a
    KeyError on the first merge after the commit as the only sign."""
    assert set(INVALIDATORS) == set(InvalidatedSurface)


def test_no_table_outside_entity_resolution_is_keyed_by_an_entity_id_but_the_projection() -> None:
    """**The claim the three invalidators rest on, measured against every model.** Each one evicts
    nothing because its surface holds nothing keyed by a canonical id, and the projection's
    `local_id` is deliberately left. Delete this and a table that starts holding an entity id
    (a memory about a client, say) is never reached by a merge, while every invalidator goes on
    reporting success."""
    found = {
        f"{table.fullname}.{column.name}"
        for table in metadata.tables.values()
        if table.schema != "er"
        for column in table.columns
        if column.name in ENTITY_KEYED_COLUMNS
    }
    assert found == set(ENTITY_KEYS_OUTSIDE_RESOLUTION)
    # The positive case: inside `er` the same scan finds the columns, so it is not blind.
    assert {
        f"{table.fullname}.{column.name}"
        for table in metadata.tables.values()
        if table.schema == "er"
        for column in table.columns
        if column.name in ENTITY_KEYED_COLUMNS
    } >= {"er.canonical.merged_into", "er.merge.merged_id", "er.unmerge.restored_id"}


def test_the_answer_caches_key_and_value_carry_no_entity_id() -> None:
    """`THE_ANSWER_CACHE_HOLDS_NOTHING_KEYED_BY_AN_ENTITY` names the key's parts. Delete this and
    an entity id added to the key leaves the cache's invalidator a no-op over entries a merge has
    made stale."""
    names = {field.name for field in dataclasses.fields(CacheKeyParts)} | {
        field.name for field in dataclasses.fields(CachedAnswer)
    }
    assert not names & ENTITY_KEYED_COLUMNS
    assert "source_epochs" in names


def test_every_surface_is_told_even_when_an_earlier_one_fails() -> None:
    """A failure on the cache is no reason to leave memory answering from before the merge.
    Delete this and the first surface that raises stops the others hearing of the merge, and the
    error names a surface but says nothing about the ones skipped."""
    told: dict[InvalidatedSurface, frozenset[str]] = {}

    def keeping(surface: InvalidatedSurface) -> merge_store.Invalidator:
        async def told_of(ids: frozenset[str]) -> None:
            told[surface] = ids

        return told_of

    async def failing(ids: frozenset[str]) -> None:
        raise RuntimeError(sorted(ids))

    invalidators = {surface: keeping(surface) for surface in InvalidatedSurface}
    invalidators[InvalidatedSurface.CACHE] = failing
    instructions = [
        Invalidation(surface=surface, entity_id=entity_id)
        for surface in InvalidatedSurface
        for entity_id in ("e1", "e2")
    ]
    with pytest.raises(merge_store.InvalidationIncompleteError, match="cache"):
        asyncio.run(invalidate(instructions, invalidators))
    assert told == {
        InvalidatedSurface.MEMORY: frozenset({"e1", "e2"}),
        InvalidatedSurface.PROJECTION: frozenset({"e1", "e2"}),
    }
    # The positive case: with nothing failing every surface is told and nothing is raised.
    invalidators[InvalidatedSurface.CACHE] = keeping(InvalidatedSurface.CACHE)
    asyncio.run(invalidate(instructions, invalidators))
    assert by_surface(instructions) == told


def test_unattended_merging_ships_off_and_is_read_by_the_merge_alone() -> None:
    """Delete this and the switch can lose its reader, so the Features screen turns a row nothing
    reads while automatic merges go on, or stop, regardless."""
    assert UNATTENDED_ENTITY_MERGE in FEATURES
    assert UNATTENDED_ENTITY_MERGE.read_by == ("brain.resolution.merge_store:merge_entities",)


# ------------------------------------------------------------------ against a database
def entity_row(url: str, entity_id: str, record: str) -> None:
    sql(
        url,
        "INSERT INTO er.canonical (entity_id, entity_type, created_at, created_by,"
        " created_from_source, created_from_entity, created_from_source_id)"
        " VALUES (%s, 'company', %s, 'a-backfill', 'freshdesk', 'company', %s)",
        entity_id,
        LONG_AGO,
        record,
    )
    sql(
        url,
        "INSERT INTO er.link (source, entity, source_id, entity_id, confidence, linked_at)"
        " VALUES ('freshdesk', 'company', %s, %s, 0.9, %s)",
        record,
        entity_id,
        LONG_AGO,
    )
    sql(
        url,
        "INSERT INTO er.alias (source, entity, source_id, name, entity_id, first_seen_at)"
        " VALUES ('freshdesk', 'company', %s, %s, %s, %s)",
        record,
        SHARED_NAME,
        entity_id,
        LONG_AGO,
    )
    sql(
        url,
        "INSERT INTO er.identifier (source, entity, source_id, kind, key_hash, entity_id,"
        " first_seen_at) VALUES ('freshdesk', 'company', %s, 'uen', %s, %s, %s)",
        record,
        DIGEST_A,
        entity_id,
        LONG_AGO,
    )


def children(url: str, *ids: str) -> list[tuple[Any, ...]]:
    """Every link, alias and identifier naming one of `ids`, as the rows stand."""
    found: list[tuple[Any, ...]] = []
    for table, columns in (
        ("er.link", "source_id, entity_id, confidence, linked_at"),
        ("er.alias", "source_id, name, entity_id, first_seen_at"),
        ("er.identifier", "source_id, kind, key_hash, entity_id, first_seen_at"),
    ):
        found += [
            (table, *row)
            for row in sql(
                url,
                f"SELECT {columns} FROM {table} WHERE entity_id = ANY(%s) ORDER BY 1, 2",  # noqa: S608
                list(ids),
            )
        ]
    return found


def canonical(url: str, entity_id: str) -> tuple[Any, ...]:
    [row] = sql(
        url,
        "SELECT entity_id, entity_type, created_at, created_by, created_from_source,"
        " created_from_entity, created_from_source_id, merged_into, merged_at"
        " FROM er.canonical WHERE entity_id = %s",
        entity_id,
    )
    return row


def ledger(url: str, trace: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT action, actor_id, subject, details FROM obs.audit_entry WHERE trace_id = %s"
        " ORDER BY seq",
        trace,
    )


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_merge_store") as url:
        yield url


def store_merge(url: str, survivor: str, merged: str, **kwargs: Any) -> Any:
    async def go() -> Any:
        engine = app_engine(url)
        try:
            return await merge_entities(
                make_session_factory(engine),
                survivor_id=survivor,
                merged_id=merged,
                **{"authority": reviewed(), "at": LONG_AGO, "trace_id": "t-merge", **kwargs},
            )
        finally:
            await engine.dispose()

    return run(go)


def store_unmerge(url: str, merge_id: str, **kwargs: Any) -> Any:
    async def go() -> Any:
        engine = app_engine(url)
        try:
            return await unmerge_entities(
                make_session_factory(engine),
                merge_id=merge_id,
                **{
                    "performed_by": "u_undoer",
                    "reason": "two clients, one name",
                    "at": LONG_AGO + timedelta(days=1),
                    "trace_id": "t-unmerge",
                    **kwargs,
                },
            )
        finally:
            await engine.dispose()

    return run(go)


@pytest.mark.needs_db
def test_a_reviewed_merge_moves_one_pointer_and_records_who_when_and_on_what(install: str) -> None:
    """M14.5.2 and M14.5.4 together, as the application role: the merged entity's pointer and
    instant move and nothing else on it, no link, alias or identifier of either side changes, the
    `er.merge` row names the reviewer, the instant, the review and the evidence as names and
    weights, and the ledger holds one entry per side naming the reviewer and the merge. Delete
    this and the store can rewrite a child row, or record a merge that names nobody."""
    entity_row(install, "m1_kept", "m1-k")
    entity_row(install, "m1_gone", "m1-g")
    before = children(install, "m1_kept", "m1_gone")
    kept_before, gone_before = canonical(install, "m1_kept"), canonical(install, "m1_gone")

    outcome = store_merge(install, "m1_kept", "m1_gone", trace_id="t-m1", reason="one uen")

    assert children(install, "m1_kept", "m1_gone") == before
    assert canonical(install, "m1_kept") == kept_before
    assert canonical(install, "m1_gone") == (*gone_before[:7], "m1_kept", LONG_AGO)
    merge_id = outcome.audit.merge_id
    [row] = sql(
        install,
        "SELECT survivor_id, merged_id, decided_at, decided_by, automatic, confidence,"
        " review_ref, evidence, money_left, reason FROM er.merge WHERE merge_id = %s",
        merge_id,
    )
    assert row == (
        "m1_kept",
        "m1_gone",
        LONG_AGO,
        "u_reviewer",
        False,
        None,
        "rev-1",
        [{"field": "uen", "weight": 10.0}, {"field": "name", "weight": 3.5}],
        "not checked",
        "one uen",
    )
    assert ledger(install, "t-m1") == [
        ("entity_merge", "u_reviewer", "entity:m1_kept", {"merge_id": merge_id}),
        ("entity_merge", "u_reviewer", "entity:m1_gone", {"merge_id": merge_id}),
    ]


@pytest.mark.needs_db
def test_the_pre_image_holds_every_row_of_both_families_as_it_stood(install: str) -> None:
    """M14.5.1: the survivor already has an entity merged into it, and the pre-image of the next
    merge holds that entity's rows too, both entities as they stood, and every link, alias and
    identifier, including two rows for one shared name. Delete this and an unmerge after a
    second merge restores from a pre-image missing the first merge's rows."""
    for one in ("m2_kept", "m2_earlier", "m2_gone"):
        entity_row(install, one, one.replace("_", "-"))
    store_merge(install, "m2_kept", "m2_earlier", trace_id="t-m2a")
    rows = children(install, "m2_kept", "m2_earlier", "m2_gone")
    outcome = store_merge(install, "m2_kept", "m2_gone", trace_id="t-m2b")

    [(stored,)] = sql(
        install, "SELECT pre_image FROM er.merge WHERE merge_id = %s", outcome.audit.merge_id
    )
    pre = pre_image_from(stored)
    assert pre == outcome.pre_image
    assert pre.survivor.entity_id == "m2_kept" and pre.survivor.is_current
    assert pre.merged.entity_id == "m2_gone" and pre.merged.is_current
    assert {one.entity_id for one in pre.links} == {"m2_kept", "m2_earlier", "m2_gone"}
    assert len(pre.links) + len(pre.aliases) + len(pre.identifiers) == len(rows)
    assert [one.name for one in pre.aliases] == [SHARED_NAME] * 3


@pytest.mark.needs_db
def test_an_automatic_merge_waits_for_its_switch_and_a_reviewed_one_never_does(
    install: str,
) -> None:
    """Off, an automatic merge is refused with nothing written; on, the same merge is made and
    records the cascade's confidence and no review. A reviewed merge was made above with the
    switch off. Delete this and an install merges unattended before its owner has decided it
    may."""
    entity_row(install, "m3_kept", "m3-k")
    entity_row(install, "m3_gone", "m3-g")
    with pytest.raises(MergeRefusedError) as refused:
        store_merge(install, "m3_kept", "m3_gone", authority=automatic(), trace_id="t-m3a")
    assert str(refused.value) == merge_store.UNATTENDED_MERGING_WAITS_FOR_ITS_SWITCH
    assert canonical(install, "m3_gone")[7] is None
    assert sql(install, "SELECT count(*) FROM er.merge WHERE merged_id = 'm3_gone'") == [(0,)]
    assert ledger(install, "t-m3a") == []

    async def on() -> None:
        engine = app_engine(install)
        try:
            async with make_session_factory(engine)() as session:
                await switch(session, UNATTENDED_ENTITY_MERGE, on=True, by="u_admin")
                await session.commit()
        finally:
            await engine.dispose()

    run(on)
    try:
        outcome = store_merge(
            install, "m3_kept", "m3_gone", authority=automatic(), trace_id="t-m3b"
        )
    finally:
        sql(
            install,
            "UPDATE ops.setting SET value = 'false' WHERE key = %s",
            UNATTENDED_ENTITY_MERGE.key,
        )
    [(automatic_, confidence, review_ref, decided_by)] = sql(
        install,
        "SELECT automatic, confidence, review_ref, decided_by FROM er.merge WHERE merge_id = %s",
        outcome.audit.merge_id,
    )
    assert (automatic_, review_ref, decided_by) == (True, None, "resolver-job")
    assert confidence == outcome.audit.confidence
    assert canonical(install, "m3_gone")[7] == "m3_kept"


@pytest.mark.needs_db
def test_an_unmerge_clears_the_one_pointer_and_an_old_id_resolves_again_to_itself(
    install: str,
) -> None:
    """M14.5.3: after the unmerge both entities are exactly the pre-image's, no child row moved in
    either direction, the unmerge row names who and why, the ledger holds one `entity_unmerge`
    per side naming the merge and the unmerge, and the merged entity's alias resolves to it
    again where during the merge it resolved to the survivor. Delete this and an unmerge can
    leave the pointer, rewrite child rows from a recompute, or go unrecorded."""
    entity_row(install, "m4_kept", "m4-k")
    entity_row(install, "m4_gone", "m4-g")
    rows = children(install, "m4_kept", "m4_gone")
    outcome = store_merge(install, "m4_kept", "m4_gone", trace_id="t-m4a")
    during = sql(
        install, "SELECT entity_id FROM er.resolved_alias WHERE observed_entity_id = 'm4_gone'"
    )
    restoration = store_unmerge(install, outcome.audit.merge_id, trace_id="t-m4b")

    assert during == [("m4_kept",)]
    assert sql(
        install, "SELECT entity_id FROM er.resolved_alias WHERE observed_entity_id = 'm4_gone'"
    ) == [("m4_gone",)]
    assert children(install, "m4_kept", "m4_gone") == rows
    for entity in outcome.pre_image.survivor, outcome.pre_image.merged:
        row = canonical(install, entity.entity_id)
        assert (row[0], row[2], row[3], row[7], row[8]) == (
            entity.entity_id,
            entity.created_at,
            entity.created_by,
            entity.merged_into or None,
            entity.merged_at,
        )
    unmerge_id = restoration.audit.unmerge_id
    assert sql(
        install,
        "SELECT merge_id, survivor_id, restored_id, performed_by, reason FROM er.unmerge"
        " WHERE unmerge_id = %s",
        unmerge_id,
    ) == [(outcome.audit.merge_id, "m4_kept", "m4_gone", "u_undoer", "two clients, one name")]
    named = {"merge_id": outcome.audit.merge_id, "unmerge_id": unmerge_id}
    assert ledger(install, "t-m4b") == [
        ("entity_unmerge", "u_undoer", "entity:m4_kept", named),
        ("entity_unmerge", "u_undoer", "entity:m4_gone", named),
    ]


@pytest.mark.needs_db
def test_only_the_merge_in_force_is_reversed(install: str) -> None:
    """An id nobody issued, a merge already reversed, and a merge superseded by a later merge of
    the same pair are each refused with nothing written; the later merge itself unmerges. Delete
    this and an old merge id clears a newer merge's pointer under the old merge's name."""
    entity_row(install, "m5_kept", "m5-k")
    entity_row(install, "m5_gone", "m5-g")
    first = store_merge(install, "m5_kept", "m5_gone", trace_id="t-m5a")
    store_unmerge(install, first.audit.merge_id, trace_id="t-m5b")
    with pytest.raises(MergeRefusedError):
        store_unmerge(install, first.audit.merge_id, trace_id="t-m5c")
    second = store_merge(
        install, "m5_kept", "m5_gone", trace_id="t-m5d", at=LONG_AGO + timedelta(days=2)
    )
    with pytest.raises(MergeRefusedError):
        store_unmerge(install, first.audit.merge_id, trace_id="t-m5e")
    with pytest.raises(MergeRefusedError):
        store_unmerge(install, "f" * 32, trace_id="t-m5f")
    assert canonical(install, "m5_gone")[7] == "m5_kept"
    assert ledger(install, "t-m5c") == ledger(install, "t-m5e") == ledger(install, "t-m5f") == []
    store_unmerge(install, second.audit.merge_id, trace_id="t-m5g")
    assert canonical(install, "m5_gone")[7] is None


@pytest.mark.needs_db
def test_a_merge_the_domain_refuses_writes_nothing(install: str) -> None:
    """Merging into an entity that is itself merged is refused by `merge`, and the store has
    written no row, no pointer and no entry by then. Delete this and a refusal can leave a merge
    row behind describing a merge that never happened."""
    entity_row(install, "m6_kept", "m6-k")
    entity_row(install, "m6_stub", "m6-s")
    entity_row(install, "m6_gone", "m6-g")
    store_merge(install, "m6_kept", "m6_stub", trace_id="t-m6a")
    with pytest.raises(ResolutionError):
        store_merge(install, "m6_stub", "m6_gone", trace_id="t-m6b")
    assert sql(install, "SELECT count(*) FROM er.merge WHERE merged_id = 'm6_gone'") == [(0,)]
    assert canonical(install, "m6_gone")[7] is None
    assert ledger(install, "t-m6b") == []


@pytest.mark.needs_db
def test_a_merge_row_in_anybody_elses_name_than_the_transactions_is_refused(install: str) -> None:
    """`0183`'s policy: the row's `decided_by` is the transaction's actor, which is who the ledger
    entry names. Delete this and a merge row and its ledger entry can name two different people."""
    entity_row(install, "m7_kept", "m7-k")
    entity_row(install, "m7_gone", "m7-g")
    statement = (
        "INSERT INTO er.merge (merge_id, survivor_id, merged_id, decided_at, decided_by,"
        " automatic, review_ref, evidence, money_left, money_right, reason, pre_image)"
        " VALUES (%s, 'm7_kept', 'm7_gone', %s, %s, false, 'rev', '[]', 'not checked',"
        " 'not checked', '', '{}')"
    )
    with psycopg.connect(install, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT set_config('brain.actor_id', 'u_actor', false)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement, ("1" * 32, LONG_AGO, "u_somebody_else"))
        conn.execute(statement, ("2" * 32, LONG_AGO, "u_actor"))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE er.merge SET reason = 'rewritten'")
    assert sql(install, "SELECT merge_id FROM er.merge WHERE merged_id = 'm7_gone'") == [
        ("2" * 32,)
    ]


@pytest.mark.needs_db
def test_the_columns_refuse_a_raw_identifier_and_evidence_that_carries_a_value(
    install: str,
) -> None:
    """The two jsonb constraints, each refused and each sibling admitted. Delete this and a
    pre-image can hold a raw address where `er.identifier` holds a digest, or the evidence what a
    field said."""
    entity_row(install, "m8_kept", "m8-k")
    entity_row(install, "m8_gone", "m8-g")
    statement = (
        "INSERT INTO er.merge (merge_id, survivor_id, merged_id, decided_at, decided_by,"
        " automatic, review_ref, evidence, money_left, money_right, reason, pre_image)"
        " VALUES (%s, 'm8_kept', 'm8_gone', %s, 'u_actor', false, 'rev', %s, 'not checked',"
        " 'not checked', '', %s)"
    )
    raw = '{"identifiers": [{"key_hash": "someone@example.com"}]}'
    digest = '{"identifiers": [{"key_hash": "' + DIGEST_B + '"}]}'
    valued = '[{"field": "uen", "weight": 1.0, "value": "201912345K"}]'
    named = '[{"field": "uen", "weight": 1.0}]'
    with psycopg.connect(install, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT set_config('brain.actor_id', 'u_actor', false)")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(statement, ("3" * 32, LONG_AGO, named, raw))
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(statement, ("4" * 32, LONG_AGO, valued, digest))
        conn.execute(statement, ("5" * 32, LONG_AGO, named, digest))


@pytest.mark.needs_db
def test_a_pointer_cleared_by_hand_is_recorded_as_an_unmerge_naming_no_merge(install: str) -> None:
    """The trigger, not the store, writes the unmerge entry, so a pointer cleared by an UPDATE
    nobody routed through the store is still on the ledger, with no ids to say it came from no
    review. Delete this and a hand repair undoes a merge with nothing recorded."""
    entity_row(install, "m9_kept", "m9-k")
    entity_row(install, "m9_gone", "m9-g")
    store_merge(install, "m9_kept", "m9_gone", trace_id="t-m9a")
    with psycopg.connect(install, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT set_config('brain.actor_id', 'u_hand', false)")
        conn.execute("SELECT set_config('brain.trace_id', 't-m9b', false)")
        conn.execute(
            "UPDATE er.canonical SET merged_into = NULL, merged_at = NULL"
            " WHERE entity_id = 'm9_gone'"
        )
    assert ledger(install, "t-m9b") == [
        ("entity_unmerge", "u_hand", "entity:m9_kept", {}),
        ("entity_unmerge", "u_hand", "entity:m9_gone", {}),
    ]


@pytest.mark.needs_db
def test_every_id_of_both_families_reaches_every_surface_on_a_merge_and_an_unmerge(
    install: str,
) -> None:
    """M14.5.5: each side already has an entity merged into it, and every surface is handed all
    four ids by the merge and again by the unmerge, including the two nobody was asking with.
    Delete this and an invalidation can cover the survivor alone, leaving every entry keyed on
    the losing family's ids answering from before the merge."""
    for one in ("m10_kept", "m10_k_stub", "m10_gone", "m10_g_stub"):
        entity_row(install, one, one.replace("_", "-"))
    store_merge(install, "m10_kept", "m10_k_stub", trace_id="t-m10a")
    store_merge(install, "m10_gone", "m10_g_stub", trace_id="t-m10b")
    told: list[tuple[InvalidatedSurface, frozenset[str]]] = []

    def keeping(surface: InvalidatedSurface) -> merge_store.Invalidator:
        async def told_of(ids: frozenset[str]) -> None:
            told.append((surface, ids))

        return told_of

    invalidators = {surface: keeping(surface) for surface in InvalidatedSurface}
    outcome = store_merge(
        install, "m10_kept", "m10_gone", trace_id="t-m10c", invalidators=invalidators
    )
    store_unmerge(install, outcome.audit.merge_id, trace_id="t-m10d", invalidators=invalidators)
    every = frozenset({"m10_kept", "m10_k_stub", "m10_gone", "m10_g_stub"})
    assert sorted(told) == sorted([(surface, every) for surface in InvalidatedSurface] * 2)


@pytest.mark.needs_db
def test_a_pointer_the_database_holds_is_never_overwritten_whatever_was_read(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The UPDATE's own WHERE clause is the last guard: when what was read says the entity is
    current and the database says it is merged elsewhere, the merge is refused and its row rolled
    back; and an unmerge whose read says the pointer stands, over a pointer already cleared, is
    refused with no unmerge row. Delete this and a read that went stale under a lock somebody
    removed overwrites an earlier merge, leaving its pre-image describing a graph that is gone."""
    for one in ("m11_kept", "m11_gone", "m11_other"):
        entity_row(install, one, one.replace("_", "-"))
    store_merge(install, "m11_other", "m11_gone", trace_id="t-m11a")
    real = merge_store._graph

    async def stale(session: Any, heads: Any) -> Any:
        entities, *rest = await real(session, heads)
        seen = {
            key: dataclasses.replace(one, merged_into="", merged_at=None)
            if key == "m11_gone"
            else one
            for key, one in entities.items()
        }
        return (seen, *rest)

    monkeypatch.setattr(merge_store, "_graph", stale)
    with pytest.raises(MergeRefusedError) as refused:
        store_merge(install, "m11_kept", "m11_gone", trace_id="t-m11b")
    assert str(refused.value) == merge_store.ONE_MERGE_IS_ONE_TRANSACTION
    assert canonical(install, "m11_gone")[7] == "m11_other"
    assert sql(install, "SELECT survivor_id FROM er.merge WHERE merged_id = 'm11_gone'") == [
        ("m11_other",)
    ]
    monkeypatch.setattr(merge_store, "_graph", real)

    entity_row(install, "m12_kept", "m12-k")
    entity_row(install, "m12_gone", "m12-g")
    outcome = store_merge(install, "m12_kept", "m12_gone", trace_id="t-m12a")
    sql(
        install,
        "UPDATE er.canonical SET merged_into = NULL, merged_at = NULL WHERE entity_id = 'm12_gone'",
    )

    async def still_merged(session: Any, heads: Any) -> Any:
        entities, *rest = await real(session, heads)
        entities["m12_gone"] = dataclasses.replace(
            entities["m12_gone"], merged_into="m12_kept", merged_at=LONG_AGO
        )
        return (entities, *rest)

    monkeypatch.setattr(merge_store, "_graph", still_merged)
    with pytest.raises(MergeRefusedError) as refused:
        store_unmerge(install, outcome.audit.merge_id, trace_id="t-m12b")
    assert str(refused.value) == merge_store.ONLY_THE_MERGE_IN_FORCE_IS_REVERSED
    assert sql(
        install, "SELECT count(*) FROM er.unmerge WHERE merge_id = %s", outcome.audit.merge_id
    ) == [(0,)]
