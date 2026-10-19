"""The install acceptance check for who decides a publication at which reach (M20.5.1).

M20.5.1 asks that an agent, a skill or a knowledge item published at department reach wait for
that department's administrator, that one published company-wide wait for a Super Admin, and that a
department's administrator be able neither to approve a publication outside their department nor to
widen an item to the whole company alone. The first half is the publication queue
(`brain.console.global_surfaces.may_approve_publication`), which asks the approving authority in a
scope admitting the row the item sits in; the second is
`brain.knowledge.visibility.holds_for_level`, which asks the same authority held over everything
for the company, for agents and knowledge alike. A skill is neither: the library is one company-wide
object, so every decision about a skill is made by the authority held over everything
(`brain.console.skill_library.may_review`), and a department's administrator is refused it.

**The department's administrator here holds each authority in their own department and nothing
wider, which is the person the rule is about.** Before M20.5.1 that person could publish an agent to
every department and approve a promotion to the company, because both asked only that the capability
be held in any scope. The check gives them exactly that grant, beside a Super Admin who holds the
same capabilities over everything, and reads what each is told, through the route functions and the
domain functions the console calls, over the install's own database and the reach it loads for each
reserved person.

**Nothing is assumed about the install.** Every person, agent and request is the check's own, and
everything is written inside its transaction and rolled back.

Task ids: M20.5.1
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_publication import _asking, _offered, _request, _status
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page, beside the publication check's own. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 409

AN_AGENT_WAS_PUBLISHED_ALONE: Final = (
    "an administrator of one department published an agent to the whole company alone"
)
NO_SUPER_ADMIN_PUBLISHED: Final = (
    "a person holding the visibility authority over everything could not publish an agent"
)
A_DEPARTMENT_ADMIN_APPROVED_THE_COMPANY: Final = (
    "an administrator of one department approved a knowledge item to the whole company"
)
A_SUPER_ADMIN_WAS_REFUSED_THE_COMPANY: Final = (
    "a person holding the promotion authority over everything could not approve to the company"
)
THE_QUEUE_OFFERED_THE_COMPANY: Final = (
    "a department's administrator was offered a request for the whole company to decide"
)
THE_QUEUE_HID_THE_COMPANY_FROM_A_SUPER_ADMIN: Final = (
    "a person holding the promotion authority over everything was not offered a company request"
)
A_DEPARTMENT_ADMIN_DECIDED_ANOTHERS: Final = (
    "an administrator of one department was offered another department's publication request"
)
A_DEPARTMENT_ADMIN_WAS_REFUSED_THEIR_OWN: Final = (
    "an administrator of a department was not offered their own department's publication request"
)
A_DEPARTMENT_ADMIN_REVIEWED_A_SKILL: Final = (
    "an administrator of one department could decide about a skill in the company's library"
)
NO_SUPER_ADMIN_REVIEWED_A_SKILL: Final = (
    "a person holding the skill review authority over everything could not decide about a skill"
)


@check(
    leaves=("M20.5.1",),
    sentence=(
        "An administrator of acceptance_a holding each approving authority in their own department "
        "cannot publish an agent or approve a knowledge item to the whole company and is not "
        "offered the request, decides acceptance_a's own department requests and not "
        "acceptance_b's, and cannot decide about a skill; a person holding the same authorities "
        "over everything can do each."
    ),
)
async def a_department_admin_decides_only_for_their_department(
    h: Harness,
) -> None:
    from brain.agent_lifecycle_routes import PublicationAsked, publish_agent
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY, AGENT_PUBLICATION_CAPABILITY
    from brain.console.global_surfaces import may_approve_publication
    from brain.console.govern import Placed
    from brain.console.reads import plane_capability_for
    from brain.console.screens import screen
    from brain.console.skill_library import REVIEW_AUTHORITY, may_review
    from brain.core.department import DEPARTMENT_FIELD
    from brain.core.errors import Absent
    from brain.knowledge.visibility import (
        PROMOTION_CAPABILITY,
        Visibility,
        VisibilityError,
        approve_promotion,
        propose_promotion,
    )
    from brain.ops.acceptance_checks_skills import _an_agent

    await h.found_departments()
    everywhere = Scope.unrestricted()
    skills = screen("skills").read
    reads = (
        (skills.requires.value, everywhere),
        (plane_capability_for(skills, skills.plane).value, everywhere),
    )
    own = {
        A: h.principal(A, "deptadmin"),
        B: h.principal(B, "deptadmin"),
    }
    for department, person in own.items():
        scope = Scope.department(department)
        await h.person(
            person,
            department=department,
            grants=(
                (AGENT_PUBLICATION_CAPABILITY.value, scope),
                (AGENT_LIFECYCLE_CAPABILITY.value, scope),
                (PROMOTION_CAPABILITY.value, scope),
                (REVIEW_AUTHORITY.value, scope),
                *reads,
            ),
        )
    super_admin, steward = h.principal(A, "super"), h.principal(A, "steward")
    await h.person(
        super_admin,
        department=A,
        grants=tuple(
            (one.value, everywhere)
            for one in (
                AGENT_PUBLICATION_CAPABILITY,
                AGENT_LIFECYCLE_CAPABILITY,
                PROMOTION_CAPABILITY,
                REVIEW_AUTHORITY,
            )
        )
        + reads,
    )
    await h.person(steward, department=A, grants=())
    colleague = h.principal(B, "colleague")
    await h.person(colleague, department=B, grants=())

    # The agent: a department's administrator is told it is not there, and the holder over
    # everything publishes it to every department.
    agent = await _an_agent(h, steward)
    _, request = _request()
    request.app.state.db_sessions = h.sessions
    asked = PublicationAsked(expected_level="department")
    try:
        status, _ = await _status(
            await publish_agent(request, agent, asked, await _asking(h, own[A]))
        )
    except Absent:
        status = 0
    if status == 200 or await _offered(h, colleague, agent):
        raise CheckFailedError(AN_AGENT_WAS_PUBLISHED_ALONE)
    status, body = await _status(
        await publish_agent(request, agent, asked, await _asking(h, super_admin))
    )
    if status != 200 or body.get("level") != "company":
        raise CheckFailedError(NO_SUPER_ADMIN_PUBLISHED)

    # Knowledge: the same grant is refused the company and admitted to its own department.
    now = datetime.now(UTC)
    to_company = propose_promotion(
        item_id="acceptance-handbook",
        from_level=Visibility.DEPARTMENT,
        to_level=Visibility.COMPANY,
        proposer_id=steward,
        owner_id=steward,
        review_by=datetime(2999, 1, 1, tzinfo=UTC),
        reason="Everybody needs it.",
        now=now,
    )
    to_department = propose_promotion(
        item_id="acceptance-notes",
        from_level=Visibility.PERSONAL,
        to_level=Visibility.DEPARTMENT,
        proposer_id=steward,
        owner_id=steward,
        review_by=datetime(2999, 1, 1, tzinfo=UTC),
        reason="The department needs it.",
        now=now,
    )
    reach_a = await h.reach(own[A])
    reach_b = await h.reach(own[B])
    reach_super = await h.reach(super_admin)
    try:
        approve_promotion(to_company, approver_id=own[A], entitlement=reach_a, now=now)
    except VisibilityError:
        pass
    else:
        raise CheckFailedError(A_DEPARTMENT_ADMIN_APPROVED_THE_COMPANY)
    try:
        approve_promotion(to_company, approver_id=super_admin, entitlement=reach_super, now=now)
    except VisibilityError:
        raise CheckFailedError(A_SUPER_ADMIN_WAS_REFUSED_THE_COMPANY) from None

    in_a = {DEPARTMENT_FIELD: A}
    if may_approve_publication(Placed(record=to_company, where=in_a), reach_a, now):
        raise CheckFailedError(THE_QUEUE_OFFERED_THE_COMPANY)
    if not may_approve_publication(Placed(record=to_company, where=in_a), reach_super, now):
        raise CheckFailedError(THE_QUEUE_HID_THE_COMPANY_FROM_A_SUPER_ADMIN)
    if may_approve_publication(Placed(record=to_department, where=in_a), reach_b, now):
        raise CheckFailedError(A_DEPARTMENT_ADMIN_DECIDED_ANOTHERS)
    if not may_approve_publication(Placed(record=to_department, where=in_a), reach_a, now):
        raise CheckFailedError(A_DEPARTMENT_ADMIN_WAS_REFUSED_THEIR_OWN)

    # A skill: one library for the company, so only the authority over everything decides.
    if may_review(reach_a, now):
        raise CheckFailedError(A_DEPARTMENT_ADMIN_REVIEWED_A_SKILL)
    if not may_review(reach_super, now):
        raise CheckFailedError(NO_SUPER_ADMIN_REVIEWED_A_SKILL)
