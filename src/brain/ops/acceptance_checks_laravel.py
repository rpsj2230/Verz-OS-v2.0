"""The install acceptance check for the Laravel database: read into the index, and asked on Ask.

M11.6.1 asks that a company's own Laravel database is read through views it controls, and M11.7.7
that it is connected from the console, which means this install can read it. The check connects a
Laravel connection made up for the run inside its own transaction, through the store the
Connectors screen's routes call, reads both views into the index with the worker's own
`brain.ops.connector_sync_run.attempt`, through the real executor over a recorded driver, and then
asks about a client through the answer lane with everything the answer route hands it built by the
route's own functions, as `brain.ops.acceptance_checks_sources` does for Xero and Freshdesk.

**No socket is opened and no real login is held.** `_Views` is the driver: it answers each view's
`SELECT` with the rows written here and records the statements it was sent, and the login the lease
hands over is minted for the check. The address every name resolves to is the one
`brain.ops.acceptance_checks_connectors` uses, which the address rule admits and nothing connects
to. See `A_RECORDED_DATABASE_IS_NEVER_A_CONNECTION`.

**What it proves.** The worker keeps the client and the staff record in `proj.record` under the
view's rule; a reader granted a client's contract value is told the value read live from the view
while they wait, narrowed to the client's id; a reader not granted it is told what a client
nobody has tells them; the value is in no table afterwards; and every read the check made carried
the connection's row cap as a bound `LIMIT`.

**The check steps aside where the install has Laravel connected already**, for
`brain.ops.acceptance_checks_sources.A_SOURCE_IS_CONNECTED_HERE_ALREADY`'s reason: connecting a
source that is connected is refused, and a real connection would stand in the check's place.

Task ids: M11.6.1, M11.7.7
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import (
    _Lease,
    _no_wait,
    _nothing_kept,
    _Resolver,
    _search,
)
from brain.ops.acceptance_checks_sources import _connection, _prose
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from brain.connectors.declaration import DatabaseLogin
    from brain.connectors.laravel import LaravelConnection, LaravelReading, ViewReader
    from brain.core.entitlement import EntitlementSet
    from brain.gate.answer import Answered
    from brain.ops.connector_store import Connection
    from brain.ops.secrets import SecretRef

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 370

A, _ = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why nothing the check does reaches a database.
A_RECORDED_DATABASE_IS_NEVER_A_CONNECTION: Final = (
    "The check reads the views through the product's own executor over a driver that answers "
    "from rows written in the check and opens no socket. The login it leases is minted for the "
    "check, and every name resolves to one public address nothing connects to."
)

#: What the check says where the install has Laravel connected already.
LARAVEL_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has its Laravel database connected already, so the check does not connect it "
    "again and does not ask about it"
)

# ------------------------------------------------------------------------ the figures
#: The user the leased login names. Made up for the check, as its password is.
READER: Final = "acceptance_reader"

#: The database the check's views are in. A name only: the driver is recorded.
SCHEMA: Final = "acceptance"

#: Where the check says the server is. Reserved for documentation, and never reached.
HOST: Final = "acceptance-check.invalid"

#: The most rows one read may return, which every read the check makes must carry as its limit.
MAX_ROWS: Final = 50


# ------------------------------------------------------------------------ the helpers
@dataclass
class _Views:
    """A driver answering each view's `SELECT` with the check's own rows. No socket.

    `selected` is every `SELECT` with its parameters, so the check can say what was read and with
    what limit.
    """

    clients: Sequence[Mapping[str, Any]]
    users: Sequence[Mapping[str, Any]]
    selected: list[tuple[str, object]] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> _Session:
        del kwargs
        return _Session(self)

    def opener(
        self, address: str, connection: LaravelConnection, login: DatabaseLogin
    ) -> ViewReader:
        """The product's executor, driving this recording."""
        from brain.ops.laravel_reader import MySqlViewReader

        return MySqlViewReader(
            address=address,
            port=connection.port,
            login=login,
            server_name=connection.host,
            tls=connection.tls,
            driver=self,
        )


@dataclass
class _Session:
    """One recorded connection: its cursor is itself, and closing it closes nothing."""

    views: _Views
    rows: Sequence[Mapping[str, Any]] = ()

    def cursor(self) -> _Session:
        return self

    def execute(self, query: str, args: object = None) -> int:
        if query.startswith("SELECT"):
            self.views.selected.append((query, args))
            self.rows = self.views.clients if ".v_client" in query else self.views.users
        return len(self.rows)

    def fetchall(self) -> Sequence[Mapping[str, Any]]:
        return tuple(dict(one) for one in self.rows)

    def close(self) -> None:
        return None


