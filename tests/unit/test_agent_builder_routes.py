"""New agent and Edit as a draft, over HTTP: start, save, check, rehearse, publish and approve.

Driven through the real application, signed in with the token machinery
`tests/fixtures/console_http.py` shares, with an in-memory `AgentDraftStore` put where
`brain.agent_builder_routes.drafts_of` looks first. So these tests prove the routes' decisions:
who is refused with the one 404, what a stale page is told, when a publish goes out on its author's
word and when it waits for a second person, and who that second person may be. That the rows and
the ledger entries reach PostgreSQL is `tests/unit/test_agent_draft_store.py`.

Every published agent is made by the product's own install flow from a signed manifest, and every
edited agent was installed the same way, so what a publish answers here is what the store writes.

Task ids: M27.11.6, M27.15.31
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.agent_builder_routes import (
    A_REHEARSAL_RUNS_NO_MODEL_YET,
    AGENT_MOVED,
    ALREADY_PUBLISHED,
    APPROVE_PATH,
    CHECK_FIRST,
    CHECK_PATH,
    DECLINE_PATH,
    DRAFT_PATH,
    DRAFTS_PATH,
    EDIT_PATH,
    FORM_PATH,
    MOVED,
    NO_INSTALL_TO_START_FROM,
    PROCEDURE_PATH,
    PUBLISH_PATH,
    PUBLISHED_EDIT,
    PUBLISHED_NEW,
    REFUSED,
    REHEARSE_PATH,
    RUNG_PROBLEM,
    SAVE_PATH,
    SAVED_SINCE,
    UNAVAILABLE,
    WAITS_FOR_A_SECOND_PERSON,
)
from brain.agent_lifecycle_routes import NO_SIGNING_KEY_HERE, FoundAgent
from brain.agent_routes import TEMPLATE_SCREEN, record_of
from brain.agents.catalogue import CATALOGUE
from brain.agents.creation import AGENT_INSTALL_CAPABILITY
from brain.agents.install import Installation
from brain.agents.lifecycle import ARCHIVE_IS_TERMINAL
from brain.agents.model import AgentAudience, AgentState
from brain.agents.template import SignedManifest, TemplateManifest
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.builder.agent_drafts import (
    DOES_NOT_MAKE_AN_AGENT_YET,
    NOT_THE_AUTHOR,
    Act,
    AgentDraft,
)
from brain.builder.draft_store import AgentDraftStore, Attribution
from brain.builder.draft_words import DraftAct, DraftState
from brain.builder.drafts import Revision
from brain.builder.form import form_document
from brain.builder.publish import NAMES_THAT_WOULD_CARRY_ANOTHER_PERSONS_ROWS
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.knowledge.visibility import Visibility
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_agent_lifecycle_routes import installed, manifest, tools
from tests.unit.test_agent_routes import DEPARTMENTS, KEY, agent_row

EVERYWHERE = Scope.unrestricted()
GALLERY = (
    Grant(capability=screen(TEMPLATE_SCREEN).read.requires, scope=EVERYWHERE),
    Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
)
BUILDS = Grant(capability=AGENT_INSTALL_CAPABILITY, scope=EVERYWHERE)
READS = tuple(
    Grant(capability=Capability(value=one), scope=EVERYWHERE)
    for one in ("read:invoice", "read:invoice.reference", "read:invoice.total")
)

#: `u_admin` (web) builds everywhere, reads the gallery and reads invoices. `u_prefix` (web) builds
#: everywhere and reads invoices: the second person. `u_narrow` (web) builds in web and reads
#: nothing, so their reach cannot cover an agent that reads invoices. `u_wide` reads the gallery and
#: builds nothing. `u_none` holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (*GALLERY, BUILDS, *READS),
    "u_prefix": (BUILDS, *READS),
    "u_narrow": (Grant(capability=AGENT_INSTALL_CAPABILITY, scope=Scope.department("web")),),
    "u_wide": GALLERY,
    "u_none": (),
    "u_elsewhere": (),
    "u_admin_only": (),
}

COMPANY = "pricing_desk"
ARCHIVED = "old_desk"
LOOSE = "loose_agent"
PERSONA = "Answer one invoice question at a time and name the invoice you read."


def a_document(
    agent_id: str = "anything",
    *,
    name: str = "Invoice helper",
    persona: str = PERSONA,
    capabilities: Sequence[str] = ("read:invoice.reference",),
    tools_allowed: Sequence[str] = ("invoice.read",),
    rung: AutonomyTier = AutonomyTier.SHADOW,
) -> dict[str, Any]:
    """A whole manifest document in the manifest's own nesting, as the form submits one."""
    document: dict[str, Any] = manifest(rung).model_dump(mode="json")
    document["identity"] = {**document["identity"], "template_id": agent_id, "display_name": name}
    document["persona"] = persona
    document["authority"] = {
        **document["authority"],
        "capabilities": [{"value": one} for one in capabilities],
        "allowed_tools": list(tools_allowed),
    }
    if not tools_allowed:
        document["guardrails"] = {**document["guardrails"], "leash": []}
    return document


