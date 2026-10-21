"""Install checks for stored workflows: writing and assigning one, and running it through the gate.

Each check calls the functions the console's routes call, as the reader that page serves, over the
check's own transaction, and reads the answer back from the tables that keep it. **Every row written
is in the transaction the run rolls back, for reserved people of acceptance_a and acceptance_b, and
nothing reaches a person.**

**The first check proves the configuration against a real database.** An administrator saves a
workflow twice and reads back two versions; a definition that asks for prose, or reads an output
nobody declared, is refused with its reasons and leaves no row; a colleague is answered as for a
screen that is not there; the workflow is assigned to an agent; and an agent not assigned it and a
workflow that does not exist are refused in one sentence before any step runs.

**The second check runs a workflow through the route a person presses, over the install's own
tools.** The agent's ceiling names the price list's four columns and the person who asks holds two,
so a step that reads a third gets nothing and is stated as a failed step, which is the gate's mask
holding at the workflow's level. The workflow has a step skipped by a condition, a step refused and
handled by another, and a step that can never succeed because of what the asker holds. Run three
times, the step that fails in each of them opens one candidate for a person, the workflow stays at
its one version, and the trace holds statuses and words and not one value the steps read.

**Not claimed:** parallel steps and retries over a source that fails are proved by the engine's
tests (`tests/unit/test_orchestration_workflow_run.py`), because no source on an install fails on
demand; and the two-connector, two-skill workflow of M17.6.8 and the monthly search report of
M17.7.1 need a person, a named client and the owner's analytics access.

Task ids: M17.6.1, M17.6.2, M17.6.3, M17.6.4, M17.6.6, M17.6.7, M17.7.7
"""

from __future__ import annotations

from collections.abc import Awaitable
from types import SimpleNamespace
from typing import Any, Final, cast

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_agent_console import _asking, _console, _readers, _request
from brain.ops.acceptance_run import Harness
from brain.ops.acceptance_workspace import installed_agent

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2690

A, B = RESERVED_DEPARTMENTS

#: The authority the check's administrator holds. Restated, so a change to a route's authority fails
#: its check instead of moving with it.
LIFECYCLE: Final = "admin:agent_lifecycle"

#: What the person who asks holds on the price list, and what the agent's ceiling names.
ASKER_HOLDS: Final = ("read:price_list", "read:price_list.name", "read:price_list.sell_price")
AGENT_NAMES: Final = (*ASKER_HOLDS, "read:price_list.cost", "read:price_list.margin")

SAVED_NOTHING: Final = "an administrator could not save a workflow"
VERSIONS_WERE_LOST: Final = "saving a workflow twice did not keep two versions"
A_BAD_DEFINITION_WAS_SAVED: Final = (
    "a definition asking for prose or an undeclared output was saved"
)
A_COLLEAGUE_WROTE: Final = "a colleague who holds no authority saved or listed a workflow"
NOT_ASSIGNED: Final = "an administrator could not assign a workflow to an agent"
THE_ASSIGNMENT_WAS_NOT_KEPT: Final = "an assignment was not in its table with who made it"
AN_UNASSIGNED_RUN_STARTED: Final = "a workflow ran through an agent that was never assigned it"
THE_REFUSALS_DIFFER: Final = "an unassigned workflow and a missing one were refused differently"
IT_RAN_WITH_THE_SWITCH_OFF: Final = "a workflow ran while running was switched off"

