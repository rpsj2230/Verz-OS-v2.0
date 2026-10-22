"""The worker's half of a browser run: admit it, send it to the launcher, relay it, keep it.

`launcher`, `runner`, `enforcer`, `envelope`, `approval`, `credentials`, `recording` and `grading`
each decide one thing and each said, in its own docstring, that the piece which joins them for a
real run was not built. This is that piece. It owns no decision. Every rule it applies is one of
those modules' and it calls them in the order a run needs, so a second statement of any of them is
the thing to refuse in review.

**The order is the design.** A run is admitted (the feature switch, the halt, the global and
per-site and per-agent room), compiled to a sealed envelope and stored with its approval, and a
write that waits for a person is not started until that person's approval is read back from the
store at the envelope's own digest. Only then is a rubric written, a session recorded as open,
and the start line sent. During the run every instruction is sent one at a time with the halt
asked between them. After it, `enforcer.recheck` replays everything the container reported
against the envelope this side sealed, the transcript is scrubbed of every value that was
substituted and written to the recordings bucket, and the session is closed naming its digest.

**The container is not believed, and neither is this process's idea of what a person said.** The
runner enforces and this side re-enforces (`recheck`), reading none of its verdicts. The approval
is read from the stored envelope row at its digest and never passed in from a caller's memory of
having asked.

**The credential never reaches the model, and not this module either, beyond one line.** An
instruction names a placeholder. `credentials.resolve` turns it into a value inside the vault's
lease, at the origin the browser reported for the snapshot just seen, and the value is put in the
one `act` line and in a list used only to scrub the recording. It is not stored on any value this
module returns, and a hit of it in a line the runner sent back is an incident on the result and
not a scrub that worked.

**The instruction source is a port, because the actor is the one thing that reads the page.**
`Actor.next` is given the last snapshot and answers with one declared instruction. The shipped
actor, `ReadOnlyActor`, walks an envelope's read steps and never reads the snapshot, so a read run
needs no model. A model actor is a second implementation of the same port and is not here. The
planner stays what `brain.browsing.shape` holds it to: nothing in this module returns a plan.

**It ships off.** `BROWSER_RUNS` is a feature and every reader of it is `browser_runs_are_on`; a
caller asks that first and a run is refused on its answer. Nothing starts a container with the
switch off, and a run that was admitted when it was on is not stopped by turning it off, because
the stop for a run in flight is the halt.

Rejected: a driver inside the launcher. The launcher holds the Docker socket and by design nothing
else, so adding a database session or a vault reference to it puts both one parser away from
model output. Rejected: resolving the credential in the runner. The container is the party who
would exfiltrate it.

Not built, and stated: the judge that gives an outcome per rubric criterion, so `RunResult.rubric`
is held and no verdict is produced (`brain.browsing.grading.verification_gaps`); a model actor; the
read-back port over a connector. A run on a real daemon is `ops/browser/REHEARSAL.md`.

Task ids: M19.1.1, M19.2.2, M19.2.3, M19.3.6, M19.4.1, M19.4.4, M19.5.1
Task ids: M19.6.2, M19.6.3, M19.6.5, M19.6.6, M19.7.2
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Final, Protocol

from sqlalchemy import select

from brain.browsing.approval import EnvelopeApproval, Previous, raise_approval
from brain.browsing.concurrency import (
    Axis,
    SessionCounts,
    SessionDecision,
    SessionKey,
    SessionLimit,
    keys_for,
    may_open,
    seed_session_limits,
)
from brain.browsing.credentials import Bindings, CredentialError, resolve, scrub_history
from brain.browsing.enforcer import Action, ActionRecord, recheck, stopped_now
from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.envelope_store import last_approved_parts, load_envelope, put_envelope
from brain.browsing.grading import Rubric, Trajectory, build_rubric
from brain.browsing.observation import Frame, ObservationError, Snapshot
from brain.browsing.recording import (
    Direction,
    Recording,
    as_written,
    record,
    recording_gaps,
    secrets_seen,
    write,
)
from brain.browsing.recording import transcript_digest as _digest_of
from brain.browsing.session_store import end as end_session
from brain.browsing.session_store import start as start_session
from brain.browsing.targets import READ_VERBS, Target, TargetRegistry, Verb
from brain.browsing.wire import (
    MAX_LINE_BYTES,
    Kind,
    WireError,
    decode,
    encode,
    snapshot_of,
    start_fields,
)
from brain.ops.features import BROWSER_RUNS, is_on
from brain.ops.halt import HaltState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from brain.browsing.autonomy import SurfaceException
    from brain.browsing.planning import Plan
    from brain.core.entitlement import EntitlementSet
    from brain.gate.injection import AutonomyTier
    from brain.ops.admission import Budget, CapacityState
    from brain.ops.secrets import Vault
    from brain.ops.storage import StorageBackend

#: Where the launcher listens, as a service on the product's own control network. Both are the
#: product's constants (`docker-compose.browser.yml` and `brain.browsing.launcher.LISTEN_PORT`),
#: not values that differ between installs.
LAUNCHER_HOST: Final = "browser-launcher"
LAUNCHER_PORT: Final = 7300

#: Why a run that was admitted is not stopped by the switch.
A_SWITCH_GATES_THE_DOOR_AND_THE_HALT_STOPS_THE_RUN: Final = (
    "The browser switch decides whether a new run may start. A run in flight is stopped by the "
    "halt, which the driver asks between every instruction, so turning the switch off cannot "
    "leave a container running that nothing is watching."
)

#: Why a write that waits for a person is not started without their approval read from the store.
A_WRITE_THAT_WAITS_STARTS_ONLY_ON_THE_STORED_APPROVAL: Final = (
    "Whether a person approved is read from the stored envelope row at the envelope's own "
    "digest. A caller's memory of having asked is not an approval, and an approval of another "
    "envelope is a different digest."
)


class RunRefusal(enum.StrEnum):
    """Why a run did not start. One reason each, and none names a page."""

    SWITCHED_OFF = "switched_off"
    HALTED = "halted"
    NO_ROOM = "no_room"
    NOT_APPROVED = "not_approved"
    LAUNCHER_UNREACHABLE = "launcher_unreachable"


class DriverError(Exception):
    """A run was asked for in terms the driver could not carry out."""


@dataclass(frozen=True)
class Instruction:
    """One declared thing to do next. A placeholder is a name, and its value is never here."""

    surface: str
    verb: Verb
    ref: str = ""
    text: str = ""
    placeholder: str = ""


class Actor(Protocol):
    """Where the next instruction comes from. The only part of a run that may read the page."""

    def next(self, index: int, last: Snapshot | None) -> Instruction | None:
        """The instruction numbered `index`, or None when the run has nothing more to do."""
        ...


@dataclass
class ReadOnlyActor:
    """Walks the read steps of an envelope in order and never looks at the snapshot.

    A plan's write steps are not sent: a write needs an element reference, which only a reader
    of the page can supply, and that is a model actor's work.
    """

    envelope: Envelope
    _steps: list[Instruction] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._steps = [
            Instruction(surface=step.surface, verb=step.verb)
            for step in self.envelope.plan.steps
            if step.verb in READ_VERBS
        ]

    def next(self, index: int, last: Snapshot | None) -> Instruction | None:
        return self._steps[index - 1] if index <= len(self._steps) else None


class RunnerLink(Protocol):
    """One connection to a launcher: one line at a time, in both directions."""

    async def put_line(self, line: bytes) -> None: ...

    async def next_line(self) -> bytes:
        """The next line, or empty bytes when the other side has closed."""
        ...

    async def hang_up(self) -> None: ...


class Ledger(Protocol):
    """Where a session's open and close are recorded. The database one is `DatabaseLedger`."""

    async def opened(self, *, run_id: str, trace_id: str, at: datetime) -> None: ...

    async def closed(
        self, *, run_id: str, at: datetime, recording: Recording | None
    ) -> str | None: ...


