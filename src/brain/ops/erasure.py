"""Finding everything held about one person, removing it, and saying honestly what that did.

This is the module where things are deleted, and it sits directly opposite
`brain.memory.correction`, which is the module where nothing ever is. That is not an
inconsistency and the boundary is worth stating precisely, because the two look like the
same operation from a distance.

**A correction marks and an erasure removes, and the difference is who asked.** A correction
is the system learning it was wrong: `A_DELETED_MEMORY_CANNOT_EXPLAIN_ITSELF` is right, a
mark is undoable, and a person asking why the system stopped saying something deserves an
answer. An erasure is a person exercising a right over their own data, and there is no
version of that which a mark satisfies: a memory marked as erased is a memory still stored.
So the cost `brain.memory.correction` refuses to pay is paid here deliberately, in one
direction only, and it is a real cost. After an erasure the system cannot explain what it
used to think about that person. That is the trade, it is not free, and it is made because
the alternative is keeping data somebody asked to be rid of. See
`A_CORRECTION_MARKS_AND_AN_ERASURE_REMOVES`.

**The store list is not written here.** It is `brain.ops.retention.Store`, iterated. A
subject access request that missed a store is a document that looks complete and is not,
and the failure has no symptom: nobody receiving one can tell that the recordings bucket was
never searched. So there is no list of stores in this file, no flag on a store that could
take it out of an assembly, and no parameter that could skip one. Assembly and deletion both
iterate the enum, which is what turns "add a store to the system and this stops being
correct" into a failing test rather than into a silence. See
`A_STORE_LEFT_OUT_OF_A_SUBJECT_ACCESS_REQUEST_IS_A_LIE`.

**Derived copies are purged after their source, and the gap between is real.** Purging the
cache first means the next question repopulates it from rows that are still there, which
leaves a deleted person answerable from cache with every log line saying the deletion
succeeded. Deleting the source first leaves a stale cache for as long as the purge takes,
which is a bounded and visible failure rather than a silent and permanent one. The order
returned by `deletion_order` puts sources first for that reason, and the gap between the two
is stated rather than pretended away.

**Backups are the honest limit and the certificate carries it.** A backup written the day
before a deletion holds the data until it rotates out, and no deletion this system performs
reaches inside one. A certificate that implied otherwise would be a false statement in a
document produced specifically to be relied on, which is worse than producing no certificate
at all. So every certificate carries the date the last backup that could contain the data
rotates out, and there is no field on it that says "complete". See
`DELETION_DOES_NOT_REACH_A_BACKUP_ALREADY_WRITTEN`.

**A certificate counts and never copies.** Same argument as `brain.memory.correction` and
`brain.ops.canaries`: a record listing the values that were deleted is a second copy of
exactly the thing somebody asked to be erased, in a document that is emailed, filed and kept
longer than the data was. Counts and classes travel; content does not, and there is no
attribute on the model to put it in.

Nothing here reaches a store. `StoreEraser` is the shape the executor must have and **the
executor is not built**; every function takes what was observed and returns what is wrong
with it, which is why the case that matters, a store that could not be reached, is testable
at all.

Task ids: M25.2.1, M25.2.2, M25.2.3, M25.2.4
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import Protocol, assert_never

from brain.ops.retention import (
    BACKUP_RETENTION_DAYS,
    DataClass,
    Store,
    data_class_of,
    facts_for,
)


class ErasureError(Exception):
    """Raised when a deletion, an assembly or a certificate cannot be believed."""


# ------------------------------------------------------------------ written-down reasons
#: The boundary with `brain.memory.correction`, in words, because the two look alike.
A_CORRECTION_MARKS_AND_AN_ERASURE_REMOVES = (
    "brain.memory.correction never deletes, and it is right not to: a memory the system was "
    "corrected about is marked, and the mark is what answers 'why did it stop saying that'. "
    "An erasure is the other case entirely. The person whose data it is has asked for it to "
    "be gone, and a mark does not satisfy that, because a marked memory is a stored memory. "
    "So this module removes, and it accepts the cost that module refuses: after an erasure "
    "the system cannot explain what it used to hold about that person. The cost is real and "
    "one-directional, and it is the smaller of the two."
)

#: Why the store list is iterated rather than written out at each call site.
A_STORE_LEFT_OUT_OF_A_SUBJECT_ACCESS_REQUEST_IS_A_LIE = (
    "A subject access request is a document that says 'this is everything we hold about "
    "you'. If one store was never searched, the document is false and nothing about it "
    "looks wrong: it arrives complete, it is signed, and the omission is discovered years "
    "later or never. So no list of stores is written in this file. The enum is iterated, "
    "every member produces a section, and a store the executor could not reach is named as "
    "not reached rather than being silently absent."
)

#: Why a source is deleted before the copies of it.
A_DERIVED_COPY_PURGED_BEFORE_ITS_SOURCE_IS_REPOPULATED = (
    "Purge the cache first and the next question rebuilds it from rows that are still "
    "there, so the deleted person is answerable from cache and every log line says the "
    "deletion worked. Delete the source first and the cache is stale until the purge lands, "
    "which is wrong for seconds and visibly wrong. One failure is silent and permanent and "
    "the other is loud and bounded, so sources go first. The gap between the two is real "
    "and is not pretended away: a deletion is not atomic across stores and nothing here "
    "claims it is."
)

#: The honest limit of a deletion (M25.2.3).
DELETION_DOES_NOT_REACH_A_BACKUP_ALREADY_WRITTEN = (
    "A deletion removes rows, objects, cache entries and index entries as they are now. It "
    "does not reach inside a backup that was taken before it ran, and nothing in this "
    "system can: a backup is a copy of the database as it was, opening one to edit it "
    "destroys the property that makes it a backup, and a restore from an edited dump is a "
    "restore nobody can verify. So data erased today remains in every dump taken before "
    "today until each of those rotates out on the backups bucket's own lifecycle rule. "
    "What this system can honestly say is the date after which no surviving backup contains "
    "it, and that date is on every certificate. A certificate claiming the deletion is "
    "complete before then would be false, in a document produced to be relied on."
)

#: Why a certificate carries counts and not content (M25.2.4).
A_CERTIFICATE_IS_NOT_A_COPY_OF_WHAT_IT_DELETED = (
    "A certificate listing the values it removed is a second copy of exactly the thing "
    "somebody asked to be erased, in a document that is emailed to them, filed by us, and "
    "kept longer than the data was. It is also the copy nobody thinks to include in the "
    "next erasure. So a certificate carries how many and of what class, never what: there "
    "is no attribute on the model to put content in, which makes including it an edit to "
    "the model in a file that argues against it rather than a line somebody adds."
)

#: Why an active legal hold stops an erasure rather than being worked around.
A_HELD_SUBJECT_IS_NOT_ERASED = (
    "brain.audit.ledger.LegalHold suspends deletion, and it is placed because somebody "
    "outside this system decided the data has to survive. An erasure that ran anyway would "
    "destroy evidence in a live dispute, and it would do it while producing a certificate "
    "saying so. So a held subject is refused here, loudly, and the refusal names the hold "
    "rather than pretending the request was satisfied. The request is not lost: it is "
    "refused, and it can be made again when the hold is released."
)


# ------------------------------------------------------------------------- dispositions
class Disposition(enum.StrEnum):
    """What a deletion does in one store. Four answers, and two of them are not deletion.

    The two that are not are the point. `ROTATES_OUT` and `RETAINED` are how the honest
    limits get expressed as data instead of as a footnote somebody drops: a store that a
    deletion does not reach has to be a store the code knows it does not reach, or the
    certificate will list it as done.
    """

    #: Rows or objects are removed. This store was the record.
    ERASE = "erase"
    #: A copy is dropped. The record was somewhere else and is what was actually erased.
    PURGE = "purge"
    #: A deletion does not reach here. Time does. See the backup constant above.
    ROTATES_OUT = "rotates_out"
    #: Kept deliberately, and the reason outranks the request.
    RETAINED = "retained"


def disposition_of(store: Store) -> Disposition:
    """What a deletion does in this store.

    `assert_never` rather than a mapping with a default, for the reason
    `brain.ops.storage.bucket_for` gives: a store added to the system without a decision
    about what deletion does in it would otherwise get the default, and the default in a
    module like this one is whichever is written first. Here it is a type error before it is
    a runtime error, and the type error arrives in the editor of whoever added the member.
    """
    match store:
        case (
            Store.ROWS
            | Store.AGENTS
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
        ):
            return Disposition.ERASE
        case Store.CACHE | Store.INDEX:
            return Disposition.PURGE
        case Store.BACKUP | Store.EXPORT:
            return Disposition.ROTATES_OUT
        case Store.AUDIT:
            return Disposition.RETAINED
        case _:  # pragma: no cover - unreachable while Store is exhaustive
            assert_never(store)


#: The order dispositions are reached in. Sources first, then the copies of them, then the
#: stores a deletion does not reach at all. See
#: `A_DERIVED_COPY_PURGED_BEFORE_ITS_SOURCE_IS_REPOPULATED`.
_ORDER: Mapping[Disposition, int] = {
    Disposition.ERASE: 0,
    Disposition.PURGE: 1,
    Disposition.ROTATES_OUT: 2,
    Disposition.RETAINED: 3,
}


def subject_access_stores() -> tuple[Store, ...]:
    """Every store a subject access request assembles from. Every one, with no filter.

    Returns the whole enum, and that is the implementation rather than an accident of the
    current declarations. There is no predicate here that could exclude a store and no
    field on `StoreFacts` that could carry one, so the only way to shrink this list is to
    delete a member of `Store`, which is a decision somebody makes visibly.
    """
    return tuple(Store)


def erasure_targets() -> tuple[Store, ...]:
    """Every store a deletion actually reaches, in the order it must reach them."""
    return tuple(
        store
        for store in deletion_order()
        if disposition_of(store) in (Disposition.ERASE, Disposition.PURGE)
    )


def deletion_order() -> tuple[Store, ...]:
    """Every store, sources before the copies made from them.

    Sorted by disposition and then by name rather than by a second hand-written list. A
    second list is a second place to forget a store, and the ordering rule is a property of
    the disposition anyway: everything that is a record goes before everything that is a
    copy of a record.
    """
    return tuple(sorted(Store, key=lambda store: (_ORDER[disposition_of(store)], store.value)))


# ------------------------------------------------------------------------- legal holds
class Hold(Protocol):
    """The shape of a legal hold, as much of it as an erasure needs.

    A protocol rather than an import of `brain.audit.ledger.LegalHold`, so this module stays
    underneath the audit package the way `brain.ops` sits underneath everything it is called
    by, and so a test can build a hold without building a ledger. `LegalHold` satisfies it
    structurally and nothing had to be added there to make that true; a test pins that,
    because a protocol nobody has checked against the real type is a protocol describing a
    class that used to exist.

    Note what is deliberately not read: `actors`. A hold covering an actor is a hold about
    who did something, and an erasure is about whose data it is. Reading `actors` here would
    suspend a person's erasure because they happened to administer something under dispute.
    """

    @property
    def subjects(self) -> frozenset[str]: ...

    @property
    def all_subjects(self) -> bool: ...

    def is_active(self, now: datetime | None = None) -> bool: ...


def holds_over(subject_id: str, holds: Iterable[Hold], now: datetime) -> tuple[Hold, ...]:
    """Every active hold reaching this subject.

    All of them rather than the first, because a subject under three holds and a subject
    under one are different conversations with whoever is asking why the erasure was
    refused, and the second hold is the reason the first being released changes nothing.
    """
    return tuple(
        hold
        for hold in holds
        if hold.is_active(now) and (hold.all_subjects or subject_id in hold.subjects)
    )


# ------------------------------------------------- M25.2.1  the subject access request
@dataclass(frozen=True)
class StoreHolding:
    """What one store had about one person. A count and a sentence, never the rows.

    `reached` separates "we looked and found nothing" from "we could not look", which are
    the two results that must never render the same way. A subject access request built from
    the second while reading like the first is the failure this whole module is arranged
    against.
    """

    store: Store
    data_class: DataClass
    items: int
    reached: bool
    holds: str

    def __post_init__(self) -> None:
        if self.items < 0:
            msg = f"{self.store.value} reported a negative count of items"
            raise ErasureError(msg)
        if not self.reached and self.items:
            msg = (
                f"{self.store.value} was not reached and reports {self.items} item(s); one "
                "of those is not true and the count is the one that would be believed"
            )
            raise ErasureError(msg)

    def line(self) -> str:
        if not self.reached:
            return f"{self.store.value}: could not be searched, so this request is incomplete"
        return f"{self.store.value} ({self.data_class.value}): {self.items} item(s); {self.holds}"


@dataclass(frozen=True)
class SubjectAccess:
    """Everything the system holds about one person, store by store (M25.2.1).

    Carries counts and the description of each store rather than the data itself. The data
    is assembled by whatever executes this; what this model is for is the property that the
    assembly covered everywhere, which is the part that cannot be checked once the document
    has been written.
    """

    subject_id: str
    at: datetime
    holdings: tuple[StoreHolding, ...]

    def __post_init__(self) -> None:
        if not self.subject_id:
            msg = "a subject access request with no subject is about everybody"
            raise ErasureError(msg)
        if self.at.tzinfo is None:
            msg = "a naive assembly time compares wrongly against an aware one"
            raise ErasureError(msg)
        covered = {one.store for one in self.holdings}
        if covered != set(Store):
            missing = sorted(store.value for store in set(Store) - covered)
            msg = (
                f"a subject access request that omits {missing} says it is everything and "
                "is not; see A_STORE_LEFT_OUT_OF_A_SUBJECT_ACCESS_REQUEST_IS_A_LIE"
            )
            raise ErasureError(msg)

    @property
    def complete(self) -> bool:
        """Whether every store was actually searched. Not whether anything was found."""
        return all(one.reached for one in self.holdings)

    @property
    def items(self) -> int:
        return sum(one.items for one in self.holdings)

    def unreached(self) -> tuple[Store, ...]:
        return tuple(one.store for one in self.holdings if not one.reached)

    def lines(self) -> tuple[str, ...]:
        body = tuple(one.line() for one in self.holdings)
        if self.complete:
            return body
        names = ", ".join(store.value for store in self.unreached())
        return (*body, f"incomplete: {names} could not be searched")


def assemble(
    *,
    subject_id: str,
    at: datetime,
    found: Mapping[Store, int],
    unreachable: Iterable[Store] = (),
) -> SubjectAccess:
    """Assemble a subject access request over every store there is.

    Built by iterating `Store`, not by iterating `found`. Iterating what the caller passed
    produces a document about the stores somebody remembered; iterating the enum produces a
    document about the stores that exist, with the ones nobody reached named in it. Only the
    second can be wrong out loud.

    A store in neither `found` nor `unreachable` is a store that reported nothing, which is
    a legitimate answer and is recorded as zero. That is not the same as unreachable and the
    caller has to say which, because the two differ only in the caller's knowledge and the
    document cannot recover the difference afterwards.
    """
    if unknown := sorted(str(store) for store in set(found) - set(Store)):
        # Unreachable through the type checker, and reachable from a mapping built by name
        # somewhere upstream. A key nobody recognises is quietly dropped by a lookup.
        msg = f"a count was reported for {unknown}, which is not a store"
        raise ErasureError(msg)
    could_not = set(unreachable)
    holdings = tuple(
        StoreHolding(
            store=store,
            data_class=data_class_of(store),
            items=0 if store in could_not else found.get(store, 0),
            reached=store not in could_not,
            holds=facts_for(store).holds,
        )
        for store in Store
    )
    return SubjectAccess(subject_id=subject_id, at=at, holdings=holdings)


# ------------------------------------------------------- M25.2.2  the deletion fan-out
class StoreEraser(Protocol):
    """What an executor must offer. **Not implemented anywhere in this repository yet.**

    Stated as a protocol and said out loud rather than left to be noticed: everything in
    this module decides, reports and refuses, and something holding a database session, a
    Valkey client and an S3 client has to do the removing. The split is
    `brain.ops.limits` and `brain.ops.limit_store` again, and the reason is the same one:
    the interesting case is the store that could not be reached, and a module that opened
    its own connections could not be made to fail that way in a test.
    """

    def count_for(self, store: Store, subject_id: str) -> int:
        """How many items this store holds about the subject."""
        ...

    def erase(self, store: Store, subject_id: str) -> int:
        """Remove them. Returns how many went."""
        ...


@dataclass(frozen=True)
class Erased:
    """What happened in one store. A count and a disposition, never a copy of what went."""

    store: Store
    disposition: Disposition
    removed: int
    reached: bool

    def __post_init__(self) -> None:
        if self.removed < 0:
            msg = f"{self.store.value} reported a negative number removed"
            raise ErasureError(msg)
        if self.removed and self.disposition in (Disposition.ROTATES_OUT, Disposition.RETAINED):
            # The line that would make a certificate false. Nothing is removed from a backup
            # or from the audit chain by this path, so a count claiming otherwise is either
            # a bug or a store that has quietly started being deleted from.
            msg = (
                f"{self.store.value} is {self.disposition.value} and reports "
                f"{self.removed} removed; a deletion does not reach it and a certificate "
                "saying it did would be false"
            )
            raise ErasureError(msg)
        if not self.reached and self.removed:
            msg = f"{self.store.value} was not reached and reports {self.removed} removed"
            raise ErasureError(msg)

    def line(self) -> str:
        if not self.reached:
            return f"{self.store.value}: not reached, so nothing was removed from it"
        match self.disposition:
            case Disposition.ERASE:
                return f"{self.store.value}: {self.removed} record(s) removed"
            case Disposition.PURGE:
                return f"{self.store.value}: {self.removed} derived entr(y/ies) purged"
            case Disposition.ROTATES_OUT:
                return f"{self.store.value}: not reached by deletion; it rotates out"
            case Disposition.RETAINED:
                return f"{self.store.value}: retained deliberately and not deleted"
            case _:  # pragma: no cover - unreachable while Disposition is exhaustive
                assert_never(self.disposition)


@dataclass(frozen=True)
class Deletion:
    """One erasure request, carried out across every store (M25.2.2).

    Like `SubjectAccess`, it covers every member of `Store` by construction, so the question
    "did anybody look in the index" has an answer on the object rather than depending on
    whether the caller thought to include it.
    """

    subject_id: str
    requested_at: datetime
    completed_at: datetime
    results: tuple[Erased, ...]

    def __post_init__(self) -> None:
        if not self.subject_id:
            msg = "a deletion with no subject deletes everybody"
            raise ErasureError(msg)
        for name in ("requested_at", "completed_at"):
            if getattr(self, name).tzinfo is None:
                msg = f"a naive {name} compares wrongly against an aware one"
                raise ErasureError(msg)
        if self.completed_at < self.requested_at:
            msg = "a deletion that completed before it was requested has the wrong clock"
            raise ErasureError(msg)
        covered = {one.store for one in self.results}
        if covered != set(Store):
            missing = sorted(store.value for store in set(Store) - covered)
            msg = f"a deletion that never considered {missing} is not a deletion of everything"
            raise ErasureError(msg)

    @property
    def removed(self) -> int:
        return sum(one.removed for one in self.results)

    def unreached(self) -> tuple[Store, ...]:
        """Targets the executor could not reach. Stores a deletion never reaches are not here."""
        return tuple(
            one.store
            for one in self.results
            if not one.reached and one.disposition in (Disposition.ERASE, Disposition.PURGE)
        )

    @property
    def complete(self) -> bool:
        return not self.unreached()

    def lines(self) -> tuple[str, ...]:
        return tuple(one.line() for one in self.results)


def erase(
    *,
    subject_id: str,
    requested_at: datetime,
    completed_at: datetime,
    removed: Mapping[Store, int],
    unreachable: Iterable[Store] = (),
    holds: Iterable[Hold] = (),
) -> Deletion:
    """Record a deletion across every store, refusing outright if the subject is held.

    The refusal is first and is not partial. Deleting from the stores a hold does not care
    about, and reporting the rest as pending, would produce a subject whose data is half
    gone: the dispute the hold was placed for now has an incomplete record, and nothing
    anywhere says which half is missing. See `A_HELD_SUBJECT_IS_NOT_ERASED`.

    Counts for the stores a deletion does not reach are refused rather than ignored, because
    a caller reporting three rows removed from a backup has either done something this
    module says is impossible or is about to have it written on a certificate.
    """
    if active := holds_over(subject_id, holds, requested_at):
        names = ", ".join(sorted({hold_id(one) for one in active}))
        msg = (
            f"{subject_id} is under {len(active)} active legal hold(s) ({names}); an "
            "erasure is refused until they are released"
        )
        raise ErasureError(msg)
    if unknown := sorted(str(store) for store in set(removed) - set(Store)):
        msg = f"a removal count was reported for {unknown}, which is not a store"
        raise ErasureError(msg)
    could_not = set(unreachable)
    results = tuple(
        Erased(
            store=store,
            disposition=disposition_of(store),
            removed=0 if store in could_not else removed.get(store, 0),
            reached=store not in could_not,
        )
        for store in deletion_order()
    )
    return Deletion(
        subject_id=subject_id,
        requested_at=requested_at,
        completed_at=completed_at,
        results=results,
    )


def hold_id(hold: Hold) -> str:
    """A hold's identifier where it has one, for a refusal message that names something.

    `getattr` rather than putting `id` in the protocol, because an identifier is not
    something an erasure needs in order to *decide*: the decision is made from `subjects`,
    `all_subjects` and `is_active`. Requiring an id in the protocol would make a test hold
    carry a field it does not use, and the message is the only consumer.
    """
    found = getattr(hold, "id", "")
    return found if isinstance(found, str) and found else "unnamed"


# ------------------------------------------------------- M25.2.3  what backups do not do
#: How long after a deletion a backup taken before it may still contain the data. Read from
#: the retention policy, which reads it from the bucket's own lifecycle rule, so there is
#: one number and it is the one the object store is actually configured with.
BACKUP_HORIZON_DAYS = BACKUP_RETENTION_DAYS


def backup_horizon(completed_at: datetime) -> datetime:
    """When the last backup that could contain the deleted data rotates out.

    Measured from when the deletion completed rather than from when it was requested. The
    backup taken between the request and the completion still contains the data, and
    measuring from the request would put the honest date earlier than the truth, which is
    the direction that makes a certificate wrong.
    """
    if completed_at.tzinfo is None:
        msg = "a naive completion time gives a backup horizon at the machine's offset"
        raise ErasureError(msg)
    return completed_at + timedelta(days=BACKUP_HORIZON_DAYS)


# ------------------------------------------------------- M25.2.4  the certificate
@dataclass(frozen=True)
class Certificate:
    """What was removed, from where, and when. Never what it said (M25.2.4).

    Read the field list as the argument. There is a store, a class and a count per line, a
    subject id, two timestamps and a caveat. There is no field for a value, a row, a
    payload, an excerpt or a sample, and adding one would be an edit to a frozen model in a
    file whose docstring argues against it; see
    `A_CERTIFICATE_IS_NOT_A_COPY_OF_WHAT_IT_DELETED`.

    There is also no field that says "complete". The nearest thing is
    `recoverable_from_backup_until`, which is a date rather than a claim, and
    `is_beyond_backup_reach`, which takes a `now` and answers for that moment. A boolean
    stamped at issue time would be read as a promise about the future.
    """

    certificate_id: str
    subject_id: str
    requested_at: datetime
    completed_at: datetime
    #: One entry per store, in deletion order. Counts and dispositions only.
    removed: tuple[Erased, ...]
    #: After this moment no backup taken before the deletion still exists.
    recoverable_from_backup_until: datetime
    #: The honest limit, in words, on the document itself rather than in a covering note.
    caveat: str = DELETION_DOES_NOT_REACH_A_BACKUP_ALREADY_WRITTEN

    def __post_init__(self) -> None:
        for name in ("certificate_id", "subject_id"):
            if not getattr(self, name):
                msg = f"a certificate with no {name} certifies nothing anybody can look up"
                raise ErasureError(msg)
        if not self.caveat.strip():
            msg = (
                "a certificate with no caveat reads as a claim that the data is gone "
                "everywhere, which is not true while a backup taken before it still exists"
            )
            raise ErasureError(msg)
        covered = {one.store for one in self.removed}
        if covered != set(Store):
            missing = sorted(store.value for store in set(Store) - covered)
            msg = f"a certificate silent about {missing} overstates what it certifies"
            raise ErasureError(msg)

    def count_for(self, store: Store) -> int:
        for one in self.removed:
            if one.store is store:
                return one.removed
        # Unreachable while the constructor requires every store, and kept as a raise
        # rather than a zero because a zero here would read as "nothing was in it".
        msg = f"this certificate says nothing about {store.value}"
        raise ErasureError(msg)

    @property
    def total_removed(self) -> int:
        return sum(one.removed for one in self.removed)

    def retained(self) -> tuple[Store, ...]:
        """Stores this deletion deliberately did not empty, named on the document."""
        return tuple(
            one.store
            for one in self.removed
            if one.disposition in (Disposition.ROTATES_OUT, Disposition.RETAINED)
        )

    def is_beyond_backup_reach(self, now: datetime) -> bool:
        """Whether every backup that could still contain this data has rotated out."""
        if now.tzinfo is None:
            msg = "a naive now compares wrongly against an aware horizon"
            raise ErasureError(msg)
        return now >= self.recoverable_from_backup_until

    def lines(self) -> tuple[str, ...]:
        """The document, in a fixed order. Every line is a count or a statement of limit."""
        named = ", ".join(store.value for store in self.retained())
        return (
            f"deletion {self.certificate_id} for {self.subject_id}",
            f"requested {self.requested_at.isoformat()}, completed {self.completed_at.isoformat()}",
            *(one.line() for one in self.removed),
            f"not reached by this deletion: {named}",
            (
                "a backup taken before this deletion still contains the data until "
                f"{self.recoverable_from_backup_until.isoformat()}"
            ),
        )


def certify(deletion: Deletion, *, certificate_id: str) -> Certificate:
    """Issue a certificate for a deletion that actually happened.

    **Refused when any target store was not reached**, and that refusal is the whole reason
    this is a function rather than a constructor call. A certificate is a document produced
    to be relied on, and one describing a deletion that reached every store but one
    will be read as saying the data is gone. The partial case already has a representation:
    the `Deletion` itself, which names what it could not reach. What must not exist is a
    certificate for it.

    Everything else the certificate says is carried over rather than recomputed, so there is
    no second opinion about what was removed. The backup horizon is computed, from the
    completion time, once.
    """
    if not certificate_id:
        msg = "a certificate needs an identifier; one nobody can cite proves nothing"
        raise ErasureError(msg)
    if missing := deletion.unreached():
        names = ", ".join(store.value for store in missing)
        msg = (
            f"{names} could not be reached, so this deletion did not happen everywhere and "
            "a certificate for it would say it did"
        )
        raise ErasureError(msg)
    return Certificate(
        certificate_id=certificate_id,
        subject_id=deletion.subject_id,
        requested_at=deletion.requested_at,
        completed_at=deletion.completed_at,
        removed=deletion.results,
        recoverable_from_backup_until=backup_horizon(deletion.completed_at),
    )


# ------------------------------------------------------------------ the structural checks
#: Field names that would turn a certificate into a copy of what it deleted.
_CONTENT_NAMES: frozenset[str] = frozenset(
    {
        "value",
        "values",
        "content",
        "text",
        "body",
        "rows",
        "payload",
        "sample",
        "excerpt",
        "snippet",
        "before",
        "old_value",
        "deleted_values",
    }
)


#: The four stores M25.2.2 names by hand. Written down so the check below is against a
#: stated requirement rather than against whatever `disposition_of` currently returns, which
#: would be the constant compared against itself.
MUST_PROPAGATE_TO: tuple[Store, ...] = (Store.CACHE, Store.INDEX, Store.MEMORY, Store.PROJECTION)

#: The models a deletion record could grow a copy of the deleted data on.
ERASURE_MODELS: tuple[type, ...] = (Certificate, Erased, StoreHolding, SubjectAccess, Deletion)


def erasure_gaps(
    stores: Sequence[Store] | None = None,
    dispositions: Callable[[Store], Disposition] | None = None,
    models: Sequence[type] | None = None,
) -> tuple[str, ...]:
    """Every way this module has stopped covering the system, or started copying it.

    Three families. The store list must still be the enum, so a subject access request
    covers everything there is. The four stores M25.2.2 names by hand must still be reached
    by a deletion, which is what catches somebody moving the cache to `ROTATES_OUT` because
    a purge was inconvenient. And no model here may carry a field that holds content.

    All three inputs are parameters defaulting to this module's own, for the reason
    `brain.ops.tracing.retention_gaps` takes one: a check that can only ever be run against
    the constant beside it cannot be shown to fail, and a check nobody has seen fail is a
    check nobody knows works. `dispositions` in particular is what lets a test ask what this
    would say if the cache stopped being purged, which is the finding that matters and is
    otherwise unreachable while the declarations are correct.
    """
    considered = tuple(Store) if stores is None else tuple(stores)
    decide = disposition_of if dispositions is None else dispositions
    findings: list[str] = []

    for store in considered:
        if store not in subject_access_stores():
            findings.append(
                f"{store.value} exists and no subject access request looks in it; see "
                "A_STORE_LEFT_OUT_OF_A_SUBJECT_ACCESS_REQUEST_IS_A_LIE"
            )

    reached = {
        store for store in considered if decide(store) in (Disposition.ERASE, Disposition.PURGE)
    }
    for store in MUST_PROPAGATE_TO:
        if store in considered and store not in reached:
            findings.append(
                f"a deletion does not reach {store.value}, which M25.2.2 names as one of "
                "the four it must propagate to"
            )

    # A check on `deletion_order` itself rather than on the ranks it sorted by: the finding
    # fires if that function stops ordering (sorted by name, say, which reads as tidier and
    # puts `cache` third).
    ranks = [_ORDER[disposition_of(store)] for store in deletion_order()]
    if ranks != sorted(ranks):
        findings.append(
            "a derived copy is purged before its source; see "
            "A_DERIVED_COPY_PURGED_BEFORE_ITS_SOURCE_IS_REPOPULATED"
        )

    for model in ERASURE_MODELS if models is None else tuple(models):
        names = {f.name for f in fields(model)}
        for forbidden in sorted(names & _CONTENT_NAMES):
            findings.append(
                f"{model.__name__} carries {forbidden}, which makes the record of a "
                "deletion a second copy of what was deleted"
            )
    return tuple(findings)
