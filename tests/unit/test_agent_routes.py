"""The agent roster and one agent's workspace over HTTP: who is listed, who is refused, and
that the two refusals are one.

Driven through the real application. The token machinery and the key source are imported
from `tests/unit/test_api_routes.py`, for the reason `tests/unit/test_routing_routes.py`
gives about the same borrowing. The directory is this file's own, because what is under test
here is an audience, and an audience is decided by a person's department, which that file's
directory gives everybody the same value of.

**The database is a stub session that answers by statement, and the statements are asserted
compiled.** The stub reads which agent a statement asked for off its WHERE clause and answers
from a dictionary, so it proves the routes' decisions and never the SQL; `test_the_statements_
ask_for_the_agent_named_and_join_the_pin_on_both_halves` is the half a stub cannot reach.

**Every refusal is compared body to body and status to status with the case it must be
indistinguishable from**, and has a sibling proving the permitted case is answered. A
function refusing everybody would satisfy every refusal here and none of the siblings.

**Installs are made by `publish` and `install`, never assembled.** The rows a route reads
are written from the domain objects a real install produces, so the loader is tested against
what the application writes rather than against a dictionary written to suit it.

Task ids: M39.1.2.5
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain import agent_routes
from brain.agent_routes import (
    MAX_ROSTER_ENTRIES,
    POPULATED_HERE,
    RosterPage,
    WorkspaceView,
    every_agent,
    gallery,
    install_for,
    install_of,
    manifest_of,
    one_agent,
    record_of,
    roster,
)
from brain.agents.catalogue import CATALOGUE
from brain.agents.model import AgentAudience, AgentViewer
from brain.agents.template import (
    ManifestIdentity,
    SignedManifest,
    SkillRef,
    TemplateInstance,
    TemplateManifest,
    install,
    materialise,
    publish,
)
from brain.api import API_PREFIX, Page
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.agent_tabs import rendering_profile
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import TABS, Tab, intersections_in, tab
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.errors import Absent
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import TrafficClass
from brain.identity.bearer import TokenAuthority
from brain.knowledge.visibility import Visibility
from brain.models.routing import DEFAULT_TIER
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, hidden_count_fields
from brain.tables.agent import AgentRow
from brain.tables.spend import SpendActualRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tools.registry import ToolRegistry
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

AGENTS = f"{API_PREFIX}/agents"
TEMPLATES = f"{API_PREFIX}/agent-templates"

#: A PostgreSQL dialect to compile statements against, taken from an engine that never
#: connects, as `tests/unit/test_api_routes.py` does for the same reason.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far outside any plausible wall clock, for the reason CLAUDE.md gives about fixtures that
#: are clocks: nothing here is about the present.
SIGNED_AT = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
INSTALLED_AT = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)
KEY = "a-key-for-this-test"

#: Who each signed-in person is. `u_narrow` sits in web, `u_wide` in sales, and `u_none` in
#: no department at all, which is the person a department audience must never match by
#: omission.
DEPARTMENTS: Mapping[str, str | None] = {
    "u_narrow": "web",
    "u_wide": "sales",
    "u_prefix": "web",
    "u_none": None,
    "u_admin": "web",
    "u_elsewhere": "finance",
}

#: What each person holds. `u_admin` may read the Settings tab: the tab's own capability and
#: the configuration plane the console adds. `u_prefix` holds the tab's capability without
#: the plane, which `brain.console.reads.permitted` refuses. `u_elsewhere` holds every tab's
#: capability and every plane, so every tab is permitted to them and what narrows their strip
#: is only what the route marks populated. Everybody else holds nothing an agent's workspace
#: reads, and every one of them is still an audience member somewhere.
SETTINGS_READ = tab(Tab.SETTINGS).read.requires

#: The three reads `u_elsewhere` holds beyond every tab's, each because one block of the
#: workspace is behind a screen no tab names: the skills, the figures on the front page, and
#: the rows of the one entity the stand-in tool registry below reads. Held by one person, so
#: that every test of a narrower reader has somebody to be narrower than.
ENTITY = "invoice"
SOURCE = "ledger"
SKILLS_READ = screen("skills").read.requires
BUDGET_READ = screen("budget").read.requires
WIDEST_READS = (SKILLS_READ, BUDGET_READ, Capability(value=f"read:{ENTITY}"))
EVERY_TAB_AND_PLANE = sorted(
    {*(one.read.requires for one in TABS), *(plane_capability(plane) for plane in Plane)},
    key=lambda capability: capability.value,
)
# A dict rather than a Mapping, because one test widens a person's grants for its own length
# and puts them back in a `finally`.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_narrow": (),
    "u_wide": (),
    "u_prefix": (Grant(capability=SETTINGS_READ, scope=Scope.unrestricted()),),
    "u_none": (),
    "u_admin": (
        Grant(capability=SETTINGS_READ, scope=Scope.unrestricted()),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=Scope.unrestricted()),
    ),
    "u_elsewhere": tuple(
        Grant(capability=capability, scope=Scope.unrestricted())
        for capability in (*EVERY_TAB_AND_PLANE, *WIDEST_READS)
    ),
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
    """A `PrincipalDirectory` whose people sit in different departments."""

    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return person(pid)
        return None


class Store:
    """A `brain.gate.resolve.EntitlementStore` over `GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


# ------------------------------------------------------------------------------ rows


def agent_row(
    agent_id: str,
    *,
    level: Visibility = Visibility.COMPANY,
    owner_id: str = "u_steward",
    department: str | None = None,
    display_name: str | None = None,
    persona: str = "Answer briefly.",
    allowed_tools: tuple[str, ...] = (),
    capabilities: tuple[Capability, ...] = (),
) -> AgentRow:
    return AgentRow(
        id=agent_id,
        display_name=display_name or agent_id.replace("_", " ").title(),
        persona=persona,
        tier=DEFAULT_TIER.value,
        visibility=level.value,
        owner_id=owner_id,
        department=department,
        scope=Scope.unrestricted().model_dump(),
        capabilities=[one.value for one in capabilities],
        allowed_tools=list(allowed_tools),
        required_tools=[],
        max_side_effect=SideEffect.NONE.value,
        created_by="u_builder",
        disabled_at=None,
        archived_at=None,
    )


SUMMARY = "Drafts a first answer to a pricing question."


def manifest(
    template_id: str = "pricing_desk",
    *,
    summary: str = SUMMARY,
    version: int = 3,
    display_name: str = "Pricing desk",
    skills: tuple[SkillRef, ...] = (),
    connectors: tuple[str, ...] = (),
) -> TemplateManifest:
    return TemplateManifest(
        identity=ManifestIdentity(
            template_id=template_id,
            version=version,
            published_by="u_publisher",
            display_name=display_name,
            summary=summary,
        ),
        persona="Answer briefly.",
        skills=skills,
        connectors=connectors,
    )


def install_rows(
    agent_id: str,
    *,
    overlay: Mapping[str, Any] | None = None,
    summary: str = SUMMARY,
    skills: tuple[SkillRef, ...] = (),
    connectors: tuple[str, ...] = (),
) -> tuple[TemplateInstanceRow, TemplateVersionRow, SignedManifest, TemplateInstance]:
    """The two rows an install writes, from a real publish and a real install."""
    signed = publish(
        manifest(summary=summary, skills=skills, connectors=connectors),
        key=KEY,
        signed_by="u_publisher",
        at=SIGNED_AT,
    )
    instance = install(
        signed,
        key=KEY,
        instance_id=agent_id,
        created_by="u_installer",
        at=INSTALLED_AT,
        overlay=dict(overlay or {"persona": "Answer briefly and name the price list."}),
    )
    effective = materialise(
        signed, instance, audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward")
    )
    version_row = TemplateVersionRow(
        template_id=signed.manifest.identity.template_id,
        version=signed.manifest.identity.version,
        content_digest=signed.content_digest,
        signature=signed.signature,
        signed_by=signed.signed_by,
        signed_at=signed.signed_at,
        document=signed.manifest.document(),
    )
    instance_row = TemplateInstanceRow(
        id=instance.instance_id,
        template_id=instance.template_id,
        template_version=instance.template_version,
        content_digest=instance.content_digest,
        overlay=dict(instance.overlay),
        field_owners={
            path: owner.model_dump(mode="json") for path, owner in instance.overlay_owners.items()
        },
        effective_document=dict(effective.document),
        effective_hash=effective.config_hash,
        created_by=instance.created_by,
    )
    return instance_row, version_row, signed, instance


# ------------------------------------------------------------------- the stub session


class Stored:
    """What the stub database holds, and every statement it was asked."""

    def __init__(self) -> None:
        self.agents: dict[str, AgentRow] = {}
        self.installs: dict[str, tuple[TemplateInstanceRow, TemplateVersionRow]] = {}
        self.spend: list[SpendActualRow] = []
        self.versions: list[TemplateVersionRow] = []
        self.statements: list[Any] = []


_STORED = Stored()


class StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


def _asked_for(statement: Any) -> str:
    """The agent id a statement's WHERE clause names. Every single-agent statement has one."""
    return str(statement.whereclause.right.value)


class StubSession(AsyncSession):
    """An `AsyncSession` that answers the five statements this router makes, and no other.

    Dispatched on the table each statement selects from rather than on how many columns it
    describes, which is what the install join used to be told apart by: the spend statement
    and the gallery's both describe one column, so counting them would have sent an agent row
    back where a cost was asked for and the route would have failed on the shape rather than
    on the decision under test.
    """

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        _STORED.statements.append(statement)
        described = statement.column_descriptions
        if len(described) == 2:
            pair = _STORED.installs.get(_asked_for(statement))
            return StubResult([pair] if pair is not None else [])
        entity = described[0]["entity"]
        if entity is SpendActualRow:
            return StubResult(list(_STORED.spend))
        if entity is TemplateVersionRow:
            return StubResult(list(_STORED.versions))
        if statement.whereclause is None:
            return StubResult([_STORED.agents[key] for key in sorted(_STORED.agents)])
        row = _STORED.agents.get(_asked_for(statement))
        return StubResult([row] if row is not None else [])

    async def close(self) -> None:
        return None


@pytest.fixture
def stored() -> Iterator[Stored]:
    """A fresh store per test, so one test's rows are never another's evidence."""
    global _STORED
    _STORED = Stored()
    yield _STORED


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
def client(stored: Stored) -> Iterator[TestClient]:
    """The real application, its router registration included, with the stub where the pool is."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        yield c


def app_of(c: TestClient) -> FastAPI:
    """The application behind a client, typed as one.

    A cast at the library boundary: `TestClient.app` is declared as any ASGI callable, and the
    `client` fixture above always builds it from `create_app`, so proving the match buys nothing.
    """
    return cast(FastAPI, c.app)


def get(c: TestClient, pid: str, path: str) -> Response:
    response: Response = c.get(path, headers={"authorization": f"Bearer {token_for(pid)}"})
    return response


def workspace_of(c: TestClient, pid: str, agent_id: str) -> Response:
    return get(c, pid, f"{AGENTS}/{agent_id}/workspace")


def listed(c: TestClient, pid: str) -> list[str]:
    response = get(c, pid, AGENTS)
    assert response.status_code == 200, response.text
    return [one["agent_id"] for one in response.json()["items"]]


# ------------------------------------------------------------------------ the roster


def test_the_roster_lists_the_agents_the_callers_audience_covers(
    client: TestClient, stored: Stored
) -> None:
    """The positive case for every refusal below: a company agent, the caller's own personal
    agent and their department's agent are all listed, by name.

    Delete this and every roster refusal is satisfied by a route that lists nothing."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.agents["my_notes"] = agent_row(
        "my_notes", level=Visibility.PERSONAL, owner_id="u_narrow"
    )
    stored.agents["web_helper"] = agent_row(
        "web_helper", level=Visibility.DEPARTMENT, department="web"
    )

    response = get(client, "u_narrow", AGENTS)

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "agent_id": "company_desk",
            "display_name": "Company Desk",
            "owner_id": "u_steward",
            "department": None,
            "ceiling": None,
        },
        {
            "agent_id": "my_notes",
            "display_name": "My Notes",
            "owner_id": "u_narrow",
            "department": None,
            "ceiling": None,
        },
        {
            "agent_id": "web_helper",
            "display_name": "Web Helper",
            "owner_id": "u_steward",
            "department": "web",
            "ceiling": None,
        },
    ]


def test_the_ceiling_column_is_sent_to_a_reader_of_the_agents_screen_and_to_nobody_else(
    client: TestClient, stored: Stored
) -> None:
    """SCREEN 4's ceiling column is a scope predicate, so it travels for a reader holding the
    Agents screen's read and the configuration plane, and the same rows carry a null ceiling
    for a reader who only sits in the audience. Every other column is the same for both.

    Delete this and the widest reach any run of an agent could have is published to everybody
    the audience covers, or the column disappears for the administrator it was drawn for."""
    stored.agents["web_helper"] = agent_row(
        "web_helper", level=Visibility.DEPARTMENT, department="web"
    )
    narrow = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
    stored.agents["web_helper"].scope = narrow.model_dump(mode="json")

    admin = get(client, "u_admin", AGENTS).json()["items"]
    member = get(client, "u_narrow", AGENTS).json()["items"]

    assert admin[0]["ceiling"] == narrow.model_dump(mode="json")
    assert member[0]["ceiling"] is None
    assert {k: v for k, v in admin[0].items() if k != "ceiling"} == {
        k: v for k, v in member[0].items() if k != "ceiling"
    }


def test_an_agent_outside_the_audience_is_absent_from_the_roster_rather_than_marked(
    client: TestClient, stored: Stored
) -> None:
    """Somebody else's personal agent and another department's agent are simply not in the
    list, and the answer is byte for byte the answer to a table that never held them.

    Delete this and the roster can grey out what it hides, which is a list of the teams and
    projects the reader was not told about."""
    stored.agents["company_desk"] = agent_row("company_desk")
    without = get(client, "u_narrow", AGENTS)

    stored.agents["their_notes"] = agent_row(
        "their_notes", level=Visibility.PERSONAL, owner_id="u_wide"
    )
    stored.agents["sales_helper"] = agent_row(
        "sales_helper", level=Visibility.DEPARTMENT, department="sales"
    )
    with_hidden = get(client, "u_narrow", AGENTS)

    assert with_hidden.status_code == without.status_code == 200
    assert with_hidden.content == without.content
    # And the same rows are listed for the people they belong to, so the refusal above is an
    # audience decision rather than a row nobody can see.
    assert listed(client, "u_wide") == ["company_desk", "sales_helper", "their_notes"]


def test_a_person_with_no_department_is_not_matched_by_a_department_audience(
    client: TestClient, stored: Stored
) -> None:
    """A department audience is a predicate on a department field, and a viewer with none must
    not satisfy it by leaving the field out.

    Delete this and the narrowest thing a person can be, in no department, becomes the widest
    audience a department agent can have."""
    stored.agents["web_helper"] = agent_row(
        "web_helper", level=Visibility.DEPARTMENT, department="web"
    )

    assert listed(client, "u_none") == []
    assert listed(client, "u_narrow") == ["web_helper"]


def test_no_roster_answer_carries_a_count_of_anything(client: TestClient, stored: Stored) -> None:
    """`total` is inherited from `Page` and is never set, and no field of the entry or the page
    is one `brain.ops.jobs` names as a hidden count.

    Delete this and "showing 3 of 47" arrives as a helpful field, which is 44 facts the reader
    did not have."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.agents["their_notes"] = agent_row(
        "their_notes", level=Visibility.PERSONAL, owner_id="u_wide"
    )

    body = get(client, "u_narrow", AGENTS).json()

    assert body["total"] is None
    assert set(body) == {"items", "next_cursor", "total", "truncated"}
    assert set(body["items"][0]) == {
        "agent_id",
        "display_name",
        "owner_id",
        "department",
        "ceiling",
    }
    assert hidden_count_fields((agent_routes.RosterEntry, RosterPage, WorkspaceView)) == ()
    # And asked of the pydantic models themselves, because `hidden_count_fields` reads
    # `__dataclass_fields__` and a `BaseModel` has none, so the line above is a check about
    # dataclasses and every view on this router is a model. `total` is declared on `Page`,
    # inherited by both listings and asserted null above, so it is the one name allowed.
    for view in (
        agent_routes.RosterEntry,
        agent_routes.AgentHeaderView,
        WorkspaceView,
        agent_routes.SkillView,
        agent_routes.ConnectorView,
        agent_routes.ConnectorStripView,
        agent_routes.ChannelView,
        agent_routes.HeadlineView,
        agent_routes.TemplateEntry,
    ):
        assert not set(view.model_fields) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, view.__name__


def test_the_roster_is_bounded_after_the_audience_filter_and_says_only_that_there_is_more() -> None:
    """Hidden agents ahead of the visible ones in the table do not use up the page, and a page
    over the bound says it is truncated without saying by how much.

    Delete this and the bound can move in front of the filter, where a short page says that
    rows were removed."""
    viewer = AgentViewer(principal_id="u_narrow", departments=frozenset({"web"}))
    hidden = [
        record_of(agent_row(f"a_hidden_{n}", level=Visibility.PERSONAL, owner_id="u_wide"))
        for n in range(MAX_ROSTER_ENTRIES)
    ]
    visible = [record_of(agent_row(f"z_visible_{n}")) for n in range(MAX_ROSTER_ENTRIES)]
    records = [one for one in (*hidden, *visible) if one is not None]

    full = roster(records, viewer)
    assert len(full.items) == MAX_ROSTER_ENTRIES
    assert all(one.agent_id.startswith("z_visible_") for one in full.items)
    assert full.truncated is False
    assert full.total is None

    extra = record_of(agent_row("z_visible_extra"))
    assert extra is not None
    over = roster([*records, extra], viewer)
    assert len(over.items) == MAX_ROSTER_ENTRIES
    assert over.truncated is True
    assert over.total is None


def test_a_row_that_does_not_construct_is_absent_from_every_roster_and_takes_nothing_down(
    client: TestClient, stored: Stored
) -> None:
    """A stored agent whose required tool is outside its allowed set fails its record's own
    validator, and the roster lists everything else rather than answering 500.

    Delete this and one bad row is an outage of the roster for every person at once."""
    stored.agents["company_desk"] = agent_row("company_desk")
    broken = agent_row("broken_desk")
    broken.required_tools = ["a_tool_nothing_allows"]
    stored.agents["broken_desk"] = broken

    assert listed(client, "u_narrow") == ["company_desk"]
    assert listed(client, "u_admin") == ["company_desk"]


# --------------------------------------------------------------------- the workspace


def test_a_missing_agent_and_an_agent_outside_the_audience_are_one_404_with_one_body(
    client: TestClient, stored: Stored
) -> None:
    """Asserted on status and body together. A personal agent belonging to somebody else, a
    department agent of another department, a row that does not construct, and a slug nothing
    holds all answer identically, and the sibling line proves the owner is answered.

    Delete this and the address bar enumerates the company's agents one slug at a time."""
    stored.agents["their_notes"] = agent_row(
        "their_notes", level=Visibility.PERSONAL, owner_id="u_wide"
    )
    stored.agents["sales_helper"] = agent_row(
        "sales_helper", level=Visibility.DEPARTMENT, department="sales"
    )
    broken = agent_row("broken_desk")
    broken.required_tools = ["a_tool_nothing_allows"]
    stored.agents["broken_desk"] = broken

    missing = workspace_of(client, "u_narrow", "nothing_here")
    refusals = [
        workspace_of(client, "u_narrow", "their_notes"),
        workspace_of(client, "u_narrow", "sales_helper"),
        workspace_of(client, "u_narrow", "broken_desk"),
    ]

    assert missing.status_code == 404
    assert missing.json()["message"] == Absent.public_message
    for refused in refusals:
        assert refused.status_code == missing.status_code
        assert {k: v for k, v in refused.json().items() if k != "trace_id"} == {
            k: v for k, v in missing.json().items() if k != "trace_id"
        }

    assert workspace_of(client, "u_wide", "their_notes").status_code == 200
    assert workspace_of(client, "u_wide", "sales_helper").status_code == 200


def test_an_agent_the_roster_lists_is_an_agent_whose_workspace_opens_and_no_other(
    client: TestClient, stored: Stored
) -> None:
    """The roster and the workspace answer the audience question with the same predicate, so
    for every person the ids listed are exactly the ids that open.

    Delete this and a person can find an agent they cannot open, or open one no list shows
    them, which is two surfaces disagreeing about who may see the same thing."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.agents["my_notes"] = agent_row(
        "my_notes", level=Visibility.PERSONAL, owner_id="u_narrow"
    )
    stored.agents["their_notes"] = agent_row(
        "their_notes", level=Visibility.PERSONAL, owner_id="u_wide"
    )
    stored.agents["web_helper"] = agent_row(
        "web_helper", level=Visibility.DEPARTMENT, department="web"
    )
    stored.agents["sales_helper"] = agent_row(
        "sales_helper", level=Visibility.DEPARTMENT, department="sales"
    )

    for pid in DEPARTMENTS:
        opens = sorted(
            agent_id
            for agent_id in stored.agents
            if workspace_of(client, pid, agent_id).status_code == 200
        )
        assert listed(client, pid) == opens, pid
    assert listed(client, "u_narrow") == ["company_desk", "my_notes", "web_helper"]


def test_the_install_of_an_agent_the_caller_may_not_see_is_never_read(
    client: TestClient, stored: Stored
) -> None:
    """The audience is decided before the install is fetched, so nothing about a hidden agent
    is read on the caller's behalf. The sibling proves a visible agent's install is read.

    Delete this and a refusal can come after a query against another person's agent, which is
    a read made for somebody who was never entitled to it."""
    stored.agents["their_notes"] = agent_row(
        "their_notes", level=Visibility.PERSONAL, owner_id="u_wide"
    )
    instance_row, version_row, _, _ = install_rows("their_notes")
    stored.installs["their_notes"] = (instance_row, version_row)

    def tables() -> list[str]:
        return [str(one.column_descriptions[-1]["entity"].__name__) for one in stored.statements]

    assert workspace_of(client, "u_narrow", "their_notes").status_code == 404
    assert tables() == ["AgentRow"]

    stored.statements.clear()
    assert workspace_of(client, "u_wide", "their_notes").status_code == 200
    assert tables() == ["AgentRow", "TemplateVersionRow", "SpendActualRow"]


def test_the_header_is_the_agent_its_steward_and_its_lineage_whoever_may_open_it(
    client: TestClient, stored: Stored
) -> None:
    """Every field the console's header reads, under the names it reads them by, for a reader
    holding nothing but a place in the audience.

    Delete this and the route can drop the owner or send half a lineage, and the page renders
    an agent with a fact silently missing."""
    stored.agents["quote_helper"] = agent_row("quote_helper", display_name="Quote Helper")
    instance_row, version_row, _, _ = install_rows("quote_helper")
    stored.installs["quote_helper"] = (instance_row, version_row)

    body = workspace_of(client, "u_narrow", "quote_helper").json()

    assert body["agent"] == {
        "agent_id": "quote_helper",
        "display_name": "Quote Helper",
        "owner_id": "u_steward",
        "summary": "Drafts a first answer to a pricing question.",
        "template_id": "pricing_desk",
        "template_version": 3,
        "created_by": None,
    }


def test_the_owner_on_the_header_is_the_steward_and_never_the_builder(
    client: TestClient, stored: Stored
) -> None:
    """`created_by` and `owner_id` differ on this row, and the steward is the one under
    `owner_id` for every reader. The builder reaches a reader of the Settings tab under its
    own name, and reaches an audience member not at all.

    Delete this and a fallback puts the name of somebody who handed the agent on where the
    person who answers for it goes, or the builder is published to everybody the audience
    covers."""
    stored.agents["quote_helper"] = agent_row("quote_helper", owner_id="u_current")

    member = workspace_of(client, "u_narrow", "quote_helper")
    admin = workspace_of(client, "u_admin", "quote_helper")

    assert member.json()["agent"]["owner_id"] == "u_current"
    assert admin.json()["agent"]["owner_id"] == "u_current"
    assert member.json()["agent"]["created_by"] is None
    assert "u_builder" not in member.text
    assert admin.json()["agent"]["created_by"] == "u_builder"


def test_the_strip_is_the_settings_tab_for_a_reader_who_may_read_it_and_empty_otherwise(
    client: TestClient, stored: Stored
) -> None:
    """The strip is `tab_strip` at the caller's reach with only Settings populated: the reader
    holding the tab's capability and the configuration plane sees Settings, a reader holding
    the capability without the plane sees nothing, and so does a reader holding neither.

    Delete this and the strip can draw tabs over panels nothing fills, or skip the plane check
    `brain.console.reads.permitted` adds to a tool's own capability."""
    stored.agents["quote_helper"] = agent_row("quote_helper")

    assert workspace_of(client, "u_admin", "quote_helper").json()["tabs"] == [
        {"tab": "settings", "label": "Settings", "purpose": tab(Tab.SETTINGS).purpose}
    ]
    assert workspace_of(client, "u_prefix", "quote_helper").json()["tabs"] == []
    assert workspace_of(client, "u_narrow", "quote_helper").json()["tabs"] == []


def test_a_reader_holding_every_tabs_grant_is_shown_only_the_tab_this_route_fills(
    client: TestClient, stored: Stored
) -> None:
    """`u_elsewhere` holds every tab's capability and every plane, so every tab is permitted to
    them, and their strip is still Settings alone because it is the only tab populated. The
    strip test above is the sibling for the readers who may not read even that.

    Delete this and the route can mark a tab populated that it holds nothing for, which draws a
    heading over an empty panel for exactly the readers trusted with the most."""
    stored.agents["quote_helper"] = agent_row("quote_helper")

    tabs = workspace_of(client, "u_elsewhere", "quote_helper").json()["tabs"]

    assert [one["tab"] for one in tabs] == ["settings"]


def test_a_blank_summary_is_sent_as_no_summary_and_the_lineage_still_arrives(
    client: TestClient, stored: Stored
) -> None:
    """A template published with no summary gives a header whose summary is null, beside a
    lineage that is still sent. The header test above is the sibling with a summary.

    Delete this and the API sends an empty string where it means no summary, which every
    consumer but this console has to know to read as absent."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    instance_row, version_row, _, _ = install_rows("quote_helper", summary="")
    stored.installs["quote_helper"] = (instance_row, version_row)

    agent = workspace_of(client, "u_narrow", "quote_helper").json()["agent"]

    assert agent["summary"] is None
    assert (agent["template_id"], agent["template_version"]) == ("pricing_desk", 3)


def test_the_roster_is_ordered_by_name_and_then_by_id_whatever_order_the_table_holds() -> None:
    """Two agents share a name and a third sorts first by id and last by name, and the roster
    is the same list read forwards and backwards.

    Delete this and the order can follow the table, which follows creation, and a list whose
    order moves when nothing in it changed reads as agents having come and gone."""
    viewer = AgentViewer(principal_id="u_narrow", departments=frozenset())
    records = [
        one
        for one in (
            record_of(agent_row("a_zulu", display_name="Zulu")),
            record_of(agent_row("c_alpha", display_name="Alpha")),
            record_of(agent_row("b_alpha", display_name="Alpha")),
        )
        if one is not None
    ]

    expected = ["b_alpha", "c_alpha", "a_zulu"]
    assert [one.agent_id for one in roster(records, viewer).items] == expected
    assert [one.agent_id for one in roster(records[::-1], viewer).items] == expected


def test_a_tab_is_populated_here_only_when_this_route_holds_what_it_reads() -> None:
    """Settings and nothing else, held against the strip itself: every tab is permitted for a
    reader holding every tab's grant, and still only Settings is drawn.

    Delete this and `POPULATED_HERE` can grow a tab no route fills, which is a heading over an
    empty panel and a count of hidden things in words."""
    everything = EntitlementSet(
        principal_id="u_all",
        grants=tuple(
            Grant(capability=capability, scope=Scope.unrestricted())
            for capability in {
                *(one.read.requires for one in TABS),
                *(plane_capability(plane) for plane in Plane),
            }
        ),
    )
    from brain.console.workspace import tab_strip

    assert len(tab_strip(everything, populated=tuple(Tab))) == len(TABS)
    assert frozenset({Tab.SETTINGS}) == POPULATED_HERE
    assert [one.tab for one in tab_strip(everything, populated=POPULATED_HERE)] == [Tab.SETTINGS]


def test_the_composition_is_sent_to_a_reader_of_the_settings_tab_and_to_nobody_else(
    client: TestClient, stored: Stored
) -> None:
    """The persona is prompt material, so the rows travel exactly when the strip holds
    Settings. For a reader who may not read it the answer is the answer for an agent with no
    install at all, and the persona is nowhere in the body.

    Delete this and every audience member reads every agent's instructions."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    stored.agents["bare_helper"] = agent_row("bare_helper")
    instance_row, version_row, _, _ = install_rows("quote_helper")
    stored.installs["quote_helper"] = (instance_row, version_row)

    admin = workspace_of(client, "u_admin", "quote_helper").json()
    paths = [row["path"] for row in admin["composition"]]
    assert "persona" in paths
    persona = next(row for row in admin["composition"] if row["path"] == "persona")
    assert persona["instance"] == '"Answer briefly and name the price list."'
    assert persona["template"] == '"Answer briefly."'
    assert persona["source"] == "instance"
    assert "set_by" not in persona

    member = workspace_of(client, "u_narrow", "quote_helper")
    assert member.json()["composition"] == []
    assert (
        member.json()["composition"]
        == workspace_of(client, "u_narrow", "bare_helper").json()["composition"]
    )
    assert "name the price list" not in member.text


def test_an_install_read_back_from_its_rows_is_the_install_that_was_written() -> None:
    """The loader rebuilds the manifest from the flat document and `SignedManifest` recomputes
    the digest, so a reconstruction that moved a value cannot load. The composition it gives
    is the one the domain objects give directly.

    Delete this and the rows can be read back into a different manifest from the one that was
    signed, and the diff would describe an agent nobody installed."""
    from brain.console.workspace import composition_rows

    instance_row, version_row, signed, instance = install_rows("quote_helper")
    record = record_of(agent_row("quote_helper"))
    assert record is not None

    rebuilt = manifest_of(version_row.document)
    assert rebuilt == signed.manifest

    loaded = install_of(instance_row, version_row, record)
    assert loaded is not None
    expected = composition_rows(signed, materialise(signed, instance, audience=record.audience))
    assert [row.model_dump() for row in loaded.composition] == [one.wire() for one in expected]
    assert (loaded.template_id, loaded.template_version) == ("pricing_desk", 3)


@pytest.mark.parametrize(
    "spoil",
    [
        "a document edited after signing",
        "a document missing a path",
        "an instance pinned to another digest",
        "an overlay with no owner",
    ],
)
def test_an_install_that_does_not_construct_is_an_agent_with_no_lineage_and_no_composition(
    client: TestClient, stored: Stored, spoil: str
) -> None:
    """Each way an install row can be wrong gives the header without a lineage and an empty
    composition, for the reader who may read Settings, rather than a 500. The unspoiled
    install beside it proves both are sent when the rows are sound.

    Delete this and one broken install is a status that says which agents have installs."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    instance_row, version_row, _, _ = install_rows("quote_helper")
    stored.installs["quote_helper"] = (instance_row, version_row)
    sound = workspace_of(client, "u_admin", "quote_helper").json()
    assert sound["agent"]["template_id"] == "pricing_desk"
    assert sound["composition"] != []

    if spoil == "a document edited after signing":
        version_row.document = {**version_row.document, "persona": "Say anything."}
    elif spoil == "a document missing a path":
        version_row.document = {k: v for k, v in version_row.document.items() if k != "persona"}
    elif spoil == "an instance pinned to another digest":
        instance_row.content_digest = "0" * 64
    else:
        instance_row.field_owners = {}

    spoiled = workspace_of(client, "u_admin", "quote_helper")

    assert spoiled.status_code == 200
    assert spoiled.json()["agent"] == {
        "agent_id": "quote_helper",
        "display_name": "Quote Helper",
        "owner_id": "u_steward",
        "summary": None,
        "template_id": None,
        "template_version": None,
        "created_by": "u_builder",
    }
    assert spoiled.json()["composition"] == []
    # And every block the install supplies goes with it, rather than half a workspace drawn
    # from a document that would not load.
    assert spoiled.json()["skills"] == []
    assert spoiled.json()["divergent"] == []
    assert spoiled.json()["connectors"] == {"shown": [], "overflow": 0}


def test_a_tab_view_never_carries_the_capability_its_tab_requires(
    client: TestClient, stored: Stored
) -> None:
    """`WorkspaceTab.read` names the grant a tab needs, and serialising the tab whole would
    send it. The body holds the tab's key, label and purpose and not the capability's text.

    Delete this and every workspace response is a map of which grant opens which tab."""
    stored.agents["quote_helper"] = agent_row("quote_helper")

    text = workspace_of(client, "u_admin", "quote_helper").text

    assert SETTINGS_READ.value not in text
    assert "agent_workspace." not in text
    assert set(agent_routes.TabView.model_fields) == {"tab", "label", "purpose"}


def test_a_process_with_no_database_answers_every_caller_and_every_slug_alike(
    stored: Stored,
) -> None:
    """A process-level fault, 500 for the roster and for a real or an invented agent alike, so
    the fault itself says nothing about which agents exist. The routes above are the sibling.

    Delete this and a deployment without a pool can answer a missing agent differently from a
    present one."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        answers = [
            get(c, "u_narrow", AGENTS),
            workspace_of(c, "u_narrow", "nothing_here"),
            workspace_of(c, "u_admin", "company_desk"),
        ]

    assert {one.status_code for one in answers} == {500}
    assert len({one.json()["message"] for one in answers}) == 1


# --------------------------------------------------------------------- the machinery


def test_the_statements_ask_for_the_agent_named_and_join_the_pin_on_both_halves() -> None:
    """Compiled, because the stub cannot see SQL. One agent is its primary key, every agent has
    no WHERE clause at all, and an install is joined to its version on the template and the
    version together.

    Delete this and the install join can match on the template alone, and an agent reads the
    composition of whichever version of its template the database returned first."""
    one = one_agent("quote_helper")
    assert one.whereclause is not None
    assert str(one.whereclause.compile(dialect=DIALECT)) == "agent.agent.id = %(id_1)s::VARCHAR"
    assert one.whereclause.right.value == "quote_helper"

    assert every_agent().whereclause is None

    joined = install_for("quote_helper")
    compiled = " ".join(str(joined.compile(dialect=DIALECT)).split())
    assert (
        "JOIN agent.template_version ON agent.template_version.template_id = "
        "agent.template_instance.template_id AND agent.template_version.version = "
        "agent.template_instance.template_version" in compiled
    )
    assert joined.whereclause is not None
    assert (
        str(joined.whereclause.compile(dialect=DIALECT))
        == "agent.template_instance.id = %(id_1)s::VARCHAR"
    )


def test_a_stored_agent_reads_back_as_the_record_with_its_audience_intact() -> None:
    """Every column the audience is made of reaches the record, including the department,
    which the table stores as null where the record holds an empty string.

    Delete this and a department agent can read back as a company one, which is the widest
    audience wearing the middle one's name."""
    record = record_of(
        agent_row("web_helper", level=Visibility.DEPARTMENT, department="web", owner_id="u_a")
    )
    assert record is not None
    assert record.audience == AgentAudience(
        level=Visibility.DEPARTMENT, owner_id="u_a", department="web"
    )
    personal = record_of(agent_row("my_notes", level=Visibility.PERSONAL, owner_id="u_a"))
    assert personal is not None
    assert personal.audience.department == ""


def test_the_router_intersects_no_entitlement_sets_and_asks_for_no_capability() -> None:
    """Nothing here narrows a reach, and nothing here holds a capability of its own: the one is
    `brain.console.workspace`'s rule applied to this source, and the other is the audience
    being the only answer to who may see an agent. Both parsed, not searched, so the docstring
    naming either word cannot satisfy or break the check.

    Delete this and the router can grow a third copy of the platform's intersection, or a
    `read:agent` check in front of the roster that the picker does not have."""
    source = inspect.getsource(agent_routes)
    assert intersections_in(source) == ()
    assert intersections_in("reach.intersect(ceiling)\n") == (1,)

    def holds_calls(text: str) -> list[int]:
        return [
            node.lineno
            for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "holds"
        ]

    assert holds_calls(source) == []
    assert holds_calls("asked.reach.holds(READ, now)\n") == [1]
    assert issubclass(RosterPage, Page)


# --------------------------------------------------- what the agent is assembled from


class InvoiceRow(Entity):
    """The one row shape the stand-in registry reads. Typed, because `ToolRegistry.register`
    refuses a handler whose result cannot be redacted."""

    reference: str = ""


def an_invoice() -> TypedResult[InvoiceRow]:
    return TypedResult[InvoiceRow]()


def tools_reading(source: str = SOURCE) -> ToolRegistry:
    """A registry with one row tool, bound to one source, as an install's binding leaves it.

    One tool and one entity, because what the connector strip reads off a registry is the
    source behind a tool the agent is allowed and the entity a caller may reach rows of, and
    a second tool would only make the fixture harder to read.
    """
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name=f"{SOURCE}.read_{ENTITY}",
            description="reads one invoice",
            entity=ENTITY,
            required_capability=f"read:{ENTITY}.reference",
            side_effect=SideEffect.NONE,
            identity_mode=IdentityMode.DELEGATED,
            source=source,
        ),
        an_invoice,
    )
    return registry


A_SKILL = SkillRef(name="ssl-renewal-runbook", digest="a" * 64)


def test_the_skills_on_an_agent_are_its_pinned_references_for_a_reader_of_the_skills_screen(
    client: TestClient, stored: Stored
) -> None:
    """The manifest's own `SkillRef` list, by name and by the digest the pin is over, for a
    reader holding the Skills screen's read beside the Settings tab. A reader holding the tab
    and not that screen gets an empty list, and the chip carries no review state either way.

    Delete this and a skill's name, which describes a procedure somebody wants to run,
    reaches every reader who can open the agent's configuration, or the block disappears for
    the administrator the screen was granted to."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    instance_row, version_row, _, _ = install_rows("quote_helper", skills=(A_SKILL,))
    stored.installs["quote_helper"] = (instance_row, version_row)

    wide = workspace_of(client, "u_elsewhere", "quote_helper").json()
    narrower = workspace_of(client, "u_admin", "quote_helper")

    assert wide["skills"] == [{"name": "ssl-renewal-runbook", "digest": "a" * 64}]
    assert narrower.json()["skills"] == []
    # The skills block and not the whole body: `composition_rows` answers the diff whole or
    # not at all, deliberately, so the `skills` path is a row of it for any reader of the
    # Settings tab. What this test holds is the block, which is the one place a skill is
    # listed as a thing on the agent rather than as one side of a diff.
    assert set(agent_routes.SkillView.model_fields) == {"name", "digest"}


def test_a_connector_the_agent_names_reads_as_attached_when_a_tool_of_its_source_is_allowed(
    client: TestClient, stored: Stored
) -> None:
    """The presence is read off the tools the agent's ceiling allows, which is what binding a
    connector wrote: the same manifest and the same reader give ATTACHED when the agent is
    allowed a tool of that source and REQUESTED when it is not.

    Delete this and every connector a template asks for reads as bound, which is exactly the
    row M39.2.1.4 exists to tell apart from a connector nobody granted."""
    stored.agents["bound_desk"] = agent_row(
        "bound_desk", allowed_tools=(f"{SOURCE}.read_{ENTITY}",)
    )
    stored.agents["asking_desk"] = agent_row("asking_desk")
    for agent_id in ("bound_desk", "asking_desk"):
        instance_row, version_row, _, _ = install_rows(agent_id, connectors=(SOURCE,))
        stored.installs[agent_id] = (instance_row, version_row)
    app_of(client).state.tools = tools_reading()

    attached = workspace_of(client, "u_elsewhere", "bound_desk").json()["connectors"]
    requested = workspace_of(client, "u_elsewhere", "asking_desk").json()["connectors"]

    assert attached == {"shown": [{"source": SOURCE, "presence": "attached"}], "overflow": 0}
    assert requested == {"shown": [{"source": SOURCE, "presence": "requested"}], "overflow": 0}


def test_a_connector_this_caller_could_not_reach_produces_no_row_in_either_state(
    client: TestClient, stored: Stored
) -> None:
    """A source the caller holds no row grant for is absent from the strip rather than shown
    as requested, and a connector no registered tool reads is absent for everybody. The reader
    who holds the grant is the sibling that proves the row exists at all.

    Delete this and a row reading requested tells somebody the source is installed here and
    that they may not reach it, which is two facts they did not have."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    instance_row, version_row, _, _ = install_rows("quote_helper", connectors=(SOURCE, "atlas"))
    stored.installs["quote_helper"] = (instance_row, version_row)
    app_of(client).state.tools = tools_reading()

    wide = workspace_of(client, "u_elsewhere", "quote_helper")
    narrower = workspace_of(client, "u_admin", "quote_helper")

    assert [one["source"] for one in wide.json()["connectors"]["shown"]] == [SOURCE]
    assert narrower.json()["connectors"] == {"shown": [], "overflow": 0}
    assert [one["source"] for one in narrower.json()["connectors"]["shown"]] == []
    # The strip and not the whole body, for the reason the skills test gives about the same
    # overlap: the `connectors` path is one row of a composition diff that is answered whole
    # or not at all, so a reader of the Settings tab sees the names there. What the strip
    # decides is which of them this caller may be shown as a connector on this agent.


def test_a_process_with_no_tool_registry_shows_the_connector_strip_a_narrow_reader_sees(
    client: TestClient, stored: Stored
) -> None:
    """No registry and no reachable source are one empty strip, so an absent registry cannot
    be told from a reader who reaches nothing. The registry case above is the sibling.

    Delete this and a process built without a registry can answer differently from a person
    holding nothing, which is a fact about the deployment on a page about an agent."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    instance_row, version_row, _, _ = install_rows("quote_helper", connectors=(SOURCE,))
    stored.installs["quote_helper"] = (instance_row, version_row)
    app_of(client).state.tools = None

    assert workspace_of(client, "u_elsewhere", "quote_helper").json()["connectors"] == {
        "shown": [],
        "overflow": 0,
    }


def test_a_channel_row_says_what_a_run_could_carry_and_never_what_is_switched_on(
    client: TestClient, stored: Stored
) -> None:
    """Every row is one of the six surfaces this product ships, with the profile that
    surface's own capabilities derive, and there is no field on it saying whether the install
    has it enabled. A caller holding nothing is offered every surface, because a run that can
    read nothing can disclose nothing, which is `highest_classification`'s own floor.

    Delete this and the workspace can assert a per-agent channel enablement nothing stores, or
    draw a profile somebody chose by hand over the adapter's declaration."""
    stored.agents["quote_helper"] = agent_row("quote_helper")

    rows = workspace_of(client, "u_narrow", "quote_helper").json()["channels"]

    declared = agent_routes.declared_channels()
    assert [one["channel"] for one in rows] == [one.channel.value for one in declared]
    assert [one["profile"] for one in rows] == [rendering_profile(one).value for one in declared]
    assert set(agent_routes.ChannelView.model_fields) == {"channel", "profile"}


def test_a_run_that_could_return_the_most_sensitive_field_is_offered_fewer_surfaces(
    client: TestClient, stored: Stored
) -> None:
    """The offer narrows with the reach rather than being the same row for everybody: a caller
    who could return the most sensitive class this product classifies is offered only the
    surfaces that may carry it, and that is a strict subset of what a caller holding nothing
    is offered. The test above is the sibling for the wide end.

    Delete this and the channel block is computed at the agent's ceiling or at nothing at
    all, and a narrow caller is offered a surface their own run would be refused on."""
    policy = agent_routes.product_field_policy()
    sensitive = max(policy.rules, key=lambda rule: rule.classification.rank)
    stored.agents["quote_helper"] = agent_row(
        "quote_helper", capabilities=(sensitive.required_capability,)
    )
    GRANTS["u_wide"] = (
        Grant(capability=sensitive.required_capability, scope=Scope.unrestricted()),
    )
    try:
        wide = workspace_of(client, "u_wide", "quote_helper").json()["channels"]
        nothing = workspace_of(client, "u_none", "quote_helper").json()["channels"]
    finally:
        GRANTS["u_wide"] = ()

    # Both terms of the intersection are needed for a surface to drop out, which is the
    # invariant rather than a detail of the fixture: the caller holding the capability is
    # narrowed by the agent's ceiling, and a caller holding nothing is offered everything
    # through the very same agent.
    carried = {one["channel"] for one in wide}
    assert carried < {one["channel"] for one in nothing}
    assert carried == {
        one.channel.value
        for one in agent_routes.declared_channels()
        if one.may_carry(sensitive.classification)
    }

    # And the other term of the intersection, which is the half a reach taken from the caller
    # alone would get wrong: the same caller, holding the same capability, through an agent
    # whose ceiling does not hold it, is offered every surface again, because their run
    # through that agent could return nothing sensitive.
    stored.agents["blunt_helper"] = agent_row("blunt_helper")
    GRANTS["u_wide"] = (
        Grant(capability=sensitive.required_capability, scope=Scope.unrestricted()),
    )
    try:
        blunted = workspace_of(client, "u_wide", "blunt_helper").json()["channels"]
    finally:
        GRANTS["u_wide"] = ()

    assert {one["channel"] for one in blunted} == {one["channel"] for one in nothing}


def spend_row(
    agent_id: str,
    principal_id: str,
    *,
    minor: int,
    at: datetime,
    trace_id: str | None = "t" * 32,
) -> SpendActualRow:
    return SpendActualRow(
        principal_id=principal_id,
        principal_kind=PrincipalKind.HUMAN.value,
        traffic=TrafficClass.HUMAN_INTERACTIVE.value,
        department="web",
        agent_id=agent_id,
        model="a-model",
        lane=Lane.ANSWER.value,
        cost_minor=minor,
        at=at,
        trace_id=trace_id,
    )


def test_the_headline_is_this_agents_spend_at_whichever_basis_the_reader_holds(
    client: TestClient, stored: Stored
) -> None:
    """A reader who could open the budget screen sees every run of this agent; a reader who
    could not sees their own and is told so by the basis beside the figure. Both are computed
    by `brain.console.workspace.headline`, so the agent's front page and the budget screen
    cannot disagree about what a run cost.

    Delete this and a shared agent's spend, which is mostly somebody else's afternoon, is
    published to everybody its audience covers with no label on it."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    now = datetime.now(UTC)
    stored.spend = [
        spend_row("quote_helper", "u_elsewhere", minor=400, at=now),
        spend_row("quote_helper", "u_somebody", minor=600, at=now),
    ]

    wide = workspace_of(client, "u_elsewhere", "quote_helper").json()["headline"]
    narrower = workspace_of(client, "u_admin", "quote_helper").json()["headline"]

    assert wide == {"basis": "everyone", "range": "30d", "spend_minor": 1000, "runs": 2}
    assert narrower == {"basis": "own", "range": "30d", "spend_minor": 0, "runs": 0}
    assert set(agent_routes.HeadlineView.model_fields) == {
        "basis",
        "range",
        "spend_minor",
        "runs",
    }


def test_a_cost_outside_the_window_or_without_a_trace_is_absent_from_the_figure(
    client: TestClient, stored: Stored
) -> None:
    """A row older than the window and a row written before a trace id was required both
    contribute nothing, and neither takes the page down. The row inside the window is the
    sibling proving the figure is computed at all.

    Delete this and a headline counts runs the window excludes, or one row from a previous
    release is a 500 on every reader's agent page."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    now = datetime.now(UTC)
    stored.spend = [
        spend_row("quote_helper", "u_elsewhere", minor=400, at=now),
        spend_row("quote_helper", "u_elsewhere", minor=900, at=now - timedelta(days=400)),
        spend_row("quote_helper", "u_elsewhere", minor=900, at=now, trace_id=None),
    ]

    answer = workspace_of(client, "u_elsewhere", "quote_helper")

    assert answer.status_code == 200
    assert answer.json()["headline"] == {
        "basis": "everyone",
        "range": "30d",
        "spend_minor": 400,
        "runs": 1,
    }


def test_the_divergence_flag_travels_with_the_composition_and_names_the_parts(
    client: TestClient, stored: Stored
) -> None:
    """The install below overlays the persona, so the persona part is divergent, and the flag
    is `brain.console.workspace.divergent_parts`' answer rather than a comparison of two
    strings. A reader without the Settings tab gets neither the rows nor the flag.

    Delete this and a local edit to something a template supplies is invisible on the one
    page that shows the two side by side."""
    stored.agents["quote_helper"] = agent_row("quote_helper")
    instance_row, version_row, _, _ = install_rows("quote_helper")
    stored.installs["quote_helper"] = (instance_row, version_row)

    assert workspace_of(client, "u_admin", "quote_helper").json()["divergent"] == ["persona"]
    assert workspace_of(client, "u_narrow", "quote_helper").json()["divergent"] == []


# ------------------------------------------------------------------ the template gallery


def published_row(template_id: str, version: int, *, display_name: str) -> TemplateVersionRow:
    signed = publish(
        manifest(template_id, version=version, display_name=display_name),
        key=KEY,
        signed_by="u_publisher",
        at=SIGNED_AT,
    )
    return TemplateVersionRow(
        template_id=signed.manifest.identity.template_id,
        version=signed.manifest.identity.version,
        content_digest=signed.content_digest,
        signature=signed.signature,
        signed_by=signed.signed_by,
        signed_at=signed.signed_at,
        document=signed.manifest.document(),
    )


def test_the_gallery_lists_what_this_product_ships_and_what_this_installation_published(
    client: TestClient, stored: Stored
) -> None:
    """Every built-in manifest is a card, a published row is a card of its own, and each says
    which it is. The refusal below is the sibling for a reader without the screen.

    Delete this and the catalogue a person installs a role from is invisible in the browser,
    which is the state the owner found it in."""
    stored.versions = [published_row("pricing_desk", 1, display_name="Pricing desk")]

    body = get(client, "u_elsewhere", TEMPLATES).json()

    listed_ids = {one["template_id"] for one in body["items"]}
    assert listed_ids >= {one.identity.template_id for one in CATALOGUE}
    assert {"template_id": "pricing_desk", "origin": "published"} in [
        {"template_id": one["template_id"], "origin": one["origin"]} for one in body["items"]
    ]
    assert body["total"] is None
    assert set(body["items"][0]) == {
        "template_id",
        "version",
        "display_name",
        "summary",
        "published_by",
        "origin",
    }


def test_a_reader_without_the_skills_screen_is_refused_the_gallery_in_one_sentence(
    client: TestClient, stored: Stored
) -> None:
    """The screen's own read decides, and a reader without it gets the same status and body
    whether or not anything has been published. The reader who holds it is the sibling.

    Delete this and the catalogue is readable by everybody who can sign in, and a template's
    summary is a sentence about what this company does."""
    stored.versions = [published_row("pricing_desk", 1, display_name="Pricing desk")]

    refused = get(client, "u_admin", TEMPLATES)
    stored.versions = []
    empty = get(client, "u_admin", TEMPLATES)

    assert refused.status_code == 404
    assert refused.json()["message"] == Absent.public_message
    assert {k: v for k, v in refused.json().items() if k != "trace_id"} == {
        k: v for k, v in empty.json().items() if k != "trace_id"
    }
    assert get(client, "u_elsewhere", TEMPLATES).status_code == 200


def test_nothing_is_read_for_a_caller_the_gallery_refuses(
    client: TestClient, stored: Stored
) -> None:
    """The screen's question is asked before the database is, so a refused caller causes no
    query at all and the refusal cannot be timed against the catalogue's size.

    Delete this and the refusal happens after a read made on behalf of somebody who was never
    entitled to it."""
    stored.versions = [published_row("pricing_desk", 1, display_name="Pricing desk")]

    assert get(client, "u_admin", TEMPLATES).status_code == 404
    assert stored.statements == []

    assert get(client, "u_elsewhere", TEMPLATES).status_code == 200
    assert [one.column_descriptions[0]["entity"].__name__ for one in stored.statements] == [
        "TemplateVersionRow"
    ]


def test_a_published_template_is_shown_at_its_highest_version_and_hides_the_built_in_one() -> None:
    """Two versions of one published template are one card at the higher version, and a
    published template sharing an id with a built-in one replaces it rather than sitting
    beside it. The built-in cards for every other id are the sibling.

    Delete this and the gallery is a version history, or it offers two different documents
    under one name with nothing saying which an install would pin."""
    shipped = CATALOGUE[0].identity.template_id
    published = [
        manifest("pricing_desk", version=1, display_name="Pricing desk"),
        manifest("pricing_desk", version=4, display_name="Pricing desk"),
        manifest(shipped, version=2, display_name="Ours"),
    ]

    cards = gallery(published).items
    by_id = {one.template_id: one for one in cards}

    assert len([one for one in cards if one.template_id == "pricing_desk"]) == 1
    # One card per id, asked of the shipped id too and not only of the published one: `by_id`
    # keeps whichever card sorted last, so a gallery carrying both would satisfy every line
    # below on whichever name happened to sort after the other.
    assert len([one for one in cards if one.template_id == shipped]) == 1
    assert len({one.template_id for one in cards}) == len(cards)
    assert by_id["pricing_desk"].version == 4
    assert (by_id[shipped].origin, by_id[shipped].version) == ("published", 2)
    assert {one.origin for one in cards} == {"published", "built_in"}
    assert [one.display_name for one in cards] == sorted(one.display_name for one in cards)


def test_a_published_row_that_does_not_construct_is_absent_from_the_gallery(
    client: TestClient, stored: Stored
) -> None:
    """A document missing a path is left out and the rest of the catalogue is answered, rather
    than one bad row taking the gallery down for everybody. The sound row beside it is the
    sibling.

    Delete this and one malformed publish is an outage of the screen an administrator opens
    to find out what is wrong."""
    sound = published_row("pricing_desk", 1, display_name="Pricing desk")
    broken = published_row("other_desk", 1, display_name="Other desk")
    broken.document = {k: v for k, v in broken.document.items() if k != "persona"}
    stored.versions = [sound, broken]

    body = get(client, "u_elsewhere", TEMPLATES)

    assert body.status_code == 200
    listed_ids = {one["template_id"] for one in body.json()["items"]}
    assert "pricing_desk" in listed_ids
    assert "other_desk" not in listed_ids
