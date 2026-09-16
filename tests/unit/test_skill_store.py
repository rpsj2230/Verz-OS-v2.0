"""The skill library's tables and store: what `0056` builds, what its triggers record, and what the
store sends.

The first half needs no database. The migration is rendered offline and compared with the models,
the trigger functions are read and held to `AuditRecorder`'s own entries, a stored row is read back
through `library_skill_of`, and the store's statements and their order are checked against a
session that notes each one. The second half runs against a scratch PostgreSQL and **skips without
a server**, which is every run on the machine this was written on.

Task ids: M42.6.4
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
import psycopg.types.json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable

from brain.audit.ledger import DIGEST, IDENTIFIER, AuditAction, AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, SkillChange
from brain.console.skill_library import (
    ASSIGN_REASON,
    REPLACE_REASON,
    SKILL_AUTHORITY,
    SKILLS_PATH,
    LibrarySkill,
    added,
    assignment,
    decided,
    ledger_reference,
    read_package,
)
from brain.console.workspace import Part
from brain.db import metadata
from brain.ops.skill_store import (
    StoredSkills,
    adding,
    assignment_values,
    deciding,
    install_hash_locked,
    install_values,
    library_skill_of,
    review_values,
    skill_values,
)
from brain.session import make_session_factory
from brain.tables import skill as table_module
from brain.tables.skill import SkillReviewRow, SkillRow
from brain.tools.skills import SKILL_NAME_RE, Skill, SkillSource, SkillState
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine, as_app
from tests.unit.test_skill_library import (
    AGENT,
    IMPORTER,
    REVIEWER,
    SKILL_MD,
    a_recorder,
    an_install,
    reach,
    text_with,
)
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MIGRATION = VERSIONS / "0056_skill_library.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

TABLES = ("agent.skill", "agent.skill_review", "agent.skill_assignment")


def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def a_skill(text: str = SKILL_MD) -> LibrarySkill:
    return added(read_package("SKILL.md", text.encode("utf-8")), by=IMPORTER, at=NOW)


def approved(text: str = SKILL_MD) -> LibrarySkill:
    return decided(a_skill(text), reviewer=REVIEWER, approve=True, at=NOW)


def rows_for(one: LibrarySkill) -> tuple[SkillRow, SkillReviewRow | None]:
    """The two rows the store writes for this skill, built from the store's own values."""
    skill_row = SkillRow(**skill_values(one), created_at=one.submitted_at)
    if one.imported.state is SkillState.IMPORTED:
        return skill_row, None
    return skill_row, SkillReviewRow(**review_values(one), created_at=one.imported.reviewed_at)


def longest(model: Any, field: str) -> int:
    """The `max_length` a pydantic field declares."""
    return int(
        next(
            one.max_length
            for one in model.model_fields[field].metadata
            if hasattr(one, "max_length")
        )
    )


# ------------------------------------------------------------------------- the migration
def test_the_migration_and_the_model_hold_the_grammars_and_figures_they_copied() -> None:
    """`0056` and `brain.tables.skill` copy grammars, widths and ledger words for the reason `0009`
    gives. Delete this and one side can change alone: a skill name the parser admits and the table
    refuses after the person pressed Add, or a trigger recording a part or a reason code the
    recorder no longer spells that way."""
    migration = migration_module(MIGRATION)

    assert migration.IDENTIFIER == IDENTIFIER
    assert migration.DIGEST == DIGEST
    assert migration.SKILL_NAME_PATTERN == SKILL_NAME_RE.pattern == table_module.SKILL_NAME_PATTERN
    assert migration.VERSION_PATTERN == table_module.VERSION_PATTERN
    assert migration.PART == Part.SKILLS.value == SKILLS_PATH
    assert (migration.ASSIGN_REASON, migration.REPLACE_REASON) == (ASSIGN_REASON, REPLACE_REASON)
    assert migration.TABLES == TABLES
    assert longest(Skill, "name") == table_module.NAME_CHARS
    assert longest(Skill, "description") == table_module.DESCRIPTION_CHARS
    assert longest(SkillSource, "location") == table_module.LOCATION_CHARS
    assert (
        SkillState.APPROVED.value,
        SkillState.REJECTED.value,
    ) == (table_module.APPROVED, table_module.REJECTED)


