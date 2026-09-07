"""Joining, moving and leaving: what each transition means and what it has to reach.

This module is the security story of the platform told backwards. Everything else here is
written to make somebody able to work; these three transitions are written to say what stops
working the moment their job changes, and when.

**It decides and it does not execute.** A transition is a decision about rows in tables this
module does not open, so what comes back is a `Plan` and a set of computed facts, not a
sequence of writes. That is the split `brain.ops.limits` and `brain.ops.limit_store` keep and
for the same reason: the case that is always wrong is the boundary, and you cannot test a
boundary through a module that holds a connection. The one exception is session termination,
argued where it happens.

**The plan is total over the surfaces, and `Action.NOTHING` is a claim rather than a gap.**
`Plan` refuses to be constructed unless every member of `Surface` appears exactly once, so a
surface nobody thought about is a build failure and not a silence. And a step that says
nothing has to happen must carry one of the reasons in `REASONS_FOR_DOING_NOTHING`, which are
this module's named constants: you cannot assert that a transition need not reach somewhere
without writing down why, in the module, where a reviewer meets it.

That construction is the answer to the sharpest leaf in the group. **A mover flow that had to
remember to purge the answer cache is a mover flow that will one day forget.** It does not
have to. `brain.gate.cache_key` builds an answer key from the entitlement hash, and
`EntitlementSet.ent_hash` is a digest of the grants themselves, so a person whose grants moved
computes a different key and there is no code path anywhere that finds the old entry. Nothing
is invalidated, purged or swept, because nothing can be reached. `answer_keys` proves it by
building both keys with the real builder rather than by calling an invalidation function that
would have to be remembered.

The same shape holds twice more. **Entitlement re-resolution needs no propagation delay**
because `brain.gate.resolve.cache_key` carries `grants_version` and the bump is an AFTER
trigger on the grant tables (`migrations/versions/0003_resolver_and_tables.py`), so a key built
before a change is orphaned in the same transaction that made it. **Knowledge access needs no
reindex** because `brain.knowledge.search.reach_predicate` conjoins the caller's reach into the
query before `LIMIT`, so the chunk rows never carried a person's name to begin with.

What would have to be true for the second of those to be false is worth stating rather than
assuming, because it is checkable and it is nearly false already. The bump triggers fire on
`INSERT OR UPDATE` and there is no `DELETE` trigger, so the guarantee rests on revocation being
a soft delete: `CapabilityGrantRow` carries `SoftDeleteMixin`, so setting `deleted_at` is an
UPDATE and the version moves. A hard `DELETE FROM gate.capability_grant` would revoke a grant
without bumping anything, and `brain.gate.resolve` would go on serving the pre-revocation set
for the length of `CACHE_TTL_SECONDS`. The second way it fails is a grant-bearing table with no
trigger on it: `resolve_entitlement` reaches a person through `TeamMembership` as well as
through their own rows, and there is no `team_membership` table yet, so whoever builds it has
to put a bump trigger on it or a mover's team change will not invalidate anything.

**Delegations are suspended and never narrowed, and the difference is consent.** Somebody
delegated a specific thing. Narrowing it when their delegator moves would leave them doing a
smaller, different thing that nobody agreed to, silently, with every row looking correct. So
`reevaluate_delegations` has nowhere to put a narrowed grant: what it hands back for a
delegation that stopped standing is a `Reconfirmation`, which names the delegation and the
person who must decide about it, and the function checks its own output is the objects it was
given, by identity, before returning. That is the argument `brain.identity.directory.reconcile`
makes about `to_delete` being a set difference: a function that could name a row it was not
shown is a function that could act on one nobody read first.

**Revocation is the deletion of a grant, and a leaver's disable is three acts in one call.**
There is no deny list here, no suspension flag on a grant, and no field anywhere that
subtracts at resolve time; `brain.identity.packs.subtractive_state` refuses across the identity
package and this module is written to pass it. What `disable` does instead is delete the rows,
end the sessions and bound the principal, and it does all three or it raises. A session that
outlives the disable is the whole revocation defeated for the length of the session lifetime,
and a principal left unbounded is a fresh token accepted after the floor, so none of the three
is a separate call a caller can skip. The shape is `brain.identity.roles.open_break_glass`'s:
both, or neither.

**Nothing here tells a joiner what exists in departments they cannot see.** The welcome path
takes one department name and there is no parameter on it that a registry fits into;
`assert_welcome_cannot_enumerate_departments` refuses a builder that grows one, which is the
mechanism `assert_no_role_in_resolution` and `assert_reconciler_cannot_reach_hand_made_grants`
both use. And the starter questions are derived from the starter pack, so the welcome path
cannot offer a question the joiner would be refused.

**A claim proposes a department and never grants one.** `MappedIdentity.primary_department`
comes off a token, and `brain.identity.oidc` exists to stop the identity provider becoming the
permission model. So `provision` takes the department as an argument somebody here supplies,
records what the claim said as a proposal for an operator to reconcile, and builds the scope
from the argument. The claim reaches `Principal.primary_department`, which is a fact about a
person, and it reaches no scope.

Four designs were rejected.

*A `suspended` column on a delegation.* It is a negative row with a friendlier name, it gives
resolution an evaluation order, and `subtractive_state` refuses it across this package.
Suspension here is the absence of the delegation from the standing set plus a request the
delegator can see and act on, which is visible and reversible in a way a column is not.

*A mover step that purges the answer cache.* It would work, and it would teach every future
reader that the cache needs purging, at which point the property that makes it unnecessary
stops being maintained and the purge becomes load-bearing. The step is `NOTHING` and it carries
the argument.

*Executing the grant writes here.* A module that both decided a transition and wrote it would
be one whose dangerous half only runs against a real database, which is
`brain.identity.directory.Reconciliation`'s argument for returning two sets and no verbs.

*Re-pointing a leaver's agents at their department admin automatically.* An owner who did not
choose the agent cannot answer for it, and an agent that keeps running with nobody answering
for it is the thing M26.3.2 exists to prevent. The default is that it stops:
`agents_for_adoption` returns records already disabled, and `adopt` is the deliberate act that
transfers and then starts it, in that order.

No SQLAlchemy model and no migration is written here, and no existing module is edited. Where a
leaf implies a table (`automation`), this is the type and the rule only. This module is not
re-exported from `brain.identity`, which is how `oidc` and `sessions` already are: a caller
names the module rather than picking it up from a package import.

Task ids: M26.1.1, M26.1.2, M26.1.3, M26.1.4, M26.2.1, M26.2.2, M26.2.3
Task ids: M26.2.4, M26.2.5, M26.2.6, M26.3.1, M26.3.2, M26.3.3, M26.3.4, M26.3.5
"""

from __future__ import annotations

import enum
import inspect
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, assert_never

from brain.agents.lifecycle import agents_needing_transfer, transfer_ownership
from brain.agents.lifecycle import disable as stop_agent
from brain.agents.lifecycle import enable as start_agent
from brain.agents.model import AgentRecord
from brain.core.department import SLUG_RE, admits_department, department_scope
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope_sql import scope_narrows
from brain.gate.cache_key import key_for as answer_cache_key
from brain.gate.resolve import cache_key as entitlement_cache_key
from brain.identity.oidc import MappedIdentity
from brain.identity.packs import (
    CapabilityPack,
    PackAssignment,
    SubjectGrant,
    resolve_entitlement,
    revoke,
)
from brain.identity.roles import (
    IdentityError,
    NoStandingEntitlement,
    Role,
    RoleGrant,
    assert_not_a_role,
)
from brain.identity.sessions import Session, SessionRegistry
from brain.identity.teams import TeamMembership, principal_subject
from brain.knowledge.search import KNOWLEDGE_READ, Reach, reach_for
from brain.knowledge.visibility import Visibility
from brain.memory.formation import Formation, Recollection, recallable
from brain.ops.automation import flow_reach
from brain.ops.erasure import Disposition
from brain.ops.retention import Store


class LifecycleError(IdentityError):
    """Raised when a joiner, mover or leaver transition would be unsafe to record.

    An authoring-time failure, like `PackError` and `DepartmentError`. Nobody asking a
    question ever sees it: it is what stops a transition being written down wrongly, and it
    is outside the `brain.core.errors` taxonomy because those five outcomes describe an
    answer given to a person.
    """


def _aware(value: datetime, field: str) -> datetime:
    """Refuse a naive timestamp.

    The same three lines `brain.identity.roles` and `brain.identity.packs` each carry
    privately. Hoisting it into one place would be an edit to two modules other people are
    working in, which this one may not make; a fourth copy would be worse than a third.
    """
    if value.tzinfo is None:
        msg = f"{field} must be timezone-aware; a naive timestamp is a silent bug"
        raise LifecycleError(msg)
    return value


# ------------------------------------------------------------------- the state machine
class Standing(enum.StrEnum):
    """Where somebody is in their working life here. Three states and no fourth.

    `NOT_PROVISIONED` is not "disabled before they arrived". It is the state in which this
    system holds no principal for them at all, which is what `brain.identity.oidc`'s
    `UnmappedSubject` describes from the token side, and it is different from `DISABLED` in
    the one way that matters: there is nothing to end, so a transition into `DISABLED` from
    it would report success for work that never happened.
    """

    NOT_PROVISIONED = "not_provisioned"
    ACTIVE = "active"
    DISABLED = "disabled"


class Transition(enum.StrEnum):
    """The three transitions. A move is the one with the same state on both sides."""

    JOIN = "join"
    MOVE = "move"
    LEAVE = "leave"


#: Why somebody coming back is a joiner rather than an un-leaver.
COMING_BACK_IS_JOINING_AGAIN: Final = (
    "There is no un-leave and there is no function here that undoes one. Revocation is the "
    "deletion of a grant, so a leaver's rows are gone and there is nothing left to switch "
    "back on; their sessions ended and the logout floor is monotonic, so nothing they held "
    "is admitted again. Somebody returning is provisioned: a role, a starter pack and a "
    "department, decided now rather than restored from what they had before they left. A "
    "restore would hand back a reach that was reviewed against a job they no longer do."
)


