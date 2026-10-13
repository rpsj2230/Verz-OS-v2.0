"""Team and personal agents: who may make which, and what the page says an agent is.

The kind is derived from the audience, and the capability rule is the builder's: a person who holds
no install authority may make an agent only they can find, and only while `personal_agents` is on;
an administrator makes both kinds either way. These tests drive the real application's builder
routes through the same in-memory store `tests/unit/test_agent_builder_routes.py` uses.

Task ids: M39.10.1, M39.10.2
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.agent_builder_routes import (
    DRAFTS_PATH,
    FORM_PATH,
    PUBLISH_PATH,
    PUBLISHED_NEW,
    REFUSED,
    SAVE_PATH,
)
from brain.agents.attachments import AttachmentError, connectors_after_attach, with_connectors
from brain.agents.kinds import (
    ONLY_AN_ADMINISTRATOR_MAKES_A_TEAM_AGENT,
    PERSONAL_AGENTS_ARE_NOT_SWITCHED_ON,
    AgentKind,
    kind_of,
    kinds_a_person_may_make,
    refusal_for,
)
from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentViewer,
    entitlement_ceiling,
    visible_agent_ids,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from tests.unit import test_agent_builder_routes as builder
from tests.unit.test_agent_builder_routes import (
    Console,
    at,
    checked,
    not_changed,
    reaching_nothing,
)

MEMBER = "u_elsewhere"


def _on(monkeypatch: pytest.MonkeyPatch, *, value: bool) -> None:
    async def answer(_sessions: object) -> bool:
        return value

    monkeypatch.setattr("brain.agent_builder_routes.personal_agents_on", answer)


#: The builder's console. With no database the switch reads off, as every install ships.
console = builder.console


def _ready(console: Console, pid: str) -> tuple[str, int]:
    response = console.post(pid, DRAFTS_PATH, {})
    assert response.status_code == 201, response.text
    draft = response.json()
    saved_as = console.post(
        pid,
        at(SAVE_PATH, draft_id=draft["draft_id"]),
        {"document": reaching_nothing(), "base": draft["revision"]},
    )
    assert saved_as.status_code == 200, saved_as.text
    revision: int = saved_as.json()["revision"]
    assert checked(console, draft["draft_id"], revision, pid).json()["passed"]
    return draft["draft_id"], revision


def test_the_kind_is_read_off_the_audience_and_stored_nowhere() -> None:
    """A personal audience is a personal agent; a department's and the company's are team agents.

    Delete this and a new audience level could be added with no kind, or a stored kind could drift
    from the audience that actually decides who may use the agent."""
    assert kind_of(AgentAudience(level=Visibility.PERSONAL, owner_id="u_a")) is AgentKind.PERSONAL
    assert (
        kind_of(AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_a", department="web"))
        is AgentKind.TEAM
    )
    assert kind_of(AgentAudience(level=Visibility.COMPANY, owner_id="u_a")) is AgentKind.TEAM


def test_an_administrator_makes_both_kinds_and_anybody_else_only_their_own_while_it_is_on() -> None:
    """The authority table: both for the install authority, personal alone behind the switch,
    nothing with the switch off.

    Delete this and the member's narrow authority could widen to a team agent, or the switch could
    stop mattering."""
    both = (AgentKind.PERSONAL, AgentKind.TEAM)
    assert kinds_a_person_may_make(installs=True, personal_on=False) == both
    assert kinds_a_person_may_make(installs=True, personal_on=True) == both
    assert kinds_a_person_may_make(installs=False, personal_on=True) == (AgentKind.PERSONAL,)
    assert kinds_a_person_may_make(installs=False, personal_on=False) == ()


def test_each_refusal_says_what_it_is_and_a_permitted_kind_has_none() -> None:
    """A team agent is refused in the administrator sentence and a switched-off personal agent in
    the switch's; a kind that is allowed is not refused.

    Delete this and a refusal could say the wrong thing, or refuse a permitted kind."""
    only_personal = (AgentKind.PERSONAL,)
    assert (
        refusal_for(AgentKind.TEAM, only_personal, personal_on=True)
        == ONLY_AN_ADMINISTRATOR_MAKES_A_TEAM_AGENT
    )
    assert (
        refusal_for(AgentKind.PERSONAL, (), personal_on=False)
        == PERSONAL_AGENTS_ARE_NOT_SWITCHED_ON
    )
    assert refusal_for(AgentKind.PERSONAL, only_personal, personal_on=True) is None
    assert refusal_for(AgentKind.TEAM, (*only_personal, AgentKind.TEAM), personal_on=True) is None


def test_with_the_switch_off_a_person_without_the_authority_cannot_start_the_builder(
    console: Console,
) -> None:
    """As shipped, only the install authority builds: a member's start is the one 404, so a
    switched-off install behaves as it did before this was written.

    Delete this and the switch ships on in effect."""
    assert console.post(MEMBER, DRAFTS_PATH, {}).status_code == 404
    assert console.get(MEMBER, FORM_PATH).status_code == 404


def test_with_the_switch_on_a_person_makes_an_agent_only_they_can_find(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive case: the member's draft is offered the personal kind alone, publishes with no
    one's approval, and the agent is theirs, personal and named a personal agent by its owner.

    Delete this and every refusal here is satisfied by a builder that refuses everybody."""
    _on(monkeypatch, value=True)
    started = console.post(MEMBER, DRAFTS_PATH, {})
    assert started.status_code == 201
    assert started.json()["agent_kinds"] == ["personal"]
    draft_id, revision = _ready(console, MEMBER)

    made = console.post(MEMBER, at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert made.status_code == 201, made.text
    assert made.json()["sentence"] == PUBLISHED_NEW
    record = console.memory.agents[made.json()["agent_id"]].record
    assert record.audience == AgentAudience(level=Visibility.PERSONAL, owner_id=MEMBER)
    assert kind_of(record.audience) is AgentKind.PERSONAL


def test_a_person_without_the_authority_cannot_publish_a_team_agent_by_either_spelling(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kind named and the older flag both ask for a department's agent, and both are refused
    in the administrator sentence with nothing stored.

    Delete this and a member who ticks "my department" makes an agent other people can use."""
    _on(monkeypatch, value=True)
    for body in ({"for_department": True}, {"agent_kind": "team"}):
        draft_id, revision = _ready(console, MEMBER)
        before = set(console.memory.agents)
        response = console.post(
            MEMBER, at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision, **body}
        )
        assert not_changed(response) == (409, REFUSED, ONLY_AN_ADMINISTRATOR_MAKES_A_TEAM_AGENT)
        assert set(console.memory.agents) == before


def test_an_administrator_makes_a_team_agent_and_is_offered_both_kinds(
    console: Console,
) -> None:
    """The administrator's draft offers both kinds, and a team agent they publish is their
    department's, with the switch off.

    Delete this and the narrowing for members could also narrow administrators."""
    started = console.post("u_admin", DRAFTS_PATH, {})
    assert started.json()["agent_kinds"] == ["personal", "team"]
    draft_id, revision = _ready(console, "u_admin")

    made = console.post(
        "u_admin",
        at(PUBLISH_PATH, draft_id=draft_id),
        {"revision": revision, "agent_kind": "team"},
    )

    assert made.status_code == 201, made.text
    record = console.memory.agents[made.json()["agent_id"]].record
    assert kind_of(record.audience) is AgentKind.TEAM
    assert record.audience.department == "web"


def test_a_personal_agent_made_through_the_builder_is_visible_to_its_owner_alone(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The agent the builder stored is in the roster of its owner and of nobody else, an
    administrator who holds the install authority included.

    Delete this and a personal agent could be listed to a colleague or an administrator."""
    _on(monkeypatch, value=True)
    draft_id, revision = _ready(console, MEMBER)
    made = console.post(MEMBER, at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})
    record = console.memory.agents[made.json()["agent_id"]].record

    def sees(principal: str, department: str | None) -> bool:
        viewer = AgentViewer(
            principal_id=principal, departments=frozenset({department} if department else ())
        )
        return record.agent_id in visible_agent_ids((record,), viewer)

    assert sees(MEMBER, "finance")
    assert not sees("u_admin", "web")
    assert not sees("u_narrow", "finance")


# ------------------------------------------------------------------ a person's own workspace
def _agent_reading_mail(audience: AgentAudience) -> AgentRecord:
    return AgentRecord(
        agent_id="mail_helper",
        display_name="Mail helper",
        persona="Answers questions about the asker's own mail and nobody else's.",
        audience=audience,
        authority=AgentAuthority(
            scope=Scope.unrestricted(),
            capabilities=(Capability(value="read:workspace_mail"),),
            connectors=("google_workspace",),
        ),
        created_by="u_maker",
    )


def test_a_personal_agent_carries_a_persons_own_workspace_and_a_team_agent_never_does() -> None:
    """The same agent naming the same connector holds the mail read when it is personal and holds
    nothing when it is a department's or the company's.

    Delete this and a team agent that names the Google connector reads one person's mail for
    everybody who asks it, which is the leak needs item 189 exists to stop."""
    mine = AgentAudience(level=Visibility.PERSONAL, owner_id="u_maker")
    theirs = (
        AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_maker", department="web"),
        AgentAudience(level=Visibility.COMPANY, owner_id="u_maker"),
    )

    def held(audience: AgentAudience) -> set[str]:
        return {
            one.capability.value
            for one in entitlement_ceiling(_agent_reading_mail(audience)).grants
        }

    assert "read:workspace_mail" in held(mine)
    assert all("read:workspace_mail" not in held(one) for one in theirs)


def test_naming_the_workspace_on_a_team_agent_opens_nothing_so_it_cannot_be_attached() -> None:
    """Attaching the Google connector to a team agent is refused in the sentence for a connector
    that would open nothing, and the same press on a personal agent is accepted.

    Delete this and the attach screen offers a team agent the one connector it must never carry."""
    reach = EntitlementSet(
        principal_id="u_maker",
        grants=(
            Grant(capability=Capability(value="read:workspace_mail"), scope=Scope.unrestricted()),
        ),
    )
    now = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)

    def bare(audience: AgentAudience) -> AgentRecord:
        record = _agent_reading_mail(audience)
        return with_connectors(record, ())

    personal = bare(AgentAudience(level=Visibility.PERSONAL, owner_id="u_maker"))
    team = bare(AgentAudience(level=Visibility.COMPANY, owner_id="u_maker"))

    assert connectors_after_attach("google_workspace", record=personal, by=reach, now=now) == (
        "google_workspace",
    )
    with pytest.raises(AttachmentError):
        connectors_after_attach("google_workspace", record=team, by=reach, now=now)
