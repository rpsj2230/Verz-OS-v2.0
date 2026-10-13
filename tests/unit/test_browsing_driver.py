"""The worker's half of a browser run, driven against the real runner inside a thread.

The runner is the code that will run in the container, and the driver is the code that will run
in the worker, so these tests join the two over a pair of queues rather than faking either side:
whatever the driver sends is read by `runner.drive`, and whatever the runner reports is what the
driver reads. Only the browser (a page that records what it was asked) and the vault are stand-ins.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M19.1.1, M19.2.2, M19.2.3, M19.3.6, M19.4.1, M19.4.4, M19.5.1
Task ids: M19.6.5, M19.6.6, M19.7.2
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.browsing.approval import EnvelopeApproval
from brain.browsing.credentials import Binding, Bindings, SecretKind
from brain.browsing.driver import (
    Instruction,
    ReadOnlyActor,
    RunDeps,
    RunRefusal,
    Substitution,
    run_envelope,
)
from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.observation import Snapshot
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.recording import Direction, Recording, recording_gaps
from brain.browsing.runner import drive
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.ops.halt import NOTHING_HALTED, HaltState
from brain.ops.secrets import Lease, SecretRef, VaultRole

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
READ = Capability(value="read:browser_surface")
WRITE = Capability(value="write:browser_surface")
ORIGIN = "https://books.example"
PASSWORD = "correct-horse-battery"
PLACEHOLDER = "{{secret:books_password}}"


def books() -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=READ,
                reads=("number",),
            ),
            Surface(
                name="login",
                origin=ORIGIN,
                path="/login",
                verbs=frozenset({Verb.OPEN, Verb.TYPE}),
                capability=WRITE,
            ),
        ),
    )


def reach() -> EntitlementSet:
    return EntitlementSet(
        principal_id="alex",
        grants=(
            Grant(capability=READ, scope=Scope.department("finance")),
            Grant(capability=WRITE, scope=Scope.department("finance")),
        ),
    )


def sealed(*surfaces: str) -> Envelope:
    request = PlanRequest(
        goal=Goal(text="Read the invoices", asked_by="alex"),
        target="books",
        surfaces=surfaces or ("invoices",),
    )
    return compile_envelope(
        plan(request, TargetRegistry(targets=(books(),))),
        books(),
        run_id="run-1",
        reach=reach(),
        ceiling=AutonomyTier.AUTONOMOUS,
    )


def approval_of(envelope: Envelope) -> EnvelopeApproval:
    return EnvelopeApproval(
        run_id=envelope.run_id,
        envelope_digest=envelope.digest(),
        approved_by="u_approver",
        approved_at=NOW,
    )


@dataclass
class Page:
    """A browser that records what it was asked and can echo what was typed into its tree."""

    at: str = "null"
    shows: str = "Invoices"
    echoes_typing: bool = False
    navigated: list[str] = field(default_factory=list)
    acted: list[tuple[Verb, str, str]] = field(default_factory=list)

    def navigate(self, url: str) -> None:
        self.navigated.append(url)
        self.at = ORIGIN

    def origin(self) -> str:
        return self.at

    def accessibility_tree(self) -> Mapping[str, Any]:
        return {
            "nodes": [
                {
                    "nodeId": "1",
                    "backendDOMNodeId": 12,
                    "role": {"value": "textbox"},
                    "name": {"value": self.shows},
                }
            ]
        }

    def act(self, verb: Verb, ref: str, text: str) -> None:
        self.acted.append((verb, ref, text))
        if self.echoes_typing:
            self.shows = text

    def capture(self) -> bytes:
        return b"a masked picture"


class Pipe:
    """The runner's channel and the driver's link: two queues and a thread running `drive`."""

    def __init__(self, page: Page) -> None:
        self.to_runner: queue.Queue[bytes] = queue.Queue()
        self.from_runner: queue.Queue[bytes] = queue.Queue()
        self.page = page
        self.sent: list[bytes] = []
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # The runner's side of the channel.
    def receive(self) -> bytes:
        return self.to_runner.get(timeout=5)

    def emit(self, line: bytes) -> None:
        self.from_runner.put(line)

    def _run(self) -> None:
        drive(self, self.page)
        self.from_runner.put(b"")

    # The driver's side.
    async def send(self, line: bytes) -> None:
        self.sent.append(line)
        self.to_runner.put(line)

    async def next_line(self) -> bytes:
        return await asyncio.to_thread(self.from_runner.get, True, 5)

    async def close(self) -> None:
        self.closed = True
        self.to_runner.put(b"")


class PipeLink:
    def __init__(self, pipe: Pipe) -> None:
        self.pipe = pipe

    async def send(self, line: bytes) -> None:
        await self.pipe.send(line)

    async def receive(self) -> bytes:
        return await self.pipe.next_line()

    async def close(self) -> None:
        await self.pipe.close()


@dataclass
class MemoryLedger:
    opened_runs: list[str] = field(default_factory=list)
    closed_runs: list[str] = field(default_factory=list)
    recordings: list[Recording | None] = field(default_factory=list)

    async def opened(self, *, run_id: str, trace_id: str, at: datetime) -> None:
        self.opened_runs.append(run_id)

    async def closed(self, *, run_id: str, at: datetime, recording: Recording | None) -> str | None:
        self.closed_runs.append(run_id)
        self.recordings.append(recording)
        return "d" * 64


@dataclass
class MemoryBackend:
    objects: dict[tuple[str, str], bytes] = field(default_factory=dict)

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self.objects[(bucket_name, key)] = body

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self.objects[(bucket_name, key)]

    def delete_object(self, bucket_name: str, key: str) -> None:
        del self.objects[(bucket_name, key)]

    def list_objects(self, bucket_name: str, prefix: str) -> Any:
        return iter(key for (bucket, key) in self.objects if bucket == bucket_name)


class Vault:
    def __init__(self) -> None:
        self.issued = 0
        self.revoked: list[str] = []

    def issue(self, ref: SecretRef, ttl: timedelta) -> Lease:
        self.issued += 1
        return Lease(
            lease_id=f"lease-{self.issued}",
            ref=ref,
            secret=PASSWORD,
            issued_at=NOW,
            expires_at=NOW + ttl,
        )

    def revoke(self, lease_id: str) -> None:
        self.revoked.append(lease_id)


class Script:
    """An actor that sends a fixed list of instructions and reads nothing."""

    def __init__(self, *instructions: Instruction) -> None:
        self.instructions = instructions
        self.seen: list[Snapshot | None] = []

    def next(self, index: int, last: Snapshot | None) -> Instruction | None:
        self.seen.append(last)
        return self.instructions[index - 1] if index <= len(self.instructions) else None


def deps(
    pipe: Pipe | None,
    actor: Any,
    *,
    ledger: MemoryLedger | None = None,
    backend: MemoryBackend | None = None,
    halts: HaltState = NOTHING_HALTED,
    substitution: Substitution | None = None,
) -> RunDeps:
    async def connect() -> PipeLink:
        if pipe is None:
            msg = "no launcher here"
            raise OSError(msg)
        return PipeLink(pipe)

    return RunDeps(
        connect=connect,
        ledger=ledger or MemoryLedger(),
        actor=actor,
        clock=lambda: NOW,
        halts=lambda: halts,
        backend=backend,
        substitution=substitution,
    )


def run(envelope: Envelope, setup: RunDeps, *, approval: EnvelopeApproval | None = None) -> Any:
    return asyncio.run(
        run_envelope(envelope, books(), approval=approval, deps=setup, trace_id="trace_1")
    )


def test_a_read_run_goes_through_the_real_runner_and_is_recorded_whole() -> None:
    """The positive case end to end: the declared page is opened by the runner, both steps are
    reported, the replay finds nothing, the recording is whole and written to the bucket, and the
    session is opened and closed once.

    Delete this and a driver that refuses everything, or never closes a session, satisfies every
    refusal below."""
    envelope = sealed()
    pipe = Pipe(Page())
    ledger, backend = MemoryLedger(), MemoryBackend()

    result = run(envelope, deps(pipe, ReadOnlyActor(envelope), ledger=ledger, backend=backend))

    assert result.started and result.clean
    assert result.ended == "stopped"
    assert result.actions == 2
    assert pipe.page.navigated == [f"{ORIGIN}/invoices"]
    assert ledger.opened_runs == ledger.closed_runs == ["run-1"]
    assert result.keys and all(key.endswith("transcript.jsonl") for key in result.keys)
    assert len(backend.objects) == 1
    assert recording_gaps(ledger.recordings[0]) == ()  # type: ignore[arg-type]
    assert result.rubric is not None and result.rubric.required()
    assert pipe.closed


def test_a_run_is_not_started_while_the_system_is_halted() -> None:
    """Delete this and the halt that stops new work does not stop a browser from opening, which
    is the one resource a halt is declared to hold back."""
    envelope = sealed()
    ledger = MemoryLedger()

    result = run(
        envelope,
        deps(Pipe(Page()), ReadOnlyActor(envelope), ledger=ledger, halts=HaltState.unknown()),
    )

    assert not result.started and result.refusal is RunRefusal.HALTED
    assert ledger.opened_runs == []


def test_a_write_that_waits_for_a_person_does_not_start_without_their_approval() -> None:
    """Delete this and an envelope whose write waits for a person starts a container on the
    caller's word that somebody agreed."""
    envelope = sealed("login")
    assert envelope.awaits_approval()
    ledger = MemoryLedger()

    result = run(envelope, deps(Pipe(Page()), Script(), ledger=ledger))

    assert not result.started and result.refusal is RunRefusal.NOT_APPROVED
    assert ledger.opened_runs == []


