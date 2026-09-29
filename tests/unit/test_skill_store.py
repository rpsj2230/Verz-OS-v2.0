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

import dataclasses
from collections.abc import Iterator, Mapping
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
    MAX_CATEGORIES,
    REPLACE_REASON,
    SKILL_AUTHORITY,
    SKILLS_PATH,
    LibrarySkill,
    Package,
    added,
    assignment,
    decided,
    edited,
    ledger_reference,
    read_package,
    read_url,
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
from brain.tools.skills import COMMIT_RE, SKILL_NAME_RE, Skill, SkillSource, SkillState, SourceKind
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
from tests.unit.test_tables import VERSIONS, as_amended, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MIGRATION = VERSIONS / "0056_skill_library.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

TABLES = ("agent.skill", "agent.skill_review", "agent.skill_assignment")


def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def a_skill(text: str = SKILL_MD) -> LibrarySkill:
    return added(read_package("SKILL.md", text.encode("utf-8")), by=IMPORTER, at=NOW)


def as_approved(one: LibrarySkill, reviewer: str = REVIEWER) -> LibrarySkill:
    """`one` with an approval on it as the tables hold one.

    Built past `decided`, whose rule that a version carries example tasks and a passing rehearsal
    of them (M12.3.4) is `tests/unit/test_skill_packages.py`'s to test: what is tested here is what
    the store writes and reads for a decision, and a pasted `SKILL.md` keeps these rows the ones
    `0056` wrote."""
    return dataclasses.replace(one, imported=one.imported.approved_by(reviewer, NOW))


def approved(text: str = SKILL_MD) -> LibrarySkill:
    return as_approved(a_skill(text))


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
    """Compared as rendered DDL, for the reason `test_tables` compares 0002's, with `0121`'s
    declared amendments applied. Delete this and the model can gain a column or lose a key with the
    database built the old way."""
    expected = squash(str(CreateTable(metadata.tables[qualified]).compile(dialect=DIALECT)))

    assert expected in as_amended(rendered("upgrade", MIGRATION))


def test_a_self_decision_must_say_so_and_only_an_approved_skill_is_assigned_in_the_tables() -> None:
    """The rules the domain enforces are in the tables' own definitions: a decision by the importer
    is admitted only as a row saying it is their own, and only the importer's row may say so, whose
    copy is held to the skill row by a composite key; an assignment names the decision `approved`
    through a key.

    Delete this and either constraint can be dropped from the model and the migration together,
    every rendered comparison above still passes, and a hand-written statement records a
    self-approval as an ordinary one or assigns a rejected skill."""
    review = squash(
        str(CreateTable(metadata.tables["agent.skill_review"]).compile(dialect=DIALECT))
    )
    assigned = squash(
        str(CreateTable(metadata.tables["agent.skill_assignment"]).compile(dialect=DIALECT))
    )

    assert "CHECK (self_decided OR submitted_by <> decided_by)" in review
    assert "CHECK (NOT self_decided OR decided_by = submitted_by)" in review
    assert "self_decided BOOLEAN DEFAULT false NOT NULL" in review
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
        "self_decided": False,
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
        good = as_approved(one)

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
        (
            IMPORTER,
            "skill:hosting-expiry",
            {"change": "imported", "digest": one.digest, "source": "upload"},
        ),
        (REVIEWER, "skill:hosting-expiry", {"change": "approved", "digest": one.digest}),
    ]
    assert AuditChain(chain).verify() is None


def test_the_database_refuses_an_unsaid_self_decision_and_an_assignment_nobody_approved() -> None:
    """Measured as the application role, with the session naming the actor so the policy admits the
    row: the check refuses the importer as decider when the row does not say it is their own, the
    key refuses an assignment of undecided bytes, and an assignment of approved bytes is recorded
    under the folded name.

    Delete this and both rules are claims about a table definition nobody has run. **Skips without
    a server.**"""
    with through_0056("brain_skill_library_refusals") as url:
        one = a_skill(
            text_with(
                name="quote-format",
                description="Use when a client asks for a quote to be formatted",
            )
        )
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


# ------------------------------------------------------------------------------------ 0121
MIGRATION_0121 = VERSIONS / "0121_skill_sources_versions_and_categories.py"


