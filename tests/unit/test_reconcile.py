"""Metered spend against an invoice: the attribution, the conversion and the verdict.

Task ids: M21.4.1
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from brain.ops.reconcile import (
    A_DIFFERENT_CURRENCY_NEEDS_THE_RATE_THE_INVOICE_USED,
    RECONCILIATION_TOLERANCE,
    ReconcileError,
    attribute,
    compare,
    in_invoice_currency,
    rate_of,
    window_problem,
)

AT = datetime(2999, 3, 1, tzinfo=UTC)


def test_the_tolerance_is_two_per_cent() -> None:
    """Stated as a literal and not against the constant. Delete this and the tolerance drifts to
    whatever the last edit made it, with every reconciliation still reading as a verdict."""
    assert Decimal("0.02") == RECONCILIATION_TOLERANCE


def test_a_model_priced_under_one_provider_is_that_providers_and_nothing_else_is() -> None:
    """Spend is split by the provider each model is priced under; a model priced under two, one
    priced under none and a request answered by two models are each not attributed, and the lines
    and the not-attributed amount add up to every row. Delete this and an invoice is held against
    spend a rule split between providers, or spend quietly dropped."""
    spent = [
        ("opus", 3, 300),
        ("gpt", 2, 200),
        ("shared", 5, 500),
        ("nobody", 1, 10),
        ("(more than one model)", 4, 40),
    ]
    split = attribute(spent, {"anthropic": ["opus", "shared"], "openai": ["gpt", "shared"]})
    assert split.by_provider == {"anthropic": (300, 3), "openai": (200, 2)}
    assert (split.unattributed_minor, split.unattributed_requests) == (550, 10)
    total = sum(cost for cost, _ in split.by_provider.values()) + split.unattributed_minor
    assert total == sum(cost for _, _, cost in spent)


def test_a_provider_with_no_spend_still_has_a_line() -> None:
    """A priced provider nothing used is a line of nothing, so an invoice for it can be held
    against nothing. Delete this and a provider that spent nothing cannot be reconciled."""
    split = attribute([], {"anthropic": ["opus"]})
    assert split.by_provider == {"anthropic": (0, 0)}


def test_the_rate_is_text_above_nothing_with_at_most_six_places() -> None:
    """Delete this and a rate of nought, a negative one, a float's long tail or a word is used to
    convert money."""
    assert rate_of(" 0.74 ") == Decimal("0.74")
    for bad in ("", "abc", "0", "-1", "NaN", "1.1234567", "inf"):
        with pytest.raises(ReconcileError):
            rate_of(bad)


def test_metered_spend_is_converted_once_and_rounded_half_to_even() -> None:
    """Delete this and each conversion rounds up, which drifts every month by half a unit."""
    assert in_invoice_currency(5, Decimal("0.5")) == 2
    assert in_invoice_currency(7, Decimal("0.5")) == 4
    assert in_invoice_currency(4000, None) == 4000


def compared(metered: int, invoice: int, **over: object) -> object:
    arguments: dict[str, object] = {
        "metered_minor": metered,
        "install_currency": "SGD",
        "invoice_minor": invoice,
        "invoice_currency": "USD",
        "rate": Decimal("0.5"),
    }
    arguments.update(over)
    return compare("anthropic", **arguments)  # type: ignore[arg-type]


def test_an_invoice_inside_two_per_cent_reconciles_and_outside_it_shows_its_difference() -> None:
    """Metered 4000 SGD at 0.5 is 2000 USD: an invoice of 2000 matches, 2039 is 1.9 per cent away
    and reconciles, 2100 is 4.8 per cent away and does not, and the difference is shown in both.
    Delete this and a verdict is a boolean nobody can check."""
    exact = compared(4000, 2000)
    assert (exact.difference_minor, exact.within_tolerance) == (0, True)  # type: ignore[attr-defined]
    near = compared(4000, 2039)
    assert (near.difference_minor, near.within_tolerance) == (-39, True)  # type: ignore[attr-defined]
    far = compared(4000, 2100)
    assert (far.difference_minor, far.within_tolerance) == (-100, False)  # type: ignore[attr-defined]
    assert far.currency == "USD" and far.metered_minor == 2000  # type: ignore[attr-defined]


def test_the_edge_of_the_tolerance_reconciles() -> None:
    """Exactly two per cent is inside. Delete this and the boundary flips with a comparison."""
    at_edge = compared(5100, 2500)  # 2550 against 2500 is exactly two per cent
    assert at_edge.within_tolerance and at_edge.difference_fraction == Decimal("0.02")  # type: ignore[attr-defined]
    over = compared(5102, 2500)
    assert not over.within_tolerance  # type: ignore[attr-defined]


def test_an_invoice_of_nothing_reconciles_only_with_nothing_metered() -> None:
    """A percentage of nothing is no verdict, so an empty invoice is held to an empty meter. Delete
    this and an invoice of nothing divides by it."""
    assert compared(0, 0).within_tolerance  # type: ignore[attr-defined]
    owed = compared(100, 0)
    assert not owed.within_tolerance and owed.difference_fraction is None  # type: ignore[attr-defined]


def test_another_currency_needs_its_rate_and_the_same_currency_refuses_one() -> None:
    """Delete this and a USD invoice is compared with SGD figures as though they were one unit, or
    a rate typed beside two figures in one currency reads as though it did something."""
    with pytest.raises(ReconcileError, match="rate"):
        compared(4000, 2000, rate=None)
    assert A_DIFFERENT_CURRENCY_NEEDS_THE_RATE_THE_INVOICE_USED
    with pytest.raises(ReconcileError, match="no rate"):
        compared(4000, 4000, invoice_currency="SGD")
    same = compared(4000, 4000, invoice_currency="SGD", rate=None)
    assert same.within_tolerance and same.rate is None  # type: ignore[attr-defined]


def test_an_invoice_names_a_currency_and_an_amount_of_nothing_or_more() -> None:
    """Delete this and 'usd' or a negative amount is compared."""
    with pytest.raises(ReconcileError):
        compared(1, 1, invoice_currency="usd")
    with pytest.raises(ReconcileError):
        compared(1, -1)


def test_a_billing_period_is_aware_and_ends_after_it_starts() -> None:
    """Delete this and a window that ends first, or one with no zone, is read."""
    assert window_problem(AT, AT + timedelta(days=30)) is None
    assert window_problem(AT, AT) is not None
    assert window_problem(AT.replace(tzinfo=None), AT + timedelta(days=1)) is not None
