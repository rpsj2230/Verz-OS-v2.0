"""The install checks for the routing chain's rules (M5.6.3), each passing and each shown failing.

The pure half holds the stand-ins to the product outside the module: each failure shape is read by
the product's own transport and adapter as the failure it is meant to be, and only the two in the
closed set may be fallen back on; the stand-ins reach nothing and name no provider of the product;
and a stand-in can never take a product provider's place.

The database half runs the module against PostgreSQL at head as the worker would, with the hosted
profile, every provider's key in a vault the test answers for, and `httpx.MockTransport` in the
place of the internet. All six checks pass and leave nothing. Then each clause's property is broken
in the product, one at a time, the way it would plausibly break (a 404 treated as a provider error,
a breaker that never opens or never closes, a residency skip that is not made, a refusal that
borrows its status, an agent's level dropped, a key from the environment, an attempt written under
another trace or counted twice), and the check for that clause is shown failing with its own
sentence. A check that passed whatever the product did would show up here as a mutation surviving.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M5.6.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from brain.models.adapter import SdkDriver, is_refusal
from brain.models.driver import DriverMessage, DriverRequest, ProviderUnavailable, Role
from brain.models.evidence import REFUSED, STOPPED, outcome_of
from brain.models.registry import SLUG_PATTERN
from brain.models.residency import requirement_of
from brain.models.routing import FallbackTrigger, may_fall_back, trigger_for
from brain.models.wire import PROVIDER_WIRES, added_wire, http_transport
from brain.ops import acceptance_models, acceptance_run, model_probe_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_models import STAND_IN, STAND_IN_ADDRESS
from brain.ops.acceptance_routing import (
    ANSWERS,
    DECLINES,
    ELSEWHERE,
    NOT_SERVED,
    OVERLOADED,
    RECOVERING,
    REFUSES,
    REGION,
    RESIDENT,
    RESIDENT_ADDRESS,
    UNREACHABLE,
    StandIns,
)
from brain.ops.provider_keys import PROVIDER_SLOTS, added_slot
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_models import Providers, laddered, live_ladder

MODULE = "brain.ops.acceptance_routing"

CLOSED_SET = "only_a_failure_in_the_closed_set_moves_to_the_next_step"
BREAKER = "a_failing_step_s_breaker_opens_and_closes_after_its_cooldown"
RESIDENCY = "a_residency_rule_skips_steps_outside_its_region_or_refuses"
REFUSAL = "a_content_refusal_is_never_tried_on_another_model"
AGENT = "an_agents_complex_question_uses_heavy_and_the_vault_key"
TRACE = "every_attempt_of_a_walk_is_on_the_request_s_trace"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_clause_of_the_leaf() -> None:
    """Six clauses, six rows, each closing M5.6.3 and nothing else. Delete this and a clause can
    lose its check with the page simply showing one row fewer, and the leaf closed on five."""
    checks = [(one.name, one.leaves) for one in registered((MODULE,))]
    assert checks == [
        (name, ("M5.6.3",)) for name in (CLOSED_SET, BREAKER, RESIDENCY, REFUSAL, AGENT, TRACE)
    ]


def _sent(model: str, responder: StandIns) -> Any:
    """One call to a stand-in through the product's own transport and adapter."""
    client = httpx.Client(transport=httpx.MockTransport(responder))
    driver = SdkDriver(
        provider=STAND_IN,
        transport=http_transport(
            added_wire(STAND_IN, STAND_IN_ADDRESS, added_slot(STAND_IN)),
            client=client,
            key=lambda: "test-stand-in-not-a-key",
        ),
    )
    request = DriverRequest(
        deployment_id=f"{STAND_IN}-{model}",
        model=model,
        messages=(DriverMessage(role=Role.USER, content="A question."),),
        timeout_seconds=1.0,
    )
    try:
        return driver.complete(request)
    except ProviderUnavailable as failed:
        return failed.failure
    finally:
        client.close()


