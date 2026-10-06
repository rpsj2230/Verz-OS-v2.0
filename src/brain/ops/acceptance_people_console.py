"""The install acceptance checks for the Govern screens' structure, grants, packs, roles and people.

Every leaf here was built, merged and wired, and none had been seen working on an install: the
routes were exercised over HTTP in the unit suite against a stub session, which proves the order of
the refusals and nothing about what PostgreSQL, the audit triggers and the one resolver do with a
write. These checks drive the routes the console's pages call, as the person each page serves,
signed in through the install's own gate (`brain.ops.acceptance_people_signed_in`), against the
install's own schema, in the harness's transaction, which is always rolled back.

**Each write is followed by what it changed, read the way the install reads it.** A grant is read
back through the People screen and through the resolver; a retirement through the screen that
listed the row; an audited change through the ledger's own rows under the person who pressed. A
check that stopped at the route's answer would pass on a route that answered and wrote nothing.

**Every refusal has a sibling that passes**, because a route that refused everybody would satisfy
a check made only of refusals. A department administrator grants inside their department and is
refused outside it; a department under a live grant is refused retirement and then retired once the
grant goes; a pack somebody holds is refused retirement and its unheld copy is retired.

**Everything is in the reserved departments, or is the whole company's and gone with the check.**
A department administrator's grants are written over a reserved department's scope; an
administrator who founds departments or writes packs holds what an install's first administrator is
granted, over everything, because founding and packs are the whole company's acts
(`brain.console.organisation.FOUNDING_OR_RETIRING_A_DEPARTMENT_IS_THE_WHOLE_COMPANYS_ACT`,
`brain.govern_pack_routes`); every row they write is uncommitted.

Task ids: M27.3.2, M27.11.1, M27.15.22, M27.7.3, M27.7.7
Task ids: M27.15.20, M27.15.24, M27.11.3, M27.7.5, M27.15.19
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Final

from sqlalchemy import select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_people_signed_in import (
    Console,
    administrator,
    console,
    everywhere,
    told,
    within,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 311

A, B = RESERVED_DEPARTMENTS

#: What a member is granted and has taken away in these checks: a read the administrator holds.
GRANTED: Final = "read:document"

#: A capability no administrator is granted at appointment, so nobody here may grant it.
NOBODY_HERE_HOLDS: Final = "read:invoice.total"

#: The capabilities the checks' pack carries, at its first version and its second.
PACK_FIRST: Final = ("read:document",)
PACK_SECOND: Final = ("read:document", "read:question")

#: How long a grant a check writes lasts: inside the hour a reserved grantor's own reach lasts.
GRANT_LASTS: Final = timedelta(minutes=30)

#: What each change to a team or a drawn scope is recorded as, in the order the check makes them.
STRUCTURE_CHANGES: Final = ("created", "renamed", "retired")

#: The reason every grant and appointment a check writes gives.
REASON: Final = "Written by an install acceptance check for the length of the check"


def lapses(h: Harness) -> datetime:
    """When a grant a check writes lapses: before its grantor does.

    A grant may not outlive the person who wrote it (`brain.console.scoped_authority._outlives`),
    and a reserved grantor lapses with the check's reach.
    """
    return h.now + GRANT_LASTS


async def registered_vocabulary(h: Harness) -> None:
    """The capabilities the product declares, registered where a row is missing, as every start of
    the application does (`brain.ops.starter_store.furnish`). On an install this writes nothing."""
    from brain.ops.starter import vocabulary
    from brain.ops.starter_store import register

    await h.execute(*h.attributed(), register(vocabulary()))


async def refused(work: Callable[[], Awaitable[Any]]) -> Exception | None:
    """What a route raised for `work`, or None when it answered."""
    try:
        await work()
    except Exception as exc:
        return exc
    return None


async def ledger(h: Harness, actor: str) -> list[tuple[str, str, str, str]]:
    """Every ledger entry attributed to `actor` in this transaction, in order: its action, its
    subject, and the change and team its details name, empty where they name none."""
    from brain.tables.audit import AuditEntryRow

    found = await h.execute(
        select(AuditEntryRow.action, AuditEntryRow.subject, AuditEntryRow.details)
        .where(AuditEntryRow.actor_id == actor)
        .order_by(AuditEntryRow.seq)
    )
    entries: list[tuple[str, str, str, str]] = []
    for action, subject, details in found.all():
        said = details if isinstance(details, dict) else {}
        entries.append(
            (str(action), str(subject), str(said.get("change", "")), str(said.get("team", "")))
        )
    return entries


def row_of(principal_id: str) -> str:
    """A person's row on the People screen: `brain.console.reads.PRINCIPAL_SUBJECT` and the id."""
    from brain.console.reads import PRINCIPAL_SUBJECT

    return f"{PRINCIPAL_SUBJECT}{principal_id}"


