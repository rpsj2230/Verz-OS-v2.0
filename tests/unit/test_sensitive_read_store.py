"""Every read of a sensitive record is written down, from what the caller was shown, and no other.

The first half needs no server: `reads_of` over finished requests built as the lane builds them,
an answer and an automation step, with records as the redactor leaves them. The second half runs
against a scratch PostgreSQL as the application role and **skips without a server**, which is
every development machine here; CI always has one. It holds the row's trigger to the entry
`brain.audit.record.AuditRecorder.record_read` builds, and a budget version to the `setting`
entry `0098` writes for it.

Task ids: M24.3.2, M24.3.7
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder
from brain.core.entitlement import EntitlementSet
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.redaction import ChannelPayload
from brain.gate.answer import LANE, Answered
from brain.gate.compose import ComposedAnswer
from brain.gate.context import Channel
from brain.gate.finish import Finished, FinishError, ModelCallOutcome, Origin, ToolCallOutcome
from brain.ops.sensitive_read_store import (
    SensitiveRead,
    SensitiveReadError,
    SensitiveReadRecorder,
    reads_of,
    row_values,
)

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
READER = Principal(
    id="u_reader", kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name="Reader"
)
ORIGIN = Origin(trace_id="trace1", principal=READER, channel=Channel.CONSOLE)
ENT = EntitlementSet(principal_id="u_reader").ent_hash()

PERSONNEL = {"@entity": "personnel", "@id": "p_7", "principal_id": "u_priya", "name": "Priya"}
CONTRACT_WITH_SALARY = {"@entity": "contract", "@id": "c_12", "salary": 5000, "title": "Lead"}
CONTRACT_MASKED = {"@entity": "contract", "@id": "c_13", "title": "Lead"}
CLIENT = {"@entity": "client", "@id": "cl_1", "name": "A client"}


def payload(*records: Mapping[str, Any]) -> ChannelPayload:
    return ChannelPayload(records=tuple(dict(one) for one in records))


def answered(*records: Mapping[str, Any]) -> Answered:
    shown = payload(*records)
    return Answered(
        frames=("done",),
        composed=ComposedAnswer(
            text="an answer", citations=(), payload=shown, trace_ref="ref", grounded=True
        ),
    )


def finished(outcome: object, *, agent_id: str | None = None) -> Finished:
    return Finished(
        ORIGIN,
        LONG_AGO,
        outcome,  # type: ignore[arg-type]
        completed_at=LONG_AGO,
        entitlement_hash=ENT,
        lane=LANE,
        tool_calls=1,
        agent_id=agent_id,
    )


# --------------------------------------------------------------------------- which reads


def test_a_personnel_record_and_a_shown_salary_are_each_one_read_and_nothing_else_is() -> None:
    """**The sentence M24.3.2 is.** Four records shown in one answer: a personnel record, a contract
    whose salary was shown, a contract whose salary was masked, and a client. Two reads, one per
    record in the declared set, each naming the reader, the kind and the record. Delete this and
    the recorder can write one row per request, or a row for the masked contract, or a row for the
    client, and item 45's narrow set becomes Option B one read at a time."""
    found = reads_of(finished(answered(PERSONNEL, CONTRACT_WITH_SALARY, CONTRACT_MASKED, CLIENT)))
    assert found == (
        SensitiveRead(
            reader_id="u_reader",
            agent_id=None,
            record_kind="personnel",
            subject_principal="u_priya",
            record_id=None,
            ent_hash=ENT,
            trace_id="trace1",
        ),
        SensitiveRead(
            reader_id="u_reader",
            agent_id=None,
            record_kind="contract",
            subject_principal=None,
            record_id="c_12",
            ent_hash=ENT,
            trace_id="trace1",
        ),
    )


def test_the_agent_a_lane_ran_is_named_on_the_read() -> None:
    """Delete this and "which agents have read my HR record", the question item 45 exists for, is
    answered with a person's name and never an agent's."""
    [read] = reads_of(finished(answered(PERSONNEL), agent_id="hr_helper"))
    assert read.agent_id == "hr_helper"


