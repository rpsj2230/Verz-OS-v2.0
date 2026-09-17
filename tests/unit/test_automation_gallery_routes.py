"""The automation gallery over HTTP: who is shown it, who may install from it, and what one
confirmed request writes.

Driven through the real application with the token machinery borrowed from
`tests/unit/test_api_routes.py`, and with two stores in memory standing where the database is. The
install store keeps the one rule the table keeps, one install per agent, template and person, and
decides nothing else. What reaches PostgreSQL and the ledger entry the trigger appends are proved in
`tests/unit/test_agent_automation_store.py`.

**Every refusal is compared body to body and status to status with the case it must be
indistinguishable from**, and has a sibling proving the permitted case is answered.

Task ids: M39.6.1.3
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import automation_gallery_routes as routes
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.automation_gallery import (
    AUTOMATION_AUTHORITY,
    BUILT_IN,
    IT_STARTS_PAUSED,
    NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET,
    Installation,
    preview,
)
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.admission import SECOND_FACTOR_NEEDED_MESSAGE, Assurance, admit
from brain.gate.context import Channel
from brain.identity.bearer import TokenAuthority
from brain.knowledge.visibility import Visibility
from brain.ops.agent_automation_store import Installed
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SUBJECTS,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

AGENT = "quote_helper"
WEB_AGENT = "web_desk"
TEMPLATE = BUILT_IN[0]

GALLERY = f"{API_PREFIX}/agents/{{agent}}/automation-templates"
PREVIEW = f"{API_PREFIX}/agents/{{agent}}/automation-templates/{{template}}/preview"
INSTALL = f"{API_PREFIX}/agents/{{agent}}/automations"

#: A literal rather than read off `bearer.SECOND_FACTOR_METHODS`, for the reason
#: `test_session_routes` gives about its own copy.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}

EVERYWHERE = Scope.unrestricted()
TAB_READ = tab(Tab.AUTOMATIONS).read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
EXISTENCE = plane_capability(Plane.EXISTENCE)

DEPARTMENTS: Mapping[str, str | None] = {
    "u_narrow": "web",
    "u_wide": "sales",
    "u_prefix": "web",
    "u_none": None,
    "u_admin": "web",
    "u_elsewhere": "finance",
}


def grant(capability: Capability | str, scope: Scope = EVERYWHERE) -> Grant:
    value = capability if isinstance(capability, Capability) else Capability(value=capability)
    return Grant(capability=value, scope=scope)


def on_agent(agent_id: str) -> Scope:
    return Scope(clauses=(Clause(field="agent_id", op=Op.EQ, value=agent_id),))


#: `u_admin` opens the tab and installs anywhere. `u_narrow` opens the tab and holds no authority.
#: `u_wide` opens the tab and installs on another agent only. `u_prefix` holds the authority and
#: the queue grant on the existence plane, which the tab refuses. `u_elsewhere` holds everything
#: and sits in finance, outside the web agent's audience. `u_none` holds nothing.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (
        grant(TAB_READ),
        grant(CONFIGURATION),
        grant(AUTOMATION_AUTHORITY),
        grant("read:client.name"),
        grant("write:ticket"),
    ),
    "u_narrow": (grant(TAB_READ), grant(CONFIGURATION), grant("read:client.name")),
    "u_wide": (
        grant(TAB_READ),
        grant(CONFIGURATION),
        grant(AUTOMATION_AUTHORITY, on_agent("some_other_agent")),
    ),
    "u_prefix": (grant(TAB_READ), grant(EXISTENCE), grant(AUTOMATION_AUTHORITY)),
    "u_elsewhere": (grant(TAB_READ), grant(CONFIGURATION), grant(AUTOMATION_AUTHORITY)),
    "u_none": (),
}


def person(pid: str) -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=f"Person {pid}",
        primary_department=DEPARTMENTS[pid],
    )


class Directory:
    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return person(pid)
        return None


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def an_agent(
    agent_id: str,
    *capabilities: str,
    department: str = "",
) -> AgentRecord:
    level = Visibility.DEPARTMENT if department else Visibility.COMPANY
    return AgentRecord(
        agent_id=agent_id,
        display_name=agent_id.replace("_", " ").title(),
        persona="Answers briefly.",
        audience=AgentAudience(level=level, owner_id="u_steward", department=department),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by="u_builder",
    )


@dataclass
class Agents:
    """`routes.AgentRecords` in memory."""

    held: dict[str, AgentRecord] = field(default_factory=dict)

    async def agent(self, agent_id: str) -> AgentRecord | None:
        return self.held.get(agent_id)


@dataclass
class Installs:
    """`routes.AutomationInstalls` in memory, keeping the table's one rule and no other."""

    rows: dict[str, Installation] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def installed_by(self, agent_id: str, principal_id: str) -> Mapping[str, str]:
        self.calls.append({"installed_by": (agent_id, principal_id)})
        return {
            one.template_id: key
            for key, one in self.rows.items()
            if one.automation.agent_id == agent_id and one.automation.runs_as.id == principal_id
        }

    async def install(
        self, installation: Installation, *, ent_hash: str, trace_id: str
    ) -> Installed:
        self.calls.append({"install": installation, "ent_hash": ent_hash, "trace_id": trace_id})
        for key, one in self.rows.items():
            if (one.automation.agent_id, one.template_id, one.automation.runs_as.id) == (
                installation.automation.agent_id,
                installation.template_id,
                installation.automation.runs_as.id,
            ):
                return Installed(automation_id=key, created=False)
        self.rows[installation.automation.automation_id] = installation
        return Installed(automation_id=installation.automation.automation_id, created=True)


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


