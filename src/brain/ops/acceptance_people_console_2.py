"""Install acceptance checks for sessions, sign-in links, sign-in strength, the ledger and exports.

The second half of the people and access leaves: what a person signed in holds back, the controls
that end a session and unlink a sign-in, the ledger read and exported by people who may read part of
it, and service accounts' keys. Each check drives the routes the console's pages call, signed in
through the install's own gate (`brain.ops.acceptance_people_signed_in`), so the token's `amr`, the
session row `asking` records and the ceilings it applies are the install's, in the harness's
transaction, which is always rolled back.

**A control is followed to the request after it.** Ending a session and unlinking a sign-in are
proved by the next request that session or that person makes being refused at the gate, and a key's
revocation by the key being refused, because a control whose row changed and whose holder kept
working is the failure each of these screens exists to prevent.

**What one reader is shown is compared with what another is, never counted.** The ledger narrowed
to an actor whose entries the reader may not see answers exactly what an actor nobody is answers;
an export and a certification report carry the exporter's department's rows and none of the other's
and no line about the rest.

**The second factor's realm half is the owner's.** Whether the realm puts an authenticator in the
token is decided by a person signing in to it; the check proves the install's half with a token
carrying what the realm's mapper writes, then asks the install whether anybody has opened a console
session with a second factor, and says it was not run until somebody has.

Task ids: M27.7.10, M27.7.11, M27.9.1, M27.9.2, M27.15.60
Task ids: M27.15.66, M27.7.13, M27.9.4, M27.11.5, M27.15.21
"""

from __future__ import annotations

