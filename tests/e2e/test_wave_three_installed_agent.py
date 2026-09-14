"""The wave-3 milestone: agents installed from the catalogue, answering with knowledge and memory.

`docs/wbs` states what must be live after wave three as "agents installed from templates,
answering with knowledge and memory", and every clause of it is load-bearing. This drives the
three together. Two templates from `brain.agents.catalogue` are signed, offered, opened and
installed through the wizard in `brain.agents.install`, as an installer would do it; each agent
that comes out is a ceiling; the ceiling is intersected with a real person's reach by
`EntitlementSet.intersect`, which is the one implementation of the platform's invariant; and what
that run reach retrieves from the document plane and recalls from memory is what the agent may
answer from.

**An agent is a lens, so every question here is asked twice.**
`tests/e2e/test_wave_two_lark_question.py` asked one question of two people. W3 adds a second
axis, because the invariant is `E_run(caller, agent) = E(caller) intersect agent_ceiling`: the
same person asks with the agent and without it. Through the agent they must never reach more than
they reach alone, which is the leak. And they must still reach whatever the ceiling admits and
they hold, which is the same bug arriving from the other side, and the one nobody files a
security report about.

**Why these two templates.** `internal_helpdesk` is the catalogue's knowledge agent: its own
docstring says it "reads policy documents and holds not one capability naming a person", so the
knowledge clause and the memory clause meet in it. `capacity_and_hours_analyst` names itself as
"the fixture case `tests/e2e/test_wave_two_lark_question.py` drives with two real people", so its
memory is where the W2 worked example carries into W3.

**The worked examples are the company fixture's own, and each is here for one reason.**

- `u_weiling` holds exactly the three client columns the analyst's ceiling names, in the one
  department it is scoped to. She is the person the analyst was written around.
- `u_aaron` is the Department Admin who installs both agents, and he holds `read:client.*`. He is
  the caller the lens has to narrow rather than refuse: through the analyst he may have the hours
  and never the money.
- `u_dual` sits in two departments at unequal depth, so an agent scoped to one department is
  exactly what must stop his reach in the other coming through it.
- `u_siti` heads another department, and `u_hr` is the only person who may read salary: a
  document and a memory carrying `CANARY-SALARY-M8VTK` reach her and nobody else.

**Knowledge reach comes from the product's own starter pack, because the fixture grants none.**
Nobody in `tests/fixtures/company.py` holds `read:knowledge`, so asked as the fixture stands every
person reaches no document at all, and every knowledge assertion here would pass because nothing
was ever retrieved. So each person also holds `brain.identity.lifecycle.STARTER_PACK`, assigned in
their own department through `brain.identity.packs.resolve_entitlement`. That is the grant a
joiner is given on their first day, and the one whose field capabilities that module describes as
"the ones `brain.agents.catalogue` already asks for on knowledge". Entitlements are additive, so
holding the pack beside the fixture's grants is a second source of grants and an edit to neither.

**What this found, and why M38.2.2.4 is not claimed.** Measured on 2026-09-14, three defects stop
the leaf being true of the product as it ships. Each is pinned by a test below that fails for
exactly that reason.

1. **No agent installed from the catalogue reaches the document plane.**
   `brain.knowledge.search.reach_for` requires `read:knowledge`, and none of the ten templates that
   read knowledge names it: each names field capabilities such as `read:knowledge.document`.
   `intersect` keeps a caller's grant only where the ceiling covers it, and `Capability.covers`
   expands only a trailing `.*`, so `read:knowledge` never survives into a run and `reach_for`
   answers None, for every caller and every catalogue agent. Because DENIED and ABSENT are one
   answer, the helpdesk would say "I could not find that" to every question with nothing anywhere
   saying why. It is the defect 258c089 fixed for the demo's rows, a record grant missing beside
   its field grants, arriving on the agent side. See
   `THE_CATALOGUE_NAMES_NO_READ_OF_THE_KNOWLEDGE_PLANE`. **Fixed on 2026-09-14**, as a class
   rather than as ten omissions: `brain.agents.model.entitlement_ceiling` derives the row read
   each column read implies, for read verbs only, so the knowledge plane and the row plane both
   open for every catalogue agent.
2. **The lens deletes a wildcard instead of narrowing it.** `u_aaron` holds
   `read:client.hours_remaining` through `read:client.*`, the analyst's ceiling admits it, and his
   run through the analyst holds nothing at all: `intersect` asks whether the ceiling covers
   `read:client.*`, and `read:client.hours_remaining` does not. Its own docstring says "a run gets
   a capability only when the caller holds it and the agent's ceiling admits it", and for every
   caller whose grants are wildcards, which is every Department Admin and the Super Admin, it
   withholds instead. `brain.memory.formation` intersects requirement-first to step around exactly
   this; the run reach has no such step. See
   `A_WILDCARD_IS_DELETED_BY_THE_LENS_RATHER_THAN_NARROWED`. **Fixed on 2026-09-14**: for every
   capability either side names, a run holds it where the caller's `scope_for` and the
   ceiling's `scope_for` both reach, so a wildcard is narrowed to the column and never wider
   than either side. The SQL twin in `gate.delegated_reach` is corrected by migration 0029.
3. **No agent installed from the catalogue can start a run.** `brain.gate.catalogue.project` keeps
   a tool only when its name is in `AgentCeiling.allowed_tools`, and not one of the twenty-three
   templates declares any, so `brain.gate.invoke.invoke` refuses every installed catalogue agent
   for every caller while `brain.agents.install.completeness` reports the install READY. The
   application also registers no tool either agent here reads. See
   `A_CEILING_THAT_ALLOWS_NO_TOOL_CANNOT_START_A_RUN`. **Fixed on 2026-09-14**, as a class: each
   template declares its tools once, `brain.agents.install` binds every declared tool to the
   registered tool of its entity and verb, a tool nothing binds holds the install incomplete
   and disabled, and `brain.knowledge.document_tools` puts the document plane's two tools on
   every install. The helpdesk starts a run; the analyst reports the two tools nothing on a
   `local` install serves, rather than reporting ready.

**Why the failing half is a strict xfail rather than absent.** 258c089 found the first of this
family and left its half-written harness out of the tree, which was right for a session that could
fix the defect in the same commit. These are in `brain.agents.catalogue` and
`brain.core.entitlement`, which this file's author does not own. A finding with no test goes stale
in a commit message, and a test asserting today's broken behaviour would go red on the fix and
read as a regression. So each defect has a test asserting the property the leaf needs, marked
`xfail(strict=True)` and restricted to `AssertionError`: the day the product is fixed that test
passes, strictness turns the pass into a failure, and whoever fixed it takes the marker off. When
all three are off, the leaf may be claimed. Everything that already holds is unmarked and runs as
an ordinary test.

**What this does not do.** No model is called and nothing composes a sentence: "answering" here is
what a run may answer from, which is everything a model would be handed. The vector leg of
retrieval does not run, because there is no inference server. The lexical leg does not run either,
because `lexical_query` is a statement for PostgreSQL and there is none. What runs of the knowledge
plane is its reach and its arrangement: `reach_for` decides the departments a run reaches,
`top_within_reach` applies `Reach.admits`, which is the Python side of `reach_predicate`, to
passages handed over in the order the lexical leg would rank them, `hybrid` fuses that leg with an
empty vector leg, and `brain.knowledge.assembly` groups the result into documents. The relevance
order is this file's, so nothing here measures ranking. Memory is recalled through
`brain.memory.review.agent_memory` and `brain.console.reach_view.readable` from `Learning` records
built here, because nothing in `src` forms one from a conversation yet. No database, no HTTP.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pytest

from brain.agents import catalogue
from brain.agents.install import (
    Installation,
    MissingKind,
    TemplateCatalogue,
    begin,
    complete,
    provide,
    rehearse,
)
from brain.agents.model import AgentAudience, AgentViewer, entitlement_ceiling
from brain.agents.template import SYSTEM_PUBLISHER, TemplateManifest, publish
from brain.app import Settings
from brain.connectors.contract import ConnectorScope, CredentialBinding, TransportKind
from brain.connectors.manifest import (
    ChangeSignal,
    ConnectorManifest,
    FieldShape,
    HotUse,
    ProjectedEntity,
    ProjectedField,
    ToolDeclaration,
)
from brain.connectors.registry import INSTALL_AUTHORITY, ConnectorRegistry
from brain.console.reach_view import readable
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.identity.lifecycle import STARTER_PACK
from brain.identity.packs import PackAssignment, resolve_entitlement
from brain.identity.teams import PrincipalSubject
from brain.knowledge.assembly import DocumentResult, RetrievedChunk, by_chunk, by_document
from brain.knowledge.item import KnowledgeState
from brain.knowledge.rows import RowQuery
from brain.knowledge.search import hybrid, reach_for, top_within_reach
from brain.knowledge.visibility import Visibility
from brain.memory.digest import Learning
from brain.memory.formation import Formation, MemoryKind
from brain.memory.review import agent_memory
from brain.memory.tiers import Change, propose
from brain.ops.secrets import SecretRef, VaultRole
from brain.tools.startup import build_registry
from tests.fixtures.company import CANARIES, DEPARTMENTS, NOW, canary_tokens, person

# ------------------------------------------------------------------ why the xfails fail
#: The first defect. See the module docstring, item 1.
THE_CATALOGUE_NAMES_NO_READ_OF_THE_KNOWLEDGE_PLANE: Final = (
    "brain.knowledge.search.reach_for requires read:knowledge, and no template in "
    "brain.agents.catalogue names it: each names field capabilities such as "
    "read:knowledge.document. EntitlementSet.intersect keeps a caller's grant only where the "
    "ceiling covers it and Capability.covers expands only a trailing .*, so read:knowledge never "
    "survives into a run and no catalogue agent reaches the document plane for anybody. It "
    "passed on 2026-09-14, when entitlement_ceiling began deriving row reads, and the marker "
    "came off."
)

#: The second defect. See the module docstring, item 2.
A_WILDCARD_IS_DELETED_BY_THE_LENS_RATHER_THAN_NARROWED: Final = (
    "EntitlementSet.intersect keeps a caller's grant only when the ceiling covers the caller's "
    "capability, so a caller holding read:client.* through a ceiling naming "
    "read:client.hours_remaining keeps nothing, although the caller holds the column and the "
    "ceiling admits it. Every Department Admin and the Super Admin hold wildcards, so every one "
    "of them reaches nothing through a template that names columns. It passed on 2026-09-14, "
    "when intersect began asking both sides scope_for about every capability either names, "
    "and the marker came off."
)

#: The third defect. See the module docstring, item 3.
A_CEILING_THAT_ALLOWS_NO_TOOL_CANNOT_START_A_RUN: Final = (
    "brain.gate.catalogue.project keeps a tool only when its name is in the ceiling's "
    "allowed_tools, and no template in brain.agents.catalogue declares any, so "
    "brain.gate.invoke.invoke refuses every agent installed from it while the install reports "
    "READY; and the application registers no tool the helpdesk reads. It passed on 2026-09-14, "
    "when templates declared their tools once and the install bound them to registered ones, "
    "and the marker came off."
)

# ------------------------------------------------------------------ the install
#: The key the catalogue is signed with on this install. A test value, not a secret anywhere.
SIGNING_KEY: Final = "wave-three-signing-key"

#: The fixture's Department Admin for Maintenance, who installs both agents.
INSTALLER: Final = "u_aaron"

#: Who assigns the starter pack. The fixture's Super Admin, the one person holding `admin:grant`.
GRANTOR: Final = "u_rupash"

#: Who may install the templates: the installer alone. Deliberately not the agent's audience, so
#: an install that published the agent to whoever could install it is visible below.
OFFERED_TO: Final = AgentAudience(level=Visibility.PERSONAL, owner_id=INSTALLER)

#: Who may see and start the agents once installed.
AUDIENCE: Final = AgentAudience(
    level=Visibility.DEPARTMENT, owner_id=INSTALLER, department="maintenance"
)

#: What the installer types for each placeholder a template requires. A placeholder not listed
#: here is a `KeyError`, which is louder than an install that quietly came out incomplete.
PLACEHOLDER_ANSWERS: Final[Mapping[str, str]] = {
    "policy_space": "the policies space in the company wiki",
}

#: Who installs a connector. Not a person this file asserts anything about: installing one is
#: guarded by `brain.connectors.registry.INSTALL_AUTHORITY`, `tests/unit/test_connectors.py` owns
#: that guard, and it is held here only so the readiness the wizard reads is real rather than
#: absent.
CONNECTOR_ADMIN: Final = EntitlementSet(
    principal_id="svc_connector_install",
    grants=(Grant(capability=INSTALL_AUTHORITY, scope=Scope.unrestricted()),),
)

#: A run with no injection signal in it. The assessment may only tighten a rung, so a clean one
#: keeps it from being the reason a rehearsal fails.
CLEAN: Final = RiskAssessment(score=0, matched=())


def connector(name: str) -> ConnectorManifest:
    """A connector by the name a template declares, shaped the way the install tests shape one."""
    return ConnectorManifest(
        name=name,
        version="1.0.0",
        transport=TransportKind.REST,
        scope=ConnectorScope(resource_kind="view", selectors=("clients",)),
        credential=CredentialBinding(ref=SecretRef(path=f"kv/{name}", role=VaultRole.APPLICATION)),
        tools=(
            ToolDeclaration(
                name=f"{name}.read_client", description="One client record.", entity="client"
            ),
        ),
        projections=(
            ProjectedEntity(
                entity="client",
                fields=(
                    ProjectedField(name="id", shape=FieldShape.IDENTIFIER, uses=(HotUse.IDENTIFY,)),
                    ProjectedField(name="status", shape=FieldShape.STATUS, uses=(HotUse.FILTER,)),
                    ProjectedField(
                        name="display_name", shape=FieldShape.LABEL, uses=(HotUse.SORT,)
                    ),
                ),
                change_signal=ChangeSignal.WEBHOOK,
                visibility=Scope.department("maintenance"),
            ),
        ),
    )


def serving(names: Sequence[str]) -> ConnectorRegistry:
    """A registry in which every connector a template declares is installed and switched on."""
    registry = ConnectorRegistry()
    for name in names:
        registry.register(connector(name), installer=CONNECTOR_ADMIN, now=NOW)
        registry.enable(name, installer=CONNECTOR_ADMIN, now=NOW)
    return registry


def install_from_catalogue(manifest: TemplateManifest) -> Installation:
    """Publish, offer, open, begin, answer and complete: the install as an installer does it.

    Every step is the product's. Nothing here builds an `AgentRecord`, a ceiling or a leash, so
    whatever the agent reaches is what the catalogue and the wizard made of it.
    """
    signed = publish(manifest, key=SIGNING_KEY, signed_by=SYSTEM_PUBLISHER, at=NOW)
    shelf = TemplateCatalogue()
    shelf.offer(signed, audience=OFFERED_TO)
    viewer = AgentViewer(principal_id=INSTALLER, departments=frozenset({"maintenance"}))
    draft = begin(
        shelf.open_for(manifest.identity.template_id, viewer),
        instance_id=manifest.identity.template_id,
        installer=INSTALLER,
    )
    for placeholder in manifest.placeholders:
        if placeholder.required:
            draft = provide(draft, placeholder.key, PLACEHOLDER_ANSWERS[placeholder.key])
    return complete(
        draft,
        key=SIGNING_KEY,
        audience=AUDIENCE,
        registry=serving(manifest.connectors),
        tools=build_registry(source=Settings(env="development").tool_source, records=NoRows()),
        at=NOW,
    )


@pytest.fixture(scope="module")
def helpdesk() -> Installation:
    return install_from_catalogue(catalogue.internal_helpdesk())


@pytest.fixture(scope="module")
def analyst() -> Installation:
    return install_from_catalogue(catalogue.capacity_and_hours_analyst())


# ------------------------------------------------------------------ whose reach
def reach_of(pid: str) -> EntitlementSet:
    """The fixture person's own grants, and the starter pack assigned in their own department.

    See the module docstring for why the pack: the fixture grants nobody the knowledge plane.
    """
    who = person(pid)
    department = who.principal.primary_department
    assert department is not None, f"{pid} has no department to be given a starter pack in"
    assignment = PackAssignment(
        subject=PrincipalSubject(principal_id=pid),
        pack_slug=STARTER_PACK.slug,
        scope=Scope.department(department),
        granted_by=GRANTOR,
        reason="the starter pack every joiner is given",
        granted_at=NOW,
    )
    pack = resolve_entitlement(
        who.principal,
        assignments=(assignment,),
        packs={STARTER_PACK.slug: STARTER_PACK},
        now=NOW,
    )
    assert isinstance(pack, EntitlementSet), f"{pid} resolves to no standing entitlement"
    return EntitlementSet(
        principal_id=pid,
        grants=(*who.grants, *pack.grants),
        not_after=who.principal.not_after,
    )


def through(reader: EntitlementSet, agent: Installation) -> EntitlementSet:
    """`E_run(caller, agent)`, by the one implementation, with the ceiling the install produced."""
    return reader.intersect(entitlement_ceiling(agent.record), NOW)


#: Everybody asked as, in the order the module docstring introduces them.
READERS: Final[tuple[str, ...]] = ("u_weiling", "u_aaron", "u_dual", "u_siti", "u_hr", "u_jason")


# ------------------------------------------------------------------ the knowledge plane
@dataclass(frozen=True)
class Passage:
    """One indexed passage: the row the reach predicate reads, and the text a reader receives."""

    chunk_id: str
    document_id: str
    title: str
    text: str
    visibility: Visibility
    department: str
    owner_id: str


#: The document plane this install holds. One passage per document, at each visibility level,
#: and the salary note is personal to the one person entitled to salary.
CORPUS: Final[tuple[Passage, ...]] = (
    Passage(
        chunk_id="k_leave_1",
        document_id="doc_leave_policy",
        title="Annual leave policy",
        text="Annual leave is booked through the leave form at least two weeks ahead.",
        visibility=Visibility.COMPANY,
        department="finance",
        owner_id="u_hr",
    ),
    Passage(
        chunk_id="k_rota_1",
        document_id="doc_maintenance_rota",
        title="Maintenance escalation rota",
        text="Out of hours maintenance escalations go to the on-call engineer first.",
        visibility=Visibility.DEPARTMENT,
        department="maintenance",
        owner_id="u_aaron",
    ),
    Passage(
        chunk_id="k_web_1",
        document_id="doc_web_standard",
        title="Web build standard",
        text="Every new site ships with the accessibility checklist completed.",
        visibility=Visibility.DEPARTMENT,
        department="web",
        owner_id="u_siti",
    ),
    Passage(
        chunk_id="k_salary_1",
        document_id="doc_salary_review",
        title="Salary review notes",
        text=f"The band review settled at {CANARIES['hr.salary']}.",
        visibility=Visibility.PERSONAL,
        department="finance",
        owner_id="u_hr",
    ),
)

#: The order the lexical leg would return the passages in. Supplied, because ranking is
#: `ts_rank_cd` inside PostgreSQL. The salary note is first on purpose: a filter applied after
#: the page is taken, rather than before, would show it to whoever it was not filtered from.
RANKED: Final[tuple[str, ...]] = ("k_salary_1", "k_leave_1", "k_rota_1", "k_web_1")

#: How many fused results a run is handed.
PAGE: Final = 10

_BY_CHUNK: Final[Mapping[str, Passage]] = {one.chunk_id: one for one in CORPUS}

BODIES: Final[Mapping[str, RetrievedChunk]] = {
    one.chunk_id: RetrievedChunk(
        chunk_id=one.chunk_id,
        document_id=one.document_id,
        ordinal=0,
        text=one.text,
        title=one.title,
    )
    for one in CORPUS
}


def row_of(passage: Passage) -> dict[str, object]:
    """The columns `Reach.admits` reads, as a published chunk carries them."""
    return {
        "chunk_id": passage.chunk_id,
        "deleted_at": None,
        "state": KnowledgeState.PUBLISHED.value,
        "owner_id": passage.owner_id,
        "visibility": passage.visibility.value,
        "department": passage.department,
    }


def documents(reader: EntitlementSet) -> tuple[DocumentResult, ...]:
    """What the document plane hands this reach, arranged as documents.

    No reach is no documents, which is the answer a caller with no grant on the plane gets and
    is indistinguishable from a plane with nothing in it.
    """
    reach = reach_for(reader, departments=DEPARTMENTS, now=NOW)
    if reach is None:
        return ()
    lexical = top_within_reach([row_of(_BY_CHUNK[ref]) for ref in RANKED], reach=reach)
    fused = hybrid(lexical=lexical, vector=(), limit=PAGE)
    return by_document(by_chunk([one.ref for one in fused], BODIES))


def document_ids(found: Sequence[DocumentResult]) -> set[str]:
    return {one.document_id for one in found}


def passage_text(found: Sequence[DocumentResult]) -> str:
    return "\n".join(f"{p.title}\n{p.text}" for one in found for p in one.passages)


# ------------------------------------------------------------------ memory
#: What each memory says, in its own words. Held apart from `Learning`, which carries no text.
STATEMENTS: Final[Mapping[str, str]] = {
    "mem_hours": "SNM Construction's retainer hours are topped up in the last week of the month.",
    "mem_money": f"SNM Construction renews at {CANARIES['client.contract_value']}.",
    "mem_web": "The web clients ask for renewal paperwork before the quarter closes.",
    "mem_rota": "Maintenance asks for the escalation rota before every public holiday.",
    "mem_salary": f"The band review settled at {CANARIES['hr.salary']}.",
}


def learning(
    memory_id: str, *, agent: Installation, formed_by: str, capability: str, department: str
) -> Learning:
    """One thing the agent learnt while acting for `formed_by`, under one capability, somewhere.

    The formation records the capability and the place, which is what recall is checked
    against; the statement is kept in `STATEMENTS` because a learning carries no text.
    """
    return Learning(
        memory_id=memory_id,
        proposal=propose(Change.PREFERENCE, subject=f"memory:{memory_id}"),
        formation=Formation(
            principal_id=formed_by,
            capabilities=(Capability(value=capability),),
            scope=Scope.department(department),
            ent_hash=person(formed_by).entitlement().ent_hash(),
            formed_at=NOW,
            kind=MemoryKind.PERSISTENT,
        ),
        agent_id=agent.record.agent_id,
    )


def analyst_learnings(analyst: Installation) -> tuple[Learning, ...]:
    """Three things the analyst learnt, and only the first is inside its ceiling.

    `mem_money` was formed at the installer's own reach, under the contract value the analyst's
    ceiling does not name: the case `brain.memory.formation` is written against, where something
    learnt for a person with broad access is recalled for a person without it. `mem_web` was
    formed for `u_dual` in Web, a department the analyst is not scoped to.
    """
    return (
        learning(
            "mem_hours",
            agent=analyst,
            formed_by="u_aaron",
            capability="read:client.hours_remaining",
            department="maintenance",
        ),
        learning(
            "mem_money",
            agent=analyst,
            formed_by="u_aaron",
            capability="read:client.contract_value",
            department="maintenance",
        ),
        learning(
            "mem_web",
            agent=analyst,
            formed_by="u_dual",
            capability="read:client.name",
            department="web",
        ),
    )


def helpdesk_learnings(helpdesk: Installation) -> tuple[Learning, ...]:
    """Two things the helpdesk learnt: one from Maintenance's documents, one from salary."""
    return (
        learning(
            "mem_rota",
            agent=helpdesk,
            formed_by="u_weiling",
            capability="read:knowledge.document",
            department="maintenance",
        ),
        learning(
            "mem_salary",
            agent=helpdesk,
            formed_by="u_hr",
            capability="read:hr.salary",
            department="finance",
        ),
    )


