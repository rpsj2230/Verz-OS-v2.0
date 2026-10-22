"""Install checks for a department's budget and its people's allowances, set from the console.

`brain.ops.budgets` built `allocate`, `apply_transfers` and `user_allowances` and nothing on an
install called them, so no department ever had a budget and no person ever had an allowance. The
routes in `brain.department_budget_routes` are the writes. These ask them as the people who may use
them, over the install's own budget history, ledger and directory, in the check's rolled-back
transaction.

**The install's own budgets are never assumed away.** An install may already hold a company
ceiling and departments' budgets of its own. The check raises the company's ceiling to the largest
the route accepts, as the next version of it, so a share of a few millionths is a real figure; it
shares that between the two reserved departments only; and it asserts on the versions it adds and
on the departments it founded, never on a total or on the absence of anything else.

**What a refusal is held to.** An allocation that, beside the departments it does not name, would
hold more than the company's ceiling is refused and writes nothing. A transfer that would take a
department to nothing is refused. The administrator of one department is refused the company's
money in words that name the role, is shown only their own department's line, and is answered for
another department in the words a stranger is answered in.

**An allowance is derived once.** Everyone in the reserved department is given the pair, the
monthly figure is no more than a quarter of the department's, and asking again writes no new
version. A person in the other reserved department is given nothing.

Task ids: M21.1.2, M21.1.3, M21.1.1
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, screen_grants
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2155

A, B = RESERVED_DEPARTMENTS

#: Restated rather than imported, so a change to the routes' authority fails the check instead of
#: moving with it.
BUDGET_ADMIN: Final = "admin:budget"

#: The company's ceiling the check sets: the largest the route accepts, so that the few millionths
#: the departments are given are whole figures whatever the install's own departments hold.
THE_CEILING: Final = 100_000_000_000

#: The two departments' shares, and what they come to. Far smaller than any real department's.
SHARE_A: Final = 0.00001
SHARE_B: Final = 0.00002
BUDGET_A: Final = 1_000_000
BUDGET_B: Final = 2_000_000

#: The money moved from the first reserved department to the second.
THE_TRANSFER: Final = 500_000

#: The per-run ceiling the check sets, and the one above the month it is refused.
THE_RUN_CEILING: Final = 40_000

REASON: Final = "Set by an install acceptance check"

THE_COMPANY_BUDGET_WAS_NOT_SET: Final = "the company's monthly budget could not be set"
THE_SHARES_WERE_NOT_WRITTEN: Final = (
    "the two departments were not given the shares the budget administrator asked for"
)
A_SHARE_WAS_NOT_A_VERSION: Final = "a share was not kept as a version of the department's budget"
A_BUDGET_DID_NOT_WARN: Final = "a department's budget did not carry the seventy and ninety warnings"
THE_ALLOCATION_WAS_NOT_LEDGERED: Final = "a share of the company's budget was not a ledger entry"
AN_OVERFLOW_WAS_ACCEPTED: Final = (
    "shares that together hold more than the company's budget were accepted"
)
A_REFUSED_ALLOCATION_WROTE: Final = "a refused allocation wrote a version of a department's budget"
THE_TRANSFER_DID_NOT_MOVE_MONEY: Final = (
    "a transfer did not move money from one department to the other"
)
THE_TRANSFER_CHANGED_THE_TOTAL: Final = "a transfer changed what the two departments hold together"
A_DEPARTMENT_WAS_EMPTIED: Final = "a transfer took a department's whole budget"
A_HEAD_MOVED_COMPANY_MONEY: Final = (
    "the administrator of one department allocated or transferred the company's money"
)
THE_REFUSAL_NAMED_NO_ROLE: Final = "the refusal to move company money did not name the role"
A_HEAD_SAW_ANOTHER_LINE: Final = "a department's administrator was shown another department's line"
A_HEAD_SAW_NO_LINE: Final = "a department's administrator was not shown their own department's line"
ANOTHER_DEPARTMENT_WAS_ANSWERED_DIFFERENTLY: Final = (
    "an administrator of one department was told something other than a stranger is told about "
    "another department"
)
THE_RUN_CEILING_WAS_NOT_SET: Final = "a department's per-run ceiling could not be set"
A_RUN_CEILING_ABOVE_THE_MONTH_STOOD: Final = (
    "a per-run ceiling above the department's month was accepted"
)
NOBODY_WAS_GIVEN_AN_ALLOWANCE: Final = (
    "the people in the department were not each given a daily and a monthly allowance"
)
AN_ALLOWANCE_WAS_NOT_CAPPED: Final = (
    "a person's monthly allowance was more than a quarter of the department's"
)
ASKING_AGAIN_WROTE_VERSIONS: Final = "giving the same allowances again wrote new versions"
A_STRANGER_WAS_GIVEN_AN_ALLOWANCE: Final = "a person in the other department was given an allowance"


async def _history(h: Harness, level: str, subject: str, period: str) -> tuple[Any, ...]:
    """Every version of one ceiling, oldest first, or none."""
    from brain.ops.budget_store import history_of
    from brain.ops.budgets import BudgetLevel, BudgetPeriod

    async with h.sessions() as session:
        found = await history_of(session, (BudgetLevel(level), subject, BudgetPeriod(period)))
    return () if found is None else tuple(found.rows)


async def _entries(h: Harness, subject: str) -> int:
    # Bounded by the time column: only the entries since this check began, which are its own.
    found = await h.execute(
        text("SELECT count(*) FROM obs.audit_entry WHERE subject = :s AND at >= :since").bindparams(
            s=subject, since=h.now
        )
    )
    return int(found.scalar_one())


async def _people(h: Harness) -> tuple[str, str, str, str]:
    """The reserved people: the budget administrator over everything, the administrator over A,
    a member of A and a member of B. Returns their ids in that order."""
    await h.found_departments()
    root, head, member, elsewhere = (
        h.principal(A, "root"),
        h.principal(A, "head"),
        h.principal(A, "member"),
        h.principal(B, "member"),
    )
    everywhere = Scope.unrestricted()
    await h.person(
        root,
        department=A,
        grants=(*screen_grants("budget", everywhere), (BUDGET_ADMIN, everywhere)),
    )
    await h.person(head, department=A, grants=((BUDGET_ADMIN, Scope.department(A)),))
    await h.person(member, department=A)
    await h.person(elsewhere, department=B)
    return root, head, member, elsewhere


async def _funded(h: Harness, root: str) -> Any:
    """The company's ceiling raised and the two departments given their shares, by the route."""
    from brain.company_routes import CompanyBudgetAsked, set_company_budget
    from brain.department_budget_routes import (
        AllocationAsked,
        ShareAsked,
        allocate_department_budgets,
    )

    console = console_for(h)
    done = await set_company_budget(
        console.request("PUT"),
        CompanyBudgetAsked(ceiling_minor=THE_CEILING, reason=REASON),
        await asking_as(h, root, strong=True),
    )
    if getattr(done, "ceiling_minor", None) != THE_CEILING:
        raise CheckFailedError(THE_COMPANY_BUDGET_WAS_NOT_SET)
    return await allocate_department_budgets(
        console.request("PUT"),
        AllocationAsked(
            shares=[
                ShareAsked(department=A, share=SHARE_A),
                ShareAsked(department=B, share=SHARE_B),
            ],
            reason=REASON,
        ),
        await asking_as(h, root, strong=True),
    )


