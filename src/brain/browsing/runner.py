"""The process inside a runner container: it holds the browser, and it is assumed to be lost.

`brain.browsing.launcher` starts one of these per run, in a gVisor container with nothing
writable but memory and no route anywhere but the run's egress proxy. It reads instructions from
its standard input and writes what it saw and did to its standard output, one line of
`brain.browsing.wire` at a time, and nothing else about it is reachable from outside.

**This process owns the DevTools session, and nothing else can reach one.** Chromium is started by
Playwright over a pipe rather than a debugging port, so there is no listening socket a page, a
neighbour or a compromised renderer could connect to and drive the browser around the enforcer.
The session lives in `Browser`'s implementation for the life of the process and ends with it. The
control plane never holds a DevTools connection: it holds a line protocol that can ask for one
declared action at a time.

**It enforces, and nobody believes it.** Every action is decided here by
`brain.browsing.enforcer.authorise` against a policy fixed at start (`wire.policy_of`), which is
the first line. It is inside the blast radius, which is why the control plane replays everything
this process reports through `enforcer.recheck` and reads none of its verdicts. The first line
still matters: it is what stops a write before it happens rather than reporting it afterwards.

**The first refusal ends the run.** A refused action means the actor asked for something the
envelope does not allow, or the page moved somewhere it should not be. Neither is a condition a
run recovers from by trying the next thing, and a run that continues after a breach is a run
whose later actions were chosen by whatever caused it.

**An opening is decided on the page it arrived at.** `authorise` checks an action against the
snapshot it cites, and before the first navigation there is no snapshot to cite. So `OPEN` is
admitted to the navigation by the envelope, the page is fetched through the egress proxy that
refuses any origin outside the run's allowlist, and the action is then decided against the tree
of the page that loaded. A navigation that landed somewhere the policy refuses ends the run on
that refusal, before anything is done on the page.

**A write happens at most once per instruction, even inside the container.** `Browser.act` is a
door that issues, so it is only ever called inside `brain.ops.idempotency.issue_once`, keyed on
the run and the instruction's index, against a ledger that lives as long as the container. A
control plane that sends one instruction twice gets one click. Nothing survives the container,
and nothing needs to: a run is never resumed, and a new run is a new envelope.

**Every page is pictured with its form controls painted over.** `Browser.capture` is the
implementation's promise to mask, and each frame is reported with `inputs_masked` set from that
promise, for `brain.browsing.verification.admit_frames` to hold it to.

Not built here, and why: the Playwright implementation of `Browser` is
`ops/browser/playwright_browser.py`, copied into the runner image and not part of this package.
It imports Playwright, which this repository does not depend on, and it cannot be run on a
machine with no browser. Its behaviour is the rehearsal in `ops/browser/REHEARSAL.md`.

Task ids: M19.1.2, M19.1.3
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final, Protocol

from brain.browsing.enforcer import Action, Enforcement, Policy, Refusal, Spend, authorise
from brain.browsing.observation import Snapshot
from brain.browsing.sessions import ACT_ON_SURFACE
from brain.browsing.targets import Verb
from brain.browsing.wire import (
    Kind,
    Message,
    WireError,
    action_of,
    decode,
    encode,
    policy_of,
    record_fields,
    snapshot_fields,
    snapshot_from_accessibility,
    surfaces_of,
)
from brain.channels.widget import normalise_origin
from brain.connectors.throttle import CallOutcome
from brain.ops.halt import NOTHING_HALTED
from brain.ops.idempotency import (
    IdempotencyError,
    Intent,
    Operation,
    OperationState,
    advance,
    issue_once,
    operation_for,
)

#: The connector name an in-container write is keyed under.
CONNECTOR: Final = "browser"

#: Why the first refusal ends the run.
A_RUN_THAT_CONTINUES_AFTER_A_BREACH_IS_STEERED_BY_WHATEVER_CAUSED_IT: Final = (
    "An action is refused because the actor asked for something outside the envelope or the page "
    "went somewhere it should not. Carrying on means the next action was chosen by the same "
    "reasoning, or on the same page, that produced the breach, so the container ends the run and "
    "is destroyed with it."
)


#: Why every ending, including an exception from the browser, is a line rather than a traceback.
A_RUN_ENDS_ON_ITS_LAST_LINE: Final = (
    "The control plane and the recording read the channel, not standard error. A run that dies on "
    "a browser exception with no last line reads as a recording cut short, and the reason is lost. "
    "So every way out of the loop writes an ended line, and an exception is named by its type "
    "alone, because its message is free to quote whatever the page said."
)


class Browser(Protocol):
    """One browser, one context, one page, and the DevTools session that drives them."""

    def navigate(self, url: str) -> None:
        """Load a declared address and wait for it. Fetched through the run's egress proxy."""
        ...

    def origin(self) -> str:
        """Where the page says it is now, as the browser reports it."""
        ...

    def accessibility_tree(self) -> Mapping[str, Any]:
        """The result of `Accessibility.getFullAXTree`, unaltered."""
        ...

    def act(self, verb: Verb, ref: str, text: str) -> None:
        """Click, type, submit or upload on the node a backend id names. Issues a side effect."""
        ...

    def capture(self) -> bytes:
        """A picture of the page with every form control painted over first."""
        ...


