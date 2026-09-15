"""Which database a console read goes to, and when its page must say it is behind.

Pure policy, so every case here is a value and an instant. Each band of lag is tested from both
sides of its threshold, and each refusal to use the replica has a sibling proving the replica is
used when nothing is wrong, because a policy that always answered "primary" would pass every
refusal in this file and route nothing.

Instants are pinned in 2999, far outside any wall clock, because nothing here is about the
present: only differences between two instants are.

Task ids: M36.1.2.2, M36.1.2.3
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from brain.console.read_replica import (
    A_REPLICA_READ_PAST_THE_BANNER_THRESHOLD_ALWAYS_CARRIES_ONE,
    BANNER_AFTER,
    FALL_BACK_AFTER,
    MEASURE_EVERY,
    MEASURE_TIMEOUT,
    ConsoleRoute,
    LagReading,
    Measurement,
    Purpose,
    ReadReplicaError,
    StalenessBanner,
    Target,
    Unreachable,
    Why,
    banner_for,
    route_read,
    stated_lag,
    threshold_gaps,
)
from brain.gate.provenance import DEFAULT_HORIZON

NOW = datetime(2999, 1, 1, 12, tzinfo=UTC)
SECOND = timedelta(seconds=1)


def behind(
    age: timedelta, *, measured: timedelta = timedelta(), caught_up: bool = False
) -> Measurement:
    """A replica in recovery whose last replay is `age` old, measured `measured` before NOW."""
    return Measurement(
        reading=LagReading(in_recovery=True, replay_age=age, caught_up=caught_up),
        at=NOW - measured,
    )


# ------------------------------------------------------------------ the healthy case
def test_a_display_read_on_a_current_replica_is_answered_by_the_replica_with_no_banner() -> None:
    """The positive case every refusal below needs beside it.

    Delete this and `route_read` can send everything to the primary, which passes every other
    test in this file and routes no console read anywhere, which is M36.1.2.2 not done."""
    route = route_read(Purpose.DISPLAY, behind(SECOND), now=NOW)

    assert route.target is Target.REPLICA
    assert route.why is Why.CURRENT
    assert route.banner is None


def test_a_replica_past_the_banner_threshold_is_read_and_the_page_says_by_how_much() -> None:
    """Between the two thresholds: the replica, with a banner stating whole seconds.

    Delete this and the band can collapse, either by falling back as soon as the banner would
    appear, which is M36.1.2.3 never showing, or by routing there with no banner."""
    route = route_read(Purpose.DISPLAY, behind(timedelta(seconds=42)), now=NOW)

    assert route.target is Target.REPLICA
    assert route.why is Why.BEHIND
    assert route.banner is not None
    assert route.banner.behind_seconds == 42
    assert "42 seconds behind" in route.banner.message


def test_the_banner_appears_just_past_its_threshold_and_not_at_it() -> None:
    """Both sides of `BANNER_AFTER`, measured at the constant rather than at a copy of it.

    The constant's value is asserted separately against the other thresholds, so this is the
    comparison and not the number. Delete this and `>` can become `>=` or the threshold can be
    ignored for a fixed figure, and nothing else in this file sits on the boundary."""
    at = route_read(Purpose.DISPLAY, behind(BANNER_AFTER), now=NOW)
    past = route_read(Purpose.DISPLAY, behind(BANNER_AFTER + SECOND), now=NOW)

    assert (at.target, at.banner) == (Target.REPLICA, None)
    assert past.target is Target.REPLICA
    assert past.banner is not None


def test_a_replica_further_behind_than_a_page_may_be_is_not_read() -> None:
    """Past `FALL_BACK_AFTER` the primary answers and there is no banner, and at it the replica.

    Delete this and a replica hours behind is served with a banner nobody reads, on a screen
    whose edit then overwrites whatever changed in between."""
    at = route_read(Purpose.DISPLAY, behind(FALL_BACK_AFTER), now=NOW)
    past = route_read(Purpose.DISPLAY, behind(FALL_BACK_AFTER + SECOND), now=NOW)

    assert at.target is Target.REPLICA
    assert at.banner is not None
    assert (past.target, past.why, past.banner) == (Target.PRIMARY, Why.TOO_FAR_BEHIND, None)


# ------------------------------------------------------------ the refusals, one each
def test_a_read_that_decides_something_is_answered_by_the_primary_however_current() -> None:
    """The one rule no lag figure can override.

    Delete this and an entitlement read through this path reads a copy where a revocation has
    not been replayed, and admits somebody the owner removed seconds ago."""
    route = route_read(Purpose.DECISION, behind(timedelta()), now=NOW)

    assert (route.target, route.why) == (Target.PRIMARY, Why.A_DECISION)


def test_no_replica_configured_means_the_primary_answers() -> None:
    """Unchanged behaviour for every install without the setting.

    Delete this and a missing measurement could be treated as a replica with no lag."""
    route = route_read(Purpose.DISPLAY, None, now=NOW)

    assert (route.target, route.why, route.banner) == (Target.PRIMARY, Why.NO_REPLICA, None)


def test_an_unreachable_replica_sends_the_read_to_the_primary() -> None:
    """Fail safe is the primary, not an error and not an empty page.

    Delete this and an unreachable replica can be routed to anyway, and the console goes down
    whenever a component it did not need before M36.1.2 does."""
    route = route_read(Purpose.DISPLAY, Measurement(reading=Unreachable(), at=NOW), now=NOW)

    assert (route.target, route.why) == (Target.PRIMARY, Why.UNREACHABLE)


def test_an_address_that_answers_as_a_primary_is_not_read_as_a_replica() -> None:
    """A promoted replica is a diverging database, and a null replay age there is not zero lag.

    `caught_up` is set true as well, so a check that looked at it before recovery would pass the
    promoted server through. Delete this and a failover that promoted the replica leaves the
    console reading a database the application has stopped writing to."""
    promoted = Measurement(
        reading=LagReading(in_recovery=False, replay_age=None, caught_up=True), at=NOW
    )

    assert route_read(Purpose.DISPLAY, promoted, now=NOW).why is Why.NOT_IN_RECOVERY


def test_a_replica_that_has_replayed_nothing_has_no_age_and_is_not_read() -> None:
    """Null replay age on a server in recovery that is not caught up: it is its base backup.

    Delete this and `None` can be read as no lag, which is the most dangerous misreading of the
    query, because a replica built from last week's backup reads as current."""
    fresh = Measurement(
        reading=LagReading(in_recovery=True, replay_age=None, caught_up=False), at=NOW
    )

    assert route_read(Purpose.DISPLAY, fresh, now=NOW).why is Why.NOTHING_REPLAYED


