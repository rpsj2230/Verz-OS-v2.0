"""Install acceptance checks for who sees an agent, what a template declares, and a run's graph.

Three leaves that were built and tested over fakes and had no check on an install: an agent's
audience at each of its three levels (M13.1.2), the manifest a template version is (M13.2.2), and
the read-only graph the Trace page draws of a completed run (M20.2.1). Each check calls the route
its console page calls, as the reader that page serves, inside the check's rolled-back transaction.

**The Agents page is read as three people, and the route is asked nothing else.** A steward and a
colleague in acceptance_a and somebody in acceptance_b each read `GET /agents` through
`brain.agent_routes.agents`, narrowed by a search to the run's own agent ids so that no agent a
real person made is read about, listed or counted. One agent is made at each level, personal to the
steward, acceptance_a's, and the whole company's, and each reader's list is held to exactly the
agents the level admits them to. The workspace route is asked too, because a level that hides an
agent from the list and opens its page has hidden nothing: an agent outside the reader's audience
has to be the very refusal an agent that was never made gets. See
`A_HIDDEN_AGENT_IS_REFUSED_AS_A_MISSING_ONE`.

**The manifest is proved by what the install keeps of a version and reads back from it.** A
version declaring all ten things the leaf names (identity, persona, skills, tools, connectors,
scope, tier, leash, golden set and placeholders) is stored as a publish stores one, and the
template page's own route shows it as written. Two of the ten have nowhere on that page: the scope
and the placeholders. So the stored row is also read back through `brain.agent_routes.manifest_of`,
the function that route calls on every row, and has to come back as the very manifest that was
signed, digest for digest. The install's database is then asked to keep a version missing one of
the schema's paths and one carrying a path outside it, and has to refuse both, which is what makes
the schema the install's and not only this release's. Rejected: proving the schema on
`TemplateManifest` alone, which is the rule written once in Python; a row written by any other door
meets the database's constraint.

**The trace graph is the console's drawing over this route's answer.** `console/src/pages/audit/
TracePage.tsx` draws with React Flow whatever `POST /traces/{trace_id}/read` answers, and an install
check cannot see a canvas. What it can prove is everything the drawing needs: a completed run
recorded by the recorder the application installs, read through `brain.trace_routes.read_trace` by
a person whose sign-in carries the payload role, comes back as one graph hanging from its request
step, every edge pointing at a step that is there, and the request step naming how the run ended
in the vocabulary the page refuses to draw a run without (`graph.ts`'s `RUN_ENDINGS`). A sign-in
without the role gets the refusal a trace that was never recorded gets. The drawing itself is held
by `console/tests/trace-graph.test.tsx` and `console/tests/trace-page.test.tsx`. See
`THE_GRAPH_IS_DRAWN_BY_THE_CONSOLE_AND_PROVED_BY_ITS_ROUTE`.

Task ids: M13.1.2, M13.2.2, M20.2.1
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.agents.template import SignedManifest

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 452

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the workspace is asked as well as the list.
A_HIDDEN_AGENT_IS_REFUSED_AS_A_MISSING_ONE: Final = (
    "An agent left off somebody's list and opened for them by its address has been hidden from "
    "nobody, and an agent whose page refuses them differently from an agent that was never made "
    "tells them it exists. So the check asks the workspace route for an agent outside the "
    "reader's audience and for one that was never made, and the two refusals must be one."
)

#: Why the trace check proves a route and not a drawing.
THE_GRAPH_IS_DRAWN_BY_THE_CONSOLE_AND_PROVED_BY_ITS_ROUTE: Final = (
    "The Trace page draws with React Flow whatever its read route answers, and an install check "
    "cannot see a canvas. It proves the route the page reads: a completed run comes back as one "
    "graph hanging from its request, every edge pointing at a step that is there, the request "
    "naming how the run ended, and only for a sign-in carrying the payload role. The drawing is "
    "held by the console's own page tests."
)

# ------------------------------------------------------------------------ the figures
#: The three levels, as the suffix of the agent made at each.
PERSONAL: Final = "_personal"
DEPARTMENT: Final = "_department"
COMPANY: Final = "_company"

#: Why the check reads a trace, as `brain.ops.tracing.PayloadRead` requires a reason.
READ_REASON: Final = "An install acceptance check reading its own run's trace"

#: How a run ended, in the words `console/src/components/graph.ts` will draw a run for. Restated
#: rather than imported, because it is the console's vocabulary; a test holds it to the TypeScript.
RUN_ENDINGS: Final[frozenset[str]] = frozenset(
    {"answered", "nothing_returned", "unresolved", "degraded", "failed"}
)

# ------------------------------------------------------------------------ the sentences
LISTED_OUTSIDE_ITS_AUDIENCE: Final = "an agent was listed to somebody outside its audience"
NOT_LISTED_TO_ITS_AUDIENCE: Final = "an agent was not listed to somebody in its audience"
HIDDEN_AGENT_OPENED: Final = "an agent's page opened for somebody outside its audience"
HIDDEN_AGENT_TOLD_APART: Final = (
    "an agent outside a reader's audience was refused differently from one never made"
)
OWN_AGENT_NOT_OPENED: Final = "an agent's page did not open for somebody in its audience"

VERSION_NOT_KEPT: Final = "a template version declaring every section was not kept"
PAGE_NOT_AS_WRITTEN: Final = "the template page did not show a version's sections as written"
NOT_READ_BACK: Final = "a stored version did not read back as the manifest that was signed"
MISSING_PATH_KEPT: Final = "the install kept a template version missing a path of the schema"
OTHER_PATH_KEPT: Final = "the install kept a template version holding a path outside the schema"

TRACE_NOT_READ: Final = "a completed run's trace was not read back for a reader holding the role"
NOT_ONE_GRAPH: Final = "a run's trace did not come back as one graph hanging from its request"
NO_ENDING: Final = "a run's trace did not name how the run ended"
READ_WITHOUT_THE_ROLE: Final = "a trace was shown to a sign-in without the payload role"
REFUSAL_TOLD_APART: Final = "a trace refused for want of the role was told apart from a missing one"


def _request(app: FastAPI, method: str = "GET") -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": app, "headers": [], "method": method})


def _app(h: Harness) -> FastAPI:
    from fastapi import FastAPI

    app = FastAPI()
    app.state.db_sessions = h.sessions
    return app


async def _refusal(call: Any) -> tuple[type[BaseException], str, str] | None:
    """How a route refused, as a person and a log see it, or None when it answered."""
    from brain.core.errors import BrainError

    try:
        await call
    except BrainError as refused:
        return type(refused), refused.public_message, str(refused)
    return None


# -------------------------------------------------------------- M13.1.2 three levels of audience
@check(
    leaves=("M13.1.2",),
    sentence=(
        "Three agents made in acceptance_a, one personal to its steward, one for the department "
        "and one for the whole company: the Agents page lists all three to the steward, the "
        "department's and the company's to a colleague, and only the company's to somebody in "
        "acceptance_b, whose page for the department's agent is refused as one never made is."
    ),
)
async def an_agent_is_seen_by_exactly_the_audience_its_level_names(h: Harness) -> None:
    from brain.agent_routes import agent_workspace, agents
    from brain.agents.model import AgentAudience
    from brain.knowledge.visibility import Visibility
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_templates import _asking
    from brain.ops.acceptance_workspace import installed_agent

    await h.found_departments()
    steward, colleague, outsider = (
        h.principal(A, "steward"),
        h.principal(A, "colleague"),
        h.principal(B, "outsider"),
    )
    for one, department in ((steward, A), (colleague, A), (outsider, B)):
        await h.person(one, department=department)
    levels = {
        PERSONAL: AgentAudience(level=Visibility.PERSONAL, owner_id=steward),
        DEPARTMENT: AgentAudience(level=Visibility.DEPARTMENT, owner_id=steward, department=A),
        COMPANY: AgentAudience(level=Visibility.COMPANY, owner_id=steward),
    }
    made = {
        level: await installed_agent(h, steward, suffix=level, audience=audience)
        for level, audience in levels.items()
    }
    app = _app(h)
    # Narrowed to this run's agents, so nothing a real person made is read about or counted.
    mine = ListAsked(search=f"acceptance_{h.run}", limit=50)

    async def listed(reader: str) -> set[str]:
        page = await agents(_request(app), await _asking(h, reader), mine)
        return {one.agent_id for one in page.items} & set(made.values())

    expected = {
        steward: {made[PERSONAL], made[DEPARTMENT], made[COMPANY]},
        colleague: {made[DEPARTMENT], made[COMPANY]},
        outsider: {made[COMPANY]},
    }
    for reader, wanted in expected.items():
        seen = await listed(reader)
        if seen - wanted:
            raise CheckFailedError(LISTED_OUTSIDE_ITS_AUDIENCE)
        if wanted - seen:
            raise CheckFailedError(NOT_LISTED_TO_ITS_AUDIENCE)

    # The page, opened by address. See `A_HIDDEN_AGENT_IS_REFUSED_AS_A_MISSING_ONE`.
    async def opened(reader: str, agent_id: str) -> tuple[type[BaseException], str, str] | None:
        return await _refusal(agent_workspace(_request(app), agent_id, await _asking(h, reader)))

    never_made = f"acceptance_{h.run}_never_made"
    for reader, hidden in ((outsider, made[DEPARTMENT]), (colleague, made[PERSONAL])):
        refused = await opened(reader, hidden)
        if refused is None:
            raise CheckFailedError(HIDDEN_AGENT_OPENED)
        if refused != await opened(reader, never_made):
            raise CheckFailedError(HIDDEN_AGENT_TOLD_APART)
    for reader, own in ((colleague, made[DEPARTMENT]), (outsider, made[COMPANY])):
        if await opened(reader, own) is not None:
            raise CheckFailedError(OWN_AGENT_NOT_OPENED)


# --------------------------------------------------------------- M13.2.2 the manifest's schema
def _every_section(h: Harness, administrator: str) -> Any:
    """A manifest declaring all ten things M13.2.2 names, each with a value of its own."""
    from brain.agents.template import (
        GoldenCase,
        LeashRung,
        ManifestAuthority,
        ManifestGuardrails,
        ManifestIdentity,
        Placeholder,
        SkillRef,
        TemplateManifest,
    )
    from brain.core.entitlement import Capability
    from brain.core.envelope import SideEffect
    from brain.gate.injection import AutonomyTier
    from brain.models.routing import Tier

    word = h.word()
    return TemplateManifest(
        identity=ManifestIdentity(
            template_id=f"acceptance_{h.run}_schema",
            version=1,
            published_by=administrator,
            display_name="Acceptance check schema",
            summary="Declares every section a template may.",
        ),
        persona=f"Answers an install acceptance check about {word} and nobody else.",
        tier=Tier.HEAVY,
        skills=(
            SkillRef(name="acceptance-skill", digest=hashlib.sha256(word.encode()).hexdigest()),
        ),
        authority=ManifestAuthority(
            scope=Scope.department(A),
            capabilities=(Capability(value="read:price_list"),),
            allowed_tools=("acceptance.search",),
        ),
        connectors=("acceptance_source",),
        guardrails=ManifestGuardrails(
            max_side_effect=SideEffect.DRAFT,
            leash=(LeashRung(target="acceptance.search", rung=AutonomyTier.SHADOW),),
        ),
        golden_set=(
            GoldenCase(question=f"What is {word}?", expectation="It names the check's word."),
            GoldenCase(question="Who may ask?", expectation="Somebody in acceptance_a."),
        ),
        placeholders=(Placeholder(key="price_list", prompt="Where the price list is kept"),),
    )


def _shown_as_written(view: Any, signed: SignedManifest) -> bool:
    """Whether the template page shows each section it has a place for as the version wrote it."""
    manifest = signed.manifest
    return (
        view.entry.template_id == manifest.identity.template_id
        and view.entry.version == manifest.identity.version
        and view.entry.display_name == manifest.identity.display_name
        and view.persona == manifest.persona
        and view.tier == manifest.tier.value
        and view.skills == [one.name for one in manifest.skills]
        and view.connectors == list(manifest.connectors)
        and view.tools == list(manifest.authority.allowed_tools)
        and view.capabilities == [one.value for one in manifest.authority.capabilities]
        and [(one.target, one.rung) for one in view.leash]
        == [(one.target, one.rung.name.lower()) for one in manifest.guardrails.leash]
        and view.max_side_effect == manifest.guardrails.max_side_effect.value
        and view.golden_cases == len(manifest.golden_set)
    )


@check(
    leaves=("M13.2.2",),
    sentence=(
        "A template version declaring identity, persona, skills, tools, connectors, scope, tier, "
        "leash, golden set and placeholders is kept by this install, shown on its template page "
        "as written and read back as the manifest that was signed; the install refuses to keep "
        "a version missing a path of that schema or holding one outside it."
    ),
)
async def a_template_version_holds_every_section_and_nothing_else(h: Harness) -> None:
    from sqlalchemy.exc import DBAPIError

    from brain.agent_routes import agent_template, manifest_of
    from brain.agents.install_store import version_values
    from brain.agents.template import content_digest, publish
    from brain.ops.acceptance_checks_templates import _administrator, _asking
    from brain.tables.template import TemplateVersionRow

    administrator = await _administrator(h)
    signed = publish(
        _every_section(h, administrator),
        key=secrets.token_hex(32),
        signed_by=administrator,
        at=h.now,
    )
    kept = version_values(signed)
    try:
        await h.execute(*h.attributed(administrator), insert(TemplateVersionRow).values(**kept))
    except DBAPIError as refused:
        raise CheckFailedError(VERSION_NOT_KEPT) from refused

    template_id = signed.manifest.identity.template_id
    view = await agent_template(_request(_app(h)), template_id, await _asking(h, administrator))
    if not _shown_as_written(view, signed):
        raise CheckFailedError(PAGE_NOT_AS_WRITTEN)
    # The scope and the placeholders have no place on the page, so the row the route reads is
    # read back through the route's own reader and held to the signed digest.
    document = (
        await h.execute(
            select(TemplateVersionRow.document).where(
                TemplateVersionRow.template_id == template_id, TemplateVersionRow.version == 1
            )
        )
    ).scalar_one()
    try:
        again = manifest_of(document)
    except (KeyError, ValueError) as unread:
        raise CheckFailedError(NOT_READ_BACK) from unread
    if content_digest(again) != signed.content_digest or again != signed.manifest:
        raise CheckFailedError(NOT_READ_BACK)

    async def refuses(version: int, document: dict[str, Any]) -> bool:
        try:
            await h.execute(
                *h.attributed(administrator),
                insert(TemplateVersionRow).values(
                    **{**kept, "version": version, "document": document}
                ),
            )
        except DBAPIError:
            return True
        return False

    whole = dict(kept["document"])
    if not await refuses(2, {path: one for path, one in whole.items() if path != "placeholders"}):
        raise CheckFailedError(MISSING_PATH_KEPT)
    if not await refuses(3, {**whole, "audience": "company"}):
        raise CheckFailedError(OTHER_PATH_KEPT)


# ----------------------------------------------------- M20.2.1 a completed run's graph, read
def _asking_with_roles(h: Harness, person: Any, roles: tuple[str, ...]) -> Any:
    """What the trace route reads of a signed-in person: their id, their token's claims, now."""
    from brain.ops.acceptance_audit import OTHER_REALM_ROLES, _signed_in

    claims = _signed_in(h, person.id, (*OTHER_REALM_ROLES, *roles))
    # A cast at the route's boundary, as `brain.ops.acceptance_checks_templates._asking` makes
    # it: the route reads these three, and a `Caller` is minted only from a verified token.
    return cast(
        Any,
        SimpleNamespace(
            caller=SimpleNamespace(principal=person, principal_id=person.id, claims=claims),
            now=datetime.now(UTC),
        ),
    )


