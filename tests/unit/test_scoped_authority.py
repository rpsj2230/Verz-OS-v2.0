"""A department head held to their own scope in every act that puts a reach into the world.

The file is written around one refusal and four applications of it. **M33.2.2.2 was a live
privilege-escalation path**: an admin holding the grant authority in one department could
write themselves a company-wide capability, and because entitlements are additive with no
deny list anywhere, nothing downstream could take it back. The first section below is that
refusal, its positive half, and the property that makes a permitted self-grant harmless.

The other four are the same containment asked about a different noun. A deputy appointment is
a role in a scope, so a department admin cannot deputise a company-wide role (M33.2.2.5), and
the thirty days is read off the leaf sentence rather than out of the module, because a test
importing `DEPUTY_MAX` and asserting it equals thirty is green for every value it could hold.
A publication is a ceiling, so an approver who could not have written one of its capabilities
is not offered it (M33.2.2.1). An adoption is that same ceiling restarting under a new name
(M33.2.2.3). A rung is the exception and is here to be one: supervision is not reach, so it
takes the Approvals capability rather than the grant one, and it has a second ceiling of its
own that nothing was checking (M33.2.2.4).

M33.2.1.2, the department's own activity, is the sixth and is not the same shape as the other
five: its authority is not a scope at all, because an audit entry carries no department for a
scope to be written against. The tests for it run a real `AuditView` over real entries with
the grants `brain.identity.staff_sync.audit_reach_for_head` produces, for the reason recorded
in item 48: every fixture in this repository that used a company-wide audit grant passed while
the page was empty for every reader it exists for.

Real `EntitlementSet`s, real `SubjectGrant`s through their own validators, a real
`RoleGrant`, real `AgentRecord`s and a real `Adoption` throughout. The pack test runs
`brain.identity.packs.expand` rather than building the expanded rows by hand, because the
claim being made is about what that function produces.

Task ids: M33.2.1.2, M33.2.1.4, M33.2.2.1, M33.2.2.2, M33.2.2.3, M33.2.2.4, M33.2.2.5
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    entitlement_ceiling,
)
from brain.audit.ledger import AuditAction, AuditChain, AuditEntry
from brain.audit.view import CAPABILITY_BY_KIND, AuditFilter, AuditView
from brain.console.govern import Placed, may_certify
from brain.console.reach_view import Operation, PromotionEvidence
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import (
    ACTIVITY_AUTHORITY,
    BUDGET_AUTHORITY,
    COVERAGE_AUTHORITY,
    REACH_AUTHORITY,
    REACH_AUTHORITY_SCREEN,
    RUNG_AUTHORITY,
    RUNG_AUTHORITY_SCREEN,
    AuthorityError,
    activity_basis,
    adoptable,
    appoint,
    approvable,
    authority_gaps,
    ceiling_within_reach,
    department_activity,
    department_coverage,
    department_pace,
    deputy_runs_at_most,
    grantable,
    may_adopt,
    may_appoint_deputy,
    may_approve_publication,
    may_grant,
    may_move_rung,
    within_ceiling,
    within_reach,
    write_grant,
)
from brain.console.screens import screen
from brain.console.spend_view import pace
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.core.scope_sql import scope_narrows
from brain.gate.injection import AutonomyTier
from brain.gate.leash import LeashEntry
from brain.identity.lifecycle import Adoption
from brain.identity.packs import CapabilityPack, PackAssignment, SubjectGrant, expand
from brain.identity.roles import DEPUTY_MAX, IdentityError, Role, RoleGrant
from brain.identity.staff_source import DEFAULT_TRUST, Roster, StaffRecord
from brain.identity.staff_sync import (
    AUDIT_PAGE_CAPABILITY,
    GRANT_LIFETIME,
    SYNC_INTERVAL,
    audit_reach_for_head,
)
from brain.identity.teams import principal_subject
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.ops.budgets import Allowance, BudgetLevel, BudgetPeriod, BudgetRow
from brain.status import leaf_sentences

#: A fixed moment, so an expiry test cannot pass because the machine's clock sat on the
#: convenient side of a boundary. Everything below is relative to it.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)

#: Two departments, so a scoped admin has somewhere to be refused.
MAINTENANCE = "maintenance"
FINANCE = "finance"

#: The capabilities the grants below are written over.
NAME = "read:client.name"
CONTRACT_VALUE = "read:client.contract_value"
EVERY_CLIENT_FIELD = "read:client.*"

#: Every leaf of the work breakdown by id, so a constant can be checked against the sentence
#: that specifies it rather than against itself. See `brain.status.leaf_sentences`.
LEAF_SENTENCES = leaf_sentences(Path(__file__).resolve().parents[2] / "docs" / "wbs.json")

#: The words a leaf sentence writes a small number in, so a figure can be read out of it.
NUMBER_WORDS = {"seven": 7, "fourteen": 14, "thirty": 30, "sixty": 60, "ninety": 90}


def holding(
    *capabilities: str,
    scope: Scope | None = None,
    principal_id: str = "u_admin",
    not_after: datetime | None = None,
) -> EntitlementSet:
    """One admin holding these capabilities in one scope.

    Built here rather than taken from the company fixture, because almost every test below
    varies exactly one of the three axes: which capability, which scope, and which expiry.
    """
    where = scope if scope is not None else Scope(clauses=())
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=Capability(value=one), scope=where) for one in capabilities),
        not_after=not_after,
    )


def proposal(
    capability: str,
    *,
    scope: Scope,
    subject_id: str = "u_1",
    granted_by: str = "u_admin",
    not_after: datetime | None = None,
) -> SubjectGrant:
    """One proposed grant row, through `SubjectGrant`'s own validators."""
    return SubjectGrant(
        subject=principal_subject(subject_id),
        capability=Capability(value=capability),
        scope=scope,
        granted_by=granted_by,
        reason="written for a test",
        granted_at=NOW,
        not_after=not_after,
    )


def an_agent(
    *capabilities: str,
    scope: Scope,
    agent_id: str = "a_reporter",
    disabled: bool = False,
) -> AgentRecord:
    """One agent whose authority reaches these capabilities over this scope."""
    return AgentRecord(
        agent_id=agent_id,
        display_name="Reporter",
        persona="answers questions about clients",
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_gone", department=FINANCE),
        authority=AgentAuthority(
            scope=scope,
            capabilities=tuple(Capability(value=one) for one in capabilities),
        ),
        created_by="u_gone",
        disabled_at=NOW - timedelta(days=1) if disabled else None,
    )


# ------------------------------------------------------- the refusal M33.2.2.2 is about
def test_a_department_admin_cannot_grant_wider_than_their_own_scope() -> None:
    """**This is the hole the module was written for.** Until it existed, an admin holding
    the grant authority in one department could write a grant over `Scope.unrestricted()`,
    and nothing anywhere refused it: `SubjectGrant` checks a scope is conjunctive and
    satisfiable, `expand` copies an assignment's scope through, and revocation deletes rows
    without asking who added them.

    Entitlements are additive with no deny list, so the row stands until somebody notices it
    and deletes it, which means the refusal has to happen at the moment of writing or not at
    all. Asserted on the whole company-wide scope rather than on another department, because
    the escalation an admin actually writes for themselves is the unrestricted one.

    Delete this and the escalation is back, silently, and every review afterwards reads the
    row as an ordinary grant written by somebody with the authority to write rows."""
    admin = holding(
        REACH_AUTHORITY.value,
        EVERY_CLIENT_FIELD,
        scope=Scope.department(MAINTENANCE),
    )
    company_wide = proposal(NAME, scope=Scope.unrestricted(), subject_id="u_admin")

    assert not may_grant(company_wide, admin, NOW)
    with pytest.raises(AuthorityError, match="may not grant"):
        write_grant(company_wide, admin, NOW)


def test_a_department_admin_may_grant_inside_their_own_scope() -> None:
    """The positive half, without which a function that refused everything would pass the
    test above. The same admin, the same capability, a scope inside theirs, and the grant
    comes back unchanged rather than rebuilt.

    Delete this and the refusal can be tightened to a constant False and nothing complains."""
    admin = holding(
        REACH_AUTHORITY.value,
        EVERY_CLIENT_FIELD,
        scope=Scope.department(MAINTENANCE),
    )
    inside = proposal(NAME, scope=Scope.department(MAINTENANCE))

    assert may_grant(inside, admin, NOW)
    assert write_grant(inside, admin, NOW) is inside


