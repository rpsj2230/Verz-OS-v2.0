"""The escalation rows: who reads a handoff, who records how it went, and who may expire it.

The first half needs no server: the migration's copied grammars and widths held to the live ones,
and how a queue's row is read. The second half builds a database at head and drives `0168` as the
application role, as a request does: a handoff is routed to the person named for its queue when it
arrives; the asker and that person read it and nobody else does; a handoff routed to nobody is read
by whoever is named later; how its delivery went is recorded once, by the asker's session alone; no
application session can mark it expired; and the worker's login marks exactly the due ones. A
skill's declaration is stored in its three columns and reads back as the skill that was approved.
**It skips when there is no server**, and CI always has one.

Task ids: M8.3.1, M8.3.2, M8.3.4
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import psycopg
import pytest

from brain.audit.ledger import IDENTIFIER
from brain.gate.abstain import EscalationRoute, EscalationTrigger
from brain.gate.caches import MAX_QUESTION_CHARS
from brain.gate.context import Channel
from brain.gate.escalating import escalation_for
from brain.ops.escalation_store import (
    NamingRefusedError,
    StoredEscalations,
    expire_overdue,
    route_key,
    route_of,
)
from brain.ops.setting_store import SettingState
from brain.session import make_session_factory
from brain.tables import escalation as escalation_table
from brain.tables import skill as skill_table
from brain.tables.escalation import EscalationDelivery
from brain.tables.identity import PRINCIPAL_ID_CHARS
from brain.tools import skills
from brain.tools.skills import skill_from_markdown
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION: Final = VERSIONS / "0168_escalation.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

QUEUE: Final = "pricing"
NEEDS: Final = "Somebody who can quote outside the price list"


# ------------------------------------------------------------ the migration and the model
def test_the_migration_copies_the_live_grammars_and_widths() -> None:
    """Delete this and the table `0168` builds can drift from what the product writes, so a queue,
    a sentence or a question the product produces is refused by a constraint nobody updated."""
    migration = migration_module(MIGRATION)
    assert skills.ESCALATION_QUEUE_RE.pattern == migration.ESCALATION_QUEUE_PATTERN
    assert migration.ESCALATION_QUEUE_PATTERN == skill_table.ESCALATION_QUEUE_PATTERN
    assert migration.ESCALATION_NEEDS_CHARS == skills.ESCALATION_NEEDS_CHARS
    assert migration.ESCALATION_NEEDS_CHARS == skill_table.ESCALATION_NEEDS_CHARS
    assert migration.MAX_ESCALATION_HOURS == skills.MAX_ESCALATION_HOURS
    assert migration.MAX_ESCALATION_HOURS == skill_table.MAX_ESCALATION_HOURS
    assert migration.MAX_QUESTION_CHARS == MAX_QUESTION_CHARS
    assert escalation_table.MAX_QUESTION_CHARS == MAX_QUESTION_CHARS
    assert migration.IDENTIFIER == IDENTIFIER
    assert migration.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    triggers = set(re.findall(r"'([a-z ]+)'", migration.TRIGGERS))
    assert triggers == {one.value for one in EscalationTrigger}
    deliveries = set(re.findall(r"'([a-z_]+)'", migration.DELIVERIES))
    assert deliveries == {one.value for one in EscalationDelivery}


def test_0168_emits_the_amendments_the_model_comparison_believes() -> None:
    """`AMENDS_CREATE_TABLE` is a claim the DDL comparison in `tests/unit/test_skill_store.py`
    trusts. Each added column is emitted, and each check the model declares on the skill's
    escalation is emitted under the model's name with the model's predicate.

    Delete this and `0168` can say it added a column or a check while its upgrade does neither, and
    every comparison built on the claim stays green."""
    from brain.db import Base
    from tests.unit.test_tables import rendered, squash

    emitted = squash(rendered("upgrade", MIGRATION))
    model = {
        str(one.name): str(one.sqltext)
        for one in Base.metadata.tables["agent.skill"].constraints
        if hasattr(one, "sqltext")
    }
    for column, kind in (
        ("escalate_to", "VARCHAR(60)"),
        ("escalation_needs", "VARCHAR(300)"),
        ("escalate_within", "SMALLINT"),
    ):
        assert f"ALTER TABLE agent.skill ADD COLUMN {column} {kind}" in emitted
    for name in ("escalate_to_shape", "an_escalation_says_what_it_needs", "escalate_within_hours"):
        assert (
            f"ALTER TABLE agent.skill ADD CONSTRAINT ck_skill_{name} "
            f"CHECK ({model[f'ck_skill_{name}']})"
        ) in emitted


def test_every_way_a_channel_answers_is_a_delivery_a_row_can_record() -> None:
    """Held against the channel's own outbound outcomes rather than against itself. Delete this and
    a vendor answer the sender can come to is refused by the row's constraint, so the handoff was
    sent and its row says nothing."""
    from brain.tables.channel import DeliveryOutcome

    outbound = {DeliveryOutcome.SENT, DeliveryOutcome.REFUSED, DeliveryOutcome.UNKNOWN}
    assert {one.value for one in outbound} <= {one.value for one in EscalationDelivery}


def _state(value: Any) -> SettingState:
    return SettingState(
        key=route_key(QUEUE),
        value_type="json",
        value=value,
        updated_by="u_admin",
        updated_at=LONG_AGO,
    )


def test_a_queue_s_row_names_a_person_a_channel_and_an_address_or_routes_nothing() -> None:
    """The positive case and the malformed ones. Delete this and a row somebody wrote by hand with
    no person, or a channel this release does not know, routes a question to nowhere as though it
    were somewhere."""
    good = route_of(QUEUE, _state({"person": "u_p", "channel": "webhook", "address": "desk"}))
    assert good is not None and (good.person, good.channel, good.address) == (
        "u_p",
        Channel.WEBHOOK,
        "desk",
    )
    for bad in (
        "u_p",
        {"channel": "webhook", "address": "desk"},
        {"person": "u_p", "channel": "carrier pigeon", "address": "desk"},
        {"person": "u_p", "channel": "webhook"},
        None,
    ):
        assert route_of(QUEUE, _state(bad)) is None


# ------------------------------------------------------------------ against a database
PEOPLE: Final = ("u_admin", "u_asker", "u_person", "u_other", "u_later")


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_escalation_store") as url:
        for pid in PEOPLE:
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name) "
                "VALUES (%s, 'human', 'staff', %s) ON CONFLICT (id) DO NOTHING",
                pid,
                pid,
            )
        yield url


def _escalation(queue: str = QUEUE, *, now: datetime = LONG_AGO) -> Any:
    skill = skill_from_markdown(
        "\n".join(
            [
                "---",
                "name: quote-desk",
                "description: Use when a client asks for a price the list does not hold",
                f"escalate_to: {queue}",
                f"escalation_needs: {NEEDS}",
                "escalate_within: 1",
                "---",
                "Hand it on.",
            ]
        )
    )
    return escalation_for(
        skill,
        route=EscalationRoute(queue=queue, channel=Channel.CONSOLE),
        asker_id="u_asker",
        question="What does the premium plan cost for a charity?",
        trace_ref="t-escalation",
        now=now,
    )


def _with(url: str, work: Any) -> Any:
    async def go() -> Any:
        engine = app_engine(url)
        try:
            return await work(StoredEscalations(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


@pytest.mark.needs_db
def test_a_handoff_goes_to_the_person_named_and_is_read_by_them_and_its_asker_alone(
    install: str,
) -> None:
    """Named, filed, and read under `0168`'s policy by each of three people. Delete this and a
    handoff can be read by anybody on the install, which is the asker's question in their own
    words shown to people it was never handed to."""

    async def work(store: StoredEscalations) -> dict[str, Any]:
        named = await store.name_route(
            QUEUE,
            "u_person",
            Channel.WEBHOOK,
            "desk",
            by="u_admin",
            ent_hash="0" * 32,
            trace_id="t-name",
        )
        filed = await store.file(
            _escalation(), skill_name="quote-desk", agent_id="agent_quotes", ent_hash="0" * 32
        )
        return {
            "named": named,
            "filed": filed,
            "asker": await store.mine("u_asker"),
            "person": await store.mine("u_person"),
            "other": await store.mine("u_other"),
        }

    said = _with(install, work)
    assert said["filed"].route is not None and said["filed"].route.person == "u_person"
    for reader in ("asker", "person"):
        [one] = [row for row in said[reader] if row.escalation_id == said["filed"].escalation_id]
        assert (one.routed_to, one.needed, one.expired_at) == ("u_person", NEEDS, None)
    assert said["other"] == ()


@pytest.mark.needs_db
def test_a_handoff_routed_to_nobody_is_read_by_whoever_is_named_next(install: str) -> None:
    """`0104`'s rule for a sensitive referral, applied to a queue. Delete this and the first
    question a skill escalates before anybody is named for its queue is never read by anybody."""

    async def work(store: StoredEscalations) -> tuple[Any, Any, Any]:
        filed = await store.file(
            _escalation("unnamed_queue"),
            skill_name="quote-desk",
            agent_id="agent_quotes",
            ent_hash="0" * 32,
        )
        before = await store.mine("u_later")
        await store.name_route(
            "unnamed_queue",
            "u_later",
            Channel.WEBHOOK,
            "later-desk",
            by="u_admin",
            ent_hash="0" * 32,
            trace_id="t-later",
        )
        return filed, before, await store.mine("u_later")

    filed, before, after = _with(install, work)
    assert filed.route is None
    assert all(one.escalation_id != filed.escalation_id for one in before)
    assert [one.escalation_id for one in after if one.escalation_id == filed.escalation_id] == [
        filed.escalation_id
    ]


@pytest.mark.needs_db
def test_a_person_who_is_not_here_cannot_be_named_for_a_queue(install: str) -> None:
    """Delete this and a queue can be routed to a name that belongs to nobody, so every question
    handed to it is read by nobody."""

    async def work(store: StoredEscalations) -> None:
        await store.name_route(
            QUEUE,
            "u_nobody",
            Channel.WEBHOOK,
            "desk",
            by="u_admin",
            ent_hash="0" * 32,
            trace_id="t",
        )

    with pytest.raises(NamingRefusedError):
        _with(install, work)


@pytest.mark.needs_db
def test_how_a_delivery_went_is_recorded_once_and_by_the_asker_s_session_alone(
    install: str,
) -> None:
    """Delete this and the named person, or anybody, could mark a handoff sent that never was, and
    a second recording could overwrite what the vendor really said."""

    async def work(store: StoredEscalations) -> tuple[bool, bool, bool]:
        filed = await store.file(
            _escalation(), skill_name="quote-desk", agent_id="agent_quotes", ent_hash="0" * 32
        )
        by_person = await store.record_delivery(
            filed.escalation_id,
            asker_id="u_person",
            delivery=EscalationDelivery.SENT,
            at=LONG_AGO,
        )
        first = await store.record_delivery(
            filed.escalation_id,
            asker_id="u_asker",
            delivery=EscalationDelivery.REFUSED,
            at=LONG_AGO,
        )
        again = await store.record_delivery(
            filed.escalation_id,
            asker_id="u_asker",
            delivery=EscalationDelivery.SENT,
            at=LONG_AGO,
        )
        return by_person, first, again

    assert _with(install, work) == (False, True, False)


@pytest.mark.needs_db
def test_no_application_session_can_mark_a_handoff_expired(install: str) -> None:
    """`0168` grants UPDATE on the two delivery columns alone. Delete this and an asker, or anybody
    whose session can reach the row, marks a handoff expired so nobody is ever asked to pick it
    up."""
    [(row_id,)] = sql(
        install,
        "SELECT id FROM gate.escalation WHERE asker_id = 'u_asker' ORDER BY raised_at LIMIT 1",
    )
    with psycopg.connect(install, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT set_config('app.principal_id', 'u_asker', false)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "UPDATE gate.escalation SET expired_at = expires_at WHERE id = %s", (row_id,)
            )


@pytest.mark.needs_db
def test_the_worker_s_login_marks_exactly_the_handoffs_that_are_due(install: str) -> None:
    """Run as the database owner, as the worker's control runs it. Delete this and the expiry can
    mark a handoff before its deadline, which tells an asker nobody picked up a question somebody
    still had time to."""
    future = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

    async def file_one(store: StoredEscalations) -> str:
        filed = await store.file(
            _escalation(now=future),
            skill_name="quote-desk",
            agent_id="agent_quotes",
            ent_hash="0" * 32,
        )
        return filed.escalation_id

    not_yet = _with(install, file_one)

    async def expire(at: datetime) -> int:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from brain.db import normalise_database_url

        engine = create_async_engine(normalise_database_url(install), poolclass=NullPool)
        try:
            async with make_session_factory(engine)() as session, session.begin():
                return await expire_overdue(session, now=at)
        finally:
            await engine.dispose()

    marked = run(lambda: expire(LONG_AGO + timedelta(days=1)))
    assert marked >= 1
    pending = sql(install, "SELECT expired_at FROM gate.escalation WHERE id = %s", not_yet)
    assert pending == [(None,)]
    due = sql(
        install,
        "SELECT count(*) FROM gate.escalation WHERE expires_at <= %s AND expired_at IS NULL",
        LONG_AGO + timedelta(days=1),
    )
    assert due == [(0,)]
    assert run(lambda: expire(future + timedelta(hours=1))) >= 1
    assert sql(
        install, "SELECT expired_at IS NOT NULL FROM gate.escalation WHERE id = %s", not_yet
    ) == [(True,)]


@pytest.mark.needs_db
def test_a_skill_s_escalation_is_stored_and_reads_back_as_the_skill_that_was_approved(
    install: str,
) -> None:
    """Through the library's own add and read. Delete this and a stored skill reads back without
    its declaration, so its digest no longer matches its key, it reads as moved and is never
    offered, and nothing it declares ever escalates."""
    from brain.console.skill_library import added, read_package
    from brain.ops.skill_store import StoredSkills

    text = "\n".join(
        [
            "---",
            "name: quote-desk-stored",
            "description: Use when a client asks for a price the list does not hold",
            f"escalate_to: {QUEUE}",
            f"escalation_needs: {NEEDS}",
            "escalate_within: 3",
            "---",
            "Hand it on.",
            "",
        ]
    ).encode("utf-8")
    made = added(read_package("SKILL.md", text), by="u_admin", at=LONG_AGO)

    async def go() -> Any:
        engine = app_engine(install)
        try:
            store = StoredSkills(make_session_factory(engine))
            await store.add(made, ent_hash="0" * 32, trace_id="t-skill")
            return await store.skill(made.digest)
        finally:
            await engine.dispose()

    found = run(go)
    assert found is not None and not found.moved
    assert found.imported.skill == made.imported.skill
    assert (found.imported.skill.escalate_to, found.imported.skill.escalate_within) == (QUEUE, 3)
