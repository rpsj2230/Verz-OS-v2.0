"""The only thing that crosses between the control plane and a runner, and how a page is read.

A runner is a container executing somebody else's JavaScript. Between it and this system there is
one channel, a line of JSON at a time over the container's standard input and output, relayed by
`brain.browsing.launcher`. There is no network route from the runner to anything of ours, so this
module is the whole of the interface an attacker holding the browser can speak to, and it is
written as a parser for hostile input rather than as a convenience for friendly code.

**Every line is bounded, every field is checked, and an unknown field is a refusal.**
`decode` refuses a line longer than `MAX_LINE_BYTES` before parsing it, refuses a message type it
does not know, and refuses a field it does not expect. A tolerant reader is how a runner smuggles
a second meaning into a message the control plane believes it understood.

**The reference is the DevTools backend node id, and that choice is the reference check.**
`snapshot_from_accessibility` reads the tree Chrome's `Accessibility.getFullAXTree` returns, and
names each node by its `backendDOMNodeId`. That number is assigned by the browser, is invisible to
the page's own scripts, and belongs to one DOM node for that node's life: a page that replaces the
button under a reference produces a node with a new number, and the old reference is refused by
`brain.browsing.enforcer.authorise` as unknown. The rejected alternative was writing a reference
into the page as an attribute, which the page can read, copy onto a different element and so
point the next click wherever it likes.

**A tree too large is refused rather than cut.** A page can generate a million nodes. Truncating
would give the actor the top of a page and let it act as though that were all of it, so a tree
over `MAX_NODES` ends the run. A single name over `MAX_NAME` is shortened, because a paragraph is
ordinary and a run refused for one is a run that cannot read a document.

**The policy the runner starts with is re-derived from its sealed parts, never trusted.**
`policy_of` recomputes the envelope digest through `brain.browsing.envelope.seal`, the same
function `brain.browsing.envelope_store` uses to refuse an edited row, and refuses a start message
whose parts do not produce the digest it carries. A runner cannot rebuild an `Envelope`, which
holds the plan and the goal it has no use for, so it builds the `Policy` from the same parts
`compile_policy` would read. That is the one place outside the enforcer a `Policy` is constructed,
and the reason is written here rather than hidden.

Task ids: M19.1.3
"""

from __future__ import annotations

import enum
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from brain.browsing.enforcer import Action, Policy, Refusal
from brain.browsing.envelope import Envelope, seal
from brain.browsing.observation import Node, ObservationError, Snapshot
from brain.browsing.targets import Target, Verb
from brain.gate.injection import AutonomyTier

#: The longest line either side accepts. Sized for one masked picture of a page, base64 encoded,
#: which is the largest thing that legitimately crosses; anything longer is refused unread.
MAX_LINE_BYTES: Final = 4 * 1024 * 1024

#: The most nodes one snapshot may hold. Above it the run ends rather than acting on part of a page.
MAX_NODES: Final = 5000

#: The longest accessible name kept. A longer one is shortened, not refused.
MAX_NAME: Final = 500

#: Why a reference is a browser-assigned number and not something written into the page.
A_REFERENCE_THE_PAGE_CAN_READ_IS_A_REFERENCE_THE_PAGE_CAN_MOVE: Final = (
    "A reference stored in the document as an attribute is visible to the page's scripts, which "
    "can copy it onto another element between the snapshot and the click. The backend node id is "
    "assigned by the browser, cannot be seen or set from the page, and dies with its node, so a "
    "replaced button is an unknown reference rather than a redirected click."
)

#: Why an unexpected field is refused.
A_TOLERANT_READER_IS_A_SECOND_PROTOCOL: Final = (
    "A reader that ignores fields it does not know accepts messages that mean more than it "
    "understood. The sender is a container running somebody else's code, so every message is "
    "exactly its declared fields or it is refused."
)


class WireError(Exception):
    """A line or a tree arrived in a shape that cannot be trusted to mean one thing."""


class Kind(enum.StrEnum):
    """Every message type. The first three go to a runner and the rest come from one."""

    START = "start"
    ACT = "act"
    STOP = "stop"
    SNAPSHOT = "snapshot"
    FRAME = "frame"
    RECORD = "record"
    ENDED = "ended"


#: The fields each message carries, beyond `kind`. Exactly these: see
#: `A_TOLERANT_READER_IS_A_SECOND_PROTOCOL`.
FIELDS: Final[Mapping[Kind, frozenset[str]]] = {
    Kind.START: frozenset(
        {
            "run_id",
            "asked_by",
            "digest",
            "approved",
            "origins",
            "steps",
            "budget",
            "tiers",
            "unattended",
            "surfaces",
        }
    ),
    Kind.ACT: frozenset({"index", "surface", "verb", "ref", "sequence", "placeholder", "text"}),
    Kind.STOP: frozenset(),
    Kind.SNAPSHOT: frozenset({"sequence", "origin", "nodes"}),
    Kind.FRAME: frozenset({"sequence", "origin", "digest", "inputs_masked", "picture"}),
    Kind.RECORD: frozenset({"index", "surface", "verb", "origin", "ref", "sequence", "refusal"}),
    Kind.ENDED: frozenset({"reason"}),
}


