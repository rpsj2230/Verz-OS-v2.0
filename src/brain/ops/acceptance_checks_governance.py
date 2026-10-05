"""The install acceptance checks for the governance surfaces: what each role may do, and no more.

M33 is the role surfaces: what a Super Admin, a department admin, a member and an auditor are each
offered, and the refusal everybody else meets. Every leaf here was built and wired before a check
named it, so each check is the screen's own route function called as the reader the leaf names, in
the order the screen calls it, against the install's own database, inside the check's rolled-back
transaction.

**Each reader is a reserved principal holding exactly the grants their role means.** A Super Admin
holds the grant decision and the screens it opens everywhere; a department admin holds the same in
acceptance_a alone; an auditor holds the audit screen everywhere; a member holds the member screen.
Nobody here is given a role row to be read as one, because no route asks a role: every route asks
a capability in a scope, which is what `brain.identity.roles` says a role is for. See
`A_ROLE_IS_THE_GRANTS_IT_MEANS_AND_NO_ROW_OF_ITS_OWN`.

**Every reader is signed in with a second factor.** A Super Admin's and a department admin's
writes are `approve:` and `admin:` verbs, which `brain.gate.admission` admits only to a sign-in
with one, so a check reading as a weaker sign-in would prove the refusal and nothing else. See
`AN_ADMINISTRATOR_SIGNS_IN_WITH_A_SECOND_FACTOR`.

**Every refusal is asked beside the act it refuses.** A check that saw only the refusal would pass
a route that refuses everything, and one that saw only the act would pass a route that lets
everybody do it, so each check has both: the reader the leaf names does the thing, and a reader in
the other reserved department, holding the same grants there, is refused it.

**Publishing an agent is signed with a key the check makes.** The builder's publish needs the
install's template signing key, which lives in the vault and is read by the web process at start;
the worker running the checks has no copy, and a check reading the vault would be a check holding
a secret. So the check's application holds a key made for the check, as
`brain.ops.acceptance_workspace` signs its agents, and what is proved is the approval, which is
what the two publication leaves ask. See `A_PUBLICATION_IS_SIGNED_WITH_A_KEY_THE_CHECK_MAKES`.

Task ids: M38.5.1
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastapi import FastAPI

    from brain.console.reads import ConsoleRead

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 410

# ------------------------------------------------------------------ written-down reasons
#: Why no reader here holds a role row.
A_ROLE_IS_THE_GRANTS_IT_MEANS_AND_NO_ROW_OF_ITS_OWN: Final = (
    "No route asks whether somebody holds a role; each asks a capability in a scope. So each "
    "reader holds the grants their role means, everywhere for a Super Admin or an auditor and in "
    "acceptance_a for its admin, and a check passing is the install deciding by those grants."
)

#: Why every reader is admitted as a sign-in with a second factor.
AN_ADMINISTRATOR_SIGNS_IN_WITH_A_SECOND_FACTOR: Final = (
    "The grant decision and the builder's authority are approve and admin verbs, which the console "
    "admits only to a sign-in with a second factor. A reader admitted without one would be "
    "refused every write here, and the check would prove the refusal and nothing else."
)

#: Why the publication checks sign with their own key.
A_PUBLICATION_IS_SIGNED_WITH_A_KEY_THE_CHECK_MAKES: Final = (
    "The builder signs a published agent with the install's template key, which the web process "
    "reads from the vault and the worker never holds. The check's application holds a key made "
    "for the check, so what is proved is who may approve a publication and what it publishes."
)

#: Why a member's workspace is read with nobody named to the transaction first.
A_WORKSPACE_IS_READ_IN_A_TRANSACTION_THAT_NAMES_NOBODY_YET: Final = (
    "Everything a check does is one transaction, and resolving a reader's reach names them to "
    "it, which a request's own transaction is never told before its route tells it. A workspace "
    "read after that would find a member's own documents whether or not the route named them, "
    "so the name is cleared first and the route is what names the reader."
)

# ------------------------------------------------------------------------ the figures
#: What a department admin is shown and decides with, over their department alone.
GRANT_DECISION: Final = "approve:grant"

#: The capability a department admin grants a member of their department.
GRANTED: Final = "read:knowledge.title"

#: How long a grant the check writes lasts, inside the reserved principals' own hour.
GRANT_LASTS: Final = timedelta(minutes=30)

#: What an auditor reads the ledger with: every subject kind, as `brain.audit.view` names them.
EVERY_AUDIT_ENTRY: Final = "read:audit.*"

#: The persona every agent the check's drafts describe carries.
PERSONA: Final = "Answers an install acceptance check and nobody else."

#: Why each grant and role the check writes is written, as its row reads.
REASON: Final = "Written by an install acceptance check for the length of the check"


# ------------------------------------------------------------------------ the helpers
def _opens(read: ConsoleRead, scope: Scope) -> tuple[tuple[str, Scope], ...]:
    """The grants that open one screen over `scope`: its read and the plane the read is on."""
    from brain.console.reads import plane_capability_for

    return (
        (read.requires.value, scope),
        (plane_capability_for(read, read.plane).value, scope),
    )


def _app(h: Harness) -> FastAPI:
    """The state the governance routes read, over the check's transaction."""
    from fastapi import FastAPI

    app = FastAPI()
    app.state.settings = h.settings
    app.state.db_sessions = h.sessions
    return app