@dataclass
class _Logins:
    """`ConnectorKeys` leasing a login this check made: a user and a password nobody else holds."""

    leased: int = 0

    def lease(self, ref: SecretRef, *, now: datetime) -> _Lease:
        del ref, now
        self.leased += 1
        return _Lease(secrets.token_hex(16), user_name=READER)


class _NoCall:
    """The REST caller, which a database's read must never use."""

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> Any:
        del url, address, headers, max_bytes
        raise CheckFailedError("the worker read a database's views over HTTP")


async def _connect_and_read(h: Harness, connection: Connection, reading: LaravelReading) -> None:
    """Connect the database as the Connectors screen's route does, and read it as the worker does.

    The worker's own `attempt`, over this check's reading, so the executor reads the recorded views.
    """
    import uuid

    from brain.ops.connector_store import StoredConnections
    from brain.ops.connector_sync import SyncOutcome, plan_for
    from brain.ops.connector_sync_run import attempt
    from brain.ops.connector_sync_store import LiveConnection

    await StoredConnections(h.sessions).connect(
        connector=connection.connector,
        settings=connection.settings,
        digest=connection.digest,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=_nothing_kept,
    )
    plan = plan_for(connection, last=None, now=h.now, readings={connection.connector: reading})
    if plan.refused or not plan.due:
        raise CheckFailedError("the worker's plan would not read a database connected as declared")
    done = await attempt(
        LiveConnection(id=uuid.uuid4(), connection=connection),
        plan,
        previous=None,
        sessions=h.sessions,
        keys=_Logins(),
        caller=_NoCall(),
        resolver=_Resolver(),
        clock=lambda: h.now,
        sleep=_no_wait,
    )
    if done.outcome is not SyncOutcome.SYNCED or done.records != 2:
        raise CheckFailedError("the worker did not read both of the database's views to the end")