@pytest.mark.parametrize("qualified", TABLES)
def test_the_migration_builds_each_table_exactly_as_the_model_declares_it(qualified: str) -> None:
    """Compared as rendered DDL, for the reason `test_tables` compares 0002's. Delete this and the
    model can gain a column or lose a key with the database built the old way."""
    expected = squash(str(CreateTable(metadata.tables[qualified]).compile(dialect=DIALECT)))

    assert expected in squash(rendered("upgrade", MIGRATION))


def test_nobody_decides_their_own_import_and_only_an_approved_skill_is_assigned_in_the_tables() -> (
    None
):
    """The two rules the domain enforces are in the tables' own definitions: a decision refuses a
    decider who is the importer, whose copy is held to the skill row by a composite key, and an
    assignment names the decision `approved` through a key.

    Delete this and either constraint can be dropped from the model and the migration together,
    every rendered comparison above still passes, and a hand-written statement approves its own
    import or assigns a rejected skill."""
    review = squash(
        str(CreateTable(metadata.tables["agent.skill_review"]).compile(dialect=DIALECT))
    )
    assigned = squash(
        str(CreateTable(metadata.tables["agent.skill_assignment"]).compile(dialect=DIALECT))
    )

    assert "CHECK (decided_by <> submitted_by)" in review
    assert (
        "FOREIGN KEY(digest, submitted_by) REFERENCES agent.skill (digest, submitted_by)" in review
    )
    assert "CHECK (approval = 'approved')" in assigned
    assert (
        "FOREIGN KEY(digest, approval) REFERENCES agent.skill_review (digest, decision)" in assigned
    )
    assert "FOREIGN KEY(digest, skill_name) REFERENCES agent.skill (digest, name)" in assigned


def test_the_application_reads_and_writes_in_its_own_name_and_never_edits_or_removes() -> None:
    """Row-level security on all three, SELECT and INSERT only, each insert policy in the session's
    own name, a trigger after every insert, and the ledger's two lists widened.

    Delete this and an UPDATE grant, a policy admitting a decision in somebody else's name or a
    table with no trigger can ship with every other test here green."""
    emitted = squash(rendered("upgrade", MIGRATION))
    principal = "current_setting('app.principal_id', true)"

    for qualified, column in (
        ("agent.skill", "submitted_by"),
        ("agent.skill_review", "decided_by"),
        ("agent.skill_assignment", "assigned_by"),
    ):
        assert f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY" in emitted
        assert f"GRANT SELECT, INSERT ON {qualified} TO brain_app" in emitted
        assert f"UPDATE ON {qualified}" not in emitted
        assert f"DELETE ON {qualified}" not in emitted
        assert f"FOR INSERT TO brain_app WITH CHECK ({column} = {principal})" in emitted
    assert (
        "CREATE TRIGGER skill_import_is_audited AFTER INSERT ON agent.skill "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_skill_import()"
    ) in emitted
    assert (
        "CREATE TRIGGER skill_review_is_audited AFTER INSERT ON agent.skill_review "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_skill_review()"
    ) in emitted
    assert (
        "CREATE TRIGGER skill_assignment_is_audited AFTER INSERT ON agent.skill_assignment "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_skill_assignment()"
    ) in emitted
    assert "'retention', 'revoke', 'session_end', 'sign_in', 'skill')" in emitted
    assert "|retention|session|skill):" in emitted
    down = squash(rendered("downgrade", MIGRATION))
    assert "DROP FUNCTION agent.record_skill_assignment()" in down
    assert down.index("DROP TABLE agent.skill_assignment") < down.index("DROP TABLE agent.skill;")


