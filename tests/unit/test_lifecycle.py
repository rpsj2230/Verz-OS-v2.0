"""Joining, moving and leaving: what stops working, and what deliberately does not.

Six claims carry the weight here, and every one of them fails silently if the test goes.

**A plan that leaves a surface out looks exactly like a plan that decided nothing was needed
there.** `test_a_plan_missing_a_surface_cannot_be_constructed` and
`test_a_step_that_does_nothing_must_name_one_of_the_modules_own_reasons` are what make
`Action.NOTHING` a claim rather than a gap, and without them the next surface added to the
system is one all three plans quietly ignore.

**Cached answers are unreachable by construction, and the test has to prove that rather than
prove that an invalidation function was called.** So the mover tests build both keys with
`brain.gate.cache_key.key_for`, which is the builder the gate uses, and compare them. A test
that called a purge would pass against a design that needs purging, which is the design this
one exists to say we do not have.

**A delegation is suspended and never narrowed**, and the test asserts identity rather than
equality: a re-evaluation that rebuilt a grant with a tighter scope would produce an object
that compares equal in every field a careless test would look at.

**A revocation tested only by what it stops is satisfied by a function that stops
everything.** Every refusal here has a sibling proving the person who did not move, and the
colleague who did not leave, can still do their job.

**The starter role and the welcome count are anchored outside themselves.** `STARTER_ROLE` is
checked against `brain.identity.roles.ROLE_SPECS` and the question count against a literal,
because a test comparing a constant with the constant it imported is green for every value
that constant could hold.

**Two of the leaves are somebody else's rule, used rather than restated.** Memory recall is
`brain.memory.formation.may_recall` and knowledge reach is
`brain.knowledge.search.reach_for`, and these tests drive the real functions. A stand-in here
would be a third implementation of the central intersection, and the permissive copy is the
one that wins the day two disagree.

Task ids: M26.1.1, M26.1.2, M26.1.3, M26.1.4, M26.2.1, M26.2.2, M26.2.3, M26.2.4
Task ids: M26.2.5, M26.2.6, M26.2.7, M26.3.1, M26.3.2, M26.3.3, M26.3.4, M26.3.5
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentState,
    AgentViewer,
    visible_agent_ids,
)
from brain.core.department import department_scope
from brain.core.entitlement import VERBS, Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.cache_key import key_for
from brain.gate.resolve import cache_key as entitlement_cache_key
from brain.identity import lifecycle
from brain.identity.lifecycle import (
    STARTER_PACK,
    STARTER_ROLE,
    STARTER_VERBS,
    WELCOME_QUESTIONS,
    Action,
    Adoption,
    Automation,
    Disablement,
    LifecycleError,
    Move,
    Plan,
    Provisioning,
    Reconfirmation,
    ReconfirmReason,
    Standing,
    StarterQuestion,
    Step,
    Surface,
    Transition,
    adopt,
    agents_following,
    agents_for_adoption,
    answer_keys,
    assert_welcome_cannot_enumerate_departments,
    automation_still_reaches_anything,
    automations_to_stop,
    departure_disposition,
    disable,
    entitlement_keys,
    knowledge_reach_after,
    old_answers_are_unreachable,
    plan_for,
    provision,
    reach_changed,
    reevaluate_delegations,
    replayable_after,
    starter_entitlement,
    transition_for,
    welcome_questions,
)
from brain.identity.oidc import MappedIdentity
from brain.identity.packs import SubjectGrant, resolve_entitlement, subtractive_state
from brain.identity.roles import (
    ROLE_SPECS,
    Role,
    RoleGrant,
    appoint_deputy,
    role_capability_leaks,
)
from brain.identity.sessions import Session, SessionRegistry
from brain.identity.teams import TeamMembership, principal_subject, team_subject
from brain.knowledge.item import KnowledgeState
from brain.knowledge.search import KNOWLEDGE_READ, reach_for
from brain.knowledge.visibility import Visibility
from brain.memory.formation import Formation, recallable
from brain.ops.erasure import Disposition, disposition_of
from brain.ops.retention import DataClass, Lifetime, Store, horizon_for

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)

JOINER = "u_priya"
DEPUTY = "u_wei_ling"
ADMIN = "u_founder"
WEB = "web"
SALES = "sales"
REGISTRY = ("web", "sales", "support")

CLIENT_NAME = Capability(value="read:client.name")
CLIENT_MARGIN = Capability(value="read:client.margin")


def cap(value: str) -> Capability:
    return Capability(value=value)


def idp(department: str | None = WEB) -> MappedIdentity:
    return MappedIdentity(
        subject="kc-0f1e",
        issuer="https://id.example.test/realms/brain",
        display_name="Priya R",
        primary_department=department,
        email="priya@example.test",
        groups=("/brain/member",),
    )


def joined(
    *,
    department: str = WEB,
    claim: str | None = WEB,
    employment: Employment = Employment.STAFF,
    principal_id: str = JOINER,
    granted_by: str = ADMIN,
) -> Provisioning:
    return provision(
        idp(claim),
        principal_id=principal_id,
        employment=employment,
        department=department,
        granted_by=granted_by,
        reason="joined the team",
        now=NOW,
    )


def person(pid: str = JOINER, *, not_after: datetime | None = None) -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="Test person",
        primary_department=WEB,
        not_after=not_after,
    )


def entitlement(pid: str, *grants: Grant, not_after: datetime | None = None) -> EntitlementSet:
    return EntitlementSet(principal_id=pid, grants=grants, not_after=not_after)


def grant_in(capability: Capability, department: str) -> Grant:
    return Grant(capability=capability, scope=department_scope(department))


def session_for(pid: str, session_id: str = "sess_one") -> Session:
    return Session(
        session_id=session_id,
        principal_id=pid,
        issuer="https://id.example.test/realms/brain",
        subject="kc-0f1e",
        opened_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        absolute_expiry=NOW + timedelta(hours=8),
    )


def agent(
    agent_id: str,
    *,
    level: Visibility,
    owner_id: str,
    department: str = "",
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name=agent_id.replace("_", " "),
        persona="Answer questions about the department.",
        audience=AgentAudience(level=level, owner_id=owner_id, department=department),
        authority=AgentAuthority(capabilities=(CLIENT_NAME,), scope=department_scope(WEB)),
        created_by=owner_id,
    )


def team_grant(path: str, capability: Capability, department: str) -> SubjectGrant:
    return SubjectGrant(
        subject=team_subject(path),
        capability=capability,
        scope=department_scope(department),
        granted_by=ADMIN,
        reason="the pod needs it",
        granted_at=NOW,
    )


def department_admin(pid: str, department: str, *, deputy_of: str | None = None) -> RoleGrant:
    return RoleGrant(
        principal_id=pid,
        role=Role.DEPARTMENT_ADMIN,
        scope=department_scope(department),
        granted_by=ADMIN,
        reason="runs the department",
        granted_at=NOW - timedelta(days=1),
        not_after=NOW + timedelta(days=20) if deputy_of else None,
        deputy_of=deputy_of,
    )


def chunk_row(department: str) -> dict[str, object]:
    return {
        "deleted_at": None,
        "state": KnowledgeState.PUBLISHED.value,
        "owner_id": "u_someone_else",
        "visibility": Visibility.DEPARTMENT.value,
        "department": department,
    }


# ==================================================== the state machine and the plans
def test_a_plan_missing_a_surface_cannot_be_constructed() -> None:
    """Every transition decides about every surface, or the plan refuses to exist.

    Delete this and a surface added to the system is one all three plans quietly ignore.
    Nothing fails, nobody is told, and the omission is indistinguishable from a decision
    that nothing was needed there, which is the sentence attached to it in the incident.
    """
    short = tuple(
        step for step in plan_for(Transition.MOVE).steps if step.surface is not Surface.AUDIT
    )
    with pytest.raises(LifecycleError, match="says nothing about"):
        Plan(transition=Transition.MOVE, steps=short)


def test_a_plan_cannot_name_one_surface_twice() -> None:
    """Two steps for one surface are two decisions and nothing says which one runs.

    Delete this and the missing-surface check above can be satisfied by duplicating a step,
    which is exactly what a copy-paste while adding a surface produces.
    """
    steps = plan_for(Transition.MOVE).steps
    with pytest.raises(LifecycleError, match="names a surface twice"):
        Plan(transition=Transition.MOVE, steps=(*steps, steps[0]))


def test_a_step_that_does_nothing_must_name_one_of_the_modules_own_reasons() -> None:
    """`Action.NOTHING` is a claim about the design, so it carries a written argument.

    Delete this and "not needed" becomes an acceptable reason for leaving a surface
    unreached, which is how the answer cache stops being unreachable by construction and
    starts being unreachable by nobody having looked.
    """
    with pytest.raises(LifecycleError, match="not one of this module"):
        Step(Surface.ANSWER_CACHE, Action.NOTHING, "not needed")

    kept = Step(
        Surface.ANSWER_CACHE,
        Action.NOTHING,
        lifecycle.CACHED_ANSWERS_ARE_UNREACHABLE_BY_CONSTRUCTION,
    )
    assert kept.action is Action.NOTHING


def test_every_step_carries_an_argument() -> None:
    """A decision nobody can explain is one that gets reversed the first time it is awkward.

    Delete this and a step with an empty reason is constructible, and the reason column in
    the console renders blank for exactly the transitions nobody argued about.
    """
    with pytest.raises(LifecycleError, match="carries no argument"):
        Step(Surface.AUDIT, Action.WRITE, "   ")


def test_somebody_never_provisioned_cannot_be_disabled() -> None:
    """Disabling a person who was never provisioned reaches nothing and reports success.

    Delete this and an offboarding run over a list containing somebody who never had an
    account finishes green, which is the shape of a run that skipped the person it was for.
    """
    with pytest.raises(LifecycleError, match="never provisioned"):
        transition_for(Standing.NOT_PROVISIONED, Standing.DISABLED)


def test_nobody_transitions_back_to_never_provisioned() -> None:
    """Removing an identity is a deletion request, not a leaver form.

    Delete this and a lifecycle transition becomes a way to erase somebody without the
    request, the hold check and the certificate that `brain.ops.erasure` requires.
    """
    for before in (Standing.ACTIVE, Standing.DISABLED, Standing.NOT_PROVISIONED):
        with pytest.raises(LifecycleError, match="no transition back"):
            transition_for(before, Standing.NOT_PROVISIONED)


def test_somebody_coming_back_is_a_joiner_and_never_an_un_leaver() -> None:
    """There is nothing left to switch back on, so returning is provisioning again.

    Delete this and somebody adds a restore path, which hands a returning person the reach
    that was reviewed against the job they no longer do.
    """
    assert transition_for(Standing.DISABLED, Standing.ACTIVE) is Transition.JOIN
    assert transition_for(Standing.NOT_PROVISIONED, Standing.ACTIVE) is Transition.JOIN


def test_re_running_an_offboarding_is_still_a_leave() -> None:
    """A second disable has to reach the floor again, so it must not be refused as a no-op.

    Delete this and somebody makes a repeat leave illegal, at which point re-running an
    offboarding after a partial failure raises instead of raising the logout floor, which is
    the one part that works on a replica holding nothing.
    """
    assert transition_for(Standing.DISABLED, Standing.DISABLED) is Transition.LEAVE
    assert transition_for(Standing.ACTIVE, Standing.DISABLED) is Transition.LEAVE
    assert transition_for(Standing.ACTIVE, Standing.ACTIVE) is Transition.MOVE


# ==================================================== M26.1.1 provisioning from the IdP
def test_provisioning_records_what_the_claim_said_and_scopes_from_the_argument() -> None:
    """M26.1.1, M26.1.3. The identity provider proposes a department and never grants one.

    Delete this and the obvious simplification is to read `identity.primary_department` and
    build the scope from it, at which point a client's own directory administrator decides
    which department each of our people is bounded by, and nothing in the row says so.
    """
    provisioned = joined(department=WEB, claim=SALES)

    assert provisioned.department == WEB
    assert provisioned.assignment.scope == department_scope(WEB)
    assert provisioned.proposed_department == SALES
    assert provisioned.department_disagreement == SALES
    assert provisioned.principal.primary_department == WEB
    assert provisioned.principal.display_name == "Priya R"
    assert provisioned.principal.kind is PrincipalKind.HUMAN


def test_a_claim_that_agrees_with_the_assignment_reports_no_disagreement() -> None:
    """The positive case for the check above: agreement is silent.

    Delete this and a disagreement report that fired on every joiner would pass, and an
    operator with a page of false disagreements stops reading the page.
    """
    assert joined(department=WEB, claim=WEB).department_disagreement is None
    assert joined(department=WEB, claim=None).department_disagreement is None


def test_a_joiner_cannot_provision_themselves() -> None:
    """A grant somebody wrote for themselves is a decision the company did not make.

    Delete this and a provisioning endpoint reachable by the account it provisions is a
    self-service starter pack, which is the same failure a self-authorised break-glass
    session is.
    """
    with pytest.raises(LifecycleError, match="cannot be provisioned by"):
        joined(granted_by=JOINER)


def test_a_partner_is_never_given_a_starter_pack() -> None:
    """A partner holds nothing standing, so a pack assigned to one confers nothing.

    Delete this and a partner acquires rows that read, to everybody who looks at the grant
    table afterwards, as though they conferred access, while `standing_entitlement` goes on
    returning `NoStandingEntitlement` and the two never meet.
    """
    with pytest.raises(LifecycleError, match="break-glass"):
        provision(
            idp(),
            principal_id="u_partner",
            employment=Employment.PARTNER,
            department=WEB,
            granted_by=ADMIN,
            reason="installing",
            now=NOW,
            not_after=NOW + timedelta(days=30),
        )


def test_a_joiner_is_bounded_to_a_real_department() -> None:
    """A department that is not a slug builds no scope, so the joiner is bounded by nothing.

    Delete this and a blank or free-text department produces an assignment whose scope
    nothing narrows, which is the widest row in the system wearing an onboarding form.
    """
    for bad in ("", "Web Team", "web.pods"):
        with pytest.raises(LifecycleError, match="not a department slug"):
            joined(department=bad)


def test_a_starter_assignment_reaching_further_than_its_department_is_refused() -> None:
    """M26.1.3. Reaching a department is not the same as being bounded by one.

    Delete this and an assignment carrying the unrestricted scope passes, because an
    unrestricted scope reaches every department: the check that a joiner can see their own
    department is satisfied by a joiner who can see all of them.
    """
    provisioned = joined()
    wide = provisioned.assignment.model_copy(
        update={"scope": Scope(clauses=(Clause(field="department", op=Op.ANY, value=None),))}
    )
    with pytest.raises(LifecycleError, match="not bounded by"):
        Provisioning(
            principal=provisioned.principal,
            role_grant=provisioned.role_grant,
            assignment=wide,
            department=WEB,
            proposed_department=WEB,
        )


def test_a_naive_timestamp_anywhere_on_this_path_is_refused() -> None:
    """Every decision in this module is a comparison against `now`, and a naive timestamp
    compares as though it were UTC whatever clock wrote it. On the leaver path that is eight
    hours in which a departure has not happened yet.

    Driven through `provision`, which is the entry point a caller reaches first, so the
    refusal arrives at the boundary rather than inside an arithmetic.

    Delete this and the branch is unreachable, which is what an audit found: three modules
    carry these same three lines privately and only two of them were watched."""
    with pytest.raises(LifecycleError, match="timezone-aware"):
        provision(
            idp(),
            principal_id=JOINER,
            employment=Employment.STAFF,
            department=WEB,
            granted_by=ADMIN,
            reason="joined the team",
            now=NOW.replace(tzinfo=None),
        )


def test_a_joiner_who_does_not_start_on_the_starter_role_is_refused() -> None:
    """**M26.1.2 says a joiner starts as one role and this is what makes that a rule.** A
    provisioning record carrying any other role is a person onboarded above the floor, and
    every later check in this module reads the record rather than the intent.

    Delete this and the constant is documentation: a caller can build a provisioning holding
    Super Admin and nothing in the type says no."""
    provisioned = joined()
    elevated = provisioned.role_grant.model_copy(update={"role": Role.SUPER_ADMIN})

    with pytest.raises(LifecycleError, match="a joiner starts as"):
        Provisioning(
            principal=provisioned.principal,
            role_grant=elevated,
            assignment=provisioned.assignment,
            department=WEB,
            proposed_department=WEB,
        )


def test_a_pack_assignment_for_somebody_else_is_refused() -> None:
    """The same comparison as the role grant one, on the other row a joiner arrives with.
    Both are needed: the role grant carries a principal id and the assignment carries a
    subject, so one check cannot cover the other.

    Delete this and a loop over a joiner list that reuses an assignment produces a person
    holding somebody else's pack, with a role grant that is correctly their own."""
    mine = joined()
    theirs = joined(principal_id="u_other")

    with pytest.raises(LifecycleError, match="somebody other than the principal"):
        Provisioning(
            principal=mine.principal,
            role_grant=mine.role_grant,
            assignment=theirs.assignment,
            department=WEB,
            proposed_department=WEB,
        )


