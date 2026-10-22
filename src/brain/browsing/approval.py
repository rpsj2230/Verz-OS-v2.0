"""A browser write waits for a person, and the person approves the envelope through the leash.

M19.7.2 asks for the write capability to sit behind envelope approval. **There is no second
approval mechanism here.** `brain.gate.leash.SuspendedAction` already holds an action a person
must see, with its artefact kept verbatim and its digest stored beside it, `brain.console.
approvals.decide` already decides one and writes the ledger entry before the state moves, and
`brain.console.role_surfaces.pending_for` already decides who may. So an envelope that waits is
raised as a suspension of one action, `browser.act_on_surface` on the target, whose arguments
carry the envelope's digest, and everything after that is the existing path.

**The approval binds to the envelope through the action digest.** The leash action's digest
covers its arguments, the arguments carry `Envelope.digest()`, and that digest covers every
step, origin, budget line, rung and unattended write. An envelope altered after the card was
shown produces a different digest, and `approved` then returns nothing, whatever the stored
state says. This is the argument `SuspendedAction` makes for storing its own digest, carried
one level further out.

**Who may approve is who could have done the write.** The action's row is the target's
`browser_target` field, the same one `brain.browsing.sessions.surface_scope` narrows the shared
credential to, so `pending_for` offers the card only to somebody holding the write capability
in a scope admitting this target. See `AN_APPROVER_MAY_NOT_WAVE_THROUGH_WHAT_THEY_COULD_NOT_DO_
THEMSELVES` in that module. The asker may approve their own run, which is what Assisted means
everywhere else in the leash: a person reads it first, and the person may be the one who asked.

**An envelope with nothing to approve is refused a card.** Reads never wait, and writes a signed
surface exception compiled to run unattended do not either; see `brain.browsing.autonomy`. A
card asking somebody to approve reading teaches them that approving is a formality.

**A card says what changed since this person's last approved run, so the approver reads a difference
and not a list.** Every card lists the writes that wait and the origins, and a person who approved
the same ten writes yesterday reads the list again without reading it. `envelope_changes` compares
the sealed parts with the ones the asker's last approved envelope for this agent and website
stored, and says in a sentence which writes are new, which are gone and which origins moved, or that
nothing did. It is an argument of the action, so it is in the digest the approval binds to: a card
whose difference was edited after it was shown is a different action. **It is a comparison with what
was approved before, not a judgement of whether the difference is safe**, and it says so by being
only a sentence. Not compared (no previous looked up) is no `changes` line at all, because "first
approval" said when nobody looked would be false.

**One answer to "is this approved", and two ways to arrive at it.** A suspension in memory and
a row read back from `agent.browser_envelope` both reduce to the fields `approved` takes, so
the rule about state, digest, run and window is written once.

Task ids: M19.7.2, M19.2.3
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from brain.browsing.envelope import Envelope
from brain.browsing.sessions import ACT_ON_SURFACE, TARGET_FIELD
from brain.browsing.targets import Target, Verb, is_write
from brain.core.entitlement import EntitlementSet
from brain.gate.leash import (
    DEFAULT_APPROVAL_WINDOW,
    DIGEST,
    Action,
    ApprovalState,
    SuspendedAction,
    render_artefact,
)

#: The argument an approval action carries the envelope's digest under.
ENVELOPE_DIGEST_ARGUMENT: Final = "envelope_digest"

#: The argument a card says what changed under, when it was compared with a previous approval.
CHANGES_ARGUMENT: Final = "changes"

#: The longest the sentence is. A card is read, and a sentence that does not fit one line of a
#: card is read as noise; the rest is in the stored envelope.
MAX_CHANGES_CHARS: Final = 300

#: What the card says when there was no earlier approved run to compare with.
FIRST_APPROVAL: Final = "the first approved run of this agent's writes on this website"

#: What it says when there is nothing to report.
NOTHING_CHANGED: Final = "no write and no origin differs from the last approved run"

#: Why an approval is of the envelope and not of each action.
A_PERSON_APPROVES_THE_CONTRACT_BEFORE_THE_CONTAINER_STARTS: Final = (
    "The actions of a browser run are decided by a page nobody has seen yet, so a card per "
    "action would be raised mid-run, against element references a person cannot judge, while "
    "a container holds a live session open. The envelope is what can be read beforehand: "
    "which surfaces, which verbs, how many times, on which origins. Approving it is approving "
    "everything the policy compiled from it can permit, and nothing it cannot."
)

#: Why an envelope that does not wait is refused a card.
A_CARD_THAT_ASKS_NOTHING_TEACHES_APPROVERS_TO_STOP_READING: Final = (
    "An approval queue full of read-only runs is a queue somebody learns to clear without "
    "reading, and the card that mattered arrives in the middle of it. Only an envelope with a "
    "write that waits for a person raises one."
)


class ApprovalError(Exception):
    """An envelope approval was asked for in terms the leash could not hold."""


@dataclass(frozen=True)
class EnvelopeApproval:
    """A person's approval of one sealed envelope, as the policy compiler receives it.

    Built by `approved` and nowhere else in the package. The compiler checks the run and the
    digest against the envelope in front of it, so a value built by hand for another envelope
    is refused there rather than trusted here.
    """

    run_id: str
    envelope_digest: str
    approved_by: str
    approved_at: datetime

    def __post_init__(self) -> None:
        if not re.fullmatch(DIGEST, self.envelope_digest):
            msg = f"{self.envelope_digest!r} is not an envelope digest"
            raise ApprovalError(msg)
        if not self.approved_by.strip():
            msg = f"an approval of run {self.run_id!r} names nobody who approved it"
            raise ApprovalError(msg)


@dataclass(frozen=True)
class Previous:
    """The sealed parts of the asker's last approved envelope for this agent and website, or none.

    A value of its own so that "nobody looked" (no `Previous` at all) and "looked and found none"
    (`Previous(None)`) are not the same thing. See the module docstring.
    """

    parts: Mapping[str, Any] | None


def _waiting_writes(parts: Mapping[str, Any]) -> dict[str, int]:
    """The writes that wait for a person in sealed parts, counted by surface and verb."""
    unattended = {(str(surface), str(verb)) for surface, verb in parts.get("unattended", [])}
    counts: dict[str, int] = {}
    for surface, verb in parts.get("steps", []):
        if is_write(Verb(str(verb))) and (str(surface), str(verb)) not in unattended:
            name = f"{surface} {verb}"
            counts[name] = counts.get(name, 0) + 1
    return counts


def _list(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{name} x{count}" for name, count in sorted(counts.items()))


def envelope_changes(previous: Previous, envelope: Envelope) -> str:
    """What differs between this envelope and the last approved one, in one sentence.

    Writes by surface and verb with their counts, and origins; read steps are not mentioned, for
    the reason `A_CARD_THAT_ASKS_NOTHING_TEACHES_APPROVERS_TO_STOP_READING` gives. A count that
    went up is a write that was added and one that went down is one that was removed, so the
    sentence is a difference and not two lists to compare by eye.
    """
    if previous.parts is None:
        return FIRST_APPROVAL
    # The same shape `envelope_store.sealed_parts` writes, so the two cannot be compared wrongly.
    from brain.browsing.envelope_store import sealed_parts

    now = sealed_parts(envelope)
    # Counter subtraction keeps the positive differences only: what rose is added, what fell is
    # dropped, and there is no comparison here to get the wrong way round.
    before_writes = Counter(_waiting_writes(previous.parts))
    now_writes = Counter(_waiting_writes(now))
    added = dict(now_writes - before_writes)
    removed = dict(before_writes - now_writes)
    before_origins = {str(one) for one in previous.parts.get("origins", [])}
    now_origins = {str(one) for one in now["origins"]}
    parts: list[str] = []
    if added:
        parts.append(f"adds {_list(added)}")
    if removed:
        parts.append(f"drops {_list(removed)}")
    if now_origins - before_origins:
        parts.append(f"reaches {', '.join(sorted(now_origins - before_origins))} as well")
    if before_origins - now_origins:
        parts.append(f"no longer reaches {', '.join(sorted(before_origins - now_origins))}")
    if not parts:
        return NOTHING_CHANGED
    sentence = "since the last approved run it " + "; ".join(parts)
    if len(sentence) > MAX_CHANGES_CHARS:
        return sentence[: MAX_CHANGES_CHARS - 3] + "..."
    return sentence


def approval_action(
    envelope: Envelope, target: Target, *, agent_id: str, previous: Previous | None = None
) -> Action:
    """The one leash action a person approves for this envelope.

    The arguments are what the card shows, so they are the things a person can judge: the run,
    the writes that wait with their counts, and the origins. The digest rides with them so the
    approval cannot be moved onto an envelope that says something else.
    """
    if envelope.plan.request.target != target.name:
        msg = (
            f"run {envelope.run_id!r} was planned against {envelope.plan.request.target!r} and "
            f"cannot be approved as a run on {target.name!r}"
        )
        raise ApprovalError(msg)
    waiting = [
        step
        for step in envelope.steps
        if step.is_write() and (step.surface, step.verb) not in envelope.unattended
    ]
    counts: dict[str, int] = {}
    for step in waiting:
        name = f"{step.surface} {step.verb.value}"
        counts[name] = counts.get(name, 0) + 1
    args = {
        "run": envelope.run_id,
        "writes": ", ".join(f"{name} x{count}" for name, count in sorted(counts.items())),
        "origins": ", ".join(sorted(envelope.origins)),
        ENVELOPE_DIGEST_ARGUMENT: envelope.digest(),
    }
    if previous is not None:
        args[CHANGES_ARGUMENT] = envelope_changes(previous, envelope)
    return Action(
        agent_id=agent_id,
        tool=ACT_ON_SURFACE,
        target=target.name,
        touched_fields=tuple(sorted(args)),
        row={TARGET_FIELD: target.name},
        args=args,
    )


def raise_approval(
    envelope: Envelope,
    target: Target,
    *,
    agent_id: str,
    reach: EntitlementSet,
    trace_id: str,
    now: datetime,
    window: timedelta = DEFAULT_APPROVAL_WINDOW,
    previous: Previous | None = None,
) -> SuspendedAction:
    """Suspend a run's envelope for a person, exactly as the leash suspends an action.

    `reach` is the run reach the envelope was compiled against, and it must belong to the
    person who asked: the suspension records whose reach the writes would run under, and a run
    raised under somebody else's would put their name on the card. The window is the leash's,
    and `SuspendedAction` refuses one longer than its maximum.
    """
    if not envelope.awaits_approval():
        msg = (
            f"run {envelope.run_id!r} has no write that waits for a person, so there is nothing "
            "to approve"
        )
        raise ApprovalError(msg)
    if reach.principal_id != envelope.plan.request.goal.asked_by:
        msg = (
            f"run {envelope.run_id!r} was asked for by somebody other than the reach it is being "
            "raised under"
        )
        raise ApprovalError(msg)
    action = approval_action(envelope, target, agent_id=agent_id, previous=previous)
    return SuspendedAction(
        id=envelope.run_id,
        trace_id=trace_id,
        action=action,
        principal_id=reach.principal_id,
        ent_hash=reach.ent_hash(),
        artefact=render_artefact(action),
        action_digest=action.digest(),
        raised_at=now,
        expires_at=now + window,
    )


def approved(
    envelope: Envelope,
    *,
    run_id: str,
    digest: str,
    state: ApprovalState | None,
    decided_by: str,
    decided_at: datetime | None,
    expires_at: datetime | None,
) -> EnvelopeApproval | None:
    """Whether this decision approves this envelope, and the approval if it does.

    All of: approved rather than pending or rejected; for this run; against the digest this
    envelope has now; by somebody; and decided before the window closed. Anything else is no
    approval, and it is the same `None` for each, because the caller's next step is the same.
    """
    if state is not ApprovalState.APPROVED:
        return None
    if run_id != envelope.run_id or digest != envelope.digest():
        return None
    if not decided_by or decided_at is None or expires_at is None:
        return None
    if decided_at >= expires_at:
        return None
    return EnvelopeApproval(
        run_id=run_id,
        envelope_digest=digest,
        approved_by=decided_by,
        approved_at=decided_at,
    )


def approval_of(suspension: SuspendedAction, envelope: Envelope) -> EnvelopeApproval | None:
    """The approval a decided suspension grants this envelope, or `None`.

    A suspension whose stored digest no longer matches its action was edited after it was shown,
    and one for any tool but `browser.act_on_surface` is not an envelope approval at all.
    """
    if suspension.action.tool.name != ACT_ON_SURFACE.name:
        return None
    if suspension.action.digest() != suspension.action_digest:
        return None
    return approved(
        envelope,
        run_id=suspension.id,
        digest=suspension.action.args.get(ENVELOPE_DIGEST_ARGUMENT, ""),
        state=suspension.state,
        decided_by=suspension.decided_by,
        decided_at=suspension.decided_at,
        expires_at=suspension.expires_at,
    )
