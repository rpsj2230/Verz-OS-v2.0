"""Retention policy, held to the two things it is always quietly wrong about.

The first is the number. A window is a constant, and a test asserting a constant against
itself is green for every value that constant could hold, which is the defect CLAUDE.md
records three authors hitting in one afternoon. So every figure below is checked against
something outside `brain.ops.retention`: the trace window from `brain.ops.tracing`, the
bucket lifecycle rules from `brain.ops.storage`, the review cycle from
`brain.audit.compliance`, and the leaf's own stated thirty days written here as a literal.

The second is coverage. A retention policy that names nine stores out of ten is not
detectably wrong from inside itself, so the store declarations are checked against
`brain.db.SCHEMAS` and `brain.ops.storage.BUCKETS`, and the check is shown failing as well
as passing. A check nobody has watched produce a finding is a check nobody knows works.

Task ids: M25.1.1, M25.1.2, M25.1.3, M25.1.4, M25.1.5
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.compliance import REGISTER_REVIEW_DAYS
from brain.db import SCHEMAS
from brain.ops.retention import (
    BACKUP_RETENTION_DAYS,
    EXPORT_RETENTION_DAYS,
    HORIZONS,
    METADATA_LEDGER_RETENTION_DAYS,
    PAYLOAD_RETENTION_DAYS,
    RECORDING_RETENTION_DAYS,
    STORES,
    TRACE_RETENTION_DAYS,
    DataClass,
    Horizon,
    Lifetime,
    RetentionError,
    RetentionReport,
    Store,
    StoreCensus,
    SweptStore,
    data_class_of,
    enforcement_gaps,
    enforcement_report,
    expires_at,
    facts_for,
    horizon_for,
    horizon_gaps,
    horizon_of,
    is_expired,
    retention_policy_gaps,
    store_gaps,
    stores_in_class,
)
from brain.ops.storage import BUCKETS, Bucket, bucket
from brain.ops.tracing import TraceRecord, retention_for

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)

#: The six stores M25.2.1 names in the tracker, spelled here rather than derived, so this
#: file states the requirement instead of restating whatever the module currently declares.
NAMED_BY_THE_TRACKER = (
    Store.ROWS,
    Store.PROJECTION,
    Store.MEMORY,
    Store.TRACE,
    Store.RECORDING,
    Store.BACKUP,
)


# ------------------------------------------------------------------- the numbers (M25.1)
def test_the_payload_store_expires_after_thirty_days_and_that_thirty_is_the_trace_window() -> None:
    """M25.1.3 asks for a thirty-day payload expiry. Both halves of that are asserted here
    and neither is asserted against the module's own constant.

    The literal 30 comes from the leaf, not from the code, so raising the constant fails
    this test rather than moving both sides of it. The second assertion pins the relation
    that makes 30 the right number rather than a nice round one: a payload is the content of
    a trace, and a payload kept longer than its trace is unreachable, still stored and still
    leakable, which is the same nesting argument `brain.ops.tracing.retention_gaps` makes one
    level in.

    Delete this and `PAYLOAD_RETENTION_DAYS` can be set to any value at all, because every
    other assertion about it in this file imports it."""
    assert PAYLOAD_RETENTION_DAYS == 30
    assert retention_for(TraceRecord.TRACE).days == PAYLOAD_RETENTION_DAYS
    assert horizon_for(DataClass.PAYLOAD).days == 30


def test_the_trace_and_recording_windows_are_the_ones_declared_where_they_live() -> None:
    """M25.1.4. The lifecycle of a trace is declared in `brain.ops.tracing` and the lifecycle
    of a recording is a rule on the recordings bucket. Retention policy restates neither.

    A second copy of a window is a copy that drifts, and it drifts in the direction that
    costs money: the copy nobody is looking at is the one that gets raised during an
    investigation and never lowered. So the assertion is equality with the other module's
    declaration, which is what makes this a cross-module check rather than a tautology.

    Delete this and somebody types 90 into either constant, the buckets keep expiring at 30,
    and the retention report says a store is clean while the object store disagrees."""
    assert retention_for(TraceRecord.TRACE).days == TRACE_RETENTION_DAYS
    assert bucket("recordings").retention_days == RECORDING_RETENTION_DAYS
    assert bucket("exports").retention_days == EXPORT_RETENTION_DAYS
    assert horizon_for(DataClass.RECORDING).days == bucket("recordings").retention_days


def test_the_backup_window_is_the_backups_bucket_and_is_thirty_five_days() -> None:
    """The one figure in this module that an outward-facing document depends on.

    `brain.ops.erasure` puts the backup horizon on every deletion certificate, so this
    number is the difference between a certificate that is true and one that is not. It is
    asserted twice: against the bucket, because that is where the lifecycle rule actually
    lives, and against the literal 35, because a change to the bucket ought to make somebody
    reread the certificate wording rather than silently move the promised date.

    Delete this and the certificate's honest limit becomes whatever number is nearest."""
    assert bucket("backups").retention_days == BACKUP_RETENTION_DAYS
    assert BACKUP_RETENTION_DAYS == 35


