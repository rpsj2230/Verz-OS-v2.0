"""An approval card sent when the approval is raised, to the Lark address a binding keeps.

The owner decided needs-rupash 118 on 2026-09-29: keep each linked person's Lark address so the
card reaches the approver the moment the approval is raised. The route half drives
`brain.approval_cards.send_raised` on the real application with an address store in memory and a
Lark that records every request. The store half runs `brain.ops.binding_store.StoredAddresses`
against PostgreSQL at head, and the erasure half runs `brain.ops.erasure_store.PostgresEraser`
over the tables the models declare. The migration half holds `0166` to the model.

Task ids: M10.2.7, M10.3.5
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import inspect
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.requests import Request

from brain.app import Settings, create_app
from brain.approval_cards import send_raised
from brain.channels.binding import settle
from brain.channels.cards import DECIDE_IN_THE_CONSOLE
from brain.channels.inbound import Inbound, Receipt, ReceiptKind, Redeemed, reply_for
from brain.channels.lark import LarkSecret
from brain.gate.addressing import from_mention
from brain.gate.context import Channel
from brain.gate.ingress import Binding, ChannelEvent, identity_hash
from brain.ops.binding_store import ADDRESS_KEPT_ON, StoredAddresses, StoredBindings
from brain.ops.channel_store import channel_secret_ref
from brain.ops.erasure_store import CLEARED, PostgresEraser
from brain.ops.retention import Store
from brain.tables.identity import CHANNEL_ADDRESS_CHARS
from brain.tools.startup import build_registry
from tests.fixtures.lark_events import (
    APP_ID,
    APP_SECRET,
    BOT_OPEN_ID,
    ENCRYPT_KEY,
    VERIFICATION_TOKEN,
)
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_answer_route import HOURS, OneRow
from tests.unit.test_api_routes import GRANTS, SOURCE, wiring
from tests.unit.test_approval_cards import (
    APPROVE,
    DM,
    ORIGIN,
    World,
    a_promotion,
    dm,
    post,
)
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_channel_pipeline import Secrets, fresh_record
from tests.unit.test_chat_answer import OPEN_IDS, Bound, People
from tests.unit.test_erasure_store import a_person, estate

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "0166_binding_lark_address.py"
WIDE, NARROW, ELSEWHERE = OPEN_IDS["u_wide"], OPEN_IDS["u_narrow"], OPEN_IDS["u_elsewhere"]


# ------------------------------------------------------------------------ in memory


@dataclass
class Addresses:
    """The address store in memory: what is kept by person, and every offer it was made."""

    kept: dict[str, str] = field(default_factory=dict)
    offered: list[tuple[Channel, str]] = field(default_factory=list)

    async def remember(self, channel: Channel, identity: str) -> bool:
        self.offered.append((channel, identity))
        return False

    async def addressed(self, channel: Channel) -> tuple[tuple[str, str], ...]:
        del channel
        return tuple(sorted(self.kept.items()))


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    """A Lark record and a promotion asked by `u_prefix`; `u_wide` and `u_elsewhere` may approve
    it and `u_narrow` may not."""
    made = World()
    made.records.kept[Channel.LARK] = fresh_record(
        Channel.LARK,
        tenant={"app_id": APP_ID, "platform": "larksuite.com", "bot_id": BOT_OPEN_ID},
    )
    monkeypatch.setitem(GRANTS, "u_wide", (*GRANTS["u_wide"], APPROVE))
    monkeypatch.setitem(GRANTS, "u_elsewhere", (*GRANTS["u_elsewhere"], APPROVE))
    promotion = a_promotion("u_prefix")
    made.store.rows[promotion.id] = promotion
    return made


@pytest.fixture
def addresses() -> Addresses:
    return Addresses()


@pytest.fixture
def client(
    world: World, addresses: Addresses, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("INSTALL_OIDC_REDIRECT_URIS", f"{ORIGIN}/callback")
    made: FastAPI = create_app(Settings(env="development"))
    kept = LarkSecret(
        app_secret=APP_SECRET, encrypt_key=ENCRYPT_KEY, verification_token=VERIFICATION_TOKEN
    ).kept()
    with TestClient(made, raise_server_exceptions=False) as c:
        state = made.state
        state.gate = wiring()
        state.tools = build_registry(source=SOURCE, records=OneRow())
        state.fast_path_rules = (HOURS,)
        state.channel_records = world.records
        state.channel_deliveries = world.deliveries
        state.channel_claims = world.claims
        state.channel_secrets = Secrets({channel_secret_ref(Channel.LARK).path: kept})
        state.channel_transport = world.lark
        state.operation_ledger = world.ledger
        state.channel_bindings = Bound()
        state.chat_people = People()
        state.suspensions = world.store
        state.card_windows = world.windows
        state.approve_from_cards = True
        state.channel_addresses = addresses
        yield c


@pytest.fixture
def app(client: TestClient) -> FastAPI:
    made = client.app
    assert isinstance(made, FastAPI)
    return made


def raised(app: FastAPI, world: World) -> int:
    """What `send_raised` delivered for the one promotion, as the promotion route runs it."""
    [promotion] = world.store.rows.values()
    request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
    return asyncio.run(send_raised(request, promotion))


# ======================================================================== sending on a raise


def test_a_raised_approval_sends_one_card_to_each_approver_s_kept_address_and_nobody_else(
    app: FastAPI, world: World, addresses: Addresses
) -> None:
    """M10.2.7. Of three addresses kept, one belongs to somebody the Approvals screen would offer
    the promotion to, one to somebody it would not, and the approver with no address kept is
    reached by nothing. One card goes out, to the approver's own chat with the bot, naming the
    approval, whom it was built for, and the reasons a rejection may give; the address is in the
    body and never in the URL. Delete this and a card goes to nobody on a raise, or to everybody
    with an address, or with the address in a URL a proxy logs."""
    addresses.kept = {"u_wide": WIDE, "u_narrow": NARROW}
    assert raised(app, world) == 1
    [(kind, where, text, card)] = world.lark.posted()
    assert (kind, where) == ("open_id", WIDE)
    assert card is not None and "Site handover" in text
    approve, reject = card["elements"][1]["actions"]
    [promotion] = world.store.rows.values()
    assert (approve["value"]["suspension_id"], approve["value"]["rendered_for"]) == (
        promotion.id,
        "u_wide",
    )
    assert reject["value"]["decision"] == "rejected"
    assert all(WIDE not in one.url and NARROW not in one.url for one in world.lark.sent)


def test_nothing_is_sent_to_an_approver_whose_binding_keeps_no_address(
    app: FastAPI, world: World, addresses: Addresses
) -> None:
    """A binding made before `0166` keeps no address until its person next writes, so a raise
    sends it nothing; the approval still waits on the Approvals screen. Delete this and a raise
    invents somewhere to send a card, or fails for everybody because one person has no address."""
    addresses.kept = {"u_narrow": NARROW}
    assert raised(app, world) == 0
    assert world.lark.sent == []


def test_with_approving_from_lark_off_the_raised_card_has_no_button_and_names_the_console(
    app: FastAPI, world: World, addresses: Addresses
) -> None:
    """Needs-rupash 117 still decides what a press may do: switched off, the card sent on a raise
    has nothing to press and names the console's Approvals page. Delete this and a raise sends a
    card with buttons on an install that switched them off."""
    app.state.approve_from_cards = False
    addresses.kept = {"u_wide": WIDE}
    assert raised(app, world) == 1
    [(_, where, text, card)] = world.lark.posted()
    assert where == WIDE and card is not None
    assert [one["tag"] for one in card["elements"]] == ["div"]
    assert text.endswith(DECIDE_IN_THE_CONSOLE.format(where=f"{ORIGIN}/approvals"))


def test_a_raise_on_an_install_whose_lark_channel_is_off_sends_nothing(
    app: FastAPI, world: World, addresses: Addresses
) -> None:
    """Delete this and switching Lark's chat off leaves approval cards still going out."""
    world.records.kept[Channel.LARK] = fresh_record(
        Channel.LARK,
        enabled=False,
        tenant={"app_id": APP_ID, "platform": "larksuite.com", "bot_id": BOT_OPEN_ID},
    )
    addresses.kept = {"u_wide": WIDE}
    assert raised(app, world) == 0
    assert world.lark.sent == []


