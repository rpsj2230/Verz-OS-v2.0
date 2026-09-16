"""What a request's model calls consumed, how the ledger row records it, and the health read back.

Three halves of one path: `brain.models.metering` counts a request's calls, `brain.ops.telemetry`
turns the count into the ledger row's seven model fields, and `brain.models.evidence` replays the
attempts those calls left into each deployment's breaker.

Task ids: M27.7.14, M27.1.5, M27.8.8, M5.3.4
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import EntitlementSet
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.gate.context import Channel
from brain.gate.finish import Finished, ModelCallOutcome, Origin, ToolCallOutcome
from brain.models.driver import DriverFailure, DriverResponse, TokenUsage
from brain.models.evidence import (
    EVIDENCE_WINDOW,
    ILL_HEALTH,
    OK,
    OUTCOMES,
    STOPPED,
    Attempt,
    EvidenceError,
    outcome_of,
    replayed,
)
from brain.models.metering import Meter, MeteringError, ModelUsage
from brain.models.routing import (
    BREAKER_CONSECUTIVE_FAILURES,
    BREAKER_MAX_COOLDOWN_SECONDS,
    BreakerState,
    FallbackTrigger,
)
from brain.ops.telemetry import (
    FILLED_BY_A_MODEL_CALL,
    RequestStatus,
    ledger_name,
    request_telemetry_of,
)
from brain.tables.routing import ATTEMPT_OUTCOMES

#: Far outside any plausible wall clock, because nothing here is about the present.
T0 = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)
TRACE = "a" * 32


def response(model: str, tokens_in: int, tokens_out: int) -> DriverResponse:
    return DriverResponse(
        deployment_id=f"{model}-global",
        model=model,
        text="ready",
        usage=TokenUsage(input_tokens=tokens_in, output_tokens=tokens_out),
        finish_reason="stop",
    )


# ------------------------------------------------------------------------- the meter


def test_a_request_that_called_no_model_has_no_usage_at_all() -> None:
    """None and not a usage of zero calls, which the ledger would record as a model call made.

    Delete this and every answer-lane row starts carrying zero tokens, which a usage report reads
    as questions that cost nothing rather than questions that called no model."""
    assert Meter().usage() is None
    with pytest.raises(MeteringError):
        ModelUsage(
            calls=0,
            tokens_in=0,
            tokens_out=0,
            model=None,
            provider=None,
            agent_version=None,
            fallback_count=0,
            retry_count=0,
        )


def test_tokens_are_summed_over_answers_and_a_failed_attempt_counts_as_a_call_and_no_tokens() -> (
    None
):
    """Delete this and a failed attempt can add an estimate, or an answered one can be dropped."""
    meter = Meter()
    meter.attempted()
    meter.fell_back()
    meter.attempted()
    meter.answered(response("claude-sonnet-5", 100, 20), provider="anthropic", agent_version=None)

    assert meter.usage() == ModelUsage(
        calls=2,
        tokens_in=100,
        tokens_out=20,
        model="claude-sonnet-5",
        provider="anthropic",
        agent_version=None,
        fallback_count=1,
        retry_count=0,
    )


def test_a_request_answered_by_two_models_sums_their_tokens_and_names_neither() -> None:
    """Delete this and the second model's tokens are filed under the first on the model table."""
    meter = Meter()
    meter.attempted()
    meter.answered(response("claude-sonnet-5", 10, 1), provider="anthropic", agent_version="a1")
    meter.attempted()
    meter.answered(response("kimi-k2", 20, 2), provider="moonshot", agent_version="a1")

    usage = meter.usage()
    assert usage is not None
    assert (usage.tokens_in, usage.tokens_out) == (30, 3)
    assert usage.model is None
    assert usage.provider is None
    assert usage.agent_version == "a1"


def test_an_answer_recorded_before_any_attempt_is_refused() -> None:
    """Delete this and a caller can record tokens for a call it never counted, so `calls` is
    lower than the answers it carries."""
    with pytest.raises(MeteringError):
        Meter().answered(response("m", 1, 1), provider="p", agent_version=None)


