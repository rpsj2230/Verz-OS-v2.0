"""Install acceptance checks for the browser agent: what holds with no container, and the worker's
half of a run joined to the real runner, the real database and the real approval route.

**What these cannot show, and the sentence says so.** No container has ever been started on this
install by this product, because the sandbox needs a Docker daemon with gVisor and the runner
image has never been built on a host (`ops/browser/REHEARSAL.md`). So nothing here claims a
sandbox, a proxy, a snapshot of a real page or a recording of a real run. What can be shown with
nothing but the product's own code, and is shown on the install rather than in CI, is the part
that has been written and tested as decisions and never joined: the worker's driver
(`brain.browsing.driver`) compiling an envelope and storing it with its approval, holding a write
until a different person approves it through the approvals route, counting the sessions it opens
from the rows that record them, and sending a run to the runner and replaying everything the
runner reports against the envelope this side sealed.

**The first check is structural and touches nothing.** The planner cannot read a page, and the
rubric is written from a goal with no trajectory to see: both are the package's own shape check
run against the installed package. A run's sandbox is built for a declared origin and refused when
anyone adds a volume or a host bind to its bodies, which is what keeps a staff member's browser
profile out of a run.

**The second check joins the halves on the install's own database.** The reserved asker's plan is
compiled to an envelope that waits for a person, stored with its pending approval through
`prepare_run`, and shown not to start. A second reserved person approves it through
`brain.approval_routes.take_decision`, the function the decision route calls, and the stored row
then names them. A session opened for the run is counted against its site and its agent and a
second is refused, and one closed gives the room back. A read-only run goes through
`run_envelope` against the product's own runner in this process, with a page that is a stand-in
the check holds (`A_RUNNER_IN_THE_PROCESS_IS_THE_RUNNER_AND_THE_PAGE_IS_A_STAND_IN`).

Everything the second check writes is in the check's transaction and rolled back with it. The
switch `browser_runs` is not read, because the check calls the driver and not the tool a person's
agent would call; whether the switch is on is the Features screen's to show.

Task ids: M19.2.1, M19.9.3, M19.5.1, M19.5.3, M19.5.4
Task ids: M19.2.2, M19.2.3, M19.3.6, M19.6.2, M19.6.3
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2301

A, _ = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why a check using the product's runner does not claim a real browser.
A_RUNNER_IN_THE_PROCESS_IS_THE_RUNNER_AND_THE_PAGE_IS_A_STAND_IN: Final = (
    "The code that decides each action inside a container is `brain.browsing.runner.drive`, and "
    "it is run here unchanged. The page it drives is a stand-in the check holds, because no "
    "browser exists on this install to be driven, so what the check shows is the worker's half "
    "and the runner's rules agreeing, and not a page in a sandbox."
)

#: The one origin the check's made-up target allows. Nothing resolves it and nothing is sent to it.
STAND_IN_ORIGIN: Final = "https://acceptance-check.invalid"


# ------------------------------------------------------------------ the stand-in page and link
@dataclass
class StandInPage:
    """A browser that records what it was asked and shows one tree. It touches no network."""

    at: str = "null"
    navigated: list[str] = field(default_factory=list)

    def navigate(self, url: str) -> None:
        self.navigated.append(url)
        self.at = STAND_IN_ORIGIN

    def origin(self) -> str:
        return self.at

    def accessibility_tree(self) -> Mapping[str, Any]:
        return {
            "nodes": [
                {
                    "nodeId": "1",
                    "backendDOMNodeId": 7,
                    "role": {"value": "heading"},
                    "name": {"value": "Invoices"},
                }
            ]
        }

    def act(self, verb: Any, ref: str, text: str) -> None:
        # Reading is an instruction like any other to the runner and changes nothing on the page.
        if str(verb) != "read":
            msg = "the stand-in page is read-only and was asked to write"
            raise AssertionError(msg)

    def capture(self) -> bytes:
        return b"a masked picture"


class InProcessRunner:
    """`brain.browsing.runner.drive` on a thread, joined to the driver by two queues."""

    def __init__(self, page: StandInPage) -> None:
        self._in: queue.Queue[bytes] = queue.Queue()
        self._out: queue.Queue[bytes] = queue.Queue()
        self.page = page
        self.closed = False
        threading.Thread(target=self._run, daemon=True).start()

    # The runner's channel.
    def receive(self) -> bytes:
        return self._in.get(timeout=10)

    def emit(self, line: bytes) -> None:
        self._out.put(line)

    def _run(self) -> None:
        from brain.browsing.runner import drive

        drive(self, self.page)
        self._out.put(b"")

    # The driver's link.
    async def put_line(self, line: bytes) -> None:
        self._in.put(line)

    async def next_line(self) -> bytes:
        return await asyncio.to_thread(self._out.get, True, 10)

    async def hang_up(self) -> None:
        self.closed = True
        self._in.put(b"")


class _Link:
    def __init__(self, runner: InProcessRunner) -> None:
        self._runner = runner

    async def put_line(self, line: bytes) -> None:
        await self._runner.put_line(line)

    async def next_line(self) -> bytes:
        return await self._runner.next_line()

    async def hang_up(self) -> None:
        await self._runner.hang_up()


@dataclass
class _Objects:
    """A bucket that keeps what it is given in memory. The recordings bucket is never reached."""

    kept: dict[tuple[str, str], bytes] = field(default_factory=dict)

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self.kept[(bucket_name, key)] = body

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self.kept[(bucket_name, key)]

    def delete_object(self, bucket_name: str, key: str) -> None:
        del self.kept[(bucket_name, key)]

    def list_objects(self, bucket_name: str, prefix: str) -> Any:
        return iter(key for (bucket, key) in self.kept if bucket == bucket_name)


# ------------------------------------------------------------------ 1. what holds with no container
@check(
    leaves=("M19.2.1", "M19.9.3", "M19.5.1", "M19.5.3", "M19.5.4"),
    sentence=(
        "The installed browsing package has no way for page content to reach a plan; a run's "
        "sandbox with a volume or a host bind is refused; a rubric is written from the goal "
        "before any run, and a run that claims success with its criteria unknown is not passed."
    ),
)
async def the_browser_planner_cannot_read_a_page_and_a_run_starts_empty(
    h: Harness,
) -> None:
    from brain.browsing.grading import (
        Claim,
        Outcome,
        Trajectory,
        build_rubric,
        score,
    )
    from brain.browsing.observation import vision_gaps
    from brain.browsing.planning import Goal, PlanRequest, plan
    from brain.browsing.sandbox import sandbox_for, sandbox_gaps
    from brain.browsing.shape import browsing_gaps
    from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
    from brain.core.entitlement import Capability

    gaps = browsing_gaps()
    if gaps:
        raise CheckFailedError("the installed browsing package lets page content reach a plan")
    if vision_gaps():
        raise CheckFailedError("a browser snapshot has a field a picture could arrive through")

    read = Capability(value="read:browser_surface")
    target = Target(
        name=f"acceptance_{h.run}_declared",
        origins=frozenset({STAND_IN_ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=STAND_IN_ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=read,
                reads=("number",),
            ),
        ),
    )
    request = PlanRequest(
        goal=Goal(text="Read the check's invoices", asked_by=h.principal(A, "asker")),
        target=target.name,
        surfaces=("invoices",),
    )
    planned = plan(request, TargetRegistry(targets=(target,)))
    if {(one.surface, one.verb) for one in planned.steps} != {
        ("invoices", Verb.OPEN),
        ("invoices", Verb.READ),
    }:
        raise CheckFailedError("a plan for a declared surface was not its declared steps")

    # A sandbox for one run, then each way a body could hold something the run could keep or
    # leave through, planted into a copy of it. The check asserts the refusal for each.
    box = sandbox_for(f"acc{h.run}", origins=frozenset({STAND_IN_ORIGIN}), app_image="app:check")
    if sandbox_gaps(box):
        raise CheckFailedError("a run's sandbox was built with a way out of it")
    for planted in _planted(box):
        if not sandbox_gaps(planted):
            raise CheckFailedError(
                "a run's sandbox given a volume, a host bind or a writable root was not refused"
            )

    rubric = build_rubric(request, target, now=h.now)
    if not rubric.required():
        raise CheckFailedError("a rubric written from a goal had no required criteria")
    unknown = score(rubric, Trajectory(run_id="check"), {})
    claimed = Claim(run_id="check", succeeded=True, text="all done")
    if unknown.passed or not unknown.disagrees_with(claimed):
        raise CheckFailedError("a run whose criteria were unknown was passed on its own account")
    named = {one.name for one in rubric.criteria}
    met = score(rubric, Trajectory(run_id="check"), dict.fromkeys(named, Outcome.MET))
    if not met.passed:
        raise CheckFailedError("a run whose every criterion was met was not passed")


def _planted(box: Any) -> tuple[Any, ...]:
    """Copies of a sandbox with a volume, a host bind and a writable root planted in the runner."""
    from dataclasses import replace

    def runner_with(*, body: dict[str, Any] | None = None, **host: Any) -> Any:
        runner = box.runner
        planted = dict(runner.body if body is None else body)
        planted["HostConfig"] = {**runner.body["HostConfig"], **host}
        return replace(box, runner=replace(runner, body=planted))

    with_volume = {**box.runner.body, "Volumes": {"/profile": {}}}
    return (
        runner_with(body=with_volume),
        runner_with(Binds=["/home/staff/.config/browser:/profile"]),
        runner_with(ReadonlyRootfs=False),
    )


# ------------------------------------------------------------------ 2. the worker's half, joined
@check(
    leaves=("M19.2.2", "M19.2.3", "M19.3.6", "M19.6.2", "M19.6.3"),
    sentence=(
        "A write in a browser plan waits for a different person to approve it through the "
        "approvals route; open sessions are counted per site and agent and a full one is refused; "
        "a read-only run goes through the product's runner with a stand-in page and replays clean."
    ),
)
async def a_browser_write_waits_for_a_person_and_runs_are_counted(
    h: Harness,
) -> None:
    from brain.approval_routes import DecidableVerdict, DecisionAsked, take_decision
    from brain.browsing.concurrency import Axis, SessionCounts
    from brain.browsing.driver import (
        DatabaseLedger,
        ReadOnlyActor,
        RunDeps,
        RunRefusal,
        approval_of_run,
        held_counts,
        prepare_run,
        room_for,
        run_envelope,
    )
    from brain.browsing.planning import Goal, PlanRequest, plan
    from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, BROWSE_SURFACE, surface_scope
    from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
    from brain.gate.injection import AutonomyTier
    from brain.gate.suspension_store import StoredSuspensions
    from brain.ops.admission import CapacityState, Resource, seed_budgets
    from brain.ops.halt import NOTHING_HALTED

    await h.found_departments()
    asker, approver = h.principal(A, "browser_asker"), h.principal(A, "browser_approver")
    target = Target(
        name=f"acceptance_{h.run}_books",
        origins=frozenset({STAND_IN_ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=STAND_IN_ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=BROWSE_SURFACE,
                reads=("number",),
            ),
            Surface(
                name="filing",
                origin=STAND_IN_ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.SUBMIT}),
                capability=ACT_ON_SURFACE_CAPABILITY,
            ),
        ),
    )
    reach_of_target = surface_scope(target)
    await h.person(
        asker,
        department=A,
        grants=(
            (BROWSE_SURFACE.value, reach_of_target),
            (ACT_ON_SURFACE_CAPABILITY.value, reach_of_target),
        ),
    )
    await h.person(
        approver, department=A, grants=((ACT_ON_SURFACE_CAPABILITY.value, reach_of_target),)
    )
    asking, approving = await h.reach(asker), await h.reach(approver)
    registry = TargetRegistry(targets=(target,))
    agent = f"acceptance_{h.run}_agent"
    store = StoredSuspensions(h.sessions)

    def planned(*surfaces: str) -> Any:
        return plan(
            PlanRequest(
                goal=Goal(text="File the check's return", asked_by=asker),
                target=target.name,
                surfaces=surfaces,
            ),
            registry,
        )

    # A write waits, and is stored with the card a person will be shown.
    write_run = f"acceptance_{h.run}_write"
    async with store.holding(asking, h.now) as rows:
        envelope = await prepare_run(
            rows.session,
            planned("invoices", "filing"),
            target,
            run_id=write_run,
            agent_id=agent,
            reach=asking,
            ceiling=AutonomyTier.AUTONOMOUS,
            trace_id=h.trace_id,
            now=h.now,
        )
    if not envelope.awaits_approval():
        raise CheckFailedError("an envelope with a write in it did not wait for a person")
    async with h.sessions() as session:
        before = await approval_of_run(session, envelope)
    if before is not None:
        raise CheckFailedError("an envelope nobody had decided was read back as approved")
    quiet = RunDeps(
        connect=_never,
        ledger=DatabaseLedger(h.sessions, asker),
        actor=ReadOnlyActor(envelope),
        clock=lambda: h.now,
        halts=lambda: NOTHING_HALTED,
    )
    held = await run_envelope(envelope, target, approval=None, deps=quiet, trace_id=h.trace_id)
    if held.started or held.refusal is not RunRefusal.NOT_APPROVED:
        raise CheckFailedError("a run with a write nobody had approved was started")

    # A different person approves it through the route's own function, and the row names them.
    await take_decision(
        store,
        write_run,
        approving,
        DecisionAsked(verdict=DecidableVerdict.APPROVED),
        trace_id=h.trace_id,
        now=h.now,
    )
    async with h.sessions() as session:
        after = await approval_of_run(session, envelope)
    if after is None or after.approved_by != approver or after.run_id != write_run:
        raise CheckFailedError("an approved envelope was not read back as approved by its approver")
    if after.envelope_digest != envelope.digest():
        raise CheckFailedError("an approval was read back for an envelope that says something else")

    # A session is counted from the rows that record it, against its site and its agent.
    ledger = DatabaseLedger(h.sessions, asker)
    budgets = tuple(one for one in seed_budgets() if one.resource is Resource.BROWSER_SESSIONS)

    async def room() -> Any:
        async with h.sessions() as session:
            counts = await held_counts(session, registry)
        return counts, room_for(
            target,
            agent_id=agent,
            trace_id=h.trace_id,
            budgets=budgets,
            state=CapacityState(),
            counts=counts,
            now=h.now,
            halts=NOTHING_HALTED,
        )

    empty, free = await room()
    if empty != SessionCounts() or not free.admitted:
        raise CheckFailedError("a made-up target already had a browser session open on it")
    await ledger.opened(run_id=write_run, trace_id=h.trace_id, at=h.now)
    counts, full = await room()
    if (
        counts.held_for((Axis.AGENT, agent)) != 1
        or counts.held_for((Axis.DOMAIN, STAND_IN_ORIGIN)) != 1
    ):
        raise CheckFailedError("an open session was not counted against its site and its agent")
    if full.admitted or {axis for axis, _ in full.over} != {Axis.AGENT, Axis.DOMAIN}:
        raise CheckFailedError(
            "a second session was admitted on a site and an agent that were full"
        )
    await ledger.closed(run_id=write_run, at=h.now + timedelta(seconds=1), recording=None)
    _, free_again = await room()
    if not free_again.admitted:
        raise CheckFailedError("a closed session did not give its room back")

    # A read-only run, through the product's own runner with a stand-in page.
    read_run = f"acceptance_{h.run}_read"
    async with store.holding(asking, h.now) as rows:
        reading = await prepare_run(
            rows.session,
            planned("invoices"),
            target,
            run_id=read_run,
            agent_id=agent,
            reach=asking,
            ceiling=AutonomyTier.AUTONOMOUS,
            trace_id=h.trace_id,
            now=h.now,
        )
    if reading.awaits_approval():
        raise CheckFailedError("a read-only envelope waited for an approval")
    runner = InProcessRunner(StandInPage())

    async def connect() -> _Link:
        return _Link(runner)

    result = await run_envelope(
        reading,
        target,
        approval=None,
        deps=RunDeps(
            connect=connect,
            ledger=ledger,
            actor=ReadOnlyActor(reading),
            clock=lambda: h.now,
            halts=lambda: NOTHING_HALTED,
            backend=_Objects(),
        ),
        trace_id=h.trace_id,
    )
    if not result.clean or result.ended != "stopped" or result.actions != 2:
        raise CheckFailedError("a read-only run did not go through the runner and replay clean")
    if result.gaps or not result.keys or result.digest is None:
        raise CheckFailedError("a read-only run was not recorded whole")
    if runner.page.navigated != [f"{STAND_IN_ORIGIN}/invoices"]:
        raise CheckFailedError("a read-only run opened a page its envelope did not name")
    final, _ = await room()
    if final != SessionCounts():
        raise CheckFailedError("a run that ended left a session counted as open")


async def _never() -> Any:
    msg = "a run that was not approved opened a link to the launcher"
    raise AssertionError(msg)