def test_a_grant_narrower_than_the_admins_own_scope_is_still_theirs_to_write() -> None:
    """The half a clause-set comparison would get wrong, which is why `scope_narrows` is the
    test rather than `set(a.clauses) <= set(b.clauses)`.

    An admin scoped to a department may write a grant over one team inside it. Under a subset
    comparison the two clause sets are unequal in the wrong direction and the narrowing admin
    is refused, so they learn to write the wide grant instead, which is a refusal that makes
    the system less safe while looking like it made it safer.

    Delete this and somebody replaces the containment call with a set comparison, every test
    above still passes, and correct narrow grants start being refused."""
    admin = holding(
        REACH_AUTHORITY.value,
        EVERY_CLIENT_FIELD,
        scope=Scope.department(MAINTENANCE),
    )
    one_team = Scope.department(MAINTENANCE).intersect(
        Scope(clauses=(Clause(field="scope_path", op=Op.PREFIX, value=f"{MAINTENANCE}."),))
    )

    assert may_grant(proposal(NAME, scope=one_team), admin, NOW)


def test_the_authority_to_grant_and_the_capability_granted_are_two_separate_questions() -> None:
    """Two checks with two capabilities, and either one alone lets an escalation through.

    An admin holding the grant authority company-wide and the capability in one department
    must not write that capability outside it, and an admin holding the capability everywhere
    with the authority in one department must not either. Both directions are asserted,
    because a single check would pass whichever of them it happened to be written as.

    Delete this and the two collapse into one, and which escalation is reachable depends on
    which capability the surviving check names."""
    wide_authority = EntitlementSet(
        principal_id="u_admin",
        grants=(
            Grant(capability=REACH_AUTHORITY, scope=Scope.unrestricted()),
            Grant(
                capability=Capability(value=EVERY_CLIENT_FIELD),
                scope=Scope.department(MAINTENANCE),
            ),
        ),
    )
    wide_capability = EntitlementSet(
        principal_id="u_admin",
        grants=(
            Grant(capability=REACH_AUTHORITY, scope=Scope.department(MAINTENANCE)),
            Grant(capability=Capability(value=EVERY_CLIENT_FIELD), scope=Scope.unrestricted()),
        ),
    )
    elsewhere = proposal(NAME, scope=Scope.department(FINANCE))

    assert not may_grant(elsewhere, wide_authority, NOW)
    assert not may_grant(elsewhere, wide_capability, NOW)


def test_an_admin_may_grant_a_field_the_wildcard_they_hold_covers() -> None:
    """`EntitlementSet.scope_for` expands a trailing `.*` through `Capability.covers`, so the
    capability check is asked against the grant's own capability rather than against a list
    of the strings the admin literally holds. `brain.console.govern.may_certify` records the
    same reasoning about the other moment.

    Delete this and somebody replaces `scope_for` with a membership test over the grant
    values, every refusal test above still passes, and an admin holding `read:client.*`
    cannot grant a single field of it."""
    admin = holding(
        REACH_AUTHORITY.value,
        EVERY_CLIENT_FIELD,
        scope=Scope.department(MAINTENANCE),
    )

    assert may_grant(proposal(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE)), admin, NOW)


def test_an_admin_holding_one_field_may_not_grant_the_wildcard_over_it() -> None:
    """The other side of `covers`, and it is not symmetric. Holding `read:client.name` does
    not confer `read:client.*`, so granting the wildcard is granting something the admin does
    not hold, in any scope at all.

    Delete this and a widening from a field to its entity looks like an ordinary grant."""
    admin = holding(
        REACH_AUTHORITY.value,
        NAME,
        scope=Scope.department(MAINTENANCE),
    )

    assert not may_grant(
        proposal(EVERY_CLIENT_FIELD, scope=Scope.department(MAINTENANCE)), admin, NOW
    )


def test_a_grant_may_not_outlive_the_entitlement_that_wrote_it() -> None:
    """The axis a scope does not carry. A contractor with three weeks left writing a grant
    with no expiry leaves access standing after the authority behind it has gone, and every
    later reader sees a row written by somebody who was entitled to write it.

    Both shapes are refused: the unbounded grant, which is the one that gets written, and the
    bounded one that simply runs longer. And the bounded one inside the granter's own window
    is permitted, or the check would be an expiry ban rather than a containment.

    Delete this and `EntitlementSet.intersect`'s reason for taking the tighter of two bounds
    stops applying at the one place a bound is chosen by a person."""
    leaves = NOW + timedelta(days=21)
    admin = holding(
        REACH_AUTHORITY.value,
        EVERY_CLIENT_FIELD,
        scope=Scope.department(MAINTENANCE),
        not_after=leaves,
    )
    where = Scope.department(MAINTENANCE)

    assert not may_grant(proposal(NAME, scope=where), admin, NOW)
    assert not may_grant(
        proposal(NAME, scope=where, not_after=leaves + timedelta(days=1)), admin, NOW
    )
    assert may_grant(proposal(NAME, scope=where, not_after=leaves), admin, NOW)


def test_an_unbounded_granter_may_still_write_an_unbounded_grant() -> None:
    """The positive half of the expiry rule. `None` on the granter's side means no bound
    rather than the earliest possible instant, and a comparison written the other way round
    would refuse every grant a permanent employee ever wrote.

    Delete this and the expiry check can be inverted and only this test would notice."""
    admin = holding(
        REACH_AUTHORITY.value,
        EVERY_CLIENT_FIELD,
        scope=Scope.department(MAINTENANCE),
    )

    assert may_grant(proposal(NAME, scope=Scope.department(MAINTENANCE)), admin, NOW)


def test_an_expired_admin_grants_nothing() -> None:
    """`EntitlementSet.scope_for` refuses an expired principal whatever the grant table says,
    and this asserts that the refusal reaches through `within_reach` rather than being
    something the caller has to remember to ask first.

    Delete this and a lapsed contractor keeps writing grants for as long as their rows sit in
    the table, which is until somebody deletes them."""
    admin = holding(
        REACH_AUTHORITY.value,
        EVERY_CLIENT_FIELD,
        scope=Scope.department(MAINTENANCE),
        not_after=NOW - timedelta(minutes=1),
    )

    assert not may_grant(proposal(NAME, scope=Scope.department(MAINTENANCE)), admin, NOW)


def test_a_permitted_self_grant_confers_nothing_the_admin_did_not_hold() -> None:
    """**Why self-granting is not refused here.** M33.1.2.5 asks for a self-grant path that
    is loud rather than forbidden, so a refusal would delete a leaf somebody specified.
    Containment makes it unnecessary, and this asserts the property rather than the argument.

    The reach afterwards is computed by asking `scope_for` on the set with the new grant in
    it, and it is checked to narrow the scope the admin already had rather than to equal it,
    because `scope_for` intersects every covering grant and a narrower self-grant makes the
    result narrower still. What must never happen is the other direction.

    Delete this and the module's claim that a self-grant is harmless is a sentence in a
    docstring with nothing behind it."""
    where = Scope.department(MAINTENANCE)
    admin = holding(REACH_AUTHORITY.value, EVERY_CLIENT_FIELD, scope=where)
    to_themselves = proposal(NAME, scope=where, subject_id="u_admin", granted_by="u_admin")

    assert may_grant(to_themselves, admin, NOW)

    before = admin.scope_for(Capability(value=NAME), NOW)
    after = EntitlementSet(
        principal_id=admin.principal_id,
        grants=(*admin.grants, to_themselves.as_grant()),
        not_after=admin.not_after,
    ).scope_for(Capability(value=NAME), NOW)

    assert before is not None
    assert after is not None
    assert scope_narrows(after, before)


def test_the_row_form_and_the_predicate_form_of_the_rule_agree() -> None:
    """**The claim that this is not a second implementation, checked rather than asserted.**

    `brain.console.govern` narrows by `scope_for` then `Scope.matches`, which asks about one
    row; this narrows by `scope_for` then `scope_narrows`, which asks about a predicate. They
    are the same rule because a row is a conjunction of equalities, and the two are driven
    against each other here over every clause shape the grammar has: an equality, a
    membership, a prefix and the unrestricted scope, each asked about a row it admits and a
    row it does not.

    `may_certify` is the caller on the row side rather than the private narrowing, so this
    compares two public surfaces and survives either module renaming an internal.

    Delete this and the two can drift, and the one that drifts permissively is the one nobody
    notices, because a governance screen showing a row it should not looks like the screen
    working."""
    held = [
        Scope.unrestricted(),
        Scope.department(MAINTENANCE),
        Scope(clauses=(Clause(field="department", op=Op.IN, value=(MAINTENANCE, FINANCE)),)),
        Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="main"),)),
    ]
    rows = [{"department": MAINTENANCE}, {"department": FINANCE}, {"department": "sales"}]

    for scope in held:
        admin = holding(REACH_AUTHORITY.value, NAME, scope=scope)
        for row in rows:
            as_scope = Scope(
                clauses=tuple(
                    Clause(field=field, op=Op.EQ, value=value) for field, value in row.items()
                )
            )
            placed = Placed(
                record=proposal(NAME, scope=as_scope),
                where=row,
            )
            certifiable = may_certify(placed, admin, NOW)
            writable = may_grant(placed.record, admin, NOW)

            assert certifiable == writable, (scope, row)