def test_the_metadata_ledger_is_the_longest_bounded_window_and_outlives_a_register_review() -> None:
    """M25.1.2 says the metadata ledger is kept long, and "long" is not a number.

    So it is pinned by two properties instead. It is the longest bounded window declared,
    which is the property that makes it the ledger rather than merely another table, and it
    is at least a processing register's review cycle from `brain.audit.compliance`, because
    a register entry reviewed once a year describes traffic somebody then goes looking for.
    Both hold whatever number is chosen, and both fail if the ledger is shortened below the
    things it is supposed to outlive.

    Delete this and the ledger can be set to seven days without a single other test in this
    repository noticing."""
    bounded = [one.days for one in HORIZONS if one.days is not None]

    assert max(bounded) == METADATA_LEDGER_RETENTION_DAYS
    assert METADATA_LEDGER_RETENTION_DAYS >= REGISTER_REVIEW_DAYS
    assert METADATA_LEDGER_RETENTION_DAYS > PAYLOAD_RETENTION_DAYS


def test_every_data_class_declares_a_horizon_and_the_declared_set_holds_together() -> None:
    """The positive case for `horizon_gaps`, and the sibling of every negative below.

    A gap check tested only by being made to fail is satisfied by a function that reports
    everything, which would be as useless as one that reports nothing and considerably more
    annoying. This is the assertion that the declared policy is actually clean.

    Delete this and `horizon_gaps` can be changed to return a finding unconditionally, and
    every other test in this file about it still passes."""
    assert horizon_gaps() == ()
    assert {one.data_class for one in HORIZONS} == set(DataClass)


def test_a_payload_kept_longer_than_its_trace_is_reported_rather_than_stored_quietly() -> None:
    """The negative sibling, run against a fabricated set of windows rather than the real
    one, which is why `horizon_gaps` takes a parameter at all.

    A check that can only ever be pointed at the constant beside it has never been seen to
    produce a finding, so nobody knows whether it can. This hands it a policy where the
    payload outlives the trace and asserts it says so, in words naming both numbers.

    Delete this and the nesting rules become decoration: the function keeps returning an
    empty tuple and the empty tuple keeps being read as proof."""
    broken = tuple(
        Horizon(
            data_class=one.data_class,
            lifetime=one.lifetime,
            days=90 if one.data_class is DataClass.PAYLOAD else one.days,
            because=one.because,
        )
        for one in HORIZONS
    )

    findings = horizon_gaps(broken)

    assert any("payloads are kept 90 days and traces 30" in one for one in findings)
    assert horizon_gaps(HORIZONS) == ()


def test_a_data_class_with_no_declared_window_is_named_rather_than_defaulted() -> None:
    """The gap that matters most when a class is added: nothing decided how long it is kept.

    A dictionary lookup with a default would give the new class the default, and the default
    in every system that has one is the longest. Here it is reported by name.

    Delete this and adding a member to `DataClass` gives it whatever the first branch
    returns, and the store using it is kept forever with nothing saying so."""
    findings = horizon_gaps([one for one in HORIZONS if one.data_class is not DataClass.TRACE])

    assert findings == ("trace: no retention declared",)


