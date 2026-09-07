"""Deletion and the subject access request, held to the two ways they lie quietly.

The first is omission. A subject access request that never searched one store comes back
looking complete, is signed, and is wrong; nobody receiving one can tell. So the tests below
assert coverage against `brain.ops.retention.Store` rather than against a list written here,
and the six stores M25.2.1 names are spelled out as a requirement so this file states the
leaf rather than restating the module.

The second is overstatement. A certificate is produced specifically to be relied on, so
every way it could claim more than happened is a test: a count from a store deletion does
not reach, a certificate for a deletion that failed halfway, a completion claim made before
the last backup holding the data has rotated out.

The legal hold used throughout is `brain.audit.ledger.LegalHold`, the real one, because a
protocol checked only against a stub written in the test file is a protocol describing a
class that may no longer exist.

Task ids: M25.2.1, M25.2.2, M25.2.3, M25.2.4
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.ledger import LegalHold
from brain.memory.correction import (
    A_DELETED_MEMORY_CANNOT_EXPLAIN_ITSELF,
    Correction,
    Demotion,
    corrected,
)
from brain.ops.erasure import (
    DELETION_DOES_NOT_REACH_A_BACKUP_ALREADY_WRITTEN,
    MUST_PROPAGATE_TO,
    Certificate,
    Deletion,
    Disposition,
    Erased,
    ErasureError,
    Hold,
    StoreHolding,
    SubjectAccess,
    assemble,
    backup_horizon,
    certify,
    deletion_order,
    disposition_of,
    erase,
    erasure_gaps,
    erasure_targets,
    holds_over,
    subject_access_stores,
)
from brain.ops.retention import Store, data_class_of
from brain.ops.storage import bucket

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)

#: The six stores M25.2.1 names, and the four M25.2.2 names, written out here rather than
#: imported, so these tests assert the tracker's requirement rather than the module's
#: current opinion of it.
ASSEMBLED_FROM = (
    Store.ROWS,
    Store.PROJECTION,
    Store.MEMORY,
    Store.TRACE,
    Store.RECORDING,
    Store.BACKUP,
)
PROPAGATES_TO = (Store.CACHE, Store.INDEX, Store.MEMORY, Store.PROJECTION)


def _hold(
    *,
    subjects: frozenset[str] = frozenset({"p_ada"}),
    all_subjects: bool = False,
    placed_at: datetime = NOW - timedelta(days=1),
    released_at: datetime | None = None,
) -> LegalHold:
    """A real `LegalHold`, active now, over one subject unless told otherwise."""
    return LegalHold(
        id="hold-1",
        reason_code="employment_dispute",
        subjects=subjects,
        all_subjects=all_subjects,
        placed_at=placed_at,
        released_at=released_at,
    )


# ------------------------------------------------ M25.2.1  the subject access request
def test_a_subject_access_request_covers_every_store_there_is() -> None:
    """**The property the whole module is arranged around.**

    A subject access request is a document saying "this is everything we hold about you". It
    is assembled by iterating `Store`, so the six the tracker names are covered because
    everything is covered, rather than because somebody remembered six.

    Both assertions matter. The first is the requirement as written down in M25.2.1; the
    second is the stronger property that makes the first survive a new store being added.

    Delete this and a section can be dropped from the assembly for any reason at all, and
    the document that comes out still reads as complete."""
    request = assemble(subject_id="p_ada", at=NOW, found={Store.MEMORY: 3})

    covered = {one.store for one in request.holdings}
    assert set(ASSEMBLED_FROM) <= covered
    assert covered == set(Store)
    assert covered == set(subject_access_stores())


def test_a_subject_access_request_missing_a_store_cannot_be_constructed_at_all() -> None:
    """The structural half. Iterating the enum is the implementation; this is the guard that
    catches somebody assembling one by hand somewhere else.

    A `SubjectAccess` built from thirteen holdings is refused by its own constructor and the
    message names which are missing, so a caller who assembled it another way finds out at
    the point of construction rather than at the point of signature.

    Delete this and a second assembly path, written for the console or for a test fixture,
    produces a shorter document that no type or check anywhere rejects."""
    partial = tuple(
        StoreHolding(
            store=store,
            data_class=data_class_of(store),
            items=0,
            reached=True,
            holds="whatever",
        )
        for store in Store
        if store is not Store.RECORDING
    )

    with pytest.raises(ErasureError, match=r"omits \['recording'\]"):
        SubjectAccess(subject_id="p_ada", at=NOW, holdings=partial)


def test_a_store_that_could_not_be_searched_is_named_rather_than_counted_as_empty() -> None:
    """ "We looked and found nothing" and "we could not look" must not render the same way.

    They differ only in the caller's knowledge, and once the document is written the
    difference cannot be recovered from it. So an unreachable store is marked, named in the
    lines, and makes the whole request incomplete.

    Delete this and an object store that was down during the assembly reads as a person with
    no recordings."""
    request = assemble(
        subject_id="p_ada",
        at=NOW,
        found={Store.MEMORY: 2},
        unreachable=(Store.RECORDING,),
    )

    assert not request.complete
    assert request.unreached() == (Store.RECORDING,)
    assert any("could not be searched" in line for line in request.lines())
    recording = next(one for one in request.holdings if one.store is Store.RECORDING)
    assert recording.items == 0
    assert not recording.reached


def test_a_request_that_reached_everywhere_is_complete_and_counts_what_it_found() -> None:
    """The positive sibling, without which every assertion above is satisfied by an assembly
    that always reports itself incomplete.

    A completeness flag that is never true is one nobody reads after the first week, and a
    request that can never be complete cannot be sent to anybody.

    Delete this and `complete` can be hard-coded to False with nothing failing."""
    request = assemble(subject_id="p_ada", at=NOW, found={Store.MEMORY: 3, Store.TRACE: 9})

    assert request.complete
    assert request.unreached() == ()
    assert request.items == 12
    assert all("could not be searched" not in line for line in request.lines())


def test_a_count_reported_for_something_that_is_not_a_store_is_refused() -> None:
    """A mapping assembled upstream by name can carry a key nothing recognises, and a lookup
    drops it silently.

    That is a count of somebody's data going missing from the document with nothing anywhere
    saying so, which is the same failure as a store nobody searched arriving by a different
    route.

    Delete this and a typo in an executor's store name removes a whole section quietly."""
    with pytest.raises(ErasureError, match="which is not a store"):
        assemble(subject_id="p_ada", at=NOW, found={"recordings": 4})  # type: ignore[dict-item]