def test_the_promotion_route_schedules_the_cards_once_the_approval_is_kept() -> None:
    """The one production route that raises an approval hands it to `send_raised` after the
    transaction that keeps it, as a background task so the person asking is answered first.
    Asserted on the call itself. Delete this and the route raises approvals nobody is sent."""
    from brain import knowledge_lifecycle_routes

    tree = ast.parse(inspect.getsource(knowledge_lifecycle_routes.propose))
    calls = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_task"
    ]
    assert calls == ["background.add_task(send_raised, request, suspension)"]
    source = inspect.getsource(knowledge_lifecycle_routes.propose)
    assert source.index("await in_transaction(request, asked, authority, write") < source.index(
        "background.add_task(send_raised"
    )


# ======================================================================== keeping it


def test_a_bound_sender_s_address_is_offered_on_every_message_and_an_unbound_one_s_never(
    client: TestClient, addresses: Addresses
) -> None:
    """M10.3.5 at the route: a bound person writing, here a decision word, offers their own
    identity to be kept; a sender bound to nobody offers nothing. That is how a binding made
    before `0166` gains its address. Delete this and no binding ever gains one."""
    post(client, dm(WIDE, "approvals"))
    post(client, dm("ou_stranger00000000000000000001", "approvals"))
    assert addresses.offered == [(Channel.LARK, WIDE)]


