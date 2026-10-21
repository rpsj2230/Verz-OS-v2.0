"""Reading a declared page for an agent: the tool handler, and the `ReadOnlyBrowser` behind it.

`sessions.READ_SURFACE` was a `ToolDefinition` with no handler, and `website_check` had a
`ReadOnlyBrowser` seam with nothing behind it; both docstrings said the worker's half was not
built. This is that half, and it owns no decision. A read is admitted by `driver` (the switch,
the halt, the room per site and per agent), compiled and stored by `driver.prepare_run`, run by
`driver.run_envelope` through the launcher and replayed by `enforcer.recheck`. What is added is
the one thing no module had: **turning the page a run saw into the declared fields and nothing
else.**

**Only the declared fields come back, and only what the page shows for them.** A surface declares
the field names a read may return (`Surface.reads`). `fields_read` looks in the snapshot the runner
reported after the read for a node called `<field>: <value>`, or a node called `<field>` followed
by the node that holds its value, and returns those pairs in declaration order, each shortened to
`MAX_VALUE_CHARS`. A field the page does not show is absent, not empty, so "the page has no such
thing" and "the page has an empty one" are not the same answer. The rest of the tree never leaves
this module: a page is somebody else's text, and a tool that returned all of it would hand a model
whatever the page said, instructions included. **That rule for finding a value in an accessibility
tree is a judgement, not a measurement**: no page has been read by it, and the first rehearsal on a
host (`ops/browser/REHEARSAL.md`) is where it meets a real one.

**A read that did not happen says so in one word, and the word names no page.** `ReadRefusedError`
carries a fixed sentence per cause and `website_check` reports any of them as
`BrowserUse.NOT_AVAILABLE`, the one word it already used for no browser, no declared surface and no
grant, so a person cannot tell which of the three it was by asking.

**Only a read-only surface is handed over.** `readable_surface` is the rule `website_check` already
applied, and the tool applies it too: a surface that admits any write verb is refused here, because
this tool declares no side effect and a plan over such a surface would be an envelope waiting for a
person.

**The run is counted against the person who asked.** A tool handler is given the run reach and not
the agent's id, so the per-agent axis of `concurrency` is keyed on the asking principal for these
runs. That is stricter than the agent where one person owns several agents and looser where several
people share one, and the dispatcher passing the agent id is what removes the difference. Stated
rather than hidden: it is the one place this module chose a key because the real one was not there.

**A halt is read when the run starts.** `driver` asks a callable between instructions, and a read is
two instructions long, so the state is read once from the halt store and held for the run. A halt
placed during a read stops the next one.

Not built, and stated: a model actor (a read walks its envelope's read steps and never looks at the
page), and a run on a real daemon, which is the rehearsal.

Task ids: M19.7.1, M19.9.6, M19.9.4
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import structlog
from pydantic import BaseModel, ConfigDict, Field

from brain.browsing.driver import (
    DatabaseLedger,
    ReadOnlyActor,
    RunDeps,
    RunnerLink,
    RunRefusal,
    browser_runs_are_on,
    dial_launcher,
    held_counts,
    prepare_run,
    room_for,
    run_envelope,
)
from brain.browsing.observation import Snapshot
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.sessions import (
    BROWSE_SURFACE,
    BROWSER_SURFACE_OBJECT,
    READ_SURFACE,
    TARGET_FIELD,
    ReadRefusedError,
    SurfaceReading,
)
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.browsing.wire import Kind, WireError, decode, snapshot_of
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.scope import Clause, Op, Scope
from brain.gate.injection import AutonomyTier
from brain.gate.suspension_store import StoredSuspensions
from brain.ops.admission import CapacityState, Resource, seed_budgets
from brain.ops.halt_store import read_state
from brain.tools.registry import RegisteredTool, ResultContract, ToolRegistry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from brain.ops.storage import StorageBackend

log = structlog.get_logger()

#: The longest value kept for one field. A cell is a sentence; a page that puts a document in one
#: has put it where a tool result is not the place for it.
MAX_VALUE_CHARS: Final = 500

#: What a read run is for. Fixed, as `website_check.RENDERED_CHECK_GOAL` is: the goal is the only
#: free text that reaches a planner, and nothing here was typed by a person.
READ_GOAL: Final = "Read the declared fields of one declared page, as a browser shows it"

#: The most a read may wait for the launcher's answer to its start, so a launcher that accepts and
#: never answers does not hold a worker for ever. The driver has no timeout of its own.
READ_SECONDS: Final = 60.0

#: Why a read that was not made is one word.
A_READ_THAT_WAS_NOT_MADE_IS_ONE_ANSWER: Final = (
    "Whether browser runs are switched on, whether a launcher answers, whether there is room and "
    "whether the system is halted are four facts about the install, and which of them stopped a "
    "read is not something the person asking was told they could see. So every cause ends the "
    "read as the one answer the website check already gave for no browser, and the cause goes to "
    "the administrator's log."
)

#: Why a value is never found by anything but the declared field's name.
ONLY_THE_DECLARED_FIELDS_COME_BACK: Final = (
    "A page is somebody else's text. A tool that returned the whole accessibility tree would hand "
    "a model whatever the page said, instructions to it included, and the surface map exists so "
    "that a person decided which few fields a read may return. Everything else the run saw stays "
    "in the recording."
)

#: One fixed sentence per cause. None names a page, a target or a person.
SWITCHED_OFF: Final = "browser runs are switched off on this install"
HALTED: Final = "the system is halted"
NO_ROOM: Final = "there is no room for another browser session"
NO_LAUNCHER: Final = "the browser launcher could not be reached"
DID_NOT_END_CLEAN: Final = "the read did not end clean"
NOT_READ_ONLY: Final = "the surface is not one a read may be made of"
NO_SUCH_SURFACE: Final = "no declared surface was named"

_CAUSES: Final = {
    RunRefusal.SWITCHED_OFF: SWITCHED_OFF,
    RunRefusal.HALTED: HALTED,
    RunRefusal.NO_ROOM: NO_ROOM,
    RunRefusal.LAUNCHER_UNREACHABLE: NO_LAUNCHER,
    RunRefusal.NOT_APPROVED: DID_NOT_END_CLEAN,
}


def readable_surface(target: Target, name: str) -> Surface | None:
    """The named surface of this target, if it reads and admits no write verb."""
    for surface in target.surfaces:
        if surface.name == name and surface.admits(Verb.READ) and not surface.writes():
            return surface
    return None


# ------------------------------------------------------------------ the page into the fields
_BLANKS = re.compile(r"\s+")

#: A node that is itself a `label: value` cell. The colon is followed by a space, so a time such as
#: 10:30 is a value and not a label. Such a node is another field's, never the value of a label
#: that stood alone before it.
_LABELLED = re.compile(r"^[^:]{1,40}:\s+\S")


def _plain(text: str) -> str:
    return _BLANKS.sub(" ", text).strip().casefold().rstrip(":").strip()


def fields_read(snapshot: Snapshot, fields: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """The declared fields the snapshot shows, in declaration order, as `(field, text)`.

    A node named `<field>: <value>` gives the value after the first colon. A node named `<field>`
    alone gives the name of the next node that has one and is not itself a `label: value` cell. The
    first match for a field wins and a field with no match, or only an empty one, is absent. See
    `ONLY_THE_DECLARED_FIELDS_COME_BACK`.
    """
    named = [node.name for node in snapshot.nodes]
    found: list[tuple[str, str]] = []
    for field in fields:
        wanted = _plain(field)
        value = ""
        for position, name in enumerate(named):
            head, colon, rest = name.partition(":")
            if colon and _plain(head) == wanted and rest.strip():
                value = rest.strip()
                break
            if _plain(name) == wanted:
                value = next(
                    (
                        later.strip()
                        for later in named[position + 1 :]
                        if later.strip() and not _LABELLED.match(later.strip())
                    ),
                    "",
                )
                if value:
                    break
        if value:
            found.append((field, value[:MAX_VALUE_CHARS]))
    return tuple(found)


# ------------------------------------------------------------------ the link that keeps snapshots
class SnapshotTap:
    """A `RunnerLink` that passes every line through and remembers the snapshots among them.

    Beside the driver and not inside it: `RunResult` names a run and what happened and never a
    page or a value, and keeping that is worth more than saving a wrapper.
    """

    def __init__(self, inner: RunnerLink, run_id: str) -> None:
        self._inner = inner
        self._run_id = run_id
        self.snapshots: list[Snapshot] = []

    async def put_line(self, line: bytes) -> None:
        await self._inner.put_line(line)

    async def next_line(self) -> bytes:
        line = await self._inner.next_line()
        if line:
            try:
                message = decode(line)
                if message.kind is Kind.SNAPSHOT:
                    self.snapshots.append(snapshot_of(message, run_id=self._run_id))
            except WireError:
                # The driver reads the same line and ends the run on it; nothing is kept here.
                return line
        return line

    async def hang_up(self) -> None:
        await self._inner.hang_up()


# ------------------------------------------------------------------ the browser
@dataclass(frozen=True)
class StoredReadOnlyBrowser:
    """`website_check.ReadOnlyBrowser` over the driver, a database and a launcher."""

    sessions: async_sessionmaker[AsyncSession]
    backend: StorageBackend | None = None
    connect: Callable[[], Awaitable[RunnerLink]] = dial_launcher
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def read(
        self, handed: object, target: Target, *, entitlement: EntitlementSet, now: datetime
    ) -> SurfaceReading:
        """Run the plan's read steps and return the declared fields the page showed."""
        from brain.browsing.planning import Plan

        if not isinstance(handed, Plan):
            raise ReadRefusedError(NO_SUCH_SURFACE)
        names = tuple(dict.fromkeys(step.surface for step in handed.steps))
        surface = readable_surface(target, names[0]) if len(names) == 1 else None
        if surface is None:
            raise ReadRefusedError(NOT_READ_ONLY)
        asker = entitlement.principal_id
        run_id = f"read-{uuid.uuid4().hex[:24]}"
        registry = TargetRegistry(targets=(target,))
        async with self.sessions() as session:
            if not await browser_runs_are_on(session):
                raise ReadRefusedError(SWITCHED_OFF)
            counts = await held_counts(session, registry)
        halts = await read_state(self.sessions)
        budgets = tuple(one for one in seed_budgets() if one.resource is Resource.BROWSER_SESSIONS)
        decision = room_for(
            target,
            agent_id=asker,
            trace_id=run_id,
            budgets=budgets,
            state=CapacityState(),
            counts=counts,
            now=now,
            halts=halts,
        )
        if not decision.admitted:
            raise ReadRefusedError(HALTED if decision.admission.halted else NO_ROOM)
        async with StoredSuspensions(self.sessions).holding(entitlement, now) as rows:
            envelope = await prepare_run(
                rows.session,
                handed,
                target,
                run_id=run_id,
                agent_id=asker,
                reach=entitlement,
                ceiling=AutonomyTier.AUTONOMOUS,
                trace_id=run_id,
                now=now,
            )
        if envelope.awaits_approval():
            raise ReadRefusedError(NOT_READ_ONLY)
        taps: list[SnapshotTap] = []

        async def tapped() -> RunnerLink:
            tap = SnapshotTap(await self.connect(), run_id)
            taps.append(tap)
            return tap

        result = await run_envelope(
            envelope,
            target,
            approval=None,
            deps=RunDeps(
                connect=tapped,
                ledger=DatabaseLedger(
                    self.sessions, asker, ent_hash=entitlement.ent_hash(), trace_id=run_id
                ),
                actor=ReadOnlyActor(envelope),
                clock=self.clock,
                halts=lambda: halts,
                backend=self.backend,
            ),
            trace_id=run_id,
        )
        if not result.started:
            log.info("browser read not made", cause=str(result.refusal))
            raise ReadRefusedError(
                _CAUSES.get(result.refusal or RunRefusal.NOT_APPROVED, DID_NOT_END_CLEAN)
            )
        if not result.clean or not taps or not taps[-1].snapshots:
            log.info("browser read did not end clean", findings=len(result.findings))
            raise ReadRefusedError(DID_NOT_END_CLEAN)
        return SurfaceReading(
            entity=BROWSER_SURFACE_OBJECT,
            id=f"{target.name}.{surface.name}",
            surface=surface.name,
            origin=surface.origin,
            values=fields_read(taps[-1].snapshots[-1], surface.reads),
            browser_target=target.name,
        )


