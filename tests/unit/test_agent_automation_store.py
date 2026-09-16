"""An installed automation reaches the system: the table, its policies, the trigger and the store.

`tests/unit/test_automation_gallery.py` holds what an install is and `tests/unit/
test_automation_gallery_routes.py` the order a request is answered in. This file holds everything
below them. The first half needs no server: it reads `0055` as the SQL it renders, holds its
copied grammars and the trigger's details to the live ones, reads the registry entry back out of
the row an install writes, and drives the store over a stub session.

The second half builds a database through `0055` and proves an install reaches the system in the
three places `docs/admin-console.md` names: the row, which is the automation and its registry entry;
the one `compose_change` entry the trigger appends, on a chain that still verifies; and the
behaviour, which is a second install writing nothing and appending nothing, and the application
role refused a row in somebody else's name and an edit of its own. **It skips when there is no
server**, and CI always has one.

Task ids: M39.6.1.3
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
import psycopg.sql
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable

from brain.agents.model import (
    CEILING_PRINCIPAL_PREFIX,
    AgentAudience,
    AgentAuthority,
    AgentRecord,
)
from brain.audit.ledger import IDENTIFIER, AuditChain, AuditEntry
from brain.audit.record import AuditRecorder
from brain.console import agent_automations
from brain.console.automation_gallery import (
    AUTOMATION_AUTHORITY,
    AUTOMATION_PART,
    BUILT_IN,
    INSTALL_REASON,
    TEMPLATE_ID,
    Installation,
    install,
    new_automation_id,
    preview,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.db import metadata
from brain.knowledge.visibility import Visibility
from brain.ops.agent_automation_store import (
    ONE_INSTALL,
    Installed,
    StoredAgentAutomations,
    already_installed,
    entry_of,
    installed_from,
    installing,
    row_values,
)
from brain.ops.automation_owner import AUTOMATION_ID
from brain.session import make_session_factory
from brain.tables import agent_automation as table_module
from brain.tables.agent_automation import AgentAutomationRow
from brain.tables.identity import PRINCIPAL_ID_CHARS
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine, as_app
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MIGRATION = VERSIONS / "0055_agent_automation.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

AGENT = "quote_helper"
INSTALLER = "u_installer"
TEMPLATE = BUILT_IN[0]


def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def an_installation(principal_id: str = INSTALLER, automation_id: str = "auto_one") -> Installation:
    installer = Principal(
        id=principal_id,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=f"Person {principal_id}",
    )
    agent = AgentRecord(
        agent_id=AGENT,
        display_name="Quote helper",
        persona="Answers pricing questions.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(capabilities=(Capability(value="read:client.name"),)),
        created_by="u_builder",
    )
    shown = preview(
        TEMPLATE,
        agent,
        installer=installer,
        installer_reach=EntitlementSet(
            principal_id=principal_id,
            grants=(Grant(capability=AUTOMATION_AUTHORITY, scope=Scope.unrestricted()),),
        ),
    )
    return install(shown, confirmation=shown.confirmation, automation_id=automation_id)


# ------------------------------------------------------------------- the migration


def test_the_migration_and_the_model_hold_the_live_grammars_and_widths_they_copied() -> None:
    """`0055` and `brain.tables.agent_automation` copy grammars and figures for the reason `0009`
    gives. Delete this and one side can change alone: an automation id the gallery mints and the
    table refuses, a name the console admits and the constraint refuses after the person
    confirmed, or a ceiling prefix that no longer stops an automation running as its agent."""
    migration = migration_module(MIGRATION)

    assert migration.AUTOMATION_ID_PATTERN == AUTOMATION_ID
    assert migration.IDENTIFIER_PATTERN == IDENTIFIER
    assert migration.TEMPLATE_ID_PATTERN == TEMPLATE_ID == table_module.TEMPLATE_ID_PATTERN
    assert migration.MINIMUM_OUTCOME_NAME == agent_automations.MINIMUM_OUTCOME_NAME
    assert table_module.MINIMUM_OUTCOME_NAME == agent_automations.MINIMUM_OUTCOME_NAME
    assert migration.MINIMUM_GUARDS == agent_automations.MINIMUM_GUARDS
    assert table_module.MINIMUM_GUARDS == agent_automations.MINIMUM_GUARDS
    assert table_module.FIRST_PERSON_OPENER == agent_automations.FIRST_PERSON_OPENER
    assert table_module.CEILING_PRINCIPAL_PREFIX == CEILING_PRINCIPAL_PREFIX
    assert IDENTIFIER.endswith(f"{{1,{PRINCIPAL_ID_CHARS}}}$")
    assert max(len(one.name) for one in BUILT_IN) <= table_module.NAME_CHARS
    assert max(len(one.task) for one in BUILT_IN) <= table_module.TASK_CHARS
    assert len(new_automation_id()) <= table_module.AUTOMATION_ID_CHARS


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """Compared as rendered DDL, for the reason `test_tables` compares 0002's. Delete this and the
    model can gain a column or lose the unique constraint with the database built the old way."""
    expected = squash(
        str(CreateTable(metadata.tables["agent.automation"]).compile(dialect=DIALECT))
    )

    assert expected in squash(rendered("upgrade", MIGRATION))


def test_the_application_reads_and_installs_in_its_own_name_and_never_edits_or_removes() -> None:
    """Row-level security on, SELECT and INSERT only, both policies in the session's own name, and
    the trigger after every insert. Delete this and an UPDATE grant, a policy admitting an install
    in somebody else's name or a table with no trigger can ship with every other test here green."""
    emitted = squash(rendered("upgrade", MIGRATION))
    principal = "current_setting('app.principal_id', true)"

    assert "ALTER TABLE agent.automation ENABLE ROW LEVEL SECURITY" in emitted
    assert "GRANT SELECT, INSERT ON agent.automation TO brain_app" in emitted
    assert "UPDATE ON agent.automation" not in emitted
    assert "DELETE ON agent.automation" not in emitted
    assert (
        "CREATE POLICY automation_readable_by_its_principal ON agent.automation FOR SELECT TO "
        f"brain_app USING (runs_as_id = {principal})"
    ) in emitted
    assert (
        "CREATE POLICY automation_installed_in_the_sessions_name ON agent.automation FOR INSERT TO "
        f"brain_app WITH CHECK (runs_as_id = {principal} AND installed_by = {principal})"
    ) in emitted
    assert (
        "CREATE TRIGGER automation_install_is_audited AFTER INSERT ON agent.automation "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_automation_install()"
    ) in emitted
    assert "DROP FUNCTION agent.record_automation_install()" in squash(
        rendered("downgrade", MIGRATION)
    )


