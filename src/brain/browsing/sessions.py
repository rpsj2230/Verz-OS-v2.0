"""Starting a browser run: the one capability that ships, and the one counter that decides.

**There is no second counter here and that is the point of the module.** Architecture section
25 lists browser sessions among the seven things that get a global budget, `brain.ops.
admission` already holds the arithmetic, `Resource.BROWSER_SESSIONS` already has a seeded row
with a measured reason on it, and `brain.orchestration.fanout` landed the same week
delegating rather than counting. A browsing module that kept its own tally would be a second
answer to whether there is room, and the two would disagree on the day it mattered: one of
them would be the number a screen shows and the other would be the number that admitted the
work. `may_start` builds an `AdmissionRequest` and calls `decide`. That is the whole of it.

**The kill switch arrives through the same door.** `admission.decide` asks the halt state
before it looks up a budget row, so a halt on everything refuses a browser session at the
moment it would have started, with `RefusalKind.HALTED` rather than a capacity refusal. The
other half, stopping a session that is already running, is in `brain.browsing.enforcer`,
because that is where the safe points are. Between them M19.6.5 is a switch with something on
both sides of it, which is what `brain.ops.halt` means by its fifth lie.

**Read-only was shipped first, and the write arrived on purpose rather than by addition.**
M19.7.1 was a statement about ordering, pinned by a test that failed the day a write tool
appeared, so that closing M19.7.2 was a decision rather than a side effect. The write is now
`ACT_ON_SURFACE`, and it is the only one: `capability_gaps` reports any other capability that
is not a read and any other tool with a side effect, because every write has to pass through
the approval `brain.browsing.enforcer.compile_policy` demands, and a second write tool would
be a write that route does not know about.

**The write tool declares SEND, the most any browser verb does.** `brain.browsing.envelope.
side_effect_of` puts an upload at SEND because a document leaves the building, and one tool
covers every write verb, so its declaration is the strongest of them. Declaring WRITE would let
an agent ceiling whose `max_side_effect` stops short of SEND reach an upload.

**No handler is registered here.** `READ_SURFACE` is a `ToolDefinition` and `register` takes
the handler from its caller, because a handler would have to drive a browser and there is no
browser in this repository. That is not a gap being papered over: the alternative is a
handler that raises, registered at import, which reads to every catalogue and every reviewer
as a working tool. The definition is real, `ToolRegistry.register` accepts it, and a test
proves that by registering it against a typed stub rather than by asserting it would.

**SERVICE rather than DELEGATED, and the scope that follows.** A browser run does not carry
the caller's own token to somebody else's website; it uses a credential from the vault under
`VaultRole.BROWSER_RUNNER`. That makes it a shared credential, the source does not narrow it
for us, and `brain.tools.registry.assert_service_tool_is_scoped` therefore requires a scope
predicate that narrows something. `surface_scope` is that predicate and it narrows to one
declared target.

Task ids: M19.6.1, M19.6.5, M19.7.1, M19.7.2
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from brain.browsing.targets import Target, Verb, is_write
from brain.core.entitlement import Capability
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition
from brain.core.lane import Lane
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import TrafficClass
from brain.ops.admission import (
    AdmissionDecision,
    AdmissionRequest,
    Budget,
    CapacityState,
    Resource,
    decide,
)
from brain.ops.halt import NOTHING_HALTED, HaltState

#: Reading a declared surface.
BROWSE_SURFACE: Final = Capability(value="read:browser_surface")

#: Acting on a declared surface. Held by whoever may perform or approve a browser write.
ACT_ON_SURFACE_CAPABILITY: Final = Capability(value="write:browser_surface")

#: Every capability browsing offers. A tuple rather than bare constants so that
#: `capability_gaps` has something to iterate and a third one cannot be added without
#: appearing in a list somebody reads.
BROWSING_CAPABILITIES: Final[tuple[Capability, ...]] = (BROWSE_SURFACE, ACT_ON_SURFACE_CAPABILITY)

#: The row field a browser credential and a browser approval are both narrowed on.
TARGET_FIELD: Final = "browser_target"

#: Why there is no second tally of browser sessions.
THE_BUDGET_IS_ALREADY_DECIDED_SOMEWHERE_ELSE: Final = (
    "Browser sessions are one of the seven resources with a global budget, the budget row "
    "exists with a measured reason on it, and admission decides before any work starts. A "
    "counter in this module would be a second answer to the same question, kept in a "
    "different place, updated on a different path, and the failure is not that they "
    "disagree: it is that the one on the screen and the one that admitted the work are not "
    "the same one."
)

#: Why there is exactly one write tool.
EVERY_BROWSER_WRITE_GOES_THROUGH_THE_ONE_APPROVED_TOOL: Final = (
    "A browser write reaches somebody else's system of record through a page that decides "
    "what a click does. The approval that stands between the two is attached to one tool and "
    "one capability, so a second write tool or capability would be a write the approval route "
    "does not know exists, and it would ship looking exactly as reviewed as the first."
)


class SessionError(Exception):
    """A browser session was asked for in terms nothing could admit."""


class SurfaceReading(Entity):
    """What one read of a declared surface returns.

    An `Entity` because the redactor walks entities and refuses anything else, which is the
    rule `brain.core.redaction.assert_tool_returns_typed_result` applies at registration. The
    fields are the declared ones from the surface map, carried as pairs rather than as a free
    mapping so that what came back can be compared with what was declared.
    """

    surface: str
    origin: str
    values: tuple[tuple[str, str], ...] = ()


ACT_ON_SURFACE: Final = ToolDefinition(
    name="browser.act_on_surface",
    description=(
        "Click, type, submit or upload on one declared surface of a browsing target, within an "
        "envelope a person approved. Refused for any write the envelope did not approve."
    ),
    entity="browser_surface",
    required_capability=ACT_ON_SURFACE_CAPABILITY.value,
    side_effect=SideEffect.SEND,
    identity_mode=IdentityMode.SERVICE,
    source="browser",
)


READ_SURFACE: Final = ToolDefinition(
    name="browser.read_surface",
    description=(
        "Read the declared fields from one declared surface of a browsing target. Opens and "
        "reads only; it cannot click, type, submit or upload."
    ),
    entity="browser_surface",
    required_capability=BROWSE_SURFACE.value,
    side_effect=SideEffect.NONE,
    identity_mode=IdentityMode.SERVICE,
    source="browser",
)


def surface_scope(target: Target) -> Scope:
    """The predicate that narrows the shared browser credential to one declared target.

    Required rather than optional: a SERVICE tool without one reaches everything its
    credential reaches, and the source will not narrow it for us. `Scope.unrestricted` is
    refused by the registry as firmly as no scope at all, which is the check this exists to
    satisfy honestly rather than to satisfy at all.
    """
    return Scope(clauses=(Clause(field=TARGET_FIELD, op=Op.EQ, value=target.name),))


def may_start(
    *,
    trace_id: str,
    budgets: Sequence[Budget],
    state: CapacityState,
    now: datetime,
    traffic: TrafficClass = TrafficClass.AUTOMATION,
    lane: Lane = Lane.TASK,
    halts: HaltState = NOTHING_HALTED,
) -> AdmissionDecision:
    """Ask the admission controller whether there is room for one more browser session.

    A thin call and deliberately thin. Everything interesting about the decision, the global
    budget, the per-class share, the queue position, the shed rule and the halt, belongs to
    `brain.ops.admission` and is tested there. What this adds is the resource and the
    defaults: a browser run is task-lane automation, because nobody watches a browser drive a
    portal, and `Resource.BROWSER_SESSIONS` is unkeyed because that budget is global.

    `key` is left empty and cannot be otherwise. `BROWSER_SESSIONS` is not in
    `admission.PER_CONNECTOR`, so an `AdmissionRequest` naming a domain raises rather than
    being counted per domain. The per-domain and per-agent limits are asked beside this, in
    `brain.browsing.concurrency.may_open`, which calls this first.
    """
    request = AdmissionRequest(
        trace_id=trace_id,
        lane=lane,
        traffic_class=traffic,
        resource=Resource.BROWSER_SESSIONS,
        units=1,
    )
    return decide(request, budgets, state, now=now, halts=halts)


def capability_gaps(
    capabilities: Sequence[Capability] = (),
    definitions: Sequence[ToolDefinition] = (),
) -> tuple[str, ...]:
    """Every browser capability or tool that could write outside the approved route.

    A capability that is not a read and is not `ACT_ON_SURFACE_CAPABILITY`, and a tool with a
    side effect that is not `ACT_ON_SURFACE`. See
    `EVERY_BROWSER_WRITE_GOES_THROUGH_THE_ONE_APPROVED_TOOL`.

    Defaults to what this module ships and takes both sequences so a test can hand it a second
    write and prove the check is looking. An absence asserted against an empty scan is
    true for every state the source could be in, which is the trap
    `tests/invariants/test_single_implementation.py` records having fallen into itself.
    """
    subjects = tuple(capabilities) or BROWSING_CAPABILITIES
    tools = tuple(definitions) or (READ_SURFACE, ACT_ON_SURFACE)
    gaps: list[str] = []
    for capability in subjects:
        if capability.verb != "read" and capability != ACT_ON_SURFACE_CAPABILITY:
            gaps.append(
                f"browsing offers {capability.value}, whose verb is {capability.verb!r}, and it "
                "is not the one write capability envelope approval is attached to"
            )
    for definition in tools:
        if definition.side_effect is not SideEffect.NONE and definition.name != ACT_ON_SURFACE.name:
            gaps.append(
                f"browsing tool {definition.name} declares side effect "
                f"{definition.side_effect.value} and is not {ACT_ON_SURFACE.name}, so its writes "
                "reach no approval"
            )
    return tuple(gaps)


def write_verbs_offered(target: Target) -> tuple[Verb, ...]:
    """The write verbs a target declares, which is what a write capability would have to cover.

    Reported rather than acted on. A target may legitimately declare write surfaces before
    anything can reach them: the declaration is configuration and the capability is the
    thing that has not shipped, and confusing the two would make the registry unable to
    describe a system fully until the write path existed.
    """
    found: set[Verb] = set()
    for surface in target.surfaces:
        found |= {verb for verb in surface.verbs if is_write(verb)}
    return tuple(sorted(found, key=lambda verb: verb.value))


def concurrency_gaps() -> tuple[str, ...]:
    """Which of M19.6's limits are not enforced, said rather than assumed.

    The per-domain and per-agent limits are decided in `brain.browsing.concurrency`; what they
    decide against is counted by nobody yet, because nothing holds a session open.
    """
    return (
        "the per-domain and per-agent session counts brain.browsing.concurrency decides "
        "against are filled by nothing, because there is no runner holding a session open",
        "M19.6.4 asks for memory and CPU caps per session, which are cgroup limits on a "
        "container runtime; nothing in this repository starts a container",
    )