# ------------------------------------------------------------------ the tool
class ReadSurfaceRequest(BaseModel):
    """What a model may say: a declared target and one of its declared surfaces, by name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str = Field(min_length=1, max_length=64)
    surface: str = Field(min_length=1, max_length=64)


#: What registration is given as the tool's scope: a row must name a target at all. The narrowing
#: that matters is the caller's own grant (`surface_scope`) and the handler's check against it; this
#: is the part of it the registry can state without knowing which targets are declared tomorrow.
REGISTERED_SCOPE: Final = Scope(clauses=(Clause(field=TARGET_FIELD, op=Op.PREFIX, value=""),))


@dataclass(frozen=True)
class ReadSurfaceTool:
    """`browser.read_surface`, bound to the declared targets and a read-only browser."""

    declared: Callable[[], Awaitable[TargetRegistry]]
    browser: StoredReadOnlyBrowser

    def handler(self) -> Callable[..., Awaitable[TypedResult[SurfaceReading]]]:
        async def read_surface(
            request: ReadSurfaceRequest,
            *,
            entitlement: EntitlementSet,
            now: datetime | None = None,
        ) -> TypedResult[SurfaceReading]:
            at = now if now is not None else datetime.now(UTC)
            registry = await self.declared()
            target = registry.get(request.target)
            scope = entitlement.scope_for(BROWSE_SURFACE, at)
            if (
                target is None
                or scope is None
                or not scope.matches({TARGET_FIELD: target.name})
                or readable_surface(target, request.surface) is None
            ):
                # One answer for a target nobody declared, one the caller holds no grant for and
                # a surface that is not there or can write.
                return TypedResult(
                    records=(), source=READ_SURFACE.source, fetched_at=at.isoformat()
                )
            handed = plan(
                PlanRequest(
                    goal=Goal(text=READ_GOAL, asked_by=entitlement.principal_id),
                    target=target.name,
                    surfaces=(request.surface,),
                ),
                registry,
            )
            try:
                reading = await self.browser.read(handed, target, entitlement=entitlement, now=at)
            except ReadRefusedError:
                return TypedResult(
                    records=(), source=READ_SURFACE.source, fetched_at=at.isoformat()
                )
            return TypedResult(
                records=(reading,), source=READ_SURFACE.source, fetched_at=at.isoformat()
            )

        return read_surface


def register_read_surface(registry: ToolRegistry, tool: ReadSurfaceTool) -> RegisteredTool:
    """Register the read through the one door every tool uses, with its contract declared."""
    definition = READ_SURFACE.model_copy(
        update={"args_schema": ReadSurfaceRequest.model_json_schema()}
    )
    return registry.register(
        definition, tool.handler(), result_contract=ResultContract.TYPED, scope=REGISTERED_SCOPE
    )