def test_a_joiner_who_does_not_start_on_the_starter_pack_is_refused() -> None:
    """The pack is where a joiner's whole reach comes from, so the wrong slug is the wrong
    reach with everything else about the record correct.

    Delete this and `STARTER_PACK` is a suggestion, and the pack a joiner lands on is
    whichever one the caller happened to pass."""
    provisioned = joined()
    other_pack = provisioned.assignment.model_copy(update={"pack_slug": "not-the-starter-pack"})

    with pytest.raises(LifecycleError, match="a joiner starts on the"):
        Provisioning(
            principal=provisioned.principal,
            role_grant=provisioned.role_grant,
            assignment=other_pack,
            department=WEB,
            proposed_department=WEB,
        )


def test_a_starter_assignment_that_does_not_reach_the_joiners_department_is_refused() -> None:
    """The first of the two scope checks, and the one that is about the joiner being able to
    work at all: an assignment bound to a department they are not in leaves them holding a
    pack that reaches nothing they can see.

    Its sibling above refuses the opposite failure, a scope that reaches their department by
    reaching every department. Both are needed and neither implies the other.

    Delete this and a joiner can be onboarded into Web with a pack bound to Sales, which
    reads as provisioned and answers nothing."""
    provisioned = joined()
    elsewhere = provisioned.assignment.model_copy(update={"scope": department_scope(SALES)})

    with pytest.raises(LifecycleError, match="does not reach"):
        Provisioning(
            principal=provisioned.principal,
            role_grant=provisioned.role_grant,
            assignment=elsewhere,
            department=WEB,
            proposed_department=WEB,
        )