def test_a_launcher_that_cannot_be_reached_refuses_the_run_and_opens_no_session() -> None:
    """Delete this and a run whose launcher is down is recorded as an open session that no
    container ever backed, and the per-site count never comes back down."""
    envelope = sealed()
    ledger = MemoryLedger()

    result = run(envelope, deps(None, ReadOnlyActor(envelope), ledger=ledger))

    assert result.refusal is RunRefusal.LAUNCHER_UNREACHABLE
    assert ledger.opened_runs == []


def test_an_action_outside_the_envelope_ends_the_run_and_the_replay_names_it() -> None:
    """The container refuses the action and the control plane, which reads none of the
    container's verdicts, finds it again from the actions reported. Delete this and the second
    check in the control plane is satisfied by a run that never tried to breach anything."""
    envelope = sealed()
    actor = Script(
        Instruction(surface="invoices", verb=Verb.OPEN),
        Instruction(surface="invoices", verb=Verb.CLICK, ref="n12", text=""),
    )
    pipe = Pipe(Page())

    result = run(envelope, deps(pipe, actor))

    assert result.started and result.ended.startswith("refused:")
    assert result.findings, "the replay should have found the click that was not in the envelope"
    assert not result.clean
    assert pipe.page.acted == []


def test_the_credential_is_typed_once_and_is_in_neither_the_recording_nor_the_result() -> None:
    """The value reaches the one `act` line and the page, and a scrubbed recording and the
    result carry the placeholder only. Delete this and the substitution could be left in the
    stored transcript for thirty days without a test noticing."""
    envelope = sealed("login")
    page = Page()
    vault = Vault()
    bound = Bindings(
        bindings=(
            Binding(
                placeholder=PLACEHOLDER,
                ref=SecretRef(path="browser/books/password", role=VaultRole.BROWSER_RUNNER),
                origin=ORIGIN,
                kind=SecretKind.PASSWORD,
            ),
        )
    )
    actor = Script(
        Instruction(surface="login", verb=Verb.OPEN),
        Instruction(surface="login", verb=Verb.TYPE, ref="n12", placeholder=PLACEHOLDER),
    )
    ledger, backend = MemoryLedger(), MemoryBackend()

    result = run(
        envelope,
        deps(
            Pipe(page),
            actor,
            ledger=ledger,
            backend=backend,
            substitution=Substitution(bindings=bound, vault=vault),
        ),
        approval=approval_of(envelope),
    )

    assert page.acted == [(Verb.TYPE, "n12", PASSWORD)]
    assert vault.issued == 1 and vault.revoked == ["lease-1"]
    stored = b"".join(backend.objects.values()).decode("utf-8")
    assert PASSWORD not in stored and PLACEHOLDER in stored
    assert all(PASSWORD not in text for _, text in ledger.recordings[0].entries)  # type: ignore[union-attr]
    assert PASSWORD not in repr(result)
    assert result.leaked == ()
    assert result.findings == ()


