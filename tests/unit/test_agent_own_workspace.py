"""A person's own Google account on their personal agent: who attaches it, who is refused, and that
the read that follows is the owner's own and nobody else's.

The route is driven through the real application over the in-memory agent store the lifecycle tests
use, with a connector store of its own; the read is driven through the real passage reader over the
recorded Google `tests/unit/test_google_workspace.py` builds, the agent's ceiling intersected with
its caller by the one `EntitlementSet.intersect`. Every refusal has a sibling that attaches or
reads.
The whole path against PostgreSQL is the install check in
`tests/unit/test_acceptance_agent_own_workspace.py`.

Task ids: M39.10.4, M39.10.5
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.agent_lifecycle_routes import FoundAgent
from brain.agent_own_workspace_routes import OWN_WORKSPACE_PATH
from brain.agent_routes import record_of
from brain.agents.attachments import with_connectors
from brain.agents.binding import provider_of
from brain.agents.model import (
    A_TEAM_AGENT_NEVER_CARRIES_A_PERSONS_OWN_WORKSPACE,
    PERSONS_OWN_CONNECTORS,
    PERSONS_OWN_READS,
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    entitlement_ceiling,
    own_reads,
)
from brain.agents.own_workspace import (
    A_TEAM_AGENT_CARRIES_NO_ONES_OWN_ACCOUNT,
    ALREADY_ATTACHED,
    ATTACHED_REASON,
    CONNECTOR,
    DETACHED_REASON,
    NOT_ATTACHED,
    NOT_OFFERED_TO_YOU,
    NOT_SWITCHED_ON,
    THE_AGENT_MOVED,
)
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connectors import google_workspace as gws
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.ops.connector_store import Connection
from brain.ops.google_workspace_live import READ_WORKSPACE
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_connector_routes import Records
from tests.unit.test_google_workspace import ADA, OPERATIONS, consented, passages_for, settings

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

OWNER = "u_narrow"
COLLEAGUE = "u_wide"
ADMINISTRATOR = "u_admin"
STRANGER = "u_none"
MINE = "my_helper"
THEIRS = "their_helper"
TEAM = "team_helper"
EVERYWHERE = Scope.unrestricted()
PATH = f"{API_PREFIX}{OWN_WORKSPACE_PATH}"

#: Who holds what. The owner and the colleague hold the read of Google Workspace in the department
#: the connection answers to; the administrator holds every authority over agents and connectors and
#: not that read, which is the point: an authority over agents is not a person's own account.
GRANTS: dict[str, tuple[Grant, ...]] = {
    OWNER: (Grant(capability=READ_WORKSPACE, scope=Scope.department(OPERATIONS)),),
    COLLEAGUE: (Grant(capability=READ_WORKSPACE, scope=Scope.department(OPERATIONS)),),
    ADMINISTRATOR: (
        Grant(capability=Capability(value="admin:agent"), scope=EVERYWHERE),
        Grant(capability=Capability(value="admin:connector"), scope=EVERYWHERE),
        Grant(capability=Capability(value="admin:agent_lifecycle"), scope=EVERYWHERE),
    ),
    STRANGER: (),
}


def a_connection() -> Connection:
    return Connection(
        connector=gws.CONNECTOR_NAME,
        settings=settings(),
        digest="0" * 64,
        connected_by=ADMINISTRATOR,
        connected_at=NOW,
    )


def found(agent_id: str, *, level: Visibility, owner: str, connectors: tuple[str, ...] = ()) -> Any:
    row = agent_row(
        agent_id,
        level=level,
        owner_id=owner,
        department="web" if level is Visibility.DEPARTMENT else None,
        connectors=connectors,
    )
    record = record_of(row)
    assert record is not None
    return FoundAgent(record=record, install=None, effective_hash=None)


@dataclass
class Bound:
    agent_id: str
    was: tuple[str, ...]
    becomes: tuple[str, ...]
    by: str
    reason_code: str


@dataclass
class Memory:
    """The lifecycle store and the one write, in memory, noting every write it was asked for."""

    agents: dict[str, FoundAgent] = field(default_factory=dict)
    writes: list[Bound] = field(default_factory=list)
    racing: bool = False

    async def agent(self, agent_id: str) -> FoundAgent | None:
        return self.agents.get(agent_id)

    async def bind(
        self,
        *,
        agent_id: str,
        was: tuple[str, ...],
        becomes: tuple[str, ...],
        by: str,
        reason_code: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        del ent_hash, trace_id
        if self.racing:
            return False
        held = self.agents[agent_id]
        self.agents[agent_id] = replace(held, record=with_connectors(held.record, becomes))
        self.writes.append(Bound(agent_id, was, becomes, by, reason_code))
        return True

    # The rest of `AgentLifecycles`, which these routes never call.
    async def version(self, *_args: object) -> None:
        return None

    async def live_principal(self, *_args: object) -> None:
        return None

    async def change(self, *_args: object, **_kwargs: object) -> bool:
        raise AssertionError("an own-workspace press never changes anything but the connectors")

    async def widen(self, *_args: object, **_kwargs: object) -> bool:
        raise AssertionError("an own-workspace press never widens")

    async def change_channels(self, *_args: object, **_kwargs: object) -> bool:
        raise AssertionError("an own-workspace press never changes channels")

    async def create(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("an own-workspace press never creates an agent")


@dataclass
class Console:
    client: TestClient
    memory: Memory
    records: Records

    def get(self, pid: str, agent_id: str) -> Any:
        return self.client.get(PATH.format(agent_id=agent_id), headers=headers(pid))

    def press(self, pid: str, agent_id: str, *, attached: bool) -> Any:
        return self.client.post(
            PATH.format(agent_id=agent_id), json={"attached": attached}, headers=headers(pid)
        )


@pytest.fixture
def console(monkeypatch: pytest.MonkeyPatch) -> Iterator[Console]:
    """The real application with the switch on, Google Workspace connected, and three agents: the
    owner's personal one, somebody else's, and a department's."""
    memory = Memory(
        agents={
            MINE: found(MINE, level=Visibility.PERSONAL, owner=OWNER),
            THEIRS: found(THEIRS, level=Visibility.PERSONAL, owner=COLLEAGUE),
            TEAM: found(TEAM, level=Visibility.DEPARTMENT, owner=OWNER),
        }
    )
    records = Records((a_connection(),))
    app = create_app(Settings(env="development"))

    async def yes(_sessions: object) -> bool:
        return True

    monkeypatch.setattr("brain.agent_own_workspace_routes.own_workspace_is_on", yes)
    with TestClient(app) as client:
        app.state.gate = gate_wiring(GRANTS)
        app.state.db_sessions = None
        app.state.agent_lifecycles = memory
        app.state.own_workspace = memory
        app.state.connector_records = records
        yield Console(client=client, memory=memory, records=records)