@check(
    leaves=("M21.1.2", "M21.1.1"),
    sentence=(
        "The administrator over everything shares the company's budget between two departments "
        "as versions that warn at seventy and ninety per cent; shares past the company's budget "
        "are refused; a transfer moves money and keeps the total, and one that empties a "
        "department is refused; a department's own administrator is refused company money."
    ),
)
async def department_shares_and_transfers_are_versions_and_nothing_else(h: Harness) -> None:
    from brain.department_budget_routes import (
        AllocationAsked,
        RunCeilingAsked,
        ShareAsked,
        TransferAsked,
        allocate_department_budgets,
        department_budgets,
        set_department_run_ceiling,
        transfer_between_departments,
    )

    root, head, _member, _elsewhere = await _people(h)
    console = console_for(h)
    a_before = len(await _history(h, "department", A, "month"))
    b_before = len(await _history(h, "department", B, "month"))
    a_entries = await _entries(h, f"department:{A}")

    funded = await _funded(h, root)
    if getattr(funded, "status_code", 200) != 200 and not hasattr(funded, "lines"):
        raise CheckFailedError(THE_SHARES_WERE_NOT_WRITTEN)
    a_rows = await _history(h, "department", A, "month")
    b_rows = await _history(h, "department", B, "month")
    if len(a_rows) != a_before + 1 or len(b_rows) != b_before + 1:
        raise CheckFailedError(A_SHARE_WAS_NOT_A_VERSION)
    if (a_rows[-1].ceiling_minor, b_rows[-1].ceiling_minor) != (BUDGET_A, BUDGET_B):
        raise CheckFailedError(THE_SHARES_WERE_NOT_WRITTEN)
    if tuple(a_rows[-1].alert_fractions) != (0.7, 0.9) or tuple(b_rows[-1].alert_fractions) != (
        0.7,
        0.9,
    ):
        raise CheckFailedError(A_BUDGET_DID_NOT_WARN)
    if await _entries(h, f"department:{A}") != a_entries + 1:
        raise CheckFailedError(THE_ALLOCATION_WAS_NOT_LEDGERED)

    over = await allocate_department_budgets(
        console.request("PUT"),
        AllocationAsked(shares=[ShareAsked(department=A, share=1.0)], reason=REASON),
        await asking_as(h, root, strong=True),
    )
    if getattr(over, "status_code", 200) != 422:
        raise CheckFailedError(AN_OVERFLOW_WAS_ACCEPTED)
    if len(await _history(h, "department", A, "month")) != len(a_rows):
        raise CheckFailedError(A_REFUSED_ALLOCATION_WROTE)

    moved = await transfer_between_departments(
        console.request("POST"),
        TransferAsked(from_department=A, to_department=B, amount_minor=THE_TRANSFER, reason=REASON),
        await asking_as(h, root, strong=True),
    )
    if getattr(moved, "status_code", 200) != 200 and not hasattr(moved, "lines"):
        raise CheckFailedError(THE_TRANSFER_DID_NOT_MOVE_MONEY)
    a_after = await _history(h, "department", A, "month")
    b_after = await _history(h, "department", B, "month")
    if (a_after[-1].ceiling_minor, b_after[-1].ceiling_minor) != (
        BUDGET_A - THE_TRANSFER,
        BUDGET_B + THE_TRANSFER,
    ):
        raise CheckFailedError(THE_TRANSFER_DID_NOT_MOVE_MONEY)
    if a_after[-1].ceiling_minor + b_after[-1].ceiling_minor != BUDGET_A + BUDGET_B:
        raise CheckFailedError(THE_TRANSFER_CHANGED_THE_TOTAL)
    emptied = await transfer_between_departments(
        console.request("POST"),
        TransferAsked(
            from_department=A, to_department=B, amount_minor=BUDGET_A - THE_TRANSFER, reason=REASON
        ),
        await asking_as(h, root, strong=True),
    )
    if getattr(emptied, "status_code", 200) != 422:
        raise CheckFailedError(A_DEPARTMENT_WAS_EMPTIED)

    for refusal in (
        await allocate_department_budgets(
            console.request("PUT"),
            AllocationAsked(shares=[ShareAsked(department=A, share=SHARE_A)], reason=REASON),
            await asking_as(h, head, strong=True),
        ),
        await transfer_between_departments(
            console.request("POST"),
            TransferAsked(from_department=A, to_department=B, amount_minor=1, reason=REASON),
            await asking_as(h, head, strong=True),
        ),
    ):
        if getattr(refusal, "status_code", 200) != 403:
            raise CheckFailedError(A_HEAD_MOVED_COMPANY_MONEY)
        if "budget administrator" not in bytes(getattr(refusal, "body", b"")).decode():
            raise CheckFailedError(THE_REFUSAL_NAMED_NO_ROLE)

    shown = await department_budgets(console.request(), await asking_as(h, head, strong=True))
    names = [one.department for one in shown.lines]
    if B in names:
        raise CheckFailedError(A_HEAD_SAW_ANOTHER_LINE)
    if A not in names:
        raise CheckFailedError(A_HEAD_SAW_NO_LINE)

    ceiling = await set_department_run_ceiling(
        console.request("PUT"),
        A,
        RunCeilingAsked(ceiling_minor=THE_RUN_CEILING, reason=REASON),
        await asking_as(h, head, strong=True),
    )
    if getattr(ceiling, "ceiling_minor", None) != THE_RUN_CEILING:
        raise CheckFailedError(THE_RUN_CEILING_WAS_NOT_SET)
    above = await set_department_run_ceiling(
        console.request("PUT"),
        A,
        RunCeilingAsked(ceiling_minor=BUDGET_A * 2, reason=REASON),
        await asking_as(h, head, strong=True),
    )
    if getattr(above, "status_code", 200) != 422:
        raise CheckFailedError(A_RUN_CEILING_ABOVE_THE_MONTH_STOOD)
    elsewhere_answer = await set_department_run_ceiling(
        console.request("PUT"),
        B,
        RunCeilingAsked(ceiling_minor=THE_RUN_CEILING, reason=REASON),
        await asking_as(h, head, strong=True),
    )
    nowhere_answer = await set_department_run_ceiling(
        console.request("PUT"),
        "acceptance_nowhere",
        RunCeilingAsked(ceiling_minor=THE_RUN_CEILING, reason=REASON),
        await asking_as(h, head, strong=True),
    )
    if getattr(elsewhere_answer, "status_code", 0) != 403 or bytes(
        getattr(elsewhere_answer, "body", b"")
    ) != bytes(getattr(nowhere_answer, "body", b"x")):
        raise CheckFailedError(ANOTHER_DEPARTMENT_WAS_ANSWERED_DIFFERENTLY)


