"""The install acceptance checks for the governance surfaces, second half: connectors, approvals and
elevation.

The second half of M33's role surfaces: what a connector administrator, an approver and an
installing partner are each offered. As in `brain.ops.acceptance_checks_governance`, every check is
the screen's own route function called as the reader the leaf names, against the install's own
database, inside the check's rolled-back transaction, with the reader signed in with a second
factor and every act asked beside the refusal of a reader who may not do it.

**A connector is connected only where the install has not connected it.** Connecting a source
that is live already is refused by the store, and switching the owner's own off inside a check,
even one rolled back, would hold his connection's lock for the check's length. So each connector
check says it was not run where the install has the source connected, for
`brain.ops.acceptance_checks_connectors.A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`'s reason. See
`A_SOURCE_CONNECTED_HERE_IS_LEFT_ALONE`.

**The key a rotation writes is written to a vault the check holds.** The install's vault cannot
delete a slot, so a key the check wrote there would outlive the check; the check's application
holds `brain.ops.acceptance_checks_connector_framework._Vault`, which is the vault as the product
asks it and keeps nothing past the check, beside the install's own record of credential writes.
What is proved is the route's binding: the connection names the slot and never the key, and a
rotation writes the slot without touching the connection. See
`A_ROTATION_IS_WRITTEN_TO_A_VAULT_THE_CHECK_HOLDS`.

**The installing partner is a reserved principal whose employment says so**, holding nothing. It
and its authoriser last three hours rather than the harness's one, because an authoriser may not
grant past their own end and an elevation is an hour at least. See
`AN_ELEVATION_IS_ASKED_ABOUT_BY_PEOPLE_WHO_OUTLAST_IT`.

Task ids: M38.5.1
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_checks_governance import (
    GRANT_DECISION,
    REASON,
    _app,
    _asking,
    _refused,
    _request,
    _slug,
    _traced,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, after the first half's. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 412

# ------------------------------------------------------------------ written-down reasons
#: Why a connector check steps aside where the install has the source connected.
A_SOURCE_CONNECTED_HERE_IS_LEFT_ALONE: Final = (
    "Connecting a source the install has connected is refused, and switching the owner's off "
    "inside a check would hold his connection's lock for the length of it, so a connector check "
    "is not run where its source is connected here."
)

#: Why the rotation check writes to a vault of its own.
A_ROTATION_IS_WRITTEN_TO_A_VAULT_THE_CHECK_HOLDS: Final = (
    "The install's vault cannot delete a slot, so a key a check wrote there would outlive it. The "
    "check's application holds a vault the product asks as it asks its own and that keeps "
    "nothing past the check, beside the install's own record of credential writes."
)

#: What a connector check says where the install has its keyless source connected already.
DOMAINS_ARE_CONNECTED_HERE: Final = (
    "this install has its domains connected already, so the check does not connect them again"
)

#: What the rotation check says where the install has its keyed source connected already.
XERO_IS_CONNECTED_HERE: Final = (
    "this install has Xero connected already, so the check does not connect it again"
)

#: Why the elevation checks' partner and authoriser last longer than the harness's hour.
AN_ELEVATION_IS_ASKED_ABOUT_BY_PEOPLE_WHO_OUTLAST_IT: Final = (
    "An authoriser may not grant past their own end, and the shortest elevation is an hour from "
    "when it is approved, which is after a reserved person's hour is up. A partner whose own end "
    "came first would also hold nothing a minute after the lapse for that reason alone. So these "
    "two last three hours: uncommitted, gone with the check, and never able to sign in."
)

# ------------------------------------------------------------------------ the figures
#: The capability every check's agent action needs, which its asker and approver hold.
ACTION_CAPABILITY: Final = "write:ticket.status"

#: How long each of the three approvals the timeout check raises waits, in a deliberate order
#: that is not the order they lapse in.
WINDOWS: Final = (timedelta(hours=3), timedelta(hours=1), timedelta(hours=2))

#: How long ago the lapsed approval was raised, and how long it waited.
LONG_AGO: Final = timedelta(hours=2)
LAPSED_WINDOW: Final = timedelta(minutes=30)

#: What the installing partner asks to be elevated to, over acceptance_a, and for how long.
ELEVATED: Final = "read:knowledge.title"
ELEVATION_HOURS: Final = 1

#: How far either side of a lapse the resolver is asked.
EITHER_SIDE: Final = timedelta(minutes=1)

#: How long the partner and the authoriser in the elevation checks last: past the elevation's
#: lapse and the minute after it. See `AN_ELEVATION_IS_ASKED_ABOUT_BY_PEOPLE_WHO_OUTLAST_IT`.
OUTLASTS: Final = timedelta(hours=ELEVATION_HOURS + 2)


# --------------------------------------------------- 1. install and configure (M33.5.1.1)
def _connector_admin(connector: str) -> tuple[tuple[str, Scope], ...]:
    """The Connectors screen's authority over one source, which is what a connector admin holds."""
    from brain.connectors.registry import INSTALL_AUTHORITY
    from brain.core.scope import Clause, Op

    return (
        (
            INSTALL_AUTHORITY.value,
            Scope(clauses=(Clause(field="connector", op=Op.EQ, value=connector),)),
        ),
    )


