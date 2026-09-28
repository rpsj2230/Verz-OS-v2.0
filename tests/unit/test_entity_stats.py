"""The arithmetic under an entity's detail page and the landing screen's Needs you.

Every figure is asserted over rows built for the case, including rows the reader may not be
counted over, so a function that counted everything would fail the narrowing tests and one that
counted nothing would fail the positive ones.

Dates are 2027, far from any wall clock, because nothing here is about the present: `NOW` only
places rows inside or outside a window.

Task ids: M27.15.27, M27.15.33, M27.2.1, M27.15.17
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.console.entity_stats import (
    LONGEST,
    PERIODS,
    Attempt,
    Delivery,
    Run,
    attempt_figures,
    bound_people,
    counted_runs,
    delivery_figures,
    last_active,
    newest,
    periods,
    run_figures,
    skill_figures,
    versions_added,
)
from brain.console.needs_you import (
    OPENS,
    UNCOUNTED_QUEUES,
    NeedsYouError,
    Queue,
    Waiting,
    halt_state,
    needs_you,
    waiting,
    worker_last_seen,
)
from brain.console.workspace import RANGE_DAYS, Basis, Range
from brain.ops.connector_sync import SyncOutcome
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.ops.telemetry import RequestStatus
from brain.tables.channel import DeliveryOutcome, Direction

NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)
WEEK_AGO = NOW - timedelta(days=7)
MONTH_AGO = NOW - timedelta(days=30)
READER = "p_reader"
COLLEAGUE = "p_colleague"


def run(principal: str, days_ago: float, status: RequestStatus, ms: float) -> Run:
    return Run(
        principal_id=principal, at=NOW - timedelta(days=days_ago), status=status, duration_ms=ms
    )


RUNS = (
    run(READER, 1, RequestStatus.ANSWERED, 100.0),
    run(READER, 2, RequestStatus.NOTHING_RETURNED, 300.0),
    run(READER, 20, RequestStatus.ANSWERED, 500.0),
    run(COLLEAGUE, 1, RequestStatus.ANSWERED, 900.0),
    run(COLLEAGUE, 3, RequestStatus.FAILED, 700.0),
    run(COLLEAGUE, 45, RequestStatus.ANSWERED, 50.0),
)


def test_everybodys_figures_count_every_request_in_the_window_and_none_outside_it() -> None:
    """The positive case over the widest basis, and the window's edge.

    Delete this and a function that counted nothing passes every narrowing test below."""
    week = run_figures(RUNS, caller_id=READER, basis=Basis.EVERYONE, since=WEEK_AGO, until=NOW)
    month = run_figures(RUNS, caller_id=READER, basis=Basis.EVERYONE, since=MONTH_AGO, until=NOW)

    assert (week.runs, week.answered, week.nothing_returned) == (4, 2, 1)
    assert week.p50_latency_ms == 500.0
    assert (month.runs, month.answered, month.nothing_returned) == (5, 3, 1)
    assert month.p50_latency_ms == 500.0


def test_on_the_narrower_basis_a_colleagues_request_moves_no_figure() -> None:
    """Delete this and the own basis counts a colleague's requests, which is their activity
    published to a reader who may not read the usage screen."""
    mine = run_figures(RUNS, caller_id=READER, basis=Basis.OWN, since=MONTH_AGO, until=NOW)
    without_colleague = run_figures(
        [one for one in RUNS if one.principal_id == READER],
        caller_id=READER,
        basis=Basis.OWN,
        since=MONTH_AGO,
        until=NOW,
    )

    assert mine == without_colleague
    assert (mine.runs, mine.answered, mine.nothing_returned) == (3, 2, 1)
    assert mine.p50_latency_ms == 300.0
    assert all(
        one.principal_id == READER
        for one in counted_runs(RUNS, caller_id=READER, basis=Basis.OWN, since=MONTH_AGO, until=NOW)
    )


def test_no_requests_is_nought_runs_and_no_median_rather_than_a_median_of_nought() -> None:
    """Delete this and an idle agent reports a median of 0 ms, which reads as very fast."""
    empty = run_figures((), caller_id=READER, basis=Basis.EVERYONE, since=WEEK_AGO, until=NOW)

    assert (empty.runs, empty.p50_latency_ms) == (0, None)
    assert (
        last_active((), caller_id=READER, basis=Basis.EVERYONE, since=WEEK_AGO, until=NOW) is None
    )


def test_last_active_is_the_newest_request_the_reader_may_be_counted_over() -> None:
    """Delete this and the last activity a narrower reader sees is a colleague's, which dates
    somebody else's work for them."""
    everyone = last_active(RUNS, caller_id=READER, basis=Basis.EVERYONE, since=MONTH_AGO, until=NOW)
    own = last_active(
        [run(COLLEAGUE, 0.5, RequestStatus.ANSWERED, 1.0), *RUNS],
        caller_id=READER,
        basis=Basis.OWN,
        since=MONTH_AGO,
        until=NOW,
    )

    assert everyone == NOW - timedelta(days=1)
    assert own == NOW - timedelta(days=1)


