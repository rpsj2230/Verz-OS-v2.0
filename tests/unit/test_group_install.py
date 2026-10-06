"""An agent installed into a group chat the bot is in: the tables, Lark's room events, the route and
the chat path that answers with it (M39.2.4.4).

The pure half holds `0205` to its models and to the ledger's grammar, reads Lark's own joining and
leaving events, and holds the chat path's choice of agent. The server half drives the application's
own routes over PostgreSQL at head as the application role, with the agents held in memory as the
lifecycle routes' tests hold them, so `0205`'s policies and its ledger trigger are the ones an
install has.

Task ids: M39.2.4.4
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.agent_group_routes import (
    A_ROOM_ANSWERS_AT_ITS_FLOOR_WHICHEVER_AGENT_IS_INSTALLED,
    GROUPS_PATH,
    NOT_INSTALLED,
    REMOVAL_PATH,
)
from brain.agents.model import answering_on
from brain.audit import ledger
from brain.audit.record import _REASON_CODE_RE, AuditRecorder
from brain.channels.adapter import Conversation, Feature, RoomChange
from brain.channels.inbound import Inbound
from brain.channels.lark import BOT_ADDED, BOT_REMOVED, LARK_FEATURES, ROOM_PREFIX, read_room
from brain.chat_answer import (
    A_GROUP_CHAT_IS_ANSWERED_BY_ITS_INSTALLED_AGENT_WHEN_NONE_IS_NAMED,
    AN_INSTALL_IS_PAUSED_WHILE_ITS_AGENT_DOES_NOT_ANSWER_ON_THE_CHANNEL,
    installed_agent_addressed,
)
from brain.console.agent_tabs import GroupInstall
from brain.db import metadata
from brain.gate.addressing import Address
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent
from brain.ops.group_install_store import StoredGroupInstalls
from brain.session import make_session_factory
from brain.tables import group_install
from brain.tables.identity import one_of
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_agent_lifecycle_routes import COMPANY, SALES, Console, Memory, console
from tests.unit.test_approval_cards import client, world
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

__all__ = ("client", "console", "world")

MIGRATION = VERSIONS / "0205_group_install.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
ROOM = "oc_7f3a9c"
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def module() -> Any:
    return migration_module(MIGRATION)


# ------------------------------------------------------------------------ the migration
def test_the_migration_builds_both_tables_exactly_as_the_models_declare_them() -> None:
    """Compared on rendered DDL. Delete this and the model can declare the one-agent-per-room
    index or the removal check while the database never has it."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for name in ("ops.channel_room", "agent.group_install"):
        table = metadata.tables[name]
        assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted, name
        for index in table.indexes:
            assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_copies_are_the_models_and_the_ledgers() -> None:
    """Each copy against what it copies, from outside it. Delete this and a room reference the
    ledger refuses can be installed, so the install's entry fails on the first press, or a channel
    the product adds is refused by the table."""
    m = module()
    assert m.ROOM_REF_PATTERN == group_install.ROOM_REF_PATTERN == ledger.IDENTIFIER
    assert one_of("channel", Channel) == m.CHANNELS
    assert (m.AGENT_ID_CHARS, m.CHANNEL_CHARS, m.ROOM_REF_CHARS, m.ROOM_NAME_CHARS) == (
        group_install.AGENT_ID_CHARS,
        group_install.CHANNEL_CHARS,
        group_install.ROOM_REF_CHARS,
        group_install.ROOM_NAME_CHARS,
    )
    assert _REASON_CODE_RE.fullmatch(m.REASON)


def test_the_trigger_writes_the_keys_compose_change_writes() -> None:
    """The install's entry against `AuditRecorder.compose_change`'s own. Delete this and the trigger
    can write a detail the recorder never does, and the audit screen renders it as a code."""
    entry = AuditRecorder(
        ledger.AuditChain(),
        actor_id="u_actor",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: LONG_AGO,
    ).compose_change(
        agent_id="a1",
        part=module().PART,
        reference=ROOM,
        attached=True,
        reason_code=module().REASON,
    )
    for key in entry.details:
        assert f"'{key}'" in module().INSTALL_TRIGGER_FUNCTION
    assert "'compose_change'" in module().INSTALL_TRIGGER_FUNCTION


