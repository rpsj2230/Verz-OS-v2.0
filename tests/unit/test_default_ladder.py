"""The routing ladder an install starts with, held to the chain, the budget and setup.

Everything here is pure: the rungs, which provider they are written for and when, and whether the
defaults, once read back as the executor reads a ladder, answer a call on the answer lane.
`tests/unit/test_default_ladder_store.py` writes them into PostgreSQL and follows each row to its
ledger entry.

Task ids: none
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace

import pytest

from brain.core.lane import Lane
from brain.firstrun import GRANTED_BY
from brain.identity.first_administrator import FIRST_RUN_LOCK
from brain.identity.sign_in_binding import UNLINK_LOCK
from brain.migrate import MIGRATION_LOCK_ID
from brain.models.adapter import TransportStatusError
from brain.models.assembly import HOSTED_PROFILE, LOCAL_PROFILE, LadderRung, RungSkip
from brain.models.calls import ModelCalls
from brain.models.default_ladder import (
    DEFAULT_MODELS,
    DEFAULT_TIERS,
    LOCAL_CONCURRENCY,
    MATRIX_PROVIDER,
    WAITED_ON,
    LadderWritten,
    WrittenStep,
    completion,
    default_chain,
    default_ladder,
    default_model,
    default_rung,
    earlier_default,
    provider_at_setup,
    provider_at_start,
    reconcile,
)
from brain.models.driver import (
    DriverMessage,
    DriverResponse,
    ProviderUnavailable,
    Role,
    check_answer_lane_budget,
)
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
#: Every provider whose default is still one primary per tier: all but the owner's matrix's.
ONE_PRIMARY_EACH = tuple(one for one in EVERY_PROVIDER if one != MATRIX_PROVIDER)

#: The owner's screenshot of 2026-09-03, restated 2026-09-29, row for row: level, step from 1,
#: provider, model and role. Written out here rather than read from the module, so the module's
#: table is compared with the design of record and not with itself.
THE_OWNERS_SCREENSHOT = [
    ("small", 1, "anthropic", "claude-haiku-4-5", "primary"),
    ("small", 2, "anthropic", "claude-sonnet-5", "same_provider_failover"),
    ("small", 3, "anthropic", "claude-opus-5", "same_provider_failover"),
    ("small", 4, "moonshot", "kimi-k2.6", "cross_provider_failover"),
    ("main", 1, "anthropic", "claude-sonnet-5", "primary"),
    ("main", 2, "anthropic", "claude-opus-5", "same_provider_failover"),
    ("main", 3, "anthropic", "claude-haiku-4-5", "same_provider_failover"),
    ("main", 4, "moonshot", "kimi-k3", "cross_provider_failover"),
    ("heavy", 1, "anthropic", "claude-opus-5", "primary"),
    ("heavy", 2, "anthropic", "claude-sonnet-5", "same_provider_failover"),
    ("heavy", 3, "anthropic", "claude-haiku-4-5", "same_provider_failover"),
    ("heavy", 4, "moonshot", "kimi-k3", "cross_provider_failover"),
]


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
            rung_id=f"{one.tier.value}-{one.position}-default",
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


@pytest.mark.parametrize("provider", ONE_PRIMARY_EACH)
def test_another_provider_s_default_is_one_primary_rung_in_each_tier_the_lanes_route_to(
    provider: str,
) -> None:
    """For every provider but the owner's matrix's, one rung per tier, at the first position with
    the primary's role, in the tier every answer-lane request lands in and the tier the task lane
    lands in, and nowhere else.

    Delete this and a default can sit in a tier no lane routes to, which is a ladder that looks
    written and answers nothing, or an OpenAI install can be written a failover onto a provider
    it never chose."""
    rungs = default_ladder(provider)
    answer = classify_tier(RoutingRequest(lane=Lane.ANSWER)).tier
    task = classify_tier(RoutingRequest(lane=Lane.TASK)).tier

    assert [one.tier for one in rungs] == list(DEFAULT_TIERS)
    assert {answer, task} == set(DEFAULT_TIERS)
    assert {(one.position, one.role) for one in rungs} == {(0, RungRole.PRIMARY)}
    assert {one.provider for one in rungs} == {provider}
    assert rungs == earlier_default(provider)


def test_the_anthropic_default_is_the_owner_s_failover_matrix_step_for_step() -> None:
    """**The design of record.** Simple, Medium and Complex each try three Anthropic models and
    then one Moonshot model, in the owner's order, and the roles come out of the chain's own
    derivation as default, next model on the same provider, and next provider.

    Delete this and the product's default can drift back to two primaries, or reorder a level,
    and the Models screen would draw a matrix that is not the one he drew."""
    drawn = [
        (one.tier.value, one.position + 1, one.provider, one.model, one.role.value)
        for one in default_ladder("anthropic")
    ]
    chain = default_chain("anthropic")

    assert MATRIX_PROVIDER == PROVIDER_SLOTS[0].slug == "anthropic"
    assert drawn == THE_OWNERS_SCREENSHOT
    assert [chain.role_of(one.routing_rung()).value for one in default_ladder("anthropic")] == [
        role for *_, role in THE_OWNERS_SCREENSHOT
    ]


def test_the_matrix_s_medium_and_complex_defaults_are_the_seed_chain_s_models() -> None:
    """The owner's Medium and Complex first steps are the models `seed_chain` starts the console
    from, so the product has one pair of names and not two.

    Delete this and the seed and the default can name different models for the same level, and
    the check of a provider no step names uses a model the matrix does not."""
    seed = seed_chain()
    firsts = {one.tier: one.model for one in default_ladder("anthropic") if one.position == 0}

    for tier in DEFAULT_TIERS:
        assert firsts[tier] == seed.rungs_for(tier)[0].model == DEFAULT_MODELS["anthropic"][tier]


@pytest.mark.parametrize("provider", EVERY_PROVIDER)
def test_the_defaults_fit_the_answer_lanes_wall_clock_budget(provider: str) -> None:
    """Every tier a person waits on, the answer lane's and the one below it, has a worst case,
    attempts times timeout over the whole walk, inside the budget a person waits for, checked by
    the same function a configuration change is checked with. The owner's four-step Medium walk
    is twelve seconds and three failovers of four, 24 in all.

    Delete this and a default can put the answer lane past the point where the person asking has
    given up, on every fresh install at once."""
    chain = default_chain(provider)
    answer = classify_tier(RoutingRequest(lane=Lane.ANSWER)).tier

    assert answer in WAITED_ON
    assert Tier.HEAVY not in WAITED_ON
    for tier in WAITED_ON:
        assert chain.worst_case_seconds(tier) <= ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS
        check_answer_lane_budget(chain, tier, {})
    if provider == MATRIX_PROVIDER:
        assert [len(chain.rungs_for(tier)) for tier in WAITED_ON] == [4, 4]
        assert chain.worst_case_seconds(Tier.MAIN) == 12.0 + 3 * 4.0


@pytest.mark.parametrize("provider", HOSTED)
def test_a_hosted_default_takes_the_seed_chains_primary_numbers_for_its_tier(provider: str) -> None:
    """Each tier's first step takes `seed_chain`'s primary numbers for that tier, Simple taking
    Medium's, measured against the seed rather than against the constants the module reads them
    from; a Complex failover takes the seed's own Complex failover numbers.

    Delete this and a default can drift from the console's starting matrix, so a fresh install and
    the screen describing a fresh install disagree about the timeout."""
    seed = seed_chain()
    for one in default_ladder(provider):
        seeded = seed.rungs_for(Tier.MAIN if one.tier is Tier.SMALL else one.tier)
        numbers = seeded[0] if one.position == 0 else seeded[1]
        if one.position > 0 and one.tier in WAITED_ON:
            continue
        assert (one.attempts, one.timeout_seconds, one.max_concurrency) == (
            numbers.attempts,
            numbers.timeout_seconds,
            numbers.max_concurrency,
        )
    assert [
        one.model
        for one in default_ladder("anthropic")
        if one.position == 0 and one.tier in DEFAULT_TIERS
    ] == [seed.rungs_for(tier)[0].model for tier in DEFAULT_TIERS]


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


def ask(calls: ModelCalls, tier: Tier) -> DriverResponse:
    """One question on the answer lane, at `tier`, as the answer lane's model step asks it."""
    return asyncio.run(
        calls.complete(
            (DriverMessage(role=Role.USER, content="ready?"),),
            tier=tier,
            lane=Lane.ANSWER,
            meter=Meter(),
            trace_id="b" * 32,
        )
    )