# ------------------------------------------------ 1. the database answers on Ask
@check(
    leaves=("M11.6.1", "M11.7.7"),
    sentence=(
        "A Laravel database made up for the check is connected as the Connectors screen does and "
        "read by the worker through the executor over a recorded driver: a client's contract value "
        "is read live from its view for a reader granted it, withheld as if absent from one who is "
        "not, and in no table, and every read carried the row cap as its limit."
    ),
)
async def a_laravel_database_answers_on_ask_from_its_views(h: Harness) -> None:
    from sqlalchemy import select

    from brain.api_routes import (
        connected_questions_of,
        covered_at,
        field_policies,
        row_readers,
        source_field_policies,
    )
    from brain.connectors import laravel
    from brain.connectors.minimal_index import fresh_canary
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connector_store import live
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tables.projection import ProjectedRecordRow
    from brain.tools.startup import build_registry

    if (await h.execute(live(laravel.CONNECTOR_NAME))).scalar_one_or_none() is not None:
        raise CheckNotRunError(LARAVEL_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()
    state = SimpleNamespace(db_sessions=h.sessions)

    # The database: one client whose contract value is a canary the index must never hold.
    canary = fresh_canary("ACCEPTANCE")
    name = f"Acceptance {h.word()}"
    client_id = 900_000 + secrets.randbelow(99_999)
    views = _Views(
        clients=(
            {
                "id": client_id,
                "contract_value": canary,
                "department": A,
                "manager_id": 1,
                "name": name,
                "status": "active",
                "updated_at": datetime(2019, 3, 1, 10, 0),
            },
        ),
        users=(
            {
                "id": client_id,
                "department": A,
                "display_name": f"Acceptance {h.word()}",
                "status": "active",
                "updated_at": datetime(2019, 3, 1, 10, 0),
            },
        ),
    )
    reading = laravel.LaravelReading(views.opener)
    settings = {
        laravel.SCHEMA_SETTING: SCHEMA,
        laravel.HOST_SETTING: HOST,
        laravel.PORT_SETTING: str(laravel.MYSQL_PORT),
        laravel.PRIVATE_NETWORK_SETTING: "no",
        laravel.TLS_SETTING: laravel.VERIFY_WORD,
        laravel.CLIENT_RULE_SETTING: f"department = {A}",
        laravel.USER_RULE_SETTING: f"department = {A}",
        laravel.MAX_ROWS_SETTING: str(MAX_ROWS),
        laravel.TIMEOUT_SETTING: "5",
    }
    connection = _connection(h, laravel.CONNECTOR_NAME, settings)
    await _connect_and_read(h, connection, reading)

    kept = (
        await h.execute(
            select(ProjectedRecordRow.entity, ProjectedRecordRow.fields).where(
                ProjectedRecordRow.source == laravel.CONNECTOR_NAME,
                ProjectedRecordRow.source_id == str(client_id),
            )
        )
    ).all()
    fields = {str(entity): dict(one) for entity, one in kept}
    if set(fields) != set(laravel.ENTITIES):
        raise CheckFailedError("proj.record did not hold the client and the staff record read")
    for entity, one in fields.items():
        declared = {each.name for each in laravel.PROJECTED_FIELDS[entity]}
        if set(one) != declared or one.get("department") != A:
            raise CheckFailedError("proj.record kept other than the view's index and its rule")

    # What the answer route builds, by its own functions, over the check's transaction.
    rules = await connected_questions_of(state)
    if laravel.CONNECTOR_NAME not in {rule.source for rule in rules}:
        raise CheckFailedError("the connected database contributed no question shapes to Ask")
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    readers = row_readers(registry)
    if (laravel.CONNECTOR_NAME, laravel.ENTITY_CLIENT) not in readers:
        raise CheckFailedError("the application registered no reader for the connected database")
    declared_here = {
        laravel.CONNECTOR_NAME: replace(laravel.CONNECTOR, reading=reading),
    }

    async def connected() -> Any:
        return ConnectedSources(
            {laravel.CONNECTOR_NAME: connection},
            keys=_Logins(),
            caller=_NoCall(),
            resolver=_Resolver(),
            clock=lambda: h.now,
            declarations=declared_here,
        )

    live_records = SourceRecords(connected=connected, clock=lambda: h.now)

    async def ask(principal_id: str, field_name: str, slot: str) -> Answered:
        person = await StoredPrincipals(h.sessions).live_principal(principal_id)
        if person is None:
            raise CheckFailedError("a reserved person was not live in the directory")
        reach: EntitlementSet = await _console(h, principal_id, second_factor=False)
        return await answer_lane(
            QUESTION_SHAPES[0].format(label=label_of(field_name), slot=slot),
            origin=Origin(trace_id=h.trace_id, principal=person, channel=Channel.CONSOLE),
            recorders=(),
            rules=rules,
            readers=readers,
            entitlement=reach,
            policies=field_policies(registry),
            reachable_sources=covered_at(registry, reach, h.now),
            sink=CountingTraceSink(),
            now=h.now,
            clock=lambda: h.now,
            live=live_records,
            source_policies=source_field_policies(registry),
        )

    reads = ("read:laravel_client", "read:laravel_client.name", "read:laravel_client.status")
    finance, sales = h.principal(A, "finance"), h.principal(A, "sales")
    await h.person(
        finance,
        department=A,
        grants=tuple(
            (one, Scope.department(A)) for one in (*reads, "read:laravel_client.contract_value")
        ),
    )
    await h.person(sales, department=A, grants=tuple((one, Scope.department(A)) for one in reads))

    # The contract value, read live from the view while the reader waits.
    before = len(views.selected)
    told = await ask(finance, "contract_value", name)
    if told.composed is None or canary not in _prose(told):
        raise CheckFailedError(
            "a client's contract value was not read live for a reader granted it"
        )
    narrowed = views.selected[before:]
    if not narrowed or any(
        not isinstance(args, tuple) or str(client_id) not in args for _, args in narrowed
    ):
        raise CheckFailedError("the live read was not narrowed to the client asked about")

    # A reader not granted it is told what a client nobody has tells them.
    withheld = await ask(sales, "contract_value", name)
    nobody = await ask(sales, "contract_value", f"Acceptance {h.word()}")
    if canary in _prose(withheld) or withheld.composed is not None:
        raise CheckFailedError("a client's contract value was told to a reader not granted it")
    if _prose(withheld) != _prose(nobody):
        raise CheckFailedError("a withheld contract value was told apart from a client not there")

    # Every read carried the connection's row cap as its limit, bound in the statement.
    if any(
        not query.rstrip().endswith("LIMIT %s")
        or not isinstance(args, tuple)
        or args[-1] != MAX_ROWS
        for query, args in views.selected
    ):
        raise CheckFailedError("a read of the database did not carry the row cap as its limit")

    # Nothing a live read returned was kept anywhere.
    if await _search(h, canary):
        raise CheckFailedError("a contract value read live was found in a table")