def test_the_import_and_decision_triggers_write_what_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps for an import or a decision and the entry
    `AuditRecorder.skill` writes for it can come apart without a server to notice."""
    migration = migration_module(MIGRATION)
    one = approved()
    recorder = AuditRecorder(
        AuditChain(), actor_id=REVIEWER, ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )
    entry = recorder.skill(name=one.name, digest=one.digest, change=SkillChange.APPROVED)
    imported = " ".join(migration.SKILL_IMPORT_TRIGGER_FUNCTION.split())
    reviewed = " ".join(migration.SKILL_REVIEW_TRIGGER_FUNCTION.split())

    assert entry.subject == f"skill:{one.name}"
    assert dict(entry.details) == {"change": "approved", "digest": one.digest}
    assert "v_subject text := 'skill:' || NEW.name;" in imported
    assert (
        "jsonb_build_object('change', 'imported', 'digest', NEW.digest);" in imported
        and SkillChange.IMPORTED.value == "imported"
    )
    assert "v_seq, v_at, NEW.submitted_by, 'skill', v_subject" in imported
    assert (
        "SELECT 'skill:' || s.name INTO v_subject FROM agent.skill s WHERE s.digest = NEW.digest;"
        in reviewed
    )
    assert "jsonb_build_object('change', NEW.decision, 'digest', NEW.digest);" in reviewed
    assert "v_seq, v_at, NEW.decided_by, 'skill', v_subject" in reviewed


def test_the_assignment_trigger_writes_what_the_recorder_writes_under_the_folded_name() -> None:
    """A replacement is a detachment then an attachment, each with the details
    `AuditRecorder.compose_change` writes for `ledger_reference`.

    Delete this and the trigger can record the raw name, which `AuditEntry` refuses on load, so the
    audit screen fails on the first assignment of a skill whose name has a hyphen in it."""
    migration = migration_module(MIGRATION)
    recorder = AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )
    entries = [
        recorder.compose_change(
            agent_id=AGENT,
            part=SKILLS_PATH,
            reference=ledger_reference("hosting-expiry"),
            attached=attached,
            reason_code=reason,
        )
        for attached, reason in ((False, REPLACE_REASON), (True, ASSIGN_REASON))
    ]
    body = " ".join(migration.SKILL_ASSIGNMENT_TRIGGER_FUNCTION.split())

    assert [dict(one.details) for one in entries] == [
        {
            "part": "skills",
            "reference": "hosting_expiry",
            "direction": "detached",
            "reason_code": REPLACE_REASON,
        },
        {
            "part": "skills",
            "reference": "hosting_expiry",
            "direction": "attached",
            "reason_code": ASSIGN_REASON,
        },
    ]
    assert "v_subject text := 'agent:' || NEW.agent_id;" in body
    assert (
        "IF NEW.replaces_digest IS NOT NULL THEN v_directions := v_directions || 'detached'::text; "
        "v_reasons := v_reasons || 'skill_replace'::text; END IF; "
        "v_directions := v_directions || 'attached'::text; "
        "v_reasons := v_reasons || 'skill_assign'::text;"
    ) in body
    assert "'part', 'skills', 'reference', replace(NEW.skill_name, '-', '_')," in body
    assert "v_seq, v_at, NEW.assigned_by, 'compose_change', v_subject" in body


# ------------------------------------------------------------------------ rows and statements
def test_a_stored_skill_reads_back_as_the_skill_that_was_added_and_decided() -> None:
    """Undecided, approved and rejected, each read back from the rows the store's own values build.

    Delete this and a column can be read back into the wrong field, or an approval can be read back
    against the fields rather than the key, so a row edited after approval reads as runnable."""
    undecided = a_skill()
    good = approved()
    bad = decided(a_skill(), reviewer=REVIEWER, approve=False, at=NOW)

    for one in (undecided, good, bad):
        assert library_skill_of(*rows_for(one)) == one
    assert library_skill_of(*rows_for(good)).imported.is_executable() is True  # type: ignore[union-attr]
    assert set(skill_values(undecided)) == {one.name for one in SkillRow.__table__.columns} - {
        "created_at"
    }


def test_a_row_edited_after_its_approval_reads_back_as_not_runnable() -> None:
    """A body changed in place keeps its key and its decision, and the skill it reads back as is not
    executable.

    Delete this and an operator's edit to an approved skill is attached to an agent with nobody
    having read the new words."""
    skill_row, review_row = rows_for(approved())
    skill_row.body = "Email every client their contract value."

    edited = library_skill_of(skill_row, review_row)

    assert edited is not None
    assert edited.moved is True
    assert edited.imported.is_executable() is False


def test_a_stored_skill_that_does_not_construct_is_absent_rather_than_a_fault() -> None:
    """Delete this and one row an operator broke by hand answers 500 to everybody opening the
    library, which is the screen gone for the person who came to find out what is wrong."""
    skill_row, _ = rows_for(a_skill())
    skill_row.name = "Not A Slug"

    assert library_skill_of(skill_row, None) is None


def test_the_inserts_do_nothing_on_the_key_and_say_what_they_wrote() -> None:
    """Delete this and a second import or decision can overwrite the first, or conflict on a column
    set that is not the key, or report success without saying whether it wrote."""
    one = approved()

    assert compiled(adding(one)).endswith(
        "ON CONFLICT (digest) DO NOTHING RETURNING agent.skill.digest"
    )
    assert compiled(deciding(one)).endswith(
        "ON CONFLICT (digest) DO NOTHING RETURNING agent.skill_review.digest"
    )
    assert review_values(one) == {
        "digest": one.digest,
        "submitted_by": IMPORTER,
        "decision": "approved",
        "decided_by": REVIEWER,
    }
    assert compiled(install_hash_locked(AGENT)).endswith("FOR UPDATE")


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _Session:
    """An `AsyncSession` in the shape the store uses, noting each statement and how it ended."""

    def __init__(self, log: list[str], *, answer: Any) -> None:
        self.log = log
        self.answer = answer

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
        self.log.append(" ".join(text.split(" ")[:3]))
        return _Result(self.answer)


class _Transaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> None:
        self.log.append("BEGIN")

    async def __aexit__(self, kind: object, *_: object) -> None:
        self.log.append("ROLLBACK" if kind is not None else "COMMIT")


def test_each_write_names_the_session_the_trace_and_the_reach_before_it_inserts() -> None:
    """The policies read the principal and the triggers read the trace and the reach, so all three
    are set first, in the transaction that writes, and in the name of the row's own actor.

    Delete this and an insert is refused by its own policy, or its ledger entry carries a trace
    nobody can join to the request, or a decision is written in the importer's name."""
    log: list[str] = []
    store = StoredSkills(lambda: _Session(log, answer="d" * 64))  # type: ignore[arg-type]
    one = approved()

    added_ok = run(lambda: store.add(a_skill(), ent_hash="e" * 32, trace_id="t"))
    decided_ok = run(lambda: store.decide(one, ent_hash="e" * 32, trace_id="t"))

    assert (added_ok, decided_ok) == (True, True)
    assert log == [
        "BEGIN",
        "set app.principal_id",
        "set brain.trace_id",
        "set brain.ent_hash",
        "INSERT INTO agent.skill",
        "COMMIT",
        "BEGIN",
        "set app.principal_id",
        "set brain.trace_id",
        "set brain.ent_hash",
        "INSERT INTO agent.skill_review",
        "COMMIT",
    ]