def test_a_pack_expansion_is_refused_capability_by_capability() -> None:
    """Where the refusal earns its keep. `brain.identity.packs.expand` turns one assignment
    into one grant per capability in the pack, every one carrying the assignment's scope
    unchanged, and nobody reads twelve expanded rows to notice that the admin holds two of
    the three capabilities in the bundle.

    The rows are produced by `expand` rather than written out here, because the claim is
    about what that function produces and a hand-built list would be testing the list.

    Delete this and a pack assignment becomes the way round the refusal: one form, one scope,
    and whichever capabilities happened to be bundled with the ones the admin holds."""
    admin = holding(REACH_AUTHORITY.value, NAME, scope=Scope.department(MAINTENANCE))
    pack = CapabilityPack(
        slug="engineer",
        label="Maintenance engineer",
        capabilities=(Capability(value=NAME), Capability(value=CONTRACT_VALUE)),
    )
    assignment = PackAssignment(
        subject=principal_subject("u_1"),
        pack_slug="engineer",
        scope=Scope.department(MAINTENANCE),
        granted_by="u_admin",
        reason="written for a test",
        granted_at=NOW,
    )

    expanded = expand(pack, assignment)
    permitted = grantable(expanded, admin, NOW)

    assert len(expanded) == 2
    assert tuple(one.capability.value for one in permitted) == (NAME,)


def test_a_listing_of_permitted_grants_carries_no_count_of_the_rest() -> None:
    """One value comes back and there is no second one describing what was dropped, which is
    `brain.console.screens.navigation`'s rule and `pending_for`'s. A count of the refused
    proposals would be a count of the capabilities an admin does not hold, published on the
    screen where they are trying to write one.

    Order is asserted to follow the input, because re-sorting discards an order the caller
    usually meant something by.

    Delete this and a helpful summary line appears saying two of five, which is three facts
    about the boundary of somebody's own authority stated as a number."""
    admin = holding(REACH_AUTHORITY.value, NAME, scope=Scope.department(MAINTENANCE))
    proposals = [
        proposal(NAME, scope=Scope.department(MAINTENANCE), subject_id="u_2"),
        proposal(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE)),
        proposal(NAME, scope=Scope.department(MAINTENANCE), subject_id="u_1"),
    ]

    permitted = grantable(proposals, admin, NOW)

    assert permitted == (proposals[0], proposals[2])


def test_a_submitted_grant_is_checked_again_rather_than_trusted_from_the_listing() -> None:
    """A form is submitted by whatever was posted rather than by what was offered, which is
    `brain.console.govern.certify`'s argument about the same pair. `grantable` decides what a
    screen shows and `write_grant` decides what a submission may do.

    Delete this and the refusal lives only in the listing, and the listing is the half an
    attacker never uses."""
    admin = holding(REACH_AUTHORITY.value, NAME, scope=Scope.department(MAINTENANCE))
    never_offered = proposal(CONTRACT_VALUE, scope=Scope.unrestricted())

    assert grantable([never_offered], admin, NOW) == ()
    with pytest.raises(AuthorityError):
        write_grant(never_offered, admin, NOW)


# ---------------------------------------------------------------- deputies (M33.2.2.5)
def test_the_deputy_maximum_is_the_number_the_leaf_writes_down() -> None:
    """**The constant checked against something outside itself.** `DEPUTY_MAX` is thirty days
    and a test importing it and asserting it equals thirty compares the constant with itself:
    change it to sixty and both sides move together.

    M33.2.2.5 is the only statement of the figure outside the module, `leaf_sentences` is the
    reader for it, and the number is taken out of the sentence's own words. The sentence is
    asserted to contain exactly one such word first, so a rewording that dropped the figure
    fails here rather than skipping the comparison.

    Delete this and the maximum can be raised in one edit with the whole suite green, which
    is the failure `CLAUDE.md` records three separate authors making in one afternoon."""
    sentence = LEAF_SENTENCES["M33.2.2.5"]
    written = [
        NUMBER_WORDS[word] for word in re.findall(r"[a-z]+", sentence) if word in NUMBER_WORDS
    ]

    assert written == [30], sentence
    assert timedelta(days=written[0]) == DEPUTY_MAX
    assert deputy_runs_at_most() == DEPUTY_MAX


def test_a_department_admin_may_not_deputise_a_company_wide_role() -> None:
    """A role grant with no scope is a company-wide role, which `SCOPE_REQUIRED` decides, and
    reading `None` as the unrestricted scope makes it fail closed without a special case: only
    an unrestricted holding contains the unrestricted scope.

    The refusal matters because a deputy inherits the standing grant's scope verbatim, so a
    department admin who could appoint a deputy Super Admin would have created somebody with
    company-wide authority for thirty days and would not themselves appear on the resulting
    grant at all.

    Delete this and `None` reads as no restriction to check rather than as no restriction."""
    admin = holding(REACH_AUTHORITY.value, scope=Scope.department(MAINTENANCE))
    company_wide = RoleGrant(
        principal_id="u_owner",
        role=Role.SUPER_ADMIN,
        granted_by="u_founder",
        reason="owns the platform",
        granted_at=NOW - timedelta(days=100),
    )

    assert not may_appoint_deputy(company_wide, admin, NOW)
    with pytest.raises(AuthorityError, match="may not appoint a deputy"):
        appoint(
            company_wide,
            admin,
            "u_stand_in",
            granted_by="u_admin",
            reason="annual leave",
            now=NOW,
        )


def test_a_department_admin_may_appoint_a_deputy_inside_their_own_scope() -> None:
    """The positive half, and it asserts the appointment came back through the module that
    owns the rules rather than being rebuilt here: the deputy carries the standing grant's
    scope, names who it covers, and expires inside the maximum.

    Delete this and the scope check can be tightened to a constant False and every refusal
    test above still passes."""
    where = Scope.department(MAINTENANCE)
    admin = holding(REACH_AUTHORITY.value, scope=where)
    standing = RoleGrant(
        principal_id="u_head",
        role=Role.DEPARTMENT_ADMIN,
        scope=where,
        granted_by="u_owner",
        reason="runs maintenance",
        granted_at=NOW - timedelta(days=100),
    )

    assert may_appoint_deputy(standing, admin, NOW)
    deputy = appoint(
        standing,
        admin,
        "u_stand_in",
        granted_by="u_admin",
        reason="annual leave",
        now=NOW,
    )

    assert deputy.deputy_of == "u_head"
    assert deputy.scope == where
    assert deputy.not_after is not None
    assert deputy.not_after - deputy.granted_at <= DEPUTY_MAX


def test_the_length_of_an_appointment_is_still_decided_where_it_always_was() -> None:
    """The refusal for a thirty-one day appointment comes from
    `brain.identity.roles.appoint_deputy` and is deliberately not repeated here, so this
    asserts it still arrives through this path as that module's own error type.

    Delete this and somebody adds a length check to the console module, the two copies
    disagree the day one of them is edited, and the console's is the one an administrator
    reads."""
    where = Scope.department(MAINTENANCE)
    admin = holding(REACH_AUTHORITY.value, scope=where)
    standing = RoleGrant(
        principal_id="u_head",
        role=Role.DEPARTMENT_ADMIN,
        scope=where,
        granted_by="u_owner",
        reason="runs maintenance",
        granted_at=NOW - timedelta(days=100),
    )

    with pytest.raises(IdentityError, match="1 to 30 days"):
        appoint(
            standing,
            admin,
            "u_stand_in",
            granted_by="u_admin",
            reason="annual leave",
            now=NOW,
            days=DEPUTY_MAX.days + 1,
        )


# -------------------------------------------------------------------- rungs (M33.2.2.4)
def _entry(rung: AutonomyTier, *, scope: Scope, target: str = "invoice") -> LeashEntry:
    return LeashEntry(agent_id="a_chaser", target=target, scope=scope, rung=rung)


def _evidence() -> PromotionEvidence:
    return PromotionEvidence(
        clean_runs=50,
        agreement_rate=1.0,
        approver_id="u_admin",
        second_approver_id="u_other",
    )


