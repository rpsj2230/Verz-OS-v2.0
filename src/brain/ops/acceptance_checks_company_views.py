"""Install checks for the Super Admin's view of the company, read through the routes its pages call.

`brain.company_routes` serves the Super Admin's three company reads: everything the install holds
(agents, skills, knowledge and connectors), all of its activity, and what it spent. Their unit
tests run over a stub pool. What they cannot show is that, over the product's own tables and
ledger, a reader who holds the four screens everywhere is shown an agent and a document in either
department, that the department and person filters narrow that to exactly what they name, and that
the reader of one department is shown that department alone and is answered alike when they ask
for another. Each check asks the route itself, as reserved people holding the grants their role
means (`brain.ops.acceptance_checks_governance`), inside the check's rolled-back transaction.

**The filters are checked against the reserved departments, so the install's own rows cannot
move them.** An install holds real agents and documents the check never made. A department
filter naming `acceptance_a` selects only what the check placed there, and a person filter naming
a reserved principal selects only what that principal owns, so the check's assertions are about
exactly the rows it wrote and an install with a hundred real agents answers the same as an empty
one. Where it asks without a filter it asserts that the check's own rows are present and its
other-department rows are absent for the narrower reader, never that the list is a particular
length: a length would be a count of what the install holds.

**Activity is made by the reserved people themselves.** A department's activity is the entries its
members made (`brain.company_routes.A_DEPARTMENT_IS_ITS_PEOPLE_AS_THIS_READER_MAY_NAME_THEM`), so
the check has a member of each department take a grant away from a colleague through the
statements the People screen runs, each attributed to them as a console request is, and then asks
for each department's activity and each person's.

**What is not proved here, and why.** M33.1.1.3 asks for the company's budget beside what it
spent, and nothing on this install writes a company ceiling, so the consumption read can only say
that none is set (`brain.company_routes`' own docstring). It is left to the budget screen's
writer and is not named below.

Task ids: M33.1.1.1, M33.1.1.2
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
from brain.ops.acceptance_checks_governance import _app, _asking, _opens, _refused, _request
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.company_routes import CompanyActivityPage, EstateView

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 800

A, B = RESERVED_DEPARTMENTS

#: What a member holds to add a document, as `brain.ops.acceptance_checks` adds one.
ADDS_KNOWLEDGE: Final = "admin:knowledge"

#: The capability a member of a department takes away from a colleague, to make activity.
TAKEN_AWAY: Final = "read:knowledge.title"


# ------------------------------------------------------------------------------- the readers
def _once(grants: Iterable[tuple[str, Scope]]) -> tuple[tuple[str, Scope], ...]:
    """Each capability once: two screens on one plane need that plane's grant only once, and a
    second live grant of one capability is refused by the table."""
    kept: dict[str, Scope] = {}
    for capability, scope in grants:
        kept.setdefault(capability, scope)
    return tuple(kept.items())


def _screens_over(scope: Scope, *names: str) -> tuple[tuple[str, Scope], ...]:
    """The grants that open each named screen over `scope`: its read and the plane it is on."""
    from brain.console.screens import screen

    return _once(grant for name in names for grant in _opens(screen(name).read, scope))


def _estate_screens(scope: Scope) -> tuple[tuple[str, Scope], ...]:
    """The four screens the estate is made of, as `brain.console.global_surfaces` maps them."""
    from brain.console.global_surfaces import ESTATE_SCREEN, EstateKind

    return _screens_over(scope, *(ESTATE_SCREEN[kind] for kind in EstateKind))


def _audit_over(scope: Scope) -> tuple[tuple[str, Scope], ...]:
    """The Activity screen and every audit noun, over `scope`, as an auditor holds them."""
    from brain.audit.view import CAPABILITY_BY_KIND

    nouns = tuple((one.value, scope) for one in CAPABILITY_BY_KIND.values())
    return (*_screens_over(scope, "audit"), *nouns)


async def _members(h: Harness) -> tuple[str, str, str, str]:
    """A Super Admin, a department head's reader and one member in each reserved department."""
    await h.found_departments()
    super_admin, head, owner_a, owner_b = (
        h.principal(A, "super"),
        h.principal(A, "reader"),
        h.principal(A, "owner"),
        h.principal(B, "owner"),
    )
    everywhere = Scope.unrestricted()
    await h.person(
        super_admin,
        department=A,
        grants=_once(
            (
                *_estate_screens(everywhere),
                *_audit_over(everywhere),
                # A department lens over activity names its people, which asks the People screen.
                *_screens_over(everywhere, "people"),
            )
        ),
    )
    await h.person(head, department=A, grants=_estate_screens(Scope.department(A)))
    await h.person(owner_a, department=A, grants=(*_in(A, ADDS_KNOWLEDGE, *KNOWLEDGE_READS),))
    await h.person(owner_b, department=B, grants=(*_in(B, ADDS_KNOWLEDGE, *KNOWLEDGE_READS),))
    return super_admin, head, owner_a, owner_b


