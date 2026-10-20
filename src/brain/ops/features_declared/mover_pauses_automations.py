"""The switch on pausing a mover's automations when the staff sync changes their reach.

Off because it stops work that is running today, on the strength of a nightly read of a staff
list: an automation a person owns is paused when the sync moves them and what it reaches would
shrink, and it stays paused until somebody confirms it should run at the reach they have now.
`brain.ops.mover_automations` asks the switch before it watches or pauses anything, and never
before a listing or a resume: a switch turned off must not leave an automation paused with no way
to start it again, which is the other half of `brain.ops.features.
A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.

Task ids: M26.2.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

MOVER_PAUSES_AUTOMATIONS: Final = Feature(
    name="mover_pauses_automations",
    title="Pause a mover's automations when their reach shrinks",
    what=(
        "When the nightly staff sync moves a person to another department, each automation they "
        "own that would lose some of what it reached is paused instead of quietly running at the "
        "smaller reach. It is listed as paused on that person's Automations page and on the page "
        "of anyone who holds authority over it, and it runs again only when somebody with that "
        "authority confirms it at the reach the person has now. An automation whose reach did "
        "not shrink is left alone."
    ),
    while_off=(
        "A person who moves keeps every automation running at whatever reach they now have, as "
        "before. An automation already paused by a move stays paused, is still listed, and can "
        "still be confirmed and started."
    ),
    read_by=("brain.ops.mover_automations:movers_pause_automations",),
)
