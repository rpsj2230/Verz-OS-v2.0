"""The access review's store: what a decision writes, in what order, and that it reaches the system.

The first half needs no server. It reads each statement as the SQL it compiles to, holds the two
decision vocabularies and the trigger's details against the recorder's, and drives `decide` over a
stub session that records whether the transaction committed or rolled back, which is the property
a removal rests on.

The second half builds a database through `0052` and proves a decision reaches the system in the
three places `docs/admin-console.md` names: the rows, the ledger entries the triggers append, and
the behaviour, which for a removal is the resolver no longer returning the grant. It skips when
there is no server, and CI always has one.

Task ids: M27.7.9
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import AuditRecorder
from brain.console.govern import Decision
from brain.gate.review_store import (
    GrantHolding,
    Holding,
    PackHolding,
    StoredReview,
    decisions_about,
    newest,
    one_assignment_to_decide,
    one_grant_to_decide,
    record_decision,
    retire,
)
from brain.session import make_session_factory
from brain.tables.gate import CapabilityGrantRow, CapabilityPackAssignmentRow, CapabilityPackRow
from brain.tables.review import ReviewDecision, ReviewDecisionRow
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import VERSIONS, migration_module

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

GRANT_ID = uuid.UUID("1f0e6a4c-2b8d-4f7a-9c1e-5d3b2a7f8e90")
ASSIGNMENT_ID = uuid.UUID("2a1b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d")


def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def a_grant_holding() -> GrantHolding:
    row = CapabilityGrantRow(
        id=GRANT_ID,
        principal_id="u_holder",
        capability="read:client.name",
        scope={"clauses": []},
        granted_by="u_seed",
        reason="the job needs it",
        not_after=None,
    )
    return GrantHolding(row=row, display_name="Holder", department="web")


def a_pack_holding() -> PackHolding:
    pack = CapabilityPackRow(
        id=uuid.uuid4(), name="pricing", description="a pack", capabilities=["read:client.name"]
    )
    row = CapabilityPackAssignmentRow(
        id=ASSIGNMENT_ID,
        principal_id="u_holder",
        pack_id=pack.id,
        scope={"clauses": []},
        granted_by="u_seed",
        reason="joined",
        not_after=None,
    )
    return PackHolding(row=row, pack=pack, display_name="Holder", department="web")


# ------------------------------------------------------------------- the vocabularies


def test_the_table_and_the_console_decide_between_the_same_two_words() -> None:
    """Delete this and `brain.console.govern.Decision` can gain a member the table's constraint
    refuses, which is a decision a person makes on the screen and the database throws away, or the
    table can admit a word no decision produces."""
    assert {one.value for one in ReviewDecision} == {one.value for one in Decision}


def test_the_trigger_writes_the_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps and the entry `AuditRecorder` writes
    for a chain held anywhere else can come apart without a server to notice. The trigger's body is
    read off the migration module that executes it, and the recorder's details from the recorder,
    for a direct grant and for a pack."""
    migration = migration_module(VERSIONS / "0052_review_decision.py")
    recorder = AuditRecorder(
        AuditChain(), actor_id="u_lead", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    )
    direct = recorder.certification(
        grant_id=str(GRANT_ID), decision=ReviewDecision.KEEP, capability="read:client.name"
    )
    packed = recorder.certification(
        grant_id=str(ASSIGNMENT_ID), decision=ReviewDecision.REMOVE, pack="pricing"
    )
    body = " ".join(migration.REVIEW_DECISION_TRIGGER_FUNCTION.split())

    assert list(direct.details) == ["decision", "capability"]
    assert list(packed.details) == ["decision", "pack"]
    assert direct.subject == f"grant:{GRANT_ID}"
    assert "'decision', NEW.decision, 'capability'," in body
    assert "'decision', NEW.decision, 'pack'," in body
    assert "'certification', 'grant:' || v_row_id" in body
    assert "v_seq, v_at, NEW.decided_by, 'certification'" in body


def test_a_decision_names_a_grant_or_a_pack_and_never_both_or_neither() -> None:
    """Delete this and the recorder writes an entry naming both a capability and a pack, which is
    a decision about two rows that the table's own constraint refuses to store."""
    recorder = AuditRecorder(
        AuditChain(), actor_id="u_lead", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    )
    for capability, pack in (("read:client.name", "pricing"), ("", "")):
        try:
            recorder.certification(
                grant_id=str(GRANT_ID),
                decision=ReviewDecision.KEEP,
                capability=capability,
                pack=pack,
            )
        except ValueError:
            continue
        raise AssertionError(f"capability={capability!r} pack={pack!r} was recorded")