# ============================================ M26.1.4 the starter questions themselves
def test_a_starter_question_that_names_no_department_is_refused() -> None:
    """**A starter question without the placeholder is a question about the company.** The
    template is filled with the joiner's own department and nothing else, so one that does not
    name it is offered to a new joiner as an invitation to ask something company-wide on their
    first day.

    Delete this and the placeholder is a convention, and the first question added without it
    is the one nobody notices."""
    with pytest.raises(LifecycleError, match="not department-scoped"):
        StarterQuestion(template="what does the company do", capabilities=(CLIENT_NAME,))


def test_a_starter_question_naming_no_capability_is_refused() -> None:
    """A question with no capability is offered to everybody, including somebody holding
    nothing, and then answered for nobody.

    Delete this and the offer list can fill with questions that pass the reach filter by
    requiring nothing to pass it with."""
    with pytest.raises(LifecycleError, match="names no capability"):
        StarterQuestion(template="what is happening in {department}", capabilities=())


def test_a_department_that_is_not_a_slug_cannot_have_questions_scoped_to_it() -> None:
    """The department is interpolated into every template and compared against every scope, so
    a value that is not a slug produces questions naming something no row carries and a scope
    test that is nonsense.

    Delete this and a blank or punctuated department reaches the template and the joiner is
    offered questions about a place that does not exist."""
    reach = entitlement(JOINER, grant_in(CLIENT_NAME, WEB))

    for bad in ("", "Web", "web team", "web;drop"):
        with pytest.raises(LifecycleError, match="not a department slug"):
            welcome_questions(reach, bad, now=NOW)


# ================================================ M26.3 what a leaver must stop reaching
def test_an_automation_with_no_id_or_no_owner_is_refused() -> None:
    """ "Whose work stops when this person goes" is the only question this record answers, so
    an automation with no id cannot be stopped and one with no owner is never reviewed, and
    the review is the only thing that ever stops it.

    Delete this and a leaver's plan can list automations that name nothing, which reads as
    coverage."""
    with pytest.raises(LifecycleError, match="needs an id"):
        Automation(automation_id="  ", owner_principal_id=JOINER)
    with pytest.raises(LifecycleError, match="needs an owner"):
        Automation(automation_id="auto_1", owner_principal_id=" ")


def test_a_provisioning_cannot_carry_another_persons_rows() -> None:
    """One comparison rules out onboarding one person with another person's grant.

    Delete this and a loop over a joiner list that reuses a role grant by mistake produces
    records that are internally consistent and about the wrong person.
    """
    mine = joined()
    theirs = joined(principal_id="u_other")
    with pytest.raises(LifecycleError, match="one comparison"):
        Provisioning(
            principal=mine.principal,
            role_grant=theirs.role_grant,
            assignment=mine.assignment,
            department=WEB,
            proposed_department=WEB,
        )


# ==================================================== M26.1.2 role and starter pack
def test_the_starter_role_is_the_one_everybody_holds() -> None:
    """M26.1.2. Anchored to `ROLE_SPECS`, which is where the answer actually lives.

    Delete this and `STARTER_ROLE` can be repointed at any member of the enum with the
    suite staying green, because every other test about it imports the constant and
    compares it against itself. Super Admin is one edit away and nothing would say so.
    """
    everyone = [role for role, spec in ROLE_SPECS.items() if spec.typical_count == "everyone"]
    assert everyone == [STARTER_ROLE]
    assert ROLE_SPECS[STARTER_ROLE].scope_required is False
    assert joined().role_grant.role is STARTER_ROLE
    assert joined().role_grant.scope is None


def test_the_starter_pack_reads_and_does_nothing_else() -> None:
    """M26.1.2. A joiner reads; writing and approving are decisions somebody makes.

    Delete this and a capability with any other verb can be added to the starter pack, and
    every new member of staff acquires it on their first day. `STARTER_VERBS` is asserted
    to be a strict subset of the whole vocabulary so that widening it to `VERBS` fails here
    rather than passing as a tautology.
    """
    assert STARTER_VERBS < VERBS
    assert {capability.verb for capability in STARTER_PACK.capabilities} <= STARTER_VERBS


def test_the_starter_pack_carries_the_read_the_document_plane_requires() -> None:
    """M26.1.2. Anchored to `brain.knowledge.search.KNOWLEDGE_READ`.

    Delete this and dropping `read:knowledge` from the pack leaves every joiner with a
    grant table that looks correct and a `reach_for` that returns None, so they retrieve
    nothing at all and the first symptom is somebody saying the search is broken.
    """
    assert KNOWLEDGE_READ in STARTER_PACK.capabilities
    reach = reach_for(starter_entitlement(joined(), now=NOW), departments=REGISTRY, now=NOW)
    assert reach is not None