def test_a_record_an_automation_step_was_handed_is_a_read_too() -> None:
    """The second way a record reaches somebody. Delete this and every read through an automation
    goes unrecorded, silently, because the recorder only looked at answers."""
    step = ToolCallOutcome(refused=False, disclosed=payload(PERSONNEL))
    [read] = reads_of(finished(step))
    assert (read.record_kind, read.subject_principal) == ("personnel", "u_priya")


def test_a_refused_step_cannot_carry_what_it_refused() -> None:
    """Delete this and a refusal can be built carrying the records it withheld, and every recorder,
    the telemetry one included, is handed what the gate refused to show."""
    with pytest.raises(FinishError):
        ToolCallOutcome(refused=True, disclosed=payload(PERSONNEL))


def test_nothing_shown_is_nothing_read() -> None:
    """A refused step, an abstention, a model check and a fault each disclosed no record. Delete
    this and a refusal can be written down as a read, which puts a denial on the subject's page as
    though it were a disclosure."""
    assert reads_of(finished(ToolCallOutcome(refused=True))) == ()
    assert reads_of(finished(Answered(frames=("nothing",)))) == ()
    assert reads_of(finished(ModelCallOutcome(answered=True))) == ()
    assert reads_of(finished(None)) == ()
    assert reads_of(finished(answered(CLIENT, CONTRACT_MASKED))) == ()


def test_a_sensitive_record_with_no_id_the_ledger_can_file_fails_the_request_in_words() -> None:
    """Shown and unfileable is a read that would go unrecorded. Delete this and such a read is
    skipped, and the member's log is short by exactly the reads nobody can check."""
    unfileable = {"@entity": "personnel", "@id": "has a space", "name": "Priya"}
    with pytest.raises(SensitiveReadError) as refused:
        reads_of(finished(answered(unfileable)))
    assert "Priya" not in str(refused.value)
    assert "has a space" not in str(refused.value)


def test_the_row_carries_the_reach_digest_and_trace_of_the_request() -> None:
    """Delete this and the row can take its digest from a session setting a route never made,
    which is the placeholder M24.3.1 exists to refuse."""
    [read] = reads_of(finished(answered(PERSONNEL)))
    values = row_values(read)
    assert (values["ent_hash"], values["trace_id"]) == (ENT, "trace1")
    assert "at" not in values


# ------------------------------------------------------------------------ what a failure means


class FailingSessions:
    """A session factory whose every transaction fails, as a database that went away does."""

    def __call__(self) -> Any:
        raise ConnectionError("the database went away")


def test_a_read_that_cannot_be_written_fails_the_request() -> None:
    """See A_SENSITIVE_READ_THAT_CANNOT_BE_WRITTEN_IS_NOT_SHOWN. Delete this and the recorder can
    be changed to catch its failure the way the measurements do, and a personnel record is shown
    with its reading unrecorded."""
    recorder = SensitiveReadRecorder(FailingSessions())  # type: ignore[arg-type]
    with pytest.raises(ConnectionError):
        asyncio.run(recorder.finished(finished(answered(PERSONNEL))))


def test_a_request_with_no_sensitive_read_never_opens_a_transaction() -> None:
    """The sibling: an ordinary read costs nothing and cannot fail on the database. Delete this and
    every answer depends on a write that only a sensitive read needs."""
    recorder = SensitiveReadRecorder(FailingSessions())  # type: ignore[arg-type]
    asyncio.run(recorder.finished(finished(answered(CLIENT))))


# ------------------------------------------------------------------------ with a server


def _entries(url: str) -> Sequence[Any]:
    from tests.unit.test_credential_writes import entries

    return entries(url)