# ------------------------------------------------------------------- the statements


def test_a_decision_row_names_exactly_the_table_its_holding_came_from() -> None:
    """Delete this and a pack's decision can be written against `grant_id`, which the foreign key
    then refuses or, worse, finds a grant with that id and records a decision about it."""
    direct = record_decision(a_grant_holding(), ReviewDecision.KEEP, "u_lead")
    packed = record_decision(a_pack_holding(), ReviewDecision.REMOVE, "u_lead")

    assert "grant_id" in compiled(direct) and "assignment_id" not in compiled(direct)
    assert "assignment_id" in compiled(packed) and "grant_id" not in compiled(packed)
    assert direct.compile().params["decided_by"] == "u_lead"
    assert packed.compile().params["decision"] == "remove"


def test_retiring_touches_only_deleted_at_on_a_row_still_live() -> None:
    """Delete this and a removal can rewrite a grant's scope or reason, or retire a row somebody
    already retired and move the instant the ledger's revoke was stamped at."""
    for holding, table in (
        (a_grant_holding(), "gate.capability_grant"),
        (a_pack_holding(), "gate.capability_pack_assignment"),
    ):
        sql_text = compiled(retire(holding))
        assigned = sql_text.split(" WHERE ")[0].split(" SET ")[1]
        assert sql_text.split(" SET ")[0] == " ".join(("UPDATE", table))
        assert assigned == "updated_at=now(), deleted_at=now()"
        assert table + ".deleted_at IS NULL" in sql_text
        assert sql_text.endswith("RETURNING " + table + ".deleted_at")


def test_the_row_being_decided_is_locked_and_must_still_be_live() -> None:
    """Delete this and two reviewers deciding one grant at once each record a decision about a row
    the other has already retired, or a retired grant is decided at all."""
    grant = compiled(one_grant_to_decide(GRANT_ID))
    assignment = compiled(one_assignment_to_decide(ASSIGNMENT_ID))

    assert grant.endswith("FOR UPDATE OF capability_grant")
    assert "gate.capability_grant.deleted_at IS NULL" in grant
    assert assignment.endswith("FOR UPDATE OF capability_pack_assignment")
    assert "gate.capability_pack.deleted_at IS NULL" in assignment


def test_the_newest_decision_about_each_row_is_the_one_shown() -> None:
    """Delete this and a grant kept last week and removed from a review this morning, then granted
    again, reads as kept by whoever decided first."""
    older = ReviewDecisionRow(
        grant_id=GRANT_ID, principal_id="u_holder", decision="keep", decided_by="u_first"
    )
    older.created_at = LONG_AGO
    newer = ReviewDecisionRow(
        grant_id=GRANT_ID, principal_id="u_holder", decision="remove", decided_by="u_second"
    )
    newer.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    packed = ReviewDecisionRow(
        assignment_id=ASSIGNMENT_ID, principal_id="u_holder", decision="keep", decided_by="u_p"
    )
    packed.created_at = LONG_AGO

    found = newest([newer, older, packed])

    assert found[GRANT_ID].decided_by == "u_second"
    assert found[GRANT_ID].decision is ReviewDecision.REMOVE
    assert found[ASSIGNMENT_ID].decided_by == "u_p"
    assert "ORDER BY gate.review_decision.created_at DESC" in compiled(decisions_about([GRANT_ID]))


# ------------------------------------------------------------ the store's orchestration


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None

    def scalar_one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None


class _Session:
    """An `AsyncSession` in the shape `decide` uses, recording what it sent and how it ended."""

    def __init__(self, answers: Callable[[str], list[Any]], log: list[str]) -> None:
        self.answers = answers
        self.log = log

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        yield

    def begin(self) -> _Transaction:
        return _Transaction(self.log)

    async def execute(self, statement: Any, *_: Any, **__: Any) -> _Result:
        sql_text = compiled(statement)
        self.log.append(sql_text.split(" ")[0])
        return _Result(self.answers(sql_text))


class _Transaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, kind: object, *_: object) -> None:
        self.log.append("ROLLBACK" if kind is not None else "COMMIT")


def stub_review(answers: Callable[[str], list[Any]]) -> tuple[StoredReview, list[str]]:
    log: list[str] = []
    return StoredReview(lambda: _Session(answers, log)), log  # type: ignore[arg-type]