def _request(app: FastAPI) -> Any:
    from brain.ops.acceptance_threads import _request as made

    return made(app)


def _traced(h: Harness) -> None:
    """The check's trace id where a route reads the request's, for as long as the check runs."""
    import structlog

    structlog.contextvars.bind_contextvars(trace_id=h.trace_id)
    h.removes(lambda: structlog.contextvars.unbind_contextvars("trace_id"))


async def _asking(h: Harness, principal_id: str) -> Any:
    """What a route reads of a signed-in reader: who, at the reach the console admits, and when.

    Admitted as a sign-in with a second factor; see `AN_ADMINISTRATOR_SIGNS_IN_WITH_A_SECOND_
    FACTOR`. The instant is the check's transaction's own, `now()`, which is what every row a
    route writes is stamped with: the check's clock is read before its transaction begins, so a
    role appointed in the check would not yet be held at it, and a deputy reckoned from the wall
    clock would end after the thirty days its table allows from when it was written. A cast at
    the routes' boundary: a `Caller` is minted only from a verified token.
    """
    from sqlalchemy import func, select

    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    now = (await h.execute(select(func.now()))).scalar_one()
    return cast(
        "Any",
        SimpleNamespace(
            caller=SimpleNamespace(principal=person, principal_id=person.id),
            reach=reach,
            channel=Channel.CONSOLE,
            now=now,
        ),
    )


