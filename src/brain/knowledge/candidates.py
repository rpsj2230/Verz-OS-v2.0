"""A person who corrects an answer may say what the right answer is, and it changes nothing until
somebody who may replace the document approves it (M16.6.5, M16.6.6, M16.7.6).

`brain.chat.turns.Correction` refuses to keep what a person says the right answer is, and its
argument is about where those words would go: straight into the knowledge base, with no review, no
scope and no provenance. This is the review, the scope and the provenance. The words are held in
`know.learning_candidate`, never on the correction, they are in no search, no recall and no
prompt, and they become part of a document only when a person approves them as a new version of
it. See `A_CORRECTION_S_WORDS_CHANGE_NOTHING_UNTIL_SOMEBODY_APPROVES_THEM`.

**The candidate is about the document the corrected answer cited, and nothing the person typed
names it.** Which document is taken from the answer's own references, the first knowledge passage
it cited, so a person cannot point their words at a document of their choosing. An answer that
cited no document forms no candidate, because there is nothing a person could approve the words
into.

**Decided as a new version is decided, by the same function.** A correction's words become a new
version of the document, and who may add a new version of a document today is
`brain.knowledge.lifecycle.Authority.may_act`: its steward while they can read it, or whoever holds
`admin:knowledge` where it sits. `may_decide` calls it and adds one refusal, below, so a correction
is reviewed exactly as an ordinary edit would be and there is no second rule about who may. It is
offered as a steward task and reviewed on its own route, the way `brain.knowledge.solutions` is,
and not on the Approvals screen, which offers a card to holders of one capability and cannot say
"the steward". See `A_CORRECTION_IS_DECIDED_BY_WHOEVER_MAY_ADD_A_NEW_VERSION`.

**Nobody whose correction it holds may approve it.** The person whose evidence opened a candidate,
and anybody whose correction grew it, is refused, here and by the database, which reads the
evidence through a function the application cannot widen. See
`NOBODY_WHOSE_CORRECTION_IT_HOLDS_MAY_APPROVE_IT`.

**Approved words are read by everybody who reads the document.** A person may have read more than
the document's audience when they wrote them, and could carry something from their wider reach
into it. The reviewer is the guard, so the review shows who will read the words in plain terms
beside them. See `APPROVED_WORDS_ARE_READ_BY_EVERYONE_WHO_READS_THE_DOCUMENT`.

**The same fix is one candidate, with every instance as its evidence.** Two people correcting the
same document's answer to the same words open one candidate and add one piece of evidence each,
keyed by the document and the words' key, `words_key`. A correction of one answer is one
piece of evidence ever, so a rejected candidate is not proposed again from the evidence that
proposed it. See `THE_SAME_FIX_IS_ONE_CANDIDATE_WITH_EVERY_INSTANCE`.

Rejected: raising the candidate on the Approvals screen as a suspended action, as a promotion is.
That screen's offer is a capability in a scope, which a steward who holds no administration grant
does not have, so a correction would be decided by a different set of people than an edit is.

Rejected: rewriting the document's text with the correction. A machine edit inside somebody's
document cannot be reviewed as a diff by its reader, and is wrong whenever the words are an
addition rather than a replacement. The new version keeps every passage of the old one as it was
and adds the correction as a passage of its own, under its own heading.

Task ids: M16.6.5, M16.6.6, M16.7.6
"""

from __future__ import annotations

import enum
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.knowledge.chunking import Block, BlockKind
from brain.knowledge.lifecycle import Authority, StoredItem
from brain.knowledge.search import TITLE_CHARS
from brain.knowledge.text_path import BLOCK_SEPARATOR
from brain.knowledge.visibility import KnowledgeVisibility, Visibility

# ------------------------------------------------------------------ written-down reasons
#: Why a correction's words are held apart and reach nothing until approved.
A_CORRECTION_S_WORDS_CHANGE_NOTHING_UNTIL_SOMEBODY_APPROVES_THEM: Final = (
    "What a person says the right answer is goes into know.learning_candidate and nowhere else: "
    "no search, no recall, no prompt and no memory reads it, and no knowledge, rule or memory "
    "changes until a person who may add a new version of the cited document approves it. Only "
    "the people whose corrections it holds and the people who may decide it read the words."
)