def test_the_periods_are_seven_and_thirty_days_from_the_window_the_headline_uses() -> None:
    """Delete this and a thirty-day figure here can start on a different day from the agent
    headline's, so the two disagree about one agent's month."""
    spans = periods(NOW)

    assert PERIODS == (Range.SEVEN_DAYS, Range.THIRTY_DAYS)
    assert LONGEST is Range.THIRTY_DAYS
    assert [(one, NOW - start, end) for one, start, end in spans] == [
        (Range.SEVEN_DAYS, timedelta(days=RANGE_DAYS[Range.SEVEN_DAYS]), NOW),
        (Range.THIRTY_DAYS, timedelta(days=RANGE_DAYS[Range.THIRTY_DAYS]), NOW),
    ]


def test_skill_figures_count_distinct_agents_and_versions_of_that_name_only() -> None:
    """Delete this and a pin of another skill, or two pins of one agent, inflate the figure."""
    pins = [
        ("agent_a", "triage", "d1"),
        ("agent_a", "triage", "d1"),
        ("agent_b", "triage", "d2"),
        ("agent_c", "invoicing", "d9"),
    ]
    library = [("triage", "d1"), ("triage", "d2"), ("triage", "d3"), ("invoicing", "d9")]

    figures = skill_figures("triage", pins, library)
    hidden_library = skill_figures("triage", pins, None)

    assert (figures.agents_pinned, figures.pinned_versions, figures.versions) == (2, 2, 3)
    assert hidden_library.versions is None
    assert (hidden_library.agents_pinned, hidden_library.pinned_versions) == (2, 2)


def test_versions_added_counts_arrivals_of_that_name_inside_the_window() -> None:
    """Delete this and an old version or another skill's arrival counts as this week's edit."""
    submitted = [
        ("triage", NOW - timedelta(days=2)),
        ("triage", NOW - timedelta(days=12)),
        ("invoicing", NOW - timedelta(days=1)),
    ]

    assert versions_added("triage", submitted, since=WEEK_AGO, until=NOW) == 1
    assert versions_added("triage", submitted, since=MONTH_AGO, until=NOW) == 2


def test_attempt_figures_keep_a_quota_wait_apart_from_a_failure() -> None:
    """Delete this and a source that asked to be left alone is reported as failing."""
    attempts = [
        Attempt(at=NOW - timedelta(days=1), outcome=SyncOutcome.SYNCED),
        Attempt(at=NOW - timedelta(days=2), outcome=SyncOutcome.FAILED),
        Attempt(at=NOW - timedelta(days=3), outcome=SyncOutcome.QUOTA),
        Attempt(at=NOW - timedelta(days=10), outcome=SyncOutcome.FAILED),
    ]

    week = attempt_figures(attempts, since=WEEK_AGO, until=NOW)
    month = attempt_figures(attempts, since=MONTH_AGO, until=NOW)

    assert (week.attempts, week.read_to_the_end, week.failures, week.quota_waits) == (3, 1, 1, 1)
    assert (month.attempts, month.failures) == (4, 2)


def test_delivery_figures_separate_what_was_received_sent_refused_and_unknown() -> None:
    """Delete this and an outbound message the vendor may have delivered is counted as failed,
    which invites a resend of a message that arrived."""
    deliveries = [
        Delivery(Direction.INBOUND, DeliveryOutcome.ACCEPTED, NOW - timedelta(days=1)),
        Delivery(Direction.INBOUND, DeliveryOutcome.REDELIVERED, NOW - timedelta(days=1)),
        Delivery(Direction.INBOUND, DeliveryOutcome.REFUSED, NOW - timedelta(days=1)),
        Delivery(Direction.OUTBOUND, DeliveryOutcome.SENT, NOW - timedelta(days=1)),
        Delivery(Direction.OUTBOUND, DeliveryOutcome.REFUSED, NOW - timedelta(days=2)),
        Delivery(Direction.OUTBOUND, DeliveryOutcome.UNKNOWN, NOW - timedelta(days=2)),
        Delivery(Direction.OUTBOUND, DeliveryOutcome.SENT, NOW - timedelta(days=20)),
    ]

    week = delivery_figures(deliveries, since=WEEK_AGO, until=NOW)
    month = delivery_figures(deliveries, since=MONTH_AGO, until=NOW)

    assert (week.received, week.sent, week.failed, week.unknown, week.refused_inbound) == (
        1,
        1,
        1,
        1,
        1,
    )
    assert month.sent == 2