def test_retries_and_fallbacks_cannot_outnumber_the_calls_after_the_first() -> None:
    """Delete this and a usage claiming two fallbacks out of two calls is written to the ledger."""
    ModelUsage(
        calls=3,
        tokens_in=0,
        tokens_out=0,
        model=None,
        provider=None,
        agent_version=None,
        fallback_count=1,
        retry_count=1,
    )
    with pytest.raises(MeteringError):
        ModelUsage(
            calls=2,
            tokens_in=0,
            tokens_out=0,
            model=None,
            provider=None,
            agent_version=None,
            fallback_count=1,
            retry_count=1,
        )
    with pytest.raises(MeteringError):
        ModelUsage(
            calls=1,
            tokens_in=-1,
            tokens_out=0,
            model=None,
            provider=None,
            agent_version=None,
            fallback_count=0,
            retry_count=0,
        )


# --------------------------------------------------------------------- the ledger row


def finished(outcome: object, usage: ModelUsage | None) -> Finished:
    return Finished(
        origin=Origin(
            trace_id=TRACE,
            principal=Principal(
                id="u_admin",
                kind=PrincipalKind.HUMAN,
                employment=Employment.STAFF,
                display_name="An administrator",
            ),
            channel=Channel.CONSOLE,
        ),
        at=T0,
        outcome=outcome,  # type: ignore[arg-type]
        completed_at=T0 + timedelta(milliseconds=40),
        entitlement_hash=EntitlementSet(principal_id="u_admin", grants=()).ent_hash(),
        lane=Lane.ANSWER,
        tool_calls=0,
        model_usage=usage,
    )


def test_a_metered_request_fills_the_seven_model_fields_of_its_ledger_row() -> None:
    """The one copy of the tokens. Delete this and the executor meters calls into a summary no
    row ever reads, which is exactly the gap this work closed."""
    usage = ModelUsage(
        calls=3,
        tokens_in=1204,
        tokens_out=88,
        model="Claude-Sonnet-5",
        provider="anthropic",
        agent_version="2.4.1",
        fallback_count=1,
        retry_count=1,
    )

    row = request_telemetry_of(finished(ModelCallOutcome(answered=True), usage))

    assert {name: getattr(row, name) for name in FILLED_BY_A_MODEL_CALL} == {
        "agent_version": "2.4.1",
        "model": "claude-sonnet-5",
        "provider": "anthropic",
        "tokens_in": 1204,
        "tokens_out": 88,
        "fallback_count": 1,
        "retry_count": 1,
    }
    assert row.status is RequestStatus.ANSWERED
    assert row.cache_hit is False


def test_a_request_with_no_usage_leaves_every_model_field_empty() -> None:
    """Delete this and a default of zero can be put back on the row for requests that called no
    model, which is `A_FIELD_NOBODY_MEASURES_IS_NONE_AND_NEVER_ZERO` broken by a caller."""
    row = request_telemetry_of(finished(ToolCallOutcome(refused=False), None))
    for name in FILLED_BY_A_MODEL_CALL:
        assert getattr(row, name) is None, name


def test_a_model_call_that_reached_no_provider_is_degraded_and_never_why() -> None:
    """Delete this and a failed provider check is recorded as answered, or as a fault of ours."""
    assert request_telemetry_of(finished(ModelCallOutcome(answered=False), None)).status is (
        RequestStatus.DEGRADED
    )


def test_a_vendor_name_is_folded_and_one_the_ledger_cannot_hold_is_dropped_not_refused() -> None:
    """A capitalised model name folds; one with a character the trace grammar treats as a value is
    dropped, and the row keeps its tokens.

    Delete this and a local runtime naming its model `Qwen/Qwen3 8B` loses every ledger row it
    serves, tokens and duration included."""
    assert ledger_name("Qwen/Qwen3-8B") == "qwen/qwen3-8b"
    assert ledger_name("my model") is None
    assert ledger_name("   ") is None
    assert ledger_name(None) is None
    usage = ModelUsage(
        calls=1,
        tokens_in=5,
        tokens_out=1,
        model="my model",
        provider="local",
        agent_version=None,
        fallback_count=0,
        retry_count=0,
    )
    row = request_telemetry_of(finished(ModelCallOutcome(answered=True), usage))
    assert row.model is None
    assert (row.tokens_in, row.tokens_out) == (5, 1)


