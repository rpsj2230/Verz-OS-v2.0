"""Why the accumulated learning does not come across, and what is done instead.

The platform being left behind has one switch for learning and an opaque store behind it.
This system has four tiers, a blast radius per kind of change and a review queue for the ones
that change who may see what. **There is no honest mapping between the two**, and the
dishonest one is easy to write: read their store, write ours, and the whole of it lands at
whatever tier the importer picked.

So there is no import function in this module and there is not meant to be one. A foreign
memory is **evidence**, a person reads it, and what they conclude goes through
`brain.memory.tiers.propose` like anything else. The tier is then not the migrator's to
choose, which is the property that survives whoever wrote the migration.

**Only tier one comes back, and the three tiers that do not are each refused for a different
reason.** Session context is a fact about one conversation that ended on another system, so
there is nothing to carry. Tier two is promoted once enough independent occurrences agree,
and re-derivations out of one old store are not independent: derive four preferences from one
memory file and the promotion machinery sees four agreeing signals where there is one. Tier
three changes who may see what and was never approved by anybody under these rules, which is
the whole of M37.2.4.3. The gated set is read from `brain.memory.tiers` rather than restated
here, so a change becoming gated later is refused here on the same day. See
`RE_DERIVED_MEMORIES_ARE_NOT_INDEPENDENT_OCCURRENCES` and
`NOBODY_HERE_APPROVED_ANYTHING_ON_THE_OLD_SYSTEM`.

**A derivation names the file and the person.** Both, because the file is what makes it
evidence rather than a belief, and the person is who somebody asks about it in six months.
"Re-derived by the team" is not a fact anybody can check.

**The handover says the system starts without their learning, and says it plainly.** That is
M37.2.4.4 and the temptation is to soften it, because it reads as a loss. It is a loss, and it
is the right trade: what was lost was a store nobody could inspect, and what replaces it is a
tier ladder where the changes that matter are decided by a person. `learning_note` renders the
sentence with figures derived from the derivations rather than typed, so a note claiming more
than was re-derived cannot be written, and it names every person who derived something,
because a note that says how many were derived and not by whom is a note nobody can follow up.

What was rejected. A `confidence` on a foreign memory, so a strongly held old belief could
skip the review queue. `brain.memory.tiers.blast_radius` has no parameter for confidence and
its docstring says why: the tier comes from what a change reaches, not from how sure anybody
is. A confidence here would be that parameter arriving by another route.

Task ids: M37.2.4.1, M37.2.4.2, M37.2.4.3, M37.2.4.4
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.memory.tiers import (
    BLAST_RADIUS,
    CHANGES_WHAT_ANYBODY_MAY_SEE,
    Change,
    Proposal,
    Tier,
    propose,
)
from brain.migration.inventory import MigrationError


class LearningError(MigrationError):
    """Raised when accumulated learning would be carried across rather than re-derived."""


# ------------------------------------------------------------------ written-down reasons
#: Why there is no function here that converts a foreign memory into a learning.
ONE_SWITCH_AND_FOUR_TIERS_HAVE_NO_HONEST_MAPPING: Final = (
    "The old platform has one switch for learning and an opaque store behind it. This system "
    "has four tiers, a blast radius per kind of change and a review queue for the ones that "
    "change who may see what. There is no mapping between them, and the one somebody writes "
    "anyway lands the whole store at whatever tier the importer picked. A foreign memory is "
    "evidence a person reads, and what they conclude is proposed the ordinary way."
)

#: Why a re-derived memory may not produce a tier-two change.
RE_DERIVED_MEMORIES_ARE_NOT_INDEPENDENT_OCCURRENCES: Final = (
    "Tier two is promoted once enough independent occurrences agree, and everything here "
    "comes out of one store that one platform wrote. Derive four preferences from one memory "
    "file and the promotion machinery sees four agreeing signals where there is one, which "
    "is a promotion built on a single source wearing the shape of corroboration."
)

#: Why a re-derived memory may not produce a gated change.
NOBODY_HERE_APPROVED_ANYTHING_ON_THE_OLD_SYSTEM: Final = (
    "A change that alters who may see what is decided by a person under these rules, and "
    "nothing on the old platform was. Carried across it is an access decision taken by "
    "whoever configured a system the company is leaving, applied to a system with a review "
    "queue that never saw it. The gated set is read from brain.memory.tiers rather than "
    "listed again here, so a change that becomes gated later is refused here the same day."
)

#: The sentence the handover carries, and the reason it is not softened.
THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING: Final = (
    "This system starts without the learning the previous one accumulated. That is a loss "
    "and it is the right trade: what is lost is a store nobody could inspect, and what "
    "replaces it is a ladder where a change that alters who may see what is decided by a "
    "person. What was carried across was re-derived by hand from the old memory files, one "
    "preference at a time, and each one names the file it came from and who read it."
)


@dataclass(frozen=True)
class ForeignMemory:
    """One memory file from the old platform, as evidence and never as a belief.

    `text` is what the file said. Nothing here reads it: it is carried so a person can, and so
    a derivation can name the file it came from.
    """

    source_file: str
    text: str
    written_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.source_file.strip():
            msg = "a foreign memory names no file, so no derivation from it can be checked"
            raise LearningError(msg)
        if not self.text.strip():
            msg = f"{self.source_file!r} holds nothing to read"
            raise LearningError(msg)


@dataclass(frozen=True)
class Derivation:
    """One thing a person concluded from one old memory file, proposed the ordinary way.

    The proposal is built by `re_derive` rather than passed in, so its tier comes from
    `brain.memory.tiers.blast_radius` and not from whoever is running the migration.
    """

    proposal: Proposal
    source_file: str
    derived_by: str
    because: str

    def __post_init__(self) -> None:
        if not self.derived_by.strip():
            msg = (
                f"the derivation from {self.source_file!r} names nobody, and 're-derived by "
                "the team' is not a fact anybody can check"
            )
            raise LearningError(msg)
        if not self.because.strip():
            msg = f"the derivation from {self.source_file!r} records no reasoning"
            raise LearningError(msg)


def re_derive(
    memory: ForeignMemory,
    *,
    change: Change,
    subject: str,
    derived_by: str,
    because: str,
) -> Derivation:
    """One tier-one conclusion drawn from one old memory file (M37.2.4.2).

    Three refusals with three different arguments, and each names its own reason constant.
    Session context is a fact about a conversation that ended on another system. Tier two is
    promoted on independent occurrences and these are not independent. Tier three was never
    approved by anybody under these rules.
    """
    tier = BLAST_RADIUS.get(change)
    if tier is None:
        # `change!r` rather than `change.value`, because the one caller that reaches this
        # branch is passing something that is not a member at all: a declared member with
        # no entry is refused by an invariant long before here.
        msg = f"{change!r} has no blast radius, so nothing can say what it would take"
        raise LearningError(msg)
    if change in CHANGES_WHAT_ANYBODY_MAY_SEE:
        msg = (
            f"{change.value} changes who may see what. "
            f"{NOBODY_HERE_APPROVED_ANYTHING_ON_THE_OLD_SYSTEM}"
        )
        raise LearningError(msg)
    if tier is Tier.PROMOTED:
        msg = (
            f"{change.value} is promoted rather than proposed. "
            f"{RE_DERIVED_MEMORIES_ARE_NOT_INDEPENDENT_OCCURRENCES}"
        )
        raise LearningError(msg)
    if tier is Tier.SESSION:
        msg = (
            f"{change.value} is true of one conversation, and the conversation it was true of "
            "ended on another system"
        )
        raise LearningError(msg)
    return Derivation(
        proposal=propose(change, subject=subject),
        source_file=memory.source_file,
        derived_by=derived_by,
        because=because,
    )


def derived_twice(derivations: Sequence[Derivation]) -> tuple[str, ...]:
    """Old memory files two people drew conclusions from, sorted.

    Not an error and not silent. Two readings of one file are two opinions about it, which is
    worth having, and they are not two occurrences of anything, which is worth saying before
    somebody counts them.
    """
    counted: dict[str, set[str]] = {}
    for one in derivations:
        counted.setdefault(one.source_file, set()).add(one.derived_by)
    return tuple(
        f"{source}: read by {' and '.join(sorted(readers))}, which is two opinions and not "
        "two occurrences"
        for source, readers in sorted(counted.items())
        if len(readers) > 1
    )


@dataclass(frozen=True)
class LearningNote:
    """What the handover says about the learning that did not come across (M37.2.4.4)."""

    sentence: str
    derived: int
    files_read: int
    readers: tuple[str, ...]


def learning_note(
    derivations: Sequence[Derivation], memories: Sequence[ForeignMemory]
) -> LearningNote:
    """The handover paragraph, with every figure read off the work rather than typed.

    A note claiming more than was re-derived cannot be written, because there is no parameter
    for a count. The readers are named because a note saying how many preferences were derived
    and not by whom is a note nobody can follow up.
    """
    read = {one.source_file for one in derivations}
    unknown = read - {one.source_file for one in memories}
    if unknown:
        msg = (
            f"derivations name {sorted(unknown)}, which are not among the memory files handed "
            "over, so the note would count a file nobody exported"
        )
        raise LearningError(msg)
    return LearningNote(
        sentence=THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING,
        derived=len(derivations),
        files_read=len(read),
        readers=tuple(sorted({one.derived_by for one in derivations})),
    )