def transition_for(before: Standing, after: Standing) -> Transition:
    """Which transition this is, or a refusal (M26.1.1, M26.2.1, M26.3.1).

    Four pairs are refused and each one is a way an offboarding or onboarding run silently
    does nothing useful.

    Disabling somebody who was never provisioned reaches no rows, ends no sessions and
    reports success, which is the shape of an offboarding run that skipped the person it was
    for. Returning anybody to `NOT_PROVISIONED` is the removal of the identity itself, which
    is `brain.ops.erasure`'s and needs a deletion request behind it, not a leaver's form.
    Staying in `NOT_PROVISIONED` is not a transition at all.

    `DISABLED` to `ACTIVE` is a join and not a reversal. See `COMING_BACK_IS_JOINING_AGAIN`.
    `DISABLED` to `DISABLED` is a leave, so re-running an offboarding is safe and does the
    thing that matters again: `SessionRegistry.end_all_for` raises the floor whether or not
    there was a session to end.
    """
    match (before, after):
        case (Standing.NOT_PROVISIONED, Standing.ACTIVE) | (Standing.DISABLED, Standing.ACTIVE):
            return Transition.JOIN
        case (Standing.ACTIVE, Standing.ACTIVE):
            return Transition.MOVE
        case (Standing.ACTIVE, Standing.DISABLED) | (Standing.DISABLED, Standing.DISABLED):
            return Transition.LEAVE
        case (Standing.NOT_PROVISIONED, Standing.DISABLED):
            msg = (
                "disabling somebody who was never provisioned reaches no grant and ends no "
                "session, and would report success for the person an offboarding run missed"
            )
            raise LifecycleError(msg)
        case (_, Standing.NOT_PROVISIONED):
            msg = (
                "there is no transition back to not provisioned; removing the identity is a "
                "deletion request and belongs to brain.ops.erasure, not to a leaver form"
            )
            raise LifecycleError(msg)
        case _:  # pragma: no cover - the nine pairs above are the whole cross product
            # A refusal rather than `assert_never`, which is what the other total functions
            # in this repository use. mypy proves exhaustiveness over a bare enum and not
            # over a tuple of two, so `assert_never` here would be a type error claiming a
            # guarantee the checker cannot give. Refusing keeps the honest behaviour if a
            # fourth `Standing` is ever added: the pair nobody decided about raises rather
            # than falling through to whichever transition is written first.
            msg = f"{before} to {after} is not a transition anybody has decided about"
            raise LifecycleError(msg)


# --------------------------------------------------- what a transition has to reach
class Surface(enum.StrEnum):
    """Every place a lifecycle transition is answerable for.

    Closed, and every plan covers all of it. A surface that could be left out of a plan is a
    surface that gets left out of the plan written in a hurry, and the omission looks exactly
    like a decision that nothing was needed there.

    `ANSWER_CACHE` and `ENTITLEMENT_CACHE` are two members rather than one because they are
    invalidated by two different mechanisms: the first by the entitlement hash in its key,
    the second by the grants version in its key, and reaching one is not reaching the other.
    That is the distinction `brain.ops.retention.Store` draws between `CACHE` and `INDEX`.
    """

    #: Capability grants and pack assignments: the rows that decide what somebody may see.
    GRANTS = "grants"
    #: Which department's scope those rows are bound to. Carried on the assignment rather
    #: than in a column of its own, which is why it goes when the assignment goes.
    DEPARTMENT = "department"
    #: Live sign-ins and the logout floor.
    SESSIONS = "sessions"
    #: Deputy appointments made against somebody's standing grant.
    DELEGATIONS = "delegations"
    #: Agents whose steward is the person in question.
    AGENTS = "agents"
    #: Scheduled work running under their name.
    AUTOMATIONS = "automations"
    #: The cached answers keyed on an entitlement hash.
    ANSWER_CACHE = "answer_cache"
    #: The resolved entitlement sets keyed on a grants version.
    ENTITLEMENT_CACHE = "entitlement_cache"
    #: What the system learnt while acting for somebody.
    MEMORY = "memory"
    #: The retrieval index over the document plane.
    KNOWLEDGE_INDEX = "knowledge_index"
    #: The starter questions a new joiner is offered.
    WELCOME = "welcome"
    #: The hash-chained ledger.
    AUDIT = "audit"


class Action(enum.StrEnum):
    """What a transition does at one surface.

    `NOTHING` is the member that carries the weight. It says the surface is reached by
    construction and there is no code to run, which is a claim about the design rather than
    an absence of work, so `Step` refuses one that does not name the argument.
    """

    #: Rows are written. Access appears.
    WRITE = "write"
    #: Rows are removed. The only revocation there is.
    DELETE = "delete"
    #: Rows removed and rows written, in one transaction. See `A_GRANT_CHANGE_IS_ONE_ACT`.
    REPLACE = "replace"
    #: Sessions terminated, automations stopped, agents stopped.
    END = "end"
    #: A person has to decide. Nothing changes until they do.
    REVIEW = "review"
    #: Reached by construction. There is nothing to run.
    NOTHING = "nothing"


# ------------------------------------------------------------------ the named reasons
#: Why the answer cache needs no purge on a move (M26.2.4).
CACHED_ANSWERS_ARE_UNREACHABLE_BY_CONSTRUCTION: Final = (
    "An answer key is built from the entitlement hash, and the hash is a digest of the "
    "grants themselves, so a person whose reach changed computes a different key and there "
    "is no code path anywhere that finds the old entry. Nothing is invalidated, purged or "
    "swept. A mover flow that had to remember to purge a cache is a mover flow that will "
    "one day forget, and the failure is silent and serves somebody else's answer."
)

#: Why an answer outlives the person who asked for it, at a join and at a departure.
AN_ANSWER_BELONGS_TO_A_REACH_AND_NOT_TO_A_PERSON: Final = (
    "The answer key carries no principal id, deliberately: two callers of identical reach "
    "share an answer, which is the whole point of the cache. So a joiner may read an answer "
    "computed for somebody with the same grants, correctly, and a leaver's answers stay "
    "readable by whoever still has the reach they were computed under. Neither is a "
    "disclosure, because the thing that decided the answer is the thing the key is built "
    "from."
)

#: Why the entitlement cache needs no invalidation (M26.2.1).
THE_VERSION_IS_IN_THE_KEY_SO_NOTHING_IS_INVALIDATED: Final = (
    "brain.gate.resolve builds its key as ent:<principal>:<version>, and the version is "
    "bumped by an AFTER trigger on every grant-bearing table rather than by application "
    "code, so a key built before a change is orphaned in the transaction that made it. A "
    "delete that does not arrive is the failure mode of the alternative, and nothing "
    "reports it. What this rests on is the delete being soft: the triggers fire on INSERT "
    "and UPDATE, so a hard DELETE would revoke a grant without moving the version."
)

#: Why a mover keeps their session (M26.2.1).
A_SESSION_CARRIES_NO_ENTITLEMENT: Final = (
    "A session is evidence about how somebody authenticated, and brain.identity.sessions "
    "puts nothing else on it: there is no grant, no scope and no hash on the record. Reach "
    "is resolved per request, so a session opened before a move is already carrying the "
    "reach the mover has now. Ending it would sign somebody out mid-sentence for a change "
    "that does not touch what their session is evidence of."
)

#: Why a personal agent needs no edit when its owner moves (M26.2.2).
A_PERSONAL_AGENT_FOLLOWS_ITS_OWNER_AND_NOT_A_DEPARTMENT: Final = (
    "A personal agent's audience is its owner id, so it follows the person and no record "
    "is touched when they move. A department agent's audience is the department, so it "
    "stays where it is and the mover simply stops being in its audience. Both fall out of "
    "brain.agents.model.visible_to being asked about the viewer, and a move that edited "
    "agent rows would be a move that could get either of them wrong."
)

#: Why a mover's automations need no edit (M26.2.2, M26.3.3).
AN_AUTOMATION_IS_INTERSECTED_PER_RUN: Final = (
    "brain.ops.automation.flow_reach is E(caller) intersect flow_ceiling, computed at each "
    "run, so a flow owned by somebody who moved reaches whatever they reach now and never "
    "more. Nothing about the flow is edited, and nothing about it could widen. Whether it "
    "still does anything useful is a question for its owner and not a safety question."
)

#: Why a memory needs no rewrite when a reader's reach changes (M26.2.5).
A_MEMORY_IS_RECALLED_AT_THE_REACH_IT_WAS_FORMED_AT: Final = (
    "brain.memory.formation.may_recall checks the reader against what the memory was formed "
    "from, on every read, so a memory tagged with a capability set the mover no longer holds "
    "stops being recalled without anything being marked, moved or deleted. Rewriting the "
    "tags on a move would be a second rule about recall, and the permissive copy is the one "
    "that wins the day the two disagree."
)

#: Why knowledge access changes with no reindex (M26.2.6).
THE_PREDICATE_IS_IN_THE_QUERY_SO_THERE_IS_NOTHING_TO_REINDEX: Final = (
    "brain.knowledge.search.reach_predicate conjoins the caller's reach into the candidate "
    "query before LIMIT, so a chunk row carries a visibility level, a department and an "
    "owner and never a list of who may read it. A move changes the predicate the next query "
    "is built from and touches no row in the index. An index that stored readers would have "
    "to be rewritten per person on every grant change, and the rewrite that does not "
    "complete is a person still retrieving what they may no longer see."
)

#: Why the welcome path is a joiner's alone (M26.1.4).
ONLY_A_JOINER_GETS_A_WELCOME_PATH: Final = (
    "The welcome path is three questions somebody is offered because they have just arrived "
    "and do not know what to ask. Offering it on a move or a departure would be offering a "
    "tour of what somebody can reach, which for a mover is a diff of their old reach "
    "against their new one and for a leaver is a list of what they have lost."
)

