"""Install acceptance checks for the console's reports and its shared list behaviour: the landing
screen, usage and adoption, the questions nothing answered, the permission canaries, retention and
erasure, and a long list paged, searched, filtered, sorted and acted on several rows at once.

Every check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`).

**What a report counts is written by the store the request path writes it with.** A question is
recorded by `brain.ops.question_store.record` and a gap by `brain.ops.question_gap_store.
record_gap`, the two functions the gate's recorders call when a request finishes, and the tokens
a question used are a request ledger row as `brain.ops.telemetry_store` writes one. Every row is
a reserved person's, inside the check's transaction, so no real report ever counts it. See
`A_REPORT_IS_FED_BY_THE_STORES_THE_REQUEST_PATH_WRITES_WITH`.

**Each report is asked twice, by two readers whose grants differ only in their department.** A
report is a decision about which rows a reader may be told of, and the case that is always wrong
is the one where a narrower reader is told the wider reader's figure. So the department the check
writes into is shown to the reader holding it and absent, with no line and no count, for the one
holding the other reserved department.

Task ids: M27.2.1, M27.7.14, M27.7.18, M27.7.19, M27.7.24, M27.8.6
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 322

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the reports are fed through the stores the request path writes with.
A_REPORT_IS_FED_BY_THE_STORES_THE_REQUEST_PATH_WRITES_WITH: Final = (
    "A report counts what the gate's recorders wrote when requests finished. The check writes "
    "its questions, gaps and token rows through the same store functions, for reserved people "
    "inside its own transaction, so the report is read exactly as it reads a real request and "
    "no real report ever counts the check."
)

# ------------------------------------------------------------------------ the figures
#: The authorities and reads the checks' people hold. Restated rather than imported, so a change
#: to a route's authority fails its check instead of moving with it.
READS_USAGE: Final = "read:usage"
READS_QUESTIONS: Final = "read:question"
READS_EVALUATION: Final = "read:evaluation"
FILES_ERASURES: Final = "admin:erasure"
ENDS_SESSIONS: Final = "admin:session"

#: The model and the agent the check's questions are metered against.
MODEL: Final = "acceptance-model"
AGENT: Final = "acceptance-agent"

#: What a reader holds to be told which agents exist, the agent axis's own requirement.
READS_AGENTS: Final = "read:agent"

#: The tokens each of the check's questions used.
TOKENS_IN: Final = 120
TOKENS_OUT: Final = 30

#: How many questions the asker asks.
QUESTIONS: Final = 2

#: The source the check's unanswered question names as the one that would have answered it.
WOULD_HAVE_ANSWERED: Final = "xero"

#: The matter an erasure is filed under. A reference, never a description.
MATTER: Final = "ACCEPTANCE-1"


# ------------------------------------------------------------------------ the helpers
async def asked_questions(h: Harness, asker: str, department: str, n: int) -> list[str]:
    """`n` questions from `asker`, recorded with their tokens as the request path records them."""
    from brain.adoption import Asked
    from brain.core.lane import Lane
    from brain.core.principal import PrincipalKind
    from brain.gate.context import Channel, TrafficClass
    from brain.ops.question_store import record
    from brain.ops.telemetry import RequestStatus
    from brain.tables.telemetry import RequestTelemetryRow

    traces: list[str] = []
    at = datetime.now(UTC) - timedelta(minutes=5)
    for index in range(n):
        trace = f"{h.trace_id}-{department[-1]}{index}"
        async with h.sessions() as session:
            await record(
                session,
                Asked(
                    trace_id=trace,
                    principal_id=asker,
                    principal_kind=PrincipalKind.HUMAN,
                    channel=Channel.CONSOLE,
                    department=department,
                    at=at,
                ),
            )
            await session.execute(
                insert(RequestTelemetryRow).values(
                    received_at=at,
                    trace_id=trace,
                    traffic_class=TrafficClass.HUMAN_INTERACTIVE.value,
                    principal=asker,
                    entitlement_hash="0" * 32,
                    lane=Lane.ANSWER.value,
                    model=MODEL,
                    agent_version=AGENT,
                    tokens_in=TOKENS_IN,
                    tokens_out=TOKENS_OUT,
                    cache_hit=False,
                    status=RequestStatus.ANSWERED.value,
                    duration_ms=1.0,
                )
            )
            await session.commit()
        traces.append(trace)
    return traces


# ------------------------------------------------------ 1. the landing screen (M27.2.1)
@check(
    leaves=("M27.2.1",),
    sentence=(
        "A reader of the overview is answered, by the routes the landing screen calls, with the "
        "install's health and the week's answered questions counted over their own requests "
        "only, while a reader holding usage across the company is counted over everybody's; a "
        "person who may not open the overview is refused both."
    ),
)
async def the_landing_screen_counts_honestly_for_its_reader(h: Harness) -> None:
    from brain.console_overview_figures_routes import overview_figures
    from brain.console_overview_routes import overview

    await h.found_departments()
    mine, wide, other, asker = (h.principal(A, role) for role in ("own", "wide", "other", "asker"))
    await h.person(mine, department=A, grants=screen_grants("overview"))
    # The usage screen's whole read, plane included, as opening that screen would ask.
    everywhere = dict.fromkeys((*screen_grants("overview"), *screen_grants("usage")))
    await h.person(wide, department=A, grants=tuple(everywhere))
    await h.person(other, department=A)
    await h.person(asker, department=A)
    await asked_questions(h, mine, A, 1)
    await asked_questions(h, asker, A, QUESTIONS)
    console = console_for(h)
    if not await refused(overview(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person who may not open the overview was shown its health")
    if not await refused(overview_figures(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person who may not open the overview was shown its figures")

    shown = await overview(console.request(), await asking_as(h, mine))
    if shown.health.status not in ("ok", "degraded") or not shown.health.parts:
        raise CheckFailedError("the overview did not show the install's health")
    own = await overview_figures(console.request(), await asking_as(h, mine))
    if own.answered != 1:
        raise CheckFailedError("a reader without usage was not counted over their own requests")
    everyone = await overview_figures(console.request(), await asking_as(h, wide))
    if everyone.basis == own.basis or everyone.answered < 1 + QUESTIONS:
        raise CheckFailedError("a reader of usage across the company was not counted over all")


# --------------------------------------------------- 2. usage and adoption (M27.7.14)
@check(
    leaves=("M27.7.14",),
    sentence=(
        "Two questions asked by a person in acceptance_a are shown by the Usage and Adoption "
        "routes to a reader of usage in acceptance_a: the department's line, the person, and "
        "the tokens by person, department, model and agent; a reader of usage in acceptance_b "
        "is shown nothing of acceptance_a's."
    ),
)
async def usage_and_adoption_count_the_departments_a_reader_may_see(
    h: Harness,
) -> None:
    from brain.listing import ListAsked
    from brain.report_routes import adoption, usage

    await h.found_departments()
    asker, here, there = h.principal(A, "asker"), h.principal(A, "usage"), h.principal(B, "usage")
    await h.person(asker, department=A)
    await h.person(
        here,
        department=A,
        grants=((READS_USAGE, Scope.department(A)), (READS_AGENTS, Scope.unrestricted())),
    )
    await h.person(there, department=B, grants=((READS_USAGE, Scope.department(B)),))
    await asked_questions(h, asker, A, QUESTIONS)
    console = console_for(h)

    adopted = await adoption(console.request(), await asking_as(h, here), ListAsked(), days=1)
    line = next((one for one in adopted.items if one.department == A), None)
    if line is None or (line.questions, line.people) != (QUESTIONS, 1):
        raise CheckFailedError("Adoption did not show the department's questions and askers")
    elsewhere = await adoption(console.request(), await asking_as(h, there), ListAsked(), days=1)
    if any(one.department == A for one in elsewhere.items):
        raise CheckFailedError("Adoption showed a department to a reader of another")

    used = await usage(console.request(), await asking_as(h, here), days=1)
    departments = {one.department: one for one in used.departments or ()}
    if A not in departments or departments[A].questions != QUESTIONS:
        raise CheckFailedError("Usage did not show the department's questions")
    if not any(one.person == asker and one.questions == QUESTIONS for one in used.people or ()):
        raise CheckFailedError("Usage did not show the person who asked")
    by_model = next((one for one in used.tokens if one.axis == "model"), None)
    line_for_model = (
        None if by_model is None else next((x for x in by_model.lines if x.key == MODEL), None)
    )
    if line_for_model is None or line_for_model.tokens_in != QUESTIONS * TOKENS_IN:
        raise CheckFailedError("Usage did not show the tokens the questions used by model")
    by_agent = next((one for one in used.tokens if one.axis == "agent"), None)
    if by_agent is None or not any(
        x.key == AGENT and x.tokens_out == QUESTIONS * TOKENS_OUT for x in by_agent.lines
    ):
        raise CheckFailedError("Usage did not show the tokens the questions used by agent")
    by_person = next((one for one in used.tokens if one.axis == "person"), None)
    by_department = next((one for one in used.tokens if one.axis == "department"), None)
    if by_person is None or by_department is None:
        raise CheckFailedError("Usage did not break the tokens down by person and department")
    hidden = await usage(console.request(), await asking_as(h, there), days=1)
    if any(one.department == A for one in hidden.departments or ()) or any(
        one.person == asker for one in hidden.people or ()
    ):
        raise CheckFailedError("Usage showed a department's questions to a reader of another")


# --------------------------------------------- 3. the questions nothing answered (M27.7.18)
@check(
    leaves=("M27.7.18",),
    sentence=(
        "A question from acceptance_a that no connected source could answer, naming the source "
        "that would have, is shown by the Questions route to a reader of questions in "
        "acceptance_a by department and source, with the words said when nothing was found; a "
        "reader of questions in acceptance_b is not shown it."
    ),
)
async def a_question_nothing_answered_is_shown_to_its_department_s_reader(h: Harness) -> None:
    from brain.ops.acceptance_checks_tools import _install_registry
    from brain.ops.question_gap_store import Gap, record_gap
    from brain.report_routes import questions

    await h.found_departments()
    asker = h.principal(A, "asker")
    here, there = h.principal(A, "questions"), h.principal(B, "questions")
    await h.person(asker, department=A)
    # And the Connectors screen, so the source is one this reader may be told exists.
    named = dict.fromkeys(((READS_QUESTIONS, Scope.department(A)), *screen_grants("connectors")))
    await h.person(here, department=A, grants=tuple(named))
    await h.person(there, department=B, grants=((READS_QUESTIONS, Scope.department(B)),))
    [trace] = await asked_questions(h, asker, A, 1)
    async with h.sessions() as session:
        await record_gap(
            session,
            Gap(
                trace_id=trace,
                department=A,
                source=WOULD_HAVE_ANSWERED,
                at=datetime.now(UTC) - timedelta(minutes=5),
            ),
        )
        await session.commit()
    console = console_for(h)
    console.app.state.tools = _install_registry(h)

    shown = await questions(console.request(), await asking_as(h, here), days=1)
    line = next((one for one in shown.gaps if one.department == A), None)
    if line is None or line.source != WOULD_HAVE_ANSWERED or line.asked != 1:
        raise CheckFailedError("Questions did not show the unanswered question by its source")
    if not shown.answered_when_nothing_found.strip():
        raise CheckFailedError("Questions did not say what a person is told when nothing is found")
    hidden = await questions(console.request(), await asking_as(h, there), days=1)
    if any(one.department == A for one in hidden.gaps):
        raise CheckFailedError("Questions showed a department's gap to a reader of another")


# --------------------------------------------- 4. the permission canaries (M27.7.19)
@check(
    leaves=("M27.7.19",),
    sentence=(
        "A run of the permission canaries recorded by the worker is shown by the Quality route, "
        "with its outcome and that the worker starts them, to a reader of evaluations; a person "
        "without that grant is shown no run."
    ),
)
async def the_permission_canaries_last_run_is_shown_to_their_reader(h: Harness) -> None:
    from brain.console.quality_view import CANARY_CONTROL
    from brain.ops.acceptance_operations_console_2 import as_login
    from brain.report_routes import quality
    from brain.tables.schedule import ControlRunRow

    await h.found_departments()
    reader, other = h.principal(A, "quality"), h.principal(A, "other")
    await h.person(reader, department=A, grants=((READS_EVALUATION, Scope.unrestricted()),))
    await h.person(other, department=A)
    started = datetime.now(UTC) - timedelta(seconds=30)
    await as_login(
        h,
        insert(ControlRunRow).values(
            name=CANARY_CONTROL,
            started_at=started,
            finished_at=started + timedelta(seconds=1),
            outcome="ok",
        ),
    )
    console = console_for(h)
    shown = await quality(console.request(), await asking_as(h, reader), days=1)
    if shown.last_canary_run is None or shown.last_canary_run.started_at != started:
        raise CheckFailedError("Quality did not show the canaries' newest run")
    if not shown.canaries_started:
        raise CheckFailedError("Quality did not say that the worker starts the canaries")
    hidden = await quality(console.request(), await asking_as(h, other), days=1)
    if hidden.last_canary_run is not None or hidden.runs:
        raise CheckFailedError("Quality showed the canaries' runs to a person without the grant")


# --------------------------------------------- 5. retention and erasure (M27.7.24)
@check(
    leaves=("M27.7.24",),
    sentence=(
        "An administrator holding the erasure authority files an erasure of a reserved person "
        "through the Retention screen's route, and it is shown queued for the worker, with how "
        "long each class of record is kept and the exports log; a reader of the screen without "
        "the authority cannot file one, and a person without the screen is refused."
    ),
)
async def an_erasure_is_filed_and_waits_in_the_deletion_queue(h: Harness) -> None:
    from brain.erasure_routes import (
        ErasureBody,
        erasure_queue,
        exports_taken,
        file_erasure,
        retention_controls,
    )

    await h.found_departments()
    admin, reader = h.principal(A, "erasure"), h.principal(A, "retention")
    subject, other = h.principal(A, "subject"), h.principal(A, "other")
    await h.person(
        admin,
        department=A,
        grants=((FILES_ERASURES, Scope.unrestricted()), *screen_grants("retention")),
    )
    await h.person(reader, department=A, grants=screen_grants("retention"))
    await h.person(subject, department=A)
    await h.person(other, department=A)
    console = console_for(h)
    if not await refused(erasure_queue(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person without the Retention screen was shown the queue")
    body = ErasureBody(subject_id=subject, reason_reference=MATTER)
    if not await refused(
        file_erasure(console.request("POST"), body, await asking_as(h, reader, strong=True))
    ):
        raise CheckFailedError("a reader without the authority filed an erasure")

    controls = await retention_controls(await asking_as(h, admin, strong=True))
    if not controls.may_erase or not controls.kept:
        raise CheckFailedError("Retention did not say what is kept and who may erase")
    async with traced(h, 1):
        filed = await file_erasure(
            console.request("POST"), body, await asking_as(h, admin, strong=True)
        )
    queue = await erasure_queue(console.request(), await asking_as(h, admin, strong=True))
    mine = [one for one in queue.requests if one.request_id == filed.request_id]
    if len(mine) != 1 or mine[0].subject_id != subject or mine[0].finished_at is not None:
        raise CheckFailedError("an erasure filed from the console was not waiting in the queue")
    if mine[0].requested_by != admin:
        raise CheckFailedError("a queued erasure did not say who filed it")
    await exports_taken(console.request(), await asking_as(h, admin, strong=True))


# --------------------------------------------- 6. a long list and several at once (M27.8.6)
@check(
    leaves=("M27.8.6",),
    sentence=(
        "Three sign-ins in acceptance_a are listed by the Sessions route to an administrator of "
        "acceptance_a two to a page, filtered by department, searched and sorted newest first; "
        "ending several at once ends the three and refuses one in acceptance_b, each its own "
        "decision, and the list then holds none of them."
    ),
)
async def a_long_list_pages_searches_sorts_and_acts_on_several(h: Harness) -> None:
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_channel_framework import _signed_in
    from brain.session_routes import SessionsEnding, end_sessions, sessions_page

    await h.found_departments()
    admin = h.principal(A, "sessions")
    grants = ((ENDS_SESSIONS, Scope.department(A)), *screen_grants("sessions", Scope.department(A)))
    await h.person(admin, department=A, grants=grants)
    people = [h.principal(A, f"member{n}") for n in range(3)]
    outsider = h.principal(B, "member")
    opened: list[str] = []
    for n, person in enumerate([*people, outsider]):
        await h.person(person, department=A if person != outsider else B)
        session_id = f"acceptance-{h.run}-{n}"
        await _signed_in(h, person, session_id, h.now - timedelta(minutes=10 - n))
        opened.append(session_id)

    console = console_for(h)
    asking = await asking_as(h, admin, strong=True)
    narrowed = (f"department:{A}",)
    first = await sessions_page(
        console.request(),
        asking,
        ListAsked(limit=2, filters=narrowed, sort="-signed_in_at", search="Acceptance check"),
    )
    if len(first.items) != 2 or first.next_cursor is None:
        raise CheckFailedError("a long list was not paged at the size asked for")
    if [one.session_id for one in first.items] != [opened[2], opened[1]]:
        raise CheckFailedError("a long list was not sorted newest first")
    rest = await sessions_page(
        console.request(),
        asking,
        ListAsked(
            limit=2,
            cursor=first.next_cursor,
            filters=narrowed,
            sort="-signed_in_at",
            search="Acceptance check",
        ),
    )
    if [one.session_id for one in rest.items] != [opened[0]] or rest.next_cursor is not None:
        raise CheckFailedError("the next page of a long list did not carry on where it stopped")

    async with traced(h, 1):
        ended = await end_sessions(
            console.request("POST"), SessionsEnding(session_ids=opened), asking
        )
    outcomes = {one.session_id: one.ended for one in ended.outcomes}
    if [outcomes.get(one) for one in opened] != [True, True, True, False]:
        raise CheckFailedError("ending several at once did not decide each row alone")
    after = await sessions_page(console.request(), asking, ListAsked(limit=200, filters=narrowed))
    if any(one.session_id in opened for one in after.items):
        raise CheckFailedError("a session ended several at once was still listed")