def test_a_caught_up_replica_on_an_idle_primary_is_current_whatever_its_replay_age() -> None:
    """The idle primary: no new transactions, so the replay age grows on a replica that is current.

    Delete this and every quiet night sends the console to the primary, which is safe and is
    also the replica never being used off-peak; or the caught-up flag can be dropped unnoticed."""
    idle = behind(timedelta(hours=3), caught_up=True)

    route = route_read(Purpose.DISPLAY, idle, now=NOW)

    assert (route.target, route.banner) == (Target.REPLICA, None)


def test_a_negative_lag_is_distrusted_rather_than_read_as_current() -> None:
    """Clocks that disagree cannot state an age, from the replay age or from the reading's instant.

    Delete this and a replica whose clock runs ahead reports a lag below zero, which is below
    every threshold, and is read however far behind it really is."""
    ahead = behind(-SECOND)
    future = behind(SECOND, measured=-SECOND)

    assert route_read(Purpose.DISPLAY, ahead, now=NOW).why is Why.CLOCKS_DISAGREE
    assert route_read(Purpose.DISPLAY, future, now=NOW).why is Why.CLOCKS_DISAGREE


def test_a_future_dated_reading_is_distrusted_even_when_it_says_caught_up() -> None:
    """The instant check comes before the caught-up shortcut.

    Delete this and a reading stamped after `now` reports a negative stated lag through the
    caught-up branch and passes every threshold."""
    future = behind(timedelta(), measured=-SECOND, caught_up=True)

    assert stated_lag(future, now=NOW) is Why.CLOCKS_DISAGREE


# ------------------------------------------------------------ the reading's own age
def test_a_cached_reading_states_its_own_age_on_top_of_the_lag_it_measured() -> None:
    """A reading taken earlier can only have got worse since.

    Delete this and a measurement cached for a while reports the lag of the moment it was taken,
    which is a page claiming to be fresher than it can be shown to be."""
    reading = behind(3 * SECOND, measured=4 * SECOND)

    assert stated_lag(reading, now=NOW) == 7 * SECOND


def test_a_caught_up_reading_states_only_its_own_age() -> None:
    """Caught up is zero lag at the instant measured, and the time since is still added.

    Delete this and the caught-up branch can return zero whatever the reading's age."""
    reading = behind(timedelta(hours=1), measured=5 * SECOND, caught_up=True)

    assert stated_lag(reading, now=NOW) == 5 * SECOND


def test_a_reading_aged_past_the_banner_threshold_puts_a_banner_on_a_current_replica() -> None:
    """The reading's age reaches the route, not only `stated_lag`.

    Delete this and `route_read` can judge the raw replay age while `stated_lag` adds the age
    for nobody."""
    reading = behind(SECOND, measured=BANNER_AFTER)

    route = route_read(Purpose.DISPLAY, reading, now=NOW)

    assert route.banner is not None
    assert route.banner.behind_seconds == 11


# ---------------------------------------------------------------------- the banner
def test_the_banner_rounds_up_so_it_never_understates() -> None:
    """10.2 seconds behind is eleven.

    Delete this and `round` or `int` can replace `ceil`, and a page reads as less behind than it
    is by up to a second."""
    assert banner_for(timedelta(seconds=10.2)).behind_seconds == 11
    assert banner_for(timedelta(seconds=10)).behind_seconds == 10


