"""The erasure executor for PostgreSQL, the queue of requests, and the worker's drain over it.

`brain.ops.erasure` decides what a deletion reaches, in what order, and what may be certified, and
its `StoreEraser` was a protocol nothing implemented, so an erasure request had nowhere to be filed
and nothing to carry it out. This is both halves: `PostgresEraser` implements the protocol for the
stores in PostgreSQL, `EstateEraser` hands each store to the executor that can reach it,
`StoredErasures` is where the console files a request, and `drain_erasure_queue` is what the
worker's schedule runs over the requests filed. It decides nothing `brain.ops.erasure` decides.

**Whose row a table holds is declared, table by table, and a table nobody decided about stops its
store.** A store is a set of schemas, and a schema holds tables a person owns, tables a person only
acted in, and tables about nobody. `SUBJECT_COLUMNS` names the column that says whose a row is,
`THROUGH` names the one table whose rows belong to a person through a parent, `ABOUT_NOBODY` names
every table no row of which is a person's own, and `RETAINED` names the one table an erasure keeps
on purpose. A table the catalogue lists and none of those four names refuses the whole store, for
`brain.ops.erasure.A_STORE_LEFT_OUT_OF_A_SUBJECT_ACCESS_REQUEST_IS_A_LIE`' reason: a table skipped
is a table whose rows about the person survive with the queue saying they were erased.
`declaration_gaps` holds the four against every table the models declare. See
`A_TABLE_NOBODY_DECIDED_ABOUT_STOPS_ITS_STORE`.

**An actor column is not whose row it is.** `granted_by`, `submitted_by` and `changed_by` name who
did something to somebody else's row, and an erasure is about whose data it is, which is
`brain.ops.erasure.Hold`'s argument against reading `actors`. So those tables are about nobody here,
and the person stays named in them as the one who acted. See `AN_ACTOR_IS_NOT_AN_OWNER`.

**How a row leaves is the table's rule, read from the catalogue and asked of the application
role.** Three cases, the same catalogue questions `brain.ops.retention_store.removal_rule` asks. A
table with `deleted_at` that the application role may update is **retired**, with the stamp
`statement_timestamp()` that `tests/invariants/test_soft_delete_invariants.py` requires of every
retirement, because `brain.db.SoftDeleteMixin` keeps the trail and an erasure does not hard-delete
past it. A table the application role may DELETE from has its rows **removed**, which today is only
`auth.directory_role_grant`. Every other table **keeps** its rows, counted and reported with the
rule, because its migration argued how its rows go and an erasure does not grant itself a second
way out. See `brain.ops.erasure.A_RETIRED_ROW_IS_UNREADABLE_AND_STILL_STORED` and
`brain.ops.erasure.A_ROW_NO_PATH_MAY_REMOVE_IS_KEPT_AND_SAID_TO_BE`.

**The executor refuses a connection row-level security narrows.** A policy that hides a row from
the connection hides it from the count and from the retirement alike, and the queue would then
report a person erased while rows it never saw are still there. So each table is asked whether the
connected role is subject to its policies, and a table it is refuses the store. The worker's
`DATABASE_URL` is the database owner's, which is what makes the executor able to see a person's
rows at all; the application's sessions run as `brain_app` and never reach this. See
`A_CONNECTION_ROW_SECURITY_NARROWS_CANNOT_COUNT_WHAT_IT_ERASES`.

**One store is one savepoint.** Every declaration is checked before anything is written, and a
database error part-way through a store rolls that store back to where it started and is reported
as the store not reached, so a store is either done as reported or untouched as reported.

**What is not reached, stated.** The object store holds recordings, attachments, exports and
backups, and `brain.ops.storage.StorageBackend` has no implementation on this commit, so
`EstateEraser` takes an object-store eraser as a parameter and, handed none, reports recordings and
attachments as not reached with `NO_OBJECT_STORE_ERASER`. That parameter is the seam an
implementation over a real backend plugs into. The answer cache has no delete by design,
`brain.cache` says why, and the retrieval index has no executor of its own, so both are reported as
not reached. **Every erasure is therefore incomplete today**, and the queue says so with the stores
named, which is the honest state rather than a defect in the queue.

**A legal hold wins, judged when the request is carried out.** The holds are read inside the drain's
own transaction by `brain.ops.retention_store.active_holds`, and a held request is finished as held
with the holds that stopped it and nothing touched. It is not left waiting: a hold can stand for
years, and a request made again when it is lifted is
`brain.ops.erasure.A_HELD_SUBJECT_IS_NOT_ERASED`.

**The queue is not a destructive control that waits for a release.**
`brain.ops.schedule.DESTRUCTIVE` holds the retention sweep until somebody reads its report, because
the sweep decides what to remove by a policy nobody looked at. Each request here is a person's
decision about one person, confirmed on the screen by somebody holding the authority to make it, so
a second release would be the same decision asked twice. See
`A_FILED_REQUEST_IS_ALREADY_THE_DECISION`.

Task ids: M27.7.24
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.ops.erasure import (
    Deletion,
    ErasureError,
    HeldError,
    StoreEraser,
    StoreRemoval,
    carry_out,
)
from brain.ops.ledger_partitions import declared_as
from brain.ops.retention import RetentionError, Store, facts_for
from brain.ops.retention_store import (
    A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME,
    A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO,
    ATTRIBUTED,
    active_holds,
    store_tables,
)
from brain.session import APPLICATION_ROLE
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.erasure import ErasureOutcome, ErasureRequestRow

# ------------------------------------------------------------------ written-down reasons
#: Why an undeclared table refuses its store.
A_TABLE_NOBODY_DECIDED_ABOUT_STOPS_ITS_STORE: Final = (
    "the catalogue lists a table in this store that is not declared as holding a person's rows, "
    "reaching them through a parent, holding nobody's, or kept on purpose; skipping it would leave "
    "whatever it holds about the person in place with the queue saying they were erased"
)

#: Why a table holding only actors is about nobody.
AN_ACTOR_IS_NOT_AN_OWNER: Final = (
    "A column naming who granted, submitted, changed or installed something names somebody who "
    "acted on another row, not whose row it is. An erasure is about whose data it is, which is "
    "brain.ops.erasure.Hold's reason for not reading actors, so a table whose only person columns "
    "are actors holds nobody's own rows, and the person stays named in it as the one who acted."
)

#: Why a connection row-level security narrows is refused.
A_CONNECTION_ROW_SECURITY_NARROWS_CANNOT_COUNT_WHAT_IT_ERASES: Final = (
    "this connection is subject to the table's row-level security, so rows a policy hides from it "
    "would be neither counted nor retired and the store would read as erased with them still "
    "there; the queue has to run on a connection the policies do not narrow, which the worker's "
    "database owner connection is"
)

#: Why the object store is not reached, and what would reach it.
NO_OBJECT_STORE_ERASER: Final = (
    "it is held in the object store, and no object-store eraser is attached: "
    "brain.ops.storage.StorageBackend has no implementation this queue is handed"
)

#: Why the answer cache is not reached.
NO_CACHE_ERASER: Final = (
    "the answer cache has no delete by design (brain.cache argues it), so its entries about the "
    "person stay until they expire or their epoch moves, and no cache eraser is attached"
)

#: Why the retrieval index is not reached.
NO_INDEX_ERASER: Final = (
    "the retrieval index has no executor of its own, so an entry pointing at the person's "
    "knowledge is not removed by this queue"
)

#: Why a store with no tables in PostgreSQL is refused by the PostgreSQL executor.
NOT_IN_POSTGRES: Final = "it is not held in PostgreSQL, so this executor cannot reach it"

#: Why the queue is not held behind a release the way the retention sweep is.
A_FILED_REQUEST_IS_ALREADY_THE_DECISION: Final = (
    "brain.ops.schedule.DESTRUCTIVE keeps the retention sweep reporting until a person reads what "
    "it would remove, because the sweep decides by a policy nobody looked at. A request in this "
    "queue is one person's decision about one person's data, confirmed on the Retention screen by "
    "somebody holding admin:erasure over everything, so holding it behind a second release would "
    "ask the same decision twice and leave the right waiting on somebody else's approval."
)

#: Why the erasure request table is kept by the erasure it records.
THE_REQUEST_IS_THE_PROOF_AND_IS_KEPT: Final = (
    "the request is the record that the erasure was asked for, by whom, and what it did; removing "
    "it would remove the only proof that the person's right was honoured"
)

#: Why a sensitive read is kept by the erasure of the person whose record was read (M24.3.2).
A_READ_OF_A_RECORD_IS_THE_LEDGERS_AND_IS_KEPT: Final = (
    "each row is the source of a record_read ledger entry naming the same reader, record kind and "
    "subject, and the ledger is the audit store, which no erasure reaches; removing the row would "
    "remove nothing the ledger does not still say, and needs a DELETE the append-only table grants "
    "nobody"
)

#: Why a learning and a correction are kept by the erasure of the person whose memory they name.
A_CORRECTION_OUTLIVES_ITS_MEMORY_OR_THE_MEMORY_COMES_BACK: Final = (
    "a learning and a correction name a memory by its id and hold neither the person nor anything "
    "anybody said; the memory is the person's and leaves by its own table's rule, and removing a "
    "correction while the memory it marked is kept would put what was corrected back into recall"
)

#: Why the staff roster and its runs are kept by an erasure (added with `0096`, 2026-09-21).
A_ROSTER_ROW_IS_THE_SOURCES_AND_RETURNS_WHILE_THE_SOURCE_LISTS_THEM: Final = (
    "a roster row is the company's staff list as its own source states it, keyed by the digest of "
    "a work address and joined to no principal; removing it while the directory still lists the "
    "person writes it back on the next nightly run, so a person leaves the roster by leaving the "
    "source, and a run's record of who joined and left is kept as the ledger's entries are"
)

# ---------------------------------------------------------------------------- figures
#: The name the queue finishes a request under, which `0060`'s trigger writes as the actor.
ERASURE_QUEUE_ACTOR: Final = "erasure-queue"

#: How often the worker's schedule drains the queue. `brain.ops.controls` restates it.
DRAIN_EVERY: Final = timedelta(minutes=15)

#: How many requests one run carries out, so one run's transaction count is bounded.
DRAIN_LIMIT: Final = 20

# ----------------------------------------------------------------------- declarations
#: The column naming whose a row is, for every table holding a person's own rows.
SUBJECT_COLUMNS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "agent.agent": "owner_id",
        # What an agent produced, for the person it was produced for. `0058` grants no way for a
        # row to leave, so an erasure keeps these and reports them kept.
        "agent.artifact": "caller_id",
        # A run of an automation, for the person it ran as, with what it found at their reach.
        # `0067` grants no way for a row to leave, so an erasure keeps these and reports them kept.
        "agent.automation_run": "principal_id",
        "agent.browser_envelope": "asked_by",
        "auth.directory_role_grant": "principal_id",
        "auth.principal": "id",
        "auth.principal_identity": "principal_id",
        # An integration a person registered acts at their reach, so it goes with them. `0095`.
        "auth.service_account": "owner_principal_id",
        "auth.session": "principal_id",
        "chat.conversation": "principal_id",
        # A request for access is the asker's question and goes with them. `0101`.
        "gate.access_request": "asker_id",
        "gate.automation_owner": "owner_principal_id",
        "gate.capability_grant": "principal_id",
        "gate.capability_pack_assignment": "principal_id",
        "gate.department_lead": "principal_id",
        "gate.elevation_request": "principal_id",
        "gate.grants_version": "principal_id",
        "gate.review_decision": "principal_id",
        # A role a person was appointed to. Retired like a grant, and refused by `0102`'s guard
        # when it would leave fewer than two Super Admins, so an erasure cannot lock the install.
        "gate.role_grant": "principal_id",
        "gate.suspension": "principal_id",
        "gate.team_membership": "principal_id",
        "know.chunk": "owner_id",
        "know.item": "owner_id",
        "mem.adaptive": "principal_id",
        "mem.persistent": "principal_id",
        "obs.request_telemetry": "principal",
        # A budget's subject is a person, a department or an agent; only a person's id matches.
        "ops.budget_version": "subject",
        # A golden question asked as a person (`0097`). An administrator wrote it, but it names the
        # person it is asked as; `0097` grants no way for a row to leave, so an erasure keeps these
        # and reports them kept, and a question asked as nobody is refused by the resolver.
        "ops.golden_question": "asked_as",
        "ops.operation": "principal_id",
        "ops.question_asked": "principal_id",
        "ops.spend_actual": "principal_id",
    }
)


@dataclass(frozen=True)
class Through:
    """A table whose rows are a person's through a parent: the key to it and the parent's key."""

    parent: str
    key: str
    parent_key: str


#: Tables whose rows belong to a person only through the row they point at.
THROUGH: Final[Mapping[str, Through]] = MappingProxyType(
    {
        "chat.message": Through(parent="chat.conversation", key="conversation_id", parent_key="id"),
        # A key is a person's through the account it speaks for. `0095`.
        "auth.api_key": Through(
            parent="auth.service_account", key="client_id", parent_key="client_id"
        ),
    }
)

#: Tables in a PostgreSQL store no row of which is a person's own. See `AN_ACTOR_IS_NOT_AN_OWNER`.
ABOUT_NOBODY: Final[frozenset[str]] = frozenset(
    {
        "agent.automation",
        # Why an automation's schedule changed and who changed it: an actor, not an owner.
        "agent.automation_schedule",
        "agent.skill",
        "agent.skill_assignment",
        "agent.skill_review",
        "agent.template_instance",
        "agent.template_version",
        "agent.upgrade_decline",
        "er.alias",
        "er.canonical",
        "er.identifier",
        "er.link",
        "gate.capability_pack",
        "gate.capability_registry",
        # A delivered message's channel, its external id and an instant: `0100` keeps no sender
        # and no text, so a claim says a message arrived and nothing about whose it was.
        "gate.channel_event",
        "gate.department",
        "gate.fast_path_rule",
        "gate.field_policy",
        "gate.policy_epoch",
        "gate.scope",
        "gate.team",
        # A log row keeps an event name, a place in the code and masked fields, never a person.
        "obs.application_log",
        "ops.connector_connection",
        # An attempt to read a connected source keeps the connection's id, the source's name, two
        # counts, three instants and a constant sentence: `0068` keeps no principal and no value
        # from the source, so nothing in it is anybody's.
        "ops.connector_sync",
        "ops.control_run",
        "ops.credential_write",
        "ops.data_export",
        # A deploy keeps an image, a commit, task ids and digests: `0091` keeps no principal.
        "ops.deployment_record",
        "ops.model_attempt",
        # A provider's terms and a matrix change name the administrator who wrote them, an actor
        # and not an owner (`0097`).
        "ops.model_provider",
        "ops.outbox_delivery",
        "ops.outbox_event",
        "ops.plugin_install",
        "ops.plugin_version",
        # A department, a source and an instant under a trace id: `0063` keeps no principal, so a
        # question no connected source covered is nobody's once the question ledger's row is gone.
        "ops.question_gap",
        "ops.report_refresh",
        "ops.retention_release",
        "ops.retention_report",
        "ops.routing_change",
        "ops.routing_rung",
        "ops.routing_tier",
        "ops.setting",
        # A requirement check keeps a register id, an outcome and who checked: an actor, not an
        # owner, so nothing in it is anybody's (`0099`).
        "ops.requirement_check",
        # A vault call keeps a slot, an operation and the HMAC of a token's accessor: `0093` keeps
        # no principal, and the digest names a token no candidate list can reverse without the key.
        "ops.vault_access",
        "ops.webhook_change",
        "ops.webhook_subscriber",
        "proj.record",
    }
)

#: Tables an erasure keeps on purpose, and why.
RETAINED: Final[Mapping[str, str]] = MappingProxyType(
    {
        "mem.correction": A_CORRECTION_OUTLIVES_ITS_MEMORY_OR_THE_MEMORY_COMES_BACK,
        "mem.learning": A_CORRECTION_OUTLIVES_ITS_MEMORY_OR_THE_MEMORY_COMES_BACK,
        "ops.erasure_request": THE_REQUEST_IS_THE_PROOF_AND_IS_KEPT,
        "auth.staff_member": A_ROSTER_ROW_IS_THE_SOURCES_AND_RETURNS_WHILE_THE_SOURCE_LISTS_THEM,
        "auth.staff_sync_run": A_ROSTER_ROW_IS_THE_SOURCES_AND_RETURNS_WHILE_THE_SOURCE_LISTS_THEM,
        "ops.sensitive_read": A_READ_OF_A_RECORD_IS_THE_LEDGERS_AND_IS_KEPT,
    }
)


def declaration_gaps(
    tables: Sequence[str],
    *,
    subjects: Mapping[str, str] = SUBJECT_COLUMNS,
    through: Mapping[str, Through] = THROUGH,
    about_nobody: frozenset[str] = ABOUT_NOBODY,
    retained: Mapping[str, str] = RETAINED,
) -> tuple[str, ...]:
    """Every table in an erasable PostgreSQL store that is declared in no way, or in two.

    `tables` is handed in rather than read from `brain.db.metadata` here, for the reason
    `brain.ops.retention.store_gaps` takes its facts: a check that can only run against the
    declarations beside it cannot be shown to fail. A table in `obs` attributed to the audit
    store is out of scope, because the audit store is never erased.
    """
    findings: list[str] = []
    kinds = (set(subjects), set(through), set(about_nobody), set(retained))
    for table in sorted(tables):
        schema = table.partition(".")[0]
        if not _erasable_schema(schema) or ATTRIBUTED.get(table) is Store.AUDIT:
            continue
        declared = sum(1 for kind in kinds if table in kind)
        if declared == 0:
            findings.append(f"{table}: {A_TABLE_NOBODY_DECIDED_ABOUT_STOPS_ITS_STORE}")
        elif declared > 1:
            findings.append(
                f"{table} is declared more than one way, so which rule applies is a guess"
            )
    for table in sorted({*subjects, *through, *about_nobody, *retained} - set(tables)):
        findings.append(f"{table} is declared here and is not a table, so a rename left it behind")
    for table, via in sorted(through.items()):
        if via.parent not in subjects:
            findings.append(f"{table} reaches a person through {via.parent}, which names nobody")
    return tuple(findings)


def _erasable_schema(schema: str) -> bool:
    return any(schema in facts_for(store).schemas for store in _POSTGRES_TARGETS)


#: The stores in PostgreSQL a deletion reaches. The audit store is in `obs` and is retained.
_POSTGRES_TARGETS: Final[tuple[Store, ...]] = tuple(
    store for store in Store if facts_for(store).schemas and store is not Store.AUDIT
)


# ------------------------------------------------------------------------- the executor
@dataclass(frozen=True)
class _Rule:
    """How one table's rows about a person leave, read from the catalogue."""

    retire: bool = False
    delete: bool = False
    kept_because: str = ""


