"""A department head's five governing acts, every one of them bounded by their own scope.

The five leaves under M33.2.2 read as five features and they are one rule asked five times.
A grant hands somebody a capability in a scope. A deputy appointment hands somebody a role in
a scope. A publication hands an agent a ceiling. An adoption puts a stopped agent's ceiling
back into the world under a new steward. Each of those is a reach entering the system, and
the only question worth asking about any of them is whether the person doing it already held
that reach. **A rung is the exception and it is here to be the exception**: supervision is not
reach, `E_run` does not move when a rung does, so it takes a different authority and a
different ceiling.

**M33.2.2.2 was a live privilege-escalation path and this module is written for it.** Nothing
in this repository refused a department admin writing a grant wider than their own scope.
`SubjectGrant` checks that a scope is conjunctive and satisfiable and never that it is
theirs to write; `expand` copies an assignment's scope through unchanged; `revoke_capability`
removes rows and has no opinion about who added them. So an admin holding `approve:grant` in
one department could write themselves `read:client.*` over `Scope.unrestricted()`, and because
entitlements are additive with no deny list anywhere, **nothing existed that could take it
back except deleting the row somebody would first have to notice**. See
`A_GRANT_WIDER_THAN_ITS_GRANTER_IS_THE_ONE_ESCALATION_AN_ADDITIVE_MODEL_CANNOT_UNDO`.

**The rule is `brain.console.govern._in_reach` asked about a predicate instead of about a
row, and it is deliberately not a second implementation of it.** That function is
`EntitlementSet.scope_for` followed by `Scope.matches`, which answers "does this reader's
grant admit this one row". Granting asks "does this granter's grant admit every row the scope
they are writing admits", which is containment of a predicate, and the repository already has
exactly one implementation of that: `brain.core.scope_sql.scope_narrows`, built on
`clause_entails`, sound and incomplete and failing towards refusal. `within_reach` is
`scope_for` followed by `scope_narrows`, which is the same two public calls with the same
first one. **The two forms are one rule and `tests/unit/test_scoped_authority.py` proves it
rather than asserting it**: a row is a scope of equality clauses, and `Scope.matches(row)`
and `scope_narrows(that scope, held)` agree on every clause shape in the grammar. See
`THE_ROW_FORM_AND_THE_PREDICATE_FORM_ARE_ONE_RULE`.

**Rejected: writing the containment test here as a clause-set comparison.**
`brain.builder.publish.widened_capabilities` does exactly that, `set(previous.clauses) <=
set(grant.scope.clauses)`, and it is right for what that function needs, which is to notice a
ceiling growing between two of its own drafts. It is the wrong test for a grant: it calls a
scope of `scope_path` prefix `web.` wider than the department scope it sits under, because the
clauses are not equal, so an admin narrowing a grant correctly would be refused and would
learn to write the wide one instead. A refusal people route around is worse than no refusal,
because everybody believes the rule is being kept.

**Rejected: a capability of this module's own for any of the five.** This is
`brain.console.govern`'s argument about `SESSION_CONTROL` and it applies four more times.
Inventing `admin:department_grant` from a console module puts a grant into the system from the
rendering layer, where the administrator who reviews grants would never meet it. Two
capabilities already exist over these acts and both are in the screen registry.
`REACH_AUTHORITY` is `approve:grant`, the Access review screen's own requirement, because
certifying a grant and writing one are the same decision at two moments and a decision made
twice does not acquire a second capability on the second occasion. `RUNG_AUTHORITY` is
`approve:action`, the Approvals screen's own requirement, because a rung is precisely what
decides which actions suspend for a person to approve, so raising one is that person giving up
their own review. Both are written out and pinned against their screens by a test rather than
derived from them: derived, the comparison would be a constant against itself.

**A self-grant is not refused here, and that absence is the point.** M33.1.2.5 asks for a
self-grant path that writes a loud audit event and notifies a steward, and
`brain.console.reads.is_self_grant` recognises one from the ledger entry rather than trusting
a declaration. Refusing self-grants here would delete a leaf somebody deliberately specified.
What containment does instead is better than a refusal: under it a self-grant can only ever
restate reach the granter already holds, because the scope must narrow their own and
`scope_for` intersects, so the set afterwards is no wider than the set before. See
`A_SELF_GRANT_INSIDE_YOUR_OWN_SCOPE_CONFERS_NOTHING`, which is asserted rather than argued.

**Time is the second axis a scope does not carry.** A contractor holding `approve:grant` for
three more weeks can write a grant with no expiry at all, and the grant outlives the authority
that wrote it. `EntitlementSet.intersect` takes `min` of the two bounds for this exact reason
and `brain.identity.roles.appoint_deputy` clamps a deputy to the grant it covers. So a
proposed grant may not outlive its granter. See
`A_GRANT_THAT_OUTLIVES_ITS_GRANTER_IS_A_SCOPE_WITH_THE_CLOCK_LEFT_OFF`.

**M33.2.2.4 has two halves and only one of them existed.**
`brain.console.reach_view.may_raise` decides whether the evidence behind a rise meets the bar
and whether an irreversible effect has its second approver, and lowering is unconditionally
true there for the reason that module gives: the fail-safe direction cannot be the one with
paperwork on it. What it never asks is whether the proposed rung is above the ceiling its side
effect allows. `brain.tools.registry.rung_ceiling` is that ceiling and it is applied on the
skill path in `brain.tools.run_skill` and **not on the main invoke path**: `brain.gate.invoke`
tightens the leash's rung by `autonomy_ceiling`, which is the risk score, and by nothing else.
So a money-touching target pinned to AUTONOMOUS by a console change runs autonomously on any
call whose risk score is low. `may_move_rung` asks both questions and neither of them here:
`may_raise` for the evidence and `rung_ceiling` for the ceiling. See
`A_RUNG_ABOVE_ITS_SIDE_EFFECTS_CEILING_IS_NOT_INERT`.

**Nothing here writes and nothing renders.** Every function returns the record or the verdict
and the caller does the writing, on the split `brain.ops.limits` keeps from
`brain.ops.limit_store`. `now` is a parameter everywhere, as in every sibling in this package.

**No console screen exists behind any of the five**, which is true of every group in this
package: `brain.console.screens.unregistered_tools([])` still returns all thirty-five. What is
claimed below is the authority decision, which is the half a screen cannot supply and the half
that was missing.

**M33.2.1.2, the department's own activity, was blocked until 2026-09-09 and is here now.** It
is the one surface in this module whose authority is not a scope, and the reason is the
finding recorded in `A_DEPARTMENT_SCOPED_AUDIT_GRANT_MATCHES_NOTHING`: an audit entry carries
no department, so a head's audit grant cannot hold a department clause and there is nothing
for `within_reach` to test against. The owner's answer, Option A on item 48, is that a head's
audit permissions name the people instead, written by
`brain.identity.staff_sync.audit_reach_for_head` and rewritten by the directory sync. What
this module adds is the narrowing on the way in and `activity_basis`, which puts the age of
that membership on the screen rather than leaving a stale page looking current.

Task ids: M33.2.1.2, M33.2.1.3, M33.2.1.4, M33.2.2.1, M33.2.2.2, M33.2.2.3, M33.2.2.4
Task ids: M33.2.2.5
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.agents.model import AgentRecord, entitlement_ceiling
from brain.audit.view import DEFAULT_PAGE_SIZE, AuditFilter, AuditPage, AuditView
from brain.console.operate import CoverageRow, coverage
from brain.console.reach_view import OPERATION_EFFECT, Operation, PromotionEvidence, may_raise
from brain.console.screens import screen
from brain.console.spend_view import Pace, pace
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.scope import Scope
from brain.core.scope_sql import scope_narrows
from brain.gate.injection import AutonomyTier
from brain.gate.leash import LeashEntry
from brain.identity.lifecycle import Adoption
from brain.identity.packs import SubjectGrant
from brain.identity.roles import DEPUTY_MAX, RoleGrant, appoint_deputy
from brain.identity.staff_sync import GRANT_LIFETIME
from brain.identity.staff_sync import due_at as next_read_due
from brain.identity.staff_sync import is_due as read_is_due
from brain.knowledge.item import KnowledgeItem
from brain.ops.budgets import Allowance, BudgetLevel
from brain.tools.registry import rung_ceiling

# ------------------------------------------------------------------ written-down reasons
#: Why a grant wider than its granter is the failure this module exists for.
A_GRANT_WIDER_THAN_ITS_GRANTER_IS_THE_ONE_ESCALATION_AN_ADDITIVE_MODEL_CANNOT_UNDO: Final = (
    "Entitlements are additive and there is no deny list anywhere, which is what makes a "
    "grant readable on its own. The price of that is that the only way access goes away is "
    "somebody deleting the row, so a grant nobody notices stands until somebody does. An "
    "admin who can write any scope can therefore write themselves a company-wide grant once "
    "and hold it forever, and every later review reads it as an ordinary row written by "
    "somebody with the authority to write rows. The refusal has to be at the moment of "
    "writing, because there is no mechanism downstream that could claw it back."
)

#: Why the row form and the predicate form of the check are one rule rather than two.
THE_ROW_FORM_AND_THE_PREDICATE_FORM_ARE_ONE_RULE: Final = (
    "brain.console.govern._in_reach is scope_for followed by Scope.matches, which asks "
    "whether a reader's grant admits one row. Granting asks whether it admits every row a "
    "proposed scope admits, which is scope_for followed by scope_narrows. They are the same "
    "rule at two granularities, because a row is a conjunction of equalities: matching a row "
    "is containment of the scope that row would be. Two implementations of a containment "
    "test is the shape where the permissive one wins, so there is one, in "
    "brain.core.scope_sql, and this calls it rather than comparing clause sets itself."
)

#: Why a permitted self-grant is harmless and is therefore not refused.
A_SELF_GRANT_INSIDE_YOUR_OWN_SCOPE_CONFERS_NOTHING: Final = (
    "M33.1.2.5 asks for a self-grant path that is loud rather than forbidden, and "
    "brain.console.reads recognises one from the ledger entry rather than from a "
    "declaration. Refusing one here would delete a leaf somebody specified. Containment "
    "makes the refusal unnecessary: a grant whose scope narrows the granter's own scope for "
    "the same capability adds nothing to what they already reach, because scope_for "
    "intersects every grant covering a capability and an intersection with something "
    "narrower is that narrower thing. The loud audit entry is still the right answer, and it "
    "is somebody else's module."
)

#: Why a grant may not outlive the entitlement that wrote it.
A_GRANT_THAT_OUTLIVES_ITS_GRANTER_IS_A_SCOPE_WITH_THE_CLOCK_LEFT_OFF: Final = (
    "A Scope is a predicate over rows and carries no time at all, so scope containment says "
    "nothing about a contractor with three weeks left writing a grant with no expiry. The "
    "grant then outlives the authority behind it and reads afterwards as though somebody "
    "still accountable had written it. EntitlementSet.intersect takes the tighter of two "
    "bounds for this reason and appoint_deputy clamps a deputy to the grant it covers for "
    "the same one. A granter with no bound may write an unbounded grant; a granter with one "
    "may not write past it."
)

#: Why lowering a rung needs a scope and no evidence.
LOWERING_A_RUNG_IS_THE_FAIL_SAFE_DIRECTION_AND_STILL_LANDS_ON_SOMEBODYS_ROWS: Final = (
    "brain.console.reach_view.may_raise returns true for any lowering and takes no evidence, "
    "because an incident is the worst moment to discover that turning something down needs "
    "paperwork. That argument is about evidence and not about whose agent it is. A leash "
    "entry carries a scope, so an admin writing one company-wide has stopped every "
    "department's work from a screen scoped to theirs. The company-wide stop already exists "
    "and is a different screen with a different capability: admin:halt, the global kill "
    "switch, which is M33.1.1.4 and belongs to a super administrator."
)

#: Why a rung above its side effect's ceiling is a live setting rather than a dead one.
A_RUNG_ABOVE_ITS_SIDE_EFFECTS_CEILING_IS_NOT_INERT: Final = (
    "brain.tools.registry.rung_ceiling is the one composition that tightens a rung by what "
    "its side effect suggests, and it is applied in brain.tools.run_skill and nowhere on the "
    "request path: brain.gate.invoke tightens the leash's rung by autonomy_ceiling, which is "
    "the risk score, and by nothing else. So a MONEY target that default_rung pins to SHADOW "
    "runs AUTONOMOUS on any call whose risk signals are quiet, if a console change put it "
    "there. Checking the ceiling at the moment of the change is the only place it is "
    "currently checked at all for an ordinary invocation."
)

#: Why a rung takes a different authority from a grant.
A_RUNG_IS_SUPERVISION_AND_SUPERVISION_IS_NOT_REACH: Final = (
    "E_run(caller, agent) = E(caller) intersect agent_ceiling, and no term in it is a rung. "
    "Moving a rung changes whether a person sees an action before it happens, never what the "
    "run may read, so it is not a reach entering the system and does not take the capability "
    "the other four here take. What it is exactly is a decision about which actions suspend "
    "for approval, so the authority is approve:action, held by the person whose queue it "
    "empties. An admin raising a rung is giving up their own review, which is theirs to give."
)

#: Why an approver may not wave through a ceiling they could not hold.
AN_APPROVER_OF_A_PUBLICATION_IS_APPROVING_EVERY_CAPABILITY_IN_THE_CEILING: Final = (
    "brain.builder.publish decides how many approvers a publish needs and refuses the author "
    "as one of them, and it never asks whether the approvers could have written the ceiling. "
    "A publication is a ceiling entering the world: brain.agents.model.entitlement_ceiling "
    "turns it into an EntitlementSet, and every grant in that set is a capability bound to "
    "the agent's scope. A department admin confirming one they could not have written "
    "themselves is brain.console.role_surfaces' rule about an approver, asked about a set "
    "rather than about one action, and it is the same rule govern applies to a certification."
)

#: Why adopting an agent is a reach decision rather than a stewardship one.
AN_ADOPTED_AGENT_STARTS_AGAIN_AT_THE_REACH_IT_ALWAYS_HAD: Final = (
    "brain.identity.lifecycle stops a leaver's agents and hands back Adoption records; adopt "
    "transfers the steward and starts it again, in that order, and the refusals it already "
    "makes are about the record and the new steward being active. None of them is about the "
    "admin doing the adopting. An agent's ceiling does not narrow when its owner leaves, so "
    "an admin who adopts one has put that ceiling back into the world under their own name, "
    "and if it reaches further than they do they are answering for something they cannot "
    "see. The queue is therefore filtered by the same containment as everything else here."
)

#: Why the deputy maximum is checked against the leaf and not against itself.
A_MAXIMUM_WRITTEN_TWICE_IS_A_MAXIMUM_THAT_AGREES_WITH_ITSELF: Final = (
    "brain.identity.roles.DEPUTY_MAX is thirty days and M33.2.2.5 says thirty days, and a "
    "test importing the constant and asserting it equals thirty is green for every value the "
    "constant could hold. The leaf sentence is the only statement of the figure outside the "
    "module, brain.status.leaf_sentences is the reader for it, and the number is taken out "
    "of the sentence's own words rather than written here a second time. A maximum somebody "
    "can raise is not a maximum, and a maximum only its author's arithmetic agrees with is "
    "not one either."
)


class AuthorityError(Exception):
    """A governing act was attempted beyond the scope the actor holds.

    Outside `brain.core.errors` for the reason `brain.console.govern.GovernError` gives about
    itself: those five outcomes describe an answer given to somebody who asked a question,
    and this is a refusal to perform an administrative act. Nobody asking a question sees one.
    """


# ------------------------------------------------------------------------- the one rule
#: The capability that decides whether a reach may enter the system, in any of four shapes.
#:
#: The Access review screen's own requirement, written out here rather than read off the
#: registry so that a test can compare the two: derived, the comparison would be a constant
#: against itself and repointing either would move both. `brain.console.govern.SESSION_CONTROL`
#: is pinned the same way, against the same screen, and records the same argument.
REACH_AUTHORITY: Final = Capability(value="approve:grant")

#: The screen that requirement belongs to. Pinned beside it, so the pair can be checked.
REACH_AUTHORITY_SCREEN: Final = "access_review"

#: The capability the rows behind this report are read with. The knowledge library's own,
#: because a coverage report is that library counted by area and nothing else, and a
#: capability invented here would be a second grant over the same rows. It is not asked
#: about here: `operate.coverage` asks it, and asking again would be the redundant check
#: that two mutations found in the first version of this surface.
COVERAGE_AUTHORITY: Final = Capability(value="read:knowledge")

#: The capability that decides whether supervision may be moved. Not `REACH_AUTHORITY`.
#:
#: See `A_RUNG_IS_SUPERVISION_AND_SUPERVISION_IS_NOT_REACH`. The Approvals screen's own
#: requirement, pinned the same way and against its own screen.
RUNG_AUTHORITY: Final = Capability(value="approve:action")

#: The screen that requirement belongs to.
RUNG_AUTHORITY_SCREEN: Final = "approvals"


def within_reach(
    entitlement: EntitlementSet,
    capability: Capability,
    scope: Scope,
    now: datetime | None = None,
) -> bool:
    """Whether this actor holds `capability` in a scope that contains `scope`.

    `EntitlementSet.scope_for` followed by `brain.core.scope_sql.scope_narrows`, which is
    `brain.console.govern._in_reach` with the row question replaced by the predicate
    question. See `THE_ROW_FORM_AND_THE_PREDICATE_FORM_ARE_ONE_RULE`. One narrowing, five
    surfaces, and no arithmetic of its own: `scope_for` decides what holding it means and
    refuses an expired principal, `scope_narrows` decides whether the held scope admits every
    row the proposed one does.

    `scope_narrows` is sound and incomplete by its own docstring and fails towards False, so
    a refusal here can be a scope this actor could in principle have written expressed in a
    shape the analysis cannot prove. That is the correct direction: the cost of a False is a
    person rewriting a predicate, and the cost of a wrong True is a grant nobody can take back.

    An unrestricted `scope` is contained only by an unrestricted holding, which falls out of
    `scope_narrows` rather than needing a case: every clause of a held scope has to be
    entailed by some clause of a scope that has none, and none is.
    """
    held = entitlement.scope_for(capability, now)
    if held is None:
        return False
    return scope_narrows(scope, held)


def ceiling_within_reach(
    ceiling: EntitlementSet,
    actor: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether every capability in `ceiling` is one this actor holds over that scope.

    All of them, so an empty ceiling is trivially within reach, which is right: an agent that
    narrows its caller to nothing reaches nothing and there is nothing to approve. The
    interesting direction is the other one, and it is the reason this returns a verdict rather
    than the capabilities that failed: `brain.console.role_surfaces` returns one value from a
    queue and has nowhere to put what it withheld, and a list of the capabilities an approver
    is short of is a description of the boundary of their own reach handed to them one
    publication at a time.
    """
    return all(within_reach(actor, one.capability, one.scope, now) for one in ceiling.grants)


