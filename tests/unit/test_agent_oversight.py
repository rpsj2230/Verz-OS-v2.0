"""Oversight of personal agents: who is told that one exists, and that it offers nothing.

A personal agent is found and used by its owner alone. A reader who holds the audit capability
for it may also be told, for oversight, that it exists, whose it is and whether it runs, and
nothing it holds. The domain is driven directly; the route is driven through the real application
over the stub database `tests/unit/test_agent_routes.py` builds, which is the same borrowing the
other agent route tests make.

Task ids: M39.10.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from brain.agent_oversight_routes import MAX_OVERSEEN, OVERSIGHT_PATH, OversightPage
from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentViewer,
    runnable_agent_ids,
    visible_agent_ids,
)
from brain.agents.oversight import AGENT_ACTIONS, OverseenAgent, overseen
from brain.api import API_PREFIX
from brain.audit.ledger import AuditAction
from brain.audit.view import CAPABILITY_BY_KIND
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.visibility import Visibility
from tests.unit.test_agent_routes import (
    GRANTS,
    Stored,
    agent_row,
    client,
    get,
    stored,
    workspace_of,
)

assert client and stored  # fixtures, imported so pytest finds them here

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
LATER = datetime(2999, 1, 1, tzinfo=UTC)

AUDIT_AGENT = CAPABILITY_BY_KIND["agent"]
PATH = f"{API_PREFIX}{OVERSIGHT_PATH}"


def personal(agent_id: str, owner: str, *, name: str | None = None) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name=name or agent_id.replace("_", " ").title(),
        persona="Answers its owner and nobody else.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=owner),
        authority=AgentAuthority(),
        created_by=owner,
    )


def team(agent_id: str, owner: str) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name=agent_id.replace("_", " ").title(),
        persona="Answers a department.",
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=owner, department="web"),
        authority=AgentAuthority(),
        created_by=owner,
    )


def auditor(scope: Scope | None = None, *, who: str = "u_auditor") -> EntitlementSet:
    return EntitlementSet(
        principal_id=who, grants=(Grant(capability=AUDIT_AGENT, scope=scope or Scope()),)
    )


# ---------------------------------------------------------------------------- the domain
def test_a_reader_holding_the_audit_capability_is_told_of_other_peoples_personal_agents() -> None:
    """The positive case for every refusal below: an auditor whose grant covers agents is told of
    each personal agent, by name, owner and state, in name order.

    Delete this and the refusals are satisfied by a view that lists nothing to anybody."""
    records = [personal("zed_helper", "u_zed"), personal("amy_helper", "u_amy")]

    told = overseen(records, auditor(), NOW)

    assert told == (
        OverseenAgent("amy_helper", "Amy Helper", "u_amy", records[1].state),
        OverseenAgent("zed_helper", "Zed Helper", "u_zed", records[0].state),
    )


def test_a_reader_with_no_audit_capability_is_told_of_none() -> None:
    """Without a grant over agents the answer is empty, whatever else the reader holds.

    Delete this and every person is told which of their colleagues have made an agent."""
    other = Grant(capability=CAPABILITY_BY_KIND["grant"], scope=Scope())
    reader = EntitlementSet(principal_id="u_nosy", grants=(other,))

    assert overseen([personal("amy_helper", "u_amy")], reader, NOW) == ()
    assert (
        overseen([personal("amy_helper", "u_amy")], EntitlementSet(principal_id="u_x"), NOW) == ()
    )


def test_a_team_agent_and_the_readers_own_agents_are_not_listed() -> None:
    """Oversight is of other people's personal agents: a team agent is on the roster of its
    audience, and a person's own personal agent is on their own.

    Delete this and an auditor's own agents turn up under a heading about other people's, or team
    agents are listed twice."""
    records = [
        team("web_helper", "u_amy"),
        personal("mine", "u_auditor"),
        personal("amy_helper", "u_amy"),
    ]

    told = overseen(records, auditor(), NOW)

    assert [one.agent_id for one in told] == ["amy_helper"]


def test_a_grant_scoped_to_a_departments_people_covers_the_agents_those_people_own() -> None:
    """A head whose audit grant is scoped to the people a department places (the staff sync's
    `actor_id IN ...`) is told of those people's personal agents and of nobody else's.

    Delete this and either a head is told of agents outside their department, or the department
    head's grant covers none, so oversight is only ever the whole company's."""
    mine = Scope(clauses=(Clause(field="actor_id", op=Op.IN, value=("u_amy",)),))
    records = [personal("amy_helper", "u_amy"), personal("zed_helper", "u_zed")]

    told = overseen(records, auditor(mine, who="u_head"), NOW)

    assert [one.agent_id for one in told] == ["amy_helper"]


def test_a_reader_whose_own_standing_has_expired_is_told_of_none() -> None:
    """The reader's expiry is judged at the instant asked: the same grant lists the agent before it
    and nothing after.

    Delete this and an auditor who has left still sees who has made an agent."""
    reader = auditor().model_copy(update={"not_after": datetime(2020, 1, 1, tzinfo=UTC)})
    records = [personal("amy_helper", "u_amy")]

    assert [one.agent_id for one in overseen(records, reader, NOW)] == ["amy_helper"]
    assert overseen(records, reader, LATER) == ()


def test_oversight_names_the_agent_and_nothing_it_holds() -> None:
    """An entry has exactly four fields, none of them its persona, connectors, channels or any
    figure, and none a total.

    Delete this and a field added later for convenience tells an auditor what an owner connected."""
    assert list(OverseenAgent.__dataclass_fields__) == [
        "agent_id",
        "display_name",
        "owner_id",
        "state",
    ]


def test_being_overseen_gives_the_auditor_no_way_to_find_use_or_open_the_agent() -> None:
    """The audience is not widened: the agent is in nobody's roster but its owner's, and nothing
    that selects an agent to answer would choose it for the auditor.

    Delete this and oversight becomes the one-line widening of the audience that lets an auditor ask
    another person's agent a question."""
    record = personal("amy_helper", "u_amy")
    viewer = AgentViewer(principal_id="u_auditor", departments=frozenset({"web"}))
    owner = AgentViewer(principal_id="u_amy")

    assert overseen([record], auditor(), NOW)
    assert visible_agent_ids([record], viewer) == frozenset()
    assert runnable_agent_ids([record], viewer) == frozenset()
    assert visible_agent_ids([record], owner) == frozenset({"amy_helper"})