class PostgresEraser:
    """`brain.ops.erasure.StoreEraser` over one PostgreSQL connection, for the stores it holds.

    Every declaration is a parameter defaulting to this module's own, for the reason
    `brain.ops.retention_store.PostgresSweeper` takes its own: an executor that can only be pointed
    at the real estate is an executor nobody has watched refuse an undeclared table.
    """

    def __init__(
        self,
        conn: psycopg.Connection[Any],
        *,
        subjects: Mapping[str, str] = SUBJECT_COLUMNS,
        through: Mapping[str, Through] = THROUGH,
        about_nobody: frozenset[str] = ABOUT_NOBODY,
        retained: Mapping[str, str] = RETAINED,
        role: str = APPLICATION_ROLE,
    ) -> None:
        self.conn = conn
        self.subjects = subjects
        self.through = through
        self.about_nobody = about_nobody
        self.retained = retained
        self.role = role

    # -------------------------------------------------------------------- the protocol
    def count_for(self, store: Store, subject_id: str) -> int:
        """Every row in this store about the person, retired rows included."""
        return sum(self._count(table, subject_id) for table in self._owned(store))

    def erase(self, store: Store, subject_id: str) -> StoreRemoval:
        """Retire, remove or keep each table's rows about the person, in one savepoint."""
        tables = self._owned(store)
        rules = {table: self._rule(table) for table in tables}
        removed = retired = kept = 0
        because: list[str] = []
        try:
            with self.conn.transaction():
                for table in tables:
                    rule = rules[table]
                    if rule.retire:
                        self._retire(table, subject_id)
                        retired += self._count(table, subject_id, retired=True)
                    elif rule.delete:
                        removed += self._delete(table, subject_id)
                    else:
                        found = self._count(table, subject_id)
                        if found:
                            kept += found
                            if rule.kept_because not in because:
                                because.append(rule.kept_because)
        except psycopg.Error as failed:
            msg = f"the database refused the erasure part-way, so nothing in it was kept: {failed}"
            raise ErasureError(msg[:500]) from failed
        return StoreRemoval(
            removed=removed, retired=retired, kept=kept, kept_because="; ".join(because)
        )

    # --------------------------------------------------------------- which tables
    def _owned(self, store: Store) -> tuple[str, ...]:
        """The tables of this store holding a person's rows. Refuses anything undecided."""
        if not facts_for(store).schemas:
            raise ErasureError(NOT_IN_POSTGRES)
        try:
            listed = store_tables(self.conn, store)
        except RetentionError as why:
            raise ErasureError(str(why)) from why
        owned: list[str] = []
        for table in listed:
            declared = declared_as(table)
            if declared in self.subjects or declared in self.through:
                owned.append(table)
            elif declared not in self.about_nobody and declared not in self.retained:
                raise ErasureError(f"{table}: {A_TABLE_NOBODY_DECIDED_ABOUT_STOPS_ITS_STORE}")
        return tuple(owned)

    def _rule(self, table: str) -> _Rule:
        """How this table's rows leave, and whether this connection may see all of them."""
        schema, _, name = table.partition(".")
        row = self.conn.execute(
            "SELECT c.relkind, c.relrowsecurity, c.relforcerowsecurity, "
            "pg_get_userbyid(c.relowner) = current_user, "
            "(SELECT r.rolsuper OR r.rolbypassrls FROM pg_catalog.pg_roles AS r "
            " WHERE r.rolname = current_user), "
            "EXISTS (SELECT 1 FROM pg_catalog.pg_attribute AS a WHERE a.attrelid = c.oid "
            " AND a.attname = 'deleted_at' AND NOT a.attisdropped), "
            "has_table_privilege(%s, c.oid, 'DELETE') "
            "FROM pg_catalog.pg_class AS c "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = %s",
            (self.role, schema, name),
        ).fetchone()
        if row is None:
            raise ErasureError(f"{table} is not in the catalogue")
        kind, secured, forced, owner, bypasses, soft, may_delete = row
        if secured and not bypasses and (forced or not owner):
            raise ErasureError(
                f"{table}: {A_CONNECTION_ROW_SECURITY_NARROWS_CANNOT_COUNT_WHAT_IT_ERASES}"
            )
        if kind == "p":
            return _Rule(kept_because=A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME)
        if soft and self._may_retire(table):
            return _Rule(retire=True)
        if may_delete:
            return _Rule(delete=True)
        return _Rule(kept_because=A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO)

    def _may_retire(self, table: str) -> bool:
        row = self.conn.execute(
            "SELECT has_column_privilege(%s, %s::regclass, 'deleted_at', 'UPDATE')",
            (self.role, table),
        ).fetchone()
        return bool(row and row[0])

    # ------------------------------------------------------------------- statements
    def _whose(self, table: str, subject_id: str) -> tuple[sql.Composable, tuple[object, ...]]:
        """The condition selecting this table's rows about the person, and its parameters."""
        declared = declared_as(table)
        via = self.through.get(declared)
        if via is None:
            column = sql.Identifier(self.subjects[declared])
            return sql.SQL("{column} = %s").format(column=column), (subject_id,)
        return (
            sql.SQL(
                "{key} IN (SELECT p.{parent_key} FROM {parent} AS p WHERE p.{owner} = %s)"
            ).format(
                key=sql.Identifier(via.key),
                parent_key=sql.Identifier(via.parent_key),
                parent=_identifier(via.parent),
                owner=sql.Identifier(self.subjects[via.parent]),
            ),
            (subject_id,),
        )

    def _count(self, table: str, subject_id: str, *, retired: bool = False) -> int:
        condition, params = self._whose(table, subject_id)
        query = sql.SQL("SELECT count(*) FROM {table} WHERE {condition}").format(
            table=_identifier(table), condition=condition
        )
        if retired:
            query = sql.SQL("{base} AND deleted_at IS NOT NULL").format(base=query)
        row = self.conn.execute(query, params).fetchone()
        return int(row[0]) if row is not None else 0

    def _retire(self, table: str, subject_id: str) -> int:
        condition, params = self._whose(table, subject_id)
        query = sql.SQL(
            "UPDATE {table} SET deleted_at = statement_timestamp() "
            "WHERE {condition} AND deleted_at IS NULL"
        ).format(table=_identifier(table), condition=condition)
        return self.conn.execute(query, params).rowcount

    def _delete(self, table: str, subject_id: str) -> int:
        condition, params = self._whose(table, subject_id)
        query = sql.SQL("DELETE FROM {table} WHERE {condition}").format(
            table=_identifier(table), condition=condition
        )
        return self.conn.execute(query, params).rowcount


