"""The retention executor: what it counts, what it removes, and every store it will not touch.

Two halves. Without a server: `retention.sweep` over a sweeper that reports whatever a test
tells it to, so the run's own refusals can be shown to fire. With one: `PostgresSweeper` in a
database this file creates, with a fixed-window table attributed to the trace store so there is
something old enough to remove, which the real estate does not have yet.

Every removal test has a sibling that proves the rows which must survive did.

Task ids: M25.1.5
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.types.json import Jsonb
from sqlalchemy.ext.asyncio import AsyncSession

from brain.audit.ledger import LegalHold
from brain.ops.retention import (
    ONLY_A_CLOCK_IS_ENFORCED_BY_AGE,
    TRACE_RETENTION_DAYS,
    CitedHold,
    DataClass,
    Lifetime,
    RetentionError,
    RetentionReport,
    Store,
    StoreCensus,
    SweptStore,
    enforcement_report,
    retention_policy_gaps,
    sweep,
)
from brain.ops.retention_store import (
    A_HOLD_THIS_CANNOT_MATCH_TO_A_ROW_STOPS_THE_SWEEP,
    A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME,
    A_RECORD_LIFETIME_NEEDS_A_SUBJECT_REFERENCE_NOBODY_HAS_DECLARED,
    A_TABLE_IN_A_SHARED_SCHEMA_BELONGS_TO_NOBODY_UNTIL_IT_IS_ATTRIBUTED,
    A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO,
    ATTRIBUTED,
    CLOCKS,
    NOT_HELD_IN_POSTGRES,
    RETENTION_SWEEP,
    SUBJECTS,
    PostgresSweeper,
    ReleaseRefusal,
    ReleaseRefusedError,
    RetentionStoreError,
    StoredReport,
    active_holds,
    attribution_gaps,
    cite,
    lift_hold,
    place_hold,
    record_failure,
    release_refusal,
    release_sweep,
    released_controls,
    report_document,
    report_from_document,
    run_retention_sweep,
    withdraw_release,
)
from brain.ops.schedule import DESTRUCTIVE
from tests.fixtures.scratch_postgres import (
    RETENTION_TABLES,
    add_modelled,
    drop,
    engine,
    fresh,
    run,
    sql,
)

#: Far outside any plausible wall clock.
NOW = datetime(2999, 1, 1, tzinfo=UTC)
OLD = NOW - timedelta(days=TRACE_RETENTION_DAYS + 10)
YOUNG = NOW - timedelta(days=TRACE_RETENTION_DAYS - 10)

TRACE_TABLE = "obs.scratch_trace"


# ------------------------------------------------------------------- without a server
@dataclass
class Scripted:
    """A sweeper that answers each store with what the test scripted, and records removals."""

    answers: dict[Store, StoreCensus | RetentionError]
    expired: list[Store] = field(default_factory=list)

    def census(self, store: Store, now: datetime) -> StoreCensus:
        answer = self.answers.get(store, RetentionError("not scripted"))
        if isinstance(answer, RetentionError):
            raise answer
        return answer

    def expire(self, store: Store, now: datetime) -> int:
        self.expired.append(store)
        census = self.answers[store]
        assert isinstance(census, StoreCensus)
        return census.due


def test_a_store_the_sweeper_cannot_count_is_named_with_its_reason() -> None:
    """The refusal's message is on the report beside "not reached", and the run is incomplete.

    Delete this and a refused store could be dropped from the report with its reason, leaving an
    operator told the run was incomplete and nothing about what would complete it."""
    report = sweep(
        Scripted({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=0)}),
        now=NOW,
        report_only=True,
    )
    assert report.complete is False
    assert "ledger: not counted, because not scripted" in report.findings
    assert Store.TRACE not in report.unreached()
    assert not any(one.startswith("trace:") for one in report.findings)


def test_a_fixed_window_with_items_due_is_expired_and_the_removal_is_reported() -> None:
    """Delete this and `sweep` could count forever and remove nothing, with a clean report."""
    sweeper = Scripted({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=4, held=1)})
    report = sweep(sweeper, now=NOW, report_only=False)

    assert sweeper.expired == [Store.TRACE]
    assert "trace: 3 removed" in report.findings


def test_report_only_removes_nothing_and_says_so() -> None:
    """Delete this and a control released for reporting would delete on its first run."""
    sweeper = Scripted({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=4)})
    report = sweep(sweeper, now=NOW, report_only=True)

    assert sweeper.expired == []
    assert "trace: 4 due and none removed, report only" in report.findings


def test_a_census_claiming_a_lifetime_without_a_clock_has_items_due_removes_nothing() -> None:
    """The audit store and a record-lifetime store both report items due; neither is expired.

    Delete this and a sweeper that miscounted the audit chain would cut it on the next run."""
    sweeper = Scripted(
        {
            Store.AUDIT: StoreCensus(store=Store.AUDIT, beyond_horizon=2),
            Store.MEMORY: StoreCensus(store=Store.MEMORY, beyond_horizon=5),
        }
    )
    report = sweep(sweeper, now=NOW, report_only=False)

    assert sweeper.expired == []
    assert any(ONLY_A_CLOCK_IS_ENFORCED_BY_AGE in one for one in report.findings)
    assert any("never expires" in one for one in report.findings)


def test_a_removal_larger_than_the_count_is_a_finding() -> None:
    """Delete this and an executor removing rows the census never counted reads as a clean run."""

    class Overreaching(Scripted):
        def expire(self, store: Store, now: datetime) -> int:
            return 9

    report = sweep(
        Overreaching({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=2)}),
        now=NOW,
        report_only=False,
    )
    assert any("disagree about what was past its window" in one for one in report.findings)


def test_the_shipped_attributions_point_at_stores_that_claim_their_schemas() -> None:
    """Clean as shipped, and a table attributed to a store outside its schema is a finding.

    Delete this and `obs.audit_entry` attributed to the rows store would never be read, and the
    table would refuse every store sharing `obs`."""
    assert attribution_gaps() == ()
    assert attribution_gaps({"obs.audit_entry": Store.ROWS}, {}, {})
    assert attribution_gaps(ATTRIBUTED, {"nowhere.table": "at"}, {})


def test_the_metadata_ledger_and_the_holds_are_attributed_with_their_clocks() -> None:
    """`obs.request_telemetry` to the ledger by `received_at` and matched to a hold by
    `principal`; `obs.legal_hold` to the audit store by `placed_at`.

    Spelled out rather than read off the tables module, because the defect this pins is a table
    that arrived in `obs` with no attribution at all, and from 0039 until this change that made
    every run report the ledger, trace, payload and audit stores as not reached. Delete this and
    the ledger could lose its attribution again, or gain the trace store's thirty days."""
    assert ATTRIBUTED["obs.request_telemetry"] is Store.LEDGER
    assert CLOCKS["obs.request_telemetry"] == "received_at"
    assert SUBJECTS["obs.request_telemetry"] == "principal"
    assert ATTRIBUTED["obs.legal_hold"] is Store.AUDIT
    assert CLOCKS["obs.legal_hold"] == "placed_at"


