"""What the Retention and erasure screen needs beside the report: who may act, what each act does,
and the two records this install does not keep.

`brain.retention_routes` serves the newest retention report and the four writes that decide
whether the sweep acts: release, withdrawal, placing a hold and lifting one. It answers a report
and it refuses a write, and neither answer tells a page which controls to draw or what pressing
one will do. This is that half, and it decides nothing `brain.retention_routes` decides.

**Who may act is `brain.retention_routes.may_release` and `may_hold`, called and never restated.**
Each is the authority held over everything, which is the only form a retention write accepts. The
flags decide whether a control is drawn, and the write route decides again whatever this said: a
flag that disagreed with the route would draw a button the route refuses, which is the direction
nobody is hurt by, and a copy of the rule here is how the two would come to disagree. See
`A_FLAG_THAT_DRAWS_A_BUTTON_IS_NOT_THE_DECISION_TO_ACCEPT_ONE`.

**What each act does is written here, in the words a confirmation shows.** `docs/admin-console.md`
requires a destructive action to say what will happen and to what, and the Sessions screen
carries `brain.session_routes`' sentence rather than the console's paraphrase. The same rule here:
the four sentences are the API's, the counts a release acts on come from the report the reader is
looking at, and the console joins the two.

**The export log and the deletion queue are two sentences and no list, and the reason is the
records rather than the screen.** `brain.console.govern_surfaces.export_log` and `deletion_rows`
decide who may read each row, and nothing produces a row for either: `brain.ops.export` builds
its audit row and says in its own docstring that nothing writes it, because
`brain.audit.ledger.AuditAction` has no member for an export, and `brain.ops.erasure.StoreEraser`
is a protocol nothing implements, so no request is recorded and none is carried out. An empty
table under "what left the building" reads as nothing having left, which is the reassuring answer
to the one question nobody established. See `AN_EMPTY_EXPORT_LOG_READS_AS_NOTHING_HAVING_LEFT`.

**How long each kind of thing is kept is `brain.ops.retention.HORIZONS`, sent whole.** It is the
product's declaration and the same for every reader who may open the screen, and it is what makes
a report's windows readable: a store line says a class, and this says what the class means.

**The screen's question is asked first**, with `brain.console.reads.permitted`, before either
authority, so a caller who may not open the screen learns nothing about what they could do on it.

Scope: one read-only route. Nothing here writes; the writes are `brain.retention_routes`'.

Task ids: none
"""

from __future__ import annotations

from typing import Final

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern_surfaces import RETENTION_SCREEN
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent
from brain.ops.retention import HORIZONS, Horizon
from brain.retention_routes import may_hold, may_release

log = structlog.get_logger()

#: The screen this route serves beside the report. Bound to the registry.
THE_SCREEN: Final = RETENTION_SCREEN

# ------------------------------------------------------------------ written-down reasons
#: Why the flags are the retention module's functions and the route still decides.
A_FLAG_THAT_DRAWS_A_BUTTON_IS_NOT_THE_DECISION_TO_ACCEPT_ONE: Final = (
    "may_release and may_hold decide whether a control is drawn, and the write route asks the "
    "same functions again when it is pressed. A copy of either rule here would be correct the day "
    "it was written and would drift, and the drift would be a button for somebody the route "
    "refuses or no button for somebody it accepts."
)

#: Why the export log and the deletion queue are sentences rather than empty tables.
AN_EMPTY_EXPORT_LOG_READS_AS_NOTHING_HAVING_LEFT: Final = (
    "An empty list under what left the building says nothing left, and an empty deletion queue "
    "says nobody asked to be forgotten. Neither was established: nothing records an export and "
    "nothing records or carries out an erasure request. So each is a sentence naming what is not "
    "recorded, and neither is a table."
)

