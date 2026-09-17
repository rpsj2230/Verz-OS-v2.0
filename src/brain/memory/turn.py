"""What an answered conversation turn proposes to remember, under the rules memory already has.

`brain.memory.formation` says what a memory must carry and when it may be recalled, `brain.memory.
recall` says which memories a correction has taken out of recall, and `brain.ops.memory_store`
writes a memory with its learning record. Nothing proposed a memory from a conversation. This module
is that proposal, and `brain.ops.memory_store.StoredFormations.after_turn` is the step that reads
what the person already has, asks this module, and writes the answer.

**Only the person's own words, and only after an answered turn.** A memory is formed from what the
person said and never from what the system answered: the answer carries values read at a reach, and
a memory of them would be a second copy of a record under the memory's permissions rather than the
record's, which `MEMORY_IS_A_HINT_AND_THE_SOURCE_IS_THE_ANSWER` refuses. A turn the lane abstained
on, refused or faulted forms nothing, because the words beside a refusal are the words of somebody
who was not helped, and remembering them teaches the system the question rather than the person. See
`A_MEMORY_IS_FORMED_FROM_WHAT_THE_PERSON_SAID`.

**Stated and extracted are two kinds with two lifetimes, and the words decide which.** A person
saying "remember that I work from the Penang office on Fridays" has stated something, which is a
`MemoryKind.PERSISTENT` memory at full confidence that stays until it is contradicted. A person
saying "I prefer short answers" in the middle of a question has not asked for anything to be kept,
and what the system takes from it is an inference: `MemoryKind.ADAPTIVE`, at `EXTRACTED_CONFIDENCE`,
decaying on `formation`'s curve. Rejected: a model reading the turn for anything memorable. It would
be a classifier deciding what may be kept, and nothing here could say why it chose what it chose.

**Only what is about the person.** A statement with no first-person word in it is a claim about the
company or somebody else, which `brain.memory.tiers` classifies as company knowledge at the gated
tier, and this module has nowhere to approve one. So it forms nothing and says why, and the change
proposed for everything it does form is `Change.PREFERENCE`, which is tier one. See
`A_FACT_ABOUT_THE_COMPANY_IS_NOT_A_PERSONS_MEMORY`.

**Formed in the person's own scope and at the reach the turn was answered at.** The formation's
scope is one clause naming the person, so `recall_place` for anybody else never matches it, whatever
they hold. Its capabilities are the ones the turn's reach held, with any a held wildcard covers
dropped: a memory of something said while reaching a client record is recalled only by a reach that
still covers it, which is `formation.may_recall`'s rule and M16.4.4's expiry. A reach naming more
than `brain.tables.memory.MAX_CAPABILITY_TAGS` forms nothing rather than a requirement cut to fit,
because a requirement cut to fit is a narrower requirement than the one the words were said under.

**Corrections are honoured through `brain.memory.recall.standing`.** A statement the person already
has standing is not formed twice. One whose memory a correction took out of recall is not inferred
again: an undo is the person's last word about it, and re-extracting it from the next conversation
would undo the undo. Stating it again is the person speaking, so a stated memory is formed even so.
See `A_CORRECTION_OUTRANKS_THE_NEXT_INFERENCE_AND_NOT_THE_NEXT_STATEMENT`.

**Where the answer lane calls it.** After `brain.gate.answer.answer_lane` returns, outside it, as
`brain.api_routes`' ask route has the question and the caller's reach and the lane does not keep
either: build a `Turn` from the route's question, `origin` and `asked.reach` with
`answered=is_answered(outcome)`, and hand it to `StoredFormations.after_turn` once the response is
written, so forming a memory never delays an answer and a failure to form one never fails it.

Task ids: M16.1.2, M16.1.3, M38.2.2.4
"""

from __future__ import annotations

import enum
import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.scope import Scope
from brain.gate.answer import Answered
from brain.memory.correction import Demotion, Supersession
from brain.memory.digest import Learning
from brain.memory.formation import (
    RECALL_FLOOR,
    Formation,
    MemoryKind,
    clause_place,
)
from brain.memory.recall import standing
from brain.memory.tiers import Change, propose

