"""The install acceptance check for the shared start of an agent run's request to a model.

M3.7.2 asks that the start of a request be the same for everybody so the provider's cache is
shared, and the owner decided (needs-rupash 175, option A, 2026-10-12) that it hold only the tools
every person already holds. What an install shows is the product's own run: an agent allowed two
tools, asked by three reserved people, with the model scripted and keeping every message it is
sent.

**What is read is what the model is sent.** The tool the joiner's pack gives everybody is the
install's own `knowledge.search_documents`; the other is its own price list tool, which the pack
does not give. With the switch off, as an install ships it, the person who holds both is sent one
system message naming both, as every run always was. With it on (inside the check's transaction,
rolled back with the rest), the same person's first system message is the protocol and the
knowledge tool and their second is the price list tool; the person who holds the knowledge grant
and not the price list is sent the same first message byte for byte and is sent the price list
tool's name nowhere; and the person who holds the price list and no knowledge grant is sent the
knowledge tool's name nowhere.

**Not proved here, and the proof is held for it.** That a provider charged the second question's
start as cached needs a real provider answering two real questions and reporting cached input
tokens, which the owner asked to be shown on his install. This check shows the start is shared and
tells nobody of a tool they lack; `docs/proof-sweep-holds.json` holds M3.7.2 until the install
shows the saving.

Task ids: M3.7.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1030

# What the check says, one sentence for each way the property can fail.
SHARED_WITH_THE_SWITCH_OFF: Final = "a run shared the start of its request with the switch off"
NOTHING_WAS_SHARED: Final = (
    "the tool everybody holds was not in the shared start with the switch on"
)
A_TOOL_WAS_NAMED_TO_THE_WRONG_PERSON: Final = (
    "the shared start named a tool to a person who cannot use it"
)
THE_START_DIFFERED: Final = "two people who hold the same universal tool were sent different starts"
THE_OWN_TOOLS_WENT_MISSING: Final = (
    "a person's own tool was not sent to them after the shared start"
)
NOT_ANSWERED: Final = "a run did not ask the model"

SEARCH: Final = "knowledge.search_documents"


@check(
    leaves=("M3.7.2",),
    sentence=(
        "An agent allowed the knowledge search and the price list, asked by three people of "
        "acceptance_a, sends one block with the switch off; with it on the first message holds the "
        "knowledge tool alone, the same for two who hold it, and nobody is sent a tool they lack."
    ),
)
async def the_shared_start_names_only_what_everybody_holds(h: Harness) -> None:
    from brain.api_routes import RunToolCaller, policy_of
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.gate.injection import RiskAssessment
    from brain.gate.runtime import AgentRuntime
    from brain.knowledge.row_store import SessionRowSource
    from brain.models.driver import Role
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
    from brain.ops.acceptance_checks_runtime import _NoPassages, _Scripted
    from brain.ops.acceptance_switch import switched
    from brain.ops.acceptance_workspace import LOCAL_READ, LOCAL_TOOL, installed_agent, stored_agent
    from brain.ops.agent_run_store import StoredAgentRuns
    from brain.ops.approved_runs import StoredStandings
    from brain.ops.features import SHARED_TOOL_START
    from brain.ops.shared_start import universal_when_on
    from brain.tools.startup import build_registry

    await h.found_departments()
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    if not registry.has(SEARCH) or not registry.has(LOCAL_TOOL):
        raise CheckFailedError(
            "the application's registry holds a tool this check is about no longer"
        )
    owner = h.principal(A, "starter")
    await h.person(owner, department=A, grants=_in(A, *KNOWLEDGE_READS))
    askers = {
        "both": (*KNOWLEDGE_READS, LOCAL_READ),
        "knowledge": tuple(KNOWLEDGE_READS),
        "price": (LOCAL_READ,),
    }
    for word, held in askers.items():
        person = h.principal(A, word)
        await h.person(person, department=A, grants=_in(A, *held))
    agent = await installed_agent(
        h,
        owner,
        capabilities=(*KNOWLEDGE_READS, LOCAL_READ),
        allowed_tools=(SEARCH, LOCAL_TOOL),
        suffix="_shared",
        scope=Scope.department(A),
    )
    standing = await StoredStandings(h.sessions).standing(agent, h.now)
    if standing is None:
        raise CheckFailedError("the check's agent was installed and the worker read no standing")
    record = await stored_agent(h, agent)

    async def sent_to(word: str, universal: frozenset[str]) -> list[tuple[Role, str]]:
        person = h.principal(A, word)
        reach: EntitlementSet = await h.reach(person)

        async def reach_now(now: Any) -> EntitlementSet:
            return await StoredEntitlements(h.sessions).load(person, now)

        async def not_halted() -> str:
            return ""

        runtime = AgentRuntime(
            record=record,
            asker=reach,
            registry=registry,
            leash=standing.leash,
            tools=RunToolCaller(registry),
            policy_for=policy_of(registry),
            reach_now=reach_now,
            halted=not_halted,
            assessment=RiskAssessment(score=0, matched=()),
            runs=StoredAgentRuns(h.sessions),
            universal=universal,
        )
        model = _Scripted(['{"answer": "done"}'])
        from brain.gate.abstain import SearchScope
        from brain.gate.model_lane import ModelLane
        from brain.models.metering import Meter
        from brain.ops.trace_sink import CountingTraceSink

        await runtime.drafted(
            "What do our documents say?",
            lane=ModelLane(search=_NoPassages(), model=model),
            scope=SearchScope(),
            sink=CountingTraceSink(),
            now=h.now,
            meter=Meter(),
            trace_id=f"{h.trace_id}-{word}-{len(universal)}",
            started=lambda: None,
        )
        if not model.shown:
            raise CheckFailedError(NOT_ANSWERED)
        return [(one.role, one.content) for one in model.shown[0]]

    def system(sent: list[tuple[Role, str]]) -> list[str]:
        return [text for role, text in sent if role is Role.SYSTEM]

    # Off, as an install ships it: nothing is shared and one block names both tools.
    off = await universal_when_on(h.sessions, registry)
    if off:
        raise CheckFailedError(SHARED_WITH_THE_SWITCH_OFF)
    unshared = system(await sent_to("both", off))
    if len(unshared) != 1 or SEARCH not in unshared[0] or LOCAL_TOOL not in unshared[0]:
        raise CheckFailedError(SHARED_WITH_THE_SWITCH_OFF)

    await switched(h, SHARED_TOOL_START, on=True)
    universal = await universal_when_on(h.sessions, registry)
    if SEARCH not in universal or LOCAL_TOOL in universal:
        raise CheckFailedError(NOTHING_WAS_SHARED)
    both = system(await sent_to("both", universal))
    knowledge = system(await sent_to("knowledge", universal))
    price = system(await sent_to("price", universal))

    if len(both) != 2 or SEARCH not in both[0] or LOCAL_TOOL in both[0]:
        raise CheckFailedError(NOTHING_WAS_SHARED)
    if LOCAL_TOOL not in both[1]:
        raise CheckFailedError(THE_OWN_TOOLS_WENT_MISSING)
    if not knowledge or knowledge[0] != both[0]:
        raise CheckFailedError(THE_START_DIFFERED)
    if any(LOCAL_TOOL in text for text in knowledge):
        raise CheckFailedError(A_TOOL_WAS_NAMED_TO_THE_WRONG_PERSON)
    if any(SEARCH in text for text in price) or not any(LOCAL_TOOL in text for text in price):
        raise CheckFailedError(A_TOOL_WAS_NAMED_TO_THE_WRONG_PERSON)