@dataclass(frozen=True)
class DatabaseLedger:
    """`Ledger` over `session_store`, one transaction per call so a crash leaves what was done.

    `asked_by` is the person the run belongs to: `agent.browser_session`'s row-level policies
    admit a session in its asker's name only, so each transaction says whose it is before it
    writes. It is the envelope's asker and is never read from a caller of the run.
    """

    sessions: async_sessionmaker[AsyncSession]
    asked_by: str
    #: The asker's reach digest and the run's trace, which the trigger on `agent.browser_session`
    #: reads for the ledger entry it appends. Empty, nothing is attributed and the entry carries the
    #: unsupplied placeholders, which is what a caller with no reach (a test) gets and a run for a
    #: person must not.
    ent_hash: str = ""
    trace_id: str = ""

    async def _as_asker(self, session: AsyncSession) -> None:
        from sqlalchemy import text

        from brain.gate.suspension_store import PRINCIPAL_SETTING
        from brain.tables.audit import attributed_to

        await session.execute(
            text("SELECT set_config(:name, :value, true)").bindparams(
                name=PRINCIPAL_SETTING, value=self.asked_by
            )
        )
        if self.ent_hash:
            for statement in attributed_to(
                actor_id=self.asked_by, ent_hash=self.ent_hash, trace_id=self.trace_id
            ):
                await session.execute(statement)

    async def opened(self, *, run_id: str, trace_id: str, at: datetime) -> None:
        async with self.sessions() as session, session.begin():
            await self._as_asker(session)
            await start_session(session, run_id=run_id, trace_id=trace_id, at=at)

    async def closed(self, *, run_id: str, at: datetime, recording: Recording | None) -> str | None:
        async with self.sessions() as session, session.begin():
            await self._as_asker(session)
            return await end_session(session, run_id=run_id, at=at, recording=recording)