def test_the_trigger_writes_the_subject_actor_and_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps and the entry `AuditRecorder.
    compose_change` writes for the same install can come apart without a server to notice."""
    migration = migration_module(MIGRATION)
    entry = AuditRecorder(
        AuditChain(), actor_id=INSTALLER, ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    ).compose_change(
        agent_id=AGENT,
        part=AUTOMATION_PART,
        reference="auto_one",
        attached=True,
        reason_code=INSTALL_REASON,
    )
    body = " ".join(migration.AUTOMATION_INSTALL_TRIGGER_FUNCTION.split())

    assert (migration.PART, migration.REASON_CODE) == (AUTOMATION_PART, INSTALL_REASON)
    assert entry.subject == f"agent:{AGENT}"
    assert dict(entry.details) == {
        "part": AUTOMATION_PART,
        "reference": "auto_one",
        "direction": "attached",
        "reason_code": INSTALL_REASON,
    }
    assert "v_subject text := 'agent:' || NEW.agent_id;" in body
    assert (
        f"jsonb_build_object( 'part', '{AUTOMATION_PART}', 'reference', NEW.automation_id, "
        f"'direction', 'attached', 'reason_code', '{INSTALL_REASON}' );"
    ) in body
    assert "v_seq, v_at, NEW.installed_by, 'compose_change', v_subject" in body


# ------------------------------------------------------------------- the row and the store


def test_the_registry_entry_read_back_out_of_the_row_is_the_entry_the_install_carried() -> None:
    """The one-row argument, checked. Delete this and a column can be dropped from the row or
    read back into the wrong field, so the registry reviewers read is not the one installed."""
    made = an_installation()
    values = row_values(made)

    assert entry_of(values) == made.entry
    assert set(values) == {one.name for one in AgentAutomationRow.__table__.columns} - {
        "created_at",
        "updated_at",
    }


def test_the_insert_does_nothing_on_the_constraints_columns_and_says_what_it_wrote() -> None:
    """Delete this and a second install can overwrite the first, conflict on a different column
    set from the constraint, or report success without saying which automation it wrote."""
    made = an_installation()

    assert ONE_INSTALL == ("agent_id", "template_id", "runs_as_id")
    assert compiled(installing(made)).endswith(
        "ON CONFLICT (agent_id, template_id, runs_as_id) DO NOTHING "
        "RETURNING agent.automation.automation_id"
    )
    assert "WHERE agent.automation.agent_id = " in compiled(already_installed(made))
    assert "AND agent.automation.template_id = " in compiled(already_installed(made))
    assert "AND agent.automation.runs_as_id = " in compiled(already_installed(made))
    assert compiled(installed_from(AGENT, INSTALLER)).endswith(
        "WHERE agent.automation.agent_id = %(agent_id_1)s::VARCHAR"
        " AND agent.automation.runs_as_id = %(runs_as_id_1)s::VARCHAR"
    )


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def scalar_one(self) -> Any:
        assert self.value is not None
        return self.value


class _Session:
    """An `AsyncSession` in the shape the store uses, noting each statement and how it ended."""

    def __init__(self, log: list[str], *, conflict: bool) -> None:
        self.log = log
        self.conflict = conflict

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction(self.log)

    async def execute(self, statement: Any, *_: Any, **__: Any) -> _Result:
        text = compiled(statement)
        if "set_config" in text:
            self.log.append(f"set {statement.compile().params['name']}")
            return _Result(None)
        self.log.append(text.split(" ")[0])
        if text.startswith("INSERT"):
            return _Result(None if self.conflict else "auto_one")
        return _Result("auto_first")


class _Transaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> None:
        self.log.append("BEGIN")

    async def __aexit__(self, kind: object, *_: object) -> None:
        self.log.append("ROLLBACK" if kind is not None else "COMMIT")


def test_the_store_names_the_session_the_trace_and_the_reach_then_inserts_once() -> None:
    """The policies read the principal and the trigger reads the trace and the reach, so all three
    are set before the insert in the same transaction. Delete this and the insert is refused by its
    own policy, or its ledger entry carries a trace nobody can join to the request."""
    log: list[str] = []
    store = StoredAgentAutomations(lambda: _Session(log, conflict=False))  # type: ignore[arg-type]

    done = run(lambda: store.install(an_installation(), ent_hash="e" * 32, trace_id="t"))

    assert done == Installed(automation_id="auto_one", created=True)
    assert log == [
        "BEGIN",
        "set app.principal_id",
        "set brain.trace_id",
        "set brain.ent_hash",
        "INSERT",
        "COMMIT",
    ]


def test_a_second_install_reads_the_first_in_the_same_transaction_and_says_it_wrote_nothing() -> (
    None
):
    """Delete this and a conflict is reported as a success with no id, or the existing automation
    is read in a second transaction a concurrent install can change underneath."""
    log: list[str] = []
    store = StoredAgentAutomations(lambda: _Session(log, conflict=True))  # type: ignore[arg-type]

    done = run(lambda: store.install(an_installation(), ent_hash="e" * 32, trace_id="t"))

    assert done == Installed(automation_id="auto_first", created=False)
    assert log[-3:] == ["INSERT", "SELECT", "COMMIT"]


# ------------------------------------------------------------------------ the database


@contextmanager
def through_0055(database: str) -> Iterator[str]:
    """A database with `0055` applied. Without pgvector, `retirable` stops at `0048`, which built
    the ledger and its append function. `0049` and `0054` are run for real, as
    `tests/unit/test_credential_writes.py` runs them, because `0054` is the migration that leaves
    the ledger's action list in the database holding `compose_change`; `0050` to `0053` are
    stamped, and `0055` is run for real."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            migrate(database, "stamp", "0053")
            migrate(database, "upgrade", "0055")
        yield url


