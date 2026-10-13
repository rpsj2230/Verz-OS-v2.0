"""Install checks for the cost ledger and the Spend report built over it, and for budget versions.

Five M21 leaves were built and wired on main and no check on an install named them: a finished
run's cost recorded against five dimensions, the Spend report served in each of them, machine
traffic left out and labelled, and a budget kept as versioned rows the ledger records.

**The figures are compared with what the install already holds, never with nothing.** An install
has spent real money. Each check reads the report, writes its own rows in its rolled-back
transaction, rebuilds the daily view inside that transaction and reads the report again, then
asserts the difference by key. A key the check made (its own principal, agent and model) must
show exactly the run it recorded, and a key the install shares (its department, a lane) must have
grown by at least that run. It never asserts a total, which would be a statement about the company
and not about the product. See `A_SPEND_CHECK_COMPARES_THE_REPORT_WITH_ITSELF_BEFORE_AND_AFTER`.

**The rows are an `Actual`'s fields, inserted as the other install checks insert a cost.** The
usage recorder is the ledger's one writer (a test over the source holds that), so the check does
not call the store's own writer; it reads back through `spend_store.recorded` that the five
dimensions arrive as written. What is not proved here is that a real question's finish reaches
the recorder, which the install's own questions prove by appearing on this report.

**The budget history is the one store every level appends to.** The company ceiling is set
twice through the route a Super Admin uses, and a department and a person's row are appended
through `brain.ops.budget_store.append`, which the route and every other writer call. Each
append reads back as a version and each is one ledger entry in its own subject's name, and the
ceiling's figure is on the row and never in the ledger.

Task ids: M21.1.5, M21.2.3, M21.3.1, M21.3.2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2110

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the report is compared with itself before and after.
A_SPEND_CHECK_COMPARES_THE_REPORT_WITH_ITSELF_BEFORE_AND_AFTER: Final = (
    "An install has real spend, so the check reads each breakdown, records two runs through the "
    "ledger's own store, rebuilds the daily view in its transaction and reads each breakdown "
    "again, and asserts what changed by key, never a total."
)

# ------------------------------------------------------------------------ the figures
#: The authority a reader of spend holds. Restated rather than imported, so a change to a route's
#: authority fails its check instead of moving with it.
READS_USAGE: Final = "read:usage"

#: What the person's run and the machine's run cost, in minor units. Far apart and each not a sum
#: of the other, so neither is mistaken for the other or for both.
THE_PERSONS_RUN: Final = 300
THE_MACHINES_RUN: Final = 7_000

#: The ceilings the budget check writes, each a figure no real ceiling is likely to be.
COMPANY_CEILINGS: Final = (8_111_111, 8_222_222)
DEPARTMENT_CEILING: Final = 8_333_333
PERSON_CEILING: Final = 8_444_444

REASON: Final = "Set by an install acceptance check"

# ----------------------------------------------------------------------- the sentences
THE_VIEW_WAS_NOT_REBUILT: Final = "the daily spend view was not rebuilt from the ledger"


async def _report(h: Harness, who: str, dimension: Any, *, machine: bool = False) -> Any:
    from brain.report_routes import spend

    console = console_for(h)
    return await spend(
        console.request(),
        await asking_as(h, who),
        dimension=dimension,
        since=None,
        until=None,
        include_machine=machine,
    )


def _by_key(view: Any) -> dict[str, int]:
    return {one.key: one.cost_minor for one in view.lines}


async def _rebuilt(h: Harness) -> None:
    from brain.ops.spend_store import refresh_spend_daily

    async with h.sessions() as session:
        await refresh_spend_daily(session)
        await session.commit()


# ---------------------------------------------- 1. recorded and reported (M21.2.3, M21.3.1)
@check(
    leaves=("M21.2.3", "M21.3.1", "M21.3.2"),
    sentence=(
        "A person's run and a machine's run recorded through the cost ledger's own store are "
        "each shown by the Spend report against the person, the department, the agent, the "
        "model and the lane they were made under once the daily view is rebuilt; the machine's "
        "run is left out and the report says it was unless it is asked for; and a reader of "
        "spend in acceptance_b is shown no line for acceptance_a."
    ),
)
async def a_run_is_recorded_and_the_report_shows_it_in_every_dimension(h: Harness) -> None:
    from brain.core.lane import Lane
    from brain.core.principal import PrincipalKind
    from brain.gate.context import TrafficClass
    from brain.ops.spend import Actual, Dimension
    from brain.ops.spend_store import recorded
    from brain.tables.spend import SpendActualRow

    await h.found_departments()
    asker, sync = h.principal(A, "asker"), h.principal(A, "sync")
    reader, outsider = h.principal(A, "spend"), h.principal(B, "spend")
    await h.person(asker, department=A)
    await h.person(reader, department=A, grants=((READS_USAGE, Scope.unrestricted()),))
    await h.person(outsider, department=B, grants=((READS_USAGE, Scope.department(B)),))
    agent_person, agent_machine = f"acc-agent-{h.run}-p", f"acc-agent-{h.run}-m"
    model_person, model_machine = f"acc-model-{h.run}-p", f"acc-model-{h.run}-m"

    await _rebuilt(h)
    before = {one: _by_key(await _report(h, reader, one, machine=True)) for one in Dimension}
    before_default = _by_key(await _report(h, reader, Dimension.DEPARTMENT))

    at = datetime.now(UTC) - timedelta(minutes=5)
    runs = (
        Actual(
            principal_id=asker,
            principal_kind=PrincipalKind.HUMAN,
            traffic=TrafficClass.HUMAN_INTERACTIVE,
            department=A,
            agent_id=agent_person,
            model=model_person,
            lane=Lane.ANSWER,
            cost_minor=THE_PERSONS_RUN,
            at=at,
            trace_id=f"{h.trace_id}-p",
        ),
        Actual(
            principal_id=sync,
            principal_kind=PrincipalKind.SERVICE,
            traffic=TrafficClass.AUTOMATION,
            department=A,
            agent_id=agent_machine,
            model=model_machine,
            lane=Lane.ANSWER,
            cost_minor=THE_MACHINES_RUN,
            at=at,
            trace_id=f"{h.trace_id}-m",
        ),
    )
    # Inserted as the other install checks insert a cost: the usage recorder is the one writer of
    # the ledger the product has, and a second module calling the store's own writer is a second
    # writer a test over the source refuses (`tests/unit/test_agent_profile.py`).
    async with h.sessions() as session:
        await session.execute(
            insert(SpendActualRow),
            [
                {
                    "principal_id": one.principal_id,
                    "principal_kind": one.principal_kind.value,
                    "traffic": one.traffic.value,
                    "department": one.department,
                    "agent_id": one.agent_id,
                    "model": one.model,
                    "lane": one.lane.value,
                    "cost_minor": one.cost_minor,
                    "at": one.at,
                    "trace_id": one.trace_id,
                }
                for one in runs
            ],
        )
        await session.commit()
    async with h.sessions() as session:
        kept = {one.trace_id: one for one in await recorded(session)}
    if kept.get(f"{h.trace_id}-p") != runs[0] or kept.get(f"{h.trace_id}-m") != runs[1]:
        raise CheckFailedError("a recorded run did not read back with its five dimensions")

    await _rebuilt(h)
    for dimension, person_key, machine_key in (
        (Dimension.PRINCIPAL, asker, sync),
        (Dimension.AGENT, agent_person, agent_machine),
        (Dimension.MODEL, model_person, model_machine),
    ):
        shown = _by_key(await _report(h, reader, dimension))
        if shown.get(person_key) != THE_PERSONS_RUN:
            raise CheckFailedError("the report did not show the person's run in every dimension")
        if machine_key in shown:
            raise CheckFailedError("the report counted the machine's run in a dimension unasked")
        everything = _by_key(await _report(h, reader, dimension, machine=True))
        if everything.get(machine_key) != THE_MACHINES_RUN:
            raise CheckFailedError(
                "the report left out the machine's run in a dimension when asked for it"
            )
    for dimension, key in ((Dimension.DEPARTMENT, A), (Dimension.LANE, Lane.ANSWER.value)):
        grew = _by_key(await _report(h, reader, dimension, machine=True))
        if grew.get(key, 0) < before[dimension].get(key, 0) + THE_PERSONS_RUN + THE_MACHINES_RUN:
            raise CheckFailedError("the report did not grow by both runs in a shared dimension")
    default = _by_key(await _report(h, reader, Dimension.DEPARTMENT))
    if default.get(A, 0) != before_default.get(A, 0) + THE_PERSONS_RUN:
        raise CheckFailedError("the report counted the machine's run unless it was asked for")
    if (await _report(h, reader, Dimension.DEPARTMENT)).machine_included:
        raise CheckFailedError("the report did not say it left machine traffic out")
    if not (await _report(h, reader, Dimension.DEPARTMENT, machine=True)).machine_included:
        raise CheckFailedError("the report did not say it included machine traffic")
    if A in _by_key(await _report(h, outsider, Dimension.DEPARTMENT, machine=True)):
        raise CheckFailedError("the report showed a department's spend to a reader of another")


# ------------------------------------------------------------ 2. versions and the ledger (M21.1.5)
@check(
    leaves=("M21.1.5",),
    sentence=(
        "The Super Admin sets the company's monthly budget twice through the route and both "
        "versions read back in order with the second superseding the first; a department's and a "
        "person's ceiling appended through the budget store are each version one of their own "
        "key; and every version is one ledger entry in its key's subject and its author's name, "
        "holding the level and the period and never the figure."
    ),
)
async def every_budget_version_is_a_row_and_a_ledger_entry(h: Harness) -> None:
    from brain.company_routes import COMPANY_BUDGET_KEY, CompanyBudgetAsked, set_company_budget
    from brain.ops.acceptance_checks_company_views import _once, _screens_over
    from brain.ops.acceptance_checks_governance import _app, _request, _traced
    from brain.ops.budget_store import append, history_of
    from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow

    _traced(h)
    await h.found_departments()
    super_admin, member = h.principal(A, "super"), h.principal(A, "budgeted")
    await h.person(
        super_admin,
        department=A,
        grants=_once(
            (
                *_screens_over(Scope.unrestricted(), "budget"),
                ("admin:budget", Scope.unrestricted()),
            )
        ),
    )
    await h.person(member, department=A)
    request = _request(_app(h))

    async def entries(subject: str) -> list[tuple[str, Any]]:
        found = await h.execute(
            text(
                "SELECT actor_id, details FROM obs.audit_entry WHERE subject = :s ORDER BY seq"
            ).bindparams(s=subject)
        )
        return [(str(who), details) for who, details in found.all()]

    async def versions(key: Any) -> tuple[Any, ...]:
        async with h.sessions() as session:
            found = await history_of(session, key)
        return () if found is None else tuple(found.rows)

    company_before = len(await versions(COMPANY_BUDGET_KEY))
    ledger_before = len(await entries("setting:budget.company"))
    for ceiling in COMPANY_CEILINGS:
        async with traced(h, ceiling):
            done = await set_company_budget(
                request,
                CompanyBudgetAsked(ceiling_minor=ceiling, reason=REASON),
                await asking_as(h, super_admin, strong=True),
            )
        if getattr(done, "ceiling_minor", None) != ceiling:
            raise CheckFailedError("the Super Admin could not set the company's monthly budget")
    held = await versions(COMPANY_BUDGET_KEY)
    if len(held) != company_before + 2:
        raise CheckFailedError("two company budgets were not kept as two versions")
    first, second = held[-2], held[-1]
    if (first.ceiling_minor, second.ceiling_minor) != COMPANY_CEILINGS:
        raise CheckFailedError("the company's budget versions did not read back as written")
    if second.version != first.version + 1 or second.author != super_admin:
        raise CheckFailedError(
            "the second company budget did not supersede the first by its author"
        )
    shown = await entries("setting:budget.company")
    if len(shown) != ledger_before + 2 or {who for who, _ in shown[-2:]} != {super_admin}:
        raise CheckFailedError(
            "each company budget version was not one ledger entry in its author's name"
        )

    reach = await h.reach(super_admin)
    others = (
        (BudgetLevel.DEPARTMENT, A, f"department:{A}", DEPARTMENT_CEILING),
        (BudgetLevel.USER, member, f"principal:{member}", PERSON_CEILING),
    )
    for level, subject, ledger_subject, ceiling in others:
        row = BudgetRow(
            level=level,
            subject=subject,
            period=BudgetPeriod.MONTH,
            ceiling_minor=ceiling,
            version=1,
            author=super_admin,
            effective_from=datetime.now(UTC),
            reason=REASON,
        )
        already = len(await entries(ledger_subject))
        async with h.sessions() as session:
            await append(session, row, ent_hash=reach.ent_hash(), trace_id=h.trace_id)
            await session.commit()
        read = await versions(row.key)
        if [one.ceiling_minor for one in read][-1:] != [ceiling]:
            raise CheckFailedError("a department or person budget did not read back as a version")
        logged = await entries(ledger_subject)
        if len(logged) != already + 1 or logged[-1][0] != super_admin:
            raise CheckFailedError("a department or person budget version left no ledger entry")
    for _, details in shown + logged:
        text_of = str(details)
        if any(str(figure) in text_of for figure in (*COMPANY_CEILINGS, PERSON_CEILING)):
            raise CheckFailedError("a budget's figure was written to the ledger")
    if not await refused(
        _company_set_by(h, request, member, CompanyBudgetAsked(ceiling_minor=1, reason=REASON))
    ):
        raise CheckFailedError("a person with no budget screen set the company's budget")


async def _company_set_by(h: Harness, request: Any, who: str, body: Any) -> Any:
    from brain.company_routes import set_company_budget

    return await set_company_budget(request, body, await asking_as(h, who, strong=True))