def test_0121_copies_the_grammars_and_figures_the_models_and_the_domain_hold() -> None:
    """`0121` copies a commit grammar, a path grammar, the category bound, the widened source and
    decider predicates and the source kinds. Delete this and one side can change alone: a source
    the domain builds and the table refuses after the press, or a category count the table and the
    library disagree about."""
    migration = migration_module(MIGRATION_0121)

    assert migration.COMMIT_PATTERN == table_module.COMMIT_PATTERN == COMMIT_RE.pattern
    assert migration.PATH_PATTERN == table_module.PATH_PATTERN
    assert migration.MAX_CATEGORIES == table_module.MAX_CATEGORIES == MAX_CATEGORIES
    assert (migration.IDENTIFIER, migration.DIGEST) == (IDENTIFIER, DIGEST)
    assert migration.SKILL_NAME_PATTERN == table_module.SKILL_NAME_PATTERN
    assert migration.SOURCE_AFTER == table_module.SOURCE_KIND_CHECK
    assert migration.DECIDER_AFTER == table_module.NOBODY_DECIDES_THEIR_OWN_UNLESS_SAID
    assert set(table_module.SOURCE_KINDS) == {kind.value for kind in SourceKind}
    assert migration.PATH_CHARS == table_module.PATH_CHARS == longest(SkillSource, "path")
    assert migration.TABLES == ("agent.skill_category",)


def test_0121_emits_the_amendments_the_model_comparison_believes() -> None:
    """`AMENDS_CREATE_TABLE` and `SUPERSEDES` are claims the DDL comparison above trusts. Each
    added column is emitted with the checks the model declares on it, the key is emitted, the two
    widened checks are emitted under `0056`'s names, and the category table is built as its model.

    Delete this and `0121` can say it added a column or widened a check while its upgrade does
    neither, and every comparison built on the claim stays green."""
    emitted = squash(rendered("upgrade", MIGRATION_0121))
    model = {
        str(one.name): str(one.sqltext)
        for qualified in ("agent.skill", "agent.skill_review")
        for one in metadata.tables[qualified].constraints
        if hasattr(one, "sqltext")
    }

    statements = [one.strip() for one in emitted.split(";")]
    for column, width, checks in (
        (
            "source_commit",
            "VARCHAR(40)",
            ("source_commit_shape", "a_repository_source_names_its_commit"),
        ),
        ("source_path", "VARCHAR(200)", ("source_path_on_a_repository_source",)),
        ("edited_from", "VARCHAR(64)", ("edited_from_another_version",)),
    ):
        # A column's constraints are a set to SQLAlchemy, so their order in the statement is not
        # asserted; each is asserted to be in the one statement that adds the column.
        (added_column,) = [
            one
            for one in statements
            if one.startswith(f"ALTER TABLE agent.skill ADD COLUMN {column} {width} ")
        ]
        for name in checks:
            assert f"CONSTRAINT ck_skill_{name} CHECK ({model[f'ck_skill_{name}']})" in added_column
    assert (
        "ALTER TABLE agent.skill ADD CONSTRAINT fk_skill_edited_from_skill "
        "FOREIGN KEY(edited_from) REFERENCES agent.skill (digest)"
    ) in emitted
    assert (
        "ALTER TABLE agent.skill_review ADD COLUMN self_decided BOOLEAN DEFAULT false NOT NULL "
        "CONSTRAINT ck_skill_review_self_decided_only_by_the_importer CHECK "
        f"({model['ck_skill_review_self_decided_only_by_the_importer']})"
    ) in emitted
    assert (
        "ALTER TABLE agent.skill ADD CONSTRAINT ck_skill_source_is_an_upload CHECK "
        f"({model['ck_skill_source_is_an_upload']})"
    ) in emitted
    assert (
        "ALTER TABLE agent.skill_review ADD CONSTRAINT "
        "ck_skill_review_nobody_decides_their_own_import "
        f"CHECK ({model['ck_skill_review_nobody_decides_their_own_import']})"
    ) in emitted
    category = squash(
        str(CreateTable(metadata.tables["agent.skill_category"]).compile(dialect=DIALECT))
    )
    assert category in emitted


