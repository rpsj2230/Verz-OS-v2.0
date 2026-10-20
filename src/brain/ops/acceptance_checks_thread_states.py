"""Install acceptance check for the state shown beside each recent conversation (M40.7.6).

A member with six conversations is asked for their list through `GET /threads`' own function, with
the install's database under it: one whose run answered, one that failed, one that held an action
for a colleague to approve, one whose approved action is still to be carried out, and one whose
approved action was carried out. **What the check is for is the three ways a state can be wrong
without looking it**: one person's list reading another's pending approval, a held action reading as
done, and a switch that does not switch. Each is asked beside the act that works.

**The rows are the product's own.** The conversations are written through `StoredThreads.record`,
the held actions through `put_suspension` and decided through `take_decision`, the request that
failed through `RequestTelemetry`, and the worker's run through the operation ledger's own table, so
the store reads what a running install holds and not a shape the check made up.

Task ids: M40.7.6
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1960

A, _B = RESERVED_DEPARTMENTS

#: The capability the held action needs, held in acceptance_a by its asker and its approver.
CAPABILITY: Final = "write:ticket.status"

#: The gate steps the failed request entered, in the words the gate keeps them.
FAILED_STEPS: Final = {"identify": 1.0, "entitle": 1.0, "invoke": 5.0}

#: The reasons a check fails, one literal sentence each: a reason is served on a public page.
SWITCH_OFF_SHOWED_A_STATE: Final = "a conversation was given a state while the switch was off"
SWITCH_OFF_HID_A_THREAD: Final = "turning the switch off hid a conversation from its owner"
ANSWERED_NOT_DONE: Final = "a conversation whose run answered was not shown as done"
FAILED_NOT_SHOWN: Final = "a conversation whose run failed was not shown as failed"
FAILED_STEP_WRONG: Final = "a failed conversation did not name the last step its request entered"
HELD_NOT_WAITING: Final = "a conversation holding an action for approval was not shown as waiting"
APPROVED_NOT_RUNNING: Final = "an approved action not yet carried out was not shown as running"
CARRIED_OUT_NOT_DONE: Final = "an approved action that was carried out was not shown as done"
LAPSED_STILL_WAITING: Final = "an approval that lapsed still showed as waiting"
READ_ANOTHERS_APPROVAL: Final = "a conversation took its state from another person's approval"
LISTED_ANOTHERS: Final = "a person was listed a conversation that was not theirs"
SEARCH_DISAGREED: Final = "the search showed a different state from the list"


def _key(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


@check(
    leaves=("M40.7.6",),
    sentence=(
        "A member's list says whether each conversation is done, failed (and at which step), "
        "waiting for approval or running, from their own run and approval records; another "
        "person's approval on the same request, and a lapsed one, change nothing; and with the "
        "switch off the same conversations are listed with no state."
    ),
)
async def each_recent_conversation_says_where_its_run_has_got_to(h: Harness) -> None:
    from sqlalchemy import insert, update

    from brain.approval_routes import DecidableVerdict, DecisionAsked, take_decision
    from brain.chat.thread_store import Exchange, StoredThreads, failed_exchange
    from brain.core.envelope import SideEffect, ToolDefinition
    from brain.core.lane import Lane
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.gate.context import Channel, TrafficClass
    from brain.gate.leash import Action, SuspendedAction, render_artefact
    from brain.gate.suspension_store import StoredSuspensions, put_suspension
    from brain.member.shell import member_capability
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_operations_console import asking_as, console_for, traced
    from brain.ops.acceptance_threads import _asking, _request, _web
    from brain.ops.features_declared.thread_states import THREAD_STATES
    from brain.ops.telemetry import Ingress, RequestStatus, RequestTelemetry
    from brain.tables.chat import RunState
    from brain.tables.operation import OperationRow
    from brain.tables.telemetry import RequestTelemetryRow
    from brain.thread_routes import my_threads, search_my_threads

    await h.found_departments()
    everywhere = Scope.unrestricted()
    member = (
        (member_capability("home").value, everywhere),
        ("read:member.content", everywhere),
    )
    ada, ben, approver, administrator = (
        h.principal(A, role) for role in ("states", "other", "approver", "states_admin")
    )
    await h.person(ada, department=A, grants=(*_in(A, CAPABILITY), *member))
    await h.person(ben, department=A, grants=(*_in(A, CAPABILITY), *member))
    await h.person(approver, department=A, grants=_in(A, CAPABILITY))
    await h.person(administrator, department=A, grants=(("admin:feature", everywhere),))

    app: FastAPI = await _web(h)
    store = StoredThreads(h.sessions)
    run = h.run.replace("-", "")[:12]
    traces = {
        name: f"acceptance_{run}_{name}"
        for name in ("done", "failed", "held", "running", "ran", "lapsed")
    }

    async def thread(name: str, state: RunState = RunState.ANSWERED) -> str:
        agent = f"acceptance_{run}_agent"
        trace = traces[name]
        if state is RunState.FAILED:
            exchange = failed_exchange(f"Question {name}?", agent_id=agent, trace_id=trace)
        else:
            exchange = Exchange(
                question=f"Question {name}?",
                answer="An answer.",
                refs=(),
                agent_id=agent,
                trace_id=trace,
                state=state,
            )
        return await store.record(
            ada, thread_id=None, channel=Channel.CONSOLE, exchange=exchange, now=h.now
        )

    ids = {name: await thread(name) for name in ("done", "held", "running", "ran", "lapsed")}
    ids["failed"] = await thread("failed", RunState.FAILED)

    # The failed request, as the gate recorded it: the steps it entered and how it ended.
    await h.execute(
        insert(RequestTelemetryRow).values(
            dict(
                RequestTelemetry(
                    ingress=Ingress(
                        trace_id=traces["failed"],
                        traffic_class=TrafficClass.HUMAN_INTERACTIVE,
                        received_at=h.now,
                    ),
                    principal=ada,
                    entitlement_hash="0" * 32,
                    lane=Lane.FAST,
                    tool_count=0,
                    cache_hit=False,
                    status=RequestStatus.FAILED,
                    duration_ms=1.0,
                    stage_ms=FAILED_STEPS,
                ).ledger_row()
            )
        )
    )

    # The held actions, raised by the product's own store and decided by its own route function.
    suspensions = StoredSuspensions(h.sessions)
    asking, approving = await h.reach(ada), await h.reach(approver)
    tool = ToolDefinition(
        name=f"acceptance_{run}.state_step",
        description="The acceptance check's own action, which changes nothing anywhere",
        entity="ticket",
        required_capability=CAPABILITY,
        side_effect=SideEffect.WRITE,
    )

    async def raised(name: str, *, by: str, trace: str, window: timedelta, ago: timedelta) -> str:
        action = Action(
            agent_id=f"acceptance_{run}_agent",
            tool=tool,
            target=tool.name,
            row={"department": A},
        )
        when = h.now - ago
        held = SuspendedAction(
            id=f"acceptance_{run}_{name}",
            trace_id=trace,
            action=action,
            principal_id=by,
            ent_hash=(asking if by == ada else await h.reach(by)).ent_hash(),
            artefact=render_artefact(action),
            action_digest=action.digest(),
            raised_at=when,
            expires_at=when + window,
        )
        async with suspensions.holding(asking if by == ada else await h.reach(by), when) as rows:
            await put_suspension(rows.session, held)
        return held.id

    hour = timedelta(hours=1)
    minutes = timedelta(minutes=10)
    await raised("held", by=ada, trace=traces["held"], window=4 * hour, ago=minutes)
    running = await raised("running", by=ada, trace=traces["running"], window=4 * hour, ago=minutes)
    ran = await raised("ran", by=ada, trace=traces["ran"], window=4 * hour, ago=minutes)
    await raised("lapsed", by=ada, trace=traces["lapsed"], window=hour, ago=3 * hour)
    # Another person's approval on the request of ada's settled conversation.
    await raised("others", by=ben, trace=traces["done"], window=4 * hour, ago=minutes)
    for one in (running, ran):
        await take_decision(
            suspensions,
            one,
            approving,
            DecisionAsked(verdict=DecidableVerdict.APPROVED),
            trace_id=h.trace_id,
            now=h.now,
        )
    # The worker's run of the second approval has settled; the first has not begun.
    key = _key(ran)
    await h.execute(
        insert(OperationRow).values(
            key=key,
            connector="acceptance",
            tool=tool.name,
            principal_id=ada,
            intent_ref=ran,
            state="pending",
        )
    )
    for state in ("sent", "succeeded"):
        await h.execute(update(OperationRow).where(OperationRow.key == key).values(state=state))

    async def switched(on: bool, n: int) -> None:
        async with traced(h, n):
            await switch_feature(
                console_for(h).request("POST"),
                THREAD_STATES.name,
                SwitchAsked(on=on),
                await asking_as(h, administrator, strong=True),
            )

    async def listed(who: str) -> dict[str, Any]:
        shown = await my_threads(_request(app), await _asking(h, who))
        return {one.thread_id: one for one in shown.items}

    # Off: every conversation is listed and none has a state.
    await switched(False, 1)
    off = await listed(ada)
    if set(off) != set(ids.values()):
        raise CheckFailedError(SWITCH_OFF_HID_A_THREAD)
    if any(one.state or one.failed_step for one in off.values()):
        raise CheckFailedError(SWITCH_OFF_SHOWED_A_STATE)

    await switched(True, 2)
    on = await listed(ada)
    if on[ids["done"]].state != "done":
        # Ben's approval on ada's request is the only held action it could have read.
        raise CheckFailedError(
            READ_ANOTHERS_APPROVAL if on[ids["done"]].state else ANSWERED_NOT_DONE
        )
    if on[ids["failed"]].state != "failed":
        raise CheckFailedError(FAILED_NOT_SHOWN)
    if "reading and asking" not in on[ids["failed"]].failed_step:
        raise CheckFailedError(FAILED_STEP_WRONG)
    if on[ids["held"]].state != "waiting_for_approval":
        raise CheckFailedError(HELD_NOT_WAITING)
    if on[ids["running"]].state != "running":
        raise CheckFailedError(APPROVED_NOT_RUNNING)
    if on[ids["ran"]].state != "done":
        raise CheckFailedError(CARRIED_OUT_NOT_DONE)
    if on[ids["lapsed"]].state != "done":
        raise CheckFailedError(LAPSED_STILL_WAITING)
    if any(one.failed_step for key_, one in on.items() if key_ != ids["failed"]):
        raise CheckFailedError(FAILED_STEP_WRONG)

    # Another person's list holds none of these, and the search says what the list says.
    if set(await listed(ben)) & set(ids.values()):
        raise CheckFailedError(LISTED_ANOTHERS)
    found = await search_my_threads(_request(app), await _asking(h, ada), "Question")
    if {one.thread_id: one.state for one in found.items} != {k: v.state for k, v in on.items()}:
        raise CheckFailedError(SEARCH_DISAGREED)