def recalled(reader: EntitlementSet, learnings: Sequence[Learning]) -> set[str]:
    """The memories whose text the viewer would show this reach."""
    return {
        one.memory_id
        for one in learnings
        if readable(one, STATEMENTS[one.memory_id], reader, now=NOW) is not None
    }


def listed(pid: str, agent: Installation, learnings: Sequence[Learning]) -> set[str]:
    """The memories the agent's own tab lists for this person, which computes `E_run` itself."""
    view = agent_memory(
        now=NOW,
        caller=reach_of(pid),
        agent_ceiling=entitlement_ceiling(agent.record),
        agent_id=agent.record.agent_id,
        learnings=learnings,
    )
    return {item.memory_id for item in view.items}


def memory_text(memory_ids: set[str]) -> str:
    return "\n".join(STATEMENTS[one] for one in sorted(memory_ids))


# ================================================================== installed from templates
@pytest.mark.parametrize(
    "template",
    [catalogue.internal_helpdesk],
    ids=["internal_helpdesk"],
)
def test_the_agent_is_installed_from_the_catalogue_whole_and_starts_supervised(
    template: Callable[[], TemplateManifest],
) -> None:
    """**The first clause of the leaf.** Installed through every step of the wizard, the agent is
    ready, selectable, pinned to the template version it came from, published to the audience
    the installer chose rather than to whoever could install it, holding the template's ceiling
    and no more, and on the bottom rung for every target the template names.

    Delete this and the knowledge and memory tests below can pass against an agent the install
    widened, disabled or published to the wrong people, because none of them looks at the
    install itself."""
    manifest = template()
    installed = install_from_catalogue(manifest)

    assert installed.completeness.is_ready, installed.completeness.missing
    assert installed.record.is_selectable
    assert (installed.instance.template_id, installed.instance.template_version) == (
        manifest.identity.template_id,
        manifest.identity.version,
    )
    assert installed.record.audience == AUDIENCE
    assert installed.record.audience != OFFERED_TO
    assert {one.value for one in installed.record.authority.capabilities} == {
        one.value for one in manifest.authority.capabilities
    }
    assert installed.record.authority.scope == manifest.authority.scope
    assert installed.leash.entries, "the template names targets, so the leash is not empty"
    assert all(entry.rung is AutonomyTier.SHADOW for entry in installed.leash.entries)


