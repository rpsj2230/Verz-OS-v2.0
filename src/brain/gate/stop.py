"""Why an agent run ended: a closed list, kept apart from the loop so a table can name it.

`brain.gate.runtime` is the loop and imports a good deal of the gate; `brain.tables.agent_run`
renders its check constraint from this list and must not import the loop to do it, because the
table package is imported by everything and the loop by very little. So the vocabulary lives here,
with nothing beside it.

Task ids: M13.7.2
"""

from __future__ import annotations

import enum


class StopReason(enum.StrEnum):
    """Why a run ended. Closed, because `ops.agent_run.stop_reason` is checked against it."""

    ANSWERED = "answered"
    TURN_BOUND = "turn_bound"
    TOOL_CALL_BOUND = "tool_call_bound"
    TIME_BOUND = "time_bound"
    SPEND_BOUND = "spend_bound"
    #: The run could not start: no tool to offer, or a halt.
    REFUSED = "refused"
    #: The model declined on content.
    DECLINED = "declined"
    FAULTED = "faulted"