def test_a_joiner_resolves_to_the_starter_pack_and_to_nothing_else() -> None:
    """M26.1.2. The pack is expanded by the real resolver, not by this test.

    Delete this and the pack could stop being the thing a joiner actually holds: an
    assignment naming a pack nobody expands, or a resolver reading packs by a second route,
    would both leave the constant looking authoritative and conferring something else.
    """
    resolved = starter_entitlement(joined(), now=NOW)
    assert sorted(g.capability.value for g in resolved.grants) == sorted(
        c.value for c in STARTER_PACK.capabilities
    )
    assert all(g.scope == department_scope(WEB) for g in resolved.grants)


def test_a_joiner_reaches_their_own_department_and_no_other() -> None:
    """M26.1.3. The department assignment is what bounds retrieval, through the real reach.

    Delete this and an assignment scoped to the department could stop bounding anything
    without the scope itself looking wrong, because the narrowing happens in `reach_for`
    and not in the row.
    """
    reach = reach_for(starter_entitlement(joined(), now=NOW), departments=REGISTRY, now=NOW)
    assert reach is not None
    assert reach.departments == (WEB,)


# ==================================================== M26.1.4 the welcome path
def test_a_welcome_path_offers_three_department_scoped_questions() -> None:
    """M26.1.4. Three, and each one names the joiner's own department and no other.

    The count is asserted as a literal rather than against `WELCOME_QUESTIONS`, which is
    imported from the module under test: comparing a constant with itself is green for
    every value it could hold. Delete this and the welcome path can offer none, one, or a
    question about a department the joiner has never heard of.
    """
    offered = welcome_questions(starter_entitlement(joined(), now=NOW), WEB, now=NOW)

    assert len(offered) == 3
    assert len(offered) == WELCOME_QUESTIONS
    assert all(WEB in question for question in offered)
    assert not any(SALES in question or "support" in question for question in offered)
    assert len(set(offered)) == 3


def test_every_starter_question_is_answerable_with_the_starter_pack() -> None:
    """M26.1.4. The questions are derived from the pack, so they can never outrun it.

    Delete this and a question can name a capability nobody is given, which offers a new
    joiner something that comes back refused on their first day, or, worse, offers it and
    is quietly filtered out so the welcome path silently shrinks.
    """
    for question in lifecycle.STARTER_QUESTIONS:
        for capability in question.capabilities:
            assert STARTER_PACK.covers(capability), question.template


def test_a_welcome_path_never_offers_a_question_the_joiner_would_be_refused() -> None:
    """M26.1.4. The filter is a filter, and the three questions discriminate.

    Delete this and dropping a capability from the pack, or from a person, would leave the
    same three questions on the screen with one of them unanswerable. The reader here holds
    two of the three requirements, so exactly one question has to go.
    """
    partial = entitlement(
        JOINER,
        grant_in(KNOWLEDGE_READ, WEB),
        grant_in(cap("read:knowledge.document"), WEB),
        grant_in(cap("read:knowledge.title"), WEB),
    )
    offered = welcome_questions(partial, WEB, now=NOW)

    assert len(offered) == 2
    assert not any("changed" in question for question in offered)


def test_a_welcome_path_offers_nothing_in_a_department_the_joiner_cannot_reach() -> None:
    """M26.1.4. A question is department-scoped in fact and not only in wording.

    Delete this and the scope check can be dropped from the filter while the capability
    check stays, which offers a joiner bounded to Web three questions about Sales: three
    questions that come back empty, and three facts about what exists.
    """
    assert welcome_questions(starter_entitlement(joined(), now=NOW), SALES, now=NOW) == ()


def test_a_company_wide_reader_is_offered_their_own_departments_questions() -> None:
    """The positive sibling: an unrestricted grant matches every department row.

    Delete this and a scope check written as "the scope names this department" would pass
    every refusal test above and hide the welcome path from everybody holding a company-wide
    grant, which reads as the feature being broken rather than as a permission bug.
    """
    wide = entitlement(
        JOINER,
        *(Grant(capability=c, scope=Scope.unrestricted()) for c in STARTER_PACK.capabilities),
    )
    assert len(welcome_questions(wide, SALES, now=NOW)) == 3


def test_a_welcome_path_cannot_be_handed_a_list_of_departments() -> None:
    """M26.1.4. DENIED and ABSENT stay indistinguishable on somebody's first day.

    Delete this and the obvious feature request, "offer a question per department they can
    reach", is a diff nothing objects to. It tells a new joiner how many departments exist
    and which are not theirs, by subtraction, before they have asked anything.
    """
    assert_welcome_cannot_enumerate_departments(welcome_questions)

    def over_a_registry(reader: EntitlementSet, departments: Sequence[str]) -> tuple[str, ...]:
        return tuple(f"{reader.principal_id}:{d}" for d in departments)

    with pytest.raises(LifecycleError, match="enumerate departments"):
        assert_welcome_cannot_enumerate_departments(over_a_registry)


# ==================================================== M26.2.1 re-resolution
def test_a_movers_old_entitlement_key_is_orphaned_by_the_version() -> None:
    """M26.2.1. The version is in the key, so nothing has to be deleted.

    Delete this and somebody replaces the version in the key with a check after the read,
    at which point the stale value was already in hand and a later refactor that drops the
    check reads as a simplification.
    """
    move = Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(CLIENT_NAME, WEB)),
        after=entitlement(JOINER, grant_in(CLIENT_NAME, SALES)),
    )
    before, after = entitlement_keys(move, before_version=7, after_version=8)

    assert before != after
    assert before == entitlement_cache_key(JOINER, 7)
    assert after == entitlement_cache_key(JOINER, 8)


def test_a_grants_version_that_moves_backwards_is_refused() -> None:
    """M26.2.1. A counter that goes backwards re-opens every key minted under it.

    Delete this and a replayed or out-of-order event that lowered the version would make
    the cache entry written under the wider entitlement readable again, and nothing else
    anywhere would notice.
    """
    move = Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(CLIENT_NAME, WEB)),
        after=entitlement(JOINER),
    )
    with pytest.raises(LifecycleError, match="moves backwards"):
        entitlement_keys(move, before_version=9, after_version=8)


def test_a_move_cannot_be_built_from_two_different_peoples_sets() -> None:
    """One comparison rules out comparing one person's old reach with another's new one.

    Delete this and a mover flow iterating a list can pair the wrong sets, and every key,
    hash and review computed from the pair is internally consistent and about nobody.
    """
    with pytest.raises(LifecycleError, match="belongs to"):
        Move(
            principal_id=JOINER,
            before=entitlement(JOINER, grant_in(CLIENT_NAME, WEB)),
            after=entitlement("u_other", grant_in(CLIENT_NAME, SALES)),
        )


# ==================================================== M26.2.2 personal agents
def test_a_personal_agent_follows_its_owner_across_a_move() -> None:
    """M26.2.2. The audience is the owner, so nothing about the record is touched.

    Delete this and somebody adds a department to a personal agent's audience on a move, or
    re-points the owner, and a person's own agents vanish from their picker the day they
    change team.
    """
    mine = agent("my_notes", level=Visibility.PERSONAL, owner_id=JOINER)
    theirs = agent("their_notes", level=Visibility.PERSONAL, owner_id=DEPUTY)
    records = (mine, theirs)

    assert agents_following(records, principal_id=JOINER) == frozenset({"my_notes"})

    before = AgentViewer(principal_id=JOINER, departments=frozenset({WEB}))
    after = AgentViewer(principal_id=JOINER, departments=frozenset({SALES}))
    assert "my_notes" in visible_agent_ids(records, before)
    assert "my_notes" in visible_agent_ids(records, after)