THE_RUN_WAS_NOT_PARTIAL: Final = "a run with a handled failure and a gap did not end as partial"
A_SKIP_DID_NOT_SAY_WHY: Final = "a step skipped by a condition did not carry the condition"
A_REFUSAL_WAS_NOT_STATED: Final = "a step refused by the gate was not stated as refused"
THE_HANDLER_DID_NOT_RUN: Final = "the handler of a refused step did not run"
THE_MASK_DID_NOT_HOLD: Final = "a step read a column the asker does not hold"
A_STEP_RAN_THAT_SHOULD_NOT_HAVE: Final = "a step ran that its condition or its handler excluded"
THE_TRACE_WAS_NOT_KEPT: Final = "a run's trace was not in the tables with its steps"
THE_TRACE_HELD_A_VALUE: Final = "a run's trace held a value a step read"
NO_SIGNAL_WAS_SENT: Final = "a finished run left no signal naming the workflow, agent and step"
NO_CANDIDATE_WAS_OPENED: Final = "a step that failed in each of three runs opened no candidate"
A_CANDIDATE_CAME_TOO_SOON: Final = "a candidate was opened before a step had failed three times"
THE_WORKFLOW_CHANGED_ITSELF: Final = "a workflow changed after it failed"


def _definition(tool: str, names: list[str]) -> dict[str, Any]:
    """Six steps over the price list: a read, a skipped read, a refused read with a handler, the
    handler, a read of a column the asker does not hold, and one that follows them all."""
    filters = {"clauses": [{"field": "name", "op": "in", "value": names}]}
    read = {"filters": filters, "limit": 5}
    return {
        "name": "Price list check",
        "steps": [
            {
                "id": "fetch",
                "kind": "tool",
                "target": tool,
                "arguments": read,
                "outputs": [
                    {"name": "label", "kind": "label", "path": "name"},
                    {"name": "price", "kind": "label", "path": "sell_price"},
                ],
            },
            {
                "id": "skipped",
                "kind": "tool",
                "target": tool,
                "arguments": read,
                "after": ["fetch"],
                "when": {"ref": "fetch.label", "op": "eq", "value": "a name no row has"},
            },
            {
                "id": "refused",
                "kind": "tool",
                "target": "acceptance.no_such_tool",
                "after": ["fetch"],
                "on_failure": "handler",
            },
            {
                "id": "handler",
                "kind": "tool",
                "target": tool,
                "arguments": read,
                "after": ["refused"],
                "handles": "refused",
            },
            {
                "id": "peek",
                "kind": "tool",
                "target": tool,
                "arguments": read,
                "after": ["fetch"],
                "outputs": [{"name": "cost", "kind": "label", "path": "cost"}],
                "on_failure": "continue",
            },
            {
                "id": "last",
                "kind": "tool",
                "target": tool,
                "arguments": read,
                "after": ["handler", "peek"],
            },
        ],
    }


async def _price_list(h: Harness) -> tuple[str, list[str]]:
    """The install's price list tool, and two rows the check writes, by the names it gave them."""
    from brain.knowledge.columns import PRICE_LIST
    from brain.knowledge.rows import RowTool
    from brain.tables.projection import ProjectedRecordRow

    tool = RowTool(
        source=h.settings.tool_source, classification=PRICE_LIST, description="The price list."
    ).name
    names = sorted({h.word(), h.word()})
    for n, name in enumerate(names):
        await h.execute(
            *h.attributed(),
            insert(ProjectedRecordRow).values(
                source=h.settings.tool_source,
                entity=PRICE_LIST.entity,
                source_id=f"acceptance-{h.run}-wf-{n}",
                last_seen_at=h.now,
                fields={
                    "department": A,
                    "sku": f"WF-{n}",
                    "name": name,
                    "sell_price": "120.00",
                    "cost": "70.00",
                    "margin": "50.00",
                },
            ),
        )
    return tool, names


async def _administrator(h: Harness) -> str:
    made = h.principal(A, "workflows")
    await h.person(made, department=A, grants=((LIFECYCLE, Scope.unrestricted()),))
    return made


async def _as_the_route_sees_it(h: Harness, who: str, *, strong: bool = False) -> Any:
    from brain.gate.context import Channel

    got = await _asking(h, who, strong=strong)
    return SimpleNamespace(caller=got.caller, reach=got.reach, now=got.now, channel=Channel.CONSOLE)


