"""What recall returns once the corrections are read, which is what makes an undo change an answer.

`brain.memory.formation.may_recall` decides whether one reader may be told one memory, from what it
was formed under and how much it has decayed. `brain.memory.correction` decides which memories have
been marked. Until 2026-09-17 nothing put the two together: `correction.corrected` was called by
`digest.undo` to decide whether an undo was a repeat, and by nothing that recalls. So a correction
written anywhere would have changed no recollection, and an undo on the Learning screen would have
been a row and a ledger entry beside a system that went on recalling exactly what it had.

**The corrections are read before reach, and a corrected memory is not recalled whoever asks.** A
correction is a fact about the memory and not about the reader: the source contradicted it, a person
refused it, or a newer memory replaced it. So `standing` removes every memory `correction.corrected`
names before `may_recall` is asked anything, and a reader who reaches everything is told the
corrected memory no more than a reader who reaches nothing. See
`A_CORRECTED_MEMORY_IS_NOT_RECALLED_WHOEVER_ASKS`.

**`standing` is the one place the two meet, and every reader of memory goes through it.** `recall`
here, and `brain.console.reach_view.split_memory`, which is what the Memory screen and a person's
own memory tab show as what the system remembers. Two filters would be two readings of which
memories an undo removed, and the one that forgot the demotions is the one a person would trust.

**Nothing here decides which corrections count.** A pair's latest word, a tie marking both, a
demotion taking effect at once: those are `correction.superseded_ids` and `correction.demoted_ids`,
reached through `correction.corrected`, and this module asks it rather than restating it.

**No count of what was corrected, and nothing that says a memory was withheld**, for
`formation.recallable`'s reason: a number beside a filtered list is the difference between what a
reader may see and what exists.

Task ids: M27.7.21
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from brain.core.entitlement import EntitlementSet
from brain.memory.correction import Demotion, Supersession, corrected
from brain.memory.formation import Formation, Recollection, may_recall

#: Why the corrections are read before anything about the reader.
A_CORRECTED_MEMORY_IS_NOT_RECALLED_WHOEVER_ASKS: Final = (
    "A correction is a fact about the memory: a newer memory replaced it, the source "
    "contradicted it, or a person refused it. None of those depends on who is asking, so a "
    "corrected memory is removed before may_recall is asked anything, and a reader who reaches "
    "everything is told it no more than a reader who reaches nothing. Asked in the other order "
    "the answer is the same, and the reason for it would be a fact about the reader rather than "
    "about the memory, which is the wrong thing to have to reason from when a recall is audited."
)


class Memory(Protocol):
    """The three facts recall reads about a memory. `brain.memory.digest.Learning` is one."""

    @property
    def memory_id(self) -> str: ...

    @property
    def formation(self) -> Formation: ...

    @property
    def formed_confidence(self) -> float: ...


@dataclass(frozen=True)
class Recalled:
    """One memory recall returned, by id, with the terms this reader has it on.

    The id is carried because `Recollection` has none, on purpose, and a caller holding a list of
    recollections could not say which memories an undo removed from it.
    """

    memory_id: str
    recollection: Recollection


def standing[T](
    memories: Iterable[T],
    memory_id: Callable[[T], str],
    *,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
) -> tuple[T, ...]:
    """Every memory no correction has marked, in the order given.

    Generic over what holds a memory, because the Memory screen hands in pairs of a memory and its
    statement and recall hands in memories alone, and one function is what keeps the two screens
    agreeing about which memories an undo removed. `memory_id` says where the id is.
    """
    marked = corrected(supersessions, demotions)
    return tuple(one for one in memories if memory_id(one) not in marked)


def recall(
    memories: Sequence[Memory],
    reader: EntitlementSet,
    *,
    now: datetime,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
    where: Mapping[str, object] | None = None,
) -> tuple[Recalled, ...]:
    """Every memory this reader may be told now, corrections read first, most confident first.

    `standing` removes what a correction marked, then `formation.may_recall` decides reach, scope
    and decay for what is left. Ties break on the formation instant and then the id, so two readings
    of an unchanged store are one list, which is `formation.recallable`'s ordering with the id added
    because this list carries one.

    Returns what may be recalled and says nothing about the rest.
    """
    found: list[Recalled] = []
    for one in standing(memories, _memory_id, supersessions=supersessions, demotions=demotions):
        seen = may_recall(
            one.formation,
            reader,
            now=now,
            where=where,
            formed_confidence=one.formed_confidence,
        )
        if seen is not None:
            found.append(Recalled(memory_id=one.memory_id, recollection=seen))
    return tuple(
        sorted(
            found,
            key=lambda one: (
                -one.recollection.confidence,
                one.recollection.formation.formed_at,
                one.memory_id,
            ),
        )
    )


def _memory_id(memory: Memory) -> str:
    return memory.memory_id
