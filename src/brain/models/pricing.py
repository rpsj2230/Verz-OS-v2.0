"""What a model call cost: the provider's own token count, at the price this install set for it.

`brain.ops.spend.TIER_RATE_PER_KTOKEN` is the estimator's table and says so: "ratios first and
prices second", in no currency, and never measured against an invoice. A cost row written from it
would be an estimate recorded as an actual, which is the one figure `brain.ops.spend.Actual` exists
to keep apart from an estimate. So an actual is priced here, from a table an administrator sets per
provider and model on the Models screen (`brain.ops.price_store`), and from nothing else.

**A price names the currency it was set in, and a call is costed only in the install's own.**
`Actual.cost_minor` carries no currency because every row is in the install's, which
`brain.locale.currency` names. A price set while the install counted in one currency and read after
it moved to another would write a figure in the old currency under the new one's sign, so a price
in any currency but the install's prices nothing. See
`A_PRICE_IS_IN_THE_CURRENCY_IT_WAS_SET_IN_AND_COSTS_NOTHING_IN_ANOTHER`.

**A call with no price is not costed, and is never costed at nought.** Nought is a measurement,
and a request answered by a model nobody priced did cost something. `cost_of` returns None for a
request any of whose answered calls is unpriced, rather than the priced part of it, because a
partial sum filed as the request's cost is a wrong number with nothing on it saying so. The
recorder logs which provider and model were unpriced, and the Models screen lists every model on
the ladder that has no price. See `AN_UNPRICED_CALL_IS_NOT_COSTED_AND_NEVER_COSTED_AT_NOUGHT`.

**A price is minor units per million tokens, and it may have a fraction.** Providers price small
models at fractions of a cent per million tokens, so a whole number of minor units cannot hold the
price of the cheapest model on sale. A `Decimal` from text, never a float, so a price written as
0.075 is 0.075 and not the nearest binary fraction.

**A request's cost is summed exactly and rounded once, to the nearest minor unit, half to even.**
`Actual.cost_minor` is whole minor units. Rounding each call up, as the estimator rounds, would
overstate every request by half a minor unit on average, and a thousand questions a day would
drift from the invoice by the price of a lunch every week. Rounding to nearest has no bias, so the
sum over many requests converges on the invoice, which is `M21.4.1`'s test of a meter. See
`A_REQUEST_IS_SUMMED_EXACTLY_AND_ROUNDED_ONCE`.

**Cached input is priced as the provider counted it.** `ModelUsage` sums `input_tokens`, which one
provider reports including cache reads and another excluding them, and the ledger row holds that
sum; pricing anything else would cost a request from tokens the row does not show. A separate
cached price is a later refinement, stated rather than half built.

Scope: pure. Nothing here performs I/O or reads a clock.

Task ids: M27.12.5, M27.15.27, M27.15.33
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Final

from brain.locale import CURRENCY_PATTERN
from brain.models.metering import AnsweredCall

# ------------------------------------------------------------------- written-down reasons

#: Why a price in another currency costs nothing.
A_PRICE_IS_IN_THE_CURRENCY_IT_WAS_SET_IN_AND_COSTS_NOTHING_IN_ANOTHER: Final = (
    "A cost row carries no currency because every row is in the install's. A price set in one "
    "currency and read after the install moved to another would write the old currency's figure "
    "under the new one's sign, so a price prices a call only in the currency it was set in, and "
    "the model shows as unpriced until somebody sets it again."
)

#: Why an unpriced call leaves no cost rather than a cost of nought.
AN_UNPRICED_CALL_IS_NOT_COSTED_AND_NEVER_COSTED_AT_NOUGHT: Final = (
    "Nought is a measurement, and a call to a model nobody priced cost something. A request with "
    "any unpriced call is not costed at all, rather than costed at the part that was priced, and "
    "the Models screen names every model on the ladder that has no price."
)

#: Why a request is rounded once, to the nearest minor unit.
A_REQUEST_IS_SUMMED_EXACTLY_AND_ROUNDED_ONCE: Final = (
    "A cost row holds whole minor units. Rounding every call up overstates every request by half "
    "a unit on average and drifts from the invoice week by week; rounding the exact sum of a "
    "request to the nearest unit, half to even, has no bias, so many requests sum to the invoice."
)

# ------------------------------------------------------------------------------ the figures

#: Tokens a price is quoted for, which is how every provider quotes one.
TOKENS_PER_PRICE: Final = 1_000_000

#: The most decimal places a price may carry. A millionth of a minor unit per million tokens is
#: below anything sold, and a bound keeps a typed price from being a number nobody meant.
MAX_PRICE_PLACES: Final = 6

#: The most a price may be, in minor units per million tokens: ten million major units in a
#: currency of hundredths. Far above any model on sale, and a guard against a slipped digit.
MAX_PRICE_MINOR: Final = Decimal(1_000_000_000)

#: ISO 4217's code for no currency, which is also `INSTALL_CURRENCY`'s default. A price is never
#: set in it: a figure in no currency is the plausibly wrong unit `brain.locale` refuses to draw.
NO_CURRENCY: Final = "XXX"

#: What a cost row names as its model when the request's answered calls named more than one. A
#: row has one model column, and naming either model files the other's cost under it, which is
#: `brain.models.metering.A_REQUEST_ANSWERED_BY_TWO_MODELS_NAMES_NONE` for money.
MORE_THAN_ONE_MODEL: Final = "(more than one model)"

#: The stored keys of one price, which are also the words the API uses.
INPUT_KEY: Final = "input_minor_per_million"
OUTPUT_KEY: Final = "output_minor_per_million"
CURRENCY_KEY: Final = "currency"


class PricingError(ValueError):
    """A price no call could be costed at."""


def decimal_of(text: object) -> Decimal:
    """A price as a `Decimal`, from its text, or a refusal naming the rule it breaks.

    Text only: a float has already lost the digits a price is written in, and an integer is text
    the API sends as a string anyway.
    """
    if not isinstance(text, str):
        msg = "a price is written as text, such as 300 or 0.075, so no digit is lost on the way"
        raise PricingError(msg)
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        msg = "a price is a number of minor units per million tokens, such as 300 or 0.075"
        raise PricingError(msg) from None
    if not value.is_finite() or value < 0:
        msg = "a price is a finite number of minor units that is not below nought"
        raise PricingError(msg)
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > MAX_PRICE_PLACES:
        msg = f"a price has at most {MAX_PRICE_PLACES} decimal places"
        raise PricingError(msg)
    if value > MAX_PRICE_MINOR:
        msg = f"a price is at most {MAX_PRICE_MINOR} minor units per million tokens"
        raise PricingError(msg)
    return value


@dataclass(frozen=True)
class Price:
    """What a million tokens cost on one model, in and out, in the currency it was set in."""

    input_minor: Decimal
    output_minor: Decimal
    currency: str

    def __post_init__(self) -> None:
        for one in (self.input_minor, self.output_minor):
            decimal_of(str(one))
        if not CURRENCY_PATTERN.match(self.currency) or self.currency == NO_CURRENCY:
            msg = (
                "a price names the currency it was set in, three upper-case letters and never "
                f"{NO_CURRENCY}, which is the code for none"
            )
            raise PricingError(msg)


def price_of(stored: object) -> Price:
    """One stored price, through `Price`'s own checks. What `brain.ops.price_store` reads."""
    if not isinstance(stored, Mapping):
        msg = "a stored price is an object naming its two figures and its currency"
        raise PricingError(msg)
    currency = stored.get(CURRENCY_KEY)
    return Price(
        input_minor=decimal_of(stored.get(INPUT_KEY)),
        output_minor=decimal_of(stored.get(OUTPUT_KEY)),
        currency=currency if isinstance(currency, str) else "",
    )


