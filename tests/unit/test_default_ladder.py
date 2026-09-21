"""The routing ladder an install starts with, held to the chain, the budget and setup.

Everything here is pure: the rungs, which provider they are written for and when, and whether the
defaults, once read back as the executor reads a ladder, answer a call on the answer lane.
`tests/unit/test_default_ladder_store.py` writes them into PostgreSQL and follows each row to its
ledger entry.

Task ids: none
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from brain.core.lane import Lane
from brain.firstrun import GRANTED_BY
from brain.identity.first_administrator import FIRST_RUN_LOCK
from brain.identity.sign_in_binding import UNLINK_LOCK
from brain.migrate import MIGRATION_LOCK_ID
from brain.models.assembly import HOSTED_PROFILE, LOCAL_PROFILE, LadderRung
from brain.models.default_ladder import (
    DEFAULT_MODELS,
    DEFAULT_TIERS,
    LOCAL_CONCURRENCY,
    LadderWritten,
    default_chain,
    default_ladder,
    provider_at_setup,
    provider_at_start,
    reconcile,
)
from brain.models.driver import DriverMessage, Role, check_answer_lane_budget
from brain.models.metering import Meter
from brain.models.routing import (
    ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS,
    RoutingRequest,
    RungRole,
    Tier,
    classify_tier,
    seed_chain,
)
from brain.models.wire import LOCAL_PROVIDER
from brain.ops.default_ladder_store import DEFAULT_LADDER_LOCK
from brain.ops.inference import REQUESTS_AT_ONCE
from brain.ops.provider_keys import PROVIDER_SLOTS
from tests.unit.test_model_calls import Ladder, Scripted, executor, ok

HOSTED = tuple(one.slug for one in PROVIDER_SLOTS)
EVERY_PROVIDER = (*HOSTED, LOCAL_PROVIDER)


@dataclass
class Writer:
    """A `LadderWriter` recording what it was asked to write, and answering as told."""

    answer: LadderWritten = LadderWritten.WRITTEN
    asked: list[tuple[str, str, str]] = field(default_factory=list)

    async def write(self, provider: str, *, actor: str, trace_id: str) -> LadderWritten:
        self.asked.append((provider, actor, trace_id))
        return self.answer


def as_read_back(provider: str) -> tuple[LadderRung, ...]:
    """The defaults as `brain.ops.model_service.ladder_rung_of` would read the rows back."""
    return tuple(
        LadderRung(
            rung_id=f"{one.tier.value}-default",
            tier=one.tier,
            position=one.position,
            deployment_id=one.deployment_id,
            provider=one.provider,
            model=one.model,
            attempts=one.attempts,
            timeout_seconds=one.timeout_seconds,
            max_concurrency=one.max_concurrency,
            enabled=True,
        )
        for one in default_ladder(provider)
    )


# --- what the defaults are ----------------------------------------------------------------------


def test_every_provider_the_wizard_can_record_and_the_local_server_have_a_default_ladder() -> None:
    """Every key slot, which is what the wizard's provider screen offers, and the install's own
    server have a ladder to write, and nothing else does.

    Delete this and a key slot added without a default ladder is a provider the wizard accepts and
    an install that answers nothing after choosing it."""
    assert set(DEFAULT_MODELS) == set(EVERY_PROVIDER)
    for provider in EVERY_PROVIDER:
        assert set(DEFAULT_MODELS[provider]) == set(DEFAULT_TIERS)


def test_a_provider_with_no_default_ladder_is_refused_rather_than_given_an_empty_one() -> None:
    """Delete this and an unknown provider writes an empty ladder, which reads as configured."""
    with pytest.raises(ValueError, match="no default ladder"):
        default_ladder("nobody")


@pytest.mark.parametrize("provider", EVERY_PROVIDER)
def test_the_defaults_are_one_primary_rung_in_each_tier_the_lanes_route_to(provider: str) -> None:
    """One rung per tier, at the first position with the primary's role, in the tier every
    answer-lane request lands in and the tier the task lane lands in, and nowhere else.

    Delete this and a default can sit in a tier no lane routes to, which is a ladder that looks
    written and answers nothing."""
    rungs = default_ladder(provider)
    answer = classify_tier(RoutingRequest(lane=Lane.ANSWER)).tier
    task = classify_tier(RoutingRequest(lane=Lane.TASK)).tier

    assert [one.tier for one in rungs] == list(DEFAULT_TIERS)
    assert {answer, task} == set(DEFAULT_TIERS)
    assert Tier.SMALL not in DEFAULT_TIERS
    assert {(one.position, one.role) for one in rungs} == {(0, RungRole.PRIMARY)}
    assert {one.provider for one in rungs} == {provider}
    chain = default_chain(provider)
    for tier in DEFAULT_TIERS:
        assert len(chain.rungs_for(tier)) == 1


@pytest.mark.parametrize("provider", EVERY_PROVIDER)
def test_the_defaults_fit_the_answer_lanes_wall_clock_budget(provider: str) -> None:
    """The answer tier's worst case, attempts times timeout, is inside the budget a person waits
    for, checked by the same function a configuration change is checked with.

    Delete this and a default can put the answer lane past the point where the person asking has
    given up, on every fresh install at once."""
    chain = default_chain(provider)
    tier = classify_tier(RoutingRequest(lane=Lane.ANSWER)).tier

    assert chain.worst_case_seconds(tier) <= ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS
    check_answer_lane_budget(chain, tier, {})


@pytest.mark.parametrize("provider", HOSTED)
def test_a_hosted_default_takes_the_seed_chains_primary_numbers_for_its_tier(provider: str) -> None:
    """The numbers are `seed_chain`'s primary rung per tier, measured against the seed rather than
    against the constants the module reads them from, and Anthropic's models are the seed's own.

    Delete this and a default can drift from the console's starting matrix, so a fresh install and
    the screen describing a fresh install disagree about the timeout."""
    seed = seed_chain()
    for one in default_ladder(provider):
        primary = seed.rungs_for(one.tier)[0]
        assert (one.attempts, one.timeout_seconds, one.max_concurrency) == (
            primary.attempts,
            primary.timeout_seconds,
            primary.max_concurrency,
        )
    assert [one.model for one in default_ladder("anthropic")] == [
        seed.rungs_for(tier)[0].model for tier in DEFAULT_TIERS
    ]


def test_the_install_s_own_server_is_asked_for_one_request_at_a_time() -> None:
    """The local rungs admit as many concurrent calls as the inference server answers, which
    `brain.ops.inference` derives from its own memory arithmetic.

    Delete this and a local install queues forty calls on a server with room for one, which is the
    container killed with a model half loaded."""
    assert LOCAL_CONCURRENCY == REQUESTS_AT_ONCE
    assert {one.max_concurrency for one in default_ladder(LOCAL_PROVIDER)} == {REQUESTS_AT_ONCE}


def test_the_ladder_lock_is_nobody_else_s() -> None:
    """Delete this and the default ladder shares an advisory lock with the first run's door, an
    unlink or the migrations, and a start waits on, or releases, a lock it never meant to hold."""
    assert DEFAULT_LADDER_LOCK not in {FIRST_RUN_LOCK, UNLINK_LOCK, MIGRATION_LOCK_ID, 8274419004}


# --- the defaults answer ------------------------------------------------------------------------


@pytest.mark.parametrize("provider", HOSTED)
def test_a_hosted_install_with_its_key_and_the_defaults_answers_a_call_on_the_answer_lane(
    provider: str,
) -> None:
    """**A fresh install can reach a model.** The defaults read back as the executor reads the
    ladder, under the hosted profile with the provider's key held, plan a chain whose answer tier
    answers, and the call is sent to the default model.

    Delete this and a default ladder the executor assembles to nothing, a local profile skipping it
    or a model name the chain refuses, passes every test that only reads the rows."""
    transport = Scripted(ok())
    calls, _ = executor(
        Ladder(as_read_back(provider)),
        {provider: transport},
        profile=HOSTED_PROFILE,
        held=frozenset({provider}),
    )
    tier = classify_tier(RoutingRequest(lane=Lane.ANSWER)).tier

    answered = asyncio.run(
        calls.complete(
            (DriverMessage(role=Role.USER, content="ready?"),),
            tier=tier,
            lane=Lane.ANSWER,
            meter=Meter(),
            trace_id="b" * 32,
        )
    )

    assert answered.deployment_id == f"{provider}-{tier.value}"
    (request,) = transport.sent
    assert request.model == DEFAULT_MODELS[provider][tier]


def test_a_local_install_s_defaults_are_in_rotation_under_the_local_profile() -> None:
    """The local server's defaults are not left out by the local profile, which takes hosted
    providers out and leaves the install's own server in.

    Delete this and a local install's ladder can be written for a provider the local profile then
    skips, which is a ladder nobody can call."""
    calls, _ = executor(
        Ladder(as_read_back(LOCAL_PROVIDER)),
        {LOCAL_PROVIDER: Scripted(ok())},
        profile=LOCAL_PROFILE,
        held=frozenset(),
    )
    planned = asyncio.run(calls.planned())

    assert {one.tier for one in planned.assembly.answering} == set(DEFAULT_TIERS)
    assert planned.assembly.skipped == ()


# --- which provider, and when -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("profile", "recorded", "expected"),
    [
        (LOCAL_PROFILE, "", LOCAL_PROVIDER),
        ("", "", LOCAL_PROVIDER),
        ("anything else", "anthropic", LOCAL_PROVIDER),
        (HOSTED_PROFILE, "moonshot", "moonshot"),
        (HOSTED_PROFILE, "nobody", None),
    ],
)
def test_the_wizard_s_ladder_is_for_the_local_server_or_the_hosted_provider_it_recorded(
    profile: str, recorded: str, expected: str | None
) -> None:
    """A profile that keeps text on the client's hardware, including one nobody recognises, writes
    the local server's ladder; a hosted one writes the recorded provider's; a hosted one naming a
    provider with no ladder names none.

    Delete this and a local install can be written a hosted ladder its profile then refuses, or a
    hosted install the local server's."""
    assert provider_at_setup(profile, recorded) == expected


