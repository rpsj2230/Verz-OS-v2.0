"""The install acceptance checks for New automation: what a person wrote is what runs, as them.

`brain.console.automation_authoring` lets a person start from a template and change when it runs and
whether something must be true, or write one in words, rehearse it, and save it paused. A test over
fakes shows the form. What an install shows is the same acts against its own database and its own
worker: a reserved person writes an automation, it is stored and read back as written, said in
words, started by somebody it does not run as and run by the worker as its writer, and a person who
could not read what the task reads is refused at the run.

**What is driven is what the routes call, in the order they call it.** `compose`, `preview`,
`rehearse` and `authoring_of` over the install's reach for the writer, then
`brain.ops.agent_automation_store.StoredAgentAutomations.author`, then the worker's own
`run_one`. The routes themselves are `tests/unit/test_automation_authoring_routes.py`'s, and the
check does not claim them: it proves the half that reaches the database and the worker.

**The field a condition names is one the check supplies.** The form offers the projected fields of
the connectors an agent is bound to, and a check cannot assume which connectors an install has
connected, so it names one field of the shape that matters (a timestamp) and holds the condition
to it. What it proves is that the condition is stored, read back and said in words, not that this
install reports that field.

**What is not proved here is a condition deciding a run.** Nothing yet reads a live record at a
run to decide a condition. The second check proves the three kinds as the owner decided them
(needs-rupash 223, option B): a schedule and a change are written and read back as written, a
webhook is refused when written, and a row a change starts is never claimed by the clock. That a
change actually starts a run is `brain.ops.acceptance_checks_automation_event`'s.

**Nothing leaves the transaction.** Every row is a reserved person's, an agent of acceptance_a named
for the run, and an automation of that agent, all rolled back with the check; nothing is sent.

Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.4, M39.9.2.5, M17.4.1, M17.4.2
"""

from __future__ import annotations

from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1600

A, _ = RESERVED_DEPARTMENTS


# What the checks say, one sentence for each way a property can fail.
NOTHING_WAS_WRITTEN_FOR_THE_PERSON: Final = "writing the automation stored nothing"
A_REHEARSAL_WROTE: Final = "a rehearsal wrote an automation"
IT_DID_NOT_READ_BACK: Final = "the automation read back as something other than what was written"
IT_STARTED_ON: Final = "an automation written by a person was scheduled before anybody started it"
THE_CADENCE_WAS_THE_TEMPLATES: Final = "the automation did not run on the cadence its writer chose"
THE_CARD_SAID_NOTHING: Final = "the card did not say the trigger and the condition in words"
IT_DID_NOT_RUN_AS_ITS_WRITER: Final = "the due automation did not run as the person who wrote it"
A_REACH_WAS_INVENTED: Final = "a person without the read the task needs was not refused at the run"
A_KIND_DID_NOT_READ_BACK: Final = "a trigger did not read back as the kind that was written"
A_KIND_HAD_THE_WRONG_CADENCE: Final = "a trigger carried a cadence its kind does not have"
A_KIND_RAN: Final = "the clock ran an automation that something other than the clock starts"
A_KIND_WAS_STARTABLE: Final = "a webhook was offered a start"
A_WEBHOOK_WAS_WRITTEN: Final = "a webhook was written, though nothing starts work from outside"


def _field() -> object:
    from brain.connectors.manifest import FieldShape
    from brain.console.automation_authoring import ConditionField

    return ConditionField(
        connector="acceptance_source",
        entity="ticket",
        name="due_by",
        shape=FieldShape.TIMESTAMP,
    )