def test_a_rung_may_not_rise_above_the_ceiling_its_side_effect_allows() -> None:
    """**The half of M33.2.2.4 that had no implementation anywhere.**
    `brain.console.reach_view.may_raise` weighs evidence and approvers and never compares the
    proposed rung against a ceiling, and `brain.tools.registry.rung_ceiling` is applied in
    `brain.tools.run_skill` and nowhere on the request path: `brain.gate.invoke` tightens the
    leash's rung by the risk score alone.

    So a write operation pinned to AUTONOMOUS by a console change runs autonomously on any
    call whose risk signals are quiet. The evidence here is deliberately perfect and has two
    approvers, so the only thing that can refuse it is the ceiling.

    Delete this and a rung can be set above the supervision its side effect requires, with
    the evidence rules all satisfied and nothing downstream putting it back."""
    admin = holding(RUNG_AUTHORITY.value, scope=Scope.department(MAINTENANCE))
    entry = _entry(AutonomyTier.AUTONOMOUS, scope=Scope.department(MAINTENANCE))

    assert not within_ceiling(AutonomyTier.AUTONOMOUS, Operation.WRITE)
    assert not may_move_rung(
        entry,
        was=AutonomyTier.ASSISTED,
        operation=Operation.WRITE,
        admin=admin,
        evidence=_evidence(),
        now=NOW,
    )


def test_a_rung_may_rise_to_the_ceiling_when_the_evidence_is_there() -> None:
    """The positive half, and it is the same call with the rung one step lower. Without it a
    function refusing every rise would pass the test above, and the leaf explicitly permits a
    rise: it forbids only one past the ceiling.

    Delete this and the ceiling check can be widened into a ban on rising at all."""
    admin = holding(RUNG_AUTHORITY.value, scope=Scope.department(MAINTENANCE))
    entry = _entry(AutonomyTier.ASSISTED, scope=Scope.department(MAINTENANCE))

    assert within_ceiling(AutonomyTier.ASSISTED, Operation.WRITE)
    assert may_move_rung(
        entry,
        was=AutonomyTier.SHADOW,
        operation=Operation.WRITE,
        admin=admin,
        evidence=_evidence(),
        now=NOW,
    )


def test_a_rung_rise_still_needs_the_evidence_reach_view_asks_for() -> None:
    """The thresholds are `brain.console.reach_view`'s and this asserts they are still being
    asked rather than reimplemented: the same rise, inside the ceiling and inside the scope,
    with no evidence at all.

    Delete this and the ceiling check can quietly replace the evidence check, and a rise to
    ASSISTED needs nobody to have looked at anything."""
    admin = holding(RUNG_AUTHORITY.value, scope=Scope.department(MAINTENANCE))
    entry = _entry(AutonomyTier.ASSISTED, scope=Scope.department(MAINTENANCE))

    assert not may_move_rung(
        entry,
        was=AutonomyTier.SHADOW,
        operation=Operation.WRITE,
        admin=admin,
        evidence=None,
        now=NOW,
    )


def test_a_rung_may_always_be_lowered_inside_the_admins_own_scope() -> None:
    """The fail-safe direction, with no evidence and from above the ceiling. An incident is
    the worst moment to discover that turning something down needs paperwork.

    **The rule is `brain.console.reach_view.may_raise`'s and this asserts it survives the
    trip through here.** An earlier version of `may_move_rung` short-circuited a lowering
    itself, and a mutation showed that nothing in this file could tell that branch from the
    first line of `may_raise`: replacing it with `if False` and deleting it outright both
    survived. Two checks nothing can separate are one check written twice, so the branch went
    and the call stayed.

    Delete this and the ceiling refusal can grow to cover demotions, which is the one change
    here that would be discovered during an incident."""
    admin = holding(RUNG_AUTHORITY.value, scope=Scope.department(MAINTENANCE))
    entry = _entry(AutonomyTier.SHADOW, scope=Scope.department(MAINTENANCE))

    assert may_move_rung(
        entry,
        was=AutonomyTier.AUTONOMOUS,
        operation=Operation.WRITE,
        admin=admin,
        evidence=None,
        now=NOW,
    )


def test_a_rung_already_above_its_ceiling_may_fall_and_may_not_be_kept() -> None:
    """The ceiling is asked on every entry rather than only on a rise, and the two halves of
    what that means are asserted together.

    A fall from an over-ceiling rung is permitted, because only the top rung is ever above a
    ceiling and nothing can fall to the top rung, so an unconditional ceiling refuses no
    lowering anybody could write. An entry that *keeps* the rung where it is, on the other
    hand, is refused: re-saving AUTONOMOUS on a write is writing a setting that should never
    have been settable, and a rule that let it stand as long as it did not move would leave
    every over-ceiling rung in place forever with nothing ever objecting.

    Delete this and the ceiling can be narrowed to rises only, which passes every other rung
    test here and makes an over-ceiling rung permanent."""
    admin = holding(RUNG_AUTHORITY.value, scope=Scope.department(MAINTENANCE))
    where = Scope.department(MAINTENANCE)

    assert may_move_rung(
        _entry(AutonomyTier.ASSISTED, scope=where),
        was=AutonomyTier.AUTONOMOUS,
        operation=Operation.WRITE,
        admin=admin,
        evidence=None,
        now=NOW,
    )
    assert not may_move_rung(
        _entry(AutonomyTier.AUTONOMOUS, scope=where),
        was=AutonomyTier.AUTONOMOUS,
        operation=Operation.WRITE,
        admin=admin,
        evidence=_evidence(),
        now=NOW,
    )


def test_a_leash_entry_outside_the_admins_scope_is_refused_in_both_directions() -> None:
    """A leash entry carries a scope, so an admin writing one company-wide has reached every
    department from a screen scoped to theirs. Lowering is the fail-safe direction for the
    agent and is still somebody else's work being stopped; the company-wide stop already
    exists as `admin:halt` on its own screen, and it is a super administrator's.

    Both directions are asserted, because the scope check sits before the branch and a
    version that put it after would let every demotion through.

    Delete this and a maintenance admin can shadow-pin finance's agents."""
    admin = holding(RUNG_AUTHORITY.value, scope=Scope.department(MAINTENANCE))
    company_wide = _entry(AutonomyTier.SHADOW, scope=Scope.unrestricted())
    rise = _entry(AutonomyTier.ASSISTED, scope=Scope.department(FINANCE))

    assert not may_move_rung(
        company_wide,
        was=AutonomyTier.ASSISTED,
        operation=Operation.WRITE,
        admin=admin,
        evidence=None,
        now=NOW,
    )
    assert not may_move_rung(
        rise,
        was=AutonomyTier.SHADOW,
        operation=Operation.WRITE,
        admin=admin,
        evidence=_evidence(),
        now=NOW,
    )


def test_moving_a_rung_takes_the_approvals_capability_and_not_the_grant_one() -> None:
    """**Supervision is not reach.** `E_run(caller, agent) = E(caller) intersect
    agent_ceiling` has no rung in it, so moving one changes whether a person sees an action
    before it happens and never what a run may read. It therefore does not take the
    capability the other four acts here take.

    Asserted both ways, so a swap of the two constants fails rather than half-passing: an
    admin holding only the grant authority cannot move a rung, and one holding only the
    approvals capability can.

    Delete this and the two authorities merge, which reads as tidier and hands everybody who
    can move a rung the capability that writes grants."""
    where = Scope.department(MAINTENANCE)
    entry = _entry(AutonomyTier.SHADOW, scope=where)
    only_grants = holding(REACH_AUTHORITY.value, scope=where)
    only_approvals = holding(RUNG_AUTHORITY.value, scope=where)

    assert not may_move_rung(
        entry,
        was=AutonomyTier.ASSISTED,
        operation=Operation.WRITE,
        admin=only_grants,
        now=NOW,
    )
    assert may_move_rung(
        entry,
        was=AutonomyTier.ASSISTED,
        operation=Operation.WRITE,
        admin=only_approvals,
        now=NOW,
    )


def test_a_read_operation_may_run_at_the_top_rung_and_a_write_may_not() -> None:
    """The ceiling is the tool registry's own composition rather than a table written here,
    so it varies by side effect: a read has no effect and `default_rung` puts it at
    AUTONOMOUS, a write lands on ASSISTED.

    Asserted across all three console operations, so a mapping that pointed every one of them
    at the same effect would fail here rather than passing everything.

    Delete this and `within_ceiling` can be replaced by a constant and only the write case
    would notice."""
    permitted = {
        one: {rung for rung in AutonomyTier if within_ceiling(rung, one)} for one in Operation
    }

    assert permitted[Operation.READ] == set(AutonomyTier)
    assert permitted[Operation.WRITE] == {AutonomyTier.SHADOW, AutonomyTier.ASSISTED}
    assert permitted[Operation.DRAFT] == permitted[Operation.WRITE]


