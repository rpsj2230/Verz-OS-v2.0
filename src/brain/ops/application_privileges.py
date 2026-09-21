"""Whether every table the application reads or writes is granted to the role it runs as.

`brain.session.make_application_sessions` runs every transaction as `brain_app`, so a table no
migration grants to that role is a table every route touching it fails on, with
`permission denied for table ...` and a 500. That is not a hypothetical: `0025` built
`ops.control_run` with three policies naming `brain_app` and no `GRANT` at all, the worker writes
it as the login and never noticed, and on 2026-09-17 four console screens on a staging install
(Live runs, Scheduled jobs, Errors and Quality) failed on it every time they opened. A policy
without a grant is a door with a lock and no hinge. Nothing compared the two halves, because each
half lives in a different place: the grant in a migration, the read in a route.

**So both halves are read from source, and compared.** The migrations are rendered by Alembic in
offline mode, which is the SQL `alembic upgrade --sql` would print, with no database anywhere:
every `GRANT`, `REVOKE`, `ALTER TABLE ... ROW LEVEL SECURITY`, `CREATE POLICY` and `DROP POLICY`
in the order they would run, including the ones a migration builds in a loop or an f-string. The
source is read with `ast`: every SQLAlchemy model and lightweight `table(...)` a module under
`src/brain` names, classified by the statement it sits in, and every SQL string handed to the
driver, classified by its verb. A use in a module the application's sessions can reach needs the
privilege on the table, directly or through a role `brain_app` is a member of, and, where row
level security is on, a policy for that command that names the role. See
`A_POLICY_WITHOUT_A_GRANT_IS_A_DOOR_WITH_NO_HINGE`.

Rejected: running the migrations against a real server and asking `has_table_privilege`. That is
the stronger evidence about the grants, and a scratch PostgreSQL proved the fix that way, but it
is evidence about the grant half only and it needs a server the invariant suite does not have.
The comparison is what fails CI, and a comparison needs the uses, which only the source has.

**What this cannot see, stated rather than implied.** See `WHAT_THE_SOURCE_DOES_NOT_SAY`. The
short version: a table named in a string built at run time, a row changed by assigning to a
loaded object's attribute, a SQL string that does not begin with its verb, and whether a policy's
`current_setting` was set to the right value before the statement ran. The last is checked only
as far as the module naming the setting at all.

**Reach is the import graph, which is wider than the truth, and the difference is written down.**
A module is read as running through the application's sessions when `brain.app`, or the module
whose job the worker hands `make_application_sessions`, imports it, however indirectly. Some of
those modules also run in the worker through a session over the login, which is not `brain_app`,
and a helper can be handed a session its caller already told who is present. Each such use is in
`USES_EXPLAINED` with the reason it is not a mismatch, and an entry that stops matching anything
fails the test beside the list, so the list cannot outlive what it excuses.

Task ids: M27.9.7
"""

from __future__ import annotations

import ast
import importlib
import io
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final

REPO: Final = Path(__file__).resolve().parents[3]
SRC: Final = REPO / "src" / "brain"

#: The role every transaction on the application's sessions runs as. `brain.session` holds the
#: statement; this is the name the migrations grant to.
APPLICATION_ROLE: Final = "brain_app"

#: The roles a grant or a policy can name that also reach `APPLICATION_ROLE`.
PUBLIC_ROLE: Final = "public"

#: Where the analysis starts: what serves requests, and what a job running as the application
#: role is handed sessions by. `brain.knowledge.chunk_store.run_embed_job` is given
#: `make_application_sessions` by the worker, so its imports are the application's too.
APPLICATION_ROOTS: Final[tuple[str, ...]] = ("brain.app", "brain.knowledge.chunk_store")

#: The privileges a statement can need on a table. TRUNCATE and REFERENCES are not used here.
PRIVILEGES: Final[tuple[str, ...]] = ("SELECT", "INSERT", "UPDATE", "DELETE")

# ------------------------------------------------------------------ written-down reasons
#: Why a policy is not enough, and why this module exists.
A_POLICY_WITHOUT_A_GRANT_IS_A_DOOR_WITH_NO_HINGE: Final = (
    "PostgreSQL asks two questions of every statement and both must say yes. The grant decides "
    "whether the role may use the table at all; row-level security then decides which rows. A "
    "policy naming brain_app on a table brain_app holds no privilege on admits nothing, and the "
    "statement fails with permission denied before any policy is consulted. ops.control_run "
    "shipped exactly that way and four console screens failed on it. The two halves are "
    "written in different files by different changes, so they are compared here from source."
)

#: What this analysis cannot see, so a green run is read as what it is.
WHAT_THE_SOURCE_DOES_NOT_SAY: Final = (
    "A table named in a string assembled at run time, or reached through a variable holding a "
    "model class, is not seen. A row changed by assigning to an attribute of a loaded object and "
    "flushing is not seen as an UPDATE, and a row removed with session.delete is not seen as a "
    "DELETE. A SQL string is read only when it begins with its verb or is handed straight to "
    "text() or a driver's execute. A policy whose predicate reads current_setting is satisfied "
    "here when the using module names that setting, which says nothing about the value it was "
    "set to. Reach is the import graph from the application's roots, so a module imported only "
    "for a constant is read as running on the application's sessions; the uses that really run "
    "through the login, or on a session a caller prepared, are listed in USES_EXPLAINED."
)

