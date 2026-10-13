"""Install check for an agent's per-run and per-day ceilings, set from its page.

`brain.ops.budgets.agent_ceilings` built a per-run and a per-day row and no route called it, so an
agent's month had a ceiling and its day and its run never did. `PUT /agents/{id}/budget/ceilings`
takes both figures together, as the next version of each, by the budget administrator over the
agent's department. This asks it as that person, through the route function over the install's own
database in the check's rolled-back transaction.

**Both are written, or neither is.** A run above the day's is refused as a pair because it could
never bind, so the check asks for one and sees nothing written; and a second write is the next
version of each and not a second row at version one, which the budget history would refuse to
order. A person who may see the agent and holds no budget authority over its department is refused
in words that name the role, and a budget administrator of another department is refused the same.
The version counts and the ledger entries are read from the install's own history and ledger and
compared with themselves before and after, never with an expected total.

Task ids: M21.1.4
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for
from brain.ops.acceptance_operations_console import refused as refusal_of
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2150

A, B = RESERVED_DEPARTMENTS

#: Restated rather than imported, so a change to the route's authority fails its check instead of
#: moving with it.
BUDGET_ADMIN: Final = "admin:budget"

#: The figures the check sets, far from any real ceiling, and the second pair that supersedes them.
FIRST: Final = (4_111, 40_111)
SECOND: Final = (5_222, 50_222)

REASON: Final = "Set by an install acceptance check"


@check(
    leaves=("M21.1.4",),
    sentence=(
        "The budget administrator over acceptance_a sets an agent's per-run and per-day ceilings "
        "together and again, each the next version of its own history with a ledger entry; a run "
        "above the day's is refused and writes neither; a member who may see the agent is refused "
        "in words naming the role, and an administrator of acceptance_b is answered as for an "
        "agent that does not exist."
    ),
)
async def an_agents_run_and_day_ceilings_are_set_together_as_versions(h: Harness) -> None:
    from brain.agent_workspace_routes import CeilingsAsked, set_agent_ceilings
    from brain.ops.acceptance_agent_console import _readers
    from brain.ops.acceptance_workspace import installed_agent
    from brain.ops.budget_store import history_of
    from brain.ops.budgets import BudgetLevel, BudgetPeriod

    await h.found_departments()
    owner, admin, member, elsewhere = (
        h.principal(A, "owner"),
        h.principal(A, "ceilings"),
        h.principal(A, "member"),
        h.principal(B, "ceilings"),
    )
    await h.person(owner, department=A)
    await h.person(admin, department=A, grants=(*_readers(), (BUDGET_ADMIN, Scope.department(A))))
    await h.person(member, department=A, grants=_readers())
    await h.person(
        elsewhere, department=B, grants=(*_readers(), (BUDGET_ADMIN, Scope.department(B)))
    )
    agent_id = await installed_agent(h, owner)
    console = console_for(h)

    async def history(period: BudgetPeriod) -> tuple[object, ...]:
        async with h.sessions() as session:
            found = await history_of(session, (BudgetLevel.AGENT, agent_id, period))
        return () if found is None else tuple(found.rows)

    async def attempt(who: str, run: int, day: int) -> object:
        return await set_agent_ceilings(
            console.request("PUT"),
            agent_id,
            CeilingsAsked(per_run_minor=run, per_day_minor=day, reason=REASON),
            await asking_as(h, who, strong=True),
        )

    async def ledger_entries() -> int:
        found = await h.execute(
            text("SELECT count(*) FROM obs.audit_entry WHERE subject = :s").bindparams(
                s=f"agent:{agent_id}"
            )
        )
        return int(found.scalar_one())

    runs_before = len(await history(BudgetPeriod.RUN))
    days_before = len(await history(BudgetPeriod.DAY))
    entries_before = await ledger_entries()
    first = await attempt(admin, *FIRST)
    if (getattr(first, "per_run_minor", None), getattr(first, "per_day_minor", None)) != FIRST:
        raise CheckFailedError(
            "the budget administrator could not set an agent's run and day ceilings"
        )
    second = await attempt(admin, *SECOND)
    if (getattr(second, "per_run_minor", None), getattr(second, "per_day_minor", None)) != SECOND:
        raise CheckFailedError("a second pair of ceilings did not replace the first")
    runs, days = await history(BudgetPeriod.RUN), await history(BudgetPeriod.DAY)
    if len(runs) != runs_before + 2 or len(days) != days_before + 2:
        raise CheckFailedError("each setting was not kept as a version of each ceiling")
    for rows, pair in ((runs, 0), (days, 1)):
        written = [getattr(one, "ceiling_minor", None) for one in rows[-2:]]
        if written != [FIRST[pair], SECOND[pair]]:
            raise CheckFailedError("the versions did not read back as set, oldest first")
        if getattr(rows[-1], "version", 0) != getattr(rows[-2], "version", 0) + 1:
            raise CheckFailedError("the second ceiling did not supersede the first")

    if await ledger_entries() != entries_before + 4:
        raise CheckFailedError("each ceiling version was not one ledger entry")
    above = await attempt(admin, 9_000, 8_000)
    if getattr(above, "status_code", 200) != 422:
        raise CheckFailedError("a run ceiling above the day's was accepted")
    if len(await history(BudgetPeriod.RUN)) != len(runs) or len(
        await history(BudgetPeriod.DAY)
    ) != len(days):
        raise CheckFailedError("a refused pair of ceilings wrote one of them")
    refused = await attempt(member, 1, 2)
    if getattr(refused, "status_code", 200) != 403:
        raise CheckFailedError("a member without the budget role set an agent's ceilings")
    if "budget administrator" not in bytes(getattr(refused, "body", b"")).decode():
        raise CheckFailedError("the refusal did not name the role that could set them")
    if not await refusal_of(attempt(elsewhere, 1, 2)):
        raise CheckFailedError("an administrator of another department could see and set them")