@dataclass(frozen=True)
class Substitution:
    """What a run needs to turn a placeholder into a value: the bindings and the vault."""

    bindings: Bindings
    vault: Vault


@dataclass(frozen=True)
class RunDeps:
    """Everything a run touches outside this module, handed in so each can be a fake."""

    connect: Callable[[], Awaitable[RunnerLink]]
    ledger: Ledger
    actor: Actor
    clock: Callable[[], datetime]
    halts: Callable[[], HaltState]
    backend: StorageBackend | None = None
    substitution: Substitution | None = None


@dataclass(frozen=True)
class RunResult:
    """What a run came to. Names the run and what happened, and never a page or a value."""

    run_id: str
    started: bool
    refusal: RunRefusal | None = None
    reason: str = ""
    ended: str = ""
    #: What `enforcer.recheck` found in everything the container reported. Empty is clean.
    findings: tuple[str, ...] = ()
    #: Lines of the history in which a substituted value was found. A hit is an incident.
    leaked: tuple[int, ...] = ()
    gaps: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()
    digest: str | None = None
    rubric: Rubric | None = None
    actions: int = 0
    #: What the container reported it did, in order, with the placeholder this side sent for each.
    #: Values-free: an action names a surface, a verb, an origin and a reference, never text typed.
    records: tuple[ActionRecord, ...] = ()
    #: One entry per picture the run took, named by digest and never carrying it.
    frames: tuple[Frame, ...] = ()
    #: The snapshots in which a bound credential value was found in the text the runner sent.
    echoed_sequences: frozenset[int] = frozenset()

    def trajectory(self) -> Trajectory:
        """What the run did as the grader and the judge's frame admission read it."""
        return Trajectory(run_id=self.run_id, records=self.records)

    @property
    def clean(self) -> bool:
        """Started, ended on a line, replayed with nothing found, nothing leaked."""
        return self.started and not self.findings and not self.leaked and bool(self.ended)


# ------------------------------------------------------------------ the switch and the counts
async def browser_runs_are_on(session: AsyncSession) -> bool:
    """Whether this install has switched browser runs on. Off until an administrator does."""
    return await is_on(session, BROWSER_RUNS)


async def held_counts(session: AsyncSession, registry: TargetRegistry) -> SessionCounts:
    """Sessions open now, per site and per agent, counted from the rows that record them.

    A session is open from the row `session_store.start` wrote until the one `end` closed, so
    this is the counter `concurrency` said nobody had built. A stored target the registry no
    longer declares counts against its agent and nothing else.
    """
    from brain.tables.browsing import BrowserEnvelopeRow, BrowserSessionRow

    rows = await session.execute(
        select(BrowserEnvelopeRow.target, BrowserEnvelopeRow.agent_id)
        .join(BrowserSessionRow, BrowserSessionRow.run_id == BrowserEnvelopeRow.run_id)
        .where(BrowserSessionRow.ended_at.is_(None))
    )
    held: dict[SessionKey, int] = {}
    for target_name, agent_id in rows.all():
        target = registry.get(target_name)
        keys: tuple[SessionKey, ...] = (
            ((Axis.AGENT, agent_id),) if target is None else keys_for(target, agent_id)
        )
        for key in keys:
            held[key] = held.get(key, 0) + 1
    return SessionCounts(held=held)