def test_0121_writes_categories_in_the_session_s_name_only_and_never_edits_them() -> None:
    """Row-level security on, SELECT and INSERT only, the insert policy in the setter's name, and a
    trigger after every insert. Delete this and a category change can be written in somebody else's
    name, edited in place, or made with no ledger entry."""
    emitted = squash(rendered("upgrade", MIGRATION_0121))
    principal = "current_setting('app.principal_id', true)"

    assert "ALTER TABLE agent.skill_category ENABLE ROW LEVEL SECURITY" in emitted
    assert "GRANT SELECT, INSERT ON agent.skill_category TO brain_app" in emitted
    assert "UPDATE ON agent.skill_category" not in emitted
    assert "DELETE ON agent.skill_category" not in emitted
    assert f"FOR INSERT TO brain_app WITH CHECK (set_by = {principal})" in emitted
    assert (
        "CREATE TRIGGER skill_category_is_audited AFTER INSERT ON agent.skill_category "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_skill_category()"
    ) in emitted


def test_0121_s_triggers_write_what_the_recorder_writes_for_an_import_an_edit_and_a_decision() -> (
    None
):
    """An import records its source, an edit the version it came from, and the importer's own
    decision `self_approved` or `self_rejected`. Delete this and the entry a deployed database keeps
    and the one `AuditRecorder.skill` writes can come apart, and the audit screen's search for a
    self-approval finds nothing."""
    migration = migration_module(MIGRATION_0121)
    recorder = AuditRecorder(
        AuditChain(), actor_id=IMPORTER, ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )
    one = a_skill()
    imported = recorder.skill(
        name=one.name, digest=one.digest, change=SkillChange.IMPORTED, source="github"
    )
    edited_entry = recorder.skill(
        name=one.name, digest="e" * 64, change=SkillChange.EDITED, edited_from=one.digest
    )
    body = " ".join(migration.SKILL_IMPORT_TRIGGER_FUNCTION.split())
    review = " ".join(migration.SKILL_REVIEW_TRIGGER_FUNCTION.split())
    category = " ".join(migration.SKILL_CATEGORY_TRIGGER_FUNCTION.split())

    assert dict(imported.details) == {
        "change": "imported",
        "digest": one.digest,
        "source": "github",
    }
    assert dict(edited_entry.details) == {
        "change": "edited",
        "digest": "e" * 64,
        "edited_from": one.digest,
    }
    assert (
        "WHEN NEW.edited_from IS NOT NULL THEN jsonb_build_object( 'change', 'edited', 'digest', "
        "NEW.digest, 'edited_from', NEW.edited_from )"
    ) in body
    assert (
        "ELSE jsonb_build_object( 'change', 'imported', 'digest', NEW.digest, 'source', "
        "NEW.source_kind )"
    ) in body
    assert (
        "'change', CASE WHEN NEW.self_decided THEN 'self_' || NEW.decision ELSE NEW.decision END"
        in review
    )
    assert {SkillChange.SELF_APPROVED.value, SkillChange.SELF_REJECTED.value} == {
        f"self_{SkillState.APPROVED.value}",
        f"self_{SkillState.REJECTED.value}",
    }
    assert f"jsonb_build_object('change', '{SkillChange.CATEGORISED.value}')" in category
    assert "v_seq, v_at, NEW.set_by, 'skill', v_subject" in category


def test_0121_s_downgrade_puts_back_0056_s_trigger_bodies() -> None:
    """Delete this and a rollback leaves triggers reading columns the rollback dropped, so the next
    import on the previous release fails inside its own trigger."""
    old = migration_module(MIGRATION)
    new = migration_module(MIGRATION_0121)

    def body(text: str) -> str:
        return " ".join(text.split()).replace("CREATE OR REPLACE FUNCTION", "CREATE FUNCTION")

    assert body(new.PREVIOUS_IMPORT_FUNCTION) == body(old.SKILL_IMPORT_TRIGGER_FUNCTION)
    assert body(new.PREVIOUS_REVIEW_FUNCTION) == body(old.SKILL_REVIEW_TRIGGER_FUNCTION)
    down = squash(rendered("downgrade", MIGRATION_0121))
    assert down.index("CREATE OR REPLACE FUNCTION agent.record_skill_review()") < down.index(
        "DROP COLUMN self_decided"
    )