def _kinds(view: EstateView) -> dict[str, set[str]]:
    """The identifiers in an estate answer, by kind."""
    found: dict[str, set[str]] = {}
    for one in view.items:
        found.setdefault(one.kind.value, set()).add(one.item_id)
    return found


# ------------------------------------------------------------------------------------ estate
@check(
    leaves=("M33.1.1.1",),
    sentence=(
        "A Super Admin asking the company estate is shown an agent and a document of each "
        "department; naming a department, a person or a kind narrows it to exactly that; the "
        "reader of one department is shown that department's rows and none of the other's, and "
        "asking for the other department answers them as a department that owns nothing."
    ),
)
async def the_company_estate_narrows_by_department_person_and_kind(
    h: Harness,
) -> None:
    from brain.agents.model import AgentAudience
    from brain.company_routes import company_estate
    from brain.console.global_surfaces import EstateKind
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_checks import _upload
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.acceptance_workspace import installed_agent

    super_admin, head, owner_a, owner_b = await _members(h)
    agent_a = await installed_agent(h, owner_a)
    agent_b = await installed_agent(
        h,
        owner_b,
        suffix="_b",
        scope=Scope.department(B),
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=owner_b, department=B),
    )
    documents: dict[str, str] = {}
    for department, owner in ((A, owner_a), (B, owner_b)):
        read = await _upload(
            h,
            owner,
            filename=f"Estate{department[-1].upper()}.md",
            declared="text/markdown",
            body=a_markdown_document("Estate", h.word()),
            department=department,
        )
        documents[department] = read.item.item_id
    request = _request(_app(h))
    wide, narrow = await _asking(h, super_admin), await _asking(h, head)

    async def estate(asked: Any, **narrowing: Any) -> EstateView:
        return await company_estate(request, asked, **narrowing)

    # 1. Everything, for the reader who holds the four screens everywhere.
    every = _kinds(await estate(wide))
    if {agent_a, agent_b} - every.get("agent", set()):
        raise CheckFailedError("a Super Admin was not shown an agent of each department")
    if set(documents.values()) - every.get("knowledge", set()):
        raise CheckFailedError("a Super Admin was not shown a document of each department")

    # 2. A department, a person and a kind each narrow to what they name.
    in_a = _kinds(await estate(wide, department=A))
    if agent_a not in in_a.get("agent", set()) or documents[A] not in in_a.get("knowledge", set()):
        raise CheckFailedError("naming a department did not show what it holds")
    if agent_b in in_a.get("agent", set()) or documents[B] in in_a.get("knowledge", set()):
        raise CheckFailedError("naming a department showed another department's rows")
    owned = _kinds(await estate(wide, person=owner_b))
    if owned != {"agent": {agent_b}, "knowledge": {documents[B]}}:
        raise CheckFailedError("naming a person did not show exactly what they own")
    only_agents = _kinds(await estate(wide, department=A, kind=EstateKind.AGENT))
    if only_agents != {"agent": {agent_a}}:
        raise CheckFailedError("naming a kind did not narrow to that kind")

    # 3. The reader of one department is shown it and no other, and told nothing of the rest.
    seen = _kinds(await estate(narrow))
    if agent_a not in seen.get("agent", set()) or documents[A] not in seen.get("knowledge", set()):
        raise CheckFailedError("a department's reader was not shown their own department's rows")
    if agent_b in seen.get("agent", set()) or documents[B] in seen.get("knowledge", set()):
        raise CheckFailedError("a department's reader was shown another department's rows")
    other = await estate(narrow, department=B)
    nothing = await estate(narrow, department="acceptance_nobody")
    if other.model_dump() != nothing.model_dump() or other.items:
        raise CheckFailedError(
            "a department's reader asking for another department was answered differently from "
            "one that owns nothing"
        )
    if B in (await estate(narrow)).departments:
        raise CheckFailedError("a department's reader was offered another department to filter by")