@pytest.mark.parametrize(
    ("profile", "held", "expected"),
    [
        (LOCAL_PROFILE, frozenset({"anthropic"}), LOCAL_PROVIDER),
        (HOSTED_PROFILE, frozenset({"moonshot", "anthropic"}), "anthropic"),
        (HOSTED_PROFILE, frozenset({"moonshot", "openai"}), "openai"),
        (HOSTED_PROFILE, frozenset(), None),
    ],
)
def test_a_start_names_the_local_server_or_the_first_held_key_s_provider_in_slot_order(
    profile: str, held: frozenset[str], expected: str | None
) -> None:
    """At a start there is no wizard answer, so a hosted install's provider is the first key slot
    whose key this process holds, in the slots' declared order, and none is named with no key held.

    Delete this and two processes holding the same keys can name different providers, or a hosted
    install with no key is written a ladder for a provider it cannot call."""
    assert [one.slug for one in PROVIDER_SLOTS] == ["anthropic", "openai", "moonshot", "deepseek"]
    assert provider_at_start(profile, held) == expected


def test_a_start_writes_nothing_on_an_install_nobody_has_set_up() -> None:
    """**No ladder before setup.** With no administrator the writer is not asked, whatever the
    profile and the keys say; with one, it is asked for the provider the start names, as first run.

    Delete this and a fresh install writes the local server's ladder at its first start, which is
    then never refilled, and sits in front of the hosted provider the wizard chooses next."""
    before = Writer()
    after = Writer()

    unset = asyncio.run(
        reconcile(
            before,
            administrators=0,
            profile=LOCAL_PROFILE,
            held=(),
            actor=GRANTED_BY,
            trace_id="startup.reconcile.a",
        )
    )
    written = asyncio.run(
        reconcile(
            after,
            administrators=1,
            profile=HOSTED_PROFILE,
            held=("moonshot",),
            actor=GRANTED_BY,
            trace_id="startup.reconcile.b",
        )
    )

    assert (unset, before.asked) == (LadderWritten.NOT_SET_UP, [])
    assert written is LadderWritten.WRITTEN
    assert after.asked == [("moonshot", GRANTED_BY, "startup.reconcile.b")]


