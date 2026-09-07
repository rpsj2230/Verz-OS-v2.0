"""A client leaving with their data, and an install that leaves nothing behind.

Task ids: M41.2.6
"""

from __future__ import annotations

from dataclasses import dataclass, is_dataclass
from datetime import UTC, datetime, timedelta

import pytest

import brain.ops.handover as handover_module
from brain.ops.erasure import StoreHolding, deletion_order
from brain.ops.handover import (
    HANDOVER_MODELS,
    Certificate,
    Handover,
    HandoverError,
    Removed,
    Residue,
    Return,
    TeardownPlan,
    assemble_return,
    certify,
    handover_gaps,
    plan_teardown,
    teardown_order,
)
from brain.ops.handover import Reason as HandoverReason
from brain.ops.retention import BACKUP_RETENTION_DAYS, Store, data_class_of, facts_for

REQUESTED = datetime(2026, 1, 6, 9, 0, tzinfo=UTC)
RETURNED = datetime(2026, 1, 7, 9, 0, tzinfo=UTC)
FINISHED = datetime(2026, 1, 8, 9, 0, tzinfo=UTC)


def _handover(**over: object) -> Handover:
    base: dict[str, object] = {
        "handover_id": "hand-0001",
        "reason": HandoverReason.CONTRACT_ENDED,
        "instructed_by": "the client's board",
        "instruction_reference": "termination letter, clause 9",
        "requested_at": REQUESTED,
    }
    base.update(over)
    return Handover(**base)  # type: ignore[arg-type]


def _return(**over: object) -> Return:
    return assemble_return(
        handover=over.pop("handover", _handover()),  # type: ignore[arg-type]
        at=RETURNED,
        found=over.pop("found", {Store.ROWS: 12, Store.AUDIT: 4_102}),  # type: ignore[arg-type]
        unreachable=over.pop("unreachable", ()),  # type: ignore[arg-type]
    )


def _removed(*, missing: object = None, outstanding: object = None) -> list[Removed]:
    everything: list[Store | Residue] = [*Store, *Residue]
    return [
        Removed(what=one, items=1, completed=one is not outstanding)
        if one is not outstanding
        else Removed(what=one, items=0, completed=False)
        for one in everything
        if one is not missing
    ]


# ------------------------------------------------------------------ the return
def test_a_return_covers_every_store_there_is() -> None:
    """A document that says "this is everything we hold" and omits a store is false, and
    nothing about it looks wrong: the client receives it, signs for it, and the omission is
    found years later or never.

    Deleting this lets a store be filtered out of the assembly, and the filter would be added
    for a good reason on the day one store was slow to read.
    """
    returned = _return()
    assert {one.store for one in returned.holdings} == set(Store)
    assert len(returned.holdings) == len(Store)


def test_a_return_that_omits_a_store_cannot_be_constructed() -> None:
    """The assembly iterates the enum, so the omission would have to be built by hand. This
    refuses the hand-built one, which is what a caller assembling sections from a query
    result would produce.

    Deleting this leaves the coverage rule enforced only inside the one function that
    already satisfies it.
    """
    short = tuple(one for one in _return().holdings if one.store is not Store.AUDIT)
    with pytest.raises(HandoverError, match="says it is everything"):
        Return(handover=_handover(), at=RETURNED, holdings=short)


def test_a_store_that_could_not_be_read_is_named_rather_than_counted_as_empty() -> None:
    """ "We looked and found nothing" and "we could not look" must never render alike. A
    return built from the second while reading like the first is the failure the whole module
    is arranged against.

    Deleting this lets an unreadable store report zero, and zero is what the client is told
    they are owed.
    """
    returned = _return(unreachable=(Store.RECORDING,))
    assert not returned.complete
    assert returned.unreached() == (Store.RECORDING,)
    recording = next(one for one in returned.holdings if one.store is Store.RECORDING)
    assert not recording.reached