def connectors_of(console: Console, agent_id: str) -> tuple[str, ...]:
    return console.memory.agents[agent_id].record.authority.connectors


# -------------------------------------------------------------------------- the route
def test_the_owner_attaches_their_own_account_to_their_own_agent_and_takes_it_off(
    console: Console,
) -> None:
    """The positive case for every refusal below: the owner, who holds the read and finds Google
    Workspace connected, attaches the account (the agent names it, one write in their name with the
    reason the ledger carries) and then detaches it.

    Delete this and every refusal is satisfied by a route that refuses everybody."""
    before = console.get(OWNER, MINE).json()
    attached = console.press(OWNER, MINE, attached=True)
    after = console.get(OWNER, MINE).json()
    detached = console.press(OWNER, MINE, attached=False)

    assert (before["attached"], before["may_attach"]) == (False, True)
    assert attached.status_code == 200 and attached.json()["attached"] is True
    assert after["attached"] is True and after["may_attach"] is False
    assert detached.status_code == 200 and detached.json()["attached"] is False
    assert [(one.becomes, one.by, one.reason_code) for one in console.memory.writes] == [
        ((CONNECTOR,), OWNER, ATTACHED_REASON),
        ((), OWNER, DETACHED_REASON),
    ]


def test_a_colleague_an_administrator_and_a_stranger_are_answered_as_for_an_agent_never_made(
    console: Console,
) -> None:
    """Nobody but the owner is answered at all: another person's personal agent, from a colleague
    who holds the same read, from an administrator who holds every authority over agents and
    connectors, and from a person holding nothing, is the 404 an agent that does not exist gets, in
    the same words, for the read and for the press, and nothing is written.

    Delete this and anybody who guesses an agent's name can attach their own account to it, or learn
    that it exists by the difference in what they are told."""
    for who in (COLLEAGUE, ADMINISTRATOR, STRANGER):
        for asked in (
            console.get(who, MINE),
            console.press(who, MINE, attached=True),
            console.press(who, MINE, attached=False),
        ):
            never = console.get(who, "never_made")
            assert asked.status_code == 404 == never.status_code
            assert asked.json()["message"] == never.json()["message"]
    assert console.memory.writes == []


