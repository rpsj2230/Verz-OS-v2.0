"""Telling one person something later: their own address, on the channel they last used, once.

The declarations half holds which channels keep a person's address (needs-rupash 118, widened to
every channel whose identity is a person's own) and that each of them can address a person while a
webhook cannot. The planning half drives `brain.tell_later.planned_for` over stores in memory. The
application half sends through the real events route's `deliver` to a Lark that records every
request, and the server half runs `StoredAddresses.last_used` against PostgreSQL at head.

Task ids: M8.3.4, M10.3.5
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.requests import Request

from brain.app import Settings, create_app
from brain.channels.adapter import PersonWire, channel_wires
from brain.channels.binding import settle
from brain.channels.email import WIRE as EMAIL_WIRE
from brain.channels.email import split_reply_address
from brain.channels.lark import LarkSecret
from brain.channels.slack import WIRE as SLACK_WIRE
from brain.core.entitlement import EntitlementSet
from brain.gate.context import Channel
from brain.gate.ingress import Binding, identity_hash
from brain.ops.binding_store import (
    A_WEBHOOK_ADDRESS_IS_A_SYSTEM_S_AND_NOT_A_PERSON_S,
    ADDRESS_KEPT_ON,
    LAST_USE_IS_KEPT_TO,
    StoredAddresses,
    StoredBindings,
)
from brain.ops.channel_store import ChannelRecord, channel_secret_ref
from brain.tables.channel import DeliveryOutcome
from brain.tell_later import planned_for, tell
from tests.fixtures.lark_events import (
    APP_ID,
    APP_SECRET,
    BOT_OPEN_ID,
    ENCRYPT_KEY,
    VERIFICATION_TOKEN,
)
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_api_routes import wiring
from tests.unit.test_approval_cards import ORIGIN, World
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_channel_pipeline import Secrets, fresh_record
from tests.unit.test_chat_answer import OPEN_IDS

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
WIDE = OPEN_IDS["u_wide"]


# ------------------------------------------------------------------------ declarations
def test_a_person_s_own_channels_keep_an_address_and_a_webhook_never_does() -> None:
    """**Needs-rupash 118, widened.** Lark, Slack and email keep a person's own address, because
    their identity is the person's; a webhook's identity is the calling system's endpoint and keeps
    none. Delete this and a later message can be sent to whatever system a webhook caller runs, or
    the widening can quietly drop a channel people write on."""
    assert frozenset({Channel.LARK, Channel.SLACK, Channel.EMAIL}) == ADDRESS_KEPT_ON
    assert Channel.WEBHOOK not in ADDRESS_KEPT_ON
    assert "calling system" in A_WEBHOOK_ADDRESS_IS_A_SYSTEM_S_AND_NOT_A_PERSON_S


def test_every_channel_that_keeps_an_address_can_write_to_its_person_and_a_webhook_cannot() -> None:
    """Delete this and an address kept on a channel whose wire cannot address a person is kept for
    nothing, or a webhook's wire grows a way to be written to unasked."""
    wires = channel_wires()
    for channel in ADDRESS_KEPT_ON:
        assert isinstance(wires[channel], PersonWire), channel
    assert not isinstance(wires[Channel.WEBHOOK], PersonWire)


def test_slack_and_email_address_a_person_where_their_own_send_step_takes_it() -> None:
    """The address `person_address` makes is one each wire's own request builder accepts: Slack's
    `user:` posts to the person's own conversation with the app, and email's bare address answers
    nothing. Delete this and a later message is built for an address its channel refuses."""
    slack = SLACK_WIRE.person_address("U0123ABCD")
    request = SLACK_WIRE.request_for(
        to=slack,
        text="hello",
        secret=json.dumps({"signing_secret": "s" * 32, "bot_token": "xoxb-test"}),
        tenant={},
        now=NOW,
    )
    assert slack == "user:U0123ABCD"
    assert request.url.endswith("/chat.postMessage")
    assert json.loads(request.body)["channel"] == "U0123ABCD"
    assert "U0123ABCD" not in request.url
    assert split_reply_address(EMAIL_WIRE.person_address("asker@example.invalid")) == (
        "asker@example.invalid",
        "",
    )


# ------------------------------------------------------------------------ planning
@dataclass
class LastUsed:
    """`LastUsedAddresses` over a dictionary of person to channel and address."""

    kept: dict[str, tuple[Channel, str]] = field(default_factory=dict)

    async def last_used(self, principal_id: str) -> tuple[Channel, str] | None:
        return self.kept.get(principal_id)


@dataclass
class Records:
    """`ChannelRecords`, reading only."""

    kept: dict[Channel, ChannelRecord] = field(default_factory=dict)

    async def get(self, channel: Channel) -> ChannelRecord | None:
        return self.kept.get(channel)

    async def every(self) -> tuple[ChannelRecord, ...]:
        return tuple(self.kept.values())

    async def save(self, *args: object, **kwargs: object) -> ChannelRecord:
        raise AssertionError("planning a later message writes no record")