def test_a_count_reported_for_something_that_is_not_a_store_is_refused() -> None:
    """A mapping built by name upstream can carry a key nothing recognises, and a lookup
    drops it silently. The return would then be missing whatever that key meant.

    Deleting this makes a typo in a store name into a section quietly reporting zero.
    """
    with pytest.raises(HandoverError, match="not a store"):
        assemble_return(
            handover=_handover(),
            at=RETURNED,
            found={"conversations": 4},  # type: ignore[dict-item]
        )


def test_a_handover_with_no_written_instruction_behind_it_is_refused() -> None:
    """A handover deletes an installation. The authority for it has to be citable afterwards,
    and a field that can be empty is a field that is empty on the day somebody is in a hurry.

    Deleting this leaves the reference optional, which makes it absent.
    """
    with pytest.raises(HandoverError, match="instruction_reference"):
        _handover(instruction_reference="  ")


# ------------------------------------------------------------------ the ordering rule
def test_a_teardown_cannot_be_planned_from_a_return_that_did_not_finish() -> None:
    """The order is the entire content of the promise: returned then removed is a handover,
    removed then returned is a deletion followed by an apology.

    Deleting this makes the ordering a step in a runbook, followed under time pressure on the
    last day of a contract.
    """
    with pytest.raises(HandoverError, match="never received"):
        plan_teardown(_return(unreachable=(Store.EXPORT,)))


def test_a_teardown_is_planned_from_the_return_and_not_from_the_instruction() -> None:
    """The positive half, and the signature is the rule: `plan_teardown` takes the return, so
    there is no call that plans a removal without one in hand.

    Deleting this leaves the ordering provable only by its refusal, which a function that
    refuses everything satisfies.
    """
    plan = plan_teardown(_return())
    assert plan.handover.handover_id == "hand-0001"
    assert set(plan.stores) == set(Store)
    assert set(plan.residue) == set(Residue)


def test_a_teardown_removes_sources_before_the_copies_made_from_them() -> None:
    """Purge the cache first and the next question rebuilds it from rows that are still
    there, so the removed data is answerable from cache while every log line says the
    teardown worked. The property is asserted rather than the list, so a reordering that
    still satisfies it is allowed and one that does not is caught.

    Deleting this lets `teardown_order` become `tuple(Store)`, which is declaration order and
    puts a purge before an erase.
    """
    from brain.ops.erasure import _ORDER, disposition_of

    ranks = [_ORDER[disposition_of(store)] for store in teardown_order()]
    assert ranks == sorted(ranks), teardown_order()
    assert teardown_order() == deletion_order()


def test_a_teardown_plan_that_leaves_a_residue_behind_cannot_be_constructed() -> None:
    """A realm still authenticates, a bucket still holds objects, a vault still opens things.
    None of them is a store and all of them survive the database being dropped.

    Deleting this lets a plan cover every store and still leave the install running, which is
    a teardown that passes every check about data and none about the installation.
    """
    with pytest.raises(HandoverError, match="leaves the install behind"):
        TeardownPlan(
            handover=_handover(),
            stores=teardown_order(),
            residue=tuple(one for one in Residue if one is not Residue.IDENTITY_REALM),
        )


def test_residue_and_stores_are_two_lists_and_not_one_written_twice() -> None:
    """If a residue were also a store, the certificate's coverage check would be satisfiable
    by counting one of them twice.

    Deleting this lets the two enums grow into each other, and the overlap is where a gap
    hides.
    """
    assert not {one.value for one in Residue} & {one.value for one in Store}


# ------------------------------------------------------------------ the certificate
def test_a_certificate_accounts_for_every_store_and_every_residue() -> None:
    """The positive half. A certificate is what the client is left holding, and one that
    covered the database and not the identity provider would read as saying the install is
    gone.

    Deleting this leaves the whole certificate path asserted only by its refusals.
    """
    certificate = certify(_return(), removed=_removed(), completed_at=FINISHED)
    assert {one.what for one in certificate.removed} == set(Store) | set(Residue)
    assert certificate.returned_items == 12 + 4_102