async def _connected(h: Harness, connector: str) -> Any:
    """The live connection of `connector` the Connectors screen's store reads back, or None."""
    from brain.ops.connector_store import StoredConnections

    found = await StoredConnections(h.sessions).connected()
    return next((one for one in found if one.connector == connector), None)


async def _connected_here(h: Harness, connector: str) -> bool:
    """Whether the install has it connected. See `A_SOURCE_CONNECTED_HERE_IS_LEFT_ALONE`."""
    from brain.ops.connector_store import live

    return (await h.execute(live(connector))).scalar_one_or_none() is not None


@check(
    leaves=("M33.5.1.1",),
    sentence=(
        "A connector admin connects the domains source with a list of domains made up for the "
        "check through the Connectors screen's route, and the install reads it back connected "
        "with them; the admin then changes the list through the edit route and it reads back "
        "changed. A member is refused both."
    ),
)
async def a_connector_admin_installs_and_configures_a_connector(h: Harness) -> None:
    import secrets

    from brain.connector_routes import ConnectAsked, ConnectorEditAsked, connect, edit
    from brain.connectors import domains

    name = domains.CONNECTOR_NAME
    if await _connected_here(h, name):
        raise CheckNotRunError(DOMAINS_ARE_CONNECTED_HERE)
    _traced(h)
    await h.found_departments()
    admin, member = h.principal(A, "connectors"), h.principal(A, "member")
    await h.person(admin, department=A, grants=_connector_admin(name))
    await h.person(member, department=A, grants=_in(A, "read:knowledge"))
    request = _request(_app(h))
    first = {"domains": f"acceptance-{secrets.token_hex(4)}.com", "department": A}
    second = {"domains": f"acceptance-{secrets.token_hex(4)}.com", "department": A}

    if not await _refused(
        connect(
            request,
            ConnectAsked(connector=name, settings=first, credential=""),
            await _asking(h, member),
        )
    ):
        raise CheckFailedError("a member without the connector authority connected a source")
    answered = await connect(
        request,
        ConnectAsked(connector=name, settings=first, credential=""),
        await _asking(h, admin),
    )
    connection = await _connected(h, name)
    if answered.status_code != 200 or connection is None or dict(connection.settings) != first:
        raise CheckFailedError("a connector admin's connection was not read back as connected")

    if not await _refused(
        edit(request, name, ConnectorEditAsked(settings=second), await _asking(h, member))
    ):
        raise CheckFailedError("a member without the connector authority changed a source")
    edited = await edit(request, name, ConnectorEditAsked(settings=second), await _asking(h, admin))
    connection = await _connected(h, name)
    if edited.status_code != 200 or connection is None or dict(connection.settings) != second:
        raise CheckFailedError("a connector admin's change to a source was not read back")