def entries(url: str) -> list[AuditEntry]:
    rows = sql(
        url,
        "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
        " entry_hash FROM obs.audit_entry ORDER BY seq",
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


def test_an_install_writes_one_row_one_ledger_entry_and_a_second_install_writes_neither() -> None:
    """M39.6.1.3's install, through the store the application uses and as the role it uses.

    One row that reads back as the installation's registry entry; exactly one `compose_change`
    entry about the agent, whose actor and details are `AuditRecorder.compose_change`'s and whose
    reach and trace are the ones the store set; the chain verifying from genesis; a second install
    of the same template by the same person answered with the first id and appending nothing; the
    same template installed by a second person written as their own. Delete this and every one of
    those can be false in production while the stubbed tests above stay green. **Skips without a
    server.**"""
    with through_0055("brain_agent_automation") as url:
        first = an_installation()
        again = an_installation(automation_id=new_automation_id())
        other = an_installation("u_other", automation_id="auto_other")

        async def installs() -> tuple[Installed, Installed, Installed, dict[str, str]]:
            engine = app_engine(url)
            try:
                store = StoredAgentAutomations(make_session_factory(engine))
                done = await store.install(first, ent_hash="a" * 32, trace_id="trace-install")
                twice = await store.install(again, ent_hash="a" * 32, trace_id="trace-again")
                theirs = await store.install(other, ent_hash="b" * 32, trace_id="trace-other")
                mine = dict(await store.installed_by(AGENT, INSTALLER))
                return done, twice, theirs, mine
            finally:
                await engine.dispose()

        done, twice, theirs, mine = run(installs)
        rows = sql(
            url,
            "SELECT automation_id, agent_id, task, runs_as_id, next_run_at, guards"
            " FROM agent.automation ORDER BY automation_id",
        )
        chain = entries(url)

    names = ("automation_id", "agent_id", "task", "runs_as_id", "next_run_at", "guards")
    stored = [entry_of(dict(zip(names, row, strict=True))) for row in rows]
    composed = [one for one in chain if one.action.value == "compose_change"]
    expected = AuditRecorder(
        AuditChain(), actor_id=INSTALLER, ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    ).compose_change(
        agent_id=AGENT,
        part=AUTOMATION_PART,
        reference="auto_one",
        attached=True,
        reason_code=INSTALL_REASON,
    )

    assert done == Installed(automation_id="auto_one", created=True)
    assert twice == Installed(automation_id="auto_one", created=False)
    assert theirs == Installed(automation_id="auto_other", created=True)
    assert stored == [first.entry, other.entry]
    assert mine == {TEMPLATE.template_id: "auto_one"}
    assert len(composed) == 2
    mine_entry = next(one for one in composed if one.actor_id == INSTALLER)
    assert (mine_entry.subject, dict(mine_entry.details)) == (
        expected.subject,
        dict(expected.details),
    )
    assert (mine_entry.ent_hash, mine_entry.trace_id) == ("a" * 32, "trace-install")
    assert AuditChain(chain).verify() is None


def test_the_application_role_can_neither_install_in_another_name_nor_read_or_edit_anothers() -> (
    None
):
    """The policies and the grants, measured as the application role. Delete this and a session
    naming one person can write an automation running as another, which is the widening the
    gallery's own rule refuses, or read which templates somebody else installed. The positive
    case is the install test above. **Skips without a server.**"""
    with through_0055("brain_agent_automation_rls") as url:
        made = an_installation()
        values = row_values(made)
        # Composed by psycopg from the model's own column names, with a placeholder for every
        # value, so nothing a test was handed reaches the statement's text.
        insert = psycopg.sql.SQL("INSERT INTO agent.automation ({}) VALUES ({})").format(
            psycopg.sql.SQL(", ").join(psycopg.sql.Identifier(one) for one in values),
            psycopg.sql.SQL(", ").join(psycopg.sql.Placeholder() for _ in values),
        )

        with (
            as_app(url, ("app.principal_id", "u_somebody_else")) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute(insert, tuple(values.values()))
        with as_app(url, ("app.principal_id", INSTALLER)) as conn:
            conn.execute(insert, tuple(values.values()))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("UPDATE agent.automation SET next_run_at = now()")
        with as_app(url, ("app.principal_id", "u_somebody_else")) as conn:
            seen = conn.execute("SELECT automation_id FROM agent.automation").fetchall()
        with as_app(url, ("app.principal_id", INSTALLER)) as conn:
            own = conn.execute("SELECT automation_id FROM agent.automation").fetchall()

    assert seen == []
    assert own == [("auto_one",)]
