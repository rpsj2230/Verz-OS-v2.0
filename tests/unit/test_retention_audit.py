"""A retention release and a legal hold reach the ledger, from `0054`'s two triggers.

The first half needs no server. It reads each trigger function off the migration that executes it
and holds its subject, its actors, its change words and its details to
`AuditRecorder.retention` and `AuditRecorder.legal_hold`, and it holds that a hold's lists of whom
it names appear nowhere in its trigger.

The second half builds a database through `0054` and makes the four writes through the functions
`brain.retention_routes` calls, as the application role: each leaves exactly one entry with the
actor its own column names, the chain verifies, an update that neither withdraws nor lifts leaves
nothing, and a row written already finished leaves both of its changes. **It skips when there is no
server**, which is every development machine here, and CI always has one.

Task ids: M25.1.5
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from brain.audit.ledger import AuditChain, LegalHold
from brain.audit.record import AuditRecorder, LegalHoldChange, RetentionChange
from brain.ops.retention_store import lift_hold, place_hold, release_sweep, withdraw_release
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credential_writes import entries, through_0054
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0054_credential_and_retention_audit.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
AT = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

RELEASE_ID = "3c2b1a09-8f7e-4d6c-9b5a-1e2d3c4b5a69"


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: AT
    )


def body(name: str) -> str:
    return " ".join(getattr(migration_module(MIGRATION), name).split())


def words_and_actors(function: str) -> list[tuple[str, str]]:
    """Each change word a trigger appends, beside the column it reads that change's actor from."""
    return re.findall(
        r"v_changes := v_changes \|\| '(\w+)'::text; v_actors := v_actors \|\| NEW\.(\w+)::text;",
        function,
    )


# ------------------------------------------------------------------ the triggers' shape