def reaching_nothing(agent_id: str = "anything") -> dict[str, Any]:
    return a_document(agent_id, capabilities=(), tools_allowed=())


# ------------------------------------------------------------------------------ the store
@dataclass
class Memory:
    """`AgentDraftStore` in memory, and every write it was asked for."""

    drafts: dict[str, AgentDraft] = field(default_factory=dict)
    agents: dict[str, FoundAgent] = field(default_factory=dict)
    versions: dict[str, list[int]] = field(default_factory=dict)
    published_templates: dict[str, TemplateManifest] = field(default_factory=dict)
    writers: list[Attribution] = field(default_factory=list)

    async def draft(self, draft_id: str) -> AgentDraft | None:
        return self.drafts.get(draft_id)

    async def drafts_owned_by(self, owner_id: str) -> tuple[AgentDraft, ...]:
        return tuple(one for one in self.drafts.values() if one.owner_id == owner_id)

    async def waiting(self) -> tuple[AgentDraft, ...]:
        return tuple(
            one
            for one in self.drafts.values()
            if any(act.act is DraftAct.REQUESTED for act in one.acts)
        )

    async def agent(self, agent_id: str) -> FoundAgent | None:
        return self.agents.get(agent_id)

    async def versions_of(self, template_id: str) -> tuple[int, ...]:
        return tuple(self.versions.get(template_id, ()))

    async def department_of(self, principal_id: str) -> str | None:
        return DEPARTMENTS.get(principal_id)

    async def newest_published(self, template_id: str) -> TemplateManifest | None:
        return self.published_templates.get(template_id)

    async def start(self, draft: AgentDraft, first: Revision, *, by: Attribution) -> None:
        self.writers.append(by)
        self.drafts[draft.draft_id] = replace(draft, revisions=(first,))

    async def append(self, revision: Revision, *, by: Attribution) -> bool:
        held = self.drafts[revision.draft_id]
        if held.revisions and held.revisions[-1].number >= revision.number:
            return False
        self.writers.append(by)
        self.drafts[revision.draft_id] = replace(held, revisions=(*held.revisions, revision))
        return True

    async def record(self, draft_id: str, act: Act, *, by: Attribution) -> bool:
        held = self.drafts[draft_id]
        if held.act_named(act.revision, act.act) is not None:
            return False
        self.writers.append(by)
        self.drafts[draft_id] = replace(held, acts=(*held.acts, act))
        return True

    def _acts(self, draft_id: str, acts: Sequence[Act]) -> None:
        held = self.drafts[draft_id]
        self.drafts[draft_id] = replace(held, acts=(*held.acts, *acts))

    async def publish_new(
        self,
        draft_id: str,
        acts: Sequence[Act],
        signed: SignedManifest,
        installation: Installation,
        *,
        by: Attribution,
    ) -> bool:
        agent_id = installation.record.agent_id
        if agent_id in self.agents:
            return False
        self.writers.append(by)
        self.agents[agent_id] = FoundAgent(
            record=installation.record,
            install=(signed, installation.instance),
            effective_hash=installation.effective.config_hash,
        )
        self.versions.setdefault(agent_id, []).append(signed.manifest.identity.version)
        self._acts(draft_id, acts)
        return True

    async def publish_edit(
        self,
        draft_id: str,
        acts: Sequence[Act],
        signed: SignedManifest,
        installation: Installation,
        *,
        base_hash: str,
        disabled_at: datetime | None,
        by: Attribution,
    ) -> bool:
        agent_id = installation.record.agent_id
        held = self.agents[agent_id]
        if held.effective_hash != base_hash or held.record.archived_at is not None:
            return False
        self.writers.append(by)
        record = installation.record.model_copy(
            update={
                "audience": held.record.audience,
                "created_by": held.record.created_by,
                "disabled_at": disabled_at,
            }
        )
        self.agents[agent_id] = FoundAgent(
            record=record,
            install=(signed, installation.instance),
            effective_hash=installation.effective.config_hash,
        )
        self.versions.setdefault(agent_id, []).append(signed.manifest.identity.version)
        self._acts(draft_id, acts)
        return True


