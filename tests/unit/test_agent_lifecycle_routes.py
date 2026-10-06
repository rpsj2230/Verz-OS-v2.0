"""Enabling, disabling, archiving, handing on, duplicating and installing an agent, over HTTP.

Driven through the real application, signed in with the token machinery
`tests/fixtures/console_http.py` shares, with an in-memory `AgentLifecycles` put where
`brain.agent_lifecycle_routes.lifecycles_of` looks first. So these tests prove the routes'
decisions: who is refused with the one 404, what a stale page is told, what an archived agent is
told, and what a duplicate and an install make. The memory's `create` hands every draft to
`brain.agents.install_store.prepared`, the function `StoredAgentInstalls.finish` writes from, so
what an install answers here is what the store would write; that the rows and the ledger entries
reach PostgreSQL is `tests/unit/test_agent_lifecycle_store.py`.

Every agent is made by the product's own install flow from a signed manifest, rather than built as
a record, so its ceiling is what binding against a tool registry made of it.

Task ids: M27.11.6, M27.11.7, M13.7.4, M39.2.4.2
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import brain.agent_lifecycle_routes as lifecycle_routes
from brain.agent_lifecycle_routes import (
    ARCHIVE_PATH,
    CANNOT_CARRY_IT,
    CANNOT_TAKE_IT,
    CHANNELS_PATH,
    DISABLE_PATH,
    DUPLICATE_PATH,
    ENABLE_PATH,
    INSTALL_PATH,
    IT_MOVED,
    LEARNING_PATH,
    LIFECYCLE_PATH,
    MOVED,
    NO_CHANNEL_ANSWERS_NOWHERE,
    NO_SIGNING_KEY_HERE,
    NOT_THE_VERSION_CONFIRMED,
    PUBLICATION_PATH,
    REFUSED,
    STARTS_DISABLED_AT_SHADOW,
    TRANSFER_PATH,
    UNAVAILABLE,
    VERSION_PATH,
    AgentLifecycles,
    FoundAgent,
    channel_choices,
)
from brain.agent_routes import TEMPLATE_SCREEN, declared_channels, record_of
from brain.agents.creation import AGENT_INSTALL_CAPABILITY, install_draft
from brain.agents.install import InstallDraft, answer
from brain.agents.install_store import Finished, prepared
from brain.agents.lifecycle import (
    AGENT_LIFECYCLE_CAPABILITY,
    AGENT_PUBLICATION_CAPABILITY,
    archive,
    enable,
)
from brain.agents.model import ASKING_CHANNELS, AgentAudience, AgentRecord, AgentState, answering_on
from brain.agents.template import (
    LeashRung,
    ManifestAuthority,
    ManifestGuardrails,
    ManifestIdentity,
    SignedManifest,
    TemplateManifest,
    publish,
)
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connectors.registry import ConnectorRegistry
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, Grant
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.injection import AutonomyTier
from brain.knowledge.visibility import Visibility
from brain.ops.learning_signal_store import StoredLearningPauses
from brain.tools.registry import ToolRegistry
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_agent_routes import KEY, agent_row, an_invoice, person

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
SIGNED_AT = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
ENDED = datetime(2019, 1, 1, tzinfo=UTC)

EVERYWHERE = Scope.unrestricted()
GALLERY = (
    Grant(capability=screen(TEMPLATE_SCREEN).read.requires, scope=EVERYWHERE),
    Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
)

#: Who holds what. `u_admin` (web) holds both authorities everywhere and reads the gallery.
#: `u_narrow` (web) holds both in web alone. `u_wide` (sales) reads the gallery and holds neither
#: authority. `u_prefix` (web) holds both authorities and the visibility one, and not the gallery's
#: read. `u_none` holds
#: nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (
        *GALLERY,
        Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=EVERYWHERE),
        Grant(capability=AGENT_INSTALL_CAPABILITY, scope=EVERYWHERE),
    ),
    "u_narrow": (
        *GALLERY,
        Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=Scope.department("web")),
        Grant(capability=AGENT_INSTALL_CAPABILITY, scope=Scope.department("web")),
    ),
    "u_wide": GALLERY,
    "u_prefix": (
        Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=EVERYWHERE),
        Grant(capability=AGENT_INSTALL_CAPABILITY, scope=EVERYWHERE),
        Grant(capability=AGENT_PUBLICATION_CAPABILITY, scope=EVERYWHERE),
    ),
    "u_none": (),
    "u_elsewhere": (),
}

COMPANY = "pricing_desk"
WEB = "web_helper"
SALES = "sales_helper"
PRIVATE = "private_helper"
RETIRED = "old_helper"
LOOSE = "loose_agent"
MISSING = "no_such_agent"

TEMPLATE_ID = "invoice_desk"
VERSION = 2
PERSONA = "Answer briefly and name the invoice you read."


def manifest(rung: AutonomyTier = AutonomyTier.SHADOW) -> TemplateManifest:
    """A template that reads invoices, with its one leash target at `rung`."""
    return TemplateManifest(
        identity=ManifestIdentity(
            template_id=TEMPLATE_ID,
            version=VERSION,
            published_by="u_publisher",
            display_name="Invoice desk",
            summary="Answers a question about one invoice.",
        ),
        persona="Answer briefly.",
        authority=ManifestAuthority(
            capabilities=(Capability(value="read:invoice.reference"),),
            allowed_tools=("invoice.read",),
        ),
        guardrails=ManifestGuardrails(
            max_side_effect=SideEffect.NONE,
            leash=(LeashRung(target="invoice.read", rung=rung),),
        ),
    )


def signed(rung: AutonomyTier = AutonomyTier.SHADOW) -> SignedManifest:
    return publish(manifest(rung), key=KEY, signed_by="u_publisher", at=SIGNED_AT)


def tools(*sources: str) -> ToolRegistry:
    """A registry with one invoice-reading tool per source, as an install's binding reads it."""
    registry = ToolRegistry()
    for source in sources:
        registry.register(
            ToolDefinition(
                name=f"{source}.read_invoice",
                description="reads one invoice",
                entity="invoice",
                required_capability="read:invoice.reference",
                side_effect=SideEffect.NONE,
                identity_mode=IdentityMode.DELEGATED,
                source=source,
            ),
            an_invoice,
        )
    return registry


