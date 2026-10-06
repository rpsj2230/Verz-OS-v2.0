"""A followed citation's place, sent back for the learning signal, and the signal read (M15.3.4).

Two routes over `brain.ops.retrieval_store`. `POST /retrievals/{id}/uses` is what the page a
citation opens sends: the retrieval's id from the answer's `x-retrieval-id` header and the
passage's place in the list the person was shown. `GET /retrievals/signal` is the signal read over
the most recent retrievals, for the people who run the knowledge layer.

**A use is accepted from anybody signed in, and says nothing back.** The id is minted per answer
and reaches only the person the answer was for, and what a use records is a place in a list that
names no document and nobody, so there is nothing a stranger holding an id could learn or spoil
beyond one position in one retrieval. An id naming nothing and a place outside the list are one
404, so the route answers nothing about which ids exist. See
`brain.ops.retrieval_store.A_USE_IS_A_PLACE_IN_THE_READERS_OWN_LIST`.

**The signal is read by a knowledge administrator, and by nobody else it is one 404.** It is
rates over the install's retrievals and names no document, question or person, so it tells a
reader nothing about what they may not see; it is withheld from everybody else because it is a
tool for tuning the ranking and a person asking questions has no use for it. Below
`brain.knowledge.quality.MINIMUM_EVENTS_FOR_A_SIGNAL` it says there is not enough yet rather than
answering with a number one afternoon decided.

Task ids: M15.3.4
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, retrievals_of
from brain.core.errors import Absent, Failed
from brain.gate.model_lane import PASSAGES_SHOWN
from brain.knowledge.search import KNOWLEDGE_UPLOAD
from brain.ops.retrieval_store import StoredRetrievals

USES_PATH: Final = "/retrievals/{event_id}/uses"
SIGNAL_PATH: Final = "/retrievals/signal"

#: A retrieval id as the table holds one: a UUID's text.
EVENT_ID_PATTERN: Final = r"^[0-9a-fA-F-]{36}$"

#: What the signal says when there is not yet enough to have one.
NOT_ENOUGH_YET: Final = (
    "Not enough questions have been answered from the library yet for the ranking to be judged."
)

router = APIRouter(prefix=API_PREFIX, tags=["retrievals"])


class UseAsked(BaseModel):
    """The place of the passage a person followed, in the list they were shown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: int = Field(ge=1, le=PASSAGES_SHOWN)


class UseView(BaseModel):
    """That the place was kept. Nothing about the retrieval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    recorded: bool


class SignalView(BaseModel):
    """The ranking's learning signal, or the sentence saying there is not enough for one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enough: bool
    told: str = ""
    events: int = 0
    used_share: float = 0.0
    top_position_share: float = 0.0
    mean_first_used_position: float = 0.0
    latency_p95_ms: float = 0.0
    cached_share: float = 0.0


def _store(request: Request) -> StoredRetrievals:
    found = retrievals_of(request.app.state)
    if found is None:
        raise Failed("no database on this process")
    return found


@router.post(USES_PATH, response_model=UseView, responses=COMMON_RESPONSES)
async def used(
    request: Request,
    asked: Asked,
    event_id: Annotated[str, Path(pattern=EVENT_ID_PATTERN)],
    body: UseAsked,
) -> UseView:
    """Keep the place of a passage a person followed from an answer (M15.3.4)."""
    del asked  # Signed in is the whole requirement; see the module docstring.
    if not await _store(request).use(event_id, body.position):
        raise Absent("that retrieval")
    return UseView(recorded=True)


@router.get(SIGNAL_PATH, response_model=SignalView, responses=COMMON_RESPONSES)
async def retrieval_signal(request: Request, asked: Asked) -> SignalView:
    """The learning signal over the most recent retrievals, for a knowledge administrator."""
    if not asked.reach.holds(KNOWLEDGE_UPLOAD, asked.now):
        raise Absent("the retrieval signal")
    found = await _store(request).signal()
    if found is None:
        return SignalView(enough=False, told=NOT_ENOUGH_YET)
    return SignalView(
        enough=True,
        events=found.events,
        used_share=found.used_share,
        top_position_share=found.top_position_share,
        mean_first_used_position=found.mean_first_used_position,
        latency_p95_ms=found.latency_p95_ms,
        cached_share=found.cached_share,
    )