class Channel(Protocol):
    """The container's standard input and output, one line at a time."""

    def receive(self) -> bytes:
        """The next line, or empty bytes when the other side has closed."""
        ...

    def emit(self, line: bytes) -> None:
        """Write one line and flush it."""
        ...


@dataclass
class RunLedger:
    """The operation records for one container's life. Memory only, and that is enough.

    `issue_once` needs a ledger whose writes survive the call, and a container's memory survives
    exactly as long as anything this ledger protects: when the container goes, so does the run,
    and a run is never resumed.
    """

    records: dict[str, Operation] = field(default_factory=dict)

    def claim(self, operation: Operation) -> Operation:
        return self.records.setdefault(operation.key, operation)

    def win(self, key: str) -> bool:
        stored = self.records[key]
        if stored.state is not OperationState.PENDING:
            return False
        self.records[key] = stored.advanced(OperationState.SENT)
        return True

    def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        stored = self.records[key]
        if stored.state is not frm:
            msg = f"operation {key[:16]} is {stored.state.value}, not {frm.value}"
            raise IdempotencyError(msg)
        settled = replace(stored, state=advance(frm, to))
        self.records[key] = settled
        return settled


@dataclass(frozen=True)
class Ended:
    """How a run inside the container ended, as the last line says."""

    reason: str


def drive(channel: Channel, browser: Browser) -> Ended:
    """Run one envelope to its end: read the start, then decide and perform one action per line.

    Returns rather than raises for every ending a run can have, and says which on the last line,
    because the control plane reads that line and a traceback on standard error is a line it does
    not.
    """
    try:
        start = decode(channel.receive())
        policy = policy_of(start)
        surfaces = surfaces_of(start)
    except WireError as exc:
        return _end(channel, f"the start could not be read: {exc}")
    principal = str(start.fields["asked_by"])
    ledger = RunLedger()
    spend = Spend()
    snapshot: Snapshot | None = None
    while line := channel.receive():
        try:
            message = decode(line)
        except WireError as exc:
            return _end(channel, f"an instruction could not be read: {exc}")
        if message.kind is Kind.STOP:
            return _end(channel, "stopped")
        if message.kind is not Kind.ACT:
            return _end(channel, f"a {message.kind.value} message is not an instruction")
        index = message.fields["index"]
        if not isinstance(index, int) or isinstance(index, bool):
            return _end(channel, "an instruction carries no index")
        try:
            outcome = _step(policy, message, surfaces, browser, ledger, spend, snapshot, principal)
        except WireError as exc:
            return _end(channel, f"instruction {index} could not be carried out: {exc}")
        except Exception as exc:  # see A_RUN_ENDS_ON_ITS_LAST_LINE
            # The browser raising (a timeout, a crashed page, an unknown verb) ends the run with a
            # reason on its last line. Only the type is said: the message can quote the page.
            return _end(channel, f"instruction {index} failed: {type(exc).__name__}")
        decision, action, observed = outcome
        spend = decision.spend
        if observed is not None:
            snapshot = observed
            _report(channel, browser, observed)
        channel.emit(encode(Kind.RECORD, **record_fields(index, action, decision.refusal)))
        if decision.refusal is not None:
            return _end(channel, f"refused: {decision.refusal.value}")
    return _end(channel, "the control plane closed the channel")