ONE_SOURCE = ("ledger",)
TWO_SOURCES = ("ledger", "books")


def installed(
    agent_id: str,
    audience: AgentAudience,
    *,
    state: AgentState = AgentState.ENABLED,
    sources: tuple[str, ...] = ONE_SOURCE,
) -> FoundAgent:
    """An agent made by the product's install flow, in the state asked for."""
    version = signed()
    draft = install_draft(version, agent_id=agent_id, maker_id="u_builder", display_name=None)
    draft = answer(draft, "persona", PERSONA)
    made = prepared(
        draft,
        key=KEY,
        audience=audience,
        registry=ConnectorRegistry(),
        tools=tools(*sources),
        at=SIGNED_AT,
    )
    record = made.record
    if state is AgentState.ENABLED:
        record = enable(record)
    elif state is AgentState.ARCHIVED:
        record = archive(record, now=SIGNED_AT)
    return FoundAgent(
        record=record,
        install=(version, made.instance),
        effective_hash=made.effective.config_hash,
    )


def everybody() -> dict[str, FoundAgent]:
    company = AgentAudience(level=Visibility.COMPANY, owner_id="u_steward")
    loose = record_of(agent_row(LOOSE))
    assert loose is not None
    return {
        COMPANY: installed(COMPANY, company),
        WEB: installed(
            WEB,
            AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_narrow", department="web"),
            state=AgentState.DISABLED,
        ),
        SALES: installed(
            SALES,
            AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_wide", department="sales"),
        ),
        PRIVATE: installed(PRIVATE, AgentAudience(level=Visibility.PERSONAL, owner_id="u_steward")),
        RETIRED: installed(RETIRED, company, state=AgentState.ARCHIVED),
        LOOSE: FoundAgent(record=loose, install=None, effective_hash=None),
    }


@dataclass
class Change:
    before: AgentRecord
    after: AgentRecord
    actor_id: str
    ent_hash: str
    trace_id: str


@dataclass
class Made:
    finished: Finished
    maker_id: str
    ent_hash: str


