"""The install acceptance check for holding a publish by what a run of the agent costs (M20.5.2).

M20.5.2 asks that an agent whose run costs more than its department allows wait for that
department's administrator before it is published, and that the publish record show what a run
costs. `brain.agent_builder_routes` is the publish route and `brain.builder.run_cost` prices the
run, so this drives the route as a reserved builder of acceptance_a, over the install's own
database, with the department's per-run ceiling written through `brain.ops.budget_store` the way
the budgets screen writes one, and the switch set through `brain.ops.features` the way the Features
page does.

**The check makes the budget it tests.** No install has a per-run ceiling for a reserved department,
so the check writes one, a ceiling of one minor unit that no run can come in under, and then one so
roomy that none can exceed it, as two versions of the same ceiling. It asserts the four things the
leaf names: with the switch off the publish goes out on its author's word; with it on and a ceiling
below the cost it waits, makes no agent, tells the author both figures and cannot be approved by the
author; a second person in the department approves it and the agent exists; and the publish record
holds the cost the gate compared. And with the ceiling raised above the cost, nothing waits.

**Nothing about the install is assumed.** The people, the agents, the budget versions and the switch
are the check's, written inside its transaction and rolled back, and the switch is set explicitly
off before it is set on, whatever an install left it as.

Task ids: M20.5.2
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_builder import (
    PERSONA,
    _builder,
    _document,
    _draft,
    _publish,
    _saved_and_checked,
)
from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
from brain.ops.acceptance_run import SET_UP_REACH, Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page, after the publication reach check's own.
#: See `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 410

HELD_WITH_NO_CEILING: Final = "a publish was held for its cost in a department that set no ceiling"
HELD_WHILE_OFF: Final = "a publish was held for its cost while the switch for it was off"
NOT_HELD: Final = "a publish costing more than its department's ceiling was not held"
HELD_WITHOUT_FIGURES: Final = "a publish held for its cost did not tell its author both figures"
AGENT_MADE_WHILE_HELD: Final = "an agent held for its cost was made before anybody approved it"
AUTHOR_APPROVED: Final = "the author of a publish held for its cost could approve it"
NOT_PUBLISHED_ON_APPROVAL: Final = (
    "a publish held for its cost was not made when a colleague agreed"
)
HELD_WITHIN_THE_CEILING: Final = "a publish costing less than its department's ceiling was held"
NO_COST_ON_THE_RECORD: Final = "the publish record did not show what a run of the agent costs"

#: A ceiling no run comes in under, and one none can exceed, in minor units.
TIGHT: Final = 1
ROOMY: Final = 10**12

#: Far outside any plausible wall clock, so the ceilings are in force whenever the check runs.
FROM: Final = datetime(2019, 1, 1, tzinfo=UTC)


@check(
    leaves=("M20.5.2",),
    sentence=(
        "With its switch on, an agent a builder of acceptance_a publishes that costs more per run "
        "than the department's ceiling waits, makes no agent and cannot be approved by its author; "
        "a colleague approves it and the record holds its cost; below the ceiling, or with the "
        "switch off, it publishes on the author's word."
    ),
)
async def a_costly_publish_waits_for_a_colleague_in_the_department(
    h: Harness,
) -> None:
    from brain.agent_builder_routes import (
        DraftRevisionAsked,
        agent_publications,
        approve_agent_draft,
    )
    from brain.builder.run_cost import HELD_FOR_ITS_COST
    from brain.core.errors import Absent
    from brain.ops.budget_store import append, history_of
    from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
    from brain.ops.features import switch
    from brain.ops.features_declared.publish_cost_hold import PUBLISH_COST_HOLD
    from brain.tables.agent import AgentRow
    from brain.tables.audit import attributed_to

    await h.found_departments()
    author = await _builder(h, "costauthor")
    colleague = await _builder(h, "costcolleague")
    app = _gallery(h, secrets.token_hex(32))
    key = (BudgetLevel.DEPARTMENT, A, BudgetPeriod.RUN)

    async def switched(on: bool) -> None:
        async with h.sessions() as session:
            for statement in attributed_to(
                actor_id=author, ent_hash=SET_UP_REACH, trace_id=h.trace_id
            ):
                await session.execute(statement)
            await switch(session, PUBLISH_COST_HOLD, on=on, by=author)
            await session.commit()

    async def ceiling(minor: int) -> None:
        async with h.sessions() as session:
            history = await history_of(session, key)
            await append(
                session,
                BudgetRow(
                    level=BudgetLevel.DEPARTMENT,
                    subject=A,
                    period=BudgetPeriod.RUN,
                    ceiling_minor=minor,
                    version=1 if history is None else history.rows[-1].version + 1,
                    author=author,
                    effective_from=FROM if history is None else h.now,
                    reason="An install acceptance check.",
                ),
                ent_hash=SET_UP_REACH,
                trace_id=h.trace_id,
            )
            await session.commit()

    async def ready() -> tuple[dict[str, object], int]:
        """A new agent draft that reaches nothing, saved and checked: only its cost can hold it."""
        draft = await _draft(h, app, author)
        agent_id = str(draft["agent_id"])
        revision = await _saved_and_checked(
            h, app, author, draft, _document(agent_id, persona=PERSONA)
        )
        return draft, revision

    async def made(agent_id: object) -> bool:
        found = await h.execute(select(AgentRow.id).where(AgentRow.id == agent_id))
        return found.first() is not None

    # A department that has set no per-run ceiling has said nothing about a run, so even with the
    # switch on nothing is held. Asked only where this department really has none, which is the
    # case for a reserved department and is not assumed.
    async with h.sessions() as session:
        none_set = await history_of(session, key) is None
    if none_set:
        await switched(True)
        draft, revision = await ready()
        status, body = await _publish(h, app, author, str(draft["draft_id"]), revision)
        if status != 201 or body.get("held_for_cost"):
            raise CheckFailedError(HELD_WITH_NO_CEILING)

    await ceiling(TIGHT)

    # Off: the publish goes out on its author's word, whatever the ceiling is.
    await switched(False)
    draft, revision = await ready()
    status, body = await _publish(h, app, author, str(draft["draft_id"]), revision)
    if status != 201 or body.get("held_for_cost"):
        raise CheckFailedError(HELD_WHILE_OFF)

    # On, with a ceiling below the cost: it waits, says why with both figures and makes nothing.
    await switched(True)
    draft, revision = await ready()
    status, body = await _publish(h, app, author, str(draft["draft_id"]), revision)
    if (
        status != 202
        or body.get("held_for_cost") is not True
        or body.get("sentence") != (HELD_FOR_ITS_COST)
    ):
        raise CheckFailedError(NOT_HELD)
    cost, limit = body.get("cost_minor"), body.get("ceiling_minor")
    if not isinstance(cost, int) or limit != TIGHT or cost <= TIGHT or not body.get("currency"):
        raise CheckFailedError(HELD_WITHOUT_FIGURES)
    if await made(draft["agent_id"]):
        raise CheckFailedError(AGENT_MADE_WHILE_HELD)

    # The author cannot approve their own; a colleague in the department can, and it is made.
    approving = DraftRevisionAsked(revision=revision)
    try:
        own = await approve_agent_draft(
            _request(app), str(draft["draft_id"]), approving, await _asking(h, author)
        )
    except Absent:
        own = None
    if own is not None and own.status_code == 201:
        raise CheckFailedError(AUTHOR_APPROVED)
    approved = await approve_agent_draft(
        _request(app), str(draft["draft_id"]), approving, await _asking(h, colleague)
    )
    if approved.status_code != 201 or not await made(draft["agent_id"]):
        raise CheckFailedError(NOT_PUBLISHED_ON_APPROVAL)
    history = (
        await agent_publications(_request(app), str(draft["agent_id"]), await _asking(h, author))
    ).publications
    if [one.cost_minor for one in history] != [cost]:
        raise CheckFailedError(NO_COST_ON_THE_RECORD)

    # On, with a ceiling above the cost: nothing waits.
    await ceiling(ROOMY)
    draft, revision = await ready()
    status, body = await _publish(h, app, author, str(draft["draft_id"]), revision)
    if status != 201 or body.get("held_for_cost"):
        raise CheckFailedError(HELD_WITHIN_THE_CEILING)
