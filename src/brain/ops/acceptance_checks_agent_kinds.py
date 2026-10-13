"""The install acceptance check for team agents and personal agents.

The owner's direction on needs item 173 (2026-10-12) is that a person makes their own agent, that
a department administrator makes both kinds, and that a personal agent is found by its owner and
by nobody else. What an install shows is the product's own builder, asked through its route
functions as three reserved people of acceptance_a: a member who holds no authority over agents,
a colleague who holds none either, and an administrator who holds the install authority over the
department.

**The switch is set inside the check and rolled back with it.** `personal_agents` ships off, and
what is proved with it off is that a member's start is refused as it always was. With it on the
same member is offered the personal kind alone, publishes on their own word with nobody's approval,
and the agent that results is personal and theirs; a colleague's list does not hold it, and the
colleague's request to open it is refused in the words and the shape a never-made agent gets, which
is the one answer a hidden agent and a missing one share
(`brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER`). An administrator's list
does not hold it either: the install authority is not an audience. The member's request for a team
agent is refused in a sentence of its own and stores nothing, and the administrator's is made, with
their department as its audience.

**Not claimed here: M39.10.3's second clause.** A personal agent is found by its owner and by
nobody else, which is proved here; that a reader holding the audit capability may also be shown it,
for oversight, is not built, and the leaf is left open for it. The ledger already records every
change to a personal agent, which an auditor reads without the roster listing it.

**Not proved here: a person connecting their own Google account.** That needs the owner's own
Google Cloud project (needs item 173), and a check cannot invent a mailbox. What is proved of
mail is the structural half, in `tests/unit/test_agent_kinds.py`: a team agent's ceiling carries
none of a person's own workspace.

Task ids: M39.10.1, M39.10.2, M39.10.6
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1500

# What the check says, one sentence for each way the property can fail.
BUILDER_OPEN_WITH_THE_SWITCH_OFF: Final = (
    "a person with no authority over agents was let into the builder with the switch off"
)
PERSONAL_NOT_OFFERED: Final = "a person was not offered the personal kind of agent"
TEAM_OFFERED_TO_A_MEMBER: Final = "a person with no authority over agents was offered a team agent"
NOT_PUBLISHED: Final = "a person's own agent was not made on their own word"
NOT_PERSONAL: Final = "an agent a person made for themselves was not personal and theirs"
LISTED_TO_ANOTHER: Final = "a personal agent was listed to somebody who is not its owner"
NOT_LISTED_TO_ITS_OWNER: Final = "a personal agent was not listed to its owner"
OPENED_BY_ANOTHER: Final = "a personal agent was opened by somebody who is not its owner"
TOLD_APART: Final = "a personal agent was refused differently from an agent never made"
TEAM_MADE_BY_A_MEMBER: Final = "a person with no authority over agents made a team agent"
TEAM_REFUSAL_NOT_SAID: Final = "a refused team agent was not refused in its own sentence"
TEAM_NOT_MADE: Final = "an administrator's team agent was not made"
TEAM_NOT_A_DEPARTMENTS: Final = "a team agent was not seen by its department and kept as its kind"


async def _member(h: Harness, role: str) -> str:
    """A reserved person of acceptance_a who holds nothing."""
    made = h.principal(A, role)
    await h.person(made, department=A, grants=())
    return made


def _published(answered: Any) -> tuple[int, dict[str, Any]]:
    import json

    body = json.loads(bytes(answered.body))
    return int(answered.status_code), dict(body)


async def _made(h: Harness, app: FastAPI, who: str, kind: str) -> tuple[int, dict[str, Any], str]:
    """A new draft of `who`, saved, checked and published as this kind, and what the route said."""
    from brain.agent_builder_routes import (
        DraftPublishAsked,
        DraftRevisionAsked,
        DraftSaveAsked,
        DraftStartAsked,
        check_agent_draft,
        publish_agent_draft,
        save_agent_draft,
        start_agent_draft,
    )
    from brain.agents.kinds import AgentKind
    from brain.ops.acceptance_checks_builder import _body, _document
    from brain.ops.acceptance_checks_templates import _asking, _request

    asking = await _asking(h, who)
    started = _body(await start_agent_draft(_request(app), DraftStartAsked(), asking))
    agent_id = str(started["agent_id"])
    persona = "Answers an install acceptance check and nobody else."
    revision = int(
        _body(
            await save_agent_draft(
                _request(app),
                started["draft_id"],
                DraftSaveAsked(
                    document=_document(agent_id, persona=persona), base=started["revision"]
                ),
                asking,
            )
        )["revision"]
    )
    await check_agent_draft(
        _request(app), started["draft_id"], DraftRevisionAsked(revision=revision), asking
    )
    answered = await publish_agent_draft(
        _request(app),
        started["draft_id"],
        DraftPublishAsked(revision=revision, agent_kind=AgentKind(kind), channels=("console",)),
        asking,
    )
    status, body = _published(answered)
    return status, body, agent_id


@check(
    leaves=("M39.10.1", "M39.10.2", "M39.10.6"),
    sentence=(
        "With the switch off a member of acceptance_a is refused the builder; with it on they make "
        "an agent that is personal and theirs, which a colleague and an administrator are neither "
        "listed nor can open; their team agent is refused and stores nothing, and an "
        "administrator's is made and is their department's."
    ),
)
async def a_person_makes_their_own_agent_and_a_team_one_needs_an_admin(
    h: Harness,
) -> None:
    from sqlalchemy import select

    from brain.agent_builder_routes import REFUSED, DraftStartAsked, start_agent_draft
    from brain.agent_routes import agent_workspace, agents
    from brain.agents.kinds import ONLY_AN_ADMINISTRATOR_MAKES_A_TEAM_AGENT
    from brain.core.errors import BrainError
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_agents import _refusal
    from brain.ops.acceptance_checks_builder import _body, _builder
    from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
    from brain.ops.acceptance_switch import switched
    from brain.ops.features import PERSONAL_AGENTS
    from brain.tables.agent import AgentRow

    app = _gallery(h, secrets.token_hex(32))
    member = await _member(h, "kinds_member")
    colleague = await _member(h, "kinds_colleague")
    administrator = await _builder(h, "kinds_administrator")

    # As an install ships it, a person with no authority over agents is refused as before.
    await switched(h, PERSONAL_AGENTS, on=False)
    try:
        await start_agent_draft(_request(app), DraftStartAsked(), await _asking(h, member))
    except BrainError:
        pass
    else:
        raise CheckFailedError(BUILDER_OPEN_WITH_THE_SWITCH_OFF)

    # With it on, the member is offered the personal kind alone and makes one.
    await switched(h, PERSONAL_AGENTS, on=True)
    try:
        offered = _body(
            await start_agent_draft(_request(app), DraftStartAsked(), await _asking(h, member))
        )
    except BrainError as stopped:
        raise CheckFailedError(PERSONAL_NOT_OFFERED) from stopped
    if "personal" not in offered["agent_kinds"]:
        raise CheckFailedError(PERSONAL_NOT_OFFERED)
    if "team" in offered["agent_kinds"]:
        raise CheckFailedError(TEAM_OFFERED_TO_A_MEMBER)
    status, _, mine = await _made(h, app, member, "personal")
    if status != 201:
        raise CheckFailedError(NOT_PUBLISHED)
    row = (await h.execute(select(AgentRow).where(AgentRow.id == mine))).scalar_one_or_none()
    if row is None or row.visibility != "personal" or row.owner_id != member:
        raise CheckFailedError(NOT_PERSONAL)

    # Listed to its owner, and to nobody else, an administrator included.
    async def listed(reader: str) -> set[str]:
        page = await agents(
            _request(app), await _asking(h, reader), ListAsked(search="Acceptance check", limit=50)
        )
        return {one.agent_id for one in page.items}

    if mine not in await listed(member):
        raise CheckFailedError(NOT_LISTED_TO_ITS_OWNER)
    for other in (colleague, administrator):
        if mine in await listed(other):
            raise CheckFailedError(LISTED_TO_ANOTHER)

    async def opened(reader: str, agent_id: str) -> tuple[type[BaseException], str, str] | None:
        return await _refusal(agent_workspace(_request(app), agent_id, await _asking(h, reader)))

    never_made = f"acceptance_{h.run}_never_made"
    for other in (colleague, administrator):
        refused = await opened(other, mine)
        if refused is None:
            raise CheckFailedError(OPENED_BY_ANOTHER)
        if refused != await opened(other, never_made):
            raise CheckFailedError(TOLD_APART)

    # The member's team agent is refused in its own sentence, and nothing is stored for it.
    status, body, wanted = await _made(h, app, member, "team")
    if status != 409 or body.get("outcome") != REFUSED:
        raise CheckFailedError(TEAM_MADE_BY_A_MEMBER)
    if body.get("sentence") != ONLY_AN_ADMINISTRATOR_MAKES_A_TEAM_AGENT:
        raise CheckFailedError(TEAM_REFUSAL_NOT_SAID)
    stored = (
        await h.execute(select(AgentRow.id).where(AgentRow.id == wanted))
    ).scalar_one_or_none()
    if stored is not None:
        raise CheckFailedError(TEAM_MADE_BY_A_MEMBER)

    # An administrator makes a team agent, which is the department's and its colleague's to see.
    status, _, theirs = await _made(h, app, administrator, "team")
    if status != 201:
        raise CheckFailedError(TEAM_NOT_MADE)
    row = (await h.execute(select(AgentRow).where(AgentRow.id == theirs))).scalar_one_or_none()
    if row is None or row.visibility != "department" or row.department != A:
        raise CheckFailedError(TEAM_NOT_A_DEPARTMENTS)
    if theirs not in await listed(colleague):
        raise CheckFailedError(TEAM_NOT_A_DEPARTMENTS)