def test_the_release_trigger_writes_the_subject_changes_and_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps for a release and the entry
    `AuditRecorder.retention` writes can come apart: a change word the enum does not have, a
    withdrawal attributed to whoever released, or a detail beside the change. Read off the function
    the migration executes, both halves of the one-way update included."""
    function = body("RETENTION_RELEASE_TRIGGER_FUNCTION")
    released = recorder().retention(release_id=RELEASE_ID, change=RetentionChange.RELEASED)
    withdrawn = recorder().retention(release_id=RELEASE_ID, change=RetentionChange.WITHDRAWN)

    assert words_and_actors(function) == [
        ("released", "released_by"),
        ("withdrawn", "withdrawn_by"),
        ("withdrawn", "withdrawn_by"),
    ]
    assert {word for word, _ in words_and_actors(function)} == {
        one.value for one in RetentionChange
    }
    assert "v_subject text := 'retention:' || NEW.id::text;" in function
    assert "v_details := jsonb_build_object('change', v_changes[i]);" in function
    assert "v_seq, v_at, v_actors[i], 'retention', v_subject, v_ent_hash," in function
    assert "ELSIF OLD.withdrawn_at IS NULL AND NEW.withdrawn_at IS NOT NULL THEN" in function
    assert (released.subject, dict(released.details)) == (
        f"retention:{RELEASE_ID}",
        {"change": "released"},
    )
    assert dict(withdrawn.details) == {"change": "withdrawn"}


def test_the_hold_trigger_writes_the_subject_changes_and_details_and_never_whom_it_names() -> None:
    """Delete this and the hold's trigger can drift from `AuditRecorder.legal_hold`, or be given
    the hold's subjects or actors to make an entry more useful, which copies a list of whose data
    is under legal hold into the table kept longest and read most widely."""
    function = body("LEGAL_HOLD_TRIGGER_FUNCTION")
    placed = recorder().legal_hold(hold_id="h_dispute", change=LegalHoldChange.PLACED)
    lifted = recorder().legal_hold(hold_id="h_dispute", change=LegalHoldChange.LIFTED)

    assert words_and_actors(function) == [
        ("placed", "placed_by"),
        ("lifted", "released_by"),
        ("lifted", "released_by"),
    ]
    assert {word for word, _ in words_and_actors(function)} == {
        one.value for one in LegalHoldChange
    }
    assert "v_subject text := 'legal_hold:' || NEW.id;" in function
    assert "v_details := jsonb_build_object('change', v_changes[i]);" in function
    assert "v_seq, v_at, v_actors[i], 'legal_hold', v_subject, v_ent_hash," in function
    assert "ELSIF OLD.released_at IS NULL AND NEW.released_at IS NOT NULL THEN" in function
    assert all(f"NEW.{column}" not in function for column in ("subjects", "actors", "all_subjects"))
    assert (placed.subject, dict(placed.details)) == ("legal_hold:h_dispute", {"change": "placed"})
    assert dict(lifted.details) == {"change": "lifted"}


def test_both_triggers_are_created_on_the_insert_and_the_update_of_their_tables() -> None:
    """The update the triggers judge has to reach them. Delete this and a trigger created on
    INSERT alone records every release and hold and never a withdrawal or a lift, which is the
    half an auditor comes back for."""
    emitted = squash(rendered("upgrade", MIGRATION))

    assert (
        "CREATE TRIGGER retention_release_is_audited AFTER INSERT OR UPDATE ON "
        "ops.retention_release FOR EACH ROW EXECUTE FUNCTION ops.record_retention_release()"
    ) in emitted
    assert (
        "CREATE TRIGGER legal_hold_is_audited AFTER INSERT OR UPDATE ON obs.legal_hold "
        "FOR EACH ROW EXECUTE FUNCTION obs.record_legal_hold()"
    ) in emitted


# ------------------------------------------------------------------------ the database


def a_report(url: str) -> uuid.UUID:
    """A report-only run with nothing in it, the day before, which a release may name."""
    [(report,)] = sql(
        url,
        "INSERT INTO ops.retention_report (at, report_only, complete, stores, holds, findings) "
        "VALUES (%s, true, false, '[]', '[]', '[]') RETURNING id",
        AT - timedelta(days=1),
    )
    return uuid.UUID(str(report))


def as_application(url: str, work: Any) -> Any:
    """Run `work(session)` in one committed transaction as the application role."""

    async def go() -> Any:
        engine = app_engine(url)
        try:
            async with make_session_factory(engine)() as session:
                answer = await work(session)
                await session.commit()
                return answer
        finally:
            await engine.dispose()

    return run(go)


def seen(url: str) -> list[tuple[str, str, str, dict[str, str]]]:
    return [
        (one.action.value, one.actor_id, one.subject, dict(one.details)) for one in entries(url)
    ]


def test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor() -> None:
    """M27.8.17 for the Retention screen's four controls, through the store functions the routes
    call and as the role the routes run as. A release by one person and its withdrawal by another,
    a hold placed by one and lifted by another: four entries, in that order, each naming the actor
    its own column names and nothing inferred, each subject and details what the recorder writes,
    and the chain verifying. Delete this and any of them can be missing or misattributed in
    production while the tests above, which read text, stay green. **Skips without a server.**"""
    hold = LegalHold(
        id="h_dispute", reason_code="litigation", subjects=frozenset({"u_one"}), placed_at=AT
    )
    with through_0054("brain_retention_audit") as url:
        report = a_report(url)
        made = as_application(
            url,
            lambda session: release_sweep(session, after_report=report, by="u_releaser", at=AT),
        )
        after_release = seen(url)
        as_application(
            url,
            lambda session: withdraw_release(
                session, by="u_withdrawer", at=AT + timedelta(hours=1)
            ),
        )
        after_withdrawal = seen(url)
        as_application(url, lambda session: place_hold(session, hold, by="u_placer"))
        after_placing = seen(url)
        as_application(
            url,
            lambda session: lift_hold(
                session, "h_dispute", by="u_lifter", at=AT + timedelta(hours=2)
            ),
        )
        chain = entries(url)

    expected = [
        (
            "retention",
            "u_releaser",
            recorder().retention(release_id=str(made), change=RetentionChange.RELEASED),
        ),
        (
            "retention",
            "u_withdrawer",
            recorder().retention(release_id=str(made), change=RetentionChange.WITHDRAWN),
        ),
        (
            "legal_hold",
            "u_placer",
            recorder().legal_hold(hold_id="h_dispute", change=LegalHoldChange.PLACED),
        ),
        (
            "legal_hold",
            "u_lifter",
            recorder().legal_hold(hold_id="h_dispute", change=LegalHoldChange.LIFTED),
        ),
    ]
    wanted = [
        (action, actor, entry.subject, dict(entry.details)) for action, actor, entry in expected
    ]
    assert (len(after_release), len(after_withdrawal), len(after_placing)) == (1, 2, 3)
    assert [(one.action.value, one.actor_id, one.subject, dict(one.details)) for one in chain] == (
        wanted
    )
    assert AuditChain(chain).verify() is None


def test_an_update_that_neither_withdraws_nor_lifts_appends_nothing() -> None:
    """The triggers fire on every update and record only the one that marks a row finished. A
    second withdrawal and a second lift, which the store's own guards turn into no row, and an
    operator's edits of other columns, leave the ledger as it was. Delete this and a trigger that
    recorded every update would put a withdrawal in the ledger each time somebody corrected a
    column, and an auditor would read the sweep as withdrawn twice. **Skips without a server.**"""
    hold = LegalHold(
        id="h_dispute", reason_code="litigation", subjects=frozenset({"u_one"}), placed_at=AT
    )
    with through_0054("brain_retention_audit_quiet") as url:
        report = a_report(url)
        as_application(
            url, lambda session: release_sweep(session, after_report=report, by="u_admin", at=AT)
        )
        as_application(
            url, lambda session: withdraw_release(session, by="u_admin", at=AT + timedelta(hours=1))
        )
        as_application(url, lambda session: place_hold(session, hold, by="u_admin"))
        as_application(
            url,
            lambda session: lift_hold(
                session, "h_dispute", by="u_admin", at=AT + timedelta(hours=2)
            ),
        )
        before = seen(url)

        again_withdrawn = as_application(
            url, lambda session: withdraw_release(session, by="u_other", at=AT + timedelta(days=1))
        )
        again_lifted = as_application(
            url,
            lambda session: lift_hold(
                session, "h_dispute", by="u_other", at=AT + timedelta(days=1)
            ),
        )
        sql(url, "UPDATE ops.retention_release SET released_by = 'u_corrected'")
        sql(url, "UPDATE obs.legal_hold SET reason_code = 'regulatory'")
        after = seen(url)

    assert len(before) == 4
    assert (again_withdrawn, again_lifted) == (False, False)
    assert after == before


def test_a_row_written_already_finished_records_both_of_its_changes_in_order() -> None:
    """Only an operator's statement can write one, since the application's policies refuse it.
    Delete this and a release inserted already withdrawn can be recorded as a release alone, so
    the ledger says the sweep was free to delete when the table says it never was, or a hold
    inserted already lifted reads as a hold still in force. **Skips without a server.**"""
    with through_0054("brain_retention_audit_finished") as url:
        report = a_report(url)
        [(made,)] = sql(
            url,
            "INSERT INTO ops.retention_release (after_report, released_at, released_by, "
            "withdrawn_at, withdrawn_by) VALUES (%s, %s, 'u_releaser', %s, 'u_withdrawer') "
            "RETURNING id",
            report,
            AT,
            AT + timedelta(hours=1),
        )
        sql(
            url,
            "INSERT INTO obs.legal_hold (id, reason_code, subjects, actors, all_subjects, "
            "placed_at, placed_by, released_at, released_by) VALUES ('h_old', 'litigation', "
            "'{}', '{}', true, %s, 'u_placer', %s, 'u_lifter')",
            AT,
            AT + timedelta(hours=1),
        )
        chain = entries(url)

    assert [(one.action.value, one.actor_id, one.subject, dict(one.details)) for one in chain] == [
        ("retention", "u_releaser", f"retention:{made}", {"change": "released"}),
        ("retention", "u_withdrawer", f"retention:{made}", {"change": "withdrawn"}),
        ("legal_hold", "u_placer", "legal_hold:h_old", {"change": "placed"}),
        ("legal_hold", "u_lifter", "legal_hold:h_old", {"change": "lifted"}),
    ]
    assert AuditChain(chain).verify() is None
