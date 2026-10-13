"""Install acceptance checks for hosting and recovery: the backup report and its alert, the
retention the install keeps, and a question measured in its lane.

**The backup report check has two halves and they prove different things.** The first hands the
product's own report builder a listing the check made, a database copy thirty hours old against a
lite install's day, and follows it the way the worker does: the report is recorded as the setting
the Recovery screen and this check read back, and the alert it raises is said once to a room and
not again the same day. The room is a stand-in that keeps what it is sent, so nothing reaches a
real chat (`A_ROOM_THE_CHECK_MADE_IS_NEVER_A_REAL_CHAT`). The second half is the install's own: the
worker's schedule has run the report, and what it recorded says the bucket was read. That half
can only be shown by the worker on that server, so an install whose worker has not run it yet
says so, as not run rather than failed.

**The answer-lane check asks a real question through the real route.** The question is answered by
the fast lane from a price list the check uploaded, so no model is called and nothing is billed. The
request leaves its row in `obs.request_telemetry`, with the lane, a duration and how it ended, and
the Service levels route counts it in that lane for a reader of that screen. **The count is read
before and after rather than asserted from nothing**, because a live install already has traffic.

**The retention check is the decided ladder and nothing grander.** The owner decided a ladder of
thirty daily copies and five weekly ones, so its horizon equals the thirty-five days the backups
bucket and every erasure certificate promise (needs-rupash item 60, option A). The check holds the
policy's own gap function to say the declaration agrees with itself.

Task ids: M30.3.10, M30.6.10, M30.5.2, M30.6.9, M30.3.5
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2321

A, _ = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the check's room is a stand-in.
A_ROOM_THE_CHECK_MADE_IS_NEVER_A_REAL_CHAT: Final = (
    "The alert is sent to a room the check holds, which keeps what it is sent. A check that "
    "posted to the install's own evening-digest conversation would be an alert to a real room "
    "about a backup that was not late."
)

#: Said when the worker's schedule has not run the report on this install.
NO_SCHEDULED_REPORT_YET: Final = (
    "the worker's schedule has recorded no run of the backup report on this install yet, so "
    "there is no scheduled run to judge; the next acceptance run after the worker's first daily "
    "tick judges it"
)

#: Said when the worker ran the report and could not read the bucket.
THE_WORKER_COULD_NOT_READ_THE_BUCKET: Final = (
    "the worker's last backup report could not read the backup bucket, so it found nothing about "
    "any copy; connect the object store, and the next run judges it"
)

# ------------------------------------------------------------------------ the figures
#: How recent the report's last run must be: a daily control and a tick's worth of slack.
REPORT_EVIDENCE_WINDOW: Final = timedelta(hours=26)

#: The fault the check's made-up listing holds: a database copy this much older than a day.
HOURS_BEHIND: Final = 30

#: The control the report is.
CONTROL: Final = "backup_exposure"


class _Room:
    """A room that keeps what it is sent."""

    def __init__(self) -> None:
        self.bodies: list[str] = []

    def send(self, payload: object, *, to: str, body: str) -> None:
        self.bodies.append(body)


# ------------------------------------------------- 1. the report and the alert (M30.3.10, M30.6.10)
@check(
    leaves=("M30.3.10", "M30.6.10"),
    sentence=(
        "A database copy thirty hours old on a lite install is recorded as a report on the "
        "install and raises one alert, said once to a room and not again that day; the "
        "worker's own last run of the report is recent and read the backup bucket."
    ),
)
async def a_backup_older_than_its_recovery_point_is_recorded_and_said_once(h: Harness) -> None:
    import json

    from sqlalchemy import select

    from brain.gate.context import Channel
    from brain.ops.acceptance_checks import _HeldLedger
    from brain.ops.backup_manifest import MANIFEST_SUFFIX
    from brain.ops.backup_report_run import (
        deliver_alerts,
        record_report,
        recorded_report,
        report_of,
    )
    from brain.ops.digest_delivery import DigestChannel
    from brain.tables.schedule import ControlRunRow

    finished = h.now - timedelta(hours=HOURS_BEHIND)
    listing = [
        (
            f"acceptance{MANIFEST_SUFFIX}",
            json.dumps(
                {
                    "backup_id": f"acceptance-{h.run}",
                    "coverage": "database",
                    "method": "full",
                    "destination": "s3://acceptance",
                    "started_at": (finished - timedelta(minutes=4)).isoformat(),
                    "finished_at": finished.isoformat(),
                    "recoverable_to": finished.isoformat(),
                    "size_bytes": 1024,
                }
            ),
        )
    ]
    report = report_of(listing, profile="lite", now=h.now)
    aged = [
        one
        for one in report.alerts
        if one.coverage is not None and one.coverage.value == "database"
    ]
    if len(aged) != 1:
        raise CheckFailedError(
            "a copy older than the recovery point did not raise exactly one alert"
        )
    inside = report_of(
        [
            (
                f"fresh{MANIFEST_SUFFIX}",
                listing[0][1].replace(
                    finished.isoformat(), (h.now - timedelta(hours=1)).isoformat()
                ),
            )
        ],
        profile="lite",
        now=h.now,
    )
    if any(one.coverage is not None and one.coverage.value == "database" for one in inside.alerts):
        raise CheckFailedError("a copy inside the recovery point raised an alert")

    # The report is recorded as the setting the Recovery screen and this check read back.
    await record_report(h.sessions, report)
    async with h.sessions() as session:
        kept = await recorded_report(session)
    if kept is None or kept.get("at") != report.as_value()["at"] or not kept.get("alerts"):
        raise CheckFailedError("a recorded backup report was not read back as it was written")

    # Said once, to a room the check holds, and not again the same day.
    room, ledger = _Room(), _HeldLedger()
    chat = DigestChannel(channel=Channel.LARK, chat_id=f"acceptance_{h.run}")
    day = h.now.date().isoformat()
    sent = [
        deliver_alerts(
            report.alerts, day=day, channel=chat, sender=room, ledger=ledger, principal_id=h.actor
        )
        for _ in range(2)
    ]
    if sent != [(1, 0), (1, 0)] or len(room.bodies) != 1:
        raise CheckFailedError("an alert was not said exactly once for the day")

    # The install's own half: the worker's schedule has run the report, and read the bucket.
    async with h.sessions() as session:
        last = (
            await session.execute(
                select(ControlRunRow)
                .where(ControlRunRow.name == CONTROL)
                .order_by(ControlRunRow.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if last is None:
        raise CheckNotRunError(NO_SCHEDULED_REPORT_YET)
    if last.outcome != "ok" or last.report_only:
        raise CheckFailedError("the schedule's last run of the backup report did not finish")
    if h.now - last.started_at > REPORT_EVIDENCE_WINDOW:
        raise CheckFailedError("the schedule has not run the backup report in a day")
    if "was not read" in (last.detail or ""):
        raise CheckNotRunError(THE_WORKER_COULD_NOT_READ_THE_BUCKET)


# ------------------------------------------------------------------ 2. retention (M30.3.5)
@check(
    leaves=("M30.3.5",),
    sentence=(
        "The retention ladder the install keeps is thirty daily and five weekly copies, its "
        "horizon is the days the backups bucket and every erasure certificate promise, and the "
        "backup policy has no gap in how it holds together."
    ),
)
async def the_retention_ladder_fits_inside_the_promised_window(h: Harness) -> None:
    from brain.ops.recovery import RETENTION_LADDER, backup_policy_gaps
    from brain.ops.retention import BACKUP_RETENTION_DAYS

    if (RETENTION_LADDER.daily, RETENTION_LADDER.weekly, RETENTION_LADDER.monthly) != (30, 5, 0):
        raise CheckFailedError("the retention ladder is not the one the owner decided")
    if RETENTION_LADDER.horizon_days() != BACKUP_RETENTION_DAYS:
        raise CheckFailedError("the ladder's horizon is not the window the backups bucket keeps")
    if backup_policy_gaps():
        raise CheckFailedError("the backup policy does not hold together")


# ------------------------------------- 3. a question measured in its lane (M30.5.2, M30.6.9)
@check(
    leaves=("M30.5.2", "M30.6.9"),
    sentence=(
        "A question asked through the answer route leaves a request row carrying its lane, a "
        "duration and how it ended, and the Service levels route counts it in that lane for a "
        "reader of that screen, one more than before it was asked; every lane is listed, "
        "including one nothing was asked through."
    ),
)
async def a_question_is_measured_in_its_lane_and_counted_on_service_levels(h: Harness) -> None:
    from brain.core.lane import Lane
    from brain.gate.context import Channel
    from brain.ops.acceptance_checks_memory import KeptPrompts
    from brain.ops.acceptance_checks_speed import a_rule_on_a_list, asked_on, rules_app
    from brain.ops.acceptance_operations_console import asking_as, console_for, screen_grants
    from brain.report_routes import service_levels

    made = await a_rule_on_a_list(h)
    watcher = h.principal(A, "levels")
    await h.person(watcher, department=A, grants=screen_grants("service_levels"))
    console = console_for(h)

    async def counts() -> dict[str, int]:
        view = await service_levels(console.request(), await asking_as(h, watcher))
        return {one.lane: one.requests for one in view.lanes}

    before = await counts()
    stand_in = KeptPrompts()
    app = await rules_app(h, stand_in)
    answered = await asked_on(h, app, made.reader, made.question(), 1, Channel.CONSOLE)
    if answered.text is None:
        raise CheckFailedError("a question the check's price list answers was not answered")

    rows = (
        await h.execute(
            text(
                "SELECT lane, duration_ms, status FROM obs.request_telemetry"
                " WHERE trace_id = :trace"
            ).bindparams(trace=f"{h.trace_id}-1")
        )
    ).all()
    if len(rows) != 1:
        raise CheckFailedError("a question left no request row, or more than one")
    lane, duration, status = rows[0]
    if not lane or duration is None or duration < 0 or not status:
        raise CheckFailedError("a request row did not carry its lane, a duration and its status")

    after = await counts()
    if after.get(str(lane), 0) != before.get(str(lane), 0) + 1:
        raise CheckFailedError("the Service levels route did not count the question in its lane")
    if {one.value for one in Lane} - set(after):
        raise CheckFailedError("the Service levels route left a lane out of its list")


# --------------------------------------- 4. a change made while a run is going (M30.4.6, M30.4.7)
async def _a_run_whose_asker_changes(h: Harness, change: str) -> tuple[str, str, str]:
    """What a scripted model was told after a search that worked, after the asker's standing was
    changed between two of its tool calls, and for a tool nobody registered. `change` is `grant`
    or `person`: the asker's grant is taken away, or the asker is switched off."""
    import json

    from sqlalchemy import update

    from brain.govern_routes import retire_grant
    from brain.ops.acceptance_checks_runtime import (
        THE_TOOLS_GRANT,
        _proposal,
        _run,
        _scripted,
        _setup,
    )
    from brain.tables.identity import PrincipalRow

    setup = await _setup(h)

    async def alter(turn: int) -> None:
        if turn != 1:
            return
        if change == "grant":
            await h.execute(*h.attributed(), retire_grant(setup.asker, THE_TOOLS_GRANT))
        else:
            await h.execute(
                *h.attributed(),
                update(PrincipalRow)
                .where(PrincipalRow.id == setup.asker)
                .values(not_after=h.now - timedelta(minutes=1)),
            )

    nonexistent = json.dumps({"tool": "knowledge.nothing_registered_here", "arguments": {}})
    model = _scripted(
        [_proposal(setup.word), _proposal(setup.word), nonexistent, '{"answer": "done"}'],
        alter,
    )
    await _run(h, setup, model, 1)
    return (
        setup.word,
        str(model.shown[2][-1].content),
        str(model.shown[3][-1].content),
    )


@check(
    leaves=("M30.4.6",),
    sentence=(
        "An installed agent's run that searches documents, has its asker's grant taken away "
        "while it is going and searches again, is refused the second time in the words a model "
        "is given for a tool nobody registered; the first search returned the document."
    ),
)
async def a_policy_change_during_a_run_refuses_the_next_call(h: Harness) -> None:
    word, after, absent = await _a_run_whose_asker_changes(h, "grant")
    if word in after:
        raise CheckFailedError("a search made after the grant lapsed still returned the document")
    if after != absent:
        raise CheckFailedError("a refused tool was told differently from a tool nobody registered")


@check(
    leaves=("M30.4.7",),
    sentence=(
        "An installed agent's run that searches documents, whose asker is switched off while it "
        "is going, is refused on its next search in the words a model is given for a tool nobody "
        "registered."
    ),
)
async def a_person_switched_off_during_a_run_is_refused_at_the_next_call(h: Harness) -> None:
    word, after, absent = await _a_run_whose_asker_changes(h, "person")
    if word in after:
        raise CheckFailedError(
            "a search made after its asker was switched off returned the document"
        )
    if after != absent:
        raise CheckFailedError("a refused tool was told differently from a tool nobody registered")