async def _refused(call: Any) -> bool:
    """Whether awaiting `call` was answered with the one refusal, `Absent`."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


def _slug(department: str) -> str:
    """The slug of the scope a reserved department is defined by."""
    from brain.console.organisation import founded

    return founded(department, f"Acceptance check {department[-1].upper()}")[1].slug


# ------------------------------------------------------------------ 1. disable (M33.1.2.4)
@check(
    leaves=("M33.1.2.4",),
    sentence=(
        "A Super Admin disables a member of acceptance_a through the People screen's route: the "
        "member is no longer a live person and holds nothing. The admin of acceptance_b, holding "
        "the same decision over their own department, is refused, and the Super Admin cannot "
        "disable themselves."
    ),
)
async def a_super_admin_disables_a_person_and_nobody_else_may(h: Harness) -> None:
    from brain.identity.principal_store import StoredPrincipals
    from brain.principal_state_routes import StateAsked, disable_person

    _traced(h)
    await h.found_departments()
    admin, member = h.principal(A, "super"), h.principal(A, "member")
    other = h.principal(B, "admin")
    await h.person(admin, department=A, grants=((GRANT_DECISION, Scope.unrestricted()),))
    await h.person(member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(other, department=B, grants=_in(B, GRANT_DECISION))
    request = _request(_app(h))

    if not await _refused(
        disable_person(request, StateAsked(principal_id=member), await _asking(h, other))
    ):
        raise CheckFailedError("an admin of another department disabled a member of acceptance_a")
    if await StoredPrincipals(h.sessions).live_principal(member) is None:
        raise CheckFailedError("a refused disable left the member disabled")
    themselves = await disable_person(
        request, StateAsked(principal_id=admin), await _asking(h, admin)
    )
    if themselves.status_code != 409:
        raise CheckFailedError("a Super Admin was not refused disabling themselves")

    done = await disable_person(request, StateAsked(principal_id=member), await _asking(h, admin))
    if done.status_code != 200:
        raise CheckFailedError("a Super Admin could not disable a member")
    if await StoredPrincipals(h.sessions).live_principal(member) is not None:
        raise CheckFailedError("a disabled member was still a live person")
    if (await h.reach(member)).grants:
        raise CheckFailedError("a disabled member still held grants")


# ------------------------------------------------------- 2. grant in scope (M33.2.2.2)
async def _grant(h: Harness, request: Any, by: str, to: str, capability: str, slug: str) -> bool:
    """`POST /govern/grants` as `by`: whether it wrote the grant rather than refusing."""
    from brain.core.errors import Absent
    from brain.govern_routes import GrantProposal, grant

    body = GrantProposal(
        principal_id=to,
        capability=capability,
        scope_slug=slug,
        reason=REASON,
        not_after=h.now + GRANT_LASTS,
    )
    try:
        written = await grant(request, body, await _asking(h, by))
    except Absent:
        return False
    return written.principal_id == to and written.capability == capability


@check(
    leaves=("M33.2.2.2",),
    sentence=(
        "The admin of acceptance_a grants a member a capability they hold over acceptance_a, "
        "through the People screen's route, and the member then holds it there. The same admin "
        "is refused that capability over acceptance_b and a capability they do not hold, and "
        "the member holds neither."
    ),
)
async def a_department_admin_grants_within_their_department_only(h: Harness) -> None:
    from brain.core.entitlement import Capability

    _traced(h)
    await h.found_departments()
    admin, member = h.principal(A, "admin"), h.principal(A, "member")
    await h.person(admin, department=A, grants=_in(A, GRANT_DECISION, GRANTED))
    await h.person(member, department=A)
    request = _request(_app(h))
    title, unheld = Capability(value=GRANTED), Capability(value="read:invoice.total")

    if await _grant(h, request, admin, member, GRANTED, _slug(B)):
        raise CheckFailedError("a department admin granted a capability over another department")
    if await _grant(h, request, admin, member, unheld.value, _slug(A)):
        raise CheckFailedError("a department admin granted a capability they do not hold")
    reach = await h.reach(member)
    if reach.scope_for(title, h.now) is not None or reach.scope_for(unheld, h.now) is not None:
        raise CheckFailedError("a refused grant left the member holding something")

    if not await _grant(h, request, admin, member, GRANTED, _slug(A)):
        raise CheckFailedError("a department admin could not grant within their department")
    held = (await h.reach(member)).scope_for(title, h.now)
    if held is None or held != Scope.department(A):
        raise CheckFailedError("a granted member did not hold the grant over the department")


# ----------------------------------------------------------- 3. a deputy (M33.2.2.5)
@check(
    leaves=("M33.2.2.5",),
    sentence=(
        "The admin of acceptance_a appoints an approver there and then a deputy to cover them for "
        "thirty days, through the Roles screen's routes, and the deputy's grant ends thirty days "
        "from now and covers that approver. Thirty-one days is refused, and so is the "
        "admin of acceptance_b deputising for an approver of acceptance_a."
    ),
)
async def a_department_admin_appoints_a_deputy_for_thirty_days_at_most(h: Harness) -> None:
    from pydantic import ValidationError

    from brain.govern_role_routes import (
        Appointment,
        DeputyAppointment,
        appoint_role,
        appoint_role_deputy,
    )
    from brain.identity.role_store import StoredRoles
    from brain.identity.roles import DEPUTY_MAX, Role

    _traced(h)
    await h.found_departments()
    admin, other = h.principal(A, "admin"), h.principal(B, "admin")
    holder, cover = h.principal(A, "approver"), h.principal(A, "cover")
    await h.person(admin, department=A, grants=_in(A, GRANT_DECISION))
    await h.person(other, department=B, grants=_in(B, GRANT_DECISION))
    for one in (holder, cover):
        await h.person(one, department=A)
    request = _request(_app(h))

    standing = await appoint_role(
        request,
        Appointment(principal_id=holder, role=Role.APPROVER, scope_slug=_slug(A), reason=REASON),
        await _asking(h, admin),
    )
    grant_id = uuid.UUID(standing.id)
    try:
        DeputyAppointment(
            grant_id=grant_id, principal_id=cover, days=DEPUTY_MAX.days + 1, reason=REASON
        )
    except ValidationError:
        pass
    else:
        raise CheckFailedError("a deputy for longer than thirty days was asked for and accepted")
    asked = DeputyAppointment(
        grant_id=grant_id, principal_id=cover, days=DEPUTY_MAX.days, reason=REASON
    )
    if not await _refused(appoint_role_deputy(request, asked, await _asking(h, other))):
        raise CheckFailedError("an admin of another department deputised for an approver here")

    appointing = await _asking(h, admin)
    deputy = await appoint_role_deputy(request, asked, appointing)
    row = await StoredRoles(h.sessions).one(uuid.UUID(deputy.id))
    if row is None or row.principal_id != cover or row.deputy_of != holder:
        raise CheckFailedError("the deputy appointed was not kept as cover for the approver")
    if row.not_after is None or row.not_after - appointing.now != DEPUTY_MAX:
        raise CheckFailedError("a deputy's grant did not end thirty days after it was made")


# --------------------------------------------------- 4. an orphaned agent (M33.2.2.3)
async def _left(h: Harness, leaver: str) -> None:
    """The staff roster marking `leaver` as having left, through their proven work address."""
    from sqlalchemy import insert

    from brain.gate.context import Channel
    from brain.identity.staff_roster import digest_of
    from brain.tables.identity import PrincipalIdentityRow
    from brain.tables.staff import StaffMemberRow

    address = digest_of(f"{leaver.rsplit('.', 1)[-1]}.{h.run}@acceptance.invalid")
    await h.execute(
        *h.attributed(),
        insert(PrincipalIdentityRow).values(
            channel=Channel.EMAIL.value, identity_hash=address, principal_id=leaver, bound_at=h.now
        ),
        insert(StaffMemberRow).values(
            source="acceptance",
            address_hash=address,
            display_name="Acceptance check leaver",
            department=A,
            first_listed_at=h.now - timedelta(days=1),
            last_listed_at=h.now - timedelta(days=1),
            left_at=h.now,
            left_because="source_says_left",
            status="left",
        ),
    )


async def _owner(h: Harness, agent_id: str) -> str | None:
    from brain.ops.acceptance_workspace import stored_agent

    return (await stored_agent(h, agent_id)).audience.owner_id


@check(
    leaves=("M33.2.2.3",),
    sentence=(
        "A member of acceptance_a owning an agent there is marked by the staff roster as having "
        "left: the agent waits for a new owner on the admin of acceptance_a's list and not on "
        "the admin of acceptance_b's, the second is refused taking it, and the first takes it "
        "and is its owner."
    ),
)
async def a_department_admin_adopts_an_agent_whose_owner_left(h: Harness) -> None:
    from brain.ops.acceptance_workspace import installed_agent
    from brain.staff_source_routes import staff_transfers, take_transfer

    _traced(h)
    await h.found_departments()
    leaver, admin = h.principal(A, "leaver"), h.principal(A, "admin")
    other = h.principal(B, "admin")
    await h.person(leaver, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(admin, department=A, grants=_in(A, GRANT_DECISION, *KNOWLEDGE_READS))
    await h.person(other, department=B, grants=_in(B, GRANT_DECISION, *KNOWLEDGE_READS))
    agent_id = await installed_agent(h, leaver, capabilities=KNOWLEDGE_READS)
    await _left(h, leaver)
    request = _request(_app(h))

    async def listed(who: str) -> list[str]:
        found = await staff_transfers(request, await _asking(h, who))
        return [one.agent_id for one in found.transfers]

    if agent_id not in await listed(admin):
        raise CheckFailedError("a leaver's agent was not waiting on its department admin's list")
    if agent_id in await listed(other):
        raise CheckFailedError("a leaver's agent was listed to another department's admin")
    if not await _refused(take_transfer(request, agent_id, await _asking(h, other))):
        raise CheckFailedError("another department's admin took a leaver's agent")
    if await _owner(h, agent_id) != leaver:
        raise CheckFailedError("a refused adoption changed the agent's owner")

    taken = await take_transfer(request, agent_id, await _asking(h, admin))
    if taken.owner_id != admin or await _owner(h, agent_id) != admin:
        raise CheckFailedError("a department admin who took a leaver's agent was not its owner")
    if agent_id in await listed(admin):
        raise CheckFailedError("an adopted agent still waited for a new owner")


# ------------------------------------------- 5. the same view, narrowed (M33.2.1.1)
@check(
    leaves=("M33.2.1.1",),
    sentence=(
        "A Super Admin and the admin of acceptance_a open the People and Roles screens through "
        "their routes: each answer has the same fields for both, the Super Admin's lists the "
        "people and role holders of both reserved departments, and the department admin's those "
        "of acceptance_a and none of acceptance_b."
    ),
)
async def a_department_admin_sees_the_super_admin_view_of_their_department(
    h: Harness,
) -> None:
    from brain.console.screens import screen
    from brain.govern_role_routes import Appointment, appoint_role, holders
    from brain.govern_routes import PEOPLE_SCREEN, ROLES_SCREEN, people_page
    from brain.identity.roles import Role
    from brain.listing import ListAsked

    _traced(h)
    await h.found_departments()
    opens = (screen(PEOPLE_SCREEN).read, screen(ROLES_SCREEN).read)

    def reading(scope: Scope) -> tuple[tuple[str, Scope], ...]:
        held = {GRANT_DECISION, *(one for read in opens for one, _ in _opens(read, scope))}
        return tuple((one, scope) for one in sorted(held))

    everywhere, here = Scope.unrestricted(), Scope.department(A)
    admin, super_admin = h.principal(A, "admin"), h.principal(A, "super")
    await h.person(super_admin, department=A, grants=reading(everywhere))
    await h.person(admin, department=A, grants=reading(here))
    people = {one: h.principal(one, "member") for one in RESERVED_DEPARTMENTS}
    for department, member in people.items():
        await h.person(member, department=department, grants=_in(department, GRANTED))
    request = _request(_app(h))
    for department, member in people.items():
        await appoint_role(
            request,
            Appointment(
                principal_id=member,
                role=Role.APPROVER,
                scope_slug=_slug(department),
                reason=REASON,
            ),
            await _asking(h, super_admin),
        )

    async def seen(who: str) -> tuple[Any, Any, set[str], set[str]]:
        asking = await _asking(h, who)
        page = await people_page(request, asking, ListAsked(limit=200))
        held = await holders(request, asking)
        return (
            page,
            held,
            {one.subject.rsplit(":", 1)[-1] for one in page.items},
            {one.principal_id for one in held.items},
        )

    whole, narrowed = await seen(super_admin), await seen(admin)
    for one, other in zip(whole[:2], narrowed[:2], strict=True):
        if type(one) is not type(other) or set(type(one).model_fields) != set(
            type(other).model_fields
        ):
            raise CheckFailedError("a department admin's screen was not the Super Admin's shape")
    a, b = people[A], people[B]
    if not ({a, b} <= whole[2] and {a, b} <= whole[3]):
        raise CheckFailedError("the Super Admin's screens did not list both departments")
    if a not in narrowed[2] or a not in narrowed[3]:
        raise CheckFailedError("a department admin's screens did not list their department")
    if b in narrowed[2] or b in narrowed[3]:
        raise CheckFailedError("a department admin's screens listed another department")


# --------------------------------- 6 and 7. approving a department's publication
def _document(agent_id: str) -> dict[str, Any]:
    """An agent of acceptance_a reading its knowledge, which widens on nothing it had before."""
    from brain.builder.agent_drafts import blank_seed

    document = blank_seed(agent_id)
    document["persona"] = PERSONA
    document["authority"] = {
        **document["authority"],
        "scope": Scope.department(A).model_dump(mode="json"),
        "capabilities": [{"value": one} for one in KNOWLEDGE_READS],
    }
    return document


def _builder_app(h: Harness) -> FastAPI:
    """The builder's state over the check's transaction, with a signing key the check made."""
    import secrets

    from brain.knowledge.row_store import SessionRowSource
    from brain.tools.startup import build_registry

    app = _app(h)
    app.state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    app.state.template_key = secrets.token_hex(32)
    return app


async def _waiting(h: Harness, request: Any, author: str) -> tuple[str, int]:
    """A draft `author` started, saved, checked and asked to publish to acceptance_a, which waits
    for a second person because a new agent reaching anything widens from nothing."""
    from brain.agent_builder_routes import (
        DraftPublishAsked,
        DraftRevisionAsked,
        DraftSaveAsked,
        DraftStartAsked,
        check_agent_draft,
        publish_agent_draft,
        save_agent_draft,
        start_agent_draft,
    )
    from brain.builder.draft_words import DraftState
    from brain.builder.drafts import FIRST_REVISION

    asking = await _asking(h, author)
    started = _body(await start_agent_draft(request, DraftStartAsked(), asking))
    draft_id = str(started["draft_id"])
    saved = _body(
        await save_agent_draft(
            request,
            draft_id,
            DraftSaveAsked(document=_document(str(started["agent_id"])), base=FIRST_REVISION),
            asking,
        )
    )
    revision = int(saved["revision"])
    checked = _body(
        await check_agent_draft(request, draft_id, DraftRevisionAsked(revision=revision), asking)
    )
    if not checked.get("passed") or not checked.get("second_person_needed"):
        raise CheckFailedError(
            "a department agent's draft did not check as needing a second person"
        )
    asked = _body(
        await publish_agent_draft(
            request, draft_id, DraftPublishAsked(revision=revision, for_department=True), asking
        )
    )
    if asked.get("state") != DraftState.WAITING.value:
        raise CheckFailedError("a department agent reaching its knowledge did not wait to publish")
    return draft_id, revision


def _body(response: Any) -> dict[str, Any]:
    """A route's JSON answer as a mapping."""
    import json

    found = json.loads(bytes(response.body))
    return found if isinstance(found, dict) else {}