def test_the_banner_names_no_row_and_carries_only_its_two_fields() -> None:
    """What reaches a response is a number of seconds and a sentence about the copy.

    Delete this and a field such as the replica's host, or the rows it lacks, can be added to
    the model and shipped to every reader of every console page."""
    banner = banner_for(timedelta(seconds=30))

    assert set(banner.model_dump()) == {"behind_seconds", "message"}
    with pytest.raises(ValidationError):
        StalenessBanner(behind_seconds=30, message="x", host="replica.internal")  # type: ignore[call-arg]


def test_a_banner_cannot_say_a_page_is_zero_seconds_behind() -> None:
    """A banner exists only for a page that is behind.

    Delete this and `ge=1` can go, and a banner reading "0 seconds behind" teaches people the
    banner means nothing."""
    with pytest.raises(ValidationError):
        StalenessBanner(behind_seconds=0, message="x")


# --------------------------------------------------------------- the route's shape
def test_a_route_to_the_replica_described_as_behind_cannot_be_built_without_a_banner() -> None:
    """Silent stale data refused by construction, with the rule as the message.

    Delete this and a caller building its own route can serve the replica past the banner
    threshold with nothing on the page."""
    with pytest.raises(ReadReplicaError) as refused:
        ConsoleRoute(target=Target.REPLICA, why=Why.BEHIND)

    assert str(refused.value) == A_REPLICA_READ_PAST_THE_BANNER_THRESHOLD_ALWAYS_CARRIES_ONE


def test_a_read_from_the_primary_cannot_carry_a_banner() -> None:
    """A current page described as behind teaches readers to ignore the banner that matters.

    Delete this and the primary fallback can carry the replica's stale banner through."""
    with pytest.raises(ReadReplicaError):
        ConsoleRoute(target=Target.PRIMARY, why=Why.NO_REPLICA, banner=banner_for(30 * SECOND))


def test_a_replica_route_cannot_be_given_a_reason_that_means_do_not_read_it() -> None:
    """`REPLICA` with `UNREACHABLE` or `A_DECISION` is a contradiction the type refuses.

    Delete this and a route can say why the replica must not be read while pointing at it."""
    for why in (Why.UNREACHABLE, Why.A_DECISION, Why.TOO_FAR_BEHIND, Why.NOT_IN_RECOVERY):
        with pytest.raises(ReadReplicaError):
            ConsoleRoute(target=Target.REPLICA, why=why)


def test_the_two_healthy_route_shapes_can_be_built() -> None:
    """The sibling of the three refusals: the valid shapes are not refused.

    Delete this and `__post_init__` can refuse every replica route, which passes all three
    refusal tests above."""
    assert ConsoleRoute(target=Target.REPLICA, why=Why.CURRENT).banner is None
    banner = banner_for(30 * SECOND)
    assert ConsoleRoute(target=Target.REPLICA, why=Why.BEHIND, banner=banner).banner == banner
    assert ConsoleRoute(target=Target.PRIMARY, why=Why.TOO_FAR_BEHIND).banner is None


# ------------------------------------------------------------------ the thresholds
def test_the_thresholds_as_shipped_contradict_nothing() -> None:
    """The positive case for `threshold_gaps`, against the constants themselves.

    Delete this and a threshold can be retuned into a contradiction and ship."""
    assert threshold_gaps() == ()


def test_a_page_may_never_be_older_than_an_answer_would_still_be_called_live() -> None:
    """`FALL_BACK_AFTER` against something outside this module: the provenance live window.

    Delete this and the fall-back threshold can be raised to an hour, a value no other assertion
    here would notice, because every other test reads the constant it would be comparing."""
    assert DEFAULT_HORIZON.live_for >= FALL_BACK_AFTER
    assert MEASURE_EVERY < BANNER_AFTER < FALL_BACK_AFTER
    assert MEASURE_TIMEOUT <= MEASURE_EVERY


@pytest.mark.parametrize(
    ("changed", "says"),
    [
        ({"measure_every": BANNER_AFTER}, "raises the banner on its own age"),
        ({"measure_timeout": MEASURE_EVERY + SECOND}, "re-attempted while it is still waiting"),
        ({"banner_after": FALL_BACK_AFTER}, "the banner can never appear"),
        ({"fall_back_after": DEFAULT_HORIZON.live_for + SECOND}, "still be called live"),
    ],
)
def test_each_contradiction_between_the_thresholds_is_named(
    changed: dict[str, timedelta], says: str
) -> None:
    """One finding per contradiction, each at its own boundary.

    Delete this and `threshold_gaps` can return nothing for every input, which passes the
    positive test above."""
    findings = threshold_gaps(**changed)

    assert len(findings) == 1
    assert says in findings[0]
