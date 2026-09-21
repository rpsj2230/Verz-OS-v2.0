"""Every soft-deleted table can be retired by the application role, stays hidden once retired and
cannot be brought back, read off the policies the migrations leave behind.

**Read from the migrations rather than from a database, because this is where a future migration
is stopped.** The invariants job has no database and refuses a skip, and the defect this guards
was a policy shape copied from one migration into five more, each citing the one before as its
reason. `tests/unit/test_retirable_rows.py` proves the same four properties as `brain_app` on a
real server; this file is what makes the next migration with the old shape red before it is ever
run.

**The replay.** Every `CREATE POLICY` and `DROP POLICY` held in a migration's module constants,
in revision order, gives the policies the schema ends with. A constant whose name begins
`DOWNGRADE_` is history and is not replayed, which is how 0045 and 0046 keep the broken shape
they put back. A policy written anywhere else in a migration is invisible to the replay, so the
first test below refuses one.

**The rules are PostgreSQL's, stated as text.** See
`A_SEPARATE_READ_POLICY_STILL_CHECKS_THE_NEW_ROW` in 0045: an UPDATE with a WHERE clause checks
its new row against the USING of every SELECT and ALL policy. So a read or ALL policy that hides
`deleted_at IS NOT NULL` without admitting the row this statement retired refuses every
retirement, and an update policy whose check does not carry that same admission either refuses it
or lets it be stamped at any instant.

**The writers are held to the stamp as well, because the policies being right did not stop two
of them being wrong.** Until 2026-09-17 `brain.gate.review_store.retire` wrote `deleted_at` as
`now()` and `brain.govern_routes.retire_grant` as the request's instant. The policies above refuse
both as `brain_app`, the unit tests of each compared the SET list with the defect, and only CI's
database ran one of them. So the last section reads every `deleted_at` written under `src/brain`
off the syntax tree, which fails here, with no database, on the commit that writes the next one.

Task ids: none
"""

from __future__ import annotations

import ast
import functools
import importlib.util
import re
import types
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import brain.tables  # noqa: F401 - registers every table on the metadata
from brain.db import metadata

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
SOURCE = Path(__file__).resolve().parents[2] / "src" / "brain"
APP_ROLE = "brain_app"
LIVE = "deleted_at IS NULL"
#: What every read and every update check on a retirable table must carry, whole.
LIVE_OR_RETIRED_NOW = "(deleted_at IS NULL OR deleted_at = statement_timestamp())"