def test_the_audit_class_never_expires_and_a_window_on_it_is_a_finding() -> None:
    """The audit chain outlives every policy in this module, which is not a preference.

    `brain.audit.ledger` calls it the one table that outlives every retention policy in the
    system, and a hash chain with a hole in the middle proves nothing about what surrounds
    the hole. So a fixed window on the audit class is reported, and the finding says why.

    Delete this and somebody gives the audit class thirty days to save space, the sweep
    prunes from the middle, and the next verification run says the ledger was tampered
    with."""
    assert horizon_for(DataClass.AUDIT).lifetime is Lifetime.NEVER_EXPIRES

    broken = tuple(
        Horizon(
            data_class=one.data_class,
            lifetime=Lifetime.FIXED_WINDOW if one.data_class is DataClass.AUDIT else one.lifetime,
            days=30 if one.data_class is DataClass.AUDIT else one.days,
            because=one.because,
        )
        for one in HORIZONS
    )

    assert any("hole in the middle of a hash chain" in one for one in horizon_gaps(broken))


def test_a_trace_blob_cannot_be_kept_longer_than_the_payload_class_that_governs_it() -> None:
    """A cross-module nesting rule nobody else states.

    `brain.ops.tracing` declares a blob window and knows nothing about data classes;
    retention declares a payload class and knows nothing about blobs. The blob store is
    where a payload too large to inline goes, so the two have to nest, and the only place
    that can be checked is here.

    Delete this and raising the blob window past the payload window leaves an overflow copy
    of a question sitting in object storage after the payload class says it is gone."""
    assert retention_for(TraceRecord.BLOB).days <= PAYLOAD_RETENTION_DAYS

    broken = tuple(
        Horizon(
            data_class=one.data_class,
            lifetime=one.lifetime,
            days=3 if one.data_class is DataClass.PAYLOAD else one.days,
            because=one.because,
        )
        for one in HORIZONS
    )

    assert any("trace blobs are kept" in one for one in horizon_gaps(broken))


# ----------------------------------------------------------- the shape of a horizon
def test_a_horizon_that_is_not_a_fixed_window_cannot_also_carry_a_number_of_days() -> None:
    """The combination that reads as a policy and is not one.

    A lifetime saying "no clock" beside a number of days is two statements, and whichever a
    future reader believes, half the callers believe the other. The constructor refuses it,
    so the contradiction cannot be written down.

    Delete this and `Lifetime.FOLLOWS_ITS_SOURCE` with `days=7` is constructible, and every
    caller that branches on the lifetime disagrees with every caller that reads the days."""
    with pytest.raises(RetentionError, match="one of those is not true"):
        Horizon(
            data_class=DataClass.DERIVED,
            lifetime=Lifetime.FOLLOWS_ITS_SOURCE,
            days=7,
            because="a cache with a window of its own",
        )

    kept = Horizon(
        data_class=DataClass.DERIVED,
        lifetime=Lifetime.FOLLOWS_ITS_SOURCE,
        days=None,
        because="follows its source",
    )
    assert kept.days is None


def test_a_fixed_window_of_zero_days_is_not_a_window() -> None:
    """Zero would mean data that expires before anybody can read it, which reads in an
    incident as the store being broken rather than as a policy anybody chose.

    The positive sibling proves one day is accepted, so this is a check on zero rather than
    a constructor that refuses everything.

    Delete this and a mis-typed constant produces a policy that expires everything
    immediately, and the first symptom is a support ticket about missing traces."""
    with pytest.raises(RetentionError, match="which is not a window"):
        Horizon(
            data_class=DataClass.TRACE,
            lifetime=Lifetime.FIXED_WINDOW,
            days=0,
            because="none",
        )

    assert (
        Horizon(
            data_class=DataClass.TRACE, lifetime=Lifetime.FIXED_WINDOW, days=1, because="one day"
        ).days
        == 1
    )


def test_a_horizon_with_no_stated_reason_is_refused() -> None:
    """The same rule `brain.ops.storage.Bucket` and `brain.ops.tracing.Retention` enforce.

    A window nobody can explain is a window that gets extended the first time somebody wants
    an older record, and the extension is permanent because nobody left behind what the
    original number was protecting.

    Delete this and the reasons rot into empty strings one refactor at a time."""
    with pytest.raises(RetentionError, match="states no reason"):
        Horizon(data_class=DataClass.BACKUP, lifetime=Lifetime.FIXED_WINDOW, days=35, because="  ")