import json
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_people_console import GRANTED, REASON, lapses, ledger, refused
from brain.ops.acceptance_people_signed_in import (
    Console,
    administrator,
    console,
    everywhere,
    told,
    within,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.scope import Scope

#: Where this module's checks stand on the Install page, after the first people module's.
CHECK_ORDER: Final = 312

A, B = RESERVED_DEPARTMENTS

#: The verbs a sign-in without a second factor withholds from an administrator, by
#: `brain.gate.admission.ASSURANCE_VERBS`: everything it holds except reading, changing and running.
WITHHELD_FROM_A_PASSWORD: Final = ("admin", "approve")

#: Why the realm half of the second factor is the owner's to show.
NOBODY_HAS_SIGNED_IN_WITH_AN_AUTHENTICATOR: Final = (
    "the install answers a token naming an authenticator with the admin and approve verbs, but "
    "nobody has opened a console session here with a second factor yet; sign in once with an "
    "authenticator and the next run shows the realm reporting it"
)

#: What opens the audit trail's screen, held over everything: the screen's read and its plane.
AUDIT_SCREEN: Final = ("read:audit", "read:console.configuration")

#: What reads the ledger's grant entries. Scoped on the ledger's own fields, since an entry carries
#: no department (`brain.audit.view._scope_row`), so an auditor of part of the install is one whose
#: grant names whose acts they read.
GRANT_ENTRIES: Final = "read:audit.grant"

#: What taking an export needs over everything (`brain.ops.data_transfer.may_export`).
EXPORT_AUTHORITY: Final = "admin:export"

#: What a reader's export is asked for: a window around the check, and a reference of its own.
EXPORT_WINDOW: Final = timedelta(minutes=5)
EXPORT_REFERENCE: Final = "ACCEPTANCE-CHECK"


async def granted(c: Console, grantor: str, member: str, department: str) -> None:
    """`POST /govern/grants` as `grantor`: `GRANTED` to `member` over `department`'s scope."""
    from brain.govern_routes import GrantProposal, grant

    asked = await c.asked(grantor)
    with c.as_route():
        await grant(
            c.request(),
            GrantProposal(
                principal_id=member,
                capability=GRANTED,
                scope_slug=department,
                reason=REASON,
                not_after=lapses(c.h),
            ),
            asked,
        )


def grants_by(actor: str) -> tuple[tuple[str, Scope], ...]:
    """`GRANT_ENTRIES` over the entries `actor` made: an auditor of one person's grants."""
    from brain.core.scope import Clause, Op, Scope

    return ((GRANT_ENTRIES, Scope(clauses=(Clause(field="actor_id", op=Op.EQ, value=actor),))),)


async def gate_refuses(c: Console, principal_id: str, **how: Any) -> bool:
    """Whether the install's gate refuses `principal_id`'s request made as `how` says."""
    from brain.identity.oidc import TokenRefusedError

    try:
        await c.asked(principal_id, **how)
    except TokenRefusedError:
        return True
    return False


# ------------------------------------------------------------- 1. sessions (M27.7.10)
@check(
    leaves=("M27.7.10",),
    sentence=(
        "A member of acceptance_a signs in, and an administrator of acceptance_a signed in with an "
        "authenticator sees that session on Sessions and not one in acceptance_b; they end it, "
        "it is in the ledger under them, and the member's next request on that session is refused "
        "by the gate while a new sign-in is not; ending acceptance_b's session is refused."
    ),
)
async def an_ended_session_is_refused_on_its_next_request(h: Harness) -> None:
    from brain.listing import ListAsked
    from brain.session_routes import SessionEnding, end_session, sessions_page

    await h.found_departments()
    c = await console(h)
    lead, member, outsider = h.principal(A, "lead"), h.principal(A, "member"), h.principal(B, "one")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(member, department=A)
    await h.person(outsider, department=B)
    theirs, elsewhere = c.session(), c.session()
    await c.asked(member, strong=False, session=theirs)
    await c.asked(outsider, strong=False, session=elsewhere)

    asked = await c.asked(lead)
    with c.as_route():
        listed = await sessions_page(c.request(), asked, ListAsked(limit=200))
    shown = {one.session_id for one in listed.items}
    if theirs not in shown or elsewhere in shown:
        raise CheckFailedError("Sessions did not list the department's session and only that")
    with c.as_route():
        outside = SessionEnding(session_id=elsewhere)
        if await refused(lambda: end_session(c.request(), outside, asked)) is None:
            raise CheckFailedError("a session outside the reader's department was ended")
        ended = await end_session(c.request(), SessionEnding(session_id=theirs), asked)
    if ended.session_id != theirs:
        raise CheckFailedError("the session asked for was not the one ended")
    if not await gate_refuses(c, member, strong=False, session=theirs):
        raise CheckFailedError("an ended session's next request was answered")
    if await gate_refuses(c, member, strong=False):
        raise CheckFailedError("ending one session refused the person's next sign-in")
    ended_by = {(action, subject) for action, subject, _, _ in await ledger(h, lead)}
    if ("session_end", f"principal:{member}") not in ended_by:
        raise CheckFailedError("ending a session is not in the ledger under who ended it")


# --------------------------------------------------------- 2. sign-in links (M27.7.11)
@check(
    leaves=("M27.7.11",),
    sentence=(
        "An administrator of the whole install signed in with an authenticator sees a member of "
        "acceptance_a on Sign-in links with when they were linked, unlinks them, and the "
        "member's next request is refused by the gate; the unlinking is in the ledger under them."
    ),
)
async def an_unlinked_sign_in_is_refused_on_its_next_request(h: Harness) -> None:
    from brain.listing import ListAsked
    from brain.session_routes import UnlinkAsked, sign_in_links_page, unlink_sign_in

    await h.found_departments()
    c = await console(h)
    keeper, member = h.principal(A, "keeper"), h.principal(A, "member")
    await h.person(keeper, department=A, grants=everywhere(*administrator()))
    await h.person(member, department=A)
    if await gate_refuses(c, member, strong=False):
        raise CheckFailedError("a linked member could not sign in")

    asked = await c.asked(keeper)
    with c.as_route():
        links = await sign_in_links_page(c.request(), asked, ListAsked(search=member, limit=200))
    if not any(one.principal_id == member and one.linked_at for one in links.items):
        raise CheckFailedError("Sign-in links did not list a linked member with when")
    with c.as_route():
        answered = await unlink_sign_in(c.request(), UnlinkAsked(principal_id=member), asked)
    if answered.status_code != 200:
        raise CheckFailedError("a member's sign-in link was not unlinked")
    if not await gate_refuses(c, member, strong=False):
        raise CheckFailedError("an unlinked person's next request was answered")
    if not any(member in subject for _, subject, _, _ in await ledger(h, keeper)):
        raise CheckFailedError("unlinking a sign-in is not in the ledger under who unlinked it")


# ------------------------------------- 3. what a sign-in holds back (M27.9.2, M27.15.60, M27.15.66)
@check(
    leaves=("M27.9.2", "M27.15.60", "M27.15.66"),
    sentence=(
        "An administrator of acceptance_a signed in without an authenticator is told by /me that "
        "this sign-in holds back administration and approvals and that signing in again gives "
        "them back; with one, nothing is held back; a member is told nothing. Refused ending a "
        "session that exists and one that does not, they are told the same sentence about the "
        "sign-in for both."
    ),
)
async def a_sign_in_without_a_second_factor_is_told_what_it_holds_back(h: Harness) -> None:
    from brain.api_routes import me, second_factor_needed
    from brain.session_routes import SessionEnding, end_session

    await h.found_departments()
    c = await console(h)
    lead, member = h.principal(A, "lead"), h.principal(A, "member")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(member, department=A, grants=within(A, GRANTED))
    theirs = c.session()
    await c.asked(member, strong=False, session=theirs)

    weak = await me(await c.asked(lead, strong=False))
    if (weak.assurance, tuple(weak.withheld_verbs), weak.second_factor_needed) != (
        "authenticated",
        WITHHELD_FROM_A_PASSWORD,
        True,
    ):
        raise CheckFailedError("a password sign-in was not told which verbs it holds back")
    strong = await me(await c.asked(lead))
    if (strong.assurance, strong.withheld_verbs, strong.second_factor_needed) != (
        "strong",
        [],
        False,
    ):
        raise CheckFailedError("a sign-in with an authenticator was told something is held back")
    plain = await me(await c.asked(member, strong=False))
    if plain.withheld_verbs or plain.second_factor_needed:
        raise CheckFailedError("a member holding only reads was told to sign in again")

    said: list[tuple[str, bool]] = []
    for session in (theirs, f"acceptance-{h.run}-nobody"):
        asked = await c.asked(lead, strong=False)
        request = c.last
        with c.as_route():
            exc = await refused(
                partial(end_session, c.request(), SessionEnding(session_id=session), asked)
            )
        if exc is None or request is None:
            raise CheckFailedError("an administrator without a second factor ended a session")
        said.append((told(exc), second_factor_needed(request)))
    if said[0] != said[1] or not said[0][1]:
        raise CheckFailedError("a refusal to a password sign-in changed with what was asked about")


# ------------------------------------------------------- 4. the realm's second factor (M27.9.1)
@check(
    leaves=("M27.9.1",),
    sentence=(
        "A token naming an authenticator, as the realm's amr mapper writes it, gives an "
        "administrator of acceptance_a the admin and approve verbs and ends a session; then the "
        "install is asked whether anybody has opened a console session here with a second "
        "factor, and the check is not run until somebody has."
    ),
)
async def a_second_factor_reported_by_the_realm_admits_administration(h: Harness) -> None:
    from brain.core.entitlement import Capability
    from brain.gate.admission import Assurance
    from brain.gate.context import Channel
    from brain.ops.acceptance import RESERVED_PRINCIPAL_PREFIX
    from brain.session_routes import SessionEnding, end_session
    from brain.tables.identity import SessionRow

    await h.found_departments()
    c = await console(h)
    lead, member = h.principal(A, "lead"), h.principal(A, "member")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(member, department=A)
    theirs = c.session()
    await c.asked(member, strong=False, session=theirs)

    asked = await c.asked(lead)
    if asked.caller.assurance is not Assurance.STRONG or asked.channel is not Channel.CONSOLE:
        raise CheckFailedError("a console token naming an authenticator was not read as strong")
    for verb in ("admin:session", "approve:grant"):
        if asked.reach.scope_for(Capability(value=verb), asked.now) is None:
            raise CheckFailedError("a strong sign-in was not admitted the admin and approve verbs")
    with c.as_route():
        await end_session(c.request(), SessionEnding(session_id=theirs), asked)

    width = len(RESERVED_PRINCIPAL_PREFIX)
    seen = await h.execute(
        select(func.count())
        .select_from(SessionRow)
        .where(
            SessionRow.channel == Channel.CONSOLE.value,
            SessionRow.assurance >= int(Assurance.STRONG),
            func.left(SessionRow.principal_id, width) != RESERVED_PRINCIPAL_PREFIX,
        )
    )
    if not int(seen.scalar_one()):
        raise CheckNotRunError(NOBODY_HAS_SIGNED_IN_WITH_AN_AUTHENTICATOR)


# ------------------------------------------------------------------- 5. the ledger (M27.7.13)
@check(
    leaves=("M27.7.13",),
    sentence=(
        "An auditor whose grant reads acceptance_a's administrator's acts reads the ledger "
        "narrowed to them and sees their grant; narrowed to acceptance_b's administrator they are "
        "answered exactly what an actor nobody is gets, with no word or count of what was left "
        "out, while an auditor of the whole install sees that administrator's grant."
    ),
)
async def the_ledger_narrows_by_actor_without_naming_what_is_withheld(h: Harness) -> None:
    from brain.audit_routes import Order, audit_page

    await h.found_departments()
    c = await console(h)
    lead, other = h.principal(A, "lead"), h.principal(B, "lead")
    mine, theirs = h.principal(A, "member"), h.principal(B, "member")
    auditor, whole = h.principal(A, "auditor"), h.principal(B, "auditor")
    await h.person(lead, department=A, grants=within(A, *administrator()))
    await h.person(other, department=B, grants=within(B, *administrator()))
    await h.person(mine, department=A)
    await h.person(theirs, department=B)
    await h.person(auditor, department=A, grants=(*everywhere(*AUDIT_SCREEN), *grants_by(lead)))
    await h.person(whole, department=B, grants=everywhere(*AUDIT_SCREEN, GRANT_ENTRIES))
    await granted(c, lead, mine, A)
    await granted(c, other, theirs, B)

    async def page(reader: str, actor: str) -> Any:
        asked = await c.asked(reader, strong=False)
        with c.as_route():
            return await audit_page(
                c.request(),
                asked,
                action=None,
                subject_kind=None,
                actor=actor,
                since=None,
                until=None,
                order=Order.NEWEST,
                cursor=None,
                limit=50,
                q="",
                subject_id=None,
                changes_only=False,
            )

    own = await page(auditor, lead)
    if not own.items or any(one.actor_id != lead for one in own.items):
        raise CheckFailedError("an auditor did not read their department's administrator's grant")
    withheld = await page(auditor, other)
    nobody = await page(auditor, h.principal(B, "nobody"))
    if withheld.model_dump() != nobody.model_dump() or withheld.items:
        raise CheckFailedError("the ledger answered a withheld actor unlike an actor nobody is")
    if not (await page(whole, other)).items:
        raise CheckFailedError("an auditor of the whole install did not read the other's grant")


# --------------------------------------------- 6. the first administrator's screens (M27.9.4)
@check(
    leaves=("M27.9.4",),
    sentence=(
        "An administrator holding what the first administrator is granted opens Routing and the "
        "price list's Classification; an exporter whose grant reads their own acts takes an "
        "audit export of the last minutes that carries their grant, none of acceptance_b's "
        "administrator's, and no figure for what it left out."
    ),
)
async def the_first_administrator_opens_routing_and_exports_what_they_read(h: Harness) -> None:
    from brain.classification_routes import classification
    from brain.data_transfer_routes import ExportAsked, take_export
    from brain.knowledge.columns import PRICE_LIST
    from brain.listing import ListAsked
    from brain.ops.export import ExportReason
    from brain.routing_routes import rungs
    from brain.tables.data_export import ExportDataSet

    await h.found_departments()
    c = await console(h)
    first, exporter = h.principal(A, "first"), h.principal(A, "exporter")
    other, mine, theirs = h.principal(B, "lead"), h.principal(A, "member"), h.principal(B, "member")
    await h.person(first, department=A, grants=everywhere(*administrator()))
    await h.person(
        exporter,
        department=A,
        grants=(
            *within(A, "approve:grant", GRANTED),
            *everywhere(EXPORT_AUTHORITY, *AUDIT_SCREEN),
            *grants_by(exporter),
        ),
    )
    await h.person(other, department=B, grants=within(B, *administrator()))
    await h.person(mine, department=A)
    await h.person(theirs, department=B)

    asked = await c.asked(first)
    with c.as_route():
        await rungs(c.request(), asked, ListAsked())
        await classification(c.request(), PRICE_LIST.entity, asked)

    await granted(c, exporter, mine, A)
    await granted(c, other, theirs, B)
    asked = await c.asked(exporter)
    with c.as_route():
        answered = await take_export(
            c.request(),
            ExportAsked(
                data_set=ExportDataSet.AUDIT_TRAIL.value,
                reason=ExportReason.INTERNAL_INVESTIGATION.value,
                reason_reference=EXPORT_REFERENCE,
                since=h.now - EXPORT_WINDOW,
                until=h.now + EXPORT_WINDOW,
            ),
            asked,
        )
    if answered.status_code != 200:
        raise CheckFailedError("an exporter of one department could not take an audit export")
    taken = json.loads(bytes(answered.body))
    lines = [json.loads(one) for one in taken["document"].splitlines() if one.strip()]
    said = json.dumps(lines)
    if exporter not in said or other in said or theirs in said:
        raise CheckFailedError("the export did not carry the exporter's department and only it")
    if any(word in said for word in ("withheld", "omitted", "hidden")):
        raise CheckFailedError("the export said something about the entries it left out")


# ----------------------------------------------------------- 7. service accounts (M27.11.5)
@check(
    leaves=("M27.11.5",),
    sentence=(
        "An integrator in acceptance_a registers a service account on the console and issues it "
        "a key, shown in that answer and on no page after; the key is answered by the gate, a "
        "second key replaces it, the first is revoked and refused while the second is answered, "
        "and retiring the account refuses the second."
    ),
)
async def a_service_account_key_is_shown_once_rotated_and_revoked(h: Harness) -> None:
    from brain.listing import ListAsked
    from brain.service_account_routes import (
        AccountAsked,
        AccountRetirement,
        KeyAsked,
        KeyRevocation,
        accounts_page,
        issue_key,
        register_account,
        retire_account,
        revoke_key,
    )

    await h.found_departments()
    c = await console(h)
    owner = h.principal(A, "integrator")
    await h.person(owner, department=A, grants=within(A, "admin:credential", GRANTED))
    client_id = f"svc_acceptance_{h.run}"
    lapses_at = lapses(h)
    asked = await c.asked(owner)

    async def key(label: str) -> dict[str, Any]:
        with c.as_route():
            made = await issue_key(
                c.request(),
                KeyAsked(client_id=client_id, label=label, not_after=lapses_at),
                asked,
            )
        if made.status_code != 201:
            raise CheckFailedError("a service account's owner could not issue it a key")
        issued: dict[str, Any] = json.loads(bytes(made.body))
        return issued

    with c.as_route():
        registered = await register_account(
            c.request(),
            AccountAsked(client_id=client_id, ceiling=[GRANTED], not_after=lapses_at),
            asked,
        )
    if registered.status_code != 201:
        raise CheckFailedError("a service account could not be registered on the console")
    first = await key("first")
    with c.as_route():
        page = await accounts_page(c.request(), asked, ListAsked())
    if first["key"] in page.model_dump_json() or not any(
        one.client_id == client_id and first["handle"] in {k.handle for k in one.keys}
        for one in page.items
    ):
        raise CheckFailedError("a key was not listed by its handle alone after it was shown")
    if await gate_refuses(c, client_id, bearer=first["key"]):
        raise CheckFailedError("a live key was refused by the gate")
    second = await key("second")
    with c.as_route():
        await revoke_key(c.request(), KeyRevocation(handle=first["handle"]), asked)
    if not await gate_refuses(c, client_id, bearer=first["key"]):
        raise CheckFailedError("a revoked key was answered")
    if await gate_refuses(c, client_id, bearer=second["key"]):
        raise CheckFailedError("the key that replaced a revoked one was refused")
    with c.as_route():
        await retire_account(c.request(), AccountRetirement(client_id=client_id), asked)
    if not await gate_refuses(c, client_id, bearer=second["key"]):
        raise CheckFailedError("a retired account's key was answered")


# --------------------------------------------------------- 8. certification and lists (M27.15.21)
@check(
    leaves=("M27.15.21",),
    sentence=(
        "An administrator of acceptance_a takes the access certification report: it is recorded "
        "under them and carries their member's grant, nothing of acceptance_b and no line about "
        "what it left out; the people list and the departments list they export from carry "
        "acceptance_a's and none of acceptance_b's."
    ),
)
async def the_certification_and_lists_export_only_what_the_exporter_reads(h: Harness) -> None:
    from brain.certification_export_routes import (
        COLUMNS,
        CertificationAsked,
        export_certification,
    )
    from brain.directory_routes import directory
    from brain.govern_people_routes import departments_page
    from brain.listing import ListAsked
    from brain.ops.export import ExportReason

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
        answered = await export_certification(
            c.request(),
            CertificationAsked(
                reason=ExportReason.INTERNAL_INVESTIGATION, reason_reference=EXPORT_REFERENCE
            ),
            asked,
        )
    taken = json.loads(bytes(answered.body))
    rows = [one.split(",") for one in taken["document"].splitlines()]
    if rows[0] != list(COLUMNS):
        raise CheckFailedError("the certification report did not begin with its header")
    report = taken["document"]
    if GRANTED not in report or "Acceptance check member" not in report or B in report:
        raise CheckFailedError("the report did not carry its department's grant and only that")
    recorded = [
        one
        for one in await ledger(h, lead)
        if one[0] == "publish" and one[1].startswith("artifact:")
    ]
    if len(recorded) != 1:
        raise CheckFailedError("the certification report is not in the ledger under its taker")

    with c.as_route():
        people = await directory(c.request(), asked, ListAsked(limit=200))
        departments = await departments_page(c.request(), asked, ListAsked(limit=200))
    listed = {one.principal_id for one in people.items}
    if mine not in listed or theirs in listed:
        raise CheckFailedError("the people list carried somebody outside the reader's department")
    named = {one.slug for one in departments.items}
    if A not in named or B in named:
        raise CheckFailedError("the departments list carried a department the reader cannot reach")