#: Why the decider of a correction is the decider of a new version.
A_CORRECTION_IS_DECIDED_BY_WHOEVER_MAY_ADD_A_NEW_VERSION: Final = (
    "A correction's words become a new version of the document it corrects, so it is decided by "
    "lifecycle.Authority.may_act, the function POST .../versions asks: the document's steward "
    "while they can read it, or whoever holds admin:knowledge where it sits. One decider, called "
    "and not restated, so a correction is reviewed exactly as an ordinary edit would be."
)

#: The four-eyes rule.
NOBODY_WHOSE_CORRECTION_IT_HOLDS_MAY_APPROVE_IT: Final = (
    "The person whose correction opened a candidate, and anybody whose correction grew it, may "
    "not approve it: their word is what it already has. Refused here and by the database, which "
    "reads the evidence through a function the application role cannot widen."
)

#: Why the review names the audience in plain terms.
APPROVED_WORDS_ARE_READ_BY_EVERYONE_WHO_READS_THE_DOCUMENT: Final = (
    "Once approved, the words are a passage of the document and are read by everyone who reads "
    "it. The person who wrote them may have read more than that audience, and could carry "
    "something from their wider reach into a narrower document. The reviewer is the guard, so "
    "the review shows who will read the words, in plain terms, beside them."
)

#: Why the same fix is grouped and a rejection is final for its evidence.
THE_SAME_FIX_IS_ONE_CANDIDATE_WITH_EVERY_INSTANCE: Final = (
    "Corrections of the same document to the same words are one candidate, keyed by the "
    "document and the words' key, carrying each correction as evidence. A correction of one "
    "answer is evidence once and ever, so a rejected candidate is not proposed again from the "
    "evidence that proposed it, and a fresh correction is what can propose it again."
)

# ------------------------------------------------------------------ the figures
#: The most a person may say the right answer is. A correction, not a document.
WORDS_CHARS: Final = 2000

#: The most a rejection's reason may say.
REASON_CHARS: Final = 400

#: How a candidate's id and a group key are spelled.
CANDIDATE_ID_PREFIX: Final = "candidate."
CANDIDATE_DIGEST_CHARS: Final = 40
GROUP_KEY_CHARS: Final = 64

#: How the new version a candidate becomes is named.
VERSION_ID_PREFIX: Final = "corrected."

#: The heading the correction's passage is written under in the new version.
CORRECTION_HEADING: Final = "Correction"

# ------------------------------------------------------------------ the words
#: The one refusal every act on a candidate it may not act on gets, and every one that does not
#: exist, so a reviewer's route is not a way to ask which candidates exist.
NOT_DECIDABLE: Final = "that correction is not one you may decide"


