"""What one question's retrieval leaves behind for the learning signal, and nothing else (M15.3.4).

`brain.knowledge.quality` holds the record, `RetrievalEvent`, and the signal read from a batch of
them, and argues at length what the record may not hold: no reference, no question, no principal,
no count of anything withheld. This module is the half that was missing, the path from a question
answered on Ask to one such record, and it is arranged so that path can only ever produce that
record.

**The search notes what it knows, the route finishes the record, and neither stores a reference.**
Only the passage search knows which retrievers ran and which passages more than one of them found;
only the answer knows how many passages the person was shown, after the redactor and the lane's
cut. So the search notes a `Searched` into a collector bound to the request, holding the chunk
ids it fused in memory for the length of the request, and `event_for` turns it into a
`RetrievalEvent` against the payload the person received: the count shown, and how many of those
were corroborated. The chunk ids are never written anywhere; the event that is written has no
field for one. See `THE_SEARCH_KNOWS_THE_LEGS_AND_THE_ANSWER_KNOWS_WHAT_WAS_SHOWN`.

**Only a retrieval a person could act on is collected.** The collector exists only inside
`collected`, which the Ask route opens around its answer, so a search made by an acceptance check,
a chat channel or an agent's tool call notes nothing: there is no list to note into. A retrieval
logged where nobody can follow a citation would count as a retrieval nobody used, and the signal's
`used_share` would fall for a reason that is about the channel and not about the ranking. See
`ONLY_A_RETRIEVAL_SOMEBODY_COULD_FOLLOW_IS_LOGGED`.

**Where the person acted is the position they followed, sent by the page and nothing more.** The
citation carries its passage's place in the list the person was shown, and the page that opens a
cited document sends that place back against the retrieval's id. The server learns that the second
passage of some retrieval was opened; the retrieval names no document, no question and nobody.

Task ids: M15.3.4
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final

from brain.knowledge.quality import RetrievalEvent

#: Why the search and the answer each supply half of one record.
THE_SEARCH_KNOWS_THE_LEGS_AND_THE_ANSWER_KNOWS_WHAT_WAS_SHOWN: Final = (
    "Which retrievers ran and which passages two of them agreed on is known inside the search; "
    "how many passages the person was shown is known only after the redactor and the lane's cut. "
    "So the search notes the first in memory for the request and the route finishes the record "
    "against the payload shown. The chunk ids the search held are never written: the record has "
    "no field for one."
)

#: Why nothing outside the Ask route is logged.
ONLY_A_RETRIEVAL_SOMEBODY_COULD_FOLLOW_IS_LOGGED: Final = (
    "The signal's used share is how often a person followed what retrieval found. A retrieval "
    "logged from a check, a chat or a tool call could never be followed, so it would read as "
    "unused and pull the share down for a reason about the channel rather than the ranking. The "
    "collector exists only inside the Ask route's answer, and a search anywhere else has no list "
    "to note into."
)


@dataclass(frozen=True)
class Searched:
    """What one passage search knew, held in memory for its request and never written.

    `corroborated` is the chunk ids more than one retriever ranked, which `event_for` counts
    against the passages actually shown and then drops. `from_cache` says the ranking was served
    from the retrieval cache rather than made for this request; see
    `brain.knowledge.document_tools.A_CACHED_RANKING_IS_NOTED_AS_SERVED_FROM_THE_CACHE`.
    """

    retrievers: tuple[str, ...]
    corroborated: frozenset[str]
    latency_ms: int
    from_cache: bool = False


_COLLECTING: ContextVar[list[Searched] | None] = ContextVar("brain_retrievals", default=None)


@contextmanager
def collected() -> Iterator[list[Searched]]:
    """A collector for the searches made inside this block, and only this block."""
    found: list[Searched] = []
    token = _COLLECTING.set(found)
    try:
        yield found
    finally:
        _COLLECTING.reset(token)


def note(searched: Searched) -> None:
    """Note one search into the request's collector, when the request has one."""
    found = _COLLECTING.get()
    if found is not None:
        found.append(searched)


def started() -> float:
    """The instant a search's latency is measured from."""
    return time.monotonic()


def elapsed_ms(since: float) -> int:
    """Whole milliseconds since `since`, never negative."""
    return max(0, round((time.monotonic() - since) * 1000))


def event_for(searched: Sequence[Searched], shown: Iterable[str]) -> RetrievalEvent | None:
    """The record for the last search a request made, against the passages the person was shown.

    None when no search was made. `shown` is the chunk ids of the payload the person received, in
    order; the count is theirs and the corroboration is counted over them alone, so a passage the
    redactor dropped is in neither number.
    """
    if not searched:
        return None
    last = searched[-1]
    ids = list(dict.fromkeys(shown))
    return RetrievalEvent(
        retrievers=tuple(sorted(set(last.retrievers))),
        returned=len(ids),
        corroborated=sum(1 for one in ids if one in last.corroborated),
        latency_ms=last.latency_ms,
        from_cache=last.from_cache,
    )