@check(
    leaves=("M39.9.2.1", "M39.9.2.2", "M39.9.2.4", "M39.9.2.5", "M17.4.2"),
    sentence=(
        "A person writes an automation from a template with its cadence changed and a condition, "
        "sees it rehearsed with nothing written, and saves it paused; it reads back as written, a "
        "second person starts it, the worker runs it as its writer, and a person who cannot read "
        "what the task reads is refused."
    ),
)
async def a_person_writes_changes_and_runs_an_automation_as_themselves(
    h: Harness,
) -> None:
    from sqlalchemy import func, select, update

    from brain.automation_schedule_routes import authored_view
    from brain.console.automation_authoring import (
        NOTHING_WAS_WRITTEN_OR_SENT,
        REHEARSED_TRIGGERS,
        Condition,
        ConditionField,
        ConditionOp,
        TriggerChoice,
        authoring_of,
        compose,
        preview,
        rehearse,
    )
    from brain.console.automation_gallery import (
        AUTOMATION_AUTHORITY,
        Cadence,
        Every,
        template_by_id,
    )
    from brain.console.automation_schedule import changed, may_start, shown_start
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
    from brain.ops.automation_run import PausedBecause, RunOutcome, next_run_after
    from brain.ops.automation_run_store import StoredAutomationSchedules, run_one
    from brain.orchestration.unattended import TriggerKind
    from brain.tables.agent_automation import AgentAutomationRow
    from brain.tables.automation_run import STARTED

    await h.found_departments()
    owner, approver, outsider = (
        h.principal(A, "writer"),
        h.principal(A, "approver"),
        h.principal(A, "outsider"),
    )
    tab_read = tab(Tab.AUTOMATIONS).read.requires.value
    authority = (AUTOMATION_AUTHORITY.value, tab_read, *_planes())
    await h.person(owner, department=A, grants=_everywhere(*authority, QUESTION_AUTHORITY.value))
    await h.person(approver, department=A, grants=_everywhere(*authority, QUESTION_AUTHORITY.value))
    # Holds the authority to write and not the read the task needs, which is the case a run exists
    # to refuse.
    await h.person(outsider, department=A, grants=_everywhere(*authority))
    agent_id = await installed_agent(
        h, owner, capabilities=(QUESTION_AUTHORITY.value,), scope=Scope.unrestricted()
    )
    record = await stored_agent(h, agent_id)
    people = StoredPrincipals(h.sessions)
    owner_principal = await people.live_principal(owner)
    outsider_principal = await people.live_principal(outsider)
    template = template_by_id("unanswered_questions")
    if owner_principal is None or outsider_principal is None or template is None:
        raise CheckFailedError("a reserved person or the template did not read back")

    # The cadence is not the template's, and there is a condition on a timestamp.
    chosen = Cadence(every=Every.DAY, hour_utc=(template.cadence.hour_utc + 3) % 24)
    field = _field()
    assert isinstance(field, ConditionField)
    fields = {field.key: field}
    condition = Condition(field=field.key, op=ConditionOp.IS_OVER, value="7")

    authored = compose(
        agent=record,
        name=template.name,
        instruction=template.summary,
        guards=template.guards,
        trigger=TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=chosen),
        tools=(),
        condition=condition,
        fields=fields,
        template=template,
    )
    owner_reach = await h.reach(owner)
    shown = preview(authored, record, author=owner_principal, author_reach=owner_reach)

    # The rehearsal: the last triggers, writing nothing.
    lines = rehearse(authored, reach_words=shown.capabilities, now=h.now, fields=fields)
    if len(lines) != REHEARSED_TRIGGERS or any(
        not one.says.endswith(NOTHING_WAS_WRITTEN_OR_SENT) for one in lines
    ):
        raise CheckFailedError("the rehearsal did not show the last triggers writing nothing")
    stored = (
        await h.execute(
            select(func.count())
            .select_from(AgentAutomationRow)
            .where(AgentAutomationRow.agent_id == agent_id)
        )
    ).scalar_one()
    if stored != 0:
        raise CheckFailedError(A_REHEARSAL_WROTE)

    # Saved paused, as its writer, in one confirmed step.
    from brain.console.automation_gallery import new_automation_id

    written = authoring_of(
        shown, confirmation=shown.confirmation, automation_id=new_automation_id()
    )
    automation_id = await StoredAgentAutomations(h.sessions).author(
        written, ent_hash=owner_reach.ent_hash(), trace_id=h.trace_id
    )
    schedules = StoredAutomationSchedules(h.sessions)
    listed = await schedules.listed(agent_id)
    if [one.automation.automation_id for one in listed] != [automation_id]:
        raise CheckFailedError(NOTHING_WAS_WRITTEN_FOR_THE_PERSON)
    [held] = listed
    if held.authored != authored:
        raise CheckFailedError(IT_DID_NOT_READ_BACK)
    if not held.automation.paused or held.automation.runs_as.id != owner:
        raise CheckFailedError(IT_STARTED_ON)
    if held.cadence != chosen or held.cadence == template.cadence:
        raise CheckFailedError(THE_CADENCE_WAS_THE_TEMPLATES)
    card = authored_view(held.authored or authored)
    if (
        card.condition is None
        or "more than 7 days ago" not in card.condition
        or chosen.words() not in card.trigger
        or not card.fires
    ):
        raise CheckFailedError(THE_CARD_SAID_NOTHING)

    # A second person starts it, and the worker runs it as its writer on the chosen cadence.
    start = shown_start(held.automation, chosen, now=h.now)
    becomes = start.becomes
    approver_reach = await h.reach(approver)
    if becomes is None or may_start(
        held.automation, owner_reach, agent=record, becomes=becomes, now=h.now
    ):
        raise CheckFailedError("its writer could start it without a second person")
    if not may_start(held.automation, approver_reach, agent=record, becomes=becomes, now=h.now):
        raise CheckFailedError("a second person could not start the automation")
    await schedules.change(
        changed(start, confirmation=start.confirmation, guards=held.guards),
        reason=STARTED,
        actor=approver,
        ent_hash=approver_reach.ent_hash(),
        trace_id=h.trace_id,
        at=h.now,
    )
    # Held to the writer's reach: the same words by somebody who cannot read what the task reads.
    outsider_reach = await h.reach(outsider)
    refused_shown = preview(
        authored, record, author=outsider_principal, author_reach=outsider_reach
    )
    refused_id = await StoredAgentAutomations(h.sessions).author(
        authoring_of(
            refused_shown,
            confirmation=refused_shown.confirmation,
            automation_id=new_automation_id(),
        ),
        ent_hash=outsider_reach.ent_hash(),
        trace_id=h.trace_id,
    )
    await h.execute(
        *h.attributed(approver),
        update(AgentAutomationRow)
        .where(AgentAutomationRow.automation_id == automation_id)
        .values(next_run_at=h.now),
    )
    await h.execute(
        *h.attributed(approver),
        update(AgentAutomationRow)
        .where(AgentAutomationRow.automation_id == refused_id)
        .values(next_run_at=h.now),
    )
    # The worker's two steps, each reading the person and their reach through its own sessions: a
    # step that read them through the application's would write its run as that role, which may not.
    ran = await run_one(
        worker_sessions(h),
        automation_id,
        now=h.now,
        principals=StoredPrincipals(worker_sessions(h)),
        entitlements=StoredEntitlements(worker_sessions(h)),
    )
    refused = await run_one(
        worker_sessions(h),
        refused_id,
        now=h.now,
        principals=StoredPrincipals(worker_sessions(h)),
        entitlements=StoredEntitlements(worker_sessions(h)),
    )
    if ran is None or ran.outcome is not RunOutcome.SUCCEEDED:
        raise CheckFailedError(IT_DID_NOT_RUN_AS_ITS_WRITER)
    both = {one.automation.automation_id: one for one in await schedules.listed(agent_id)}
    after = both[automation_id]
    last = after.runs[0] if after.runs else None
    if last is None or last.principal_id != owner or last.ent_hash is None:
        raise CheckFailedError(IT_DID_NOT_RUN_AS_ITS_WRITER)
    if after.automation.next_run_at != next_run_after(chosen, h.now):
        raise CheckFailedError(THE_CADENCE_WAS_THE_TEMPLATES)

    if refused is None or refused.outcome is not RunOutcome.REFUSED or not refused.paused:
        raise CheckFailedError(A_REACH_WAS_INVENTED)
    stopped = both[refused_id]
    if stopped.stopped_because != PausedBecause.OWNER_LOST_REACH.value:
        raise CheckFailedError(A_REACH_WAS_INVENTED)