async def approval_of_run(session: AsyncSession, envelope: Envelope) -> EnvelopeApproval | None:
    """The approval the stored row holds for this envelope, or None. See
    `A_WRITE_THAT_WAITS_STARTS_ONLY_ON_THE_STORED_APPROVAL`."""
    stored = await load_envelope(session, envelope.run_id)
    return None if stored is None else stored.approval_for(envelope)


async def prepare_run(
    session: AsyncSession,
    plan: Plan,
    target: Target,
    *,
    run_id: str,
    agent_id: str,
    reach: EntitlementSet,
    ceiling: AutonomyTier,
    trace_id: str,
    now: datetime,
    exceptions: Sequence[SurfaceException] | None = None,
) -> Envelope:
    """Compile a plan to an envelope, raise its approval if a write waits, and store both.

    Does not commit. `reach` is the run reach the gate already computed for the asker, and it
    is handed to `compile_envelope` and `raise_approval` as it is: this is not a second place
    that intersects anything. The suspension and the envelope row are written in the one
    transaction, so a waiting envelope with no card, which `envelope_store.row_values` refuses,
    cannot be left behind by a failure between them.
    """
    from brain.browsing.declared import live_exceptions
    from brain.gate.suspension_store import at_reach, put_suspension

    # The exceptions in force at this instant, read here and nowhere later: one that lapsed or was
    # revoked is not in the envelope this run is compiled to, and one signed afterwards is not in
    # it either (`brain.browsing.autonomy`). A caller that hands a list in is deciding for itself.
    if exceptions is None:
        exceptions = await live_exceptions(session, now, target=target.name)
    envelope = compile_envelope(
        plan,
        target,
        run_id=run_id,
        reach=reach,
        ceiling=ceiling,
        exceptions=exceptions,
        now=now if exceptions else None,
    )
    await at_reach(session, reach, now)
    suspension = None
    if envelope.awaits_approval():
        # What the card says changed is the asker's own last approved run, by the query.
        previous = Previous(
            await last_approved_parts(
                session, asked_by=reach.principal_id, agent_id=agent_id, target=target.name
            )
        )
        suspension = raise_approval(
            envelope,
            target,
            agent_id=agent_id,
            reach=reach,
            trace_id=trace_id,
            now=now,
            previous=previous,
        )
    if suspension is not None:
        await put_suspension(session, suspension)
    await put_envelope(session, envelope, agent_id=agent_id, suspension=suspension)
    return envelope


def room_for(
    target: Target,
    *,
    agent_id: str,
    trace_id: str,
    budgets: Sequence[Budget],
    state: CapacityState,
    counts: SessionCounts,
    now: datetime,
    halts: HaltState,
    limits: Sequence[SessionLimit] | None = None,
) -> SessionDecision:
    """Whether one more session may open, asked of `concurrency.may_open` with the seeded limits."""
    return may_open(
        target,
        agent_id=agent_id,
        trace_id=trace_id,
        budgets=budgets,
        state=state,
        limits=seed_session_limits() if limits is None else limits,
        counts=counts,
        now=now,
        halts=halts,
    )


