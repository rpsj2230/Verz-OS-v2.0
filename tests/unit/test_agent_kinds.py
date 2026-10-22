"""Team and personal agents: who may make which, and what the page says an agent is.

The kind is derived from the audience, and the capability rule is the builder's: a person who holds
no install authority may make an agent only they can find, and only while `personal_agents` is on;
an administrator makes both kinds either way. These tests drive the real application's builder
routes through the same in-memory store `tests/unit/test_agent_builder_routes.py` uses.

Task ids: M39.10.1, M39.10.2
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from brain.agent_builder_routes import (
    DRAFTS_PATH,
    EDIT_PATH,
    FORM_PATH,
    PUBLISH_PATH,
    PUBLISHED_NEW,
    REFUSED,
    SAVE_PATH,
    WAITS_FOR_A_SECOND_PERSON,
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
    a_document,
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


def _ready_reaching(console: Console, pid: str) -> tuple[str, int]:
    """A new draft of `pid` holding an agent that reads invoices, saved and checked."""
    draft = console.post(pid, DRAFTS_PATH, {}).json()
    saved_as = console.post(
        pid,
        at(SAVE_PATH, draft_id=draft["draft_id"]),
        {"document": a_document(), "base": draft["revision"]},
    )
    assert saved_as.status_code == 200, saved_as.text
    revision: int = saved_as.json()["revision"]
    return draft["draft_id"], revision


def test_a_member_publishes_their_own_agent_at_once_when_it_reaches_no_further_than_they_do(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A member who reads invoices (`u_wide`) builds an agent that reads invoices: the check says
    nobody else is needed and the publish goes out on their word, personal and theirs. The owner's
    direction on needs item 173 is that a person makes their own agent without asking anybody.

    Delete this and a member's own agent waits for a second person for every capability it names,
    which is asking somebody."""
    _on(monkeypatch, value=True)
    draft_id, revision = _ready_reaching(console, "u_wide")

    check = checked(console, draft_id, revision, "u_wide").json()
    assert check["passed"] is True
    assert check["second_person_needed"] is False and check["widened"] == []
    made = console.post("u_wide", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert made.status_code == 201, made.text
    record = console.memory.agents[made.json()["agent_id"]].record
    assert record.audience == AgentAudience(level=Visibility.PERSONAL, owner_id="u_wide")
    assert "read:invoice.reference" in {one.value for one in record.authority.capabilities}


def test_a_member_whose_agent_reaches_further_than_they_do_still_waits_for_a_second_person(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal side of the same rule: the same agent built by a member who reads nothing is
    held for a second person, the check says so, and nothing is stored until one approves it.

    Delete this and the exemption can be widened to every member, so a ceiling that outgrows its
    author's reach ships on that author's word alone."""
    _on(monkeypatch, value=True)
    draft_id, revision = _ready_reaching(console, MEMBER)
    before = set(console.memory.agents)

    check = checked(console, draft_id, revision, MEMBER).json()
    assert check["second_person_needed"] is True
    assert "read:invoice.reference" in check["widened"]
    asked = console.post(MEMBER, at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert asked.status_code == 202, asked.text
    assert asked.json()["sentence"] == WAITS_FOR_A_SECOND_PERSON
    assert set(console.memory.agents) == before


def test_an_administrators_publish_keeps_its_second_person_even_when_it_is_their_own_reach(
    console: Console,
) -> None:
    """An administrator who holds the install authority and reads invoices builds the same agent
    and it still waits, because they make both kinds and the kind is chosen at the publish.

    Delete this and the member's exemption becomes everybody's, which removes the second person
    from every administrator's publish."""
    draft_id, revision = _ready_reaching(console, "u_admin")
    assert checked(console, draft_id, revision, "u_admin").json()["passed"]

    asked = console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert asked.status_code == 202, asked.text
    assert asked.json()["sentence"] == WAITS_FOR_A_SECOND_PERSON


def test_the_exemption_is_for_the_callers_own_personal_agent_in_their_reach_and_no_other() -> None:
    """Asked directly of the rule: it holds for a member's own personal agent that reads what they
    read, and not for someone else's personal agent, a department's agent, an agent reading what
    the member does not, or a caller who holds the install authority.

    Delete this and the rule can be loosened on any one of those four sides while the routes'
    tests, which can only reach a member's own new agent, stay green."""
    from types import SimpleNamespace

    from brain.agent_builder_routes import _owners_own_within_their_reach
    from brain.agents.creation import AGENT_INSTALL_CAPABILITY

    reads = Grant(capability=Capability(value="read:invoice"), scope=Scope.unrestricted())
    install = Grant(capability=AGENT_INSTALL_CAPABILITY, scope=Scope.unrestricted())

    def asked(*grants: Grant) -> Any:
        reach = EntitlementSet(principal_id="u_maker", grants=grants)
        return SimpleNamespace(
            reach=reach,
            now=datetime(2019, 3, 1, 9, 0, tzinfo=UTC),
            caller=SimpleNamespace(principal=SimpleNamespace(id="u_maker")),
        )

    mine = AgentAudience(level=Visibility.PERSONAL, owner_id="u_maker")
    record = AgentRecord(
        agent_id="invoice_helper",
        display_name="Invoice helper",
        persona="Answers questions about invoices the asker may read.",
        audience=mine,
        authority=AgentAuthority(
            scope=Scope.unrestricted(), capabilities=(Capability(value="read:invoice"),)
        ),
        created_by="u_maker",
    )
    someone_elses = AgentAudience(level=Visibility.PERSONAL, owner_id="u_other")
    a_departments = AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_maker", department="web")

    assert _owners_own_within_their_reach(mine, record, asked(reads)) is True
    assert _owners_own_within_their_reach(someone_elses, record, asked(reads)) is False
    assert _owners_own_within_their_reach(a_departments, record, asked(reads)) is False
    assert _owners_own_within_their_reach(mine, record, asked()) is False
    assert _owners_own_within_their_reach(mine, record, asked(reads, install)) is False


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


def test_a_person_edits_their_own_personal_agent_and_nobody_else_edits_it(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the switch on, the owner of a personal agent starts a draft that changes it, and an
    administrator who cannot see it is answered as for an agent never made; with the switch off the
    owner is refused too, as they are everywhere else the builder is closed to them.

    Delete this and a person can make an agent they can then never change, or edit one that is not
    theirs."""
    _on(monkeypatch, value=True)
    draft_id, revision = _ready(console, MEMBER)
    made = console.post(MEMBER, at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})
    agent_id = made.json()["agent_id"]
    edit = at(EDIT_PATH, agent_id=agent_id)

    mine = console.post(MEMBER, edit)
    theirs = console.post("u_admin", edit)
    never = console.post("u_admin", at(EDIT_PATH, agent_id="never_made_here"))

    assert mine.status_code == 201, mine.text
    assert mine.json()["kind"] == "edit"
    assert theirs.status_code == never.status_code == 404
    assert theirs.json()["message"] == never.json()["message"]

    _on(monkeypatch, value=False)
    assert console.post(MEMBER, edit).status_code == 404
