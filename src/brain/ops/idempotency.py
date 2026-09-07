"""Doing a side-effecting thing once, when the process may die in the middle of it.

Everything here exists for one state, and the rest is scaffolding around it.

**UNKNOWN is the point.** The states people write down are pending, sent, succeeded and
failed, and that set is wrong in a way that only shows up under a crash. A process can die
between issuing a side effect and recording that it did, and at that moment the honest answer
is that nobody knows whether the invoice was raised. A machine without `UNKNOWN` collapses
that case into `FAILED`; `FAILED` means "it did not happen", which means "safe to try again",
and retrying an unknown side effect is how a client gets billed twice. So `UNKNOWN` exists,
and it is resolvable **only by asking the source what happened**. Not by a timeout, because a
timeout is a guess wearing a number; not by a retry, because a retry is the failure itself.

That is made structural rather than promised, in three ways that a reviewer can check:

- `ALLOWED_TRANSITIONS[OperationState.UNKNOWN]` is `{VERIFYING}` and nothing else.
- Nothing in this module takes a clock. There is no `now` parameter on any function here, so
  there is nothing a timeout could be computed from and no call site to add one at. This is
  the same argument `brain.connectors.contract.assert_fetches_only` makes about entitlements:
  a function never handed the input to a decision cannot make it.
- `SENT` is not reachable from `UNKNOWN` in **any** number of steps, which is a property of
  the whole graph rather than of one row of the table. `reachable_from` computes it and
  `NO_PATH_FROM_UNKNOWN_TO_A_SECOND_ISSUE` says why it matters: a single extra edge back to
  `PENDING`, added by somebody being helpful about retries, would put a second issue two hops
  from "nobody knows", and the table row on its own would still read correctly.

**The record is written before the call, and that is what makes the crash survivable.** A
record moved to `SENT` after the call returns leaves a window with no row in it, and the whole
argument above is about that window. So `SENT` means "a request has left this process and a
side effect may now exist", not "the source acknowledged". A record found in `SENT` by a
recovering worker is therefore an `UNKNOWN` that has not been recognised yet, and `resume`
says exactly that.

**An idempotency key is derived, never generated.** A random key minted at call time is a new
key on every attempt, which is not idempotency at all: the source sees two unrelated requests
and does the thing twice. So the key is a function of the operation's identity, and there is
no clock and no entropy anywhere in that function. It is also hashed rather than joined,
because the key travels into the source's own system, into its logs and into ours, and a key
built by concatenating arguments would carry a client's name and an invoice amount into every
one of those places with none of the permissions that governed them. See
`A_KEY_IS_DERIVED_NEVER_GENERATED`.

**A connector that cannot be read back may not be written to.** An operation against it could
never leave `UNKNOWN`, because verification is the only exit and there is nothing to verify
with. `brain.connectors.manifest.ToolDeclaration` refuses to declare such a tool at all, and
this module does not check that again: two enforcement points that are really one is the
mistake `ProjectedEntity.__post_init__` records having made and removed. What is here instead
is the *derivation* the request path uses. `issuable_tools` computes the set of tools an
operation may be raised against from the read-back declaration, so a connector added without
one has an empty set by construction and no request path can name a tool on it. Nobody has to
remember.

Rejected: an edge from `UNKNOWN` or from `VERIFYING` back to `PENDING`, so that an operation
verified absent could simply be issued again. It is the obvious feature and it is the one
change that makes the property above false. A verified-absent operation is `FAILED`, which is
terminal and means "definitely did not happen"; trying again is a new intent, raised by
whoever decided to try, with its own reference. The cost is a caller writing one more line.
The cost of the other choice is paid once, by somebody's client, in a duplicated payment.

Scope: domain logic. Nothing here opens a connection, reads a clock or stores a row. Where the
records live is a table this module does not name and `src/brain/tables/` does not yet hold.

Task ids: M17.3.2, M17.3.4, M17.3.5
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

from brain.connectors.manifest import DIGEST_CHARS, ConnectorManifest, ToolDeclaration
from brain.connectors.throttle import CallOutcome
from brain.core.envelope import SideEffect

# ------------------------------------------------------------------ written-down reasons
#: Why the key is a function of the intent rather than a value minted per attempt.
A_KEY_IS_DERIVED_NEVER_GENERATED = (
    "A key generated at call time is a different key on every attempt, so the source sees "
    "two unrelated requests and raises two invoices. The key has to be a function of what "
    "the operation is, so that the same intent produces the same key however many times it "
    "is attempted: who is acting, which tool, which decision asked for it, and the arguments "
    "that make one instance of it different from another. A clock or a random value in any "
    "of those turns the function back into a generator, which is why nothing in this module "
    "is handed either one. And the result is hashed rather than joined, because the key is "
    "sent to the source, stored in its records and written to both sides' logs; a key built "
    "by concatenation would carry a client name and an amount into all of those, with none "
    "of the permissions that governed them still attached."
)

#: The central claim. Kept as a sentence because the whole module is downstream of it.
UNKNOWN_IS_NOT_FAILED = (
    "FAILED means the side effect definitely did not happen, which is why it is safe to act "
    "on. UNKNOWN means nobody knows whether it did. Collapsing the second into the first is "
    "the ordinary mistake, and it is invisible until the day a process dies between issuing "
    "a payment and recording that it issued one: the operation reads as failed, a retry "
    "looks correct, and the client is billed twice with nothing anywhere reporting it."
)

#: Why verification is the only exit, expressed as a graph property rather than a table row.
NO_PATH_FROM_UNKNOWN_TO_A_SECOND_ISSUE = (
    "It is not enough that UNKNOWN cannot go straight back to SENT. There must be no path of "
    "any length, because the edge somebody adds is never the direct one: it is a helpful "
    "'a verified-absent operation can just be issued again' from VERIFYING back to PENDING, "
    "and that puts a second issue two hops from 'nobody knows'. The table row would still "
    "read correctly on the day it was added. So the property is stated over the closure and "
    "tested there."
)

#: Why the row is written before the request goes out rather than after it comes back.
THE_RECORD_IS_WRITTEN_BEFORE_THE_CALL = (
    "SENT is recorded before the request is made, so it means 'a side effect may now exist' "
    "rather than 'the source said yes'. Recording it afterwards leaves exactly the window "
    "this module exists for: the process dies between the source acting and the row being "
    "written, and the recovering worker finds a record that says nothing happened. Writing "
    "first costs one state that is sometimes pessimistic and buys a crash that is always "
    "recoverable."
)

#: Why the absence of a read-back is a permission rule and not a retry setting.
NO_READ_BACK_MEANS_READ_ONLY = (
    "A connector that cannot answer 'did operation X land' cannot resolve an UNKNOWN, so an "
    "operation against it has no exit from the one state that matters. The restriction is "
    "therefore on making the operation at all: the connector is read-only. That is declared "
    "on the tool in brain.connectors.manifest, which refuses to accept a side-effecting tool "
    "with no read-back, and derived here rather than checked again. issuable_tools computes "
    "the writable set from the declaration, so a connector added without a read-back has an "
    "empty one and no request path can name a tool on it."
)

#: What the crash model in the tests covers, and what it does not.
WHAT_THE_CRASH_MODEL_DOES_NOT_COVER = (
    "The exactly-once test drives the machine through every point at which the process could "
    "die and asserts that resuming from the recorded state never issues a second side "
    "effect. That is at-most-once under a model, not a killed process, and three things sit "
    "outside it. The store must make the write durable and the key unique: two workers that "
    "both read no record and both write one will both issue, and only a unique index on the "
    "key can stop that. The source must honour the key it is sent, or exactly-once rests "
    "entirely on the read-back. And a source that returns a definite refusal after having "
    "acted has lied about whether it acted, and no state machine is correct against that."
)


class IdempotencyError(Exception):
    """An operation was described in a shape that cannot be made safe to repeat.

    Outside the taxonomy in `brain.core.errors`, for the reason
    `brain.connectors.contract.ConnectorContractError` gives about itself: nobody asking a
    question should ever see this. It is a mistake by whoever wired the call site up.
    """


class IllegalTransitionError(IdempotencyError):
    """A move the state machine does not have an edge for.

    A distinct type rather than a message, so that a recovery sweep can catch a bad
    transition without also catching a malformed key, and so that the one transition that
    must never exist has a name to fail with.
    """


# ------------------------------------------------------------------ the key (M17.3.1)
#: What the hashed material is about. Two different vocabularies are hashed in this system
#: with the same algorithm, and a digest whose meaning depends on which table it was found in
#: is a digest that will eventually be compared across them.
KEY_DOMAIN: Final = "brain.operation.v1"

#: How many hex characters a key is. The whole SHA-256, and anchored to
#: `manifest.DIGEST_CHARS` rather than restated: both are compared for equality rather than
#: looked up, so there is no index to keep small, and a truncated digest is a collision
#: surface offered for nothing.
KEY_CHARS: Final = DIGEST_CHARS

#: A key that is not this shape is a key somebody minted. It refuses the ordinary spellings
#: of a generated identifier: a uuid is 32 hex characters or 36 with dashes, a request id is
#: not hex at all. It cannot refuse 64 random hex characters, which is why the derivation is
#: a function rather than a convention, and why this is a shape check and not the rule.
_KEY_RE: Final = re.compile(rf"^[0-9a-f]{{{KEY_CHARS}}}$")

#: Argument names that mean "this attempt" rather than "this intent". Matched on word parts,
#: the way `brain.ops.automation._CREDENTIAL_NAME_RE` is, so `retry_count` is caught and
#: `due_at` is not. It catches the name and not the value: a caller who passes a clock
#: reading under the name `reference` defeats it, and the structural half of the rule is that
#: nothing in this module is handed a clock to read in the first place.
VOLATILE_ARGUMENT_RE: Final = re.compile(
    r"(^|_)(now|nonce|uuid|guid|random|rand|entropy|attempt|attempts|retry|retries"
    r"|timestamp|sent_at|issued_at|attempted_at|requested_at|generated_at"
    r"|request_id|trace_id|correlation_id|idempotency_key)(_|$)"
)


def derive_key(
    *,
    principal_id: str,
    tool: str,
    intent_ref: str,
    arguments: Mapping[str, str | int] = MappingProxyType({}),
) -> str:
    """The key for one intent. The same intent gives the same key, for ever.

    Four parts, and each is there because leaving it out merges two things that are not the
    same operation.

    **The principal.** Two people raising the same invoice are raising two invoices. Without
    this, the second one is deduplicated against the first and silently never happens.

    **The tool.** The same arguments handed to `xero.create_invoice` and to
    `xero.void_invoice` are two opposite intents that would otherwise share a key.

    **The intent reference.** The identifier of the decision that asked: an automation run, a
    turn, a job. This is the part that has to be got right in both directions. It must be
    stable across every attempt at that decision, or the key changes under retry and there is
    no idempotency; and it must differ between two decisions, or a nightly automation raising
    this month's invoice on Monday is deduplicated against Tuesday's and one of them never
    happens.

    **The arguments.** What makes one instance of the intent different from another.

    Serialised the way `brain.connectors.manifest.digest_input` serialises a manifest, and for
    the same reason: sorted keys and no whitespace, so reordering a mapping for readability is
    not a different intent.

    Long argument values are welcome here and nowhere else in this package.
    `brain.ops.queue.Job` and `brain.ops.checkpoints` both refuse them, because those rows are
    stored and a stored value is a copy of business data with no permissions on it. Here the
    value is hashed and discarded, and it has to be included or two different emails collide
    on one key. That is precisely why the hash is not optional.

    Floats are not accepted. They have no canonical text form, so two spellings of one number
    would derive two keys for one intent, and the failure is a duplicate rather than an error.
    """
    if not principal_id.strip():
        msg = "an operation key names the principal acting; an unkeyed one merges two people"
        raise IdempotencyError(msg)
    if not tool.strip():
        msg = "an operation key names the tool; without it two opposite intents share a key"
        raise IdempotencyError(msg)
    if not intent_ref.strip():
        msg = (
            "an operation key names the decision that asked for it. Without one, every "
            "attempt at the same arguments is the same operation for ever, so a monthly "
            "automation runs once and never again"
        )
        raise IdempotencyError(msg)

    volatile = sorted(name for name in arguments if VOLATILE_ARGUMENT_RE.search(name.lower()))
    if volatile:
        msg = (
            f"argument(s) {volatile} name this attempt rather than this intent, so the key "
            f"would change on every retry and stop being an idempotency key. "
            f"{A_KEY_IS_DERIVED_NEVER_GENERATED}"
        )
        raise IdempotencyError(msg)

    material = json.dumps(
        {
            "domain": KEY_DOMAIN,
            "principal": principal_id,
            "tool": tool,
            "intent": intent_ref,
            "arguments": dict(arguments),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ------------------------------------------------------- the state machine (M17.3.2)
class OperationState(enum.StrEnum):
    """Where one side-effecting operation has got to. Six values, and the fourth is the point.

    Read the two that are easy to confuse together. `FAILED` is a claim: the side effect did
    not happen, and something knows that, either because the source refused the request or
    because a read-back looked and it was not there. `UNKNOWN` is the absence of a claim. See
    `UNKNOWN_IS_NOT_FAILED`.
    """

    #: Recorded, nothing issued. A crash here has cost nothing.
    PENDING = "pending"
    #: A request has left this process. A side effect may now exist. See
    #: `THE_RECORD_IS_WRITTEN_BEFORE_THE_CALL`.
    SENT = "sent"
    #: Nobody knows whether it landed. Only a read-back can settle it.
    UNKNOWN = "unknown"
    #: A read-back is in flight. Separate from UNKNOWN so that a crash during verification is
    #: distinguishable from a crash before one started, which is the difference between "ask"
    #: and "ask again".
    VERIFYING = "verifying"
    #: It happened, once.
    SUCCEEDED = "succeeded"
    #: It definitely did not happen.
    FAILED = "failed"


#: Every move the machine has an edge for. Exhaustive over `OperationState`, and there is a
#: test whose only job is to keep it that way: a member added without an entry would be a
#: state with no way out, and a record in it would sit unresolved for ever.
ALLOWED_TRANSITIONS: Mapping[OperationState, frozenset[OperationState]] = MappingProxyType(
    {
        # FAILED is reachable from PENDING because a refusal can happen before anything is
        # issued: the leash declines, the limiter refuses, the gate says no. Nothing left, so
        # nothing happened, and that is a claim rather than an absence of one.
        OperationState.PENDING: frozenset({OperationState.SENT, OperationState.FAILED}),
        OperationState.SENT: frozenset(
            {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.UNKNOWN}
        ),
        # One edge, and the whole module is downstream of it being one.
        OperationState.UNKNOWN: frozenset({OperationState.VERIFYING}),
        # Back to UNKNOWN when the read-back itself could not answer. A verification that
        # failed has told us nothing, and pretending otherwise is the collapse this module
        # refuses in the other direction.
        OperationState.VERIFYING: frozenset(
            {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.UNKNOWN}
        ),
        OperationState.SUCCEEDED: frozenset(),
        OperationState.FAILED: frozenset(),
    }
)

#: States with nothing after them. Derived rather than listed, so a terminal state cannot be
#: declared here and given an outgoing edge above.
TERMINAL: Final[frozenset[OperationState]] = frozenset(
    state for state, onward in ALLOWED_TRANSITIONS.items() if not onward
)


def reachable_from(state: OperationState) -> frozenset[OperationState]:
    """Every state this one can reach, in any number of steps. Excludes itself unless a cycle
    returns to it.

    The closure rather than one row, because the property that matters is about paths. See
    `NO_PATH_FROM_UNKNOWN_TO_A_SECOND_ISSUE`.
    """
    seen: set[OperationState] = set()
    frontier = list(ALLOWED_TRANSITIONS[state])
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(ALLOWED_TRANSITIONS[current])
    return frozenset(seen)


def advance(state: OperationState, to: OperationState) -> OperationState:
    """Move an operation, or refuse the move.

    Raises rather than returning the old state on refusal, for the reason
    `brain.channels.webhook.verify` gives about itself: a function that reports a refusal in
    its return value is a function whose result can be ignored by a caller who wrote the call
    on a line of its own, and it reads as a check.
    """
    onward = sorted(ALLOWED_TRANSITIONS[state])
    if to not in onward:
        allowed = ", ".join(onward) if onward else "nothing; it is terminal"
        msg = (
            f"an operation cannot move from {state} to {to}; from {state} it may go to "
            f"{allowed}. {UNKNOWN_IS_NOT_FAILED}"
        )
        raise IllegalTransitionError(msg)
    return to


def state_after_call(outcome: CallOutcome) -> OperationState:
    """What one call's outcome says about whether the side effect happened.

    Asked once per operation, with the outcome the attempt ended on. Backing off and calling
    again after a 429 is `brain.connectors.throttle.retry_delay`'s job and happens while the
    operation is in `SENT`, which is also what makes a crash in the middle of that loop
    recoverable.

    `UNAVAILABLE` is the branch the module exists for. A timeout, a dropped connection and a
    500 all mean the same thing here, which is that the request may have been processed and
    the answer lost, so the state is `UNKNOWN` and only a read-back settles it.

    `QUOTA` is the one place a definite answer is taken from a status code rather than from a
    read-back, and it is worth naming the risk. A 429 is defined as a refusal to process, and
    `brain.connectors.throttle.A_QUOTA_REFUSAL_IS_NOT_ILL_HEALTH` reads it the same way: the
    source's rate limiter stopped us at the door. A source that applies a change and then
    returns 429 has lied about whether it acted, and nothing here can be correct against
    that; see `WHAT_THE_CRASH_MODEL_DOES_NOT_COVER`.

    `TRUNCATED` is refused rather than mapped. It is a statement about a result set that came
    back short, which no write produces: `throttle.classify` only reaches it when a caller
    passes a returned-record count. A caller that gets here has classified a read and is about
    to record a write as having succeeded on the strength of it.
    """
    if outcome is CallOutcome.OK:
        return OperationState.SUCCEEDED
    if outcome in (CallOutcome.REJECTED, CallOutcome.QUOTA):
        return OperationState.FAILED
    if outcome is CallOutcome.UNAVAILABLE:
        return OperationState.UNKNOWN
    msg = (
        f"{outcome} is a read's outcome and describes a result set, not a side effect; "
        "recording a write from it would call a truncated search a completed operation"
    )
    raise IdempotencyError(msg)


# ------------------------------------------------------- the read-back (M17.3.3)
class Verification(enum.StrEnum):
    """What asking the source produced.

    `INCONCLUSIVE` is the same argument as `UNKNOWN` one level down, and leaving it out is the
    same mistake: a read-back that timed out has not shown the effect to be absent, and a
    verifier with two values has to call it one or the other.
    """

    #: The source has it, under our key or by its natural identity.
    FOUND = "found"
    #: The source has looked and it is not there.
    ABSENT = "absent"
    #: The read-back could not answer. Nothing has been learnt.
    INCONCLUSIVE = "inconclusive"


#: What each answer settles. `INCONCLUSIVE` returns the record to UNKNOWN rather than leaving
#: it in VERIFYING, so a record is never parked in a state that reads as work in progress
#: when no work is in progress.
_AFTER_VERIFICATION: Mapping[Verification, OperationState] = MappingProxyType(
    {
        Verification.FOUND: OperationState.SUCCEEDED,
        Verification.ABSENT: OperationState.FAILED,
        Verification.INCONCLUSIVE: OperationState.UNKNOWN,
    }
)


def state_after_verification(answer: Verification) -> OperationState:
    """What a read-back settles. Exhaustive over `Verification` by construction."""
    return _AFTER_VERIFICATION[answer]


#: One connector's read-back: given the operation, say whether the source has it.
#:
#: A callable rather than a class, and it is handed the whole record rather than the key
#: alone, because a source that does not echo our key has to be searched by the operation's
#: natural identity and the record is where that lives. It returns a `Verification` and has no
#: way to express "assume it worked", which is the same shape rule
#: `brain.ops.limits.VolumeAssessment` follows: a type with nowhere to say the dangerous thing
#: cannot be made to say it by somebody in a hurry.
ReadBackFn = Callable[["Operation"], Verification]


# ------------------------------------------------- what may be operated on (M17.3.4)
def issuable_tools(manifest: ConnectorManifest) -> tuple[str, ...]:
    """The tools on this connector an operation may be raised against, in sorted order.

    Derived, not configured. A tool qualifies when it declares a side effect and declares a
    read-back, so a connector that can verify nothing has an empty set and there is no request
    path that can name a tool on it. That is what `NO_READ_BACK_MEANS_READ_ONLY` means by
    structural: nobody has to remember the rule, because there is nothing to remember it
    against.

    This is deliberately not a second enforcement point.
    `brain.connectors.manifest.ToolDeclaration` already refuses to declare a side-effecting
    tool with no read-back, so within a valid manifest the second term is implied by the
    first, and `ProjectedEntity.__post_init__` records what happens when two checks that are
    really one are left in place: the next person deletes whichever they find first. What this
    adds is the derivation the request path uses and the two failures the manifest cannot
    make, which are a tool nobody declared and a tool that is read-only.
    """
    return tuple(
        sorted(
            tool.name
            for tool in manifest.tools
            if tool.side_effect is not SideEffect.NONE and tool.verifies_write
        )
    )


def read_only_reason(manifest: ConnectorManifest) -> str:
    """Why this connector may make no operations, or an empty string if it may.

    A sentence rather than a boolean, because the question is asked in a console row and by
    whoever is wondering why their write tool is not there, and "False" answers neither.
    """
    if issuable_tools(manifest):
        return ""
    return (
        f"{manifest.name} declares no tool that both has a side effect and can be read back, "
        f"so it is read-only. {NO_READ_BACK_MEANS_READ_ONLY}"
    )


def declaration_for(manifest: ConnectorManifest, tool: str) -> ToolDeclaration:
    """The declaration an operation will run under, or a refusal naming what is missing.

    Default-deny on a name the manifest does not carry. A manifest can only refuse what it was
    shown, so a call site naming a tool that was never declared is the one shape the review at
    declaration time cannot have caught, and treating it as an ordinary write is how a
    connector acquires a write path without one being granted.
    """
    issuable = issuable_tools(manifest)
    if tool not in issuable:
        declared = manifest.tool_names()
        detail = f"it is not one of {list(issuable)}" if issuable else read_only_reason(manifest)
        known = "" if tool in declared else f"; {manifest.name} does not declare it at all"
        msg = f"no operation may be raised against {tool!r}: {detail}{known}"
        raise IdempotencyError(msg)
    for declaration in manifest.tools:
        if declaration.name == tool:
            return declaration
    # Not reachable: `issuable_tools` reads the same tuple this loop walks. Present so that a
    # future edit which computes the issuable set from somewhere else cannot fall through to
    # None and be typed as though it could not.
    msg = f"{tool!r} passed the issuable check and is not in the manifest"
    raise IdempotencyError(msg)


# ------------------------------------------------------------------- the record
@dataclass(frozen=True)
class Operation:
    """One side-effecting intent, and how far it has got.

    Frozen, and moved by `advanced` rather than by assignment, so that every change of state
    goes through `advance` and there is no second way to reach `SENT`. A mutable `state`
    attribute would make the transition table advisory.
    """

    key: str
    connector: str
    tool: str
    principal_id: str
    intent_ref: str
    state: OperationState = OperationState.PENDING

    def __post_init__(self) -> None:
        if not _KEY_RE.match(self.key):
            msg = (
                f"{self.key[:16]!r} is not a derived key. A key is the whole of a SHA-256 in "
                f"lower-case hex, {KEY_CHARS} characters, produced by derive_key. "
                f"{A_KEY_IS_DERIVED_NEVER_GENERATED}"
            )
            raise IdempotencyError(msg)
        for name in ("connector", "tool", "principal_id", "intent_ref"):
            if not str(getattr(self, name)).strip():
                msg = f"an operation record with no {name} cannot be resumed by anybody"
                raise IdempotencyError(msg)

    def advanced(self, to: OperationState) -> Operation:
        return replace(self, state=advance(self.state, to))

    @property
    def is_settled(self) -> bool:
        return self.state in TERMINAL


def begin(
    *,
    manifest: ConnectorManifest,
    tool: str,
    principal_id: str,
    intent_ref: str,
    arguments: Mapping[str, str | int] = MappingProxyType({}),
) -> Operation:
    """Record the intent to do something, before anything is done.

    The only constructor a call site should use, because it is the one that resolves the tool
    against the manifest and derives the key. Building an `Operation` by hand is possible and
    is checked (the key has to be a derived one), but the tool check lives here and there is
    nothing further in that repeats it.

    Returns a record in `PENDING`, which means nothing has been issued. The caller stores it,
    then advances it to `SENT`, then makes the call. In that order: see
    `THE_RECORD_IS_WRITTEN_BEFORE_THE_CALL`.
    """
    declaration = declaration_for(manifest, tool)
    return Operation(
        key=derive_key(
            principal_id=principal_id,
            tool=declaration.name,
            intent_ref=intent_ref,
            arguments=arguments,
        ),
        connector=manifest.name,
        tool=declaration.name,
        principal_id=principal_id,
        intent_ref=intent_ref,
    )


def verify(operation: Operation, read_back: ReadBackFn) -> Operation:
    """Ask the source what happened, and record what it said.

    Moved to `VERIFYING` **before** the read-back runs, for the reason the whole module moves
    to `SENT` before the call: a crash during verification has to be distinguishable from a
    crash before one started, and it only is if the intent to verify was written down first.

    A record already in `VERIFYING` is verified again rather than refused. That is the state a
    worker finds after dying mid-verification, and repeating a read costs nothing, which is
    the entire reason a read-back is the safe way out of `UNKNOWN` and a retry is not.

    **Anything else is refused by the transition table rather than by a check here.** There
    was a guard on this function saying only `UNKNOWN` and `VERIFYING` may be verified, and
    mutation testing showed it was an equivalent mutant: `PENDING`, `SENT` and both terminal
    states have no edge to `VERIFYING`, so `advanced` already raises for every one of them and
    the guard could be deleted whole without a single test noticing. Two checks that look
    like two enforcement points and are really one is worse than one, for the reason
    `brain.connectors.manifest.ProjectedEntity.__post_init__` records having found the same
    way: the next person to edit this deletes whichever they find first, and it is a coin
    toss which. The explanation moved here.
    """
    verifying = (
        operation
        if operation.state is OperationState.VERIFYING
        else operation.advanced(OperationState.VERIFYING)
    )
    return verifying.advanced(state_after_verification(read_back(verifying)))


# ------------------------------------------------------- resuming after a crash (M17.3.5)
class Disposition(enum.StrEnum):
    """What a recovering worker does with a record it found.

    Four, and `ISSUE` appears against exactly one state. That is the exactly-once property
    written as data rather than as a branch, and a test asserts the count rather than the row.
    """

    #: Make the call. Reachable from PENDING and from nowhere else.
    ISSUE = "issue"
    #: Ask the source what happened.
    VERIFY = "verify"
    #: Already done. Return what was recorded.
    DONE = "done"
    #: Already failed. Trying again is a new intent, raised by whoever decides to.
    STOP = "stop"


#: For every state a crash can leave behind: what the record becomes, and what happens next.
#: Exhaustive over `OperationState` and tested to be, like
#: `brain.ops.limit_store.UNREACHABLE_POLICY`, and for the same reason: a missing entry would
#: pick a behaviour by accident, and the accident nobody notices is the one that issues.
RESUME_PLAN: Mapping[OperationState, tuple[OperationState, Disposition]] = MappingProxyType(
    {
        OperationState.PENDING: (OperationState.PENDING, Disposition.ISSUE),
        # The crash this module exists for. A request left the process and the answer did not
        # come back, or came back and was not recorded. Those are the same situation and the
        # honest name for it is UNKNOWN.
        OperationState.SENT: (OperationState.UNKNOWN, Disposition.VERIFY),
        OperationState.UNKNOWN: (OperationState.UNKNOWN, Disposition.VERIFY),
        OperationState.VERIFYING: (OperationState.VERIFYING, Disposition.VERIFY),
        OperationState.SUCCEEDED: (OperationState.SUCCEEDED, Disposition.DONE),
        OperationState.FAILED: (OperationState.FAILED, Disposition.STOP),
    }
)


@dataclass(frozen=True)
class Resumption:
    """What to do with one record found after a restart, and the record as it now stands.

    Carries the reason as well as the verdict, because a worker that quarantines an operation
    puts it in front of a person, and "verify" on its own does not tell them why this row is
    theirs to look at.
    """

    operation: Operation
    disposition: Disposition
    reason: str

    @property
    def may_issue(self) -> bool:
        return self.disposition is Disposition.ISSUE


_RESUME_REASONS: Mapping[OperationState, str] = MappingProxyType(
    {
        OperationState.PENDING: (
            "the record was written and nothing was issued, so the world is unchanged and "
            "this is the first attempt rather than a second one"
        ),
        OperationState.SENT: (
            "a request left this process and no outcome was recorded. Whether the side "
            "effect happened is not knowable from here, so it is asked rather than assumed"
        ),
        OperationState.UNKNOWN: (
            "nobody knows whether this landed, and a read-back is the only thing that can "
            "settle it. A retry would be a second side effect wearing a first attempt's name"
        ),
        OperationState.VERIFYING: (
            "a read-back was in flight when the process died. Repeating a read costs nothing "
            "and is why verification, rather than retry, is the way out of unknown"
        ),
        OperationState.SUCCEEDED: "it happened once, and once is the whole requirement",
        OperationState.FAILED: (
            "it definitely did not happen. Another go is a new intent with its own reference, "
            "decided by somebody rather than by a recovery sweep"
        ),
    }
)


def resume(operation: Operation) -> Resumption:
    """What a recovering worker does with this record. Never issues except from `PENDING`.

    The table above is the whole decision. Written as data because the property somebody has
    to be able to check in ten seconds is "how many states lead to ISSUE", and a chain of
    branches does not answer that.
    """
    state, disposition = RESUME_PLAN[operation.state]
    resumed = operation if state is operation.state else operation.advanced(state)
    return Resumption(
        operation=resumed,
        disposition=disposition,
        reason=_RESUME_REASONS[operation.state],
    )
