"""Which of our queue tasks a recovery sweep may put back, decided by the class of work each does.

`REDRIVE_BY_TASK` used to be typed beside each task. It is now read off the class its operation is
given in `brain.ops.reliability`, so the leaf that classifies work is what decides whether a dead
worker's job is run again, and a task cannot be called safe without its work being so.

Task ids: M30.4.2
"""

from __future__ import annotations

import pytest

from brain.knowledge.embed_queue import EMBED_TASK, REEMBED_TASK
from brain.knowledge.ingest_queue import INGEST_TASK
from brain.ops.queue import Redrive
from brain.ops.recovery_run import (
    OPERATION_BY_TASK,
    REDRIVE_BY_TASK,
    redrive_for,
    redrive_of_class,
)
from brain.ops.reliability import OPERATION_CLASSES, RetryClass, retry_class_for


def test_every_task_names_an_operation_somebody_classified() -> None:
    """Delete this and a task can name work nothing classifies, which `retry_class_for` refuses
    only when the module is imported, far from the person adding the task."""
    classified = {one.name for one in OPERATION_CLASSES}
    assert set(OPERATION_BY_TASK) == set(REDRIVE_BY_TASK)
    assert set(OPERATION_BY_TASK.values()) <= classified


def test_what_each_task_may_do_after_a_crash_is_what_its_work_is_classified_as() -> None:
    """The three real tasks, against the values they carried when they were typed beside each
    task. Delete this and a reclassified operation changes what a sweep does to a client's queue
    with nothing saying so."""
    assert redrive_for("brain.controls.run") is Redrive.UNSAFE
    assert redrive_for(EMBED_TASK) is Redrive.SAFE
    assert redrive_for(REEMBED_TASK) is Redrive.SAFE
    assert redrive_for(INGEST_TASK) is Redrive.SAFE
    assert retry_class_for(OPERATION_BY_TASK["brain.controls.run"]) is RetryClass.UNSAFE


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (RetryClass.SAFE, Redrive.SAFE),
        (RetryClass.AFTER_VERIFICATION, Redrive.UNSAFE),
        (RetryClass.UNSAFE, Redrive.UNSAFE),
        (RetryClass.NEEDS_A_HUMAN, Redrive.UNSAFE),
    ],
)
def test_only_work_classified_safe_is_put_back_without_a_person(
    kind: RetryClass, expected: Redrive
) -> None:
    """Each of the four, so the rule is not satisfied by a function that says safe for everything
    or unsafe for everything. Delete this and work that needs the far side asked first, or a
    person, is put back on the queue by the sweep."""
    assert redrive_of_class(kind) is expected


def test_a_task_nobody_declared_is_still_unsafe() -> None:
    """The default stays the cautious one. Delete this and a task added to the worker without an
    entry is put back blind."""
    assert redrive_for("brain.not.a.task") is Redrive.UNSAFE
