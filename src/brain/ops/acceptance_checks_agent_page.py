"""Install checks for an agent's page header and tab strip, read through the page's own route.

The agent page draws its header and its tab strip from one answer, `GET /agents/{id}/workspace`
(`brain.agent_routes.agent_workspace`), and the unit tests prove that answer over a stub pool. What
they cannot prove is that on an install, over the product's own tables and an agent installed from
a signed template, the header names the agent, its steward, its department and its lineage to
everybody its audience covers, and the strip offers each reader the tabs their grants open and no
other. This check asks the route itself, as three reserved people a page would really be read by:
the steward, a colleague who may open the Memory tab alone, and a colleague the audience covers
who may open none.

**The header is checked for what everybody is told and for what only the Settings reader is.**
Who built the agent and the state it is in travel with the Settings tab
(`agent_routes.THE_BUILDER_TRAVELS_WITH_THE_AUDIT_AND_THE_STEWARD_TRAVELS_WITH_THE_AGENT`), so the
check asks both halves: a reader without that tab is told the name, the steward and the lineage
and is not told who built it. A check that only looked at the steward would pass over a route
sending the builder to everybody.

**The strip is checked against tabs written out here, not against `tab_strip`.** The tabs a
reader should see are the ones their grants open among those this install populates, and the check
states them in its own words. Comparing the answer with `tab_strip` would compare the route with
itself, which is the constant-against-itself mistake CLAUDE.md names.

**What is not checked here, and why.** M39.1.1.1 asks for twelve parts of an agent and the
composition enumerates ten (`workspace.Part` names no tools and no workflows), so it is left out.
M39.1.2.4's server half, `workspace.deep_link` and `workspace.resolve`, is called by no route and
no alert carries a link yet. M39.1.2.5 is keyboard behaviour in the console, which a server check
cannot reach and `console/tests/agent-page.test.tsx` holds.

Task ids: M39.1.2.1, M39.1.2.2
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_workspace import installed_agent

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.agent_routes import WorkspaceView
    from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page: after the workspace checks.
CHECK_ORDER: Final = 275

A, B = RESERVED_DEPARTMENTS

#: The name the check's template gives the agent, which the header must carry.
TEMPLATE_NAME: Final = "Acceptance check template"

#: The strip each reader should be offered, in the strip's order, written out rather than derived.
STEWARDS_STRIP: Final = ("automations", "memory", "artifacts", "settings")
MEMORY_READERS_STRIP: Final = ("memory",)


def _app(h: Harness) -> FastAPI:
    """What the workspace route reads off the application: the check's own sessions, and no
    takeover store or tool registry, which the header and the strip do not need."""
    from fastapi import FastAPI

    app = FastAPI()
    app.state.db_sessions = h.sessions
    app.state.takeovers = None
    app.state.tools = None
    return app


async def _asking(h: Harness, principal_id: str) -> Any:
    """What the route reads of a signed-in person, admitted on the console with a second factor."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the route's boundary, as `brain.ops.acceptance_checks_templates._asking` makes it:
    # the route reads these three, and a `Caller` is minted only from a verified token.
    return cast(
        Any,
        SimpleNamespace(
            caller=SimpleNamespace(principal=person), reach=reach, now=datetime.now(UTC)
        ),
    )


async def _page(h: Harness, app: FastAPI, agent_id: str, principal_id: str) -> WorkspaceView:
    """The workspace answer the agent page draws, as this person reads it."""
    from starlette.requests import Request

    from brain.agent_routes import agent_workspace

    request = Request({"type": "http", "app": app, "headers": [], "method": "GET"})
    return await agent_workspace(request, agent_id, await _asking(h, principal_id))


def _tab_read(name: str) -> str:
    from brain.console.workspace import Tab, tab

    return tab(Tab(name)).read.requires.value


@check(
    leaves=("M39.1.2.1", "M39.1.2.2"),
    sentence=(
        "An agent installed from a signed template is read through its page's own route by its "
        "steward and two colleagues: each is told its name, steward, department and lineage; "
        "only the Settings reader is told who built it; and each strip holds exactly the tabs "
        "that reader's grants open."
    ),
)
async def an_agents_header_names_its_lineage_and_its_strip_follows_grants(
    h: Harness,
) -> None:
    from brain.console.reads import Plane, plane_capability
    from brain.console.workspace import Tab

    await h.found_departments()
    steward, memory_reader, colleague = (
        h.principal(A, "steward"),
        h.principal(A, "memory_reader"),
        h.principal(A, "colleague"),
    )
    planes = tuple(plane_capability(one).value for one in Plane)
    every_tab = tuple(_tab_read(one.value) for one in Tab)
    await h.person(
        steward,
        department=A,
        grants=[(one, Scope.unrestricted()) for one in (*every_tab, *planes)],
    )
    await h.person(
        memory_reader,
        department=A,
        grants=[(one, Scope.unrestricted()) for one in (_tab_read("memory"), *planes)],
    )
    await h.person(colleague, department=A, grants=[])
    agent_id = await installed_agent(h, steward)
    app = _app(h)

    seen = {who: await _page(h, app, agent_id, who) for who in (steward, memory_reader, colleague)}

    # 1. The header, for everybody the audience covers.
    for page in seen.values():
        header = page.agent
        if header.display_name != TEMPLATE_NAME or header.owner_id != steward:
            raise CheckFailedError("the header did not name the agent and its steward")
        if header.department != A:
            raise CheckFailedError("the header's role line did not name the agent's department")
        if (header.template_id, header.template_version, header.template_name) != (
            agent_id,
            1,
            TEMPLATE_NAME,
        ):
            raise CheckFailedError("the header did not carry the template lineage and version")

    # 2. The strip: the populated tabs each reader's grants open, in the strip's order.
    strips = {who: tuple(one.tab for one in page.tabs) for who, page in seen.items()}
    if strips[steward] != STEWARDS_STRIP:
        raise CheckFailedError("the steward's strip was not every tab this install populates")
    if strips[memory_reader] != MEMORY_READERS_STRIP:
        raise CheckFailedError("a reader holding one tab was not offered that tab alone")
    if strips[colleague]:
        raise CheckFailedError("a reader holding no tab was offered one")

    # 3. Who built it and its state travel with the Settings tab, and only there.
    if seen[steward].agent.created_by != steward or seen[steward].agent.state is None:
        raise CheckFailedError("the Settings reader was not told who built the agent")
    for other in (memory_reader, colleague):
        if seen[other].agent.created_by is not None or seen[other].agent.state is not None:
            raise CheckFailedError("a reader without the Settings tab was told who built it")