def test_a_value_that_comes_back_from_the_page_is_an_incident_on_the_result() -> None:
    """A page that echoes what was typed puts the value into a snapshot the runner sends back.
    Delete this and a credential that reached the tree is scrubbed quietly and nobody is told."""
    envelope = sealed("login")
    page = Page(echoes_typing=True)
    bound = Bindings(
        bindings=(
            Binding(
                placeholder=PLACEHOLDER,
                ref=SecretRef(path="browser/books/password", role=VaultRole.BROWSER_RUNNER),
                origin=ORIGIN,
                kind=SecretKind.PASSWORD,
            ),
        )
    )
    actor = Script(
        Instruction(surface="login", verb=Verb.OPEN),
        Instruction(surface="login", verb=Verb.TYPE, ref="n12", placeholder=PLACEHOLDER),
    )

    result = run(
        envelope,
        deps(Pipe(page), actor, substitution=Substitution(bindings=bound, vault=Vault())),
        approval=approval_of(envelope),
    )

    assert result.leaked
    assert not result.clean


def test_a_placeholder_on_another_origin_is_refused_and_nothing_is_typed() -> None:
    """The binding names one origin and the page reports another, so no credential is issued and
    the run is stopped. Delete this and origin binding is proved only by a unit test of `resolve`
    that the driver never has to pass through."""
    envelope = sealed("login")
    page = Page()
    vault = Vault()
    bound = Bindings(
        bindings=(
            Binding(
                placeholder=PLACEHOLDER,
                ref=SecretRef(path="browser/books/password", role=VaultRole.BROWSER_RUNNER),
                origin="https://elsewhere.example",
                kind=SecretKind.PASSWORD,
            ),
        )
    )
    actor = Script(
        Instruction(surface="login", verb=Verb.OPEN),
        Instruction(surface="login", verb=Verb.TYPE, ref="n12", placeholder=PLACEHOLDER),
    )

    result = run(
        envelope,
        deps(Pipe(page), actor, substitution=Substitution(bindings=bound, vault=vault)),
        approval=approval_of(envelope),
    )

    assert page.acted == []
    assert vault.issued == 0
    assert "credential was refused" in result.ended


@pytest.mark.parametrize("direction", [Direction.TO_RUNNER, Direction.FROM_RUNNER])
def test_the_recording_holds_both_directions_of_the_run(direction: Direction) -> None:
    """Delete this and a recording that kept only what the runner said, or only what was sent,
    satisfies the whole-run check by omission."""
    envelope = sealed()
    ledger = MemoryLedger()

    run(envelope, deps(Pipe(Page()), ReadOnlyActor(envelope), ledger=ledger))

    recording = ledger.recordings[0]
    assert recording is not None
    assert any(one is direction for one, _ in recording.entries)