@dataclass
class Memory:
    """`AgentLifecycles` in memory, and every write it was asked for."""

    agents: dict[str, FoundAgent] = field(default_factory=everybody)
    versions: dict[tuple[str, int], SignedManifest] = field(
        default_factory=lambda: {(TEMPLATE_ID, VERSION): signed()}
    )
    people: dict[str, Principal] = field(default_factory=dict)
    changes: list[Change] = field(default_factory=list)
    made: list[Made] = field(default_factory=list)
    version_reads: int = 0
    #: When true, every change loses a race to somebody else's.
    racing: bool = False

    async def agent(self, agent_id: str) -> FoundAgent | None:
        return self.agents.get(agent_id)

    async def version(self, template_id: str, version: int) -> SignedManifest | None:
        self.version_reads += 1
        return self.versions.get((template_id, version))

    async def live_principal(self, principal_id: str) -> Principal | None:
        return self.people.get(principal_id)

    async def change(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        if self.racing:
            return False
        held = self.agents[before.agent_id]
        self.agents[before.agent_id] = replace(held, record=after)
        self.changes.append(Change(before, after, actor_id, ent_hash, trace_id))
        return True

    async def widen(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        if self.racing:
            return False
        held = self.agents[before.agent_id]
        self.agents[before.agent_id] = replace(held, record=after)
        self.changes.append(Change(before, after, actor_id, ent_hash, trace_id))
        return True

    async def change_channels(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        if self.racing:
            return False
        held = self.agents[before.agent_id]
        self.agents[before.agent_id] = replace(held, record=after)
        self.changes.append(Change(before, after, actor_id, ent_hash, trace_id))
        return True

    async def create(
        self,
        draft: InstallDraft,
        *,
        key: str,
        registry: ConnectorRegistry,
        tools: ToolRegistry,
        at: datetime,
        ent_hash: str,
        trace_id: str,
        audience: AgentAudience,
        channels: tuple[str, ...] = (),
    ) -> Finished:
        installation = prepared(
            draft,
            key=key,
            audience=audience,
            registry=registry,
            tools=tools,
            at=at,
            channels=channels,
        )
        agent_id = installation.record.agent_id
        if agent_id in self.agents:
            return Finished(installation=installation, created=False)
        self.agents[agent_id] = FoundAgent(
            record=installation.record,
            install=(draft.offer.signed, installation.instance),
            effective_hash=installation.effective.config_hash,
        )
        finished = Finished(installation=installation, created=True)
        self.made.append(Made(finished, draft.installer, ent_hash))
        return finished


@dataclass
class Console:
    client: TestClient
    app: FastAPI
    memory: Memory

    def post(self, pid: str, path: str, body: Mapping[str, Any], *, strong: bool = True) -> Any:
        return self.client.post(
            f"{API_PREFIX}{path}", json=dict(body), headers=headers(pid, strong=strong)
        )

    def get(self, pid: str, path: str, *, strong: bool = True) -> Any:
        return self.client.get(f"{API_PREFIX}{path}", headers=headers(pid, strong=strong))


@pytest.fixture
def console() -> Iterator[Console]:
    """The real application, with the memory, a signing key and a one-source tool registry."""
    app = create_app(Settings(env="development"))
    memory = Memory()
    assert isinstance(memory, AgentLifecycles)
    with TestClient(app) as client:
        app.state.gate = gate_wiring(GRANTS)
        app.state.db_sessions = None
        app.state.agent_lifecycles = memory
        app.state.template_key = KEY
        app.state.tools = tools(*ONE_SOURCE)
        yield Console(client=client, app=app, memory=memory)


def path(template: str, **values: object) -> str:
    return template.format(**values)


def state_of(console: Console, agent_id: str) -> AgentState:
    return console.memory.agents[agent_id].record.state


def channels_of(console: Console, agent_id: str) -> tuple[str, ...]:
    return console.memory.agents[agent_id].record.channels


def refusal(response: Any) -> tuple[int, str]:
    """A refusal as a person reads it: the status and the sentence, never the trace id."""
    return response.status_code, response.json()["message"]


def not_changed(response: Any) -> tuple[int, str, str]:
    body = response.json()
    return response.status_code, body["outcome"], body["sentence"]


# ------------------------------------------------------------------ each move, pressed


def test_a_disabled_agent_is_enabled_and_the_store_is_told_who_did_it(console: Console) -> None:
    """The positive path of enable: 200, the agent reads enabled, and exactly one write was asked
    for, naming the person and carrying the request's reach digest.

    Delete this and the refusals below are satisfied by a route that refuses everybody, and the
    ledger's actor could be anybody the store was not told about."""
    response = console.post(
        "u_admin", path(ENABLE_PATH, agent_id=WEB), {"expected_state": "disabled"}
    )

    assert response.status_code == 200
    assert response.json()["state"] == "enabled"
    assert state_of(console, WEB) is AgentState.ENABLED
    [change] = console.memory.changes
    assert (change.before.state, change.after.state) == (AgentState.DISABLED, AgentState.ENABLED)
    assert change.actor_id == "u_admin"
    assert re.fullmatch(r"[0-9a-f]{32}", change.ent_hash)


def test_disable_then_archive_each_move_the_agent_once_and_name_the_person(
    console: Console,
) -> None:
    """Disable and archive, each pressed with the state the page drew after the last press.

    Delete this and either route can stop writing, or archive can write a state that is not
    archived, with enable's test still green."""
    disabled = console.post(
        "u_admin", path(DISABLE_PATH, agent_id=COMPANY), {"expected_state": "enabled"}
    )
    archived = console.post(
        "u_admin", path(ARCHIVE_PATH, agent_id=COMPANY), {"expected_state": "disabled"}
    )

    assert (disabled.status_code, disabled.json()["state"]) == (200, "disabled")
    assert (archived.status_code, archived.json()["state"]) == (200, "archived")
    assert [(one.after.state, one.actor_id) for one in console.memory.changes] == [
        (AgentState.DISABLED, "u_admin"),
        (AgentState.ARCHIVED, "u_admin"),
    ]
    assert console.memory.agents[COMPANY].record.archived_at is not None


def test_a_transfer_hands_the_agent_to_somebody_here_and_names_who_handed_it(
    console: Console,
) -> None:
    """The steward moves, nothing else about the agent does, and the write names the person.

    Delete this and a leaver's agents have no route to a new steward, which is M13.1.5's whole
    point, while the refusals of a transfer stay green."""
    console.memory.people["u_wide"] = person("u_wide")
    before = console.memory.agents[COMPANY].record

    response = console.post(
        "u_admin",
        path(TRANSFER_PATH, agent_id=COMPANY),
        {"to_owner": "u_wide", "expected_owner": "u_steward"},
    )

    assert response.status_code == 200
    assert response.json()["owner_id"] == "u_wide"
    after = console.memory.agents[COMPANY].record
    assert after.audience.owner_id == "u_wide"
    assert after.authority == before.authority
    assert [(one.actor_id, one.after.audience.owner_id) for one in console.memory.changes] == [
        ("u_admin", "u_wide")
    ]


# ------------------------------------------------------------------ who is refused


def test_every_reason_a_caller_may_not_act_is_the_one_404_a_missing_agent_gets(
    console: Console,
) -> None:
    """No authority, authority in another department, outside the audience, and a personal agent
    that is somebody else's: each is the status and sentence an agent that does not exist gets, on
    every route that names an agent, the channel switch included, and none of them wrote. A
    sign-in without a second factor is a 404 too, in the weak sign-in's own sentence.

    Delete this and a route can answer "not yours" where the workspace answers "not found", which
    lets anybody holding a sign-in list the company's agents by trying slugs."""
    missing = {
        "lifecycle": refusal(console.get("u_admin", path(LIFECYCLE_PATH, agent_id=MISSING))),
        "enable": refusal(
            console.post(
                "u_admin", path(ENABLE_PATH, agent_id=MISSING), {"expected_state": "disabled"}
            )
        ),
        "transfer": refusal(
            console.post(
                "u_admin",
                path(TRANSFER_PATH, agent_id=MISSING),
                {"to_owner": "u_wide", "expected_owner": "u_steward"},
            )
        ),
        "duplicate": refusal(
            console.post(
                "u_admin",
                path(DUPLICATE_PATH, agent_id=MISSING),
                {"display_name": "Copy", "expected_hash": "a" * 64},
            )
        ),
        "channels": refusal(
            console.post(
                "u_admin", path(CHANNELS_PATH, agent_id=MISSING), {"channels": [], "expected": []}
            )
        ),
    }
    assert missing["lifecycle"][0] == 404
    assert len(set(missing.values())) == 1

    cases = (
        ("u_wide", COMPANY, True),  # no authority at all
        ("u_none", COMPANY, True),  # nothing
        ("u_narrow", COMPANY, True),  # authority in web; a company agent's row has no department
        ("u_admin", SALES, True),  # authority everywhere, outside the audience
        ("u_admin", PRIVATE, True),  # somebody else's personal agent
    )
    for pid, agent_id, strong in cases:
        seen = {
            "lifecycle": refusal(
                console.get(pid, path(LIFECYCLE_PATH, agent_id=agent_id), strong=strong)
            ),
            "enable": refusal(
                console.post(
                    pid,
                    path(ENABLE_PATH, agent_id=agent_id),
                    {"expected_state": state_of(console, agent_id).value},
                    strong=strong,
                )
            ),
            "transfer": refusal(
                console.post(
                    pid,
                    path(TRANSFER_PATH, agent_id=agent_id),
                    {"to_owner": "u_wide", "expected_owner": "u_steward"},
                    strong=strong,
                )
            ),
            "duplicate": refusal(
                console.post(
                    pid,
                    path(DUPLICATE_PATH, agent_id=agent_id),
                    {
                        "display_name": "Copy",
                        "expected_hash": console.memory.agents[agent_id].effective_hash,
                    },
                    strong=strong,
                )
            ),
            "channels": refusal(
                console.post(
                    pid,
                    path(CHANNELS_PATH, agent_id=agent_id),
                    {"channels": ["email"], "expected": list(channels_of(console, agent_id))},
                    strong=strong,
                )
            ),
        }
        assert seen == missing, (pid, agent_id, strong)
    # Without a second factor the answer is still a 404, in the sentence every administrative
    # route gives a weak sign-in since W0.2, and nothing is written.
    weak = console.post(
        "u_admin", path(ENABLE_PATH, agent_id=COMPANY), {"expected_state": "enabled"}, strong=False
    )
    assert weak.status_code == 404
    assert console.memory.changes == []
    assert console.memory.made == []


def test_authority_held_over_a_department_acts_on_that_departments_agent(
    console: Console,
) -> None:
    """The sibling of the refusal above for `u_narrow`: authority in web moves web's agent.

    Delete this and the scope check could refuse every grant that is not over everything, which
    would leave a department's own administrator unable to switch its agents off."""
    response = console.post(
        "u_narrow", path(ENABLE_PATH, agent_id=WEB), {"expected_state": "disabled"}
    )

    assert response.status_code == 200
    assert [one.actor_id for one in console.memory.changes] == ["u_narrow"]


# ------------------------------------------------------------------ what a person is told


def test_an_archived_agent_cannot_be_enabled_and_is_told_so_in_a_sentence(
    console: Console,
) -> None:
    """A page that drew an archived agent and pressed Enable reads why in words, and nothing is
    written.

    Delete this and archive stops being terminal from the console, or the refusal becomes the 404
    that means "not yours", which tells an administrator nothing they can act on."""
    response = console.post(
        "u_admin", path(ENABLE_PATH, agent_id=RETIRED), {"expected_state": "archived"}
    )

    status, outcome, sentence = not_changed(response)
    assert (status, outcome) == (409, REFUSED)
    assert "cannot be enabled" in sentence
    assert "archived" in sentence
    assert state_of(console, RETIRED) is AgentState.ARCHIVED
    assert console.memory.changes == []


def test_a_stale_state_steward_hash_or_digest_changes_nothing(console: Console) -> None:
    """Each move names what the page drew, and each mismatch is the same 409 with nothing written.

    Delete this and a page opened before somebody else archived, handed on or edited an agent can
    act on a state its reader never saw."""
    console.memory.people["u_wide"] = person("u_wide")
    enabled = console.post(
        "u_admin", path(ENABLE_PATH, agent_id=WEB), {"expected_state": "enabled"}
    )
    handed = console.post(
        "u_admin",
        path(TRANSFER_PATH, agent_id=COMPANY),
        {"to_owner": "u_wide", "expected_owner": "u_narrow"},
    )
    copied = console.post(
        "u_admin",
        path(DUPLICATE_PATH, agent_id=COMPANY),
        {"display_name": "Copy", "expected_hash": "b" * 64},
    )
    installed_ = console.post(
        "u_admin",
        path(INSTALL_PATH, template_id=TEMPLATE_ID, version=VERSION),
        {"expected_digest": "c" * 64},
    )

    assert not_changed(enabled) == (409, MOVED, IT_MOVED)
    assert not_changed(handed) == (409, MOVED, IT_MOVED)
    assert not_changed(copied) == (409, MOVED, IT_MOVED)
    assert not_changed(installed_) == (409, MOVED, NOT_THE_VERSION_CONFIRMED)
    assert console.memory.changes == []
    assert console.memory.made == []


def test_a_move_that_loses_a_race_to_another_administrator_says_it_moved(
    console: Console,
) -> None:
    """The page was right when it was drawn and the row moved before the write: the store's
    compare-and-set finds nothing, and the answer is the stale page's.

    Delete this and a lost race answers 200 with a state the database does not hold."""
    console.memory.racing = True

    response = console.post(
        "u_admin", path(DISABLE_PATH, agent_id=COMPANY), {"expected_state": "enabled"}
    )

    assert not_changed(response) == (409, MOVED, IT_MOVED)
    assert state_of(console, COMPANY) is AgentState.ENABLED


def test_a_steward_who_has_left_and_one_who_never_existed_are_one_sentence(
    console: Console,
) -> None:
    """Handing an agent to an ended engagement and to an id nobody holds read the same, and
    neither moves the steward.

    Delete this and the transfer route answers "who works here" for anybody holding the lifecycle
    authority, and a leaver's agents can be handed to another leaver."""
    console.memory.people["u_gone"] = Principal(
        id="u_gone",
        kind=PrincipalKind.HUMAN,
        employment=Employment.CONTRACTOR,
        display_name="Gone",
        not_after=ENDED,
    )
    body = {"expected_owner": "u_steward"}
    gone = console.post(
        "u_admin", path(TRANSFER_PATH, agent_id=COMPANY), {**body, "to_owner": "u_gone"}
    )
    nobody = console.post(
        "u_admin", path(TRANSFER_PATH, agent_id=COMPANY), {**body, "to_owner": "u_nobody"}
    )

    assert not_changed(gone) == not_changed(nobody) == (409, REFUSED, CANNOT_TAKE_IT)
    assert console.memory.agents[COMPANY].record.audience.owner_id == "u_steward"


# ------------------------------------------------------------------ a duplicate


def test_a_duplicate_is_a_new_disabled_agent_from_the_same_version_with_the_same_ceiling(
    console: Console,
) -> None:
    """A new id and name, the version and overlay of the source, its authority exactly, disabled,
    seen by its maker alone, and made by the person who pressed.

    Delete this and the widening refusal below is satisfied by a route that duplicates nothing."""
    source = console.memory.agents[COMPANY]
    assert source.install is not None

    response = console.post(
        "u_admin",
        path(DUPLICATE_PATH, agent_id=COMPANY),
        {"display_name": "Pricing desk for tenders", "expected_hash": source.effective_hash},
    )

    assert response.status_code == 201
    [made] = console.memory.made
    installation = made.finished.installation
    copy = installation.record
    assert made.maker_id == "u_admin"
    assert response.json()["agent"]["agent_id"] == copy.agent_id != COMPANY
    assert copy.agent_id.startswith("pricing_desk_for_tenders_")
    assert copy.display_name == "Pricing desk for tenders"
    assert copy.state is AgentState.DISABLED
    assert copy.authority == source.record.authority
    assert copy.audience == AgentAudience(level=Visibility.PERSONAL, owner_id="u_admin")
    assert installation.instance.content_digest == source.install[1].content_digest
    assert installation.instance.overlay["persona"] == PERSONA


def test_a_duplicate_answers_on_the_channels_its_source_answers_on(console: Console) -> None:
    """**M13.7.4.** Duplicating asks nothing about channels, so the copy is switched on where the
    agent it copies is. Delete this and every duplicate is made mute without anybody being told."""
    source = console.memory.agents[COMPANY]
    console.memory.agents[COMPANY] = replace(
        source, record=answering_on(source.record, ("lark", "console"))
    )

    response = console.post(
        "u_admin",
        path(DUPLICATE_PATH, agent_id=COMPANY),
        {"display_name": "Pricing desk copy", "expected_hash": source.effective_hash},
    )

    assert response.status_code == 201
    [made] = console.memory.made
    assert made.finished.installation.record.channels == ("console", "lark")


def test_a_duplicate_never_reaches_a_tool_its_source_was_never_bound_to(
    console: Console,
) -> None:
    """A second system registered for invoices since the source was installed would bind a second
    tool into the copy: the duplicate is refused, naming the tool, and nothing is made.

    Delete this and duplicating an agent is a way to widen it, past the publish gate that exists
    to catch exactly that."""
    console.app.state.tools = tools(*TWO_SOURCES)
    source = console.memory.agents[COMPANY]

    response = console.post(
        "u_admin",
        path(DUPLICATE_PATH, agent_id=COMPANY),
        {"display_name": "Wider copy", "expected_hash": source.effective_hash},
    )

    status, outcome, sentence = not_changed(response)
    assert (status, outcome) == (409, REFUSED)
    assert "books.read_invoice" in sentence
    assert console.memory.made == []


def test_an_agent_with_no_install_has_no_version_to_duplicate_from(console: Console) -> None:
    """Said in words to a caller who may duplicate, and offered as unavailable on the view.

    Delete this and a duplicate of an agent seeded without an install fails as a 500."""
    view = console.get("u_admin", path(LIFECYCLE_PATH, agent_id=LOOSE)).json()
    response = console.post(
        "u_admin",
        path(DUPLICATE_PATH, agent_id=LOOSE),
        {"display_name": "Copy", "expected_hash": "a" * 64},
    )

    assert (view["may_duplicate"], view["duplicate_unavailable"]) == (
        False,
        not_changed(response)[2],
    )
    assert not_changed(response)[:2] == (409, REFUSED)


# ------------------------------------------------------------------ an install


def test_an_installed_version_starts_disabled_and_at_shadow_on_every_target(
    console: Console,
) -> None:
    """The version answers its digest and the sentence a person confirms; the install made with
    that digest is a minted id, disabled, with every leash target at Shadow.

    Delete this and an install from the console could be live in every picker on the press of
    Install, or start with a rung above Shadow."""
    version = console.get(
        "u_admin", path(VERSION_PATH, template_id=TEMPLATE_ID, version=VERSION)
    ).json()
    assert (version["starts"], version["unavailable"]) == (STARTS_DISABLED_AT_SHADOW, None)

    response = console.post(
        "u_admin",
        path(INSTALL_PATH, template_id=TEMPLATE_ID, version=VERSION),
        {"expected_digest": version["content_digest"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["agent"]["state"] == "disabled"
    assert body["leash"] and {one["rung"] for one in body["leash"]} == {"shadow"}
    [made] = console.memory.made
    record = made.finished.installation.record
    assert record.state is AgentState.DISABLED and record.disabled_at is not None
    assert {entry.rung for entry in made.finished.installation.leash.entries} == {
        AutonomyTier.SHADOW
    }
    assert re.fullmatch(r"invoice_desk_[0-9a-f]{6}", record.agent_id)
    assert made.maker_id == "u_admin"
    assert record.channels == ()


def test_an_install_answers_on_the_channels_ticked_and_refuses_one_nothing_is_asked_on(
    console: Console,
) -> None:
    """**M13.7.4.** The version offers every channel an agent may answer on, unticked, with the
    sentence that none answers nowhere; the ticked ones are stored on the new agent, and a channel
    outside the list is a 422 that installs nothing. Delete this and the template install either
    drops the boxes on the way to the row or stores a box that switches nothing on."""
    version = console.get(
        "u_admin", path(VERSION_PATH, template_id=TEMPLATE_ID, version=VERSION)
    ).json()
    assert [one["name"] for one in version["channels"]] == list(ASKING_CHANNELS)
    assert version["channels_note"] == NO_CHANNEL_ANSWERS_NOWHERE
    target = path(INSTALL_PATH, template_id=TEMPLATE_ID, version=VERSION)

    refused = console.post(
        "u_admin",
        target,
        {"expected_digest": version["content_digest"], "channels": ["scheduler"]},
    )
    assert refused.status_code == 422
    assert console.memory.made == []

    made = console.post(
        "u_admin",
        target,
        {"expected_digest": version["content_digest"], "channels": ["whatsapp", "console"]},
    )
    assert made.status_code == 201
    [one] = console.memory.made
    assert one.finished.installation.record.channels == ("console", "whatsapp")


def test_a_version_whose_leash_starts_above_shadow_is_unavailable_and_installs_nothing(
    console: Console,
) -> None:
    """Offered with the reason it cannot be installed, and refused when pressed anyway.

    Delete this and a published version with a raised rung installs agents that act without a
    person on their first run."""
    raised = signed(AutonomyTier.ASSISTED)
    console.memory.versions[(TEMPLATE_ID, VERSION)] = raised

    version = console.get(
        "u_admin", path(VERSION_PATH, template_id=TEMPLATE_ID, version=VERSION)
    ).json()
    response = console.post(
        "u_admin",
        path(INSTALL_PATH, template_id=TEMPLATE_ID, version=VERSION),
        {"expected_digest": raised.content_digest},
    )

    assert version["unavailable"] is not None and "invoice.read" in version["unavailable"]
    status, outcome, sentence = not_changed(response)
    assert (status, outcome) == (409, REFUSED)
    assert "above Shadow" in sentence
    assert console.memory.made == []


def test_a_process_without_a_signing_key_installs_and_duplicates_nothing_and_says_so(
    console: Console,
) -> None:
    """Both routes answer the same sentence, and the view offers no duplicate and says why.

    Delete this and a process with no key verifies nothing, or fails with a 500 that reads as a
    fault rather than a decision nobody has made yet."""
    console.app.state.template_key = None
    digest = console.memory.versions[(TEMPLATE_ID, VERSION)].content_digest

    installed_ = console.post(
        "u_admin",
        path(INSTALL_PATH, template_id=TEMPLATE_ID, version=VERSION),
        {"expected_digest": digest},
    )
    copied = console.post(
        "u_admin",
        path(DUPLICATE_PATH, agent_id=COMPANY),
        {"display_name": "Copy", "expected_hash": console.memory.agents[COMPANY].effective_hash},
    )
    view = console.get("u_admin", path(LIFECYCLE_PATH, agent_id=COMPANY)).json()

    assert (
        not_changed(installed_)
        == not_changed(copied)
        == (
            409,
            UNAVAILABLE,
            NO_SIGNING_KEY_HERE,
        )
    )
    assert (view["may_duplicate"], view["duplicate_unavailable"]) == (False, NO_SIGNING_KEY_HERE)
    assert console.memory.made == []


def test_a_maker_whose_authority_is_one_department_makes_that_departments_agent_only(
    console: Console,
) -> None:
    """`u_narrow` holds the install authority in web: an agent seen by them alone is outside it
    and refused in words, and one seen by web is made, in web.

    Delete this and the new agent's row is never checked, so a department's administrator could
    make agents their authority does not reach."""
    digest = console.memory.versions[(TEMPLATE_ID, VERSION)].content_digest
    target = path(INSTALL_PATH, template_id=TEMPLATE_ID, version=VERSION)

    alone = console.post("u_narrow", target, {"expected_digest": digest})
    for_web = console.post("u_narrow", target, {"expected_digest": digest, "for_department": True})

    assert not_changed(alone)[:2] == (409, REFUSED)
    assert for_web.status_code == 201
    [made] = console.memory.made
    assert made.finished.installation.record.audience == AgentAudience(
        level=Visibility.DEPARTMENT, owner_id="u_narrow", department="web"
    )


def test_installing_is_refused_in_the_gallerys_words_without_its_read_and_nothing_is_read(
    console: Console,
) -> None:
    """Holding the install authority without the gallery's read, or the read without the
    authority, is the refusal a reader with neither gets, and no version is looked up for them.

    Delete this and the version route becomes a way round the gallery's own read."""
    target = path(VERSION_PATH, template_id=TEMPLATE_ID, version=VERSION)
    nothing = refusal(console.get("u_none", target))

    assert nothing[0] == 404
    assert refusal(console.get("u_prefix", target)) == nothing
    assert refusal(console.get("u_wide", target)) == nothing
    assert console.memory.version_reads == 0
    assert console.get("u_admin", target).status_code == 200


def test_the_lifecycle_view_says_what_the_reader_may_do(console: Console) -> None:
    """The state, the steward, the configuration hash a duplicate names, the channels and every
    control.

    Delete this and the console draws controls from a view that could say anything."""
    view = console.get("u_admin", path(LIFECYCLE_PATH, agent_id=COMPANY)).json()

    assert view == {
        "agent_id": COMPANY,
        "display_name": "Invoice desk",
        "state": "enabled",
        "owner_id": "u_steward",
        "effective_hash": console.memory.agents[COMPANY].effective_hash,
        "may_change": True,
        "may_duplicate": True,
        "duplicate_unavailable": None,
        "level": "company",
        "may_publish": False,
        "channels": list(console.memory.agents[COMPANY].record.channels),
        # Every channel but the website widget, which declares nothing it can carry yet.
        "channel_choices": [
            one.model_dump() for one in channel_choices() if one.name != Channel.WIDGET.value
        ],
        "channels_note": NO_CHANNEL_ANSWERS_NOWHERE,
        "may_change_channels": True,
    }
    # A department agent seen by somebody holding the visibility authority who is not its steward
    # is offered for publication; the same agent once company-wide is not.
    offered = console.get("u_prefix", path(LIFECYCLE_PATH, agent_id=WEB)).json()
    assert (offered["level"], offered["may_publish"]) == ("department", True)


# ------------------------------------------------------------ the learning switch (M16.7.13)
class KeptPauses(StoredLearningPauses):
    """`StoredLearningPauses` in memory: every pause and resume it was asked to write, in order."""

    def __init__(self) -> None:
        self.written: list[tuple[str, bool, str, str]] = []

    async def set(self, *, agent_id: str, paused: bool, reason: str, by: str) -> None:
        self.written.append((agent_id, paused, reason, by))

    async def paused(self, agent_ids: Collection[str]) -> frozenset[str]:
        latest: dict[str, bool] = {}
        for agent_id, paused, _, _ in self.written:
            latest[agent_id] = paused
        return frozenset(one for one in agent_ids if latest.get(one, False))


def test_an_agents_learning_is_paused_and_resumed_by_who_may_switch_it_off(
    console: Console,
) -> None:
    """**Each agent has a learning switch** (M16.7.13, CONA-23). Whoever holds the lifecycle
    authority over an agent pauses it with a reason, in their own name, reads it paused, and
    resumes it; somebody holding that authority in another department, and somebody with none,
    are the one 404 a missing agent gets and write nothing.

    Delete this and the switch can be pressed by anybody who can name an agent, or pressed and
    answered with nothing written."""
    pauses = KeptPauses()
    console.app.state.learning_pauses = pauses
    route = path(LEARNING_PATH, agent_id=COMPANY)

    before = console.get("u_admin", route)
    paused = console.post("u_admin", route, {"paused": True, "reason": "a wrong lesson"})
    read = console.get("u_admin", route)
    resumed = console.post("u_admin", route, {"paused": False, "reason": "fixed at source"})
    outside = console.post(
        "u_narrow", path(LEARNING_PATH, agent_id=SALES), {"paused": True, "reason": "x"}
    )
    nobody = console.post("u_none", route, {"paused": True, "reason": "x"})
    missing = console.post(
        "u_admin", path(LEARNING_PATH, agent_id=MISSING), {"paused": True, "reason": "x"}
    )

    assert (before.status_code, before.json()["paused"]) == (200, False)
    assert (paused.status_code, paused.json()["paused"]) == (200, True)
    assert read.json() == {"agent_id": COMPANY, "paused": True}
    assert resumed.json()["paused"] is False
    assert pauses.written == [
        (COMPANY, True, "a wrong lesson", "u_admin"),
        (COMPANY, False, "fixed at source", "u_admin"),
    ]
    assert refusal(outside) == refusal(nobody) == refusal(missing)
    assert refusal(missing)[0] == 404


# ------------------------------------------------------------------ a company-wide publication
def test_somebody_other_than_the_steward_publishes_a_department_agent_to_the_whole_company(
    console: Console,
) -> None:
    """The positive path (M33.1.2.1): a web agent stewarded by `u_narrow`, published by `u_prefix`,
    who holds the visibility authority. The agent becomes company-wide with no department, the
    store is told who did it, and the view says so.

    Delete this and every refusal below is satisfied by a route that refuses everybody."""
    published = console.post(
        "u_prefix", path(PUBLICATION_PATH, agent_id=WEB), {"expected_level": "department"}
    )

    assert published.status_code == 200, published.text
    assert published.json()["level"] == "company"
    record = console.memory.agents[WEB].record
    assert record.audience.level is Visibility.COMPANY
    assert record.audience.department == ""
    assert [(one.after.audience.level, one.actor_id) for one in console.memory.changes] == [
        (Visibility.COMPANY, "u_prefix")
    ]


def test_a_publication_is_refused_to_its_steward_to_a_stale_page_and_to_an_archived_agent(
    console: Console,
) -> None:
    """Three refusals, each a 409 that writes nothing: the agent's own steward publishing it, a page
    that drew another audience, and an archived agent. Delete this and a steward could publish
    their own agent alone, which `A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE` exists to stop."""
    held = console.memory.agents[WEB]
    console.memory.agents[WEB] = replace(
        held,
        record=held.record.model_copy(
            update={"audience": held.record.audience.model_copy(update={"owner_id": "u_prefix"})}
        ),
    )
    own = console.post(
        "u_prefix", path(PUBLICATION_PATH, agent_id=WEB), {"expected_level": "department"}
    )
    console.memory.agents[WEB] = held
    stale = console.post(
        "u_prefix", path(PUBLICATION_PATH, agent_id=WEB), {"expected_level": "personal"}
    )
    retired = console.post(
        "u_prefix", path(PUBLICATION_PATH, agent_id=RETIRED), {"expected_level": "company"}
    )

    assert not_changed(own)[:2] == (409, REFUSED)
    assert not_changed(stale) == (409, MOVED, IT_MOVED)
    assert not_changed(retired)[:2] == (409, REFUSED)
    assert console.memory.changes == []


def test_a_publication_by_somebody_without_the_visibility_authority_is_the_one_404(
    console: Console,
) -> None:
    """`u_admin` holds both lifecycle authorities and not the visibility one, and a hidden agent
    is the same 404. Delete this and the lifecycle authority would publish, which is the grant
    `brain.console.global_surfaces.PUBLISHING_WIDENS_WHO_IS_TOLD_AND_NEVER_WHAT_IS_REACHED` says
    it must not be."""
    nothing = refusal(console.get("u_admin", path(LIFECYCLE_PATH, agent_id=MISSING)))
    refused = console.post(
        "u_admin", path(PUBLICATION_PATH, agent_id=WEB), {"expected_level": "department"}
    )
    hidden = console.post(
        "u_prefix", path(PUBLICATION_PATH, agent_id=PRIVATE), {"expected_level": "personal"}
    )

    assert refusal(refused) == nothing
    assert refusal(hidden) == nothing
    assert console.memory.changes == []


# ------------------------------------------------------------------ channels (M13.7.4)
def test_an_agent_s_steward_switches_its_channels_and_the_store_is_told_who_did_it(
    console: Console,
) -> None:
    """**A_STEWARD_OR_AN_ADMINISTRATOR_SWITCHES_AN_AGENT_S_CHANNELS, the steward's half.** The
    steward holds no lifecycle authority and still switches the agent's channels; the view says
    so and the store is told who. Delete this and an existing agent can only be made answerable by
    an administrator, which leaves every steward's new agent mute until somebody else acts."""
    view = console.get("u_wide", path(LIFECYCLE_PATH, agent_id=SALES))
    switched = console.post(
        "u_wide",
        path(CHANNELS_PATH, agent_id=SALES),
        {"channels": ["lark", "console", "lark"], "expected": []},
    )

    assert view.status_code == 200
    assert view.json()["may_change_channels"] is True
    assert view.json()["channels"] == []
    assert switched.status_code == 200, switched.text
    assert switched.json()["channels"] == ["console", "lark"]
    [change] = console.memory.changes
    assert (change.before.channels, change.after.channels) == ((), ("console", "lark"))
    assert change.actor_id == "u_wide"


def test_an_administrator_over_the_row_switches_an_agent_s_channels(console: Console) -> None:
    """The administrator's half: a holder of the lifecycle authority over the agent's row who is
    not its steward. Delete this and the rule can narrow to the steward alone."""
    switched = console.post(
        "u_admin", path(CHANNELS_PATH, agent_id=COMPANY), {"channels": ["email"], "expected": []}
    )

    assert switched.status_code == 200, switched.text
    assert console.memory.agents[COMPANY].record.channels == ("email",)


def test_anybody_else_is_answered_as_if_the_agent_did_not_exist(console: Console) -> None:
    """A reader who sees the agent and is neither its steward nor an administrator over it gets the
    one 404 a missing agent gets, and nothing is written. Delete this and the route tells a reader
    which agents exist by answering them differently."""
    refused = console.post(
        "u_wide", path(CHANNELS_PATH, agent_id=COMPANY), {"channels": ["email"], "expected": []}
    )
    missing = console.post(
        "u_wide", path(CHANNELS_PATH, agent_id=MISSING), {"channels": ["email"], "expected": []}
    )

    assert refusal(refused) == refusal(missing)
    assert refused.status_code == 404
    assert console.memory.changes == []


def test_a_channel_nothing_can_ask_on_is_refused_and_a_stale_page_writes_nothing(
    console: Console,
) -> None:
    """A name that is not a channel a person can ask on is a 422, and a page that drew channels the
    agent no longer has is a 409; neither writes. Delete this and the route can store a channel
    nothing reads, or overwrite a switch somebody else just made."""
    unknown = console.post(
        "u_admin",
        path(CHANNELS_PATH, agent_id=COMPANY),
        {"channels": ["scheduler"], "expected": []},
    )
    stale = console.post(
        "u_admin",
        path(CHANNELS_PATH, agent_id=COMPANY),
        {"channels": ["email"], "expected": ["lark"]},
    )

    assert unknown.status_code == 422
    assert stale.status_code == 409
    assert console.memory.changes == []


def only_lark_is_declared(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deployment whose one adapter is Lark, so the real `channel_rows` offers Lark alone."""
    declared = declared_channels()
    monkeypatch.setattr(
        lifecycle_routes,
        "declared_channels",
        lambda: tuple(one for one in declared if one.channel is Channel.LARK),
    )


def test_a_channel_its_run_could_not_be_carried_on_is_not_switched_on_and_nothing_is_written(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**A_CHANNEL_IS_SWITCHED_ON_ONLY_WHERE_ITS_RUN_COULD_BE_CARRIED, the refusal (M39.2.4.2).**
    WhatsApp is not among the channels `channel_rows` offers this reader for this agent, so a
    switch onto it is the domain's refusal in its own sentence, and the boxes never offered it.
    Delete this and the switch can turn an agent on for a surface that cannot carry what it may
    answer, which is the offer the workspace refuses made anyway by a POST."""
    only_lark_is_declared(monkeypatch)

    view = console.get("u_admin", path(LIFECYCLE_PATH, agent_id=COMPANY)).json()
    refused = console.post(
        "u_admin",
        path(CHANNELS_PATH, agent_id=COMPANY),
        {"channels": ["lark", "whatsapp"], "expected": []},
    )

    assert [one["name"] for one in view["channel_choices"]] == ["console", "lark", "api"]
    assert refused.status_code == 409
    assert (refused.json()["outcome"], refused.json()["sentence"]) == (REFUSED, CANNOT_CARRY_IT)
    assert console.memory.changes == []


def test_a_channel_it_could_be_carried_on_is_switched_on_and_one_already_on_may_stay(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive sibling: Lark, which `channel_rows` offers, and the console, which answers the
    asker in their own session, are switched on; and a channel already on that would not be
    offered now (the widget) may stay on and be switched off, because only switching on is judged.
    Delete this and the rule can refuse every switch, or strand an agent on a channel nobody may
    now switch off."""
    only_lark_is_declared(monkeypatch)
    found = console.memory.agents[COMPANY]
    console.memory.agents[COMPANY] = replace(found, record=answering_on(found.record, ["widget"]))

    kept = console.post(
        "u_admin",
        path(CHANNELS_PATH, agent_id=COMPANY),
        {"channels": ["widget", "lark", "console"], "expected": ["widget"]},
    )
    off = console.post(
        "u_admin",
        path(CHANNELS_PATH, agent_id=COMPANY),
        {"channels": ["lark"], "expected": ["console", "lark", "widget"]},
    )

    assert kept.status_code == 200, kept.text
    assert "widget" in [one["name"] for one in kept.json()["channel_choices"]]
    assert off.status_code == 200, off.text
    assert console.memory.agents[COMPANY].record.channels == ("lark",)
