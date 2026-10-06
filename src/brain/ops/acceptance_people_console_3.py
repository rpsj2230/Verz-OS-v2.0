"""Install acceptance checks for console scope, approvals, elevation, review and own workspace.

The third half of the people and access leaves: which console a reader is given and what it offers,
what a refusal and a filter may say, the approvals waiting on a person and the one decision each
takes, an elevation asked for and given with its lapse, a department lead's review, a member's own
workspace and the data steward. Each check drives the route the console's page calls, signed in
through the install's own gate (`brain.ops.acceptance_people_signed_in`), in the harness's
transaction, which is always rolled back.

**A department reader is compared with a company reader, never described.** "Sees less" is shown by
the same route answering the department's reader a subset of what it answers the company's, and
"not offered" by the screens a department reader's own grants open being absent from their menu.
A check reading one reader alone could pass on a route that narrows nothing.

**An approval is raised the way the gate raises one.** The action is decided by
`brain.gate.leash.decide` and suspended by `brain.gate.leash.suspend` for the check's own agent and
target, stored at the asker's reach, and then left to the Approvals routes, so the queue and the
decision are read and written exactly as an approver's phone reads and writes them.

**The data steward is whoever the install has.** On an install whose steward is named, the check
reads that person's reach and never changes it, and is refused a second appointment in words; on
one with nobody named, it names a person through the route, inside the transaction.

Task ids: M27.5.6, M27.5.10, M27.7.29, M27.5.8, M27.15.63, M27.3.7
Task ids: M27.9.3, M27.7.8, M27.7.9, M27.7.28, M27.9.9
"""

from __future__ import annotations

from functools import partial
from typing import Any, Final

