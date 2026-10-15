"""Mutation table for the run again control (M27.13.3). Run from the repository root."""

from __future__ import annotations

import subprocess
from pathlib import Path

from brain.ops.mutation import Mutation, verify

repo = Path(".").resolve()
changed = subprocess.run(
    ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
).stdout.splitlines()
carry = tuple(
    line[3:].strip()
    for line in changed
    if line[3:].strip().endswith(".py")
    and not line[3:].strip().startswith("console/")
    and not line[3:].strip().startswith(".")
)

CTRL = "src/brain/ops/redrive_control.py"
ROUTES = "src/brain/jobs_routes.py"
QUEUE = "src/brain/ops/queue.py"
SWEEP = "src/brain/ops/recovery_run.py"
PURE = ("tests/unit/test_redrive_control.py",)
HTTP = ("tests/unit/test_redrive_routes.py",)
DB = (
    "tests/unit/test_dead_letter.py::"
    "test_a_persons_ask_puts_one_job_back_through_the_drivers_retry_and_is_answered_once",
)

mutations = [
    Mutation(
        label="an answered ask is live again only when it is later than its answer",
        path=CTRL,
        before="return answered is None or answered.at < asked.at",
        after="return answered is None",
        tests=PURE,
    ),
    Mutation(
        label="an ask in the future is not live",
        path=CTRL,
        before="    if asked.at > now:\n        return False\n    return answered",
        after="    return answered",
        tests=PURE,
    ),
    Mutation(
        label="a naive instant is not an ask",
        path=CTRL,
        before="    return at if at.tzinfo is not None else None",
        after="    return at",
        tests=PURE,
    ),
    Mutation(
        label="an answer must hold a real boolean",
        path=CTRL,
        before="if at is None or not isinstance(put_back, bool):",
        after="if at is None:",
        tests=PURE,
    ),
    Mutation(
        label="one minute carries out a bounded number of asks",
        path=CTRL,
        before="for job in live_job_ids(asked, answered, now=now):",
        after="for job in asked:",
        tests=PURE,
    ),
    Mutation(
        label="the oldest ask is carried out first",
        path=CTRL,
        before="    return tuple(job for _, job in owed[:MOST_PER_MINUTE])",
        after="    return tuple(job for _, job in owed[::-1][:MOST_PER_MINUTE])",
        tests=PURE,
    ),
    Mutation(
        label="a job id is digits and nothing else",
        path=CTRL,
        before="if JOB_ID.fullmatch(job_id) is None:",
        after="if False:",
        tests=PURE,
    ),
    Mutation(
        label="the worker answers every ask it carries out",
        path=CTRL,
        before="        await rows.answer(job, WorkerAnswer(at=now, put_back=moved))\n",
        after="",
        tests=PURE,
    ),
    Mutation(
        label="an ask for a job no longer failed is answered as not put back",
        path=CTRL,
        before="        (put_back if moved else could_not).append(job)",
        after="        put_back.append(job)",
        tests=PURE,
    ),
    Mutation(
        label="the screen says nothing of a job nobody asked about",
        path=CTRL,
        before=(
            "    if asked is None:\n        return None\n"
            "    if answered is None or answered.at < asked.at:"
        ),
        after="    if answered is None or answered.at < asked.at:",
        tests=PURE,
    ),
    Mutation(
        label="pressing needs the schedule's authority",
        path=ROUTES,
        before='    if not may_control(asked.reach, asked.now):\n        log.info("run again refused"',
        after='    if False:\n        log.info("run again refused"',
        tests=HTTP,
    ),
    Mutation(
        label="the job's own read decides, and a hidden job is the one refusal",
        path=ROUTES,
        before="        if entry is None or not (",
        after="        if entry is None or False and (",
        tests=HTTP,
    ),
    Mutation(
        label="the switch gates the press",
        path=ROUTES,
        before=(
            "        if not await is_on(session, JOB_REDRIVE):\n"
            "            await session.rollback()\n"
            "            raise _refused_because(REDRIVE_SWITCHED_OFF)"
        ),
        after="        if False:\n            raise _refused_because(REDRIVE_SWITCHED_OFF)",
        tests=HTTP,
    ),
    Mutation(
        label="a dead letter whose references are gone is refused",
        path=ROUTES,
        before="        if not entry.is_actionable(asked.now):",
        after="        if False:",
        tests=HTTP,
    ),
    Mutation(
        label="the press is attributed to the person",
        path=ROUTES,
        before="            await _attribute(session, asked)\n            await ask(session, job_id",
        after="            await ask(session, job_id",
        tests=HTTP,
    ),
    Mutation(
        label="the list carries each ask's standing",
        path=ROUTES,
        before=(
            "            run_again_standing=standing_of(asked.get(one.job_id), "
            "answered.get(one.job_id)),"
        ),
        after="            run_again_standing=None,",
        tests=HTTP,
    ),
    Mutation(
        label="the driver's retry is asked only for a failed job",
        path=QUEUE,
        before='        if not found or str(found[0]["status"]) != "failed":\n            return False',
        after="        if not found:\n            return False",
        tests=DB,
    ),
    Mutation(
        label="the worker writes its answer as the worker",
        path=QUEUE,
        before="            by=WORKER,",
        after='            by="u_admin",',
        tests=DB,
    ),
    Mutation(
        label="the sweep's minute carries out the asks",
        path=SWEEP,
        before="            return replace(swept, asked=await carry_out_asks(queue, now=now))",
        after="            return swept",
        tests=DB,
    ),
]

report = verify(mutations, repo=repo, carry=carry)
print(report.table())
print("SURVIVORS:", [one.mutation.label for one in report.survivors])