def test_an_agent_whose_tools_nothing_here_serves_installs_incomplete_and_disabled() -> None:
    """**The install says what an agent cannot use, rather than calling it ready.** The analyst
    reads client columns and declares `client.read` and `client.search`. On an install reading
    `local` no registered tool serves either, so `complete` reports both as missing tools, the
    badge is incomplete and the agent starts disabled. Everything else the install decides still
    holds: the audience it was published to, the template's ceiling and the bottom rung.

    Until 2026-09-14 this agent installed ready and `invoke` refused it for every caller, which
    is `A_CEILING_THAT_ALLOWS_NO_TOOL_CANNOT_START_A_RUN`. It was a parameter of the test above,
    and it left that test when installing whole stopped being true of it.

    Delete this and an install can report ready again for an agent no run can start."""
    manifest = catalogue.capacity_and_hours_analyst()
    installed = install_from_catalogue(manifest)

    assert not installed.completeness.is_ready
    assert {(one.kind, one.name) for one in installed.completeness.missing} == {
        (MissingKind.TOOL, "client.read"),
        (MissingKind.TOOL, "client.search"),
    }
    assert not installed.record.is_selectable
    assert installed.record.audience == AUDIENCE
    assert {one.value for one in installed.record.authority.capabilities} == {
        one.value for one in manifest.authority.capabilities
    }
    assert all(entry.rung is AutonomyTier.SHADOW for entry in installed.leash.entries)