def test_a_department_agent_stays_with_the_department_and_not_with_the_person() -> None:
    """M26.2.2. The other half, and a test of one direction alone would not see it.

    Delete this and "personal agents follow the person" is satisfied by code that makes
    every agent follow the person, which hands a mover their old department's agents for
    ever and gives them none of their new department's.
    """
    web_agent = agent("web_helper", level=Visibility.DEPARTMENT, owner_id=ADMIN, department=WEB)
    sales_agent = agent(
        "sales_helper", level=Visibility.DEPARTMENT, owner_id=ADMIN, department=SALES
    )
    records = (web_agent, sales_agent)

    before = AgentViewer(principal_id=JOINER, departments=frozenset({WEB}))
    after = AgentViewer(principal_id=JOINER, departments=frozenset({SALES}))

    assert visible_agent_ids(records, before) == frozenset({"web_helper"})
    assert visible_agent_ids(records, after) == frozenset({"sales_helper"})
    assert agents_following(records, principal_id=JOINER) == frozenset()


# ==================================================== M26.2.3 delegations
def standing_and_deputy(department: str = WEB) -> tuple[RoleGrant, RoleGrant]:
    standing = department_admin(JOINER, department)
    deputy = appoint_deputy(
        standing,
        DEPUTY,
        granted_by=JOINER,
        reason="covering annual leave",
        now=NOW,
        days=20,
    )
    return standing, deputy


def test_a_delegation_its_delegator_can_no_longer_sustain_is_suspended() -> None:
    """M26.2.3. Suspension, and the row comes back untouched.

    Delete this and the natural fix for a delegation that no longer fits is to re-point its
    scope at whatever the delegator holds now. The deputy would then be doing a smaller,
    different thing that nobody asked them about, and every row would look correct.
    """
    _, deputy = standing_and_deputy()
    moved = department_admin(JOINER, SALES)

    review = reevaluate_delegations([deputy], delegator_grants=[moved], now=LATER)

    assert review.standing == ()
    assert len(review.to_reconfirm) == 1
    item = review.to_reconfirm[0]
    assert item.because is ReconfirmReason.DELEGATOR_SCOPE_NO_LONGER_COVERS_IT
    assert item.delegator_id == JOINER
    # Identity, not equality. A re-evaluation that rebuilt the grant with a tighter scope
    # would produce something that compares equal in every field a careless test reads.
    assert item.delegation is deputy
    assert item.delegation.scope == department_scope(WEB)


def test_a_delegation_still_inside_its_delegators_scope_goes_on_standing() -> None:
    """M26.2.3. The positive case, without which suspending everything would pass.

    Delete this and a re-evaluation that suspended every delegation on every move would
    satisfy the test above, and the console would fill with reconfirmation requests that
    teach every delegator to confirm without reading.
    """
    standing, deputy = standing_and_deputy()

    review = reevaluate_delegations([deputy], delegator_grants=[standing], now=LATER)

    assert review.to_reconfirm == ()
    assert review.expired == ()
    assert review.standing[0] is deputy


def test_a_delegator_whose_scope_widened_keeps_the_delegations_they_made() -> None:
    """M26.2.3. Widening is not a reason to suspend, and equality would say it was.

    Delete this and the scope test can be written as an equality, which suspends every
    delegation held by anybody who was promoted. Nothing about that is unsafe and all of it
    is noise, which is how a reconfirmation queue stops being read.
    """
    narrow = Scope(
        clauses=(
            Clause(field="department", op=Op.EQ, value=WEB),
            Clause(field="team", op=Op.EQ, value="web_pods"),
        )
    )
    standing = RoleGrant(
        principal_id=JOINER,
        role=Role.DEPARTMENT_ADMIN,
        scope=narrow,
        granted_by=ADMIN,
        reason="runs one pod",
        granted_at=NOW - timedelta(days=1),
    )
    deputy = appoint_deputy(standing, DEPUTY, granted_by=JOINER, reason="cover", now=NOW, days=20)
    widened = department_admin(JOINER, WEB)

    review = reevaluate_delegations([deputy], delegator_grants=[widened], now=LATER)

    assert review.to_reconfirm == ()
    assert review.standing[0] is deputy


def test_a_delegator_who_holds_nothing_suspends_their_delegations() -> None:
    """M26.2.3. The leaver case: the standing grant is gone, so the cover is gone with it.

    Delete this and a deputy goes on holding a department admin's authority after the
    department admin has left, which is a standing grant that nobody appointed and that no
    review will find, because the row it hangs off does not exist.
    """
    _, deputy = standing_and_deputy()

    review = reevaluate_delegations([deputy], delegator_grants=[], now=LATER)

    assert review.to_reconfirm[0].because is ReconfirmReason.DELEGATOR_NO_LONGER_HOLDS_THE_ROLE


def test_a_delegator_holding_the_role_only_as_a_deputy_cannot_sustain_a_delegation() -> None:
    """M26.2.3. Deputies are depth one, and a move can create the chain a check refuses.

    Delete this and a move that leaves somebody covering the role they used to hold turns
    their existing delegation into a two-link chain, which is the arrangement
    `appoint_deputy` refuses at appointment time and nothing re-checks afterwards.
    """
    _, deputy = standing_and_deputy()
    now_a_deputy = department_admin(JOINER, WEB, deputy_of=ADMIN)

    review = reevaluate_delegations([deputy], delegator_grants=[now_a_deputy], now=LATER)

    assert review.to_reconfirm[0].because is ReconfirmReason.DELEGATOR_HOLDS_IT_ONLY_AS_A_DEPUTY


def test_an_expired_delegation_is_not_put_in_the_reconfirmation_queue() -> None:
    """M26.2.3. An appointment that ended as intended needs no decision from anybody.

    Delete this and every lapsed deputy appointment reappears as a request to re-open it,
    which both buries the suspensions that matter and asks delegators to renew things they
    deliberately time-boxed.
    """
    _, deputy = standing_and_deputy()
    after_it_ended = NOW + timedelta(days=25)

    review = reevaluate_delegations(
        [deputy], delegator_grants=[department_admin(JOINER, SALES)], now=after_it_ended
    )

    assert review.to_reconfirm == ()
    assert review.standing == ()
    assert review.expired[0] is deputy


def test_a_standing_grant_handed_in_as_a_delegation_is_refused() -> None:
    """M26.2.3. Suspending somebody's own role because their colleague moved is the misuse.

    Delete this and passing the whole role grant table to the re-evaluator suspends every
    grant whose holder covers for somebody who moved, which takes roles away from people
    nobody delegated anything to.

    Matched on the re-evaluator's own wording rather than on the phrase both refusals share.
    `Reconfirmation` refuses the same thing at construction, deliberately, and a looser
    match here would be satisfied by the second guard while the first one was gone.
    """
    with pytest.raises(LifecycleError, match="re-evaluating one here"):
        reevaluate_delegations([department_admin(JOINER, WEB)], delegator_grants=[], now=LATER)


def test_a_reconfirmation_has_nowhere_to_put_a_narrowed_delegation() -> None:
    """M26.2.3. Narrowing is structurally impossible rather than merely absent.

    Delete this and a `suggested_scope` field can be added beside the delegation, which is
    the value the console renders and the thing a delegator confirms, so the narrowing
    happens with a click and an audit row saying they agreed to it.
    """
    names = {field.name for field in dataclass_fields(Reconfirmation)}
    assert names == {"delegation", "delegator_id", "because"}

    _, deputy = standing_and_deputy()
    with pytest.raises(LifecycleError, match="must be the person"):
        Reconfirmation(
            delegation=deputy,
            delegator_id=ADMIN,
            because=ReconfirmReason.DELEGATOR_NO_LONGER_HOLDS_THE_ROLE,
        )
    # The second guard, and the reason the test above matches on the re-evaluator's wording:
    # the routing check is the one a refactor drops and this is the one a hand-built object
    # goes around, so both exist and each is asserted where it fires.
    with pytest.raises(LifecycleError, match="suspending one here"):
        Reconfirmation(
            delegation=department_admin(JOINER, WEB),
            delegator_id=ADMIN,
            because=ReconfirmReason.DELEGATOR_NO_LONGER_HOLDS_THE_ROLE,
        )