def test_a_moonshot_step_with_no_moonshot_key_is_left_out_and_never_called() -> None:
    """**No key is a marker, never an error to the person asking.** On an install holding the
    Anthropic key and no Moonshot key, the three Moonshot steps are left out before the chain is
    planned, each for `NO_KEY`, which the Models screen draws as the "no key" marker. When every
    Anthropic step of Medium fails, the walk has tried Sonnet, Opus and Haiku in the owner's order
    and nothing is sent to Moonshot, and the person is told what any failed walk tells them, with
    no word about a key.

    Positive sibling: `test_with_the_moonshot_key_held_the_last_step_answers_when_anthropic_fails`.

    Delete this and a Moonshot step can be dialled with no key, which is an authentication failure
    on somebody's question, on every install that chose Anthropic and never added Moonshot."""
    anthropic = Scripted(TransportStatusError(503))
    moonshot = Scripted(ok())
    calls, _ = executor(
        Ladder(as_read_back("anthropic")),
        {"anthropic": anthropic, "moonshot": moonshot},
        profile=HOSTED_PROFILE,
        held=frozenset({"anthropic"}),
    )
    planned = asyncio.run(calls.planned())

    assert sorted(
        (one.rung.tier.value, one.rung.provider, one.reason) for one in planned.assembly.skipped
    ) == [
        ("heavy", "moonshot", RungSkip.NO_KEY),
        ("main", "moonshot", RungSkip.NO_KEY),
        ("small", "moonshot", RungSkip.NO_KEY),
    ]
    with pytest.raises(ProviderUnavailable) as refused:
        ask(calls, Tier.MAIN)

    assert [one.model for one in anthropic.sent] == [
        "claude-sonnet-5",
        "claude-opus-5",
        "claude-haiku-4-5",
    ]
    assert moonshot.sent == []
    assert "key" not in refused.value.public_message.lower()