from sqlalchemy import func, select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_people_console import GRANTED, ledger, refused
from brain.ops.acceptance_people_console_2 import granted
from brain.ops.acceptance_people_signed_in import (
    Console,
    administrator,
    console,
    everywhere,
    told,
    within,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after the second people module's.
CHECK_ORDER: Final = 313

A, B = RESERVED_DEPARTMENTS

#: The screens whose subject is the installation, which a department console never offers:
#: `brain.console.screens.Group.INSTALL` and `NOT_AT_DEPARTMENT_SCOPE`.
INSTALLATION_SCREENS: Final = frozenset(
    {"install", "updates", "recovery", "limits", "connections", "service_levels"}
)

#: The capability the check's agent action needs, held by its asker and approver in acceptance_a.
ACTION_CAPABILITY: Final = "write:ticket.status"

#: Why the elevation check's approver holds their reach for two hours rather than one.
AN_APPROVER_OUTLASTS_THE_HOUR_THEY_GIVE: Final = (
    "An approved elevation is a grant lapsing the hours asked for after the database's instant, "
    "and a grant may not outlive its granter. A reserved person's reach lapses an hour after the "
    "check began, which is before the shortest elevation an approval writes, so the approver's "
    "rows are moved to two hours inside the check's own transaction, which is rolled back."
)

#: The made-up work address a steward named by the check is given, on a domain nothing delivers to.
STEWARD_ADDRESS: Final = "acceptance-steward@acceptance.invalid"


async def navigation(c: Console, reader: str) -> Any:
    """`GET /console/navigation` as `reader`, signed in with an authenticator."""
    from brain.navigation_routes import console_navigation

    asked = await c.asked(reader)
    with c.as_route():
        return await console_navigation(asked)


def entry_keys(answered: Any) -> set[str]:
    """Every registry screen the menu's entries and tabs open."""
    keys: set[str] = set()
    for section in answered.sections:
        for entry in section.entries:
            keys.add(entry.key)
            keys.update(tab.key for tab in entry.tabs)
    return {one for one in keys if one}


async def people_listed(c: Console, reader: str) -> set[str]:
    """`GET /govern/directory` as `reader`: the people they are shown."""
    from brain.directory_routes import directory
    from brain.listing import ListAsked

    asked = await c.asked(reader)
    with c.as_route():
        page = await directory(c.request(), asked, ListAsked(limit=200))
    return {one.principal_id for one in page.items}


# ------------------------------------------------------------ 1. navigation (M27.5.6)
@check(
    leaves=("M27.5.6",),
    sentence=(
        "A member appointed department administrator of acceptance_a, holding no grant, is given "
        "a department console with nothing in it; given the People grants over acceptance_a, the "
        "same person's menu offers People, so the menu follows the grants and never the role."
    ),
)
async def the_menu_follows_the_grants_and_never_the_role(h: Harness) -> None:
    from brain.govern_role_routes import Appointment, appoint_role
    from brain.identity.roles import Role

    await h.found_departments()
    c = await console(h)
    lead, appointed = h.principal(A, "lead"), h.principal(A, "appointed")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(appointed, department=A)
    asked = await c.asked(lead)
    with c.as_route():
        await appoint_role(
            c.request(),
            Appointment(
                principal_id=appointed,
                role=Role.DEPARTMENT_ADMIN,
                scope_slug=A,
                reason="Appointed by an install acceptance check",
            ),
            asked,
        )
    bare = await navigation(c, appointed)
    if bare.console != "department" or entry_keys(bare):
        raise CheckFailedError("an appointed role holding no grant was offered a screen")
    for capability in ("read:grant", "read:console.configuration"):
        await h.grant(appointed, capability, within(A, capability)[0][1])
    if "people" not in entry_keys(await navigation(c, appointed)):
        raise CheckFailedError("a person given the People grants was not offered People")


# ------------------------------------------------------ 2. department scope (M27.5.10, M27.7.29)
@check(
    leaves=("M27.5.10", "M27.7.29"),
    sentence=(
        "An administrator of acceptance_a is given the department console bounded to it, with no "
        "screen whose subject is the installation although their grants open several, while an "
        "administrator of the whole install is given the company console; People lists the "
        "department's reader a part of what it lists the company's, and nobody in acceptance_b."
    ),
)
async def a_department_reader_is_given_less_and_no_installation_screen(h: Harness) -> None:
    from brain.console.reads import permitted
    from brain.console.screens import screen

    await h.found_departments()
    c = await console(h)
    lead, whole = h.principal(A, "lead"), h.principal(B, "whole")
    mine, theirs = h.principal(A, "member"), h.principal(B, "member")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(whole, department=B, grants=everywhere(*administrator()))
    await h.person(mine, department=A)
    await h.person(theirs, department=B)

    reach = await h.reach(lead)
    opened = {key for key in INSTALLATION_SCREENS if permitted(screen(key).read, reach, h.now)}
    menu = await navigation(c, lead)
    if menu.console != "department" or menu.departments != [A] or not entry_keys(menu):
        raise CheckFailedError("a department administrator was not given their department console")
    if not opened or entry_keys(menu) & INSTALLATION_SCREENS:
        raise CheckFailedError("a department console offered a screen whose subject is the install")
    if (await navigation(c, whole)).console != "company":
        raise CheckFailedError("an administrator of the whole install was not given its console")

    department, company = await people_listed(c, lead), await people_listed(c, whole)
    if not department < company or mine not in department or theirs in department:
        raise CheckFailedError(
            "People did not list the department's reader less than the company's"
        )


# --------------------------------------------- 3. filters and refusals (M27.5.8, M27.15.63)
@check(
    leaves=("M27.5.8", "M27.15.63"),
    sentence=(
        "Scopes offers an administrator of acceptance_a a department filter holding acceptance_a "
        "and not acceptance_b, while the whole install's is offered both; a person in acceptance_b "
        "and a person who does not exist are refused alike on a person's page, in words that say "
        "nothing about why."
    ),
)
async def filters_offer_only_what_is_reached_and_refusals_say_no_why(h: Harness) -> None:
    from brain.directory_routes import person_page
    from brain.govern_routes import scopes
    from brain.listing import ListAsked

    await h.found_departments()
    c = await console(h)
    lead, whole, theirs = h.principal(A, "lead"), h.principal(B, "whole"), h.principal(B, "member")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(whole, department=B, grants=everywhere(*administrator()))
    await h.person(theirs, department=B)

    async def offered(reader: str) -> set[str]:
        asked = await c.asked(reader)
        with c.as_route():
            return set((await scopes(c.request(), asked, ListAsked(limit=200))).departments)

    department, company = await offered(lead), await offered(whole)
    if A not in department or B in department or not {A, B} <= company:
        raise CheckFailedError("a department filter offered a department the reader cannot reach")

    asked = await c.asked(lead)
    said: list[str] = []
    for who in (theirs, h.principal(B, "nobody")):
        with c.as_route():
            exc = await refused(partial(person_page, c.request(), who, asked))
        if exc is None:
            raise CheckFailedError("a person outside the reader's department was shown")
        said.append(told(exc))
    if said[0] != said[1]:
        raise CheckFailedError("a withheld person was refused unlike one who does not exist")


# ---------------------------------------------------- 4. approvals (M27.3.7, M27.9.3)
@check(
    leaves=("M27.3.7", "M27.9.3"),
    sentence=(
        "An agent's action held for a person is on Approvals for an approver in acceptance_a and "
        "not for one in acceptance_b; approved from the console it is recorded once in the ledger, "
        "read as decided by a store opened afresh, as after a restart, and a second decision and "
        "the other department's are refused alike."
    ),
)
async def an_approval_waits_on_a_person_and_is_decided_once(h: Harness) -> None:
    from brain.approval_routes import DecidableVerdict, DecisionAsked, approvals, decide_approval
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.envelope import SideEffect, ToolDefinition
    from brain.core.field_policy import FieldPolicy
    from brain.core.scope import Scope
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.leash import Action, Leash, LeashEntry, decide, suspend
    from brain.gate.suspension_store import StoredSuspensions, put_suspension
    from brain.listing import ListAsked
    from brain.tables.audit import AuditEntryRow

    await h.found_departments()
    c = await console(h)
    asker, approver = h.principal(A, "asker"), h.principal(A, "approver")
    elsewhere = h.principal(B, "approver")
    for one, where in ((asker, A), (approver, A), (elsewhere, B)):
        await h.person(
            one, department=where, grants=within(where, ACTION_CAPABILITY, "approve:action")
        )
    agent, target = f"acceptance_{h.run}_agent", f"acceptance_{h.run}.update_status"
    action = Action(
        agent_id=agent,
        tool=ToolDefinition(
            name=target,
            description="The acceptance check's own action, which changes nothing anywhere",
            entity="ticket",
            required_capability=ACTION_CAPABILITY,
            side_effect=SideEffect.WRITE,
        ),
        target=target,
        row={"department": A},
    )
    asking = await h.reach(asker)
    decided = decide(
        action,
        caller=asking,
        agent_ceiling=EntitlementSet(
            principal_id=agent,
            grants=(
                Grant(capability=Capability(value=ACTION_CAPABILITY), scope=Scope.unrestricted()),
            ),
        ),
        policy=FieldPolicy(rules=()),
        leash=Leash(
            entries=(
                LeashEntry(
                    agent_id=agent,
                    target=target,
                    scope=Scope.unrestricted(),
                    rung=AutonomyTier.ASSISTED,
                ),
            )
        ),
        assessment=RiskAssessment(score=0, matched=()),
        now=h.now,
    )
    raised = suspend(
        action,
        decided,
        principal_id=asker,
        trace_id=h.trace_id,
        now=h.now,
        suspension_id=f"acceptance_{h.run}_approval",
    )
    store = StoredSuspensions(h.sessions)
    async with store.holding(asking, h.now) as rows:
        await put_suspension(rows.session, raised)
    c.app.state.suspensions = store

    async def queued(reader: str) -> set[str]:
        asked = await c.asked(reader)
        with c.as_route():
            page = await approvals(c.request(), asked, ListAsked(limit=200))
        return {one.suspension_id for one in page.items}

    if raised.id not in await queued(approver) or raised.id in await queued(elsewhere):
        raise CheckFailedError("an action waiting on a person was not queued for its approver only")

    approving = DecisionAsked(verdict=DecidableVerdict.APPROVED)
    other = await c.asked(elsewhere)
    with c.as_route():
        outside = await refused(lambda: decide_approval(c.request(), raised.id, other, approving))
        if outside is None:
            raise CheckFailedError("an approver outside the action's department decided it")
        asked = await c.asked(approver)
        await decide_approval(c.request(), raised.id, asked, approving)
        again = await refused(lambda: decide_approval(c.request(), raised.id, asked, approving))
    if again is None or told(again) != told(outside):
        raise CheckFailedError("a decided approval was decided again, or refused unlike another")

    entries = await h.execute(
        select(func.count())
        .select_from(AuditEntryRow)
        .where(AuditEntryRow.subject.contains(raised.id), AuditEntryRow.actor_id == approver)
    )
    if int(entries.scalar_one()) != 1:
        raise CheckFailedError("a decision did not leave exactly one ledger entry")
    afresh = StoredSuspensions(h.sessions).reading_as(await h.reach(approver), h.now)
    if raised.id in {one.id for one in await afresh.open_suspensions()}:
        raise CheckFailedError("a store opened afresh still read the decided approval as open")


# ---------------------------------------------------------------- 5. elevation (M27.7.8)
@check(
    leaves=("M27.7.8",),
    sentence=(
        "A member of acceptance_a asks for a capability over acceptance_a for an hour; their "
        "administrator sees who asked, for what and why, approves it, a standing Super Admin is "
        "told, and the member holds it with the lapse the screen shows; asking for what they "
        "already hold is refused, and the requester cannot decide their own."
    ),
)
async def an_elevation_is_asked_for_given_and_lapses(h: Harness) -> None:
    from brain.core.entitlement import Capability
    from brain.govern_people_routes import (
        ElevationAsked,
        ElevationDecisionAsked,
        decide_elevation,
        elevation_page,
        file_elevation,
    )
    from brain.identity.roles import BreakGlassReason
    from brain.listing import ListAsked
    from brain.tables.elevation import ElevationDecision

    await h.found_departments()
    c = await console(h)
    lead, member = h.principal(A, "lead"), h.principal(A, "member")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(member, department=A)
    asking = ElevationAsked(
        capability=GRANTED,
        scope_slug=A,
        reason=BreakGlassReason.INCIDENT_RESPONSE,
        explanation="An install acceptance check asking for an hour",
        hours=1,
    )
    asked = await c.asked(member)
    with c.as_route():
        filed = await file_elevation(c.request(), asking, asked)
        own = await refused(
            lambda: decide_elevation(
                c.request(),
                _uuid(filed.request_id),
                ElevationDecisionAsked(decision=ElevationDecision.APPROVED),
                asked,
            )
        )
    if own is None:
        raise CheckFailedError("a requester decided their own elevation")

    await outlasting(h, lead)
    await a_standing_super_admin(c, h.principal(B, "owner"))
    deciding = await c.asked(lead)
    with c.as_route():
        shown = await elevation_page(c.request(), deciding, ListAsked(limit=200))
        row = next((one for one in shown.items if one.request_id == filed.request_id), None)
        if row is None or (row.principal_id, row.capability, row.decidable) != (
            member,
            GRANTED,
            True,
        ):
            raise CheckFailedError("an administrator was not shown who asked for what")
        approved = await decide_elevation(
            c.request(),
            _uuid(filed.request_id),
            ElevationDecisionAsked(decision=ElevationDecision.APPROVED),
            deciding,
        )
    if h.principal(B, "owner") not in approved.notified:
        raise CheckFailedError("an approved elevation told no standing Super Admin")
    if approved.lapses_at is None or approved.principal_id != member:
        raise CheckFailedError("an approved elevation was given with no lapse")
    holds = await h.reach(member)
    if holds.scope_for(Capability(value=GRANTED), h.now) is None:
        raise CheckFailedError("an approved elevation was not held by its requester")
    again = await c.asked(member)
    with c.as_route():
        if await refused(lambda: file_elevation(c.request(), asking, again)) is None:
            raise CheckFailedError("an elevation of what is already held was filed")
        after = await elevation_page(c.request(), deciding, ListAsked(limit=200))
    decided = next((one for one in after.items if one.request_id == filed.request_id), None)
    if decided is None or (decided.decided_by, decided.lapses_at) != (lead, approved.lapses_at):
        raise CheckFailedError("the screen did not show who gave the elevation and its lapse")


async def a_standing_super_admin(c: Console, principal_id: str) -> None:
    """`principal_id` appointed Super Admin on Roles by an administrator of the whole install, so
    an elevation has somebody independent to tell (`brain.console.elevation.client_recipients`)."""
    from brain.govern_role_routes import Appointment, appoint_role
    from brain.identity.roles import Role

    h = c.h
    appointer = h.principal(B, "appointer")
    await h.person(appointer, department=B, grants=everywhere(*administrator()))
    await h.person(principal_id, department=B)
    asked = await c.asked(appointer)
    with c.as_route():
        await appoint_role(
            c.request(),
            Appointment(
                principal_id=principal_id,
                role=Role.SUPER_ADMIN,
                reason="Appointed by an install acceptance check",
            ),
            asked,
        )


async def outlasting(h: Harness, principal_id: str) -> None:
    """Let a reserved approver's reach run past the shortest elevation. See
    `AN_APPROVER_OUTLASTS_THE_HOUR_THEY_GIVE`."""
    from datetime import timedelta

    from sqlalchemy import update

    from brain.tables.gate import CapabilityGrantRow
    from brain.tables.identity import PrincipalRow

    until = h.now + timedelta(hours=2)
    await h.execute(
        *h.attributed(),
        update(PrincipalRow).where(PrincipalRow.id == principal_id).values(not_after=until),
        update(CapabilityGrantRow)
        .where(CapabilityGrantRow.principal_id == principal_id)
        .values(not_after=until),
    )


def _uuid(value: str) -> Any:
    import uuid

    return uuid.UUID(value)


# ---------------------------------------------------------------- 6. access review (M27.7.9)
@check(
    leaves=("M27.7.9",),
    sentence=(
        "The lead of acceptance_a reviews what their people hold: the review lists their member's "
        "grant and nothing in acceptance_b, a keep is recorded under them, a removal takes the "
        "grant away, and a decision on acceptance_b's grant is refused."
    ),
)
async def a_department_lead_recertifies_what_their_people_hold(h: Harness) -> None:
    from brain.console.govern import Decision
    from brain.core.entitlement import Capability
    from brain.govern_people_routes import (
        HoldingKind,
        ReviewDecisionAsked,
        access_review_page,
        decide_review,
    )
    from brain.listing import ListAsked

    await h.found_departments()
    c = await console(h)
    lead, other = h.principal(A, "lead"), h.principal(B, "lead")
    mine, theirs = h.principal(A, "member"), h.principal(B, "member")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(other, department=B, grants=within(B, *administrator()))
    await h.person(mine, department=A)
    await h.person(theirs, department=B)
    await granted(c, lead, mine, A)
    await granted(c, other, theirs, B)

    asked = await c.asked(lead)
    with c.as_route():
        page = await access_review_page(c.request(), asked, ListAsked(limit=200))
    rows = {one.principal_id: one for one in page.items if one.capabilities == [GRANTED]}
    if mine not in rows or theirs in rows:
        raise CheckFailedError("the review did not list the lead's people and only theirs")
    row_id = _uuid(rows[mine].row_id)

    def asking(decision: Decision, row: Any = row_id) -> ReviewDecisionAsked:
        return ReviewDecisionAsked(kind=HoldingKind.GRANT, row_id=row, decision=decision)

    with c.as_route():
        kept = await decide_review(c.request(), asking(Decision.KEEP), asked)
        theirs_row = await _row_of(h, theirs)
        outside = await refused(
            lambda: decide_review(c.request(), asking(Decision.KEEP, theirs_row), asked)
        )
        removed = await decide_review(c.request(), asking(Decision.REMOVE), asked)
    if outside is None:
        raise CheckFailedError("a lead decided a grant outside their department")
    if (kept.decision.value, removed.decision.value) != ("keep", "remove"):
        raise CheckFailedError("a keep and a removal were not each recorded")
    if (await h.reach(mine)).scope_for(Capability(value=GRANTED), h.now) is not None:
        raise CheckFailedError("a removal in the review did not take the grant away")
    if not await ledger(h, lead):
        raise CheckFailedError("the review's decisions are not in the ledger under the lead")


async def _row_of(h: Harness, principal_id: str) -> Any:
    """The live grant row of `GRANTED` for `principal_id`."""
    from brain.tables.gate import CapabilityGrantRow

    found = await h.execute(
        select(CapabilityGrantRow.id).where(
            CapabilityGrantRow.principal_id == principal_id,
            CapabilityGrantRow.capability == GRANTED,
            CapabilityGrantRow.deleted_at.is_(None),
        )
    )
    return found.scalar_one()


# ------------------------------------------------------------ 7. own workspace (M27.7.28)
@check(
    leaves=("M27.7.28",),
    sentence=(
        "A member of acceptance_a who administers nothing opens My workspace and is answered as "
        "themselves, with the two questions they asked this month and not another member's; the "
        "same person is refused People."
    ),
)
async def a_member_reads_their_own_workspace_and_no_administration(h: Harness) -> None:
    from brain.adoption import Asked as QuestionAsked
    from brain.directory_routes import directory
    from brain.gate.context import Channel
    from brain.listing import ListAsked
    from brain.mine_routes import workspace
    from brain.ops.question_store import record

    await h.found_departments()
    c = await console(h)
    member, other = h.principal(A, "member"), h.principal(A, "other")
    for one in (member, other):
        await h.person(one, department=A)
    async with h.sessions() as session:
        for n, who in enumerate((member, member, other)):
            await record(
                session,
                QuestionAsked(
                    trace_id=f"{h.trace_id}-{n}",
                    principal_id=who,
                    principal_kind=_human(),
                    channel=Channel.CONSOLE,
                    department=A,
                    at=h.now,
                ),
            )
        await session.commit()

    asked = await c.asked(member, strong=False)
    with c.as_route():
        mine = await workspace(c.request(), asked)
        if await refused(lambda: directory(c.request(), asked, ListAsked())) is None:
            raise CheckFailedError("a member who administers nothing was answered People")
    if mine.principal_id != member or mine.asked.questions != 2:
        raise CheckFailedError("My workspace did not answer the member's own questions")


def _human() -> Any:
    from brain.core.principal import PrincipalKind

    return PrincipalKind.HUMAN


# ------------------------------------------------------------- 8. the data steward (M27.9.9)
@check(
    leaves=("M27.9.9",),
    sentence=(
        "The data steward is named, through the console where nobody is, and holds the content "
        "plane, the grant authority and every capability each connected source declares, over "
        "everything; the administrator who named them holds none of the content plane, and a "
        "second naming is refused in words."
    ),
)
async def the_data_steward_holds_what_every_connected_source_declares(h: Harness) -> None:
    import json

    from brain.core.entitlement import Capability
    from brain.data_steward_routes import StewardAsked, data_steward, name_data_steward
    from brain.identity.data_steward import APPOINTED_WITH, declared_by_connections_in

    c = await console(h)
    first = h.principal(A, "first")
    await h.person(first, department=A, grants=everywhere(*administrator()))
    asked = await c.asked(first)
    naming = StewardAsked(
        same_as_administrator=False,
        full_name="Acceptance check steward",
        work_address=STEWARD_ADDRESS,
    )
    with c.as_route():
        now = await data_steward(c.request(), asked)
        if not now.appointed:
            named = await name_data_steward(c.request(), naming, asked)
            if named.status_code != 200:
                raise CheckFailedError("a data steward could not be named from the console")
            now = await data_steward(c.request(), asked)
        second = await name_data_steward(c.request(), naming, asked)
    if second.status_code != 409 or not json.loads(bytes(second.body)).get("message"):
        raise CheckFailedError("a second data steward was named, or refused without words")
    steward = now.principal_id
    if steward is None or steward == first:
        raise CheckFailedError("the data steward is the administrator who named them")

    async with h.sessions() as session:
        declared = await declared_by_connections_in(session)
    reach = await h.reach(steward)
    for one in (*APPOINTED_WITH, *declared):
        scope = reach.scope_for(Capability(value=one), h.now)
        if scope is None or not scope.is_unrestricted():
            raise CheckFailedError(
                "the data steward does not hold what a connected source declares"
            )
    if (await h.reach(first)).scope_for(Capability(value=APPOINTED_WITH[0]), h.now) is not None:
        raise CheckFailedError("the administrator holds the content plane by default")