def listed(page: Any) -> dict[str, tuple[str, ...]]:
    """The People screen's rows, subject to capabilities."""
    return {one.subject: tuple(one.capabilities) for one in page.items}


async def people(c: Console, reader: str) -> dict[str, tuple[str, ...]]:
    """`GET /govern/people` as `reader`, signed in with an authenticator."""
    from brain.govern_routes import people_page
    from brain.listing import ListAsked

    asked = await c.asked(reader)
    with c.as_route():
        return listed(await people_page(c.request(), asked, ListAsked(limit=200)))


def held_at(reach: Any, capability: str, now: Any) -> Any:
    """The scope a reach holds `capability` over, or None."""
    from brain.core.entitlement import Capability

    return reach.scope_for(Capability(value=capability), now)


def holds_exactly(before: Any, after: Any) -> set[str]:
    """The capabilities `after` holds that `before` did not, by name. Both are the resolver's
    answers, so neither carries a lapsed grant."""
    return {one.capability.value for one in after.grants} - {
        one.capability.value for one in before.grants
    }


# --------------------------------------------- 1. the structure (M27.11.1, M27.3.2, M27.15.22)
@check(
    leaves=("M27.11.1", "M27.3.2", "M27.15.22"),
    sentence=(
        "An administrator creates both reserved departments from the console, renames one, adds, "
        "renames and retires a team, draws, renames and retires a scope, each in the ledger under "
        "them; Scopes lists both departments, a grant over one is written in the same session, "
        "and retiring it is refused in words until the grant is removed, then done."
    ),
)
async def departments_teams_and_scopes_are_shaped_from_the_console(h: Harness) -> None:
    from brain.console.organisation import A_DEPARTMENT_UNDER_LIVE_GRANTS_IS_NOT_RETIRED
    from brain.govern_people_routes import (
        DepartmentFounding,
        DepartmentRenaming,
        DepartmentRetirement,
        ScopeDrawing,
        ScopeRenaming,
        ScopeRetirement,
        TeamAdding,
        TeamRenaming,
        TeamRetirement,
        add_team,
        draw_scope,
        found_department,
        rename_department,
        rename_scope,
        rename_team,
        retire_department,
        retire_scope,
        retire_team,
    )
    from brain.govern_routes import GrantProposal, GrantRemoval, grant, remove_grant, scopes
    from brain.listing import ListAsked

    c = await console(h)
    founder, member = h.principal(A, "founder"), h.principal(B, "member")
    await h.person(founder, department=A, grants=everywhere(*administrator()))
    await h.person(member, department=B)
    asked = await c.asked(founder)
    request = c.request()
    names = {A: "Acceptance check A", B: "Acceptance check B"}

    with c.as_route():
        for slug in RESERVED_DEPARTMENTS:
            made = await found_department(
                request, DepartmentFounding(slug=slug, name=names[slug]), asked
            )
            if (made.kind, made.slug, made.change) != ("department", slug, "created"):
                raise CheckFailedError("a reserved department was not created from the console")
        listing = await scopes(request, asked, ListAsked(limit=200))
        shown = {one.slug for one in listing.items}
        if not {A, B} <= shown or not {A, B} <= set(listing.departments):
            raise CheckFailedError(
                "the Scopes screen did not list a department created from the console"
            )

        await rename_department(
            request,
            DepartmentRenaming(slug=A, expected_name=names[A], name="Acceptance check A renamed"),
            asked,
        )
        stale = await refused(
            lambda: rename_department(
                request,
                DepartmentRenaming(slug=A, expected_name=names[A], name="Acceptance check A again"),
                asked,
            )
        )
        if stale is None:
            raise CheckFailedError("a rename confirmed against a name since changed was written")

        team = "checked"
        await add_team(request, TeamAdding(department=A, slug=team, name="Checked"), asked)
        await rename_team(
            request,
            TeamRenaming(department=A, slug=team, expected_name="Checked", name="Checked twice"),
            asked,
        )
        await retire_team(
            request, TeamRetirement(department=A, slug=team, expected_name="Checked twice"), asked
        )

        drawn = f"{A}_checked"
        await draw_scope(
            request, ScopeDrawing(slug=drawn, label="Checked scope", departments=[A]), asked
        )
        await rename_scope(
            request,
            ScopeRenaming(slug=drawn, expected_label="Checked scope", label="Checked scope again"),
            asked,
        )
        predicate = next(
            (
                one.scope
                for one in (await scopes(request, asked, ListAsked(limit=200))).items
                if one.slug == drawn
            ),
            None,
        )
        if predicate is None:
            raise CheckFailedError("a scope drawn from the console was not listed")
        await retire_scope(request, ScopeRetirement(slug=drawn, expected_scope=predicate), asked)
        if drawn in {one.slug for one in (await scopes(request, asked, ListAsked())).items}:
            raise CheckFailedError("a retired scope was still listed")

        # Grantable in the same session it was created in (M27.15.22).
        await grant(
            request,
            GrantProposal(
                principal_id=member,
                capability=GRANTED,
                scope_slug=B,
                reason=REASON,
                not_after=lapses(h),
            ),
            asked,
        )
        retiring = DepartmentRetirement(slug=B, expected_name=names[B])
        held_back = await refused(lambda: retire_department(request, retiring, asked))
        if held_back is None or A_DEPARTMENT_UNDER_LIVE_GRANTS_IS_NOT_RETIRED.rstrip(".") not in (
            told(held_back)
        ):
            raise CheckFailedError("a department under a live grant was not refused retirement")
        await remove_grant(request, GrantRemoval(principal_id=member, capability=GRANTED), asked)
        gone = await retire_department(request, retiring, asked)
        if gone.change != "retired":
            raise CheckFailedError("a department with no live grant left was not retired")
        if B in {one.slug for one in (await scopes(request, asked, ListAsked())).items}:
            raise CheckFailedError("a retired department's scope was still offered")

    entries = set(await ledger(h, founder))
    shaped = "organisation"
    wanted = {
        (shaped, f"department:{A}", "created", ""),
        (shaped, f"department:{A}", "renamed", ""),
        (shaped, f"department:{B}", "created", ""),
        (shaped, f"department:{B}", "retired", ""),
        *((shaped, f"department:{A}", one, f"{A}.{team}") for one in STRUCTURE_CHANGES),
        *((shaped, f"scope:{drawn}", one, "") for one in STRUCTURE_CHANGES),
    }
    if not wanted <= entries:
        raise CheckFailedError("a change to the structure is not in the ledger under its maker")


