"""Install acceptance checks for the clauses of "roles and administration are proved on an install"
that had no check: the floor of two Super Admins, a deputy that cannot be covered, every console
write carrying the writer's real reach and trace, and what a person holds read back through the
People screen as the resolver gives it.

M27.15.3 is a composite, and each clause was left to a check written for a narrower leaf: a steward
is told of a grant somebody gave themselves (`acceptance_stewardship`), a deputy's grant ends in
thirty days (`acceptance_checks_governance`), the data steward holds what every source declares
(`acceptance_people_console_3`), and what a library lists is not what it lets a person open
(this module). Those checks now name M27.15.3 as well, so the leaf closes when every one of them
has passed on both of the install's newest runs, and a clause with no check cannot hide inside a
roll-up that passed on the others.

**The floor is proved on an install that already has its own Super Admins.** The check adds three
Super Admins of its own, retires every other standing one inside its rolled-back transaction, and
then removes one of the three through the Roles screen's route and is refused removing a second,
so what is proved is the product's floor and not how many Super Admins the install happens to
hold. Nothing here is kept: every row is the check's transaction's, which is always rolled back.

Task ids: M27.15.3
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import func, insert, select, update

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_governance import (
    GRANT_DECISION,
    GRANTED,
    REASON,
    _app,
    _asking,
    _grant,
    _refused,
    _request,
    _slug,
    _traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1360

A, B = RESERVED_DEPARTMENTS


# ---------------------------------------------------- 1. the floor, and a deputy of a deputy
@check(
    leaves=("M27.15.3",),
    sentence=(
        "With three Super Admins standing, one is removed through the Roles route and the next is "
        "refused in words, leaving two; a deputy is appointed for an approver, and a deputy "
        "cannot itself be given a deputy."
    ),
)
async def the_floor_of_two_super_admins_holds_and_a_deputy_has_no_deputy(h: Harness) -> None:
    from brain.console.scoped_authority import REACH_AUTHORITY
    from brain.govern_role_routes import (
        THE_FLOOR_IS_TWO,
        Appointment,
        DeputyAppointment,
        Removal,
        appoint_role,
        appoint_role_deputy,
        remove_role,
    )
    from brain.identity.roles import DEPUTY_MAX, Role
    from brain.tables.role_grant import RoleGrantRow

    _traced(h)
    await h.found_departments()
    admin = h.principal(A, "roles")
    supers = [h.principal(A, f"super{n}") for n in range(3)]
    approver, cover, other = (h.principal(A, one) for one in ("approver", "cover", "other"))
    await h.person(admin, department=A, grants=((REACH_AUTHORITY.value, Scope.unrestricted()),))
    for one in (*supers, approver, cover, other):
        await h.person(one, department=A)
    request = _request(_app(h))

    ours = []
    for one in supers:
        made = (
            await h.execute(
                *h.attributed(admin),
                insert(RoleGrantRow)
                .values(
                    principal_id=one,
                    role=Role.SUPER_ADMIN.value,
                    granted_by=admin,
                    reason=REASON,
                )
                .returning(RoleGrantRow.id),
            )
        ).scalar_one()
        ours.append(made)
    # Every other standing Super Admin the install holds is retired in this transaction, so the
    # floor is judged over the three above and not over whoever the install happens to have.
    await h.execute(
        *h.attributed(admin),
        update(RoleGrantRow)
        .where(
            RoleGrantRow.role == Role.SUPER_ADMIN.value,
            RoleGrantRow.deputy_of.is_(None),
            RoleGrantRow.deleted_at.is_(None),
            RoleGrantRow.id.not_in(ours),
        )
        .values(deleted_at=func.statement_timestamp()),
    )

    async def standing() -> int:
        return int(
            (
                await h.execute(
                    select(func.count())
                    .select_from(RoleGrantRow)
                    .where(
                        RoleGrantRow.role == Role.SUPER_ADMIN.value,
                        RoleGrantRow.deputy_of.is_(None),
                        RoleGrantRow.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
        )

    if await standing() != 3:
        raise CheckFailedError("the check could not hold the install to three Super Admins")
    asked = await _asking(h, admin)
    removed = await remove_role(request, Removal(grant_id=ours[0]), asked)
    if removed.change != "removed" or await standing() != 2:
        raise CheckFailedError("a Super Admin above the floor could not be removed")
    from brain.core.errors import Absent

    try:
        await remove_role(request, Removal(grant_id=ours[1]), await _asking(h, admin))
    except Absent as refused:
        if THE_FLOOR_IS_TWO not in refused.public_message:
            raise CheckFailedError(
                "the removal at the floor was refused without saying why"
            ) from None
    else:
        raise CheckFailedError("the last two Super Admins could be removed")
    if await standing() != 2:
        raise CheckFailedError("a refused removal changed who stands as a Super Admin")

    standing_role = await appoint_role(
        request,
        Appointment(principal_id=approver, role=Role.APPROVER, scope_slug=_slug(A), reason=REASON),
        await _asking(h, admin),
    )
    deputy = await appoint_role_deputy(
        request,
        DeputyAppointment(
            grant_id=uuid.UUID(standing_role.id),
            principal_id=cover,
            days=DEPUTY_MAX.days,
            reason=REASON,
        ),
        await _asking(h, admin),
    )
    if not await _refused(
        appoint_role_deputy(
            request,
            DeputyAppointment(
                grant_id=uuid.UUID(deputy.id), principal_id=other, days=1, reason=REASON
            ),
            await _asking(h, admin),
        )
    ):
        raise CheckFailedError("a deputy was given a deputy of their own")


# ------------------------------------- 2. every console write names the writer's reach and trace
@check(
    leaves=("M27.15.3",),
    sentence=(
        "A data steward grants a member a read and a Super Admin disables another member, each "
        "through its route: the ledger entry of each carries the reach digest the writer was "
        "admitted at and the request's own trace, and neither is the placeholder."
    ),
)
async def a_console_write_names_the_writers_real_reach_and_trace(h: Harness) -> None:
    from brain.audit.ledger import AuditAction
    from brain.principal_state_routes import StateAsked, disable_person
    from brain.tables.audit import AuditEntryRow

    _traced(h)
    await h.found_departments()
    steward, member, leaving = (h.principal(A, one) for one in ("steward", "member", "leaving"))
    everywhere = Scope.unrestricted()
    await h.person(
        steward, department=A, grants=((GRANT_DECISION, everywhere), (GRANTED, everywhere))
    )
    await h.person(member, department=A)
    await h.person(leaving, department=A)
    request = _request(_app(h))
    if not await _grant(h, request, steward, member, GRANTED, _slug(A)):
        raise CheckFailedError("a data steward could not grant a member a read")
    asked = await _asking(h, steward)
    done = await disable_person(request, StateAsked(principal_id=leaving), asked)
    if done.status_code != 200:
        raise CheckFailedError("a person who holds the grant decision could not disable a member")

    found = (
        await h.execute(
            select(AuditEntryRow.action, AuditEntryRow.ent_hash, AuditEntryRow.trace_id).where(
                AuditEntryRow.actor_id == steward
            )
        )
    ).all()
    wanted = {AuditAction.GRANT.value, AuditAction.PRINCIPAL_STATE.value}
    if {str(one[0]) for one in found} < wanted:
        raise CheckFailedError("a grant and a disable were not each in the ledger under the writer")
    for action, reach, trace in found:
        if action in wanted and (reach != asked.reach.ent_hash() or trace != h.trace_id):
            raise CheckFailedError(
                "a write's ledger entry did not carry the writer's reach or trace"
            )
        if reach == "0" * 32:
            raise CheckFailedError("a write's ledger entry carried the placeholder reach")


# ------------------------------------------------- 3. seen to exist, and not opened
@check(
    leaves=("M27.15.3",),
    sentence=(
        "A reader of the library across the company with no read of knowledge is listed a "
        "department's document and is not let open it, while the person who added it is; the "
        "list carries no count of what it left out."
    ),
)
async def a_library_reader_without_a_grant_sees_an_item_and_cannot_open_it(
    h: Harness,
) -> None:
    from brain.estate_routes import library
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
    from brain.ops.acceptance_checks_company_views import _screens_over
    from brain.ops.acceptance_checks_lifecycle import _added, _as, _live

    await h.found_departments()
    keeper, super_admin = h.principal(A, "keeper"), h.principal(B, "superadmin")
    from brain.knowledge.search import KNOWLEDGE_UPLOAD

    await h.person(keeper, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    await h.person(super_admin, department=B, grants=_screens_over(Scope.unrestricted(), "library"))
    item_id = await _added(h, keeper, h.word())
    request = _request(_app(h))

    listed = await library(
        request, await _asking(h, super_admin), ListAsked(search=item_id, limit=50)
    )
    if item_id not in {one.item_id for one in listed.items}:
        raise CheckFailedError("a reader of the whole library was not told a document exists")
    if listed.total is not None:
        raise CheckFailedError("the library answered with a count of what it left out")
    owner, reader = await _as(h, keeper), await _as(h, super_admin)
    stored = await _live(h, owner, item_id)
    if stored is None or not owner.authority.may_read(stored):
        raise CheckFailedError("the person who added a document could not open it")
    if reader.authority.may_read(stored):
        raise CheckFailedError("a library reader with no read of knowledge could open a document")


# ------------------------------------- 4. what the Access view lists is what the resolver gives
@check(
    leaves=("M27.15.3",),
    sentence=(
        "A member holding a direct grant and a pack is read back on their Access page as exactly "
        "the capabilities the resolver gives them, and after the grant is removed as exactly "
        "those that remain."
    ),
)
async def the_access_view_lists_exactly_what_the_resolver_gives(h: Harness) -> None:
    from brain.directory_routes import person_page
    from brain.govern_pack_routes import PackProposal, PackWriting, assign_pack, create_pack
    from brain.govern_routes import GrantRemoval, remove_grant
    from brain.ops.acceptance_people_console import (
        PACK_FIRST,
        lapses,
        registered_vocabulary,
    )
    from brain.ops.acceptance_people_console import (
        REASON as PEOPLE_REASON,
    )
    from brain.ops.acceptance_people_signed_in import administrator, console, everywhere, within

    await h.found_departments()
    await registered_vocabulary(h)
    c = await console(h)
    writer, member = h.principal(A, "writer"), h.principal(A, "member")
    await h.person(writer, department=A, grants=everywhere(*administrator()))
    await h.person(member, department=A, grants=within(A, "read:question"))
    asked = await c.asked(writer)
    slug = f"acceptance_{h.run}_access"
    with c.as_route():
        await create_pack(
            c.request(),
            PackWriting(
                slug=slug, label=f"Acceptance access {h.run}", capabilities=list(PACK_FIRST)
            ),
            asked,
        )
        await assign_pack(
            c.request(),
            PackProposal(
                principal_id=member,
                pack_slug=slug,
                scope_slug=A,
                reason=PEOPLE_REASON,
                not_after=lapses(h),
            ),
            asked,
        )

    async def shown() -> set[str]:
        with c.as_route():
            page = await person_page(c.request(), member, asked)
        return {one for held in page.held for one in held.capabilities}

    async def given() -> set[str]:
        return {one.capability.value for one in (await h.reach(member)).grants}

    before = await shown()
    if before != await given() or not set(PACK_FIRST) <= before or "read:question" not in before:
        raise CheckFailedError("the Access page did not list what the resolver gives the member")
    with c.as_route():
        await remove_grant(
            c.request(), GrantRemoval(principal_id=member, capability="read:question"), asked
        )
    after = await shown()
    if after != await given() or "read:question" in after:
        raise CheckFailedError("the Access page still listed what the member no longer holds")
