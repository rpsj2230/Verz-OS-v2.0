"""Install check for metered spend held against a provider's invoice.

`brain.models.pricing` prices a call so that many requests sum to the provider's invoice, and until
`GET /report/spend/providers` nothing held the sum against one. This asks the route as the people it
is for, over spend the check records in its rolled-back transaction.

**A provider of the check's own and a model of the check's own.** An install has real spend, and
the figures a provider's line shows are the sum of every model priced under it. So the check
prices one model under a provider name that exists nowhere else and records spend only against
that model, which makes the provider's line exactly the check's, whatever the company has spent.
It asserts on that line, and on the not-attributed amount only as at least what it put there,
never on a total.

**What is held.** The line counts the rows inside the window and not the one a month earlier; a
model priced under a second provider belongs to neither and its spend moves to the not-attributed
line; an invoice that the metered spend matches inside two per cent reconciles and one it does not
is shown with its difference and says so; a different currency without a rate and a rate beside the
same currency are each refused with nothing computed; and a reader whose usage grant covers one
department is told the provider totals are withheld and shown none.

Task ids: M21.4.1
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import insert

from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_operations_console import asking_as, console_for
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2145

A, _B = RESERVED_DEPARTMENTS

#: Restated rather than imported, so a change to the route's authority fails the check.
READS_USAGE: Final = "read:usage"

#: What the check's three recorded requests cost, in the install's minor units, and their sum.
COSTS: Final = (1_000, 2_500, 500)
METERED: Final = 4_000

#: The invoice in another currency: the rate that turns the install's units into the invoice's, and
#: the invoice that the metered spend then matches exactly, and one it misses by four per cent.
RATE: Final = "0.5"
MATCHING_INVOICE: Final = 2_000
MISSING_INVOICE: Final = 2_100

NO_CURRENCY_SET: Final = (
    "this install has not set its currency, so metered spend is not compared with an invoice here"
)
THE_LINE_WAS_NOT_THE_CHECKS: Final = (
    "the provider's line did not hold exactly the three requests the check recorded inside the "
    "window, or it counted one recorded a month before it or after it"
)
A_SHARED_MODEL_WAS_ATTRIBUTED: Final = (
    "a model priced under two providers was attributed to one of them"
)
THE_SHARED_SPEND_WAS_NOT_SAID: Final = (
    "the spend of a model priced under two providers was not shown as not attributed"
)
A_MATCHING_INVOICE_DID_NOT_RECONCILE: Final = (
    "an invoice the metered spend matches exactly did not reconcile"
)
A_MISSING_INVOICE_RECONCILED: Final = "an invoice four per cent away reconciled"
THE_DIFFERENCE_WAS_NOT_SHOWN: Final = "the difference from the invoice was not shown"
AN_INVOICE_FOR_NO_PROVIDER_WAS_COMPARED: Final = (
    "an invoice was held against a provider that has no price set under it"
)
A_CURRENCY_WITH_NO_RATE_WAS_COMPARED: Final = (
    "an invoice in another currency was compared with no rate"
)
A_RATE_BESIDE_THE_SAME_CURRENCY_WAS_ACCEPTED: Final = (
    "a rate was accepted beside an invoice in the install's own currency"
)
A_DEPARTMENT_READER_WAS_SHOWN_PROVIDERS: Final = (
    "a reader of one department's spend was shown a provider's total"
)


@check(
    leaves=("M21.4.1",),
    sentence=(
        "Metered spend for a billing period is shown per provider, counting only requests inside "
        "it and leaving a model priced under two providers as not attributed; an invoice is held "
        "against it in its own currency, reconciles inside two per cent and shows its difference "
        "outside it; a missing or needless rate is refused; a department reader sees no total."
    ),
)
async def metered_spend_is_held_against_a_providers_invoice(
    h: Harness,
) -> None:
    from brain.models.pricing import Price
    from brain.ops.price_store import set_price_statement
    from brain.report_routes import money_and_clock
    from brain.spend_detail_routes import spend_by_provider
    from brain.tables.audit import attributed_to
    from brain.tables.spend import SpendActualRow

    code, _zone = money_and_clock()
    if code == "XXX":
        raise CheckNotRunError(NO_CURRENCY_SET)
    await h.found_departments()
    asker = h.principal(A, "asker")
    company, department = h.principal(A, "company"), h.principal(A, "department")
    await h.person(asker, department=A)
    await h.person(company, department=A, grants=((READS_USAGE, Scope.unrestricted()),))
    await h.person(department, department=A, grants=((READS_USAGE, Scope.department(A)),))
    console = console_for(h)
    provider = f"acc_{h.run.replace('-', '')[:12].lower()}"
    other = f"{provider}_b"
    model = f"acc-invoice-model-{h.run}"
    now = datetime.now(UTC)
    price = Price(input_minor=Decimal(1), output_minor=Decimal(1), currency="USD")

    async def priced(under: str) -> None:
        await h.execute(
            *attributed_to(
                actor_id=company, ent_hash=(await h.reach(company)).ent_hash(), trace_id=h.trace_id
            ),
            set_price_statement(under, model, price, by=company),
        )

    async def recorded(cost: int, at: datetime, trace: str) -> None:
        async with h.sessions() as session:
            await session.execute(
                insert(SpendActualRow).values(
                    principal_id=asker,
                    principal_kind=PrincipalKind.HUMAN.value,
                    traffic=TrafficClass.HUMAN_INTERACTIVE.value,
                    department=A,
                    agent_id=None,
                    model=model,
                    lane=Lane.ANSWER.value,
                    cost_minor=cost,
                    at=at,
                    trace_id=trace,
                )
            )
            await session.commit()

    await priced(provider)
    for number, cost in enumerate(COSTS):
        await recorded(cost, now - timedelta(minutes=5), f"{h.trace_id}-i{number}")
    await recorded(99_999, now - timedelta(days=40), f"{h.trace_id}-old")
    await recorded(77_777, now + timedelta(days=3), f"{h.trace_id}-later")
    since, until = (now - timedelta(days=2)).date(), (now + timedelta(days=1)).date()

    async def read(who: str, **asked: Any) -> Any:
        return await spend_by_provider(
            console.request(), await asking_as(h, who), since=since, until=until, **asked
        )

    def line(answer: Any, name: str) -> Any:
        return next((one for one in answer.providers if one.provider == name), None)

    shown = await read(company)
    ours = line(shown, provider)
    if ours is None or ours.metered_minor != METERED or ours.requests != len(COSTS):
        raise CheckFailedError(THE_LINE_WAS_NOT_THE_CHECKS)

    invoice_currency = "USD" if code != "USD" else "EUR"
    held = await read(
        company,
        provider=provider,
        invoice_minor=MATCHING_INVOICE,
        invoice_currency=invoice_currency,
        rate=RATE,
    )
    matched = line(held, provider).reconciliation
    if matched is None or not matched.within_tolerance or matched.difference_minor != 0:
        raise CheckFailedError(A_MATCHING_INVOICE_DID_NOT_RECONCILE)
    missed = line(
        await read(
            company,
            provider=provider,
            invoice_minor=MISSING_INVOICE,
            invoice_currency=invoice_currency,
            rate=RATE,
        ),
        provider,
    ).reconciliation
    if missed is None or missed.within_tolerance:
        raise CheckFailedError(A_MISSING_INVOICE_RECONCILED)
    if missed.difference_minor != MATCHING_INVOICE - MISSING_INVOICE:
        raise CheckFailedError(THE_DIFFERENCE_WAS_NOT_SHOWN)

    nobody = await read(
        company, provider=f"{provider}_none", invoice_minor=1, invoice_currency=invoice_currency
    )
    if getattr(nobody, "status_code", 200) != 422:
        raise CheckFailedError(AN_INVOICE_FOR_NO_PROVIDER_WAS_COMPARED)
    no_rate = await read(
        company,
        provider=provider,
        invoice_minor=MATCHING_INVOICE,
        invoice_currency=invoice_currency,
    )
    if getattr(no_rate, "status_code", 200) != 422:
        raise CheckFailedError(A_CURRENCY_WITH_NO_RATE_WAS_COMPARED)
    needless = await read(
        company,
        provider=provider,
        invoice_minor=METERED,
        invoice_currency=code,
        rate=RATE,
    )
    if getattr(needless, "status_code", 200) != 422:
        raise CheckFailedError(A_RATE_BESIDE_THE_SAME_CURRENCY_WAS_ACCEPTED)

    before = shown.not_attributed_minor
    await priced(other)
    split = await read(company)
    if line(split, provider).metered_minor != 0 or line(split, other).metered_minor != 0:
        raise CheckFailedError(A_SHARED_MODEL_WAS_ATTRIBUTED)
    if split.not_attributed_minor < before + METERED:
        raise CheckFailedError(THE_SHARED_SPEND_WAS_NOT_SAID)

    scoped = await read(department)
    if not scoped.withheld or scoped.providers:
        raise CheckFailedError(A_DEPARTMENT_READER_WAS_SHOWN_PROVIDERS)