async def _offered(h: Harness, request: Any, who: str) -> list[str]:
    """The drafts waiting for `who` to approve, as the drafts list answers them."""
    from brain.agent_builder_routes import agent_drafts

    page = await agent_drafts(request, await _asking(h, who))
    return [one.draft_id for one in page.waiting_for_you]


async def _approved(
    h: Harness, request: Any, who: str, draft_id: str, revision: int
) -> dict[str, Any]:
    """`POST /agent-drafts/{id}/approve` as `who`, its answer, or nothing for the one refusal."""
    from brain.agent_builder_routes import DraftRevisionAsked, approve_agent_draft
    from brain.core.errors import Absent

    try:
        answered = await approve_agent_draft(
            request, draft_id, DraftRevisionAsked(revision=revision), await _asking(h, who)
        )
    except Absent:
        return {}
    return _body(answered) if answered.status_code == 201 else {}


async def _published_to_the_department(h: Harness, agent_id: str, author: str) -> bool:
    """Whether the agent is on file, seen by acceptance_a and owned by its author."""
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_workspace import stored_agent

    record = await stored_agent(h, agent_id)
    audience = record.audience
    return (
        audience.level is Visibility.DEPARTMENT
        and audience.department == A
        and audience.owner_id == author
    )


async def _a_publication_waits(
    h: Harness, approver_grants: Sequence[tuple[str, Scope]]
) -> tuple[Any, str, str, str, int]:
    """Two departments, an author in acceptance_a with a waiting draft, `approver` holding
    `approver_grants`, and the admin of acceptance_b holding the same over their own."""
    from brain.agents.creation import AGENT_INSTALL_CAPABILITY

    _traced(h)
    await h.found_departments()
    author, approver = h.principal(A, "author"), h.principal(A, "approver")
    other, narrow = h.principal(B, "admin"), h.principal(A, "narrow")
    builds = AGENT_INSTALL_CAPABILITY.value
    await h.person(author, department=A, grants=_in(A, builds))
    await h.person(approver, department=A, grants=approver_grants)
    await h.person(other, department=B, grants=_in(B, builds, *KNOWLEDGE_READS))
    await h.person(narrow, department=A, grants=_in(A, builds))
    request = _request(_builder_app(h))
    draft_id, revision = await _waiting(h, request, author)
    return request, author, approver, draft_id, revision


