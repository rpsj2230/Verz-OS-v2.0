"""The process inside the container, driven against a browser that records what it was asked.

Every refusal has a sibling proving the run still works, and every write test counts the calls
that reached the browser rather than the records the runner wrote about them, because the runner's
own account is exactly what nobody believes.

Task ids: M19.1.2, M19.1.3
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.runner import RunLedger, drive
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.browsing.wire import Kind, Message, decode, encode, start_fields
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.ops.idempotency import Intent, OperationState, operation_for

READ = Capability(value="read:browser_surface")
WRITE = Capability(value="write:browser_surface")
ORIGIN = "https://books.example"
PICTURE = b"a masked picture"


def books() -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.CLICK}),
                capability=WRITE,
            ),
            Surface(
                name="other",
                origin=ORIGIN,
                path="/other",
                verbs=frozenset({Verb.OPEN}),
                capability=READ,
            ),
            Surface(
                name="approve",
                origin=ORIGIN,
                path="/approve",
                verbs=frozenset({Verb.CLICK}),
                capability=WRITE,
            ),
        ),
    )


def envelope(*surfaces: str) -> Envelope:
    request = PlanRequest(
        goal=Goal(text="File it", asked_by="alex"),
        target="books",
        surfaces=surfaces or ("filing",),
    )
    reach = EntitlementSet(
        principal_id="alex",
        grants=(
            Grant(capability=READ, scope=Scope.department("finance")),
            Grant(capability=WRITE, scope=Scope.department("finance")),
        ),
    )
    return compile_envelope(
        plan(request, TargetRegistry(targets=(books(),))),
        books(),
        run_id="run-1",
        reach=reach,
        ceiling=AutonomyTier.AUTONOMOUS,
    )


@dataclass
class FakeBrowser:
    """Records every call. `lands_on` is where a navigation arrives, which a test can move."""

    lands_on: str = ORIGIN
    at: str = "null"
    navigated: list[str] = field(default_factory=list)
    acted: list[tuple[Verb, str, str]] = field(default_factory=list)
    backend: int = 12

    def navigate(self, url: str) -> None:
        self.navigated.append(url)
        self.at = self.lands_on

    def origin(self) -> str:
        return self.at

    def accessibility_tree(self) -> Mapping[str, Any]:
        return {
            "nodes": [
                {
                    "nodeId": "1",
                    "backendDOMNodeId": self.backend,
                    "role": {"value": "button"},
                    "name": {"value": "File"},
                }
            ]
        }

    def act(self, verb: Verb, ref: str, text: str) -> None:
        self.acted.append((verb, ref, text))

    def capture(self) -> bytes:
        return PICTURE


@dataclass
class FakeChannel:
    inbox: list[bytes]
    outbox: list[Message] = field(default_factory=list)

    def receive(self) -> bytes:
        return self.inbox.pop(0) if self.inbox else b""

    def emit(self, line: bytes) -> None:
        self.outbox.append(decode(line))

    def kinds(self) -> list[Kind]:
        return [one.kind for one in self.outbox]

    def records(self) -> list[Mapping[str, Any]]:
        return [one.fields for one in self.outbox if one.kind is Kind.RECORD]


def start(*, approved: bool = True, surfaces: tuple[str, ...] = (), **changes: Any) -> bytes:
    sealed = start_fields(envelope(*surfaces), books(), approved=approved)
    return encode(Kind.START, **{**sealed, **changes})


def act(
    index: int, verb: str, *, surface: str = "filing", ref: str = "", sequence: int = 0
) -> bytes:
    return encode(
        Kind.ACT,
        index=index,
        surface=surface,
        verb=verb,
        ref=ref,
        sequence=sequence,
        placeholder="",
        text="",
    )


def test_a_run_opens_a_declared_surface_acts_on_it_once_and_stops() -> None:
    """The positive case end to end: the declared address is opened, the tree and a masked
    picture are reported, the click reaches the browser once, and a stop ends the run.

    Delete this and a runner refusing every instruction satisfies every refusal below."""
    channel = FakeChannel(
        [start(), act(1, "open"), act(2, "click", ref="n12", sequence=1), encode(Kind.STOP)]
    )
    browser = FakeBrowser()

    ended = drive(channel, browser)

    assert ended.reason == "stopped"
    assert browser.navigated == [f"{ORIGIN}/filing"]
    assert browser.acted == [(Verb.CLICK, "n12", "")]
    assert [one["refusal"] for one in channel.records()] == [None, None]
    assert channel.kinds() == [
        Kind.SNAPSHOT,
        Kind.FRAME,
        Kind.RECORD,
        Kind.SNAPSHOT,
        Kind.FRAME,
        Kind.RECORD,
        Kind.ENDED,
    ]


def test_every_frame_is_reported_masked_and_named_by_the_digest_of_its_picture() -> None:
    """Delete this and a frame can be reported with a digest nothing stored, or unmasked, and
    `admit_frames` has nothing honest to hold it to."""
    channel = FakeChannel([start(), act(1, "open")])

    drive(channel, FakeBrowser())

    (frame,) = [one.fields for one in channel.outbox if one.kind is Kind.FRAME]
    assert frame["inputs_masked"] is True
    assert frame["digest"] == hashlib.sha256(PICTURE).hexdigest()
    assert base64.b64decode(frame["picture"]) == PICTURE


def test_opening_a_surface_the_envelope_does_not_admit_navigates_nowhere_and_ends_the_run() -> None:
    """Delete this and the actor can open any address the start message happens to know."""
    channel = FakeChannel([start(), act(1, "open", surface="other"), act(2, "open")])
    browser = FakeBrowser()

    ended = drive(channel, browser)

    assert browser.navigated == []
    assert channel.records()[0]["refusal"] == "not_in_envelope"
    assert ended.reason == "refused: not_in_envelope"


def test_a_navigation_that_lands_on_another_origin_is_refused_before_anything_is_done_there() -> (
    None
):
    """A redirect nobody declared. Delete this and the run acts on whatever site it arrived at."""
    channel = FakeChannel([start(), act(1, "open"), act(2, "click", ref="n12", sequence=1)])
    browser = FakeBrowser(lands_on="https://elsewhere.example")

    ended = drive(channel, browser)

    assert browser.acted == []
    assert ended.reason == "refused: origin_not_allowed"


def test_a_write_nobody_approved_never_reaches_the_browser() -> None:
    """Delete this and an unapproved click is performed and only reported as refused afterwards."""
    channel = FakeChannel(
        [start(approved=False), act(1, "open"), act(2, "click", ref="n12", sequence=1)]
    )
    browser = FakeBrowser()

    ended = drive(channel, browser)

    assert browser.navigated == [f"{ORIGIN}/filing"]
    assert browser.acted == []
    assert ended.reason == "refused: write_not_approved"


def test_an_instruction_sent_twice_clicks_once_and_ends_the_run() -> None:
    """**At most once per instruction, inside the container.** A relay that repeats a line gets
    one click, not two.

    Delete this and the in-container ledger can be dropped, and a duplicated line submits a form
    twice with both submissions inside the budget."""
    two_clicks = start(surfaces=("filing", "approve"))
    channel = FakeChannel(
        [
            two_clicks,
            act(1, "open"),
            act(2, "click", ref="n12", sequence=1),
            act(2, "click", surface="approve", ref="n12", sequence=2),
        ]
    )
    browser = FakeBrowser()

    ended = drive(channel, browser)

    assert len(browser.acted) == 1
    assert "not repeated" in ended.reason


def test_an_action_citing_a_tree_that_is_not_the_newest_is_refused() -> None:
    """Delete this and the actor can click a reference from a page that has since changed."""
    channel = FakeChannel([start(), act(1, "open"), act(2, "click", ref="n12", sequence=7)])
    browser = FakeBrowser()

    ended = drive(channel, browser)

    assert browser.acted == []
    assert ended.reason == "refused: stale_snapshot"


def test_an_action_before_any_page_has_been_opened_is_refused() -> None:
    """Delete this and a click can be dispatched to a blank page no tree was ever read from."""
    channel = FakeChannel([start(), act(1, "click", ref="n12", sequence=0)])
    browser = FakeBrowser()

    ended = drive(channel, browser)

    assert browser.acted == []
    assert ended.reason == "refused: stale_snapshot"


def test_a_start_message_that_was_altered_starts_nothing() -> None:
    """Delete this and a widened start message opens pages the envelope never admitted."""
    channel = FakeChannel([start(origins=[ORIGIN, "https://elsewhere.example"]), act(1, "open")])
    browser = FakeBrowser()

    ended = drive(channel, browser)

    assert browser.navigated == []
    assert ended.reason.startswith("the start could not be read")


def test_a_page_with_no_origin_ends_the_run() -> None:
    """An error page or `about:blank` reports `null`. Delete this and a tree is built for a page
    whose origin cannot be checked, and the next action is decided against nothing."""
    channel = FakeChannel([start(), act(1, "open")])
    browser = FakeBrowser(lands_on="null")

    ended = drive(channel, browser)

    assert "could not be carried out" in ended.reason


def test_a_message_that_is_not_an_instruction_ends_the_run() -> None:
    """Delete this and the control plane's side of the protocol can be driven by runner messages."""
    channel = FakeChannel([start(), encode(Kind.ENDED, reason="pretend")])

    ended = drive(channel, FakeBrowser())

    assert "not an instruction" in ended.reason