def _step(
    policy: Policy,
    message: Message,
    surfaces: Mapping[str, str],
    browser: Browser,
    ledger: RunLedger,
    spend: Spend,
    current: Snapshot | None,
    principal: str,
) -> tuple[Enforcement, Action, Snapshot | None]:
    """Decide one instruction, perform it if allowed, and observe what it left behind."""
    verb = Verb(message.fields["verb"])
    if verb is Verb.OPEN:
        surface = str(message.fields["surface"])
        address = surfaces.get(surface)
        if address is None or not policy.admits(surface, Verb.OPEN):
            action = action_of(message, run_id=policy.run_id, origin=browser.origin())
            return _refused(spend, Refusal.NOT_IN_ENVELOPE), action, None
        browser.navigate(address)
        sequence = (current.sequence if current is not None else 0) + 1
        observed = _observe(policy.run_id, sequence, browser)
        action = replace(
            action_of(message, run_id=policy.run_id, origin=browser.origin()), sequence=sequence
        )
        decision = authorise(
            policy, action, observed, spend, halts=NOTHING_HALTED, sequence=sequence
        )
        return decision, action, observed
    action = action_of(message, run_id=policy.run_id, origin=browser.origin())
    if current is None:
        return _refused(spend, Refusal.STALE_SNAPSHOT), action, None
    decision = authorise(
        policy, action, current, spend, halts=NOTHING_HALTED, sequence=current.sequence
    )
    if not decision.allowed:
        return decision, action, None
    text = str(message.fields["text"])
    # Keyed on the instruction alone, not on what it names: one index is one effect, whatever a
    # second line carrying that index asks for.
    operation = operation_for(
        Intent(principal_id=principal, intent_ref=f"{policy.run_id}:{message.fields['index']}"),
        connector=CONNECTOR,
        tool=ACT_ON_SURFACE.name,
    )

    def perform(_: Operation) -> CallOutcome:
        # The one call in this module that changes somebody else's page.
        browser.act(action.verb, action.ref, text)
        return CallOutcome.OK

    issued = issue_once(ledger, operation, perform)
    if not issued.issued:
        msg = "an instruction already carried out was sent again and was not repeated"
        raise WireError(msg)
    return decision, action, _observe(policy.run_id, current.sequence + 1, browser)


def _observe(run_id: str, sequence: int, browser: Browser) -> Snapshot:
    """The tree of the page as it is now, numbered as the next snapshot of this run."""
    origin = normalise_origin(browser.origin())
    if not origin:
        msg = "the page has no origin, so nothing on it can be checked against the allowlist"
        raise WireError(msg)
    return snapshot_from_accessibility(
        browser.accessibility_tree(), run_id=run_id, sequence=sequence, origin=origin
    )


def _report(channel: Channel, browser: Browser, snapshot: Snapshot) -> None:
    """The tree and a masked picture of the page, both numbered with the snapshot's sequence."""
    channel.emit(encode(Kind.SNAPSHOT, **snapshot_fields(snapshot)))
    picture = browser.capture()
    channel.emit(
        encode(
            Kind.FRAME,
            sequence=snapshot.sequence,
            origin=snapshot.origin,
            digest=hashlib.sha256(picture).hexdigest(),
            inputs_masked=True,
            picture=base64.b64encode(picture).decode("ascii"),
        )
    )


def _refused(spend: Spend, refusal: Refusal) -> Enforcement:
    return Enforcement(allowed=False, spend=spend, refusal=refusal)


def _end(channel: Channel, reason: str) -> Ended:
    channel.emit(encode(Kind.ENDED, reason=reason))
    return Ended(reason=reason)