# ================================================================== answering with knowledge
def test_each_person_reaches_their_own_department_and_the_company_without_any_agent() -> None:
    """The positive sibling that makes the knowledge xfail below mean something. Alone, each
    person reaches the company's document and their own department's, and the salary note
    reaches its owner. Asserted as sets written against `CORPUS`, not against anything the
    search module computes.

    Delete this and the xfail can be satisfied by a corpus nobody reaches, and the refusal tests
    by a reach predicate that admits nothing."""
    expected = {
        "u_weiling": {"doc_leave_policy", "doc_maintenance_rota"},
        "u_aaron": {"doc_leave_policy", "doc_maintenance_rota"},
        "u_siti": {"doc_leave_policy", "doc_web_standard"},
        "u_jason": {"doc_leave_policy", "doc_web_standard"},
        "u_hr": {"doc_leave_policy", "doc_salary_review"},
        "u_dual": {"doc_leave_policy"},
    }

    for pid, found in expected.items():
        assert document_ids(documents(reach_of(pid))) == found, pid


@pytest.mark.parametrize("pid", ["u_weiling", "u_siti"])
def test_through_the_helpdesk_a_person_reaches_the_documents_they_reach_alone(
    pid: str, helpdesk: Installation
) -> None:
    """**The knowledge clause, in the direction nobody reports.** The helpdesk's ceiling names
    documents and no person, so through it a person must reach exactly the documents they reach
    alone. Two people in two departments, so a helpdesk that answered everybody from one
    department's documents cannot pass.

    Failed until 2026-09-14 for `THE_CATALOGUE_NAMES_NO_READ_OF_THE_KNOWLEDGE_PLANE`, when
    `brain.agents.model.entitlement_ceiling` began deriving the row read a column read implies.

    Delete this and the catalogue's knowledge agents can go on retrieving nothing for everybody,
    which every refusal test in this file reads as the permission model working."""
    alone = document_ids(documents(reach_of(pid)))

    assert document_ids(documents(through(reach_of(pid), helpdesk))) == alone


