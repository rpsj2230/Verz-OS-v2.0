"""The routing matrix screen: what it shows, what it refuses to hide, and what it adds up.

Two properties carry this file. Every rung in the chain reaches the screen, whatever state it
is in, because a display that can be left in a reassuring state is worse than no display. And
a tier whose every rung is open is asked about directly, because that is a fact about the set
and a screen rendering state per row leaves the reader to notice it by counting.

Task ids: M27.2.3
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from brain.console.model_matrix import (
    MATRIX_AUTHORITY,
    ModelMatrixError,
    Rung,
    exhausted_tiers,
    matrix,
    unhealthy,
)
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.models.health import OpenReason, ProviderHealth
from brain.models.routing import (
    BreakerState,
    CircuitBreaker,
    Deployment,
    ResidencyClass,
    RoutingChain,
    RoutingRung,
    RungRole,
    Tier,
)

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
ROUTE = Capability(value="read:model_route")


def a_deployment(deployment_id: str, *, provider: str, model: str) -> Deployment:
    """One reachable endpoint, through the real constructor."""
    return Deployment(
        id=deployment_id,
        provider=provider,
        model=model,
        region="eu",
        residency_class=ResidencyClass.REGION_PINNED,
        context_window=100_000,
    )


def a_rung(tier: Tier, position: int, deployment: Deployment) -> RoutingRung:
    """One position in one tier's chain."""
    return RoutingRung(
        tier=tier,
        position=position,
        model=deployment.model,
        deployment=deployment,
        attempts=1,
        timeout_seconds=20.0,
        max_concurrency=4,
    )


def a_chain() -> RoutingChain:
    """Two tiers, two rungs each, two providers, so a fold that drops one is visible."""
    return RoutingChain(
        rungs=(
            a_rung(Tier.MAIN, 1, a_deployment("d_main_1", provider="alpha", model="big")),
            a_rung(Tier.MAIN, 2, a_deployment("d_main_2", provider="beta", model="big-alt")),
            a_rung(Tier.SMALL, 1, a_deployment("d_small_1", provider="alpha", model="small")),
            a_rung(Tier.SMALL, 2, a_deployment("d_small_2", provider="beta", model="small-alt")),
        )
    )


def an_open_deployment(deployment_id: str) -> ProviderHealth:
    """A breaker that is open, with a live ring that says why."""
    return ProviderHealth(
        breaker=CircuitBreaker(
            deployment_id=deployment_id,
            state=BreakerState.OPEN,
            consecutive_failures=5,
            live=(False, False, False, False, False),
            opened_at=NOW,
        )
    )


def a_reader() -> EntitlementSet:
    """Somebody holding the models screen's capability."""
    return EntitlementSet(
        principal_id="u_operator",
        grants=(Grant(capability=ROUTE, scope=Scope.unrestricted()),),
    )


def nobody() -> EntitlementSet:
    """Somebody holding nothing at all."""
    return EntitlementSet(principal_id="u_nobody", grants=())


# --- what reaches the screen -------------------------------------------------------------


def test_every_rung_in_the_chain_reaches_the_screen_whatever_state_it_is_in() -> None:
    """M27.2.3. **A matrix that can hide an open rung is a screen that says everything is
    fine**, and the person who left the filter on is the person who set it during the last
    incident.

    Two of the four rungs are open here, and all four are expected. A screen that dropped the
    unhealthy ones would return two rows and look entirely reasonable.

    Delete this and the obvious convenience arrives: a `healthy_only` flag, defaulting to
    something, on the one screen whose job is to show what is broken."""
    health = {
        "d_main_1": an_open_deployment("d_main_1"),
        "d_small_2": an_open_deployment("d_small_2"),
    }

    rows = matrix(a_chain(), health, a_reader(), now=NOW)

    assert [one.deployment_id for one in rows] == [
        "d_small_1",
        "d_small_2",
        "d_main_1",
        "d_main_2",
    ]
    assert sum(1 for one in rows if one.state is BreakerState.OPEN) == 2


