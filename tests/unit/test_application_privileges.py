"""The two readings `brain.ops.application_privileges` compares, each driven from text written here.

The invariant in `tests/invariants/test_application_privileges.py` runs the comparison over the
repository. This file holds the parts of it to what PostgreSQL and SQLAlchemy actually do, one
shape at a time, so a reading that stops recognising a shape fails with that shape's name rather
than as an invariant that went quietly green.

Task ids: M27.9.7
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.ops.application_privileges import (
    NO_COLUMN_GRANT,
    NO_GRANT,
    NO_POLICY,
    NO_SETTING,
    NO_SUCH_TABLE,
    Catalogue,
    Use,
    catalogue_of,
    mismatches,
    reachable,
    settings_named,
    sql_uses,
    statements,
    uses_in,
)

KNOWN: frozenset[str] = frozenset(
    {"ops.control_run", "ops.setting", "know.item", "obs.audit_entry", "gate.suspension"}
)

GRANTED = """
CREATE TABLE ops.control_run (id uuid);
ALTER TABLE ops.control_run ENABLE ROW LEVEL SECURITY;
CREATE POLICY control_run_readable ON ops.control_run FOR SELECT TO brain_app USING (true);
GRANT SELECT ON ops.control_run TO brain_app;
"""


def a_module(tmp_path: Path, name: str, source: str) -> tuple[Path, Path]:
    """A module in a source tree of its own, as `src/brain/<name>.py` is in the repository."""
    src = tmp_path / "brain"
    src.mkdir(exist_ok=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    path = src / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    return path, src


def found(tmp_path: Path, source: str, name: str = "store") -> set[tuple[str, str]]:
    path, src = a_module(tmp_path, name, source)
    return {(one.table, one.privilege) for one in uses_in(path, KNOWN, src)}


# ------------------------------------------------------------------------ the script
def test_a_statement_ends_at_a_semicolon_outside_a_comment_a_string_or_a_body() -> None:
    """An apostrophe in a comment, a semicolon in a string and a function body full of them.

    Delete this and the rendered script's `-- Running upgrade ... somebody's data` comment opens a
    string that swallows the next migration's grants, which is what the first version did."""
    script = (
        "-- Running upgrade 0059 -> 0060, somebody's data\n"
        "CREATE TABLE ops.a (x text DEFAULT 'a;b');\n"
        "CREATE FUNCTION ops.f() RETURNS trigger AS $b$ BEGIN PERFORM 1; RETURN NULL; END; $b$;\n"
        "GRANT SELECT ON ops.a TO brain_app;"
    )

    assert statements(script) == (
        "CREATE TABLE ops.a (x text DEFAULT 'a;b')",
        "CREATE FUNCTION ops.f() RETURNS trigger AS $b$ BEGIN PERFORM 1; RETURN NULL; END; $b$",
        "GRANT SELECT ON ops.a TO brain_app",
    )


def test_a_grant_a_revoke_a_column_grant_and_a_role_membership_are_read_in_order() -> None:
    """Delete this and a revoke, a column grant or a privilege held through `brain_fastlane` is
    read as its opposite."""
    read = catalogue_of(
        """
        CREATE TABLE ops.a (x text); CREATE TABLE ops.b (x text); CREATE TABLE proj.r (x text);
        GRANT SELECT, INSERT, UPDATE ON ops.a TO brain_app;
        REVOKE UPDATE ON ops.a FROM brain_app;
        GRANT SELECT, INSERT ON ops.b TO brain_app;
        GRANT UPDATE (state, decided_at) ON ops.b TO brain_app;
        GRANT brain_fastlane TO brain_app;
        GRANT SELECT ON proj.r TO brain_fastlane;
        """
    )

    assert read.holds("brain_app", "ops.a", "INSERT")
    assert not read.holds("brain_app", "ops.a", "UPDATE")
    assert read.holds("brain_app", "ops.b", "UPDATE")
    assert read.columns_held("brain_app", "ops.b", "UPDATE") == frozenset({"state", "decided_at"})
    assert read.columns_held("brain_app", "ops.a", "SELECT") is None
    assert read.holds("brain_app", "proj.r", "SELECT")
    assert not read.holds("brain_fastlane", "ops.a", "SELECT")


def test_row_security_admits_a_command_only_through_a_permissive_policy_naming_the_role() -> None:
    """Security off admits everything; on, a policy for the command or for ALL naming the role
    does; a restrictive one, one for another role, and one dropped afterwards do not.

    Delete this and a table whose only policy was dropped and re-created under the same name for
    another command reads as still admitting the first."""
    read = catalogue_of(
        """
        CREATE TABLE ops.open (x text);
        CREATE TABLE ops.closed (x text);
        ALTER TABLE ops.closed ENABLE ROW LEVEL SECURITY;
        CREATE POLICY p ON ops.closed FOR ALL TO brain_app USING (true) WITH CHECK (true);
        DROP POLICY p ON ops.closed;
        CREATE POLICY p ON ops.closed FOR SELECT TO brain_app USING (true);
        CREATE POLICY q ON ops.closed AS RESTRICTIVE FOR INSERT TO brain_app WITH CHECK (true);
        CREATE POLICY r ON ops.closed FOR DELETE TO brain_fastlane USING (true);
        """
    )

    assert read.admits("brain_app", "ops.open", "DELETE")
    assert read.admits("brain_app", "ops.closed", "SELECT")
    assert not read.admits("brain_app", "ops.closed", "UPDATE")
    assert not read.admits("brain_app", "ops.closed", "INSERT")
    assert not read.admits("brain_app", "ops.closed", "DELETE")


def test_a_policy_reading_a_setting_needs_it_only_when_every_admitting_policy_reads_it() -> None:
    """Delete this and a policy admitting company rows to anybody reads as requiring a principal,
    or an insert whose check is `true` reads as needing what only the read needs."""
    read = catalogue_of(
        """
        CREATE TABLE know.item (x text);
        ALTER TABLE know.item ENABLE ROW LEVEL SECURITY;
        CREATE POLICY own ON know.item FOR ALL TO brain_app
            USING (owner_id = current_setting('app.principal_id', true)) WITH CHECK (true);
        CREATE TABLE ops.setting (x text);
        ALTER TABLE ops.setting ENABLE ROW LEVEL SECURITY;
        CREATE POLICY own ON ops.setting FOR SELECT TO brain_app
            USING (by = current_setting('app.principal_id', true));
        CREATE POLICY everyone ON ops.setting FOR SELECT TO brain_app USING (true);
        """
    )

    assert read.settings_needed("brain_app", "know.item", "SELECT") == {"app.principal_id"}
    assert read.settings_needed("brain_app", "know.item", "INSERT") == frozenset()
    assert read.settings_needed("brain_app", "ops.setting", "SELECT") == frozenset()


def test_an_invoker_trigger_body_is_kept_and_a_definer_one_is_not() -> None:
    """Delete this and a write whose audit trigger appends as the writer is compared without the
    append, or a `SECURITY DEFINER` body is charged to the caller."""
    read = catalogue_of(
        """
        CREATE TABLE ops.setting (x text);
        CREATE FUNCTION ops.record() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN MERGE INTO obs.audit_entry AS t USING (SELECT 1 AS s) AS s ON false
            WHEN NOT MATCHED THEN INSERT (seq) VALUES (1); RETURN NULL; END; $$;
        CREATE FUNCTION ops.owner() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
        BEGIN INSERT INTO ops.control_run (id) VALUES (gen_random_uuid()); RETURN NULL; END; $$;
        CREATE TRIGGER a AFTER INSERT OR UPDATE ON ops.setting
            FOR EACH ROW EXECUTE FUNCTION ops.record();
        CREATE TRIGGER b AFTER DELETE ON ops.setting FOR EACH ROW EXECUTE FUNCTION ops.owner();
        """
    )

    (body,) = read.fired_by("ops.setting", "UPDATE")
    assert set(sql_uses(body, KNOWN)) == {
        ("obs.audit_entry", "SELECT"),
        ("obs.audit_entry", "INSERT"),
    }
    assert read.fired_by("ops.setting", "DELETE") == ()
    assert read.fired_by("ops.setting", "SELECT") == ()


# -------------------------------------------------------------------------- the SQL
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            "SELECT id FROM ops.control_run JOIN ops.setting s ON true",
            {("ops.control_run", "SELECT"), ("ops.setting", "SELECT")},
        ),
        ("INSERT INTO ops.setting (k) VALUES ('x')", {("ops.setting", "INSERT")}),
        (
            "INSERT INTO ops.setting (k) VALUES ('x') ON CONFLICT (k) DO UPDATE SET v = 1",
            {("ops.setting", "INSERT"), ("ops.setting", "UPDATE")},
        ),
        (
            "UPDATE ops.setting SET v = 1 WHERE k = 'x'",
            {("ops.setting", "UPDATE"), ("ops.setting", "SELECT")},
        ),
        (
            "DELETE FROM ops.setting WHERE k = 'x'",
            {("ops.setting", "DELETE"), ("ops.setting", "SELECT")},
        ),
        (
            "SELECT k FROM ops.setting WHERE k = 'x' FOR UPDATE SKIP LOCKED",
            {("ops.setting", "SELECT"), ("ops.setting", "UPDATE")},
        ),
        ("SELECT 1 FROM ops.somewhere_else", set()),
    ],
)
def test_a_sql_string_needs_what_its_verb_and_its_clauses_ask_postgresql_for(
    sql: str, expected: set[tuple[str, str]]
) -> None:
    """Delete this and an upsert reads as an insert alone, a row lock as a read, or a filtered
    update as needing no read of its own target, each of which PostgreSQL refuses."""
    assert set(sql_uses(sql, KNOWN)) == expected


# ------------------------------------------------------------------------ the source
def test_a_model_is_charged_by_the_statement_it_sits_in(tmp_path: Path) -> None:
    """A select reads, an insert target inserts, an update target updates and reads its filter, a
    delete deletes, and a column's own methods inside a select are still a read.

    Delete this and `X.started_at.desc()` inside a select is charged as an insert, which the first
    version did, or an update's filter goes uncharged."""
    source = """
from sqlalchemy import delete, insert, select, update
from brain.tables.schedule import ControlRunRow

def read():
    return select(ControlRunRow.name).order_by(ControlRunRow.started_at.desc()).limit(1)

def add():
    return insert(ControlRunRow).values(name="x")

def finish():
    return update(ControlRunRow).where(ControlRunRow.id == 1).values(outcome="ok")

def remove():
    return delete(ControlRunRow).where(ControlRunRow.id == 1)
"""
    assert found(tmp_path, source) == {
        ("ops.control_run", "SELECT"),
        ("ops.control_run", "INSERT"),
        ("ops.control_run", "UPDATE"),
        ("ops.control_run", "DELETE"),
    }


def test_a_row_lock_charges_only_the_tables_it_names_and_a_constructed_model_inserts(
    tmp_path: Path,
) -> None:
    """Delete this and `with_for_update(of=X)` charges every joined table with UPDATE, or a model
    handed to `session.add` goes uncharged."""
    locked = """
from sqlalchemy import select
from brain.tables.schedule import ControlRunRow
from brain.tables.config import SettingRow

def claim():
    return (
        select(ControlRunRow, SettingRow)
        .join(SettingRow, SettingRow.key == ControlRunRow.name)
        .with_for_update(of=ControlRunRow)
    )
"""
    added = """
from brain.tables.schedule import ControlRunRow

async def start(session):
    session.add(ControlRunRow(name="x"))
"""
    assert found(tmp_path, locked) == {
        ("ops.control_run", "SELECT"),
        ("ops.control_run", "UPDATE"),
        ("ops.setting", "SELECT"),
    }
    assert found(tmp_path, added, name="other") == {("ops.control_run", "INSERT")}


def test_an_upsert_built_through_a_variable_updates_and_a_docstring_is_not_sql(
    tmp_path: Path,
) -> None:
    """Delete this and `statement = insert(X)` then `statement.on_conflict_do_update(...)`, the
    shape `brain.ops.setting_store` writes, reads as an insert alone; or a docstring explaining a
    statement is charged as one."""
    source = '''
"""Reads FROM ops.control_run, which this sentence only describes."""
from sqlalchemy.dialects.postgresql import insert
from brain.tables.config import SettingRow

def put():
    """UPDATE ops.control_run SET nothing, in prose."""
    statement = insert(SettingRow).values(key="k")
    return statement.on_conflict_do_update(index_elements=[SettingRow.key], set_={"value": 1})
'''
    assert found(tmp_path, source) == {
        ("ops.setting", "INSERT"),
        ("ops.setting", "UPDATE"),
        ("ops.setting", "SELECT"),
    }


def test_a_core_table_and_a_string_handed_to_text_are_read(tmp_path: Path) -> None:
    """Delete this and `know.chunk`, which is a Core `Table` and not a model, or a `text(...)`
    statement, is invisible to the comparison."""
    source = """
import sqlalchemy as sa
from sqlalchemy import text
from brain.db import Base

ITEMS = sa.Table(
    "item", Base.metadata, sa.Column("item_id", sa.String()), schema="know", extend_existing=True
)

def count():
    return sa.select(ITEMS.c.item_id)

def raw():
    return text("DELETE FROM obs.audit_entry WHERE seq = :s")
"""
    assert found(tmp_path, source) == {
        ("know.item", "SELECT"),
        ("obs.audit_entry", "DELETE"),
        ("obs.audit_entry", "SELECT"),
    }


def test_a_row_changed_by_assigning_to_a_loaded_object_is_not_seen(tmp_path: Path) -> None:
    """**The blind spot, pinned.** `WHAT_THE_SOURCE_DOES_NOT_SAY` says a unit-of-work update is
    invisible, and this holds that sentence true: the day the reader learns the shape, this fails
    and the sentence is corrected rather than left overstating what is missed.

    Delete this and the list of what the comparison cannot see can drift from what it cannot see."""
    source = """
from brain.tables.schedule import ControlRunRow

async def finish(session, run_id):
    row = await session.get(ControlRunRow, run_id)
    row.outcome = "ok"
    await session.commit()
"""
    assert found(tmp_path, source) == {("ops.control_run", "SELECT")}


def test_a_setting_is_named_literally_through_a_constant_or_through_an_imported_function(
    tmp_path: Path,
) -> None:
    """Delete this and `brain.knowledge.chunk_store`, which sets the reach through
    `session_settings` from another module, reads as a writer that never says who it is."""
    src = tmp_path / "brain"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "reach.py").write_text(
        'PRINCIPAL: str = "app.principal_id"\n\n'
        "def settings(who):\n    return ('set', PRINCIPAL, who)\n",
        encoding="utf-8",
    )
    (src / "through_function.py").write_text(
        "from brain.reach import settings\n\nasync def go(s):\n    await s.execute(settings(1))\n",
        encoding="utf-8",
    )
    (src / "through_constant.py").write_text(
        "from brain.reach import PRINCIPAL\n\nNAME = PRINCIPAL\n", encoding="utf-8"
    )
    (src / "names_nothing.py").write_text("def go():\n    return 1\n", encoding="utf-8")

    assert settings_named(src / "through_function.py", src) == {"app.principal_id"}
    assert settings_named(src / "through_constant.py", src) == {"app.principal_id"}
    assert settings_named(src / "names_nothing.py", src) == frozenset()


def test_reach_follows_imports_at_any_depth_and_the_packages_they_run(tmp_path: Path) -> None:
    """Delete this and a store imported inside a route's function body, which is where several
    routes import theirs, falls outside the application's reach."""
    src = tmp_path / "brain"
    (src / "ops").mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "ops" / "__init__.py").write_text("", encoding="utf-8")
    (src / "app.py").write_text("def build():\n    from brain.ops import store\n", encoding="utf-8")
    (src / "ops" / "store.py").write_text("import brain.ops.deeper\n", encoding="utf-8")
    (src / "ops" / "deeper.py").write_text("", encoding="utf-8")
    (src / "worker.py").write_text("", encoding="utf-8")

    assert reachable(("brain.app",), src) == {
        "brain",
        "brain.app",
        "brain.ops",
        "brain.ops.store",
        "brain.ops.deeper",
    }


# -------------------------------------------------------------------- the comparison
def test_each_missing_half_is_named_and_a_served_use_is_not_reported(tmp_path: Path) -> None:
    """A policy without a grant, a grant without a policy, a column grant too narrow, a table no
    migration creates, a setting nobody names, and beside them a use every half serves.

    Delete this and the comparison can report everything, which the invariant would read as a
    wall of mismatches, or nothing, which it would read as green."""
    read: Catalogue = catalogue_of(
        GRANTED
        + """
        CREATE TABLE gate.suspension (x text);
        ALTER TABLE gate.suspension ENABLE ROW LEVEL SECURITY;
        CREATE POLICY readable ON gate.suspension FOR SELECT TO brain_app USING (true);
        GRANT SELECT ON gate.suspension TO brain_app;
        GRANT UPDATE (state) ON gate.suspension TO brain_app;
        CREATE POLICY decided ON gate.suspension FOR UPDATE TO brain_app USING (true);
        CREATE TABLE ops.setting (x text);
        ALTER TABLE ops.setting ENABLE ROW LEVEL SECURITY;
        GRANT INSERT ON ops.setting TO brain_app;
        CREATE TABLE know.item (x text);
        ALTER TABLE know.item ENABLE ROW LEVEL SECURITY;
        CREATE POLICY own ON know.item FOR SELECT TO brain_app
            USING (owner_id = current_setting('app.principal_id', true));
        GRANT SELECT ON know.item TO brain_app;
        """
    )
    path, src = a_module(tmp_path, "route", "def nothing():\n    return 1\n")
    module = "brain.route"
    asked = [
        Use(module, 1, "ops.control_run", "SELECT"),
        Use(module, 2, "ops.control_run", "INSERT"),
        Use(module, 3, "ops.setting", "INSERT"),
        Use(module, 4, "gate.suspension", "UPDATE", frozenset({"state", "decided_by"})),
        Use(module, 5, "gate.suspension", "UPDATE", frozenset({"state"})),
        Use(module, 6, "ops.nowhere", "SELECT"),
        Use(module, 7, "know.item", "SELECT"),
    ]
    del path

    reported = {(one.use.line, one.missing) for one in mismatches(read, asked, src=src)}

    assert reported == {
        (2, NO_GRANT),
        (3, NO_POLICY),
        (4, NO_COLUMN_GRANT),
        (6, NO_SUCH_TABLE),
        (7, NO_SETTING),
    }
