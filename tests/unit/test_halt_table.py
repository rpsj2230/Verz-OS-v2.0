"""`ops.halt` and `0136`: a stop and its resume are rows, each audited once, and nothing edits one.

The migration is held to the model on rendered DDL and to the domain's vocabularies, its audit
grammar is held to today's rather than the one it was drafted against, and on a database built
through the whole chain a row is written, audited, refused and survives a downgrade and an upgrade.
The database half skips where `DATABASE_URL` is unset, and CI always sets it.

Task ids: none
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.audit.ledger import SUBJECT_KINDS, AuditAction
from brain.audit.record import HaltAct
from brain.db import metadata
from brain.identity.principal_store import PRINCIPAL_SETTING
from brain.ops.halt import MINIMUM_REASON, HaltScope
from brain.tables import halt as tables
from brain.tables.audit import SUBJECT_PATTERN
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import migrate, sql
from tests.unit.test_audit_view import a_recorder
from tests.unit.test_review_store import entries
from tests.unit.test_tables import DIALECT, VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0136_ops_halt.py"

#: A reason long enough to be one, for the rows whose reason is not what is under test.
REASON = "a connector is writing to the wrong ledger"


def module() -> Any:
    return migration_module(MIGRATION)


# ------------------------------------------------------------------------ the migration's copy
def test_the_migration_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """The copy compared on rendered DDL. Delete this and the model can declare the scope list or
    the reason's floor while the database enforces a different one."""
    emitted = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables["ops.halt"]
    assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_vocabularies_the_migration_copies_are_the_ones_the_code_holds() -> None:
    """Each copied constant against the enum or the figure it copies, and each width against what
    has to fit in it. Delete this and a sixth halt scope is refused by the database after passing
    every test that only exercised Python."""
    m = module()
    assert one_of("act", HaltAct) == m.ACTS
    assert one_of("scope", HaltScope) == m.SCOPES
    assert m.MINIMUM_REASON == MINIMUM_REASON
    assert (m.ACT_CHARS, m.SCOPE_CHARS, m.TARGET_CHARS, m.ROLE_CHARS) == (
        tables.ACT_CHARS,
        tables.SCOPE_CHARS,
        tables.TARGET_CHARS,
        tables.ROLE_CHARS,
    )
    assert m.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert max(len(one.value) for one in HaltAct) <= m.ACT_CHARS
    assert max(len(one.value) for one in HaltScope) <= m.SCOPE_CHARS


def test_the_audit_grammar_is_widened_over_todays_by_halt_alone() -> None:
    """**The defect this migration was landed with a fix for.** It was drafted over `0083` and
    copied that day's action list, so applying it would have dropped the four actions and the
    subject kind added since, and the next `vault_access` entry would have been refused. The
    narrower lists are the ones the newest earlier migrations wrote, and the widened ones are the
    model's. Delete this and a draft carried forward can narrow the ledger silently."""
    m = module()
    assert one_of("action", AuditAction) == m.WIDENED_ACTIONS
    assert f"subject ~ '{SUBJECT_PATTERN}'" == m.WIDENED_SUBJECTS
    assert (
        m.NARROWER_ACTIONS
        == migration_module(VERSIONS / "0105_agent_owner_audit.py").WIDENED_ACTIONS
    )
    older_subjects = migration_module(VERSIONS / "0104_compliance_record_and_decision_entries.py")
    assert m.NARROWER_SUBJECTS == older_subjects.WIDENED_SUBJECTS
    assert "'halt'" in m.WIDENED_ACTIONS and "'halt'" not in m.NARROWER_ACTIONS
    assert "halt" in SUBJECT_KINDS
    assert m.SUPERSEDES == {
        m.NARROWER_ACTIONS: m.WIDENED_ACTIONS,
        m.NARROWER_SUBJECTS: m.WIDENED_SUBJECTS,
    }


def test_the_application_may_read_and_add_a_row_and_never_change_one() -> None:
    """Insert-only is the absence of two grants. Delete this and an UPDATE grant can arrive with a
    store that "just marks the halt lifted", overwriting who stopped the system."""
    m = module()
    assert m.GRANTS == ("GRANT SELECT, INSERT ON ops.halt TO brain_app",)
    upgrade = squash(rendered("upgrade", MIGRATION))
    assert "ALTER TABLE ops.halt ENABLE ROW LEVEL SECURITY" in upgrade
    assert "CREATE TRIGGER halt_is_audited AFTER INSERT ON ops.halt" in upgrade


# ------------------------------------------------------------------------------ the database
@pytest.fixture
def database() -> Iterator[tuple[str, str]]:
    name = f"brain_halt_{uuid.uuid4().hex[:8]}"
    with retirable(name) as url:
        if not sql(url, "SELECT to_regclass('ops.halt')")[0][0]:
            pytest.skip("0136 is built only on the chain CI runs, where every table is")
        yield name, url


