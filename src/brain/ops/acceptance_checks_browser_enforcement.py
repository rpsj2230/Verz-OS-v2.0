"""Install acceptance check: a browser run is held to the envelope it was sealed with, and the first
thing it is refused ends it, as the worker's driver and the product's runner decide it together.

**What this joins that the runner's own tests do not.** `brain.browsing.runner.drive` is tested on
its own, and `brain.browsing.enforcer.recheck` is tested on its own. A run is the two of them with
the driver between, and a refusal the runner makes has to arrive in the control plane as a record
the replay agrees was an attempt, with the page never having been touched. This check sends one
sealed envelope through `driver.run_envelope` to the runner, in this process, over a page the check
holds, five times: once with every instruction inside the envelope, and once for each way an
instruction can leave it.

- **The policy is the envelope's** (M19.3.1): the start line carries the digest the control plane
  sealed, a policy rebuilt from the start line carries the same one, a start line whose parts were
  edited starts nothing, and `Policy` is a frozen value with no field that would let it be re-read.
- **An invented reference is refused** (M19.3.2): a click on an element no snapshot named never
  reaches the page.
- **An origin nobody declared is refused** (M19.3.3): a navigation that lands somewhere else ends
  the run before anything is done there.
- **A verb or a count the envelope does not hold is refused** (M19.3.4): a submit where only a
  click was approved, and a second click where one was.

Each refusal ends the run on its reason, the page's `act` is never called for it, and the replay
reports the attempt, because `recheck` reads none of the container's verdicts.

**The page is a stand-in and says so**, as in `acceptance_checks_browser`: the code that decides is
run unchanged and the page it drives is held here. What this cannot show is a container that is
compromised or a Chromium that reports a tree no stand-in imagined, and that is the rehearsal.

The check writes nothing: no database row, no object, no session.

Task ids: M19.3.1, M19.3.2, M19.3.3, M19.3.4
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError, dataclass, field
from datetime import datetime
from typing import Any, Final

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_browser import InProcessRunner, _Link, _Objects
from brain.ops.acceptance_run import Harness

#: Where this module's check stands on the Install page, after the read check's (2306).
CHECK_ORDER: Final = 2307

#: The one origin the made-up website allows, and one it does not. Nothing resolves either.
ORIGIN: Final = "https://acceptance-check.invalid"
ELSEWHERE: Final = "https://elsewhere.invalid"

#: The reference of the one button the stand-in page shows.
BUTTON: Final = "n12"


@dataclass
class _Page:
    """A browser that shows one button and records every call. `lands_on` is where it navigates."""

    lands_on: str = ORIGIN
    at: str = "null"
    navigated: list[str] = field(default_factory=list)
    acted: list[tuple[str, str]] = field(default_factory=list)

    def navigate(self, url: str) -> None:
        self.navigated.append(url)
        self.at = self.lands_on

    def origin(self) -> str:
        return self.at

    def accessibility_tree(self) -> Any:
        return {
            "nodes": [
                {
                    "nodeId": "1",
                    "backendDOMNodeId": 12,
                    "role": {"value": "button"},
                    "name": {"value": "File"},
                }
            ]
        }

    def act(self, verb: Any, ref: str, text: str) -> None:
        self.acted.append((str(verb), ref))

    def capture(self) -> bytes:
        return b"a masked picture"


@dataclass
class _Script:
    """The instructions an actor sends, one at a time, whatever the page shows."""

    steps: Sequence[Any]

    def next(self, index: int, last: Any) -> Any:
        return self.steps[index - 1] if index <= len(self.steps) else None


A_REFUSAL_ENDS_THE_RUN_AND_IS_REPORTED: Final = (
    "a refused instruction was performed, did not end the run on its reason, or was not reported "
    "as an attempt by the replay"
)
THE_POLICY_IS_NOT_THE_ENVELOPES: Final = (
    "the policy a runner starts with was not the one the envelope sealed, or could be edited"
)
AN_INSIDE_RUN_WAS_REFUSED: Final = "a run that stayed inside its envelope was refused or flagged"


@check(
    leaves=("M19.3.1", "M19.3.2", "M19.3.3", "M19.3.4"),
    sentence=(
        "A browser run's policy is the envelope's digest and cannot be re-read; an invented "
        "reference, an origin nobody declared, a verb the envelope does not hold and a second use "
        "of a one-use verb are each refused before the page is touched, end the run on that reason "
        "and are reported as attempts by the replay."
    ),
)
async def a_browser_run_is_held_to_the_envelope_it_was_sealed_with(h: Harness) -> None:
    from brain.browsing.driver import Instruction, RunDeps, run_envelope
    from brain.browsing.enforcer import policy_gaps
    from brain.browsing.envelope import compile_envelope
    from brain.browsing.planning import Goal, PlanRequest, plan
    from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, BROWSE_SURFACE
    from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
    from brain.browsing.wire import Kind, WireError, decode, encode, policy_of, start_fields
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.gate.injection import AutonomyTier
    from brain.ops.halt import NOTHING_HALTED

    target = Target(
        name=f"acceptance_{h.run}_enforced",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.CLICK}),
                capability=ACT_ON_SURFACE_CAPABILITY,
            ),
        ),
    )
    asker = "acceptance_enforced_asker"
    reach = EntitlementSet(
        principal_id=asker,
        grants=(
            Grant(capability=BROWSE_SURFACE, scope=Scope.unrestricted()),
            Grant(capability=ACT_ON_SURFACE_CAPABILITY, scope=Scope.unrestricted()),
        ),
    )
    envelope = compile_envelope(
        plan(
            PlanRequest(
                goal=Goal(text="File the check's return", asked_by=asker),
                target=target.name,
                surfaces=("filing",),
            ),
            TargetRegistry(targets=(target,)),
        ),
        target,
        run_id=f"acceptance_{h.run}_enforced",
        reach=reach,
        ceiling=AutonomyTier.AUTONOMOUS,
    )
    if not envelope.awaits_approval():
        raise CheckFailedError(AN_INSIDE_RUN_WAS_REFUSED)

    # The policy is the envelope's.
    sealed = start_fields(envelope, target, approved=True)
    if sealed["digest"] != envelope.digest():
        raise CheckFailedError(THE_POLICY_IS_NOT_THE_ENVELOPES)
    rebuilt = policy_of(decode(encode(Kind.START, **sealed)))
    if rebuilt.envelope_digest != envelope.digest() or policy_gaps():
        raise CheckFailedError(THE_POLICY_IS_NOT_THE_ENVELOPES)
    try:
        rebuilt.run_id = "another"  # type: ignore[misc]
    except FrozenInstanceError:
        policy_was_frozen = True
    else:
        policy_was_frozen = False
    if not policy_was_frozen:
        raise CheckFailedError(THE_POLICY_IS_NOT_THE_ENVELOPES)
    edited = {**sealed, "budget": [[verb, count + 5] for verb, count in sealed["budget"]]}
    try:
        policy_of(decode(encode(Kind.START, **edited)))
    except WireError:
        edited_start_was_refused = True
    else:
        edited_start_was_refused = False
    if not edited_start_was_refused:
        raise CheckFailedError(THE_POLICY_IS_NOT_THE_ENVELOPES)

    approval = _approval(envelope, h.now)
    open_filing = Instruction(surface="filing", verb=Verb.OPEN)

    async def run(steps: Sequence[Instruction], page: _Page, *, approved: bool = True) -> Any:
        runner = InProcessRunner(page)  # type: ignore[arg-type]

        async def connect() -> _Link:
            return _Link(runner)

        return await run_envelope(
            envelope,
            target,
            approval=approval if approved else None,
            deps=RunDeps(
                connect=connect,
                ledger=_Quiet(),
                actor=_Script(steps),
                clock=lambda: h.now,
                halts=lambda: NOTHING_HALTED,
                backend=_Objects(),
            ),
            trace_id=h.trace_id,
        )

    # Inside the envelope: opened, clicked once, stopped.
    inside_page = _Page()
    inside = await run(
        [open_filing, Instruction(surface="filing", verb=Verb.CLICK, ref=BUTTON)], inside_page
    )
    if not inside.clean or inside.ended != "stopped" or inside_page.acted != [("click", BUTTON)]:
        raise CheckFailedError(AN_INSIDE_RUN_WAS_REFUSED)

    refusals = (
        # An element no snapshot named.
        (
            [open_filing, Instruction(surface="filing", verb=Verb.CLICK, ref="n999")],
            _Page(),
            "unknown_reference",
        ),
        # A page that sent the browser somewhere else.
        (
            [open_filing, Instruction(surface="filing", verb=Verb.CLICK, ref=BUTTON)],
            _Page(lands_on=ELSEWHERE),
            "origin_not_allowed",
        ),
        # A verb the envelope does not hold on a surface it does.
        (
            [open_filing, Instruction(surface="filing", verb=Verb.SUBMIT, ref=BUTTON)],
            _Page(),
            "not_in_envelope",
        ),
        # A second use of a verb approved once.
        (
            [
                open_filing,
                Instruction(surface="filing", verb=Verb.CLICK, ref=BUTTON),
                Instruction(surface="filing", verb=Verb.CLICK, ref=BUTTON),
            ],
            _Page(),
            "budget_spent",
        ),
    )
    for steps, page, reason in refusals:
        result = await run(steps, page)
        expected_acts = [("click", BUTTON)] if reason == "budget_spent" else []
        # A reference is checked against the tree the container reported, which the control plane
        # cannot ask the container to mark for it, so the replay does not repeat that one check
        # (`enforcer.recheck`); every other refusal is an attempt the replay reports.
        replayed = bool(result.findings) is (reason != "unknown_reference")
        if result.ended != f"refused: {reason}" or page.acted != expected_acts or not replayed:
            raise CheckFailedError(A_REFUSAL_ENDS_THE_RUN_AND_IS_REPORTED)


def _approval(envelope: Any, now: datetime) -> Any:
    from brain.browsing.approval import EnvelopeApproval

    return EnvelopeApproval(
        run_id=envelope.run_id,
        envelope_digest=envelope.digest(),
        approved_by="acceptance_enforced_approver",
        approved_at=now,
    )


class _Quiet:
    """A ledger that writes nothing: this check opens no session row."""

    async def opened(self, *, run_id: str, trace_id: str, at: datetime) -> None:
        return None

    async def closed(self, *, run_id: str, at: datetime, recording: Any) -> str | None:
        return None