def test_each_stand_in_is_read_by_the_product_as_the_failure_it_stands_for() -> None:
    """Held against the adapter, the evidence and the closed set, which are outside the module:
    the 404 stops the chain, the 503 and the refused connection are in the closed set, the 400 is a
    refusal, the content filter is a refusal inside a reply, and only the two in the closed set may
    be fallen back on. Delete this and a stand-in's body can drift from the shape the product reads,
    and a check passes on a failure the product never classifies that way."""
    responder = StandIns()
    outcomes = {model: _sent(model, responder) for model in (NOT_SERVED, OVERLOADED, REFUSES)}
    outcomes[UNREACHABLE] = _sent(UNREACHABLE, responder)
    assert outcome_of(outcomes[NOT_SERVED]) == STOPPED and outcomes[NOT_SERVED].status == 404
    assert outcomes[OVERLOADED].trigger is FallbackTrigger.PROVIDER_ERROR
    assert outcome_of(outcomes[REFUSES]) == REFUSED and outcomes[REFUSES].trigger is None
    assert outcomes[UNREACHABLE].trigger is FallbackTrigger.CONNECTION_ERROR
    assert [model for model, one in outcomes.items() if may_fall_back(outcome_of(one))] == [
        OVERLOADED,
        UNREACHABLE,
    ]
    declined = _sent(DECLINES, responder)
    assert is_refusal(declined.finish_reason)
    answered = _sent(ANSWERS, responder)
    assert answered.text and not is_refusal(answered.finish_reason)


def test_the_recovering_stand_in_fails_to_connect_until_it_is_told_it_has_recovered() -> None:
    """The breaker check's step: down, then up. Delete this and the probe after the cooldown can be
    sent to a step that is still down, and the check fails for a reason that is the test's."""
    responder = StandIns()
    assert _sent(RECOVERING, responder).trigger is FallbackTrigger.CONNECTION_ERROR
    responder.recovered = True
    assert _sent(RECOVERING, responder).text
    assert responder.sent_to(STAND_IN_ADDRESS, RECOVERING) == 2


def test_the_stand_ins_reach_nothing_and_name_no_provider_of_the_product() -> None:
    """`A_FAILURE_SHAPE_IS_ANSWERED_IN_THE_PROCESS`: both addresses are under `.invalid`, both slugs
    are ones the registry can hold and no product provider owns, and the two regions are ones a
    constraint may allow and different from each other. Delete this and a stand-in can be pointed at
    a host that answers, or named like a provider whose key it would be sent."""
    for address in (STAND_IN_ADDRESS, RESIDENT_ADDRESS):
        assert httpx.URL(address).host.endswith(".invalid") and address.startswith("https://")
    import re

    for slug in (STAND_IN, RESIDENT):
        assert re.fullmatch(SLUG_PATTERN, slug)
        assert slug not in PROVIDER_WIRES and slug not in {one.slug for one in PROVIDER_SLOTS}
    assert len({REGION, ELSEWHERE}) == 2
    for region in (REGION, ELSEWHERE):
        assert requirement_of([region], on_prem_only=False).allowed_regions == frozenset({region})


