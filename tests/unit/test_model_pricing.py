"""What a model call cost, from the provider's own count at the price this install set (M27.12.5).

The figure an agent's runs and cost are read from (M27.15.27), in the install's currency (M27.15.33).

Pure: `brain.models.pricing` and the per-call record `brain.models.metering.Meter` keeps for it.
The recorder that writes the figure and the database it lands in are `test_usage_store`'s.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brain.install import BY_NAME
from brain.models.driver import DriverResponse, TokenUsage
from brain.models.metering import AnsweredCall, Meter, MeteringError, ModelUsage
from brain.models.pricing import (
    MAX_PRICE_PLACES,
    MORE_THAN_ONE_MODEL,
    NO_CURRENCY,
    TOKENS_PER_PRICE,
    Costed,
    Price,
    PricingError,
    cost_of,
    decimal_of,
    price_of,
    stored_of,
    unpriced,
)

SGD = "SGD"


def price(input_minor: str, output_minor: str, currency: str = SGD) -> Price:
    return Price(
        input_minor=Decimal(input_minor), output_minor=Decimal(output_minor), currency=currency
    )


def call(tokens_in: int, tokens_out: int, *, model: str = "sonnet") -> AnsweredCall:
    return AnsweredCall(
        provider="anthropic", model=model, tokens_in=tokens_in, tokens_out=tokens_out
    )


PRICES = {
    ("anthropic", "sonnet"): price("300", "1500"),
    ("anthropic", "haiku"): price("0.075", "0.3"),
}


# --- the arithmetic ---------------------------------------------------------------------------


def test_a_call_costs_its_tokens_at_the_price_per_million_in_minor_units() -> None:
    """A million tokens in and a million out at 300 and 1500 minor units is 1800, and a thousand
    of each is 1.8, which rounds to 2.

    What breaks if this is deleted: the price's unit (per million) or the in and out halves can be
    swapped, and every cost on every page is out by the ratio between them."""
    assert TOKENS_PER_PRICE == 1_000_000
    assert cost_of([call(1_000_000, 1_000_000)], PRICES, currency=SGD) == Costed(1800, "sonnet")
    assert cost_of([call(1_000, 0)], PRICES, currency=SGD) == Costed(0, "sonnet")
    assert cost_of([call(0, 1_000)], PRICES, currency=SGD) == Costed(2, "sonnet")


def test_a_request_is_summed_exactly_and_rounded_once_to_the_nearest_half_even() -> None:
    """Three calls of 0.4 minor units each are 1.2 together, which is 1: rounding each call would
    say 0, and rounding each up would say 3. Half a unit goes to the even neighbour.

    What breaks if this is deleted: per-call rounding comes back, and a busy install's costs drift
    from the invoice by a unit per call, which is the bias the module docstring rules out."""
    tenths = [call(0, 800, model="sonnet") for _ in range(3)]
    assert cost_of(tenths, {("anthropic", "sonnet"): price("0", "500")}, currency=SGD) == Costed(
        1, "sonnet"
    )
    halves = {("anthropic", "sonnet"): price("0", "500000")}
    assert cost_of([call(0, 1)], halves, currency=SGD) == Costed(0, "sonnet")
    assert cost_of([call(0, 3)], halves, currency=SGD) == Costed(2, "sonnet")


def test_a_fractional_price_is_exact_and_never_a_binary_fraction() -> None:
    """0.075 per million is exactly 0.075: forty million input tokens cost 3 minor units.

    What breaks if this is deleted: a price read through a float costs a cheap model's traffic
    at the nearest binary fraction, and the difference is a rounding step on a large volume."""
    assert cost_of([call(40_000_000, 0, model="haiku")], PRICES, currency=SGD) == Costed(3, "haiku")


def test_a_call_with_no_price_or_a_price_in_another_currency_is_not_costed_at_all() -> None:
    """An unpriced model, a price in another currency and a request with one of each beside a
    priced call all cost None, never nought and never the priced part. The priced call alone is
    the sibling that is costed. The log's list names exactly the unpriced pairs.

    What breaks if this is deleted: an install nobody priced records every request at 0.00, which
    the page draws as the agent having cost nothing."""
    priced = call(1_000_000, 0)
    unknown = call(1_000_000, 0, model="opus")
    assert cost_of([priced], PRICES, currency=SGD) == Costed(300, "sonnet")
    assert cost_of([unknown], PRICES, currency=SGD) is None
    assert cost_of([priced, unknown], PRICES, currency=SGD) is None
    assert cost_of([priced], PRICES, currency="EUR") is None
    assert unpriced([priced, unknown], PRICES, currency=SGD) == (("anthropic", "opus"),)
    assert unpriced([priced], PRICES, currency="EUR") == (("anthropic", "sonnet"),)


def test_a_request_no_call_answered_is_not_costed() -> None:
    """What breaks if this is deleted: a request whose every attempt failed is written at nought,
    a figure the provider's own count never gave."""
    assert cost_of([], PRICES, currency=SGD) is None