# ------------------------------------------------------------------ the link to a launcher
@dataclass
class StreamLink:
    """`RunnerLink` over an asyncio stream pair, which is what a launcher connection is."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter

    async def put_line(self, line: bytes) -> None:
        self.writer.write(line)
        await self.writer.drain()

    async def next_line(self) -> bytes:
        try:
            return await self.reader.readuntil(b"\n")
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            return b""

    async def hang_up(self) -> None:
        self.writer.close()


async def dial_launcher(host: str = LAUNCHER_HOST, port: int = LAUNCHER_PORT) -> RunnerLink:
    """Open one connection to the launcher. One run per connection, as the launcher serves it."""
    reader, writer = await asyncio.open_connection(host, port, limit=MAX_LINE_BYTES + 1)
    return StreamLink(reader=reader, writer=writer)


# ------------------------------------------------------------------ the run
def refused(run_id: str, why: RunRefusal, reason: str) -> RunResult:
    """A run that was not started, and the one reason."""
    return RunResult(run_id=run_id, started=False, refusal=why, reason=reason)


async def run_envelope(
    envelope: Envelope,
    target: Target,
    *,
    approval: EnvelopeApproval | None,
    deps: RunDeps,
    trace_id: str,
    now: datetime | None = None,
) -> RunResult:
    """Run one sealed, admitted envelope to its end and keep what it did.

    The caller has asked `browser_runs_are_on` and `room_for` and passes the approval read by
    `approval_of_run`. What is rechecked here is what only this moment knows: the halt, and
    that an envelope waiting for a person carries that person's approval.
    """
    run_id = envelope.run_id
    started_at = now or deps.clock()
    if stopped_now(deps.halts()):
        return refused(run_id, RunRefusal.HALTED, "the system is halted, so no browser was started")
    if envelope.awaits_approval() and approval is None:
        return refused(
            run_id, RunRefusal.NOT_APPROVED, "a write in this run waits for a person's approval"
        )
    # Written before anything has run and with no way for the run to reach it.
    rubric = build_rubric(envelope.plan.request, target, now=started_at)
    try:
        link = await _open(deps)
    except (OSError, TimeoutError):
        return refused(
            run_id, RunRefusal.LAUNCHER_UNREACHABLE, "the browser launcher could not be reached"
        )
    await deps.ledger.opened(run_id=run_id, trace_id=trace_id, at=started_at)
    exchanged: list[tuple[Direction, bytes]] = []
    records: list[ActionRecord] = []
    values: list[str] = []
    ended = ""
    try:
        start = encode(Kind.START, **start_fields(envelope, target, approved=approval is not None))
        await link.put_line(start)
        exchanged.append((Direction.TO_RUNNER, start))
        ended = await _relay(link, envelope, deps, exchanged, records, values)
    except OSError:
        ended = "the channel to the launcher failed"
    finally:
        await link.hang_up()
    return await _finish(
        envelope, approval, deps, rubric, started_at, exchanged, records, values, ended
    )


async def _open(deps: RunDeps) -> RunnerLink:
    return await deps.connect()


async def _relay(
    link: RunnerLink,
    envelope: Envelope,
    deps: RunDeps,
    exchanged: list[tuple[Direction, bytes]],
    records: list[ActionRecord],
    values: list[str],
) -> str:
    """Send instructions one at a time and read until the run says it has ended."""
    run_id = envelope.run_id
    last: Snapshot | None = None
    index = 0
    stopping = ""
    # The placeholder this side sent with each instruction, which is what the replay trusts and not
    # whatever the container says it was sent.
    placeholders: dict[int, str] = {}
    while True:
        index += 1
        if stopped_now(deps.halts()):
            stopping = "stopped by the halt"
        instruction = None if stopping else deps.actor.next(index, last)
        if instruction is None:
            stop = encode(Kind.STOP)
            await link.put_line(stop)
            exchanged.append((Direction.TO_RUNNER, stop))
            return await _until_ended(link, exchanged) or stopping or "stopped"
        try:
            text = _value_for(instruction, last, deps, values)
        except CredentialError:
            stop = encode(Kind.STOP)
            await link.put_line(stop)
            exchanged.append((Direction.TO_RUNNER, stop))
            await _until_ended(link, exchanged)
            return "a credential was refused for this action"
        placeholders[index] = instruction.placeholder
        act = encode(
            Kind.ACT,
            index=index,
            surface=instruction.surface,
            verb=instruction.verb.value,
            ref=instruction.ref,
            sequence=last.sequence if last is not None else 0,
            placeholder=instruction.placeholder,
            text=text,
        )
        await link.put_line(act)
        exchanged.append((Direction.TO_RUNNER, act))
        while True:
            line = await link.next_line()
            if not line:
                return "the channel closed before the run ended"
            exchanged.append((Direction.FROM_RUNNER, line))
            try:
                message = decode(line)
            except WireError:
                return "a line from the run could not be read"
            try:
                if message.kind is Kind.SNAPSHOT:
                    last = snapshot_of(message, run_id=run_id)
                elif message.kind is Kind.RECORD:
                    records.append(_record_of(message.fields, run_id, placeholders.get(index, "")))
                    if message.fields["refusal"] is not None:
                        # The first refusal ends a run inside the container, so what is read
                        # next is its last line and not an answer to another instruction.
                        return await _until_ended(link, exchanged) or "refused"
                    break
            except WireError:
                return "a line from the run could not be read"
            if message.kind is Kind.ENDED:
                return str(message.fields["reason"])


async def _until_ended(link: RunnerLink, exchanged: list[tuple[Direction, bytes]]) -> str:
    """Read to the run's last line, keeping every line, and return its reason."""
    while line := await link.next_line():
        exchanged.append((Direction.FROM_RUNNER, line))
        try:
            message = decode(line)
        except WireError:
            return "a line from the run could not be read"
        if message.kind is Kind.ENDED:
            return str(message.fields["reason"])
    return ""


