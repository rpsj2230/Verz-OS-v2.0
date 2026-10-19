"""The switch on putting a job set aside for a person back on its queue from the console.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off until the owner has seen it on his install, because it is a new way for one person's press to
make the worker run something again that its own sweep decided not to: a job of a task nobody
declared safe to run twice, or one that failed at its cap. Everything else on the Scheduled jobs
screen reads and changes nothing about the queue; this is the one control that does, so it has its
own switch rather than riding `schedule_control`, which an administrator may well have on for
pausing a job and not for this. See `brain.ops.redrive_control` for why it is a person's act.

Task ids: M27.13.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

JOB_REDRIVE: Final = Feature(
    name="job_redrive",
    title="Run a job that was set aside again, from the console",
    what=(
        "An administrator holding the schedule's authority may press Run again on a job the "
        "recovery sweep set aside for a person. The worker puts that one job back on its queue on "
        "its next minute, with the arguments it already had, and the screen then says when it "
        "did. Nothing runs a job again that was not asked for by name."
    ),
    while_off=(
        "A job set aside stays where it is until the person who looks at it deals with it on the "
        "server. The list of jobs set aside is still shown, and a run again asked for while this "
        "was on is still carried out."
    ),
    read_by=(
        "brain.jobs_routes:dead_letters",
        "brain.jobs_routes:redrive_dead_letter",
    ),
)