async def _decided_by(
    h: Harness, request: Any, author: str, approver: str, draft_id: str, revision: int
) -> None:
    """What both publication checks ask once a draft waits: the author, the other department's
    admin, a builder whose reach does not cover the agent, and then the approver, in that order."""
    other, narrow = h.principal(B, "admin"), h.principal(A, "narrow")
    if draft_id in await _offered(h, request, other) or await _approved(
        h, request, other, draft_id, revision
    ):
        raise CheckFailedError("another department's admin was offered or approved a publication")
    if draft_id in await _offered(h, request, narrow) or await _approved(
        h, request, narrow, draft_id, revision
    ):
        raise CheckFailedError("a builder who cannot read what an agent reads approved it")
    if await _approved(h, request, author, draft_id, revision):
        raise CheckFailedError("the author of a widening publication approved it themselves")
    if draft_id not in await _offered(h, request, approver):
        raise CheckFailedError("a publication waiting for its approver was not on their list")
    published = await _approved(h, request, approver, draft_id, revision)
    agent_id = str(published.get("agent_id", ""))
    if not agent_id or not await _published_to_the_department(h, agent_id, author):
        raise CheckFailedError("an approved publication did not publish the agent to acceptance_a")
    if draft_id in await _offered(h, request, approver):
        raise CheckFailedError("a published draft still waited for its approver")