# ---------------------------------------------- 2. bind and rotate a key (M33.5.1.2)
@check(
    leaves=("M33.5.1.2",),
    sentence=(
        "A connector admin connects Xero with a key made for the check, then replaces the key, "
        "each through the Connectors screen's route: the connection names the key's slot and "
        "never the key, the slot holds the second key, the connection is unchanged by the "
        "rotation, and no table holds either key. A member may not replace it."
    ),
)
async def a_connector_admin_binds_and_rotates_a_key_reference(h: Harness) -> None:
    import secrets

    from brain.connector_routes import ConnectAsked, ConnectorKeyAsked, connect, replace_key
    from brain.ops.acceptance_checks_connector_framework import _Vault
    from brain.ops.acceptance_checks_connectors import SOURCE, _search, _settings
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials, connector_key_slot

    if await _connected_here(h, SOURCE):
        raise CheckNotRunError(XERO_IS_CONNECTED_HERE)
    _traced(h)
    await h.found_departments()
    admin, member = h.principal(A, "connectors"), h.principal(A, "member")
    await h.person(admin, department=A, grants=_connector_admin(SOURCE))
    await h.person(member, department=A, grants=_in(A, "read:knowledge"))
    vault = _Vault()
    app = _app(h)
    app.state.credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))
    request = _request(app)
    slot = connector_key_slot(SOURCE).path
    first, second = secrets.token_hex(24), secrets.token_hex(24)

    connected = await connect(
        request,
        ConnectAsked(connector=SOURCE, settings=_settings(), credential=first),
        await _asking(h, admin),
    )
    bound = await _connected(h, SOURCE)
    if (
        connected.status_code != 200
        or bound is None
        or first not in vault.slots.get(slot, {}).values()
    ):
        raise CheckFailedError("a connector admin's key was not kept in its source's slot")

    if not await _refused(
        replace_key(request, SOURCE, ConnectorKeyAsked(credential=second), await _asking(h, member))
    ):
        raise CheckFailedError("a member without the connector authority replaced a source's key")
    replaced = await replace_key(
        request, SOURCE, ConnectorKeyAsked(credential=second), await _asking(h, admin)
    )
    held = vault.slots.get(slot, {})
    if replaced.status_code != 200 or second not in held.values() or first in held.values():
        raise CheckFailedError("a replaced key was not the one the source's slot held")
    after = await _connected(h, SOURCE)
    if after is None or (after.digest, after.connected_at) != (bound.digest, bound.connected_at):
        raise CheckFailedError("replacing a source's key changed its connection")
    if await _search(h, first) or await _search(h, second):
        raise CheckFailedError("a source's key was found in a table")