def test_a_start_on_a_hosted_install_with_no_key_asks_for_no_ladder() -> None:
    """Delete this and a hosted install with no key held is asked to write a ladder for nobody,
    which raises at every start and fills the log with a refusal nobody can act on."""
    writer = Writer()

    outcome = asyncio.run(
        reconcile(
            writer,
            administrators=1,
            profile=HOSTED_PROFILE,
            held=(),
            actor=GRANTED_BY,
            trace_id="startup.reconcile.c",
        )
    )

    assert (outcome, writer.asked) == (LadderWritten.NO_PROVIDER, [])


def test_what_the_writer_found_is_what_a_start_reports() -> None:
    """A held or emptied ladder is the writer's to find, under its lock, and the start reports it
    rather than deciding it again from a read taken outside the lock.

    Delete this and a start can report a ladder as written that the writer refused to touch."""
    writer = Writer(answer=LadderWritten.EMPTIED)

    outcome = asyncio.run(
        reconcile(
            writer,
            administrators=2,
            profile=LOCAL_PROFILE,
            held=(),
            actor=GRANTED_BY,
            trace_id="startup.reconcile.d",
        )
    )

    assert outcome is LadderWritten.EMPTIED
    assert writer.asked == [(LOCAL_PROVIDER, GRANTED_BY, "startup.reconcile.d")]
