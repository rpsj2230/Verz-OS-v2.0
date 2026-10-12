"""Install acceptance checks for the lists the console draws from one object's own routes: an
agent's recent runs, and the automations a person owns.

Each check calls the route the page calls, as the reader that page serves, over the check's own
transaction. **Every row the checks write is the check's own** (an agent, requests and spend rows
for reserved people of acceptance_a), so nothing the install holds is changed and nothing is left.

Task ids: M27.15.27, M27.15.18, M27.7.17, M27.15.17, M27.15.4
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1370

A, B = RESERVED_DEPARTMENTS


# ------------------------------------------------------------ 1. recent runs (M27.15.27)
@check(
    leaves=("M27.15.27",),
    sentence=(
        "Three requests chose an agent of acceptance_a, one of them an automation's: a reader of "
        "everybody's usage is listed all three newest first, each with who asked, how it ended "
        "and how long it took, a member is listed their own alone, and a person outside the "
        "agent's audience is refused."
    ),
)
async def an_agents_recent_runs_are_the_ones_its_reader_is_counted_over(h: Harness) -> None:
    from brain.console_stats_routes import agent_stats
    from brain.gate.context import TrafficClass
    from brain.ops.acceptance_agent_console import _asking, _console, _request
    from brain.ops.acceptance_operations_console import refused
    from brain.ops.acceptance_workspace import (
        _everywhere,
        _planes,
        installed_agent,
    )
    from brain.ops.acceptance_workspace import (
        _request as made,
    )
    from brain.tables.telemetry import RequestTelemetryRow

    await h.found_departments()
    heavy, light, reader, outsider = (
        h.principal(A, "heavy"),
        h.principal(A, "light"),
        h.principal(A, "reader"),
        h.principal(B, "outsider"),
    )
    for one in (heavy, light, outsider):
        await h.person(one, department=A if one != outsider else B)
    await h.person(
        reader, department=A, grants=_everywhere("read:budget", "read:usage", *_planes())
    )
    agent_id = await installed_agent(h, heavy)
    person, scheduled = TrafficClass.HUMAN_INTERACTIVE.value, TrafficClass.AUTOMATION.value
    requests = [
        (heavy, h.now - timedelta(hours=1), person),
        (light, h.now - timedelta(hours=2), person),
        (heavy, h.now - timedelta(hours=3), scheduled),
    ]
    async with h.sessions() as session:
        await session.execute(
            insert(RequestTelemetryRow),
            [
                made(agent_id, who, at, traffic, f"{h.trace_id}-r{n}")
                for n, (who, at, traffic) in enumerate(requests)
            ],
        )
        await session.commit()
    app = _console(h)

    everyones = await agent_stats(_request(app), agent_id, await _asking(h, reader))
    if [(one.principal_id, one.by_a_person) for one in everyones.recent] != [
        (heavy, True),
        (light, True),
        (heavy, False),
    ]:
        raise CheckFailedError(
            "the list was not every run the reader is counted over, newest first"
        )
    if any(not one.status or one.duration_ms <= 0 for one in everyones.recent):
        raise CheckFailedError("a listed run did not say how it ended and how long it took")
    if {one.principal_id: one.name for one in everyones.recent}.get(heavy) is None:
        raise CheckFailedError("a listed run did not name who asked")

    own = await agent_stats(_request(app), agent_id, await _asking(h, light))
    if [one.principal_id for one in own.recent] != [light]:
        raise CheckFailedError("a member was listed a run somebody else made")
    if not await refused(agent_stats(_request(app), agent_id, await _asking(h, outsider))):
        raise CheckFailedError("a person outside the agent's audience was listed its runs")


# ------------------------------------ 2. what a person owns, on their own page (M27.15.18)
@check(
    leaves=("M27.15.18",),
    sentence=(
        "A person's page asks for the agents and the automations they own and the ledger entries "
        "about them: a reader who may open them is told each, a reader whose audience does not "
        "cover the agent is answered as for a person who owns nothing, and a reader without "
        "the Activity screen is refused the entries."
    ),
)
async def a_persons_page_lists_what_they_own_and_what_the_ledger_says(
    h: Harness,
) -> None:
    from brain.agent_routes import agents
    from brain.audit_routes import audit_page
    from brain.automations_routes import automations
    from brain.console.automation_gallery import (
        AUTOMATION_AUTHORITY,
        install,
        new_automation_id,
        preview,
        template_by_id,
    )
    from brain.console.questions_view import QUESTION_AUTHORITY
    from brain.console.workspace import Tab, tab
    from brain.identity.principal_store import StoredPrincipals
    from brain.listing import ListAsked
    from brain.ops.acceptance_agent_console import _asking, _console, _request
    from brain.ops.acceptance_checks_company_views import _audit_over
    from brain.ops.acceptance_checks_governance import GRANT_DECISION, GRANTED
    from brain.ops.acceptance_checks_governance import _asking as governed
    from brain.ops.acceptance_operations_console import refused, traced
    from brain.ops.acceptance_workspace import (
        _everywhere,
        _planes,
        installed_agent,
        stored_agent,
    )
    from brain.ops.agent_automation_store import StoredAgentAutomations
    from brain.principal_state_routes import StateAsked, disable_person

    await h.found_departments()
    owner, reader, auditor, outsider, admin = (
        h.principal(A, "owner"),
        h.principal(A, "reader"),
        h.principal(A, "auditor"),
        h.principal(B, "outsider"),
        h.principal(A, "admin"),
    )
    tab_read = tab(Tab.AUTOMATIONS).read.requires.value
    held = _everywhere(AUTOMATION_AUTHORITY.value, tab_read, QUESTION_AUTHORITY.value, *_planes())
    for one in (owner, reader):
        await h.person(one, department=A, grants=held)
    await h.person(outsider, department=B, grants=held)
    await h.person(auditor, department=A, grants=_audit_over(Scope.unrestricted()))
    await h.person(
        admin,
        department=A,
        grants=((GRANT_DECISION, Scope.unrestricted()), (GRANTED, Scope.unrestricted())),
    )
    agent_id = await installed_agent(
        h, owner, capabilities=(QUESTION_AUTHORITY.value,), scope=Scope.unrestricted()
    )
    people = StoredPrincipals(h.sessions)
    person = await people.live_principal(owner)
    template = template_by_id("unanswered_questions")
    if person is None or template is None:
        raise CheckFailedError("the check's owner or the gallery's template did not read back")
    reach = await h.reach(owner)
    shown = preview(
        template, await stored_agent(h, agent_id), installer=person, installer_reach=reach
    )
    made = await StoredAgentAutomations(h.sessions).install(
        install(shown, confirmation=shown.confirmation, automation_id=new_automation_id()),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    )
    if not made.created:
        raise CheckFailedError("an automation the check owns could not be installed")

    app = _console(h)
    mine = ListAsked(filters=(f"owner_id:{owner}",), limit=50)

    async def owned_agents(who: str) -> list[str]:
        page = await agents(_request(app), await _asking(h, who), mine)
        return [one.agent_id for one in page.items]

    async def owned_automations(who: str) -> list[str]:
        page = await automations(_request(app), await _asking(h, who), mine)
        return [one.automation_id for one in page.items]

    if agent_id not in await owned_agents(reader):
        raise CheckFailedError("a reader was not told which agents a person owns")
    if await owned_automations(reader) != [made.automation_id]:
        raise CheckFailedError("a reader was not told which automations a person owns")
    for hidden in (owned_agents, owned_automations):
        if await hidden(outsider):
            raise CheckFailedError("a reader whose audience does not cover them was told of them")

    # The ledger's entries about the person: one is written by disabling them, as an
    # administrator who holds the grant decision does it.
    async with traced(h, 11):
        done = await disable_person(
            _request(app), StateAsked(principal_id=owner), await governed(h, admin)
        )
    if done.status_code != 200:
        raise CheckFailedError("the check could not write an entry about the person")
    entries = await audit_page(
        _request(app), await _asking(h, auditor), subject_kind="principal", subject_id=owner
    )
    if not any(one.subject_id == owner for one in entries.items):
        raise CheckFailedError("an auditor was not told what the ledger says of the person")
    if not await refused(
        audit_page(
            _request(app), await _asking(h, reader), subject_kind="principal", subject_id=owner
        )
    ):
        raise CheckFailedError("a reader without the Activity screen was told what the ledger says")


# ----------------------------------------------- 3. who has stopped asking (M27.7.17)
@check(
    leaves=("M27.7.17",),
    sentence=(
        "Of three people of acceptance_a who asked before the window, one asks again in it and "
        "one does not, and a new one starts: Adoption's line for acceptance_a counts one as "
        "stopped, a reader of usage in acceptance_b is shown no line of acceptance_a's, and a "
        "department nobody stopped in has a line saying none."
    ),
)
async def adoption_counts_who_stopped_asking_in_the_readers_departments(
    h: Harness,
) -> None:
    from datetime import UTC, datetime

    from brain.adoption import Asked
    from brain.core.principal import PrincipalKind
    from brain.gate.context import Channel
    from brain.listing import ListAsked
    from brain.ops.acceptance_operations_console import asking_as, console_for
    from brain.ops.question_store import record
    from brain.report_routes import adoption

    await h.found_departments()
    stopper, stayer, newcomer = (h.principal(A, one) for one in ("stopper", "stayer", "newcomer"))
    here, there = h.principal(A, "usage"), h.principal(B, "usage")
    for one in (stopper, stayer, newcomer):
        await h.person(one, department=A)
    await h.person(here, department=A, grants=(("read:usage", Scope.department(A)),))
    await h.person(there, department=B, grants=(("read:usage", Scope.department(B)),))

    now = datetime.now(UTC)
    window = 2
    asks = [
        (stopper, now - timedelta(days=3)),
        (stayer, now - timedelta(days=3)),
        (stayer, now - timedelta(hours=1)),
        (newcomer, now - timedelta(hours=1)),
    ]
    for number, (who, at) in enumerate(asks):
        async with h.sessions() as session:
            await record(
                session,
                Asked(
                    trace_id=f"{h.trace_id}-s{number}",
                    principal_id=who,
                    principal_kind=PrincipalKind.HUMAN,
                    channel=Channel.CONSOLE,
                    department=A,
                    at=at,
                ),
            )
            await session.commit()
    console = console_for(h)

    mine = await adoption(console.request(), await asking_as(h, here), ListAsked(), days=window)
    line = next((one for one in mine.items if one.department == A), None)
    if line is None or (line.people, line.stopped) != (2, 1):
        raise CheckFailedError("Adoption did not count the person who stopped asking")
    elsewhere = await adoption(
        console.request(), await asking_as(h, there), ListAsked(), days=window
    )
    if any(one.department == A for one in elsewhere.items):
        raise CheckFailedError("Adoption showed who stopped in a department to a reader of another")
    if any(one.stopped for one in elsewhere.items):
        raise CheckFailedError("a department nobody stopped in was shown with somebody stopped")


# ------------------------------------ 4. the landing figures by period and department (M27.15.17)
@check(
    leaves=("M27.15.17",),
    sentence=(
        "A reader of usage across the company is shown the landing figures over thirty days and, "
        "narrowed to acceptance_a, counting exactly the questions its people asked and none of "
        "acceptance_b's; a reader of usage in acceptance_b asking for acceptance_a is answered as "
        "for a department that is not there."
    ),
)
async def landing_figures_follow_the_period_and_department_a_reader_reads(
    h: Harness,
) -> None:
    from brain.console.workspace import Range
    from brain.console_overview_figures_routes import overview_figures
    from brain.ops.acceptance_operations_console import (
        asking_as,
        console_for,
        refused,
        screen_grants,
    )
    from brain.ops.acceptance_operations_console_3 import QUESTIONS, asked_questions

    await h.found_departments()
    asker, other, wide, narrow = (
        h.principal(A, "asker"),
        h.principal(B, "asker"),
        h.principal(A, "wide"),
        h.principal(B, "narrow"),
    )
    await h.person(asker, department=A)
    await h.person(other, department=B)
    everything = dict.fromkeys((*screen_grants("overview"), *screen_grants("usage")))
    await h.person(wide, department=A, grants=tuple(everything))
    only_b = dict.fromkeys(
        (*screen_grants("overview"), *screen_grants("usage", Scope.department(B)))
    )
    await h.person(narrow, department=B, grants=tuple(only_b))
    await asked_questions(h, asker, A, QUESTIONS)
    await asked_questions(h, other, B, 1)
    console = console_for(h)

    month = await overview_figures(
        console.request(), await asking_as(h, wide), range=Range.THIRTY_DAYS, department=None
    )
    if month.range != Range.THIRTY_DAYS.value or (month.until - month.since).days != 30:
        raise CheckFailedError("the figures were not asked over the window the reader chose")
    here = await overview_figures(
        console.request(), await asking_as(h, wide), range=Range.SEVEN_DAYS, department=A
    )
    if (here.department, here.answered) != (A, QUESTIONS):
        raise CheckFailedError("the figures for a department did not count its people's questions")
    there = await overview_figures(
        console.request(), await asking_as(h, wide), range=Range.SEVEN_DAYS, department=B
    )
    if there.answered != 1:
        raise CheckFailedError("the figures for another department counted somebody else's")
    if not await refused(
        overview_figures(
            console.request(), await asking_as(h, narrow), range=Range.SEVEN_DAYS, department=A
        )
    ):
        raise CheckFailedError("a reader of one department was shown another's figures")


# ------------------------------------- 5. an account bound to nobody is told once (M27.15.4)
@check(
    leaves=("M27.15.4",),
    sentence=(
        "A person the identity provider signs in whom nobody has linked is told, by the sign-in "
        "status route, that an administrator must link their account and by whom, the "
        "administrators named being people who can sign in themselves; a linked person is told "
        "only that they are linked; a token the gate would refuse is refused as everywhere."
    ),
)
async def an_account_bound_to_nobody_is_told_who_can_link_it(h: Harness) -> None:
    from brain.identity.oidc import TokenRefusedError
    from brain.ops.acceptance_people_signed_in import administrator, console, everywhere
    from brain.sign_in_routes import YOUR_ACCOUNT_IS_NOT_LINKED_YET, sign_in_status

    await h.found_departments()
    c = await console(h)
    admin, member = h.principal(A, "linker"), h.principal(A, "linked")
    await h.person(admin, department=A, grants=everywhere(*administrator()))
    await h.person(member, department=A)
    await c.link(admin)
    linked_as = await c.link(member)
    stranger = f"acceptance-{h.run}-stranger"

    unlinked = await sign_in_status(c.request(c.token(stranger, session=c.session())))
    if unlinked.linked or unlinked.told != YOUR_ACCOUNT_IS_NOT_LINKED_YET:
        raise CheckFailedError("an account nobody linked was not told it is not linked")
    if "Acceptance check linker" not in unlinked.administrators:
        raise CheckFailedError("an unlinked account was not told who can link it")
    if any(one == "Acceptance check linked" for one in unlinked.administrators):
        raise CheckFailedError("a person who cannot link accounts was named as able to")

    told = await sign_in_status(c.request(c.token(linked_as, session=c.session())))
    if not told.linked or told.told is not None or told.administrators:
        raise CheckFailedError("a linked account was told more than that it is linked")
    try:
        await sign_in_status(c.request("not-a-token"))
    except TokenRefusedError:
        pass
    else:
        raise CheckFailedError("a token the gate would refuse was told whether it is linked")