def test_there_is_no_parameter_that_would_remove_a_rung() -> None:
    """Asserted on the signature as well as on the behaviour, because the wrong version
    arrives as a parameter rather than as a changed calculation, and behaviour alone keeps
    passing on the day it lands with a default of False.

    Delete this and the filter is one keyword argument away, on the screen that most needs to
    be unable to lie."""
    taken = inspect.signature(matrix).parameters

    assert set(taken) == {"chain", "health", "entitlement", "now"}


def test_the_rows_are_in_the_order_the_router_tries_them() -> None:
    """Position is what the router follows. A screen sorted by provider or by name makes a
    reader work out which rung is tried first, and the first rung is the one that matters
    when something is wrong.

    The chain is built with the main tier's rungs first and small's second, and the rows come
    back the other way round, so this asserts the tier order is the enum's rather than the
    order somebody happened to declare.

    Delete this and the matrix renders in dictionary order."""
    rows = matrix(a_chain(), {}, a_reader(), now=NOW)

    assert [(one.tier, one.position) for one in rows] == [
        (Tier.SMALL, 1),
        (Tier.SMALL, 2),
        (Tier.MAIN, 1),
        (Tier.MAIN, 2),
    ]


def test_a_rung_nothing_has_failed_against_is_shown_as_healthy_and_not_as_unknown() -> None:
    """`ProviderHealth.for_deployment` starts closed rather than unknown, because starting
    unknown-and-blocked means a fresh install serves nothing until something probes every
    rung. A screen showing the same rung as unknown would contradict the router, in the
    alarming direction.

    No health records at all, which is exactly what a fresh install looks like.

    Delete this and a correct new deployment renders as a matrix of question marks, and the
    first thing anybody does about it is look for a fault that is not there."""
    rows = matrix(a_chain(), {}, a_reader(), now=NOW)

    assert len(rows) == 4
    assert all(one.state is BreakerState.CLOSED for one in rows)
    assert all(one.unhealthy_because is None for one in rows)
    assert all(one.live_seen == 0 and one.live_failed == 0 for one in rows)


def test_a_reader_without_the_screens_capability_sees_nothing_and_is_told_nothing() -> None:
    """Empty rather than a refusal, like every other console surface here: a refusal naming
    the capability would say the screen exists.

    Delete this and holding no grant becomes distinguishable from an estate with no models
    configured."""
    assert matrix(a_chain(), {}, nobody(), now=NOW) == ()


def test_the_capability_is_the_screens_own_and_not_one_invented_here() -> None:
    """A capability invented for this view would be a second grant over the same rows, and an
    administrator reviewing the console's screens would never meet it.

    Anchored to the literal as well as to the screen, so the pair is not compared against
    itself.

    Delete this and the matrix is read behind a grant nobody reviews."""
    assert MATRIX_AUTHORITY.value == "read:model_route"
    assert screen("models").read.requires == MATRIX_AUTHORITY


# --- what the rows say -------------------------------------------------------------------


def test_an_open_rung_carries_the_routers_own_reason() -> None:
    """The vocabulary is `brain.models.health.OpenReason`, so an operator reading this screen
    and an engineer reading a log are looking at the same words.

    Delete this and the screen invents an adjective, and the two accounts of one outage stop
    matching."""
    rows = matrix(a_chain(), {"d_main_1": an_open_deployment("d_main_1")}, a_reader(), now=NOW)
    broken = next(one for one in rows if one.deployment_id == "d_main_1")

    assert broken.state is BreakerState.OPEN
    assert isinstance(broken.unhealthy_because, OpenReason)
    assert broken.live_seen == 5
    assert broken.live_failed == 5


def test_a_rung_that_is_not_open_may_not_carry_a_reason_and_an_open_one_need_not() -> None:
    """The constraint runs one way and the asymmetry is deliberate. A closed rung with a
    reason beside it reads as a warning nobody acted on. An open rung with no reason is a real
    state: the breaker opened and the evidence that opened it has since aged out of the ring,
    and requiring a reason there would turn an ordinary state into an exception on a screen
    somebody opens during an incident.

    Delete this and one of the two becomes possible, and which one depends on how the
    condition was written."""
    with pytest.raises(ModelMatrixError, match="is not open"):
        Rung(
            tier=Tier.MAIN,
            position=1,
            model="big",
            deployment_id="d_main_1",
            provider="alpha",
            role=RungRole.PRIMARY,
            state=BreakerState.CLOSED,
            unhealthy_because=OpenReason.CONSECUTIVE_LIVE_FAILURES,
            live_seen=0,
            live_failed=0,
            last_probe_at=None,
        )

    aged = Rung(
        tier=Tier.MAIN,
        position=1,
        model="big",
        deployment_id="d_main_1",
        provider="alpha",
        role=RungRole.PRIMARY,
        state=BreakerState.OPEN,
        unhealthy_because=None,
        live_seen=0,
        live_failed=0,
        last_probe_at=None,
    )

    assert aged.state is BreakerState.OPEN