async def _any(call: Awaitable[object]) -> Any:
    """A route's answer, which is its view or a 409 body, read by the check as it finds it."""
    return cast(Any, await call)


def _refused(reply: Any) -> bool:
    return int(getattr(reply, "status_code", 200)) == 409


async def _count(h: Harness, sql: str, **bound: Any) -> int:
    async with h.sessions() as session:
        return int((await session.execute(text(sql), bound)).scalar_one())


# --------------------------------------- 1. writing, assigning and refusing (M17.6.1, M17.7.7)
@check(
    leaves=("M17.6.1", "M17.7.7"),
    sentence=(
        "An administrator saves a workflow twice and reads two versions; a definition asking for "
        "prose is refused with its reasons and leaves no row; a colleague is answered as for a "
        "screen that is not there; it is assigned to an agent; and an unassigned workflow and a "
        "missing one are refused in one sentence before any step runs."
    ),
)
async def a_workflow_is_saved_in_versions_and_run_by_an_assigned_agent(
    h: Harness,
) -> None:
    from brain.core.errors import BrainError
    from brain.ops.acceptance_switch import switched
    from brain.ops.features_declared.stored_workflows import STORED_WORKFLOWS
    from brain.workflow_routes import (
        WorkflowIdAsked,
        WorkflowSaveAsked,
        assign_workflow,
        list_workflows,
        run_assigned_workflow,
        save_workflow,
    )

    await h.found_departments()
    tool, names = await _price_list(h)
    admin, colleague = await _administrator(h), h.principal(A, "colleague")
    await h.person(colleague, department=A, grants=_readers())
    agent = await installed_agent(h, admin, suffix="_wf")
    app = _console(h)
    workflow = f"acceptance-{h.run}-wf"
    request = _request(app)

    async def save(who: str, definition: dict[str, Any]) -> Any:
        return await save_workflow(
            request,
            WorkflowSaveAsked(workflow_id=workflow, definition=definition),
            await _as_the_route_sees_it(h, who, strong=True),
        )

    first = await save(admin, _definition(tool, names))
    if _refused(first) or first.version != 1:
        raise CheckFailedError(SAVED_NOTHING)
    second = await save(admin, _definition(tool, names))
    if _refused(second) or second.version != 2:
        raise CheckFailedError(VERSIONS_WERE_LOST)
    if (
        await _count(
            h, "SELECT count(*) FROM ops.workflow_version WHERE workflow_id = :w", w=workflow
        )
        != 2
    ):
        raise CheckFailedError(VERSIONS_WERE_LOST)

    prose = _definition(tool, names)
    prose["steps"][0]["outputs"][0]["kind"] = "text"
    unread = _definition(tool, names)
    unread["steps"][1]["when"]["ref"] = "fetch.nothing_declared"
    for bad in (prose, unread):
        if not _refused(await save(admin, bad)):
            raise CheckFailedError(A_BAD_DEFINITION_WAS_SAVED)
    if (
        await _count(
            h, "SELECT count(*) FROM ops.workflow_version WHERE workflow_id = :w", w=workflow
        )
        != 2
    ):
        raise CheckFailedError(A_BAD_DEFINITION_WAS_SAVED)

    for refused_call in (
        save(colleague, _definition(tool, names)),
        list_workflows(request, await _as_the_route_sees_it(h, colleague)),
    ):
        try:
            await refused_call
        except BrainError:
            continue
        raise CheckFailedError(A_COLLEAGUE_WROTE)

    assigned = await _any(
        assign_workflow(
            request,
            agent,
            WorkflowIdAsked(workflow_id=workflow),
            await _as_the_route_sees_it(h, admin, strong=True),
        )
    )
    if _refused(assigned) or assigned.workflows != [workflow]:
        raise CheckFailedError(NOT_ASSIGNED)
    if (
        await _count(
            h,
            "SELECT count(*) FROM agent.workflow_assignment"
            " WHERE agent_id = :a AND workflow_id = :w"
            " AND assigned_by = :by AND removed_at IS NULL",
            a=agent,
            w=workflow,
            by=admin,
        )
        != 1
    ):
        raise CheckFailedError(THE_ASSIGNMENT_WAS_NOT_KEPT)

    # An agent that was never assigned it, and a workflow that does not exist, are one refusal; and
    # nothing runs while the switch is off.
    other = await installed_agent(h, admin, suffix="_wf_other")
    await switched(h, STORED_WORKFLOWS, on=False)
    asker = await _as_the_route_sees_it(h, colleague)
    if not _refused(
        await _any(
            run_assigned_workflow(request, agent, WorkflowIdAsked(workflow_id=workflow), asker)
        )
    ):
        raise CheckFailedError(IT_RAN_WITH_THE_SWITCH_OFF)
    await switched(h, STORED_WORKFLOWS, on=True)
    unassigned = await _any(
        run_assigned_workflow(request, other, WorkflowIdAsked(workflow_id=workflow), asker)
    )
    missing = await _any(
        run_assigned_workflow(
            request, agent, WorkflowIdAsked(workflow_id="no-such-workflow"), asker
        )
    )
    if not (_refused(unassigned) and _refused(missing)):
        raise CheckFailedError(AN_UNASSIGNED_RUN_STARTED)
    if unassigned.body != missing.body:
        raise CheckFailedError(THE_REFUSALS_DIFFER)
    if await _count(h, "SELECT count(*) FROM ops.workflow_run WHERE workflow_id = :w", w=workflow):
        raise CheckFailedError(AN_UNASSIGNED_RUN_STARTED)