# ---------------------------------------------------------------------------------- activity
async def _took_away(h: Harness, by: str, from_: str) -> str:
    """One grant given to `from_` and taken away by `by`, as the People screen's statements do.

    Returns the grant's identifier. The entries land in the ledger attributed to `by`.
    """
    from datetime import timedelta

    from brain.core.entitlement import Capability
    from brain.govern_routes import add_grant, retire_grant
    from brain.identity.packs import SubjectGrant
    from brain.identity.teams import PrincipalSubject
    from brain.tables.audit import attributed_to

    reach = await h.reach(by)
    attributed = attributed_to(actor_id=by, ent_hash=reach.ent_hash(), trace_id=h.trace_id)
    async with h.sessions() as session:
        for statement in attributed:
            await session.execute(statement)
        given = await session.execute(
            add_grant(
                SubjectGrant(
                    subject=PrincipalSubject(principal_id=from_),
                    capability=Capability(value=TAKEN_AWAY),
                    scope=Scope.department(A),
                    granted_by=by,
                    reason="Granted by an install acceptance check for the length of the check",
                    granted_at=h.now,
                    not_after=h.now + timedelta(hours=1),
                ),
                principal_id=from_,
            )
        )
        grant_id = str(given.scalar_one().id)
        await session.execute(retire_grant(from_, TAKEN_AWAY))
        await session.commit()
    return grant_id


def _actors(page: CompanyActivityPage) -> set[str]:
    return {one.actor_id for one in page.items}


@check(
    leaves=("M33.1.1.2",),
    sentence=(
        "A Super Admin asking the company's activity is shown what a member of each department "
        "did; naming a department shows its members' entries alone, naming a person shows that "
        "person's alone, and somebody without the Activity screen is refused."
    ),
)
async def the_company_activity_narrows_to_a_department_and_to_a_person(h: Harness) -> None:
    from brain.company_routes import company_activity_page

    super_admin, _head, owner_a, owner_b = await _members(h)
    outsider = h.principal(A, "outsider")
    await h.person(outsider, department=A)
    colleague_a, colleague_b = h.principal(A, "colleague"), h.principal(B, "colleague")
    await h.person(colleague_a, department=A)
    await h.person(colleague_b, department=B)
    await _took_away(h, owner_a, colleague_a)
    await _took_away(h, owner_b, colleague_b)
    request = _request(_app(h))
    wide = await _asking(h, super_admin)

    everyone = _actors(await company_activity_page(request, wide, limit=100))
    if not {owner_a, owner_b} <= everyone:
        raise CheckFailedError("a Super Admin was not shown what a member of each department did")

    in_a = await company_activity_page(request, wide, department=A, limit=100)
    if owner_a not in _actors(in_a) or owner_b in _actors(in_a):
        raise CheckFailedError("naming a department did not narrow activity to its members")
    by_one = await company_activity_page(request, wide, person=owner_b, limit=100)
    if not by_one.items or _actors(by_one) != {owner_b}:
        raise CheckFailedError("naming a person did not narrow activity to their entries")

    if not await _refused(company_activity_page(request, await _asking(h, outsider), limit=100)):
        raise CheckFailedError("somebody without the Activity screen was shown company activity")


