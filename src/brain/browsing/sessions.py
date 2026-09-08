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

**Read-only is shipped first, and this module is where that claim is checkable.** M19.7.1 is
a statement about ordering: the write capability does not exist yet. It did not exist before
this package and it does not exist after it. `BROWSING_CAPABILITIES` holds one entry, its
verb is `read`, `READ_SURFACE` declares `SideEffect.NONE`, and `capability_gaps` reports
anything that would change either. The day somebody adds a write tool, the test that pins
this goes red and closing M19.7.2 becomes a deliberate act rather than a side effect of
adding a tool.

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

Task ids: M19.6.1, M19.6.5, M19.7.1
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

#: The one capability this package ships. Read, and nothing else, on purpose.
BROWSE_SURFACE: Final = Capability(value="read:browser_surface")

#: Every capability browsing offers today. A tuple rather than a bare constant so that
#: `capability_gaps` has something to iterate and a second one cannot be added without
#: appearing in a list somebody reads.
BROWSING_CAPABILITIES: Final[tuple[Capability, ...]] = (BROWSE_SURFACE,)

#: Why there is no second tally of browser sessions.
THE_BUDGET_IS_ALREADY_DECIDED_SOMEWHERE_ELSE: Final = (
    "Browser sessions are one of the seven resources with a global budget, the budget row "
    "exists with a measured reason on it, and admission decides before any work starts. A "
    "counter in this module would be a second answer to the same question, kept in a "
    "different place, updated on a different path, and the failure is not that they "
    "disagree: it is that the one on the screen and the one that admitted the work are not "
    "the same one."
)

#: Why the shipped capability is a read.
SHIPPING_THE_READ_FIRST_IS_A_CLAIM_ABOUT_WHAT_DOES_NOT_EXIST: Final = (
    "M19.7.1 is not satisfied by a read capability existing. It is satisfied by the write "
    "capability not existing, which is a property of the whole repository rather than of "
    "this file, and it stops being true the moment somebody adds a browser tool with a side "
    "effect. So it is pinned by a test that fails on the addition rather than by a comment "
    "asking for one, and the person adding the write closes M19.7.2 on purpose."
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
    return Scope(clauses=(Clause(field="browser_target", op=Op.EQ, value=target.name),))


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
    being counted per domain. That is M19.6.2 and it is not delivered; see
    `concurrency_gaps`.
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
    """Everything that would make "read-only shipped first" untrue (M19.7.1).

    Defaults to what this module ships and takes both sequences so a test can hand it a write
    capability and prove the check is looking. An absence asserted against an empty scan is
    true for every state the source could be in, which is the trap
    `tests/invariants/test_single_implementation.py` records having fallen into itself.
    """
    subjects = tuple(capabilities) or BROWSING_CAPABILITIES
    tools = tuple(definitions) or (READ_SURFACE,)
    gaps: list[str] = []
    for capability in subjects:
        if capability.verb != "read":
            gaps.append(
                f"browsing offers {capability.value}, whose verb is {capability.verb!r}; the "
                "write capability was supposed not to exist yet, and M19.7.2 asks for it to "
                "sit behind envelope approval that nothing here builds"
            )
    for definition in tools:
        if definition.side_effect is not SideEffect.NONE:
            gaps.append(
                f"browsing tool {definition.name} declares side effect "
                f"{definition.side_effect.value}, so a write ships without the assisted "
                "ceiling and the signed per-surface exception M19.7.3 asks for"
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
    """Which of M19.6's limits are enforced and which are not, said rather than assumed.

    The two that are missing are missing for the same structural reason and neither is fixed
    by counting here. `AdmissionRequest` carries a resource, a lane, a traffic class and a
    connector key, and `PER_CONNECTOR` holds only source calls, so there is nowhere to put a
    domain and nowhere to put an agent. `brain.ops.halt.ENFORCED_AXES` records the identical
    shape of gap about halts, from the other side.
    """
    return (
        "M19.6.2 asks for a per-domain concurrency limit and browser sessions are budgeted "
        "once globally; expressing one means adding Resource.BROWSER_SESSIONS to "
        "admission.PER_CONNECTOR and seeding a per-domain row, which changes a module the "
        "whole request path runs through",
        "M19.6.3 asks for a per-agent limit and an AdmissionRequest carries no agent, which "
        "is the same axis brain.ops.halt.ENFORCED_AXES reports as unenforceable for halts",
        "M19.6.4 asks for memory and CPU caps per session, which are cgroup limits on a "
        "container runtime; nothing in this repository starts a container",
    )