def test_an_unbounded_bucket_cannot_be_turned_into_a_retention_class() -> None:
    """`brain.ops.storage` allows a bucket kept until somebody deletes it, with prose saying
    why. A retention class cannot be built from one, and the refusal has to be reachable.

    The bucket built here is a fabricated one rather than a declared one, which is the only
    way to exercise the branch: all four declared buckets have windows and two of them are
    forbidden from losing theirs.

    Delete this and relaxing the recordings bucket to unbounded silently produces a payload
    class with no expiry at all."""
    from brain.ops.retention import _expiring

    forever = Bucket(
        name="fabricated",
        holds="a bucket somebody decided to keep indefinitely",
        retention_days=None,
        retention_reason="kept until somebody deletes it",
        versioned=False,
    )

    with pytest.raises(RetentionError, match="no window to build a retention class from"):
        _expiring(forever)

    assert _expiring(bucket("backups")) == 35


# ------------------------------------------------------------------- expiry arithmetic
def test_a_thing_expires_one_window_after_it_was_written_and_not_before() -> None:
    """The positive case for the arithmetic, and the boundary rather than the middle.

    A day before the window closes it is not expired; at the moment it closes it is. Checked
    at the boundary because the middle of a window is where every implementation is right.

    Delete this and an off-by-one in the comparison keeps everything an extra day or throws
    it away a day early, and neither is visible in any report."""
    written = NOW
    due = expires_at(DataClass.PAYLOAD, written)

    assert due == written + timedelta(days=PAYLOAD_RETENTION_DAYS)
    assert not is_expired(DataClass.PAYLOAD, written, due - timedelta(seconds=1))
    assert is_expired(DataClass.PAYLOAD, written, due)


def test_a_class_without_a_clock_has_no_expiry_date_and_is_never_expired_by_age() -> None:
    """Three of the four lifetimes are not clocks, and age must not decide for any of them.

    The audit chain in particular: `is_expired` returning True for it under any `now` would
    be the sweep being told it may prune a hash chain. Checked for all three rather than for
    the interesting one, because the other two would be found later and by accident.

    Delete this and a lifetime that means "goes when its source goes" starts being swept on
    age, which deletes a cache entry whose source is fine and an audit row that is not."""
    far_future = NOW + timedelta(days=100_000)

    for data_class in (DataClass.AUDIT, DataClass.DERIVED, DataClass.BUSINESS_RECORD):
        assert expires_at(data_class, NOW) is None
        assert not is_expired(data_class, NOW, far_future)


def test_a_naive_write_time_is_refused_rather_than_expiring_at_the_machines_offset() -> None:
    """The same rule the rest of the repository enforces on timestamps.

    A naive datetime compared against an aware one is wrong by however many hours the
    machine happens to be offset, and the error is silent and only a few hours wide, which
    is exactly the size that never gets noticed.

    Delete this and a retention sweep in Singapore expires things eight hours early or eight
    hours late depending on which container ran it."""
    with pytest.raises(RetentionError, match="naive write time"):
        expires_at(DataClass.PAYLOAD, datetime(2026, 9, 7, 9, 0))

    assert expires_at(DataClass.PAYLOAD, NOW) is not None


# --------------------------------------------------------- the store list (constraint 1)
def test_every_declared_store_has_facts_and_every_fact_names_a_store() -> None:
    """The two halves of "the store list is complete", asserted in both directions.

    One direction catches a member added to the enum with nothing decided about it; the
    other catches a declaration left behind after a member was removed, which would make a
    subject access request iterate over a store that no longer exists.

    Delete this and adding `Store.WHATEVER` compiles, assembles, and produces a subject
    access request with a section nobody filled in."""
    assert {one.store for one in STORES} == set(Store)
    assert len(STORES) == len(set(Store))
    for store in Store:
        assert facts_for(store).store is store


def test_every_postgres_schema_is_claimed_by_a_store_so_a_new_one_cannot_be_forgotten() -> None:
    """**The check that makes "we looked everywhere" a claim rather than a habit.**

    `brain.db.SCHEMAS` is the list of Postgres namespaces, maintained by whoever adds a
    table. Nothing about adding an eleventh schema would otherwise tell anybody that a
    subject access request no longer covers the database, because the request would come
    back looking complete. This asserts every schema is claimed, and the negative case below
    shows the finding actually appearing.

    Delete this and a new schema is a store nobody searches, discovered years later or
    never."""
    claimed = {schema for one in STORES for schema in one.schemas}

    assert claimed == set(SCHEMAS)
    assert store_gaps() == ()