# ------------------------------------------------- 2. granting within a scope (M27.7.3, M27.7.7)
@check(
    leaves=("M27.7.3", "M27.7.7"),
    sentence=(
        "An administrator of acceptance_a signed in with an authenticator grants a member of it a "
        "capability over acceptance_a: People lists the member holding it, the resolver gives "
        "them it over that scope, and nobody in acceptance_b is listed; a grant over acceptance_b, "
        "to its member, or of a capability they lack is refused; the removal takes it away; both "
        "are in the ledger under them."
    ),
)
async def a_capability_is_granted_and_removed_within_the_grantor_s_scope(h: Harness) -> None:
    from brain.govern_routes import GrantProposal, GrantRemoval, grant, remove_grant

    await h.found_departments()
    c = await console(h)
    lead, member, outsider = h.principal(A, "lead"), h.principal(A, "member"), h.principal(B, "one")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(member, department=A)
    await h.person(outsider, department=B, grants=within(B, GRANTED))
    asked = await c.asked(lead)
    request = c.request()

    def proposal(who: str, capability: str, scope: str) -> GrantProposal:
        return GrantProposal(
            principal_id=who,
            capability=capability,
            scope_slug=scope,
            reason=REASON,
            not_after=lapses(h),
        )

    with c.as_route():
        written = await grant(request, proposal(member, GRANTED, A), asked)
    if (written.principal_id, written.granted_by) != (member, lead):
        raise CheckFailedError("a grant was not written for the member as the grantor's act")
    shown = await people(c, lead)
    if GRANTED not in shown.get(row_of(member), ()):
        raise CheckFailedError("People did not list the member holding what they were granted")
    if row_of(outsider) in shown:
        raise CheckFailedError("People listed somebody outside the reader's department")
    reach = await h.reach(member)
    if held_at(reach, GRANTED, h.now) is None:
        raise CheckFailedError("the resolver did not give the member what they were granted")

    with c.as_route():
        for wider in (
            proposal(member, GRANTED, B),
            proposal(outsider, GRANTED, B),
            proposal(member, NOBODY_HERE_HOLDS, A),
        ):
            if await refused(partial(grant, request, wider, asked)) is None:
                raise CheckFailedError("a grant wider than the grantor's own was written")
        outside = GrantRemoval(principal_id=outsider, capability=GRANTED)
        if await refused(lambda: remove_grant(request, outside, asked)) is None:
            raise CheckFailedError("a grant outside the remover's department was removed")
        await remove_grant(request, GrantRemoval(principal_id=member, capability=GRANTED), asked)

    if GRANTED in (await people(c, lead)).get(row_of(member), ()):
        raise CheckFailedError("People still listed a capability that was removed")
    if held_at(await h.reach(member), GRANTED, h.now) is not None:
        raise CheckFailedError("the resolver still gave the member a capability that was removed")
    actions = {
        action for action, subject, _, _ in await ledger(h, lead) if subject.startswith("grant")
    }
    if not {"grant", "revoke"} <= actions:
        raise CheckFailedError("the grant and its removal are not in the ledger under the grantor")