#: Why a joiner has nothing to end (M26.1.1).
A_JOINER_HOLDS_NOTHING_BEFORE_THEY_ARE_PROVISIONED: Final = (
    "Before provisioning there is no principal, so there is no session, no delegation, no "
    "agent and no automation to reach. This is stated rather than left blank because the "
    "state it describes is the one a rejoiner is in as well, and a rejoiner looks like "
    "somebody who might still have things attached to them. They do not: leaving deleted "
    "the rows and stopped the agents, and nothing here restores either."
)

#: Why the two halves of a grant change are one transaction (M26.2.1).
A_GRANT_CHANGE_IS_ONE_ACT: Final = (
    "A move deletes the rows that bound somebody to where they were and writes the rows "
    "that bind them to where they are, and the two are one transaction. Deleting first "
    "leaves a window in which the mover holds nothing and their work fails for reasons "
    "nobody can explain; writing first leaves a window in which they hold both, which is "
    "the window an audit will ask about."
)

#: Why revocation is deletion (M26.3.1).
REVOCATION_IS_THE_DELETION_OF_A_GRANT: Final = (
    "There is no deny list in this system and there must not be one. A leaver loses access "
    "because the rows that conferred it are gone, never because a row was added saying no. "
    "brain.identity.packs.ADDITIVE_ONLY is the sentence and subtractive_state is the sweep "
    "that keeps it true across this package, this module included."
)

#: Why a disable and a session termination are one call (M26.3.1).
A_DISABLE_THAT_LEAVES_A_SESSION_LIVE_IS_NOT_A_DISABLE: Final = (
    "A session that outlives the disable is the entire revocation defeated for the length "
    "of the session lifetime, which is up to ten hours. So disable ends the sessions, "
    "raises the logout floor and bounds the principal in the same call, and there is no "
    "argument to it that skips any of the three. Ending sessions without bounding the "
    "principal is the same failure one step later: the floor refuses the tokens already "
    "issued, and a fresh one minted a second afterwards is admitted."
)

#: Why a delegation is suspended rather than narrowed (M26.2.3).
A_DELEGATION_IS_SUSPENDED_AND_NEVER_NARROWED: Final = (
    "Somebody delegated a specific thing. Narrowing it when their delegator moves would "
    "leave them doing a smaller, different thing that nobody agreed to, and nothing about "
    "the row would say so. Suspension is visible and reversible: the delegation stops "
    "standing and the delegator is asked to confirm it again on the terms that hold now. "
    "So there is nowhere in this module's output for a narrowed grant to go, and "
    "reevaluate_delegations checks that every grant it hands back is one it was given, by "
    "identity, before it returns."
)

#: Why an agent whose steward has gone stops (M26.3.2).
AN_UNADOPTED_AGENT_STOPS: Final = (
    "An agent nobody answers for keeps running against a persona and a ceiling that were "
    "signed off by somebody who has left, and the person who would notice it going wrong is "
    "the one who is gone. So the default is that it stops, reversibly: agents_for_adoption "
    "returns records already disabled, and adopt is the deliberate act that gives it a "
    "steward and starts it again. Disabled and not archived, because archiving is terminal "
    "and an unadopted agent is waiting for a decision rather than finished."
)

#: Why a leaver's automations are stopped rather than left to run empty (M26.3.3).
AN_EMPTY_REACH_IS_NOT_A_STOPPED_AUTOMATION: Final = (
    "A flow owned by a leaver reaches nothing, because flow_reach intersects with an owner "
    "who now holds nothing, and that is the safety property. It is not the stop. A flow that "
    "runs on schedule and quietly produces nothing looks healthy on every screen, fills the "
    "queue, spends the budget and hides the fact that the work it was doing is not being "
    "done. Stopping it is what makes the gap visible to whoever picks the work up."
)

#: Why a departure keeps what a deletion request would remove (M26.3.4).
A_DEPARTURE_IS_NOT_A_DELETION_REQUEST: Final = (
    "Leaving is a change in what somebody may reach, not a decision that what they wrote "
    "should stop existing. Personal knowledge stays at personal visibility with the leaver "
    "as owner, which makes it reachable by nobody without touching the index and without "
    "promoting anything, and promotion stays behind brain.knowledge.visibility's approval "
    "path where it belongs. Memories stay because recall is decided by the reader's reach "
    "and never by the writer's, so a colleague who still reaches what a memory was formed "
    "from still gets it. Erasing either at departure would destroy the company's own record "
    "on an event that is not a deletion request, and brain.ops.erasure is where one is "
    "answered."
)

#: Why the audit record outlives every transition (M26.3.5).
THE_AUDIT_RECORD_OUTLIVES_EVERY_TRANSITION: Final = (
    "brain.ops.retention gives the audit class Lifetime.NEVER_EXPIRES and brain.ops.erasure "
    "gives the audit store Disposition.RETAINED, which is the one store a deletion request "
    "does not reach. A lifecycle transition is a weaker event than a deletion request, so it "
    "reaches it even less. Every transition writes to the ledger and none of them removes "
    "anything from it."
)

#: Why the department is an argument and never a claim (M26.1.3).
A_CLAIM_PROPOSES_A_DEPARTMENT_AND_NEVER_GRANTS_ONE: Final = (
    "MappedIdentity.primary_department comes off a token, and brain.identity.oidc exists to "
    "stop the identity provider becoming the permission model. So the department a scope is "
    "built from is an argument somebody here supplies, the claim is recorded as a proposal "
    "for an operator to reconcile, and the two are separate fields on the provisioning so "
    "that a disagreement is visible rather than resolved by whichever was read last."
)

#: Why a joiner cannot provision themselves (M26.1.2).
A_JOINER_IS_PROVISIONED_BY_SOMEBODY_ELSE: Final = (
    "The person who runs the onboarding is not the person arriving, for the reason a "
    "break-glass session is authorised by somebody other than the principal using it: a "
    "grant somebody wrote for themselves is a decision the company did not make. It is one "
    "comparison and it rules out the case where a provisioning endpoint is reachable by the "
    "account it provisions."
)

#: Why the starter questions are derived from the starter pack (M26.1.4).
A_STARTER_QUESTION_IS_ANSWERABLE_WITH_THE_STARTER_PACK: Final = (
    "Every starter question names the capabilities it needs, and the welcome path keeps a "
    "question only when the joiner holds all of them in their own department. So a question "
    "the joiner would be refused is never offered, and a question about a department they "
    "cannot see cannot be constructed, because the builder is given one department name and "
    "has no parameter a registry fits into. Offering a question that comes back empty would "
    "teach a new joiner, on their first day, exactly which things exist and are not theirs."
)

#: The arguments that may stand behind `Action.NOTHING`. A step claiming a transition need
#: not reach a surface has to name one of these, so the claim comes with its reason attached
#: in the module rather than in a commit message somebody has to find.
REASONS_FOR_DOING_NOTHING: Final[frozenset[str]] = frozenset(
    {
        CACHED_ANSWERS_ARE_UNREACHABLE_BY_CONSTRUCTION,
        AN_ANSWER_BELONGS_TO_A_REACH_AND_NOT_TO_A_PERSON,
        THE_VERSION_IS_IN_THE_KEY_SO_NOTHING_IS_INVALIDATED,
        A_SESSION_CARRIES_NO_ENTITLEMENT,
        A_PERSONAL_AGENT_FOLLOWS_ITS_OWNER_AND_NOT_A_DEPARTMENT,
        AN_AUTOMATION_IS_INTERSECTED_PER_RUN,
        A_MEMORY_IS_RECALLED_AT_THE_REACH_IT_WAS_FORMED_AT,
        THE_PREDICATE_IS_IN_THE_QUERY_SO_THERE_IS_NOTHING_TO_REINDEX,
        ONLY_A_JOINER_GETS_A_WELCOME_PATH,
        A_JOINER_HOLDS_NOTHING_BEFORE_THEY_ARE_PROVISIONED,
        A_DEPARTURE_IS_NOT_A_DELETION_REQUEST,
    }
)


@dataclass(frozen=True)
class Step:
    """One surface, what happens there, and the argument for it.

    `because` is required prose on every step and not only on the ones that do nothing, for
    the reason `brain.ops.retention.Horizon.because` is required: a decision nobody can
    explain is a decision that gets reversed the first time it is inconvenient, and the
    reversal is permanent because nobody left behind what the original was protecting.
    """

    surface: Surface
    action: Action
    because: str

    def __post_init__(self) -> None:
        if not self.because.strip():
            msg = f"the step for {self.surface} carries no argument; every step has one"
            raise LifecycleError(msg)
        if self.action is Action.NOTHING and self.because not in REASONS_FOR_DOING_NOTHING:
            # The check that makes `NOTHING` a claim rather than a gap. A free-text reason
            # here would let "not needed" stand in for an argument, which is the sentence
            # every unreached surface has attached to it in the incident afterwards.
            msg = (
                f"the step for {self.surface} says nothing has to happen and names a reason "
                "that is not one of this module's; a surface reached by construction has an "
                "argument written down, or it is a surface nobody thought about"
            )
            raise LifecycleError(msg)