def _identifier(table: str) -> sql.Identifier:
    schema, _, name = table.partition(".")
    return sql.Identifier(schema, name)


class EstateEraser:
    """The eraser the queue runs: each store to the executor that can reach it, the rest refused.

    `objects` is the seam for the object store. Handed none, which is every install on this
    commit, recordings and attachments are refused with `NO_OBJECT_STORE_ERASER`; an
    implementation over a real `brain.ops.storage.StorageBackend` is passed here and nothing else
    changes. See the module docstring.
    """

    def __init__(self, postgres: PostgresEraser, *, objects: StoreEraser | None = None) -> None:
        self.postgres = postgres
        self.objects = objects

    def _executor(self, store: Store) -> StoreEraser:
        facts = facts_for(store)
        if facts.schemas:
            return self.postgres
        if facts.buckets:
            if self.objects is None:
                raise ErasureError(NO_OBJECT_STORE_ERASER)
            return self.objects
        if store is Store.CACHE:
            raise ErasureError(NO_CACHE_ERASER)
        raise ErasureError(NO_INDEX_ERASER)

    def count_for(self, store: Store, subject_id: str) -> int:
        return self._executor(store).count_for(store, subject_id)

    def erase(self, store: Store, subject_id: str) -> StoreRemoval:
        return self._executor(store).erase(store, subject_id)