def answering(*, retired: bool = True) -> Callable[[str], list[Any]]:
    holding = a_grant_holding()

    def answer(sql_text: str) -> list[Any]:
        if sql_text.startswith("SELECT gate.capability_grant"):
            return [(holding.row, holding.display_name, holding.department)]
        if sql_text.startswith("INSERT INTO gate.review_decision"):
            return [LONG_AGO]
        if sql_text.startswith("UPDATE"):
            return [LONG_AGO] if retired else []
        return []

    return answer


def decide(store: StoredReview, decision: ReviewDecision, may: Callable[[Holding], bool]) -> Any:
    return run(
        lambda: store.decide(
            GRANT_ID,
            pack=False,
            decision=decision,
            may=may,
            decided_by="u_lead",
            ent_hash="0" * 32,
            trace_id="t",
        )
    )


def test_a_kept_grant_records_the_decision_and_retires_nothing() -> None:
    """M27.7.9, the positive case. Delete this and keeping a grant can retire it, or record nothing
    and still answer that it was kept."""
    store, log = stub_review(answering())

    decided = decide(store, ReviewDecision.KEEP, lambda holding: True)

    assert decided is not None and decided.decision is ReviewDecision.KEEP
    assert log == ["SELECT", "SELECT", "SELECT", "SELECT", "INSERT", "COMMIT"]


def test_a_removal_records_the_decision_and_retires_the_row_in_one_commit() -> None:
    """Delete this and a removal can record the decision and leave the grant conferring everything
    it did, which is a review completed over access nobody took away."""
    store, log = stub_review(answering())

    decided = decide(store, ReviewDecision.REMOVE, lambda holding: True)

    assert decided is not None and decided.principal_id == "u_holder"
    assert log[-3:] == ["INSERT", "UPDATE", "COMMIT"]


def test_a_removal_whose_row_was_retired_first_rolls_the_decision_back() -> None:
    """`A_REMOVAL_THAT_RECORDS_THE_DECISION_AND_NOT_THE_REMOVAL_IS_A_KEEP`. Delete this and the
    decision row commits while the retirement wrote nothing."""
    store, log = stub_review(answering(retired=False))

    assert decide(store, ReviewDecision.REMOVE, lambda holding: True) is None
    assert log[-1] == "ROLLBACK"


def test_a_decision_the_caller_may_not_make_writes_nothing() -> None:
    """Delete this and `may` is asked and ignored: the decision row is written for a grant the
    reviewer could not have written, which is the original decision laundered through a round."""
    store, log = stub_review(answering())
    asked: list[Holding] = []

    def refuses(holding: Holding) -> bool:
        asked.append(holding)
        return False

    assert decide(store, ReviewDecision.KEEP, refuses) is None
    assert len(asked) == 1 and asked[0].row.id == GRANT_ID
    assert "INSERT" not in log and log[-1] == "ROLLBACK"


# ------------------------------------------------------------------- the database