# -------------------------------------------------------------- publications (M33.2.2.1)
def test_an_approver_may_not_approve_a_ceiling_they_could_not_have_written() -> None:
    """`brain.builder.publish` decides how many approvers a publish needs and refuses the
    author as one of them, and it never asks whether an approver could have written the
    ceiling. An approver who confirms one they could not have written is the decision
    laundered through a process, which is the rule `brain.console.role_surfaces` applies to a
    suspended action and `brain.console.govern` to a certification.

    Both axes are asserted, because a ceiling can be out of reach for two different reasons:
    a capability the approver does not hold at all, and one they hold somewhere else.

    Delete this and a department admin approves a company-wide agent."""
    admin = holding(EVERY_CLIENT_FIELD, scope=Scope.department(MAINTENANCE))
    unheld = entitlement_ceiling(
        an_agent("read:invoice.amount", scope=Scope.department(MAINTENANCE))
    )
    elsewhere = entitlement_ceiling(an_agent(NAME, scope=Scope.department(FINANCE)))

    assert not may_approve_publication(unheld, admin, NOW)
    assert not may_approve_publication(elsewhere, admin, NOW)


def test_an_approver_may_approve_a_ceiling_inside_their_own_reach() -> None:
    """The positive half. The ceiling is built by `brain.agents.model.entitlement_ceiling`
    rather than assembled here, so the set being checked is the one `E_run` would actually
    intersect against.

    Delete this and the approval check can refuse everything with every refusal test above
    still green."""
    admin = holding(EVERY_CLIENT_FIELD, scope=Scope.department(MAINTENANCE))
    inside = entitlement_ceiling(an_agent(NAME, scope=Scope.department(MAINTENANCE)))

    assert may_approve_publication(inside, admin, NOW)
    assert ceiling_within_reach(EntitlementSet(principal_id="ceiling:empty"), admin, NOW)


def test_a_publication_queue_is_filtered_rather_than_shown_greyed_out() -> None:
    """The queue returns what this admin may decide and nothing describing the rest, which is
    `recertifiable`'s decision for the same reason: a disabled row is the thing disclosed
    with an explanation attached, and an approver reading one has learnt that an agent exists,
    what it reaches, and that it is not theirs.

    Delete this and the natural next feature is showing every pending publication with the
    out-of-scope ones dimmed."""
    admin = holding(EVERY_CLIENT_FIELD, scope=Scope.department(MAINTENANCE))
    mine = entitlement_ceiling(an_agent(NAME, scope=Scope.department(MAINTENANCE)))
    theirs = entitlement_ceiling(an_agent(NAME, scope=Scope.department(FINANCE)))

    assert approvable([theirs, mine], admin, NOW) == (mine,)


# ---------------------------------------------------------------- adoptions (M33.2.2.3)
def test_an_admin_may_not_adopt_an_agent_that_reaches_further_than_they_do() -> None:
    """An agent's ceiling does not narrow when its owner leaves, so adopting one puts that
    ceiling back into the world under a new name. `brain.identity.lifecycle.adopt` refuses an
    archived record and an inactive new steward and has no opinion about the admin doing the
    adopting, because it takes no entitlement.

    Delete this and the offboarding queue is a list of every departing person's agents,
    adoptable by whichever admin opens it first."""
    admin = holding(NAME, scope=Scope.department(MAINTENANCE))
    reaches_finance = an_agent(NAME, scope=Scope.department(FINANCE), disabled=True)

    assert not may_adopt(reaches_finance, admin, NOW)


def test_an_admin_may_adopt_an_agent_inside_their_own_reach() -> None:
    """The positive half, and the queue asserted alongside it: the adoption for the agent
    inside their scope comes back and the other does not, in the order the offboarding
    report produced them.

    Delete this and the filter can refuse the whole queue, which presents as an empty
    offboarding report rather than as a bug."""
    admin = holding(EVERY_CLIENT_FIELD, scope=Scope.department(MAINTENANCE))
    mine = an_agent(NAME, scope=Scope.department(MAINTENANCE), agent_id="a_mine", disabled=True)
    theirs = an_agent(NAME, scope=Scope.department(FINANCE), agent_id="a_theirs", disabled=True)
    queue = (
        Adoption(agent_id="a_mine", record=mine, former_owner_id="u_gone"),
        Adoption(agent_id="a_theirs", record=theirs, former_owner_id="u_gone"),
    )

    assert may_adopt(mine, admin, NOW)
    assert adoptable(queue, admin, NOW) == (queue[0],)


# ------------------------------------------------------------------------ the diagnostic
def test_the_pinned_capabilities_are_the_screens_own_requirements() -> None:
    """Both constants are written out in the module and checked against the registry here
    rather than derived from it: derived, the comparison would be a constant against itself
    and repointing either would move both. `brain.console.govern.SESSION_CONTROL` is pinned
    the same way against the same screen.

    The deployment check is asserted alongside, so the module's own constants are the ones
    being compared and not only the pair this test passes in.

    Delete this and a console module can invent a capability, and the administrator who
    reviews grants never meets it because nothing in the registry names it."""
    assert screen(REACH_AUTHORITY_SCREEN).read.requires == REACH_AUTHORITY
    assert screen(RUNG_AUTHORITY_SCREEN).read.requires == RUNG_AUTHORITY
    assert authority_gaps() == ()


def test_a_capability_pinned_to_a_screen_that_does_not_require_it_is_reported() -> None:
    """The diagnostic exercised with a broken pair rather than only against the healthy tree,
    which is `govern_gaps`' argument about its own parameters: a check that can only run
    against a correct configuration has nothing to report, so switching it off changes
    nothing observable.

    Both failure shapes are covered: a capability that disagrees with its screen, and a
    screen key the registry does not have.

    Delete this and the pinning check survives every mutation of itself."""
    wrong = authority_gaps(reach_authority=Capability(value="read:client.name"))
    missing = authority_gaps(rung_screen="no_such_screen")

    assert any("invented a capability" in one for one in wrong), wrong
    assert any("the registry does not have" in one for one in missing), missing


def test_supervision_and_reach_may_not_be_authorised_by_one_capability() -> None:
    """The third check, and the one that is about a change somebody would make on purpose.
    Merging the two constants reads as tidying up, and what it does is require the
    grant-writing capability to move a rung, which is a strictly larger authority handed to
    everybody who supervises an agent.

    Delete this and the two can be pointed at the same capability with the two tests above
    still passing, because each of them would still agree with its own screen."""
    merged = authority_gaps(rung_authority=REACH_AUTHORITY, rung_screen=REACH_AUTHORITY_SCREEN)

    assert any("supervision and access have become one authority" in one for one in merged), merged


def test_an_unrestricted_scope_is_contained_only_by_an_unrestricted_holding() -> None:
    """The base case of the containment, asserted directly on `within_reach` because every
    surface above depends on it and none of them exercises the unrestricted holding.

    Delete this and the direction of `scope_narrows` can be reversed, which makes a
    department admin's grant the container and the company-wide one the thing contained, and
    the escalation test above is the only thing that would notice."""
    capability = Capability(value=NAME)
    company = holding(NAME, scope=Scope.unrestricted())
    department = holding(NAME, scope=Scope.department(MAINTENANCE))

    assert within_reach(company, capability, Scope.unrestricted(), NOW)
    assert within_reach(company, capability, Scope.department(MAINTENANCE), NOW)
    assert not within_reach(department, capability, Scope.unrestricted(), NOW)
    assert within_reach(department, capability, Scope.department(MAINTENANCE), NOW)


# --- what a department knows (M33.2.1.4) ------------------------------------------------------


def an_item(item_id: str, *, area: str, owner: str = "u_author") -> KnowledgeItem:
    """One knowledge item visible to one department, through its own validators.

    Built the way `test_operate` builds one, because the thing under test calls that module's
    `coverage` and a fixture shaped differently would be testing a different function."""
    return KnowledgeItem(
        item_id=item_id,
        content="something written down",
        visibility=KnowledgeVisibility.of_department(area),
        owner_id=owner,
        state=KnowledgeState.PUBLISHED,
        verified_by="u_steward",
        verified_at=NOW - timedelta(days=1),
    )


