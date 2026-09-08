"""The guard between an untrusted container and everything it can reach, and its own limits.

Everything else in this package decides what a run may do. This module is what refuses the
action in front of it, one at a time, and it is written on the assumption that the process
asking is already lost. A browser rendering somebody else's JavaScript is not a trustworthy
narrator of its own behaviour, so nothing it says about itself is read: not its claim that an
action is safe, not its idea of what the policy is, and not its account of what it did.

**The policy is compiled once, from the sealed envelope, and there is no way to change it.**
`Policy` is frozen, `compile_policy` is the only constructor anything should use, and it
carries the envelope's digest so that a policy and an envelope can be checked against each
other later. What M19.3.1 is really asking for is the absence of a reload: a policy that can
be refreshed mid-run is a policy whose source can be reached mid-run, and the party who would
reach it is the one holding the compromised browser. There is no `reload`, no `update`, no
setter and no cache with a time to live, and `policy_gaps` fails if a field arrives that
would let one exist.

**A reference is validated against the tree it came from, and only the newest tree.** An
element reference names a node the runner saw. Between that snapshot and the action, the page
can move, replace or re-label that node, so a reference checked against nothing in particular
authorises clicking whatever now sits in that slot. The sequence number in
`brain.browsing.observation.Snapshot` is what makes "the snapshot just produced" checkable
rather than assumed.

**The order of the checks is the argument.** A halt is asked first, before anything about the
action is considered, for the reason `brain.ops.admission.decide` asks it first: a stopped
system is stopped rather than in breach, and the two want different sentences for the person
and opposite instructions for whoever is on call. Then the action must belong to this run,
because nothing below means anything if it does not. Then the origin, because a reference is
only meaningful on the page it was read from and validating one against a tree from another
origin would report a valid reference on the wrong site. Then currency, then the reference,
then the envelope, then the count.

**This is the first thing in the repository to consult `Effect.SIGNAL_RUNNING`.**
`brain.ops.halt` says in its own docstring that refusing new work and stopping running work
are separately implementable and separately forgettable, and until now only the first had a
call site. A browser session is the case that needs the second: it can run for minutes, and
an administrator pressing stop while one is halfway through a supplier portal means stop.
`stopped_now` is asked before every action, which is what "at its next safe point" means when
the safe points are the actions.

**What is not enforced, said rather than assumed.** A halt is asked with no axis, so only a
halt on everything reaches a browser run. That is what M19.6.5 asks for and it is the whole
of what is delivered: a halt scoped to one agent, one department or one person still stops no
browser session, for the reason `brain.ops.halt.ENFORCED_AXES` already records about
admission. `enforcement_gaps` reports it rather than leaving an administrator to discover it.

Scope: domain logic. Nothing here starts a container, and there is no container runtime in
this repository to start. What is here is the decision such a runtime would ask for.

Task ids: M19.3.1, M19.3.2, M19.3.3, M19.3.4, M19.3.6, M19.6.5
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Any, Final, cast

from brain.browsing.envelope import Envelope
from brain.browsing.observation import Snapshot, is_current
from brain.browsing.targets import Verb, is_write
from brain.channels.widget import normalise_origin
from brain.ops.halt import HaltScope, HaltState

#: Why a policy has no way to be refreshed.
A_POLICY_THAT_CAN_BE_RELOADED_CAN_BE_RELOADED_BY_THE_RUN: Final = (
    "The threat is a container whose browser is executing somebody else's code. Any path "
    "that lets the policy change after the container starts is a path that party can try to "
    "reach, and the ones that look most innocent are the worst: a refresh on a timer, a "
    "cache with an expiry, a field somebody made mutable so a test could set it. The policy "
    "is compiled at start from the sealed envelope, it is frozen, and there is nothing to "
    "reach."
)

#: Why the container's own verdict is discarded.
A_COMPROMISED_ENFORCER_REPORTS_THAT_EVERYTHING_WAS_FINE: Final = (
    "The in-container enforcer is the first line and it is inside the blast radius. If the "
    "browser process is taken, the enforcer beside it is taken, and what comes back is a "
    "list of actions each marked allowed. So the control plane re-derives the policy from "
    "the envelope it sealed and replays every returned record against it, reading the "
    "actions and never the verdicts. This is the same reason M19.5.3 ignores the agent's "
    "own account of whether it succeeded."
)

#: Why a stale snapshot is refused rather than tolerated.
A_STALE_REFERENCE_NAMES_WHATEVER_IS_THERE_NOW: Final = (
    "References are minted per tree. Acting on one from an older tree asks the page to "
    "resolve a name we last saw meaning something else, and the page is the party that "
    "decides what it means now. The failure is quiet, because the action succeeds: it "
    "simply succeeds on a different element."
)

#: Why the halt is asked before anything about the action.
A_HALTED_RUN_IS_STOPPED_RATHER_THAN_IN_BREACH: Final = (
    "Asking the envelope first would refuse a halted run for whichever rule it happened to "
    "break next, or admit it if it broke none, and an operator watching would see a policy "
    "refusal during an incident they had already stopped the system for. The halt is asked "
    "first so the reason is the reason."
)


class EnforcementError(Exception):
    """A policy or an action was formed in a way that cannot be decided on."""


class Refusal(enum.StrEnum):
    """Why an action was refused. One member per check, and no member meaning "other".

    Distinct members because they call for different responses: a halt is somebody's
    decision, a stale snapshot is a runner bug, an origin outside the allowlist is either a
    redirect nobody declared or an attack, and a spent budget is a run doing more than it
    planned. A single REFUSED would put all four on the same screen.
    """

    HALTED = "halted"
    WRONG_RUN = "wrong_run"
    ORIGIN_NOT_ALLOWED = "origin_not_allowed"
    ORIGIN_NOT_THE_SNAPSHOT = "origin_not_the_snapshot"
    STALE_SNAPSHOT = "stale_snapshot"
    UNKNOWN_REFERENCE = "unknown_reference"
    NOT_IN_ENVELOPE = "not_in_envelope"
    BUDGET_SPENT = "budget_spent"


@dataclass(frozen=True)
class Policy:
    """What one container may do, compiled at its start and immutable for its life.

    Every field is a value and the whole thing is frozen. `envelope_digest` is carried so
    that a policy can be checked against the envelope it claims to come from without having
    to compare every field, which is what `recheck` does from the trusted side.
    """

    run_id: str
    envelope_digest: str
    origins: frozenset[str]
    #: Surface and verb pairs the envelope admitted.
    allowed: frozenset[tuple[str, Verb]]
    #: How many of each write verb the run may perform in total.
    budget: tuple[tuple[Verb, int], ...]

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            msg = "a policy belonging to no run cannot be matched to an action"
            raise EnforcementError(msg)
        if not self.envelope_digest.strip():
            msg = (
                "a policy with no envelope digest cannot be checked against the envelope it "
                "was compiled from, which is the whole of the control plane's second check"
            )
            raise EnforcementError(msg)

    def allowance(self, verb: Verb) -> int:
        for budgeted, count in self.budget:
            if budgeted == verb:
                return count
        return 0

    def admits(self, surface: str, verb: Verb) -> bool:
        return (surface, verb) in self.allowed


def compile_policy(envelope: Envelope) -> Policy:
    """Turn a sealed envelope into the policy a container starts with.

    The only constructor anything should reach for, and it is a function rather than a
    classmethod so that the direction of the dependency is visible: a policy is derived from
    an envelope and an envelope knows nothing about a policy.

    Called once, at container start. Nothing calls it again during a run and there is
    nowhere for a second call's result to go, because `Policy` is what the enforcer was
    handed and it holds no reference to anything that could be re-read.
    """
    return Policy(
        run_id=envelope.run_id,
        envelope_digest=envelope.digest(),
        origins=envelope.origins,
        allowed=frozenset((step.surface, step.verb) for step in envelope.steps),
        budget=envelope.budget,
    )


@dataclass(frozen=True)
class Action:
    """One thing a container proposes to do next.

    `origin` is where the container says it is. It is checked against the allowlist and
    against the snapshot rather than trusted, which is why it is a field here at all: an
    action whose origin was inferred from the policy would agree with the policy by
    construction and check nothing.
    """

    run_id: str
    surface: str
    verb: Verb
    origin: str
    #: The node this acts on, from the snapshot. Empty for a verb that touches no node.
    ref: str = ""
    #: Which snapshot the reference was read from.
    sequence: int = 0
    #: The credential this action needs, named and never valued.
    placeholder: str = ""


@dataclass(frozen=True)
class Spend:
    """How much of the write budget a run has used. A value, threaded rather than mutated.

    Frozen and returned updated, so that a refused action cannot spend and a caller cannot
    forget to roll one back. A counter object with an `increment` would make the spend happen
    somewhere other than where the decision was made.
    """

    used: tuple[tuple[Verb, int], ...] = ()

    def of(self, verb: Verb) -> int:
        for spent, count in self.used:
            if spent == verb:
                return count
        return 0

    def plus(self, verb: Verb) -> Spend:
        counts = dict(self.used)
        counts[verb] = counts.get(verb, 0) + 1
        return Spend(used=tuple(sorted(counts.items(), key=lambda pair: pair[0].value)))


@dataclass(frozen=True)
class Enforcement:
    """The decision on one action, and the spend that follows it.

    `spend` is always present and is the caller's next tally, unchanged on a refusal. A
    caller that has to decide for itself whether to advance the count is a caller that will
    advance it on the refusal path, which is the direction that costs a run its budget for
    actions it was not allowed to take.
    """

    allowed: bool
    spend: Spend
    refusal: Refusal | None = None

    def __post_init__(self) -> None:
        if self.allowed and self.refusal is not None:
            msg = f"an allowed action carries refusal {self.refusal.value!r}"
            raise EnforcementError(msg)
        if not self.allowed and self.refusal is None:
            msg = "a refused action names no reason, so nothing downstream can say what happened"
            raise EnforcementError(msg)


def stopped_now(halts: HaltState) -> bool:
    """Whether work already in flight must stop, asked with no axis so only a global halt bites.

    Fails closed, exactly as `HaltState.admits` does and for the same reason: a store that
    cannot be read during an incident is disproportionately likely to be unreadable *because*
    of the incident, and carrying on then is ignoring a halt at the moment it was declared.

    **This belongs on `HaltState` and is here instead.** `admits` answers the question for new
    work; there is no method answering it for running work, so every future caller has to
    remember the `known` half for itself, which is precisely the kind of thing one caller gets
    right and the third gets wrong. It is not being added there today because that module is
    shared and two other agents are working in this tree; `enforcement_gaps` reports it so the
    duplication is visible rather than quiet.
    """
    if not halts.known:
        return True
    return any(one.signals_running() for one in halts.blocking())


def authorise(
    policy: Policy,
    action: Action,
    snapshot: Snapshot,
    spend: Spend,
    *,
    halts: HaltState,
    sequence: int,
) -> Enforcement:
    """Decide one action. Pure, total, and it reads nothing the container asserted about itself.

    `sequence` is the newest snapshot the control plane knows about, held outside the
    container. Taking it from the snapshot instead would let a container replay an old tree
    and its own old number together, and the pair would agree.

    There is no branch that admits anyway under some condition. That absence is the whole of
    the module: a guard with an exception is a guard that holds on the days nothing was going
    to go wrong.
    """
    if stopped_now(halts):
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.HALTED)
    if action.run_id != policy.run_id:
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.WRONG_RUN)
    origin = normalise_origin(action.origin)
    # An origin that did not parse is refused on its own line rather than left to the
    # membership test. `normalise_origin` answers with the empty string for `null`, for a
    # `file://` document and for anything malformed, so a single membership test would admit
    # every one of them the moment an empty entry reached the allowlist by any route. The
    # constructors in `brain.browsing.targets` refuse that entry, and this refuses the action
    # regardless, because the two are separately reachable and this is the enforcement path.
    if not origin:
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.ORIGIN_NOT_ALLOWED)
    if origin not in policy.origins:
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.ORIGIN_NOT_ALLOWED)
    if origin != snapshot.origin:
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.ORIGIN_NOT_THE_SNAPSHOT)
    if not is_current(snapshot, run_id=policy.run_id, sequence=sequence):
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.STALE_SNAPSHOT)
    if action.sequence != sequence:
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.STALE_SNAPSHOT)
    if action.ref and not snapshot.has(action.ref):
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.UNKNOWN_REFERENCE)
    if not policy.admits(action.surface, action.verb):
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.NOT_IN_ENVELOPE)
    if is_write(action.verb):
        if spend.of(action.verb) >= policy.allowance(action.verb):
            return Enforcement(allowed=False, spend=spend, refusal=Refusal.BUDGET_SPENT)
        return Enforcement(allowed=True, spend=spend.plus(action.verb))
    return Enforcement(allowed=True, spend=spend)


@dataclass(frozen=True)
class ActionRecord:
    """One action as the container reports it afterwards, with the container's own verdict.

    `claimed_allowed` is carried and never read by anything that decides. It is here so that
    a disagreement between what the container thought and what the control plane concludes is
    visible to a person, which is a useful signal about a runner and a useless input to a
    decision. See `A_COMPROMISED_ENFORCER_REPORTS_THAT_EVERYTHING_WAS_FINE`.
    """

    action: Action
    claimed_allowed: bool


def recheck(envelope: Envelope, records: Sequence[ActionRecord]) -> tuple[str, ...]:
    """Replay everything a container returned against the sealed envelope (M19.3.6).

    The second check, and what makes it worth having is not that the rules differ. They are
    the same rules. What differs is the input and the trust domain: this runs in the control
    plane, over a policy re-derived here from the envelope this side sealed, reading the
    actions and discarding every verdict the container attached to them. A container that
    bypassed its own enforcer entirely still has to send back a list of what it did, and this
    is what reads that list.

    **Two honest limits.** A bug in a rule is in both copies, so this is defence against a
    compromised container and not against a wrong rule. And reference validation is not
    repeated here: the only trees available are the ones the container returned, so checking
    a reference against them asks the untrusted party to mark its own work. Origin, verb,
    envelope membership, count and ordering are all decidable from the sealed side, and those
    are what this checks.

    Returns findings rather than raising, in the shape `brain.ops.halt.halt_gaps` uses: a
    caller reviewing a finished run wants every disagreement, not the first one.
    """
    policy = compile_policy(envelope)
    findings: list[str] = []
    spend = Spend()
    last = 0
    for index, record in enumerate(records, 1):
        action = record.action
        where = f"action {index} ({action.verb.value} on {action.surface!r})"
        if action.run_id != policy.run_id:
            findings.append(f"{where} belongs to run {action.run_id!r} and not {policy.run_id!r}")
            continue
        origin = normalise_origin(action.origin)
        if not origin or origin not in policy.origins:
            findings.append(f"{where} reached an origin the envelope does not allow")
        if not policy.admits(action.surface, action.verb):
            findings.append(f"{where} is not in the envelope")
        if action.sequence < last:
            findings.append(
                f"{where} cites snapshot {action.sequence} after snapshot {last}, so the run "
                "acted on a tree it had already replaced"
            )
        last = max(last, action.sequence)
        if is_write(action.verb):
            spend = spend.plus(action.verb)
            if spend.of(action.verb) > policy.allowance(action.verb):
                findings.append(
                    f"{where} is write number {spend.of(action.verb)} of "
                    f"{action.verb.value} against a budget of {policy.allowance(action.verb)}"
                )
    return tuple(findings)


def policy_gaps(subject: type = Policy) -> tuple[str, ...]:
    """Every field on `Policy` that would make it something other than immutable.

    The same shape as `brain.ops.halt.halt_gaps` and for the same reason: the failure is not
    somebody deciding to make a policy reloadable, it is a field called `refreshed_at` or
    `version` arriving with a plausible default and being read six months later as an
    invitation. Checked against the type rather than against behaviour, because by the time
    the behaviour is wrong the field is load bearing.

    Takes the type so a test can plant one carrying `refreshed_at` and prove the check is
    looking rather than that it is empty. `brain.browsing.observation.vision_gaps` takes its
    subjects for the same reason, and both were made to after a mutation run showed the
    branches unreachable: a scan that never scanned reports the same clean answer as a scan
    that found nothing.
    """
    names = {one.name for one in fields(cast(Any, subject))}
    gaps: list[str] = []
    for forbidden in ("expires_at", "ttl", "refreshed_at", "reloaded_at", "version", "epoch"):
        if forbidden in names:
            gaps.append(
                f"{subject.__name__} carries {forbidden}, which is a reason to re-read the "
                "policy during a run, and the party who would reach whatever it is re-read "
                "from is the container whose browser is running somebody else's code"
            )
    if "envelope_digest" not in names:
        gaps.append(
            f"{subject.__name__} carries no envelope digest, so a policy cannot be checked "
            "against the envelope it claims to come from and the control plane's second "
            "check has nothing to compare"
        )
    return tuple(gaps)


def enforcement_gaps() -> tuple[str, ...]:
    """What this module refuses that it looks like it refuses, and what it does not.

    Written down rather than left in a commit message, because the person who needs it is an
    administrator declaring a halt on one agent and expecting a browser session to stop.
    """
    gaps = list(policy_gaps())
    unenforced = sorted(scope.value for scope in HaltScope if scope is not HaltScope.EVERYTHING)
    gaps.append(
        "a browser run consults the halt state with no axis, so only a halt on everything "
        f"stops one; halts scoped to {', '.join(unenforced)} stop no browser session, which "
        "is the same gap brain.ops.halt.ENFORCED_AXES records about admission"
    )
    gaps.append(
        "stopped_now asks a question that belongs on HaltState beside admits, so the "
        "fail-closed half of it is stated twice in the repository and only one copy is "
        "covered by that module's tests"
    )
    return tuple(gaps)