def squash(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class Policy:
    """One policy as its `CREATE POLICY` statement wrote it, whitespace collapsed."""

    name: str
    table: str
    command: str
    roles: frozenset[str]
    using: str | None
    check: str | None

    def reads(self) -> bool:
        return APP_ROLE in self.roles and self.command in {"ALL", "SELECT"}

    def updates(self) -> bool:
        return APP_ROLE in self.roles and self.command in {"ALL", "UPDATE"}

    def update_check(self) -> str:
        """What PostgreSQL checks an updated row against: WITH CHECK, or USING without one."""
        return self.check if self.check is not None else (self.using or "")


_CREATE = re.compile(
    r"^CREATE POLICY (\w+) ON ([\w.]+) (?:AS \w+ )?FOR (\w+) TO (.+?)"
    r"(?: USING (.+?))?(?: WITH CHECK (.+))?$",
    re.IGNORECASE,
)
_DROP = re.compile(r"^DROP POLICY (?:IF EXISTS )?(\w+) ON ([\w.]+)$", re.IGNORECASE)
_NAMED_IN_SOURCE = re.compile(r"CREATE\s+POLICY\s+(\w+)\s+ON\s+([\w.]+)", re.IGNORECASE)


def _unwrapped(clause: str | None) -> str | None:
    """A clause without the one pair of parentheses the statement put around it."""
    if clause is None:
        return None
    clause = clause.strip()
    depth = 0
    for index, character in enumerate(clause):
        depth += {"(": 1, ")": -1}.get(character, 0)
        if depth == 0 and index < len(clause) - 1:
            return clause
    return squash(clause[1:-1]) if clause.startswith("(") else clause


def parse(statement: str) -> Policy:
    found = _CREATE.match(squash(statement))
    assert found is not None, f"a CREATE POLICY this replay cannot read: {statement}"
    name, table, command, roles, using, check = found.groups()
    return Policy(
        name=name,
        table=table,
        command=command.upper(),
        roles=frozenset(one.strip() for one in roles.split(",")),
        using=_unwrapped(using),
        check=_unwrapped(check),
    )


@functools.cache
def _module(path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_replay_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrations() -> list[Path]:
    return sorted(VERSIONS.glob("[0-9][0-9][0-9][0-9]_*.py"))


def _strings(module: types.ModuleType, *, history: bool) -> Iterator[tuple[str, str]]:
    """(constant name, statement) for every policy statement a module's constants hold."""
    for name, value in vars(module).items():
        if name.startswith("_") or name.startswith("DOWNGRADE_") is not history:
            continue
        values = (value,) if isinstance(value, str) else value
        if not isinstance(values, tuple | list):
            continue
        for one in values:
            if isinstance(one, str) and squash(one).upper().startswith(
                ("CREATE POLICY", "DROP POLICY")
            ):
                yield name, squash(one)


def replay(before: str | None = None) -> dict[tuple[str, str], Policy]:
    """The policies the migrations leave, or the ones they had left before revision `before`."""
    policies: dict[tuple[str, str], Policy] = {}
    for path in migrations():
        if before is not None and path.name[:4] >= before:
            break
        for _, statement in _strings(_module(path), history=False):
            dropped = _DROP.match(statement)
            if dropped is not None:
                key = (dropped.group(2), dropped.group(1))
                assert key in policies, f"{path.name} drops {key}, which the replay never saw"
                del policies[key]
                continue
            policy = parse(statement)
            policies[(policy.table, policy.name)] = policy
    return policies


def soft_deleted_tables() -> frozenset[str]:
    return frozenset(key for key, table in metadata.tables.items() if "deleted_at" in table.c)


def built_after_the_repair() -> frozenset[str]:
    """Soft-deleted tables a migration after `0046` built, read from each migration's `TABLES`.

    They did not exist when `0045` and `0046` repaired the policies, so a replay to `0045` cannot
    find them hidden; each is built with the repaired policy from its first migration, which the
    rules below hold on the current schema.
    """
    found: set[str] = set()
    for path in sorted(VERSIONS.glob("*.py")):
        if path.stem[:4].isdigit() and int(path.stem[:4]) > 46:
            found.update(getattr(_module(path), "TABLES", ()))
    return frozenset(found) & soft_deleted_tables()


def _on(policies: dict[tuple[str, str], Policy], table: str) -> list[Policy]:
    return [one for (on, _), one in sorted(policies.items()) if on == table]


# ------------------------------------------------------------------------- the rules


def carries_the_stamp(clause: str) -> bool:
    """Whether a clause admits the row this statement retired, as a whole parenthesised term.

    Read with the clause's own parentheses put back, because `parse` removes the pair around a
    whole clause, and a policy whose USING is exactly the disjunction arrives without them. An
    unparenthesised `a OR b AND c` still fails, which is the precedence mistake it should fail.
    """
    return LIVE_OR_RETIRED_NOW in f"({clause})"


def hidden_from_its_own_retirement(policies: dict[tuple[str, str], Policy]) -> list[str]:
    """Read or ALL policies whose USING refuses the new row of a retiring UPDATE."""
    found: list[str] = []
    for table in sorted(soft_deleted_tables()):
        for one in _on(policies, table):
            if not one.reads():
                continue
            using = one.using or ""
            if one.command == "ALL" and LIVE in using:
                found.append(f"{table}: {one.name} is FOR ALL and hides retired rows")
            elif LIVE in using and not carries_the_stamp(using):
                found.append(f"{table}: {one.name} hides the row its own retirement writes")
    return found


def not_stamped_by_its_statement(policies: dict[tuple[str, str], Policy]) -> list[str]:
    """Tables where no update admits a retirement, or one admits it at any instant."""
    found: list[str] = []
    for table in sorted(soft_deleted_tables()):
        updates = [one for one in _on(policies, table) if one.updates()]
        if not updates:
            found.append(f"{table}: no policy admits an update, so nothing can retire a row")
        found.extend(
            f"{table}: {one.name} checks an updated row against {one.update_check()!r}"
            for one in updates
            if not carries_the_stamp(one.update_check())
        )
    return found


def brought_back(policies: dict[tuple[str, str], Policy]) -> list[str]:
    """Update policies that reach a retired row. Permissive, so one is enough to un-retire."""
    return [
        f"{table}: {one.name} updates rows whatever their deleted_at"
        for table in sorted(soft_deleted_tables())
        for one in _on(policies, table)
        if one.updates() and LIVE not in (one.using or "")
    ]


def readable_once_retired(policies: dict[tuple[str, str], Policy]) -> list[str]:
    """Read policies that admit retired rows. Permissive, so one is enough to read them."""
    return [
        f"{table}: {one.name} reads rows whatever their deleted_at"
        for table in sorted(soft_deleted_tables())
        for one in _on(policies, table)
        if one.reads() and LIVE not in (one.using or "")
    ]


def retirable_migration() -> types.ModuleType:
    return _module(VERSIONS / "0045_retirable_rows.py")


# ------------------------------------------------------------------------- the tests


def test_every_policy_a_migration_writes_is_one_the_replay_reads() -> None:
    """A policy written inline in `upgrade`, or assembled at run time, is invisible to the
    replay, and every rule below would then judge a schema that is not the one built. Delete
    this and a migration can bring the old shape back through `op.execute("CREATE POLICY ...")`
    with every test here green."""
    unread: list[str] = []
    checked = 0
    for path in migrations():
        module = _module(path)
        held = {
            (policy.table, policy.name)
            for history in (False, True)
            for _, statement in _strings(module, history=history)
            if statement.upper().startswith("CREATE POLICY")
            for policy in (parse(statement),)
        }
        named = {
            (table, name)
            for name, table in _NAMED_IN_SOURCE.findall(path.read_text(encoding="utf-8"))
        }
        checked += len(named)
        unread.extend(f"{path.name}: {one}" for one in sorted(named - held))
    assert unread == [], f"policies written where the replay cannot read them: {unread}"
    assert checked > 50, "the source scan found almost no policies, so it checked nothing"


def test_the_replay_ends_with_policies_on_every_soft_deleted_table() -> None:
    """The positive case for every rule below. Delete it and a replay that collects nothing
    satisfies all four, because a table with no policies breaks no rule about policies."""
    policies = replay()
    tables = soft_deleted_tables()

    assert {"auth.principal_identity", "gate.capability_grant", "know.chunk"} <= tables
    assert all(_on(policies, table) for table in tables), sorted(
        table for table in tables if not _on(policies, table)
    )


def test_no_read_policy_hides_the_row_its_own_retirement_writes() -> None:
    """The defect 0045 repaired. Delete this and the next soft-deleted table can be written
    `FOR ALL USING (deleted_at IS NULL) WITH CHECK (true)` again, or split into a read policy of
    `deleted_at IS NULL` alone, and nothing the application does can revoke a grant on it."""
    assert hidden_from_its_own_retirement(replay()) == []


def test_every_retirement_is_admitted_and_stamped_by_its_own_statement() -> None:
    """Delete this and an update policy can drop its WITH CHECK, which makes PostgreSQL check
    the new row against `USING (deleted_at IS NULL)` and refuse every retirement, or relax it to
    `true`, which lets a grant be recorded as revoked at whatever instant somebody writes."""
    assert not_stamped_by_its_statement(replay()) == []


def test_a_retired_row_cannot_be_updated_back() -> None:
    """Revocation is the deletion of a grant, and a deletion somebody can undo with an UPDATE is
    a grant that was suspended. Delete this and an update policy of `USING (true)` passes, which
    is what 0019 wrote for the fast-path rules."""
    assert brought_back(replay()) == []


def test_a_retired_row_is_unreadable_except_where_a_migration_argues_otherwise() -> None:
    """Delete this and a read policy of `USING (true)` passes on any table, so every revoked
    grant is back in every read that forgot its WHERE clause. The one exception is held to the
    table 0019 argues for and to the unconditional read it argues, so the exception cannot
    quietly widen."""
    exceptions = retirable_migration().RETIRED_ROWS_STAY_READABLE
    policies = replay()
    found = readable_once_retired(policies)

    assert set(exceptions) == {"gate.fast_path_rule"}
    assert "0019" in exceptions["gate.fast_path_rule"]
    assert [one for one in found if not one.startswith("gate.fast_path_rule:")] == []
    assert [one.using for one in _on(policies, "gate.fast_path_rule") if one.reads()] == ["true"]


def test_the_rules_find_the_defect_on_the_schema_before_it_was_repaired() -> None:
    """A rule asserted only against a schema that obeys it is satisfied by a rule that finds
    nothing. Replayed up to 0045, the first rule must name exactly the sixteen tables 0045 and
    0046 repaired, and the third the fast-path rules. Delete this and any of the rules above can
    stop firing with this file green."""
    before = replay(before="0045")
    hidden = {one.split(":")[0] for one in hidden_from_its_own_retirement(before)}

    # Tables built after the repair (0095's two, 0097's two) did not exist before 0045 and were
    # written with 0045's policies; they are read from each later migration's `TABLES`.
    assert {"auth.service_account", "auth.api_key"} <= built_after_the_repair()
    assert hidden == soft_deleted_tables() - {"gate.fast_path_rule"} - built_after_the_repair()
    assert len(hidden) == 16
    assert [one.split(":")[0] for one in brought_back(before)] == ["gate.fast_path_rule"]
    assert {one.split(":")[0] for one in hidden_from_its_own_retirement(replay("0046"))} == {
        "know.chunk"
    }


def test_both_repairs_stamp_a_retirement_the_same_way() -> None:
    """0046 restates 0045's constant rather than importing another migration. Delete this and the
    two can drift, and a chunk would then need a different stamp from every other table."""
    stamp = retirable_migration().RETIRED_BY_THIS_STATEMENT

    restated = _module(VERSIONS / "0046_retirable_chunks.py").RETIRED_BY_THIS_STATEMENT
    written = f"({LIVE} OR {stamp})"

    assert (restated, written) == (stamp, LIVE_OR_RETIRED_NOW)


def test_the_repairs_follow_the_migration_before_them() -> None:
    """A revision that does not chain is a migration Alembic never runs, and the symptom is the
    old policies in production while every test here passes."""
    assert (retirable_migration().revision, retirable_migration().down_revision) == ("0045", "0044")
    chunks = _module(VERSIONS / "0046_retirable_chunks.py")
    assert (chunks.revision, chunks.down_revision) == ("0046", "0045")


# ------------------------------------------------------------------------- the writers

#: The stamp a retirement may carry, as SQLAlchemy spells it and as SQL text spells it.
STAMPED_BY_ITS_STATEMENT: frozenset[str] = frozenset(
    {"func.statement_timestamp()", "statement_timestamp()"}
)

#: A SET list naming `deleted_at`, up to the WHERE clause. Case-sensitive, because SQL here is
#: written in capitals and prose that says "sets" is not a statement.
_SETS_DELETED_AT = re.compile(r"\bSET\b(?:(?!\bWHERE\b).)*?\bdeleted_at\s*=\s*([^,\s]+)", re.DOTALL)


def writes_of_deleted_at(source: str, name: str) -> list[tuple[str, str]]:
    """(`name:line`, the expression) for every `deleted_at` this source writes.

    Three shapes: `deleted_at` handed to a `.values(...)` call, as a keyword or a dictionary key;
    an assignment to an attribute called `deleted_at`, which is an ORM update; and a SQL string
    whose SET list names it. An insert with `deleted_at` in its values is named too, which is
    deliberate: a row created retired is a retirement no statement stamped.
    """
    found: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        where = f"{name}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr != "values":
                continue
            found.extend(
                (where, ast.unparse(one.value)) for one in node.keywords if one.arg == "deleted_at"
            )
            found.extend(
                (where, ast.unparse(value))
                for mapping in node.args
                if isinstance(mapping, ast.Dict)
                for key, value in zip(mapping.keys, mapping.values, strict=True)
                if isinstance(key, ast.Constant) and key.value == "deleted_at"
            )
        elif isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            found.extend(
                (where, ast.unparse(node.value))
                for target in targets
                if isinstance(target, ast.Attribute) and target.attr == "deleted_at"
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.extend((where, one.group(1)) for one in _SETS_DELETED_AT.finditer(node.value))
    # In line order, because `ast.walk` is breadth first and a report out of order is misread.
    return sorted(found, key=lambda one: int(one[0].rsplit(":", 1)[1]))


def application_writes_of_deleted_at() -> list[tuple[str, str]]:
    root = SOURCE.parents[1]
    return [
        found
        for path in sorted(SOURCE.rglob("*.py"))
        for found in writes_of_deleted_at(
            path.read_text(encoding="utf-8"), path.relative_to(root).as_posix()
        )
    ]


def not_stamped_by_their_statement(writes: list[tuple[str, str]]) -> list[str]:
    return [
        f"{where} writes deleted_at as {expression}"
        for where, expression in writes
        if expression not in STAMPED_BY_ITS_STATEMENT
    ]


def test_every_retirement_the_application_writes_is_stamped_by_its_own_statement() -> None:
    """The writer's half of `test_every_retirement_is_admitted_and_stamped_by_its_own_statement`.

    Delete this and a store can retire a row with `now()` or an instant it was handed, which reads
    correctly, passes every test that compiles the statement, and is refused by PostgreSQL as
    `brain_app` on the first removal anybody makes. `review_store.retire` did exactly that and was
    found by CI's database; `govern_routes.retire_grant` did it and was found by nothing."""
    assert not_stamped_by_their_statement(application_writes_of_deleted_at()) == []


def test_the_writer_scan_finds_the_retirements_the_application_makes() -> None:
    """The positive case. Delete this and a scan that walks nothing, or reads the wrong directory,
    satisfies the rule above, because no writes break no rule about writes."""
    modules = {where.split(":")[0] for where, _ in application_writes_of_deleted_at()}

    assert {
        "src/brain/gate/review_store.py",
        "src/brain/govern_routes.py",
        "src/brain/identity/sign_in_binding.py",
    } <= modules


def test_the_writer_scan_names_every_other_stamp_in_every_shape_it_reads() -> None:
    """A rule asserted only against code that obeys it is satisfied by a rule that finds nothing.
    Delete this and any of the three shapes can stop being read, with the two tests above green."""
    source = "\n".join(
        (
            "update(t).values(deleted_at=func.now())",
            "update(t).values({'deleted_at': at})",
            "row.deleted_at = datetime.now(UTC)",
            "SQL = 'UPDATE t SET updated_at = now(), deleted_at = %s WHERE id = %s'",
            "update(t).values(deleted_at=func.statement_timestamp())",
            "SQL = 'UPDATE t SET deleted_at = statement_timestamp() WHERE deleted_at IS NULL'",
            "update(t).where(t.deleted_at.is_(None)).values(reason='x')",
        )
    )

    assert not_stamped_by_their_statement(writes_of_deleted_at(source, "m")) == [
        "m:1 writes deleted_at as func.now()",
        "m:2 writes deleted_at as at",
        "m:3 writes deleted_at as datetime.now(UTC)",
        "m:4 writes deleted_at as %s",
    ]