def _outlives(bound: datetime | None, granter: EntitlementSet) -> bool:
    """Whether a proposed expiry runs past the granter's own.

    A granter with no bound may write an unbounded grant, and one with a bound may not write
    past it. See `A_GRANT_THAT_OUTLIVES_ITS_GRANTER_IS_A_SCOPE_WITH_THE_CLOCK_LEFT_OFF`. The
    unbounded proposal is the case worth naming: `None` is later than every datetime and
    comparing it as though it were a value is how it ends up sorting as the earliest.
    """
    if granter.not_after is None:
        return False
    return bound is None or bound > granter.not_after


# ------------------------------------------------------------------- granting (M33.2.2.2)
def may_grant(
    proposed: SubjectGrant,
    granter: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether this admin may write this grant (M33.2.2.2). Three questions, all of them.

    The authority to write grants at all, held over the scope being written. The capability
    being granted, held over the scope being written. And the granter's own expiry, which the
    grant may not run past.

    The first two are different questions with different capabilities and both are needed,
    which is the shape `brain.console.govern.may_certify` uses at the other moment: an admin
    holding `approve:grant` company-wide and `read:client.contract_value` in one department
    may not write that capability outside it, and an admin holding the capability everywhere
    but the authority in one department may not write it outside that.

    The second is asked against the grant's own capability rather than a wildcard covering
    it, because `EntitlementSet.scope_for` already expands a trailing `.*` through
    `Capability.covers`: an admin holding `read:client.*` may grant `read:client.name`, and
    one holding only the narrow capability may not grant the wide one.

    A self-grant is permitted and confers nothing; see
    `A_SELF_GRANT_INSIDE_YOUR_OWN_SCOPE_CONFERS_NOTHING`.
    """
    if not within_reach(granter, REACH_AUTHORITY, proposed.scope, now):
        return False
    if not within_reach(granter, proposed.capability, proposed.scope, now):
        return False
    return not _outlives(proposed.not_after, granter)


def write_grant(
    proposed: SubjectGrant,
    granter: EntitlementSet,
    now: datetime | None = None,
) -> SubjectGrant:
    """Return the grant this admin may write, or refuse it (M33.2.2.2).

    `may_grant` is asked here as well as by `grantable`, and that is not belt and braces: the
    listing decides what a screen offers and this decides what a submitted form may do, and a
    form is submitted by whatever was posted rather than by what was offered. It is the
    argument `brain.console.govern.certify` makes about the same pair.

    The refusal names the capability and the scope, and both of those are the granter's own
    submission read back to them, which discloses nothing they did not type. It names nothing
    about the subject: whether the subject already holds this, whether they exist, and whether
    somebody else has written the same grant are three facts about other people and none of
    them changed the answer.
    """
    if not may_grant(proposed, granter, now):
        msg = (
            f"{proposed.granted_by!r} may not grant {proposed.capability.value} over "
            f"{proposed.scope.model_dump_json()}. "
            f"{A_GRANT_WIDER_THAN_ITS_GRANTER_IS_THE_ONE_ESCALATION_AN_ADDITIVE_MODEL_CANNOT_UNDO}"
        )
        raise AuthorityError(msg)
    return proposed


def grantable(
    proposals: Sequence[SubjectGrant],
    granter: EntitlementSet,
    now: datetime | None = None,
) -> tuple[SubjectGrant, ...]:
    """The proposals in a batch this admin may write (M33.2.2.2). One value, and no count.

    A batch is what a pack assignment becomes: `brain.identity.packs.expand` turns one
    assignment into one grant per capability in the pack, all carrying the assignment's scope
    unchanged. So a pack is where this refusal earns its keep, because nobody reads twelve
    expanded rows and the one capability the admin does not hold is in the middle of them.

    Order follows `proposals`, for the reason `screens.offerable` gives: the caller's order is
    usually meaningful and re-sorting discards it. No second value carries what was dropped.
    """
    return tuple(one for one in proposals if may_grant(one, granter, now))


# ------------------------------------------------------------------- deputies (M33.2.2.5)
def may_appoint_deputy(
    standing: RoleGrant,
    admin: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether this admin may appoint a deputy against this standing grant (M33.2.2.5).

    A deputy appointment is a role in a scope entering the system, so it takes
    `REACH_AUTHORITY` over the scope the standing grant carries. A grant with no scope is a
    company-wide role, which `brain.identity.roles.SCOPE_REQUIRED` decides, and it is read
    here as the unrestricted scope: that is what a role restricting no rows means, and it
    fails closed, because only an unrestricted holding contains it. A department admin
    therefore cannot deputise a Super Admin, and nothing here needed a case for it.

    Says nothing about the length. `appoint_deputy` owns that, and asking it here as well
    would be a second copy of the maximum in the module that exists to have one copy of it.
    """
    return within_reach(admin, REACH_AUTHORITY, standing.scope or Scope.unrestricted(), now)


def appoint(
    standing: RoleGrant,
    admin: EntitlementSet,
    deputy_principal_id: str,
    *,
    granted_by: str,
    reason: str,
    now: datetime,
    days: int = DEPUTY_MAX.days,
) -> RoleGrant:
    """Appoint a deputy, refusing one outside this admin's scope (M33.2.2.5).

    The appointment itself is `brain.identity.roles.appoint_deputy`, called and never
    reimplemented. That function owns four refusals this one deliberately does not repeat:
    depth one, an inactive standing grant, a length outside one to `DEPUTY_MAX.days`, and the
    clamp that stops a deputy outliving the grant it covers. A second copy of the thirty days
    here is the failure `A_MAXIMUM_WRITTEN_TWICE_IS_A_MAXIMUM_THAT_AGREES_WITH_ITSELF` names,
    and it would be the copy that got raised.

    What is added is the scope question, which that module cannot ask because it takes no
    entitlement and must not: `brain.identity.roles` opens with the rule that no role implies
    a capability, and a function there that read an admin's grants would be the first place
    the two met.
    """
    if not may_appoint_deputy(standing, admin, now):
        msg = (
            f"{granted_by!r} may not appoint a deputy for {standing.role} over "
            f"{(standing.scope or Scope.unrestricted()).model_dump_json()}. "
            f"{A_GRANT_WIDER_THAN_ITS_GRANTER_IS_THE_ONE_ESCALATION_AN_ADDITIVE_MODEL_CANNOT_UNDO}"
        )
        raise AuthorityError(msg)
    return appoint_deputy(
        standing,
        deputy_principal_id,
        granted_by=granted_by,
        reason=reason,
        now=now,
        days=days,
    )


def deputy_runs_at_most() -> timedelta:
    """The longest a deputy appointment may run, read from the one place it is decided.

    `brain.identity.roles.DEPUTY_MAX`, returned rather than copied. A console module holding
    its own thirty days would be a second maximum, and the console's is the one an
    administrator reads, so it is the one that would look authoritative while being wrong.
    """
    return DEPUTY_MAX


# ---------------------------------------------------------------------- rungs (M33.2.2.4)
def within_ceiling(rung: AutonomyTier, operation: Operation) -> bool:
    """Whether this rung is at or below the ceiling this operation's side effect allows.

    `brain.tools.registry.rung_ceiling` composes with `min` and can only tighten, so a rung is
    within its ceiling exactly when tightening it changes nothing. Asked that way rather than
    by comparing against `default_rung`, because `rung_ceiling` is the composition the rest of
    the system uses and a comparison written here would be a second statement of what the
    ceiling is.

    `OPERATION_EFFECT` is `brain.console.reach_view`'s own mapping from the three console
    operations to the side effects the tool registry names, so the ceiling asked about is the
    one a tool of that shape would actually run under.
    """
    return rung_ceiling(rung, OPERATION_EFFECT[operation]) is rung


def may_move_rung(
    entry: LeashEntry,
    *,
    was: AutonomyTier,
    operation: Operation,
    admin: EntitlementSet,
    evidence: PromotionEvidence | None = None,
    now: datetime | None = None,
) -> bool:
    """Whether this admin may move this rung to what the entry says (M33.2.2.4).

    Three questions and they fail for different reasons.

    The scope, always, in both directions. A leash entry carries one and an admin writing it
    company-wide has reached outside their department whichever way the rung moved; see
    `LOWERING_A_RUNG_IS_THE_FAIL_SAFE_DIRECTION_AND_STILL_LANDS_ON_SOMEBODYS_ROWS`. The
    capability is `RUNG_AUTHORITY` rather than `REACH_AUTHORITY`, because a rung is not a
    reach: see `A_RUNG_IS_SUPERVISION_AND_SUPERVISION_IS_NOT_REACH`.

    The ceiling, unconditionally, and that is not the same as blocking a fall. Only the top
    rung is ever above a ceiling and nothing can fall to the top rung, so this refuses no
    lowering that could be written; what it does refuse is an entry that *keeps* a rung above
    its ceiling, which is how one that should never have been set gets cleaned up rather than
    re-affirmed. See `A_RUNG_ABOVE_ITS_SIDE_EFFECTS_CEILING_IS_NOT_INERT` for why the ceiling
    is not already being applied anywhere on the request path.

    The evidence, and it is `brain.console.reach_view.may_raise` rather than a rule of this
    module's. That function holds the clean-run count, the agreement rate and the second
    approver an irreversible effect needs, and it raises rather than returning False if a
    leash increase ever stops being a gated change. Reimplementing any of it here would be
    three thresholds in two places.

    **Rejected: a lowering short-circuit of this module's own.** The first version read `if
    entry.rung <= was: return True` before the two checks below, which reads as this module
    keeping the fail-safe rule itself. `may_raise`'s own first line is that rule, so nothing
    could tell the two apart: a mutation replacing the branch with `if False` and a mutation
    deleting it outright both survived every test in the file, because every path they
    changed ended at the same answer. Two checks nothing can separate are one check written
    twice, which is `brain.console.govern.friction`'s finding about its own pair. The rule
    belongs to `reach_view`, which argues for it, and this asks it once.
    """
    if not within_reach(admin, RUNG_AUTHORITY, entry.scope, now):
        return False
    if not within_ceiling(entry.rung, operation):
        return False
    return may_raise(
        was=was,
        proposed=entry.rung,
        evidence=evidence,
        effect=OPERATION_EFFECT[operation],
    )


# --------------------------------------------------------------- publications (M33.2.2.1)
def may_approve_publication(
    ceiling: EntitlementSet,
    approver: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether this department admin may approve this publication (M33.2.2.1).

    The ceiling the agent will run at, every capability of it, held by the approver over the
    agent's own scope. See
    `AN_APPROVER_OF_A_PUBLICATION_IS_APPROVING_EVERY_CAPABILITY_IN_THE_CEILING`.

    **Says nothing about how many approvers there are or whether the author is one of them.**
    `brain.builder.publish.approvers_needed` and `approval_refusals` own both, including the
    two-approver rule for a publish that widens a ceiling, and this is the question neither of
    them asks: whether a particular person is one of the people who could. A publish needing
    two approvers needs two who each pass this.
    """
    return ceiling_within_reach(ceiling, approver, now)


def approvable(
    ceilings: Sequence[EntitlementSet],
    approver: EntitlementSet,
    now: datetime | None = None,
) -> tuple[EntitlementSet, ...]:
    """The publications waiting in this admin's queue (M33.2.2.1). Filtered, never greyed out.

    Filtered before it is rendered rather than rendered whole with the out-of-scope rows
    disabled, which is `brain.console.govern.recertifiable`'s decision and for the same
    reason: a disabled row is the thing disclosed with an explanation attached.
    """
    return tuple(one for one in ceilings if may_approve_publication(one, approver, now))


# ------------------------------------------------------------------ adoptions (M33.2.2.3)
def may_adopt(
    record: AgentRecord,
    admin: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether this admin may take on a stopped agent (M33.2.2.3).

    The same question as a publication and asked with the same call, because it is the same
    event: a ceiling entering the world with somebody's name against it. See
    `AN_ADOPTED_AGENT_STARTS_AGAIN_AT_THE_REACH_IT_ALWAYS_HAD`.

    `brain.agents.model.entitlement_ceiling` builds the set, so the reach asked about is the
    one `E_run` would actually intersect against rather than a reading of the authority record
    made here. An agent with no capabilities is adoptable by anybody who reaches its screen,
    which is right: it narrows every caller to nothing.
    """
    return ceiling_within_reach(entitlement_ceiling(record), admin, now)


def adoptable(
    adoptions: Iterable[Adoption],
    admin: EntitlementSet,
    now: datetime | None = None,
) -> tuple[Adoption, ...]:
    """The orphaned agents this admin may adopt (M33.2.2.3).

    Over `brain.identity.lifecycle.agents_for_adoption`'s own output rather than over a scan
    of the estate, keeping that function's rule: a listing built from who owns what is an org
    chart with agent counts on it. Every record in an `Adoption` is already stopped, which its
    constructor refuses one without, so nothing here has to check that a running agent is not
    being handed over.

    Order follows `adoptions`, which that function sorts by id so an offboarding runbook
    processes the same list the same way twice. No count of the ones left out.
    """
    return tuple(one for one in adoptions if may_adopt(one.record, admin, now))


# -------------------------------------------------------------------------- the diagnostic
def authority_gaps(
    *,
    reach_authority: Capability = REACH_AUTHORITY,
    reach_screen: str = REACH_AUTHORITY_SCREEN,
    rung_authority: Capability = RUNG_AUTHORITY,
    rung_screen: str = RUNG_AUTHORITY_SCREEN,
) -> tuple[str, ...]:
    """Everything about this module that would let an act reach past the actor.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason `brain.console.govern.govern_gaps` gives about itself: a diagnostic that can only
    run against the healthy tree has nothing to report, so switching off any of its refusals
    changes nothing observable and every one survives. Calling it with no arguments is the
    deployment check and calling it with a constructed pair is the test.

    Three checks. Two hold each pinned capability to the screen it was taken from, which is
    what stops a console module quietly inventing a grant. The third holds them apart: a rung
    and a reach taking one capability would make supervision and access the same authority,
    and the day they merged, raising a rung would need the capability that writes grants,
    which reads as safer and is a strictly larger set of people holding the wrong one.
    """
    gaps: list[str] = []

    for pinned, key, what in (
        (reach_authority, reach_screen, "a reach"),
        (rung_authority, rung_screen, "a rung"),
    ):
        try:
            required = screen(key).read.requires
        except KeyError:
            gaps.append(
                f"{what} is authorised by {pinned.value}, pinned against a screen named "
                f"{key!r} that the registry does not have, so nothing checks the capability"
            )
            continue
        if pinned != required:
            gaps.append(
                f"{what} is authorised by {pinned.value} and the {key} screen requires "
                f"{required.value}, so this module has invented a capability from the "
                "rendering layer and the administrator who reviews grants will never meet it"
            )

    if reach_authority == rung_authority:
        gaps.append(
            f"a reach and a rung are both authorised by {reach_authority.value}, so "
            "supervision and access have become one authority. "
            f"{A_RUNG_IS_SUPERVISION_AND_SUPERVISION_IS_NOT_REACH}"
        )

    return tuple(gaps)


# ------------------------------------------------- what a department knows (M33.2.1.4)
#: Why this surface asks which departments somebody heads rather than which they can read.
#:
#: **The first version of this checked the reader's scope and two mutations proved it did
#: nothing.** `brain.console.operate.coverage` already narrows by the reader's own reach, so a
#: containment check here refused exactly what it was going to refuse anyway, and deriving the
#: areas from the named department changed nothing either. Both were redundant, which is the
#: honest reason this leaf sat open: read as "coverage, scoped", M33.2.1.4 is `coverage` and
#: nothing more.
#:
#: What makes it a department surface is a different question, and it is one nothing else
#: asks: **reading a department and heading it are not the same thing.** A person can hold
#: `read:knowledge` company-wide, for an audit or because somebody was generous, and head one
#: department. The company overview is right to show them everything they may read. A
#: department head's page is about the department they answer for, and showing them finance
#: because their grant happens to reach it turns the page into the overview with a heading.
#:
#: So the departments come from the role and never from the parameter, and a department this
#: person does not head produces nothing whether or not their grant reaches it.
HEADING_A_DEPARTMENT_IS_NOT_THE_SAME_AS_READING_IT: Final = (
    "A person may hold read:knowledge company-wide and head one department. Narrowing this "
    "page by what they may read shows them every department, which is the company overview "
    "with a heading on it. Narrowing it by what they head is the question the page is about, "
    "and the two differ for exactly the person most likely to be looking at it."
)


def department_coverage(
    department: str,
    items: Sequence[KnowledgeItem],
    entitlement: EntitlementSet,
    *,
    headed: Sequence[str],
    areas_of: Mapping[str, Sequence[str]],
    now: datetime,
) -> tuple[CoverageRow, ...]:
    """What this department knows and where the gaps are, for the person who heads it
    (M33.2.1.4).

    `brain.console.operate.coverage` does the counting and the staleness, called and not
    reimplemented: it already returns no row for an area the reader does not reach, counts an
    item against its own area, and carries no total, share or percentage, because each of
    those is this figure divided by a number the reader was not shown.

    **What is decided here is that heading a department and being able to read it are
    different questions.** See `HEADING_A_DEPARTMENT_IS_NOT_THE_SAME_AS_READING_IT`. `headed`
    is the departments this person answers for, which the caller derives from their role
    grants because that is `brain.identity.roles`' question and not this module's. Narrowing
    by their reach instead would be `coverage` with a heading on it, which two mutations
    proved when this was written that way.

    Empty rather than a refusal for a department this person does not head, and empty for one
    that does not exist, because those must be one answer: somebody who could tell a
    department they do not head from one that is not there has been handed the org chart one
    guess at a time.

    Both narrowings still apply. A head sees their own department's areas, and within them
    only what their own grant reaches, because `coverage` asks that second question and this
    module does not repeat it.
    """
    if not department.strip():
        msg = "a department coverage report needs a department; over none it is the company's"
        raise ValueError(msg)
    if department not in set(headed):
        return ()
    return coverage(
        items,
        entitlement,
        areas=tuple(areas_of.get(department, ())),
        now=now,
    )


# -------------------------------------------- what a department did, as its head reads it
#: Why this view is narrowed by people and never by the department it is named after.
#:
#: `brain.console.global_surfaces.activity_filter` refuses a department lens because an audit
#: entry carries no department. That is the visible half. The half found on 2026-09-08, while
#: trying to build the department version, is that **a department-scoped audit grant matches
#: no audit entry at all**: `brain.audit.view._scope_row` offers `action`, `actor_id`,
#: `subject` and `subject_kind`, and `brain.core.scope.Clause.matches` refuses a row that does
#: not carry the field, which is the correct fail-closed reading. So a department admin whose
#: audit grants are scoped to their own department reads an empty ledger, and would do so
#: whatever this module did with the filter. Run rather than reasoned about: the same reader
#: with the same capability scoped to a named person sees that person's entries, which is
#: both the confirmation and the shape of the fix.
#:
#: A wrapper that narrowed by member ids would therefore have been a surface that is always
#: empty for exactly the readers it is for, and its tests would have passed: every fixture
#: would have used a company-wide grant. It was item 48 in `docs/needs-rupash.md` because the
#: answer is a decision about what the longest-retained record in the estate says about a
#: person, and it was decided on 2026-09-09 as Option A: a head's audit permissions are
#: written against the people rather than against the department, and
#: `brain.identity.staff_sync.audit_reach_for_head` writes them. The sentence below is still
#: the finding and is now also the reason this function takes members and not a scope.
A_DEPARTMENT_SCOPED_AUDIT_GRANT_MATCHES_NOTHING: Final = (
    "An audit entry carries an action, a subject kind, a subject and an actor, and no "
    "department. A scope written against a department therefore matches no entry, because a "
    "missing field must never satisfy a predicate. brain.audit.view.CAPABILITY_BY_KIND gives "
    "one capability per subject kind and every one of them is matched against that same row, "
    "so a department admin whose audit grants are scoped to their department reads an empty "
    "ledger, and a department activity screen built on that would be empty for every reader "
    "it exists for while passing every test written with a company-wide fixture."
)

#: Why an empty member list may never be handed to an audit filter.
#:
#: `AuditFilter.actors` reads an empty set as every actor, on the same reading as an empty
#: scope, which is correct for a filter and catastrophic as a fallback. A failed membership
#: query would arrive here as an empty sequence and turn a department page into every actor
#: the reader's grant admits, under a department heading. `brain.core.department.compose`
#: refuses an empty list of scopes rather than returning the identity for exactly this reason
#: and says so in the same words.
AN_EMPTY_MEMBER_LIST_MEANS_EVERY_ACTOR: Final = (
    "brain.audit.view.AuditFilter reads an empty actors set as every actor rather than as no "
    "actor. So a department page handed no members would widen to everything its reader's "
    "grant admits, with a department's name at the top of it, and every row on the page would "
    "be one they were entitled to see, which is what makes it unnoticeable. It is refused "
    "here rather than defaulted, exactly as brain.core.department.compose refuses an empty "
    "sequence rather than returning the identity."
)

#: Why the screen's member list and the grant's member list are allowed to disagree.
A_FILTER_AND_A_GRANT_THAT_DISAGREE_CAN_ONLY_NARROW: Final = (
    "The members this page filters by are today's directory answer and the members inside the "
    "head's grant are the last sync's, so during the window between a transfer and the next "
    "run the two differ. Neither can widen the other: the filter is applied by "
    "brain.audit.view.AuditView on top of its own visibility decision, so a member the grant "
    "does not cover is absent and a person the grant still covers but the directory has moved "
    "out is dropped by the filter. The screen therefore closes the open half of the staleness "
    "window on the way in, and the grant closes it for everything else at the next run."
)

#: The capability that opens this page, and the screen it belongs to.
#:
#: `screen("audit").read.requires` rather than the string, so this cannot drift from the
#: registry, and it is the same capability `brain.identity.staff_sync.AUDIT_PAGE_CAPABILITY`
#: writes. The two are built from different sources on purpose, the registry here and
#: `brain.audit.view.AUDIT_NOUN` there, and `test_scoped_authority.py` asserts they agree:
#: derived from one another the comparison would be a constant against itself.
ACTIVITY_AUTHORITY: Final = screen("audit").read.requires


@dataclass(frozen=True)
class ActivityBasis:
    """How fresh the membership behind a head's activity view is, as the screen says it.

    Times and never counts. How stale the reading is, when the next one is due and whether it
    is overdue are all facts about this reader's own grant; how many people are in it or
    missing from it would be a count of what they cannot see, arrived at from the other side.
    """

    #: When the roster behind the head's audit grants was read.
    read_at: datetime
    #: When the next read is due, or None when the source has never been applied.
    due_at: datetime | None
    #: When the grants lapse if no read happens. See `staff_sync.GRANT_LIFETIME`.
    lapses_at: datetime
    #: True when the next read was due before now, which is the failure worth showing: a sync
    #: that has quietly stopped leaves the page confidently rendering an old department.
    overdue: bool


def activity_basis(*, read_at: datetime, now: datetime) -> ActivityBasis:
    """When the membership behind this page was read, and whether that reading is late.

    The visible half of the staleness cost item 48 records, and the reason it is a function
    rather than a sentence in a docstring: a window nobody is shown is a window nobody has.
    `brain.identity.staff_sync.THE_STALENESS_WINDOW` states it once and this puts the three
    moments a screen needs beside it.

    `due_at` and `is_due` are the sync's own, called and not recomputed. A second arithmetic
    for when a read is due would be a page saying one thing and the scheduler doing another,
    and the page is the one somebody believes.
    """
    return ActivityBasis(
        read_at=read_at,
        due_at=next_read_due(read_at),
        lapses_at=read_at + GRANT_LIFETIME,
        overdue=read_is_due(read_at, now),
    )


def department_activity(
    view: AuditView,
    department: str,
    *,
    headed: Sequence[str],
    members: Sequence[str],
    criteria: AuditFilter | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> AuditPage:
    """What this department's people did, for the person who heads it (M33.2.1.2).

    A narrowing of `brain.audit.view.AuditView.page` and nothing else. That module decides
    entry by entry what this reader may see and this one adds a filter on top of it, so a head
    cannot acquire by asking about their department anything they could not have read one
    entry at a time. `brain.console.auditor.permission_history` is the same shape one surface
    along and this deliberately does not restate its argument.

    **The narrowing is a set of people, because a department is not a thing an audit entry
    carries.** See `A_DEPARTMENT_SCOPED_AUDIT_GRANT_MATCHES_NOTHING` for the finding and
    `brain.identity.staff_sync.audit_reach_for_head` for the grants that make the reader's own
    side of it work. `members` is today's directory answer and the grant holds the last sync's;
    see `A_FILTER_AND_A_GRANT_THAT_DISAGREE_CAN_ONLY_NARROW`.

    **Empty rather than a refusal for a department this person does not head**, matching
    `department_coverage` and every other surface here: somebody who could tell a department
    they do not head from one that is not there has been handed the org chart one guess at a
    time. An empty page is also what a department with nothing in it returns, which is the
    point.

    `headed` is the departments this person answers for, derived by the caller from their role
    grants, because that is `brain.identity.roles`' question. It is asked instead of
    `within_reach(entitlement, ACTIVITY_AUTHORITY, Scope.department(department))`, which every
    other department surface here can ask and this one cannot: an audit grant scoped to a
    department is precisely the thing that matches no entry, so a head's real grant does not
    contain a department clause for that test to succeed against.

    Passing `criteria` narrows further by action, kind and date. Any actors it names are
    intersected with `members` rather than replacing them, so a caller cannot widen the page
    by naming somebody outside the department, and an intersection that comes out empty
    returns an empty page rather than a refusal: asking about somebody who is not in this
    department has to read the same as a department where nothing happened.
    """
    if not department.strip():
        msg = "a department activity view needs a department; over none it is the company's"
        raise ValueError(msg)
    if not members:
        msg = (
            f"the {department!r} activity view was given no members. "
            f"{AN_EMPTY_MEMBER_LIST_MEANS_EVERY_ACTOR}"
        )
        raise ValueError(msg)
    if department not in set(headed):
        return AuditPage()

    wanted = frozenset(members)
    if criteria is not None and criteria.actors:
        wanted &= criteria.actors
    if not wanted:
        # An intersection of nobody. Returned as an empty page and never as the empty filter,
        # which `AuditFilter` would read as every actor. See
        # `AN_EMPTY_MEMBER_LIST_MEANS_EVERY_ACTOR`, which is the same trap arriving by
        # subtraction rather than by an empty argument.
        return AuditPage()

    base = criteria or AuditFilter()
    return view.page(
        AuditFilter(
            actions=base.actions,
            subject_kinds=base.subject_kinds,
            actors=wanted,
            since=base.since,
            until=base.until,
        ),
        limit=limit,
        cursor=cursor,
    )


# ------------------------------------- what a department spent, against pace (M33.2.1.3)
#: The capability a department budget view is read behind: the budget screen's own.
BUDGET_AUTHORITY: Final = screen("budget").read.requires


def department_pace(
    department: str,
    allowance: Allowance,
    entitlement: EntitlementSet,
    *,
    started_at: datetime,
    ends_at: datetime,
    now: datetime,
) -> Pace | None:
    """This department's spend against the part of the period that has elapsed (M33.2.1.3).

    The arithmetic is `brain.console.spend_view.pace` and is called rather than repeated: it
    already refuses a per-run budget, a period with no length and an instant outside it, and a
    second copy of those three would be a second set of edge cases to keep in step.

    What is decided here is the two things that make it a department surface. The head's
    authority is asked about the department first, and **the allowance has to be this
    department's own**. That second one is the mistake worth guarding: a company allowance
    passed to a department page renders the company's consumption under a department heading,
    every figure correct and every one about somebody else. It is refused rather than
    rendered, because a pace is two fractions and neither of them says whose.

    `None` rather than a refusal for a head who does not reach the department, matching every
    other surface here: a refusal naming the department would answer "does this exist".
    """
    if not department.strip():
        msg = "a department budget view needs a department; over none it is the company's"
        raise ValueError(msg)
    if allowance.row.level is not BudgetLevel.DEPARTMENT or allowance.row.subject != department:
        msg = (
            f"the allowance is {allowance.row.level.value}:{allowance.row.subject!r} and this "
            f"is the {department!r} page; a budget from another level renders somebody else's "
            "consumption under this heading with every figure correct"
        )
        raise ValueError(msg)
    if not within_reach(entitlement, BUDGET_AUTHORITY, Scope.department(department), now):
        return None
    return pace(allowance, started_at=started_at, ends_at=ends_at, now=now)