def test_a_schema_no_store_claims_is_reported_by_name() -> None:
    """The negative sibling, and the exact shape of what happens when a schema is added.

    Dropping a claim from a fabricated declaration exercises the same loop an unclaimed new
    schema would: `store_gaps` compares what is claimed against the real `brain.db.SCHEMAS`,
    so a schema arriving upstream and a claim disappearing here produce the same finding.

    Delete this and the coverage check is never watched failing, which is the state in which
    a check quietly stops working."""
    thinned = tuple(
        replace(one, schemas=frozenset()) if one.store is Store.CONVERSATION else one
        for one in STORES
    )

    findings = store_gaps(thinned)

    assert any("schema 'chat'" in one and "no store claims it" in one for one in findings)
    assert store_gaps(STORES) == ()


def test_every_object_bucket_is_claimed_by_exactly_one_store() -> None:
    """A bucket has one lifecycle rule, so it must have one horizon.

    Two stores over one bucket is two windows over one rule, and the shorter wins by
    accident rather than by anybody choosing it. The rule differs from the schema rule
    deliberately: `obs` holds four different lifetimes and is claimed four times.

    Delete this and a second store claims `recordings`, the retention report shows it under
    two horizons, and whichever sweep runs first decides."""
    claimed = [name for one in STORES for name in one.buckets]

    assert sorted(claimed) == sorted(b.name for b in BUCKETS)
    assert len(claimed) == len(set(claimed))


def test_two_stores_over_one_bucket_is_reported() -> None:
    """The negative sibling of the rule above.

    Delete this and the duplicate-bucket branch is never exercised, which makes it a branch
    that has never run in its life."""
    doubled = tuple(
        replace(one, buckets=frozenset({"recordings"})) if one.store is Store.CACHE else one
        for one in STORES
    )

    findings = store_gaps(doubled)

    assert any("is claimed by" in one and "recordings" in one for one in findings)


def test_a_store_with_no_declaration_is_named_rather_than_skipped() -> None:
    """The failure the whole arrangement exists to prevent, made to happen.

    A store present in `Store` and absent from `STORES` is a store that a subject access
    request iterates over and has nothing to say about. `store_gaps` names it and stops,
    because a declaration list with a hole in it cannot be checked for anything else.

    Delete this and the first branch of `store_gaps` becomes unreachable in testing, and it
    is the branch that fires on the day somebody adds a store."""
    findings = store_gaps([one for one in STORES if one.store is not Store.INDEX])

    assert findings == ("index: no declaration, so nothing would look in it",)


def test_a_store_claiming_a_schema_that_does_not_exist_is_reported() -> None:
    """The rename case, which is the one that reads as clean.

    A store pointed at a schema that has been renamed reports nothing found, forever, and a
    sweep over it succeeds every time. So a claim on a schema `brain.db.SCHEMAS` does not
    declare is a finding.

    Delete this and renaming a schema silently removes a store from every sweep."""
    renamed = tuple(
        replace(one, schemas=frozenset({"mem_old"})) if one.store is Store.MEMORY else one
        for one in STORES
    )

    findings = store_gaps(renamed)

    assert any("claims schema 'mem_old'" in one for one in findings)
    assert any("schema 'mem'" in one and "no store claims it" in one for one in findings)


def test_the_six_stores_the_tracker_names_all_exist_and_carry_a_horizon() -> None:
    """M25.2.1 names rows, projections, memory, traces, recordings and backups by hand.

    Spelled out in this file rather than derived from the module, so this asserts the
    requirement rather than restating the implementation. Each is also asserted to have a
    horizon through its class, which is what proves the store is governed rather than merely
    listed.

    Delete this and a rename of any of the six leaves the tracker's requirement unmet with
    every other test still green."""
    for store in NAMED_BY_THE_TRACKER:
        assert facts_for(store).holds
        assert horizon_of(store) is horizon_for(data_class_of(store))