@check(
    leaves=("M17.4.1", "M39.9.2.2"),
    sentence=(
        "A schedule and a connector change can each be written and read back as the kind written, "
        "with the schedule alone carrying a cadence; a webhook is refused when it is written, and "
        "an automation a change starts is never claimed by the clock, however due its row looks."
    ),
)
async def each_kind_of_trigger_is_saved_and_a_webhook_is_refused(h: Harness) -> None:
    from sqlalchemy import update

    from brain.console.automation_authoring import (
        NOTHING_FIRES_THIS_YET,
        Authored,
        AuthoringRefusedError,
        TriggerChoice,
        authoring_of,
        compose,
        preview,
    )
    from brain.console.automation_gallery import (
        AUTOMATION_AUTHORITY,
        Cadence,
        Every,
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
    from brain.ops.automation_event import WEBHOOKS_ARE_NOT_OFFERED
    from brain.ops.automation_run_store import StoredAutomationSchedules, run_one
    from brain.orchestration.unattended import TriggerKind
    from brain.tables.agent_automation import AgentAutomationRow

    await h.found_departments()
    owner = h.principal(A, "writer")
    source = "acceptance_source"
    tab_read = tab(Tab.AUTOMATIONS).read.requires.value
    await h.person(
        owner,
        department=A,
        grants=_everywhere(
            AUTOMATION_AUTHORITY.value, tab_read, QUESTION_AUTHORITY.value, *_planes()
        ),
    )
    agent_id = await installed_agent(
        h,
        owner,
        capabilities=(QUESTION_AUTHORITY.value,),
        connectors=(source,),
        scope=Scope.unrestricted(),
    )
    record = await stored_agent(h, agent_id)
    people = StoredPrincipals(h.sessions)
    principal = await people.live_principal(owner)
    template = template_by_id("unanswered_questions")
    if principal is None or template is None:
        raise CheckFailedError("a reserved person or the template did not read back")
    reach = await h.reach(owner)

    written = {
        TriggerKind.SCHEDULE: TriggerChoice(
            kind=TriggerKind.SCHEDULE, cadence=Cadence(every=Every.DAY, hour_utc=4)
        ),
        TriggerKind.CONNECTOR_EVENT: TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source=source),
    }
    webhook = TriggerChoice(kind=TriggerKind.WEBHOOK, source="acceptance_hook")
    ids: dict[TriggerKind, str] = {}
    store = StoredAgentAutomations(h.sessions)
    for kind, trigger in written.items():
        authored = compose(
            agent=record,
            name=template.name,
            instruction=template.summary,
            guards=template.guards,
            trigger=trigger,
            tools=(),
            condition=None,
            fields={},
            template=template,
        )
        shown = preview(authored, record, author=principal, author_reach=reach)
        ids[kind] = await store.author(
            authoring_of(shown, confirmation=shown.confirmation, automation_id=new_automation_id()),
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
        )

    # A webhook is refused when it is written: the owner decided nothing starts work from outside.
    try:
        compose(
            agent=record,
            name=template.name,
            instruction=template.summary,
            guards=template.guards,
            trigger=webhook,
            tools=(),
            condition=None,
            fields={},
            template=template,
        )
    except AuthoringRefusedError as refused:
        if WEBHOOKS_ARE_NOT_OFFERED not in refused.findings:
            raise CheckFailedError(A_WEBHOOK_WAS_WRITTEN) from refused
    else:
        raise CheckFailedError(A_WEBHOOK_WAS_WRITTEN)

    # One stored before it was refused still reads back, says it cannot be started, and is never
    # claimed by the clock. Written as the row the earlier release wrote, past `compose`.
    legacy = Authored(
        name=template.name,
        instruction=template.summary,
        guards=template.guards,
        trigger=webhook,
        tools=(),
        template_id=template.template_id,
        task=template.task,
    )
    legacy_shown = preview(legacy, record, author=principal, author_reach=reach)
    ids[TriggerKind.WEBHOOK] = await store.author(
        authoring_of(
            legacy_shown, confirmation=legacy_shown.confirmation, automation_id=new_automation_id()
        ),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    )

    schedules = StoredAutomationSchedules(h.sessions)
    held = {one.automation.automation_id: one for one in await schedules.listed(agent_id)}
    every = {**written, TriggerKind.WEBHOOK: webhook}
    for kind, trigger in every.items():
        one = held.get(ids[kind])
        if one is None or one.authored is None or one.authored.trigger != trigger:
            raise CheckFailedError(A_KIND_DID_NOT_READ_BACK)
        if (one.cadence is None) != (kind is not TriggerKind.SCHEDULE):
            raise CheckFailedError(A_KIND_HAD_THE_WRONG_CADENCE)
        if one.authored.trigger.fires is (kind is TriggerKind.WEBHOOK):
            raise CheckFailedError(A_KIND_WAS_STARTABLE)
    if "cannot be started" not in NOTHING_FIRES_THIS_YET:
        raise CheckFailedError(A_KIND_WAS_STARTABLE)

    # Due by force, and offered to the worker's clock: neither is claimed, so neither is run, and
    # neither is paused by a refusal it was never asked to make.
    quiet = (TriggerKind.CONNECTOR_EVENT, TriggerKind.WEBHOOK)
    for kind in quiet:
        await h.execute(
            *h.attributed(),
            update(AgentAutomationRow)
            .where(AgentAutomationRow.automation_id == ids[kind])
            .values(next_run_at=h.now),
        )
    for kind in quiet:
        claimed = await run_one(
            worker_sessions(h),
            ids[kind],
            now=h.now,
            principals=StoredPrincipals(worker_sessions(h)),
            entitlements=StoredEntitlements(worker_sessions(h)),
        )
        if claimed is not None:
            raise CheckFailedError(A_KIND_RAN)
    after = {one.automation.automation_id: one for one in await schedules.listed(agent_id)}
    for kind in quiet:
        if after[ids[kind]].runs or after[ids[kind]].automation.next_run_at != h.now:
            raise CheckFailedError(A_KIND_RAN)
