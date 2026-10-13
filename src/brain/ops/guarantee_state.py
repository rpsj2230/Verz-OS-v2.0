"""Whether a guarantee is held: the state of the control that keeps it, and nothing else.

A console screen that says a protection is in force is making a claim about a mechanism that has to
keep running, and `brain.ops.controls` is the register of those mechanisms. Until this module a
screen that reported a guarantee read the thing the mechanism produces (a backup's timestamp, a
chain's head) and never whether the mechanism itself was still running, so a control nothing
called, or one that had stopped a week ago, left every screen it served saying the guarantee held.

**A guarantee is held exactly when its control is not overdue, and every way of not running is
not held.** `controls.overdue` already separates the four ways a control fails to run: nothing
calls it (`UNREACHABLE`), nothing records its runs (`NOT_RECORDED`), its runs are recorded and there
has never been one (`NEVER_RUN`), or the last one is too old (`BEHIND`). Each of the four is a
guarantee that is **not held**, which is the whole of the leaf: a screen has no fifth word like
"probably" and no reading in which an unknown is shown as fine. The reason travels with the state
so a screen can say which of the four, in `controls.overdue`'s own sentence.

**An unreadable record is not held either.** When the run record could not be read at all
(`last_run` is `None`) every guarantee is `NOT_RECORDED`: the screen was about to say the
protection holds on the strength of a table it could not open. See
`A_GUARANTEE_IS_NOT_HELD_ON_EVIDENCE_THAT_COULD_NOT_BE_READ`.

**A control the registry does not name is not held.** `held_by` answers False for a name nobody
registered, so a screen that points at a control which was renamed fails visibly, as a guarantee
nobody keeps, rather than silently as one that always holds.

Rejected: a state per screen, kept beside the figure the screen draws. That is the second copy of
the question and it drifts the first time a control is renamed; the one function below is asked by
every screen and the answer is the register's.

Rejected: reading `Missed` as a severity. `controls.overdue` sorts by `Severity` and a screen
needs only held or not, so the reason is a word and the severity stays the alert's.

Task ids: M27.15.54
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.ops.controls import CONTROLS, Control, Missed, overdue

#: Why an unreadable run record leaves every guarantee not held.
A_GUARANTEE_IS_NOT_HELD_ON_EVIDENCE_THAT_COULD_NOT_BE_READ: Final = (
    "A screen that cannot open the table of runs cannot say a control ran. The reading is the same "
    "as for a control whose runs nothing records, a guarantee that is not held, and never the "
    "reading that nothing was wrong, which is the one a screen draws when it looks at nothing."
)


@dataclass(frozen=True)
class Guarantee:
    """One protection, whether it is held now, and why not when it is not.

    `because` is None exactly when `held`, which `__post_init__` refuses to see otherwise, so a
    renderer is never handed a held guarantee with a reason or a lapsed one without.
    """

    control: str
    guards: str
    held: bool
    because: Missed | None
    #: The sentence a person reads: what it guards and, when not held, what to know.
    said: str

    def __post_init__(self) -> None:
        if self.held != (self.because is None):
            msg = "a guarantee is held with no reason, or not held with one"
            raise ValueError(msg)


def guarantees(
    last_run: Mapping[str, datetime | None] | None,
    now: datetime,
    controls: Sequence[Control] | None = None,
) -> tuple[Guarantee, ...]:
    """The state of the guarantee each control keeps, in registry order.

    `last_run` maps a control's name to when it last finished successfully, or None for a record
    that holds none, and is itself None when the record could not be read. A name missing from the
    mapping is a control nothing records.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    if last_run is None:
        return tuple(_lapsed(one, Missed.NOT_RECORDED) for one in rows)
    late = {one.control.name: one for one in overdue(last_run=last_run, now=now, controls=rows)}
    out: list[Guarantee] = []
    for one in rows:
        found = late.get(one.name)
        if found is None:
            out.append(
                Guarantee(
                    control=one.name,
                    guards=one.guards,
                    held=True,
                    because=None,
                    said=f"Held: {one.guards}.",
                )
            )
        else:
            out.append(
                Guarantee(
                    control=one.name,
                    guards=one.guards,
                    held=False,
                    because=found.missed,
                    said=found.text,
                )
            )
    return tuple(out)


def _lapsed(one: Control, why: Missed) -> Guarantee:
    return Guarantee(
        control=one.name,
        guards=one.guards,
        held=False,
        because=why,
        said=(
            f"Not held: {one.guards}. Nothing says {one.name} has run, because the record of runs "
            "could not be read."
        ),
    )


def held_by(control: str, states: Sequence[Guarantee]) -> bool:
    """Whether the guarantee this control keeps is held, False for a control nobody registered."""
    return any(one.control == control and one.held for one in states)