@check(
    leaves=("M20.2.1",),
    sentence=(
        "A completed run recorded by the trace recorder this install runs is read through the "
        "Trace page's route by a person whose sign-in carries the payload role, as one graph "
        "hanging from its request with every edge pointing at a step that is there and the "
        "request naming how the run ended; a sign-in without the role is refused as for no trace."
    ),
)
async def a_completed_runs_graph_is_read_for_the_trace_page(h: Harness) -> None:
    from brain.core.errors import BrainError
    from brain.core.lane import Lane
    from brain.core.redaction import ChannelPayload
    from brain.gate.context import Channel
    from brain.gate.finish import Finished, Origin, ToolCallOutcome, finish
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.trace_store import TraceRecorder
    from brain.ops.tracing import PAYLOAD_ROLE, StepKind
    from brain.trace_routes import TraceReadAsked, read_trace

    reader_id = h.principal(A, "operator")
    await h.person(reader_id, department=A)
    reader = await StoredPrincipals(h.sessions).live_principal(reader_id)
    if reader is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    trace_id = f"{h.trace_id}-graph"
    await finish(
        (TraceRecorder(h.sessions, environment=h.settings.env),),
        Finished(
            Origin(trace_id=trace_id, principal=reader, channel=Channel.CONSOLE),
            h.now,
            ToolCallOutcome(refused=False, disclosed=ChannelPayload(records=())),
            completed_at=h.now,
            entitlement_hash=(await h.reach(reader_id)).ent_hash(),
            lane=Lane.TASK,
            tool_calls=2,
        ),
    )
    app = _app(h)
    asked = TraceReadAsked(reason=READ_REASON)

    async def read(roles: tuple[str, ...], which: str) -> Any:
        return await read_trace(
            _request(app, "POST"), which, asked, _asking_with_roles(h, reader, roles)
        )

    try:
        graph = await read((PAYLOAD_ROLE,), trace_id)
    except BrainError as refused:
        raise CheckFailedError(TRACE_NOT_READ) from refused
    steps = {one.step: one for one in graph.steps}
    roots = [one for one in graph.steps if one.parent is None]
    hanging = [one for one in graph.steps if one.parent is not None]
    if (
        len(steps) != len(graph.steps)
        or len(roots) != 1
        or roots[0].kind != StepKind.REQUEST.value
        or len(hanging) < 2
        or any(one.parent not in steps for one in hanging)
        or not any(one.parent == roots[0].step for one in hanging)
    ):
        raise CheckFailedError(NOT_ONE_GRAPH)
    if roots[0].attributes.get("outcome") not in RUN_ENDINGS:
        raise CheckFailedError(NO_ENDING)

    # A sign-in without the role, and a trace never recorded, are one refusal.
    without = await _refusal(read((), trace_id))
    if without is None:
        raise CheckFailedError(READ_WITHOUT_THE_ROLE)
    if without != await _refusal(read((PAYLOAD_ROLE,), f"{h.trace_id}-never")):
        raise CheckFailedError(REFUSAL_TOLD_APART)