def test_a_stand_in_named_like_a_product_provider_does_not_replace_its_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard in `models_for`: a driver handed in under a product provider's name is dropped, so
    a check cannot answer for a real provider in its place. Its positive sibling: one under a
    stand-in's name is kept. Delete this and a mistyped slug makes a routing check pass with a
    stand-in answering as OpenAI."""
    from brain.ops.acceptance_run import Harness

    for one in PROVIDER_SLOTS:
        monkeypatch.delenv(one.env_var, raising=False)
    monkeypatch.setattr(model_probe_run, "_PROCESS_KEYS", {})
    harness = Harness(run="0a1b2c3d", now=None, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    impostor, stand_in = object(), object()
    models = asyncio.run(
        acceptance_models.models_for(
            harness,
            standing={"openai": impostor, STAND_IN: stand_in},  # type: ignore[dict-item]
        )
    )
    drivers = models.calls._drivers  # the executor's own map, read to show what it holds
    assert drivers["openai"] is not impostor
    assert drivers[STAND_IN] is stand_in
    asyncio.run(harness.undo(stream=__import__("sys").stderr))


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    """One database at head for the module, with the ladder the wizard writes. Every check rolls
    back, so the runs below share it; the first test measures that they do."""
    with at_head("brain_acceptance_routing") as url:
        laddered(url)
        yield url


@pytest.fixture
def vaulted(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """The hosted profile, every provider's key in a vault the test answers for and none in the
    environment, and the providers `tests/unit/test_acceptance_models.py` answers as. The keys are
    this file's test values and reach nothing: every request is answered in the process."""
    from brain.ops.openbao import OpenBaoVault

    answering = Providers()
    for one in PROVIDER_SLOTS:
        monkeypatch.delenv(one.env_var, raising=False)
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")
    monkeypatch.setattr(model_probe_run, "_PROCESS_KEYS", {})
    monkeypatch.setattr(
        OpenBaoVault,
        "read_static_kv",
        lambda self, path: {"api_key": f"test-{path.rsplit('/', 1)[-1]}-not-a-key"},
    )
    monkeypatch.setattr(
        acceptance_models,
        "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(answering)),
    )
    return answering


def run_routing(url: str, *names: str) -> dict[str, tuple[str, str]]:
    """The module's checks, or the ones named, run as the worker runs them."""
    from brain.db import normalise_database_url

    settings = settings_from(
        {
            "BRAIN_DATABASE_URL": url,
            "BRAIN_VAULT_ADDRESS": "https://vault.acceptance.invalid",
            "BRAIN_VAULT_TOKEN": "test-token-not-a-token",
        }
    )
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_every_routing_check_passes_on_an_install_and_leaves_nothing(
    install: str, vaulted: Providers, capsys: pytest.CaptureFixture[str]
) -> None:
    """**The module run as the worker runs it, against PostgreSQL at head.** All six pass; every
    table a check wrote to, the residency constraints and the provider registry among them, holds
    what it held before, and so does the ladder; exactly one request reached a provider of the
    product, the agent's Complex question; and no key reached a line of output. Delete this and a
    check that can never pass, one that commits a constraint, or one that makes more real calls
    than its module says, reaches the owner's server first."""
    before, ladder = counts(install), live_ladder(install)
    outcomes = run_routing(install)
    after, left = counts(install), live_ladder(install)
    said = capsys.readouterr()

    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 6
    assert after == before and left == ladder and ladder
    real = {httpx.URL(one.base_url).host for one in PROVIDER_WIRES.values()}
    assert len(vaulted.sent) == 1 and vaulted.hosts() <= real
    assert "not-a-key" not in said.out + said.err


@pytest.mark.needs_db
def test_a_company_wide_residency_rule_is_set_aside_inside_the_check_and_stands_after(
    install: str, vaulted: Providers
) -> None:
    """`THE_CONSTRAINTS_ARE_PINNED_INSIDE_THE_TRANSACTION`, with a rule to set aside: an install
    whose committed constraint covers every scope still passes the stand-in checks, because each
    retires it inside its own transaction, and the rule is live and unchanged afterwards. Delete
    this and the retirement is a branch no test reaches, so a check can either fail on every
    install with a company-wide rule or commit the rule's retirement."""
    from tests.fixtures.scratch_postgres import sql

    sql(
        install,
        "INSERT INTO ops.residency_constraint (scope, allowed_regions, created_by)"
        " VALUES (%s::jsonb, %s::jsonb, 'u_admin')",
        '{"clauses": []}',
        '["eu-west-1"]',
    )
    try:
        outcomes = run_routing(install, CLOSED_SET, RESIDENCY)
        live = sql(
            install, "SELECT allowed_regions FROM ops.residency_constraint WHERE deleted_at IS NULL"
        )
    finally:
        sql(install, "DELETE FROM ops.residency_constraint")
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2 and live == [(["eu-west-1"],)]


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_routing(url, name).values()
    assert outcome == FAILED, reason
    return reason


def _wrapped(original: Callable[..., Any], change: Callable[..., Any]) -> Callable[..., Any]:
    def call(*args: Any, **kwargs: Any) -> Any:
        return change(original, *args, **kwargs)

    return call