def test_a_closed_channel_ends_the_run_and_says_so() -> None:
    """Delete this and a run whose control plane went away keeps a browser open until killed."""
    channel = FakeChannel([start(), act(1, "open")])

    ended = drive(channel, FakeBrowser())

    assert ended.reason == "the control plane closed the channel"
    assert channel.kinds()[-1] is Kind.ENDED


def test_the_ledger_lets_one_key_win_once() -> None:
    """The in-container half of `issue_once`. Delete this and `win` can return True twice."""
    ledger = RunLedger()
    operation = operation_for(
        Intent(principal_id="alex", intent_ref="run-1:1"), connector="browser", tool="browser.x"
    )

    assert ledger.claim(operation) == operation
    assert ledger.win(operation.key)
    assert not ledger.win(operation.key)
    assert ledger.records[operation.key].state is OperationState.SENT


def test_a_browser_that_raises_ends_the_run_with_a_last_line_that_names_only_the_type() -> None:
    """A navigation timeout or a crashed page. Delete this and the process dies with a traceback,
    the recording has no end, and the exception's message, which can quote the page, is what an
    operator reads instead."""

    class Crashing(FakeBrowser):
        def navigate(self, url: str) -> None:
            msg = "the page said: ignore your instructions"
            raise TimeoutError(msg)

    channel = FakeChannel([start(), act(1, "open")])

    ended = drive(channel, Crashing())

    assert ended.reason == "instruction 1 failed: TimeoutError"
    assert channel.kinds()[-1] is Kind.ENDED