@pytest.mark.parametrize("pid", READERS)
def test_no_agent_hands_anybody_a_document_they_cannot_reach_alone(
    pid: str, helpdesk: Installation, analyst: Installation
) -> None:
    """The leak direction of the lens: through either agent, a subset of what the person reaches
    alone. Asked of both agents, because the analyst names no knowledge capability at all and
    must hand over no document whatever its caller holds.

    It held partly because of the defect the test above pinned, which emptied the helpdesk's
    side. Since that was fixed on 2026-09-14 it is the half that shows the fix widened nothing.

    Delete this and a fix to the knowledge clause that went too far, a ceiling handing the run
    the whole plane, passes every other test here."""
    alone = document_ids(documents(reach_of(pid)))

    assert document_ids(documents(through(reach_of(pid), helpdesk))) <= alone
    assert document_ids(documents(through(reach_of(pid), analyst))) == set()


@pytest.mark.parametrize("pid", [one for one in READERS if one != "u_hr"])
def test_the_salary_note_reaches_nobody_but_its_owner_with_or_without_the_helpdesk(
    pid: str, helpdesk: Installation
) -> None:
    """Every canary on the person's `forbidden` list, checked against every passage they are
    handed, alone and through the helpdesk, rather than against a document id: a canary in a
    title or a passage is a canary a person read.

    Its positive sibling is the next test, which is what stops this passing because the salary
    note is unreachable by everybody.

    Delete this and the personal branch of the reach predicate can admit a document to anybody,
    and nothing else here reads passage text."""
    handed = passage_text(documents(reach_of(pid))) + passage_text(
        documents(through(reach_of(pid), helpdesk))
    )

    for forbidden in person(pid).forbidden:
        token = CANARIES.get(forbidden)
        if token is not None:
            assert token not in handed, f"{pid} was handed {forbidden}"


