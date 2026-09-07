"""The weekly digest of what the system learnt, and what one click of undo actually does.

`brain.memory.tiers` decides how much oversight a learning needs and has nowhere to approve
one. This is the first of the four surfaces that hand a learning to a person, and it is the
one that arrives as an email, which is what makes it the dangerous one: an email is forwarded,
read on a phone by whoever is standing behind the reader, and clicked twice by somebody who
does not remember clicking it the first time.

**Undo is a mark, never a removal, and it uses the two corrections that already exist.**
`brain.memory.correction` argues at length that a deleted memory cannot explain itself, and a
digest is exactly where that argument gets quietly lost, because the button says undo and undo
sounds like it makes something go away. So this module writes a `Supersession` when there is a
previous memory to restore and a `Demotion` when there is not, and it has no third correction
and no removal of any kind. See `UNDO_IS_A_MARK_AND_NEVER_A_REMOVAL`.

Rejected: a third correction kind, `Undone`. It reads better in a log and it costs the recall
path a third question to remember to ask. `correction.corrected` is one set for exactly that
reason, and every member added to it is another one that gets forgotten at a call site.

**Undo is idempotent, and idempotent here means something sharper than "safe to repeat".** The
click can arrive a week after the email, by which time something else may have superseded the
same memory. Undoing then must not undo *that*: it must do nothing at all. So `undo` asks
`correction.corrected` whether this memory has already been marked, whichever way, and returns
a no-op if it has. It never touches the memory that did the superseding. See
`AN_UNDO_CLICKED_LATE_MUST_NOT_UNDO_THE_SECOND_THING`.

Rejected: making `undo` unconditional and letting the store deduplicate. The store would
deduplicate identical rows, which is not the case that matters; the case that matters produces
two *different* rows, the second of which reverses a correction nobody asked to reverse.

**The digest covers tier one and tier two, and the filter is derived rather than restated.** A
digest mixing tier three in would put a scope widening one button away from an undo in an
email, and the difference between the two buttons is whether somebody may see more than they
could. The tier set is computed from `Tier`'s own ordering, so a tier added above `GATED` is
outside it by construction. There is a second, independent refusal underneath: a change in
`tiers.CHANGES_WHAT_ANYBODY_MAY_SEE` is excluded whatever tier its blast radius claims, which
is what stops a mis-entered `BLAST_RADIUS` row from mailing a capability addition to
everybody. Two grounds because this is the one place where being wrong is a disclosure.

Rejected: writing the filter out as `{Tier.AUTOMATIC, Tier.PROMOTED}`. It is shorter and it is
a second copy of the tier vocabulary, and the copy is the one that goes stale.

**No listing shape here carries a count of what it did not show.** Not a total, not "and three
more", not pagination metadata with a full count in it. A filtered listing beside a total is a
subtraction, and the difference is the number of things about the reader or their department
that they may not see, which is a fact they did not have before opening the email. `Undo`,
`MemoryItem` and `WeeklyDigest` are checked field by field for it, because the field is what a
renderer finds and uses. See `A_COUNT_BESIDE_A_FILTERED_LISTING_IS_A_SUBTRACTION`.

**A digest is entitled like every other disclosure.** It is a list of things the system learnt,
and it is filtered through `formation.may_recall`, which composes `EntitlementSet.intersect`,
`scope_for` and `Scope.matches` and is the only definition of narrower this repository has.
Nothing here decides reach for itself.

**Nothing here applies, sends or stores anything.** `weekly_digest` builds a value, `undo`
returns a correction for somebody else to write, and no clock is read: `now` is a parameter,
as it is in `limits.check` and `denial_alerts.digest`, because a surface that reads its own
clock cannot be tested at the week boundary and the boundary is the only part that is ever
wrong.

Task ids: M16.5.1
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta

from brain.core.entitlement import EntitlementSet
from brain.core.scope import Scope
from brain.memory.correction import Correction, Demotion, Supersession, corrected
from brain.memory.formation import (
    RECALL_FLOOR,
    Formation,
    Recollection,
    confidence_now,
    may_recall,
)
from brain.memory.signals import Observation, Signal
from brain.memory.tiers import CHANGES_WHAT_ANYBODY_MAY_SEE, Change, Proposal, Tier, blast_radius

# ------------------------------------------------------------------ written-down reasons
#: Why the button says undo and the system writes a mark.
UNDO_IS_A_MARK_AND_NEVER_A_REMOVAL = (
    "A person clicking undo in a digest, or delete in a memory tab, is telling the system it "
    "learnt something it should not have. The system records that as a correction and leaves "
    "the memory where it is. `brain.memory.correction` gives the argument in full: deleting "
    "is the one operation that makes the previous behaviour unexplainable, so a person asking "
    "why the system used to say something has nothing left to be answered from, and the mark "
    "is undoable where a delete is not. Undo writes a `Supersession` when there is a previous "
    "memory to restore and a `Demotion` when there is not. There is no third correction and "
    "no code path here that removes anything, which is what the first reader who does not "
    "know this rule would otherwise write."
)

#: Why undoing twice is a no-op rather than a second correction.
AN_UNDO_CLICKED_LATE_MUST_NOT_UNDO_THE_SECOND_THING = (
    "A digest is an email. It is clicked twice by somebody who does not remember the first "
    "click, and it is clicked a week later, by which time something else may have superseded "
    "the same memory. A second correction written then would reverse a correction nobody "
    "asked to reverse, and the memory would come back into recall looking like the system "
    "changing its mind on its own. So undo asks `correction.corrected` whether this memory "
    "has already been marked, either way, and does nothing if it has. It never names the "
    "memory that did the superseding, so there is no path by which undoing the first thing "
    "can touch the second."
)

#: Why the digest stops below the gate, on two independent grounds.
THE_DIGEST_STOPS_BELOW_THE_GATE = (
    "Tier three changes who may see what, and `tiers.propose` deliberately has nowhere to "
    "approve one. A digest carrying tier three would put a scope widening in an email beside "
    "an undo button, and approving a widening by pressing something undo-adjacent is the "
    "failure this whole plane is arranged against. So the digest is tier one and tier two, "
    "and it refuses on two independent grounds: the tier, derived from `Tier`'s ordering "
    "rather than restated, and membership of `CHANGES_WHAT_ANYBODY_MAY_SEE`, which holds "
    "even if a `BLAST_RADIUS` row is edited to say otherwise. One ground would be enough "
    "until the day somebody lowered a row by accident."
)

#: Why no shape here carries a total.
A_COUNT_BESIDE_A_FILTERED_LISTING_IS_A_SUBTRACTION = (
    "A listing filtered by entitlement, shown beside a total, is a subtraction: "
    "'showing twelve of forty' tells the reader there are twenty-eight memories about them "
    "or their department that they may not see, which is twenty-eight facts they did not "
    "have. It is the same rule `denial_alerts` keeps by carrying no number at all, and a "
    "listing is where it leaks most easily, because a total is the first thing anybody adds "
    "to a page of rows. So no shape here has a field for one, and a test walks the fields "
    "rather than the rendered text, because the field is what a later renderer finds."
)

#: Why the evidence in a listing names what was noticed and not where it happened.
EVIDENCE_NAMES_WHAT_WAS_NOTICED_AND_NEVER_WHOSE_CONVERSATION_IT_WAS = (
    "An `Observation` carries a conversation id, a message id and the principal it happened "
    "for, so that somebody can go back to `chat.message` and read what was actually said "
    "under that conversation's own permissions. In a listing shown to a different reader "
    "those three fields are the disclosure: the conversation id says a conversation exists, "
    "and the principal id says whose it was, which turns a memory tab into a note about who "
    "the system learns from. `A_COUNT_PER_PERSON_IS_A_PERFORMANCE_REVIEW` refuses the "
    "aggregate version of that and this refuses the itemised one. So the evidence in a "
    "listing is the set of signal kinds and nothing else: a set rather than a sequence, "
    "because the multiplicity is a count of things that happened in conversations the reader "
    "may not be able to open. What it costs is that the reader cannot follow the evidence "
    "from here; the audit view is the surface built to hold that, filtered per reader."
)


# ------------------------------------------------------------------------- what is shown
#: Field names a filtered listing must never carry, in this module or the surfaces built on
#: it. Not an exhaustive list of every word for a number, which is unwritable: it is the
#: names somebody reaches for when they add a total to a page of rows, which is the moment
#: the rule is broken. `digest_gaps` and `review.review_gaps` both walk it.
COUNTING_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "all_count",
        "and_more",
        "count",
        "counts",
        "filtered_out",
        "hidden",
        "hidden_count",
        "more",
        "num_pages",
        "of_total",
        "omitted",
        "page_count",
        "remaining",
        "shown_of",
        "suppressed",
        "total",
        "total_count",
        "totals",
        "unseen",
        "withheld",
    }
)

#: The tiers a weekly digest may report, from `Tier`'s own ordering rather than a second
#: copy of its membership.
#:
#: Above `SESSION`, because a change confined to one conversation is noise in an email and
#: telling somebody about it trains them to ignore the notices that matter. Below `GATED`,
#: because a gated change waits for a person and an email has no way to be one. Derived, so
#: a tier added above three is outside this by construction; a tier inserted between one and
#: three would land inside it, and what catches that case is the second refusal in
#: `may_digest`, which reads `CHANGES_WHAT_ANYBODY_MAY_SEE` instead.
DIGEST_TIERS: frozenset[Tier] = frozenset(tier for tier in Tier if Tier.SESSION < tier < Tier.GATED)

#: How much of the past one digest covers.
#:
#: A week, which is the leaf's word, and the property that makes a week defensible rather
#: than a habit is that the undo button has to still do something when the email arrives. A
#: memory formed at the start of the window must still be above `formation.RECALL_FLOOR` at
#: the end of it, or the digest is reporting learnings that have already decayed out of
#: recall and the button changes nothing anybody would notice. At a thirty-day half-life a
#: week costs about fifteen per cent of a memory's confidence; a sixty-day digest would put
#: the oldest entries under the floor before the reader saw them. `digest_gaps` checks that
#: against `confidence_now` rather than against a second copy of the arithmetic.
DIGEST_PERIOD = timedelta(days=7)

#: A fixed instant for the arithmetic in `digest_gaps`. Exponential decay depends only on the
#: elapsed time, so any instant answers the question; naming one keeps a clock out of a
#: diagnostic that must give the same answer whenever it is run.
_ANY_INSTANT = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Learning:
    """One thing the system learnt, in the shape every human surface reads it in.

    Shared by the digest, the per-agent tab, the department view and the review queue,
    because four shapes for one record is four places to disagree about what a learning is.

    **Nothing here has taken effect.** `tiers` has no `apply` and neither has this module, so
    a `Learning` is a record that something was proposed at a tier, not a statement that the
    system is now behaving differently. At tier three it is a proposal waiting for a person;
    the tier is what says which, and no surface may read it as anything else.

    Carries no text, no value and no answer, for the reason `formation.Recollection` and
    `signals.Observation` both give: a learning record holding what was said would be a
    second transcript under this record's permissions rather than the conversation's. What it
    carries instead is a `Formation`, which is what recall is checked against, and a
    `Proposal`, whose `subject` is an opaque reference the caller understands.
    """

    memory_id: str
    #: What the learning would change, and the tier its reach requires. Built by
    #: `tiers.propose`, which is the only constructor that cannot lower its own tier.
    proposal: Proposal
    #: What was true about the writer when it was formed. The entitlement check reads this.
    formation: Formation
    #: The signal kinds that prompted it, as a set. See the named constant for why a set and
    #: why kinds only; `evidence_from` is how one is built from observations.
    evidence: frozenset[Signal] = frozenset()
    #: What it was worth when it was formed. Decay from here is `confidence_now`'s job.
    formed_confidence: float = 1.0
    #: The memory this one replaced, when it replaced one. What undo restores.
    replaced_id: str | None = None
    #: The agent that was running when it was formed, if one was. `None` is a learning from
    #: a plain conversation, which belongs to no agent's tab and is not hidden from anybody
    #: by being absent from one.
    agent_id: str | None = None

    def __post_init__(self) -> None:
        if not self.memory_id:
            msg = "a learning with no memory id names nothing a surface can act on"
            raise ValueError(msg)
        if self.replaced_id is not None and self.replaced_id == self.memory_id:
            # Caught here rather than in `Supersession`, which refuses the same thing at the
            # point the correction is written. By then the mistake is a field on a record
            # somebody built hours earlier, and the traceback names the wrong module.
            msg = (
                "a learning cannot have replaced itself; undoing it would write a "
                "supersession that is a loop the recall path would follow"
            )
            raise ValueError(msg)
        if self.agent_id is not None and not self.agent_id:
            msg = "an empty agent id is not the same as no agent and belongs to no tab"
            raise ValueError(msg)
        if not 0.0 < self.formed_confidence <= 1.0:
            msg = (
                f"a learning formed at {self.formed_confidence} is either worth nothing or "
                "worth more than certain; confidence is a fraction of one"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class MemoryItem:
    """One row of a memory listing, as one reader may see it.

    The row every surface but the review queue shows: what was learnt, the evidence, the
    confidence it has now, and what the control would write. The queue has its own shape with
    no control on it at all, because a gated change is not something a person deletes.

    There is no total, no "and more" and no count of anything on this row or on any shape
    that holds a tuple of these. See `A_COUNT_BESIDE_A_FILTERED_LISTING_IS_A_SUBTRACTION`.
    """

    memory_id: str
    change: Change
    #: An ordering rather than a count, which is why it is the one integer-valued field here.
    tier: Tier
    #: What the learning is about, as the opaque reference `Proposal` carries. Never a value.
    subject: str
    #: The signal kinds that prompted it, sorted. No conversation, no message, no principal.
    evidence: tuple[Signal, ...]
    #: What it is worth now, after decay, as `formation.may_recall` computed it.
    confidence: float
    #: Where this reader reaches it, which is at most where it was formed.
    scope: Scope
    learned_at: datetime
    #: What pressing the control would write. `SUPERSEDED` when there is a previous memory to
    #: restore, `DEMOTED` when there is not. A `Correction` rather than a sentence, so a
    #: renderer can say which of the two will happen, and so the one thing this field cannot
    #: express is a removal: `Correction` has two members and deliberately no third.
    control_writes: Correction


@dataclass(frozen=True)
class WeeklyDigest:
    """One week of learning, for one reader, and the window it covers.

    `covers_from` and `covers_to` are here so the email can say which week it is about. They
    are the only two numbers on this shape and neither is a count: a reader who knows the
    window learns nothing about what was withheld inside it.
    """

    reader_id: str
    covers_from: datetime
    covers_to: datetime
    entries: tuple[MemoryItem, ...]


@dataclass(frozen=True)
class Undo:
    """What one click produced: a correction to write, or nothing, and why.

    `correction` is `None` when the click was a no-op, which is the ordinary outcome of a
    second click and of a late one. A no-op is a result rather than an error, because the
    person did nothing wrong and there is nothing for them to fix.

    There is no field here meaning removed, deleted or purged, and `correction.Correction`
    has no member for one either, so an undo that removed something is not a value away.
    """

    memory_id: str
    correction: Supersession | Demotion | None
    reason: str

    @property
    def took_effect(self) -> bool:
        """Whether this click wrote anything. False on a repeat and on a late click."""
        return self.correction is not None


def evidence_from(observations: Iterable[Observation]) -> frozenset[Signal]:
    """The evidence a listing may show, from the observations that prompted a learning.

    Keeps the signal kind and drops everything else: the conversation id, the message id, the
    principal it happened for and the time it happened. Those four are what make an
    `Observation` followable, and following it is a thing to do in the audit view, which
    filters per reader, rather than in a listing rendered for whoever opened a tab. See
    `EVIDENCE_NAMES_WHAT_WAS_NOTICED_AND_NEVER_WHOSE_CONVERSATION_IT_WAS`.

    A set, so four re-asks are one piece of evidence that answers were re-asked rather than a
    count of how many times somebody had to ask again.
    """
    return frozenset(one.signal for one in observations)


def may_digest(learning: Learning) -> bool:
    """Whether this learning belongs in an email with an undo button beside it.

    Two refusals on independent grounds, in this order.

    The first reads `CHANGES_WHAT_ANYBODY_MAY_SEE`, which is a list somebody has to edit on
    purpose, and it holds whatever `BLAST_RADIUS` says. That ordering is the point: if a row
    in the map were lowered by accident, the tier check alone would let a capability addition
    into a weekly email, and the map is the thing most likely to be edited in a hurry.

    The second reads the tier, which covers everything the first does not: a session learning
    nobody is told about, and any tier added above three.
    """
    if learning.proposal.change in CHANGES_WHAT_ANYBODY_MAY_SEE:
        return False
    return learning.proposal.tier in DIGEST_TIERS


def memory_item(learning: Learning, seen: Recollection) -> MemoryItem:
    """One listing row, from a learning and the terms this reader reaches it on.

    The confidence and the scope come from the `Recollection` rather than from the learning,
    which is what makes the row a statement about this reader: the confidence is after decay
    and the scope is at most where they reach it, never where it was formed.

    Public because `brain.memory.review` builds the same row for three other surfaces, and
    one builder is what stops four surfaces disagreeing about what a learning looks like.
    """
    return MemoryItem(
        memory_id=learning.memory_id,
        change=learning.proposal.change,
        tier=learning.proposal.tier,
        subject=learning.proposal.subject,
        evidence=tuple(sorted(learning.evidence)),
        confidence=seen.confidence,
        scope=seen.scope,
        learned_at=learning.formation.formed_at,
        control_writes=(
            Correction.SUPERSEDED if learning.replaced_id is not None else Correction.DEMOTED
        ),
    )


def weekly_digest(
    *,
    now: datetime,
    reader: EntitlementSet,
    learnings: Sequence[Learning],
    period: timedelta = DIGEST_PERIOD,
) -> WeeklyDigest:
    """What to tell one person the system learnt this week, at their own reach.

    Every learning goes through `formation.may_recall`, which is where `intersect`,
    `scope_for` and `Scope.matches` compose into the one definition of narrower this
    repository has. There is no second rule here and no shortcut for a reader who looks like
    an administrator: a digest is a disclosure and it is entitled like any other.

    The window is half open, `(now - period, now]`. A closed interval puts a learning formed
    exactly on the boundary into two consecutive emails, and the second one is an undo button
    for something the reader already decided about, which reads as the system having learnt
    it twice. Learnings from the future are outside the window rather than at the top of it:
    clock skew between a writer and a reader is ordinary, and a digest whose first entry has
    not happened yet is the strangest possible thing to hand somebody on a Monday.

    Newest first. A digest is read from the top and abandoned partway down, so the thing most
    likely to still be wrong goes where it will be read. The review queue in
    `brain.memory.review` sorts the other way for the opposite reason.

    Returns what may be shown and says nothing whatever about the rest: no total, no count,
    no "and others". See `A_COUNT_BESIDE_A_FILTERED_LISTING_IS_A_SUBTRACTION`.
    """
    since = now - period
    entries: list[MemoryItem] = []
    for learning in learnings:
        if not may_digest(learning):
            continue
        if not since < learning.formation.formed_at <= now:
            continue
        seen = may_recall(
            learning.formation,
            reader,
            now=now,
            formed_confidence=learning.formed_confidence,
        )
        if seen is None:
            continue
        entries.append(memory_item(learning, seen))

    return WeeklyDigest(
        reader_id=reader.principal_id,
        covers_from=since,
        covers_to=now,
        entries=tuple(
            sorted(entries, key=lambda one: (-one.learned_at.timestamp(), one.memory_id))
        ),
    )


def undo(
    learning: Learning,
    *,
    at: datetime,
    prompted_by: Signal = Signal.REJECTED,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
) -> Undo:
    """What one click of undo, or of delete, means.

    A mark and never a removal. Which mark depends on whether there is anything to restore:

    - The learning replaced an earlier memory, so undoing it means putting the earlier one
      back. That is a `Supersession` of the new memory *by* the old one, which is the same
      shape and the same table an ordinary correction uses, read in the other direction.
    - The learning replaced nothing, so there is nothing to restore and the honest correction
      is a `Demotion`: the memory goes to zero confidence at once and is flagged. A person
      saying the system should not have learnt something is the authority `Demotion` is for,
      and `THE_SOURCE_DOES_NOT_WAIT_FOR_A_THRESHOLD` is why it takes effect immediately
      rather than being scored down and waiting for a decay curve. `Demotion` needs a field
      name, and the only thing a learning knows about itself is `Proposal.subject`, which is
      an opaque reference rather than a value; that is what goes there.

    Idempotent, and idempotent in the sharp sense. A memory already marked either way is left
    alone and the click reports that it did nothing. The correction that marked it is never
    read, never reversed and never named in the result, so undoing the first thing cannot
    reach the second. See `AN_UNDO_CLICKED_LATE_MUST_NOT_UNDO_THE_SECOND_THING`.

    `prompted_by` defaults to `Signal.REJECTED`, which is the signal for an approval refused:
    a person pressing undo is refusing a learning, and recording it as anything else would
    put a human decision into the evidence pile as though the system had noticed it itself.

    Writes nothing. The correction is returned for whoever owns the table, which is the same
    split `limits.check` keeps: a policy module that stored its own answer could not be
    tested for the case that matters, which here is the second click.
    """
    if learning.memory_id in corrected(supersessions, demotions):
        return Undo(
            memory_id=learning.memory_id,
            correction=None,
            reason=(
                "this memory has already been marked, so there is nothing to undo; the "
                "correction that marked it is left exactly as it is"
            ),
        )
    if learning.replaced_id is not None:
        return Undo(
            memory_id=learning.memory_id,
            correction=Supersession(
                superseded_id=learning.memory_id,
                by_id=learning.replaced_id,
                prompted_by=prompted_by,
                at=at,
            ),
            reason="the memory this learning replaced is restored and this one is marked",
        )
    return Undo(
        memory_id=learning.memory_id,
        correction=Demotion(memory_id=learning.memory_id, field=learning.proposal.subject, at=at),
        reason="nothing preceded this learning, so it is marked and stops being recalled",
    )


def digest_gaps() -> tuple[str, ...]:
    """Everything about this module that would put the wrong thing in front of a person.

    Four checks, and the first is the one worth having: it reads
    `CHANGES_WHAT_ANYBODY_MAY_SEE` against `blast_radius`, which is the pairing that would
    let an access-changing learning into an email if a row in the map were edited. The others
    pin the tier boundary, the period against the decay curve that makes a week defensible,
    and the absence of a count on any shape a renderer will read.
    """
    gaps: list[str] = []

    for change in sorted(CHANGES_WHAT_ANYBODY_MAY_SEE, key=lambda one: one.value):
        if blast_radius(change) in DIGEST_TIERS:
            gaps.append(
                f"{change.value} changes who may see what and its blast radius puts it in a "
                "weekly email, where approving a widening is one button away from undoing a "
                "preference"
            )

    if Tier.GATED in DIGEST_TIERS or Tier.SESSION in DIGEST_TIERS:
        gaps.append(
            "the digest tiers include the gate or the session, so an email either asks a "
            "person to decide something it cannot carry, or reports a change confined to a "
            "conversation they are already having"
        )

    if confidence_now(1.0, formed_at=_ANY_INSTANT, now=_ANY_INSTANT + DIGEST_PERIOD) < RECALL_FLOOR:
        gaps.append(
            "a memory formed at the start of one digest period is below the retrieval floor "
            "by the end of it, so the digest reports learnings that have already stopped "
            "being recalled and the undo button changes nothing"
        )

    for model in (MemoryItem, WeeklyDigest, Undo, Learning):
        for one in fields(model):
            if one.name in COUNTING_FIELD_NAMES:
                gaps.append(
                    f"{model.__name__} carries {one.name}, which beside a filtered listing "
                    "is the number of things the reader may not see"
                )

    return tuple(gaps)
