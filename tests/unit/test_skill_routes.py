"""The skills catalogue over HTTP: what it lists, what it refuses, and what it will not say.

Driven through the real application, with the token machinery, the key source and the stub
session shape borrowed from `tests/unit/test_agent_routes.py`, for the reason that file gives
about borrowing from `tests/unit/test_api_routes.py`. What is under test here is a listing
assembled from two decisions somebody else owns, so the fixtures are that file's: an audience
is decided by a person's department, and an install is written by a real publish and a real
install rather than assembled to suit.

**Every refusal has a sibling proving the permitted case is answered.** A route that refused
everybody would satisfy every refusal below and none of the positives, which is the failure
CLAUDE.md names about a guard tested only by its refusals.

**The two claims this screen makes about itself are asserted as properties and not as words.**
There is no write on this router, and no route answers one skill by name; both are read off the
application's own OpenAPI document rather than off a constant in the module under test.

**Nothing on any answer counts what was withheld.** `brain.ops.jobs.hidden_count_fields` is
asked of every view type, and the narrow-reader test compares two responses byte for byte
rather than reading a number off one of them.

Task ids: M42.6.4
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain import skill_routes
from brain.agent_routes import record_of
from brain.agents.model import AgentAudience
from brain.agents.template import (
    ManifestIdentity,
    SkillRef,
    TemplateInstance,
    TemplateManifest,
    install,
    materialise,
    publish,
)
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.govern import Placed
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.skill_library import (
    NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED,
    REVIEW_AUTHORITY,
    SKILL_AUTHORITY,
    Assignment,
    LibrarySkill,
    added,
    decided,
    read_package,
)
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.knowledge.visibility import Visibility
from brain.listing import MAX_PAGE_ROWS
from brain.ops.jobs import hidden_count_fields
from brain.prompt_routes import installed
from brain.skill_routes import (
    AgentChoiceView,
    AssignedView,
    FoundAgent,
    LibrarySkillView,
    QueueEntryView,
    SkillPinView,
    SkillQueueView,
    SkillRow,
    SkillsPage,
    ToolReachView,
    bounded_agents,
    catalogue,
    installs_of,
    pins_of,
    queue_view,
    submitted,
)
from brain.tables.agent import AgentRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tools.review import STALE_AFTER, QueueEntry
from brain.tools.skills import (
    ImportedSkill,
    Skill,
    SkillPin,
    SkillSource,
    SourceKind,
)
from tests.fixtures.http_client import Response
from tests.unit.test_agent_routes import (
    Directory,
    agent_row,
)
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)
from tests.unit.test_skill_library import SKILL_MD, a_registry, text_with

SKILLS = f"{API_PREFIX}/skills"

#: A PostgreSQL dialect to compile statements against, from an engine that never connects.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far outside any plausible wall clock, for the reason CLAUDE.md gives about a fixture that is
#: a clock: nothing here is about the present, and a date near today goes off on a schedule
#: nobody chose.
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
KEY = "a-key-for-this-test"

#: Two digests of the right shape, so a pin is a pin rather than a string the type refuses.
DIGEST_ONE = "a" * 64
DIGEST_TWO = "b" * 64

SKILL_READ = screen("skills").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
EXISTENCE = plane_capability(Plane.EXISTENCE)
CLIENT_NAMES = Capability(value="read:client.name")

#: Who sits where. `u_narrow` is in web, `u_wide` in sales, and both may open the screen; the
#: difference between them is the audience, which is the point of the narrow-reader test.
DEPARTMENTS: Mapping[str, str | None] = {
    "u_narrow": "web",
    "u_wide": "sales",
    "u_prefix": "web",
    "u_none": None,
    "u_admin": "web",
    "u_elsewhere": "finance",
}

#: What each person holds. `u_narrow`, `u_wide` and `u_admin` hold the screen's capability and
#: the configuration plane, which is what `brain.console.reads.permitted` asks for together.
#: `u_prefix` holds the capability and only the existence plane, which is the reader a bare
#: capability check would let in. `u_none` holds nothing. `u_elsewhere` holds the screen at a
#: scope that admits finance rows and no other, which is what narrows the queue.
#:
#: Of the writes: `u_admin` adds, reviews and assigns skills over everything, as a first
#: administrator does, and reads client names, so a skill naming the client tool reaches it through
#: an agent allowed it and a skill they added is one they may not decide; `u_wide` reviews over
#: everything and adds nothing; `u_elsewhere` assigns in finance and nowhere else; `u_narrow`
#: reads the screen and may do none of the three.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_narrow": (
        Grant(capability=SKILL_READ, scope=Scope.unrestricted()),
        Grant(capability=CONFIGURATION, scope=Scope.unrestricted()),
    ),
    "u_wide": (
        Grant(capability=SKILL_READ, scope=Scope.unrestricted()),
        Grant(capability=CONFIGURATION, scope=Scope.unrestricted()),
        Grant(capability=REVIEW_AUTHORITY, scope=Scope.unrestricted()),
    ),
    "u_prefix": (
        Grant(capability=SKILL_READ, scope=Scope.unrestricted()),
        Grant(capability=EXISTENCE, scope=Scope.unrestricted()),
    ),
    "u_none": (),
    "u_admin": (
        Grant(capability=SKILL_READ, scope=Scope.unrestricted()),
        Grant(capability=CONFIGURATION, scope=Scope.unrestricted()),
        Grant(capability=SKILL_AUTHORITY, scope=Scope.unrestricted()),
        Grant(capability=REVIEW_AUTHORITY, scope=Scope.unrestricted()),
        Grant(capability=CLIENT_NAMES, scope=Scope.unrestricted()),
    ),
    "u_elsewhere": (
        Grant(capability=SKILL_READ, scope=Scope.department("finance")),
        Grant(capability=CONFIGURATION, scope=Scope.unrestricted()),
        Grant(capability=SKILL_AUTHORITY, scope=Scope.department("finance")),
        Grant(capability=CLIENT_NAMES, scope=Scope.unrestricted()),
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


class Store:
    """A `brain.gate.resolve.EntitlementStore` over `GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


# ---------------------------------------------------------------------- the rows


def skilled_rows(
    agent_id: str, *, skills: tuple[SkillRef, ...]
) -> tuple[TemplateInstanceRow, TemplateVersionRow]:
    """The two rows an install writes for an agent whose template names skills.

    Written through `publish`, `install` and `materialise`, so the loader is tested against
    what the application writes rather than against a dictionary written to suit it.
    """
    signed = publish(
        TemplateManifest(
            identity=ManifestIdentity(
                template_id="pricing_desk",
                version=3,
                published_by="u_publisher",
                display_name="Pricing desk",
                summary="Drafts a first answer to a pricing question.",
            ),
            persona="Answer briefly.",
            skills=skills,
        ),
        key=KEY,
        signed_by="u_publisher",
        at=datetime(2019, 3, 4, 9, 0, tzinfo=UTC),
    )
    instance = install(
        signed,
        key=KEY,
        instance_id=agent_id,
        created_by="u_installer",
        at=datetime(2019, 3, 5, 9, 0, tzinfo=UTC),
        overlay={},
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
    return instance_row, version_row


# ------------------------------------------------------------------- the stub session


class Stored:
    """What the stub database holds, and every statement it was asked."""

    def __init__(self) -> None:
        self.agents: dict[str, AgentRow] = {}
        self.installs: dict[str, tuple[TemplateInstanceRow, TemplateVersionRow]] = {}
        self.statements: list[Any] = []
        self.library = Library(self)


class Library:
    """A `brain.skill_routes.SkillLibrary` over a dictionary, keyed and refusing as the tables do.

    A second import of one digest and a second decision about one are refused, as the keys refuse
    them. An assignment writes the install into the stub rows the catalogue reads, so a test can
    follow an assignment to the pin the Skills screen lists afterwards, and refuses when the hash it
    was handed is not the stored one, as the store does under its lock. Every call is noted.
    """

    def __init__(self, stored: Stored) -> None:
        self.stored = stored
        self.skills: dict[str, LibrarySkill] = {}
        self.calls: list[str] = []
        self.assigned: list[Assignment] = []

    async def library(self, limit: int = 500) -> tuple[LibrarySkill, ...]:
        self.calls.append("library")
        return tuple(self.skills.values())[:limit]

    async def skill(self, digest: str) -> LibrarySkill | None:
        self.calls.append("skill")
        return self.skills.get(digest)

    async def add(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool:
        self.calls.append("add")
        if one.digest in self.skills:
            return False
        self.skills[one.digest] = one
        return True

    async def decide(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool:
        self.calls.append("decide")
        if self.skills[one.digest].imported.reviewer:
            return False
        self.skills[one.digest] = one
        return True

    async def assign(
        self, made: Assignment, *, expected_hash: str, ent_hash: str, trace_id: str
    ) -> bool:
        self.calls.append("assign")
        instance_row, _ = self.stored.installs[made.agent_id]
        if instance_row.effective_hash != expected_hash:
            return False
        instance_row.overlay = dict(made.instance.overlay)
        instance_row.field_owners = {
            path: owner.model_dump(mode="json")
            for path, owner in made.instance.overlay_owners.items()
        }
        instance_row.effective_document = dict(made.effective_document)
        instance_row.effective_hash = made.effective_hash
        self.assigned.append(made)
        return True


class Installs:
    """A `brain.skill_routes.AgentInstalls` over the stub rows the catalogue reads."""

    async def agent(self, agent_id: str) -> FoundAgent | None:
        row = _STORED.agents.get(agent_id)
        record = None if row is None else record_of(row)
        if record is None:
            return None
        pair = _STORED.installs.get(agent_id)
        return FoundAgent(
            record=record,
            install=None if pair is None else installed(*pair),
            effective_hash=None if pair is None else pair[0].effective_hash,
        )


_STORED = Stored()


class StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class StubSession(AsyncSession):
    """An `AsyncSession` answering the two statements this router makes, and no other.

    The install statement is told apart by its two column descriptions, which is
    `tests/unit/test_agent_routes.py`'s stub and the same distinction. The agents it names are
    read off the `IN` clause rather than assumed, so a route that stopped filtering would be
    answered every install rather than the ones it asked for, and the audience test below would
    fail rather than passing on the stub's tidiness.
    """

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        _STORED.statements.append(statement)
        if len(statement.column_descriptions) == 2:
            asked = set(statement.whereclause.right.value)
            return StubResult(
                [_STORED.installs[key] for key in sorted(asked & set(_STORED.installs))]
            )
        return StubResult([_STORED.agents[key] for key in sorted(_STORED.agents)])

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
        app.state.skill_library = stored.library
        app.state.agent_installs = Installs()
        app.state.tools = a_registry()
        yield c


#: A session signed in with a second factor. `brain.gate.admission` withholds every `admin:`
#: capability from a password-only session, so without this no write here is ever reached.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


def get(c: TestClient, pid: str, path: str = SKILLS) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR)
    response: Response = c.get(path, headers={"authorization": f"Bearer {token}"})
    return response


def names(response: Response) -> list[str]:
    return [one["name"] for one in response.json()["items"]]


# ------------------------------------------------------------------- the catalogue


def test_the_catalogue_lists_every_skill_the_callers_agents_are_pinned_to(
    client: TestClient, stored: Stored
) -> None:
    """The positive case for every refusal below: two agents, three pins, and the agents that
    hold each skill named beside it.

    Delete this and every refusal here is satisfied by a route that lists nothing at all."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.agents["web_helper"] = agent_row(
        "web_helper", level=Visibility.DEPARTMENT, department="web"
    )
    stored.installs["company_desk"] = skilled_rows(
        "company_desk",
        skills=(
            SkillRef(name="hosting-expiry", digest=DIGEST_ONE),
            SkillRef(name="quote-format", digest=DIGEST_TWO),
        ),
    )
    stored.installs["web_helper"] = skilled_rows(
        "web_helper", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )

    response = get(client, "u_narrow")

    assert response.status_code == 200, response.text
    assert names(response) == ["hosting-expiry", "quote-format"]
    first = response.json()["items"][0]
    assert first["pinned_by"] == [
        {"agent_id": "company_desk", "digest": DIGEST_ONE},
        {"agent_id": "web_helper", "digest": DIGEST_ONE},
    ]
    assert first["versions_differ"] is False


def test_a_skill_only_a_hidden_agent_pins_is_absent_rather_than_listed_without_its_agent(
    client: TestClient, stored: Stored
) -> None:
    """A caller whose audience covers fewer agents sees fewer skills, and the answer is byte
    for byte the answer to an install that never held the hidden agent at all.

    Delete this and a skill row can be drawn for an agent the reader may not see, which
    discloses through a procedure's name what the roster refuses to disclose by name."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.installs["company_desk"] = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )
    without = get(client, "u_narrow")

    stored.agents["sales_helper"] = agent_row(
        "sales_helper", level=Visibility.DEPARTMENT, department="sales"
    )
    stored.installs["sales_helper"] = skilled_rows(
        "sales_helper", skills=(SkillRef(name="quote-format", digest=DIGEST_TWO),)
    )
    with_hidden = get(client, "u_narrow")

    assert with_hidden.status_code == without.status_code == 200
    assert with_hidden.content == without.content
    # And the same skill is listed for the person whose audience does cover that agent, so the
    # absence above is an audience decision rather than a row nobody can see.
    assert names(get(client, "u_wide")) == ["hosting-expiry", "quote-format"]


def test_an_agent_row_that_does_not_construct_is_absent_for_everybody(
    client: TestClient, stored: Stored
) -> None:
    """A stored agent whose row its own validators refuse takes no skill with it and takes the
    screen down for nobody.

    Delete this and one malformed row answers 500 to every reader, which is the whole catalogue
    gone over an agent nobody can see anyway, and `brain.agent_routes.
    A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY` is undone one route along."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.installs["company_desk"] = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )
    broken = agent_row("broken_desk")
    # A tier no vocabulary holds, which is what `record_of` catches: `Tier(row.tier)` raises a
    # `ValueError` and the record is None rather than a half-built agent.
    broken.tier = "not-a-tier"
    stored.agents["broken_desk"] = broken
    stored.installs["broken_desk"] = skilled_rows(
        "broken_desk", skills=(SkillRef(name="quote-format", digest=DIGEST_TWO),)
    )

    response = get(client, "u_narrow")

    assert response.status_code == 200, response.text
    assert names(response) == ["hosting-expiry"]


def test_agents_pinned_to_different_bytes_of_one_skill_are_one_row_that_says_so(
    client: TestClient, stored: Stored
) -> None:
    """Two agents pinned to two digests of one name come back as one row with
    `versions_differ` true, and the same pair on one digest comes back false.

    Delete this and the drift `docs/screens.html` SCREEN 6 shows as an upstream-drift card is
    invisible: two agents running different procedures under one name read as one skill."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.agents["web_helper"] = agent_row(
        "web_helper", level=Visibility.DEPARTMENT, department="web"
    )
    stored.installs["company_desk"] = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )
    stored.installs["web_helper"] = skilled_rows(
        "web_helper", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_TWO),)
    )

    response = get(client, "u_narrow")
    row = response.json()["items"][0]

    assert row["name"] == "hosting-expiry"
    assert row["versions_differ"] is True
    assert [one["digest"] for one in row["pinned_by"]] == [DIGEST_ONE, DIGEST_TWO]


def test_an_install_that_does_not_construct_is_an_agent_with_no_skills(stored: Stored) -> None:
    """A version row whose document is not a manifest produces no pins and raises nothing.

    Delete this and one unreadable install answers 500 for every reader, which takes the whole
    screen away from the person who came to find out what is wrong with it."""
    instance_row, version_row = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )
    record = materialise(
        *_pair(instance_row, version_row),
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
    ).record
    broken = TemplateVersionRow(
        template_id=version_row.template_id,
        version=version_row.version,
        content_digest=version_row.content_digest,
        signature=version_row.signature,
        signed_by=version_row.signed_by,
        signed_at=version_row.signed_at,
        document={"persona": "Answer briefly."},
    )

    assert pins_of(instance_row, version_row, record) == (
        SkillPin(agent_id="company_desk", skill_name="hosting-expiry", digest=DIGEST_ONE),
    )
    assert pins_of(instance_row, broken, record) == ()


def _pair(
    instance_row: TemplateInstanceRow, version_row: TemplateVersionRow
) -> tuple[Any, TemplateInstance]:
    """The signed manifest and the instance behind two stored rows, for a test that needs the
    record rather than the response."""
    from brain.agent_routes import manifest_of
    from brain.agents.template import FieldOwner, SignedManifest

    signed = SignedManifest(
        manifest=manifest_of(version_row.document),
        content_digest=version_row.content_digest,
        signature=version_row.signature,
        signed_by=version_row.signed_by,
        signed_at=version_row.signed_at,
    )
    instance = TemplateInstance(
        instance_id=instance_row.id,
        template_id=instance_row.template_id,
        template_version=instance_row.template_version,
        content_digest=instance_row.content_digest,
        overlay=instance_row.overlay,
        overlay_owners={
            path: FieldOwner.model_validate(owner)
            for path, owner in instance_row.field_owners.items()
        },
        created_by=instance_row.created_by,
    )
    return signed, instance


def test_an_install_belonging_to_an_agent_outside_the_audience_is_dropped_by_the_route(
    client: TestClient, stored: Stored
) -> None:
    """An install row for an agent the audience did not admit contributes no pins, even when a
    statement hands one over.

    Delete this and the filter is applied in exactly one place, the statement, so the day that
    statement is rewritten the route lists every agent's skills and nothing fails."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.installs["company_desk"] = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )
    # An install whose agent is in no roster at all, which the statement did not ask for and a
    # generous session could still return.
    stored.installs["ghost"] = skilled_rows(
        "ghost", skills=(SkillRef(name="quote-format", digest=DIGEST_TWO),)
    )
    _STORED.installs["ghost"] = stored.installs["ghost"]

    class GenerousSession(StubSession):
        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            _STORED.statements.append(statement)
            if len(statement.column_descriptions) == 2:
                return StubResult([_STORED.installs[key] for key in sorted(_STORED.installs)])
            return StubResult([_STORED.agents[key] for key in sorted(_STORED.agents)])

    client.app.state.db_sessions = async_sessionmaker(class_=GenerousSession)  # type: ignore[attr-defined]

    assert names(get(client, "u_narrow")) == ["hosting-expiry"]


# -------------------------------------------------------------------- the refusals


def test_a_caller_without_the_screens_grant_is_refused_and_one_with_it_is_answered(
    client: TestClient, stored: Stored
) -> None:
    """The refusal and its sibling in one test, over one set of rows: a person holding nothing
    is refused, and a person holding the screen's capability and its plane is answered.

    Delete this and the catalogue is readable by anybody who can reach the port."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.installs["company_desk"] = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )

    refused = get(client, "u_none")
    answered = get(client, "u_admin")

    assert refused.status_code == 404
    assert answered.status_code == 200
    assert names(answered) == ["hosting-expiry"]


def test_a_reader_holding_only_the_existence_plane_is_refused_a_configuration_screen(
    client: TestClient, stored: Stored
) -> None:
    """`u_prefix` holds `read:skill` and the existence plane, and gets the same answer as
    somebody holding nothing.

    Delete this and a bare capability check passes here, which is the distinction
    `brain.console.reads.Plane` exists to draw: knowing a skill exists is not being shown how
    every agent in the company is configured to run it."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.installs["company_desk"] = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )

    existence_only = get(client, "u_prefix")
    nothing = get(client, "u_none")

    assert existence_only.status_code == nothing.status_code == 404
    # The message and nothing else: the trace id differs between any two requests, which is
    # what a person quotes in a support conversation rather than a fact about either caller.
    assert existence_only.json()["message"] == nothing.json()["message"]


def test_a_caller_with_no_grant_cannot_tell_whether_this_process_has_a_database() -> None:
    """The screen's question is asked before the session factory is reached for, read out of
    the route's own source.

    Delete this and the two lines can be swapped by somebody tidying, after which a caller
    holding nothing is refused on an instance with a database and told this process is broken
    on one without, which is the deployment's state readable by anybody who can reach the
    port."""
    source = inspect.getsource(skill_routes.skills)
    tree = ast.parse(source.lstrip())
    refusal = next(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and "_not_answerable" in ast.unparse(node)
    )
    session = next(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node).startswith("_require_sessions")
    )

    assert refusal < session


def test_a_process_with_no_database_is_a_fault_and_not_an_empty_catalogue(
    stored: Stored,
) -> None:
    """A reader who holds the screen's grant on an instance with no pool gets the fault every
    route here gives, rather than a page saying this company runs no skills.

    Delete this and a misconfigured instance answers an empty catalogue to an administrator,
    who reads it as a fact about the company."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        response = get(c, "u_admin")

    assert response.status_code == 500
    # The application's own error body, which is what `Failed` produces: an instance whose
    # missing pool reached the route as an ordinary crash would answer 500 as well, and the
    # difference between a refusal this module made and an exception nobody caught is exactly
    # what `_require_sessions` exists to keep.
    assert isinstance(response.json().get("message"), str)
    assert isinstance(response.json().get("trace_id"), str)


# ------------------------------------------------------------------ the review queue


def imported(name: str) -> ImportedSkill:
    return ImportedSkill(
        skill=Skill(name=name, description=f"Use when {name} comes up.", tools=()),
        source=SkillSource(
            kind=SourceKind.URL,
            location="https://example.invalid/skill.zip",
            content_digest="c" * 64,
        ),
    )


def waiting(
    name: str, *, days: int, where: str, changed: tuple[str, ...] = ()
) -> Placed[QueueEntry]:
    return Placed(
        record=QueueEntry(
            skill=imported(name), waiting_since=NOW - timedelta(days=days), changed=changed
        ),
        where={"department": where},
    )


def reader(pid: str) -> EntitlementSet:
    return EntitlementSet(principal_id=pid, grants=GRANTS[pid])


def test_the_queue_is_narrowed_to_the_reader_before_it_is_summarised() -> None:
    """A reader whose grant admits finance rows sees the finance submission and its counts;
    a reader granted everywhere sees both and counts both.

    Delete this and the route can summarise the whole queue beside a listing of one row, which
    publishes how many skills are waiting that this reader may not read."""
    entries = (
        waiting("xero-reconciliation", days=9, where="finance"),
        waiting("quote-format", days=1, where="sales", changed=("body",)),
    )

    narrow = queue_view(entries, reader("u_elsewhere"), NOW)
    wide = queue_view(entries, reader("u_admin"), NOW)

    assert [one.name for one in narrow.entries] == ["xero-reconciliation"]
    assert (narrow.waiting, narrow.edits, narrow.stale) == (1, 0, 1)
    assert [one.name for one in wide.entries] == ["xero-reconciliation", "quote-format"]
    assert (wide.waiting, wide.edits, wide.stale) == (2, 1, 1)


def test_a_summary_counts_exactly_the_entries_beside_it() -> None:
    """Whatever the reader, the `waiting` figure is the length of the list under it.

    Delete this and the two halves can be computed over different lists, which is the
    subtraction `brain.console.govern_estate.
    A_SUMMARY_OVER_A_WIDER_LIST_THAN_THE_LISTING_IS_A_SUBTRACTION` names."""
    entries = (
        waiting("xero-reconciliation", days=9, where="finance"),
        waiting("quote-format", days=1, where="sales"),
    )

    for pid in ("u_elsewhere", "u_admin", "u_none"):
        view = queue_view(entries, reader(pid), NOW)
        assert view.waiting == len(view.entries)
        assert view.stale <= view.waiting


def test_staleness_on_a_queue_entry_is_the_review_modules_own_line() -> None:
    """An entry that has waited `STALE_AFTER` is stale and one that has waited a day less is
    not, measured against that constant rather than against a number written here.

    Delete this and a threshold copied into the route ages differently from the queue the
    reviewer reads, and the screen calls something overdue that the module does not."""
    old = queue_view(
        (waiting("a-skill", days=STALE_AFTER.days, where="finance"),), reader("u_admin"), NOW
    )
    fresh = queue_view(
        (waiting("a-skill", days=STALE_AFTER.days - 1, where="finance"),), reader("u_admin"), NOW
    )

    assert old.entries[0].stale is True
    assert fresh.entries[0].stale is False


def test_every_undecided_skill_in_the_library_is_submitted_for_review() -> None:
    """`submitted` is the library's undecided skills, placed where the queue narrows them, and a
    decided one is not among them.

    Delete this and the queue can go on listing nothing now that a store exists, which is the day
    the function was kept a function for."""
    waiting = added(read_package("SKILL.md", SKILL_MD.encode("utf-8")), by="u_admin", at=NOW)
    decided_one = decided(
        added(
            read_package(
                "SKILL.md",
                text_with(name="quote-format", description="Formats a quote").encode("utf-8"),
            ),
            by="u_admin",
            at=NOW,
        ),
        reviewer="u_wide",
        approve=True,
        at=NOW,
    )

    entries = submitted((waiting, decided_one), NOW)

    assert [one.record.skill.skill.name for one in entries] == ["hosting-expiry"]
    assert queue_view(entries, reader("u_admin"), NOW).waiting == 1
    assert queue_view(entries, reader("u_elsewhere"), NOW).waiting == 0


def test_a_queue_entry_carries_no_body_and_no_reviewer() -> None:
    """`QueueEntryView` has five fields and none of them can hold the instructions or the name of
    whoever decided.

    Delete this and a queue listing hands over the procedure of a skill nobody has approved to
    every reader of the queue, where the library row discloses it only to a reader who may add or
    review skills."""
    assert set(QueueEntryView.model_fields) == {
        "name",
        "digest",
        "waiting_since",
        "changed",
        "stale",
    }


# --------------------------------------------------------------- what it will not say


def test_the_writes_are_three_posts_and_no_read_answers_one_skill_by_name(
    client: TestClient,
) -> None:
    """Under `/skills` there is one GET, which takes no path parameter, and three POSTs: add a
    skill, decide about one, and assign one. Read off the application's own document.

    Delete this and a fourth write, an approval folded into an import say, or a GET answering one
    skill by name, can arrive without anybody arguing for it."""
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    mine = {path: set(operations) for path, operations in paths.items() if path.startswith(SKILLS)}

    assert mine == {
        SKILLS: {"get", "post"},
        f"{SKILLS}/{{digest}}/review": {"post"},
        f"{SKILLS}/{{digest}}/assignments": {"post"},
    }
    assert [path for path, methods in mine.items() if "get" in methods and "{" in path] == []


def test_no_row_here_carries_a_state_a_source_or_a_reviewer(client: TestClient) -> None:
    """`SkillRow` and `SkillPinView` have no field a review word could travel in.

    Delete this and somebody adds a `state` column filled from the pin, which says a skill was
    approved on the strength of an agent having been configured with it."""
    forbidden = {"state", "source", "review", "reviewer", "reviewed_at", "approved_digest"}

    assert set(SkillRow.model_fields) & forbidden == set()
    assert set(SkillPinView.model_fields) & forbidden == set()
    assert set(SkillRow.model_fields) == {"name", "pinned_by", "versions_differ"}


def test_no_answer_carries_a_count_of_what_the_reader_was_not_shown(
    client: TestClient, stored: Stored
) -> None:
    """No view type here holds a field `brain.ops.jobs` recognises as a hidden count, and
    `total` is never populated on the page.

    Delete this and "showing 3 of 47" arrives as a field somebody added for a footer."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.agents["sales_helper"] = agent_row(
        "sales_helper", level=Visibility.DEPARTMENT, department="sales"
    )
    stored.installs["company_desk"] = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )

    body = get(client, "u_narrow").json()

    views = (
        SkillRow,
        SkillPinView,
        SkillsPage,
        SkillQueueView,
        LibrarySkillView,
        ToolReachView,
        AgentChoiceView,
        AssignedView,
    )
    assert hidden_count_fields(views) == ()
    assert body["total"] is None
    assert body["next_cursor"] is None


def test_nothing_in_this_module_computes_a_reach() -> None:
    """There is no `intersect` call in the route module.

    Delete this and the console grows a second implementation of the platform's central rule
    in a file whose job is to load rows and render them."""
    assert intersections_in(inspect.getsource(skill_routes)) == ()


# ------------------------------------------------------------------ the statements


def test_the_statements_bound_the_agents_and_join_the_pin_on_both_halves() -> None:
    """The agents statement carries the limit it was given, and the install statement joins the
    version on the template and the version number together.

    Delete this and the join can be written on the template alone, which attaches an instance
    to whichever version of its template the database happened to return: a catalogue of the
    skills some other version of the template names."""
    agents = str(bounded_agents(7).compile(dialect=DIALECT))
    installs = str(installs_of(["a", "b"]).compile(dialect=DIALECT))

    assert "LIMIT" in agents
    assert bounded_agents(7).compile(dialect=DIALECT).params["param_1"] == 7
    assert "agent.template_version.template_id = agent.template_instance.template_id" in installs
    assert "agent.template_version.version = agent.template_instance.template_version" in installs
    assert "agent.template_instance.id IN" in installs


def test_the_bound_on_the_page_is_a_bound_on_the_load_and_not_on_the_answer(
    client: TestClient, stored: Stored, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`truncated` is true when the agent load came back full, whatever was searched for, and
    the rows are whatever survived the audience.

    Delete this and the flag can be computed against the rows that survived filtering, which
    is a count of what the filter removed spelled as a boolean, or against a load the search
    narrowed."""
    stored.agents["company_desk"] = agent_row("company_desk")
    stored.agents["sales_helper"] = agent_row(
        "sales_helper", level=Visibility.DEPARTMENT, department="sales"
    )
    stored.installs["company_desk"] = skilled_rows(
        "company_desk", skills=(SkillRef(name="hosting-expiry", digest=DIGEST_ONE),)
    )

    monkeypatch.setattr(skill_routes, "MAX_AGENTS_CONSIDERED", 2)
    full = get(client, "u_narrow", SKILLS)
    searched = get(client, "u_narrow", f"{SKILLS}?q=nothing-is-called-this")
    monkeypatch.setattr(skill_routes, "MAX_AGENTS_CONSIDERED", 3)
    roomy = get(client, "u_narrow", SKILLS)

    assert full.json()["truncated"] is True
    assert searched.json()["truncated"] is True
    assert roomy.json()["truncated"] is False
    assert names(full) == names(roomy) == ["hosting-expiry"]


def test_a_limit_outside_the_routes_bound_is_refused_rather_than_clamped(
    client: TestClient, stored: Stored
) -> None:
    """A limit over `brain.listing.MAX_PAGE_ROWS` and one below one are both 422.

    Delete this and a caller can ask for a page the statement was never bounded for, which is
    a resource decision made by whoever wrote the query string."""
    over = get(client, "u_admin", f"{SKILLS}?limit={MAX_PAGE_ROWS + 1}")
    under = get(client, "u_admin", f"{SKILLS}?limit=0")

    assert over.status_code == under.status_code == 422


# ---------------------------------------------------------------- the projection


def test_pins_are_grouped_by_name_and_sorted_so_two_readings_are_one_page() -> None:
    """`catalogue` groups two agents' pins of one skill on to one row, sorts the rows by name
    and the pins by agent, whatever order the pins arrive in.

    Delete this and the page depends on the order rows came back from the database, so two
    readings of an unchanged install are two different pages and a diff of them is noise."""
    pins = (
        SkillPin(agent_id="web_helper", skill_name="quote-format", digest=DIGEST_TWO),
        SkillPin(agent_id="company_desk", skill_name="hosting-expiry", digest=DIGEST_ONE),
        SkillPin(agent_id="web_helper", skill_name="hosting-expiry", digest=DIGEST_ONE),
    )

    rows = catalogue(pins)

    assert [one.name for one in rows] == ["hosting-expiry", "quote-format"]
    assert [one.agent_id for one in rows[0].pinned_by] == ["company_desk", "web_helper"]
    assert catalogue(reversed(pins)) == rows


def test_one_agent_pinned_to_one_digest_does_not_read_as_a_disagreement() -> None:
    """`versions_differ` is false for a single pin and for two identical ones.

    Delete this and the flag can be written as "there is a pin", which marks every skill on the
    screen as drifting and makes the marker worth nothing."""
    one = catalogue((SkillPin(agent_id="a", skill_name="s", digest=DIGEST_ONE),))
    same = catalogue(
        (
            SkillPin(agent_id="a", skill_name="s", digest=DIGEST_ONE),
            SkillPin(agent_id="b", skill_name="s", digest=DIGEST_ONE),
        )
    )
    different = catalogue(
        (
            SkillPin(agent_id="a", skill_name="s", digest=DIGEST_ONE),
            SkillPin(agent_id="b", skill_name="s", digest=DIGEST_TWO),
        )
    )

    assert one[0].versions_differ is False
    assert same[0].versions_differ is False
    assert different[0].versions_differ is True


def test_the_screen_key_is_the_one_the_agents_tab_already_declares() -> None:
    """This route and `brain.console.agent_tabs` name one screen, so a grant that opens the tab
    opens the catalogue.

    Delete this and the two drift into two capabilities for one screen, and an administrator
    granted the tab finds the catalogue refused with nothing saying why."""
    from brain.console.agent_tabs import SKILL_SCREEN

    assert skill_routes.SKILLS_SCREEN == SKILL_SCREEN
    assert screen(skill_routes.SKILLS_SCREEN).read.requires == SKILL_READ


def test_the_refusal_names_the_screen_and_never_the_caller_or_the_capability(
    client: TestClient, stored: Stored
) -> None:
    """The body a refused caller gets carries the screen's name and nothing about them.

    Delete this and a refusal grows a sentence naming what was withheld, which is the
    disclosure the withholding was for."""
    body = get(client, "u_none").json()
    text = str(body)

    assert "u_none" not in text
    assert SKILL_READ.value not in text


# ------------------------------------------------------------------ the three writes


def post(
    c: TestClient, pid: str, path: str, body: Mapping[str, Any], *, strong: bool = True
) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR if strong else {})
    response: Response = c.post(path, json=dict(body), headers={"authorization": f"Bearer {token}"})
    return response


def screen_refusal(c: TestClient) -> str:
    """The message a caller holding nothing is given, which every refusal to act must match."""
    return str(get(c, "u_none").json()["message"])


def a_package(text: str = SKILL_MD) -> dict[str, str]:
    return {"file_name": "SKILL.md", "content": text, "encoding": "text"}


def an_assignable_agent(stored: Stored, agent_id: str = "company_desk", **row: Any) -> None:
    """An agent whose ceiling reads client names through the client tool, with an install."""
    stored.agents[agent_id] = agent_row(
        agent_id,
        allowed_tools=("crm.read_client",),
        capabilities=(CLIENT_NAMES,),
        **row,
    )
    stored.installs[agent_id] = skilled_rows(agent_id, skills=())


def test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent(
    client: TestClient, stored: Stored
) -> None:
    """**M42.6.4 end to end, through the application.** An administrator adds a skill from a
    pasted `SKILL.md` and is answered with what it is trusted to reach, read off the registry; the
    library lists it undecided and the queue lists it waiting; the same administrator is refused
    the decision in words saying why; a second person approves it; the administrator assigns it to
    an agent and is answered with what it reaches through that agent for them, which is the one
    tool the agent is allowed; and the Skills screen then lists the agent pinned to exactly the
    approved bytes.

    Delete this and add, reach and assign can each be proved on their own while the three never
    meet: a skill added that the queue does not list, an approval the assignment does not see, or
    an assignment that writes an install the screen does not read."""
    an_assignable_agent(stored)

    added_skill = post(client, "u_admin", SKILLS, a_package())
    assert added_skill.status_code == 201, added_skill.text
    row = added_skill.json()
    digest = row["digest"]
    assert row["review"] == "pending"
    assert row["tools"] == [
        {"name": "crm.read_client", "capability": "read:client.name"},
        {"name": "desk.read_ticket", "capability": "read:ticket.status"},
    ]
    assert row["capabilities"] == ["read:client.name", "read:ticket.status"]
    assert row["reviewable"] is False

    page = get(client, "u_admin").json()
    assert [one["name"] for one in page["library"]] == ["hosting-expiry"]
    assert [one["digest"] for one in page["queue"]["entries"]] == [digest]
    assert page["may_add"] is True
    assert page["agents"] == [{"agent_id": "company_desk", "display_name": "Company Desk"}]

    own = post(client, "u_admin", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    assert own.status_code == 404
    assert NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED in own.json()["message"]
    early = post(client, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": "company_desk"})
    assert early.status_code == 404
    assert stored.library.assigned == []

    reviewed = post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    assert reviewed.status_code == 200, reviewed.text
    assert (reviewed.json()["review"], reviewed.json()["reviewer"]) == ("approved", "u_wide")

    assigned = post(
        client, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": "company_desk"}
    )
    assert assigned.status_code == 201, assigned.text
    assert assigned.json()["reach"] == ["crm.read_client"]
    assert assigned.json()["digest"] == digest
    assert assigned.json()["replaced_digest"] is None

    after = get(client, "u_admin").json()
    assert after["items"] == [
        {
            "name": "hosting-expiry",
            "pinned_by": [{"agent_id": "company_desk", "digest": digest}],
            "versions_differ": False,
        }
    ]
    assert after["queue"]["entries"] == []
    assert [one["review"] for one in after["library"]] == ["approved"]


def test_a_caller_without_the_authority_is_refused_every_write_before_anything_is_read(
    client: TestClient, stored: Stored
) -> None:
    """`u_narrow` may open the screen and holds neither authority: adding, deciding and assigning
    are each the screen's one refusal, and the library is never asked.

    Delete this and the screen's read becomes enough to write, or the refusal comes after a lookup
    and a digest typed by anybody answers whether that skill exists."""
    an_assignable_agent(stored)
    digest = "d" * 64

    refusals = [
        post(client, "u_narrow", SKILLS, a_package()),
        post(client, "u_narrow", f"{SKILLS}/{digest}/review", {"decision": "approve"}),
        post(client, "u_narrow", f"{SKILLS}/{digest}/assignments", {"agent_id": "company_desk"}),
        post(client, "u_wide", SKILLS, a_package()),
    ]

    assert [one.status_code for one in refusals] == [404, 404, 404, 404]
    assert {one.json()["message"] for one in refusals} == {screen_refusal(client)}
    assert stored.library.calls == []


def test_a_password_only_session_holds_no_authority_to_add_a_skill(
    client: TestClient, stored: Stored
) -> None:
    """The administrator signed in without a second factor is refused the write they are granted.

    Delete this and the authority to put a procedure in front of every agent is exercised from a
    session one stolen password opened, which is what `brain.gate.admission` withholds `admin:`
    for."""
    weak = post(client, "u_admin", SKILLS, a_package(), strong=False)
    strong = post(client, "u_admin", SKILLS, a_package())

    assert weak.status_code == 404
    assert weak.json()["message"] == screen_refusal(client)
    assert strong.status_code == 201


def test_the_reviewer_approves_and_a_reader_who_only_adds_is_refused_the_decision(
    client: TestClient, stored: Stored
) -> None:
    """The review authority decides; the skill authority does not, whoever added the skill.

    Delete this and the authority to add a skill is an authority to approve one, and the queue is
    reviewed by the people filling it."""
    digest = post(client, "u_admin", SKILLS, a_package()).json()["digest"]

    refused = post(client, "u_elsewhere", f"{SKILLS}/{digest}/review", {"decision": "reject"})
    rejected = post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "reject"})
    twice = post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})

    assert refused.status_code == 404
    assert rejected.status_code == 200
    assert rejected.json()["review"] == "rejected"
    assert twice.status_code == 404
    assert "already rejected" in twice.json()["message"]


def test_a_rejected_skill_is_refused_assignment_and_nothing_is_written(
    client: TestClient, stored: Stored
) -> None:
    """Delete this and a skill a named person read and refused reaches an agent anyway."""
    an_assignable_agent(stored)
    digest = post(client, "u_admin", SKILLS, a_package()).json()["digest"]
    post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "reject"})
    before = stored.installs["company_desk"][0].effective_hash

    refused = post(
        client, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": "company_desk"}
    )

    assert refused.status_code == 404
    assert "cannot be pinned" in refused.json()["message"]
    assert stored.library.assigned == []
    assert stored.installs["company_desk"][0].effective_hash == before


def test_an_agent_outside_the_audience_or_the_authority_is_refused_as_one_that_does_not_exist(
    client: TestClient, stored: Stored
) -> None:
    """`u_elsewhere` assigns in finance: a finance agent is assigned, a web agent they cannot see
    and a company agent outside their authority are each the screen's one refusal, and so is an
    agent that does not exist.

    Delete this and a department's administrator assigns skills to every department's agents, or
    learns which agents exist by trying."""
    an_assignable_agent(stored, "finance_desk", level=Visibility.DEPARTMENT, department="finance")
    an_assignable_agent(stored, "web_desk", level=Visibility.DEPARTMENT, department="web")
    an_assignable_agent(stored, "company_desk")
    digest = post(client, "u_admin", SKILLS, a_package()).json()["digest"]
    post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})

    def assign(agent_id: str) -> Response:
        return post(client, "u_elsewhere", f"{SKILLS}/{digest}/assignments", {"agent_id": agent_id})

    finance = assign("finance_desk")
    hidden, outside, missing = assign("web_desk"), assign("company_desk"), assign("nobody_desk")

    assert finance.status_code == 201, finance.text
    assert finance.json()["reach"] == ["crm.read_client"]
    assert [one.status_code for one in (hidden, outside, missing)] == [404, 404, 404]
    assert {one.json()["message"] for one in (hidden, outside, missing)} == {screen_refusal(client)}


def test_an_agent_the_authority_covers_and_the_audience_does_not_is_refused_as_absent(
    client: TestClient, stored: Stored
) -> None:
    """`u_admin` holds the skill authority over everything and sits in web: a sales department's
    agent is inside their authority and outside their audience, and is refused as absent, while a
    company agent is assigned.

    Delete this and the audience check can be dropped from the assignment, because every other
    refusal above is also outside the caller's authority, and an administrator learns of, and
    configures, an agent the roster never listed to them."""
    an_assignable_agent(stored, "sales_desk", level=Visibility.DEPARTMENT, department="sales")
    an_assignable_agent(stored, "company_desk")
    digest = post(client, "u_admin", SKILLS, a_package()).json()["digest"]
    post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})

    hidden = post(client, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": "sales_desk"})
    seen = post(client, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": "company_desk"})

    assert hidden.status_code == 404
    assert hidden.json()["message"] == screen_refusal(client)
    assert seen.status_code == 201
    assert [one.agent_id for one in stored.library.assigned] == ["company_desk"]


def test_the_instructions_are_disclosed_only_to_a_reader_who_may_add_or_review(
    client: TestClient, stored: Stored
) -> None:
    """The body travels to the administrator and the reviewer, and not to a reader of the screen.

    Delete this and every reader of the Skills screen reads the procedure of a skill nobody has
    approved, which `brain.tools.skills.body_of` refuses to an agent for the reason that reading a
    procedure is most of running it."""
    post(client, "u_admin", SKILLS, a_package())

    bodies = {pid: get(client, pid).json()["library"][0]["body"] for pid in ("u_admin", "u_wide")}
    reader_row = get(client, "u_narrow").json()["library"][0]

    assert bodies == dict.fromkeys(bodies, "Look up the domain, then open a ticket.")
    assert reader_row["body"] is None
    assert reader_row["reviewable"] is False
    assert get(client, "u_wide").json()["library"][0]["reviewable"] is True


def test_a_package_that_does_not_parse_or_repeats_a_skill_is_refused_saying_why(
    client: TestClient, stored: Stored
) -> None:
    """A skill declaring a reach, the same bytes twice, and the same name spelt another way, each
    refused with a sentence, and none of them written.

    Delete this and the reason a person's package was refused is the screen's generic sentence, or a
    second spelling of a skill shares every ledger entry with the first."""
    reach_declared = post(
        client, "u_admin", SKILLS, a_package(text_with(capabilities="[write:client.name]"))
    )
    first = post(client, "u_admin", SKILLS, a_package())
    again = post(client, "u_admin", SKILLS, a_package())
    spelt = post(
        client,
        "u_admin",
        SKILLS,
        a_package(text_with(name="hosting_expiry", description="Checks domains a second way")),
    )
    not_base64 = post(
        client,
        "u_admin",
        SKILLS,
        {"file_name": "skill.zip", "content": "not base64!", "encoding": "base64"},
    )

    assert first.status_code == 201
    assert reach_declared.status_code == again.status_code == spelt.status_code == 404
    assert "declares no reach of its own" in reach_declared.json()["message"]
    assert "already in the library" in again.json()["message"]
    assert "same name spelt differently" in spelt.json()["message"]
    assert "could not be read" in not_base64.json()["message"]
    assert [one.name for one in stored.library.skills.values()] == ["hosting-expiry"]


def test_an_install_changed_since_it_was_read_is_refused_and_the_change_is_kept(
    client: TestClient, stored: Stored
) -> None:
    """The store is handed the hash the route read, and a store that finds another refuses.

    Delete this and an assignment overwrites an instruction edit made while it was being decided."""
    an_assignable_agent(stored)
    digest = post(client, "u_admin", SKILLS, a_package()).json()["digest"]
    post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})

    class Moving(Installs):
        async def agent(self, agent_id: str) -> FoundAgent | None:
            found = await super().agent(agent_id)
            assert found is not None
            return FoundAgent(record=found.record, install=found.install, effective_hash="0" * 64)

    client.app.state.agent_installs = Moving()  # type: ignore[attr-defined]
    refused = post(
        client, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": "company_desk"}
    )

    assert refused.status_code == 404
    assert "changed this agent after you opened it" in refused.json()["message"]
    assert stored.library.assigned == []