class CandidateState(enum.StrEnum):
    """Where a candidate is. Held equal to `0198`'s check by a test."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CandidateError(Exception):
    """A candidate that would be unsafe or meaningless, said to its actor."""


class CandidateNotOffered(Exception):  # noqa: N818 - a refusal, named like the ones beside it
    """The one refusal: `NOT_DECIDABLE`."""


@dataclass(frozen=True)
class Candidate:
    """One candidate as `know.learning_candidate` holds it, and whose evidence it holds."""

    candidate_id: str
    item_id: str
    words: str
    raised_by: str
    raised_at: datetime
    proposers: frozenset[str]
    state: CandidateState = CandidateState.PENDING
    decided_by: str = ""
    decided_at: datetime | None = None
    reason: str = ""
    applied_item_id: str = ""

    def __post_init__(self) -> None:
        if not self.words.strip() or len(self.words) > WORDS_CHARS:
            msg = f"say what the right answer is, in at most {WORDS_CHARS} characters"
            raise CandidateError(msg)
        if self.raised_by not in self.proposers:
            msg = "a candidate's first correction is among its evidence"
            raise CandidateError(msg)
        if bool(self.decided_by) != (self.decided_at is not None):
            msg = "a decision is a person and a date, or it is nothing"
            raise CandidateError(msg)
        if bool(self.decided_by) == (self.state is CandidateState.PENDING):
            msg = f"a {self.state.value} candidate names {'a' if self.decided_by else 'no'} decider"
            raise CandidateError(msg)
        if self.decided_by in self.proposers:
            raise CandidateError(NOBODY_WHOSE_CORRECTION_IT_HOLDS_MAY_APPROVE_IT)
        if bool(self.applied_item_id) != (self.state is CandidateState.APPROVED):
            msg = "an approved candidate names the version it became, and nothing else does"
            raise CandidateError(msg)
        if bool(self.reason) != (self.state is CandidateState.REJECTED):
            msg = "a rejected candidate keeps its reason, and nothing else has one"
            raise CandidateError(msg)


#: The words of a fix, lower-cased, as `brain.memory.turn.key_of` reads a statement. Restated
#: rather than imported, because `brain.tables` reads this module and `brain.memory.turn` reads the
#: answer lane, and a test holds the two equal on the same sentences.
_WORD_RE: Final = re.compile(r"[a-z']+")


def words_key(words: str) -> str:
    """What two fixes share when they say the same thing: their words, lower-cased, in order."""
    return " ".join(_WORD_RE.findall(words.lower()))


def group_key(item_id: str, words: str) -> str:
    """What makes two corrections the same fix: the document, and the words' key."""
    joined = chr(10).join((item_id, words_key(words)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:GROUP_KEY_CHARS]


def candidate_id_for(item_id: str, words: str, *, at: datetime) -> str:
    """A candidate's id: a digest of the fix and when it was first proposed, never the words."""
    joined = chr(10).join((group_key(item_id, words), at.isoformat()))
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return CANDIDATE_ID_PREFIX + digest[:CANDIDATE_DIGEST_CHARS]


def may_decide(candidate: Candidate, item: StoredItem, by: Authority) -> bool:
    """Whether this person may approve or reject this candidate now.

    Waiting, about this live document, decided by `Authority.may_act` as a new version is, and
    holding no correction of theirs. See `A_CORRECTION_IS_DECIDED_BY_WHOEVER_MAY_ADD_A_NEW_VERSION`
    and `NOBODY_WHOSE_CORRECTION_IT_HOLDS_MAY_APPROVE_IT`.
    """
    return (
        candidate.state is CandidateState.PENDING
        and candidate.item_id == item.item_id
        and by.principal_id not in candidate.proposers
        and by.may_act(item)
    )


def audience(place: KnowledgeVisibility) -> str:
    """Who reads a document placed here, in plain terms. See
    `APPROVED_WORDS_ARE_READ_BY_EVERYONE_WHO_READS_THE_DOCUMENT`."""
    match place.level:
        case Visibility.COMPANY:
            return "Everyone in the company will see these words."
        case Visibility.DEPARTMENT:
            return f"Everyone in {place.department} will see these words."
        case Visibility.PERSONAL:
            return "Only the document's own steward will see these words."


def correction_block(words: str, *, start: int) -> Block:
    """The correction as a passage of its own, under its heading, at `start` in the new content."""
    return Block(
        kind=BlockKind.PROSE,
        text=f"{CORRECTION_HEADING}{chr(10)}{chr(10)}{words.strip()}",
        start=start,
        section=CORRECTION_HEADING,
    )


@dataclass(frozen=True)
class Passage:
    """One passage of the document being corrected: its text, and where it sat."""

    body: str
    section: str = ""
    page: int | None = None


def corrected_blocks(passages: Sequence[Passage], words: str) -> tuple[Block, ...]:
    """The new version's blocks: every passage of the old one, as it was, then the correction.

    Each at its own offset in the content `brain.knowledge.text_path.joined` makes of them, which
    is what `chunk_store.write_document` checks a citation span against.
    """
    blocks: list[Block] = []
    start = 0
    for one in passages:
        if not one.body:
            continue
        blocks.append(
            Block(
                kind=BlockKind.PROSE, text=one.body, start=start, page=one.page, section=one.section
            )
        )
        start += len(one.body) + len(BLOCK_SEPARATOR)
    blocks.append(correction_block(words, start=start))
    return tuple(blocks)


def version_id_for(candidate_id: str, predecessor_id: str) -> str:
    """The new version's id: the candidate and the version it corrects, so applying it twice names
    one document and the second write is refused by the table's key."""
    joined = chr(10).join((candidate_id, predecessor_id))
    return VERSION_ID_PREFIX + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:40]


def version_title(title: str) -> str:
    """The new version keeps the document's title."""
    return title[:TITLE_CHARS]