def a_head(department: str) -> EntitlementSet:
    """A department head: the knowledge library's capability, scoped to their department."""
    where = Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))
    return EntitlementSet(
        principal_id="u_head",
        grants=(
            Grant(capability=COVERAGE_AUTHORITY, scope=where),
            Grant(capability=plane_capability(Plane.EXISTENCE), scope=where),
        ),
    )


def test_a_department_head_sees_the_areas_of_their_own_department_and_no_others() -> None:
    """M33.2.1.4. The counting and the staleness are `operate.coverage`'s and are called
    rather than reimplemented; what is decided here is that the areas come from the
    department and the head's authority is asked about the department first.

    The two departments hold items either side of the boundary, so the difference between
    the two answers is the head's own scope and nothing else.

    Delete this and a department coverage screen becomes the company one with a heading."""
    items = [an_item("k_1", area=MAINTENANCE), an_item("k_2", area=FINANCE)]
    areas_of = {MAINTENANCE: [MAINTENANCE], FINANCE: [FINANCE]}

    mine = department_coverage(
        MAINTENANCE, items, a_head(MAINTENANCE), headed=[MAINTENANCE], areas_of=areas_of, now=NOW
    )

    assert [one.area for one in mine] == [MAINTENANCE]


def test_a_department_this_head_does_not_head_and_one_that_does_not_exist_are_one_answer() -> None:
    """**A head who could tell a department they cannot reach from one that is not there has
    been handed the org chart one guess at a time.** Both are empty, and the emptiness carries
    nothing: no refusal naming the department, no count, no note that something was withheld.

    Three calls rather than two, because a function returning empty for everything satisfies
    the first two: the head's own department with the same items produces rows.

    Delete this and the coverage surface answers "does this department exist" for anybody who
    can type a string."""
    items = [an_item("k_1", area=MAINTENANCE), an_item("k_2", area=FINANCE)]
    areas_of = {MAINTENANCE: [MAINTENANCE], FINANCE: [FINANCE]}
    head = a_head(MAINTENANCE)

    assert (
        department_coverage(FINANCE, items, head, headed=[MAINTENANCE], areas_of=areas_of, now=NOW)
        == ()
    )
    assert (
        department_coverage("legal", items, head, headed=[MAINTENANCE], areas_of=areas_of, now=NOW)
        == ()
    )
    assert (
        department_coverage(
            MAINTENANCE, items, head, headed=[MAINTENANCE], areas_of=areas_of, now=NOW
        )
        != ()
    )


def test_the_areas_come_from_the_department_and_are_not_a_question_the_head_may_ask() -> None:
    """`operate.coverage` takes its areas as a parameter, which is right for the company
    overview: it asks about every area and the reader's reach decides which produce a row.
    Handing a department head that parameter makes the list a question, and the list is the
    disclosure.

    Asserted on the signature as well as on the behaviour, because the wrong version arrives
    as an `areas` parameter added so a head can narrow their own page, and behaviour alone
    would keep passing on the day it lands.

    Delete this and the surface grows the parameter, and an area with no row stops meaning
    one thing."""
    import inspect

    taken = inspect.signature(department_coverage).parameters

    assert "areas" not in taken
    assert "areas_of" in taken
    assert "department" in taken
    assert "headed" in taken, "the departments come from the role and not from the reach"

    # And the mapping really is what supplies them: a department absent from it has no areas
    # and therefore no rows, which is the same answer as one out of reach.
    items = [an_item("k_1", area=MAINTENANCE)]
    head = a_head(MAINTENANCE)

    assert (
        department_coverage(MAINTENANCE, items, head, headed=[MAINTENANCE], areas_of={}, now=NOW)
        == ()
    )
    assert (
        department_coverage(
            MAINTENANCE,
            items,
            head,
            headed=[MAINTENANCE],
            areas_of={MAINTENANCE: [MAINTENANCE]},
            now=NOW,
        )
        != ()
    )


def test_a_coverage_report_needs_a_department_and_there_is_no_value_meaning_all_of_them() -> None:
    """Over no department it is the company's report, which is a different screen with a
    different grant. `govern_estate` made the same decision about the memory viewer and
    `agent_automations` about a listing with no agent id.

    Whitespace as well as empty, because `" "` is what arrives from a form and passes a bare
    falsiness check.

    Delete this and one call with an empty string is the whole company's coverage read behind
    a department head's grant."""
    items = [an_item("k_1", area=MAINTENANCE)]
    head = a_head(MAINTENANCE)

    for nobody in ("", " "):
        with pytest.raises(ValueError, match="needs a department"):
            department_coverage(nobody, items, head, headed=[MAINTENANCE], areas_of={}, now=NOW)


def test_a_head_who_may_read_every_department_still_sees_only_the_one_they_head() -> None:
    """**The case that makes this a department surface rather than the company overview.**
    A person can hold `read:knowledge` company-wide, for an audit or because somebody was
    generous, and head one department. Narrowing this page by what they may read shows them
    every department, and the two answers differ for exactly the person most likely to be
    looking at it.

    Two mutations proved the first version of this surface did nothing: it checked the
    reader's scope, which `operate.coverage` had already checked, so both the authority check
    and the area derivation refused exactly what was going to be refused anyway.

    Delete this and the department page becomes the overview with a heading on it."""
    everywhere = EntitlementSet(
        principal_id="u_head",
        grants=(
            Grant(capability=COVERAGE_AUTHORITY, scope=Scope()),
            Grant(capability=plane_capability(Plane.EXISTENCE), scope=Scope()),
        ),
    )
    items = [an_item("k_1", area=MAINTENANCE), an_item("k_2", area=FINANCE)]
    areas_of = {MAINTENANCE: [MAINTENANCE], FINANCE: [FINANCE]}

    mine = department_coverage(
        MAINTENANCE, items, everywhere, headed=[MAINTENANCE], areas_of=areas_of, now=NOW
    )
    theirs = department_coverage(
        FINANCE, items, everywhere, headed=[MAINTENANCE], areas_of=areas_of, now=NOW
    )

    assert [one.area for one in mine] == [MAINTENANCE]
    assert theirs == (), "a grant that reaches finance is not a headship of finance"


def test_the_capability_is_the_knowledge_librarys_own_and_not_one_invented_here() -> None:
    """A coverage report is the knowledge library counted by area and nothing else, so a
    capability invented for it would be a second grant over the same rows, which is the
    finding `agent_output` makes about a second artifact grant: an administrator reviewing
    the library screen would never meet it.

    Delete this and the department page acquires a grant nobody reviews."""
    assert COVERAGE_AUTHORITY.value == "read:knowledge"
    assert COVERAGE_AUTHORITY != REACH_AUTHORITY

    # A head holding the grant-writing capability and not the library's sees nothing.
    wrong = EntitlementSet(
        principal_id="u_head",
        grants=(
            Grant(capability=REACH_AUTHORITY, scope=Scope.department(MAINTENANCE)),
            Grant(
                capability=plane_capability(Plane.EXISTENCE), scope=Scope.department(MAINTENANCE)
            ),
        ),
    )
    items = [an_item("k_1", area=MAINTENANCE)]

    assert (
        department_coverage(
            MAINTENANCE,
            items,
            wrong,
            headed=[MAINTENANCE],
            areas_of={MAINTENANCE: [MAINTENANCE]},
            now=NOW,
        )
        == ()
    )


# --- what a department spent, against pace (M33.2.1.3) ----------------------------------------

MONTH_START = datetime(2026, 3, 1, tzinfo=UTC)
MONTH_END = datetime(2026, 3, 31, tzinfo=UTC)
QUARTER_WAY = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)


def a_budget_for(
    department: str, *, ceiling: int = 1_000, spent: int = 250, level: BudgetLevel | None = None
) -> Allowance:
    """One budget row with spend against it, through the real constructors."""
    return Allowance(
        row=BudgetRow(
            level=level if level is not None else BudgetLevel.DEPARTMENT,
            subject=department,
            period=BudgetPeriod.MONTH,
            ceiling_minor=ceiling,
            version=1,
            author="u_admin",
            effective_from=MONTH_START,
            reason="a figure written for this test",
        ),
        spent_minor=spent,
    )


def a_budget_head(department: str) -> EntitlementSet:
    """A department head holding the budget screen's capability over their department."""
    return EntitlementSet(
        principal_id="u_head",
        grants=(Grant(capability=BUDGET_AUTHORITY, scope=Scope.department(department)),),
    )