@check(
    leaves=("M33.2.2.1",),
    sentence=(
        "A member of acceptance_a asks to publish an agent reading its knowledge to the "
        "department and it waits: the admin of acceptance_a is offered it and approves it, which "
        "publishes it there. The admin of acceptance_b, a builder of acceptance_a who cannot read "
        "that knowledge and the author are neither offered it nor able to approve it."
    ),
)
async def a_department_admin_approves_their_departments_publication(h: Harness) -> None:
    from brain.agents.creation import AGENT_INSTALL_CAPABILITY

    request, author, admin, draft_id, revision = await _a_publication_waits(
        h, _in(A, AGENT_INSTALL_CAPABILITY.value, *KNOWLEDGE_READS)
    )
    await _decided_by(h, request, author, admin, draft_id, revision)


@check(
    leaves=("M33.1.2.2",),
    sentence=(
        "A member of acceptance_a asks to publish an agent reading its knowledge to the "
        "department and it waits: a Super Admin, who builds and reads everywhere, is offered it "
        "and approves it, which publishes it there. The admin of acceptance_b, a builder of "
        "acceptance_a who cannot read that knowledge and the author are neither offered it nor "
        "able to approve it."
    ),
)
async def a_super_admin_approves_a_departments_publication_request(h: Harness) -> None:
    from brain.agents.creation import AGENT_INSTALL_CAPABILITY

    everywhere = Scope.unrestricted()
    request, author, super_admin, draft_id, revision = await _a_publication_waits(
        h,
        tuple((one, everywhere) for one in (AGENT_INSTALL_CAPABILITY.value, *KNOWLEDGE_READS)),
    )
    await _decided_by(h, request, author, super_admin, draft_id, revision)