@dataclass(frozen=True)
class Plan:
    """What one transition has to reach, everywhere, once.

    **Every member of `Surface` appears exactly once or this refuses to exist.** A plan that
    could leave a surface out is a plan that leaves one out, and the omission is invisible:
    nothing fails, nobody is told, and the surface is discovered later by whoever is holding
    the incident. Adding a member to `Surface` therefore breaks all three plans until
    somebody decides what each transition does about it, which is the point.

    Rejected: a mapping from surface to action. It carries the same information and it makes
    the missing key a `KeyError` at the call site rather than a refusal at construction, so
    the plan would be wrong for as long as nobody happened to ask about that surface.
    """

    transition: Transition
    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        covered = [step.surface for step in self.steps]
        missing = sorted(surface.value for surface in Surface if surface not in covered)
        if missing:
            msg = (
                f"the {self.transition} plan says nothing about {missing}; a surface left "
                "out of a plan is one nobody decided about, and it looks exactly like a "
                "decision that nothing was needed there"
            )
            raise LifecycleError(msg)
        if len(covered) != len(set(covered)):
            msg = (
                f"the {self.transition} plan names a surface twice; two steps for one "
                "surface are two decisions, and nothing here says which one runs"
            )
            raise LifecycleError(msg)

    def action_at(self, surface: Surface) -> Action:
        """What this transition does at one surface. Total, because the plan is."""
        for step in self.steps:
            if step.surface is surface:
                return step.action
        # Unreachable while `__post_init__` holds, and a refusal rather than a default: a
        # default here would be the one place the totality argument quietly stops being true.
        msg = f"the {self.transition} plan has no step for {surface}"
        raise LifecycleError(msg)

    def reason_at(self, surface: Surface) -> str:
        """The argument recorded for what this transition does at one surface."""
        for step in self.steps:
            if step.surface is surface:
                return step.because
        msg = f"the {self.transition} plan has no step for {surface}"
        raise LifecycleError(msg)


JOIN_PLAN: Final = Plan(
    transition=Transition.JOIN,
    steps=(
        Step(Surface.GRANTS, Action.WRITE, A_JOINER_IS_PROVISIONED_BY_SOMEBODY_ELSE),
        Step(Surface.DEPARTMENT, Action.WRITE, A_CLAIM_PROPOSES_A_DEPARTMENT_AND_NEVER_GRANTS_ONE),
        Step(Surface.SESSIONS, Action.NOTHING, A_JOINER_HOLDS_NOTHING_BEFORE_THEY_ARE_PROVISIONED),
        Step(
            Surface.DELEGATIONS,
            Action.NOTHING,
            A_JOINER_HOLDS_NOTHING_BEFORE_THEY_ARE_PROVISIONED,
        ),
        Step(Surface.AGENTS, Action.NOTHING, A_JOINER_HOLDS_NOTHING_BEFORE_THEY_ARE_PROVISIONED),
        Step(
            Surface.AUTOMATIONS,
            Action.NOTHING,
            A_JOINER_HOLDS_NOTHING_BEFORE_THEY_ARE_PROVISIONED,
        ),
        Step(
            Surface.ANSWER_CACHE, Action.NOTHING, AN_ANSWER_BELONGS_TO_A_REACH_AND_NOT_TO_A_PERSON
        ),
        Step(
            Surface.ENTITLEMENT_CACHE,
            Action.NOTHING,
            THE_VERSION_IS_IN_THE_KEY_SO_NOTHING_IS_INVALIDATED,
        ),
        Step(Surface.MEMORY, Action.NOTHING, A_MEMORY_IS_RECALLED_AT_THE_REACH_IT_WAS_FORMED_AT),
        Step(
            Surface.KNOWLEDGE_INDEX,
            Action.NOTHING,
            THE_PREDICATE_IS_IN_THE_QUERY_SO_THERE_IS_NOTHING_TO_REINDEX,
        ),
        Step(Surface.WELCOME, Action.WRITE, A_STARTER_QUESTION_IS_ANSWERABLE_WITH_THE_STARTER_PACK),
        Step(Surface.AUDIT, Action.WRITE, THE_AUDIT_RECORD_OUTLIVES_EVERY_TRANSITION),
    ),
)

MOVE_PLAN: Final = Plan(
    transition=Transition.MOVE,
    steps=(
        Step(Surface.GRANTS, Action.REPLACE, A_GRANT_CHANGE_IS_ONE_ACT),
        Step(Surface.DEPARTMENT, Action.REPLACE, A_GRANT_CHANGE_IS_ONE_ACT),
        Step(Surface.SESSIONS, Action.NOTHING, A_SESSION_CARRIES_NO_ENTITLEMENT),
        Step(Surface.DELEGATIONS, Action.REVIEW, A_DELEGATION_IS_SUSPENDED_AND_NEVER_NARROWED),
        Step(
            Surface.AGENTS,
            Action.NOTHING,
            A_PERSONAL_AGENT_FOLLOWS_ITS_OWNER_AND_NOT_A_DEPARTMENT,
        ),
        Step(Surface.AUTOMATIONS, Action.NOTHING, AN_AUTOMATION_IS_INTERSECTED_PER_RUN),
        Step(
            Surface.ANSWER_CACHE,
            Action.NOTHING,
            CACHED_ANSWERS_ARE_UNREACHABLE_BY_CONSTRUCTION,
        ),
        Step(
            Surface.ENTITLEMENT_CACHE,
            Action.NOTHING,
            THE_VERSION_IS_IN_THE_KEY_SO_NOTHING_IS_INVALIDATED,
        ),
        Step(Surface.MEMORY, Action.NOTHING, A_MEMORY_IS_RECALLED_AT_THE_REACH_IT_WAS_FORMED_AT),
        Step(
            Surface.KNOWLEDGE_INDEX,
            Action.NOTHING,
            THE_PREDICATE_IS_IN_THE_QUERY_SO_THERE_IS_NOTHING_TO_REINDEX,
        ),
        Step(Surface.WELCOME, Action.NOTHING, ONLY_A_JOINER_GETS_A_WELCOME_PATH),
        Step(Surface.AUDIT, Action.WRITE, THE_AUDIT_RECORD_OUTLIVES_EVERY_TRANSITION),
    ),
)

LEAVE_PLAN: Final = Plan(
    transition=Transition.LEAVE,
    steps=(
        Step(Surface.GRANTS, Action.DELETE, REVOCATION_IS_THE_DELETION_OF_A_GRANT),
        Step(Surface.DEPARTMENT, Action.DELETE, REVOCATION_IS_THE_DELETION_OF_A_GRANT),
        Step(Surface.SESSIONS, Action.END, A_DISABLE_THAT_LEAVES_A_SESSION_LIVE_IS_NOT_A_DISABLE),
        Step(Surface.DELEGATIONS, Action.REVIEW, A_DELEGATION_IS_SUSPENDED_AND_NEVER_NARROWED),
        Step(Surface.AGENTS, Action.END, AN_UNADOPTED_AGENT_STOPS),
        Step(Surface.AUTOMATIONS, Action.END, AN_EMPTY_REACH_IS_NOT_A_STOPPED_AUTOMATION),
        Step(
            Surface.ANSWER_CACHE, Action.NOTHING, AN_ANSWER_BELONGS_TO_A_REACH_AND_NOT_TO_A_PERSON
        ),
        Step(
            Surface.ENTITLEMENT_CACHE,
            Action.NOTHING,
            THE_VERSION_IS_IN_THE_KEY_SO_NOTHING_IS_INVALIDATED,
        ),
        Step(Surface.MEMORY, Action.NOTHING, A_DEPARTURE_IS_NOT_A_DELETION_REQUEST),
        Step(Surface.KNOWLEDGE_INDEX, Action.NOTHING, A_DEPARTURE_IS_NOT_A_DELETION_REQUEST),
        Step(Surface.WELCOME, Action.NOTHING, ONLY_A_JOINER_GETS_A_WELCOME_PATH),
        Step(Surface.AUDIT, Action.WRITE, THE_AUDIT_RECORD_OUTLIVES_EVERY_TRANSITION),
    ),
)


def plan_for(transition: Transition) -> Plan:
    """The plan for one transition. Total over the enum by construction.

    `assert_never` rather than a mapping with a default, for the reason
    `brain.ops.erasure.disposition_of` gives: a fourth transition added without a plan would
    otherwise get whichever plan happens to be written first, and the wrong plan is the one
    that runs.
    """
    match transition:
        case Transition.JOIN:
            return JOIN_PLAN
        case Transition.MOVE:
            return MOVE_PLAN
        case Transition.LEAVE:
            return LEAVE_PLAN
        case _:  # pragma: no cover - unreachable while Transition is exhaustive
            assert_never(transition)


# ============================================================== M26.1 the joiner
#: The role every joiner starts with (M26.1.2).
#:
#: Anchored to `brain.identity.roles.ROLE_SPECS` rather than chosen here: this is the role
#: whose spec says everyone holds it, and it is the only one that does. It also carries no
#: scope requirement, which matters because a scope-required role granted to a joiner would
#: need a scope decided before anybody has reviewed what they do. No role implies a
#: capability, including this one, so the starter role confers no reach at all.
STARTER_ROLE: Final = Role.MEMBER

#: The verbs a starter pack may use. A strict subset of `brain.identity.roles.VERBS`, which
#: is what makes it a restriction rather than a copy of the vocabulary: a joiner reads, and
#: writing, invoking, approving and administering are things somebody decides to give them.
STARTER_VERBS: Final[frozenset[str]] = frozenset({"read"})

#: What a joiner is given on their first day (M26.1.2).
#:
#: `read:knowledge` is `brain.knowledge.search.KNOWLEDGE_READ` and is imported rather than
#: spelled, because `reach_for` returns None without it and a joiner would retrieve nothing
#: at all while every row in the grant table looked correct. The three field capabilities are
#: the ones `brain.agents.catalogue` already asks for on knowledge, so a joiner can reach the
#: agents built against them rather than a set invented here.
STARTER_PACK: Final = CapabilityPack(
    slug="starter",
    label="Starter",
    capabilities=(
        KNOWLEDGE_READ,
        Capability(value="read:knowledge.document"),
        Capability(value="read:knowledge.title"),
        Capability(value="read:knowledge.updated_at"),
    ),
)

#: How many starter questions a welcome path offers (M26.1.4).
WELCOME_QUESTIONS: Final = 3