def test_a_request_two_models_answered_names_neither_and_sums_both() -> None:
    """What breaks if this is deleted: the second model's cost is filed under the first on the
    spend report by model."""
    both = [call(1_000_000, 0), call(40_000_000, 0, model="haiku")]
    assert cost_of(both, PRICES, currency=SGD) == Costed(303, MORE_THAN_ONE_MODEL)


# --- the price ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "written", ["-1", "NaN", "Infinity", "abc", "", "1e10", "0." + "1" * (MAX_PRICE_PLACES + 1)]
)
def test_a_price_that_is_not_a_finite_bounded_figure_is_refused(written: str) -> None:
    """What breaks if this is deleted: a negative price makes a request earn money, and a slipped
    digit or an endless fraction is stored as a price somebody meant."""
    with pytest.raises(PricingError):
        decimal_of(written)


def test_a_price_is_read_from_text_and_never_from_a_float() -> None:
    """The positive case, and the float refusal beside it.

    What breaks if this is deleted: a JSON number reaches the price as a float and 0.075 becomes
    0.07499999999999999722444243843710864894092082977294921875."""
    assert decimal_of(" 0.075 ") == Decimal("0.075")
    assert decimal_of("0") == Decimal(0)
    with pytest.raises(PricingError):
        decimal_of(0.075)


def test_a_price_names_a_real_currency_and_never_the_code_for_none() -> None:
    """`NO_CURRENCY` is the install's own default, so a price set before a currency was chosen is
    refused by the type as well as by the route.

    What breaks if this is deleted: prices set in `XXX` are costed as whichever currency is chosen
    later, or the constant drifts from the install's default and the guard guards nothing."""
    assert BY_NAME["INSTALL_CURRENCY"].default == NO_CURRENCY
    with pytest.raises(PricingError):
        price("1", "1", NO_CURRENCY)
    with pytest.raises(PricingError):
        price("1", "1", "sgd")
    assert price("1", "1").currency == SGD


def test_a_stored_price_reads_back_as_the_price_it_was() -> None:
    """What breaks if this is deleted: the stored keys and the read keys drift apart and every
    price set on the Models screen reads back as unpriced."""
    one = price("0.075", "1500")
    assert price_of(stored_of(one)) == one
    assert all(isinstance(value, str) for value in stored_of(one).values())
    with pytest.raises(PricingError):
        price_of({"input_minor_per_million": 0.075, "output_minor_per_million": "1"})


# --- what the meter keeps ----------------------------------------------------------------------


def response(model: str, tokens_in: int, tokens_out: int) -> DriverResponse:
    return DriverResponse(
        deployment_id="d",
        model=model,
        text="x",
        usage=TokenUsage(input_tokens=tokens_in, output_tokens=tokens_out),
        finish_reason="stop",
    )


def test_each_answered_call_is_kept_under_the_model_its_rung_asked_for() -> None:
    """The response names a dated alias and the rung the name the ladder shows; the price book is
    keyed by the rung's. A caller with no rung keeps the response's name.

    What breaks if this is deleted: a provider echoing `sonnet-20260101` for `sonnet` misses the
    price an administrator set against the name the Models screen shows them."""
    meter = Meter()
    meter.attempted()
    meter.answered(
        response("sonnet-20260101", 10, 2), provider="anthropic", agent_version=None, model="sonnet"
    )
    meter.attempted()
    meter.answered(response("haiku", 5, 1), provider="anthropic", agent_version=None)
    usage = meter.usage()
    assert usage is not None
    assert usage.answered == (call(10, 2, model="sonnet"), call(5, 1, model="haiku"))


def test_a_usage_whose_calls_do_not_add_up_is_refused() -> None:
    """What breaks if this is deleted: a cost is priced from calls that disagree with the tokens on
    the same ledger row, and neither can be reconciled with the other."""
    usage = {
        "calls": 1,
        "tokens_in": 10,
        "tokens_out": 2,
        "model": "sonnet",
        "provider": "anthropic",
        "agent_version": None,
        "fallback_count": 0,
        "retry_count": 0,
    }
    assert ModelUsage(**usage, answered=(call(10, 2),)).answered == (call(10, 2),)
    with pytest.raises(MeteringError):
        ModelUsage(**usage, answered=(call(11, 2),))
    with pytest.raises(MeteringError):
        ModelUsage(**usage, answered=(call(5, 1), call(5, 1)))