#: Uses the comparison reports and that are not mismatches, keyed by module, table and privilege,
#: each with the reason in words. Read by `unexplained` and held against the comparison by
#: `tests/invariants/test_application_privileges.py`, which fails on an entry nothing matches.
_RECORDED_BY_THE_WORKER: Final = (
    "record_start and record_finish are called by brain.ops.worker.start_owed and nothing else, "
    "on sessions from make_session_factory over the owner's login (Settings.owner_database_url, "
    "and the worker refuses to start on brain_app) and never make_application_sessions: "
    "a control's run is written by the worker as the database owner and only read by the console, "
    "which is why 0069 grants SELECT and not the writes 0025's policies describe"
)
_SET_BY_THE_CALLER: Final = (
    "put_item has one caller, brain.knowledge.chunk_store.write_document, which runs "
    "brain.knowledge.search.session_settings for the owner's reach in the same transaction before "
    "it, so the upsert reads and writes the item as its owner"
)
USES_EXPLAINED: Final[Mapping[tuple[str, str, str], str]] = MappingProxyType(
    {
        ("brain.ops.schedule_store", "ops.control_run", "INSERT"): _RECORDED_BY_THE_WORKER,
        ("brain.ops.schedule_store", "ops.control_run", "UPDATE"): _RECORDED_BY_THE_WORKER,
        ("brain.ops.erasure_store", "ops.erasure_request", "UPDATE"): (
            "drain_erasure_queue runs on the psycopg connection brain.ops.schedule_runner opens as "
            "the database owner, and refuses a connection row-level security narrows, because a "
            "row a policy hides is a row the erasure would silently leave behind"
        ),
        ("brain.knowledge.item_store", "know.item", "SELECT"): _SET_BY_THE_CALLER,
        ("brain.knowledge.item_store", "know.item", "UPDATE"): _SET_BY_THE_CALLER,
    }
)


# ------------------------------------------------------------------------- the catalogue
@dataclass(frozen=True)
class Policy:
    """One `CREATE POLICY`, as far as the comparison needs it."""

    name: str
    table: str
    command: str
    roles: tuple[str, ...]
    permissive: bool
    #: The `USING` expression, or empty when the policy has none.
    using: str
    #: The `WITH CHECK` expression, or empty when the policy has none.
    check: str

    def reads_rows_with(self, command: str) -> str:
        """The expressions PostgreSQL applies for `command`: `USING` for rows read, the check for
        rows written, and `USING` standing in for a check a policy does not state."""
        if command == "INSERT":
            return self.check or self.using
        if command == "UPDATE":
            return f"{self.using} {self.check or self.using}"
        return self.using


