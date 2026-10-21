"""The switch on letting an agent operate an allowlisted desktop application.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file. Off
until the owner has seen it on his install, and not offered anywhere until the desktop runner
exists: the Profile says computer use is not offered (`brain.console.agent_behaviour`), and this
switch does not change that sentence. It is the switch the runner will read when it exists, so
that turning it on is a decision about a thing that runs and not about a thing that is described.

A run in flight is stopped by the halt, not by this switch, for the reason
`brain.browsing.driver.A_SWITCH_GATES_THE_DOOR_AND_THE_HALT_STOPS_THE_RUN` gives.

Task ids: M19.8.1
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

DESKTOP_RUNS: Final = Feature(
    name="desktop_runs",
    title="Let agents operate an allowed desktop application",
    what=(
        "An agent whose ceiling holds the desktop tools may operate one application an "
        "administrator allowed, inside a virtual desktop of its own with no network, on the "
        "windows and controls that were declared and nowhere else. A write waits for a person to "
        "approve the whole run first, and every run is recorded."
    ),
    while_off=(
        "No desktop is started. Nothing is offered to an agent, and a run that started while this "
        "was on is stopped by the halt, not by this."
    ),
    read_by=("brain.browsing.desktop_app:desktop_runs_are_on",),
)