@dataclass(frozen=True)
class StarterQuestion:
    """One question a new joiner is offered, and what it takes to answer it.

    `capabilities` is the whole safety of the welcome path. A question is offered only when
    the joiner holds every capability on it, in their own department, so the path can never
    offer something that comes back refused or empty. A question with no capabilities would
    be offered to everybody, including somebody who holds nothing, which is why an empty
    tuple is refused here rather than filtered later.

    `template` carries exactly one placeholder and it is the joiner's own department. There
    is no template here that names two departments, and nothing in this module could fill a
    second one, because the builder is handed one name.
    """

    template: str
    capabilities: tuple[Capability, ...]

    def __post_init__(self) -> None:
        if "{department}" not in self.template:
            msg = (
                f"{self.template!r} is not department-scoped; a starter question that does "
                "not name the joiner's own department is a question about the company"
            )
            raise LifecycleError(msg)
        if not self.capabilities:
            msg = (
                f"{self.template!r} names no capability, so it would be offered to somebody "
                "holding nothing and answered for nobody"
            )
            raise LifecycleError(msg)


#: The starter questions, in the order they are offered (M26.1.4).
#:
#: Three, and three different requirements rather than three phrasings of one: dropping a
#: capability from `STARTER_PACK` removes exactly one of them, which is what makes the filter
#: below a filter rather than a formality.
STARTER_QUESTIONS: Final[tuple[StarterQuestion, ...]] = (
    StarterQuestion(
        template="What does the {department} team do here?",
        capabilities=(KNOWLEDGE_READ, Capability(value="read:knowledge.document")),
    ),
    StarterQuestion(
        template="Which {department} documents should I read first?",
        capabilities=(KNOWLEDGE_READ, Capability(value="read:knowledge.title")),
    ),
    StarterQuestion(
        template="What has changed in {department} recently?",
        capabilities=(KNOWLEDGE_READ, Capability(value="read:knowledge.updated_at")),
    ),
)


@dataclass(frozen=True)
class Provisioning:
    """What onboarding one person amounts to: a principal, a role and a pack (M26.1.1).

    Returned rather than written, for the reason `brain.identity.directory.Reconciliation` is
    returned rather than executed: the part that decides is pure and testable without a
    database, and the part that writes holds a transaction and no judgement.

    `department` is the decision and `proposed_department` is what the token claimed. Two
    fields rather than one, so a disagreement between the directory and the person who ran
    the onboarding is visible to whoever looks rather than resolved by whichever was read
    last. See `A_CLAIM_PROPOSES_A_DEPARTMENT_AND_NEVER_GRANTS_ONE`.
    """

    principal: Principal
    role_grant: RoleGrant
    assignment: PackAssignment
    department: str
    #: What `MappedIdentity.primary_department` said, or None when the claim was absent.
    proposed_department: str | None

    def __post_init__(self) -> None:
        if self.role_grant.principal_id != self.principal.id:
            msg = (
                f"the role grant names {self.role_grant.principal_id!r} and the principal is "
                f"{self.principal.id!r}; one comparison rules out provisioning one person "
                "with another person's rows"
            )
            raise LifecycleError(msg)
        if self.role_grant.role is not STARTER_ROLE:
            msg = f"a joiner starts as {STARTER_ROLE}, not {self.role_grant.role}"
            raise LifecycleError(msg)
        if self.assignment.subject != principal_subject(self.principal.id):
            msg = "the pack assignment is for somebody other than the principal being joined"
            raise LifecycleError(msg)
        if self.assignment.pack_slug != STARTER_PACK.slug:
            msg = (
                f"a joiner starts on the {STARTER_PACK.slug!r} pack, not "
                f"{self.assignment.pack_slug!r}"
            )
            raise LifecycleError(msg)
        if not admits_department(self.assignment.scope, self.department):
            msg = (
                f"the starter assignment does not reach {self.department!r}, so the joiner "
                "would hold a pack bound to somewhere they do not work"
            )
            raise LifecycleError(msg)
        if not scope_narrows(self.assignment.scope, department_scope(self.department)):
            # The other direction, and the one that matters: a scope reaching the department
            # is not the same as a scope bounded by it. Without this a starter assignment
            # carrying the unrestricted scope would pass the check above, because an
            # unrestricted scope reaches every department.
            msg = (
                f"the starter assignment is not bounded by {self.department!r}; a pack is "
                "the largest thing anybody assigns in one action and this one reaches "
                "further than the department it was written for"
            )
            raise LifecycleError(msg)

    @property
    def department_disagreement(self) -> str | None:
        """What the claim said, when it disagrees with the department that was assigned.

        None when they agree or when the claim was silent. Reported to an operator and never
        to the joiner: it names one department they are in and one a directory thinks they
        are in, both of which they already know about.
        """
        if self.proposed_department is None or self.proposed_department == self.department:
            return None
        return self.proposed_department


def provision(
    identity: MappedIdentity,
    *,
    principal_id: str,
    employment: Employment,
    department: str,
    granted_by: str,
    reason: str,
    now: datetime,
    not_after: datetime | None = None,
) -> Provisioning:
    """Turn what the identity provider says into a joiner (M26.1.1, M26.1.2, M26.1.3).

    Takes a `MappedIdentity`, which `brain.identity.oidc.map_claims` produces only from
    `VerifiedClaims`, so a joiner cannot be provisioned from something unchecked. What it
    reads off it is the display name, the subject's proposed department and nothing else:
    `identity.groups` is not consulted here, because groups map to roles and that mapping is
    `roles_from_groups`'s, which returns a `frozenset[Role]` and can carry no capability.

    **The department is an argument.** See
    `A_CLAIM_PROPOSES_A_DEPARTMENT_AND_NEVER_GRANTS_ONE`. The claim is recorded on the
    provisioning as a proposal and on the principal as a fact about the person, and the scope
    the joiner is bounded by is built from the argument.

    A partner is refused. `brain.identity.roles.standing_entitlement` gives a partner
    `NoStandingEntitlement` whatever rows exist for them, so a starter pack assigned to one
    would be a row that confers nothing and reads, to everybody who looks at it afterwards,
    as though it conferred something. A partner acts through `open_break_glass`, which is
    time-boxed, separately audited and notified.
    """
    assert_not_a_role(principal_id)
    _aware(now, "now")
    if granted_by == principal_id:
        msg = (
            f"{principal_id!r} cannot be provisioned by {granted_by!r}; "
            f"{A_JOINER_IS_PROVISIONED_BY_SOMEBODY_ELSE}"
        )
        raise LifecycleError(msg)
    if employment is Employment.PARTNER:
        msg = (
            "a partner holds no standing entitlement, so a starter pack assigned to one "
            "would confer nothing and read as though it conferred something; a partner acts "
            "through a break-glass session"
        )
        raise LifecycleError(msg)
    if not SLUG_RE.match(department):
        msg = (
            f"{department!r} is not a department slug, so no scope can be built from it and "
            "the joiner would be bound to nothing"
        )
        raise LifecycleError(msg)

    principal = Principal(
        id=principal_id,
        kind=kind_for(employment),
        employment=employment,
        display_name=identity.display_name or principal_id,
        primary_department=department,
        not_after=not_after,
    )
    role_grant = RoleGrant(
        principal_id=principal_id,
        role=STARTER_ROLE,
        granted_by=granted_by,
        reason=reason,
        granted_at=now,
        not_after=not_after,
    )
    assignment = PackAssignment(
        subject=principal_subject(principal_id),
        pack_slug=STARTER_PACK.slug,
        scope=department_scope(department),
        granted_by=granted_by,
        reason=reason,
        granted_at=now,
        not_after=not_after,
    )
    return Provisioning(
        principal=principal,
        role_grant=role_grant,
        assignment=assignment,
        department=department,
        proposed_department=identity.primary_department,
    )


def kind_for(employment: Employment) -> PrincipalKind:
    """Which kind of principal an employment implies.

    A service engagement is a service principal and everything else is a human. Written as a
    function rather than inlined because getting it wrong is silent: a human recorded as
    `SERVICE` is exempt from nothing in particular today and from whatever the kind comes to
    mean later, and nothing about the record says it was a mistake.
    """
    return PrincipalKind.SERVICE if employment is Employment.SERVICE else PrincipalKind.HUMAN


def starter_entitlement(
    provisioning: Provisioning, *, now: datetime | None = None
) -> EntitlementSet:
    """What a joiner can actually reach on their first day (M26.1.2).

    Resolved through `brain.identity.packs.resolve_entitlement` rather than by expanding the
    pack here, because `expand` is the only route from a pack to a grant and a second one
    would be a second definition of what a pack means. The role grant is deliberately not
    passed: `resolve_entitlement` has no parameter for one, which is M1.3.5 written as a
    signature, and a joiner's reach comes from their pack alone.
    """
    resolved = resolve_entitlement(
        provisioning.principal,
        assignments=(provisioning.assignment,),
        packs={STARTER_PACK.slug: STARTER_PACK},
        now=now,
    )
    if isinstance(resolved, NoStandingEntitlement):
        # Unreachable while `provision` refuses a partner, and a refusal rather than a
        # convenient empty set: an empty `EntitlementSet` type-checks everywhere a real one
        # does, so returning one here would hide the day somebody widens that refusal.
        msg = f"{provisioning.principal.id!r} holds no standing entitlement to start from"
        raise LifecycleError(msg)
    return resolved