def write(
    url: str,
    *,
    as_: str,
    actor: str,
    scope: str = "everything",
    target: str = "",
    reason: str = REASON,
    act: str = "halt",
) -> str:
    """One row written as the application role, with the session's principal set to `as_`."""
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT set_config(%s, %s, false)", (PRINCIPAL_SETTING, as_))
        row = conn.execute(
            "INSERT INTO ops.halt (act, scope, target, actor_id, actor_role, reason)"
            " VALUES (%s, %s, %s, %s, 'administrator', %s) RETURNING id",
            (act, scope, target, actor, reason),
        ).fetchone()
    assert row is not None
    return str(row[0])


def test_a_halt_and_its_resume_are_two_rows_and_two_ledger_entries(
    database: tuple[str, str],
) -> None:
    """The positive case. Each act is one entry under its own subject, naming the act and the scope
    and never the target or the reason, with exactly the details the recorder writes. Delete this
    and the trigger can record nothing, or record the reason an administrator typed."""
    _, url = database
    stopped = write(url, as_="u_admin", actor="u_admin", scope="person", target="u_compromised")
    resumed = write(
        url,
        as_="u_other",
        actor="u_other",
        scope="person",
        target="u_compromised",
        act="resume",
        reason="the account was reset and the token revoked",
    )

    found = entries(url, "halt")
    assert [one.subject for one in found] == [f"halt:{stopped}", f"halt:{resumed}"]
    assert [one.actor_id for one in found] == ["u_admin", "u_other"]
    recorder, _ = a_recorder()
    assert (
        found[0].details
        == recorder.halt(halt_id=stopped, act=HaltAct.HALT, scope=HaltScope.PERSON).details
    )
    assert found[1].details == {"act": "resume", "scope": "person"}
    assert all("u_compromised" not in str(one.details) for one in found)
    assert sql(url, "SELECT count(*) FROM ops.halt") == [(2,)]


def test_a_row_naming_somebody_other_than_the_session_is_refused(
    database: tuple[str, str],
) -> None:
    """The actor is the session's principal. Delete this and a row can say somebody else stopped
    the system, and the resume would name the wrong person as overridden."""
    _, url = database
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        write(url, as_="u_admin", actor="u_somebody_else")
    assert entries(url, "halt") == []


def test_the_application_can_neither_edit_nor_delete_a_halt(database: tuple[str, str]) -> None:
    """Delete this and a halt row can be rewritten to say it never happened."""
    _, url = database
    stopped = write(url, as_="u_admin", actor="u_admin")
    for statement in (
        "UPDATE ops.halt SET reason = 'nothing happened here at all' WHERE id = %s",
        "DELETE FROM ops.halt WHERE id = %s",
    ):
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET ROLE brain_app")
            conn.execute("SELECT set_config(%s, %s, false)", (PRINCIPAL_SETTING, "u_admin"))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement, (stopped,))
    assert sql(url, "SELECT reason FROM ops.halt") == [(REASON,)]


@pytest.mark.parametrize(
    ("scope", "target", "reason"),
    [
        ("everything", "", "too short"),
        ("person", "", REASON),
        ("everything", "u_admin", REASON),
        ("forever", "", REASON),
    ],
)
def test_a_halt_that_would_not_work_is_refused_by_the_database(
    database: tuple[str, str], scope: str, target: str, reason: str
) -> None:
    """The domain's refusals, held where an operator's statement cannot step round them: a reason
    that says nothing, a targeted halt naming nothing, a halt on everything naming something, and
    a scope nothing reads. Delete this and a row `Halt` would refuse to build can be written and
    then fail to load after the restart it was meant to survive."""
    _, url = database
    with pytest.raises(psycopg.errors.CheckViolation):
        write(url, as_="u_admin", actor="u_admin", scope=scope, target=target, reason=reason)


def test_a_downgrade_keeps_the_entries_and_an_upgrade_builds_the_table_again(
    database: tuple[str, str],
) -> None:
    """A deploy with no way home is the failure a downgrade exists for. Delete this and the
    downgrade can fail on its own `NOT VALID` constraint, or drop the ledger's record of a stop."""
    name, url = database
    write(url, as_="u_admin", actor="u_admin")
    migrate(name, "downgrade", str(module().down_revision))
    assert sql(url, "SELECT to_regclass('ops.halt')") == [(None,)]
    assert len(entries(url, "halt")) == 1
    migrate(name, "upgrade", "head")
    assert sql(url, "SELECT count(*) FROM ops.halt") == [(0,)]
    write(url, as_="u_admin", actor="u_admin")
    assert len(entries(url, "halt")) == 2
