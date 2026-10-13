"""The install acceptance check for other people's conversations on an agent's page.

The owner decided on needs item 121 (2026-10-13, option B) that on an agent's page its owner and
administrators also see that other people's conversations happened: who, when, and whether the
agent failed, never the question or the answer. This asks the page's own route
(`brain.agent_conversation_routes.agent_conversations_route`) as four reserved people of
acceptance_a, over runs written through the runtime's own run log.

**What is read.** A department's agent is used by a colleague twice, once to the end and once
failing, and by its steward once. The steward is told of the colleague's two runs, who, when and
how each ended, and not of their own among the others; an administrator who holds the lifecycle
authority over the agent is told of those and of the steward's; the colleague, who holds neither,
is told nothing and is not told that anything was withheld. A personal agent the steward owns and
has used is not read by the administrator even holding that authority: the route answers them as
it answers for an agent never made. And what the answer carries, in every case, has no field that
could hold a word of what was asked.

Task ids: M39.11.1, M39.11.2
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1530

# What the check says, one sentence for each way the property can fail.
STEWARD_NOT_TOLD: Final = (
    "an agent's steward was not told that a colleague's conversations happened"
)
NOT_WHO_WHEN_AND_HOW: Final = (
    "a colleague's conversation was not told as who, when and how it ended"
)
ADMINISTRATOR_NOT_TOLD: Final = "an administrator over the agent was not told of its conversations"
A_COLLEAGUE_WAS_TOLD: Final = (
    "somebody who may not oversee the agent was told of other people's use"
)
WORDS_CARRIED: Final = "other people's conversations carried a field that could hold what was said"
PERSONAL_AGENT_READ: Final = "an administrator was told of a personal agent's runs"
PERSONAL_REFUSED_DIFFERENTLY: Final = "a personal agent was refused differently from one never made"


async def _run(
    h: Harness, person: str, agent_id: str, *, failed: bool, minutes: int, tag: str
) -> None:
    from brain.core.lane import Lane
    from brain.gate.runtime import RunRecord
    from brain.gate.stop import StopReason
    from brain.ops.agent_run_store import StoredAgentRuns

    started = h.now - timedelta(minutes=minutes)
    await StoredAgentRuns(h.sessions).record(
        RunRecord(
            trace_id=f"acceptance_{h.run}_{tag}",
            principal_id=person,
            agent_id=agent_id,
            lane=Lane.ANSWER,
            stop_reason=StopReason.FAULTED if failed else StopReason.ANSWERED,
            turns=1,
            tool_calls=0,
            tokens=10,
            steered=0,
            started_at=started,
            ended_at=started + timedelta(seconds=5),
        )
    )


async def _read(h: Harness, app: FastAPI, reader: str, agent_id: str) -> dict[str, Any]:
    from brain.agent_conversation_routes import agent_conversations_route
    from brain.ops.acceptance_checks_templates import _asking, _request

    answered = await agent_conversations_route(_request(app), agent_id, await _asking(h, reader))
    return dict(answered.model_dump(mode="json"))


@check(
    leaves=("M39.11.1", "M39.11.2"),
    sentence=(
        "A colleague of acceptance_a uses a department's agent twice, once failing: its steward "
        "and an administrator over it are told who, when and how each ended and nothing asked or "
        "answered, the colleague is told nothing, and an administrator is told nothing of a "
        "personal agent."
    ),
)
async def an_agents_steward_is_told_that_others_conversations_happened(h: Harness) -> None:
    from fastapi import FastAPI

    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
    from brain.agents.model import AgentAudience
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_checks_agents import _refusal
    from brain.ops.acceptance_workspace import installed_agent

    await h.found_departments()
    steward, colleague, administrator = (
        h.principal(A, "oversight_steward"),
        h.principal(A, "oversight_colleague"),
        h.principal(A, "oversight_administrator"),
    )
    await h.person(steward, department=A, grants=())
    await h.person(colleague, department=A, grants=())
    await h.person(
        administrator,
        department=A,
        grants=((AGENT_LIFECYCLE_CAPABILITY.value, Scope.department(A)),),
    )
    desk = await installed_agent(
        h,
        steward,
        suffix="oversight",
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=steward, department=A),
    )
    mine = await installed_agent(
        h,
        steward,
        suffix="oversight_personal",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=steward),
    )
    app = FastAPI()
    app.state.db_sessions = h.sessions

    await _run(h, colleague, desk, failed=True, minutes=30, tag="c1")
    await _run(h, colleague, desk, failed=False, minutes=90, tag="c2")
    await _run(h, steward, desk, failed=False, minutes=10, tag="s1")
    await _run(h, steward, mine, failed=False, minutes=5, tag="p1")

    # The steward is told of the colleague's two runs; an administrator, who used the agent
    # themselves not at all, of the steward's as well. Newest first.
    expected = (
        (steward, ["failed", "answered"]),
        (administrator, ["answered", "failed", "answered"]),
    )
    for reader, outcomes in expected:
        seen = await _read(h, app, reader, desk)
        if not seen["oversees"] or len(seen["others"]) != len(outcomes):
            if reader == steward:
                raise CheckFailedError(STEWARD_NOT_TOLD)
            raise CheckFailedError(ADMINISTRATOR_NOT_TOLD)
        if [one["outcome"] for one in seen["others"]] != outcomes:
            raise CheckFailedError(NOT_WHO_WHEN_AND_HOW)
        if any(
            set(one) != {"person", "started_at", "ended_at", "outcome"} for one in seen["others"]
        ):
            raise CheckFailedError(WORDS_CARRIED)

    mine_seen = await _read(h, app, colleague, desk)
    if mine_seen["oversees"] or mine_seen["others"]:
        raise CheckFailedError(A_COLLEAGUE_WAS_TOLD)

    never_made = f"acceptance_{h.run}_never_made"
    refused = await _refusal(_read(h, app, administrator, mine))
    if refused is None:
        raise CheckFailedError(PERSONAL_AGENT_READ)
    if refused != await _refusal(_read(h, app, administrator, never_made)):
        raise CheckFailedError(PERSONAL_REFUSED_DIFFERENTLY)