def test_a_person_named_beside_a_personal_audience_still_does_not_find_the_agent() -> None:
    """A department or a person added beside an audience offers the agent to them at the department
    level, and at the personal level it offers it to nobody.

    Delete this and one row beside a personal audience makes another person's agent findable."""
    audience = AgentAudience(
        level=Visibility.PERSONAL,
        owner_id="u_amy",
        extra_people=("u_zed",),
        extra_departments=("web",),
    )
    record = personal("amy_helper", "u_amy").model_copy(update={"audience": audience})
    department = team("web_helper", "u_amy").model_copy(
        update={
            "audience": AgentAudience(
                level=Visibility.DEPARTMENT,
                owner_id="u_amy",
                department="web",
                extra_people=("u_zed",),
            )
        }
    )
    zed = AgentViewer(principal_id="u_zed", departments=frozenset({"web"}))

    assert visible_agent_ids([record], zed) == frozenset()
    assert visible_agent_ids([department], zed) == frozenset({"web_helper"})


def test_the_two_actions_the_ledger_records_an_agent_under_are_the_ones_asked() -> None:
    """Oversight asks the capability of the entries an agent's life and owner are written as.

    Delete this and a scope written on an action covers none of them (or all of the wrong ones)."""
    assert set(AGENT_ACTIONS) == {AuditAction.AGENT, AuditAction.AGENT_OWNER}
    only_agent = Scope(clauses=(Clause(field="action", op=Op.EQ, value="agent"),))
    only_grants = Scope(clauses=(Clause(field="action", op=Op.EQ, value="grant"),))
    records = [personal("amy_helper", "u_amy")]

    assert overseen(records, auditor(only_agent), NOW)
    assert overseen(records, auditor(only_grants), NOW) == ()