@pytest.fixture
def agents() -> Agents:
    return Agents(
        held={
            AGENT: an_agent(AGENT, "read:client.name", "read:invoice.total"),
            WEB_AGENT: an_agent(WEB_AGENT, "read:client.name", department="web"),
        }
    )


@pytest.fixture
def installs() -> Installs:
    return Installs()


@pytest.fixture
def client(agents: Agents, installs: Installs) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    # Included here as well, which is `tests/unit/test_session_routes.py`' arrangement: this file
    # then tests the router whether or not the line in `brain.app` is in the tree it runs in.
    app.include_router(routes.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.agent_records = agents
        app.state.automation_installs = installs
        yield c


def auth(pid: str, *, strong: bool = True) -> dict[str, str]:
    claims: dict[str, object] = {"sid": "sess-1", **(SECOND_FACTOR if strong else {})}
    return {"authorization": f"Bearer {token_for(pid, claims=claims)}"}


def refusal(answer: Response) -> dict[str, Any]:
    """One refusal body with the per-request trace id taken out, its presence asserted."""
    assert answer.status_code == 404, answer.text
    body = dict(answer.json())
    assert "trace_id" in body
    body["trace_id"] = "<per request>"
    return body


def gallery_of(c: TestClient, pid: str, agent: str = AGENT, **kw: bool) -> Response:
    answer: Response = c.get(GALLERY.format(agent=agent), headers=auth(pid, **kw))
    return answer


def preview_of(
    c: TestClient, pid: str, agent: str = AGENT, template: str = TEMPLATE.template_id
) -> Response:
    answer: Response = c.get(PREVIEW.format(agent=agent, template=template), headers=auth(pid))
    return answer


def install_as(
    c: TestClient, pid: str, body: Mapping[str, object], agent: str = AGENT, *, strong: bool = True
) -> Response:
    answer: Response = c.post(
        INSTALL.format(agent=agent), json=dict(body), headers=auth(pid, strong=strong)
    )
    return answer


def confirmed(c: TestClient, pid: str, agent: str = AGENT) -> dict[str, object]:
    shown = preview_of(c, pid, agent)
    assert shown.status_code == 200, shown.text
    return {"template_id": TEMPLATE.template_id, "confirmation": shown.json()["confirmation"]}


# ------------------------------------------------------------------ the gallery


def test_a_reader_of_the_automations_tab_is_shown_every_template_and_what_installing_does(
    client: TestClient,
) -> None:
    """The gallery, listed and ordered, with the sentence that says nothing runs yet. The positive
    case for every gallery refusal below. Delete this and each refusal is satisfied by a route that
    lists nothing."""
    body = gallery_of(client, "u_admin").json()
    expected = sorted(BUILT_IN, key=lambda one: (one.name, one.template_id))

    assert [one["template_id"] for one in body["items"]] == [one.template_id for one in expected]
    assert body["items"][0] == {
        "template_id": expected[0].template_id,
        "version": expected[0].version,
        "name": expected[0].name,
        "summary": expected[0].summary,
        "schedule": expected[0].cadence.words(),
        "installed_as": None,
        "installable": True,
    }
    assert body["installing"] == NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET


def test_a_card_offers_the_install_only_to_a_reader_whose_authority_covers_this_agent(
    client: TestClient,
) -> None:
    """Delete this and the control is drawn for a reader the install then refuses, or withheld
    from one it would accept. Presentation only: the install route decides again."""
    for pid, offered in (("u_admin", True), ("u_narrow", False), ("u_wide", False)):
        items = gallery_of(client, pid).json()["items"]
        assert {one["installable"] for one in items} == {offered}, pid


def test_a_reader_who_may_not_open_the_tab_and_an_agent_nobody_may_see_are_one_answer(
    client: TestClient,
) -> None:
    """DENIED equals ABSENT. The tab refused for want of the plane, an agent that does not exist
    and an agent outside the reader's audience give one status and one body. Delete this and the
    gallery says which agent ids exist to somebody trying them."""
    missing = refusal(gallery_of(client, "u_admin", "no_such_agent"))

    assert refusal(gallery_of(client, "u_prefix")) == missing
    assert refusal(gallery_of(client, "u_none")) == missing
    assert refusal(gallery_of(client, "u_elsewhere", WEB_AGENT)) == missing
    assert gallery_of(client, "u_admin", WEB_AGENT).status_code == 200


def test_no_gallery_answer_carries_a_count_of_anything(client: TestClient) -> None:
    """Delete this and a `total` or a count of installs can be added to the gallery, and a count
    beside a list filtered for one person is a count of what others have."""
    for path in (
        GALLERY.format(agent=AGENT),
        PREVIEW.format(agent=AGENT, template=TEMPLATE.template_id),
    ):
        body = client.get(path, headers=auth("u_admin")).json()
        assert not set(body) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, path


# ------------------------------------------------------------------ the preview


def test_the_preview_shows_the_outcome_who_it_runs_as_its_schedule_its_reach_and_a_paused_start(
    client: TestClient, agents: Agents
) -> None:
    """What the person confirms, as the domain computes it. The reach is the installer's reads that
    the agent's ceiling also allows, and no write. Delete this and the confirmation panel can show
    a principal, a reach or a start that is not the one the install writes."""
    body = preview_of(client, "u_admin").json()
    expected = preview(
        TEMPLATE,
        agents.held[AGENT],
        installer=person("u_admin"),
        installer_reach=admit(
            EntitlementSet(principal_id="u_admin", grants=GRANTS["u_admin"]),
            Channel.CONSOLE,
            Assurance.STRONG,
        ),
    )

    assert body["name"] == TEMPLATE.name
    assert (body["runs_as"], body["runs_as_name"]) == ("u_admin", "Person u_admin")
    assert body["schedule"] == TEMPLATE.cadence.words()
    assert body["starts_paused"] is True
    assert body["paused_because"] == IT_STARTS_PAUSED
    assert body["reach"] == ["read:client.name"]
    assert body["confirmation"] == expected.confirmation


def test_a_preview_is_refused_without_the_authority_exactly_as_a_missing_agent_is(
    client: TestClient,
) -> None:
    """Delete this and a reader who may not install can fetch the confirmation digest, or learn
    from a different refusal which agents exist."""
    missing = refusal(preview_of(client, "u_admin", "no_such_agent"))

    assert refusal(preview_of(client, "u_narrow")) == missing
    assert refusal(preview_of(client, "u_wide")) == missing
    assert refusal(preview_of(client, "u_admin", AGENT, "no_such_template")) == missing
    assert refusal(preview_of(client, "u_elsewhere", WEB_AGENT)) == missing


# ------------------------------------------------------------------ the install


def test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context(
    client: TestClient, installs: Installs
) -> None:
    """M39.6.1.3's one-step install through HTTP. One row, running as the installer, paused, with
    its registry entry; the store handed the reach's digest the trigger records; and the gallery
    then marks the card with it. Delete this and every refusal below is satisfied by a route that
    installs nothing."""
    body = confirmed(client, "u_admin")

    answer = install_as(client, "u_admin", body)

    assert answer.status_code == 201, answer.text
    made = answer.json()
    [(automation_id, row)] = installs.rows.items()
    assert made["automation_id"] == automation_id == row.automation.automation_id
    assert (made["runs_as"], made["next_run_at"]) == ("u_admin", None)
    assert made["registry"] == {
        "automation_id": automation_id,
        "agent_id": AGENT,
        "task": TEMPLATE.task,
        "runs_as_id": "u_admin",
        "next_run_at": None,
        "guards": TEMPLATE.guards,
    }
    [call] = [one for one in installs.calls if "install" in one]
    admitted = admit(
        EntitlementSet(principal_id="u_admin", grants=GRANTS["u_admin"]),
        Channel.CONSOLE,
        Assurance.STRONG,
    )
    assert call["ent_hash"] == admitted.ent_hash()
    marked = {
        one["template_id"]: one["installed_as"]
        for one in gallery_of(client, "u_admin").json()["items"]
    }
    assert marked[TEMPLATE.template_id] == automation_id


def test_an_install_whose_confirmation_does_not_match_is_refused_and_writes_nothing(
    client: TestClient, installs: Installs
) -> None:
    """The server-side confirmation refusal. A well-formed digest that is not what would be
    installed now is a 409 saying to look again. Delete this and a request that never saw the
    preview installs."""
    answer = install_as(
        client, "u_admin", {"template_id": TEMPLATE.template_id, "confirmation": "0" * 64}
    )

    assert answer.status_code == 409, answer.text
    assert answer.json()["outcome"] == routes.UNCONFIRMED
    assert answer.json()["sentence"] == routes.LOOK_AGAIN
    assert installs.rows == {}


def test_an_install_with_no_confirmation_at_all_never_reaches_the_store(
    client: TestClient, installs: Installs
) -> None:
    """Delete this and `confirmation` can be made optional, and the browser becomes the only place
    a confirmation is asked for."""
    for body in (
        {"template_id": TEMPLATE.template_id},
        {"template_id": TEMPLATE.template_id, "confirmation": "yes"},
    ):
        answer = install_as(client, "u_admin", body)
        assert answer.status_code == 422, answer.text
    assert installs.calls == []


def test_a_confirmation_that_went_stale_is_refused(
    client: TestClient, agents: Agents, installs: Installs
) -> None:
    """The agent's ceiling narrowed between the preview and the press. Delete this and the person
    confirms one reach and the install is written at another."""
    body = confirmed(client, "u_admin")
    agents.held[AGENT] = an_agent(AGENT, "read:invoice.total")

    answer = install_as(client, "u_admin", body)

    assert answer.status_code == 409 and answer.json()["outcome"] == routes.UNCONFIRMED
    assert installs.rows == {}


def test_installing_twice_is_told_the_first_and_writes_nothing_more(
    client: TestClient, installs: Installs
) -> None:
    """Delete this and a double press installs two automations silently."""
    body = confirmed(client, "u_admin")
    first = install_as(client, "u_admin", body)

    second = install_as(client, "u_admin", confirmed(client, "u_admin"))

    assert first.status_code == 201
    assert second.status_code == 409, second.text
    # The sentence a failure carries is the document's own, and its reference is the header's:
    # see `brain.api.A_DOCUMENT_A_ROUTE_WROTE_STILL_CARRIES_THE_TWO_FIELDS_EVERY_FAILURE_DOES`.
    assert second.json() == {
        "outcome": routes.ALREADY_INSTALLED,
        "sentence": routes.ALREADY_YOURS,
        "automation_id": first.json()["automation_id"],
        "message": routes.ALREADY_YOURS,
        "trace_id": second.headers["x-trace-id"],
    }
    assert len(installs.rows) == 1


def test_an_install_without_the_authority_over_this_agent_is_refused_as_a_missing_agent_is(
    client: TestClient, installs: Installs
) -> None:
    """The capability check through HTTP: no authority, an authority for another agent, the tab
    refused, and an agent outside the audience, each the one 404 and each writing nothing. Delete
    this and an install is admitted by the gallery read alone."""
    body = {"template_id": TEMPLATE.template_id, "confirmation": "a" * 64}
    missing = refusal(install_as(client, "u_admin", body, "no_such_agent"))

    for pid, agent in (
        ("u_narrow", AGENT),
        ("u_wide", AGENT),
        ("u_prefix", AGENT),
        ("u_none", AGENT),
        ("u_elsewhere", WEB_AGENT),
    ):
        assert refusal(install_as(client, pid, body, agent)) == missing, pid
    assert installs.calls == []


def test_a_session_without_a_second_factor_cannot_install_and_the_same_person_with_one_can(
    client: TestClient, installs: Installs
) -> None:
    """`brain.gate.admission` withholds `admin:` from a password-only session, which is told what
    its sign-in lacks identically for this agent and for one that does not exist. Delete this and
    the authority can be renamed to a verb such a session carries."""
    body = confirmed(client, "u_admin")

    weak = install_as(client, "u_admin", body, strong=False)
    strong = install_as(client, "u_admin", body)

    missing = install_as(client, "u_admin", body, "no_such_agent", strong=False)
    assert refusal(weak) == refusal(missing)
    assert refusal(weak)["message"] == SECOND_FACTOR_NEEDED_MESSAGE
    assert strong.status_code == 201, strong.text
    assert len(installs.rows) == 1


def test_an_authority_scoped_to_this_agent_installs_here(
    client: TestClient, installs: Installs
) -> None:
    """The sibling of the scoped refusal: a grant written for one agent is enough for that agent.
    Delete this and the scope check can refuse every scoped grant, which passes every refusal."""
    original = GRANTS["u_wide"]
    GRANTS["u_wide"] = (
        grant(TAB_READ),
        grant(CONFIGURATION),
        grant(AUTOMATION_AUTHORITY, on_agent(AGENT)),
    )
    try:
        answer = install_as(client, "u_wide", confirmed(client, "u_wide"))
    finally:
        GRANTS["u_wide"] = original

    assert answer.status_code == 201, answer.text
    assert answer.json()["runs_as"] == "u_wide"
