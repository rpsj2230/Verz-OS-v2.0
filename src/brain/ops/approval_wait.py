"""How long approvals wait, as one figure, and whether it is long enough that push is due.

The deferral of push notifications for approvals (`brain.locale.PUSH_FOR_APPROVALS`) said an
install whose typical approval wait passes `PUSH_IS_DUE_ABOVE_HOURS` has the problem push solves,
and that "the measurement exists". It did not: `gate.suspension` shows a person only the approvals
they raised or decided, so no reader could see the whole queue's timings. `0227` adds the view
`gate.approval_wait`, two times per decided approval and nothing that names a person, and this
module is its reader.

**The figure is a median and the module returns no count.** A count of decided approvals is a fact
about what the install's people were asked, and nobody on the Install page is entitled to it. The
median of the waits is one duration. **An install with nothing decided yet has no typical wait**,
which is `None` and is shown as unknown with the reason, never as zero: zero would read as
"approvals are answered at once" and would keep push deferred on no evidence.

**Whether push is due is `locale.triggered`'s answer**, not a second comparison here. This module
supplies the measurement the deferral's own trigger names and `locale` decides.

Task ids: M35.4.5, M35.3.2.2
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.locale import PUSH_FOR_APPROVALS, PUSH_IS_DUE_ABOVE_HOURS, Trigger, triggered

#: How far back a decision counts towards the typical wait. A quarter: long enough for a quiet
#: install to have decided some, short enough that a fixed habit shows.
LOOKBACK: Final = timedelta(days=90)

#: The most decisions one measurement reads, newest first. A resource bound, and far above the
#: decisions of any install the product is sized for.
MOST_READ: Final = 5000

_READ: Final = text(
    "SELECT raised_at, decided_at FROM gate.approval_wait"
    " WHERE decided_at >= :since ORDER BY decided_at DESC LIMIT :most"
)


async def waits_since(
    session: AsyncSession, *, now: datetime, lookback: timedelta = LOOKBACK
) -> tuple[tuple[datetime, datetime], ...]:
    """Every decided approval's raised and decided instants in the look-back, newest first."""
    rows = (await session.execute(_READ.bindparams(since=now - lookback, most=MOST_READ))).all()
    return tuple((one[0], one[1]) for one in rows)


def typical_wait(pairs: Sequence[tuple[datetime, datetime]]) -> timedelta | None:
    """The median wait between raised and decided, or None when nothing was decided.

    A decision recorded before its own raising (clock skew between writers) counts as no wait
    rather than a negative one, which would drag the median below what anybody experienced.
    """
    waits = [max((decided - raised).total_seconds(), 0.0) for raised, decided in pairs]
    if not waits:
        return None
    return timedelta(seconds=statistics.median(waits))


def push_is_wanted(typical: timedelta | None) -> bool:
    """Whether the deferral's trigger has fired: the typical wait is past the stated hours."""
    if typical is None:
        return False
    facts = {
        Trigger.APPROVALS_WAIT_LONGER_THAN_THE_STATED_HOURS: typical
        > timedelta(hours=PUSH_IS_DUE_ABOVE_HOURS)
    }
    return PUSH_FOR_APPROVALS in triggered(facts)


def worded(typical: timedelta) -> str:
    """A wait as a person reads it: whole hours and minutes, or 'under a minute'."""
    minutes = int(typical.total_seconds() // 60)
    if minutes < 1:
        return "under a minute"
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("" if hours == 1 else "s"))
    if minutes:
        parts.append(f"{minutes} minute" + ("" if minutes == 1 else "s"))
    return " ".join(parts)