def test_a_certificate_cannot_be_issued_while_anything_is_outstanding() -> None:
    """A document produced to be relied on must not describe a teardown that reached
    everything but one thing. The partial case already has a representation, which is the
    list of what was removed; what must not exist is a certificate for it.

    Deleting this lets a handover finish on paper before it finishes in fact.
    """
    with pytest.raises(HandoverError, match="could not be removed"):
        certify(
            _return(), removed=_removed(outstanding=Residue.VAULT_SECRETS), completed_at=FINISHED
        )


def test_a_certificate_cannot_be_issued_for_a_return_that_did_not_reach_every_store() -> None:
    """The other half of the ordering rule, at the other end. A teardown could not have been
    planned from this return, so a certificate for it describes something that did not happen.

    Deleting this leaves one path to a certificate that skips the return entirely.
    """
    with pytest.raises(HandoverError, match="did not reach every store"):
        certify(_return(unreachable=(Store.INDEX,)), removed=_removed(), completed_at=FINISHED)


def test_a_certificate_that_does_not_account_for_something_cannot_be_constructed() -> None:
    """`certify` iterates what it is given, so a missing entry would have to be built by
    hand. The model refuses it, which is what makes the coverage a property of the document
    rather than of the one function that usually produces it.

    Deleting this lets a certificate be assembled from a partial list somewhere else.
    """
    with pytest.raises(HandoverError, match="does not account for"):
        Certificate(
            handover=_handover(),
            returned_at=RETURNED,
            completed_at=FINISHED,
            returned_items=0,
            removed=tuple(_removed(missing=Store.CACHE)),
            recoverable_from_backup_until=FINISHED,
        )


def test_a_certificate_states_a_date_and_never_a_claim_of_completeness() -> None:
    """No deletion reaches inside a backup already written. A boolean stamped at issue time
    would be read as a promise about the future, so the certificate carries the date after
    which no surviving backup can hold the data and answers for a given moment.

    Deleting this lets a `complete` field be added, and it would be true on the day it was
    written and wrong for as long as anybody kept the document.
    """
    certificate = certify(_return(), removed=_removed(), completed_at=FINISHED)
    assert not hasattr(certificate, "complete")
    assert not certificate.is_beyond_backup_reach(FINISHED + timedelta(days=1))
    assert certificate.is_beyond_backup_reach(FINISHED + timedelta(days=BACKUP_RETENTION_DAYS + 1))


def test_the_backup_horizon_is_the_retention_policys_number_and_not_one_typed_here() -> None:
    """A second copy of "how long backups live" drifts from the bucket's own lifecycle rule,
    and it drifts in the direction of the certificate promising sooner than the truth.

    Deleting this lets the horizon become a literal, which would be right on the day it was
    written and wrong the first time the bucket policy changed.
    """
    certificate = certify(_return(), removed=_removed(), completed_at=FINISHED)
    assert certificate.recoverable_from_backup_until == FINISHED + timedelta(
        days=BACKUP_RETENTION_DAYS
    )


def test_a_removal_that_did_not_complete_cannot_also_report_a_count() -> None:
    """One of the two is not true and the count is the one that would be believed.

    Deleting this lets a step report "could not reach it, removed four hundred rows", which
    is a sentence somebody quotes half of.
    """
    with pytest.raises(HandoverError, match="not completed and reports"):
        Removed(what=Store.CACHE, items=4, completed=False)


def test_a_certificate_cannot_say_the_install_went_before_the_data_came_back() -> None:
    """The ordering, stated on the document itself. Deleting this lets a certificate carry
    two timestamps that contradict the promise it is making."""
    with pytest.raises(HandoverError, match="before the data was returned"):
        Certificate(
            handover=_handover(),
            returned_at=FINISHED,
            completed_at=RETURNED,
            returned_items=0,
            removed=tuple(_removed()),
            recoverable_from_backup_until=FINISHED,
        )