def stored_of(price: Price) -> dict[str, Any]:
    """One price as it is kept: each figure as text, so no digit is lost in the JSON."""
    return {
        INPUT_KEY: str(price.input_minor),
        OUTPUT_KEY: str(price.output_minor),
        CURRENCY_KEY: price.currency,
    }


@dataclass(frozen=True)
class Costed:
    """What one request cost, in whole minor units of the install's currency, and its model."""

    cost_minor: int
    model: str


def cost_of(
    calls: Sequence[AnsweredCall],
    prices: Mapping[tuple[str, str], Price],
    *,
    currency: str,
) -> Costed | None:
    """What these calls cost together, or None when there is nothing honest to write.

    None for no answered call, which reported no tokens and so costs nothing a provider counted
    (`brain.models.metering.TOKENS_ARE_THE_PROVIDERS_COUNT_AND_A_FAILED_CALL_REPORTED_NONE`), and
    None for any call whose model has no price in `currency`. See the module docstring.
    """
    if not calls:
        return None
    exact = Decimal(0)
    for one in calls:
        price = prices.get((one.provider, one.model))
        if price is None or price.currency != currency:
            return None
        exact += one.tokens_in * price.input_minor + one.tokens_out * price.output_minor
    whole = (exact / TOKENS_PER_PRICE).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    models = {one.model for one in calls}
    return Costed(
        cost_minor=int(whole),
        model=next(iter(models)) if len(models) == 1 else MORE_THAN_ONE_MODEL,
    )


def unpriced(
    calls: Sequence[AnsweredCall], prices: Mapping[tuple[str, str], Price], *, currency: str
) -> tuple[tuple[str, str], ...]:
    """The provider and model of every call `cost_of` could not price, for the log line."""
    return tuple(
        sorted(
            {
                (one.provider, one.model)
                for one in calls
                if (found := prices.get((one.provider, one.model))) is None
                or found.currency != currency
            }
        )
    )