def test_an_assignment_writes_only_when_the_install_is_the_one_it_was_decided_about() -> None:
    """The hash is read under the lock first; a match records the assignment and writes the
    install, and a mismatch writes neither.

    Delete this and two administrators assigning at once overwrite each other's install, or an
    instruction edit made while somebody was choosing a skill is lost without a word."""
    one = approved()
    signed, instance, record = an_install()
    made = assignment(
        one,
        record=record,
        signed=signed,
        instance=instance,
        library=(one,),
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(AuditChain()),
        now=NOW,
    )
    matched: list[str] = []
    moved: list[str] = []

    wrote = run(
        lambda: StoredSkills(lambda: _Session(matched, answer="h" * 64)).assign(  # type: ignore[arg-type]
            made, expected_hash="h" * 64, ent_hash="e" * 32, trace_id="t"
        )
    )
    refused = run(
        lambda: StoredSkills(lambda: _Session(moved, answer="other")).assign(  # type: ignore[arg-type]
            made, expected_hash="h" * 64, ent_hash="e" * 32, trace_id="t"
        )
    )

    assert (wrote, refused) == (True, False)
    assert matched[4:] == [
        "SELECT agent.template_instance.effective_hash FROM",
        "INSERT INTO agent.skill_assignment",
        "UPDATE agent.template_instance SET",
        "COMMIT",
    ]
    assert moved[4:] == ["SELECT agent.template_instance.effective_hash FROM", "COMMIT"]
    assert assignment_values(made)["assigned_by"] == "u_admin"
    assert install_values(made)["overlay"][SKILLS_PATH] == [
        {"name": "hosting-expiry", "digest": one.digest}
    ]