def test_an_install_is_appended_and_removed_and_never_rewritten_or_deleted() -> None:
    """Read off the emitted statements. Delete this and an install can be rewritten into another
    room, or deleted with its history."""
    up = squash(rendered("upgrade", MIGRATION))
    assert "GRANT SELECT, INSERT ON agent.group_install TO brain_app" in up
    assert "GRANT UPDATE (removed_by, removed_at) ON agent.group_install TO brain_app" in up
    assert "DELETE" not in " ".join(module().GRANTS)
    for table in ("ops.channel_room", "agent.group_install"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in up


# ------------------------------------------------------------------------ Lark's room events
def room_event(kind: str, **body: Any) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {"event_id": "ev_room_1", "event_type": kind, "create_time": "1551690000000"},
        "event": {
            "chat_id": ROOM,
            "name": "Pricing desk",
            "operator_id": {"open_id": "ou_1"},
            **body,
        },
    }


def test_lark_reads_the_bot_joining_and_leaving_a_group_chat_as_a_room_change() -> None:
    """Lark's `im.chat.member.bot.added_v1` and `deleted_v1`, read: the chat, its name and the way
    it went, claimed under its own prefix and carrying no text. Delete this and the console has no
    room to offer, or a room change is answered as a message."""
    joined = read_room(room_event(BOT_ADDED), joined=True)
    left = read_room(room_event(BOT_REMOVED), joined=False)

    assert joined.room == RoomChange(conversation_id=ROOM, name="Pricing desk", joined=True)
    assert left.room is not None and left.room.joined is False
    assert joined.event.external_id == f"{ROOM_PREFIX}ev_room_1"
    assert joined.event.text == "" and joined.conversation is None and joined.press is None
    with pytest.raises(ValueError, match="chat"):
        read_room(room_event(BOT_ADDED, chat_id=""), joined=True)


def test_lark_declares_group_installation_and_nothing_else_new() -> None:
    """The feature `install_to_group` asks for, declared where Lark's other features are. Delete
    this and the console offers group installation nowhere, which is where it stood before."""
    assert Feature.GROUP_INSTALL in LARK_FEATURES
    assert Feature.STREAMING not in LARK_FEATURES


# ------------------------------------------------------------------------ the chat path
class Installs(StoredGroupInstalls):
    """The store with its one read answered from a mapping, and no pool behind it."""

    installed: dict[tuple[Channel, str], str]

    def __init__(self, installed: dict[tuple[Channel, str], str]) -> None:
        object.__setattr__(self, "installed", installed)

    async def installed_in(self, channel: Channel, room_ref: str) -> str | None:
        found: str | None = self.installed.get((channel, room_ref))
        return found


class State:
    def __init__(self, installs: StoredGroupInstalls, agents: Memory) -> None:
        self.group_installs = installs
        self.agent_lifecycles = agents


class App:
    def __init__(self, installs: StoredGroupInstalls, agents: Memory) -> None:
        self.state = State(installs, agents)


class Request:
    def __init__(self, installs: StoredGroupInstalls, agents: Memory | None = None) -> None:
        self.app = App(installs, agents if agents is not None else on_lark(Memory(), COMPANY))


def on_lark(agents: Memory, agent_id: str, *, answering: bool = True) -> Memory:
    """The in-memory agents with this one answering on Lark, or on nothing."""
    found = agents.agents[agent_id]
    agents.agents[agent_id] = replace(
        found, record=answering_on(found.record, ["lark"] if answering else [])
    )
    return agents


def a_message(agent_id: str | None) -> Inbound:
    return Inbound(
        event=ChannelEvent(
            channel=Channel.LARK,
            external_id="m1",
            channel_identity="ou_1",
            text="how much is it",
            received_at=LONG_AGO,
        ),
        address=Address(question="how much is it", agent_id=agent_id),
    )