# -------------------------------------------------------- 8. the audit trail (M33.4.1.1)
@check(
    leaves=("M33.4.1.1",),
    sentence=(
        "A Super Admin grants a member of acceptance_a a capability and disables another, each "
        "through its screen's route: an auditor reading the Audit screen's route sees both "
        "entries under the Super Admin's name, and a member without the audit screen is refused "
        "it."
    ),
)
async def an_auditor_reads_the_super_admins_own_acts(h: Harness) -> None:
    from brain.audit.ledger import AuditAction
    from brain.audit_routes import AUDIT_SCREEN, audit_page
    from brain.console.screens import screen
    from brain.principal_state_routes import StateAsked, disable_person

    _traced(h)
    await h.found_departments()
    super_admin, auditor = h.principal(A, "super"), h.principal(B, "auditor")
    member, leaving = h.principal(A, "member"), h.principal(A, "leaving")
    everywhere = Scope.unrestricted()
    await h.person(
        super_admin,
        department=A,
        grants=((GRANT_DECISION, everywhere), (GRANTED, everywhere)),
    )
    await h.person(
        auditor,
        department=B,
        grants=(*_opens(screen(AUDIT_SCREEN).read, everywhere), (EVERY_AUDIT_ENTRY, everywhere)),
    )
    await h.person(member, department=A)
    await h.person(leaving, department=A)
    request = _request(_app(h))

    if not await _grant(h, request, super_admin, member, GRANTED, _slug(A)):
        raise CheckFailedError("a Super Admin could not grant a member a capability")
    done = await disable_person(
        request, StateAsked(principal_id=leaving), await _asking(h, super_admin)
    )
    if done.status_code != 200:
        raise CheckFailedError("a Super Admin could not disable a member")

    async def read(who: str) -> Any:
        return await audit_page(request, await _asking(h, who), actor=super_admin, limit=100)

    page = await read(auditor)
    acts = {
        (one.action, one.details.get("capability", one.subject_id))
        for one in page.items
        if one.actor_id == super_admin
    }
    if not {(AuditAction.GRANT, GRANTED), (AuditAction.PRINCIPAL_STATE, leaving)} <= acts:
        raise CheckFailedError("an auditor did not read the Super Admin's own acts")
    if not await _refused(read(member)):
        raise CheckFailedError("a member without the audit screen read the audit trail")


# ---------------------------------------- 9. a member's own things (M33.3.1.1, M33.3.1.2)
async def _workspace(h: Harness, request: Any, who: str) -> Any:
    """`GET /me/workspace` as `who`, read as a request's own transaction would read it.

    The check's transaction is one for every step, and resolving a reader's reach tells it who
    is present, which a request's own transaction is never told until the route tells it. So
    the setting is cleared first, and the route is what names the reader to the database. See
    `A_WORKSPACE_IS_READ_IN_A_TRANSACTION_THAT_NAMES_NOBODY_YET`.
    """
    from sqlalchemy import func, select

    from brain.knowledge.search import PRINCIPAL_SETTING
    from brain.mine_routes import workspace

    asking = await _asking(h, who)
    await h.execute(select(func.set_config(PRINCIPAL_SETTING, "", True)))
    return await workspace(request, asking)


