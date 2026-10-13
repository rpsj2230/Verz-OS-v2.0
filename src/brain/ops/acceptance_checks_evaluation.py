"""Install checks for the evaluation gate's two stores of evidence: where a canary may be found, and
that the scheduled canary run is owed, is run and alerts.

**A canary planted in the restricted column of a real upload, asked about through `/answer`'s own
route, and then looked for in every table on the install.** `brain.ops.canaries.scan_stores`
says the same check can be made over any set of texts, and its own docstring says why the answer is
the least likely place to leak: it is the one surface with a redactor in front of it, while a trace
step, a stored payload and a thread are written by code that was thinking about something else.
The fixture suite scans the stores it knows. An install holds more of them than a fixture does, so
this check asks `brain.ops.index_audit.tables_holding`, which reads **every** table, and says which
may hold the value: the table the upload was written to and nothing else. A new table that quietly
kept a payload would appear in that list on the next run and fail it, with no edit here.

**The value is planted in the check's own rolled-back transaction, in a reserved department.** That
is not what `brain.ops.canaries.PRODUCTION_NEVER_PLANTS_A_CANARY` refuses: the scheduled production
run writes nothing into a client's records, and this check's value is gone with its transaction.

**The scheduled run is shown from the install's own record of it.** The canary control's cadence is
read from the registry and must be the one `brain.ops.canaries` declares, the product's own
functions run over the install's reaches must find nothing, and a red run, built from a finding made
for the check, must raise with a sentence that names nothing and write an alert line that names the
field and never the value. What the install's worker has really done is read from its own run
table: a worker that has never started the canaries makes the check not run, and a last run that
was red fails it.

Task ids: M28.2.2, M28.2.4
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_checks_connectors import _search
from brain.ops.acceptance_checks_signal_log import _asked, _thread_text
from brain.ops.acceptance_checks_tables import (
    ASKED_COLUMNS,
    ASKED_HEADINGS,
    SELL_PRICE,
    WITHHELD,
    A,
    _administrator,
    _apply,
    _price_list,
    _upload,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 872

#: The only table a planted value may be found in: where the upload was written.
WHERE_THE_UPLOAD_LIVES: Final = frozenset({"know.classified_row"})

THE_PERMITTED_FIGURE_WAS_NOT_ANSWERED: Final = (
    "a reader of a price list was not told the sell price they may read"
)
A_CANARY_REACHED_AN_ANSWER: Final = "a restricted column's canary reached an answer or a thread"
A_CANARY_WAS_KEPT_ELSEWHERE: Final = (
    "a restricted column's canary was found in a table other than the upload's own"
)
THE_CANARY_WAS_NEVER_UPLOADED: Final = "the planted canary was not in the table it was uploaded to"
THE_CADENCE_MOVED: Final = "the canary control's cadence is not the one the canaries declare"
A_FIRST_RUN_WAS_NOT_OWED: Final = "a run that has never happened was not owed"
A_FRESH_RUN_WAS_OWED: Final = "a run that has just finished was owed again"
THE_RUN_WAS_RED: Final = "the permission canaries found a defect over this install's reaches"
A_RED_RUN_DID_NOT_RAISE: Final = "a run that found a defect did not raise"
A_RED_RUN_NAMED_ITS_SUBJECT: Final = "a red run's recorded sentence named what it found"
THE_ALERT_WAS_NOT_RAISED: Final = "a red run's finding was not written to the alert, by field"
THE_ALERT_CARRIED_THE_VALUE: Final = "a red run's alert carried the value that leaked"
THE_WORKER_HAS_NOT_STARTED_THEM: Final = (
    "this install's worker has not started the permission canaries yet, so no scheduled run is "
    "on record to judge"
)
THE_LAST_SCHEDULED_RUN_WAS_RED: Final = "the install's own last scheduled canary run was red"


# ---------------------------------------------------------------------------- M28.2.2
@check(
    leaves=("M28.2.2",),
    sentence=(
        "A canary planted in the restricted columns of a price list uploaded in acceptance_a is "
        "asked about through Ask as a reader holding the table and not the columns: the sell "
        "price is answered, the canary is in no answer and no thread, and a search of every table "
        "on the install finds it in the upload's own table and nowhere else."
    ),
)
async def a_planted_canary_is_found_in_no_store_but_the_upload_s_own(h: Harness) -> None:
    from brain.gate.streaming import frames
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.knowledge.columns import ColumnAccess, table_capability
    from brain.ops.acceptance_threads import _web
    from brain.ops.canaries import scan_stores

    await h.found_departments()
    admin = await _administrator(h, A)
    prices = _price_list(h, "canary", ASKED_HEADINGS, ASKED_COLUMNS)
    await _upload(h, admin, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    opened = await _apply(h, admin, prices.entity, "department", ColumnAccess.OPEN)
    if not opened.applied:
        raise CheckFailedError("an uploaded price list's department column could not be opened")
    service = prices.rows[0]
    canaries = {f"{prices.entity}.{column}": service[column] for column in WITHHELD}

    member = h.principal(A, "canary_reader")
    await h.person(member, department=A, grants=_in(A, table_capability(prices.entity).value))
    app = await _web(h)
    told: list[str] = []
    thread: str | None = None
    for n, column in enumerate((SELL_PRICE, *WITHHELD), start=1):
        question = QUESTION_SHAPES[0].format(label=label_of(column), slot=service["name"])
        answered, thread, _ = await _asked(h, app, member, question, thread, n)
        told.append(frames(answered.frames))
    if service[SELL_PRICE] not in told[0]:
        raise CheckFailedError(THE_PERMITTED_FIGURE_WAS_NOT_ANSWERED)
    kept = [await _thread_text(h, member, thread)] if thread is not None else []
    if scan_stores(
        asker=member,
        question_id="acceptance",
        stores={"answer": told, "thread": kept},
        canaries=canaries,
    ):
        raise CheckFailedError(A_CANARY_REACHED_AN_ANSWER)

    for token in canaries.values():
        holding = set(await _search(h, token))
        if not holding:
            raise CheckFailedError(THE_CANARY_WAS_NEVER_UPLOADED)
        if not holding <= WHERE_THE_UPLOAD_LIVES:
            raise CheckFailedError(A_CANARY_WAS_KEPT_ELSEWHERE)


# ---------------------------------------------------------------------------- M28.2.4
@check(
    leaves=("M28.2.4",),
    sentence=(
        "The permission canaries are scheduled at the cadence they declare, a run that has never "
        "happened is owed and a fresh one is not, the product's own run over this install's "
        "reaches finds nothing, a run that finds a defect raises with a sentence naming nothing "
        "and writes an alert naming the field and never the value, and the worker has started "
        "them, last without finding a defect."
    ),
)
async def the_scheduled_canary_run_is_owed_runs_and_alerts(h: Harness) -> None:
    from brain.console.quality_view import CANARY_CONTROL
    from brain.ops.canaries import (
        CANARY_INTERVAL_SECONDS,
        CanaryFinding,
        Finding,
        alert_lines,
        due,
    )
    from brain.ops.canary_run import (
        ALERT_PREFIX,
        RED_RUN_DETAIL,
        CanariesFoundError,
        CanaryRun,
        minted_value,
        raise_the_alert,
        run_canaries,
        verdict,
    )
    from brain.ops.controls import CONTROLS

    control = next((one for one in CONTROLS if one.name == CANARY_CONTROL), None)
    if control is None or control.every != timedelta(seconds=CANARY_INTERVAL_SECONDS):
        raise CheckFailedError(THE_CADENCE_MOVED)
    now = datetime.now(UTC)
    if not due(last_run=None, now=now):
        raise CheckFailedError(A_FIRST_RUN_WAS_NOT_OWED)
    if due(last_run=now, now=now):
        raise CheckFailedError(A_FRESH_RUN_WAS_OWED)

    green = await run_canaries(
        h.sessions, tool_source=h.settings.tool_source, now=h.now, value=minted_value()
    )
    try:
        verdict(green)
    except CanariesFoundError:
        raise CheckFailedError(THE_RUN_WAS_RED) from None

    field, value = "price_list.cost", h.word()
    red = CanaryRun(
        findings=(
            CanaryFinding(
                kind=Finding.LEAKED, asker="acceptance", question_id="acceptance", subject=field
            ),
        ),
        rules_asked=(),
    )
    try:
        verdict(red)
    except CanariesFoundError as found:
        if str(found) != RED_RUN_DETAIL or field in str(found):
            raise CheckFailedError(A_RED_RUN_NAMED_ITS_SUBJECT) from None
        stream = io.StringIO()
        raise_the_alert(found.alert, stream)
        said = stream.getvalue()
        if (
            ALERT_PREFIX not in said
            or field not in said
            or found.alert != alert_lines(red.findings)
        ):
            raise CheckFailedError(THE_ALERT_WAS_NOT_RAISED) from None
        if value in said:
            raise CheckFailedError(THE_ALERT_CARRIED_THE_VALUE) from None
    else:
        raise CheckFailedError(A_RED_RUN_DID_NOT_RAISE)

    last = (
        await h.execute(
            text(
                "SELECT outcome FROM ops.control_run WHERE name = :name"
                " ORDER BY started_at DESC LIMIT 1"
            ).bindparams(name=CANARY_CONTROL)
        )
    ).scalar_one_or_none()
    if last is None:
        raise CheckNotRunError(THE_WORKER_HAS_NOT_STARTED_THEM)
    if last != "ok":
        raise CheckFailedError(THE_LAST_SCHEDULED_RUN_WAS_RED)