def test_a_team_agent_a_reader_can_see_is_told_the_rule_and_a_read_of_it_is_the_404(
    console: Console,
) -> None:
    """A press to attach on a team agent is refused in the one sentence, nothing is written, and the
    card's read is the 404 because a team agent has no such card.

    Delete this and a team agent can be given one person's own account, which is the leak needs item
    189 exists to stop."""
    refused = console.press(OWNER, TEAM, attached=True)

    assert (refused.status_code, refused.json()["message"]) == (
        409,
        A_TEAM_AGENT_CARRIES_NO_ONES_OWN_ACCOUNT,
    )
    assert console.get(OWNER, TEAM).status_code == 404
    assert console.memory.writes == []


def test_a_person_who_may_not_have_the_account_is_told_so_and_nothing_is_written(
    console: Console,
) -> None:
    """Without the read of Google Workspace in the connection's department, and with Google
    Workspace not connected, the owner is refused in one sentence that names neither.

    Delete this and the card says attached for an account nothing would ever be read from."""
    kept = GRANTS[OWNER]
    GRANTS[OWNER] = ()
    try:
        no_read = console.press(OWNER, MINE, attached=True)
    finally:
        GRANTS[OWNER] = kept
    console.records.rows.clear()
    not_connected = console.press(OWNER, MINE, attached=True)

    assert (no_read.status_code, no_read.json()["message"]) == (409, NOT_OFFERED_TO_YOU)
    assert (not_connected.status_code, not_connected.json()["message"]) == (409, NOT_OFFERED_TO_YOU)
    assert console.memory.writes == []