# ------------------------------------------------------ enforcement, without a server
def test_a_store_whose_due_items_are_all_queued_is_not_expired_and_says_why() -> None:
    """Four due, four queued behind a partition rule: `expire` is never called, nothing is
    removed, and the rule is on the report.

    Delete this and a sweep could delete from the metadata ledger row by row, which is the one
    thing `0039` says never happens to it."""
    sweeper = Scripted(
        {
            Store.LEDGER: StoreCensus(
                store=Store.LEDGER,
                beyond_horizon=4,
                queued=4,
                queued_because=A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME,
            )
        }
    )
    report = sweep(sweeper, now=NOW, report_only=False)

    assert sweeper.expired == []
    ledger = next(one for one in report.swept if one.store is Store.LEDGER)
    assert (ledger.removed, ledger.queued) == (0, 4)
    assert ledger.queued_because == A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME
    assert (
        f"ledger: 4 due and queued, because {A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME}"
        in report.findings
    )


def test_a_store_with_part_of_its_due_items_queued_expires_the_rest_and_names_both() -> None:
    """Five due, two queued: the store is expired, the removal is reported, and so is the queue.

    Delete this and a store holding one queued table beside a deletable one could be skipped
    whole, keeping the deletable table's rows for ever."""
    sweeper = Scripted(
        {
            Store.TRACE: StoreCensus(
                store=Store.TRACE,
                beyond_horizon=5,
                queued=2,
                queued_because=A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO,
            )
        }
    )
    report = sweep(sweeper, now=NOW, report_only=False)

    assert sweeper.expired == [Store.TRACE]
    assert "trace: 5 removed" in report.findings
    assert any(one.startswith("trace: 2 due and queued") for one in report.findings)


def test_a_removal_is_measured_against_what_is_removable_rather_than_what_is_due() -> None:
    """Five due, two queued, and the executor removes four: more than the three it may, which
    is a finding, while four is under the five due.

    Delete this and an executor deleting from a queued table as well as the deletable one would
    read as a clean run, because the total still fits under what was due."""

    class Overreaching(Scripted):
        def expire(self, store: Store, now: datetime) -> int:
            return 4

    report = sweep(
        Overreaching(
            {
                Store.TRACE: StoreCensus(
                    store=Store.TRACE,
                    beyond_horizon=5,
                    queued=2,
                    queued_because=A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO,
                )
            }
        ),
        now=NOW,
        report_only=False,
    )
    assert any("counted 3 removable" in one for one in report.findings)


def test_what_a_run_removed_lands_on_its_store_and_is_summed_by_class() -> None:
    """Three traces and two payloads removed, one ledger item held: the stores carry their own
    counts, the report sums them per class, and a class nothing happened to is not listed.

    Delete this and a report could show items due and nothing removed for a run that removed
    them, which reads as a sweep that failed."""
    sweeper = Scripted(
        {
            Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=3),
            Store.PAYLOAD: StoreCensus(store=Store.PAYLOAD, beyond_horizon=2),
            Store.LEDGER: StoreCensus(store=Store.LEDGER, beyond_horizon=1, held=1),
        }
    )
    report = sweep(sweeper, now=NOW, report_only=False)

    removed = {one.store: one.removed for one in report.swept}
    assert (removed[Store.TRACE], removed[Store.PAYLOAD], removed[Store.LEDGER]) == (3, 2, 0)
    assert report.removed == 5
    assert report.removed_by_class() == ((DataClass.TRACE, 3), (DataClass.PAYLOAD, 2))
    assert report.held_by_class() == ((DataClass.METADATA_LEDGER, 1),)
    assert report.queued_by_class() == ()


def test_two_stores_of_one_class_are_added_together_in_the_class_total() -> None:
    """Rows and agents are both business records. A report built with a count on each sums them.

    Delete this and a total by class could keep the last store's count instead of the sum."""
    report = enforcement_report(
        now=NOW,
        census=[
            StoreCensus(store=Store.ROWS, beyond_horizon=2, held=2),
            StoreCensus(store=Store.AGENTS, beyond_horizon=3, held=3),
        ],
    )
    assert report.held_by_class() == ((DataClass.BUSINESS_RECORD, 5),)