def test_with_the_moonshot_key_held_the_last_step_answers_when_anthropic_fails() -> None:
    """With both keys held, as on an install that kept all four, a Medium question whose three
    Anthropic steps fail is answered by the owner's fourth step, Moonshot's kimi-k3, and a Simple
    one by kimi-k2.6.

    Delete this and the cross-provider step can be written and never reached, which is a matrix
    that draws a fourth step and walks three."""
    anthropic = Scripted(TransportStatusError(503))
    moonshot = Scripted(ok())
    calls, _ = executor(
        Ladder(as_read_back("anthropic")),
        {"anthropic": anthropic, "moonshot": moonshot},
        profile=HOSTED_PROFILE,
        held=frozenset({"anthropic", "moonshot"}),
    )

    medium = ask(calls, Tier.MAIN)
    simple = ask(calls, Tier.SMALL)

    assert (medium.deployment_id, simple.deployment_id) == (
        "moonshot-kimi-k3",
        "moonshot-kimi-k2.6",
    )
    assert [one.model for one in moonshot.sent] == ["kimi-k3", "kimi-k2.6"]


# --- an earlier default, completed --------------------------------------------------------------


def written(provider: str) -> list[WrittenStep]:
    """The earlier default's rows as the store reads them back from the table."""
    return [WrittenStep.of(one) for one in earlier_default(provider)]


