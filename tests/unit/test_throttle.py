"""What one call's facts mean, and the status that is not a status.

`brain.connectors.throttle.classify` is where a transport's answer becomes an outcome, and
every module downstream of it acts on the outcome rather than on the facts. That makes the
direction of its mistakes asymmetric: reading a failure as a success tells
`brain.ops.idempotency.state_after_call` that a side effect landed, and nothing afterwards asks
again.

This file exists for the branch that was missing. The rest of the module's behaviour is
exercised through the connector tests that call it, which is why there is no attempt here to
cover the bucket or the breaker.

Task ids: M11.3.1
"""

from __future__ import annotations

import pytest

from brain.connectors.throttle import (
    HTTP_CLIENT_ERROR,
    HTTP_SERVER_ERROR,
    HTTP_SMALLEST_STATUS,
    HTTP_TOO_MANY_REQUESTS,
    CallOutcome,
    classify,
)
from brain.ops.idempotency import state_after_call


def test_a_status_below_the_smallest_real_one_is_not_a_success() -> None:
    """**`classify(status=0)` was `OK`.** Several HTTP clients report `0` or `-1` instead of
    raising when the connection failed, the request timed out or the response never parsed,
    and every one of those is exactly what `connection_failed` means. The branch order checks
    real failures first and then falls through to success, and a fall-through is a success by
    default, so a number smaller than four hundred was a successful call.

    Zero, negative and just below the smallest real status, because a check written against
    zero alone passes on the other two and clients differ about which they report.

    Delete this and a connection failure to a source is recorded as an answer from it."""
    for nothing_answered in (0, -1, -503, HTTP_SMALLEST_STATUS - 1):
        assert classify(status=nothing_answered) is CallOutcome.UNAVAILABLE


def test_the_smallest_real_status_and_everything_above_it_still_reads_as_it_did() -> None:
    """The sibling, and the reason the boundary is one hundred rather than two hundred. A 1xx
    is a real answer from a real source, and a rule written against the success range would
    have quietly reclassified it.

    The four bands are asserted together because the branch order is the rule: a quota refusal
    is a 4xx and is checked before the generic client-error branch, and losing that ordering
    would make a retryable refusal permanent.

    Delete this and the guard above can be widened until it swallows a real status."""
    assert classify(status=HTTP_SMALLEST_STATUS) is CallOutcome.OK
    assert classify(status=200) is CallOutcome.OK
    assert classify(status=HTTP_TOO_MANY_REQUESTS) is CallOutcome.QUOTA
    assert classify(status=HTTP_CLIENT_ERROR) is CallOutcome.REJECTED
    assert classify(status=HTTP_SERVER_ERROR) is CallOutcome.UNAVAILABLE


def test_a_status_that_never_came_is_still_the_caller_saying_so() -> None:
    """`status=None` with neither flag set is a caller who has no status to give, and it stays
    a success: that is the shape a connector uses when the transport answered and the status
    is not the thing being classified.

    Asserted so the new guard cannot be written as `not status`, which is true for `None` as
    well as for zero and would change this answer.

    Delete this and the guard above can be written with a falsiness check, which is the one
    spelling that also catches the case this test protects."""
    assert classify() is CallOutcome.OK
    assert classify(timed_out=True) is CallOutcome.UNAVAILABLE
    assert classify(connection_failed=True) is CallOutcome.UNAVAILABLE


def test_a_failed_connection_reported_as_a_number_does_not_record_a_side_effect() -> None:
    """The consequence, asserted through the module that acts on the outcome rather than
    stopping at the outcome itself. `state_after_call` turns an `OK` into `SUCCEEDED`, which
    is the record saying the filing happened, and nothing downstream asks the source again.

    This is what made the missing branch worth a test rather than a tidy-up: the failure was
    not "an outcome is wrong", it was "a side effect is recorded as having happened because
    the connection to the source failed".

    Delete this and the two modules can drift apart, with `classify` correct and the
    consequence untested."""
    unreachable = classify(status=0)
    answered = classify(status=200)

    assert state_after_call(unreachable) is not state_after_call(answered)


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (99, CallOutcome.UNAVAILABLE),
        (100, CallOutcome.OK),
        (399, CallOutcome.OK),
        (400, CallOutcome.REJECTED),
        (428, CallOutcome.REJECTED),
        (429, CallOutcome.QUOTA),
        (430, CallOutcome.REJECTED),
        (499, CallOutcome.REJECTED),
        (500, CallOutcome.UNAVAILABLE),
    ],
)
def test_each_band_begins_where_the_standard_says_it_does(
    status: int, outcome: CallOutcome
) -> None:
    """Every boundary, written as a literal on both sides.

    The first version of this asserted `classify(b) is not classify(b - 1)` for each constant,
    which is the constant compared against itself: moving `HTTP_CLIENT_ERROR` to 401 moved
    both sides of every comparison and all four mutations survived. A status code is defined
    by RFC 9110 rather than by this repository, so a literal here is anchored to something
    outside the module, which is what the anchor has to be.

    429 is surrounded on both sides deliberately. It is a 4xx and is checked before the
    generic client-error branch, so a quota refusal and a rejection are one number apart, and
    losing that ordering makes a retryable refusal permanent.

    Delete this and the four constants can each drift by one with every other test still
    passing, because every other test uses round numbers well inside a band."""
    assert classify(status=status) is outcome


def test_the_bands_are_the_numbers_the_standard_gives_them() -> None:
    """The constants themselves, against literals rather than against each other. This is the
    half the parametrised test above cannot do: it proves the behaviour is right at those
    numbers, and this proves the numbers are the ones anybody reading the module would expect
    to find.

    Delete this and a renamed constant can be given a different value with the behaviour test
    still passing, because the behaviour test never names a constant."""
    assert HTTP_SMALLEST_STATUS == 100
    assert HTTP_CLIENT_ERROR == 400
    assert HTTP_TOO_MANY_REQUESTS == 429
    assert HTTP_SERVER_ERROR == 500