def everybody() -> dict[str, FoundAgent]:
    company = AgentAudience(level=Visibility.COMPANY, owner_id="u_steward")
    loose = record_of(agent_row(LOOSE))
    assert loose is not None
    return {
        COMPANY: installed(COMPANY, company, state=AgentState.ENABLED),
        ARCHIVED: installed(ARCHIVED, company, state=AgentState.ARCHIVED),
        LOOSE: FoundAgent(record=loose, install=None, effective_hash=None),
    }


@dataclass
class Console:
    client: TestClient
    app: FastAPI
    memory: Memory

    def post(self, pid: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        return self.client.post(f"{API_PREFIX}{path}", json=dict(body or {}), headers=headers(pid))

    def get(self, pid: str, path: str) -> Any:
        return self.client.get(f"{API_PREFIX}{path}", headers=headers(pid))


@pytest.fixture
def console() -> Iterator[Console]:
    """The real application, with the memory, a signing key and a one-source tool registry."""
    app = create_app(Settings(env="development"))
    memory = Memory(agents=everybody())
    assert isinstance(memory, AgentDraftStore)
    with TestClient(app) as client:
        app.state.gate = gate_wiring(GRANTS)
        app.state.db_sessions = None
        app.state.agent_drafts = memory
        app.state.template_key = KEY
        app.state.tools = tools("ledger")
        yield Console(client=client, app=app, memory=memory)


def at(template: str, **values: object) -> str:
    return template.format(**values)


def not_changed(response: Any) -> tuple[int, str, str]:
    body = response.json()
    return response.status_code, body["outcome"], body["sentence"]


def started(console: Console, pid: str = "u_admin", **body: Any) -> dict[str, Any]:
    response = console.post(pid, DRAFTS_PATH, body)
    assert response.status_code == 201, response.text
    view: dict[str, Any] = response.json()
    return view


def saved(console: Console, draft: Mapping[str, Any], document: Mapping[str, Any]) -> int:
    response = console.post(
        "u_admin",
        at(SAVE_PATH, draft_id=draft["draft_id"]),
        {"document": dict(document), "base": draft["revision"]},
    )
    assert response.status_code == 200, response.text
    number: int = response.json()["revision"]
    return number


def checked(console: Console, draft_id: str, revision: int, pid: str = "u_admin") -> Any:
    return console.post(pid, at(CHECK_PATH, draft_id=draft_id), {"revision": revision})


def ready(console: Console, document: Mapping[str, Any]) -> tuple[str, int]:
    """A new draft holding `document`, saved and checked, and its revision."""
    draft = started(console)
    revision = saved(console, draft, document)
    assert checked(console, draft["draft_id"], revision).json()["passed"]
    return draft["draft_id"], revision


# ------------------------------------------------------------------ the form and the one 404
def test_the_form_is_the_builders_own_document_and_nobody_else_is_given_it(
    console: Console,
) -> None:
    """The form served is `form_document()` whole, and a reader who cannot build gets the one 404.

    Delete this and the console could render a form the server does not describe, or the form
    could be served to anybody, which lists what an agent may be given."""
    given = console.get("u_admin", FORM_PATH)
    refused = console.get("u_wide", FORM_PATH)

    assert given.status_code == 200
    assert given.json() == form_document()
    assert refused.status_code == 404


def test_a_draft_somebody_else_wrote_is_answered_as_a_draft_that_does_not_exist(
    console: Console,
) -> None:
    """Another builder, a reader without the capability and a made-up id get one body.

    Delete this and one request per id would say which drafts exist and that somebody is building
    them, which `A_DRAFT_SOMEBODY_ELSE_OWNS_IS_A_DRAFT_THAT_DOES_NOT_EXIST` refuses."""
    draft = started(console)
    theirs = console.get("u_prefix", at(DRAFT_PATH, draft_id=draft["draft_id"]))
    unbuilt = console.get("u_wide", at(DRAFT_PATH, draft_id=draft["draft_id"]))
    missing = console.get(
        "u_prefix", at(DRAFT_PATH, draft_id="00000000-0000-4000-8000-000000000000")
    )
    mine = console.get("u_admin", at(DRAFT_PATH, draft_id=draft["draft_id"]))

    assert {theirs.status_code, unbuilt.status_code, missing.status_code} == {404}
    assert theirs.json()["message"] == missing.json()["message"] == unbuilt.json()["message"]
    assert mine.status_code == 200
    assert mine.json()["yours"] is True


# ------------------------------------------------------------------------- starting a draft
def test_a_new_draft_starts_from_the_blank_template_under_an_id_minted_for_it(
    console: Console,
) -> None:
    """The first revision is the blank template named "New agent", addressed to the minted id.

    Delete this and a new draft could start with somebody's typed id, which answers "taken" for an
    agent the person may not see, or with no document to fill in."""
    draft = started(console)

    assert draft["kind"] == "new"
    assert draft["state"] == DraftState.DRAFT.value
    assert draft["revision"] == 1
    assert re.fullmatch(r"agent_[0-9a-f]{6}", draft["agent_id"])
    assert draft["document"]["identity"]["template_id"] == draft["agent_id"]
    assert draft["document"]["identity"]["display_name"] == "New agent"
    assert draft["document"]["guardrails"] == {"max_side_effect": "none", "leash": []}


def test_a_draft_from_a_template_starts_from_its_words_under_an_id_of_its_own(
    console: Console,
) -> None:
    """A built-in template seeds the draft, and a template nobody offers is refused.

    Delete this and "start from a template" could seed an empty draft, or the template's own id,
    which would make an edit of this agent a new version of the shared template."""
    template = CATALOGUE[0]
    draft = started(console, template_id=template.identity.template_id)
    unknown = console.post("u_admin", DRAFTS_PATH, {"template_id": "no_such_template"})
    no_gallery = console.post(
        "u_prefix", DRAFTS_PATH, {"template_id": template.identity.template_id}
    )

    assert draft["document"]["persona"] == template.persona
    assert draft["document"]["identity"]["template_id"] == draft["agent_id"]
    assert draft["agent_id"] != template.identity.template_id
    assert unknown.status_code == 404
    assert no_gallery.status_code == 404


# ------------------------------------------------------------------------------ saving
def test_a_save_is_a_new_revision_and_a_save_from_an_older_one_is_refused(
    console: Console,
) -> None:
    """Two saves make revisions two and three, the same body again returns three, and a save made
    from revision two after three exists changes nothing.

    Delete this and a second tab can bury the first tab's save, which is
    `A_SAVE_FROM_AN_OLDER_REVISION_WOULD_HIDE_THE_ONE_IN_BETWEEN`."""
    draft = started(console)
    path = at(SAVE_PATH, draft_id=draft["draft_id"])
    second = console.post("u_admin", path, {"document": a_document(), "base": 1})
    third = console.post("u_admin", path, {"document": a_document(name="Invoice desk"), "base": 2})
    again = console.post("u_admin", path, {"document": a_document(name="Invoice desk"), "base": 2})
    stale = console.post("u_admin", path, {"document": a_document(name="Other"), "base": 2})

    assert (second.json()["revision"], third.json()["revision"]) == (2, 3)
    assert again.json()["revision"] == 3
    assert not_changed(stale) == (409, MOVED, SAVED_SINCE)
    held = console.memory.drafts[draft["draft_id"]]
    assert [one.number for one in held.revisions] == [1, 2, 3]
    assert held.revisions[-1].document()["identity"]["template_id"] == draft["agent_id"]


def test_an_incomplete_draft_is_kept_and_its_problems_are_said_in_the_forms_words(
    console: Console,
) -> None:
    """A document the manifest model refuses is saved, and each problem names its section.

    Delete this and a half-filled form either loses its afternoon's work or says `identity.
    display_name` to somebody who never saw a path."""
    draft = started(console)
    document = a_document(name="")
    response = console.post(
        "u_admin", at(SAVE_PATH, draft_id=draft["draft_id"]), {"document": document, "base": 1}
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert any(one.startswith("Identity, name: ") for one in response.json()["problems"])


# ------------------------------------------------------------------------------ checking
def test_a_check_that_passes_is_recorded_and_a_publish_needs_one(console: Console) -> None:
    """Publishing before a check is refused; a passing check is an act on that revision; and a
    save after the check is a draft again, which a publish refuses until it is checked.

    Delete this and what is published need not be what was checked."""
    draft = started(console)
    revision = saved(console, draft, reaching_nothing())
    unchecked = console.post(
        "u_admin", at(PUBLISH_PATH, draft_id=draft["draft_id"]), {"revision": revision}
    )
    check = checked(console, draft["draft_id"], revision)

    assert not_changed(unchecked) == (409, REFUSED, CHECK_FIRST)
    assert check.json()["passed"] is True
    held = console.memory.drafts[draft["draft_id"]]
    assert held.act_named(revision, DraftAct.CHECKED) is not None

    after = saved(
        console,
        {"draft_id": draft["draft_id"], "revision": revision},
        reaching_nothing() | {"persona": PERSONA + " Briefly."},
    )
    again = console.post(
        "u_admin", at(PUBLISH_PATH, draft_id=draft["draft_id"]), {"revision": after}
    )
    assert not_changed(again) == (409, REFUSED, CHECK_FIRST)


def test_a_check_that_fails_says_why_in_words_and_records_nothing(console: Console) -> None:
    """A blank persona and a rung above Shadow are each a sentence, and no act is recorded.

    Delete this and a draft that cannot become an agent, or one naming autonomy nobody earned,
    reaches the publish button looking ready."""
    draft = started(console)
    blank = saved(console, draft, a_document(persona=""))
    first = checked(console, draft["draft_id"], blank).json()
    raised = saved(
        console,
        {"draft_id": draft["draft_id"], "revision": blank},
        a_document(rung=AutonomyTier.ASSISTED),
    )
    second = checked(console, draft["draft_id"], raised).json()

    assert first["passed"] is False
    assert DOES_NOT_MAKE_AN_AGENT_YET in first["problems"]
    assert second["passed"] is False
    assert RUNG_PROBLEM.format(targets="invoice.read") in second["problems"]
    assert console.memory.drafts[draft["draft_id"]].acts == ()


def test_a_check_names_what_a_new_agent_would_reach_and_that_a_second_person_is_needed(
    console: Console,
) -> None:
    """A new agent reaching anything is a widening from nothing, named in the manifest's words.

    Delete this and the author is not told, before pressing publish, that it will wait."""
    draft_id, revision = ready(console, a_document())
    check = checked(console, draft_id, revision).json()

    assert check["second_person_needed"] is True
    assert "read:invoice.reference" in check["widened"]
    assert "ledger.read_invoice" in check["widened"]


# ----------------------------------------------------------------------------- publishing
def test_a_new_agent_reaching_nothing_publishes_on_its_authors_word_switched_off_at_shadow(
    console: Console,
) -> None:
    """The positive path: 201, the agent exists, disabled, owned by its author, and the draft is
    published and takes no further save.

    Delete this and every refusal below is satisfied by a publish route that refuses everybody."""
    draft_id, revision = ready(console, reaching_nothing())
    response = console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert response.status_code == 201
    assert response.json()["sentence"] == PUBLISHED_NEW
    agent_id = response.json()["agent_id"]
    made = console.memory.agents[agent_id]
    assert made.record.state is AgentState.DISABLED
    assert made.record.audience.owner_id == "u_admin"
    assert made.record.audience.level is Visibility.PERSONAL
    assert [one.act for one in console.memory.drafts[draft_id].acts] == [
        DraftAct.CHECKED,
        DraftAct.PUBLISHED,
    ]
    after = console.post(
        "u_admin",
        at(SAVE_PATH, draft_id=draft_id),
        {"document": reaching_nothing(), "base": revision},
    )
    assert not_changed(after) == (409, REFUSED, ALREADY_PUBLISHED)


def test_a_new_agent_that_reaches_anything_waits_for_a_second_person_who_is_not_its_author(
    console: Console,
) -> None:
    """The widening path, M27.15.31: the author's publish waits, the author cannot approve it, a
    builder whose reach does not cover it never sees it, and a second person who could have written
    it sees it in their queue and approves it, which publishes it.

    Delete this and the builder's one hazard, a ceiling wider than its author's reach, ships on one
    person's word."""
    draft_id, revision = ready(console, a_document())
    asked = console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert asked.status_code == 202
    assert asked.json()["sentence"] == WAITS_FOR_A_SECOND_PERSON
    assert console.memory.agents.keys() == everybody().keys()

    body = {"revision": revision}
    own = console.post("u_admin", at(APPROVE_PATH, draft_id=draft_id), body)
    narrow = console.post("u_narrow", at(APPROVE_PATH, draft_id=draft_id), body)
    queue_for_narrow = console.get("u_narrow", DRAFTS_PATH).json()["waiting_for_you"]
    queue_for_second = console.get("u_prefix", DRAFTS_PATH).json()["waiting_for_you"]
    opened = console.get("u_prefix", at(DRAFT_PATH, draft_id=draft_id)).json()

    assert not_changed(own) == (409, REFUSED, NOT_THE_AUTHOR)
    assert narrow.status_code == 404
    assert queue_for_narrow == []
    assert [one["draft_id"] for one in queue_for_second] == [draft_id]
    assert opened["waiting_on_you"] is True and opened["yours"] is False
    assert "read:invoice.reference" in opened["widened"]

    approved = console.post("u_prefix", at(APPROVE_PATH, draft_id=draft_id), body)

    assert approved.status_code == 201
    agent_id = approved.json()["agent_id"]
    assert console.memory.agents[agent_id].record.audience.owner_id == "u_admin"
    acts = console.memory.drafts[draft_id].acts
    assert [(one.act, one.actor_id) for one in acts] == [
        (DraftAct.CHECKED, "u_admin"),
        (DraftAct.REQUESTED, "u_admin"),
        (DraftAct.APPROVED, "u_prefix"),
        (DraftAct.PUBLISHED, "u_prefix"),
    ]
    assert console.get("u_prefix", DRAFTS_PATH).json()["waiting_for_you"] == []


def test_a_publish_sent_back_publishes_nothing_and_returns_to_its_author(console: Console) -> None:
    """Declining records the act and makes no agent; the author sees the draft sent back.

    Delete this and a declined publish could still be approved later from a stale queue, or the
    decline could publish."""
    draft_id, revision = ready(console, a_document())
    console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})
    declined = console.post("u_prefix", at(DECLINE_PATH, draft_id=draft_id), {"revision": revision})
    late = console.post("u_prefix", at(APPROVE_PATH, draft_id=draft_id), {"revision": revision})

    assert declined.status_code == 200
    assert console.memory.agents.keys() == everybody().keys()
    assert late.status_code == 404
    assert console.get("u_admin", at(DRAFT_PATH, draft_id=draft_id)).json()["state"] == "declined"