# ------------------------------------------------------------------ written-down reasons
#: Why a memory is formed from the person's words and never from the answer.
A_MEMORY_IS_FORMED_FROM_WHAT_THE_PERSON_SAID: Final = (
    "A memory is formed from what the person said in an answered turn, and never from what was "
    "answered. An answer carries values read at a reach, and a memory of them would be a copy of "
    "a record under the memory's permissions rather than the record's. A turn that was refused, "
    "abstained on or failed forms nothing."
)

#: Why a claim about anything but the person forms nothing here.
A_FACT_ABOUT_THE_COMPANY_IS_NOT_A_PERSONS_MEMORY: Final = (
    "A statement with nothing in it about the person is a claim about the company or about "
    "somebody else, which is company knowledge at the gated tier, and a person has to decide it. "
    "Nothing here can approve one, so it forms nothing rather than keeping it as a preference."
)

#: Why an undo stops the next inference and not the next statement.
A_CORRECTION_OUTRANKS_THE_NEXT_INFERENCE_AND_NOT_THE_NEXT_STATEMENT: Final = (
    "A memory a correction took out of recall is the person's last word about it, so the same "
    "thing inferred from the next conversation is not formed again. The person stating it again "
    "is a newer word from the same person, so a stated memory is formed whatever was corrected."
)

#: What an extracted memory is worth when formed. Above the recall floor, so it is recalled at
#: once, and below certain, so it decays under the floor in a few weeks with nothing reinforcing
#: it; `test_memory_turn.py` holds both against `RECALL_FLOOR` and `STATED_CONFIDENCE`.
EXTRACTED_CONFIDENCE: Final = 0.6

#: What a stated memory is worth: what the person said, at full confidence.
STATED_CONFIDENCE: Final = 1.0

#: How much of a sentence may become a statement. A preference or a fact about a person is a
#: sentence; anything longer is a paragraph somebody pasted, and a memory is not a paste buffer.
MAX_STATEMENT_CHARS: Final = 280

#: How a memory id is made: a letter and 25 hex characters, the 26 `mem.persistent.id` holds.
MEMORY_ID_PREFIX: Final = "m"
MEMORY_ID_DIGEST_CHARS: Final = 25

#: The largest requirement a formation may carry. `brain.tables.memory.MAX_CAPABILITY_TAGS`,
#: restated because that module is a table and this one is the domain; a test holds them equal.
MAX_CAPABILITY_TAGS: Final = 32

#: How a stated memory opens. Lower-case, matched at the start of a sentence.
STATED_OPENERS: Final[tuple[str, ...]] = (
    "please remember that ",
    "please remember ",
    "remember that ",
    "remember: ",
    "note that ",
    "for future reference, ",
)

#: How a preference the system may infer opens. Each is somebody saying how they want to be
#: answered, which is `Change.PREFERENCE`'s own description.
EXTRACTED_OPENERS: Final[tuple[str, ...]] = (
    "i prefer ",
    "i'd prefer ",
    "i would prefer ",
    "i'd rather ",
    "i would rather ",
    "please always ",
    "please never ",
    "from now on ",
)

#: The words that make a statement about the person. Whole words, lower-cased.
FIRST_PERSON: Final[frozenset[str]] = frozenset(
    {"i", "i'm", "i'd", "i've", "i'll", "me", "my", "mine"}
)

_SENTENCE_RE: Final = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE: Final = re.compile(r"[a-z']+")


class NotFormed(enum.StrEnum):
    """Why a turn formed nothing, or why one sentence of it did not. Closed."""

    NOT_ANSWERED = "not_answered"
    NOTHING_TO_REMEMBER = "nothing_to_remember"
    NOT_ABOUT_THE_PERSON = "not_about_the_person"
    NO_REACH = "no_reach"
    REACH_TOO_WIDE_TO_TAG = "reach_too_wide_to_tag"
    ALREADY_REMEMBERED = "already_remembered"
    CORRECTED = "corrected"


class TurnError(ValueError):
    """A turn was described in a shape nothing should be formed from."""