# ------------------------------------------ 3. packs (M27.15.24, M27.15.20, M27.11.3)
@check(
    leaves=("M27.15.24", "M27.15.20", "M27.11.3"),
    sentence=(
        "An administrator creates a pack, versions it, copies it and retires the copy from the "
        "console, each in the ledger under them; assigning the pack over acceptance_a widens a "
        "member by exactly its capabilities, shown on their Access view as from that pack; "
        "removing one of them alone is refused with a sentence naming the pack, and so is "
        "retiring a pack somebody holds."
    ),
)
async def a_pack_is_written_assigned_and_removed_only_whole(h: Harness) -> None:
    from brain.directory_routes import person_page
    from brain.govern_pack_routes import (
        A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED,
        PackCopying,
        PackProposal,
        PackRetirement,
        PackVersioning,
        PackWriting,
        assign_pack,
        copy_pack,
        create_pack,
        retire_pack,
        version_pack,
    )
    from brain.govern_routes import GrantRemoval, remove_grant

    await h.found_departments()
    await registered_vocabulary(h)
    c = await console(h)
    writer, member = h.principal(A, "writer"), h.principal(A, "member")
    await h.person(writer, department=A, grants=everywhere(*administrator()))
    await h.person(member, department=A)
    asked = await c.asked(writer)
    request = c.request()
    slug, copy = f"acceptance_{h.run}", f"acceptance_{h.run}_copy"
    label = f"Acceptance check pack {h.run}"

    with c.as_route():
        made = await create_pack(
            request, PackWriting(slug=slug, label=label, capabilities=list(PACK_FIRST)), asked
        )
        moved = await version_pack(
            request,
            PackVersioning(
                slug=slug,
                expected_version=made.version,
                label=label,
                capabilities=list(PACK_SECOND),
            ),
            asked,
        )
        copied = await copy_pack(
            request, PackCopying(slug=slug, new_slug=copy, label=f"{label} copy"), asked
        )
        retired = await retire_pack(
            request, PackRetirement(slug=copy, expected_version=copied.version), asked
        )
    if (made.version, moved.version, copied.change, retired.change) != (
        1,
        2,
        "copied",
        "retired",
    ):
        raise CheckFailedError("a pack was not created, versioned, copied and retired in turn")

    before = await h.reach(member)
    with c.as_route():
        await assign_pack(
            request,
            PackProposal(
                principal_id=member,
                pack_slug=slug,
                scope_slug=A,
                reason=REASON,
                not_after=lapses(h),
            ),
            asked,
        )
    after = await h.reach(member)
    if holds_exactly(before, after) != set(PACK_SECOND):
        raise CheckFailedError("assigning a pack did not widen the member by exactly the pack")
    with c.as_route():
        page = await person_page(c.request(), member, asked)
    if not any(one.kind == "pack" and one.pack == slug for one in page.held):
        raise CheckFailedError("the member's Access view did not show what came from the pack")

    with c.as_route():
        alone = GrantRemoval(principal_id=member, capability=PACK_SECOND[0])
        single = await refused(lambda: remove_grant(request, alone, asked))
        if single is None or label not in told(single):
            raise CheckFailedError("removing one capability of a pack was not refused naming it")
        held = await refused(
            lambda: retire_pack(
                request, PackRetirement(slug=slug, expected_version=moved.version), asked
            )
        )
        if held is None or A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED not in told(held):
            raise CheckFailedError("a pack somebody holds was retired, or refused unsaid")

    written = [(action, subject, change) for action, subject, change, _ in await ledger(h, writer)]
    if [one for one in written if one[0] == "pack"] != [
        ("pack", f"pack:{slug}", "created"),
        ("pack", f"pack:{slug}", "versioned"),
        ("pack", f"pack:{copy}", "created"),
        ("pack", f"pack:{copy}", "retired"),
    ]:
        raise CheckFailedError("the pack's writes are not each in the ledger under the writer")