def _value_for(
    instruction: Instruction, last: Snapshot | None, deps: RunDeps, values: list[str]
) -> str:
    """The text an instruction types: its own, or the value a placeholder resolves to here."""
    if not instruction.placeholder:
        return instruction.text
    if deps.substitution is None or last is None:
        msg = "an instruction names a credential and nothing here could substitute it"
        raise CredentialError(msg)
    value = resolve(
        instruction.placeholder,
        deps.substitution.bindings,
        vault=deps.substitution.vault,
        origin=last.origin,
        now=deps.clock(),
    )
    values.append(value)
    return value


def _record_of(fields: Mapping[str, object], run_id: str, placeholder: str = "") -> ActionRecord:
    """One reported action, with the container's own verdict carried and never read.

    `placeholder` is the one this side sent for the instruction, because the record line carries no
    such field and a container's word about whether it was typing a credential is the one thing the
    judge's frame admission must not rest on.
    """
    try:
        action = Action(
            run_id=run_id,
            surface=str(fields["surface"]),
            verb=Verb(str(fields["verb"])),
            origin=str(fields["origin"]),
            ref=str(fields["ref"]),
            sequence=int(str(fields["sequence"])),
            placeholder=placeholder,
        )
    except ValueError as exc:
        msg = "a record line named a verb or a position the protocol does not have"
        raise WireError(msg) from exc
    return ActionRecord(action=action, claimed_allowed=fields["refusal"] is None)


def frames_of(exchanged: list[tuple[Direction, bytes]], run_id: str) -> tuple[Frame, ...]:
    """The pictures a run took, from the lines the runner sent: named by digest, never carried.

    A frame whose line cannot be read, or whose digest is not one a stored picture could have, is
    left out here and is reported by the recording (`Recording.mismatched`), so a judge is never
    offered a picture nothing can find.
    """
    found: list[Frame] = []
    for _, line in exchanged:
        # Only the runner sends a frame; `decode` and the kind are the whole of that rule.
        try:
            message = decode(line)
            if message.kind is not Kind.FRAME:
                continue
            found.append(
                Frame(
                    run_id=run_id,
                    sequence=int(str(message.fields["sequence"])),
                    origin=str(message.fields["origin"]),
                    digest=str(message.fields["digest"]),
                    inputs_masked=message.fields["inputs_masked"] is True,
                )
            )
        except (WireError, ObservationError, ValueError):
            continue
    return tuple(found)


async def _finish(
    envelope: Envelope,
    approval: EnvelopeApproval | None,
    deps: RunDeps,
    rubric: Rubric,
    started_at: datetime,
    exchanged: list[tuple[Direction, bytes]],
    records: list[ActionRecord],
    values: list[str],
    ended: str,
) -> RunResult:
    """Replay, scrub, keep and close. Runs for every run that opened a session."""
    run_id = envelope.run_id
    findings = recheck(envelope, records, approval)
    recording = record(run_id, started_at, exchanged, values, keep_pictures=frozenset())
    from_runner = [
        (position, line.decode("utf-8", errors="replace"))
        for position, (direction, line) in enumerate(exchanged)
        if direction is Direction.FROM_RUNNER
    ]
    # The line this side sent holds the value by design, so only what came back is searched.
    # Searched for as a line holds a value as well as plain, as the recording does: a password with
    # a quote or a backslash in it is escaped in the line and a search for the plain form misses it.
    _, hits = scrub_history([text for _, text in from_runner], list(as_written(values)))
    leaked = tuple(sorted(set(recording.leaked) | {from_runner[one][0] for one in hits}))
    gaps = recording_gaps(recording)
    keys = write(deps.backend, recording) if deps.backend is not None else ()
    digest = await deps.ledger.closed(run_id=run_id, at=deps.clock(), recording=recording)
    return RunResult(
        run_id=run_id,
        started=True,
        ended=ended or "the run sent no last line",
        findings=findings,
        leaked=leaked,
        gaps=gaps,
        keys=keys,
        digest=digest or _digest_of(recording),
        rubric=rubric,
        actions=len(records),
        records=tuple(records),
        frames=frames_of(exchanged, run_id),
        echoed_sequences=secrets_seen(exchanged, values),
    )