def a_room(shared: bool) -> Conversation:
    return Conversation(
        room_to=f"chat:{ROOM}", sender_to="user:ou_1", conversation_id=ROOM, shared=shared
    )


def test_a_group_chats_message_naming_no_agent_is_answered_by_its_installed_agent() -> None:
    """`A_GROUP_CHAT_IS_ANSWERED_BY_ITS_INSTALLED_AGENT_WHEN_NONE_IS_NAMED`, in all four cases: a
    shared chat with an install and no agent named is the installed agent's; a message naming an
    agent keeps it; a private chat and a chat with no install are as before. Delete this and a
    group install chooses nothing, or overrides the agent somebody named."""
    request: Any = Request(Installs({(Channel.LARK, ROOM): COMPANY}))
    empty: Any = Request(Installs({}))

    async def go() -> tuple[Inbound, ...]:
        return (
            await installed_agent_addressed(request, a_message(None), a_room(shared=True)),
            await installed_agent_addressed(
                request, a_message("sales_helper"), a_room(shared=True)
            ),
            await installed_agent_addressed(request, a_message(None), a_room(shared=False)),
            await installed_agent_addressed(empty, a_message(None), a_room(shared=True)),
        )

    installed, named, private, none = run(go)
    assert installed.address.agent_id == COMPANY
    assert installed.address.question == "how much is it"
    assert named.address.agent_id == "sales_helper"
    assert (private.address.agent_id, none.address.agent_id) == (None, None)
    assert "floor" in A_GROUP_CHAT_IS_ANSWERED_BY_ITS_INSTALLED_AGENT_WHEN_NONE_IS_NAMED
    assert "floor" in A_ROOM_ANSWERS_AT_ITS_FLOOR_WHICHEVER_AGENT_IS_INSTALLED
    assert set(GroupInstall.__dataclass_fields__) == {"agent_id", "channel", "room_ref"}


def test_an_install_whose_agent_was_switched_off_the_channel_is_paused_and_resumes_when_on() -> (
    None
):
    """`AN_INSTALL_IS_PAUSED_WHILE_ITS_AGENT_DOES_NOT_ANSWER_ON_THE_CHANNEL`: with the agent's Lark
    channel switched off, a message in its chat goes exactly where it would with no install, and
    switching the channel back on resumes the same install with nobody installing it again. Delete
    this and switching a channel off leaves the agent answering in every chat it was installed in,
    or an install has to be made again after every switch."""
    installs = Installs({(Channel.LARK, ROOM): COMPANY})
    agents = on_lark(Memory(), COMPANY, answering=False)
    switched_off: Any = Request(installs, agents)
    no_install: Any = Request(Installs({}), agents)

    async def ask(request: Any) -> Inbound:
        return await installed_agent_addressed(request, a_message(None), a_room(shared=True))

    paused = run(lambda: ask(switched_off))
    without = run(lambda: ask(no_install))
    on_lark(agents, COMPANY, answering=True)
    resumed = run(lambda: ask(switched_off))

    assert paused == without
    assert paused.address.agent_id is None
    assert resumed.address.agent_id == COMPANY
    assert installs.installed == {(Channel.LARK, ROOM): COMPANY}
    assert "back on" in AN_INSTALL_IS_PAUSED_WHILE_ITS_AGENT_DOES_NOT_ANSWER_ON_THE_CHANNEL


# ------------------------------------------------------------------------ on a server
@pytest.fixture
def database() -> Iterator[str]:
    with at_head(f"brain_group_install_{uuid.uuid4().hex[:6]}") as url:
        yield url


def wired(console: Console, url: str) -> Any:
    """The console fixture's application, reading rooms and installs from this database."""
    engine = app_engine(url)
    console.app.state.group_installs = StoredGroupInstalls(make_session_factory(engine))
    return engine


def answering_on_lark(console: Console, agent_id: str) -> None:
    found = console.memory.agents[agent_id]
    console.memory.agents[agent_id] = replace(found, record=answering_on(found.record, ["lark"]))