def test_the_code_that_binds_a_sender_offers_their_address_at_once() -> None:
    """The first message a person sends a bot is usually the code that binds them, so it is kept
    then rather than a message later. Delete this and a person who binds and never writes again
    is never sent a card."""
    event = ChannelEvent(
        channel=Channel.LARK,
        external_id="om_code",
        channel_identity=WIDE,
        text="LINK-CODE-GOOD",
        received_at=datetime(2999, 1, 1, tzinfo=UTC),
    )
    receipt = Receipt(
        kind=ReceiptKind.ACCEPTED,
        inbound=Inbound(event=event, address=from_mention(event.text)),
        reply_to=f"chat:{DM}",
    )

    class Nobody:
        async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
            del channel, digest
            return None

    class Binds:
        async def redeem(self, event: ChannelEvent, text: str, *, now: datetime) -> Redeemed:
            del event, text, now
            return Redeemed.BOUND

    book = Addresses()
    asyncio.run(
        reply_for(
            receipt,
            record=fresh_record(Channel.LARK, tenant={"bot_id": BOT_OPEN_ID}),
            bindings=Nobody(),
            answerer=None,
            binder=Binds(),
            addresses=book,
            now=datetime(2999, 1, 1, tzinfo=UTC),
        )
    )
    assert book.offered == [(Channel.LARK, WIDE)]


def test_only_lark_keeps_an_address_and_an_erasure_clears_it() -> None:
    """The declarations the column rests on. Delete this and an address is kept for a channel
    nobody decided about, or survives an erasure on a row the trail keeps."""
    assert frozenset({Channel.LARK}) == ADDRESS_KEPT_ON
    assert CLEARED == {"auth.principal_identity": ("channel_address",)}


# ======================================================================== the migration


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0166", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_adds_the_column_the_model_declares_and_the_downgrade_drops_it() -> None:
    """`AMENDS_CREATE_TABLE` is a claim `tests/unit/test_tables.py` trusts; this holds it to the
    ALTER the upgrade emits, and the width to the model's. Delete this and the model can say the
    column exists while the upgrade adds another, or none."""
    from tests.unit.test_tables import rendered, squash

    migration = _migration()
    # Which revision it follows moves with the train it lands in, so it is not pinned here: every
    # test that builds the schema at head refuses a chain with two heads or a missing predecessor.
    assert migration.revision == "0166"
    assert migration.CHANNEL_ADDRESS_CHARS == CHANNEL_ADDRESS_CHARS
    up = squash(rendered("upgrade", MIGRATION))
    down = squash(rendered("downgrade", MIGRATION))
    assert (
        f"ALTER TABLE auth.principal_identity ADD COLUMN channel_address "
        f"VARCHAR({CHANNEL_ADDRESS_CHARS})" in up
    )
    assert "ALTER TABLE auth.principal_identity DROP COLUMN channel_address" in down
    [(old, new)] = migration.AMENDS_CREATE_TABLE.items()
    assert new.replace(f"channel_address VARCHAR({CHANNEL_ADDRESS_CHARS}), ", "") == old


# ======================================================================== on a server


@pytest.fixture(scope="module")
def migrated() -> Iterator[str]:
    """Every migration that ships, through `0166`."""
    with retirable("brain_test_card_on_raise") as url:
        if not has_pgvector(url):
            pytest.skip("the migrations to head need pgvector, which CI's server has")
        yield url


ALICE, BOB = "u_card_alice", "u_card_bob"


def _people(url: str) -> None:
    for pid in (ALICE, BOB):
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name) "
            "VALUES (%s, 'human', 'staff', %s) ON CONFLICT (id) DO NOTHING",
            pid,
            pid,
        )


def _kept(url: str) -> list[tuple[str, str, str | None, bool]]:
    return [
        (row[0], row[1], row[2], row[3])
        for row in sql(
            url,
            "SELECT principal_id, channel, channel_address, deleted_at IS NULL "
            "FROM auth.principal_identity WHERE principal_id IN (%s, %s) "
            "ORDER BY principal_id, channel, deleted_at NULLS FIRST",
            ALICE,
            BOB,
        )
    ]