def test_a_stores_horizon_comes_through_its_class_and_two_stores_can_share_one() -> None:
    """M25.1.1 in one line: the class decides, so stores sharing a class share a window.

    The cache and the index are the case. If a horizon were a property of the store, those
    two would be two policies that happen to agree today, and the day one of them is edited
    the other silently stops matching.

    Delete this and per-store windows can be introduced without any test noticing."""
    assert horizon_of(Store.CACHE) is horizon_of(Store.INDEX)
    assert set(stores_in_class(DataClass.DERIVED)) == {Store.CACHE, Store.INDEX}
    assert set(stores_in_class(DataClass.LEARNED)) == {Store.MEMORY, Store.KNOWLEDGE}


# --------------------------------------------------- automated enforcement (M25.1.5)
def test_a_report_covers_every_store_even_when_the_census_mentions_two() -> None:
    """The positive case for the report, and the property it is built around.

    The report is assembled by iterating `Store` rather than by iterating what the executor
    handed over, so a census naming two stores still produces a document about every store,
    with thirteen of them marked as not reached.

    Delete this and `enforcement_report` can be rewritten to iterate the census, which
    produces a shorter, tidier report that cannot say anything was missed."""
    report = enforcement_report(
        now=NOW,
        census=[
            StoreCensus(store=Store.PAYLOAD, beyond_horizon=12),
            StoreCensus(store=Store.TRACE, beyond_horizon=4, held=1, oldest_days=44),
        ],
    )

    assert {one.store for one in report.swept} == set(Store)
    assert not report.complete
    assert report.due == 12 + 3
    assert set(report.unreached()) == set(Store) - {Store.PAYLOAD, Store.TRACE}


def test_a_full_census_produces_a_report_that_is_complete() -> None:
    """The sibling without which every assertion above is satisfied by a report that always
    says it is incomplete.

    A completeness flag that is never true is a flag nobody reads after the first week.

    Delete this and `complete` can be hard-coded to False and nothing fails."""
    report = enforcement_report(
        now=NOW,
        census=[StoreCensus(store=store, beyond_horizon=0) for store in Store],
    )

    assert report.complete
    assert report.unreached() == ()
    assert report.due == 0
    assert enforcement_gaps([StoreCensus(store=store, beyond_horizon=0) for store in Store]) == ()


def test_a_store_the_sweep_never_reached_is_named_rather_than_counted_as_clean() -> None:
    """M25.1.5's real failure mode. A run over every store but one, reporting success, reads
    exactly like a run that reached them all.

    Both halves are asserted: the line for the unreached store says so in words, and the
    finding names it. One without the other means either the report or the alert is silent.

    Delete this and a sweep that cannot connect to the object store reports a clean
    estate."""
    reached = [
        StoreCensus(store=store, beyond_horizon=0)
        for store in Store
        if store is not Store.RECORDING
    ]
    report = enforcement_report(now=NOW, census=reached)

    line = next(one.line() for one in report.swept if one.store is Store.RECORDING)
    assert "not reached" in line
    assert any("recording: no census" in one for one in report.findings)
    assert not report.complete


def test_a_census_claiming_the_audit_chain_has_expired_rows_is_a_finding() -> None:
    """A sweep that believes the audit class expires is a sweep about to cut a hash chain.

    The finding names the class and says what acting on it would do, because the person
    reading it has to decide whether to stop the run.

    Delete this and a census bug in the executor becomes a pruned ledger, and the next
    verification job reports tampering."""
    findings = enforcement_gaps([StoreCensus(store=Store.AUDIT, beyond_horizon=9)])
    clean = enforcement_gaps([StoreCensus(store=store, beyond_horizon=0) for store in Store])

    assert any("would cut a hash chain" in one for one in findings)
    assert not any("hash chain" in one for one in clean)


def test_a_store_reported_twice_in_one_run_is_a_finding_rather_than_a_sum() -> None:
    """Two censuses for one store cannot be added: they are either the same rows counted
    twice or two different readings, and nothing distinguishes them.

    Delete this and a retrying executor doubles a count, an operator sees a spike, and the
    investigation is into a store that is fine."""
    report = enforcement_report(
        now=NOW,
        census=[
            StoreCensus(store=Store.CACHE, beyond_horizon=3),
            StoreCensus(store=Store.CACHE, beyond_horizon=5),
        ],
    )

    assert any("reported twice" in one for one in report.findings)
    swept = next(one for one in report.swept if one.store is Store.CACHE)
    assert swept.beyond_horizon == 3