# --------------------------------- 2. a run through the gate, kept as one trace (M17.6.2 ...)
@check(
    leaves=("M17.6.2", "M17.6.3", "M17.6.4", "M17.6.6", "M17.6.7"),
    sentence=(
        "A workflow run through the route reads the price list at the asker's two columns and no "
        "third, skips a step by its condition and says which, states a refused step and runs its "
        "handler, keeps one trace of words and no value, tells subscribers which step failed, and "
        "opens one candidate when a step fails in each of three runs and changes nothing."
    ),
)
async def a_workflow_runs_through_the_gate_and_one_trace_is_kept(h: Harness) -> None:
    from brain.ops.acceptance_switch import switched
    from brain.ops.features_declared.stored_workflows import STORED_WORKFLOWS
    from brain.workflow_routes import (
        WorkflowIdAsked,
        WorkflowSaveAsked,
        assign_workflow,
        run_assigned_workflow,
        save_workflow,
    )

    await h.found_departments()
    tool, names = await _price_list(h)
    admin, asker_id = await _administrator(h), h.principal(A, "asker")
    await h.person(asker_id, department=A, grants=[(c, Scope.unrestricted()) for c in ASKER_HOLDS])
    agent = await installed_agent(
        h,
        admin,
        suffix="_wfrun",
        capabilities=AGENT_NAMES,
        allowed_tools=(tool,),
        scope=Scope.unrestricted(),
    )
    app = _console(h)
    request = _request(app)
    workflow = f"acceptance-{h.run}-run"
    await switched(h, STORED_WORKFLOWS, on=True)
    strong = await _as_the_route_sees_it(h, admin, strong=True)
    saved = await save_workflow(
        request,
        WorkflowSaveAsked(workflow_id=workflow, definition=_definition(tool, names)),
        strong,
    )
    if _refused(saved):
        raise CheckFailedError(SAVED_NOTHING)
    await assign_workflow(request, agent, WorkflowIdAsked(workflow_id=workflow), strong)
    asked = await _as_the_route_sees_it(h, asker_id)

    runs = []
    for number in range(3):
        ran = await _any(
            run_assigned_workflow(request, agent, WorkflowIdAsked(workflow_id=workflow), asked)
        )
        if _refused(ran):
            raise CheckNotRunError("this install could not run a workflow through its own tools")
        runs.append(ran)
        if number < 2 and ran.candidates_opened:
            raise CheckFailedError(A_CANDIDATE_CAME_TOO_SOON)
    first = runs[0]
    by = {one.step_id: one for one in first.steps}
    if first.outcome != "partial" or first.failed_step != "refused":
        raise CheckFailedError(THE_RUN_WAS_NOT_PARTIAL)
    if by["fetch"].status != "ok" or by["last"].status != "ok":
        raise CheckFailedError(A_STEP_RAN_THAT_SHOULD_NOT_HAVE)
    if (by["skipped"].status, by["skipped"].cause) != ("skipped", "condition_not_met") or (
        "fetch.label eq" not in by["skipped"].detail
    ):
        raise CheckFailedError(A_SKIP_DID_NOT_SAY_WHY)
    if (by["refused"].status, by["refused"].cause) != ("failed", "refused"):
        raise CheckFailedError(A_REFUSAL_WAS_NOT_STATED)
    if by["handler"].status != "ok":
        raise CheckFailedError(THE_HANDLER_DID_NOT_RUN)
    if (by["peek"].status, by["peek"].cause) != ("failed", "invalid_output"):
        raise CheckFailedError(THE_MASK_DID_NOT_HOLD)
    if runs[2].candidates_opened != ["refused", "peek"]:
        raise CheckFailedError(NO_CANDIDATE_WAS_OPENED)

    if (
        await _count(
            h,
            "SELECT count(*) FROM ops.workflow_run WHERE workflow_id = :w AND run_by = :by",
            w=workflow,
            by=asker_id,
        )
        != 3
    ):
        raise CheckFailedError(THE_TRACE_WAS_NOT_KEPT)
    if (
        await _count(
            h,
            "SELECT count(*) FROM ops.workflow_step_run s JOIN ops.workflow_run r"
            " ON r.run_id = s.run_id WHERE r.workflow_id = :w",
            w=workflow,
        )
        != 18
    ):
        raise CheckFailedError(THE_TRACE_WAS_NOT_KEPT)
    async with h.sessions() as session:
        words = (
            await session.execute(
                text(
                    "SELECT s.status, s.cause, s.detail FROM ops.workflow_step_run s JOIN"
                    " ops.workflow_run r ON r.run_id = s.run_id WHERE r.workflow_id = :w"
                ),
                {"w": workflow},
            )
        ).all()
    if any(value in repr(words) for value in ("120.00", "70.00", "50.00", *names)):
        raise CheckFailedError(THE_TRACE_HELD_A_VALUE)
    signals = await _count(
        h,
        "SELECT count(*) FROM ops.outbox_event WHERE kind = 'automation.run_finished'"
        " AND entity = 'workflow_run' AND attributes->>'workflow_id' = :w"
        " AND attributes->>'agent_id' = :a AND attributes->>'failed_step' = 'refused'",
        w=workflow,
        a=agent,
    )
    if signals != 3:
        raise CheckFailedError(NO_SIGNAL_WAS_SENT)
    candidates = await _count(
        h,
        "SELECT count(*) FROM ops.evaluation_candidate WHERE agent_id = :a AND source = 'workflow'"
        " AND case_ref IN (:r, :p)",
        a=agent,
        r=f"workflow:{workflow}:refused",
        p=f"workflow:{workflow}:peek",
    )
    if candidates != 2:
        raise CheckFailedError(NO_CANDIDATE_WAS_OPENED)
    if (
        await _count(
            h, "SELECT count(*) FROM ops.workflow_version WHERE workflow_id = :w", w=workflow
        )
        != 1
    ):
        raise CheckFailedError(THE_WORKFLOW_CHANGED_ITSELF)