def welcome_questions(
    entitlement: EntitlementSet, department: str, *, now: datetime | None = None
) -> tuple[str, ...]:
    """The starter questions this joiner may actually ask, in their own department (M26.1.4).

    At most `WELCOME_QUESTIONS`, and a question is kept only when the reader holds every
    capability it names *and* the scope they hold it in admits their department. Holding the
    capability company-wide is enough, because an unrestricted scope matches every row; a
    scope naming a different department is not.

    A scope carrying a clause about a field the department row does not have makes the
    question fall out, which is a false negative and the safe direction: the joiner is
    offered one question fewer, never one they cannot ask.

    Nothing here says how many were dropped, and nothing anywhere reports it. A count of
    withheld questions is the difference between what somebody may ask and what exists,
    which is the subtraction this system refuses everywhere.
    """
    if not SLUG_RE.match(department):
        msg = f"{department!r} is not a department slug; no question can be scoped to it"
        raise LifecycleError(msg)

    place: dict[str, object] = {"department": department}
    offered: list[str] = []
    for question in STARTER_QUESTIONS:
        reachable = True
        for capability in question.capabilities:
            scope = entitlement.scope_for(capability, now)
            if scope is None or not scope.matches(dict(place)):
                reachable = False
                break
        if reachable:
            offered.append(question.template.format(department=department))
    return tuple(offered[:WELCOME_QUESTIONS])


#: Annotations that would let a welcome builder be handed more than one department. Matched
#: on the annotation rather than the body, for the reason
#: `brain.identity.oidc.assert_no_capability_from_claims` matches there: a body check is
#: removable by whoever adds the feature that needs it, and a signature change is a diff with
#: a reviewer on it.
COLLECTION_OF_NAMES = (
    r"(Sequence|Iterable|Collection|AbstractSet|list|set|frozenset|tuple)\[[^]]*str"
)

_COLLECTION_OF_NAMES_RE = re.compile(COLLECTION_OF_NAMES)


def assert_welcome_cannot_enumerate_departments(fn: Callable[..., object]) -> None:
    """Refuse a welcome builder that could be handed a list of department names (M26.1.4).

    DENIED and ABSENT have to stay indistinguishable, and the welcome path is the easiest
    place in the system to break that, because the obvious implementation walks the
    department registry and offers a question per department the joiner can reach. On their
    first day, that tells a new joiner exactly how many departments exist and which ones are
    not theirs, by subtraction, before they have asked anything.

    So the builder is handed one department name and there is nowhere for a registry to go.
    A check inside the function would be removable by whoever adds the feature; a parameter
    that does not exist has to be added first. Same mechanism as
    `brain.identity.packs.assert_no_role_in_resolution` and
    `brain.identity.directory.assert_reconciler_cannot_reach_hand_made_grants`.

    `eval_str=True` so the annotations are real objects rather than the strings
    `from __future__ import annotations` leaves behind.
    """
    signature = inspect.signature(fn, eval_str=True)
    offending = sorted(
        name
        for name, parameter in signature.parameters.items()
        if _COLLECTION_OF_NAMES_RE.search(str(parameter.annotation))
    )
    if offending:
        msg = (
            f"{fn.__name__} can be handed {offending}, which is a list of department names "
            "in everything but the annotation; a welcome path that can enumerate "
            "departments tells a joiner which ones exist and are not theirs"
        )
        raise LifecycleError(msg)


# ============================================================== M26.2 the mover
@dataclass(frozen=True)
class Move:
    """One person's reach before and after a move.

    Both sides are the same principal, checked here. A move assembled from two different
    people's sets is the catastrophic failure and it is one comparison to rule out, in the
    shape `brain.gate.resolve` compares a loaded set's principal against the one it asked for
    and `brain.identity.sessions.reach_for` compares an account's owner.

    `NoStandingEntitlement` is not accepted on either side and there is no field here it fits
    into. A partner has no standing reach to move: what they hold is a break-glass session,
    which is bounded, separately audited and ends on its own.
    """

    principal_id: str
    before: EntitlementSet
    after: EntitlementSet

    def __post_init__(self) -> None:
        for side, entitlement in (("before", self.before), ("after", self.after)):
            if entitlement.principal_id != self.principal_id:
                msg = (
                    f"the {side} entitlement belongs to {entitlement.principal_id!r}, not "
                    f"{self.principal_id!r}; a move built from two people's sets would "
                    "compare one person's old reach with another's new one"
                )
                raise LifecycleError(msg)


def reach_changed(move: Move) -> bool:
    """Whether this move changed what the person may see (M26.2.4).

    Compared on `ent_hash` rather than on the grant tuples, because the hash is what every
    cache key downstream is built from: two sets that hash the same *are* the same reach as
    far as anything that caches is concerned, whatever order their rows arrived in.

    A move that does not change the hash is a real and ordinary event. Somebody who holds a
    company-wide grant and changes desk reaches exactly what they reached yesterday, and
    their cached answers are still correct for them. Reporting that as a change would make
    the interesting case indistinguishable from the common one.
    """
    return move.before.ent_hash() != move.after.ent_hash()


def entitlement_keys(move: Move, *, before_version: int, after_version: int) -> tuple[str, str]:
    """The resolver cache keys either side of a move (M26.2.1).

    Built with `brain.gate.resolve.cache_key` and not restated, so what this proves is what
    the resolver actually does. The versions are arguments because the counter is moved by a
    database trigger and nothing in the application writes it; passing the two the caller
    read is the honest shape, and inventing an increment here would be this module asserting
    a bump it cannot make.
    """
    if after_version < before_version:
        # Monotonic, matching the check constraint on `gate.grants_version`. A counter that
        # went backwards would hand out a key that was already used under a wider
        # entitlement, and whatever is cached under it is readable again.
        msg = (
            f"the grants version went from {before_version} to {after_version}; a version "
            "that moves backwards re-opens every key minted under the earlier one"
        )
        raise LifecycleError(msg)
    return (
        entitlement_cache_key(move.principal_id, before_version),
        entitlement_cache_key(move.principal_id, after_version),
    )


def answer_keys(
    move: Move,
    *,
    question: str,
    agent_config_hash: str,
    policy_epoch: int,
    source_epochs: Mapping[str, int],
    sources: frozenset[str] | None = None,
) -> tuple[str, str]:
    """The answer cache keys this person computes either side of a move (M26.2.4).

    Built with `brain.gate.cache_key.key_for`, which is the builder the gate uses, so the
    keys compared here are the keys that would be looked up. A second builder written for a
    test would prove that the second builder changes, which is not the claim.

    A volatile question raises `NotCacheableError` out of the builder and that is left to
    propagate: an answer that is never stored cannot be reached from either side of a move,
    so the question this function asks does not arise for one.
    """
    return (
        answer_cache_key(
            question,
            move.before.ent_hash(),
            agent_config_hash,
            policy_epoch,
            source_epochs,
            sources,
        ),
        answer_cache_key(
            question,
            move.after.ent_hash(),
            agent_config_hash,
            policy_epoch,
            source_epochs,
            sources,
        ),
    )


def old_answers_are_unreachable(
    move: Move,
    *,
    question: str,
    agent_config_hash: str,
    policy_epoch: int,
    source_epochs: Mapping[str, int],
    sources: frozenset[str] | None = None,
) -> bool:
    """Whether the mover can still construct the key their old answers sit under (M26.2.4).

    True when the two keys differ, which is exactly when their reach changed. There is no
    purge, no sweep and no invalidation call anywhere in this module, and this function does
    not perform one: it reports a property of the key builder. See
    `CACHED_ANSWERS_ARE_UNREACHABLE_BY_CONSTRUCTION`.

    False is the correct answer for somebody whose reach did not change, and it is not a
    failure. Their old answers are still answers to their question at their reach, and
    refusing to serve them would mean recomputing an identical answer because somebody
    changed desk.
    """
    before, after = answer_keys(
        move,
        question=question,
        agent_config_hash=agent_config_hash,
        policy_epoch=policy_epoch,
        source_epochs=source_epochs,
        sources=sources,
    )
    return before != after


def agents_following(records: Iterable[AgentRecord], *, principal_id: str) -> frozenset[str]:
    """The agents that move with this person rather than with their department (M26.2.2).

    Audience only, and every state, exactly as `brain.agents.model.visible_agent_ids` is: an
    agent this person disabled last month is still theirs and still follows them, and
    filtering by state here would produce a list that disagreed with the visibility question
    it is about.

    A frozenset of ids and nothing else, with nowhere for a count of what was left out. An
    agent belonging to a department the person is leaving and an agent that does not exist
    are one answer, which is `A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER`.
    """
    return frozenset(
        record.agent_id
        for record in records
        if record.audience.level is Visibility.PERSONAL and record.audience.owner_id == principal_id
    )


class ReconfirmReason(enum.StrEnum):
    """Why a delegation stopped standing. Three, and each names a different failure.

    A closed vocabulary rather than free text, for the reason
    `brain.identity.roles.BreakGlassReason` is one: it is recordable through
    `redact_details` intact, and "how many delegations lapsed because somebody moved" is a
    query rather than a reading exercise.
    """

    #: The delegator holds nothing of that role any more.
    DELEGATOR_NO_LONGER_HOLDS_THE_ROLE = "delegator_no_longer_holds_the_role"
    #: The delegator holds it only as somebody else's deputy, and deputies are depth one.
    DELEGATOR_HOLDS_IT_ONLY_AS_A_DEPUTY = "delegator_holds_it_only_as_a_deputy"
    #: The delegator's scope moved, and the delegation is no longer inside it.
    DELEGATOR_SCOPE_NO_LONGER_COVERS_IT = "delegator_scope_no_longer_covers_it"


