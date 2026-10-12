"""Install check for the company's budget beside what the company spent.

`brain.company_routes` served the company's consumption and said, in its own docstring, that nothing
wrote a company ceiling, so the leaf's first half (a budget) was never there to be read. The route
now writes it (`PUT /company/budget`) and the consumption read puts it beside the figure. The unit
tests run over a stub pool. What they cannot show is that, on an install, over the product's own
budget history and spend ledger, the Super Admin sets the ceiling and is then shown it beside the
spend, that a budget administrator over one department is refused in words that name the role, that
a reader the total is withheld from is shown no ceiling either, and that a reader with no budget
screen is answered as there is none.

**The figures are compared with what the install already holds.** An install has spent real money
and may have set a real ceiling. The check reads the consumption before it writes anything, adds a
run of its own to the spend ledger in its rolled-back transaction, and asserts that the total grew
by at least that run and that the ceiling it set is the ceiling shown; it never asserts the total or
that none was set before, which would be a statement about the company and not about the product.

**Nothing here stops anything.** A company ceiling is appended as the next version of the monthly
budget; whether a spent budget refuses questions is the install's own switch (needs-rupash item 169)
and the check neither reads nor changes it.

Task ids: M33.1.1.3
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_company_views import _once, _screens_over
from brain.ops.acceptance_checks_governance import _app, _asking, _refused, _request, _traced
from brain.ops.acceptance_checks_role_surfaces import _spend
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 893

A, B = RESERVED_DEPARTMENTS

#: The authority a budget is set with.
BUDGET_ADMIN: Final = "admin:budget"

#: What the check's own run cost, and the ceiling it sets. Far apart, so neither is mistaken for
#: the other, and the ceiling is a figure no real company ceiling is likely to be.
THE_RUN_COST: Final = 700
THE_CEILING: Final = 7_654_321

THE_BUDGET_WAS_NOT_SET: Final = "the Super Admin could not set the company's monthly budget"
THE_CEILING_WAS_NOT_SHOWN: Final = (
    "the company's budget was not shown beside its spend to a reader who may be shown the total"
)
THE_SPEND_WAS_NOT_SHOWN: Final = "the company's spend did not include a run the check recorded"
THE_VERSION_DID_NOT_MOVE: Final = "setting the company's budget did not add a version of it"
A_DEPARTMENT_ADMIN_SET_THE_COMPANYS: Final = (
    "a budget administrator over one department set the company's budget"
)
THE_REFUSAL_NAMED_NO_ROLE: Final = "the refusal to set the company's budget did not name the role"
A_CEILING_WAS_SHOWN_WITH_NO_FIGURE: Final = (
    "a reader whose company total is withheld was shown the company's ceiling"
)
A_READER_WITH_NO_SCREEN_WAS_ANSWERED: Final = "a reader with no budget screen was answered"


@check(
    leaves=("M33.1.1.3",),
    sentence=(
        "The Super Admin sets the company's monthly budget and is shown it beside what the company "
        "spent, including a run the check recorded, and a second version supersedes the first; a "
        "budget administrator over acceptance_a alone is refused in words naming the role, a "
        "reader whose total is withheld is shown no ceiling, and a reader with no budget screen is "
        "answered as there is none."
    ),
)
async def the_company_budget_is_set_and_read_beside_the_spend(
    h: Harness,
) -> None:
    from brain.company_routes import (
        COMPANY_BUDGET_KEY,
        CompanyBudgetAsked,
        company_consumption_view,
        set_company_budget,
    )
    from brain.ops.budget_store import history_of
    from brain.tables.spend import SpendActualRow

    _traced(h)
    await h.found_departments()
    everywhere = Scope.unrestricted()
    super_admin, department_admin, narrow, nobody = (
        h.principal(A, "super"),
        h.principal(A, "department_admin"),
        h.principal(A, "narrow"),
        h.principal(A, "nobody"),
    )
    await h.person(
        super_admin,
        department=A,
        grants=_once((*_screens_over(everywhere, "budget"), (BUDGET_ADMIN, everywhere))),
    )
    await h.person(
        department_admin,
        department=A,
        grants=_once(
            (*_screens_over(Scope.department(A), "budget"), (BUDGET_ADMIN, Scope.department(A)))
        ),
    )
    await h.person(narrow, department=A, grants=_screens_over(Scope.department(A), "budget"))
    await h.person(nobody, department=A)
    request = _request(_app(h))

    async def consumption(who: str) -> Any:
        return await company_consumption_view(request, await _asking(h, who))

    before = await consumption(super_admin)
    if before.withheld:
        raise CheckFailedError(THE_CEILING_WAS_NOT_SHOWN)
    versions_before = len(await _history(h, history_of, COMPANY_BUDGET_KEY))

    await h.execute(
        *h.attributed(super_admin),
        insert(SpendActualRow).values(**_spend(super_admin, THE_RUN_COST, h.now, h.trace_id)),
    )
    done = await set_company_budget(
        request,
        CompanyBudgetAsked(ceiling_minor=THE_CEILING, reason="Set by an install acceptance check"),
        await _asking(h, super_admin),
    )
    if getattr(done, "ceiling_minor", None) != THE_CEILING:
        raise CheckFailedError(THE_BUDGET_WAS_NOT_SET)
    if len(await _history(h, history_of, COMPANY_BUDGET_KEY)) != versions_before + 1:
        raise CheckFailedError(THE_VERSION_DID_NOT_MOVE)

    after = await consumption(super_admin)
    if after.withheld or not after.ceiling_set or after.ceiling_minor != THE_CEILING:
        raise CheckFailedError(THE_CEILING_WAS_NOT_SHOWN)
    if not after.may_set_budget:
        raise CheckFailedError(THE_BUDGET_WAS_NOT_SET)
    if (after.spend_minor or 0) < (before.spend_minor or 0) + THE_RUN_COST:
        raise CheckFailedError(THE_SPEND_WAS_NOT_SHOWN)

    refused = await set_company_budget(
        request,
        CompanyBudgetAsked(ceiling_minor=1, reason="Set by an install acceptance check"),
        await _asking(h, department_admin),
    )
    if getattr(refused, "status_code", 200) != 403:
        raise CheckFailedError(A_DEPARTMENT_ADMIN_SET_THE_COMPANYS)
    if "budget administrator" not in bytes(getattr(refused, "body", b"")).decode():
        raise CheckFailedError(THE_REFUSAL_NAMED_NO_ROLE)
    if (await consumption(narrow)).ceiling_minor is not None:
        raise CheckFailedError(A_CEILING_WAS_SHOWN_WITH_NO_FIGURE)
    if not await _refused(consumption(nobody)):
        raise CheckFailedError(A_READER_WITH_NO_SCREEN_WAS_ANSWERED)


async def _history(h: Harness, read: Any, key: Any) -> tuple[Any, ...]:
    """Every version of the company's monthly ceiling, oldest first, or none."""
    async with h.sessions() as session:
        found = await read(session, key)
    return () if found is None else tuple(found.rows)