# ------------------------------------------------------------------ a department's own head
#: What the department's day ceiling is, and what is charged to it, so the pace is a figure the
#: check can state: three tenths of the ceiling spent.
DAY_CEILING: Final = 1000
SPENT_TODAY: Final = 300

#: The model the check's price is for, which no provider serves.
PRICED_MODEL: Final = "acceptance-model"


async def _cost_is_recorded(h: Harness, by: str) -> None:
    """Give this transaction a price in the install's currency, as the Models screen would.

    A department's pace is withheld on an install where no model has a price in its own currency
    (`brain.console_overview_figures_routes.cost_recorded_in`), because the recorder writes no
    cost there and every department would read as having spent nothing. The check writes the
    price in its rolled-back transaction so it asks the same question on every install, and says
    it was not run where the install's currency cannot be resolved at all.
    """
    from decimal import Decimal

    from brain.core.errors import Failed
    from brain.locale import NO_CURRENCY_CODE, LocaleError
    from brain.locale import currency as install_currency
    from brain.models.pricing import Price
    from brain.ops.acceptance import CheckNotRunError
    from brain.ops.price_store import set_price_statement

    try:
        code = install_currency()
    except (LocaleError, Failed):
        raise CheckNotRunError(
            "this install's currency does not resolve, so no cost can be recorded to pace"
        ) from None
    if code == NO_CURRENCY_CODE:
        raise CheckNotRunError(
            "this install has no currency set, so no cost is recorded and no pace can be shown"
        )
    price = Price(input_minor=Decimal(1), output_minor=Decimal(1), currency=code)
    await h.execute(
        *h.attributed(by), set_price_statement("acceptance", PRICED_MODEL, price, by=by)
    )