def test_a_census_cannot_hold_more_items_than_it_found_or_a_negative_count() -> None:
    """Arithmetic that would make `due` negative, which renders as a sweep with work to
    undo.

    The positive sibling proves an ordinary census constructs, so this is a check on the
    impossible values rather than a constructor that refuses everything.

    Delete this and `held` greater than `beyond_horizon` produces a report promising to
    remove a negative number of rows."""
    with pytest.raises(RetentionError, match="more held than there are"):
        StoreCensus(store=Store.MEMORY, beyond_horizon=2, held=3)
    with pytest.raises(RetentionError, match="negative count"):
        StoreCensus(store=Store.MEMORY, beyond_horizon=-1)

    ordinary = StoreCensus(store=Store.MEMORY, beyond_horizon=5, held=2)
    assert ordinary.due == 3


def test_everything_past_a_horizon_being_held_is_said_out_loud() -> None:
    """A store where every expired item is under legal hold is a store whose window is not
    being applied, and it will keep not being applied until somebody releases the hold.

    That is a fact an operator needs and a count of zero removed does not carry it: zero
    removed also describes a store that was already clean.

    Delete this and a hold placed in 2026 quietly suspends a retention policy forever."""
    findings = enforcement_gaps([StoreCensus(store=Store.LEDGER, beyond_horizon=4, held=4)])

    assert any("under legal hold" in one for one in findings)


def test_a_retention_report_has_nowhere_to_name_whose_rows_they_are() -> None:
    """The structural half of `A_RETENTION_REPORT_COUNTS_AND_NEVER_NAMES`.

    An operational report travels: to a dashboard, into an alert, into whatever the person
    on call pastes it into. A count of rows past a horizon is a fact about volume; a list of
    the subjects is a directory of who the system holds data on, in a document with weaker
    access control than the stores it describes.

    Delete this and `subject_id: str = ""` appears on `SweptStore` for a console filter, and
    every other test here still passes because none of them construct one with it set."""
    for model in (StoreCensus, SweptStore, RetentionReport):
        names = {f.name for f in fields(model)}
        for forbidden in ("subject", "subject_id", "principal_id", "subjects", "who"):
            assert forbidden not in names, f"{model.__name__} can name a subject"

    @dataclass(frozen=True)
    class Named:
        store: Store
        subject_id: str

    assert any(
        "names who the rows are about" in one for one in retention_policy_gaps(models=[Named])
    )


# ------------------------------------------------ no per-row override (M25.1.1)
def test_a_horizon_takes_a_data_class_and_nothing_else() -> None:
    """M25.1.1's structural half, asserted on the signature rather than on the prose.

    A per-row override is how one payload lives forever, and it arrives as a helpful keyword
    argument during an incident. `horizon_for` accepting exactly one parameter is the
    property; anything else it grew would be the way out.

    Delete this and `horizon_for(data_class, keep_until=...)` is a two-line change nobody
    reviews twice."""
    assert set(inspect.signature(horizon_for).parameters) == {"data_class"}
    assert retention_policy_gaps() == ()


def test_a_function_that_could_postpone_a_window_is_reported() -> None:
    """The negative sibling, run against a fabricated function so the scan can be watched
    working.

    `retention_policy_gaps` takes its surface as a parameter for exactly this: a scan only
    ever pointed at code known to be clean has never produced a finding, and nobody knows
    whether it can.

    Delete this and the override scan is a function that has only ever returned an empty
    tuple, which is indistinguishable from one that always will."""

    def sweep(data_class: DataClass, keep_until: datetime) -> None:
        """A plausible helper somebody adds during an investigation."""

    findings = retention_policy_gaps(functions=[sweep])

    assert any("sweep takes a keep_until" in one for one in findings)


def test_a_model_that_could_carry_a_per_row_window_is_reported() -> None:
    """The same hole with a longer path to it: the override arrives on the census instead of
    on the call.

    Delete this and a `retention_days` column on a report model is a per-item window that
    the policy never sees."""

    @dataclass(frozen=True)
    class Row:
        store: Store
        retention_days: int

    findings = retention_policy_gaps(models=[Row])

    assert any("Row carries retention_days" in one for one in findings)