@dataclass(frozen=True)
class Message:
    """One decoded line: its kind and its fields, already checked against `FIELDS`."""

    kind: Kind
    fields: Mapping[str, Any]


def encode(kind: Kind, **fields: Any) -> bytes:
    """One message as one line. Refuses a field `FIELDS` does not declare, on the way out too."""
    if set(fields) != FIELDS[kind]:
        msg = f"a {kind.value} message carries {sorted(fields)}, not {sorted(FIELDS[kind])}"
        raise WireError(msg)
    body = json.dumps({"kind": kind.value, **fields}, separators=(",", ":"), sort_keys=True)
    line = body.encode("utf-8") + b"\n"
    if len(line) > MAX_LINE_BYTES:
        msg = (
            f"a {kind.value} message is {len(line)} bytes, over the {MAX_LINE_BYTES} a line may be"
        )
        raise WireError(msg)
    return line


def decode(line: bytes) -> Message:
    """One line as a message, or a refusal. The length is checked before anything is parsed."""
    if len(line) > MAX_LINE_BYTES:
        msg = f"a line of {len(line)} bytes was refused unread"
        raise WireError(msg)
    try:
        parsed = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = "a line that is not JSON was refused"
        raise WireError(msg) from exc
    if not isinstance(parsed, dict):
        msg = "a line that is not a JSON object was refused"
        raise WireError(msg)
    try:
        kind = Kind(parsed.pop("kind", None))
    except ValueError as exc:
        msg = "a line of no known kind was refused"
        raise WireError(msg) from exc
    if set(parsed) != FIELDS[kind]:
        msg = f"a {kind.value} message arrived with fields {sorted(parsed)}"
        raise WireError(msg)
    return Message(kind=kind, fields=parsed)


# ------------------------------------------------------------------ the tree
def snapshot_from_accessibility(
    tree: Mapping[str, Any], *, run_id: str, sequence: int, origin: str
) -> Snapshot:
    """The DevTools accessibility tree as a `Snapshot`, named by backend node id.

    Ignored nodes and nodes with no DOM node behind them are dropped: neither can be acted on,
    and an ignored node is one the browser itself decided a person would not perceive. A second
    AX node over the same DOM node keeps the first, because two nodes with one reference would
    make validating that reference authorise acting on either.
    """
    raw = tree.get("nodes")
    if not isinstance(raw, list):
        msg = "an accessibility tree with no node list cannot be read"
        raise WireError(msg)
    nodes: list[Node] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, Mapping) or entry.get("ignored") is True:
            continue
        backend = entry.get("backendDOMNodeId")
        if not isinstance(backend, int) or isinstance(backend, bool) or backend < 1:
            continue
        ref = f"n{backend}"
        if ref in seen:
            continue
        role = _value(entry.get("role"))
        if not role.strip():
            continue
        seen.add(ref)
        nodes.append(Node(ref=ref, role=role, name=_value(entry.get("name"))[:MAX_NAME]))
        if len(nodes) > MAX_NODES:
            msg = f"a page with more than {MAX_NODES} nodes was refused rather than read in part"
            raise WireError(msg)
    try:
        return Snapshot(run_id=run_id, sequence=sequence, origin=origin, nodes=tuple(nodes))
    except ObservationError as exc:
        raise WireError(str(exc)) from exc


def _value(field: object) -> str:
    """The `value` of a DevTools `AXValue`, as text, or empty when there is none."""
    if isinstance(field, Mapping):
        value = field.get("value")
        if isinstance(value, str):
            return value
    return ""


def snapshot_fields(snapshot: Snapshot) -> dict[str, Any]:
    """A snapshot as the fields of a `snapshot` message."""
    return {
        "sequence": snapshot.sequence,
        "origin": snapshot.origin,
        "nodes": [[node.ref, node.role, node.name] for node in snapshot.nodes],
    }


def snapshot_of(message: Message, *, run_id: str) -> Snapshot:
    """A `snapshot` message back into the type, checked by the type's own constructor."""
    _expect(message, Kind.SNAPSHOT)
    fields = message.fields
    try:
        nodes = tuple(
            Node(ref=str(ref), role=str(role), name=str(name))
            for ref, role, name in fields["nodes"]
        )
        if len(nodes) > MAX_NODES:
            msg = f"a snapshot of more than {MAX_NODES} nodes was refused"
            raise WireError(msg)
        return Snapshot(
            run_id=run_id,
            sequence=int(fields["sequence"]),
            origin=str(fields["origin"]),
            nodes=nodes,
        )
    except (ObservationError, TypeError, ValueError) as exc:
        msg = f"a snapshot message could not be read: {exc}"
        raise WireError(msg) from exc