def test_an_untouched_earlier_default_is_completed_with_exactly_the_steps_the_matrix_adds() -> None:
    """**The upgrade.** The rows an install set up before 2026-09-29 holds, one primary in Medium
    and one in Complex, are completed with the ten steps that make them the owner's matrix, and
    the earlier rows plus the completion are the default step for step.

    Delete this and an install on the earlier default keeps two steps for ever, which is the
    owner's install as he found it: Simple empty and no failover."""
    added = completion("anthropic", written("anthropic"))
    whole = sorted(
        (*earlier_default("anthropic"), *added), key=lambda one: (one.tier.value, one.position)
    )

    assert len(earlier_default("anthropic")) == 2
    assert len(added) == 10
    assert [WrittenStep.of(one) for one in whole] == sorted(
        (WrittenStep.of(one) for one in default_ladder("anthropic")),
        key=lambda one: (one.tier.value, one.position),
    )


@pytest.mark.parametrize(
    "changed",
    [
        "a timeout",
        "a pause",
        "a narrowed scope",
        "another model",
        "a step added",
        "a step retired",
        "another provider's default",
    ],
)
def test_a_ladder_that_is_not_exactly_the_earlier_default_is_not_completed(changed: str) -> None:
    """**A ladder anybody changed is theirs.** Any difference from the rows the product wrote,
    in a number, the switch, the scope, the model, a step more or a step fewer, or the rows of
    another provider's default, and nothing is added.

    Positive sibling: `test_an_untouched_earlier_default_is_completed_with_exactly_the_steps_...`.

    Delete this and a start can add ten steps behind an administrator's own ladder, which is the
    product deciding against somebody who already decided."""
    rows = written("anthropic")
    first = rows[0]
    variants = {
        "a timeout": [replace(first, timeout_seconds=20.0), rows[1]],
        "a pause": [replace(first, enabled=False), rows[1]],
        "a narrowed scope": [replace(first, everywhere=False), rows[1]],
        "another model": [replace(first, model="claude-opus-5"), rows[1]],
        "a step added": [*rows, replace(first, position=1, deployment_id="anthropic-x")],
        "a step retired": [rows[1]],
        "another provider's default": written("openai"),
    }

    assert completion("anthropic", variants[changed]) == ()


@pytest.mark.parametrize("provider", ONE_PRIMARY_EACH)
def test_another_provider_s_earlier_default_is_already_complete(provider: str) -> None:
    """For every provider but Anthropic the earlier default is the whole default, so a start adds
    nothing to it.

    Delete this and an OpenAI install can be handed steps on a provider it never chose."""
    assert completion(provider, written(provider)) == ()


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


@pytest.mark.parametrize("provider", sorted(DEFAULT_MODELS))
def test_one_default_step_carries_exactly_the_numbers_the_default_ladder_writes(
    provider: str,
) -> None:
    """`default_rung` is what the Models screen's check sends a provider no step names through,
    and every primary `default_ladder` writes in the tiers a lane routes to is built from it, so
    the two cannot drift into two sets of numbers.

    Delete this and the check of a provider with no step can run at numbers no default step would
    carry, so a provider that passes the check can time out once it is given a step."""
    primaries = [
        one for one in default_ladder(provider) if one.position == 0 and one.tier in DEFAULT_TIERS
    ]
    assert [one.tier for one in primaries] == list(DEFAULT_TIERS)
    for step in primaries:
        assert default_rung(provider, step.tier, step.model) == step


def test_the_model_a_check_uses_is_the_products_default_then_the_registrys_first_then_none() -> (
    None
):
    """The product's own name for its first default level wins, a provider added from the console
    is checked with the first model its row lists, and one naming none has no default at all.

    Delete this and a check can be sent to a model nobody named, or skip the product's default
    for whatever the registry happens to list first."""
    assert (
        default_model("openai", ("some-other-model",)) == DEFAULT_MODELS["openai"][DEFAULT_TIERS[0]]
    )
    assert default_model("acme_llm", ("", "acme-1", "acme-2")) == "acme-1"
    assert default_model("acme_llm") is None