# ------------------------------------------------------------ what each act does, in words
#: What releasing the sweep does, as a confirmation shows it beside the report's counts.
RELEASING: Final = (
    "Releasing lets the sweep act. From its next run it removes what is past its window in every "
    "store it reaches, keeps everything a legal hold covers, and leaves alone what it queued for "
    "the rule that removes it and every store it could not reach. The counts are from the report "
    "you read; anything that passes its window before the next run is removed as well. "
    "Withdrawing the release puts the sweep back to reporting, and nothing already removed comes "
    "back."
)

#: What withdrawing the release does.
WITHDRAWING: Final = (
    "Withdrawing puts the sweep back to reporting. Its next run removes nothing and writes a "
    "report of what it would have removed. Nothing it removed while released is brought back."
)

#: What placing a hold does.
HOLDING: Final = (
    "A legal hold stops the sweep removing anything about the people it names, or anything they "
    "did, from the moment it is placed until it is lifted, including what is written after it is "
    "placed. A store that cannot tell which of its rows a hold covers is not swept at all while "
    "the hold stands. The hold is recorded with your name, and it is lifted rather than ever "
    "deleted."
)

#: What lifting a hold does.
LIFTING: Final = (
    "Lifting a hold lets the sweep remove what the hold was keeping, on the sweep's next released "
    "run, once each item is past its window. The hold stays on record with who placed it, who "
    "lifted it and when."
)

#: What the export log would show, and why it shows nothing.
EXPORTS_ARE_NOT_RECORDED: Final = (
    "Nothing on this install records an export, so this page cannot say what left, who took it or "
    "under whose reach. An export builds the record of itself, but nothing writes that record "
    "anywhere this page can read: the audit trail has no entry for an export yet."
)

#: What the deletion queue would show, and why it shows nothing.
ERASURES_ARE_NOT_RECORDED: Final = (
    "Nothing on this install records a request to erase somebody's data, and nothing carries one "
    "out. The order a deletion would follow and the stores it would not reach are decided; the "
    "step that removes a person's data from each store is not built. So there is no queue to show, "
    "and a request made today has to be handled and recorded outside this system."
)


# ------------------------------------------------------------------------ the shapes
class KeptView(BaseModel):
    """How long one class of thing is kept, and why that answer. `brain.ops.retention.Horizon`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_class: str
    lifetime: str
    #: Set exactly when the lifetime is a fixed window.
    days: int | None
    because: str


class RetentionControlsView(BaseModel):
    """Which controls this reader may be shown, what each does, and the two unrecorded lists."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    may_release: bool
    may_hold: bool
    releasing: str
    withdrawing: str
    holding: str
    lifting: str
    exports: str
    erasures: str
    kept: list[KeptView]


def kept_view(one: Horizon) -> KeptView:
    """One horizon, copied field by field."""
    return KeptView(
        data_class=one.data_class.value,
        lifetime=one.lifetime.value,
        days=one.days,
        because=one.because,
    )


# ------------------------------------------------------------------------ the route
def _not_answerable() -> Absent:
    """The refusal the Retention screen makes, in `brain.retention_routes`' own words."""
    return Absent(f"the {THE_SCREEN} screen is not answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get(
    "/govern/retention/controls", response_model=RetentionControlsView, responses=COMMON_RESPONSES
)
async def retention_controls(asked: Asked) -> RetentionControlsView:
    """Who may act on the Retention screen, what each act does, and what is not recorded.

    The screen first, then the two authorities, each asked of the retention module's own function.
    No database: every answer here is a decision about the reader or a declaration.
    """
    if not permitted(screen(THE_SCREEN).read, asked.reach, asked.now):
        log.info("retention controls not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    return RetentionControlsView(
        may_release=may_release(asked.reach, asked.now),
        may_hold=may_hold(asked.reach, asked.now),
        releasing=RELEASING,
        withdrawing=WITHDRAWING,
        holding=HOLDING,
        lifting=LIFTING,
        exports=EXPORTS_ARE_NOT_RECORDED,
        erasures=ERASURES_ARE_NOT_RECORDED,
        kept=[kept_view(one) for one in HORIZONS],
    )