# --------------------------------------------- approvals: the card and its clock (M33.6)
async def _raised(
    h: Harness, asker: str, name: str, *, at: Any, window: timedelta, args: dict[str, Any]
) -> Any:
    """An agent's action held for a person, raised by `brain.gate.leash.suspend` at `at` and
    stored at the asker's reach, as `brain.ops.acceptance_takeover` raises one."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.envelope import SideEffect, ToolDefinition
    from brain.core.field_policy import FieldPolicy
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.leash import Action, Leash, LeashEntry, decide, suspend
    from brain.gate.suspension_store import StoredSuspensions, put_suspension

    agent = f"acceptance_{h.run}_agent"
    target = f"acceptance_{h.run}.update_status"
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
        touched_fields=tuple(args),
        args=args,
    )
    asking = await h.reach(asker)
    decision = decide(
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
        decision,
        principal_id=asker,
        trace_id=h.trace_id,
        now=at,
        window=window,
        suspension_id=f"acceptance_{h.run}_{name}",
    )
    async with StoredSuspensions(h.sessions).holding(asking, h.now) as rows:
        await put_suspension(rows.session, raised)
    return raised


def _approvals_app(h: Harness) -> FastAPI:
    from brain.gate.suspension_store import StoredSuspensions

    app = _app(h)
    app.state.suspensions = StoredSuspensions(h.sessions)
    return app


async def _two_people(h: Harness) -> tuple[str, str, str]:
    """An asker and an approver in acceptance_a holding the action's capability there, and a
    reader of acceptance_b holding it over their own department."""
    _traced(h)
    await h.found_departments()
    asker, approver = h.principal(A, "asker"), h.principal(A, "approver")
    other = h.principal(B, "approver")
    for one in (asker, approver):
        await h.person(one, department=A, grants=_in(A, ACTION_CAPABILITY))
    await h.person(other, department=B, grants=_in(B, ACTION_CAPABILITY))
    return asker, approver, other


#: What each way of showing an approver the wrong thing fails with.
SHOWN_THE_TOOL_CALL: Final = (
    "an approval carried the tool call, its capability or its arguments rather than the request"
)
SHOWN_A_LOCKED_FIELD: Final = (
    "an approver was shown the value of a field they may not read, rather than the lock"
)
NOT_THE_ONE_RENDER: Final = (
    "an approver was not shown the request as the one render draws it at their own reach"
)
SHOWN_TO_ANOTHER_DEPARTMENT: Final = "an approver of another department was shown the card"


@check(
    leaves=("M33.6.1.2",),
    sentence=(
        "An agent's action naming a value made up for the check waits for a person: the approver "
        "of acceptance_a reads it through the Approvals routes, on its card and its page, as the "
        "one render of the request at their own reach, with the lock where they may not read a "
        "field and never the value, and no field holding the tool call, its capability or its "
        "arguments. Acceptance_b's approver is not shown it."
    ),
)
async def an_approver_reads_the_request_at_their_own_reach(h: Harness) -> None:
    from brain.approval_routes import ApprovalCardView, approval, approvals
    from brain.console.approvals import request_policy
    from brain.core.redaction import LOCK_TEXT
    from brain.gate.approval_request import render_request
    from brain.listing import ListAsked

    asker, approver, other = await _two_people(h)
    word = h.word()
    raised = await _raised(h, asker, "artefact", at=h.now, window=WINDOWS[0], args={"status": word})
    request = _request(_approvals_app(h))
    asked = await _asking(h, approver)

    queue = await approvals(request, asked, ListAsked(limit=200))
    card = next((one for one in queue.items if one.suspension_id == raised.id), None)
    page = await approval(request, raised.id, asked)
    if card is None:
        raise CheckFailedError(NOT_THE_ONE_RENDER)
    shown = (card.model_dump(mode="json"), page.model_dump(mode="json"))
    if set(card.model_dump()) != set(ApprovalCardView.model_fields) or any(
        ACTION_CAPABILITY in str(value) or (isinstance(value, dict | list) and word in str(value))
        for one in shown
        for value in one.values()
    ):
        raise CheckFailedError(SHOWN_THE_TOOL_CALL)
    if word in card.request or word in page.request or f"status: {LOCK_TEXT}" not in card.request:
        raise CheckFailedError(SHOWN_A_LOCKED_FIELD)
    drawn = render_request(raised.action, asked.reach, request_policy(raised.action), asked.now)
    if card.request != drawn.text or page.request != drawn.text:
        raise CheckFailedError(NOT_THE_ONE_RENDER)
    if not await _refused(approval(request, raised.id, await _asking(h, other))):
        raise CheckFailedError(SHOWN_TO_ANOTHER_DEPARTMENT)


@check(
    leaves=("M33.6.1.4",),
    sentence=(
        "Three of an agent's actions wait with different windows and a fourth has lapsed: the "
        "approver of acceptance_a is shown each waiting card with the instant it lapses, soonest "
        "first, and the lapsed one is in nobody's queue, cannot be opened and cannot be decided."
    ),
)
async def an_approver_sees_when_each_approval_lapses_and_a_lapsed_one_goes(
    h: Harness,
) -> None:
    from brain.approval_routes import (
        DecidableVerdict,
        DecisionAsked,
        approval,
        approvals,
        decide_approval,
    )
    from brain.listing import ListAsked

    asker, approver, _ = await _two_people(h)
    waiting = [
        await _raised(h, asker, f"waits_{n}", at=h.now, window=window, args={})
        for n, window in enumerate(WINDOWS)
    ]
    lapsed = await _raised(h, asker, "lapsed", at=h.now - LONG_AGO, window=LAPSED_WINDOW, args={})
    request = _request(_approvals_app(h))

    queue = await approvals(request, await _asking(h, approver), ListAsked(limit=200))
    mine = {one.id for one in (*waiting, lapsed)}
    shown = [
        (one.suspension_id, one.expires_at) for one in queue.items if one.suspension_id in mine
    ]
    expected = sorted(((one.id, one.expires_at) for one in waiting), key=lambda one: one[1])
    if shown != expected:
        raise CheckFailedError(
            "the waiting approvals were not shown with their lapse, soonest first"
        )
    if not await _refused(approval(request, lapsed.id, await _asking(h, approver))):
        raise CheckFailedError("a lapsed approval could still be opened")
    approve = DecisionAsked(verdict=DecidableVerdict.APPROVED)
    if not await _refused(decide_approval(request, lapsed.id, await _asking(h, approver), approve)):
        raise CheckFailedError("a lapsed approval could still be decided")


# ------------------------------------------------ elevation (M33.7.1.2, .4, .5)
async def _outlasting(
    h: Harness,
    principal_id: str,
    *,
    department: str,
    employment: str,
    grants: tuple[tuple[str, Scope], ...] = (),
) -> None:
    """A reserved person whose own reach outlasts the hour an elevation is asked for. See
    `AN_ELEVATION_IS_ASKED_ABOUT_BY_PEOPLE_WHO_OUTLAST_IT`."""
    from sqlalchemy import insert

    from brain.core.principal import PrincipalKind
    from brain.tables.identity import PrincipalRow

    await h.execute(
        *h.attributed(),
        insert(PrincipalRow).values(
            id=principal_id,
            kind=PrincipalKind.HUMAN.value,
            employment=employment,
            display_name=f"Acceptance check {principal_id.rsplit('.', 1)[-1]}",
            primary_department=department,
            not_after=h.now + OUTLASTS,
        ),
    )
    for capability, scope in grants:
        await h.grant(principal_id, capability, scope)


async def _elevation_desk(h: Harness) -> tuple[Any, str, str, str]:
    """Both departments, a partner holding nothing, an authoriser holding the grant decision and
    the elevated capability over acceptance_a, and a standing Super Admin appointed to that role
    by a Super Admin holding the grant decision everywhere."""
    from brain.core.principal import Employment
    from brain.govern_role_routes import Appointment, appoint_role
    from brain.identity.roles import Role

    _traced(h)
    await h.found_departments()
    partner, authoriser = h.principal(A, "partner"), h.principal(A, "authoriser")
    owner, standing = h.principal(A, "owner"), h.principal(B, "super")
    await _outlasting(h, partner, department=A, employment=Employment.PARTNER.value)
    await _outlasting(
        h,
        authoriser,
        department=A,
        employment=Employment.STAFF.value,
        grants=_in(A, GRANT_DECISION, ELEVATED),
    )
    await h.person(owner, department=A, grants=((GRANT_DECISION, Scope.unrestricted()),))
    await h.person(standing, department=B)
    request = _request(_app(h))
    await appoint_role(
        request,
        Appointment(principal_id=standing, role=Role.SUPER_ADMIN, reason=REASON),
        await _asking(h, owner),
    )
    return request, partner, authoriser, standing


async def _filed(h: Harness, request: Any, partner: str) -> str:
    from brain.govern_people_routes import ElevationAsked, file_elevation
    from brain.identity.roles import BreakGlassReason

    filed = await file_elevation(
        request,
        ElevationAsked(
            capability=ELEVATED,
            scope_slug=_slug(A),
            reason=BreakGlassReason.INSTALL,
            explanation="An install acceptance check asks for this for one hour",
            hours=ELEVATION_HOURS,
        ),
        await _asking(h, partner),
    )
    return filed.request_id


async def _approved(h: Harness, request: Any, request_id: str, by: str) -> Any:
    """`POST /govern/elevation/requests/{id}/decision` approving, as `by`, or None if refused."""
    import uuid

    from brain.core.errors import Absent
    from brain.govern_people_routes import ElevationDecisionAsked, decide_elevation
    from brain.tables.elevation import ElevationDecision

    try:
        return await decide_elevation(
            request,
            uuid.UUID(request_id),
            ElevationDecisionAsked(decision=ElevationDecision.APPROVED),
            await _asking(h, by),
        )
    except Absent:
        return None


async def _holds(h: Harness, partner: str, at: Any) -> bool:
    """Whether the resolver, asked at `at`, returns the partner the elevated grant."""
    from brain.gate.entitlement_store import StoredEntitlements

    reach = await StoredEntitlements(h.sessions).load(partner, at)
    return any(one.capability.value == ELEVATED for one in reach.grants)


@check(
    leaves=("M33.7.1.2",),
    sentence=(
        "An installing partner holding nothing asks through the Elevation route for one capability "
        "over acceptance_a, for an hour, with a reason from the closed list: the request carries "
        "the reason, the partner cannot approve it, and the authoriser's approval grants it with "
        "a lapse an hour after it was approved."
    ),
)
async def a_partner_is_elevated_for_a_stated_reason_and_a_bounded_time(h: Harness) -> None:
    from brain.govern_people_routes import elevation_page
    from brain.identity.roles import BreakGlassReason
    from brain.listing import ListAsked

    request, partner, authoriser, _ = await _elevation_desk(h)
    if (await h.reach(partner)).grants:
        raise CheckFailedError("an installing partner held something before asking")
    request_id = await _filed(h, request, partner)
    page = await elevation_page(request, await _asking(h, partner), ListAsked(limit=200))
    asked = next((one for one in page.items if one.request_id == request_id), None)
    if asked is None or asked.reason != BreakGlassReason.INSTALL.value:
        raise CheckFailedError("an elevation request did not carry the reason it was asked for")
    if await _approved(h, request, request_id, partner) is not None:
        raise CheckFailedError("an installing partner approved their own elevation")
    decided = await _approved(h, request, request_id, authoriser)
    if decided is None or decided.lapses_at is None:
        raise CheckFailedError("an authoriser could not approve an installing partner's request")
    if decided.lapses_at - decided.decided_at != timedelta(hours=ELEVATION_HOURS):
        raise CheckFailedError("an approved elevation did not lapse the hours it was asked for")
    if not await _holds(h, partner, decided.decided_at):
        raise CheckFailedError("an approved elevation did not grant what it was asked for")


@check(
    leaves=("M33.7.1.4",),
    sentence=(
        "An installing partner's elevation over acceptance_a is approved: the standing Super "
        "Admin is told of it, with who was elevated, who allowed it, why and until when, through "
        "the notices route; the authoriser and the partner are told nothing, and the approval "
        "names who was told."
    ),
)
async def every_elevation_is_told_to_the_standing_super_admins(h: Harness) -> None:
    from brain.govern_people_routes import break_glass_notices
    from brain.identity.roles import BreakGlassReason

    request, partner, authoriser, standing = await _elevation_desk(h)
    request_id = await _filed(h, request, partner)
    decided = await _approved(h, request, request_id, authoriser)
    if decided is None or standing not in decided.notified:
        raise CheckFailedError("an approved elevation did not say the Super Admin was told")

    async def told(who: str) -> list[Any]:
        found = await break_glass_notices(request, await _asking(h, who))
        return [one for one in found.items if one.session_id == request_id]

    notices = await told(standing)
    said = [(one.principal_id, one.authorised_by, one.reason, one.lapses_at) for one in notices]
    if said != [(partner, authoriser, BreakGlassReason.INSTALL, decided.lapses_at)]:
        raise CheckFailedError("the standing Super Admin was not told who, by whom, why and until")
    if await told(authoriser) or await told(partner):
        raise CheckFailedError("an elevation's notice reached somebody other than a Super Admin")


@check(
    leaves=("M33.7.1.5",),
    sentence=(
        "An installing partner's approved elevation is held a minute before its lapse and not a "
        "minute after, with nothing run to end it; removed through the People screen's grant "
        "removal before its lapse, it is held no longer and its request reads as ended."
    ),
)
async def an_elevation_lapses_by_itself_and_can_be_revoked_before_it_does(h: Harness) -> None:
    from brain.console.elevation import ElevationState
    from brain.govern_people_routes import elevation_page
    from brain.govern_routes import GrantRemoval, remove_grant
    from brain.listing import ListAsked

    request, partner, authoriser, _ = await _elevation_desk(h)
    decided = await _approved(h, request, await _filed(h, request, partner), authoriser)
    if decided is None or decided.lapses_at is None:
        raise CheckFailedError("an authoriser could not approve an installing partner's request")
    lapse = decided.lapses_at
    if not await _holds(h, partner, lapse - EITHER_SIDE):
        raise CheckFailedError("an elevation was not held before its lapse")
    if await _holds(h, partner, lapse + EITHER_SIDE):
        raise CheckFailedError("an elevation was still held after its lapse")

    removed = await remove_grant(
        request,
        GrantRemoval(principal_id=partner, capability=ELEVATED),
        await _asking(h, authoriser),
    )
    if removed.capability != ELEVATED or await _holds(h, partner, decided.decided_at):
        raise CheckFailedError("an elevation removed before its lapse was still held")
    page = await elevation_page(request, await _asking(h, partner), ListAsked(limit=200))
    states = {one.request_id: one.state for one in page.items}
    if states.get(str(decided.request_id)) is not ElevationState.ENDED:
        raise CheckFailedError("a removed elevation's request did not read as ended")