@dataclass
class Reach:
    """`EntitlementStore` answering one reach for everybody, lapsed when told to be."""

    lapsed: bool = False

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(
            principal_id=principal_id,
            not_after=datetime(2019, 1, 1, tzinfo=UTC) if self.lapsed else None,
        )


def plan(
    addresses: LastUsed, records: Records, reach: Reach | None = None
) -> tuple[object, ...] | None:
    return asyncio.run(
        planned_for(
            "u_asker",
            "Nobody picked this up.",
            intent_ref="escalation_expired.e1",
            addresses=addresses,
            records=records,  # type: ignore[arg-type]
            reach=reach or Reach(),
            now=NOW,
        )
    )


def test_a_later_message_goes_to_the_person_s_own_address_at_the_reach_they_hold_now() -> None:
    """**The positive case.** One message, to the address `person_address` makes on the channel the
    person last used, naming them as its recipient and the digest of their reach now, keyed by the
    caller's intent. Delete this and every refusal below is satisfied by a planner that plans
    nothing."""
    planned = plan(
        LastUsed({"u_asker": (Channel.SLACK, "U0123ABCD")}),
        Records({Channel.SLACK: fresh_record(Channel.SLACK)}),
    )

    assert planned is not None
    outgoing, record = planned
    assert outgoing.channel is Channel.SLACK  # type: ignore[attr-defined]
    assert outgoing.to == "user:U0123ABCD"  # type: ignore[attr-defined]
    assert outgoing.recipient == "u_asker"  # type: ignore[attr-defined]
    assert outgoing.planned_hash == EntitlementSet(principal_id="u_asker").ent_hash()  # type: ignore[attr-defined]
    assert outgoing.intent.intent_ref == "escalation_expired.e1"  # type: ignore[attr-defined]
    assert record.channel is Channel.SLACK  # type: ignore[attr-defined]


def test_nothing_is_planned_with_no_address_on_a_channel_switched_off_or_for_a_lapsed_reach() -> (
    None
):
    """Delete this and a later message is invented for somebody with nowhere to send it, sent on a
    channel an administrator switched off, or sent to somebody who has left."""
    on = Records({Channel.SLACK: fresh_record(Channel.SLACK)})
    off = Records({Channel.SLACK: fresh_record(Channel.SLACK, enabled=False)})
    kept = LastUsed({"u_asker": (Channel.SLACK, "U0123ABCD")})

    assert plan(LastUsed(), on) is None
    assert plan(kept, Records()) is None
    assert plan(kept, off) is None
    assert plan(kept, on, Reach(lapsed=True)) is None


def test_a_webhook_address_a_store_returned_anyway_is_planned_nothing() -> None:
    """The store names no webhook address, and the planner refuses one too, so a second store
    cannot widen what is written to unasked. Delete this and a store's mistake reaches a system's
    endpoint."""
    planned = plan(
        LastUsed({"u_asker": (Channel.WEBHOOK, "https://hook.example.invalid/in")}),
        Records({Channel.WEBHOOK: fresh_record(Channel.WEBHOOK)}),
    )

    assert planned is None


def test_a_channel_the_decision_does_not_cover_is_refused_even_where_its_wire_could_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The planner asks `ADDRESS_KEPT_ON` itself rather than trusting the wire: with Slack taken
    out of the decision, a Slack address a store returned is planned nothing, though Slack's wire
    can address a person. Delete this and the day a wire for a channel nobody decided about grows
    `person_address`, a store's mistake writes to people there unasked."""
    import brain.tell_later

    monkeypatch.setattr(brain.tell_later, "ADDRESS_KEPT_ON", frozenset({Channel.LARK}))
    planned = plan(
        LastUsed({"u_asker": (Channel.SLACK, "U0123ABCD")}),
        Records({Channel.SLACK: fresh_record(Channel.SLACK)}),
    )

    assert isinstance(channel_wires()[Channel.SLACK], PersonWire)
    assert planned is None


# ------------------------------------------------------------------------ on the application
@pytest.fixture
def world() -> World:
    made = World()
    made.records.kept[Channel.LARK] = fresh_record(
        Channel.LARK,
        tenant={"app_id": APP_ID, "platform": "larksuite.com", "bot_id": BOT_OPEN_ID},
    )
    return made