def test_an_unreached_store_carries_its_reason_on_its_line_and_in_the_failures() -> None:
    """The sweeper refuses the recordings store: its line says why, and `failures` names it.

    Delete this and the reason a store was not reached would survive only as a free-standing
    finding, which a screen listing stores has no way to put beside the store."""
    report = sweep(
        Scripted({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=0)}),
        now=NOW,
        report_only=True,
    )
    recording = next(one for one in report.swept if one.store is Store.RECORDING)
    trace = next(one for one in report.swept if one.store is Store.TRACE)

    assert recording.unreached_because == "not scripted"
    assert recording.line().endswith("because not scripted")
    assert trace.unreached_because == ""
    assert "recording: not scripted" in report.failures()
    assert not any(one.startswith("trace:") for one in report.failures())


def test_a_run_says_whether_it_was_allowed_to_act_and_cites_its_holds() -> None:
    """Both modes land on the report, and the holds handed in are cited by id and reason.

    Delete this and a report showing items due beside nothing removed could not say whether the
    sweep was forbidden to act or failed to."""
    cited = (CitedHold(hold_id="h_dispute", reason_code="litigation", company_wide=False),)
    scripted: dict[Store, StoreCensus | RetentionError] = {
        Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=0)
    }

    reporting = sweep(Scripted(dict(scripted)), now=NOW, report_only=True, holds=cited)
    acting = sweep(Scripted(dict(scripted)), now=NOW, report_only=False)

    assert (reporting.report_only, acting.report_only) == (True, False)
    assert reporting.holds == cited
    assert acting.holds == ()


def test_a_reached_line_says_what_was_removed_and_what_was_queued() -> None:
    """Delete this and the one line an operator reads per store could drop the removal count."""
    line = SweptStore(
        store=Store.TRACE,
        data_class=DataClass.TRACE,
        lifetime=Lifetime.FIXED_WINDOW,
        days=30,
        reached=True,
        beyond_horizon=9,
        held=1,
        oldest_days=40,
        removed=6,
        queued=2,
    ).line()
    assert line == "trace (trace, 30d): 8 due, 1 held, 6 removed, 2 queued, oldest 40d"


def test_a_census_refuses_a_queue_it_cannot_explain_or_that_is_larger_than_what_is_due() -> None:
    """Negative, larger than due, queued with no rule, and a rule with nothing queued: all four
    refused. And the ordinary case, with `removable` being due less queued.

    Delete this and a report could say items are queued behind a rule nobody named, which is
    items kept for ever with a reason that is a blank."""
    with pytest.raises(RetentionError, match="negative"):
        StoreCensus(store=Store.TRACE, beyond_horizon=1, queued=-1)
    with pytest.raises(RetentionError, match="more queued than"):
        StoreCensus(store=Store.TRACE, beyond_horizon=3, held=1, queued=3, queued_because="x")
    with pytest.raises(RetentionError, match="not true"):
        StoreCensus(store=Store.TRACE, beyond_horizon=3, queued=2)
    with pytest.raises(RetentionError, match="not true"):
        StoreCensus(store=Store.TRACE, beyond_horizon=3, queued_because="a rule")
    ordinary = StoreCensus(
        store=Store.TRACE, beyond_horizon=5, held=1, queued=3, queued_because="a rule"
    )
    assert (ordinary.due, ordinary.removable) == (4, 1)
    assert StoreCensus(store=Store.TRACE, beyond_horizon=4, held=1, queued=3, queued_because="r")


def test_a_cited_hold_names_its_identifier_and_reason_and_has_nowhere_for_a_subject() -> None:
    """Delete this and a cited hold could arrive with no reason, or grow the subjects it holds,
    which would put a list of people under legal hold on an operational dashboard."""
    with pytest.raises(RetentionError):
        CitedHold(hold_id=" ", reason_code="litigation", company_wide=False)
    with pytest.raises(RetentionError):
        CitedHold(hold_id="h_one", reason_code="", company_wide=False)
    assert {f.name for f in fields(CitedHold)} == {"hold_id", "reason_code", "company_wide"}
    assert retention_policy_gaps() == ()


def test_a_hold_is_cited_by_identifier_reason_and_breadth_and_never_by_subject() -> None:
    """`cite` built from a real `LegalHold` over two people.

    Delete this and the subjects could be copied onto the report on the way through."""
    placed = datetime(2019, 1, 1, tzinfo=UTC)
    over_two = LegalHold(
        id="h_dispute",
        reason_code="litigation",
        subjects=frozenset({"u_one", "u_two"}),
        placed_at=placed,
    )
    everybody = LegalHold(id="h_all", reason_code="regulator", all_subjects=True, placed_at=placed)

    assert cite([over_two, everybody]) == (
        CitedHold(hold_id="h_dispute", reason_code="litigation", company_wide=False),
        CitedHold(hold_id="h_all", reason_code="regulator", company_wide=True),
    )


# -------------------------------------------------------------- a report, written and read
def _a_run() -> RetentionReport:
    return sweep(
        Scripted(
            {
                Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=3, oldest_days=41),
                Store.LEDGER: StoreCensus(
                    store=Store.LEDGER,
                    beyond_horizon=2,
                    held=1,
                    queued=1,
                    queued_because=A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME,
                ),
            }
        ),
        now=NOW,
        report_only=False,
        holds=(CitedHold(hold_id="h_dispute", reason_code="litigation", company_wide=True),),
    )