# ------------------------------------------------------- 4. roles (M27.7.5, M27.11.3)
@check(
    leaves=("M27.7.5", "M27.11.3"),
    sentence=(
        "Roles answers the six roles and what each is for; an administrator of acceptance_a "
        "appoints a member as Approver over acceptance_a, who is then listed as holding it to them "
        "and not to acceptance_b's administrator, and an appointment over acceptance_b is refused."
    ),
)
async def roles_are_appointed_over_a_scope_and_shown_where_holders_sit(h: Harness) -> None:
    from brain.govern_role_routes import Appointment, appoint_role, holders
    from brain.govern_routes import roles
    from brain.identity.roles import ROLE_COUNT, Role

    await h.found_departments()
    c = await console(h)
    lead, member = h.principal(A, "lead"), h.principal(A, "member")
    other = h.principal(B, "lead")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(other, department=B, grants=within(B, *administrator()))
    await h.person(member, department=A)
    asked = await c.asked(lead)
    request = c.request()

    with c.as_route():
        catalogue = await roles(asked)
    if len(catalogue.roles) != ROLE_COUNT or any(not one.exists_to for one in catalogue.roles):
        raise CheckFailedError("Roles did not answer the six roles and what each is for")

    with c.as_route():
        appointed = await appoint_role(
            request,
            Appointment(principal_id=member, role=Role.APPROVER, scope_slug=A, reason=REASON),
            asked,
        )
        wider = Appointment(principal_id=member, role=Role.APPROVER, scope_slug=B, reason=REASON)
        if await refused(lambda: appoint_role(request, wider, asked)) is None:
            raise CheckFailedError("an appointment over another department was written")
        own = await holders(request, asked)
    if appointed.change != "appointed" or not any(
        one.principal_id == member and one.role == Role.APPROVER.value for one in own.items
    ):
        raise CheckFailedError("an appointed Approver was not listed to the appointer")
    elsewhere = await c.asked(other)
    with c.as_route():
        theirs = await holders(request, elsewhere)
    if any(one.principal_id == member for one in theirs.items):
        raise CheckFailedError("a role holder was listed to a reader outside their department")