def test_publishing_without_this_installs_signing_key_says_so_and_records_nothing(
    console: Console,
) -> None:
    """With no key the publish is unavailable, before any request is recorded.

    Delete this and a publish could be asked for, approved by a second person and then fail, or be
    signed with a key kept somewhere weaker."""
    console.app.state.template_key = None
    draft_id, revision = ready(console, a_document())
    response = console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert not_changed(response) == (409, UNAVAILABLE, NO_SIGNING_KEY_HERE)
    assert [one.act for one in console.memory.drafts[draft_id].acts] == [DraftAct.CHECKED]


# ---------------------------------------------------------------------------- editing an agent
def edited(console: Console, document_change: Mapping[str, Any]) -> tuple[str, int]:
    """A checked draft of the company agent, changed as asked."""
    response = console.post("u_admin", at(EDIT_PATH, agent_id=COMPANY))
    assert response.status_code == 201, response.text
    draft = response.json()
    document = {**draft["document"], **document_change}
    revision = saved(console, draft, document)
    assert checked(console, draft["draft_id"], revision).json()["passed"]
    return draft["draft_id"], revision


def test_an_edit_starts_from_the_agent_as_it_is_and_an_instruction_change_publishes_at_once(
    console: Console,
) -> None:
    """The draft is the effective manifest; a persona change reaches no further and goes out on the
    author's word; the agent keeps its steward, audience and state and is pinned to version one of
    its own lineage.

    Delete this and editing an agent either cannot publish at all or rewrites who answers for it."""
    before = console.memory.agents[COMPANY]
    draft_id, revision = edited(console, {"persona": PERSONA})
    response = console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert response.status_code == 201
    assert response.json()["sentence"] == PUBLISHED_EDIT
    after = console.memory.agents[COMPANY]
    assert after.record.persona == PERSONA
    assert after.record.audience == before.record.audience
    assert after.record.state is AgentState.ENABLED
    assert after.install is not None
    assert after.install[0].manifest.identity.template_id == COMPANY
    assert after.install[0].manifest.identity.version == 1