def test_a_report_reads_back_as_the_report_that_was_written() -> None:
    """Every field of every store, the holds, the findings and the mode survive the documents.

    Delete this and the screen could show a report the store wrote differently: a removed count
    lost in the JSON reads as a sweep that did nothing."""
    written = _a_run()
    document = report_document(written)

    read = report_from_document(
        at=written.at,
        report_only=written.report_only,
        stores=document["stores"],
        holds=document["holds"],
        findings=document["findings"],
    )
    assert read == written


def test_a_report_document_carries_counts_and_reasons_and_no_subject() -> None:
    """The keys each store is written with, spelled out, so a key added to the document is a
    decision somebody makes here rather than a field that travels.

    Delete this and a `subjects` key could be added to the document without touching a model."""
    document = report_document(_a_run())

    assert set(document) == {"stores", "holds", "findings"}
    assert {key for one in document["stores"] for key in one} == {
        "store",
        "reached",
        "beyond_horizon",
        "held",
        "oldest_days",
        "removed",
        "queued",
        "queued_because",
        "unreached_because",
    }
    assert {key for one in document["holds"] for key in one} == {
        "hold_id",
        "reason_code",
        "company_wide",
    }


def test_a_stored_report_missing_a_store_reads_it_as_unreached_and_an_unknown_one_is_refused() -> (
    None
):
    """A row written before a store existed reads that store as not reached, and a row naming a
    store the policy no longer has is refused rather than dropped.

    Delete this and an old report could show a store added since as reached and clean."""
    document = report_document(_a_run())
    without_trace = [one for one in document["stores"] if one["store"] != Store.TRACE.value]

    read = report_from_document(
        at=NOW, report_only=False, stores=without_trace, holds=[], findings=[]
    )
    trace = next(one for one in read.swept if one.store is Store.TRACE)
    assert (trace.reached, trace.removed) == (False, 0)
    assert len(read.swept) == len(Store)

    with pytest.raises(ValueError, match="nowhere"):
        report_from_document(
            at=NOW,
            report_only=False,
            stores=[{**document["stores"][0], "store": "nowhere"}],
            holds=[],
            findings=[],
        )


# ------------------------------------------------------- a run that raised, without a server
class _Written:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row


class _Connection:
    """Enough of a psycopg connection for the failure path: it refuses to read holds, records the
    statements it was given, and can refuse the transaction the failure report is written in."""

    def __init__(self, *, holds_fail: bool = True, transaction_fails: bool = False) -> None:
        self.holds_fail = holds_fail
        self.transaction_fails = transaction_fails
        self.inserted: list[tuple[object, ...]] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self.transaction_fails:
            raise psycopg.OperationalError("the server closed the connection")
        yield

    def execute(self, query: object, params: tuple[object, ...] = ()) -> _Written:
        text = str(query)
        if "obs.legal_hold" in text and self.holds_fail:
            raise psycopg.errors.UndefinedTable('relation "obs.legal_hold" does not exist')
        if text.startswith("INSERT INTO ops.retention_report"):
            self.inserted.append(params)
            return _Written((uuid.UUID(int=3),))
        return _Written(None)


def test_a_run_that_cannot_read_its_holds_reports_every_store_unreached_and_raises() -> None:
    """The holds table missing: the run raises its own exception, and one report is written with
    every store unreached, the mode it ran in, and the exception's name.

    Delete this and a failed run could write nothing, so the screen would show yesterday's clean
    report as the latest, or write a report that reads as reached."""
    conn = _Connection()

    with pytest.raises(psycopg.errors.UndefinedTable):
        run_retention_sweep(conn, now=NOW, report_only=False)  # type: ignore[arg-type]

    (params,) = conn.inserted
    at, report_only, complete, stores, _holds, _findings, failure = params
    assert (at, report_only, complete) == (NOW, False, False)
    assert isinstance(stores, Jsonb)
    assert [one["reached"] for one in stores.obj] == [False] * len(Store)
    assert isinstance(failure, str)
    assert failure.startswith("UndefinedTable: ")


def test_a_failure_report_the_database_cannot_take_does_not_replace_the_runs_own_exception() -> (
    None
):
    """The transaction for the failure report refused too: nothing is raised from recording it,
    so the run's own exception is the one the run record gets.

    Delete this and a database that went away mid-run would be recorded as failing to write a
    report, which is the least useful of the two things that went wrong."""
    conn = _Connection(transaction_fails=True)

    record_failure(conn, now=NOW, report_only=True, failure=RuntimeError("gone"))  # type: ignore[arg-type]

    assert conn.inserted == []


def test_a_failure_longer_than_a_sentence_is_cut_to_what_the_column_holds() -> None:
    """Delete this and an exception carrying a long message would be refused by the column's own
    check, and the failure report would be lost along with the run."""
    conn = _Connection()

    record_failure(conn, now=NOW, report_only=True, failure=RuntimeError("x" * 5000))  # type: ignore[arg-type]

    (params,) = conn.inserted
    assert isinstance(params[-1], str)
    # The figure `0049`'s check constraint states, written out rather than imported.
    assert len(params[-1]) == 2000


# ----------------------------------------------------------------- releasing the sweep
REPORT_ID = uuid.UUID(int=7)


def _stored(*, report_only: bool = True, failure: str | None = None) -> StoredReport:
    report = replace(_a_run(), report_only=report_only)
    return StoredReport(id=REPORT_ID, report=report, failure=failure)


def test_the_sweep_may_be_released_after_the_newest_clean_report_only_run() -> None:
    """The positive case the refusals below are siblings of. Delete this and a decision that
    refused every release would pass all of them."""
    assert release_refusal(_stored(), after_report=REPORT_ID, at=NOW, live=False) is None
    assert (
        release_refusal(_stored(), after_report=REPORT_ID, at=NOW + timedelta(days=1), live=False)
        is None
    )