# ------------------------------------------------------------ 5. a person by hand (M27.15.19)
#: Why the hand-added person is proved only on an install reading no staff list.
A_STAFF_LIST_IS_READ_HERE: Final = (
    "this install reads its people from a staff list, so nobody is added by hand here; the "
    "console refused the addition in words, and the rest needs an install that reads none"
)


@check(
    leaves=("M27.15.19",),
    sentence=(
        "On an install reading no staff list, an administrator of acceptance_a adds a person to it "
        "by hand from the console, links them to a sign-in, grants them a capability over "
        "acceptance_a and places them in a team; the person then signs in and holds it. Where a "
        "staff list is read the addition is refused in words and the check says it was not run."
    ),
)
async def a_person_added_by_hand_signs_in_and_holds_their_grant(h: Harness) -> None:
    from brain.directory_routes import (
        PEOPLE_ARRIVE_FROM_THE_STAFF_SOURCE,
        PersonAdding,
        add_person,
        reads_a_staff_list,
    )
    from brain.govern_people_routes import MembershipChange, TeamAdding, add_team, change_membership
    from brain.govern_routes import GrantProposal, grant

    await h.found_departments()
    c = await console(h)
    lead = h.principal(A, "lead")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    asked = await c.asked(lead)
    request = c.request()
    adding = PersonAdding(display_name="Acceptance check by hand", department=A)

    if reads_a_staff_list():
        with c.as_route():
            said = await refused(lambda: add_person(request, adding, asked))
        if said is None or PEOPLE_ARRIVE_FROM_THE_STAFF_SOURCE.rstrip(".") not in told(said):
            raise CheckFailedError("a person was added by hand beside a staff list")
        raise CheckNotRunError(A_STAFF_LIST_IS_READ_HERE)

    with c.as_route():
        added = await add_person(request, adding, asked)
        outside = PersonAdding(display_name="Acceptance check by hand", department=B)
        if await refused(lambda: add_person(request, outside, asked)) is None:
            raise CheckFailedError("a person was added in a department the adder does not govern")
    person = added.principal_id
    signed_in = await c.asked(person, strong=False)
    if signed_in.caller.principal_id != person:
        raise CheckFailedError("a person added by hand and linked could not sign in")
    with c.as_route():
        await grant(
            request,
            GrantProposal(
                principal_id=person,
                capability=GRANTED,
                scope_slug=A,
                reason=REASON,
                not_after=lapses(h),
            ),
            asked,
        )
        await add_team(request, TeamAdding(department=A, slug="checked", name="Checked"), asked)
        await change_membership(
            request,
            MembershipChange(principal_id=person, department=A, team="checked", change="join"),
            asked,
        )
    again = await c.asked(person, strong=False)
    if held_at(again.reach, GRANTED, h.now) is None:
        raise CheckFailedError("a person added by hand did not hold what they were granted")