@pytest.mark.needs_db
def test_a_404_the_chain_fell_back_on_fails_the_closed_set_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property broken: a 404 read as a provider error, so an unknown model is tried on the
    next step. Delete this and the closed-set check can pass on a chain that falls back on
    anything."""

    def change(original: Callable[..., Any], **kwargs: Any) -> Any:
        if kwargs.get("status") == 404:
            return FallbackTrigger.PROVIDER_ERROR
        return original(**kwargs)

    monkeypatch.setattr("brain.models.driver.trigger_for", _wrapped(trigger_for, change))
    assert _failed(install, CLOSED_SET) == (
        "a failure outside the closed set did not stop the chain at its step"
    )


@pytest.mark.needs_db
def test_a_503_the_chain_stopped_on_fails_the_closed_set_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half: a 503 read as no trigger, so a provider error ends the walk. Delete this and
    the check can pass on a chain that never falls back at all."""

    def change(original: Callable[..., Any], **kwargs: Any) -> Any:
        return None if kwargs.get("status") == 503 else original(**kwargs)

    monkeypatch.setattr("brain.models.driver.trigger_for", _wrapped(trigger_for, change))
    assert _failed(install, CLOSED_SET) == (
        "a failure inside the closed set was not answered by the next step"
    )


@pytest.mark.needs_db
def test_a_breaker_that_never_opens_fails_the_breaker_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The replay counting no failure as ill health, so three refused connections open nothing.
    Delete this and the check can pass with the breaker never consulted."""
    from brain.models import evidence

    monkeypatch.setattr(evidence, "ILL_HEALTH", frozenset())
    assert _failed(install, BREAKER) == "three failures in a row did not open the step's breaker"


@pytest.mark.needs_db
def test_a_breaker_that_never_closes_fails_the_breaker_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A half-open breaker that stays half open when its probe answers. Delete this and the check
    can pass on a step taken out of rotation for good after one bad minute."""
    from brain.models.routing import BreakerState, CircuitBreaker

    original = CircuitBreaker.record_success

    def stays(self: CircuitBreaker, now: Any) -> CircuitBreaker:
        return self if self.state is BreakerState.HALF_OPEN else original(self, now)

    monkeypatch.setattr(CircuitBreaker, "record_success", stays)
    assert _failed(install, BREAKER) == "the probe answering did not close the breaker"


@pytest.mark.needs_db
def test_a_step_outside_the_region_being_asked_fails_the_residency_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every step satisfying every rule, so the step documented nowhere answers acceptance_a.
    Delete this and the check can pass with residency never applied."""
    from brain.models.routing import ResidencyRequirement

    monkeypatch.setattr(ResidencyRequirement, "satisfied_by", lambda self, deployment: True)
    assert _failed(install, RESIDENCY) == (
        "a question under a residency rule was not answered in its region"
    )


@pytest.mark.needs_db
def test_a_question_sent_where_no_step_complies_fails_the_residency_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only acceptance_b's rule ignored: a question nothing complies for is answered rather than
    refused. Delete this and the check can pass on a chain that degrades across a border when the
    compliant steps run out, which is the failure residency exists to prevent."""
    from brain.models.routing import ResidencyRequirement

    original = ResidencyRequirement.satisfied_by

    def waived(self: ResidencyRequirement, deployment: Any) -> bool:
        return self.allowed_regions == frozenset({ELSEWHERE}) or original(self, deployment)

    monkeypatch.setattr(ResidencyRequirement, "satisfied_by", waived)
    assert _failed(install, RESIDENCY) == (
        "a question whose region no step is in was not refused with the product's sentence"
    )


