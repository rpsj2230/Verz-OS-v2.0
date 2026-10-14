"""Starting an automation when a connected source reports a change (needs-rupash 223, option B).

Off because it is a new way to start unattended work: the owner decided what may start one (a
schedule or a connector's change and nothing from outside) and asked that it ship off until proved
on his install with a changed record. `brain.ops.automation_event_store` is the worker's reader and
the two routes modules say on a screen whether it is on.

Task ids: M17.4.1
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

AUTOMATION_EVENTS: Final = Feature(
    name="automation_events",
    title="Start an automation when a connected source reports a change",
    what=(
        "An automation written to run when something changes in a connected source can be "
        "started, and then runs as the person it belongs to each time a record in that source "
        "changes, at most a few times an hour. It runs only for a record that person may already "
        "read, and a run never carries the record's content: it reads what it needs as them, as "
        "every run does. Nothing starts work from outside the install."
    ),
    while_off=(
        "An automation written for a change cannot be started and nothing runs on one. One "
        "started while this was on keeps listening for when it is turned back on, and can still be "
        "stopped."
    ),
    read_by=(
        "brain.ops.automation_event_store:event_starts_are_on",
        "brain.automation_schedule_routes:events_are_on",
        "brain.automation_authoring_routes:events_are_on",
    ),
)