@dataclass(frozen=True)
class Turn:
    """One answered or unanswered turn: who said what, at which reach, under which trace.

    `said` is the person's own words as they typed them, and nothing the system produced. `reach`
    is the reach the turn was answered at, which is the caller's run reach, and belongs to the
    person: a turn handed another principal's reach is refused.
    """

    trace_id: str
    principal_id: str
    said: str
    answered: bool
    reach: EntitlementSet
    at: datetime
    agent_id: str | None = None

    def __post_init__(self) -> None:
        if not self.trace_id.strip() or not self.principal_id.strip():
            msg = "a turn with no trace or no person cannot be told apart from another"
            raise TurnError(msg)
        if self.reach.principal_id != self.principal_id:
            msg = (
                f"a turn by {self.principal_id!r} was handed the reach of "
                f"{self.reach.principal_id!r}, and a memory formed at it would be formed at "
                "somebody else's"
            )
            raise TurnError(msg)
        if self.at.tzinfo is None:
            msg = "a naive instant forms a memory whose decay starts at the wrong time"
            raise TurnError(msg)


def is_answered(outcome: Answered) -> bool:
    """Whether the lane answered: no abstention, which covers every refusal and every nothing."""
    return outcome.abstention is None


@dataclass(frozen=True)
class Held:
    """One memory the person already has: its id, its kind, and the statement it keeps."""

    memory_id: str
    kind: MemoryKind
    statement: str


@dataclass(frozen=True)
class Proposed:
    """One memory to write: the learning, which carries the formation, and its statement."""

    learning: Learning
    statement: str


@dataclass(frozen=True)
class Proposals:
    """What a turn proposes, and why each sentence that proposed nothing did not. No counts."""

    formed: tuple[Proposed, ...]
    skipped: tuple[NotFormed, ...]


# ------------------------------------------------------------------ the words
def sentences(said: str) -> tuple[str, ...]:
    """The turn split into sentences, trimmed, with empty ones dropped."""
    return tuple(one.strip() for one in _SENTENCE_RE.split(said) if one.strip())


def key_of(statement: str) -> str:
    """What two statements share when they say the same thing: the words, lower-cased, in order."""
    return " ".join(_WORD_RE.findall(statement.lower()))


def about_the_person(statement: str) -> bool:
    """Whether a statement has a first-person word in it."""
    return bool(set(_WORD_RE.findall(statement.lower())) & FIRST_PERSON)


def candidate(sentence: str) -> tuple[MemoryKind, str] | None:
    """The kind and the statement one sentence would form, or None when it asks for nothing.

    A stated opener is removed and the rest kept; an extracted one is kept whole, because "I prefer
    short answers" is the statement and "short answers" is not. Trailing punctuation goes, and a
    statement longer than `MAX_STATEMENT_CHARS` is not a memory.
    """
    lowered = sentence.lower()
    for opener in STATED_OPENERS:
        if lowered.startswith(opener):
            kept = sentence[len(opener) :].strip().rstrip(".!?").strip()
            return _bounded(MemoryKind.PERSISTENT, kept)
    for opener in EXTRACTED_OPENERS:
        if lowered.startswith(opener):
            return _bounded(MemoryKind.ADAPTIVE, sentence.strip().rstrip(".!?").strip())
    return None


def _bounded(kind: MemoryKind, statement: str) -> tuple[MemoryKind, str] | None:
    if not key_of(statement) or len(statement) > MAX_STATEMENT_CHARS:
        return None
    return kind, statement


# ------------------------------------------------------------------ the formation
def requirement_of(reach: EntitlementSet, now: datetime) -> tuple[Capability, ...] | None:
    """The capabilities a memory formed at this reach carries, or None when there is no honest set.

    Every capability the reach holds at `now`, less any another held one covers, sorted. None for
    a reach holding nothing and for one naming more than `MAX_CAPABILITY_TAGS`.
    """
    held = sorted(
        {grant.capability.value for grant in reach.grants if reach.holds(grant.capability, now)}
    )
    capabilities = [Capability(value=one) for one in held]
    kept = tuple(
        one
        for one in capabilities
        if not any(other != one and other.covers(one) for other in capabilities)
    )
    if not kept or len(kept) > MAX_CAPABILITY_TAGS:
        return None
    return kept