# ---------------------------------------------------------------------------- the drain
def stores_document(deletion: Deletion) -> list[dict[str, Any]]:
    """What a finished request records about each store. Counts and sentences, never a value."""
    return [
        {
            "store": one.store.value,
            "disposition": one.disposition.value,
            "reached": one.reached,
            "removed": one.removed,
            "retired": one.retired,
            "kept": one.kept,
            "because": one.because,
        }
        for one in deletion.results
    ]


def _set(conn: psycopg.Connection[Any], name: str, value: str) -> None:
    conn.execute("SELECT set_config(%s, %s, true)", (name, value))


def drain_erasure_queue(
    conn: psycopg.Connection[Any],
    *,
    now: datetime,
    report_only: bool = False,
    limit: int = DRAIN_LIMIT,
    objects: StoreEraser | None = None,
) -> str:
    """Carry out the oldest open requests filed by `now`, one transaction each, as report lines.

    Each request is taken with `FOR UPDATE SKIP LOCKED`, so two workers never carry out one
    request. Inside its transaction the holds are read, the request is carried out over
    `EstateEraser`, and the row is finished with the outcome, what each store did and the holds
    that stopped it, and `0060`'s trigger appends the ledger entry in the same commit. A request
    whose run raises anything other than a refusal is rolled back whole and stays open, and the
    run raises on, so the control run records the failure.

    The session's actor is the queue's name and its trace the request's, so every entry the
    erasure's own writes append, the revokes a retired grant writes among them, is attributed to
    the queue working on this request.

    In report-only mode nothing is carried out, and the count of open requests is the report.
    The queue is not in `brain.ops.schedule.DESTRUCTIVE`, see
    `A_FILED_REQUEST_IS_ALREADY_THE_DECISION`, so the schedule never asks for that mode; it is
    answered rather than ignored in case something does.
    """
    if report_only:
        row = conn.execute(
            "SELECT count(*) FROM ops.erasure_request "
            "WHERE finished_at IS NULL AND requested_at <= %s",
            (now,),
        ).fetchone()
        waiting = 0 if row is None else int(row[0])
        return f"report only: {waiting} erasure request(s) open and none carried out"
    lines: list[str] = []
    for _ in range(limit):
        with conn.transaction():
            taken = conn.execute(
                "SELECT request_id, subject_id, requested_at FROM ops.erasure_request "
                "WHERE finished_at IS NULL AND requested_at <= %s "
                "ORDER BY requested_at, request_id LIMIT 1 FOR UPDATE SKIP LOCKED",
                (now,),
            ).fetchone()
            if taken is None:
                break
            request_id, subject_id, requested_at = taken
            _set(conn, ACTOR_SETTING, ERASURE_QUEUE_ACTOR)
            _set(conn, TRACE_ID_SETTING, f"erasure.{request_id}")
            holds = active_holds(conn, now)
            try:
                deletion = carry_out(
                    EstateEraser(PostgresEraser(conn), objects=objects),
                    subject_id=subject_id,
                    requested_at=requested_at,
                    completed_at=now,
                    holds=holds,
                )
            except HeldError as held:
                outcome, stores, held_by = ErasureOutcome.HELD, [], list(held.hold_ids)
            else:
                outcome = ErasureOutcome.ERASED if deletion.complete else ErasureOutcome.INCOMPLETE
                stores, held_by = stores_document(deletion), []
            conn.execute(
                "UPDATE ops.erasure_request SET finished_at = %s, finished_by = %s, outcome = %s, "
                "stores = %s, holds = %s WHERE request_id = %s",
                (
                    now,
                    ERASURE_QUEUE_ACTOR,
                    outcome.value,
                    Jsonb(stores),
                    Jsonb(held_by),
                    request_id,
                ),
            )
        lines.append(f"erasure request {request_id}: {outcome.value}")
    return "\n".join(lines) if lines else "no erasure request was open"


