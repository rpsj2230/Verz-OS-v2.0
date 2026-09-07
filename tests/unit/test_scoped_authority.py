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

Real `EntitlementSet`s, real `SubjectGrant`s through their own validators, a real
`RoleGrant`, real `AgentRecord`s and a real `Adoption` throughout. The pack test runs
`brain.identity.packs.expand` rather than building the expanded rows by hand, because the
claim being made is about what that function produces.

Task ids: M33.2.2.1, M33.2.2.2, M33.2.2.3, M33.2.2.4, M33.2.2.5
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
from brain.console.govern import Placed, may_certify
from brain.console.reach_view import Operation, PromotionEvidence
from brain.console.scoped_authority import (
    REACH_AUTHORITY,
    REACH_AUTHORITY_SCREEN,
    RUNG_AUTHORITY,
    RUNG_AUTHORITY_SCREEN,
    AuthorityError,
    adoptable,
    appoint,
    approvable,
    authority_gaps,
    ceiling_within_reach,
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
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.core.scope_sql import scope_narrows
from brain.gate.injection import AutonomyTier
from brain.gate.leash import LeashEntry
from brain.identity.lifecycle import Adoption
from brain.identity.packs import CapabilityPack, PackAssignment, SubjectGrant, expand
from brain.identity.roles import DEPUTY_MAX, IdentityError, Role, RoleGrant
from brain.identity.teams import principal_subject
from brain.knowledge.visibility import Visibility
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