# ==================================================== M26.2.4 the answer cache
def moved_person() -> Move:
    return Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(CLIENT_NAME, WEB)),
        after=entitlement(JOINER, grant_in(CLIENT_NAME, SALES)),
    )


def cached_key(reach: EntitlementSet) -> str:
    return key_for(
        "how many clients are on retainer",
        reach.ent_hash(),
        "agent-cfg-1",
        4,
        {"laravel": 12},
    )


def test_a_mover_cannot_construct_the_key_their_old_answers_sit_under() -> None:
    """M26.2.4. Proved on the real key builder, and with no invalidation call anywhere.

    Delete this and the property that makes the answer cache safe stops being checked, and
    the first person to add a component to the key that is not derived from reach, or to
    key on the principal instead, breaks it invisibly: nothing fails, and one person's
    answer is served to another.
    """
    move = moved_person()
    assert reach_changed(move) is True

    before, after = answer_keys(
        move,
        question="how many clients are on retainer",
        agent_config_hash="agent-cfg-1",
        policy_epoch=4,
        source_epochs={"laravel": 12},
    )
    assert before != after
    assert before == cached_key(move.before)
    assert after == cached_key(move.after)
    assert old_answers_are_unreachable(
        move,
        question="how many clients are on retainer",
        agent_config_hash="agent-cfg-1",
        policy_epoch=4,
        source_epochs={"laravel": 12},
    )


def test_somebody_whose_reach_did_not_change_still_reaches_their_cached_answers() -> None:
    """M26.2.4. The positive sibling, and it is the one that keeps the cache a cache.

    Delete this and a key that changed on every transition would pass the test above while
    throwing away every cached answer whenever anybody changed desk, and the only symptom
    would be a latency complaint.
    """
    same = Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(CLIENT_NAME, WEB)),
        after=entitlement(JOINER, grant_in(CLIENT_NAME, WEB)),
    )
    assert reach_changed(same) is False
    assert not old_answers_are_unreachable(
        same,
        question="how many clients are on retainer",
        agent_config_hash="agent-cfg-1",
        policy_epoch=4,
        source_epochs={"laravel": 12},
    )


def test_nothing_in_the_mover_plan_purges_a_cache() -> None:
    """M26.2.4. The absence is the leaf, so the absence is what is asserted.

    Delete this and a purge step is added to the mover plan by somebody being careful, and
    from that moment the property that makes the purge unnecessary stops being maintained
    and the purge becomes the thing that has to be remembered.
    """
    plan = plan_for(Transition.MOVE)

    assert plan.action_at(Surface.ANSWER_CACHE) is Action.NOTHING
    assert plan.action_at(Surface.ENTITLEMENT_CACHE) is Action.NOTHING
    assert plan.action_at(Surface.KNOWLEDGE_INDEX) is Action.NOTHING
    assert (
        plan.reason_at(Surface.ANSWER_CACHE)
        is lifecycle.CACHED_ANSWERS_ARE_UNREACHABLE_BY_CONSTRUCTION
    )


# ==================================================== M26.2.5 memory
def formed(capability: Capability, department: str) -> Formation:
    return Formation(
        principal_id=JOINER,
        capabilities=(capability,),
        scope=department_scope(department),
        ent_hash="0" * 32,
        formed_at=NOW,
    )


def test_a_memory_formed_under_a_capability_the_mover_lost_is_not_replayed() -> None:
    """M26.2.5. Checked through the real `may_recall`, with nothing rewritten.

    Delete this and a mover goes on being told what the system learnt while they had reach
    they no longer have, and the disclosure arrives looking like the system being helpful.
    """
    move = Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(CLIENT_MARGIN, WEB)),
        after=entitlement(JOINER, grant_in(CLIENT_NAME, SALES)),
    )
    memory = formed(CLIENT_MARGIN, WEB)

    assert len(recallable([(memory, 1.0)], move.before, now=NOW)) == 1
    assert replayable_after(move, [(memory, 1.0)], now=NOW) == ()


def test_a_memory_the_mover_still_reaches_is_still_replayed() -> None:
    """M26.2.5. The positive sibling: a move must not wipe somebody's working memory.

    Delete this and a rule that replayed nothing after a move would pass the test above,
    and every mover would arrive in their new team with the system having forgotten
    everything it knew about how they work.
    """
    move = Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(CLIENT_MARGIN, WEB)),
        after=entitlement(JOINER, grant_in(CLIENT_NAME, SALES)),
    )
    still_theirs = formed(CLIENT_NAME, SALES)

    replayed = replayable_after(move, [(still_theirs, 1.0)], now=NOW)
    assert len(replayed) == 1
    assert replayed[0].formation is still_theirs


# ==================================================== M26.2.6 knowledge
def test_a_move_changes_which_chunks_are_retrievable_without_touching_a_row() -> None:
    """M26.2.6. The same row object is admitted before and refused after.

    Delete this and somebody stores the readers on the chunk, which turns every grant
    change into an index rewrite; the rewrite that does not complete is a person still
    retrieving what they may no longer see, and nothing reports a partial rewrite.
    """
    move = Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(KNOWLEDGE_READ, WEB)),
        after=entitlement(JOINER, grant_in(KNOWLEDGE_READ, SALES)),
    )
    row = chunk_row(WEB)

    before = reach_for(move.before, departments=REGISTRY, now=NOW)
    after = knowledge_reach_after(move, departments=REGISTRY, now=NOW)
    assert before is not None
    assert after is not None

    assert before.departments == (WEB,)
    assert after.departments == (SALES,)
    assert before.admits(row) is True
    assert after.admits(row) is False
    # The row was never handed to a writer, and there is nothing here that could have been.
    assert row == chunk_row(WEB)


def test_a_mover_reaches_their_new_departments_documents() -> None:
    """M26.2.6. The positive sibling: a move is a change of reach, not a loss of it.

    Delete this and a reach that admitted nothing after a move would satisfy the test
    above, and every mover would arrive with an empty knowledge base and no way to tell
    that from a department with nothing in it.
    """
    move = Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(KNOWLEDGE_READ, WEB)),
        after=entitlement(JOINER, grant_in(KNOWLEDGE_READ, SALES)),
    )
    after = knowledge_reach_after(move, departments=REGISTRY, now=NOW)
    assert after is not None
    assert after.admits(chunk_row(SALES)) is True


# ==================================================== M26.2.7 all of it, once
def test_one_move_reaches_every_one_of_the_mover_leaves() -> None:
    """M26.2.7. One transition, and all six of the leaves above asserted on it.

    This is the leaf: the six properties are individually true and the question is whether
    one real move exercises all of them together. Delete it and each half stays tested in
    isolation, which is exactly the arrangement in which two of them can be true only for
    different inputs.
    """
    move = Move(
        principal_id=JOINER,
        before=entitlement(JOINER, grant_in(KNOWLEDGE_READ, WEB), grant_in(CLIENT_MARGIN, WEB)),
        after=entitlement(JOINER, grant_in(KNOWLEDGE_READ, SALES)),
    )
    question = "which clients need chasing"

    # M26.2.1 re-resolution: the key is orphaned by the version, nothing is deleted.
    old_key, new_key = entitlement_keys(move, before_version=11, after_version=12)
    assert old_key != new_key
    assert plan_for(Transition.MOVE).action_at(Surface.ENTITLEMENT_CACHE) is Action.NOTHING

    # M26.2.2 personal agents follow the person.
    records = (
        agent("my_notes", level=Visibility.PERSONAL, owner_id=JOINER),
        agent("web_helper", level=Visibility.DEPARTMENT, owner_id=ADMIN, department=WEB),
    )
    assert agents_following(records, principal_id=JOINER) == frozenset({"my_notes"})
    assert "my_notes" in visible_agent_ids(
        records, AgentViewer(principal_id=JOINER, departments=frozenset({SALES}))
    )

    # M26.2.3 delegations suspended, never narrowed.
    _, deputy = standing_and_deputy()
    review = reevaluate_delegations(
        [deputy], delegator_grants=[department_admin(JOINER, SALES)], now=LATER
    )
    assert review.standing == ()
    assert review.to_reconfirm[0].delegation is deputy

    # M26.2.4 cached answers unreachable by construction.
    assert old_answers_are_unreachable(
        move,
        question=question,
        agent_config_hash="cfg",
        policy_epoch=2,
        source_epochs={"laravel": 3},
    )

    # M26.2.5 memories tagged with the old capability set are not replayed.
    memory = formed(CLIENT_MARGIN, WEB)
    assert len(recallable([(memory, 1.0)], move.before, now=NOW)) == 1
    assert replayable_after(move, [(memory, 1.0)], now=NOW) == ()

    # M26.2.6 knowledge access changes with no reindex.
    row = chunk_row(WEB)
    before_reach = reach_for(move.before, departments=REGISTRY, now=NOW)
    after_reach = knowledge_reach_after(move, departments=REGISTRY, now=NOW)
    assert before_reach is not None and after_reach is not None
    assert before_reach.admits(row) and not after_reach.admits(row)
    assert row == chunk_row(WEB)