@pytest.mark.needs_db
def test_a_written_read_appends_exactly_the_recorders_entry_and_the_chain_holds() -> None:
    """M24.3.2 end to end, as the role the application logs in with: two reads, two rows, two
    `record_read` entries whose actor, subject and details are `AuditRecorder.record_read`'s, the
    reach digest and trace the request's, the chain verifying, and the row not editable. **Skips
    without a server.**"""
    from brain.session import make_session_factory
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine

    with retirable("brain_sensitive_read") as url:
        if not has_pgvector(url):
            pytest.skip("0098 needs the whole chain, which needs pgvector")

        async def record() -> None:
            engine = app_engine(url)
            try:
                sessions: async_sessionmaker[AsyncSession] = make_session_factory(engine)
                await SensitiveReadRecorder(sessions).finished(
                    finished(answered(PERSONNEL, CONTRACT_WITH_SALARY), agent_id="hr_helper")
                )
            finally:
                await engine.dispose()

        run(record)
        chain = list(_entries(url))
        [(may_update,)] = sql(
            url, "SELECT has_table_privilege('brain_app', 'ops.sensitive_read', 'UPDATE')"
        )

    recorder = AuditRecorder(
        AuditChain(), actor_id="u_reader", ent_hash=ENT, trace_id="trace1", clock=lambda: LONG_AGO
    )
    expected = [
        recorder.record_read(
            subject_id="u_priya", entity="personnel", disclosed=("name",), agent_id="hr_helper"
        ),
    ]
    reads = [one for one in chain if one.action.value == "record_read"]
    assert [(one.subject, one.actor_id, one.details) for one in reads[:1]] == [
        (one.subject, "u_reader", one.details) for one in expected
    ]
    assert reads[1].subject == "entity:c_12"
    assert reads[1].details == {"record_kind": "contract", "agent": "hr_helper"}
    assert {(one.ent_hash, one.trace_id) for one in reads} == {(ENT, "trace1")}
    assert AuditChain(chain).verify() is None
    assert may_update is False


@pytest.mark.needs_db
def test_a_budget_version_appends_a_setting_entry_filed_under_whose_money_it_counts() -> None:
    """M24.3.7 against the real trigger: a person's ceiling is filed under `principal:`, carries
    the level and the period and never the figure, and is attributed to its author. **Skips
    without a server.**"""
    from brain.ops.budget_store import append
    from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
    from brain.session import make_session_factory
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import run
    from tests.unit.test_automation_owner_store import app_engine

    with retirable("brain_budget_audit") as url:
        if not has_pgvector(url):
            pytest.skip("0098 needs the whole chain, which needs pgvector")

        async def write() -> None:
            engine = app_engine(url)
            try:
                sessions: async_sessionmaker[AsyncSession] = make_session_factory(engine)
                async with sessions() as session, session.begin():
                    await append(
                        session,
                        BudgetRow(
                            level=BudgetLevel.USER,
                            subject="u_priya",
                            period=BudgetPeriod.MONTH,
                            ceiling_minor=424242,
                            version=1,
                            author="u_admin",
                            effective_from=LONG_AGO,
                        ),
                    )
            finally:
                await engine.dispose()

        run(write)
        chain = list(_entries(url))

    [entry] = [one for one in chain if one.action.value == "setting"]
    assert (entry.subject, entry.actor_id) == ("principal:u_priya", "u_admin")
    assert entry.details == {"budget_level": "user", "budget_period": "month"}
    assert "424242" not in str(entry.details)
    assert AuditChain(chain).verify() is None


# ------------------------------------------------------------------------ the migration


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """Compared as rendered DDL, for `0009`'s reason about a migration that copies its patterns.
    Delete this and the model can drift from the table `0098` builds, and the recorder writes
    columns the database refuses."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from sqlalchemy.schema import CreateTable

    from brain.db import metadata
    from tests.unit.test_tables import VERSIONS, rendered, squash

    dialect = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
    migration = VERSIONS / "0098_sensitive_reads_and_budget_audit.py"
    expected = squash(
        str(CreateTable(metadata.tables["ops.sensitive_read"]).compile(dialect=dialect))
    )
    upgrade = squash(rendered("upgrade", migration))
    assert expected in upgrade
    assert "UPDATE ON ops.sensitive_read" not in upgrade
    assert "DELETE ON ops.sensitive_read" not in upgrade