def test_an_edit_that_widens_the_ceiling_waits_and_one_that_changed_underneath_is_refused(
    console: Console,
) -> None:
    """A capability added waits for a second person; an agent that moved since the draft began is
    not overwritten.

    Delete this and an edit can widen an agent on one person's word, or silently undo a change
    somebody else made after the draft was started."""
    wider = {
        "authority": {
            **a_document()["authority"],
            "capabilities": [{"value": "read:invoice.reference"}, {"value": "read:invoice.total"}],
        }
    }
    draft_id, revision = edited(console, wider)
    waits = console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert waits.status_code == 202
    assert waits.json()["widened"] == ["read:invoice.total"]

    other_id, other_revision = edited(console, {"persona": PERSONA})
    held = console.memory.agents[COMPANY]
    console.memory.agents[COMPANY] = replace(held, effective_hash="0" * 64)
    moved = console.post(
        "u_admin", at(PUBLISH_PATH, draft_id=other_id), {"revision": other_revision}
    )
    assert moved.status_code == 409
    assert AGENT_MOVED in moved.json()["sentence"]


def test_an_archived_agent_and_an_agent_with_no_install_cannot_be_edited_as_a_draft(
    console: Console,
) -> None:
    """Archive is terminal, in the domain's own words, and an agent never installed from a version
    has nothing to start a draft from.

    Delete this and a draft can resurrect an archived agent's configuration."""
    archived = console.post("u_admin", at(EDIT_PATH, agent_id=ARCHIVED))
    loose = console.post("u_admin", at(EDIT_PATH, agent_id=LOOSE))

    assert not_changed(archived) == (409, REFUSED, ARCHIVE_IS_TERMINAL)
    assert not_changed(loose) == (409, REFUSED, NO_INSTALL_TO_START_FROM)