# ==================================================== M26.3.1 the leaver's disable
def test_a_disable_deletes_the_grants_ends_the_sessions_and_bounds_the_principal() -> None:
    """M26.3.1. Three acts, one call, and no argument that skips any of them.

    Delete this and the three drift apart. Grants deleted with a session left live is the
    revocation defeated for up to ten hours; sessions ended with the principal unbounded is
    the same failure one token later, because the floor refuses what was issued and admits
    what is issued next.
    """
    provisioned = joined()
    registry = SessionRegistry()
    registry.register(session_for(JOINER))
    assert len(registry.live_for(JOINER, NOW)) == 1

    disabled = disable(
        provisioned.principal,
        registry=registry,
        now=LATER,
        assignments=(provisioned.assignment,),
        packs={STARTER_PACK.slug: STARTER_PACK},
    )

    assert disabled.remaining_assignments == ()
    assert len(disabled.ended_sessions) == 1
    assert registry.live_for(JOINER, LATER) == ()
    assert registry.not_before_for(JOINER) == LATER
    assert disabled.principal.not_after == LATER
    assert disabled.principal.is_active(LATER) is False


def test_a_leaver_still_reached_through_a_team_is_refused() -> None:
    """M26.3.1. A subject filter over the grant rows looks complete and is not.

    Delete this and a leaver keeps every capability their pod holds, because the grant
    naming the team is not theirs to delete and the membership that carries it to them was
    never removed. The postcondition here runs the real resolver, which is the only check
    that sees it.
    """
    registry = SessionRegistry()
    grants = (team_grant("web.pods", CLIENT_NAME, WEB),)
    memberships = (TeamMembership(principal_id=JOINER, team_path="web.pods", since=NOW),)

    disabled = disable(
        person(),
        registry=registry,
        now=LATER,
        grants=grants,
        memberships=memberships,
    )

    assert disabled.remaining_grants == grants
    assert disabled.remaining_memberships == ()
    resolved = resolve_entitlement(
        disabled.principal,
        grants=disabled.remaining_grants,
        memberships=disabled.remaining_memberships,
        now=LATER,
    )
    assert isinstance(resolved, EntitlementSet)
    assert resolved.grants == ()


def test_disabling_one_person_leaves_everybody_else_working() -> None:
    """M26.3.1. A revocation tested only by what it stops is satisfied by stopping all of it.

    Delete this and a disable that deleted every row and ended every session in the system
    would pass every other test here, and the first symptom would be the whole company
    signed out on the day somebody left.
    """
    # Ten minutes in, so the colleague's session is still inside its idle window: the claim
    # is that this disable left it alone, not that it outlived `SESSION_IDLE`.
    soon = NOW + timedelta(minutes=10)
    registry = SessionRegistry()
    registry.register(session_for(JOINER, "sess_leaver"))
    registry.register(session_for(DEPUTY, "sess_stayer"))
    grants = (
        team_grant("web.pods", CLIENT_NAME, WEB),
        SubjectGrant(
            subject=principal_subject(DEPUTY),
            capability=CLIENT_NAME,
            scope=department_scope(WEB),
            granted_by=ADMIN,
            reason="does the work",
            granted_at=NOW,
        ),
    )
    memberships = (
        TeamMembership(principal_id=JOINER, team_path="web.pods", since=NOW),
        TeamMembership(principal_id=DEPUTY, team_path="web.pods", since=NOW),
    )

    disabled = disable(
        person(), registry=registry, now=soon, grants=grants, memberships=memberships
    )

    assert registry.live_for(JOINER, soon) == ()
    assert len(registry.live_for(DEPUTY, soon)) == 1
    assert registry.not_before_for(DEPUTY) is None
    assert len(disabled.remaining_memberships) == 1
    assert disabled.remaining_memberships[0].principal_id == DEPUTY

    stayer = resolve_entitlement(
        person(DEPUTY),
        grants=disabled.remaining_grants,
        memberships=disabled.remaining_memberships,
        now=soon,
    )
    assert isinstance(stayer, EntitlementSet)
    assert sorted(g.capability.value for g in stayer.grants) == [
        CLIENT_NAME.value,
        CLIENT_NAME.value,
    ]


def test_a_disablement_cannot_be_built_for_somebody_still_active() -> None:
    """M26.3.1. Holding one of these has to be evidence that the disable happened.

    Delete this and a `Disablement` can be constructed for a person who is still active,
    which is a record saying somebody was disabled sitting beside an account that still
    accepts a fresh token.
    """
    with pytest.raises(LifecycleError, match="still active"):
        Disablement(
            principal=person(),
            at=LATER,
            remaining_grants=(),
            remaining_assignments=(),
            remaining_memberships=(),
            ended_sessions=(),
            not_before=LATER,
        )


def test_a_disablement_cannot_carry_a_floor_that_predates_it() -> None:
    """M26.3.1. A floor before the disable admits a token minted between the two.

    Delete this and a stale floor read from a replica, or one raised by an earlier logout,
    satisfies the record while leaving a window in which a token issued after the earlier
    event and before the disable is accepted.
    """
    with pytest.raises(LifecycleError, match="floor"):
        Disablement(
            principal=person(not_after=NOW),
            at=LATER,
            remaining_grants=(),
            remaining_assignments=(),
            remaining_memberships=(),
            ended_sessions=(),
            not_before=NOW,
        )


def test_a_disable_raises_the_floor_even_with_no_session_to_end() -> None:
    """M26.3.1. The case the floor exists for: a replica that never held the session.

    Delete this and an implementation that returned early when there was nothing to end
    would pass every other test here and fail in production behind a load balancer, where
    the process handling the disable is not the one holding the session.
    """
    registry = SessionRegistry()
    disabled = disable(person(), registry=registry, now=LATER)

    assert disabled.ended_sessions == ()
    assert disabled.not_before == LATER
    assert registry.not_before_for(JOINER) == LATER


# ==================================================== M26.3.2 owned agents
def test_an_agent_whose_steward_has_left_is_stopped_and_queued() -> None:
    """M26.3.2. The default is that it stops, and reversibly.

    Delete this and an agent whose owner has gone keeps answering against a persona and a
    ceiling signed off by somebody who is not here, and the person who would notice it
    going wrong is the one who left.
    """
    mine = agent("renewal_chaser", level=Visibility.DEPARTMENT, owner_id=JOINER, department=WEB)
    theirs = agent("support_triage", level=Visibility.DEPARTMENT, owner_id=DEPUTY, department=WEB)

    queued = agents_for_adoption((mine, theirs), departing=frozenset({JOINER}), now=LATER)

    assert [item.agent_id for item in queued] == ["renewal_chaser"]
    assert queued[0].record.state is AgentState.DISABLED
    assert queued[0].record.disabled_at == LATER
    assert queued[0].former_owner_id == JOINER
    # Disabled and not archived: it is waiting for a decision rather than finished.
    assert queued[0].record.archived_at is None