@check(
    leaves=("M21.1.3",),
    sentence=(
        "The administrator over acceptance_a gives everyone in it a daily and a monthly allowance "
        "from its monthly budget, each the first version of that person's allowance, no person's "
        "monthly figure more than a quarter of the department's; asking again writes no new "
        "version; and a person in acceptance_b is given nothing."
    ),
)
async def a_departments_people_are_given_capped_allowances(
    h: Harness,
) -> None:
    from brain.department_budget_routes import AllowancesAsked, give_department_allowances

    root, head, member, elsewhere = await _people(h)
    console = console_for(h)
    await _funded(h, root)
    month = (await _history(h, "department", A, "month"))[-1]

    async def give() -> Any:
        return await give_department_allowances(
            console.request("POST"),
            A,
            AllowancesAsked(reason=REASON),
            await asking_as(h, head, strong=True),
        )

    first = await give()
    people = (root, head, member)
    for person in people:
        daily = await _history(h, "user", person, "day")
        monthly = await _history(h, "user", person, "month")
        if len(daily) != 1 or len(monthly) != 1:
            raise CheckFailedError(NOBODY_WAS_GIVEN_AN_ALLOWANCE)
        if monthly[0].ceiling_minor > month.ceiling_minor // 4:
            raise CheckFailedError(AN_ALLOWANCE_WAS_NOT_CAPPED)
    if getattr(first, "people", 0) < len(people):
        raise CheckFailedError(NOBODY_WAS_GIVEN_AN_ALLOWANCE)
    await give()
    for person in people:
        if (
            len(await _history(h, "user", person, "day")) != 1
            or len(await _history(h, "user", person, "month")) != 1
        ):
            raise CheckFailedError(ASKING_AGAIN_WROTE_VERSIONS)
    if await _history(h, "user", elsewhere, "day") or await _history(h, "user", elsewhere, "month"):
        raise CheckFailedError(A_STRANGER_WAS_GIVEN_AN_ALLOWANCE)