def test_the_salary_note_reaches_its_owner() -> None:
    """The other direction. The one person entitled to salary reaches her own note, so the
    refusals above are withholding something that exists rather than something nobody can reach.

    Delete this and the salary canary can be removed from every reach and the refusal test above
    goes on passing."""
    assert CANARIES["hr.salary"] in passage_text(documents(reach_of("u_hr")))


# ================================================================== answering with memory
def test_the_analyst_recalls_to_the_person_it_was_written_around_what_it_learnt_in_its_ceiling(
    analyst: Installation,
) -> None:
    """**The memory clause.** Wei Ling holds exactly what the analyst's ceiling names, in its
    department, so through it she is told what it learnt about hours and nothing else it
    learnt.

    Delete this and memory can be withheld from everybody through every agent, which the refusal
    tests below read as correct."""
    learnings = analyst_learnings(analyst)

    assert recalled(through(reach_of("u_weiling"), analyst), learnings) == {"mem_hours"}
    assert listed("u_weiling", analyst, learnings) == {"mem_hours"}


def test_the_department_admin_who_installed_the_analyst_recalls_what_it_learnt_through_it(
    analyst: Installation,
) -> None:
    """**The lens narrows a wider caller; it does not refuse him.** Aaron holds every client
    column in Maintenance and installed the analyst. Through it he may be told what it learnt
    about hours, which his reach and its ceiling both admit, and never what it learnt about the
    money, which its ceiling does not.

    Failed until 2026-09-14 for `A_WILDCARD_IS_DELETED_BY_THE_LENS_RATHER_THAN_NARROWED`.

    Delete this and the people who install agents, who are the people with wildcards, can reach
    nothing through any of them, which no refusal test can notice."""
    learnings = analyst_learnings(analyst)

    assert recalled(through(reach_of("u_aaron"), analyst), learnings) == {"mem_hours"}