def test_a_head_reads_their_own_departments_pace_and_gets_nothing_for_another() -> None:
    """M33.2.1.3. The same reach question every other surface in this module asks, and the
    same answer shape: `None` rather than a refusal, because a refusal naming the department
    answers "does this exist".

    Two departments either side of the boundary, so the difference between the two answers is
    the head's own scope and nothing else.

    Delete this and a department head reads another department's consumption on a page headed
    with their own department's name."""
    mine = department_pace(
        MAINTENANCE,
        a_budget_for(MAINTENANCE),
        a_budget_head(MAINTENANCE),
        started_at=MONTH_START,
        ends_at=MONTH_END,
        now=QUARTER_WAY,
    )
    theirs = department_pace(
        FINANCE,
        a_budget_for(FINANCE),
        a_budget_head(MAINTENANCE),
        started_at=MONTH_START,
        ends_at=MONTH_END,
        now=QUARTER_WAY,
    )

    assert mine is not None
    assert mine.spent_fraction == 0.25
    assert mine.elapsed_fraction == 0.25
    assert theirs is None


def test_a_budget_from_another_level_or_another_department_is_refused() -> None:
    """**A company allowance passed to a department page renders the company's consumption
    under a department heading, with every figure correct and every one about somebody else.**
    A pace is two fractions and neither of them says whose, so nothing downstream could
    notice.

    Both mistakes, because they are different: the wrong level and the right level with the
    wrong subject. A check on one passes a test that only makes the other.

    Delete this and the department page is one argument away from being the company's."""
    head = a_budget_head(MAINTENANCE)

    with pytest.raises(ValueError, match="another level"):
        department_pace(
            MAINTENANCE,
            a_budget_for("everybody", level=BudgetLevel.COMPANY),
            head,
            started_at=MONTH_START,
            ends_at=MONTH_END,
            now=QUARTER_WAY,
        )
    with pytest.raises(ValueError, match="another level"):
        department_pace(
            MAINTENANCE,
            a_budget_for(FINANCE),
            head,
            started_at=MONTH_START,
            ends_at=MONTH_END,
            now=QUARTER_WAY,
        )
    # And the case a subject check alone lets through, which a mutation found: a company
    # budget whose subject happens to be spelled the same as the department. The key is
    # (level, subject, period), so nothing stops a company row being keyed on that string,
    # and the figure it carries is the whole install's.
    with pytest.raises(ValueError, match="another level"):
        department_pace(
            MAINTENANCE,
            a_budget_for(MAINTENANCE, level=BudgetLevel.COMPANY),
            head,
            started_at=MONTH_START,
            ends_at=MONTH_END,
            now=QUARTER_WAY,
        )


def test_a_department_pace_needs_a_department_and_there_is_no_value_meaning_all_of_them() -> None:
    """Over no department it is the company's figure, which is a different screen with a
    different grant. The same decision `department_coverage` makes above.

    Whitespace as well as empty, because `" "` is what arrives from a form.

    Delete this and one call with an empty string is the company's consumption behind a
    department head's grant."""
    # A real allowance, because `BudgetRow` refuses an empty subject in its own constructor
    # and the blank department has to be the thing that fails here.
    for nobody in ("", " "):
        with pytest.raises(ValueError, match="needs a department"):
            department_pace(
                nobody,
                a_budget_for(MAINTENANCE),
                a_budget_head(MAINTENANCE),
                started_at=MONTH_START,
                ends_at=MONTH_END,
                now=QUARTER_WAY,
            )


def test_the_arithmetic_is_spend_views_own_and_not_a_second_copy() -> None:
    """`brain.console.spend_view.pace` already refuses a per-run budget, a period with no
    length and an instant outside it. A second copy here would be a second set of edge cases
    to keep in step, and the one that gets fixed is the one somebody is looking at.

    Asserted on the source as well as on the answer, because a reimplementation that agrees
    today passes an equality check and is exactly the thing being refused.

    Delete this and the three refusals get rewritten here, slightly differently."""
    import inspect

    body = inspect.getsource(department_pace)
    allowance = a_budget_for(MAINTENANCE)

    assert "return pace(" in body
    assert department_pace(
        MAINTENANCE,
        allowance,
        a_budget_head(MAINTENANCE),
        started_at=MONTH_START,
        ends_at=MONTH_END,
        now=QUARTER_WAY,
    ) == pace(allowance, started_at=MONTH_START, ends_at=MONTH_END, now=QUARTER_WAY)


def test_the_capability_is_the_budget_screens_own_and_not_one_invented_here() -> None:
    """A capability invented for this page would be a second grant over the same figures, and
    an administrator reviewing the console's screens would never meet it.

    Anchored to the literal as well as to the screen, so the pair is not compared against
    itself.

    Delete this and the department budget page is read behind a grant nobody reviews."""
    assert BUDGET_AUTHORITY.value == "read:budget"
    assert screen("budget").read.requires == BUDGET_AUTHORITY


# ============================================ what a department did, as its head reads it
#: When the roster behind the head's grants was read: seven hours before `NOW`, so the next
#: read is due later today and the reach has not lapsed.
READ_AT = NOW - timedelta(hours=7)

#: The department's people and one person in another department, so every narrowing has
#: somebody it has to leave out.
ACTIVITY_ROSTER = (
    StaffRecord(work_address="priya@example.com", display_name="Priya", department=MAINTENANCE),
    StaffRecord(work_address="wei@example.com", display_name="Wei", department=MAINTENANCE),
    StaffRecord(work_address="sam@example.com", display_name="Sam", department=FINANCE),
)

ACTIVITY_KNOWN = {
    "priya@example.com": "u_priya",
    "wei@example.com": "u_wei",
    "sam@example.com": "u_sam",
}


def a_head_of(department: str = MAINTENANCE) -> EntitlementSet:
    """The reach a head actually holds, produced by the sync rather than written here.

    Built through `brain.identity.staff_sync.audit_reach_for_head` and `SubjectGrant.as_grant`
    on purpose: a fixture that wrote the grants by hand would be this file agreeing with
    itself about what a head holds, which is how the empty page went unnoticed in the first
    place.
    """
    produced = audit_reach_for_head(
        Roster(
            source="google_workspace",
            people=ACTIVITY_ROSTER,
            complete=True,
            asserts=DEFAULT_TRUST["google_workspace"],
        ),
        department=department,
        head_id="u_head",
        known=ACTIVITY_KNOWN,
        read_at=READ_AT,
    )
    return EntitlementSet(
        principal_id="u_head", grants=tuple(one.as_grant() for one in produced.to_insert)
    )


def an_activity_ledger(*actors: str) -> tuple[AuditEntry, ...]:
    """One grant entry per actor named, each about somebody who is not the reader."""
    chain = AuditChain()
    return tuple(
        chain.append(
            at=NOW - timedelta(hours=index + 1),
            actor_id=actor,
            action=AuditAction.GRANT,
            subject=f"principal:u_subject{index}",
            ent_hash="a" * 32,
            trace_id="t1",
            details={"capability": NAME},
        )
        for index, actor in enumerate(actors)
    )


def a_head_view(*actors: str) -> AuditView:
    return AuditView(an_activity_ledger(*actors), reader=a_head_of(), now=NOW)


def test_a_head_reads_their_own_peoples_activity_and_nobody_elses() -> None:
    """**The leaf, end to end.** The reader's grants are the ones the sync writes, the entries
    are real and chained, and the visibility decision is `brain.audit.view.AuditView`'s own.
    What this module adds is the narrowing, and the assertion is that the two together produce
    this department's people and only them.

    Run through the real view rather than asserted against the filter, because the failure
    item 48 records is precisely a filter that looks right over a grant that admits nothing:
    every fixture in the repository used a company-wide grant, so every test passed while the
    page was empty for every reader it exists for.

    Delete this and the surface can go back to being empty for exactly its own readers, and
    nothing in the suite would say so."""
    page = department_activity(
        a_head_view("u_priya", "u_sam", "u_wei"),
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya", "u_wei"],
    )

    assert [row.actor_id for row in page.rows] == ["u_wei", "u_priya"]


def test_a_department_this_person_does_not_head_reads_as_one_with_nothing_in_it() -> None:
    """Empty rather than a refusal, matching `department_coverage` and every other surface in
    this module: somebody who could tell a department they do not head from one that is not
    there has been handed the org chart one guess at a time.

    Asserted as an identity between the three answers rather than as three empty pages, which
    is the strong form: a refusal that differed by a message, a field or a cursor would be the
    same disclosure arriving through the shape of the reply.

    Delete this and the obvious improvement, raising with the department's name in it, tells
    an outsider which departments exist."""
    view = a_head_view("u_priya", "u_wei")

    not_headed = department_activity(view, FINANCE, headed=[MAINTENANCE], members=["u_priya"])
    invented = department_activity(view, "nowhere", headed=[MAINTENANCE], members=["u_priya"])
    heads_nothing = department_activity(view, MAINTENANCE, headed=[], members=["u_priya"])

    assert not_headed.model_dump_json() == invented.model_dump_json()
    assert not_headed.model_dump_json() == heads_nothing.model_dump_json()
    assert not_headed.rows == ()


