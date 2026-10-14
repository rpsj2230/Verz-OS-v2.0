"""The install acceptance check for an automation a change starts: one run, as its owner, for what
they may read, and for nothing else.

The owner decided on 2026-10-13 (needs-rupash 223, option B) that an automation starts by a schedule
or when a connected source's index reports a changed record, and that nothing from outside starts
one. A test over fakes shows the pass. What an install shows is the same acts against its own
database: a record changes in the index through the sync's own upsert, the worker's own pass finds
it, and the automation's owner is the person the run is recorded as.

**The check writes a source of its own and runs two automations of its own, and nothing else.** The
source's name is made for the run, so it holds no record of anyone's and cannot meet one. The pass
is `run_changes_of`, one automation at a time, and not `run_changes`, which would run every armed
automation the install has and write their runs inside this transaction. It does not assume an empty
database for the same reason and does not turn the switch on: the switch decides whether the
worker's tick asks, and this proves what the pass does when asked.

**What is shown.** Two people hold the read the task needs. One also holds the read of the check's
kind of record in its department; the other does not. A record in that department and a record in
the other reserved department change. The first person's automation runs once, as them, for the
record they may read, a second pass over the same change writes nothing, and the arming is still on
the automation. The second person's automation, listening to the same source, runs nothing, and the
record the first could not read starts nothing for anybody. See
`brain.ops.automation_event.A_CHANGE_OUTSIDE_THE_OWNERS_REACH_STARTS_NOTHING`.

**What is not shown here:** that the install's own worker asks, which is the install having turned
`automation_events` on and its tick running (`ops.control_run` records it), and the bounds, which
`tests/unit/test_automation_event_store.py` holds against a real database.

Task ids: M17.4.1
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1610

A, B = RESERVED_DEPARTMENTS

#: The kind of record the check's source holds, and so the read its reader needs.
ENTITY: Final = "acceptance_ticket"

NO_RUN_WAS_STARTED: Final = "a record its owner may read started no run"
A_RUN_WAS_NOT_THEIRS: Final = "the run was not recorded as the person the automation belongs to"
A_RECORD_STARTED_TWO: Final = "a change started a run more than once, or for a record not theirs"
A_REPEAT_LOOK_RAN: Final = "a second look at a change already run started another"
AN_OUTSIDER_RAN: Final = "a person without the read of the record had a run started for them"
THE_ARMING_MOVED: Final = "a run moved the instant the automation was armed"


@check(
    leaves=("M17.4.1",),
    sentence=(
        "A record changing in a connected source's index starts one run of an automation listening "
        "to that source, as the person it belongs to, when that person may read the record: the "
        "same change found again starts nothing, a record in another department starts nothing, "
        "and a person without the read of that kind of record has no run started for them."
    ),
)
async def a_change_starts_one_run_as_an_owner_who_may_read_it(h: Harness) -> None:
    from sqlalchemy import func, select, update

    from brain.connectors.projection import ProjectedRecord
    from brain.console.automation_authoring import (
        TriggerChoice,
        authoring_of,
        compose,
        preview,
    )
    from brain.console.automation_gallery import (
        AUTOMATION_AUTHORITY,
        new_automation_id,
        template_by_id,
    )
    from brain.console.questions_view import QUESTION_AUTHORITY
    from brain.console.workspace import Tab, tab
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_workspace import (
        _everywhere,
        _planes,
        installed_agent,
        stored_agent,
        worker_sessions,
    )
    from brain.ops.agent_automation_store import StoredAgentAutomations
    from brain.ops.automation_event import Change, event_run_id
    from brain.ops.automation_event_store import run_changes_of
    from brain.ops.automation_run import RunOutcome
    from brain.ops.connector_sync_store import record_upsert
    from brain.orchestration.unattended import TriggerKind
    from brain.tables.agent_automation import AgentAutomationRow
    from brain.tables.automation_run import AutomationRunRow
    from brain.tables.projection import ProjectedRecordRow

    await h.found_departments()
    source = f"acceptance_{secrets.token_hex(6)}"
    reader, outsider = h.principal(A, "reader"), h.principal(A, "outsider")
    tab_read = tab(Tab.AUTOMATIONS).read.requires.value
    authority = (AUTOMATION_AUTHORITY.value, tab_read, QUESTION_AUTHORITY.value, *_planes())
    await h.person(
        reader,
        department=A,
        grants=(*_everywhere(*authority), (f"read:{ENTITY}", Scope.department(A))),
    )
    await h.person(outsider, department=A, grants=_everywhere(*authority))
    agent_id = await installed_agent(
        h,
        reader,
        capabilities=(QUESTION_AUTHORITY.value, f"read:{ENTITY}"),
        connectors=(source,),
        scope=Scope.unrestricted(),
    )
    record = await stored_agent(h, agent_id)
    people = StoredPrincipals(h.sessions)
    template = template_by_id("unanswered_questions")
    if template is None:
        raise CheckFailedError("the template did not read back")

    # Two automations of one kind, listening to the same source, armed an hour ago.
    armed_at = h.now - timedelta(hours=1)
    ids: dict[str, str] = {}
    for person in (reader, outsider):
        principal = await people.live_principal(person)
        if principal is None:
            raise CheckFailedError("a reserved person did not read back")
        authored = compose(
            agent=record,
            name=template.name,
            instruction=template.summary,
            guards=template.guards,
            trigger=TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source=source),
            tools=(),
            condition=None,
            fields={},
            template=template,
        )
        reach = await h.reach(person)
        shown = preview(authored, record, author=principal, author_reach=reach)
        ids[person] = await StoredAgentAutomations(h.sessions).author(
            authoring_of(shown, confirmation=shown.confirmation, automation_id=new_automation_id()),
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
        )
        await h.execute(
            *h.attributed(),
            update(AgentAutomationRow)
            .where(AgentAutomationRow.automation_id == ids[person])
            .values(next_run_at=armed_at),
        )

    # Two records change in the index through the sync's own upsert: one the reader may read, one
    # in the other reserved department that they may not.
    mine, theirs = f"acceptance-{h.word()}", f"acceptance-{h.word()}"
    async with h.sessions() as session, session.begin():
        for source_id, department in ((mine, A), (theirs, B)):
            row = ProjectedRecord(
                source=source,
                entity=ENTITY,
                source_id=source_id,
                last_seen_at=h.now,
                fields={"department": department},
            )
            await session.execute(record_upsert(row, {"department": department}))
    stamped = {
        str(one): at
        for one, at in (
            await h.execute(
                select(ProjectedRecordRow.source_id, ProjectedRecordRow.updated_at).where(
                    ProjectedRecordRow.source == source
                )
            )
        ).all()
    }
    if set(stamped) != {mine, theirs}:
        raise CheckFailedError("the index did not hold the records the check wrote")

    async def pass_over(person: str) -> list[RunOutcome]:
        done = await run_changes_of(
            worker_sessions(h),
            ids[person],
            now=h.now,
            principals=StoredPrincipals(worker_sessions(h)),
            entitlements=StoredEntitlements(worker_sessions(h)),
        )
        return [] if done is None else [one.outcome for one in done]

    first, again, nothing = (
        await pass_over(reader),
        await pass_over(reader),
        await pass_over(outsider),
    )
    if first != [RunOutcome.SUCCEEDED]:
        raise CheckFailedError(NO_RUN_WAS_STARTED if not first else A_RECORD_STARTED_TWO)
    if again:
        raise CheckFailedError(A_REPEAT_LOOK_RAN)
    if nothing:
        raise CheckFailedError(AN_OUTSIDER_RAN)

    runs = (
        await h.execute(
            select(AutomationRunRow.run_id, AutomationRunRow.principal_id).where(
                AutomationRunRow.automation_id.in_(ids.values())
            )
        )
    ).all()
    expected = event_run_id(
        ids[reader],
        Change(source=source, entity=ENTITY, source_id=mine, changed_at=stamped[mine]),
    )
    if len(runs) != 1 or runs[0][0] != expected:
        raise CheckFailedError(A_RECORD_STARTED_TWO)
    if runs[0][1] != reader:
        raise CheckFailedError(A_RUN_WAS_NOT_THEIRS)
    armed = (
        await h.execute(
            select(func.count())
            .select_from(AgentAutomationRow)
            .where(
                AgentAutomationRow.automation_id.in_(ids.values()),
                AgentAutomationRow.next_run_at == armed_at,
            )
        )
    ).scalar_one()
    if armed != len(ids):
        raise CheckFailedError(THE_ARMING_MOVED)