def test_a_holding_cannot_report_items_from_a_store_it_could_not_reach() -> None:
    """Two contradictory statements on one row, and the count is the one a reader believes.

    Delete this and a partial failure in an executor produces a row saying both that it
    could not look and that it found four things."""
    with pytest.raises(ErasureError, match="one of those is not true"):
        StoreHolding(
            store=Store.CACHE,
            data_class=data_class_of(Store.CACHE),
            items=4,
            reached=False,
            holds="answers computed for them",
        )


# ------------------------------------------------------- M25.2.2  the deletion fan-out
def test_a_deletion_reaches_the_cache_the_index_memory_and_the_projection() -> None:
    """M25.2.2 names four stores that a deletion must propagate to, and they are the four
    that get forgotten: none of them is the record, so none of them looks like data.

    The four are written out in this file rather than imported from the module, so this
    asserts the leaf rather than whatever `disposition_of` currently returns.

    Delete this and moving the cache to "rotates out" because a purge was inconvenient
    leaves a deleted person answerable from cache with every log line saying otherwise."""
    reached = set(erasure_targets())

    assert set(PROPAGATES_TO) <= reached
    assert set(MUST_PROPAGATE_TO) == set(PROPAGATES_TO)
    for store in PROPAGATES_TO:
        assert disposition_of(store) in (Disposition.ERASE, Disposition.PURGE)


def test_a_deletion_that_stopped_reaching_the_cache_is_reported() -> None:
    """The negative sibling, asked of a fabricated disposition rather than of the real one.

    `erasure_gaps` takes the disposition function as a parameter for exactly this: the
    finding that matters is unreachable while the declarations are correct, so a check that
    could only be run against them has never been seen to produce it.

    Delete this and the four-store rule is a branch that has never executed."""
    findings = erasure_gaps(
        dispositions=lambda store: (
            Disposition.ROTATES_OUT if store is Store.CACHE else disposition_of(store)
        )
    )

    assert any("does not reach cache" in one for one in findings)
    assert erasure_gaps() == ()