@pytest.mark.parametrize(
    ("newest", "after", "at", "live", "refusal"),
    [
        (None, REPORT_ID, NOW, False, ReleaseRefusal.NO_REPORT),
        ("clean", uuid.UUID(int=8), NOW, False, ReleaseRefusal.NOT_THE_NEWEST),
        ("acted", REPORT_ID, NOW, False, ReleaseRefusal.NOT_A_REPORT_ONLY_RUN),
        ("failed", REPORT_ID, NOW, False, ReleaseRefusal.A_FAILED_RUN),
        ("clean", REPORT_ID, NOW - timedelta(seconds=1), False, ReleaseRefusal.BEFORE_THE_REPORT),
        ("clean", REPORT_ID, NOW, True, ReleaseRefusal.ALREADY_RELEASED),
    ],
)
def test_a_release_is_refused_unless_it_is_about_the_newest_clean_report_only_run(
    newest: str | None, after: uuid.UUID, at: datetime, live: bool, refusal: ReleaseRefusal
) -> None:
    """Each refusal on its own, with every other condition met.

    Delete this and a release could be recorded against a report somebody never read, a report
    of a run that had already deleted, or a run that failed with no counts in it, and the
    record meant to prove a person approved the deletion would prove nothing."""
    stored = {
        None: None,
        "clean": _stored(),
        "acted": _stored(report_only=False),
        "failed": _stored(failure="OperationalError: gone"),
    }[newest]
    assert release_refusal(stored, after_report=after, at=at, live=live) is refusal


def test_a_hold_that_arrives_already_lifted_is_refused_before_anything_is_written() -> None:
    """Delete this and a hold built with a lift date could be recorded, reading in the table as
    protection that was never in force."""
    lifted = LegalHold(
        id="h_late",
        reason_code="litigation",
        all_subjects=True,
        placed_at=OLD,
        released_at=NOW,
    )

    with pytest.raises(RetentionStoreError, match="already lifted"):
        run(lambda: place_hold(None, lifted, by="u_admin"))  # type: ignore[arg-type]


def test_the_only_destructive_control_is_the_one_a_release_can_be_recorded_for() -> None:
    """`brain.ops.schedule.DESTRUCTIVE` against the one control `ops.retention_release` releases.

    Delete this and a second destructive control could be added with nowhere to record its
    release, so it would report for ever, or be released by the retention sweep's row."""
    assert frozenset({RETENTION_SWEEP}) == DESTRUCTIVE
    assert RETENTION_SWEEP == "retention_sweep"


# ------------------------------------------------------------------------ with a server
@dataclass(frozen=True)
class AHold:
    """The three things `brain.ops.erasure.Hold` reads."""

    subjects: frozenset[str] = frozenset()
    all_subjects: bool = False
    active: bool = True

    def is_active(self, now: datetime | None = None) -> bool:
        return self.active


@pytest.fixture
def server() -> Iterator[str]:
    """A database with the schemas `0001` leaves, a trace-class table the application role may
    delete from, an audit table, a table in the one-store `ops` schema, and the three tables
    `0049` builds, from their models."""
    database = "brain_retention_store_check"
    url = fresh(database)
    try:
        sql(url, f"CREATE TABLE {TRACE_TABLE} (at timestamptz NOT NULL, subject text NOT NULL)")
        sql(url, f"GRANT SELECT, DELETE ON {TRACE_TABLE} TO brain_app")
        add_modelled(url, RETENTION_TABLES)
        sql(url, "CREATE TABLE obs.audit_entry (at timestamptz NOT NULL)")
        sql(url, "CREATE TABLE ops.something (at timestamptz NOT NULL)")
        for at, subject in ((OLD, "u_one"), (OLD, "u_two"), (YOUNG, "u_one")):
            sql(url, "INSERT INTO obs.scratch_trace VALUES (%s, %s)", at, subject)
        sql(url, "INSERT INTO obs.audit_entry VALUES (%s)", NOW - timedelta(days=4000))
        yield url
    finally:
        drop(database)


def a_sweeper(conn: psycopg.Connection[tuple[object, ...]], **overrides: object) -> PostgresSweeper:
    declared: dict[str, object] = {
        "attributed": {**ATTRIBUTED, TRACE_TABLE: Store.TRACE},
        "clocks": {"obs.audit_entry": "at", TRACE_TABLE: "at"},
        "subjects": {TRACE_TABLE: "subject"},
    }
    declared.update(overrides)
    return PostgresSweeper(conn, **declared)  # type: ignore[arg-type]


def remaining(url: str) -> list[tuple[object, ...]]:
    return sql(url, "SELECT subject, at FROM obs.scratch_trace ORDER BY subject, at")


def test_rows_past_a_fixed_window_are_removed_and_younger_rows_are_kept(server: str) -> None:
    """Two rows forty days old go, one twenty days old stays, and the census counted two.

    Delete this and the executor could delete by the wrong comparison, or by no clock at all,
    and nothing else here would see a row go."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn)
        census = sweeper.census(Store.TRACE, NOW)
        assert census.beyond_horizon == 2
        assert census.oldest_days == TRACE_RETENTION_DAYS + 10
        report = sweep(sweeper, now=NOW, report_only=False)
        conn.commit()

    assert "trace: 2 removed" in report.findings
    assert remaining(server) == [("u_one", YOUNG)]


def test_a_held_subjects_rows_are_counted_as_held_and_survive_the_sweep(server: str) -> None:
    """A hold on u_two: one of the two old rows is held, one is removed.

    Delete this and a legal hold would be honoured by the report and ignored by the delete."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn, holds=(AHold(subjects=frozenset({"u_two"})),))
        census = sweeper.census(Store.TRACE, NOW)
        assert (census.beyond_horizon, census.held) == (2, 1)
        sweep(sweeper, now=NOW, report_only=False)
        conn.commit()

    assert remaining(server) == [("u_one", YOUNG), ("u_two", OLD)]