@pytest.fixture
def app(world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.setenv("INSTALL_OIDC_REDIRECT_URIS", f"{ORIGIN}/callback")
    made: FastAPI = create_app(Settings(env="development"))
    kept = LarkSecret(
        app_secret=APP_SECRET, encrypt_key=ENCRYPT_KEY, verification_token=VERIFICATION_TOKEN
    ).kept()
    with TestClient(made, raise_server_exceptions=False):
        state = made.state
        state.gate = wiring()
        state.channel_records = world.records
        state.channel_deliveries = world.deliveries
        state.channel_secrets = Secrets({channel_secret_ref(Channel.LARK).path: kept})
        state.channel_transport = world.lark
        state.operation_ledger = world.ledger
        state.channel_addresses = LastUsedBook({"u_wide": (Channel.LARK, WIDE)})
        yield made


@dataclass
class LastUsedBook(LastUsed):
    """The address store the events route reads, in memory: `last_used` and nothing kept."""

    async def remember(self, channel: Channel, identity: str) -> bool:
        return False

    async def addressed(self, channel: Channel) -> tuple[tuple[str, str], ...]:
        return ()


def told(app: FastAPI, person: str, intent_ref: str) -> object:
    request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
    return asyncio.run(
        tell(request, person, "Nobody picked this up.", intent_ref=intent_ref, now=NOW)
    )


def test_a_person_is_told_once_in_their_own_lark_chat_through_the_events_route_s_send(
    app: FastAPI, world: World
) -> None:
    """Through the real `deliver`: one text to the person's own chat with the bot by open id in the
    body, never the URL; the same intent again sends nothing; somebody with no address is sent
    nothing. Delete this and a later message can go twice on a retry, into a URL a proxy logs, or
    to somebody the Brain has no address for."""
    first = told(app, "u_wide", "escalation_expired.e1")
    again = told(app, "u_wide", "escalation_expired.e1")
    nobody = told(app, "u_narrow", "escalation_expired.e2")

    assert first is not None and first.outcome is DeliveryOutcome.SENT  # type: ignore[attr-defined]
    assert nobody is None
    [(kind, where, text, card)] = world.lark.posted()
    assert (kind, where, text, card) == ("open_id", WIDE, "Nobody picked this up.", None)
    assert all(WIDE not in one.url for one in world.lark.sent)
    # The second call was planned and keyed on the same intent, so the ledger sent nothing more.
    assert again is not None
    assert len(world.lark.sent) == 1


# ------------------------------------------------------------------------ on a server
@pytest.fixture(scope="module")
def migrated() -> Iterator[str]:
    """Every migration that ships."""
    with retirable("brain_test_tell_later") as url:
        if not has_pgvector(url):
            pytest.skip("the migrations to head need pgvector, which CI's server has")
        yield url


CAROL = "u_tell_carol"


@pytest.mark.needs_db
def test_the_channel_a_person_last_wrote_on_is_the_one_they_are_told_on(migrated: str) -> None:
    """**`THE_CHANNEL_LAST_USED_IS_KEPT_TO_THE_HOUR`, against a server.** A person bound on Lark and
    on Slack writes on Lark and then on Slack: Slack is the one last used. Writing on Lark again
    inside the hour writes nothing, so Slack stays; an hour later it writes, and Lark is last used.
    A webhook binding is never an answer. Delete this and a later message goes to a channel the
    person stopped reading, or a person writing every minute writes the row every minute."""
    sql(
        migrated,
        "INSERT INTO auth.principal (id, kind, employment, display_name) "
        "VALUES (%s, 'human', 'staff', %s) ON CONFLICT (id) DO NOTHING",
        CAROL,
        CAROL,
    )
    lark, slack, hook = (
        "ou_carol_" + uuid.uuid4().hex,
        "U" + uuid.uuid4().hex[:10].upper(),
        "hook-carol-" + uuid.uuid4().hex,
    )

    def aged(channel: Channel) -> None:
        sql(
            migrated,
            "UPDATE auth.principal_identity SET updated_at = now() - %s "
            "WHERE principal_id = %s AND channel = %s AND deleted_at IS NULL",
            LAST_USE_IS_KEPT_TO * 2,
            CAROL,
            channel.value,
        )

    async def through() -> tuple[object, ...]:
        db = app_engine(migrated)
        sessions = async_sessionmaker(db, expire_on_commit=False)
        bindings, book = StoredBindings(sessions), StoredAddresses(sessions)
        for channel, who in ((Channel.LARK, lark), (Channel.SLACK, slack), (Channel.WEBHOOK, hook)):
            fresh = Binding(
                channel=channel,
                identity_hash=identity_hash(channel, who),
                principal_id=CAROL,
                bound_at=datetime(2999, 1, 1, tzinfo=UTC),
            )
            await bindings.bind(fresh, decide=partial(settle, fresh), trace_id="t1")
        await book.remember(Channel.LARK, lark)
        aged(Channel.LARK)
        await book.remember(Channel.SLACK, slack)
        after_slack = await book.last_used(CAROL)
        inside_the_hour = await book.remember(Channel.SLACK, slack)
        await book.remember(Channel.WEBHOOK, hook)
        aged(Channel.SLACK)
        lark_again = await book.remember(Channel.LARK, lark)
        after_lark = await book.last_used(CAROL)
        await db.dispose()
        return after_slack, inside_the_hour, lark_again, after_lark

    after_slack, inside_the_hour, lark_again, after_lark = run(through)

    assert after_slack == (Channel.SLACK, slack)
    assert inside_the_hour is False
    assert lark_again is True
    assert after_lark == (Channel.LARK, lark)