def test_a_source_is_deleted_before_the_copies_made_from_it() -> None:
    """Order is the difference between a bounded failure and a silent one.

    Purge the cache first and the next question rebuilds it from rows that are still there.
    Delete the source first and the cache is stale until the purge lands. The first is wrong
    permanently and reads as success; the second is wrong for seconds.

    Asserted on positions in the real order rather than on the sort key, so rewriting
    `deletion_order` to sort by name fails here.

    Delete this and the fan-out order becomes alphabetical, which puts `cache` third."""
    order = deletion_order()
    place = {store: index for index, store in enumerate(order)}

    assert set(order) == set(Store)
    for source in (Store.ROWS, Store.MEMORY, Store.PROJECTION, Store.KNOWLEDGE):
        for derived in (Store.CACHE, Store.INDEX):
            assert place[source] < place[derived], f"{derived} is purged before {source}"


def test_an_erasure_removes_a_memory_although_a_correction_never_deletes_one() -> None:
    """The boundary with `brain.memory.correction`, asserted in both directions at once.

    That module is right that a deleted memory cannot explain itself, and it has no member
    of `Correction` meaning "removed" so that the operation cannot arrive by accident. This
    module reaches memory anyway, because a person exercising a right over their own data is
    not satisfied by a mark: a marked memory is a stored memory.

    The contrast is asserted on what survives each operation rather than on the prose either
    module writes about it. A correction leaves the memory nameable: `corrected` hands back
    its id, which is what answers "why did it stop saying that". An erasure leaves a count
    and nothing else, which is the point and is also the cost.

    Delete this and the two modules drift into agreeing, which means either a correction
    starts deleting or an erasure stops reaching memory, and both are wrong in a way nobody
    would notice from inside either file."""
    assert Store.MEMORY in erasure_targets()
    assert disposition_of(Store.MEMORY) is Disposition.ERASE
    assert {one.value for one in Correction} == {"superseded", "demoted"}
    assert A_DELETED_MEMORY_CANNOT_EXPLAIN_ITSELF.strip()

    marked = corrected(demotions=[Demotion(memory_id="m_1", field="client.renewal", at=NOW)])
    assert marked == frozenset({"m_1"})

    deletion = erase(
        subject_id="p_ada", requested_at=NOW, completed_at=LATER, removed={Store.MEMORY: 1}
    )
    gone = next(one for one in deletion.results if one.store is Store.MEMORY)
    assert gone.removed == 1
    assert {f.name for f in fields(Erased)} == {"store", "disposition", "removed", "reached"}


def test_a_deletion_covers_every_store_and_counts_only_what_it_removed() -> None:
    """The positive case for the fan-out: an ordinary deletion, with the counts arriving
    where the executor put them.

    Delete this and every other assertion in this section is satisfied by a function that
    refuses everything."""
    deletion = erase(
        subject_id="p_ada",
        requested_at=NOW,
        completed_at=LATER,
        removed={Store.MEMORY: 3, Store.CACHE: 7, Store.ROWS: 1},
    )

    assert {one.store for one in deletion.results} == set(Store)
    assert deletion.removed == 11
    assert deletion.complete
    assert deletion.unreached() == ()


def test_a_deletion_cannot_claim_to_have_removed_anything_from_a_backup() -> None:
    """The line that would put a false statement on a certificate.

    Nothing in this system reaches inside a backup or prunes the audit chain by this path,
    so a count claiming otherwise is either a bug in an executor or a store that has quietly
    started being deleted from. Either way it must not reach the document.

    Delete this and an executor reporting "backups: 4 removed" produces a certificate saying
    the data is gone from the backups, which is the exact claim M25.2.3 exists to prevent."""
    with pytest.raises(ErasureError, match="a deletion does not reach it"):
        erase(
            subject_id="p_ada",
            requested_at=NOW,
            completed_at=LATER,
            removed={Store.BACKUP: 4},
        )

    with pytest.raises(ErasureError, match="a deletion does not reach it"):
        Erased(store=Store.AUDIT, disposition=Disposition.RETAINED, removed=1, reached=True)