# --------------------------------------------------------------------------- the console
class ErasureRefusedError(Exception):
    """A request was not filed, and why, in a word the route can name to somebody with authority."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"the erasure request was not filed: {reason}")


#: The one reason a request is refused by the store: an open request for the person already exists.
ALREADY_REQUESTED: Final = "already_requested"


@dataclass(frozen=True)
class ErasureRecord:
    """One request as `ops.erasure_request` holds it, and how it finished, where it has."""

    request_id: str
    subject_id: str
    reason_reference: str
    requested_by: str
    requested_at: datetime
    finished_at: datetime | None
    outcome: ErasureOutcome | None
    #: `stores_document`, as written. Empty until finished, and for a held request.
    stores: tuple[Mapping[str, Any], ...]
    holds: tuple[str, ...]


@runtime_checkable
class ErasureRecords(Protocol):
    """What the Retention screen's erasure routes need from the database.

    `StoredErasures` is one.
    """

    async def file(
        self,
        *,
        subject_id: str,
        reason_reference: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> ErasureRecord:
        """File one request in the actor's name. `ErasureRefusedError` for an open duplicate."""
        ...

    async def requests(self, *, limit: int) -> tuple[ErasureRecord, ...]:
        """The newest requests, newest first."""
        ...


def _setting(name: str, value: str) -> Any:
    # `set_config(..., true)` is transaction-scoped, which is what a pooled connection needs.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def record_from(row: ErasureRequestRow) -> ErasureRecord:
    """The record a row holds."""
    return ErasureRecord(
        request_id=str(row.request_id),
        subject_id=row.subject_id,
        reason_reference=row.reason_reference,
        requested_by=row.requested_by,
        requested_at=row.requested_at,
        finished_at=row.finished_at,
        outcome=None if row.outcome is None else ErasureOutcome(row.outcome),
        stores=tuple(row.stores or ()),
        holds=tuple(row.holds or ()),
    )


class StoredErasures:
    """`ops.erasure_request`, filed and read as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def file(
        self,
        *,
        subject_id: str,
        reason_reference: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> ErasureRecord:
        try:
            async with self._sessions() as session, session.begin():
                await session.execute(_setting(PRINCIPAL_SETTING, actor))
                await session.execute(_setting(ENT_HASH_SETTING, ent_hash))
                await session.execute(_setting(TRACE_ID_SETTING, trace_id))
                row = ErasureRequestRow(
                    request_id=uuid.uuid4(),
                    subject_id=subject_id,
                    reason_reference=reason_reference,
                    requested_by=actor,
                    requested_at=at,
                )
                session.add(row)
                await session.flush()
                filed = record_from(row)
        except IntegrityError as refused:
            # The partial unique index on an open request is the only key a valid row can meet.
            raise ErasureRefusedError(ALREADY_REQUESTED) from refused
        return filed

    async def requests(self, *, limit: int) -> tuple[ErasureRecord, ...]:
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(ErasureRequestRow)
                        .order_by(
                            ErasureRequestRow.requested_at.desc(), ErasureRequestRow.request_id
                        )
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return tuple(record_from(row) for row in rows)
