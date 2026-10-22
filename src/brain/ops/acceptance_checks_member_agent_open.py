"""Install acceptance check for a member opening one of their agents (M40.2.2.2).

One check. A member opens their own agent's page through the product's own route function, as a
reserved person of acceptance_a, and three people ask beside them: another with the same grants,
one holding the grant that unlocks the Settings tab, and a stranger to the department.

**The page answers a member as their reach allows and no more.** A member holding nothing but the
member grants is shown the agent's header and an empty strip, with no Profile and no composition,
because every one of those travels with a tab they hold no grant for. A member who also holds the
grant for the Settings tab is shown that tab and the Profile that travels with it. The same page,
two readers, and the difference is exactly their reach.

**An agent they may not see answers as one never made.** A personal agent belongs to the person who
made it, so a colleague asking for it is refused in the words and with the cause a made-up
identifier is refused with, and holding the Settings grant changes nothing: the audience is decided
before the strip is.

**A member's own agent goes out on their word when it reaches no further than they do.** The
second check builds a personal agent whose ceiling names the knowledge reads, as a member who holds
them and as one who holds nothing. The first publishes at once, personal and theirs, and the second
is held for a second person and stores nothing, which is the owner's direction on needs item 173
(a person makes their own agent without asking anybody) kept to the case where the ceiling cannot
outgrow its author's reach.

Everything the check makes is written by reserved people of acceptance_a and rolls back with it.

Task ids: M40.2.2.2, M40.2.2.3
"""

from __future__ import annotations

import secrets
from typing import Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1970


async def _opened(h: Harness, app: Any, agent_id: str, who: str) -> Any:
    """What the agent's page route answers `who` for `agent_id`: the page, or how it refused."""
    from brain.agent_routes import agent_workspace
    from brain.core.errors import BrainError
    from brain.ops.acceptance_checks_templates import _asking, _request

    try:
        return await agent_workspace(_request(app), agent_id, await _asking(h, who))
    except BrainError as refused:
        return type(refused), refused.public_message, str(refused)


@check(
    leaves=("M40.2.2.2",),
    sentence=(
        "A member of acceptance_a who made a personal agent opens its page and is shown the tabs "
        "their own grants allow and no others, with the Profile only once they hold the grant for "
        "the Settings tab; a colleague, with that grant or without it, and a person in "
        "acceptance_b are refused as for an agent never made."
    ),
)
async def a_member_opens_their_agent_and_sees_only_their_tabs(
    h: Harness,
) -> None:
    from brain.console.reads import plane_capability_for
    from brain.console.workspace import Tab, tab
    from brain.ops.acceptance_checks_agent_kinds import _made
    from brain.ops.acceptance_checks_templates import _gallery
    from brain.ops.acceptance_switch import switched
    from brain.ops.features import PERSONAL_AGENTS

    await h.found_departments()
    app = _gallery(h, secrets.token_hex(32))
    read = tab(Tab.SETTINGS).read
    # Both counts of `permitted`: the tool's own capability and the plane the read sits on.
    settings = (
        (read.requires.value, Scope.unrestricted()),
        (plane_capability_for(read, read.plane).value, Scope.unrestricted()),
    )
    plain, keen, colleague, stranger = (
        h.principal(A, "opens_plain"),
        h.principal(A, "opens_keen"),
        h.principal(A, "opens_colleague"),
        h.principal(B, "opens_stranger"),
    )
    await h.person(plain, department=A)
    await h.person(keen, department=A, grants=settings)
    await h.person(colleague, department=A, grants=settings)
    await h.person(stranger, department=B)
    await switched(h, PERSONAL_AGENTS, on=True)
    made = []
    for owner in (plain, keen):
        status, _, agent_id = await _made(h, app, owner, "personal")
        if status != 201:
            raise CheckFailedError("a member's own personal agent was not made")
        made.append(agent_id)
    mine, hers = made

    shown = await _opened(h, app, mine, plain)
    if isinstance(shown, tuple) or shown.agent.agent_id != mine:
        raise CheckFailedError("a member was refused the page of their own agent")
    if shown.tabs or shown.profile is not None or shown.composition:
        raise CheckFailedError("a member was shown a tab or a block they hold no grant for")

    wider = await _opened(h, app, hers, keen)
    if isinstance(wider, tuple) or [one.tab for one in wider.tabs] != [Tab.SETTINGS.value]:
        raise CheckFailedError("a member holding the Settings grant was not shown that tab alone")
    if wider.profile is None:
        raise CheckFailedError("a member holding the Settings grant was not shown the Profile")

    never_made = await _opened(h, app, f"acceptance_{h.run}_never_made", plain)
    if not isinstance(never_made, tuple):
        raise CheckFailedError("an agent nobody made had a page")
    for asker in (colleague, stranger):
        if await _opened(h, app, mine, asker) != never_made:
            raise CheckFailedError("an agent's page was refused differently from one never made")


@check(
    leaves=("M40.2.2.3",),
    sentence=(
        "A member of acceptance_a who holds the knowledge reads builds a personal agent that names "
        "them and it is published at once, personal and theirs and not found by a colleague; the "
        "same agent built by a member who holds none is held for a second person and stores "
        "nothing."
    ),
)
async def a_member_s_own_agent_in_their_reach_goes_out_on_their_word(h: Harness) -> None:
    from sqlalchemy import select

    from brain.ops.acceptance_checks import KNOWLEDGE_READS
    from brain.ops.acceptance_checks_agent_kinds import _made
    from brain.ops.acceptance_checks_templates import _gallery
    from brain.ops.acceptance_switch import switched
    from brain.ops.features import PERSONAL_AGENTS
    from brain.tables.agent import AgentRow

    await h.found_departments()
    app = _gallery(h, secrets.token_hex(32))
    holder, empty, colleague = (
        h.principal(A, "owns_reach"),
        h.principal(A, "owns_none"),
        h.principal(A, "owns_other"),
    )
    await h.person(
        holder, department=A, grants=tuple((one, Scope.unrestricted()) for one in KNOWLEDGE_READS)
    )
    await h.person(empty, department=A)
    await h.person(colleague, department=A)
    await switched(h, PERSONAL_AGENTS, on=True)

    status, body, mine = await _made(h, app, holder, "personal", capabilities=KNOWLEDGE_READS)
    if status != 201 or body.get("state") != "published":
        raise CheckFailedError("a member's own agent within their reach was not published at once")
    opened = await _opened(h, app, mine, holder)
    if isinstance(opened, tuple) or opened.agent.owner_id != holder:
        raise CheckFailedError("a member's own published agent was not theirs to open")
    if not isinstance(await _opened(h, app, mine, colleague), tuple):
        raise CheckFailedError("a colleague opened a member's own agent")

    status, body, beyond = await _made(h, app, empty, "personal", capabilities=KNOWLEDGE_READS)
    if status != 202 or body.get("state") != "waiting":
        raise CheckFailedError("an agent reaching further than its author was not held")
    async with h.sessions() as session:
        found = await session.execute(select(AgentRow.id).where(AgentRow.id == beyond))
        stored = found.first()
    if stored is not None:
        raise CheckFailedError(
            "an agent held for a second person was stored before it was approved"
        )