def test_an_export_already_produced_is_not_reached_by_a_deletion_either() -> None:
    """The limit nobody expects, sitting beside the one everybody does.

    An export that has been handed over is a copy with the permissions stripped off, and a
    deletion cannot recall it any more than it can edit a backup. It rotates out on the
    exports bucket's own lifecycle rule and the certificate names it.

    Delete this and an export is quietly treated as a store a deletion empties, which is a
    claim about files that have already left the building."""
    assert disposition_of(Store.EXPORT) is Disposition.ROTATES_OUT
    assert Store.EXPORT not in erasure_targets()


# --------------------------------------------------- M25.2.3  what a backup does not do
def test_the_backup_horizon_is_the_bucket_lifecycle_and_runs_from_completion() -> None:
    """The date the certificate stands or falls on.

    Two properties. It is the backups bucket's own lifecycle rule, imported rather than
    retyped, because a second copy of 35 would drift and the drift would move a promised
    date. And it runs from completion rather than from the request, because a backup taken
    between the two still contains the data and measuring from the request would put the
    date earlier than the truth.

    Delete this and the horizon is whatever number was nearest, in a document a regulator
    reads."""
    kept = bucket("backups").retention_days
    assert kept is not None

    assert backup_horizon(LATER) == LATER + timedelta(days=kept)
    assert backup_horizon(LATER) > backup_horizon(NOW)

    with pytest.raises(ErasureError, match="naive completion time"):
        backup_horizon(datetime(2026, 9, 7, 9, 0))


def test_the_honest_limit_is_written_down_and_says_what_a_deletion_does_not_reach() -> None:
    """M25.2.3 is a policy and its honest limits, and the limits are the part that gets
    dropped when somebody summarises.

    So they are a named constant, which is how a rule survives the person who wrote it, and
    the constant is on every certificate rather than in a covering note that gets detached.

    Delete this and the caveat becomes an empty string that no test notices."""
    assert "does not reach inside a backup" in DELETION_DOES_NOT_REACH_A_BACKUP_ALREADY_WRITTEN
    assert "rotates out" in DELETION_DOES_NOT_REACH_A_BACKUP_ALREADY_WRITTEN

    deletion = erase(subject_id="p_ada", requested_at=NOW, completed_at=LATER, removed={})
    certificate = certify(deletion, certificate_id="c-1")
    assert certificate.caveat == DELETION_DOES_NOT_REACH_A_BACKUP_ALREADY_WRITTEN


# ------------------------------------------------------------ M25.2.4  the certificate
def test_a_certificate_has_nowhere_to_put_what_it_deleted() -> None:
    """**The structural half of `A_CERTIFICATE_IS_NOT_A_COPY_OF_WHAT_IT_DELETED`.**

    The prose says a certificate must not carry the values; this says there is no attribute
    to carry them in. A rule stated in a docstring holds until somebody has a bad afternoon,
    and "include the rows for debugging" is a change somebody makes at the end of a long
    week.

    Checked on every model in the deletion path, not only on the certificate, because the
    field would be added wherever it was convenient and copied forward.

    Delete this and `deleted_values: tuple[str, ...] = ()` appears on `Erased`, and every
    other test here passes because none of them construct one with it set."""
    forbidden = (
        "value",
        "values",
        "content",
        "text",
        "body",
        "rows",
        "payload",
        "sample",
        "excerpt",
        "deleted_values",
    )

    for model in (Certificate, Erased, StoreHolding, SubjectAccess, Deletion):
        names = {f.name for f in fields(model)}
        for name in forbidden:
            assert name not in names, f"{model.__name__} can carry a {name}"

    @dataclass(frozen=True)
    class Chatty:
        store: Store
        deleted_values: tuple[str, ...]

    assert any("Chatty carries deleted_values" in one for one in erasure_gaps(models=[Chatty]))


def test_a_certificate_states_the_backup_horizon_rather_than_claiming_completion() -> None:
    """A certificate that says "complete" on the day it is issued is false for the next
    thirty-five days, in a document produced to be relied on.

    So there is no completion field. `is_beyond_backup_reach` takes a moment and answers for
    that moment, which is the only honest shape: the answer changes with time and a stamped
    boolean would not.

    Delete this and `complete: bool = True` is added to the model for a console badge."""
    deletion = erase(
        subject_id="p_ada", requested_at=NOW, completed_at=LATER, removed={Store.MEMORY: 2}
    )
    certificate = certify(deletion, certificate_id="c-1")
    kept = bucket("backups").retention_days
    assert kept is not None

    names = {f.name for f in fields(Certificate)}
    assert "complete" not in names
    assert "completed" not in names

    assert not certificate.is_beyond_backup_reach(LATER)
    assert not certificate.is_beyond_backup_reach(LATER + timedelta(days=kept, seconds=-1))
    assert certificate.is_beyond_backup_reach(LATER + timedelta(days=kept))
    assert any("still contains the data until" in line for line in certificate.lines())


