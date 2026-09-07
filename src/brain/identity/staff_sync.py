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
named rather than imported: this package imports nothing outside itself and `brain.core`, and
one string constant is not worth being the first exception.

**A dry run does not touch the schedule.** It changes nothing, so recording it as a run would
push the next real sync out by a full interval every time somebody looked. There is no
parameter here that a dry run fits into: `is_due` takes the last time a sync was *applied*.

Task ids: M1.6.12
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.identity.directory import DirectoryAssertion, reconcile
from brain.identity.staff_source import (
    GroupRule,
    Roster,
    StaffRecord,
    StaffSourceError,
    assertions_from,
    source_gaps,
)

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