# ------------------------------------------------------------------ the permission surface
def test_nothing_in_this_module_takes_a_reach() -> None:
    """The leaf's permission property. An export computed at somebody's entitlement is an
    inventory of what exists as seen by them, and the difference between two such inventories
    is exactly what one of them may not see. An export is never re-checked, so that
    difference leaves the building permanently.

    Deleting this lets an `entitlement` argument be added to `assemble_return`, which is the
    single change that turns a handover into a disclosure.
    """
    assert handover_gaps() == ()


def test_a_model_carrying_a_principal_is_reported() -> None:
    """The check driven rather than described. A scan tested only against types that pass is
    satisfied by a function returning an empty tuple.

    Deleting this leaves the reach rule asserted by nothing.
    """

    @dataclass(frozen=True)
    class Careless:
        handover_id: str
        principal_id: str

    findings = handover_gaps(models=(Careless,), surface=())
    assert any("view computed for one person" in one for one in findings), findings


def test_a_function_taking_an_entitlement_is_reported() -> None:
    """The same rule on the other surface. A reach arrives as an argument far more easily
    than as a field, because an argument looks like plumbing.

    Deleting this leaves the function half of the rule unasserted.
    """

    def careless(*, entitlement: object) -> None:
        return None

    findings = handover_gaps(models=(), surface=(careless,))
    assert any("takes a reach" in one for one in findings), findings


def test_a_model_counting_what_was_not_handed_over_is_reported() -> None:
    """There is nothing to withhold in a handover, so a field named for it is a field
    somebody fills in from somewhere, and a count of what a person did not receive is the
    disclosure this platform refuses everywhere else.

    Deleting this lets `withheld` onto the certificate, where it reads as diligence.
    """

    @dataclass(frozen=True)
    class Careless:
        items: int
        withheld: int

    findings = handover_gaps(models=(Careless,), surface=())
    assert any("counts what was not handed over" in one for one in findings), findings


def test_the_return_reuses_the_store_description_rather_than_writing_a_second_one() -> None:
    """The sections are `brain.ops.erasure.StoreHolding`. A second model of the same shape
    would be a second place for the "unreached cannot report a count" invariant to be
    written, and the copy that is wrong is the one nobody looked at.

    Deleting this lets a parallel model appear, and the two would agree until one of them
    was changed.
    """
    returned = _return()
    assert all(isinstance(one, StoreHolding) for one in returned.holdings)
    rows = next(one for one in returned.holdings if one.store is Store.ROWS)
    assert rows.data_class is data_class_of(Store.ROWS)
    assert rows.holds == facts_for(Store.ROWS).holds


def test_every_type_this_module_defines_is_scanned_for_a_disclosure() -> None:
    """**A survivor found this.** `HANDOVER_MODELS` is the list `handover_gaps` walks, and
    shrinking it from five entries to one left every test green: the scan simply covered less,
    silently, which is the shape of a guard that stops guarding without ever failing.

    So the set is anchored outside itself, against the module's own dataclasses. A type defined
    here and left out of the list is exactly the case that matters: somebody adds a model during
    a handover that is going badly, gives it a `reach` or a `withheld_count`, and the check that
    would have refused it never looks at it.

    Delete this and the disclosure rule quietly stops applying to the newest type, which is
    always the one written in a hurry."""
    defined = {
        value
        for value in vars(handover_module).values()
        if isinstance(value, type)
        and is_dataclass(value)
        and value.__module__ == handover_module.__name__
    }

    assert set(HANDOVER_MODELS) == defined, (
        "a dataclass defined here is not scanned by handover_gaps: "
        f"{sorted(one.__name__ for one in defined - set(HANDOVER_MODELS))}"
    )
    assert len(HANDOVER_MODELS) >= 5
