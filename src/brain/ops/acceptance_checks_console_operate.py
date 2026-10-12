"""Install acceptance checks for the Operate screens: the Stop control, what is running and waiting.

Each check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`), over
the check's own transaction. **Nothing here is committed**, so the install is never stopped, and
no run the check puts on a screen outlives it.

**The Stop control is asked of the menu, because that is where the header reads it.** The header of
every page draws its Stop control from `GET /console/navigation`, whose `stop` field the server
decides, so the check reads the field the browser reads and not a function beside it. See
`THE_STOP_CONTROL_IS_READ_FROM_THE_MENU_THE_HEADER_READS`.

Task ids: M27.15.14, M27.12.4, M27.2.8, M27.2.6, M27.12.3, M27.15.37
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
    traced,
)
from brain.ops.acceptance_operations_console_2 import a_job, as_login
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 900

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the check reads the header's control from the menu.
THE_STOP_CONTROL_IS_READ_FROM_THE_MENU_THE_HEADER_READS: Final = (
    "The header of every console page draws its Stop control from the menu answer's stop field, "
    "which the server decides from the reader's halt grant. The check asks that answer as three "
    "readers and holds the field to what each may stop, so a control drawn for a person who may "
    "not stop anything, or withheld from one who may, fails here and not in a browser."
)

#: Why a halt is shown to have survived by reading the table afresh.
A_HALT_IS_THE_TABLES_AND_NEVER_THE_PROCESS_S: Final = (
    "A halt that survives a restart is one the table holds and no process does. The check reads "
    "the halts in force through a new session each time and holds the row itself, so a halt kept "
    "in a variable of the process that stopped it would show on the page that stopped it and "
    "not on the read made afterwards."
)

#: Said when this install lists more automations than one page holds.
MORE_AUTOMATIONS_THAN_ONE_PAGE: Final = (
    "this install lists more automations than one page of the screen holds, so the one the "
    "check made may not be on the page it reads"
)

# ------------------------------------------------------------------------ the figures
#: What the menu answer's stop field says, restated so a renamed word fails the check.
STOPS_EVERYTHING: Final = "everything"
STOPS_ITS_DEPARTMENTS: Final = "departments"


# ------------------------------------------------------- 1. the Stop control (M27.15.14)
@check(
    leaves=("M27.15.14", "M27.12.4", "M27.2.8"),
    sentence=(
        "The Stop control is drawn in the header for a reader holding the halt capability and "
        "for nobody else, and says whether one press stops everything or only the reader's "
        "departments; a stop made from the console is listed on the Stop screen as what is "
        "stopped now, refuses a member's work, and is held by the table, so a read through a "
        "new session finds it as a restarted application would."
    ),
)
async def the_stop_control_is_drawn_for_its_holders_and_a_stop_is_kept(
    h: Harness,
) -> None:
    from brain.console.reads import Plane, plane_capability
    from brain.halt_routes import HALT_SCREEN, StopAsked, halts, stop_now
    from brain.navigation_routes import console_navigation
    from brain.ops.acceptance_checks import _in
    from brain.ops.halt import HALT_CAPABILITY, HaltScope
    from brain.ops.halt_store import Work, read_state, refusal_in

    await h.found_departments()
    holding = (HALT_CAPABILITY.value, plane_capability(Plane.CONFIGURATION).value)
    whole, scoped, member, other = (
        h.principal(A, "stopper"),
        h.principal(A, "dept-stopper"),
        h.principal(A, "member"),
        h.principal(A, "other"),
    )
    await h.person(
        whole, department=A, grants=tuple((one, Scope.unrestricted()) for one in holding)
    )
    await h.person(scoped, department=A, grants=_in(A, *holding))
    await h.person(member, department=A)
    await h.person(other, department=A)

    offered = {
        who: (await console_navigation(await asking_as(h, who, strong=True))).stop
        for who in (whole, scoped, other)
    }
    if offered[whole] != STOPS_EVERYTHING:
        raise CheckFailedError("the header did not offer a stop of everything to its holder")
    if offered[scoped] != STOPS_ITS_DEPARTMENTS:
        raise CheckFailedError("the header did not offer a department's holder a department stop")
    if offered[other]:
        raise CheckFailedError("the header offered a Stop control to a person who may stop nothing")
    del HALT_SCREEN

    console = console_for(h)
    before = await halts(console.request(), await asking_as(h, whole, strong=True))
    if not before.known:
        raise CheckFailedError("the Stop screen could not say what was stopped")
    target = f"{h.word().lower()}_operator"
    stopped = await stop_now(
        console.request("POST"),
        await asking_as(h, whole, strong=True),
        StopAsked(scope=HaltScope.AGENT, target=target),
    )
    if getattr(stopped, "target", None) != target:
        raise CheckFailedError("a stop made from the console was not stored as asked")

    listed = await halts(console.request(), await asking_as(h, whole, strong=True))
    if (HaltScope.AGENT, target) not in [(one.scope, one.target) for one in listed.halts]:
        raise CheckFailedError("the Stop screen did not list what had just been stopped")

    kept = (
        await h.execute(
            text(
                "SELECT count(*) FROM ops.halt WHERE scope = :scope AND target = :target"
            ).bindparams(scope=HaltScope.AGENT.value, target=target)
        )
    ).scalar_one()
    if int(kept) != 1:
        raise CheckFailedError("a stop made from the console was not a row of the halt table")
    # A new read each time: the state is the table's, as it is for an application that restarts.
    refused = refusal_in(await read_state(h.sessions), Work(person=member, agent=target))
    admitted = refusal_in(await read_state(h.sessions), Work(person=member, agent=f"{target}_x"))
    if not refused or admitted:
        raise CheckFailedError("a stop held by the table did not refuse exactly what it named")


# ------------------------------------------------ 2. what is running and what waits (M27.2.6)
@check(
    leaves=("M27.2.6",),
    sentence=(
        "Live runs lists a scheduled job the worker has started and not finished as running, "
        "and a job owed a run and not started as waiting, each behind its own screen's grant: "
        "a reader of running work is not shown the queue, a reader of the queue is not shown "
        "running work, and a person with neither is shown two empty lists."
    ),
)
async def running_and_waiting_work_is_listed_by_state_to_its_readers(h: Harness) -> None:
    from brain.console.operate import unattended_waiting
    from brain.operate_routes import live_runs
    from brain.ops.schedule import Owed
    from brain.tables.schedule import ControlRunRow

    await h.found_departments()
    runner, waiter, both, nobody = (
        h.principal(A, "runs-only"),
        h.principal(A, "queue-only"),
        h.principal(A, "both"),
        h.principal(A, "nobody"),
    )
    await h.person(runner, department=A, grants=screen_grants("runs"))
    await h.person(waiter, department=A, grants=screen_grants("queue"))
    await h.person(
        both,
        department=A,
        grants=tuple(dict.fromkeys((*screen_grants("runs"), *screen_grants("queue")))),
    )
    await h.person(nobody, department=A)
    job = a_job()
    await as_login(h, insert(ControlRunRow).values(name=job.name, started_at=datetime.now(UTC)))

    console = console_for(h)

    async def seen(person: str) -> tuple[list[str], list[str]]:
        found = await live_runs(console.request(), await asking_as(h, person))
        return [one.control for one in found.running], [one.control for one in found.waiting]

    running_to_both, waiting_to_both = await seen(both)
    if job.name not in running_to_both:
        raise CheckFailedError("Live runs did not list a job started and not finished as running")
    if job.name in waiting_to_both:
        raise CheckFailedError("a job already running was also listed as waiting")
    running_only, waiting_in_runs = await seen(runner)
    if job.name not in running_only or waiting_in_runs:
        raise CheckFailedError("a reader of running work was shown the queue, or not the run")
    running_in_queue, waiting_only = await seen(waiter)
    if running_in_queue or waiting_only != waiting_to_both:
        raise CheckFailedError("a reader of the queue was shown running work, or not the queue")
    if any(await seen(nobody)):
        raise CheckFailedError("Live runs showed work to a person with neither screen")

    # Whether anything is owed a run now is the install's own state, so what is owed is made up:
    # a control that has never run, shown through the same decision the route asks.
    owed = Owed(
        name=job.name, due_since=h.now, late_by=timedelta(), first_run=True, report_only=False
    )
    shown = {
        who: [one.control for one in unattended_waiting([owed], await h.reach(who), h.now)]
        for who in (runner, waiter, both, nobody)
    }
    if shown != {runner: [], waiter: [job.name], both: [job.name], nobody: []}:
        raise CheckFailedError("a control owed a run was not listed to its screen's readers alone")


# ------------------------------------------------- 3. an installed automation (M27.12.3, M27.15.37)
async def an_installed_automation(h: Harness) -> tuple[str, str, str, str]:
    """An agent of acceptance_a with an automation installed paused from the gallery, and its two
    people: the owner it runs as and a second administrator. Returns agent, automation, owner and
    approver."""
    from brain.console.automation_gallery import (
        AUTOMATION_AUTHORITY,
        install,
        new_automation_id,
        preview,
        template_by_id,
    )
    from brain.console.questions_view import QUESTION_AUTHORITY
    from brain.console.workspace import Tab, tab
    from brain.ops.acceptance_workspace import _everywhere, _planes, installed_agent, stored_agent
    from brain.ops.agent_automation_store import StoredAgentAutomations

    await h.found_departments()
    owner, approver = h.principal(A, "owner"), h.principal(A, "approver")
    tab_read = tab(Tab.AUTOMATIONS).read.requires.value
    for one in (owner, approver):
        await h.person(
            one,
            department=A,
            grants=_everywhere(
                AUTOMATION_AUTHORITY.value, tab_read, QUESTION_AUTHORITY.value, *_planes()
            ),
        )
    agent_id = await installed_agent(
        h, owner, capabilities=(QUESTION_AUTHORITY.value,), scope=Scope.unrestricted()
    )
    record = await stored_agent(h, agent_id)
    template = template_by_id("unanswered_questions")
    from brain.identity.principal_store import StoredPrincipals

    owner_principal = await StoredPrincipals(h.sessions).live_principal(owner)
    if owner_principal is None or template is None:
        raise CheckFailedError("the check's owner or the gallery's template did not read back")
    owner_reach = await h.reach(owner)
    shown = preview(template, record, installer=owner_principal, installer_reach=owner_reach)
    installation = install(
        shown, confirmation=shown.confirmation, automation_id=new_automation_id()
    )
    done = await StoredAgentAutomations(h.sessions).install(
        installation, ent_hash=owner_reach.ent_hash(), trace_id=h.trace_id
    )
    if not done.created:
        raise CheckFailedError("installing an automation from the gallery wrote nothing")
    return agent_id, done.automation_id, owner, approver


@check(
    leaves=("M27.12.3",),
    sentence=(
        "An automation installed from the gallery is listed on the Automations screen to a "
        "reader who may see it and to nobody else; a second administrator starts it and "
        "changes when it runs, its owner pauses it, and each change names what was shown and "
        "is refused when what was shown has moved; it is then removed, and its history says "
        "each of these, newest first."
    ),
)
async def an_automation_is_started_changed_paused_and_removed(
    h: Harness,
) -> None:
    from brain.automation_schedule_routes import ChangeAsked
    from brain.automations_routes import (
        RescheduleAsked,
        automation,
        automations,
        pause_automation,
        remove_automation,
        reschedule_automation,
        resume_automation,
    )
    from brain.console.automation_gallery import Every
    from brain.listing import ListAsked

    _, automation_id, owner, approver = await an_installed_automation(h)
    stranger = h.principal(A, "stranger")
    await h.person(stranger, department=A)
    console = console_for(h)

    async def detail(person: str) -> Any:
        return await automation(
            console.request(), automation_id, await asking_as(h, person, strong=True)
        )

    listed = await automations(
        console.request(), await asking_as(h, approver, strong=True), ListAsked(limit=200)
    )
    if automation_id not in [one.automation_id for one in listed.items]:
        if listed.next_cursor is not None:
            raise CheckNotRunError(MORE_AUTOMATIONS_THAN_ONE_PAGE)
        raise CheckFailedError("the Automations screen did not list an automation to its reader")
    if await refused(automation(console.request(), automation_id, await asking_as(h, stranger))):
        pass
    else:
        raise CheckFailedError("the Automations screen showed an automation to a stranger")

    first_owner, first = await detail(owner), await detail(approver)
    if first_owner.may_resume or not first.may_resume or first.may_pause:
        raise CheckFailedError("the screen did not offer a start to a second person alone")
    async with traced(h, 1):
        started = await resume_automation(
            console.request("POST"),
            automation_id,
            ChangeAsked(confirmation=first.confirmation),
            await asking_as(h, approver, strong=True),
        )
    if started.status_code != 200:
        raise CheckFailedError("a second administrator could not start the automation")
    running = await detail(approver)
    if running.automation.state.value == first.automation.state.value or not running.may_pause:
        raise CheckFailedError("a started automation was not shown as running")
    stale = await pause_automation(
        console.request("POST"),
        automation_id,
        ChangeAsked(confirmation=first.confirmation),
        await asking_as(h, approver, strong=True),
    )
    if stale.status_code != 409:
        raise CheckFailedError("a change made over what had since moved was not refused")

    async with traced(h, 2):
        moved = await reschedule_automation(
            console.request("POST"),
            automation_id,
            RescheduleAsked(confirmation=running.confirmation, every=Every.DAY, hour_utc=5),
            await asking_as(h, approver, strong=True),
        )
    if moved.status_code != 200 or (await detail(approver)).cadence is None:
        raise CheckFailedError("a second administrator could not change when it runs")
    async with traced(h, 3):
        paused = await pause_automation(
            console.request("POST"),
            automation_id,
            ChangeAsked(confirmation=(await detail(owner)).confirmation),
            await asking_as(h, owner, strong=True),
        )
    if paused.status_code != 200 or not (await detail(approver)).may_resume:
        raise CheckFailedError("an automation's owner could not pause it")
    async with traced(h, 4):
        removed = await remove_automation(
            console.request("POST"),
            automation_id,
            ChangeAsked(confirmation=(await detail(owner)).confirmation),
            await asking_as(h, owner, strong=True),
        )
    after = await detail(approver)
    if removed.status_code != 200 or after.may_resume or after.may_pause or after.may_remove:
        raise CheckFailedError("a removed automation was still offered a change")
    if len(after.history) < 4:
        raise CheckFailedError("the automation's history did not say each change made to it")


@check(
    leaves=("M27.15.37",),
    sentence=(
        "An automation whose owner has left is shown as ownerless and offered for adoption to an "
        "administrator who holds the authority over it and to nobody else; adopting it, over "
        "what was shown, makes the administrator the person it runs as, leaves it paused, and "
        "is in its history."
    ),
)
async def an_ownerless_automation_is_adopted_and_runs_as_the_adopter(h: Harness) -> None:
    from datetime import timedelta

    from sqlalchemy import update

    from brain.automation_schedule_routes import ChangeAsked
    from brain.automations_routes import adopt_automation, automation
    from brain.tables.identity import PrincipalRow

    _, automation_id, owner, approver = await an_installed_automation(h)
    stranger = h.principal(A, "stranger")
    await h.person(stranger, department=A)
    console = console_for(h)

    async def detail(person: str) -> Any:
        return await automation(
            console.request(), automation_id, await asking_as(h, person, strong=True)
        )

    if (await detail(approver)).may_adopt:
        raise CheckFailedError("an automation with its owner here was offered for adoption")
    await h.execute(
        *h.attributed(),
        update(PrincipalRow)
        .where(PrincipalRow.id == owner)
        .values(not_after=h.now - timedelta(days=1)),
    )
    shown = await detail(approver)
    if not shown.may_adopt or shown.owner_id != owner:
        raise CheckFailedError("an automation whose owner had left was not offered for adoption")
    if await refused(automation(console.request(), automation_id, await asking_as(h, stranger))):
        pass
    else:
        raise CheckFailedError("an ownerless automation was shown to a stranger")
    async with traced(h, 1):
        adopted = await adopt_automation(
            console.request("POST"),
            automation_id,
            ChangeAsked(confirmation=shown.confirmation),
            await asking_as(h, approver, strong=True),
        )
    after = await detail(approver)
    if adopted.status_code != 200 or after.owner_id != approver or after.may_adopt:
        raise CheckFailedError(
            "adopting an ownerless automation did not make the adopter its owner"
        )
    if after.automation.next_run_at is not None:
        raise CheckFailedError("an adopted automation was running before anybody started it")
    if len(after.history) <= len(shown.history):
        raise CheckFailedError("the adoption was not in the automation's history")