def test_with_the_switch_off_attaching_is_refused_and_detaching_still_works(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off refuses the press in its own sentence; an account attached before it went off stays
    attached and can be taken off.

    Delete this and the switch that ships off ships on, or a person is held up taking their own
    account off their own agent."""
    console.press(OWNER, MINE, attached=True)

    async def no(_sessions: object) -> bool:
        return False

    monkeypatch.setattr("brain.agent_own_workspace_routes.own_workspace_is_on", no)
    console.press(OWNER, MINE, attached=False)
    off = console.press(OWNER, MINE, attached=True)

    assert (off.status_code, off.json()["message"]) == (409, NOT_SWITCHED_ON)
    assert connectors_of(console, MINE) == ()
    assert [one.reason_code for one in console.memory.writes] == [ATTACHED_REASON, DETACHED_REASON]


def test_attaching_twice_and_detaching_what_is_not_attached_are_each_told_and_write_nothing(
    console: Console,
) -> None:
    """The second attach and a detach of nothing are refused in their own sentences.

    Delete this and a repeated press writes a second ledger entry for a change that never
    happened."""
    nothing = console.press(OWNER, MINE, attached=False)
    console.press(OWNER, MINE, attached=True)
    twice = console.press(OWNER, MINE, attached=True)

    assert nothing.json()["message"] == NOT_ATTACHED
    assert twice.json()["message"] == ALREADY_ATTACHED
    assert len(console.memory.writes) == 1


def test_a_stale_page_is_told_the_agent_moved_and_nothing_is_written(console: Console) -> None:
    """When another change lands between the read and the write, the compare and set fails and the
    person is told, in words, to look again.

    Delete this and a press made from a stale page overwrites somebody else's change to the list."""
    console.memory.racing = True

    lost = console.press(OWNER, MINE, attached=True)

    assert (lost.status_code, lost.json()["message"]) == (409, THE_AGENT_MOVED)
    assert console.memory.writes == []


# ---------------------------------------------------------------------------- the ceiling
def personal_record(
    *, connectors: tuple[str, ...], capabilities: tuple[str, ...] = ()
) -> AgentRecord:
    return AgentRecord(
        agent_id="amy_helper",
        display_name="Amy helper",
        persona="Reads its owner's mail for them.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=ADA),
        authority=AgentAuthority(
            capabilities=tuple(Capability(value=one) for one in capabilities),
            connectors=connectors,
        ),
        created_by=ADA,
    )


def team_record(*, connectors: tuple[str, ...], capabilities: tuple[str, ...] = ()) -> AgentRecord:
    personal = personal_record(connectors=connectors, capabilities=capabilities)
    return personal.model_copy(
        update={
            "audience": AgentAudience(
                level=Visibility.DEPARTMENT, owner_id=ADA, department=OPERATIONS
            )
        }
    )


def held(record: AgentRecord) -> set[str]:
    return {one.capability.value for one in entitlement_ceiling(record).grants}


def test_naming_the_connector_on_a_personal_agent_is_the_whole_of_attaching_it() -> None:
    """The ceiling of a personal agent holds the read of Google Workspace exactly when it names the
    connector, and holds it once however it is also written.

    Delete this and attaching changes a page and no run, or a run reads a mailbox its page does not
    show."""
    assert gws.READER in held(personal_record(connectors=(CONNECTOR,)))
    assert gws.READER not in held(personal_record(connectors=()))
    both = personal_record(connectors=(CONNECTOR,), capabilities=(gws.READER,))
    assert [one.capability.value for one in entitlement_ceiling(both).grants].count(gws.READER) == 1


def test_a_team_agent_never_carries_the_read_however_it_is_written() -> None:
    """A department's agent that names the connector, and one that names the read as a capability as
    well, hold neither; the same two on a personal agent are the siblings that hold it.

    Delete this and a team agent reads the asker's own mail into answers other people read, the leak
    `A_TEAM_AGENT_NEVER_CARRIES_A_PERSONS_OWN_WORKSPACE` exists to stop."""
    for connectors, capabilities in (
        ((CONNECTOR,), ()),
        ((CONNECTOR,), (gws.READER,)),
        ((), (gws.READER,)),
    ):
        assert gws.READER not in held(team_record(connectors=connectors, capabilities=capabilities))
    assert gws.READER in held(personal_record(connectors=(CONNECTOR,), capabilities=(gws.READER,)))
    assert own_reads(team_record(connectors=(CONNECTOR,))) == ()
    assert "own" in A_TEAM_AGENT_NEVER_CARRIES_A_PERSONS_OWN_WORKSPACE


def test_a_personal_agent_listing_the_read_without_naming_the_connector_does_not_hold_it() -> None:
    """The read is an entity the connector provides, so it is bound like every other: an agent that
    lists it and does not name the connector is not left holding it.

    Delete this and the read is the one capability on a connector's entity that no connector list
    narrows."""
    assert gws.READER not in held(personal_record(connectors=(), capabilities=(gws.READER,)))
    assert provider_of(gws.READER_ENTITY) == gws.CONNECTOR_NAME


def test_the_spellings_the_agent_model_holds_are_the_connectors_own() -> None:
    """The model cannot import the connector (a cycle), so it spells the connector and its read;
    each is held equal to the connector's here.

    Delete this and a rename in the connector leaves the agent model deriving a read nobody
    holds."""
    assert {gws.CONNECTOR_NAME: gws.READER} == PERSONS_OWN_READS
    assert {gws.CONNECTOR_NAME} == PERSONS_OWN_CONNECTORS
    assert CONNECTOR == gws.CONNECTOR_NAME
    assert Capability(value=gws.READER).noun == gws.READER_ENTITY


# ------------------------------------------------------------------------------ the read
def caller_with_the_read(who: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id=who,
        grants=(Grant(capability=READ_WORKSPACE, scope=Scope.department(OPERATIONS)),),
    )


def test_a_personal_agent_reads_its_owners_own_account_with_their_token_and_nobody_elses() -> None:
    """The owner's run of their personal agent is handed passages read as them, with Google called
    for their account alone; the same caller through a team agent naming the same connector, and
    through a personal agent that never named it, is handed nothing and Google is never called.

    Delete this and the attachment is a page and not a read, or a team agent is a way to a
    mailbox."""
    mine = personal_record(connectors=(CONNECTOR,))
    google, keys = consented(ADA)
    run = caller_with_the_read(ADA).intersect(entitlement_ceiling(mine), NOW)

    reading = passages_for(run, google, keys)

    assert reading.records
    assert {who for _, who in google.asked} == {ADA}
    assert all(one.owner_id == ADA for one in reading.records)
    for record in (team_record(connectors=(CONNECTOR,)), personal_record(connectors=())):
        silent, quiet_keys = consented(ADA)
        run = caller_with_the_read(ADA).intersect(entitlement_ceiling(record), NOW)
        assert passages_for(run, silent, quiet_keys).records == ()
        assert silent.asked == []


def test_a_colleague_asking_reads_their_own_account_and_never_the_owners() -> None:
    """Whoever asks is read with their own token: the colleague who asks without the owner's agent
    is handed their own mail (here, none, since they have not consented) and Google is never called
    in the owner's name.

    Delete this and one person's consent is a way to read their mail for somebody else."""
    google, keys = consented(ADA)
    reading = passages_for(caller_with_the_read("u_bea"), google, keys)

    assert reading.records == ()
    assert ADA not in {who for _, who in google.asked}


def test_a_person_who_is_not_the_owner_is_refused_even_where_the_audience_check_said_yes(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route asks for the owner as well as the audience, so a personal agent somebody else was
    somehow offered is still not theirs to attach to: the read and the press are the 404 and nothing
    is written.

    Delete this and the audience check is the only thing between a colleague and another person's
    agent, which a row beside an audience once made findable."""
    monkeypatch.setattr("brain.agent_own_workspace_routes.visible", lambda *_args, **_kw: True)

    for asked in (console.get(COLLEAGUE, MINE), console.press(COLLEAGUE, MINE, attached=True)):
        never = console.get(COLLEAGUE, "never_made")
        assert asked.status_code == 404 == never.status_code
        assert asked.json()["message"] == never.json()["message"]
    assert console.memory.writes == []
    assert console.press(OWNER, MINE, attached=True).status_code == 200


def test_a_name_for_the_connector_on_a_team_agent_is_inert_and_is_not_an_attachment(
    console: Console,
) -> None:
    """A department's agent that still names the connector (an agent published wider than it was)
    is not attached: its card is the 404, a detach is refused as nothing attached, and nothing is
    written.

    Delete this and the page offers to take off an account the agent never carried, writing a ledger
    entry for a change that changed nothing."""
    console.memory.agents[TEAM] = found(
        TEAM, level=Visibility.DEPARTMENT, owner=OWNER, connectors=(CONNECTOR,)
    )

    refused = console.press(OWNER, TEAM, attached=False)

    assert (refused.status_code, refused.json()["message"]) == (409, NOT_ATTACHED)
    assert console.get(OWNER, TEAM).status_code == 404
    assert console.memory.writes == []