def test_a_certificate_names_the_stores_a_deletion_did_not_empty() -> None:
    """The other half of not overstating: the document says where the data still is.

    Backups, exports already handed over and the audit chain are all named, so a reader can
    see the shape of what remains rather than inferring it from silence.

    Delete this and a certificate lists twelve stores it emptied and says nothing about the
    three it did not, which reads as three stores that were empty."""
    deletion = erase(subject_id="p_ada", requested_at=NOW, completed_at=LATER, removed={})
    certificate = certify(deletion, certificate_id="c-1")

    assert set(certificate.retained()) == {Store.BACKUP, Store.EXPORT, Store.AUDIT}
    assert any("not reached by this deletion" in line for line in certificate.lines())


def test_a_certificate_counts_per_store_and_the_counts_are_what_was_removed() -> None:
    """The positive case: a certificate that is useful as well as honest.

    A document that refused to say anything would satisfy every constraint above and be
    worth nothing to the person who asked for the deletion.

    Delete this and the certificate can be reduced to a caveat with no counts on it."""
    deletion = erase(
        subject_id="p_ada",
        requested_at=NOW,
        completed_at=LATER,
        removed={Store.MEMORY: 3, Store.INDEX: 5},
    )
    certificate = certify(deletion, certificate_id="c-1")

    assert certificate.count_for(Store.MEMORY) == 3
    assert certificate.count_for(Store.INDEX) == 5
    assert certificate.count_for(Store.ROWS) == 0
    assert certificate.total_removed == 8
    assert certificate.subject_id == "p_ada"


def test_a_certificate_is_refused_for_a_deletion_that_could_not_reach_a_store() -> None:
    """A certificate for a partial deletion will be read as saying the data is gone.

    The partial case already has a representation, which is the `Deletion` itself, and it
    names what it could not reach. What must not exist is a certificate for it.

    Delete this and a deletion that failed against the object store is certified as done,
    and the person who asked has a signed document saying so."""
    partial = erase(
        subject_id="p_ada",
        requested_at=NOW,
        completed_at=LATER,
        removed={Store.MEMORY: 1},
        unreachable=(Store.RECORDING,),
    )

    assert partial.unreached() == (Store.RECORDING,)
    with pytest.raises(ErasureError, match="could not be reached"):
        certify(partial, certificate_id="c-1")


def test_a_certificate_needs_an_identifier_and_covers_every_store() -> None:
    """Two ways a certificate could refer to nothing or say less than it appears to.

    Delete this and a certificate with no id proves nothing, and one assembled by hand from
    twelve results overstates by omission."""
    deletion = erase(subject_id="p_ada", requested_at=NOW, completed_at=LATER, removed={})

    with pytest.raises(ErasureError, match="needs an identifier"):
        certify(deletion, certificate_id="")

    with pytest.raises(ErasureError, match="silent about"):
        Certificate(
            certificate_id="c-1",
            subject_id="p_ada",
            requested_at=NOW,
            completed_at=LATER,
            removed=deletion.results[:-1],
            recoverable_from_backup_until=backup_horizon(LATER),
        )


def test_a_deletion_that_completed_before_it_was_requested_is_refused() -> None:
    """A clock running backwards makes the backup horizon wrong in the dangerous direction.

    Delete this and two containers with different clocks produce a certificate promising an
    earlier date than the truth."""
    with pytest.raises(ErasureError, match="wrong clock"):
        erase(subject_id="p_ada", requested_at=LATER, completed_at=NOW, removed={Store.MEMORY: 1})


# ------------------------------------------------------------------------ legal holds
def test_an_erasure_is_refused_while_a_legal_hold_reaches_the_subject() -> None:
    """A hold is placed because somebody outside this system decided the data must survive.

    Running the erasure anyway destroys evidence in a live dispute and issues a certificate
    saying so. The refusal names the hold, so whoever asked can find out why.

    Delete this and an erasure request submitted during a dispute is carried out, and there
    is no undo."""
    with pytest.raises(ErasureError, match="active legal hold"):
        erase(
            subject_id="p_ada",
            requested_at=NOW,
            completed_at=LATER,
            removed={Store.MEMORY: 1},
            holds=[_hold()],
        )