@pytest.mark.parametrize("pid", [*READERS, "u_rupash"])
def test_nothing_learnt_beyond_the_analysts_ceiling_is_recalled_through_it_by_anybody(
    pid: str, analyst: Installation
) -> None:
    """The leak direction. What the analyst learnt under the contract value, and what it learnt
    in Web, are recalled through it by nobody: not the Department Admin who formed the first,
    not the two-department person who formed the second, and not the Super Admin. The canary is
    checked in the text the viewer would show, not only in the ids.

    Delete this and an agent becomes a way to hear, from memory, what its ceiling was written to
    keep out of its answers."""
    learnings = analyst_learnings(analyst)
    run = through(reach_of(pid), analyst)
    told = recalled(run, learnings) | listed(pid, analyst, learnings)

    assert not told & {"mem_money", "mem_web"}, (pid, sorted(told))
    assert CANARIES["client.contract_value"] not in memory_text(told)


def test_what_the_analyst_may_not_recall_is_recalled_by_the_people_entitled_to_it(
    analyst: Installation,
) -> None:
    """The positive sibling that says the refusals above came from the agent. Asked alone, the
    person who formed each memory is told it, and Wei Ling, who may not see the money, is not.

    Delete this and the refusal test above passes against memories nobody may ever recall, so an
    agent that narrowed nothing would pass it too."""
    learnings = analyst_learnings(analyst)

    assert "mem_money" in recalled(reach_of("u_aaron"), learnings)
    assert "mem_web" in recalled(reach_of("u_dual"), learnings)
    assert "mem_money" not in recalled(reach_of("u_weiling"), learnings)