def test_a_hold_over_every_subject_removes_nothing_and_a_lifted_hold_does_not_count(
    server: str,
) -> None:
    """Delete this and a company-wide hold, the one issued in litigation, protects nobody."""
    with psycopg.connect(server) as conn:
        assert a_sweeper(conn, holds=(AHold(all_subjects=True),)).expire(Store.TRACE, NOW) == 0
        held = a_sweeper(conn, holds=(AHold(all_subjects=True),)).census(Store.TRACE, NOW)
        assert held.held == 2
        lifted = a_sweeper(conn, holds=(AHold(all_subjects=True, active=False),))
        assert lifted.census(Store.TRACE, NOW).held == 0
        conn.rollback()
    assert len(remaining(server)) == 3


def test_a_hold_that_cannot_be_matched_to_rows_refuses_the_store_and_removes_nothing(
    server: str,
) -> None:
    """A subject hold over a table with no declared subject column: the trace store is not
    reached, nothing is removed, and the report says why.

    Delete this and a hold would be skipped for any table nobody had described, which is every
    table added after the hold was written."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn, subjects={}, holds=(AHold(subjects=frozenset({"u_two"})),))
        report = sweep(sweeper, now=NOW, report_only=False)
        conn.commit()

    assert Store.TRACE in report.unreached()
    with psycopg.connect(server) as conn:
        assert a_sweeper(conn, subjects={}).census(Store.TRACE, NOW).beyond_horizon == 2
    assert any(A_HOLD_THIS_CANNOT_MATCH_TO_A_ROW_STOPS_THE_SWEEP in one for one in report.findings)
    assert len(remaining(server)) == 3


def test_an_unattributed_table_in_a_shared_schema_refuses_every_store_sharing_it(
    server: str,
) -> None:
    """The shipped attributions do not know the scratch table: every `obs` store is unreached
    and nothing is removed.

    Delete this and the metadata ledger arriving in `obs` unattributed could be swept on the
    trace store's thirty days."""
    with psycopg.connect(server) as conn:
        report = sweep(PostgresSweeper(conn), now=NOW, report_only=False)
        conn.commit()

    assert {Store.LEDGER, Store.TRACE, Store.PAYLOAD, Store.AUDIT} <= set(report.unreached())
    assert any(
        A_TABLE_IN_A_SHARED_SCHEMA_BELONGS_TO_NOBODY_UNTIL_IT_IS_ATTRIBUTED in one
        for one in report.findings
    )
    assert len(remaining(server)) == 3


def test_a_fixed_window_table_with_no_clock_refuses_the_store(server: str) -> None:
    """Delete this and a table with no declared clock would be skipped, and kept forever."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn, clocks={"obs.audit_entry": "at"})
        with pytest.raises(RetentionError, match="declares no clock column"):
            sweeper.census(Store.TRACE, NOW)
        with pytest.raises(RetentionError, match="declares no clock column"):
            sweeper.expire(Store.TRACE, NOW)


def test_the_audit_store_is_reached_with_nothing_due_and_its_age_reported(server: str) -> None:
    """A row eleven years old in a class that never expires: nothing due, the age visible, and
    `expire` refuses outright.

    Delete this and the audit store could be counted on some window, or left unreached, and a
    chain that stopped growing would have no age anywhere."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn)
        census = sweeper.census(Store.AUDIT, NOW)
        assert (census.beyond_horizon, census.oldest_days) == (0, 4000)
        assert a_sweeper(conn, clocks={}).census(Store.AUDIT, NOW).oldest_days is None
        with pytest.raises(RetentionError, match="only a fixed window"):
            sweeper.expire(Store.AUDIT, NOW)
    assert sql(server, "SELECT count(*) FROM obs.audit_entry") == [(1,)]


def test_record_lifetime_stores_and_stores_outside_postgres_are_refused_by_name(
    server: str,
) -> None:
    """`ops` holds a table and is a record-lifetime store; the recordings bucket is not in
    PostgreSQL. Both refuse with their reasons, and the table in `ops` keeps its row.

    Delete this and either could be reported as reached with nothing due, which is a clean line
    for a store nobody counted."""
    sql(server, "INSERT INTO ops.something VALUES (%s)", OLD)
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn)
        with pytest.raises(RetentionError) as operations:
            sweeper.census(Store.OPERATIONS, NOW)
        with pytest.raises(RetentionError) as recordings:
            sweeper.census(Store.RECORDING, NOW)
        run_retention_sweep(conn, now=NOW, report_only=False)

    assert str(operations.value) == A_RECORD_LIFETIME_NEEDS_A_SUBJECT_REFERENCE_NOBODY_HAS_DECLARED
    assert str(recordings.value) == NOT_HELD_IN_POSTGRES
    assert sql(server, "SELECT count(*) FROM ops.something") == [(1,)]


def test_a_scheduled_run_returns_one_line_per_store_and_commits_its_removals(server: str) -> None:
    """`run_retention_sweep` over the shipped declarations, with the scratch table dropped so
    `obs` is attributable: the ledger, trace, payload and audit stores are reached, the rest are
    named, and the text carries a line for every store.

    Delete this and the entry point a scheduler calls could return before its transaction
    commits, or return the census without the report."""
    sql(server, f"DROP TABLE {TRACE_TABLE}")
    with psycopg.connect(server) as conn:
        text = run_retention_sweep(conn, now=NOW, report_only=False)

    lines = text.splitlines()
    for store in Store:
        assert any(line.startswith(f"{store.value}") for line in lines), store
    assert "ledger (metadata_ledger, 1825d): 0 due, 0 held, 0 removed, 0 queued" in lines
    assert "audit (audit, never_expires): 0 due, 0 held, 0 removed, 0 queued, oldest 4000d" in lines
    assert (
        f"recording: not reached, so nothing in it was considered, because {NOT_HELD_IN_POSTGRES}"
        in lines
    )


