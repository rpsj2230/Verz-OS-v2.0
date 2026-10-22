"""Metered spend held against a provider's own invoice, and what the difference is.

`brain.models.pricing` prices every model call from a table an administrator sets and says in so
many words that it is "M21.4.1's test of a meter": request costs are rounded once, half to even, so
that many of them sum to the invoice. Nothing ever held the sum against an invoice, so the meter was
believed rather than checked. This is the comparison, and it decides nothing about money.

**The unit is the provider's, not the install's.** An invoice arrives in the provider's currency and
the ledger is in the install's, so a figure shown beside it in the install's currency would leave
the reader to convert. The comparison is therefore made in the invoice's currency: the metered spend
is converted with a rate the person types, and the response states the rate it used. There is no
exchange-rate source here and there must not be one: a rate fetched by the product would be a
number nobody entered and nobody can be asked about, and the invoice carries its own.
A different currency without a rate is refused, not guessed. See
`A_DIFFERENT_CURRENCY_NEEDS_THE_RATE_THE_INVOICE_USED`.

**A provider is the provider a price was set under.** A cost row names its model and no provider,
and a model is priced per provider (`brain.ops.price_store`). A model priced under exactly one
provider is that provider's. A model priced under two is attributed to neither and its spend is
reported as not attributed, because splitting it by a rule would put a figure beside an invoice
that neither provider charged. A cost row whose model is none of those, including the row a
request answered by more than one model leaves, is reported as not attributed too, with its
amount, so the sum of the lines and the not-attributed amount is every row in the window. See
`WHAT_CANNOT_BE_ATTRIBUTED_IS_SAID_BESIDE_WHAT_CAN`.

**The tolerance is stated, not tuned.** Two per cent of the invoice. Request costs are rounded
without bias, so the legitimate sources of a difference are prices that moved during the period, a
model priced from a stale table and calls not made through this product with the same key; none of
them is below two per cent on a real bill, and a looser figure would pass a mispriced model. It is
returned with every answer so a reader sees what the verdict was held to. See
`RECONCILIATION_TOLERANCE`.

**Nothing here writes.** The comparison is computed from the ledger and the figures typed, and the
answer is a screen's, not a record: an invoice figure kept would be a second place for a number the
provider holds, and one that would be wrong the day the provider issues a credit note.

Task ids: M21.4.1
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Final

from brain.locale import CURRENCY_PATTERN

# ------------------------------------------------------------------ written-down reasons
#: Why a different currency needs a rate typed.
A_DIFFERENT_CURRENCY_NEEDS_THE_RATE_THE_INVOICE_USED: Final = (
    "An invoice in another currency than the install's is compared in its own currency, using the "
    "rate you type. The product does not fetch a rate: one it fetched would be a number nobody "
    "entered, on a day the provider did not use, and the invoice states the rate it applied."
)

#: Why what cannot be attributed to a provider is said beside what can.
WHAT_CANNOT_BE_ATTRIBUTED_IS_SAID_BESIDE_WHAT_CAN: Final = (
    "A cost row names its model and not its provider. A model priced under two providers, one "
    "nobody priced and a request answered by more than one model are not attributed to any "
    "provider, and their spend is shown as its own line, so the lines add up to everything the "
    "ledger recorded in the window and none of it is silently dropped."
)

# ------------------------------------------------------------------------ the figures
#: How far metered spend may differ from the invoice and still reconcile: two per cent.
RECONCILIATION_TOLERANCE: Final = Decimal("0.02")

#: The most decimal places a rate may carry. An exchange rate is quoted to six at most.
MAX_RATE_PLACES: Final = 6


class ReconcileError(ValueError):
    """A comparison that cannot be made as asked, in a sentence for the person asking."""


@dataclass(frozen=True)
class Attributed:
    """The spend of a window, split by provider, and what no provider could be given."""

    by_provider: Mapping[str, tuple[int, int]]
    unattributed_minor: int
    unattributed_requests: int


@dataclass(frozen=True)
class Comparison:
    """One provider's metered spend against its invoice, in the invoice's currency."""

    provider: str
    currency: str
    invoice_minor: int
    metered_minor: int
    #: Metered less invoiced. Positive where the product metered more than it was billed.
    difference_minor: int
    #: The difference as a fraction of the invoice, or None for an invoice of nothing.
    difference_fraction: Decimal | None
    tolerance: Decimal
    within_tolerance: bool
    #: The rate used to bring the metered spend into the invoice's currency, or None for the same.
    rate: Decimal | None


def rate_of(text: str) -> Decimal:
    """A rate from its text, or a refusal naming the rule it breaks.

    Text only, for `brain.models.pricing.decimal_of`'s reason: a float has lost the digits a rate
    is quoted in.
    """
    try:
        found = Decimal(text.strip())
    except InvalidOperation:
        msg = "a rate is a number such as 0.74"
        raise ReconcileError(msg) from None
    exponent = found.as_tuple().exponent
    if not found.is_finite() or found <= 0:
        msg = "a rate is a number above nothing"
        raise ReconcileError(msg)
    if isinstance(exponent, int) and -exponent > MAX_RATE_PLACES:
        msg = f"a rate has at most {MAX_RATE_PLACES} decimal places"
        raise ReconcileError(msg)
    return found


def attribute(
    spent: Iterable[tuple[str, int, int]], models_by_provider: Mapping[str, Iterable[str]]
) -> Attributed:
    """Split `(model, requests, cost_minor)` lines by the provider each model is priced under.

    A model priced under more than one provider belongs to none, and so does one priced under
    none. See `WHAT_CANNOT_BE_ATTRIBUTED_IS_SAID_BESIDE_WHAT_CAN`.
    """
    owners: dict[str, set[str]] = {}
    for provider, models in models_by_provider.items():
        for model in models:
            owners.setdefault(model, set()).add(provider)
    totals: dict[str, tuple[int, int]] = dict.fromkeys(models_by_provider, (0, 0))
    loose = loose_requests = 0
    for model, requests, cost in spent:
        who = owners.get(model, set())
        if len(who) == 1:
            (only,) = who
            before_cost, before_requests = totals[only]
            totals[only] = (before_cost + cost, before_requests + requests)
        else:
            loose += cost
            loose_requests += requests
    return Attributed(
        by_provider=totals, unattributed_minor=loose, unattributed_requests=loose_requests
    )


def in_invoice_currency(metered_minor: int, rate: Decimal | None) -> int:
    """Metered minor units brought into the invoice's currency, rounded once, half to even."""
    if rate is None:
        return metered_minor
    return int((Decimal(metered_minor) * rate).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def compare(
    provider: str,
    *,
    metered_minor: int,
    install_currency: str,
    invoice_minor: int,
    invoice_currency: str,
    rate: Decimal | None,
) -> Comparison:
    """Hold one provider's metered spend against its invoice, in the invoice's currency.

    A different currency with no rate is refused, and a rate given for the same currency is
    refused too: a rate beside two figures in one currency is either a slip or a figure that
    would change nothing and read as though it had.
    """
    if not CURRENCY_PATTERN.match(invoice_currency):
        msg = "an invoice names its currency as three upper-case letters, such as USD"
        raise ReconcileError(msg)
    if invoice_minor < 0:
        msg = "an invoice is an amount of nothing or more"
        raise ReconcileError(msg)
    same = invoice_currency == install_currency
    if same and rate is not None:
        msg = "the invoice is in the install's currency, so there is no rate to apply"
        raise ReconcileError(msg)
    if not same and rate is None:
        raise ReconcileError(A_DIFFERENT_CURRENCY_NEEDS_THE_RATE_THE_INVOICE_USED)
    metered = in_invoice_currency(metered_minor, rate)
    difference = metered - invoice_minor
    if invoice_minor == 0:
        fraction: Decimal | None = None
        within = metered == 0
    else:
        fraction = Decimal(difference) / Decimal(invoice_minor)
        within = abs(fraction) <= RECONCILIATION_TOLERANCE
    return Comparison(
        provider=provider,
        currency=invoice_currency,
        invoice_minor=invoice_minor,
        metered_minor=metered,
        difference_minor=difference,
        difference_fraction=fraction,
        tolerance=RECONCILIATION_TOLERANCE,
        within_tolerance=within,
        rate=rate,
    )


def window_problem(since: datetime, until: datetime) -> str | None:
    """Why this billing period cannot be read, or None. Aware instants, the end after the start."""
    if since.tzinfo is None or until.tzinfo is None:
        return "a billing period starts and ends at an instant with a zone"
    if until <= since:
        return "a billing period ends after it starts"
    return None