@pytest.mark.needs_db
def test_an_address_is_kept_only_on_its_own_binding_only_for_lark_and_cleared_on_unbind(
    migrated: str,
) -> None:
    """**M10.3.5 against a server.** An address is kept on the one live Lark binding it is the
    fingerprint of, once however often it is offered; one bound to nobody, or on the webhook
    channel, is kept nowhere; `addressed` lists exactly the bindings holding one; nothing is
    written to the ledger for keeping it; and unbinding clears it with the row it sat on.

    Delete this and an address can be written onto somebody else's binding, kept for a channel
    nobody decided about, or outlive the binding it belonged to."""
    _people(migrated)
    alice = "ou_alice_" + uuid.uuid4().hex
    bob_hook = "hook-bob-" + uuid.uuid4().hex

    async def through() -> tuple[Any, ...]:
        db = app_engine(migrated)
        sessions = async_sessionmaker(db, expire_on_commit=False)
        bindings, book = StoredBindings(sessions), StoredAddresses(sessions)
        for pid, channel, who in ((ALICE, Channel.LARK, alice), (BOB, Channel.WEBHOOK, bob_hook)):
            fresh = Binding(
                channel=channel,
                identity_hash=identity_hash(channel, who),
                principal_id=pid,
                bound_at=datetime(2999, 1, 1, tzinfo=UTC),
            )
            await bindings.bind(fresh, decide=partial(settle, fresh), trace_id="t1")
        before = sql(migrated, "SELECT count(*) FROM obs.audit_entry")[0][0]
        first = await book.remember(Channel.LARK, alice)
        again = await book.remember(Channel.LARK, alice)
        stranger = await book.remember(Channel.LARK, "ou_nobody_" + uuid.uuid4().hex)
        webhook = await book.remember(Channel.WEBHOOK, bob_hook)
        listed = await book.addressed(Channel.LARK)
        on_webhook = await book.addressed(Channel.WEBHOOK)
        after = sql(migrated, "SELECT count(*) FROM obs.audit_entry")[0][0]
        kept = _kept(migrated)
        await bindings.unbind(ALICE, Channel.LARK, actor=ALICE, ent_hash="1f" * 16, trace_id="t2")
        listed_after = await book.addressed(Channel.LARK)
        await db.dispose()
        return (
            first,
            again,
            stranger,
            webhook,
            listed,
            on_webhook,
            after - before,
            kept,
            listed_after,
        )

    first, again, stranger, webhook, listed, on_webhook, written, kept, listed_after = run(through)
    assert (first, again, stranger, webhook) == (True, False, False, False)
    assert (ALICE, alice) in listed and on_webhook == ()
    assert written == 0
    assert (ALICE, "lark", alice, True) in kept and (BOB, "webhook", None, True) in kept
    assert all(address != alice for _, address in listed_after)
    assert [row for row in _kept(migrated) if row[0] == ALICE] == [(ALICE, "lark", None, False)]


@pytest.mark.needs_db
def test_an_erasure_clears_the_address_on_every_row_about_the_person_and_nobody_else_s() -> None:
    """**Erasure removes the address (M10.3.5).** A person's live Lark binding and one retired
    before the erasure both hold an address; the erasure retires the live row as it does every
    binding and clears the address on both, and another person's address is untouched.

    Delete this and an erased person's Lark address is kept in a row the trail keeps, readable by
    whoever reads the table as its owner."""
    with estate("brain_erasure_address") as url:
        a_person(url, "p_ada")
        a_person(url, "p_ben")
        for person, live in (("p_ada", True), ("p_ada", False), ("p_ben", True)):
            sql(
                url,
                "INSERT INTO auth.principal_identity "
                "(channel, identity_hash, principal_id, bound_at, channel_address, deleted_at) "
                "VALUES ('lark', %s, %s, now(), %s, %s)",
                uuid.uuid4().hex + uuid.uuid4().hex,
                person,
                f"ou_{person}_{uuid.uuid4().hex[:8]}",
                None if live else datetime(2019, 1, 1, tzinfo=UTC),
            )
        with psycopg.connect(url) as conn:
            PostgresEraser(conn).erase(Store.ROWS, "p_ada")
            conn.commit()
        remaining = sql(
            url,
            "SELECT principal_id, count(channel_address) FROM auth.principal_identity "
            "GROUP BY principal_id ORDER BY principal_id",
        )
    assert [(row[0], int(row[1])) for row in remaining] == [("p_ada", 0), ("p_ben", 1)]