def test_a_table_the_application_role_may_not_delete_from_is_queued_and_keeps_its_rows(
    server: str,
) -> None:
    """The scratch trace table's DELETE taken away: the two old rows are counted as queued with
    the grant rule, the sweep removes nothing, and all three rows are still there.

    Delete this and the sweep could delete from a table whose own migration argued it has no
    DELETE, on the authority of the one mechanism with the widest reach in the estate."""
    sql(server, f"REVOKE DELETE ON {TRACE_TABLE} FROM brain_app")
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn)
        census = sweeper.census(Store.TRACE, NOW)
        report = sweep(sweeper, now=NOW, report_only=False)
        assert sweeper.expire(Store.TRACE, NOW) == 0
        conn.commit()

    assert (census.beyond_horizon, census.queued) == (2, 2)
    assert census.queued_because == A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO
    assert next(one for one in report.swept if one.store is Store.TRACE).removed == 0
    assert len(remaining(server)) == 3


def test_a_partitioned_table_is_queued_even_where_the_role_may_delete_from_it(server: str) -> None:
    """A trace-class table partitioned by its clock, with DELETE granted: still queued, because a
    partitioned table's rows leave with their partition. Held rows are not queued twice.

    Delete this and the metadata ledger, which is partitioned, could be swept row by row the day
    somebody grants DELETE on it for an unrelated reason."""
    parted = "obs.scratch_parted"
    sql(
        server,
        f"CREATE TABLE {parted} (at timestamptz NOT NULL, subject text NOT NULL) "
        "PARTITION BY RANGE (at)",
    )
    sql(server, f"CREATE TABLE obs.scratch_parted_default PARTITION OF {parted} DEFAULT")
    sql(server, f"GRANT SELECT, DELETE ON {parted} TO brain_app")
    for subject in ("u_one", "u_two", "u_three"):
        sql(server, "INSERT INTO obs.scratch_parted VALUES (%s, %s)", OLD, subject)
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(
            conn,
            attributed={**ATTRIBUTED, TRACE_TABLE: Store.TRACE, parted: Store.TRACE},
            clocks={"obs.audit_entry": "at", TRACE_TABLE: "at", parted: "at"},
            subjects={TRACE_TABLE: "subject", parted: "subject"},
            holds=(AHold(subjects=frozenset({"u_two"})),),
        )
        census = sweeper.census(Store.TRACE, NOW)
        removed = sweeper.expire(Store.TRACE, NOW)
        conn.commit()

    assert sweeper_rule(server, parted) == A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME
    assert (census.beyond_horizon, census.held, census.queued) == (5, 2, 2)
    assert removed == 1
    assert sql(server, "SELECT count(*) FROM obs.scratch_parted") == [(3,)]


def sweeper_rule(url: str, table: str) -> str:
    with psycopg.connect(url) as conn:
        return PostgresSweeper(conn).removal_rule(table)


def test_the_removal_rule_is_empty_only_for_an_ordinary_table_the_role_may_delete_from(
    server: str,
) -> None:
    """The positive case for `removal_rule`, and a table nothing knows refuses.

    Delete this and a rule that queued everything would pass both tests above."""
    assert sweeper_rule(server, TRACE_TABLE) == ""
    assert sweeper_rule(server, "ops.something") == (
        A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO
    )
    with pytest.raises(RetentionError, match="not in the catalogue"):
        sweeper_rule(server, "obs.nothing_here")


def _hold(
    url: str, hold_id: str, *, subjects: list[str], placed: datetime, lifted: datetime | None
) -> None:
    sql(
        url,
        "INSERT INTO obs.legal_hold (id, reason_code, subjects, actors, all_subjects, placed_at, "
        "placed_by, released_at, released_by) VALUES (%s, 'litigation', %s, '{}', false, %s, "
        "'u_admin', %s, %s)",
        hold_id,
        subjects,
        placed,
        lifted,
        None if lifted is None else "u_admin",
    )


def test_the_holds_a_run_reads_are_those_placed_by_its_instant_and_not_yet_lifted(
    server: str,
) -> None:
    """Four holds: live, lifted before the run, lifted after it, and placed after it. The run
    reads the first and the third.

    Delete this and a hold lifted last year could still suspend deletion, or one placed tomorrow
    could be honoured today, which a reader of the report could never explain."""
    _hold(server, "h_live", subjects=["u_one"], placed=OLD, lifted=None)
    _hold(server, "h_lifted", subjects=["u_one"], placed=OLD, lifted=NOW - timedelta(days=1))
    _hold(server, "h_lifted_later", subjects=["u_two"], placed=OLD, lifted=NOW + timedelta(days=1))
    _hold(server, "h_future", subjects=["u_two"], placed=NOW + timedelta(days=1), lifted=None)
    with psycopg.connect(server) as conn:
        read = active_holds(conn, NOW)

    assert [hold.id for hold in read] == ["h_live", "h_lifted_later"]
    assert read[0].subjects == frozenset({"u_one"})