def _member(read: ConsoleRead, department: str) -> tuple[tuple[str, Scope], ...]:
    """A member: the member screen over their department, and its knowledge."""
    return (*_opens(read, Scope.department(department)), *_in(department, *KNOWLEDGE_READS))


@check(
    leaves=("M33.3.1.1",),
    sentence=(
        "A member of acceptance_a with an agent of their own and a department agent opens their "
        "workspace through its route: both are listed, theirs as personal; another member's "
        "personal agent is not, and that member's workspace lists the department agent and not "
        "the first member's own."
    ),
)
async def a_member_sees_their_own_agents_and_not_anybody_elses(h: Harness) -> None:
    from brain.member.shell import member_screen
    from brain.mine_routes import MEMBER_HOME
    from brain.ops.acceptance_workspace import installed_agent

    _traced(h)
    await h.found_departments()
    home = member_screen(MEMBER_HOME).read
    member, colleague = h.principal(A, "member"), h.principal(A, "colleague")
    for one in (member, colleague):
        await h.person(one, department=A, grants=_member(home, A))
    theirs = await installed_agent(h, member, suffix="_own", personal=True)
    others = await installed_agent(h, colleague, suffix="_other", personal=True)
    shared = await installed_agent(h, colleague, suffix="_shared")
    request = _request(_app(h))

    def agents(page: Any) -> dict[str, str]:
        return {one.agent_id: one.provision for one in page.agents}

    mine = agents(await _workspace(h, request, member))
    if theirs not in mine or shared not in mine:
        raise CheckFailedError("a member's workspace did not list their own and their department's")
    if mine[theirs] == mine[shared]:
        raise CheckFailedError("a member's own agent was not told apart from a department's")
    if others in mine:
        raise CheckFailedError("a member's workspace listed somebody else's own agent")
    colleagues = agents(await _workspace(h, request, colleague))
    if theirs in colleagues or shared not in colleagues:
        raise CheckFailedError("a colleague's workspace listed another member's own agent")


@check(
    leaves=("M33.3.1.2",),
    sentence=(
        "A member of acceptance_a adds a document for themselves and one for the department "
        "through the upload route's own sequence and opens their workspace: both are listed as "
        "theirs, each at its level; a colleague's workspace lists neither, and a document the "
        "colleague added is not on the first member's."
    ),
)
async def a_member_sees_the_knowledge_they_added_and_nobody_elses(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge.visibility import Visibility
    from brain.member.shell import member_screen
    from brain.mine_routes import MEMBER_HOME
    from brain.ops.acceptance_checks import _upload
    from brain.ops.acceptance_documents import a_markdown_document

    _traced(h)
    await h.found_departments()
    home = member_screen(MEMBER_HOME).read
    member, colleague = h.principal(A, "member"), h.principal(A, "colleague")
    for one in (member, colleague):
        await h.person(
            one, department=A, grants=(*_member(home, A), *_in(A, KNOWLEDGE_UPLOAD.value))
        )

    async def added(who: str, level: Visibility) -> str:
        body = a_markdown_document("Acceptance workspace", f"It says {h.word()}.")
        read = await _upload(
            h,
            who,
            filename="Acceptance workspace.md",
            declared=MediaType.MARKDOWN.value,
            body=body,
            level=level,
        )
        item = getattr(read, "item", None)
        if item is None:
            raise CheckFailedError("a well-formed Markdown document could not be added")
        return str(item.item_id)

    personal = await added(member, Visibility.PERSONAL)
    departmental = await added(member, Visibility.DEPARTMENT)
    theirs = await added(colleague, Visibility.PERSONAL)
    request = _request(_app(h))

    def kept(page: Any) -> dict[str, str]:
        return {one.item_id: one.level for one in page.knowledge}

    mine = kept(await _workspace(h, request, member))
    wanted = {personal: Visibility.PERSONAL.value, departmental: Visibility.DEPARTMENT.value}
    if {key: mine.get(key) for key in wanted} != wanted:
        raise CheckFailedError("a member's workspace did not list what they added, at its level")
    if theirs in mine:
        raise CheckFailedError("a member's workspace listed a document somebody else added")
    colleagues = kept(await _workspace(h, request, colleague))
    if personal in colleagues or departmental in colleagues or theirs not in colleagues:
        raise CheckFailedError("a colleague's workspace listed what another member added")