@contextmanager
def through_0052(database: str) -> Iterator[str]:
    """The soft-deleted tables with `0050` and `0052` applied. Without pgvector, `retirable` stops
    at `0048`'s function, and `0047`, `0050` and `0052` are run for real over stamps of the rest."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "stamp", "0046")
            migrate(database, "upgrade", "0047")
            migrate(database, "stamp", "0049")
            migrate(database, "upgrade", "0050")
            migrate(database, "stamp", "0051")
            migrate(database, "upgrade", "0052")
        yield url


def seeded(url: str) -> tuple[uuid.UUID, uuid.UUID]:
    """A holder, a direct grant and a pack assignment. Returns the grant's and assignment's ids."""
    for pid in ("u_holder", "u_lead"):
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
            " VALUES (%s, 'human', 'staff', %s, 'web')",
            pid,
            f"Person {pid}",
        )
    [(grant_id,)] = sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason)"
        " VALUES ('u_holder', 'read:client.name', '{\"clauses\": []}', 'u_seed', 'needed')"
        " RETURNING id",
    )
    [(pack_id,)] = sql(
        url,
        "INSERT INTO gate.capability_pack (name, description, capabilities)"
        " VALUES ('pricing', 'a pack', ARRAY['read:invoice.total']) RETURNING id",
    )
    [(assignment_id,)] = sql(
        url,
        "INSERT INTO gate.capability_pack_assignment"
        " (principal_id, pack_id, scope, granted_by, reason)"
        " VALUES ('u_holder', %s, '{\"clauses\": []}', 'u_seed', 'joined') RETURNING id",
        pack_id,
    )
    return grant_id, assignment_id


def with_review(url: str, work: Callable[[StoredReview], Any]) -> Any:
    async def go() -> Any:
        engine = app_engine(url)
        try:
            return await work(StoredReview(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def entries(url: str, action: str) -> list[AuditEntry]:
    rows = sql(
        url,
        "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
        " entry_hash FROM obs.audit_entry WHERE action = %s ORDER BY seq",
        action,
    )
    names = (
        "seq",
        "at",
        "actor_id",
        "action",
        "subject",
        "ent_hash",
        "trace_id",
        "details",
        "prev_hash",
        "entry_hash",
    )
    return [AuditEntry(**dict(zip(names, row, strict=True))) for row in rows]


def test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to() -> (
    None
):
    """M27.7.9's proof that the control reaches the system, in one database.

    Kept: a decision row naming the lead, a `certification` entry with the lead as actor and the
    request's digest and trace, and the grant still live. Removed: a second decision row, the
    assignment retired, a `certification` entry and a `revoke` entry attributed to the lead, and
    `gate.resolve_entitlements` no longer returning the pack's capability. Delete this and every
    one of those can be false in production while the stubbed tests above stay green."""
    with through_0052("brain_review_decide") as url:
        grant_id, assignment_id = seeded(url)

        def allow(holding: Holding) -> bool:
            return True

        async def both(store: StoredReview) -> tuple[Any, Any]:
            kept = await store.decide(
                grant_id,
                pack=False,
                decision=ReviewDecision.KEEP,
                may=allow,
                decided_by="u_lead",
                ent_hash="a" * 32,
                trace_id="trace-keep",
            )
            removed = await store.decide(
                assignment_id,
                pack=True,
                decision=ReviewDecision.REMOVE,
                may=allow,
                decided_by="u_lead",
                ent_hash="b" * 32,
                trace_id="trace-remove",
            )
            return kept, removed

        kept, removed = with_review(url, both)
        rows = sql(
            url,
            "SELECT grant_id, assignment_id, decision, decided_by FROM gate.review_decision"
            " ORDER BY created_at, decision",
        )
        grant_live = sql(
            url, "SELECT deleted_at IS NULL FROM gate.capability_grant WHERE id = %s", grant_id
        )
        assignment_live = sql(
            url,
            "SELECT deleted_at IS NULL FROM gate.capability_pack_assignment WHERE id = %s",
            assignment_id,
        )
        certified = entries(url, "certification")
        revoked = entries(url, "revoke")
        held = sql(url, "SELECT gate.resolve_entitlements('u_holder', now())")

    assert kept is not None and removed is not None
    assert rows == [
        (grant_id, None, "keep", "u_lead"),
        (None, assignment_id, "remove", "u_lead"),
    ]
    assert grant_live == [(True,)] and assignment_live == [(False,)]
    assert [(one.actor_id, one.subject, dict(one.details)) for one in certified] == [
        ("u_lead", f"grant:{grant_id}", {"decision": "keep", "capability": "read:client.name"}),
        ("u_lead", f"grant:{assignment_id}", {"decision": "remove", "pack": "pricing"}),
    ]
    assert [(one.ent_hash, one.trace_id) for one in certified] == [
        ("a" * 32, "trace-keep"),
        ("b" * 32, "trace-remove"),
    ]
    assert [one.actor_id for one in revoked] == ["u_lead"]
    capabilities = {one["capability"]["value"] for one in held[0][0]["grants"]}
    assert "read:client.name" in capabilities
    assert "read:invoice.total" not in capabilities


def test_nobody_can_record_a_decision_about_their_own_grant_even_bypassing_the_console() -> None:
    """`not_decided_by_its_subject`. Delete this and a hand-written insert, or a `may` that forgot
    `govern.Certification`'s refusal, records somebody renewing their own access, and the store
    must answer it as the ordinary refusal rather than a 500 carrying the constraint's name."""
    with through_0052("brain_review_self") as url:
        grant_id, _ = seeded(url)

        async def own(store: StoredReview) -> Any:
            return await store.decide(
                grant_id,
                pack=False,
                decision=ReviewDecision.KEEP,
                may=lambda holding: True,
                decided_by="u_holder",
                ent_hash="0" * 32,
                trace_id="t",
            )

        answer = with_review(url, own)
        rows = sql(url, "SELECT count(*) FROM gate.review_decision")
        certified = entries(url, "certification")

    assert answer is None
    assert rows == [(0,)]
    assert certified == []