def test_a_steward_installs_their_agent_in_a_chat_the_bot_is_in_and_takes_it_out(
    console: Console, database: str
) -> None:
    """**M39.2.4.4 on PostgreSQL.** The bot is added to a Lark chat, which the route offers to the
    steward of an agent that answers on Lark; installing writes the row in the steward's name and a
    `compose_change` entry by them, the room is no longer offered, and taking it out writes the
    removal and its entry. Anybody else is the one 404, for reading as for writing. Delete this and
    no agent can be installed into a group chat, or anybody can install one."""
    engine = wired(console, database)
    answering_on_lark(console, SALES)
    store = console.app.state.group_installs

    async def joined() -> None:
        await store.note(Channel.LARK, RoomChange(ROOM, "Pricing desk", joined=True), LONG_AGO)

    run(joined)
    listed = console.get("u_wide", GROUPS_PATH.format(agent_id=SALES))
    stranger = console.get("u_none", GROUPS_PATH.format(agent_id=SALES))
    # `u_wide` sees the company's agent and may not switch its channels: the missing agent's 404.
    onlooker = console.get("u_wide", GROUPS_PATH.format(agent_id=COMPANY))
    missing = console.get("u_wide", GROUPS_PATH.format(agent_id="no_such_agent"))
    made = console.post(
        "u_wide", GROUPS_PATH.format(agent_id=SALES), {"channel": "lark", "room_ref": ROOM}
    )
    again = console.post(
        "u_admin", GROUPS_PATH.format(agent_id=COMPANY), {"channel": "lark", "room_ref": ROOM}
    )
    [install] = made.json()["installs"]
    # Switched off Lark, the install is shown paused; switched back on, it answers again, and it is
    # the same install throughout.
    found = console.memory.agents[SALES]
    console.memory.agents[SALES] = replace(found, record=answering_on(found.record, []))
    paused = console.get("u_wide", GROUPS_PATH.format(agent_id=SALES)).json()["installs"]
    answering_on_lark(console, SALES)
    resumed = console.get("u_wide", GROUPS_PATH.format(agent_id=SALES)).json()["installs"]
    removed = console.post(
        "u_wide", REMOVAL_PATH.format(agent_id=SALES), {"install_id": install["id"]}
    )
    run(engine.dispose)

    assert listed.status_code == 200, listed.text
    assert listed.json()["rooms"] == [{"channel": "lark", "room_ref": ROOM, "name": "Pricing desk"}]
    assert stranger.status_code == 404
    assert (onlooker.status_code, onlooker.json()["message"]) == (404, missing.json()["message"])
    assert made.status_code == 201, made.text
    assert (install["room_ref"], install["name"], install["present"]) == (
        ROOM,
        "Pricing desk",
        True,
    )
    assert made.json()["rooms"] == []
    assert install["answering"] is True
    assert [(one["id"], one["answering"]) for one in paused] == [(install["id"], False)]
    assert [(one["id"], one["answering"]) for one in resumed] == [(install["id"], True)]
    # One agent per room: another agent is refused in the one sentence, and nothing is written.
    assert (again.status_code, again.json()["sentence"]) == (409, NOT_INSTALLED)
    assert removed.status_code == 200, removed.text
    assert removed.json()["installs"] == []
    assert sql(
        database,
        "SELECT agent_id, installed_by, removed_by FROM agent.group_install",
    ) == [(SALES, "u_wide", "u_wide")]
    changes = [
        (
            one.actor_id,
            one.subject,
            one.details["part"],
            one.details["reference"],
            one.details["direction"],
        )
        for one in entries(database, "compose_change")
    ]
    assert changes == [
        ("u_wide", f"agent:{SALES}", "group", ROOM, "attached"),
        ("u_wide", f"agent:{SALES}", "group", ROOM, "detached"),
    ]


