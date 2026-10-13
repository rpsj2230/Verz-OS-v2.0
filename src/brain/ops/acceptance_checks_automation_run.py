"""The install acceptance check for what an automation runs at: its owner's live reach at the
instant it starts, and a refusal that pauses it with its reason when the owner loses what it reads.

**The decision is the product's and the rows are the install's.** `brain.ops.automation_run_store`
writes a run on the database owner's connection, and the role a check runs as can read a run and
never write one, so a check cannot make the worker run an automation. What it can do is exactly
what the worker does first: read the automation's own row, its owner through the directory, the
owner's grants through the one resolver and the agent from the agent table, and hand all four to
`brain.ops.automation_run.admitted_run`, which decides whether the run starts and at which reach.
The check installs an automation as a library person would (the row the gallery writes), asks
that decision with the owner holding the grant the task reads, revokes the grant, and asks again.
**The second answer must be a refusal naming the lost reach, and `afterwards` must turn it into a
pause with no next run**, which is what stops a refused automation from being refused on every
slot for ever. See `A_RUN_IS_ITS_OWNERS_AT_THE_INSTANT_IT_STARTS`.

**What this does not show**, and says so: that the worker's tick starts the runner is the
schedule's own record (`ops.control_run`), and the write of the run and its pause is proved in CI
against a real database (`tests/unit/test_automation_run_store.py`).

Task ids: M17.4.3, M17.4.4
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import func, insert, select, text, update

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.console.agent_automations import Automation

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2010


@check(
    leaves=("M17.4.3", "M17.4.4"),
    sentence=(
        "An automation installed by a person holding what its task reads is admitted at a reach "
        "carrying it; once that grant is revoked the same automation is refused as having lost "
        "its reach, and the refusal leaves it paused with no next run."
    ),
)
async def an_automation_runs_at_its_owner_s_reach_and_stops_without_it(
    h: Harness,
) -> None:
    from brain.agent_routes import one_agent, record_of
    from brain.console.agent_automations import Automation
    from brain.console.automation_gallery import BUILT_IN
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_checks_agent_reach import _agent
    from brain.ops.automation_owner_store import PRINCIPAL_SETTING
    from brain.ops.automation_run import (
        Admitted,
        PausedBecause,
        RunOutcome,
        admitted_run,
        afterwards,
        task_declaration,
    )
    from brain.tables.agent_automation import AgentAutomationRow
    from brain.tables.gate import CapabilityGrantRow

    runnable = [
        (one, task)
        for one in BUILT_IN
        if (task := task_declaration(one.task)) is not None and task.reads is not None
    ]
    if not runnable:
        raise CheckFailedError("no automation template names a task this install can run")
    template, declaration = runnable[0]
    if declaration.reads is None:  # pragma: no cover - filtered above; narrows the type
        raise CheckFailedError("no automation template names a task this install can run")
    reads = declaration.reads.value

    await h.found_departments()
    owner = h.principal(A, "owner")
    await h.person(owner, department=A, grants=_in(A, reads))
    agent_id = await _agent(h, owner, "automation", (reads,))
    automation_id = f"acceptance-{h.run}-automation"
    due = h.now - timedelta(minutes=1)
    await h.execute(
        *h.attributed(owner),
        text("SELECT set_config(:name, :value, true)").bindparams(
            name=PRINCIPAL_SETTING, value=owner
        ),
        insert(AgentAutomationRow).values(
            automation_id=automation_id,
            agent_id=agent_id,
            name=template.name,
            runs_as_id=owner,
            task=template.task,
            next_run_at=due,
            guards=template.guards,
            template_id=template.template_id,
            template_version=template.version,
            installed_by=owner,
        ),
    )

    async def decided() -> Admitted | PausedBecause:
        """What the worker decides for this automation now, from rows read afresh."""
        async with h.sessions() as session:
            row = (
                await session.execute(
                    select(AgentAutomationRow).where(
                        AgentAutomationRow.automation_id == automation_id
                    )
                )
            ).scalar_one()
            agent_row = (await session.execute(one_agent(row.agent_id))).scalar_one_or_none()
        person = await StoredPrincipals(h.sessions).live_principal(row.runs_as_id)
        if person is None or agent_row is None:
            raise CheckFailedError("an installed automation's owner or agent was not found")
        automation = Automation(
            automation_id=row.automation_id,
            agent_id=row.agent_id,
            name=row.name,
            runs_as=person,
            task=row.task,
            next_run_at=row.next_run_at,
        )
        return admitted_run(
            automation,
            owner=person,
            owner_entitlements=await StoredEntitlements(h.sessions).load(row.runs_as_id, h.now),
            agent=record_of(agent_row),
            now=h.now,
        )

    first = await decided()
    if isinstance(first, PausedBecause):
        raise CheckFailedError("an automation whose owner holds what it reads was refused")
    if first.reach.scope_for(declaration.reads, h.now) is None:
        raise CheckFailedError("an admitted run's reach does not hold what its task reads")

    await h.execute(
        *h.attributed(owner),
        update(CapabilityGrantRow)
        .where(
            CapabilityGrantRow.principal_id == owner,
            CapabilityGrantRow.capability == reads,
            CapabilityGrantRow.deleted_at.is_(None),
        )
        .values(deleted_at=func.statement_timestamp()),
    )
    second = await decided()
    if second is not PausedBecause.OWNER_LOST_REACH:
        raise CheckFailedError("an automation whose owner lost what it reads was not refused")

    after = afterwards(
        _automation(owner, agent_id, template.name, template.task, due),
        outcome=RunOutcome.REFUSED,
        refused_because=PausedBecause.OWNER_LOST_REACH,
        failures_before=0,
        cadence=None,
        owner_id=owner,
        guards=template.guards,
        at=h.now,
    )
    if after.next_run_at is not None or after.paused_because is not PausedBecause.OWNER_LOST_REACH:
        raise CheckFailedError("a refused run did not leave the automation paused with its reason")


def _automation(owner: str, agent_id: str, name: str, task: str, due: datetime) -> Automation:
    """The automation as `afterwards` is told of it: a name, an agent, a task and its owner."""
    from brain.console.agent_automations import Automation
    from brain.core.principal import Employment, Principal, PrincipalKind

    return Automation(
        automation_id="auto-acceptance",
        agent_id=agent_id,
        name=name,
        runs_as=Principal(
            id=owner,
            kind=PrincipalKind.HUMAN,
            employment=Employment.STAFF,
            display_name="Acceptance check owner",
        ),
        task=task,
        next_run_at=due,
    )