def test_an_agent_whose_steward_stayed_is_left_alone() -> None:
    """M26.3.2. The positive sibling, without which stopping everything would pass.

    Delete this and an offboarding run that disabled the whole estate would satisfy the
    test above, and one person leaving would stop every agent in the company.
    """
    theirs = agent("support_triage", level=Visibility.DEPARTMENT, owner_id=DEPUTY, department=WEB)
    assert agents_for_adoption((theirs,), departing=frozenset({JOINER}), now=LATER) == ()


def test_an_adoption_cannot_hold_an_agent_that_is_still_running() -> None:
    """M26.3.2. A flagged agent that was left running does damage while it waits.

    Delete this and the queue can be built from live records, so "flagged for adoption"
    becomes a label on a report rather than a thing that happened, and the wait is however
    long it takes somebody to read the report.
    """
    live = agent("renewal_chaser", level=Visibility.DEPARTMENT, owner_id=JOINER, department=WEB)
    with pytest.raises(LifecycleError, match="still selectable"):
        Adoption(agent_id=live.agent_id, record=live, former_owner_id=JOINER)


def test_adopting_an_agent_gives_it_a_steward_and_starts_it_again() -> None:
    """M26.3.2. Adoption is the deliberate act, and it moves the steward and nothing else.

    Delete this and the queue becomes a list nothing can be done with, or adoption starts
    an agent without moving the owner, which is the state the queue exists to leave.
    """
    mine = agent("renewal_chaser", level=Visibility.DEPARTMENT, owner_id=JOINER, department=WEB)
    queued = agents_for_adoption((mine,), departing=frozenset({JOINER}), now=LATER)

    adopted = adopt(queued[0], to_owner=person(DEPUTY), now=LATER)

    assert adopted.audience.owner_id == DEPUTY
    assert adopted.state is AgentState.ENABLED
    assert adopted.created_by == JOINER
    assert adopted.authority == mine.authority


def test_an_agent_is_not_adopted_by_somebody_who_has_also_left() -> None:
    """M26.3.2. One leaver's agents handed to another leaver look correctly owned.

    Delete this and an offboarding run down a list gives the first leaver's agents to the
    second, and every record reads as though the work has a steward.
    """
    mine = agent("renewal_chaser", level=Visibility.DEPARTMENT, owner_id=JOINER, department=WEB)
    queued = agents_for_adoption((mine,), departing=frozenset({JOINER}), now=LATER)

    with pytest.raises(Exception, match="not active"):
        adopt(queued[0], to_owner=person(DEPUTY, not_after=NOW), now=LATER)


# ==================================================== M26.3.3 automations
def test_a_leavers_automations_are_stopped_by_ownership_and_not_by_their_reach() -> None:
    """M26.3.3. An empty reach is a safety property and it is not a stop.

    Delete this and somebody relies on the intersection: the flow keeps running, reaches
    nothing, and looks healthy on every screen while the work it was doing quietly stops
    being done and the budget goes on being spent.
    """
    flows = (
        Automation(automation_id="chase_renewals", owner_principal_id=JOINER),
        Automation(automation_id="triage_tickets", owner_principal_id=DEPUTY),
    )

    assert automations_to_stop(flows, departing=frozenset({JOINER})) == ("chase_renewals",)

    ceiling = entitlement("flow:chase_renewals", grant_in(CLIENT_NAME, WEB))
    assert (
        automation_still_reaches_anything(flow_ceiling=ceiling, owner=entitlement(JOINER)) is False
    )


def test_a_colleagues_automations_are_not_stopped() -> None:
    """M26.3.3. The positive sibling: stopping everything is not an offboarding.

    Delete this and a filter that returned every automation would pass the test above, and
    one departure would stop every scheduled job the company runs.
    """
    flows = (Automation(automation_id="triage_tickets", owner_principal_id=DEPUTY),)
    assert automations_to_stop(flows, departing=frozenset({JOINER})) == ()

    ceiling = entitlement("flow:triage_tickets", grant_in(CLIENT_NAME, WEB))
    owner = entitlement(DEPUTY, grant_in(CLIENT_NAME, WEB))
    assert automation_still_reaches_anything(flow_ceiling=ceiling, owner=owner) is True


def test_an_automation_owned_by_nobody_is_refused() -> None:
    """M26.3.3. A flow nobody owns is a flow nobody reviews and nothing ever stops.

    Delete this and a row with a blank owner is never named by `automations_to_stop`, for
    any departure, so it runs until somebody finds it by accident.
    """
    with pytest.raises(LifecycleError, match="needs an owner"):
        Automation(automation_id="orphan", owner_principal_id="  ")


# ==================================================== M26.3.4 and M26.3.5 disposition
def test_a_departure_retains_what_a_deletion_request_would_erase() -> None:
    """M26.3.4. Leaving is a change of reach, not a decision that the record should go.

    Delete this and offboarding acquires an erase, which destroys the company's own record
    on an event that is not a deletion request, with none of the hold check, the ordering
    or the certificate `brain.ops.erasure` requires.
    """
    for store in (Store.KNOWLEDGE, Store.MEMORY, Store.CONVERSATION, Store.AGENTS):
        assert disposition_of(store) is Disposition.ERASE, store
        assert departure_disposition(store) is Disposition.RETAINED, store


def test_a_departure_reaches_the_cache_and_the_index_by_leaving_them_alone() -> None:
    """M26.3.4. The same construction the mover rests on, stated for the leaver.

    Delete this and the leaver flow acquires a purge, which is work that cannot fail
    usefully: there is nothing under those keys to remove, and the purge becomes a step
    people believe is doing something.
    """
    for store in (Store.CACHE, Store.INDEX):
        assert disposition_of(store) is Disposition.PURGE, store
        assert departure_disposition(store) is Disposition.RETAINED, store


def test_a_departure_erases_the_rows_that_confer_access_and_only_those() -> None:
    """M26.3.4. One store is erased, and that erasure is the whole revocation.

    Delete this and `departure_disposition` can return RETAINED everywhere, which is a
    leaver who keeps their grants, or ERASE everywhere, which is a deletion request nobody
    made. Both read as one word changed in a match statement.
    """
    erased = [store for store in Store if departure_disposition(store) is Disposition.ERASE]
    assert erased == [Store.ROWS]


def test_the_audit_record_survives_a_departure_and_every_transition() -> None:
    """M26.3.5. Anchored to the two modules that own the answer, not restated here.

    Delete this and the audit ledger becomes reachable by an offboarding path, which is the
    one store a deletion request itself does not reach; the record of what somebody did
    would go on the day they stopped being here to explain it.
    """
    assert horizon_for(DataClass.AUDIT).lifetime is Lifetime.NEVER_EXPIRES
    assert disposition_of(Store.AUDIT) is Disposition.RETAINED
    assert departure_disposition(Store.AUDIT) is Disposition.RETAINED

    for transition in Transition:
        plan = plan_for(transition)
        assert plan.action_at(Surface.AUDIT) is Action.WRITE, transition


# ==================================================== the package invariants
def test_nothing_in_this_module_subtracts_at_resolve_time() -> None:
    """M1.4.2 applied here. A suspension is not a column and must never become one.

    Delete this and the first person who wants a delegation suspended in the table adds a
    `suspended` flag, and from that moment resolution has an order, two rows can disagree,
    and no grant can be read on its own again. `brain.identity.lifecycle` is not in
    `IDENTITY_MODULES`, which is a tuple in another agent's file, so this is where the sweep
    reaches it.
    """
    assert subtractive_state(lifecycle) == []


def test_no_name_here_maps_a_role_to_a_capability() -> None:
    """M1.3.5 applied here. The starter pack sits next to the starter role in one module.

    Delete this and the convenient next step is a mapping from role to starter pack, which
    is a role implying a capability, in the one module that holds both halves.
    """
    assert role_capability_leaks(vars(lifecycle)) == []