def test_a_chat_the_bot_left_or_was_never_in_takes_no_agent(
    console: Console, database: str
) -> None:
    """The refusals' positive sibling is above; here a chat the bot was removed from and a chat it
    was never in are each refused in the one sentence, and nothing is written. Delete this and an
    agent can be installed where no message will ever reach it."""
    engine = wired(console, database)
    answering_on_lark(console, SALES)
    store = console.app.state.group_installs

    async def left() -> None:
        await store.note(Channel.LARK, RoomChange(ROOM, "Pricing desk", joined=True), LONG_AGO)
        await store.note(Channel.LARK, RoomChange(ROOM, "Pricing desk", joined=False), LONG_AGO)

    run(left)
    listed = console.get("u_wide", GROUPS_PATH.format(agent_id=SALES))
    gone = console.post(
        "u_wide", GROUPS_PATH.format(agent_id=SALES), {"channel": "lark", "room_ref": ROOM}
    )
    never = console.post(
        "u_wide", GROUPS_PATH.format(agent_id=SALES), {"channel": "lark", "room_ref": "oc_never"}
    )
    run(engine.dispose)

    assert listed.json()["rooms"] == []
    assert (gone.status_code, gone.json()["sentence"]) == (409, NOT_INSTALLED)
    assert (never.status_code, never.json()["sentence"]) == (409, NOT_INSTALLED)
    assert sql(database, "SELECT count(*) FROM agent.group_install") == [(0,)]


def test_an_agent_that_does_not_answer_on_the_channel_cannot_be_installed_there(
    console: Console, database: str
) -> None:
    """`install_to_group`'s second refusal, through the route: the agent answers nowhere, so a
    Lark chat cannot take it. Delete this and a group install binds an agent that answers
    nothing."""
    engine = wired(console, database)
    store = console.app.state.group_installs

    async def joined() -> None:
        await store.note(Channel.LARK, RoomChange(ROOM, "Pricing desk", joined=True), LONG_AGO)

    run(joined)
    refused = console.post(
        "u_wide", GROUPS_PATH.format(agent_id=SALES), {"channel": "lark", "room_ref": ROOM}
    )
    listed = console.get("u_wide", GROUPS_PATH.format(agent_id=SALES))
    run(engine.dispose)

    assert (refused.status_code, refused.json()["sentence"]) == (409, NOT_INSTALLED)
    assert listed.json()["rooms"] == []


# ------------------------------------------------------------------------ through the events route
class Noted(StoredGroupInstalls):
    """The store with its one write recorded in a list, and no pool behind it."""

    changes: list[tuple[Channel, RoomChange]]

    def __init__(self) -> None:
        object.__setattr__(self, "changes", [])

    async def note(self, channel: Channel, change: RoomChange, at: datetime) -> None:
        self.changes.append((channel, change))


def test_a_signed_lark_room_event_is_noted_through_the_events_route_and_answered_with_nothing(
    client: Any, world: Any
) -> None:
    """The route's branch for a room change: Lark's signed `bot.added` event reaches the store as
    the room it names, the vendor is answered at once, and nothing is sent to the chat. Delete this
    and a room change can fall through to the answering path, which would answer a chat that asked
    nothing, or never be noted."""
    from tests.fixtures.lark_events import APP_ID, VERIFICATION_TOKEN
    from tests.unit.test_approval_cards import post

    noted = Noted()
    client.app.state.group_installs = noted
    added = room_event(BOT_ADDED)
    added["header"] |= {"token": VERIFICATION_TOKEN, "app_id": APP_ID, "tenant_key": "t1"}
    removed = room_event(BOT_REMOVED)
    removed["header"] |= {
        "token": VERIFICATION_TOKEN,
        "app_id": APP_ID,
        "tenant_key": "t1",
        "event_id": "ev_room_2",
    }

    answer = post(client, added)
    gone = post(client, removed)

    assert (answer.status_code, gone.status_code) == (200, 200), answer.text
    assert noted.changes == [
        (Channel.LARK, RoomChange(conversation_id=ROOM, name="Pricing desk", joined=True)),
        (Channel.LARK, RoomChange(conversation_id=ROOM, name="Pricing desk", joined=False)),
    ]
    assert world.lark.sent == []