# ------------------------------------------------------------------ the start of a run
def start_fields(envelope: Envelope, target: Target, *, approved: bool) -> dict[str, Any]:
    """What a runner is told at start: the sealed parts, the digest, and where each surface is.

    `approved` is the control plane's statement that `brain.browsing.approval.approved` returned an
    approval for this envelope. The runner cannot check it and does not need to: a runner lying
    about it to itself only refuses its own writes, and the control plane's `recheck` replays
    everything it did against the approval it actually holds.
    """
    return {
        "run_id": envelope.run_id,
        "asked_by": envelope.plan.request.goal.asked_by,
        "digest": envelope.digest(),
        "approved": approved,
        "origins": sorted(envelope.origins),
        "steps": [[step.surface, step.verb.value] for step in envelope.steps],
        "budget": [[verb.value, count] for verb, count in envelope.budget],
        "tiers": [[verb.value, int(tier)] for verb, tier in envelope.tiers],
        "unattended": [[surface, verb.value] for surface, verb in envelope.unattended],
        "surfaces": {
            step.surface: f"{surface.origin}{surface.path}"
            for step in envelope.steps
            if (surface := target.surface(step.surface)) is not None
        },
    }


def policy_of(message: Message) -> Policy:
    """The policy a runner enforces, rebuilt from a start message and refused if it was altered."""
    _expect(message, Kind.START)
    fields = message.fields
    try:
        run_id = str(fields["run_id"])
        origins = frozenset(str(one) for one in fields["origins"])
        steps = tuple((str(surface), Verb(verb)) for surface, verb in fields["steps"])
        budget = tuple((Verb(verb), int(count)) for verb, count in fields["budget"])
        tiers = tuple((Verb(verb), AutonomyTier(int(tier))) for verb, tier in fields["tiers"])
        unattended = tuple((str(surface), Verb(verb)) for surface, verb in fields["unattended"])
    except (TypeError, ValueError) as exc:
        msg = f"a start message could not be read: {exc}"
        raise WireError(msg) from exc
    digest = seal(
        run_id=run_id,
        origins=origins,
        steps=steps,
        budget=budget,
        tiers=tiers,
        unattended=unattended,
    )
    if digest != fields["digest"]:
        msg = f"the start message for run {run_id!r} does not produce the digest it carries"
        raise WireError(msg)
    if not isinstance(fields["approved"], bool):
        msg = f"the start message for run {run_id!r} says neither yes nor no about approval"
        raise WireError(msg)
    return Policy(
        run_id=run_id,
        envelope_digest=digest,
        origins=origins,
        allowed=frozenset(steps),
        budget=budget,
        approved_digest=digest if fields["approved"] else "",
        unattended=frozenset(unattended),
    )


def surfaces_of(message: Message) -> dict[str, str]:
    """Where each surface in a start message is, as the address a runner opens."""
    _expect(message, Kind.START)
    raw = message.fields["surfaces"]
    if not isinstance(raw, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
    ):
        msg = "a start message names its surfaces in a shape that cannot be read"
        raise WireError(msg)
    return dict(raw)


def action_of(message: Message, *, run_id: str, origin: str) -> Action:
    """An `act` message as the action the enforcer decides, at the origin the browser reports.

    The origin is the browser's, taken at the moment of deciding, and never a field of the
    message: an action whose origin came from the instruction would agree with the policy by
    construction and check nothing.
    """
    _expect(message, Kind.ACT)
    fields = message.fields
    try:
        return Action(
            run_id=run_id,
            surface=str(fields["surface"]),
            verb=Verb(fields["verb"]),
            origin=origin,
            ref=str(fields["ref"]),
            sequence=int(fields["sequence"]),
            placeholder=str(fields["placeholder"]),
        )
    except (TypeError, ValueError) as exc:
        msg = f"an act message could not be read: {exc}"
        raise WireError(msg) from exc


def record_fields(index: int, action: Action, refusal: Refusal | None) -> dict[str, Any]:
    """What a runner reports about one action it decided: the action and its own verdict."""
    return {
        "index": index,
        "surface": action.surface,
        "verb": action.verb.value,
        "origin": action.origin,
        "ref": action.ref,
        "sequence": action.sequence,
        "refusal": None if refusal is None else refusal.value,
    }


def _expect(message: Message, kind: Kind) -> None:
    if message.kind is not kind:
        msg = f"a {message.kind.value} message was read where a {kind.value} message belongs"
        raise WireError(msg)