def test_an_empty_member_list_is_refused_because_a_filter_reads_it_as_everybody() -> None:
    """`AuditFilter` reads an empty actors set as every actor, on the same reading as an empty
    scope. Correct for a filter, catastrophic as a fallback: a failed membership query would
    arrive here as an empty sequence and widen the page to everything the reader's grant
    admits, under a department's name, with every row on it one they were entitled to see.

    The filter's own reading is asserted here rather than assumed, because it is the entire
    reason this is a refusal.

    Delete this and the empty case becomes a default, which is
    `brain.core.department.compose` returning the identity for an empty list of scopes."""
    view = AuditView(an_activity_ledger("u_priya", "u_wei"), reader=a_head_of(), now=NOW)
    assert len(view.page(AuditFilter(actors=frozenset())).rows) == 2

    with pytest.raises(ValueError, match="no members"):
        department_activity(a_head_view("u_priya"), MAINTENANCE, headed=[MAINTENANCE], members=[])


def test_a_member_the_grant_does_not_yet_cover_is_absent_and_never_counted() -> None:
    """**The staleness window, in the direction that fails closed.** Somebody joined this
    morning, so the directory names them and the grant written at the last sync does not. Their
    entries are absent, and the page is byte-identical to the page a ledger without them
    produces: no placeholder, no shorter-page signal, and nothing anywhere that could be
    subtracted into a count of what was withheld.

    Delete this and the natural repair for a thin page, reporting the members whose entries
    could not be read, emits exactly the hidden count this system may not emit."""
    joiner_present = department_activity(
        a_head_view("u_priya", "u_newcomer", "u_wei"),
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya", "u_wei", "u_newcomer"],
    )
    joiner_absent = department_activity(
        a_head_view("u_priya", "u_wei"),
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya", "u_wei", "u_newcomer"],
    )

    assert [row.actor_id for row in joiner_present.rows] == ["u_wei", "u_priya"]
    assert joiner_present.next_cursor is None
    assert len(joiner_present.rows) == len(joiner_absent.rows)


def test_somebody_the_directory_has_moved_out_is_dropped_before_the_grant_catches_up() -> None:
    """The staleness window in the direction that fails open, closed on the way in. The grant
    still names them because the sync has not run since the transfer; the member list is
    today's answer, and the filter narrows to it.

    The screen therefore closes the open half of the window immediately and the sync closes it
    everywhere else at the next run. See
    `A_FILTER_AND_A_GRANT_THAT_DISAGREE_CAN_ONLY_NARROW`.

    Delete this and a transfer is invisible on the head's own page until the next sync, which
    is the cost item 48 named and the one thing that could be done about it here."""
    page = department_activity(
        a_head_view("u_priya", "u_wei"),
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya"],
    )

    assert [row.actor_id for row in page.rows] == ["u_priya"]


def test_an_actor_filter_naming_an_outsider_cannot_widen_the_page() -> None:
    """A caller may narrow by actor and may not replace the member list with one. The two are
    intersected, so naming somebody outside the department adds nobody, and the head cannot
    turn their own page into a search over the ledger by passing a name.

    **The second half is the case that actually tests this function.** Naming somebody the
    head's grant already refuses proves nothing, because the view refuses them whatever this
    module does with the filter: a mutation replacing the intersection with the caller's own
    set survived exactly that assertion. The case that bites is somebody the grant still
    covers and the directory has moved out, which is the staleness window, and there the
    intersection is the only thing standing between the caller and a row.

    Delete this and `criteria` becomes a way round the department the page is named after."""
    outsider = department_activity(
        a_head_view("u_priya", "u_sam", "u_wei"),
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya", "u_wei"],
        criteria=AuditFilter(actors=frozenset({"u_priya", "u_sam"})),
    )
    moved_out = department_activity(
        a_head_view("u_priya", "u_wei"),
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya"],
        criteria=AuditFilter(actors=frozenset({"u_priya", "u_wei"})),
    )

    assert [row.actor_id for row in outsider.rows] == ["u_priya"]
    assert [row.actor_id for row in moved_out.rows] == ["u_priya"]


def test_asking_about_somebody_outside_the_department_reads_as_no_activity() -> None:
    """An intersection of nobody is returned as an empty page and never as the empty filter,
    which would mean every actor. It is not a refusal either: asking about a person who is not
    in this department has to read the same as a department where nothing happened, or the
    refusal answers whether that person exists.

    Delete this and either the page widens to everybody or the shape of the reply tells the
    reader which names are real."""
    page = department_activity(
        a_head_view("u_priya", "u_sam"),
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya", "u_wei"],
        criteria=AuditFilter(actors=frozenset({"u_sam"})),
    )
    quiet = department_activity(
        a_head_view(), MAINTENANCE, headed=[MAINTENANCE], members=["u_priya"]
    )

    assert page.model_dump_json() == quiet.model_dump_json()


def test_criteria_still_narrow_by_action_and_by_date() -> None:
    """The positive half of the two refusals above. A filter that is only ever refused or
    emptied is satisfied by a function that ignores `criteria` entirely, and the date range is
    what a head actually uses the page with.

    Delete this and the intersection logic can drop every other field of the filter while both
    refusal tests stay green."""
    view = a_head_view("u_priya", "u_wei")

    by_action = department_activity(
        view,
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya", "u_wei"],
        criteria=AuditFilter(actions=frozenset({AuditAction.REVOKE})),
    )
    recent = department_activity(
        view,
        MAINTENANCE,
        headed=[MAINTENANCE],
        members=["u_priya", "u_wei"],
        criteria=AuditFilter(since=NOW - timedelta(minutes=90)),
    )

    assert by_action.rows == ()
    assert [row.actor_id for row in recent.rows] == ["u_priya"]


def test_the_basis_says_when_the_membership_was_read_and_whether_a_read_is_overdue() -> None:
    """The visible half of the staleness cost. A window nobody is shown is a window nobody
    has, and the failure worth showing is not the ordinary one: it is a sync that has quietly
    stopped, leaving the page confidently rendering a department as it was.

    The arithmetic is the sync's own, called and not recomputed, so the page and the scheduler
    cannot disagree about when a read is due.

    Delete this and a stale page looks exactly like a current one."""
    fresh = activity_basis(read_at=READ_AT, now=NOW)
    stopped = activity_basis(read_at=NOW - 3 * SYNC_INTERVAL, now=NOW)

    assert fresh.read_at == READ_AT
    assert fresh.due_at == READ_AT + SYNC_INTERVAL
    assert fresh.lapses_at == READ_AT + GRANT_LIFETIME
    assert not fresh.overdue
    assert stopped.overdue
    assert stopped.lapses_at < NOW


def test_the_basis_carries_times_and_never_a_number_of_people() -> None:
    """How stale a reading is, when the next one is due and whether it is late are facts about
    this reader's own grant. How many people it covers, or how many it has stopped covering,
    is a count of what somebody may not see arrived at from the other side.

    Read off the fields rather than asserted about one of them, so a count cannot be added
    later under a name this test did not think of.

    Delete this and the obvious next addition, "covering 14 of 15 people", is the hidden
    count."""
    carried = activity_basis(read_at=READ_AT, now=NOW)

    for field, value in vars(carried).items():
        assert isinstance(value, datetime | bool | type(None)), field


def test_the_page_capability_is_the_activity_screens_own_and_the_one_the_sync_writes() -> None:
    """Three names for one capability, and this is where they are checked against each other:
    the screen registry's requirement, the literal, and the capability
    `brain.identity.staff_sync` writes onto a head's grant. Derived from one another the
    comparison would be a constant against itself; built from different sources, a divergence
    is a red test rather than a menu entry nobody can reach.

    Delete this and the sync can write a page capability the registry does not ask for, and
    the head holds a grant that opens nothing."""
    assert ACTIVITY_AUTHORITY.value == "read:audit"
    assert screen("audit").read.requires == ACTIVITY_AUTHORITY
    assert AUDIT_PAGE_CAPABILITY == ACTIVITY_AUTHORITY
    assert not ACTIVITY_AUTHORITY.covers(CAPABILITY_BY_KIND["principal"])