@dataclass(frozen=True)
class Reconfirmation:
    """A delegation that stopped standing, and the person who has to decide about it.

    **This is what makes narrowing structurally impossible rather than merely absent.** There
    is no field here that could hold a modified grant: `delegation` is the row as it was
    written, and the only other fields are who must decide and why. Something that wanted to
    hand back a narrower delegation would have to add a field to this type, in a module whose
    docstring argues against it, rather than editing a line nobody reads.

    Rejected: carrying the narrower scope alongside, as a suggestion. A suggestion in the
    same object as the decision is the value the console renders, and a delegator confirming
    what is on the screen has agreed to something nobody asked them about.
    """

    delegation: RoleGrant
    delegator_id: str
    because: ReconfirmReason

    def __post_init__(self) -> None:
        if self.delegation.deputy_of is None:
            msg = (
                f"{self.delegation.principal_id!r} holds {self.delegation.role} in their own "
                "right; a standing grant is not a delegation and suspending one here would "
                "take away a role nobody delegated"
            )
            raise LifecycleError(msg)
        if self.delegation.deputy_of != self.delegator_id:
            msg = (
                f"the delegation covers {self.delegation.deputy_of!r} and the reconfirmation "
                f"names {self.delegator_id!r}; the person asked to confirm must be the "
                "person the delegation was made against"
            )
            raise LifecycleError(msg)


@dataclass(frozen=True)
class DelegationReview:
    """What one re-evaluation found: three lists, and every input in exactly one of them.

    `expired` is separate from `to_reconfirm` on purpose. A delegation that ran out on the
    date somebody chose needs no decision from anybody, and putting it in the queue would ask
    a delegator to re-open an appointment that ended as intended. Folding the two together
    would also make "how many delegations did this move suspend" unanswerable, because the
    number would move every time an unrelated appointment expired.
    """

    #: Unchanged, and the same objects that were handed in.
    standing: tuple[RoleGrant, ...]
    #: Stopped standing. Somebody has to decide.
    to_reconfirm: tuple[Reconfirmation, ...]
    #: Ran out on their own. Nothing to decide.
    expired: tuple[RoleGrant, ...]


def _reconfirm_reason(
    delegation: RoleGrant, delegator_grants: Sequence[RoleGrant], now: datetime
) -> ReconfirmReason | None:
    """Why this delegation stopped standing, or None when it still does.

    The scope test is `brain.core.scope_sql.scope_narrows` and not a comparison written here.
    A delegator whose scope *widened* still covers the delegation, and a hand-written
    equality check would suspend every delegation held by anybody who was promoted, which is
    a stream of noise that teaches everybody to confirm without reading.
    """
    delegator = delegation.deputy_of
    held = [
        grant
        for grant in delegator_grants
        if grant.principal_id == delegator
        and grant.role is delegation.role
        and grant.is_active(now)
    ]
    if not held:
        return ReconfirmReason.DELEGATOR_NO_LONGER_HOLDS_THE_ROLE
    standing = [grant for grant in held if not grant.is_deputy]
    if not standing:
        # `appoint_deputy` refuses this at the point of appointment and `check_deputy_depth`
        # reports it over the table; here it is the state a move can create, by leaving
        # somebody holding as a deputy what they used to hold in their own right.
        return ReconfirmReason.DELEGATOR_HOLDS_IT_ONLY_AS_A_DEPUTY
    if delegation.scope is not None and not any(
        grant.scope is not None and scope_narrows(delegation.scope, grant.scope)
        for grant in standing
    ):
        return ReconfirmReason.DELEGATOR_SCOPE_NO_LONGER_COVERS_IT
    return None


def reevaluate_delegations(
    delegations: Sequence[RoleGrant],
    *,
    delegator_grants: Sequence[RoleGrant],
    now: datetime,
) -> DelegationReview:
    """Re-evaluate every delegation against what its delegator holds now (M26.2.3).

    **Suspension is the only outcome and there is no narrowing anywhere in it.** A delegation
    the delegator can no longer sustain comes back as a `Reconfirmation`, which carries the
    row unchanged and the person who must decide. See
    `A_DELEGATION_IS_SUSPENDED_AND_NEVER_NARROWED`.

    Every grant handed in comes back, in exactly one of the three lists, and the check is by
    identity rather than by equality: a future edit that rebuilt a grant with a tighter scope
    would produce an equal-looking object and a different one, and it is the different one
    this refuses. That is the argument `brain.identity.directory.reconcile` makes about
    `to_delete` being a set difference, enforced here as a postcondition because this
    function is a loop with conditions in it rather than arithmetic.

    A standing grant handed in as a delegation is refused rather than passed through. It is
    the way this function would be misused, and the damage is specific: somebody's own role
    would be suspended because the person they happen to cover for moved.
    """
    _aware(now, "now")
    standing: list[RoleGrant] = []
    to_reconfirm: list[Reconfirmation] = []
    expired: list[RoleGrant] = []

    for delegation in delegations:
        delegator = delegation.deputy_of
        if delegator is None:
            msg = (
                f"{delegation.principal_id!r} holds {delegation.role} in their own right; a "
                "standing grant is not a delegation, and re-evaluating one here would "
                "suspend a role nobody delegated"
            )
            raise LifecycleError(msg)
        if not delegation.is_active(now):
            expired.append(delegation)
            continue
        because = _reconfirm_reason(delegation, delegator_grants, now)
        if because is None:
            standing.append(delegation)
            continue
        to_reconfirm.append(
            Reconfirmation(delegation=delegation, delegator_id=delegator, because=because)
        )

    returned = [*standing, *(item.delegation for item in to_reconfirm), *expired]
    if len(returned) != len(delegations) or not all(
        any(candidate is original for candidate in returned) for original in delegations
    ):
        msg = (
            "a re-evaluation handed back a delegation it was not given; "
            f"{A_DELEGATION_IS_SUSPENDED_AND_NEVER_NARROWED}"
        )
        raise LifecycleError(msg)

    return DelegationReview(
        standing=tuple(standing), to_reconfirm=tuple(to_reconfirm), expired=tuple(expired)
    )


def replayable_after(
    move: Move,
    formations: Sequence[tuple[Formation, float]],
    *,
    now: datetime,
    where: Mapping[str, object] | None = None,
) -> tuple[Recollection, ...]:
    """What the mover may still be told, computed from their new reach alone (M26.2.5).

    Delegates to `brain.memory.formation.recallable`, which is the rule, and adds nothing. A
    memory is recalled at the reach it was formed at, checked on every read, so a memory
    tagged with a capability set the mover no longer holds simply stops coming back and
    nothing anywhere is marked, moved or deleted. There are two implementations of
    `intersect` in this repository and a third is forbidden; the same applies to this.

    Deliberately not a diff. A function returning what the mover *lost* would be a count of
    things withheld, which is the subtraction this system refuses, and it would be the one
    surface in the mover flow that reported it.
    """
    return recallable(formations, move.after, now=now, where=where)


def knowledge_reach_after(
    move: Move, *, departments: Sequence[str], now: datetime | None = None
) -> Reach | None:
    """What the mover retrieves from the document plane now (M26.2.6).

    Delegates to `brain.knowledge.search.reach_for`, which intersects the caller's grant
    scope against the department registry. Nothing about the index is touched and nothing
    could be: this returns a `Reach`, which is what `reach_predicate` conjoins into the next
    query, and there is no return value here that a writer could act on.

    None means the mover holds no read of the knowledge plane at all, which is not the
    unrestricted reach and cannot be confused with it: `Reach` has no constructor that means
    everything.
    """
    return reach_for(move.after, departments=departments, now=now)


# ============================================================== M26.3 the leaver
@dataclass(frozen=True)
class Disablement:
    """Evidence that a leaver was disabled: rows gone, sessions over, principal bounded.

    Holding one of these means all three happened. The sessions were ended and the floor
    raised before this object existed, because `disable` does that itself rather than
    describing it; the rows are the ones that remain after the deletions, checked here
    against the real resolver; and the principal carried is the bounded one.

    Rejected: a plan describing the disable, for a caller to apply. Every other transition in
    this module returns one, and this is the one where the caller who does not apply it
    leaves somebody signed in with everything they had. The shape is
    `brain.identity.roles.open_break_glass`'s: both, or neither.
    """

    principal: Principal
    at: datetime
    #: What is left after the leaver's own rows were deleted. Team grants stay: they belong
    #: to the team, and the membership is what stopped reaching this person.
    remaining_grants: tuple[SubjectGrant, ...]
    remaining_assignments: tuple[PackAssignment, ...]
    remaining_memberships: tuple[TeamMembership, ...]
    ended_sessions: tuple[Session, ...]
    #: The logout floor. Every token issued at or before it is refused from now on.
    not_before: datetime

    def __post_init__(self) -> None:
        _aware(self.at, "at")
        _aware(self.not_before, "not_before")
        if self.principal.is_active(self.at):
            msg = (
                f"{self.principal.id!r} is still active at {self.at.isoformat()}; ending the "
                "sessions without bounding the principal refuses the tokens already issued "
                "and admits the next one"
            )
            raise LifecycleError(msg)
        if self.not_before < self.at:
            msg = (
                f"the logout floor is {self.not_before.isoformat()} and the disable is "
                f"{self.at.isoformat()}; a floor that predates the disable admits a token "
                "minted between the two"
            )
            raise LifecycleError(msg)