def test_a_hidden_agent_and_a_missing_agent_are_one_answer_to_edit_as_a_draft(
    console: Console,
) -> None:
    """A builder in web alone and a made-up id get one 404 body.

    Delete this and "edit as a draft" answers which agents exist outside the caller's authority."""
    outside = console.post("u_narrow", at(EDIT_PATH, agent_id=COMPANY))
    missing = console.post("u_admin", at(EDIT_PATH, agent_id="no_such_agent"))

    assert outside.status_code == missing.status_code == 404
    assert outside.json()["message"] == missing.json()["message"]


# ------------------------------------------------------------------------- rehearsing, drawing
def test_a_rehearsal_says_what_it_did_not_do_and_carries_no_row(console: Console) -> None:
    """It reports the run for the person asking, at Shadow, and the sentence saying no model ran,
    and nothing in the answer has a name a row could arrive in.

    Delete this and the rehearsal could become a way of reading data, or could draw a result that
    no model produced."""
    draft = started(console)
    revision = saved(console, draft, a_document())
    response = console.post(
        "u_admin", at(REHEARSE_PATH, draft_id=draft["draft_id"]), {"revision": revision}
    )

    body = response.json()
    assert response.status_code == 200
    assert body["not_done"] == A_REHEARSAL_RUNS_NO_MODEL_YET
    assert body["rung"] == "shadow"
    assert body["starts_for_you"] is True
    assert body["reaches_for_you"] == ["ledger.read_invoice"]
    assert not set(body) & NAMES_THAT_WOULD_CARRY_ANOTHER_PERSONS_ROWS
    assert console.memory.drafts[draft["draft_id"]].acts == ()