def test_the_helpdesk_recalls_what_it_learnt_from_a_department_to_that_department_only(
    helpdesk: Installation,
) -> None:
    """Memory through the knowledge agent. What the helpdesk learnt from Maintenance's documents
    is recalled to Maintenance through it and not to Web; what it learnt about salary is recalled
    through it by nobody, including the one person who may read salary, because the helpdesk
    holds no capability naming a person. Alone, she is told it.

    Delete this and the helpdesk's memory becomes the one place its refusal to read about people
    does not apply."""
    learnings = helpdesk_learnings(helpdesk)

    assert recalled(through(reach_of("u_weiling"), helpdesk), learnings) == {"mem_rota"}
    assert recalled(through(reach_of("u_siti"), helpdesk), learnings) == set()
    assert "mem_salary" not in recalled(through(reach_of("u_hr"), helpdesk), learnings)
    assert "mem_salary" in recalled(reach_of("u_hr"), learnings)


@pytest.mark.parametrize("pid", READERS)
def test_the_memory_tab_and_the_memory_viewer_agree_about_what_a_run_may_be_told(
    pid: str, helpdesk: Installation, analyst: Installation
) -> None:
    """Two surfaces show one agent's memory, and they reach their answer differently:
    `agent_memory` intersects the caller with the ceiling itself, and the viewer is handed the run
    reach computed here. They must agree for every person and both agents.

    Delete this and the tab can stop applying the agent's ceiling while every test that reads
    the viewer stays green."""
    for agent, learnings in (
        (helpdesk, helpdesk_learnings(helpdesk)),
        (analyst, analyst_learnings(analyst)),
    ):
        assert listed(pid, agent, learnings) == recalled(through(reach_of(pid), agent), learnings)


# ================================================================== answering
def test_one_question_through_one_agent_is_answered_differently_for_two_people(
    helpdesk: Installation,
) -> None:
    """**The sentence the milestone is a composition of.** One installed agent, two people in
    two departments, and what the agent may answer from differs by their reach and not by
    anything in the question. The difference today is carried by memory alone, because the
    document half is the xfail above.

    Delete this and an agent that answered everybody from one person's reach passes every test
    that looks at people one at a time."""
    learnings = helpdesk_learnings(helpdesk)

    def answerable(pid: str) -> tuple[set[str], set[str]]:
        run = through(reach_of(pid), helpdesk)
        return document_ids(documents(run)), recalled(run, learnings)

    maintenance = answerable("u_weiling")
    web = answerable("u_siti")

    assert maintenance != web
    assert "mem_rota" in maintenance[1]
    assert "mem_rota" not in web[1]


class NoRows:
    """A `RowSource` with nothing in it. The rehearsal below is about whether a run starts."""

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, object]]:
        return ()


def test_an_agent_installed_from_the_catalogue_starts_a_run_for_somebody_who_holds_what_it_reads(
    helpdesk: Installation,
) -> None:
    """**An agent that cannot start a run answers nothing.** Rehearsed through the real
    `brain.gate.invoke.invoke`, against the registry the application builds for itself, as a
    person who holds everything the helpdesk's ceiling names.

    Failed until 2026-09-14 for `A_CEILING_THAT_ALLOWS_NO_TOOL_CANNOT_START_A_RUN`.

    Delete this and every other test here passes for an agent the gate will never run."""
    registry = build_registry(source=Settings(env="development").tool_source, records=NoRows())

    rehearsal = rehearse(
        helpdesk, registry=registry, entitlement=reach_of("u_weiling"), assessment=CLEAN, now=NOW
    )

    assert rehearsal.started, "the helpdesk starts no run for a person holding its whole ceiling"


def test_every_canary_planted_here_is_one_the_corpus_declares() -> None:
    """The guard on every canary check above. They assert tokens are absent, and a token renamed
    in the fixture would make them pass for the wrong reason, so the two this file plants are
    asserted to be the corpus's own.

    Delete this and renaming a canary silently empties the leak checks."""
    planted = {CANARIES["client.contract_value"], CANARIES["hr.salary"]}

    assert planted <= canary_tokens()
    assert any(CANARIES["hr.salary"] in one.text for one in CORPUS)
    assert CANARIES["client.contract_value"] in STATEMENTS["mem_money"]