# ------------------------------------------------------------------------ the database
@contextmanager
def through_0056(database: str) -> Iterator[str]:
    """A database with `0056` applied, built the way `test_agent_automation_store.through_0055`
    builds its own: `0049` and `0054` to `0056` run for real, `0050` to `0053` stamped."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            migrate(database, "stamp", "0053")
            migrate(database, "upgrade", "0056")
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


def test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store() -> None:
    """M42.6.4 through the store the application uses and as the role it uses: a skill added and
    read back, a decision by a second person read back as runnable, one `skill` entry for each with
    the recorder's subject and details, the chain verifying, and a second import of the same bytes
    writing nothing. **Skips without a server.**"""
    with through_0056("brain_skill_library") as url:
        one = a_skill()
        good = decided(one, reviewer=REVIEWER, approve=True, at=NOW)

        async def writes() -> tuple[bool, bool, bool, tuple[LibrarySkill, ...]]:
            engine = app_engine(url)
            try:
                store = StoredSkills(make_session_factory(engine))
                first = await store.add(one, ent_hash="a" * 32, trace_id="trace-add")
                again = await store.add(one, ent_hash="a" * 32, trace_id="trace-again")
                decision = await store.decide(good, ent_hash="b" * 32, trace_id="trace-decide")
                return first, again, decision, await store.library()
            finally:
                await engine.dispose()

        first, again, decision, library = run(writes)
        chain = entries(url)

    assert (first, again, decision) == (True, False, True)
    assert len(library) == 1
    assert library[0].imported.is_executable() is True
    assert library[0].imported.reviewer == REVIEWER
    skill_entries = [entry for entry in chain if entry.action is AuditAction.SKILL]
    assert [(entry.actor_id, entry.subject, dict(entry.details)) for entry in skill_entries] == [
        (IMPORTER, "skill:hosting-expiry", {"change": "imported", "digest": one.digest}),
        (REVIEWER, "skill:hosting-expiry", {"change": "approved", "digest": one.digest}),
    ]
    assert AuditChain(chain).verify() is None


def test_the_database_refuses_a_decision_by_the_importer_and_an_assignment_nobody_approved() -> (
    None
):
    """Measured as the application role, with the session naming the actor so the policy admits the
    row: the check refuses the importer as decider, the key refuses an assignment of undecided
    bytes, and an assignment of approved bytes is recorded under the folded name.

    Delete this and both rules are claims about a table definition nobody has run. **Skips without
    a server.**"""
    with through_0056("brain_skill_library_refusals") as url:
        one = a_skill(text_with(name="quote-format", description="Formats a quote for a client"))
        values = skill_values(one)
        columns = ", ".join(values)
        marks = ", ".join(["%s"] * len(values))
        with as_app(url, ("app.principal_id", IMPORTER)) as conn:
            conn.execute(
                f"INSERT INTO agent.skill ({columns}) VALUES ({marks})",  # noqa: S608
                tuple(
                    psycopg.types.json.Jsonb(v) if k == "tools" else v for k, v in values.items()
                ),
            )
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO agent.skill_review (digest, submitted_by, decision, decided_by)"
                    " VALUES (%s, %s, 'approved', %s)",
                    (one.digest, IMPORTER, IMPORTER),
                )
        with (
            as_app(url, ("app.principal_id", "u_admin")) as conn,
            pytest.raises(psycopg.errors.ForeignKeyViolation),
        ):
            conn.execute(
                "INSERT INTO agent.skill_assignment (agent_id, skill_name, digest, assigned_by)"
                " VALUES (%s, %s, %s, 'u_admin')",
                (AGENT, one.name, one.digest),
            )
        with as_app(url, ("app.principal_id", REVIEWER)) as conn:
            conn.execute(
                "INSERT INTO agent.skill_review (digest, submitted_by, decision, decided_by)"
                " VALUES (%s, %s, 'approved', %s)",
                (one.digest, IMPORTER, REVIEWER),
            )
        with as_app(url, ("app.principal_id", "u_admin")) as conn:
            conn.execute(
                "INSERT INTO agent.skill_assignment (agent_id, skill_name, digest, assigned_by)"
                " VALUES (%s, %s, %s, 'u_admin')",
                (AGENT, one.name, one.digest),
            )
        with (
            as_app(url, ("app.principal_id", "u_somebody_else")) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute(
                "INSERT INTO agent.skill_assignment (agent_id, skill_name, digest, assigned_by)"
                " VALUES (%s, %s, %s, 'u_admin')",
                (AGENT, one.name, one.digest),
            )
        chain = entries(url)

    composed = [entry for entry in chain if entry.action is AuditAction.COMPOSE_CHANGE]
    assert [(entry.subject, dict(entry.details)) for entry in composed] == [
        (
            f"agent:{AGENT}",
            {
                "part": "skills",
                "reference": "quote_format",
                "direction": "attached",
                "reason_code": ASSIGN_REASON,
            },
        )
    ]
    assert AuditChain(chain).verify() is None