def own_scope(principal_id: str) -> Scope:
    """The scope a person's own memory is formed in: one clause naming them."""
    return clause_place(principal_id=principal_id)


def recall_place(principal_id: str, department: str | None = None) -> dict[str, object]:
    """Where a recall for this reader happens, for the lane to hand `recall.recall` as `where`.

    The reader's own id, so a memory formed in somebody else's scope never matches, and their
    department when they have one, so a reader whose grants are scoped to it still recalls their
    own: `formation.may_recall` matches the place against both scopes conjoined.
    """
    place: dict[str, object] = {"principal_id": principal_id}
    if department:
        place["department"] = department
    return place


def memory_id(turn: Turn, kind: MemoryKind, statement: str) -> str:
    """A memory's id, derived from the turn, the kind and the statement and never minted.

    A turn handed to formation twice therefore proposes the same ids, and the second finds the
    first already standing.
    """
    source = f"{turn.principal_id}\n{turn.trace_id}\n{kind.value}\n{key_of(statement)}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"{MEMORY_ID_PREFIX}{digest[:MEMORY_ID_DIGEST_CHARS]}"


def propose_memories(
    turn: Turn,
    held: Sequence[Held],
    *,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
) -> Proposals:
    """What this turn proposes to remember, given what the person already has.

    `held` is every memory of this person's, corrected or not, with its statement; the corrections
    are every one naming them. Which of those still stand is `recall.standing`'s answer, asked once.
    """
    if not turn.answered:
        return Proposals(formed=(), skipped=(NotFormed.NOT_ANSWERED,))
    found = [one for one in map(candidate, sentences(turn.said)) if one is not None]
    if not found:
        return Proposals(formed=(), skipped=(NotFormed.NOTHING_TO_REMEMBER,))
    capabilities = requirement_of(turn.reach, turn.at)
    if capabilities is None:
        reason = NotFormed.NO_REACH if not turn.reach.grants else NotFormed.REACH_TOO_WIDE_TO_TAG
        return Proposals(formed=(), skipped=(reason,))

    still = {
        one.memory_id
        for one in standing(held, _held_id, supersessions=supersessions, demotions=demotions)
    }
    standing_keys = {key_of(one.statement) for one in held if one.memory_id in still}
    corrected_keys = {key_of(one.statement) for one in held if one.memory_id not in still}

    formed: list[Proposed] = []
    skipped: list[NotFormed] = []
    seen: set[str] = set()
    for kind, statement in found:
        key = key_of(statement)
        if not about_the_person(statement):
            skipped.append(NotFormed.NOT_ABOUT_THE_PERSON)
            continue
        if key in standing_keys or key in seen:
            skipped.append(NotFormed.ALREADY_REMEMBERED)
            continue
        if kind is MemoryKind.ADAPTIVE and key in corrected_keys:
            skipped.append(NotFormed.CORRECTED)
            continue
        seen.add(key)
        made = memory_id(turn, kind, statement)
        formed.append(
            Proposed(
                learning=Learning(
                    memory_id=made,
                    proposal=propose(Change.PREFERENCE, subject=f"memory:{made}"),
                    formation=Formation(
                        principal_id=turn.principal_id,
                        capabilities=capabilities,
                        scope=own_scope(turn.principal_id),
                        ent_hash=turn.reach.ent_hash(),
                        formed_at=turn.at,
                        kind=kind,
                    ),
                    formed_confidence=(
                        STATED_CONFIDENCE if kind is MemoryKind.PERSISTENT else EXTRACTED_CONFIDENCE
                    ),
                    agent_id=turn.agent_id,
                ),
                statement=statement,
            )
        )
    return Proposals(formed=tuple(formed), skipped=tuple(skipped))


def _held_id(one: Held) -> str:
    return one.memory_id


#: The floor, re-read here so the confidence argument has its figure beside it.
FLOOR: Final = RECALL_FLOOR