# ------------------------------------------------------------------------ the evidence


def failures(deployment: str, count: int, *, start: datetime, outcome: str) -> list[Attempt]:
    return [
        Attempt(deployment_id=deployment, finished_at=start + timedelta(seconds=i), outcome=outcome)
        for i in range(count)
    ]


def test_the_outcomes_replayed_are_exactly_the_ones_the_attempt_column_admits() -> None:
    """Compared with the table's own vocabulary, which is built separately.

    Delete this and an outcome the executor writes can be one the column refuses, or one the
    replay refuses to read, and either way the evidence is lost."""
    assert frozenset(ATTEMPT_OUTCOMES) == OUTCOMES
    assert ILL_HEALTH < OUTCOMES
    assert outcome_of(None) == OK
    assert outcome_of(DriverFailure(deployment_id="d", status=400)) == STOPPED
    assert outcome_of(DriverFailure(deployment_id="d", status=503)) == (
        FallbackTrigger.PROVIDER_ERROR.value
    )
    with pytest.raises(EvidenceError):
        Attempt(deployment_id="d", finished_at=T0, outcome="weak_answer")
    with pytest.raises(EvidenceError):
        Attempt(deployment_id="d", finished_at=T0.replace(tzinfo=None), outcome=OK)


def test_consecutive_provider_failures_open_the_breaker_and_other_failures_do_not() -> None:
    """Three connection failures, timeouts or server errors open it; a rate limit, a stop and an
    overflow are the provider answering.

    Delete this and either a working provider is taken out of rotation over a question asked
    twice, or a dead one is never taken out."""
    for ill in sorted(ILL_HEALTH):
        opened = replayed(failures("d", BREAKER_CONSECUTIVE_FAILURES, start=T0, outcome=ill))
        assert opened["d"].state is BreakerState.OPEN, ill
    for fine in (
        FallbackTrigger.RATE_LIMITED.value,
        STOPPED,
        FallbackTrigger.CONTEXT_EXCEEDED.value,
    ):
        kept = replayed(failures("d", 10, start=T0, outcome=fine))
        assert kept["d"].state is BreakerState.CLOSED, fine
        assert kept["d"].live == ()


def test_a_deployment_nothing_attempted_has_no_health_record() -> None:
    """Absent, not closed. Delete this and the screen's `measured` has nothing to be false about."""
    health = replayed([Attempt(deployment_id="called", finished_at=T0, outcome=OK)])
    assert set(health) == {"called"}


def test_an_answer_after_the_cooldown_closes_the_breaker_it_was_the_half_open_request_for() -> None:
    """The replay advances to each attempt's instant before recording it.

    Delete this and a provider that recovered stays drawn open for as long as the window holds
    the failures, because its first good answer is dropped as a stray."""
    opened_at = T0 + timedelta(seconds=BREAKER_CONSECUTIVE_FAILURES - 1)
    attempts = [
        *failures("d", BREAKER_CONSECUTIVE_FAILURES, start=T0, outcome="timeout"),
        Attempt(
            deployment_id="d",
            finished_at=opened_at + timedelta(seconds=BREAKER_MAX_COOLDOWN_SECONDS + 1),
            outcome=OK,
        ),
    ]
    assert replayed(attempts)["d"].state is BreakerState.CLOSED
    assert replayed(attempts[:-1])["d"].state is BreakerState.OPEN


def test_the_evidence_window_outlasts_the_longest_cooldown() -> None:
    """Compared with the routing module's ceiling. Delete this and a shortened window can start
    after a breaker opened and before it cooled, so every process reads a dead provider closed."""
    assert timedelta(seconds=BREAKER_MAX_COOLDOWN_SECONDS) < EVIDENCE_WINDOW
