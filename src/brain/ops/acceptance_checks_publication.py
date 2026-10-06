"""The install acceptance check for publishing an agent to the whole company and retiring it.

M33.1.2.1 asks a super admin to publish and retire global agents. Publishing is
`brain.agent_lifecycle_routes.publish_agent`, which writes `brain.agents.lifecycle.publish`'s
move; retiring is the archive route every agent has. The check asks both routes as reserved
principals and reads what a member of another department is then offered, through the same roster
`/answer` reads.

**A second person publishes, and that is the product's rule rather than the check's.** The agent's
steward holds the visibility authority as well, and is refused; a reserved administrator who is
not the steward publishes it. `brain.agents.lifecycle.A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE`
is what a pass here demonstrates. Somebody holding every lifecycle authority but not the visibility
one is told the agent does not exist, because publishing widens who is told and that is a
different grant (`brain.console.global_surfaces.PUBLISHING_WIDENS_WHO_IS_TOLD_AND_NEVER_WHAT_IS_
REACHED`).

**What publication changes is who may choose the agent, read as `/answer` reads it.** Before, a
member of acceptance_b is not offered the acceptance_a agent; after, they are; once it is retired,
nobody is.

Task ids: M33.1.2.1
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Final, cast

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 408

OFFERED_BEFORE: Final = "a department's agent was offered to a member of another department"
STEWARD_PUBLISHED: Final = "an agent's steward published it alone"
LIFECYCLE_PUBLISHED: Final = (
    "a holder of the lifecycle authority alone was not told the agent is not there"
)
NOT_PUBLISHED: Final = "a second person holding the visibility authority could not publish"
NOT_OFFERED: Final = "a published agent was not offered to a member of another department"
NOT_RETIRED: Final = "a published agent could not be retired"
STILL_OFFERED: Final = "a retired agent was still offered to somebody"


def _request() -> Any:
    from fastapi import FastAPI
    from starlette.requests import Request

    app = FastAPI()
    return app, Request({"type": "http", "app": app, "headers": [], "method": "POST"})


async def _asking(h: Harness, principal_id: str) -> Any:
    """What the routes read of a signed-in person with a second factor."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the routes' boundary, as `brain.ops.acceptance_threads` makes it.
    return cast(
        Any,
        SimpleNamespace(
            caller=SimpleNamespace(principal=person), reach=reach, now=datetime.now(UTC)
        ),
    )


async def _offered(h: Harness, principal_id: str, agent_id: str) -> bool:
    """Whether `/answer` would let this person choose the agent: the roster it reads."""
    from brain.gate.context import Channel
    from brain.gate.roster import answer_roster, viewer_for
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_routing import roster_over

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    stored = await roster_over(h)()
    # The console channel, which `_an_agent` enables the agent on: an agent answers only where it
    # is enabled (M13.7.4), and the route reads the install hashes with the records.
    roster = answer_roster(
        stored.records,
        viewer_for(person),
        channel=Channel.CONSOLE,
        default={},
        tool_names=(),
        install_hashes=stored.install_hashes,
    )
    return agent_id in roster.visible


async def _status(answered: Any) -> tuple[int, dict[str, Any]]:
    return answered.status_code, cast(dict[str, Any], json.loads(bytes(answered.body)))


@check(
    leaves=("M33.1.2.1",),
    sentence=(
        "An acceptance_a agent offered to nobody in acceptance_b is published to the whole company "
        "by an administrator who is not its steward, after its steward and a holder of every "
        "lifecycle authority are each refused; a member of acceptance_b is then offered it, and "
        "once the administrator retires it nobody is."
    ),
)
async def a_second_person_publishes_an_agent_company_wide_and_retires_it(h: Harness) -> None:
    from brain.agent_lifecycle_routes import (
        LifecycleStateAsked,
        PublicationAsked,
        archive_agent,
        publish_agent,
    )
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY, AGENT_PUBLICATION_CAPABILITY
    from brain.core.errors import Absent
    from brain.ops.acceptance_checks_skills import _an_agent

    await h.found_departments()
    visibility = AGENT_PUBLICATION_CAPABILITY.value
    lifecycle = AGENT_LIFECYCLE_CAPABILITY.value
    steward = h.principal(A, "steward")
    publisher = h.principal(A, "publisher")
    keeper = h.principal(A, "keeper")
    member = h.principal(B, "member")
    everywhere = Scope.unrestricted()
    await h.person(steward, department=A, grants=((visibility, everywhere),))
    await h.person(
        publisher, department=A, grants=((visibility, everywhere), (lifecycle, everywhere))
    )
    await h.person(keeper, department=A, grants=((lifecycle, everywhere),))
    await h.person(member, department=B, grants=())
    agent = await _an_agent(h, steward)
    if await _offered(h, member, agent):
        raise CheckFailedError(OFFERED_BEFORE)

    _, request = _request()
    request.app.state.db_sessions = h.sessions
    asked = PublicationAsked(expected_level="department")
    own, _ = await _status(await publish_agent(request, agent, asked, await _asking(h, steward)))
    if own == 200:
        raise CheckFailedError(STEWARD_PUBLISHED)
    try:
        await publish_agent(request, agent, asked, await _asking(h, keeper))
    except Absent:
        pass
    else:
        raise CheckFailedError(LIFECYCLE_PUBLISHED)
    status, body = await _status(
        await publish_agent(request, agent, asked, await _asking(h, publisher))
    )
    if status != 200 or body.get("level") != "company":
        raise CheckFailedError(NOT_PUBLISHED)
    if not await _offered(h, member, agent):
        raise CheckFailedError(NOT_OFFERED)

    status, body = await _status(
        await archive_agent(
            request,
            agent,
            LifecycleStateAsked(expected_state=cast(Any, body["state"])),
            await _asking(h, publisher),
        )
    )
    if status != 200 or body.get("state") != "archived":
        raise CheckFailedError(NOT_RETIRED)
    if await _offered(h, member, agent) or await _offered(h, publisher, agent):
        raise CheckFailedError(STILL_OFFERED)