def test_a_scheduled_run_writes_its_report_and_the_report_reads_back(server: str) -> None:
    """One run with a live hold: a row in `ops.retention_report` whose documents read back as the
    report whose lines the run returned, with the hold cited.

    Delete this and a run could return its lines to the run record and write nothing an
    administrator can read, which is where this leaf was before."""
    sql(server, f"DROP TABLE {TRACE_TABLE}")
    _hold(server, "h_live", subjects=["u_one"], placed=OLD, lifted=None)
    with psycopg.connect(server) as conn:
        text = run_retention_sweep(conn, now=NOW, report_only=True)

    rows = sql(
        server,
        "SELECT at, report_only, complete, stores, holds, findings, failure "
        "FROM ops.retention_report",
    )
    assert len(rows) == 1
    at, report_only, complete, stores, holds, findings, failure = rows[0]
    read = report_from_document(
        at=at, report_only=report_only, stores=stores, holds=holds, findings=findings
    )
    assert "\n".join(read.lines()) == text
    assert (report_only, complete, failure) == (True, False, None)
    assert read.holds == (
        CitedHold(hold_id="h_live", reason_code="litigation", company_wide=False),
    )


def test_a_run_that_cannot_read_its_holds_removes_nothing_writes_a_failed_report_and_raises(
    server: str,
) -> None:
    """The holds table gone: the run raises, the scratch trace table keeps all three rows, and a
    report saying the run failed is written anyway.

    Delete this and a sweep that could not see its holds could delete under one, or fail with
    the retention screen still showing yesterday's clean report as the latest."""
    sql(server, "DROP TABLE obs.legal_hold")
    with psycopg.connect(server) as conn, pytest.raises(psycopg.errors.UndefinedTable):
        run_retention_sweep(conn, now=NOW, report_only=False)

    rows = sql(server, "SELECT report_only, complete, failure FROM ops.retention_report")
    assert len(rows) == 1
    report_only, complete, failure = rows[0]
    assert (report_only, complete) == (False, False)
    assert failure.startswith("UndefinedTable: ")
    assert len(remaining(server)) == 3


def test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked(server: str) -> None:
    """Two runs, a release after the first refused, a release after the second recorded, read
    back as released, withdrawn, and read back as not.

    Delete this and the store's reads could disagree with `release_refusal` about which report
    is the newest, or a withdrawal could leave the sweep released."""
    sql(server, f"DROP TABLE {TRACE_TABLE}")
    with psycopg.connect(server) as conn:
        run_retention_sweep(conn, now=NOW - timedelta(days=1), report_only=True)
        run_retention_sweep(conn, now=NOW, report_only=True)
    first, second = (
        row[0] for row in sql(server, "SELECT id FROM ops.retention_report ORDER BY at")
    )

    async def exercise() -> tuple[ReleaseRefusal | None, frozenset[str], bool, frozenset[str]]:
        stale: ReleaseRefusal | None = None
        built = engine(server)
        try:
            async with AsyncSession(built) as session:
                try:
                    await release_sweep(session, after_report=first, by="u_admin", at=NOW)
                except ReleaseRefusedError as refused:
                    stale = refused.reason
                await release_sweep(session, after_report=second, by="u_admin", at=NOW)
                await session.commit()
                live = await released_controls(session, now=NOW)
                withdrawn = await withdraw_release(session, by="u_admin", at=NOW)
                await session.commit()
                after = await released_controls(session, now=NOW)
                return stale, live, withdrawn, after
        finally:
            await built.dispose()

    stale, live, withdrawn, after = run(exercise)
    assert stale is ReleaseRefusal.NOT_THE_NEWEST
    assert live == frozenset({RETENTION_SWEEP})
    assert withdrawn is True
    assert after == frozenset()
    assert sql(server, "SELECT count(*) FROM ops.retention_release") == [(1,)]


def test_a_hold_is_placed_lifted_once_and_kept(server: str) -> None:
    """Placed, lifted, lifted again: the second lift changes nothing and the row stays.

    Delete this and a second lift could move the recorded instant, or a lift could remove the
    record of whose data was held and for how long."""
    placed = LegalHold(
        id="h_dispute", reason_code="litigation", subjects=frozenset({"u_one"}), placed_at=OLD
    )

    async def exercise() -> tuple[bool, bool]:
        built = engine(server)
        try:
            async with AsyncSession(built) as session:
                await place_hold(session, placed, by="u_admin")
                first = await lift_hold(session, "h_dispute", by="u_admin", at=NOW)
                second = await lift_hold(
                    session, "h_dispute", by="u_other", at=NOW + timedelta(days=1)
                )
                await session.commit()
                return first, second
        finally:
            await built.dispose()

    assert run(exercise) == (True, False)
    assert sql(server, "SELECT released_at, released_by FROM obs.legal_hold") == [(NOW, "u_admin")]


def test_the_oldest_age_is_the_oldest_row_across_every_table_a_store_holds(server: str) -> None:
    """A second trace-class table holding only a young row, read after the first: the store's
    oldest age is still the old row's.

    Delete this and the comparison across tables could keep the last table's minimum, so a store
    with one stale table and one busy one would report the busy one's age."""
    sql(server, "CREATE TABLE obs.scratch_trace_young (at timestamptz NOT NULL)")
    sql(server, "INSERT INTO obs.scratch_trace_young VALUES (%s)", YOUNG)
    young = "obs.scratch_trace_young"
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(
            conn,
            attributed={**ATTRIBUTED, TRACE_TABLE: Store.TRACE, young: Store.TRACE},
            clocks={"obs.audit_entry": "at", TRACE_TABLE: "at", young: "at"},
        )
        census = sweeper.census(Store.TRACE, NOW)
    assert (census.beyond_horizon, census.oldest_days) == (2, TRACE_RETENTION_DAYS + 10)