# ------------------------------------------------------------------------------ the route
@pytest.fixture
def on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The switch on, and `u_wide` an auditor over every agent."""

    async def yes(_sessions: object) -> bool:
        return True

    monkeypatch.setattr("brain.agent_oversight_routes.oversight_is_on", yes)
    monkeypatch.setitem(GRANTS, "u_wide", (Grant(capability=AUDIT_AGENT, scope=Scope()),))
    yield


def made(stored: Stored) -> None:
    stored.agents["amy_helper"] = agent_row(
        "amy_helper", level=Visibility.PERSONAL, owner_id="u_narrow"
    )
    stored.agents["web_helper"] = agent_row(
        "web_helper", level=Visibility.DEPARTMENT, owner_id="u_narrow", department="web"
    )


def test_the_route_tells_an_auditor_of_a_personal_agent_and_nobody_else(
    client: TestClient, stored: Stored, on: None
) -> None:
    """With the switch on, the auditor is told of the personal agent (not the team one) with its
    owner's name; the owner, a stranger and a person holding nothing are told of none.

    Delete this and the screen's list is satisfied by a route that answers every reader the same."""
    made(stored)

    seen = get(client, "u_wide", PATH).json()
    assert [
        (one["agent_id"], one["owner_id"], one["owner_name"], one["state"]) for one in seen["items"]
    ] == [("amy_helper", "u_narrow", "Person u_narrow", "enabled")]
    for reader in ("u_narrow", "u_none", "u_admin"):
        assert get(client, reader, PATH).json() == {"items": [], "truncated": False}


def test_every_reader_gets_one_status_and_one_shape_whether_or_not_there_is_anything_to_tell(
    client: TestClient, stored: Stored, on: None
) -> None:
    """An auditor of an estate with no personal agent, a reader with no capability and a reader of
    an estate that has some are all answered `200` with the same two fields.

    Delete this and the answer says which readers hold the capability, or whether anybody has made
    a personal agent, by a refusal or by a field present for some and absent for others."""
    answers = []
    for populated in (False, True):
        stored.agents.clear()
        if populated:
            made(stored)
        for reader in ("u_wide", "u_none"):
            response = get(client, reader, PATH)
            answers.append((response.status_code, sorted(response.json())))

    assert answers == [(200, ["items", "truncated"])] * 4
    assert sorted(OversightPage.model_fields) == ["items", "truncated"]


