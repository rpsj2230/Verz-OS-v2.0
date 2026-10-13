"""Install acceptance checks for the people screens, through the install's own gate.

Each check signs a reserved person in as `brain.ops.acceptance_people_signed_in` does (the realm's
signing key is the one thing stood in for) and calls the route the console page calls, so the
reader a route sees is the one the install's gate produces. **Nothing is committed**: the sign-in
bindings, the sessions the gate records and every ledger entry are in the check's own transaction.

Task ids: M27.15.25
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_people_console import ledger
from brain.ops.acceptance_people_console_2 import gate_refuses
from brain.ops.acceptance_people_signed_in import administrator, console, everywhere
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 910

A, B = RESERVED_DEPARTMENTS


# ------------------------------------------------- 1. a person's sessions and sign-in (M27.15.25)
@check(
    leaves=("M27.15.25",),
    sentence=(
        "A member signed in twice has both sessions on Sessions for an administrator of the whole "
        "install, who ends them in one request, each in the ledger under them; the gate refuses "
        "each and admits a new sign-in. A sign-in unlinked by mistake is bound again to the same "
        "person, and both acts are in the ledger."
    ),
)
async def every_session_of_a_person_ends_and_a_wrong_unlink_is_undone(h: Harness) -> None:
    from brain.listing import ListAsked
    from brain.session_routes import (
        SessionsEnding,
        UnlinkAsked,
        end_sessions,
        sessions_page,
        unlink_sign_in,
    )
    from brain.sign_in_routes import SignInAsked, bind_sign_in

    await h.found_departments()
    c = await console(h)
    keeper, member = h.principal(A, "keeper"), h.principal(A, "member")
    await h.person(keeper, department=A, grants=everywhere(*administrator()))
    await h.person(member, department=A)
    first, second = c.session(), c.session()
    await c.asked(member, strong=False, session=first)
    await c.asked(member, strong=False, session=second)

    asked = await c.asked(keeper)
    with c.as_route():
        listed = await sessions_page(c.request(), asked, ListAsked(search=member, limit=200))
    theirs = sorted(one.session_id for one in listed.items if one.principal_id == member)
    if theirs != sorted((first, second)):
        raise CheckFailedError("Sessions did not list both of one person's sessions")
    with c.as_route():
        ended = await end_sessions(c.request(), SessionsEnding(session_ids=theirs), asked)
    if sorted(one.session_id for one in ended.outcomes if one.ended) != theirs:
        raise CheckFailedError("one request did not end every session of the person")
    for one in (first, second):
        if not await gate_refuses(c, member, strong=False, session=one):
            raise CheckFailedError("an ended session's next request was answered")
    if await gate_refuses(c, member, strong=False):
        raise CheckFailedError("ending every session refused the person's next sign-in")
    endings = [
        subject for action, subject, _, _ in await ledger(h, keeper) if action == "session_end"
    ]
    if endings.count(f"principal:{member}") != 2:
        raise CheckFailedError("each session's ending is not in the ledger under who ended it")

    subject = c._subjects[member]
    with c.as_route():
        unlinked = await unlink_sign_in(c.request(), UnlinkAsked(principal_id=member), asked)
    if unlinked.status_code != 200 or not await gate_refuses(c, member, strong=False):
        raise CheckFailedError("a member's sign-in was not unlinked")
    with c.as_route():
        relinked = await bind_sign_in(
            c.request(), asked, SignInAsked(subject=subject, principal_id=member)
        )
    if relinked.status_code != 200:
        raise CheckFailedError("an unlinked sign-in could not be bound to the same person again")
    if await gate_refuses(c, member, strong=False):
        raise CheckFailedError("a sign-in bound again was not admitted as the same person")
    kept = [
        subject_of
        for action, subject_of, _, _ in await ledger(h, keeper)
        if member in subject_of and action != "session_end"
    ]
    if len(kept) < 2:
        raise CheckFailedError("the unlinking and the binding are not both in the ledger")
