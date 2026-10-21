"""The state of each recent thread: running, waiting for approval, done or failed (M40.7.6).

Off because a new capability ships switched off on every install, and because turning it on makes
the member's list read three more places for every list it draws: the actions a person's runs held,
what the worker did with the ones approved, and how a failed request ended. Nothing it shows is
anyone else's or new to the person, so the switch is about cost and about the owner watching it
work before it is everywhere. `brain.thread_routes` asks the switch before reading those records
and never before listing the threads themselves, so a person's list is the same list either way.

Task ids: M40.7.6
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

THREAD_STATES: Final = Feature(
    name="thread_states",
    title="Show whether each recent conversation is running, waiting, done or failed",
    what=(
        "Each of a person's recent conversations says what became of the last thing they asked: "
        "still running, waiting for somebody to approve something it prepared, done, or failed. A "
        "failed one says which step of answering it stopped at. It is read from the records of "
        "their own runs and shows nothing about anyone else's."
    ),
    while_off=("The conversations are listed exactly as before, without a state beside each."),
    read_by=("brain.thread_routes:thread_states_are_on",),
)