def test_a_released_or_not_yet_placed_hold_does_not_stop_an_erasure() -> None:
    """The positive sibling, and it is three siblings rather than one.

    A guard tested only by its refusals is satisfied by a function that refuses everything,
    and this one would then suspend every erasure in the company forever. A released hold, a
    hold placed in the future and a hold over somebody else all leave the erasure running.

    Delete this and any hold anywhere blocks every deletion, which looks like compliance and
    is a permanent failure to honour a right."""
    released = _hold(released_at=NOW - timedelta(hours=1))
    future = _hold(placed_at=NOW + timedelta(days=1))
    other = _hold(subjects=frozenset({"p_ben"}))

    for hold in (released, future, other):
        deletion = erase(
            subject_id="p_ada",
            requested_at=NOW,
            completed_at=LATER,
            removed={Store.MEMORY: 1},
            holds=[hold],
        )
        assert deletion.removed == 1

    assert holds_over("p_ada", [released, future, other], NOW) == ()


def test_a_company_wide_hold_reaches_a_subject_it_does_not_name() -> None:
    """`all_subjects` is explicit on `LegalHold` precisely because "no subjects named" would
    otherwise read as "everybody" by accident. It must still mean everybody when it is set.

    Delete this and a company-wide hold suspends nothing, which is the failure the hold's own
    constructor was written to prevent, arriving one module later."""
    everybody = _hold(subjects=frozenset(), all_subjects=True)

    assert holds_over("p_ada", [everybody], NOW) == (everybody,)
    with pytest.raises(ErasureError, match="active legal hold"):
        erase(
            subject_id="p_ada",
            requested_at=NOW,
            completed_at=LATER,
            removed={},
            holds=[everybody],
        )


def test_a_hold_over_an_actor_does_not_suspend_that_persons_own_erasure() -> None:
    """A hold naming actors is a hold about who did something. An erasure is about whose data
    it is, and the two are different questions about the same identifier.

    Reading `actors` here would suspend the erasure of anybody who happened to administer
    something under dispute, indefinitely and for a reason nobody could explain to them.

    Delete this and `actors` gets added to the predicate during a refactor because it looks
    like a field that was missed."""
    over_actor = LegalHold(
        id="hold-2",
        reason_code="employment_dispute",
        actors=frozenset({"p_ada"}),
        placed_at=NOW - timedelta(days=1),
    )

    assert holds_over("p_ada", [over_actor], NOW) == ()
    deletion = erase(
        subject_id="p_ada",
        requested_at=NOW,
        completed_at=LATER,
        removed={Store.MEMORY: 1},
        holds=[over_actor],
    )
    assert deletion.removed == 1


def test_a_subject_access_request_still_assembles_while_a_hold_suspends_deletion() -> None:
    """A hold suspends deletion. It does not suspend a person's right to know what is held.

    Conflating the two is easy and one-directional: refusing the request as well looks
    cautious and is a second failure to honour a right, on top of the one the hold already
    forces.

    Delete this and a held subject is told nothing at all, which nobody would notice because
    the hold is a reasonable-sounding explanation for both refusals."""
    request = assemble(subject_id="p_ada", at=NOW, found={Store.MEMORY: 3})

    assert request.complete
    assert request.items == 3


def test_the_real_legal_hold_satisfies_the_protocol_without_adaptation() -> None:
    """`Hold` is a protocol so that this module stays underneath the audit package, and a
    protocol never checked against the real type is a description of a class that may have
    changed.

    The assignment is what the type checker reads; the call is what proves the runtime shape
    matches too, because a structural match mypy accepts can still be a class whose
    `is_active` means something else.

    Delete this and `LegalHold` grows a different signature, mypy has nothing to compare, and
    every hold silently stops reaching anybody."""
    hold: Hold = _hold()

    assert hold.is_active(NOW)
    assert "p_ada" in hold.subjects
    assert not hold.all_subjects
    assert holds_over("p_ada", [hold], NOW) == (hold,)