@dataclass(frozen=True)
class Catalogue:
    """What the migrations leave behind about tables, grants and row-level security."""

    tables: frozenset[str]
    privileges: Mapping[tuple[str, str], frozenset[str]]
    columns: Mapping[tuple[str, str, str], frozenset[str]]
    memberships: Mapping[str, frozenset[str]]
    row_security: frozenset[str]
    policies: Mapping[str, tuple[Policy, ...]]
    #: Per table, the functions its triggers run and the events each fires on. Only functions
    #: that run as the caller are kept: a `SECURITY DEFINER` body runs as its owner.
    triggers: Mapping[str, tuple[tuple[frozenset[str], str], ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    #: The body of every function that runs as its caller, by qualified name.
    bodies: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def fired_by(self, table: str, privilege: str) -> tuple[str, ...]:
        """The bodies of the invoker triggers a write of this kind to this table runs."""
        return tuple(
            self.bodies[function]
            for events, function in self.triggers.get(table, ())
            if privilege in events and function in self.bodies
        )

    def roles_of(self, role: str) -> frozenset[str]:
        """The role, every role it is a member of however indirectly, and PUBLIC."""
        found = {role, PUBLIC_ROLE}
        pending = [role]
        while pending:
            for parent in self.memberships.get(pending.pop(), frozenset()):
                if parent not in found:
                    found.add(parent)
                    pending.append(parent)
        return frozenset(found)

    def holds(self, role: str, table: str, privilege: str) -> bool:
        """Whether `role` may use `privilege` on `table` at all, on the table or on a column.

        A column grant counts, because PostgreSQL admits a statement touching only the granted
        columns, and whether the statement touches only those is `columns_held`'s question.
        """
        for one in self.roles_of(role):
            if privilege in self.privileges.get((one, table), frozenset()):
                return True
            if self.columns.get((one, table, privilege)):
                return True
        return False

    def columns_held(self, role: str, table: str, privilege: str) -> frozenset[str] | None:
        """The columns a column grant admits, or None when the privilege is held on the table."""
        held: set[str] = set()
        for one in self.roles_of(role):
            if privilege in self.privileges.get((one, table), frozenset()):
                return None
            held |= self.columns.get((one, table, privilege), frozenset())
        return frozenset(held)

    def admits(self, role: str, table: str, command: str) -> bool:
        """Whether row-level security lets `role` run `command` against `table` at all.

        True when security is off. Otherwise a permissive policy for the command, or for ALL,
        naming the role or one it inherits: with none, PostgreSQL applies default deny and the
        statement sees no rows or refuses every new one.
        """
        if table not in self.row_security:
            return True
        roles = self.roles_of(role)
        return any(
            one.permissive
            and one.command in {command, "ALL"}
            and any(named in roles for named in one.roles)
            for one in self.policies.get(table, ())
        )

    def settings_needed(self, role: str, table: str, command: str) -> frozenset[str]:
        """The `app.*` settings every admitting policy for this command reads.

        Empty when some policy admits without reading one, because then the statement can run
        without the setting having been made.
        """
        roles = self.roles_of(role)
        admitting = [
            one
            for one in self.policies.get(table, ())
            if one.permissive
            and one.command in {command, "ALL"}
            and any(named in roles for named in one.roles)
        ]
        if not admitting or table not in self.row_security:
            return frozenset()
        read = [frozenset(SETTING.findall(one.reads_rows_with(command))) for one in admitting]
        if any(not names for names in read):
            return frozenset()
        return frozenset.intersection(*read)


#: A setting a policy predicate reads.
SETTING: Final = re.compile(r"current_setting\(\s*'(app\.[a-z_]+)'")

_QUALIFIED = r"([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)"
_GRANT_ON_TABLE: Final = re.compile(
    rf"^GRANT (?P<privs>.+?) ON (?:TABLE )?(?P<tables>{_QUALIFIED}(?:\s*,\s*{_QUALIFIED})*)"
    r" TO (?P<roles>.+)$",
    re.IGNORECASE,
)
_REVOKE_ON_TABLE: Final = re.compile(
    rf"^REVOKE (?P<privs>.+?) ON (?:TABLE )?(?P<tables>{_QUALIFIED}(?:\s*,\s*{_QUALIFIED})*)"
    r" FROM (?P<roles>.+)$",
    re.IGNORECASE,
)
_GRANT_ROLE: Final = re.compile(r"^GRANT (?P<granted>[a-z_]+) TO (?P<member>[a-z_]+)$", re.I)
_REVOKE_ROLE: Final = re.compile(r"^REVOKE (?P<granted>[a-z_]+) FROM (?P<member>[a-z_]+)$", re.I)
_ROW_SECURITY: Final = re.compile(
    rf"^ALTER TABLE (?:IF EXISTS )?(?:ONLY )?{_QUALIFIED} (ENABLE|DISABLE) ROW LEVEL SECURITY$",
    re.IGNORECASE,
)
_CREATE_POLICY: Final = re.compile(
    rf"^CREATE POLICY (?P<name>[a-z_0-9]+) ON {_QUALIFIED}(?P<rest>.*)$", re.IGNORECASE
)
_DROP_POLICY: Final = re.compile(
    rf"^DROP POLICY (?:IF EXISTS )?(?P<name>[a-z_0-9]+) ON {_QUALIFIED}", re.IGNORECASE
)
_CREATE_RELATION: Final = re.compile(
    rf"^CREATE (?:OR REPLACE )?(?:UNLOGGED )?(?:MATERIALIZED )?(?:TABLE|VIEW)"
    rf" (?:IF NOT EXISTS )?{_QUALIFIED}",
    re.IGNORECASE,
)
_DROP_RELATION: Final = re.compile(
    rf"^DROP (?:MATERIALIZED )?(?:TABLE|VIEW) (?:IF EXISTS )?{_QUALIFIED}", re.IGNORECASE
)
_POLICY_FOR: Final = re.compile(r"\bFOR (ALL|SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)
_POLICY_AS: Final = re.compile(r"^\s*AS (PERMISSIVE|RESTRICTIVE)\b", re.IGNORECASE)
_POLICY_TO: Final = re.compile(
    r"\bTO ([a-z_]+(?:\s*,\s*[a-z_]+)*)(?=\s+(?:USING|WITH)\b|\s*$)", re.IGNORECASE
)
_CREATE_FUNCTION: Final = re.compile(
    rf"^CREATE (?:OR REPLACE )?FUNCTION {_QUALIFIED}\s*\(", re.IGNORECASE
)
_SECURITY_DEFINER: Final = re.compile(r"\bSECURITY\s+DEFINER\b", re.IGNORECASE)
_CREATE_TRIGGER: Final = re.compile(
    r"^CREATE (?:OR REPLACE )?(?:CONSTRAINT )?TRIGGER \w+ (?:BEFORE|AFTER|INSTEAD OF) "
    rf"(?P<events>.+?) ON (?P<table>{_QUALIFIED[1:-1]}) .*?EXECUTE (?:FUNCTION|PROCEDURE) "
    rf"(?P<function>{_QUALIFIED[1:-1]})\s*\(",
    re.IGNORECASE,
)
_COLUMN_PRIVILEGE: Final = re.compile(r"^(SELECT|INSERT|UPDATE|REFERENCES)\s*\((.*)\)$", re.I)


def statements(sql: str) -> tuple[str, ...]:
    """The statements in a script, split on semicolons outside quotes, comments and bodies.

    Written by hand because a function body is dollar-quoted and holds semicolons of its own,
    and splitting on the character would cut every trigger in the schema into pieces.
    """
    found: list[str] = []
    current: list[str] = []
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        end = index + 1
        if char == "'":
            closing = sql.find("'", index + 1)
            end = length if closing < 0 else closing + 1
        elif sql.startswith("--", index):
            # A comment is dropped rather than kept, so an apostrophe in one cannot open a string.
            closing = sql.find("\n", index)
            index = length if closing < 0 else closing
            continue
        elif char == "$" and (tag := re.match(r"\$[A-Za-z_]*\$", sql[index:])):
            closing = sql.find(tag.group(0), index + len(tag.group(0)))
            end = length if closing < 0 else closing + len(tag.group(0))
        elif char == ";":
            found.append("".join(current))
            current = []
            index += 1
            continue
        current.append(sql[index:end])
        index = end
    found.append("".join(current))
    return tuple(one for one in (" ".join(part.split()) for part in found) if one)


def _split_list(text: str) -> list[str]:
    """A comma separated list, ignoring commas inside parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    parts.append("".join(current).strip())
    return [one for one in parts if one]


def _roles(text: str) -> list[str]:
    return [one.strip().lower() for one in text.split(",") if one.strip()]


def _clause(rest: str, keyword: str) -> str:
    """The parenthesised expression after `USING` or `WITH CHECK` in a policy, or empty."""
    match = re.search(rf"\b{keyword}\s*\(", rest, re.IGNORECASE)
    if match is None:
        return ""
    depth = 0
    for index in range(match.end() - 1, len(rest)):
        if rest[index] == "(":
            depth += 1
        elif rest[index] == ")":
            depth -= 1
            if depth == 0:
                return rest[match.end() : index]
    return rest[match.end() :]


def catalogue_of(sql: str) -> Catalogue:
    """Read a rendered migration script, statement by statement, in the order it runs."""
    tables: set[str] = set()
    privileges: dict[tuple[str, str], set[str]] = defaultdict(set)
    columns: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    memberships: dict[str, set[str]] = defaultdict(set)
    row_security: set[str] = set()
    policies: dict[str, list[Policy]] = defaultdict(list)
    triggers: dict[str, list[tuple[frozenset[str], str]]] = defaultdict(list)
    bodies: dict[str, str] = {}

    def each_grant(match: re.Match[str]) -> Iterator[tuple[str, str, str, frozenset[str]]]:
        named = [one.strip().lower() for one in match.group("tables").split(",")]
        for role in _roles(match.group("roles")):
            for table in named:
                for raw in _split_list(match.group("privs")):
                    column = _COLUMN_PRIVILEGE.match(raw)
                    if column:
                        cols = frozenset(one.strip().lower() for one in column.group(2).split(","))
                        yield role, table, column.group(1).upper(), cols
                    elif raw.upper() in {"ALL", "ALL PRIVILEGES"}:
                        for privilege in PRIVILEGES:
                            yield role, table, privilege, frozenset()
                    else:
                        yield role, table, raw.upper(), frozenset()

    for statement in statements(sql):
        if match := _CREATE_RELATION.match(statement):
            tables.add(match.group(1).lower())
        elif match := _DROP_RELATION.match(statement):
            dropped = match.group(1).lower()
            tables.discard(dropped)
            row_security.discard(dropped)
            policies.pop(dropped, None)
            for key in [key for key in privileges if key[1] == dropped]:
                del privileges[key]
            for ckey in [ckey for ckey in columns if ckey[1] == dropped]:
                del columns[ckey]
        elif match := _GRANT_ON_TABLE.match(statement):
            for role, table, privilege, cols in each_grant(match):
                if cols:
                    columns[(role, table, privilege)] |= cols
                else:
                    privileges[(role, table)].add(privilege)
        elif match := _REVOKE_ON_TABLE.match(statement):
            for role, table, privilege, cols in each_grant(match):
                if cols:
                    columns[(role, table, privilege)] -= cols
                else:
                    privileges[(role, table)].discard(privilege)
                    columns.pop((role, table, privilege), None)
        elif match := _GRANT_ROLE.match(statement):
            memberships[match.group("member").lower()].add(match.group("granted").lower())
        elif match := _REVOKE_ROLE.match(statement):
            memberships[match.group("member").lower()].discard(match.group("granted").lower())
        elif match := _ROW_SECURITY.match(statement):
            if match.group(2).upper() == "ENABLE":
                row_security.add(match.group(1).lower())
            else:
                row_security.discard(match.group(1).lower())
        elif match := _CREATE_POLICY.match(statement):
            rest = match.group("rest")
            command = _POLICY_FOR.search(rest)
            kind = _POLICY_AS.match(rest)
            to = _POLICY_TO.search(rest.split(" USING ")[0].split(" WITH CHECK ")[0])
            policies[match.group(2).lower()].append(
                Policy(
                    name=match.group("name").lower(),
                    table=match.group(2).lower(),
                    command=command.group(1).upper() if command else "ALL",
                    roles=tuple(_roles(to.group(1))) if to else (PUBLIC_ROLE,),
                    permissive=not (kind and kind.group(1).upper() == "RESTRICTIVE"),
                    using=_clause(rest, "USING"),
                    check=_clause(rest, "WITH CHECK"),
                )
            )
        elif match := _CREATE_FUNCTION.match(statement):
            name = match.group(1).lower()
            body = re.search(r"\$([A-Za-z_]*)\$(.*)\$\1\$", statement, re.DOTALL)
            if body is not None and not _SECURITY_DEFINER.search(statement):
                bodies[name] = body.group(2)
            else:
                # Replaced by a definer, or by a body this cannot read: it no longer runs as the
                # caller, so what it reads is not the caller's to hold.
                bodies.pop(name, None)
        elif match := _CREATE_TRIGGER.match(statement):
            events = frozenset(
                one.upper()
                for one in re.findall(r"INSERT|UPDATE|DELETE", match.group("events"), re.I)
            )
            triggers[match.group("table").lower()].append((events, match.group("function").lower()))
        elif match := _DROP_POLICY.match(statement):
            table = match.group(2).lower()
            name = match.group("name").lower()
            kept = [one for one in policies.get(table, []) if one.name != name]
            # A policy of the same name is dropped once per drop: the last created goes first,
            # which is the one a migration that re-creates it under the same name means.
            removed = [one for one in policies.get(table, []) if one.name == name]
            policies[table] = kept + removed[:-1]

    return Catalogue(
        tables=frozenset(tables),
        privileges=MappingProxyType({key: frozenset(value) for key, value in privileges.items()}),
        columns=MappingProxyType({key: frozenset(value) for key, value in columns.items()}),
        memberships=MappingProxyType({k: frozenset(v) for k, v in memberships.items()}),
        row_security=frozenset(row_security),
        policies=MappingProxyType({key: tuple(value) for key, value in policies.items()}),
        triggers=MappingProxyType({key: tuple(value) for key, value in triggers.items()}),
        bodies=MappingProxyType(dict(bodies)),
    )


def rendered_migrations(repo: Path = REPO, revision: str = "head") -> str:
    """Every migration's upgrade up to `revision`, rendered as the SQL Alembic would run.

    Offline mode is Alembic's own renderer, so a grant a migration builds in a loop or through an
    f-string arrives here exactly as it would reach PostgreSQL, and no database is needed. The
    address is a placeholder that is never connected to; `migrations/env.py` insists on having one.
    No `alembic.ini` is read, because reading it would reconfigure logging for the process running
    the test.
    """
    from alembic import command
    from alembic.config import Config

    buffer = io.StringIO()
    config = Config(output_buffer=buffer)
    config.set_main_option("script_location", str(repo / "migrations"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://offline@localhost/offline")
    command.upgrade(config, revision, sql=True)
    return buffer.getvalue()


@cache
def migrations_catalogue(repo: Path = REPO, revision: str = "head") -> Catalogue:
    """The catalogue the migrations in `repo` build up to `revision`, rendered once per process."""
    return catalogue_of(rendered_migrations(repo, revision))


# ------------------------------------------------------------------------------ the uses
@dataclass(frozen=True)
class Use:
    """One place a module reads or writes a table, and the privilege that needs."""

    module: str
    line: int
    table: str
    privilege: str
    #: For an UPDATE whose columns are known from `.values(...)`, those columns.
    columns: frozenset[str] = field(default_factory=frozenset)


_SQL_VERB: Final = re.compile(r"^\s*\(?\s*(SELECT|INSERT|UPDATE|DELETE|MERGE|WITH|LOCK)\b", re.I)
_SQL_FROM: Final = re.compile(rf"\b(?:FROM|JOIN)\s+(?:ONLY\s+)?{_QUALIFIED}", re.IGNORECASE)
_SQL_INSERT: Final = re.compile(rf"\bINSERT\s+INTO\s+{_QUALIFIED}", re.IGNORECASE)
_SQL_UPDATE: Final = re.compile(
    rf"\bUPDATE\s+(?:ONLY\s+)?{_QUALIFIED}\s+(?:AS\s+\w+\s+)?SET\b", re.I
)
_SQL_DELETE: Final = re.compile(rf"\bDELETE\s+FROM\s+(?:ONLY\s+)?{_QUALIFIED}", re.IGNORECASE)
_SQL_MERGE: Final = re.compile(rf"\bMERGE\s+INTO\s+(?:ONLY\s+)?{_QUALIFIED}", re.IGNORECASE)
_SQL_LOCK: Final = re.compile(rf"\bLOCK\s+TABLE\s+(?:ONLY\s+)?{_QUALIFIED}", re.IGNORECASE)
_SQL_CONFLICT_UPDATE: Final = re.compile(r"\bON\s+CONFLICT\b[^;]*?\bDO\s+UPDATE\b", re.I)
_SQL_READS_TARGET: Final = re.compile(r"\b(WHERE|RETURNING|FROM)\b", re.IGNORECASE)
_SQL_FOR_UPDATE: Final = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?(?:UPDATE|SHARE|KEY\s+SHARE)\b", re.I)


def sql_uses(sql: str, known: frozenset[str]) -> list[tuple[str, str]]:
    """Every `(table, privilege)` a SQL string needs, for tables in `known`.

    The verb decides the privilege on its target, and every other table the text names in a FROM
    or a JOIN is read. An UPDATE or DELETE that filters or returns reads its own target too, and
    PostgreSQL asks for SELECT on it; an upsert asks for UPDATE; a row lock asks for UPDATE.
    """
    found: list[tuple[str, str]] = []
    targets: set[str] = set()
    for pattern, privilege in (
        (_SQL_INSERT, "INSERT"),
        (_SQL_UPDATE, "UPDATE"),
        (_SQL_DELETE, "DELETE"),
        (_SQL_LOCK, "UPDATE"),
    ):
        for match in pattern.finditer(sql):
            table = match.group(1).lower()
            if table not in known:
                continue
            targets.add(table)
            found.append((table, privilege))
            tail = sql[match.end() :]
            if privilege == "INSERT" and _SQL_CONFLICT_UPDATE.search(tail):
                found.append((table, "UPDATE"))
            if privilege in {"UPDATE", "DELETE"} and _SQL_READS_TARGET.search(tail):
                found.append((table, "SELECT"))
            if privilege == "INSERT" and re.search(r"\bRETURNING\b", tail, re.I):
                found.append((table, "SELECT"))
    for match in _SQL_MERGE.finditer(sql):
        # `MERGE` reads its target to match, and needs each action it can take. The actions are
        # the clauses up to the statement's end, which inside a function body is its semicolon.
        table = match.group(1).lower()
        if table not in known:
            continue
        clauses = sql[match.end() :].split(";", 1)[0]
        targets.add(table)
        found.append((table, "SELECT"))
        for action in ("INSERT", "UPDATE", "DELETE"):
            if re.search(rf"\bTHEN\s+{action}\b", clauses, re.IGNORECASE):
                found.append((table, action))
    for match in _SQL_FROM.finditer(sql):
        table = match.group(1).lower()
        if table not in known:
            continue
        # The FROM of a DELETE is its target, already counted.
        if sql[: match.start()].rstrip().upper().endswith("DELETE") and table in targets:
            continue
        found.append((table, "SELECT"))
        if _SQL_FOR_UPDATE.search(sql):
            found.append((table, "UPDATE"))
    return found


@cache
def orm_tables(src: Path = SRC) -> Mapping[str, str]:
    """Every mapped class, by `module.Class`, and every Core table, by `module.NAME`, to its table.

    The mapped classes are read off the registry, which is what SQLAlchemy itself resolves. A Core
    `Table` has no class to be registered under, so the module-level assignment that builds one is
    read from source instead: `brain.knowledge.search.CHUNK` is `know.chunk` and is not a model.
    """
    from brain.db import Base

    # Imported for what importing it does, which is register every model on `Base`. By name
    # rather than `import brain.tables`, which binds `brain` here and invites a `del` that would
    # remove the attribute from the package for every later importer.
    importlib.import_module("brain.tables")
    found = {
        # `local_table` is typed as any selectable; a declarative model's is always its `Table`.
        f"{mapper.class_.__module__}.{mapper.class_.__name__}": str(
            getattr(mapper.local_table, "fullname", mapper.local_table)
        )
        for mapper in Base.registry.mappers
    }
    for path in _python_files(src):
        module = module_name(path, src)
        for node in _parsed(path).body:
            value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
            target = (
                node.targets[0]
                if isinstance(node, ast.Assign) and len(node.targets) == 1
                else node.target
                if isinstance(node, ast.AnnAssign)
                else None
            )
            if not (isinstance(value, ast.Call) and _call_name(value) == "Table" and value.args):
                continue
            name = _string_of(value.args[0])
            schema = next(
                (_string_of(one.value) for one in value.keywords if one.arg == "schema"), None
            )
            if isinstance(target, ast.Name) and name and schema:
                found[f"{module}.{target.id}"] = f"{schema}.{name}"
    return MappingProxyType(found)


def module_name(path: Path, src: Path = SRC) -> str:
    """`src/brain/ops/x.py` as `brain.ops.x`, and a package's `__init__` as the package."""
    relative = path.relative_to(src.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _python_files(src: Path) -> Iterator[Path]:
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


@cache
def _parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_bytes().decode("utf-8"))


def _resolve_from(module: str, node: ast.ImportFrom, is_package: bool) -> str:
    """The absolute module an `ImportFrom` names, relative imports included."""
    if not node.level:
        return node.module or ""
    base = module.split(".")
    base = base if is_package else base[:-1]
    if node.level > 1:
        base = base[: len(base) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _aliases(tree: ast.Module, module: str, is_package: bool) -> dict[str, str]:
    """Every name a module binds by import, to the dotted name it stands for, at any depth."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for one in node.names:
                if one.asname:
                    names[one.asname] = one.name
                else:
                    names[one.name.split(".")[0]] = one.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            source = _resolve_from(module, node, is_package)
            for one in node.names:
                names[one.asname or one.name] = f"{source}.{one.name}"
    return names


def _dotted(node: ast.expr, aliases: Mapping[str, str]) -> str | None:
    """`a.b.c` for a name or an attribute chain, with the first part resolved through imports."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    head = aliases.get(current.id, current.id)
    return ".".join([head, *reversed(parts)])


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _chain_root(call: ast.Call) -> ast.Call:
    """The first call of a method chain: `update(X)` in `update(X).where(...).values(...)`."""
    current = call
    while isinstance(current.func, ast.Attribute) and isinstance(current.func.value, ast.Call):
        current = current.func.value
    return current


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


_STATEMENTS: Final = {
    "select": "SELECT",
    "insert": "INSERT",
    "update": "UPDATE",
    "delete": "DELETE",
}
_READ_CALLS: Final = frozenset({"select", "exists", "union", "union_all", "get", "scalar_subquery"})


def _docstring_nodes(tree: ast.Module) -> set[ast.AST]:
    found: set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant | ast.JoinedStr):
            found.add(node.value)
    return found


def _string_of(node: ast.expr) -> str | None:
    """A string constant, an f-string with its holes blanked, or a `+` of those."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            one.value if isinstance(one, ast.Constant) and isinstance(one.value, str) else " _ "
            for one in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _string_of(node.left), _string_of(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _orm_privileges(
    reference: ast.expr, parents: Mapping[ast.AST, ast.AST]
) -> list[tuple[str, frozenset[str]]]:
    """The privileges one reference to a model needs, from the statement it sits in."""
    node: ast.AST = reference
    parent = parents.get(node)
    # The model itself called is a row about to be added. `X.col.desc()` is a column's method.
    if isinstance(parent, ast.Call) and parent.func is node:
        return [("INSERT", frozenset())]
    # `X.col`, `X.col.desc()` and `X.__table__` are the model too; climb out of the chain.
    while isinstance(parent, ast.Attribute) or (
        isinstance(parent, ast.Call) and parent.func is node
    ):
        node = parent
        parent = parents.get(node)
    while parent is not None:
        if isinstance(parent, ast.Call) and node is not parent.func:
            name = _call_name(parent)
            root = _chain_root(parent)
            verb = _STATEMENTS.get(_call_name(root), "")
            if parent is root and name in {"insert", "update", "delete"}:
                if parent.args and parent.args[0] is node:
                    return [(_STATEMENTS[name], frozenset())]
                return [("SELECT", frozenset())]
            if name in _READ_CALLS and parent is root:
                return [("SELECT", frozenset())]
            if verb:
                found: list[tuple[str, frozenset[str]]] = [("SELECT", frozenset())]
                chain = [parent]
                probe: ast.AST = parent
                while isinstance(parents.get(probe), ast.Attribute):
                    outer = parents.get(parents[probe])
                    if not isinstance(outer, ast.Call):
                        break
                    chain.append(outer)
                    probe = outer
                if any(_locks(one, reference) for one in chain):
                    found.append(("UPDATE", frozenset()))
                return found
            return [("SELECT", frozenset())]
        node = parent
        parent = parents.get(node)
    return []


def _locks(call: ast.Call, reference: ast.expr) -> bool:
    """Whether a `with_for_update` locks the model `reference` names.

    Every table in the statement when `of` is absent, and only the named ones when it is present,
    which is PostgreSQL's rule for `FOR UPDATE OF` and the privilege it asks for.
    """
    if _call_name(call) != "with_for_update":
        return False
    of = next((one.value for one in call.keywords if one.arg == "of"), None)
    if of is None:
        return True
    named = of.elts if isinstance(of, ast.Tuple | ast.List) else [of]
    return any(ast.dump(one) == ast.dump(reference) for one in named)


def _statement_privileges(root: ast.Call, parents: Mapping[ast.AST, ast.AST]) -> list[str]:
    """What a whole chain adds beyond its target: an upsert updates, a lock updates."""
    added: list[str] = []
    probe: ast.AST = root
    while isinstance(parents.get(probe), ast.Attribute):
        outer = parents.get(parents[probe])
        if not isinstance(outer, ast.Call):
            break
        name = _call_name(outer)
        if name == "on_conflict_do_update":
            added.append("UPDATE")
        if name in {"returning", "where", "filter", "filter_by"} and _call_name(root) != "select":
            added.append("SELECT")
        if name == "with_for_update":
            added.append("UPDATE")
        probe = outer
    return added


def _values_columns(root: ast.Call, parents: Mapping[ast.AST, ast.AST]) -> frozenset[str]:
    names: set[str] = set()
    probe: ast.AST = root
    while isinstance(parents.get(probe), ast.Attribute):
        outer = parents.get(parents[probe])
        if not isinstance(outer, ast.Call):
            break
        if _call_name(outer) == "values":
            names.update(one.arg for one in outer.keywords if one.arg)
        probe = outer
    return frozenset(names)


def uses_in(path: Path, known: frozenset[str], src: Path = SRC) -> list[Use]:
    """Every table use one module's source states."""
    module = module_name(path, src)
    tree = _parsed(path)
    aliases = _aliases(tree, module, path.name == "__init__.py")
    parents = _parents(tree)
    models = orm_tables(src)
    # A model or a Core table defined in this module is named here without its module.
    local_models = {
        name.removeprefix(f"{module}."): table
        for name, table in models.items()
        if name.startswith(f"{module}.") and "." not in name.removeprefix(f"{module}.")
    }
    docstrings = _docstring_nodes(tree)
    found: list[Use] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Attribute) and not isinstance(
            parents.get(node), ast.Attribute
        ):
            # The model is the whole chain, or the head of one: `X`, `tables.X`, `X.col.desc`.
            head: ast.expr = node
            table = None
            while True:
                dotted = _dotted(head, aliases)
                if dotted is not None:
                    table = models.get(dotted) or local_models.get(dotted)
                if table is not None or not isinstance(head, ast.Attribute):
                    break
                head = head.value
            if table is None or _in_annotation(node, parents):
                continue
            for privilege, columns in _orm_privileges(head, parents):
                found.append(Use(module, node.lineno, table, privilege, columns))
            root = _enclosing_root(node, parents)
            if root is not None and root.args and _refers(root.args[0], table, aliases, models):
                for privilege in _statement_privileges(root, parents):
                    found.append(Use(module, node.lineno, table, privilege))
                if _call_name(root) == "update":
                    columns = _values_columns(root, parents)
                    if columns:
                        found.append(Use(module, node.lineno, table, "UPDATE", columns))
        elif isinstance(node, ast.Call) and _call_name(node) == "on_conflict_do_update":
            # An upsert built in two steps: `statement = insert(X)...` and then
            # `statement.on_conflict_do_update(...)`. The chain alone does not reach `insert(X)`.
            target = _upserted(node, parents, aliases, {**models, **local_models})
            if target is not None:
                found.append(Use(module, node.lineno, target, "UPDATE"))
                found.append(Use(module, node.lineno, target, "SELECT"))
        elif isinstance(node, ast.Call) and _call_name(node) == "table" and node.args:
            name = _string_of(node.args[0])
            schema = next(
                (_string_of(one.value) for one in node.keywords if one.arg == "schema"), None
            )
            if name and schema and f"{schema}.{name}" in known:
                for privilege, columns in _orm_privileges(node, parents):
                    found.append(Use(module, node.lineno, f"{schema}.{name}", privilege, columns))
        elif isinstance(node, ast.Constant | ast.JoinedStr | ast.BinOp):
            if node in docstrings or isinstance(parents.get(node), ast.BinOp | ast.JoinedStr):
                continue
            text = _string_of(node)
            if text is None or not _is_sql(node, text, parents):
                continue
            for table, privilege in sql_uses(text, known):
                found.append(Use(module, node.lineno, table, privilege))
    return found


def _upserted(
    call: ast.Call,
    parents: Mapping[ast.AST, ast.AST],
    aliases: Mapping[str, str],
    models: Mapping[str, str],
) -> str | None:
    """The table an `on_conflict_do_update` updates, following one variable back if it must."""
    root = _chain_root(call)
    if _call_name(root) == "insert" and root.args:
        return _model_table(root.args[0], aliases, models)
    func = root.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
        return None
    variable = func.value.id
    scope: ast.AST | None = parents.get(call)
    while scope is not None and not isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
        scope = parents.get(scope)
    if scope is None:
        return None
    for node in ast.walk(scope):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(one, ast.Name) and one.id == variable for one in node.targets)
            and isinstance(node.value, ast.Call)
        ):
            assigned = _chain_root(node.value)
            if _call_name(assigned) == "insert" and assigned.args:
                return _model_table(assigned.args[0], aliases, models)
    return None