def test_a_repository_source_and_an_edit_read_back_as_they_were_added() -> None:
    """`0121`'s columns written by `skill_values` and read by `library_skill_of`. Delete this and a
    commit or a folder is read back into the wrong field, or an edit forgets its parent."""
    source = SkillSource(
        kind=SourceKind.GITHUB,
        location="example-org/agent-skills",
        commit="0" * 40,
        path="skills/hosting-expiry",
        content_digest="f" * 64,
    )
    package = read_package("SKILL.md", SKILL_MD.encode("utf-8"))
    one = added(Package(skill=package.skill, source=source), by=IMPORTER, at=NOW)
    edit = LibrarySkill(
        imported=one.imported,
        digest="d" * 64,
        submitted_by=IMPORTER,
        submitted_at=NOW,
        edited_from=one.digest,
    )

    assert library_skill_of(*rows_for(one)) == one
    assert skill_values(one)["source_commit"] == "0" * 40
    assert skill_values(one)["source_path"] == "skills/hosting-expiry"
    assert skill_values(a_skill())["source_commit"] is None
    assert skill_values(edit)["edited_from"] == one.digest
    assert library_skill_of(SkillRow(**skill_values(edit), created_at=NOW), None).edited_from == (  # type: ignore[union-attr]
        one.digest
    )