def test_a_rehearsal_for_somebody_who_reaches_nothing_through_it_does_not_start(
    console: Console,
) -> None:
    """The same draft rehearsed by a builder holding no invoice read does not start for them.

    Delete this and the rehearsal could be reporting the agent's ceiling as the person's reach,
    which is the preview of a different run."""
    console.memory.drafts.clear()
    draft = started(console, pid="u_narrow")
    response = console.post(
        "u_narrow",
        at(SAVE_PATH, draft_id=draft["draft_id"]),
        {"document": a_document(), "base": 1},
    )
    rehearsal = console.post(
        "u_narrow", at(REHEARSE_PATH, draft_id=draft["draft_id"]), {"revision": 2}
    )

    assert response.status_code == 200
    assert rehearsal.json()["starts_for_you"] is False
    assert rehearsal.json()["reaches_for_you"] == []


def test_a_procedure_over_the_drafts_own_tools_becomes_a_skill_and_another_tool_is_refused(
    console: Console,
) -> None:
    """A drawing calling an allowed tool comes back as a SKILL.md, and one calling a tool the draft
    does not allow is refused.

    Delete this and the canvas could put a tool in a skill that the agent was never allowed."""
    draft = started(console)
    saved(console, draft, a_document())

    def drawing(tool: str) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": "start", "kind": "start"},
                {"id": "look", "kind": "tool_call", "tool": tool},
                {"id": "done", "kind": "finish"},
            ],
            "edges": [
                {"from": "start", "to": "look", "way": "next"},
                {"from": "look", "to": "done", "way": "next"},
            ],
        }

    path = at(PROCEDURE_PATH, draft_id=draft["draft_id"])
    body = {
        "name": "look-up-an-invoice",
        "description": "Use when somebody asks about one invoice.",
    }
    good = console.post("u_admin", path, {**body, "drawing": drawing("ledger.read_invoice")})
    bad = console.post("u_admin", path, {**body, "drawing": drawing("mail.send_message")})

    assert good.status_code == 200
    assert "call `ledger.read_invoice`" in good.json()["skill"]
    assert bad.status_code == 409
    assert bad.json()["outcome"] == REFUSED