@pytest.mark.needs_db
def test_a_residency_refusal_told_as_an_outage_fails_the_residency_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The chain refusing, but in an outage's words, which sends the asker to wait for a recovery
    that will not come. Delete this and the check can pass on any refusal, whatever it says."""
    from brain.core.errors import Degraded
    from brain.models.routing import ChainSelection, NoCompliantRoute

    def outage(self: ChainSelection) -> Any:
        if self.rungs:
            return self.rungs
        raise NoCompliantRoute("nothing left", public_message=Degraded.public_message)

    monkeypatch.setattr(ChainSelection, "require", outage)
    assert _failed(install, RESIDENCY) == (
        "a question whose region no step is in was not refused with the product's sentence"
    )


@pytest.mark.needs_db
def test_a_refusal_that_borrows_its_status_fails_the_refusal_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect `brain.models.adapter.failure_from` is written against: a refusal kept as the
    status it arrived with, so the chain shops for another model. Delete this and the check can
    pass on a chain that retries a refusal until something says yes."""
    from brain.models import adapter
    from brain.models.driver import DriverFailure

    original = adapter.failure_from

    def borrowed(exc: BaseException, *, deployment_id: str) -> DriverFailure:
        if isinstance(exc, adapter.ContentPolicyRefusedError):
            return DriverFailure(deployment_id=deployment_id, status=503)
        return original(exc, deployment_id=deployment_id)

    monkeypatch.setattr(adapter, "failure_from", borrowed)
    assert _failed(install, REFUSAL) == (
        "a model declining on content was not told to the asker as such"
    )


@pytest.mark.needs_db
def test_an_agent_s_level_dropped_fails_the_agent_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer lane classifying an agent's question without its level, so it lands on Medium.
    Delete this and the check can pass with every agent answered at the default level."""
    from brain.gate import model_lane

    original = model_lane.routing_for
    monkeypatch.setattr(
        model_lane, "routing_for", lambda messages, requested=None: original(messages)
    )
    assert _failed(install, AGENT) == (
        "an agent's Complex question was not routed to the level it pins"
    )
    assert vaulted.sent == []


@pytest.mark.needs_db
def test_a_key_the_environment_supplied_fails_the_agent_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every provider's key set in the worker's environment, which outranks the vault. Delete this
    and the check can pass on a key nobody kept in the install's vault."""
    for one in PROVIDER_SLOTS:
        monkeypatch.setenv(one.env_var, f"test-{one.slug}-not-a-key")
    assert _failed(install, AGENT) == "the key the call read was not the install's vault key"


@pytest.mark.needs_db
def test_an_attempt_written_under_another_trace_fails_the_trace_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every attempt after the first written under a trace that is not the request's. Delete this
    and the check can pass with a walk's fallbacks missing from its trace."""
    from brain.ops import model_service

    def change(
        original: Callable[..., Any], trace_id: str, rung_id: str, sequence: int, *a: Any
    ) -> Any:
        return original(trace_id if sequence == 0 else f"{trace_id}-x", rung_id, sequence, *a)

    monkeypatch.setattr(
        model_service, "attempt_started", _wrapped(model_service.attempt_started, change)
    )
    assert _failed(install, TRACE) == "an attempt of the walk was not on the request's trace"


@pytest.mark.needs_db
def test_an_attempt_never_written_fails_the_trace_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second of three attempts left unrecorded. Delete this and the check can pass with an
    attempt missing from the rows the trace is read from."""
    from brain.ops.model_service import SessionAttempts

    original = SessionAttempts.started

    async def skipped(self: SessionAttempts, **kwargs: Any) -> str:
        return "" if kwargs["sequence"] == 1 else await original(self, **kwargs)

    monkeypatch.setattr(SessionAttempts, "started", skipped)
    assert _failed(install, TRACE) == "the walk's attempts were not in sequence from the first"


@pytest.mark.needs_db
def test_a_fallback_the_meter_lost_fails_the_trace_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The meter not counting a fallback, so the request row says fewer attempts than the rows
    hold. (Counting one twice is refused by the meter's own usage check before any row is written,
    so that is not the way this breaks.) Delete this and the request row and the attempt rows can
    disagree with the check passing."""
    from brain.models.metering import Meter

    monkeypatch.setattr(Meter, "fell_back", lambda self: None)
    assert _failed(install, TRACE) == (
        "the request row counted attempts the attempt rows do not hold"
    )