def disable(
    principal: Principal,
    *,
    registry: SessionRegistry,
    now: datetime,
    grants: Sequence[SubjectGrant] = (),
    assignments: Sequence[PackAssignment] = (),
    packs: Mapping[str, CapabilityPack] | None = None,
    memberships: Sequence[TeamMembership] = (),
) -> Disablement:
    """Disable a leaver: delete their grants, end their sessions, bound them (M26.3.1).

    Three acts, one call, and no argument that skips any of them. See
    `A_DISABLE_THAT_LEAVES_A_SESSION_LIVE_IS_NOT_A_DISABLE`.

    **Revocation is deletion.** `brain.identity.packs.revoke` removes the rows and there is
    no flag written anywhere; this module adds no deny list, no tombstone and no suspension
    column, and `subtractive_state` refuses one across the package.

    **The team memberships go and the team's grants stay.** A grant with a `TeamSubject`
    belongs to the team, so deleting it would take access away from everybody else in it,
    and leaving the membership would leave the leaver reaching everything the team reaches.
    This is the one part of the deletion that is easy to miss, because a subject filter over
    the grant rows looks complete and is not: `resolve_entitlement` reaches a person through
    `subject_reaches`, which walks memberships.

    **The postcondition is resolved rather than asserted.** What comes back is run through
    the real `resolve_entitlement`, and a leaver who still resolves to a grant is a refusal.
    Checking the subjects instead would pass for exactly the team case above.

    That postcondition cannot fire today and is kept anyway, which is worth saying plainly so
    nobody reads it as a branch under test. `resolve_entitlement` reaches a principal through
    `subject_reaches` and through nothing else, and that is two routes: a `PrincipalSubject`
    matching the id, deleted above, and a `TeamSubject` reached through a membership, also
    deleted above. So no input to this function can leave a grant standing, and removing this
    check changes no behaviour that a test can observe. What it is for is the third route:
    the day `resolve_entitlement` gains one, this fails loudly here instead of silently
    leaving a leaver with access, which is the failure the whole leaf is about.

    Sessions are ended through `end_all_for`, which raises the floor whether or not this
    process ever saw a session, so a disable that runs on a replica holding nothing still
    refuses the token already in somebody's hand.
    """
    _aware(now, "now")
    subject = principal_subject(principal.id)
    remaining_grants = revoke(tuple(grants), where=lambda row: row.subject == subject)
    remaining_assignments = revoke(tuple(assignments), where=lambda row: row.subject == subject)
    remaining_memberships = revoke(
        tuple(memberships), where=lambda row: row.principal_id == principal.id
    )

    bound = now if principal.not_after is None else min(principal.not_after, now)
    # Rebuilt through the constructor rather than `model_copy`, which skips validation
    # entirely; this is the one path that ever writes `not_after` onto a leaver, so the
    # validators refusing a naive timestamp would be dead code that still passed its test.
    fields = {name: getattr(principal, name) for name in type(principal).model_fields}
    bounded = Principal.model_validate({**fields, "not_after": bound})

    resolved = resolve_entitlement(
        bounded,
        grants=remaining_grants,
        assignments=remaining_assignments,
        packs=packs,
        memberships=remaining_memberships,
        now=now,
    )
    if isinstance(resolved, EntitlementSet) and resolved.grants:
        msg = (
            f"{principal.id!r} still resolves to {len(resolved.grants)} grant(s) after their "
            "own rows were deleted; something reaches them that a subject filter does not, "
            "which is what a team membership does"
        )
        raise LifecycleError(msg)

    ended = registry.end_all_for(principal.id, now)
    floor = registry.not_before_for(principal.id)
    if floor is None:
        # Unreachable while `end_all_for` raises the floor unconditionally, and a refusal
        # rather than a default: the floor is the only thing that refuses a token this
        # process never saw, so a `Disablement` without one would be evidence of a disable
        # that did not happen.
        msg = (
            f"no logout floor was recorded for {principal.id!r}; without one a token already "
            "issued is admitted for as long as it lives"
        )
        raise LifecycleError(msg)

    return Disablement(
        principal=bounded,
        at=now,
        remaining_grants=remaining_grants,
        remaining_assignments=remaining_assignments,
        remaining_memberships=remaining_memberships,
        ended_sessions=ended,
        not_before=floor,
    )


@dataclass(frozen=True)
class Adoption:
    """One agent waiting for a steward, already stopped.

    `record` is the disabled record, not the live one. A queue of agents that were flagged
    and left running is a queue whose entries do damage while they wait, and the wait is
    however long it takes somebody to read the offboarding report. See
    `AN_UNADOPTED_AGENT_STOPS`.
    """

    agent_id: str
    record: AgentRecord
    former_owner_id: str

    def __post_init__(self) -> None:
        if self.record.disabled_at is None:
            msg = (
                f"{self.agent_id!r} is queued for adoption and still selectable; an agent "
                "waiting for a steward is an agent nobody answers for while it runs"
            )
            raise LifecycleError(msg)


def agents_for_adoption(
    records: Iterable[AgentRecord], *, departing: frozenset[str], now: datetime
) -> tuple[Adoption, ...]:
    """Stop the departing people's agents and queue them for a steward (M26.3.2).

    The list comes from `brain.agents.lifecycle.agents_needing_transfer`, which is keyed on
    the ids the caller named and never on a scan of who owns what: a function that read the
    estate and reported every owner would be an org chart with agent counts on it.

    Each record is disabled through `brain.agents.lifecycle.disable`, which is reversible and
    keeps the first timestamp on a retry, and never archived, which is terminal.

    In id order, so an offboarding runbook processes the same list the same way twice.
    """
    _aware(now, "now")
    by_id = {record.agent_id: record for record in records}
    return tuple(
        Adoption(
            agent_id=agent_id,
            record=stop_agent(by_id[agent_id], now=now),
            former_owner_id=by_id[agent_id].audience.owner_id,
        )
        for agent_id in agents_needing_transfer(by_id.values(), departing=departing)
    )


def adopt(adoption: Adoption, *, to_owner: Principal, now: datetime) -> AgentRecord:
    """Give a stopped agent a steward and start it again (M26.3.2).

    Transfer first, then enable, and the order is the safety. `transfer_ownership` is where
    the refusals live: it refuses an archived record, a transfer to the current owner, and a
    new steward who is not active at `now`, which is the check that stops one leaver's agents
    being handed to another leaver on the same offboarding run. Enabling first would leave an
    agent running with no steward for exactly as long as it takes the transfer to fail.

    The order is a statement about the writes a caller makes from these records and not a
    behaviour this module can be caught changing: both functions return new frozen records
    and neither mutates its argument, so swapping them raises the same refusal and leaves the
    same nothing behind. It is written in the safe order so that a caller who applies each
    result as it arrives cannot produce the running-and-unowned state.
    """
    return start_agent(transfer_ownership(adoption.record, to_owner=to_owner, now=now))


@dataclass(frozen=True)
class Automation:
    """Scheduled work running under somebody's name. The type only; no table is written here.

    Two fields, and no ceiling on it. What a flow may reach is decided per run by
    `brain.ops.automation.flow_reach`, and a ceiling stored beside the owner here would be a
    second copy of it that reads as authority. What this type is for is answering "whose work
    stops when this person goes", which is a question about ownership and nothing else.
    """

    automation_id: str
    owner_principal_id: str

    def __post_init__(self) -> None:
        if not self.automation_id.strip():
            msg = "an automation needs an id; one that names nothing cannot be stopped"
            raise LifecycleError(msg)
        if not self.owner_principal_id.strip():
            msg = (
                "an automation needs an owner; one owned by nobody is one nobody reviews, "
                "and the review is the only thing that ever stops it"
            )
            raise LifecycleError(msg)
        assert_not_a_role(self.owner_principal_id)


def automations_to_stop(
    automations: Iterable[Automation], *, departing: frozenset[str]
) -> tuple[str, ...]:
    """The automations that stop when these people go (M26.3.3).

    Keyed on ownership and on nothing else. It does not consult what a flow reaches, and
    that is deliberate: see `AN_EMPTY_REACH_IS_NOT_A_STOPPED_AUTOMATION`. A flow owned by a
    leaver already reaches nothing, and a flow that runs on schedule and quietly produces
    nothing looks healthy on every screen there is.

    `departing` is who the caller named. Sorted ids, with no count of anything omitted.
    """
    return tuple(
        sorted(
            automation.automation_id
            for automation in automations
            if automation.owner_principal_id in departing
        )
    )


def automation_still_reaches_anything(
    *, flow_ceiling: EntitlementSet, owner: EntitlementSet
) -> bool:
    """Whether a flow owned by this person could still touch a row (M26.3.3).

    Computed with `brain.ops.automation.flow_reach`, which is `E(caller) intersect
    flow_ceiling` and the same intersection every agent run uses. Reported and never relied
    on: `automations_to_stop` does not call this, and a leaver's flows are stopped whatever
    it says. It is here so an operator can see that a flow left running would have done
    nothing, which is the difference between a stopped automation and a silent one.
    """
    return bool(flow_reach(owner, flow_ceiling).grants)


def departure_disposition(store: Store) -> Disposition:
    """What a departure does in one store (M26.3.4, M26.3.5).

    The vocabulary is `brain.ops.erasure.Disposition` rather than a second one, and the
    answers deliberately differ from `disposition_of`, which answers for a deletion request.
    A departure is not one. See `A_DEPARTURE_IS_NOT_A_DELETION_REQUEST`.

    Two of the differences are the leaves. `KNOWLEDGE` and `MEMORY` are erased by a deletion
    request and retained by a departure: personal items stay at personal visibility with the
    leaver as owner, which makes them reachable by nobody without an index write and without
    promoting anything, and memories stay because recall is decided by the reader's reach.
    `CACHE` and `INDEX` are purged by a deletion request and retained by a departure, which
    is the same construction the mover rests on: there is nothing to purge, because there is
    nothing anybody can reach.

    `ROWS` is the one store a departure erases, and that is the whole revocation: the grants
    and the sessions. The identity row itself stays, because the ledger refers to the person
    by id and an audit entry naming a row that no longer exists is a trace nobody can read.

    `assert_never` rather than a mapping with a default, exactly as `disposition_of` does: a
    store added without a decision about what a departure does in it would otherwise get
    whichever answer is written first.
    """
    match store:
        case Store.ROWS:
            return Disposition.ERASE
        case (
            Store.AGENTS
            | Store.OPERATIONS
            | Store.CONVERSATION
            | Store.PROJECTION
            | Store.KNOWLEDGE
            | Store.MEMORY
            | Store.LEDGER
            | Store.TRACE
            | Store.PAYLOAD
            | Store.RECORDING
            | Store.ATTACHMENT
            | Store.EXPORT
            | Store.BACKUP
            | Store.CACHE
            | Store.INDEX
            | Store.AUDIT
        ):
            return Disposition.RETAINED
        case _:  # pragma: no cover - unreachable while Store is exhaustive
            assert_never(store)