def test_bound_people_is_everybody_distinct_or_whether_the_reader_is_bound() -> None:
    """Delete this and the narrower basis counts colleagues' bindings, which is a census of who
    uses a channel given to somebody who may not read people."""
    bound = [READER, COLLEAGUE, COLLEAGUE, "p_third"]

    assert bound_people(bound, caller_id=READER, basis=Basis.EVERYONE) == 3
    assert bound_people(bound, caller_id=READER, basis=Basis.OWN) == 1
    assert bound_people([COLLEAGUE], caller_id=READER, basis=Basis.OWN) == 0
    assert newest([None, NOW, WEEK_AGO]) == NOW
    assert newest([None]) is None


def test_no_result_type_carries_a_field_named_like_a_count_of_what_was_withheld() -> None:
    """Delete this and a `total` beside a narrowed count arrives in a later edit as a better
    screen, and it is the count of what the reader was not shown."""
    from brain.console import entity_stats, needs_you

    types = [
        getattr(module, name)
        for module in (entity_stats, needs_you)
        for name in dir(module)
        if isinstance(getattr(module, name), type)
        and hasattr(getattr(module, name), "__dataclass_fields__")
    ]

    assert types
    assert [
        f"{one.__name__}.{field.name}"
        for one in types
        for field in fields(one)
        if field.name in NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
    ] == []


# ------------------------------------------------------------------------------ needs you
def test_needs_you_drops_a_queue_the_reader_may_not_open_and_orders_by_the_register() -> None:
    """Delete this and a queue the reader may not open is drawn as nought, which says it exists
    and is being kept from them."""
    shown = needs_you(
        [
            waiting(Queue.SKILL_REVIEWS, ["a", "b"]),
            None,
            waiting(Queue.APPROVALS, ["x"], at_least=True),
        ]
    )

    assert [(one.queue, one.waiting, one.at_least) for one in shown] == [
        (Queue.APPROVALS, 1, True),
        (Queue.SKILL_REVIEWS, 2, False),
    ]
    assert shown[0].opens == OPENS[Queue.APPROVALS]


def test_needs_you_refuses_two_figures_for_one_queue() -> None:
    """Delete this and a reader's own count beside everybody's is rendered, and the difference
    is other people's work."""
    with pytest.raises(NeedsYouError, match="two figures"):
        needs_you([waiting(Queue.APPROVALS, ["x"]), waiting(Queue.APPROVALS, ["x", "y"])])


def test_a_queue_figure_is_counted_from_rows_and_never_negative() -> None:
    """Delete this and a figure handed in from elsewhere, or a nonsense one, reaches the page."""
    with pytest.raises(NeedsYouError, match="not a count"):
        Waiting(queue=Queue.ELEVATION, waiting=-1)
    assert waiting(Queue.ELEVATION, iter(range(3))).waiting == 3


def test_every_queue_opens_a_page_and_the_uncounted_ones_are_queues() -> None:
    """Delete this and a queue added to the register has no page to open, or an uncounted
    sentence names a queue that does not exist."""
    assert set(OPENS) == set(Queue)
    assert {one.figure for one in UNCOUNTED_QUEUES} <= {one.value for one in Queue}
    assert all(one.why.strip() for one in UNCOUNTED_QUEUES)


def test_the_worker_was_last_seen_at_the_newest_start_or_finish() -> None:
    """Delete this and a run still in progress, which has no finish, hides the newest evidence."""
    assert worker_last_seen([(WEEK_AGO, NOW - timedelta(days=6)), (NOW, None)]) == NOW
    assert worker_last_seen([]) is None


def test_the_state_is_the_halts_whose_latest_act_is_a_halt_and_unknown_on_a_bad_row() -> None:
    """Delete this and a resumed halt is read as in force, or a row that does not construct is
    dropped, which tells a reader nothing is stopped while that halt refuses their work."""
    rows = [
        ("everything", "", "resume", "u_a", "lifted after the incident", NOW),
        ("department", "finance", "halt", "u_a", "a finance incident reason", NOW),
    ]

    state = halt_state(rows)
    broken = halt_state([*rows, ("department", "", "halt", "u_a", "names no department", NOW)])

    assert [(one.scope.value, one.target) for one in state.halts] == [("department", "finance")]
    assert state.known is True
    assert (broken.halts, broken.known) == ((), False)