def _model_table(
    expression: ast.expr, aliases: Mapping[str, str], models: Mapping[str, str]
) -> str | None:
    head = expression
    while True:
        name = _dotted(head, aliases)
        if name is not None and name in models:
            return models[name]
        if not isinstance(head, ast.Attribute):
            return None
        head = head.value


def _is_sql(node: ast.expr, text: str, parents: Mapping[ast.AST, ast.AST]) -> bool:
    """A string that begins with its verb, or one handed straight to `text` or an execute."""
    if _SQL_VERB.match(text):
        return True
    parent = parents.get(node)
    return isinstance(parent, ast.Call) and _call_name(parent) in {
        "text",
        "execute",
        "exec_driver_sql",
    }


def _in_annotation(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> bool:
    child: ast.AST = node
    parent = parents.get(child)
    while parent is not None:
        if isinstance(parent, ast.arg) and parent.annotation is child:
            return True
        if isinstance(parent, ast.AnnAssign) and parent.annotation is child:
            return True
        if isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef) and parent.returns is child:
            return True
        if isinstance(parent, ast.Subscript) and isinstance(parents.get(parent), ast.arg):
            return True
        if isinstance(parent, ast.stmt):
            return False
        child, parent = parent, parents.get(parent)
    return False


def _enclosing_root(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> ast.Call | None:
    """The statement constructor a reference sits under, if it is one of the four verbs."""
    current = parents.get(node)
    while current is not None and not isinstance(current, ast.stmt):
        if (
            isinstance(current, ast.Call)
            and _call_name(current) in _STATEMENTS
            and current is _chain_root(current)
        ):
            return current
        current = parents.get(current)
    return None


def _refers(
    expression: ast.expr, table: str, aliases: Mapping[str, str], models: Mapping[str, str]
) -> bool:
    head = expression
    while isinstance(head, ast.Attribute):
        name = _dotted(head, aliases)
        if name and models.get(name) == table:
            return True
        head = head.value
    name = _dotted(head, aliases)
    return bool(name and models.get(name) == table)


# ---------------------------------------------------------------------------- the reach
@cache
def _imports(path: Path, src: Path) -> frozenset[str]:
    """Every `brain` module a file imports, at any depth in the file, as dotted names."""
    module = module_name(path, src)
    tree = _parsed(path)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(one.name for one in node.names)
        elif isinstance(node, ast.ImportFrom):
            source = _resolve_from(module, node, path.name == "__init__.py")
            names.add(source)
            names.update(f"{source}.{one.name}" for one in node.names)
    return frozenset(one for one in names if one == "brain" or one.startswith("brain."))


def reachable(roots: Sequence[str] = APPLICATION_ROOTS, src: Path = SRC) -> frozenset[str]:
    """Every module under `src` the roots import, however indirectly, the roots included.

    A package is reached with a module inside it, because importing `brain.a.b` runs
    `brain/a/__init__.py` first.
    """
    files = {module_name(path, src): path for path in _python_files(src)}
    found: set[str] = set()
    pending = [one for one in roots if one in files]
    while pending:
        module = pending.pop()
        if module in found:
            continue
        found.add(module)
        parts = module.split(".")
        for depth in range(1, len(parts)):
            package = ".".join(parts[:depth])
            if package in files and package not in found:
                pending.append(package)
        for name in _imports(files[module], src):
            for candidate in (name, name.rsplit(".", 1)[0]):
                if candidate in files and candidate not in found:
                    pending.append(candidate)
    return frozenset(found)


# ------------------------------------------------------------------------- the settings
@cache
def setting_constants(src: Path = SRC) -> Mapping[str, str]:
    """Every module-level constant holding an `app.*` setting name, `module.NAME` to the name."""
    found: dict[str, str] = {}
    for path in _python_files(src):
        module = module_name(path, src)
        for node in _parsed(path).body:
            target: ast.expr | None = None
            value: ast.expr | None = None
            if isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            if isinstance(target, ast.Name) and value is not None:
                text = _string_of(value)
                if text and re.fullmatch(r"app\.[a-z_]+", text):
                    found[f"{module}.{target.id}"] = text
    return MappingProxyType(found)


def _named_in(node: ast.AST, module: str, aliases: Mapping[str, str], src: Path) -> set[str]:
    """The settings one subtree names: a literal, or a constant holding one."""
    constants = setting_constants(src)
    named: set[str] = set()
    for one in ast.walk(node):
        text = _string_of(one) if isinstance(one, ast.Constant | ast.JoinedStr) else None
        if text:
            named.update(re.findall(r"\bapp\.[a-z_]+\b", text))
        if isinstance(one, ast.Name | ast.Attribute):
            dotted = _dotted(one, aliases)
            if dotted is not None and dotted in constants:
                named.add(constants[dotted])
            elif isinstance(one, ast.Name) and f"{module}.{one.id}" in constants:
                named.add(constants[f"{module}.{one.id}"])
    return named


@cache
def function_settings(src: Path = SRC) -> Mapping[str, frozenset[str]]:
    """Every module-level function naming a setting, `module.function` to the settings named."""
    found: dict[str, frozenset[str]] = {}
    for path in _python_files(src):
        module = module_name(path, src)
        tree = _parsed(path)
        aliases = _aliases(tree, module, path.name == "__init__.py")
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                named = _named_in(node, module, aliases, src)
                if named:
                    found[f"{module}.{node.name}"] = frozenset(named)
    return MappingProxyType(found)


def settings_named(path: Path, src: Path = SRC) -> frozenset[str]:
    """The `app.*` settings a module names: literally, through a constant, or through a function
    it imports whose body names them, which is how `brain.knowledge.search.session_settings`
    sets the reach for every store writing the corpus."""
    module = module_name(path, src)
    tree = _parsed(path)
    aliases = _aliases(tree, module, path.name == "__init__.py")
    functions = function_settings(src)
    named = _named_in(tree, module, aliases, src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Attribute):
            dotted = _dotted(node, aliases)
            if dotted is not None and dotted in functions:
                named |= functions[dotted]
    return frozenset(named)


# ------------------------------------------------------------------------ the comparison
@dataclass(frozen=True)
class Mismatch:
    """A use the migrations do not serve, and which half is missing."""

    use: Use
    missing: str

    def key(self) -> tuple[str, str, str]:
        """What `USES_EXPLAINED` is keyed by: the module, the table and the privilege."""
        return (self.use.module, self.use.table, self.use.privilege)

    def sentence(self) -> str:
        where = f"{self.use.module}:{self.use.line}"
        return f"{where} needs {self.use.privilege} on {self.use.table}: {self.missing}"


#: The halves a use can be missing, in the words a failing test prints.
NO_SUCH_TABLE: Final = "no migration creates it"
NO_GRANT: Final = "no migration grants it to brain_app"
NO_COLUMN_GRANT: Final = "the column grant does not cover every column written"
NO_POLICY: Final = "row-level security is on and no policy for that command names brain_app"
NO_SETTING: Final = "every policy admitting it reads a setting the module never names"


def uses(
    src: Path = SRC, roots: Sequence[str] = APPLICATION_ROOTS, known: frozenset[str] | None = None
) -> list[Use]:
    """Every table use in a module the application's sessions reach, in module order."""
    tables = known if known is not None else frozenset(orm_tables().values())
    reach = reachable(roots, src)
    found: list[Use] = []
    for path in _python_files(src):
        module = module_name(path, src)
        if module in reach and not module.startswith("brain.tables"):
            found.extend(uses_in(path, tables, src))
    return found


def mismatches(
    catalogue: Catalogue,
    found: Iterable[Use],
    *,
    role: str = APPLICATION_ROLE,
    src: Path = SRC,
) -> list[Mismatch]:
    """Every use the catalogue does not serve, one line per module, table and privilege.

    A write also needs what the triggers it fires read and write, when those run as the caller:
    `0059`'s audit triggers append to `obs.audit_entry` in the writer's own name, so a table whose
    writes are granted and whose ledger is not fails on the first write exactly as an ungranted
    table does. Those derived uses are checked for the grant and the policy and not for settings,
    which the trigger body reads from whatever its caller set.
    """
    seen: set[tuple[str, str, str, frozenset[str], str]] = set()
    missing: list[Mismatch] = []
    files = {module_name(path, src): path for path in _python_files(src)}
    for use in found:
        derived = [
            (Use(use.module, use.line, table, privilege), f"a trigger on {use.table} ")
            for body in (
                () if use.privilege == "SELECT" else catalogue.fired_by(use.table, use.privilege)
            )
            for table, privilege in sql_uses(body, catalogue.tables)
        ]
        for one, through in [(use, ""), *derived]:
            key = (one.module, one.table, one.privilege, one.columns, through)
            if key in seen:
                continue
            seen.add(key)
            path = None if through else files.get(one.module)
            why = _missing(catalogue, one, role, path, src)
            if why:
                missing.append(Mismatch(one, f"{through}{why}" if through else why))
    return missing


def _missing(catalogue: Catalogue, use: Use, role: str, path: Path | None, src: Path) -> str:
    if use.table not in catalogue.tables:
        return NO_SUCH_TABLE
    if not catalogue.holds(role, use.table, use.privilege):
        return NO_GRANT
    held = catalogue.columns_held(role, use.table, use.privilege)
    if held is not None and use.columns and not use.columns <= held:
        return NO_COLUMN_GRANT
    if not catalogue.admits(role, use.table, use.privilege):
        return NO_POLICY
    needed = catalogue.settings_needed(role, use.table, use.privilege)
    if needed and path is not None and not needed & settings_named(path, src):
        return NO_SETTING
    return ""


def unexplained(
    found: Iterable[Mismatch], explained: Mapping[tuple[str, str, str], str] = USES_EXPLAINED
) -> list[Mismatch]:
    """The mismatches no entry in `explained` accounts for."""
    return [one for one in found if one.key() not in explained]


def stale(
    found: Iterable[Mismatch], explained: Mapping[tuple[str, str, str], str] = USES_EXPLAINED
) -> list[tuple[str, str, str]]:
    """The entries in `explained` that no mismatch matches any more, in key order."""
    keys = {one.key() for one in found}
    return sorted(key for key in explained if key not in keys)


def main() -> int:  # pragma: no cover - a command for a person, exercised through its parts
    catalogue = migrations_catalogue()
    found = mismatches(catalogue, uses(known=catalogue.tables))
    for one in unexplained(found):
        print(one.sentence())
    for key in stale(found):
        print(f"explained and no longer found: {key}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