def test_a_rung_cannot_report_more_failures_than_outcomes() -> None:
    """Two counts that have to agree, and the arithmetic is the whole of what the pair means.
    A row saying three failures out of two is a row a reader either does not notice or does
    not trust, and both are bad.

    Delete this and a renderer can be handed a ring it has miscounted."""
    with pytest.raises(ModelMatrixError, match="failures out of"):
        Rung(
            tier=Tier.MAIN,
            position=1,
            model="big",
            deployment_id="d_main_1",
            provider="alpha",
            role=RungRole.PRIMARY,
            state=BreakerState.CLOSED,
            unhealthy_because=None,
            live_seen=2,
            live_failed=3,
            last_probe_at=None,
        )


# --- what the set says that no row does --------------------------------------------------


def test_a_tier_with_every_rung_open_is_reported_and_a_tier_with_one_open_is_not() -> None:
    """M27.2.3, and the one thing on this screen worth an alert. One open rung is a chain
    doing its job; a tier with none left cannot answer at all.

    Both cases in one test, because a function reporting every tier and one reporting none
    each satisfy half of it.

    Delete this and the difference between a working fallback and an outage is left to
    whoever is counting the amber rows."""
    both_open = {
        "d_main_1": an_open_deployment("d_main_1"),
        "d_main_2": an_open_deployment("d_main_2"),
        "d_small_1": an_open_deployment("d_small_1"),
    }

    rows = matrix(a_chain(), both_open, a_reader(), now=NOW)

    assert exhausted_tiers(rows) == (Tier.MAIN,)


def test_a_tier_with_no_rungs_at_all_is_not_an_outage() -> None:
    """Nothing was tried and failed; nothing is configured. Reporting it as exhausted would
    put a tier nobody has set up beside a tier that has just fallen over, and the two go to
    different people.

    The property holds by construction: a tier reaches the grouping only by having a row in
    it. That is worth asserting anyway, because it is a property of the answer rather than of
    the implementation, and the implementation is free to change. The first version of
    `exhausted_tiers` guarded it explicitly and a mutation showed the guard changed no answer.

    Delete this and a fresh install alerts about every tier it has not been given a model
    for, on whatever implementation comes next."""
    one_tier = RoutingChain(
        rungs=(a_rung(Tier.MAIN, 1, a_deployment("d_main_1", provider="alpha", model="big")),)
    )

    rows = matrix(one_tier, {}, a_reader(), now=NOW)

    assert exhausted_tiers(rows) == ()
    assert [one.tier for one in rows] == [Tier.MAIN]


def test_a_reader_who_sees_no_rows_is_told_about_no_outages() -> None:
    """The honest answer for somebody holding nothing: they were not shown the estate, so the
    screen says nothing about it, rather than saying it is fine.

    Delete this and the banner is computed from the chain rather than from what was shown,
    and a reader with no grant is told which tier is down."""
    assert exhausted_tiers(matrix(a_chain(), {}, nobody(), now=NOW)) == ()


def test_the_banner_names_the_rungs_rather_than_counting_them() -> None:
    """A count is what a screen prints when it has decided not to show the rows. An operator
    needs to know which provider, not how many.

    Delete this and `unhealthy` becomes a number, and the screen that reports an outage stops
    saying whose."""
    health = {"d_main_1": an_open_deployment("d_main_1")}

    named = unhealthy(matrix(a_chain(), health, a_reader(), now=NOW))

    assert [one.deployment_id for one in named] == ["d_main_1"]
    assert named[0].provider == "alpha"