def test_with_the_switch_off_even_an_auditor_is_told_of_none(
    client: TestClient, stored: Stored, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off is the empty answer, the one an estate with no personal agents gives.

    Delete this and the switch that ships off ships on."""

    async def no(_sessions: object) -> bool:
        return False

    monkeypatch.setattr("brain.agent_oversight_routes.oversight_is_on", no)
    monkeypatch.setitem(GRANTS, "u_wide", (Grant(capability=AUDIT_AGENT, scope=Scope()),))
    made(stored)

    assert get(client, "u_wide", PATH).json() == {"items": [], "truncated": False}


def test_an_overseen_agent_is_still_the_404_an_agent_never_made_is_to_the_auditor(
    client: TestClient, stored: Stored, on: None
) -> None:
    """The auditor told of the agent opens its workspace and is answered exactly as for an agent
    that does not exist; the owner opens it.

    Delete this and oversight is the roster by another name, and a way to read what the agent
    holds."""
    made(stored)

    assert [one["agent_id"] for one in get(client, "u_wide", PATH).json()["items"]] == [
        "amy_helper"
    ]
    seen = workspace_of(client, "u_wide", "amy_helper")
    never = workspace_of(client, "u_wide", "never_made")
    assert (seen.status_code, seen.json()["message"]) == (
        never.status_code,
        never.json()["message"],
    )
    assert seen.status_code == 404
    assert workspace_of(client, "u_narrow", "amy_helper").status_code == 200


def test_the_roster_does_not_list_an_overseen_agent_to_the_auditor(
    client: TestClient, stored: Stored, on: None
) -> None:
    """The auditor's roster holds the team agent and not the personal one.

    Delete this and the roster is widened for oversight, which is the conflation of seeing and
    using that `AUDIENCE_IS_NOT_AUTHORITY` refuses."""
    made(stored)
    page = get(client, "u_wide", f"{API_PREFIX}/agents").json()

    assert "amy_helper" not in [one["agent_id"] for one in page["items"]]


def test_the_page_is_bounded_and_says_only_that_there_is_more_to_tell(
    client: TestClient, stored: Stored, on: None
) -> None:
    """More than the bound inside the reader's reach is one flag and `MAX_OVERSEEN` entries; never a
    number.

    Delete this and the list is unbounded, or the flag becomes a total."""
    for number in range(MAX_OVERSEEN + 1):
        name = f"agent_{number:04d}"
        stored.agents[name] = agent_row(name, level=Visibility.PERSONAL, owner_id="u_narrow")

    answer = get(client, "u_wide", PATH).json()

    assert len(answer["items"]) == MAX_OVERSEEN
    assert answer["truncated"] is True
    assert sorted(answer) == ["items", "truncated"]


# --------------------------------------------------------------- the other places it could leak
def test_a_leavers_personal_agent_is_not_offered_to_whoever_may_adopt_agents() -> None:
    """The leaver's team agent is offered for a new owner and their personal agent is not: it was
    found by its owner alone, and taking it would show another person's agent and what its owner
    connected to it.

    Delete this and the Staff sources screen lists a person's personal agent to an administrator
    when that person leaves."""
    from brain.console.staff_source_view import transfers_for

    everything = EntitlementSet(
        principal_id="u_admin",
        grants=(
            Grant(capability=Capability(value="admin:agent"), scope=Scope()),
            Grant(capability=Capability(value="admin:agent_lifecycle"), scope=Scope()),
        ),
    )
    records = [team("web_helper", "u_gone"), personal("gone_helper", "u_gone")]

    listed = transfers_for(records, leavers=frozenset({"u_gone"}), reader=everything, now=NOW)

    assert [one.agent_id for one in listed] == ["web_helper"]


def test_the_audit_question_for_an_agent_is_asked_in_its_owners_name() -> None:
    """`may_audit` takes the actor of the entries when it is not the subject; left out it is the
    subject, as it always was.

    Delete this and a department-scoped grant covers agents by their own ids, which no people list
    ever names, so a head is told of none."""
    from brain.audit.view import may_audit

    scope = Scope(clauses=(Clause(field="actor_id", op=Op.IN, value=("u_amy",)),))
    head = auditor(scope, who="u_head")

    def asked(**more: str) -> bool:
        return may_audit(
            head,
            subject_kind="agent",
            subject_id="amy_helper",
            actions=AGENT_ACTIONS,
            now=NOW,
            **more,
        )

    assert asked(actor_id="u_amy")
    assert not asked(actor_id="u_zed")
    assert not asked()


def test_a_reader_outside_every_audit_reach_makes_the_route_read_no_agent(
    client: TestClient, stored: Stored, on: None
) -> None:
    """The capability is asked before the estate is read, so a reader who holds none costs the
    database nothing and the answer cannot be timed to say how many agents there are.

    Delete this and the gate in front of the read can go, with every answer unchanged, and an
    ordinary person's request reads the whole agent table."""
    made(stored)

    answer = get(client, "u_none", PATH)

    assert answer.json() == {"items": [], "truncated": False}
    assert stored.statements == []
