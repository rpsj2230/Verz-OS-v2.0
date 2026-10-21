"""Running a stored workflow through an agent that was assigned it (M17.6.1, M17.6.2, M17.7.7).

Off because it is a new way to do unattended work: a series of tool and connector reads, in an
order an administrator wrote, run by an agent for the person who asked, with each step's retry and
failure path decided by the definition. Every step goes through the same gate as an agent's own
call, at the asker's access narrowed by the agent, and a workflow only reads until a held action
from an unattended run has been shown to reach the right person. Saving a workflow and assigning it
to an agent are configuration and are read and set whether the switch is on or not, so turning it
off never hides what was written.

Task ids: M17.6.1, M17.6.2, M17.7.7
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

STORED_WORKFLOWS: Final = Feature(
    name="stored_workflows",
    title="Run a stored workflow through an agent",
    what=(
        "An administrator writes a workflow as a list of steps (a tool, a connector read or a "
        "skill), says what each returns, what it waits for, when it is skipped and what happens "
        "when it fails, and assigns it to an agent. A person who may use that agent starts it, "
        "and the steps run in order, together where marked, each at that person's own access "
        "narrowed by the agent. The run keeps one trace of what each step came to, and a step "
        "that fails in each of its last runs is put in front of a person as a candidate."
    ),
    while_off=(
        "No workflow runs. Workflows can still be written, read and assigned, and the runs already "
        "kept can still be read."
    ),
    read_by=("brain.workflow_routes:workflows_are_on",),
)