@contextmanager
def through_0121(database: str) -> Iterator[str]:
    """A database with `0121` applied: the whole chain where the server has pgvector, and
    otherwise `through_0056`'s chain with the revisions between it and `0121` stamped."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            migrate(database, "stamp", "0053")
            migrate(database, "upgrade", "0056")
            migrate(database, "stamp", str(migration_module(MIGRATION_0121).down_revision))
            migrate(database, "upgrade", "0121")
        yield url


def test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger() -> None:
    """**M12.2.2, M12.2.3, M12.3.2, M12.4.6 and M12.4.13 through the store and the application
    role.** A skill from a repository and one from an address, an edit of the first, a
    self-approval of the edit and categories set twice: every row reads back as written, the
    newest categories are the ones that apply, and the ledger holds one `skill` entry for each
    write, saying how each import arrived, which version the edit came from, that the approval was
    the importer's own, and that categories changed; the chain verifies. **Skips without a
    server.**"""
    github = added(read_package("SKILL.md", SKILL_MD.encode("utf-8")), by=IMPORTER, at=NOW)
    github = LibrarySkill(
        imported=github.imported.model_copy(
            update={
                "source": SkillSource(
                    kind=SourceKind.GITHUB,
                    location="example-org/agent-skills",
                    commit="0" * 40,
                    path="skills/hosting-expiry",
                    content_digest=github.imported.source.content_digest,
                )
            }
        ),
        digest=github.digest,
        submitted_by=IMPORTER,
        submitted_at=NOW,
    )
    quote = text_with(name="quote-format", description="Use when a client asks for a quote")
    from_url = added(
        read_url("https://raw.githubusercontent.com/o/r/main/SKILL.md", quote.encode()),
        by=IMPORTER,
        at=NOW,
    )
    new_text = text_with(version="1.1.0").replace("open a ticket", "call the client")
    edit = edited(github, new_text, by=IMPORTER, at=NOW, library=(github,))
    own = as_approved(edit, reviewer=IMPORTER)

    with through_0121("brain_skill_library_0121") as url:

        async def writes() -> tuple[tuple[LibrarySkill, ...], Mapping[str, tuple[str, ...]]]:
            engine = app_engine(url)
            try:
                store = StoredSkills(make_session_factory(engine))
                for one in (github, from_url, edit):
                    assert await store.add(one, ent_hash="a" * 32, trace_id="trace-add")
                assert await store.decide(own, ent_hash="b" * 32, trace_id="trace-own")
                for categories in (("hosting",), ("hosting", "seo")):
                    await store.categorise(
                        github.name, categories, by=IMPORTER, ent_hash="c" * 32, trace_id="t"
                    )
                return await store.library(), await store.categories(
                    [github.name, from_url.name, "nobody-filed-this"]
                )
            finally:
                await engine.dispose()

        library, filed = run(writes)
        chain = entries(url)

    by_digest = {one.digest: one for one in library}

    def written(one: LibrarySkill) -> tuple[object, ...]:
        # The instant is the database's own clock on the way back, not the one the test chose.
        return (one.imported, one.digest, one.submitted_by, one.edited_from)

    assert written(by_digest[github.digest]) == written(github)
    assert written(by_digest[from_url.digest]) == written(from_url)
    assert by_digest[edit.digest].edited_from == github.digest
    assert by_digest[edit.digest].self_decided is True
    assert by_digest[edit.digest].imported.is_executable() is True
    assert filed == {github.name: ("hosting", "seo")}
    skill_entries = [
        (entry.actor_id, entry.subject, dict(entry.details))
        for entry in chain
        if entry.action is AuditAction.SKILL
    ]
    assert skill_entries == [
        (
            IMPORTER,
            "skill:hosting-expiry",
            {"change": "imported", "digest": github.digest, "source": "github"},
        ),
        (
            IMPORTER,
            "skill:quote-format",
            {"change": "imported", "digest": from_url.digest, "source": "url"},
        ),
        (
            IMPORTER,
            "skill:hosting-expiry",
            {"change": "edited", "digest": edit.digest, "edited_from": github.digest},
        ),
        (IMPORTER, "skill:hosting-expiry", {"change": "self_approved", "digest": edit.digest}),
        (IMPORTER, "skill:hosting-expiry", {"change": "categorised"}),
        (IMPORTER, "skill:hosting-expiry", {"change": "categorised"}),
    ]
    assert AuditChain(chain).verify() is None


def test_the_tables_refuse_a_source_or_a_decision_that_does_not_say_what_it_is() -> None:
    """Measured as the application role: a repository row naming no commit, an upload naming one,
    an edit of a version that does not exist, a self-decision flag on somebody else's decision,
    categories set in another person's name and nine categories are each refused, and a
    self-decision that says so is admitted. **Skips without a server.**"""
    one = a_skill()
    values = skill_values(one)

    def inserting(row: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
        columns = ", ".join(row)
        marks = ", ".join(["%s"] * len(row))
        return (
            f"INSERT INTO agent.skill ({columns}) VALUES ({marks})",  # noqa: S608
            tuple(psycopg.types.json.Jsonb(v) if k == "tools" else v for k, v in row.items()),
        )

    with through_0121("brain_skill_library_0121_refusals") as url:
        with as_app(url, ("app.principal_id", IMPORTER)) as conn:
            for bad in (
                values | {"source_kind": "github"},
                values | {"source_commit": "0" * 40},
                values | {"source_path": "skills/x"},
                values | {"edited_from": "e" * 64},
            ):
                with pytest.raises(psycopg.errors.IntegrityError):
                    conn.execute(*inserting(bad))
            conn.execute(*inserting(values))
            conn.execute(
                "INSERT INTO agent.skill_review (digest, submitted_by, decision, decided_by,"
                " self_decided) VALUES (%s, %s, 'approved', %s, true)",
                (one.digest, IMPORTER, IMPORTER),
            )
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO agent.skill_category (skill_name, categories, set_by)"
                    " VALUES (%s, %s, %s)",
                    (one.name, psycopg.types.json.Jsonb([f"c{n}" for n in range(9)]), IMPORTER),
                )
        with (
            as_app(url, ("app.principal_id", REVIEWER)) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute(
                "INSERT INTO agent.skill_category (skill_name, categories, set_by)"
                " VALUES (%s, %s, %s)",
                (one.name, psycopg.types.json.Jsonb(["x"]), IMPORTER),
            )
        other = a_skill(text_with(name="quote-format", description="Use when a quote is due"))
        with as_app(url, ("app.principal_id", IMPORTER)) as conn:
            conn.execute(*inserting(skill_values(other)))
        with (
            as_app(url, ("app.principal_id", REVIEWER)) as conn,
            pytest.raises(psycopg.errors.CheckViolation),
        ):
            conn.execute(
                "INSERT INTO agent.skill_review (digest, submitted_by, decision, decided_by,"
                " self_decided) VALUES (%s, %s, 'approved', %s, true)",
                (other.digest, IMPORTER, REVIEWER),
            )
        decided_rows = sql(url, "SELECT digest, self_decided FROM agent.skill_review")

    assert decided_rows == [(one.digest, True)]