@check(
    leaves=("M33.2.1.3", "M33.2.1.4"),
    sentence=(
        "The person who leads acceptance_a is shown its day ceiling against the part of the day "
        "gone and the knowledge it holds by freshness; a member of it, the lead of acceptance_b "
        "and a department that does not exist are each answered with the one refusal."
    ),
)
async def a_departments_head_reads_its_pace_and_its_knowledge_coverage(h: Harness) -> None:
    from brain.department_view_routes import coverage_of_department, pace_of_department
    from brain.identity.organisation_store import StoredOrganisation
    from brain.ops.acceptance_checks import _upload
    from brain.ops.acceptance_checks_role_surfaces import _spend
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.budget_store import append
    from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
    from brain.tables.spend import SpendActualRow

    await h.found_departments()
    head, member, other_head, owner = (
        h.principal(A, "head"),
        h.principal(A, "member"),
        h.principal(B, "head"),
        h.principal(A, "owner"),
    )
    budget = _screens_over(Scope.department(A), "budget")
    await h.person(head, department=A, grants=(*_in(A, *KNOWLEDGE_READS), *budget))
    await h.person(member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(
        other_head,
        department=B,
        grants=(*_in(B, *KNOWLEDGE_READS), *_screens_over(Scope.department(B), "budget")),
    )
    await h.person(owner, department=A, grants=_in(A, ADDS_KNOWLEDGE, *KNOWLEDGE_READS))
    store = StoredOrganisation(h.sessions)

    def anyone(*_: object) -> bool:
        """Every structural question here is the run's own, about its own reserved rows."""
        return True

    for lead, department in ((head, A), (other_head, B)):
        if (
            await store.appoint(
                department=department,
                principal_id=lead,
                actor=h.actor,
                ent_hash=SET_UP_REACH,
                trace_id=h.trace_id,
                may=anyone,
            )
            is None
        ):
            raise CheckFailedError("a head could not be appointed to lead a department")
    await _cost_is_recorded(h, owner)
    await _upload(
        h,
        owner,
        filename="Coverage.md",
        declared="text/markdown",
        body=a_markdown_document("Coverage", h.word()),
        department=A,
    )
    reach = await h.reach(owner)
    async with h.sessions() as session:
        await session.execute(
            insert(SpendActualRow), [_spend(owner, SPENT_TODAY, h.now, h.trace_id)]
        )
        await append(
            session,
            BudgetRow(
                level=BudgetLevel.DEPARTMENT,
                subject=A,
                period=BudgetPeriod.DAY,
                ceiling_minor=DAY_CEILING,
                version=1,
                author=owner,
                effective_from=h.now,
                reason="Set by an install acceptance check",
                alert_fractions=(),
            ),
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
        )
        await session.commit()
    request = _request(_app(h))
    by_head = await _asking(h, head)

    pace = await pace_of_department(request, by_head, department=A)
    [day] = [one for one in pace.paces if one.period == "day"]
    if pace.not_recorded or abs(day.spent_fraction - SPENT_TODAY / DAY_CEILING) > 1e-9:
        raise CheckFailedError(
            "a head was not shown their department's day spend against its ceiling"
        )
    coverage = await coverage_of_department(request, by_head, department=A)
    if [one.area for one in coverage.areas] != [A] or coverage.areas[0].items < 1:
        raise CheckFailedError("a head was not shown the knowledge their department holds")

    for who, asked_for in ((member, A), (other_head, A), (head, B), (head, "acceptance_nobody")):
        for call in (pace_of_department, coverage_of_department):
            if not await _refused(call(request, await _asking(h, who), department=asked_for)):
                raise CheckFailedError("somebody who does not lead the department was answered")


# ------------------------------------------------------------------------- a role nomination
@check(
    leaves=("M33.1.2.3",),
    sentence=(
        "A person nominates a colleague for the approver role of acceptance_a and cannot confirm "
        "it, nor can the colleague, even holding the grant decision; a third person holding it "
        "over acceptance_a confirms and the colleague then holds the role, granted by that third "
        "person; the admin of acceptance_b confirming a nomination for acceptance_a is refused."
    ),
)
async def a_role_nomination_is_confirmed_only_by_a_third_person(
    h: Harness,
) -> None:
    from brain.govern_routes import ROLES_SCREEN
    from brain.identity.role_store import StoredRoles
    from brain.identity.roles import Role
    from brain.nomination_routes import (
        Decision,
        DecisionBody,
        NominationBody,
        decide_nomination,
        listed_nominations,
        nominate,
    )
    from brain.ops.acceptance_checks_governance import GRANT_DECISION, _slug

    await h.found_departments()
    proposer, nominee, confirmer, outsider = (
        h.principal(A, "proposer"),
        h.principal(A, "nominee"),
        h.principal(A, "confirmer"),
        h.principal(B, "outsider"),
    )
    roles_in_a = _screens_over(Scope.department(A), ROLES_SCREEN)
    for who in (proposer, nominee, confirmer):
        await h.person(who, department=A, grants=_once((*roles_in_a, *_in(A, GRANT_DECISION))))
    await h.person(
        outsider,
        department=B,
        grants=_once((*_screens_over(Scope.department(B), ROLES_SCREEN), *_in(B, GRANT_DECISION))),
    )
    request = _request(_app(h))
    body = NominationBody(
        principal_id=nominee, role=Role.APPROVER, scope_slug=_slug(A), reason="Acceptance check"
    )

    if not await _refused(
        nominate(
            request, body.model_copy(update={"principal_id": proposer}), await _asking(h, proposer)
        )
    ):
        raise CheckFailedError("a person nominated themselves")
    made = await nominate(request, body, await _asking(h, proposer))
    nomination = uuid.UUID(made.id)
    confirm = DecisionBody(decision=Decision.CONFIRM)

    for who in (proposer, nominee, outsider):
        if not await _refused(
            decide_nomination(request, confirm, await _asking(h, who), nomination)
        ):
            raise CheckFailedError(
                "somebody other than a third person with the authority confirmed a nomination"
            )
    if any(one[0].principal_id == nominee for one in await StoredRoles(h.sessions).holders(500)):
        raise CheckFailedError("a refused confirmation left the nominee holding the role")
    waiting = await listed_nominations(request, await _asking(h, confirmer))
    if [one.id for one in waiting.deciding] != [made.id]:
        raise CheckFailedError("the third person was not offered the nomination to decide")

    done = await decide_nomination(request, confirm, await _asking(h, confirmer), nomination)
    if done.change != "confirmed":
        raise CheckFailedError("the third person could not confirm the nomination")
    held = [
        one
        for one, _name, _who in await StoredRoles(h.sessions).holders(500)
        if one.principal_id == nominee and one.role == Role.APPROVER.value
    ]
    if len(held) != 1 or held[0].granted_by != confirmer:
        raise CheckFailedError("a confirmed nomination did not make the nominee hold the role")


# ----------------------------------------------------------------- a person's own conversation
@check(
    leaves=("M33.3.1.3",),
    sentence=(
        "A member lists their own conversation and exports it: the file holds their question and "
        "the answer they were given, and the export is on the install's record in their own name "
        "before it is handed over; a colleague listing conversations is not shown it and naming "
        "its identifier to export it is answered as a conversation that does not exist."
    ),
)
async def a_member_exports_their_own_conversation_and_nobody_elses(h: Harness) -> None:
    import json

    from sqlalchemy import text

    from brain.chat.thread_store import Exchange, StoredThreads
    from brain.gate.context import Channel
    from brain.ops.acceptance_threads import _asking as web_asking
    from brain.ops.acceptance_threads import _listed
    from brain.tables.chat import RunState
    from brain.tables.data_export import ExportDataSet
    from brain.thread_routes import export_my_thread

    await h.found_departments()
    member, colleague = h.principal(A, "member"), h.principal(A, "colleague")
    await h.person(member, department=A)
    await h.person(colleague, department=A)
    store = StoredThreads(h.sessions)
    asked, told = h.word(), h.word()
    thread = await store.record(
        member,
        thread_id=None,
        channel=Channel.CONSOLE,
        exchange=Exchange(
            question=asked,
            answer=told,
            refs=(),
            agent_id="",
            trace_id=f"{h.trace_id}-1",
            state=RunState.ANSWERED,
        ),
        now=h.now,
    )
    if thread is None:
        raise CheckFailedError("a person's exchange was kept in no thread")
    app = _app(h)
    request = _request(app)

    if [one.thread_id for one in await _listed(h, app, member)].count(thread) != 1:
        raise CheckFailedError("a person's own conversation was not in their history")
    if any(one.thread_id == thread for one in await _listed(h, app, colleague)):
        raise CheckFailedError("a person's conversation was in a colleague's history")

    done = await export_my_thread(request, await web_asking(h, member), thread)
    taken = json.loads(bytes(done.body))
    document = json.loads(taken["document"])
    said = [one["text"] for one in document["turns"]]
    if done.status_code != 200 or asked not in said:
        raise CheckFailedError("an exported conversation did not hold the person's own question")
    recorded = (
        await h.execute(
            text(
                "SELECT count(*) FROM ops.data_export WHERE requested_by = :who"
                " AND data_set = :data_set AND reason_reference = :reference"
            ).bindparams(
                who=member, data_set=ExportDataSet.CONVERSATION.value, reference=f"thread/{thread}"
            )
        )
    ).scalar_one()
    if recorded != 1:
        raise CheckFailedError("an export was handed over with no record of it in its owner's name")
    if not await _refused(export_my_thread(request, await web_asking(h, colleague), thread)):
        raise CheckFailedError("a colleague exported a conversation that was not theirs")
