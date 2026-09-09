"""The scheduled roster read, and the dry run that is the only way to see it before it runs.

A roster source is read on a schedule and nobody watches a schedule. So the product of this
module is not the sync, it is **the diff**: the list of who would be added and who would be
removed, produced from the same inputs the real run uses, by the same code, writing nothing.
A dry run assembled by a different code path is a rehearsal of a different performance.

**Nothing here writes.** `brain.identity.directory.reconcile` is what a caller executes and it
is called here to compute the answer rather than reimplemented, so a role assertion this dry
run shows is the exact assertion the applying step would act on. That is the split
`Reconciliation` already argues for: the function that decides is pure and testable without a
database, and the function that writes holds a transaction and no judgement.

**Three separate things can stop a removal, and they are not the same thing.**

*The source did not promise completeness.* Absence is not deletion, and an export that timed
out, a filter somebody narrowed and a paging bug all produce a shorter list. This is
`A_SOURCE_THAT_HALF_ANSWERED_LOOKS_EXACTLY_LIKE_A_COMPANY_THAT_HALVED` and it is asked of the
roster with `may_remove` rather than restated here.

*Nobody has ever seen what this source returns.* Completeness is a promise about the source's
own answer and says nothing about whether the source was pointed at the right place. A
Workspace connector aimed at one organisational unit is complete and correct about that unit
and wrong about the company, and its first run would propose removing everybody outside it.
So **a source's first run may add and may never remove**, whatever it promised, and the second
run is the one that can, because by then somebody has read a dry run.
See `THE_FIRST_RUN_OF_A_SOURCE_HAS_NOTHING_TO_BE_WRONG_AGAINST`.

*The source said this person has left.* That is the one removal that survives both of the
above, because it is the source stating a fact rather than failing to mention one, and it is
reported separately for exactly that reason.

**A dry run is run against a configuration that might be wrong, so it reports refusals rather
than raising them.** `assertions_from` refuses a source wired to role rules it may not assert,
deliberately and at configuration time, and configuration time is precisely when somebody is
looking at a dry run. Letting that exception escape would mean the one tool for finding the
misconfiguration is the one tool that cannot survive it. So it is caught, named, and the run
is marked as not safe to apply.
See `A_DRY_RUN_THAT_CANNOT_SURVIVE_A_BAD_CONFIGURATION_IS_NO_USE_AT_ALL`.

**The schedule is a timestamp and not a state.** There is no `SCHEDULED` member anywhere here
and no state machine; there is a last-applied time and an interval, and `is_due` is a
comparison. That is `brain.ops.jobs.SCHEDULING_IS_A_TIMESTAMP_AND_NOT_A_STATE`, which is
named rather than imported: nothing here reaches into `brain.ops`, and one string constant is
not worth being the first exception. That sentence used to read "this package imports nothing
outside itself and `brain.core`", which was never true of the package: `brain.identity.roles`
has imported `brain.audit.ledger` for as long as it has existed. It is corrected rather than
worked around, because the half of this module described below imports the audit package on
purpose and a false claim of purity is how a real import gets argued about in the wrong terms.

**A dry run does not touch the schedule.** It changes nothing, so recording it as a run would
push the next real sync out by a full interval every time somebody looked. There is no
parameter here that a dry run fits into: `is_due` takes the last time a sync was *applied*.

---

**The second half of this module writes a department head's audit reach against people, and
it is here because the roster is the only thing that knows who those people are.** That is
item 48 in `docs/needs-rupash.md`, decided as Option A on 2026-09-09, and the finding behind
it was re-run before a line of this was written: a reader holding every audit capability
scoped to `department = maintenance` sees **nought** rows of a nine-entry ledger, and the same
reader scoped to `actor_id IN (two people)` sees six, being those two people's and nobody
else's. Not filtered, empty. See `A_DEPARTMENT_SCOPED_AUDIT_GRANT_MATCHES_NO_ENTRY`.

**Two costs, and the second is the design question.** The reach goes stale between a transfer
and the next sync, which is bounded by `SYNC_INTERVAL` and stated in `THE_STALENESS_WINDOW`;
and an audit permission is per subject kind, eight in all, so somebody has to say which of the
eight a head holds. `AUDIT_KIND_DECISIONS` is that answer with an argument beside every one of
the eight, and `HEAD_AUDIT_SUBJECT_KINDS` is derived from it rather than written twice, so the
list is data a reviewer reads and never a branch they have to trace.

**Rejected: `read:audit.*` as one grant instead of a chosen set.** It is one row rather than
four and it hands a head the merge history of every business record their people touched, the
id of every artefact they published and every break-glass session they opened. The reason the
per-kind capabilities exist is that those are different questions, and a wildcard is the
answer somebody writes when nobody has decided.

Task ids: M1.6.12, M33.2.1.2
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

from brain.audit.ledger import SUBJECT_KINDS
from brain.audit.view import AUDIT_NOUN, CAPABILITY_BY_KIND
from brain.core.entitlement import Capability
from brain.core.scope import Clause, Op, Scope
from brain.identity.directory import DirectoryAssertion, reconcile
from brain.identity.packs import SubjectGrant
from brain.identity.staff_source import (
    Asserts,
    GroupRule,
    Roster,
    StaffRecord,
    StaffSourceError,
    assertions_from,
    source_gaps,
)
from brain.identity.teams import PrincipalSubject

# ------------------------------------------------------------------ written-down reasons
#: Why the first run of a newly wired source may add and may never remove.
THE_FIRST_RUN_OF_A_SOURCE_HAS_NOTHING_TO_BE_WRONG_AGAINST: Final = (
    "Completeness is a promise about the source's own answer: this is every person I was "
    "asked about. It says nothing about whether the question was right. A directory "
    "connector aimed at one organisational unit, a Sheets range covering one office and a "
    "directory search rooted one level too deep are each complete, correct and wrong about "
    "the company, and every one of them proposes removing everybody outside its scope on the "
    "first run. Nothing distinguishes that from a company that really did shrink, because "
    "there is no previous run to compare it with. So the first run adds only, and by the "
    "second somebody has had a dry run to read."
)

#: Why a refusal is reported by a dry run rather than raised out of it.
A_DRY_RUN_THAT_CANNOT_SURVIVE_A_BAD_CONFIGURATION_IS_NO_USE_AT_ALL: Final = (
    "`assertions_from` refuses a source wired to role rules it is not trusted to assert, on "
    "purpose and at configuration time rather than on the night the sync runs. Configuration "
    "time is exactly when somebody is looking at a dry run, so letting that exception escape "
    "would make the one tool for finding the misconfiguration the one tool that cannot "
    "survive it. It is caught and named, and the run says it is not safe to apply, which is "
    "the same refusal delivered where the person can read it."
)

#: Why the removals a dry run shows are never wider than the absences it found.
A_DRY_RUN_MAY_NEVER_NAME_A_REMOVAL_IT_DID_NOT_FIND: Final = (
    "Everything in `would_remove` comes from `absent`, which is a set difference against what "
    "the caller was already holding. The reasoning is `brain.identity.directory.reconcile`'s "
    "and it is the same one: a dry run that could name somebody the caller did not show it "
    "is a dry run proposing to delete a row nobody read first. Suppression only ever "
    "narrows, so every rule in this file can make the removal list shorter and none of them "
    "can make it longer."
)

#: How often a roster is read when nobody asks for one sooner.
#:
#: A day, and the number comes from what this sync is for rather than from taste. A roster is
#: a statement about employment, which changes on the timescale of a working day: somebody
#: joins, moves department or leaves, and none of those is a decision taken between two
#: readings an hour apart. The thing that would argue for a shorter interval, a leaver
#: keeping access, does not depend on this at all: sign-in is Keycloak's and an account
#: disabled in the directory cannot sign in whatever this roster last said. What a longer
#: interval would cost is a joiner waiting, which is the visible failure, and a day is
#: already the outside of what somebody starting a job will tolerate.
SYNC_INTERVAL: Final = timedelta(days=1)


@dataclass(frozen=True)
class DryRun:
    """What one sync would do, computed from the inputs it would use and writing nothing.

    Every field is a list of things rather than a count of them. An operator reading "four
    people would be removed" cannot act on it and cannot tell whether the four are the four
    they expect, which is the only question a dry run exists to answer.
    """

    source: str
    #: People in the roster that the caller is not already holding, and who are working here.
    would_add: tuple[StaffRecord, ...]
    #: Addresses the caller is holding that this roster does not mention. Reported whether or
    #: not anything may be done about them, because who is missing is the fact an operator
    #: needs in order to decide whether the source is pointed at the right place.
    absent: tuple[str, ...]
    #: The subset of `absent` this run would actually remove. Always a subset, never wider.
    would_remove: tuple[str, ...]
    #: Addresses the source says have left. The one removal that survives an incomplete
    #: roster and a first run, because it is the source stating a fact rather than omitting
    #: one.
    would_deactivate: tuple[str, ...]
    #: Why `would_remove` is narrower than `absent`, in words, or empty when it is not.
    withheld: tuple[str, ...]
    #: Directory role assertions this roster supports that the caller does not hold.
    role_grants_to_add: tuple[DirectoryAssertion, ...]
    #: Held assertions this roster no longer supports. Subject to the same suppression as
    #: `would_remove`, because a role removed on the strength of an incomplete roster is the
    #: same mistake one table along.
    role_grants_to_remove: tuple[DirectoryAssertion, ...]
    #: Configuration this run refuses to act on, named. Non-empty means nothing may be
    #: applied.
    refusals: tuple[str, ...]
    #: What `source_gaps` says about this source, unchanged and not restated.
    gaps: tuple[str, ...]

    @property
    def safe_to_apply(self) -> bool:
        """Whether a caller may execute this run.

        False when anything was refused. A dry run that reported a refusal and still handed
        back an applicable plan would be a refusal in name only.
        """
        return not self.refusals

    @property
    def changes_nothing(self) -> bool:
        """True when applying this would leave the estate exactly as it is.

        Worth being able to say cheaply for the same reason `Reconciliation.is_empty` is: a
        scheduled job that writes an audit entry per run whether or not anything changed
        buries the runs that did.
        """
        return not (
            self.would_add
            or self.would_remove
            or self.would_deactivate
            or self.role_grants_to_add
            or self.role_grants_to_remove
        )


def dry_run(
    roster: Roster,
    *,
    known: Mapping[str, str],
    last_applied: datetime | None,
    rules: Sequence[GroupRule] = (),
    held: Iterable[DirectoryAssertion] = (),
) -> DryRun:
    """What this roster would change, and why it would not change the rest.

    `known` maps a casefolded work address to the principal this system already holds for it,
    which is the same argument `assertions_from` takes and is passed straight through rather
    than rebuilt. `held` is what `auth.directory_role_grant` currently contains for this
    source. `last_applied` is when a sync from this source was last executed, and `None` means
    never, which is the first-run case.

    **`last_applied` is a time rather than a flag**, and that is not decoration: it is the
    same value `is_due` reads, so a caller cannot be holding one answer about whether this
    source has ever run and a different answer about when it last did.

    Rejected: taking the previous roster and diffing against it. It is the obvious shape and
    it answers the wrong question. What matters is the difference between the roster and what
    the *system* is holding, because that is what a sync would change; two rosters agreeing
    tells you nothing about a person somebody provisioned by hand last week.
    """
    listed = {one.work_address.casefold(): one for one in roster.people}
    absent = tuple(sorted(set(known) - set(listed)))

    withheld: list[str] = []
    if not roster.may_remove():
        withheld.append(
            f"{roster.source!r} did not promise a complete list, so nothing is removed on the "
            "strength of this run; an export that half succeeded looks exactly like this"
        )
    if last_applied is None:
        withheld.append(
            f"{roster.source!r} has never been applied, so nothing is removed on the strength "
            "of its first run: a source aimed at the wrong place is complete about the wrong "
            "question and there is no previous run to notice it against"
        )
    may_remove = not withheld

    refusals: list[str] = []
    try:
        # Copied into a `dict` because that is the parameter's declared type; a `Mapping` is
        # what a caller naturally holds and the two are not interchangeable to mypy.
        asserted = assertions_from(roster, rules, principal_for=dict(known))
    except StaffSourceError as why:
        # Reported rather than propagated. See
        # `A_DRY_RUN_THAT_CANNOT_SURVIVE_A_BAD_CONFIGURATION_IS_NO_USE_AT_ALL`.
        refusals.append(str(why))
        asserted = ()

    # `reconcile` computes both differences and this discards one of them when removals are
    # suppressed, rather than computing the additions separately. A second set difference here
    # would be a second answer to what a sync proposes, and the wrong copy is the one that
    # ships.
    proposed = reconcile(asserted, held)

    return DryRun(
        source=roster.source,
        would_add=tuple(
            sorted(
                (one for at, one in listed.items() if at not in known and one.active),
                key=lambda one: one.work_address.casefold(),
            )
        ),
        absent=absent,
        would_remove=absent if may_remove else (),
        would_deactivate=tuple(
            sorted(at for at, one in listed.items() if not one.active and at in known)
        ),
        withheld=tuple(withheld),
        role_grants_to_add=tuple(sorted(proposed.to_insert, key=_ordering)),
        role_grants_to_remove=(
            tuple(sorted(proposed.to_delete, key=_ordering)) if may_remove else ()
        ),
        refusals=tuple(refusals),
        gaps=source_gaps([roster]),
    )


def _ordering(assertion: DirectoryAssertion) -> tuple[str, str, str]:
    """A total order over assertions, so two dry runs of the same state read identically.

    Sets iterate in an order that varies with hash randomisation, so without this a person
    comparing this morning's dry run with last night's sees movement that is not there.
    """
    return (assertion.principal_id, assertion.role.value, assertion.source_group)


def due_at(last_applied: datetime | None, *, every: timedelta = SYNC_INTERVAL) -> datetime | None:
    """When the next scheduled read is due, or None when it is due now.

    None rather than "now", because a source that has never been read has no interval to
    count from and answering with the current time would make the answer depend on when the
    question was asked. A caller that gets None reads immediately.
    """
    if last_applied is None:
        return None
    return last_applied + every


def is_due(
    last_applied: datetime | None, now: datetime, *, every: timedelta = SYNC_INTERVAL
) -> bool:
    """Whether a scheduled read should happen.

    **There is no parameter here that a dry run fits into.** A dry run writes nothing, so
    recording one as a run would push the next real sync out by a full interval every time
    somebody looked at the diff, and the failure would be a sync that silently stops
    happening on the day somebody starts watching it.
    """
    due = due_at(last_applied, every=every)
    return due is None or now >= due


# ================================================ a department head's audit reach (M33.2.1.2)
#: Why a head's audit permissions are written against people and never against a department.
A_DEPARTMENT_SCOPED_AUDIT_GRANT_MATCHES_NO_ENTRY: Final = (
    "An audit entry records what happened, what kind of thing it happened to, which thing "
    "and who did it, and no department. brain.audit.view._scope_row lists those four fields "
    "and brain.core.scope.Clause.matches refuses a row that does not carry the field a clause "
    "names, which is the correct fail-closed reading. So a head whose audit grants are scoped "
    "to their own department reads nought rows rather than a filtered ledger, and every test "
    "written with a company-wide fixture passes over the top of it. Re-run on 2026-09-10 "
    "before this was built: nine entries, three actors; the department-scoped reader saw 0 "
    "and the same reader scoped to two named actors saw 6, being those two and nobody else."
)

#: Why the scope is written on the actor, and why it can carry only that one axis.
ACTIVITY_IS_THE_ACTOR_AXIS_AND_A_SCOPE_HOLDS_ONE_OF_THEM: Final = (
    "Two of the four fields could carry a set of people: actor_id, who did it, and subject, "
    "which for a principal entry is who it was done to. Activity means the first, which is "
    "what brain.console.global_surfaces.activity_filter already decides by turning a person "
    "lens into AuditFilter.actors. It cannot be both, because brain.core.scope.Scope composes "
    "by conjunction only and has no disjunction to add one to: two clauses would mean an "
    "entry has to satisfy both, and two grants of one capability are intersected by "
    "EntitlementSet.scope_for, which narrows again. So a head reads what their people did, "
    "and what was done to their people is a different grant nobody has asked for."
)

#: The rule that generates the list below: which entries belong to a head and which do not.
A_HEAD_READS_THE_GOVERNANCE_OF_THEIR_PEOPLE_AND_NOT_THEIR_WORK: Final = (
    "A head governs: they write grants inside their own scope, move a rung, publish an agent, "
    "adopt a stopped one and decide a suspended action. The audit entries those acts produce "
    "are the record of the authority they already hold, so reading them back is the review "
    "half of a power they have. An entry about a business record or an artefact is their "
    "people's work, and whether this reader may see one of those is decided by a scope on the "
    "object which an actor-scoped audit grant does not consult; admitting it would make the "
    "ledger the way round the scope on the data. That is the line, and every one of the eight "
    "is put on one side of it below rather than left to a reader to infer."
)


@dataclass(frozen=True)
class AuditKindDecision:
    """One of the eight audit subject kinds, and whether a department head reads it.

    A record rather than two lists, so the answer and its argument cannot come apart. Two
    lists drift the first time somebody moves a kind and edits one of them, and the direction
    the drift takes is invisible: a kind in neither list is a kind nobody decided about, and a
    kind in both is a contradiction that reads as an inclusion.
    """

    kind: str
    #: True when a head's grants cover this kind. `HEAD_AUDIT_SUBJECT_KINDS` is derived from
    #: this field, so the set is this data and never a second copy of it.
    covered: bool
    because: str

    def __post_init__(self) -> None:
        if self.kind not in SUBJECT_KINDS:
            msg = (
                f"{self.kind!r} is not an audit subject kind; the eight are "
                f"{sorted(SUBJECT_KINDS)} and a decision about a ninth decides nothing"
            )
            raise ValueError(msg)
        if not self.because.strip():
            # The same rule `brain.identity.lifecycle.Step` keeps: a decision nobody can
            # explain is one that gets reversed the first time it is inconvenient, and by
            # then what it was protecting is gone.
            msg = f"the decision about {self.kind!r} carries no argument; every one has one"
            raise ValueError(msg)


#: All eight audit subject kinds, each with the sentence that puts it in or out.
#:
#: This is the list item 48 asked for, and it is deliberately a mapping over the whole
#: vocabulary rather than the chosen subset: a ninth subject kind added to
#: `brain.audit.ledger.SUBJECT_KINDS` leaves this incomplete and fails a test, which is how a
#: new kind gets decided about rather than quietly inheriting whichever side the code falls
#: on. See `A_HEAD_READS_THE_GOVERNANCE_OF_THEIR_PEOPLE_AND_NOT_THEIR_WORK` for the rule.
AUDIT_KIND_DECISIONS: Final[Mapping[str, AuditKindDecision]] = MappingProxyType(
    {
        one.kind: one
        for one in (
            AuditKindDecision(
                kind="principal",
                covered=True,
                because=(
                    "Every grant and every revocation lands here: brain.audit.record.grant and "
                    "revoke both write subject('principal', ...), so this kind and not the one "
                    "named grant is where a permission history is. A head writes grants inside "
                    "their own scope, and a grant wider than its granter is the one escalation "
                    "an additive model cannot undo, so withholding this would leave them "
                    "performing the act they cannot review."
                ),
            ),
            AuditKindDecision(
                kind="agent",
                covered=True,
                because=(
                    "Leash changes and composition changes land here. Both are acts a head "
                    "already performs, and a rung raised above the ceiling its side effects "
                    "allow is not inert: it runs autonomously on any call whose risk score is "
                    "low. The head who may move a rung is the reader who should see one moved."
                ),
            ),
            AuditKindDecision(
                kind="leash",
                covered=True,
                because=(
                    "An approval is recorded against the suspension rather than the target, "
                    "and brain.audit.record.approval says why: so that what an approver has "
                    "been waving through is one query rather than a search through everything "
                    "the writes touched. A head holds the approval authority, so that question "
                    "is theirs about their own people."
                ),
            ),
            AuditKindDecision(
                kind="grant",
                covered=False,
                because=(
                    "Nothing writes an entry under this kind. Every recorder method that "
                    "concerns a grant addresses the principal, so the only entry that could "
                    "arrive here is a refusal a caller chose to label this way. A capability "
                    "whose whole content today is a refusal about an unnamed object is a grant "
                    "nobody could review, and this is the exclusion the written list makes "
                    "visible where a branch would have hidden it."
                ),
            ),
            AuditKindDecision(
                kind="entity",
                covered=False,
                because=(
                    "A merge entry names two business record ids. Whether this reader may see "
                    "a business record is decided by a scope over that record, and an audit "
                    "grant bounded by the actor does not consult it, so this kind would admit "
                    "the id of every record their people touched including the ones their own "
                    "grants refuse. The ledger must not be the way round the scope on the data."
                ),
            ),
            AuditKindDecision(
                kind="artifact",
                covered=False,
                because=(
                    "The same argument one object along. A publish entry names an artefact id "
                    "and brain.console.agent_output decides who may see an artefact; an "
                    "actor-scoped audit grant asks that question of nobody."
                ),
            ),
            AuditKindDecision(
                kind="connector",
                covered=False,
                because=(
                    "A connector is estate configuration and a head cannot install, bind or "
                    "rotate one; none of their governing acts touches a connector. An entry "
                    "about one is the install's activity rather than the department's, and it "
                    "belongs to whoever holds the connector custody role."
                ),
            ),
            AuditKindDecision(
                kind="session",
                covered=False,
                because=(
                    "Break-glass lands here, and it already names its authoriser and the "
                    "people it notified, so a head who ought to know is told by name rather "
                    "than by holding a standing reach. What that reach would amount to is "
                    "every session entry fifteen named people generate, kept for as long as "
                    "the ledger is kept, which is a record of presence rather than of work "
                    "and is the thing this decision was taken in order not to start keeping."
                ),
            ),
        )
    }
)

#: The subject kinds a department head's audit grants cover. Derived, never written twice.
HEAD_AUDIT_SUBJECT_KINDS: Final[tuple[str, ...]] = tuple(
    sorted(kind for kind, decision in AUDIT_KIND_DECISIONS.items() if decision.covered)
)

#: Why the screen's own capability is granted beside the per-kind ones.
#:
#: `brain.console.govern_surfaces.READ_AUDIT_OPENS_THE_PAGE_AND_READ_AUDIT_DOT_KIND_FILLS_IT`
#: is the same sentence written from the console's side, and it is named rather than imported
#: because the identity package must not depend on the console. `Capability.covers` expands
#: only a trailing `.*`, so `read:audit` and `read:audit.principal` are disjoint: the first
#: opens the page and confers no entry, the second fills it and lights up no menu. A head
#: given one and not the other is a grant somebody wrote half of.
THE_PAGE_AND_THE_ROWS_ARE_TWO_GRANTS: Final = (
    "The Activity screen requires read:audit and brain.audit.view asks read:audit.<kind> per "
    "entry. Neither capability covers the other, so a head holding only the kinds has rows "
    "and no menu entry, and a head holding only read:audit has a page showing them their own "
    "entries and nothing else, which is correct and reads as broken. Both are written, with "
    "one scope, so the two halves cannot be granted apart by this sync."
)

#: The page capability, built from the audit view's own noun rather than spelled here.
AUDIT_PAGE_CAPABILITY: Final = Capability(value=f"read:{AUDIT_NOUN}")

#: Every audit capability this sync could ever have written, for any decision about the eight.
#:
#: Wider than what it writes today, on purpose. `to_delete` is computed against this set, so
#: the day a kind is taken out of `AUDIT_KIND_DECISIONS` the grant that kind produced is
#: deleted on the next run. Computed against only the current set, the removal would change
#: what new heads receive and leave every existing head holding it for ever, which is the
#: shape of a policy change that applies to nobody it was written about.
AUDIT_CAPABILITIES_A_SYNC_MAY_WRITE: Final[frozenset[str]] = frozenset(
    {AUDIT_PAGE_CAPABILITY.value} | {cap.value for cap in CAPABILITY_BY_KIND.values()}
)

#: The field an audit grant's scope is written against. See
#: `ACTIVITY_IS_THE_ACTOR_AXIS_AND_A_SCOPE_HOLDS_ONE_OF_THEM`.
#:
#: A literal, because the only public name for it is inside `brain.audit.view._scope_row`,
#: which is private. What stops it drifting is not this comment: it is that
#: `test_staff_sync.py` builds real entries, hands them to a real `AuditView` with the grants
#: this module produces, and asserts the head sees exactly their own people's rows. A rename
#: on either side turns that test red rather than turning a head's page silently empty, which
#: is the failure this whole section exists to answer.
ACTOR_FIELD: Final = "actor_id"

#: What `granted_by` says on a grant this sync wrote. The source is appended, so a reviewer
#: reading the grant table sees which roster asserted it. The same shape, and for the same
#: reason, as `brain.identity.directory.ISSUER_PREFIX`.
ROSTER_PREFIX: Final = "roster:"

#: `SubjectGrant.granted_by` is `Field(max_length=128)`.
GRANTED_BY_CHARS: Final = 128

#: How long one of these grants outlives the roster reading behind it.
#:
#: Two intervals rather than one, and an expiry rather than none, and both halves are the
#: answer to the staleness cost item 48 names. With no expiry a sync that stops leaves a head
#: reading a membership list from whenever it stopped, for ever, and nothing about the page
#: says so. With one interval a single missed run empties the page, which is an outage on a
#: schedule. Two means one missed run is survivable, two closes the reach, and the window
#: within which a head can still read somebody who has left their department is bounded by
#: construction rather than by somebody remembering to look.
GRANT_LIFETIME: Final = 2 * SYNC_INTERVAL

#: How stale a head's audit reach can be, stated once so a screen and a report agree.
THE_STALENESS_WINDOW: Final = (
    "A head's audit reach is as fresh as the last applied sync, so a transfer is reflected at "
    "the next run and the window is at most one SYNC_INTERVAL. It fails in both directions "
    "inside it and only one of them matters: a joiner the head cannot see yet is closed and "
    "invisible, and somebody who transferred out this morning can still be read until the "
    "next run. The grant lapses GRANT_LIFETIME after the reading behind it, so a sync that "
    "stops closes the reach instead of freezing it, and "
    "brain.console.scoped_authority.activity_basis puts the reading time, the due time and "
    "whether it is overdue on the screen, because a window nobody is shown is a window "
    "nobody has."
)

#: Why a source not trusted to place people cannot rewrite a head's audit reach.
A_ROSTER_NOT_TRUSTED_WITH_DEPARTMENTS_NAMES_THE_WRONG_PEOPLE: Final = (
    "Asserts.DEPARTMENT is the promise that this source may say which department somebody is "
    "in, and a spreadsheet anybody with the link can edit does not make it. Every other "
    "suppression in this module is against a list that is too short, which fails closed; this "
    "one is against a list that is wrong, and a wrong department field puts somebody else's "
    "people into a head's reach. It is the one failure here that widens, so it refuses to "
    "produce a member list at all rather than producing one nobody may act on."
)

#: Why a roster that did not promise completeness cannot rewrite a head's audit reach either.
A_HALF_ANSWERED_ROSTER_NARROWS_A_HEAD_WHERE_NOBODY_CAN_SEE_IT: Final = (
    "An export that timed out looks exactly like a department that halved, which is "
    "A_SOURCE_THAT_HALF_ANSWERED_LOOKS_EXACTLY_LIKE_A_COMPANY_THAT_HALVED asked about a grant "
    "instead of a person. The direction is safe and the visibility is not: the head's page "
    "quietly shows fewer people, and DENIED and ABSENT being indistinguishable is exactly "
    "what stops them noticing. So the member list is reported and the rewrite is withheld."
)

#: Why the sync deletes only rows it wrote, and why that is weaker than the sibling rule.
#:
#: `brain.identity.directory` gets to say a reconciler structurally cannot reach a hand-made
#: grant, because directory role grants live in a table of their own. There is one
#: `capability_grant` table and no second one to move these into, so the same protection here
#: is a filter on `granted_by` rather than a signature that has nowhere to put the wrong row.
#: That is precisely the "WHERE clause somebody can forget" that module rejected, and it is
#: named here rather than presented as equivalent.
THE_SYNC_DELETES_ONLY_WHAT_IT_WROTE: Final = (
    "to_delete is restricted to grants whose granted_by carries ROSTER_PREFIX, so an audit "
    "grant a person wrote by hand survives every run. brain.identity.directory buys the same "
    "property with a second table and calls a filter on a column the weaker form, correctly: "
    "this one is a condition that can be dropped in a refactor rather than a parameter that "
    "would have to be added. It is the strongest available while these rows share a table "
    "with every other capability grant, and the test naming a hand-made row is what watches it."
)


@dataclass(frozen=True)
class HeadAuditReach:
    """What one department head's audit grants should say, and what a run would write.

    Three lists rather than a verb, on the split `brain.identity.directory.Reconciliation`
    already argues for: the function that decides is pure and testable without a database,
    and the function that writes holds a transaction and no judgement.

    `unchanged` is not an empty category. A row whose capability and scope both still hold is
    the same reach, and the only thing a run touches on it is the moment it lapses, which is
    bookkeeping about the sync rather than a change to what the head may read. Deleting and
    re-inserting it instead would put a revocation and a grant into the ledger every night for
    a head whose department did not change, which is `DirectoryAssertion`'s churn argument
    arriving one table along.
    """

    department: str
    head_id: str
    #: The principals the roster places in this department, sorted. Empty when the source is
    #: not trusted to place anybody.
    members: tuple[str, ...]
    to_insert: tuple[SubjectGrant, ...]
    #: Always a subset of the held rows this sync wrote. Never wider, and never hand-made.
    to_delete: tuple[SubjectGrant, ...]
    #: Held rows the run would keep, whose lapse the caller moves forward with `renewed`.
    unchanged: tuple[SubjectGrant, ...]
    #: When the roster behind this was read. What `activity_basis` puts on the screen.
    read_at: datetime
    #: Configuration or a source this run refuses to act on, named. Non-empty means nothing
    #: may be applied.
    refusals: tuple[str, ...]

    @property
    def safe_to_apply(self) -> bool:
        """Whether a caller may execute this. False when anything was refused."""
        return not self.refusals

    @property
    def changes_nothing(self) -> bool:
        """True when the head's audit grants already say what this roster says.

        The common case, and worth being able to say cheaply for the reason
        `Reconciliation.is_empty` gives: a job that writes an audit entry per run whether or
        not anything changed buries the runs that did.
        """
        return not (self.to_insert or self.to_delete)


def audit_reach_for_head(
    roster: Roster,
    *,
    department: str,
    head_id: str,
    known: Mapping[str, str],
    read_at: datetime,
    held: Iterable[SubjectGrant] = (),
) -> HeadAuditReach:
    """The audit grants this head should hold, and the difference from what they hold (M33.2.1.2).

    `known` maps a casefolded work address to the principal this system already holds for it,
    which is the same argument `dry_run` and `assertions_from` take and is passed through
    rather than rebuilt. `held` is every capability grant the caller loaded for this head.

    **Four grants, one scope.** `AUDIT_PAGE_CAPABILITY` and one per kind in
    `HEAD_AUDIT_SUBJECT_KINDS`, each scoped to `actor_id IN (the members)`. See
    `THE_PAGE_AND_THE_ROWS_ARE_TWO_GRANTS` for why the first is there and
    `A_HEAD_READS_THE_GOVERNANCE_OF_THEIR_PEOPLE_AND_NOT_THEIR_WORK` for why the other three
    are the three.

    **A person the source says has left is not in the list.** Item 48's own wording is that
    the grant is rewritten when somebody joins or leaves, and the alternative keeps a head
    reading a departed person's trail indefinitely, which is retention arriving through a
    permission. Their entries do not go anywhere: the ledger keeps them and whoever holds the
    wider audit grant reads them.

    **The head is in the list exactly when the roster puts them in the department.** Adding
    them here would make the grant disagree with the directory, and a permission that names
    the people it covers is worth having because somebody can read it against the org chart.
    A head who is not on their own department's roster reads their own entries anyway, by
    `brain.audit.view.AuditView._may_see`'s first branch.

    Refusals rather than exceptions, for the reason
    `A_DRY_RUN_THAT_CANNOT_SURVIVE_A_BAD_CONFIGURATION_IS_NO_USE_AT_ALL` gives about the
    sibling: this is read at the moment somebody is looking at whether a source is wired up
    correctly, and the one tool for finding that must survive it. The two refusals differ in
    what they leave behind, deliberately: an untrusted department field yields no member list
    at all, because the source cannot answer the question; a half-answered roster yields the
    members it did name, because that list is the diagnostic an operator needs.
    """
    if not department.strip():
        msg = "an audit reach needs a department; over none it is the company's ledger"
        raise ValueError(msg)
    if not head_id.strip():
        msg = "an audit reach needs the head it is for; a blank id names nobody"
        raise ValueError(msg)

    refusals: list[str] = []
    if Asserts.DEPARTMENT not in roster.asserts:
        refusals.append(
            f"{roster.source!r} is not trusted to say which department somebody is in, so it "
            "cannot name a head's people. "
            + A_ROSTER_NOT_TRUSTED_WITH_DEPARTMENTS_NAMES_THE_WRONG_PEOPLE
        )
        members: tuple[str, ...] = ()
    else:
        members = _members_of(roster, department=department, known=known)

    if not roster.may_remove():
        refusals.append(
            f"{roster.source!r} did not promise a complete list, so a head's audit reach is "
            "not rewritten from it. "
            + A_HALF_ANSWERED_ROSTER_NARROWS_A_HEAD_WHERE_NOBODY_CAN_SEE_IT
        )

    subject = PrincipalSubject(principal_id=head_id)
    mine = tuple(
        row
        for row in held
        if row.subject == subject
        and row.capability.value in AUDIT_CAPABILITIES_A_SYNC_MAY_WRITE
        and row.granted_by.startswith(ROSTER_PREFIX)
    )
    if refusals:
        # Nothing is proposed, in either direction. A plan computed from a source that was
        # refused is a plan somebody can apply, and the refusal would then be a note beside
        # the rows rather than a refusal.
        return HeadAuditReach(
            department=department,
            head_id=head_id,
            members=members,
            to_insert=(),
            to_delete=(),
            unchanged=(),
            read_at=read_at,
            refusals=tuple(refusals),
        )

    wanted = _audit_grants(
        roster,
        subject=subject,
        department=department,
        members=members,
        read_at=read_at,
    )
    wanted_by_key = {_confers(row): row for row in wanted}
    held_by_key = {_confers(row): row for row in mine}

    return HeadAuditReach(
        department=department,
        head_id=head_id,
        members=members,
        to_insert=tuple(
            wanted_by_key[key] for key in sorted(wanted_by_key.keys() - held_by_key.keys())
        ),
        to_delete=tuple(
            held_by_key[key] for key in sorted(held_by_key.keys() - wanted_by_key.keys())
        ),
        unchanged=tuple(
            held_by_key[key] for key in sorted(held_by_key.keys() & wanted_by_key.keys())
        ),
        read_at=read_at,
        refusals=(),
    )


def renewed(grant: SubjectGrant, *, read_at: datetime) -> SubjectGrant:
    """The same reach, lapsing one grant lifetime after this reading.

    What a caller applies to everything in `unchanged`. `granted_at` is carried through
    unchanged and not moved to `read_at`, which is
    `brain.identity.directory.directory_role_grants`' argument about its own timestamp: a
    grant stamped with the current time reads, in every review afterwards, as though the
    appointment were made this morning.

    Nothing else moves. The capability and the scope are what the row confers, and a function
    that could change either while claiming to renew would be a widening with a reassuring
    name.
    """
    return SubjectGrant(
        subject=grant.subject,
        capability=grant.capability,
        scope=grant.scope,
        granted_by=grant.granted_by,
        reason=grant.reason,
        granted_at=grant.granted_at,
        not_after=read_at + GRANT_LIFETIME,
        from_pack=grant.from_pack,
    )


def _members_of(roster: Roster, *, department: str, known: Mapping[str, str]) -> tuple[str, ...]:
    """The principals this roster places in this department, sorted and deduplicated.

    Casefolded on both sides, because `known` is keyed on a casefolded address and a
    department read out of a directory is whatever somebody typed into it.

    Somebody the roster lists and this system does not hold contributes nothing. That is not
    a gap being swallowed: `dry_run.would_add` is where an unknown person is reported, and
    naming them here as well would be two answers to who is missing.
    """
    wanted = department.casefold()
    found = {
        known[one.work_address.casefold()]
        for one in roster.people
        if one.active
        and one.department.casefold() == wanted
        and one.work_address.casefold() in known
    }
    return tuple(sorted(found))


def _audit_grants(
    roster: Roster,
    *,
    subject: PrincipalSubject,
    department: str,
    members: tuple[str, ...],
    read_at: datetime,
) -> tuple[SubjectGrant, ...]:
    """The grants a head with these members should hold.

    **No members, no grants, and that is a refusal rather than an accident of arithmetic.** An
    `IN` clause with an empty member list is refused by `assert_conjunctive` before a
    `SubjectGrant` can hold it, so the alternative is not a wide grant; it is an exception out
    of the middle of a sync. Returning nothing says the same thing in the shape a caller can
    act on, and it is the correct reading: a head of a department the roster places nobody in
    reads nothing, exactly as they would if the grant had never been written.
    """
    if not members:
        return ()

    granted_by = f"{ROSTER_PREFIX}{roster.source}"
    if len(granted_by) > GRANTED_BY_CHARS:
        # The same refusal `brain.identity.directory.directory_role_grants` makes about an
        # issuer. A grantor string too long for the column fails at the INSERT otherwise,
        # which is after the decision has been taken and inside a transaction.
        msg = (
            f"source {roster.source!r} is too long to record as a grantor; the column holds "
            f"{GRANTED_BY_CHARS} characters and the row would fail at the insert"
        )
        raise StaffSourceError(msg)

    scope = Scope(clauses=(Clause(field=ACTOR_FIELD, op=Op.IN, value=members),))
    capabilities = (
        AUDIT_PAGE_CAPABILITY,
        *(CAPABILITY_BY_KIND[kind] for kind in HEAD_AUDIT_SUBJECT_KINDS),
    )
    return tuple(
        SubjectGrant(
            subject=subject,
            capability=capability,
            scope=scope,
            granted_by=granted_by,
            reason=f"heads {department}, whose people this roster names",
            granted_at=read_at,
            not_after=read_at + GRANT_LIFETIME,
        )
        for capability in capabilities
    )


def _confers(grant: SubjectGrant) -> tuple[str, str]:
    """What a grant amounts to, ignoring when it was written and when it lapses.

    Two rows agreeing on both confer one reach, and the fields left out are the ones a run
    moves without anybody's access changing. `brain.identity.directory._confers` is the same
    idea about a role grant and is not shared with it: that one returns a role and a deputy
    and this one a capability and a scope, so a common helper would take a union of two
    types' fields and mean neither.

    The scope is rendered rather than carried, because `Scope` normalises its clauses on
    construction and two scopes admitting the same rows serialise identically, which is the
    property `EntitlementSet.ent_hash` already rests on.
    """
    return (grant.capability.value, grant.scope.model_dump_json())
