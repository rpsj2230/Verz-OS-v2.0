"""A Lark Base switched on in Connect Lark: where it is, how it is read, and its minimal index.

Connect Lark keeps the Lark app's credential in the `lark_base` vault slot and records which Base
and which platform as installation settings (`brain.ops.lark_connect`). It registers no connection
for the sync worker, on purpose: a Base is read by its own schema, table by table, and the worker's
connection rows name one declaration each. Until this module nothing read those settings, so a
Base switched on answered no question. `brain.connectors.lark_base` held every rule about reading a
Base (the budget of a hundred calls a minute, the envelopes, the field kinds, the minimal index)
and nothing called it.

**What is switched on is read from the installation values, in one place.** `switched_on` answers
the Base's id and its platform's host when `INSTALL_LARK_USES` names knowledge from Base, and None
otherwise, so every reader (the worker's index, the answer route's lane, the live read) asks the
same question the same way and a Base switched off is read by nothing from the next question.

**The index is the connector's own minimal index and nothing more.** Each table the Base lists is
bound by its own schema (`lark_base.bindings_for`): the primary field is the one label kept, the
first modified time the one timestamp, and every other readable field is read live when a question
asks for it and never stored. The rows go through `brain.ops.connector_sync.kept_fields` and
`record_upsert`, the sync's own two functions, so a Lark row is held to exactly the rules a Xero
row is. See `A_BASE_IS_INDEXED_AND_NEVER_COPIED`.

**Who may read a row is a grant on this install, and the index registers the words for it.**
`lark_base.A_SHARING_SETTING_IS_NOT_A_PERMISSION_MODEL` argues that a Base's own sharing is a list
Lark holds and `base:record:read` cannot read, so the one fact this install can state about a row
is which Base it came from: that is the visibility predicate every kept row carries
(`A_BASE_ROW_IS_SCOPED_BY_ITS_BASE`). Reading a table is then `read:lark_<table>` and its fields
`read:lark_<table>.<field>`, granted by an administrator, and each run registers the table's two
capabilities in `gate.capability_registry` under the table's own title, so the grants screen can
offer them (`A_TABLE_S_GRANT_IS_OFFERED_BY_ITS_TITLE`).

**Every call spends the run's share of the tenant's minute.** The schema reads and the page reads
each spend a `lark_base.MinuteBudget` before they are made, and a run that spends it stops and says
so; the next run reads again from the start. See
`lark_base.ONE_QUESTION_MUST_NOT_SPEND_THE_COMPANYS_MINUTE`.

**The token is the app's own, exchanged for each run and never kept.** The slot holds the app's id
and secret, leased for the run by the same `ConnectorKeys` a connected source's run borrows its key
through (needs-rupash 99); each run exchanges them for a tenant token at Lark's documented address,
uses it for that run's reads and drops it, and the lease is given back when the run ends. Rejected:
holding a token between runs, which is a credential kept somewhere the vault does not govern.

Nothing here imports `brain.knowledge`, which `tests/invariants/test_minimal_index.py` holds: this
module is on the sync worker's path, and that path hands nothing to the knowledge corpus.

Task ids: M11.6.3
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Protocol

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors import lark_base
from brain.connectors.contract import AccessMode, ConnectorContractError, CredentialBinding
from brain.connectors.lark_base import (
    FIELDS_PATH,
    LARK_BASE,
    LARK_HOSTS,
    PAGE_SIZE,
    TABLES_PATH,
    Endpoint,
    LarkBaseBudgetError,
    LarkBaseRefusedError,
    LarkBaseTable,
    LarkBaseUnreachableError,
    LarkReply,
    MinuteBudget,
    PageCursor,
    SchemaRequest,
    arguments_for,
)
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.projection import ProjectedRecord
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.staff_directories import LARK_PLATFORMS
from brain.connectors.transports import TransportError
from brain.core.entitlement import Capability
from brain.core.projection import MAX_LABEL_CHARS
from brain.core.scope import Clause, Op, Scope
from brain.install import value_of
from brain.ops.connectable import key_reference
from brain.ops.connector_sync import kept_fields
from brain.ops.connector_sync_store import record_upsert
from brain.ops.secrets import SecretsUnavailableError
from brain.tables.projection import ProjectedRecordRow
from brain.tools.fetch import Resolver, assert_fetchable

if TYPE_CHECKING:
    from brain.ops.connector_sync_run import ConnectorKeys
    from brain.ops.starter import Declared

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the Base's id is the visibility predicate on every kept row.
A_BASE_ROW_IS_SCOPED_BY_ITS_BASE: Final = (
    "A Base's own sharing is a list Lark holds and base:record:read cannot read, so no predicate "
    "about people can be taken from it. The one fact this install can state about a Lark row is "
    "which Base it came from, and a grant naming that Base is the administrator's decision about "
    "who reads it; a row with no predicate would be refused by manifest review as a copy nobody "
    "scoped."
)

#: Why the index keeps a table's label and time and nothing else.
A_BASE_IS_INDEXED_AND_NEVER_COPIED: Final = (
    "The index keeps what finding a record takes: its id, the table's primary field as its one "
    "label and its first modified time. Every other value is read from Lark by the record's id "
    "when a question asks for it, at the asker's reach, and is never written here. A Base copied "
    "whole would be the bulk sync the owner has ruled out, and a copy that answers is a copy "
    "that is out of date the moment somebody edits the Base."
)

#: Why each run registers the table's capabilities under its title.
A_TABLE_S_GRANT_IS_OFFERED_BY_ITS_TITLE: Final = (
    "A grant can name only a capability in the registry, and a table's capability is named by "
    "its Lark id, which nobody would recognise. So each run registers read:lark_<table> and "
    "read:lark_<table>.* with the table's own title in the description, and the grants screen "
    "offers them in words. Registering is not granting: nobody reads a table until an "
    "administrator grants it."
)

__all__ = [
    "A_BASE_IS_INDEXED_AND_NEVER_COPIED",
    "A_BASE_ROW_IS_SCOPED_BY_ITS_BASE",
    "A_TABLE_S_GRANT_IS_OFFERED_BY_ITS_TITLE",
]

# The sentences a run that read nothing leaves. Constant, and naming no Base and no table.
NO_KEY_FOR_THE_BASE: Final = "the Lark app's key could not be borrowed for this run"
NO_TOKEN_FOR_THE_BASE: Final = "Lark did not exchange the kept key for a token"  # noqa: S105
LARK_DID_NOT_ANSWER: Final = "Lark did not answer, or refused, a read of the Base"

# ------------------------------------------------------------------------ the figures
#: The use Connect Lark names knowledge from Base by. Restated from `brain.ops.lark_connect.Use`,
#: which imports the routes' world, and held equal to it by a test.
LARK_BASE_USE: Final = "knowledge_base"

#: The field every kept Lark row carries its Base's id under.
BASE_ID_FIELD: Final = "base_id"

#: Where a Lark app exchanges its id and secret for a tenant token, as Lark documents it.
#: An address, not a secret: the word in it is Lark's name for what the exchange returns.
TOKEN_PATH: Final = "/open-apis/auth/v3/tenant_access_token/internal"  # noqa: S105

#: How long one token exchange may take before the run reads nothing.
TOKEN_TIMEOUT_SECONDS: Final = 10.0

#: How often the worker reads a switched-on Base's index again. Half an hour, because the index is
#: only what finding a record takes: a value is read from Lark when it is asked for, so the index
#: ages in which records exist and what they are called, and a new record is findable within it.
INDEX_EVERY: Final = timedelta(minutes=30)


# ------------------------------------------------------------------------ switched on
@dataclass(frozen=True)
class LarkBaseUse:
    """One Base switched on: its id and the host of the platform its tenant is on."""

    base_id: str
    host: str

    def visibility(self) -> Scope:
        """Every kept row's predicate. See `A_BASE_ROW_IS_SCOPED_BY_ITS_BASE`."""
        return Scope(clauses=(Clause(field=BASE_ID_FIELD, op=Op.EQ, value=self.base_id),))

    def credential(self) -> CredentialBinding:
        """The app's credential by reference, read-only, in the slot Connect Lark keeps it in."""
        return CredentialBinding(ref=key_reference(LARK_BASE), mode=AccessMode.READ_ONLY)

    def manifest(self, table: LarkBaseTable) -> ConnectorManifest:
        """What one table declares, as `lark_base.manifest` builds it for this install."""
        return lark_base.manifest(
            table, host=self.host, credential=self.credential(), visibility=self.visibility()
        )


def switched_on(read: Callable[[str], str] = value_of) -> LarkBaseUse | None:
    """The Base Connect Lark switched on, or None when knowledge from Base is off or unset.

    `read` is `brain.install.value_of`, the one reader of installation values, so a Base saved on
    the console is read by the next question without a restart.
    """
    uses = {one.strip() for one in read("INSTALL_LARK_USES").split(",")}
    if LARK_BASE_USE not in uses:
        return None
    base_id = read("INSTALL_LARK_BASE").strip()
    platform = read("INSTALL_LARK_PLATFORM").strip().lower()
    if platform not in LARK_PLATFORMS or not base_id:
        return None
    try:
        SchemaRequest(base_id=base_id)
    except ConnectorContractError:
        return None
    return LarkBaseUse(base_id=base_id, host=LARK_PLATFORMS[platform][1])


# --------------------------------------------------------------------------- the token
class TokenIssuer(Protocol):
    """Whatever exchanges the app's id and secret for a tenant token at `TOKEN_PATH`."""

    def issue(self, host: str, *, app_id: str, app_secret: str) -> str | None:
        """The tenant token, or None when Lark refused or could not be reached."""
        ...


def token_from(status: int, body: Any) -> str | None:
    """The tenant token an exchange answered with, or None for anything else.

    Lark answers a refused exchange with a 200 and a non-zero `code`, so the code is read before
    the token, for the reason `lark_base.assert_lark_answered` reads it first.
    """
    if status != 200 or not isinstance(body, Mapping) or body.get("code") != 0:
        return None
    token = body.get("tenant_access_token")
    return token if isinstance(token, str) and token else None


class HttpsTokenIssuer:
    """`TokenIssuer` over HTTPS, to Lark's own open hosts and nowhere else, following nothing."""

    def __init__(self, *, timeout_seconds: float = TOKEN_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_seconds

    def issue(self, host: str, *, app_id: str, app_secret: str) -> str | None:
        if host not in LARK_HOSTS:
            return None
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
                answer = client.post(
                    f"https://{host}{TOKEN_PATH}",
                    json={"app_id": app_id, "app_secret": app_secret},
                )
            body = answer.json()
        except (httpx.HTTPError, ValueError):
            return None
        return token_from(answer.status_code, body)


def app_credential(kept: str) -> tuple[str, str] | None:
    """The app's id and secret out of the value Connect Lark keeps, or None for another shape."""
    from brain.ops.staff_sync_run import CredentialRefusedError, client_credential

    try:
        return client_credential(kept)
    except CredentialRefusedError:
        return None


# --------------------------------------------------------------------------- the calls
class LarkCaller(Protocol):
    """One GET to a checked address, answered with what came back. See `SourceCaller`."""

    def get(self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int) -> Any:
        """A `brain.ops.connector_sync_run.SourceAnswer`."""
        ...


def _reply(answer: Any) -> LarkReply:
    """A caller's answer as the value `lark_base` reads. An unreadable body is no body."""
    if answer.timed_out or answer.connection_failed or answer.status is None:
        # `lark_base.assert_lark_answered` reads a 503 as unreachable, which this was.
        return LarkReply(status=503, headers={}, body=None)
    try:
        body = json.loads(answer.body) if answer.body else None
    except ValueError:
        body = None
    return LarkReply(status=answer.status, headers=dict(answer.headers or {}), body=body)


@dataclass
class LarkReads:
    """`lark_base.SchemaReader` and a `RecordReader` per table, over one run's token.

    Every address is checked by `brain.tools.fetch.assert_fetchable` before anything connects,
    and the token goes into one header of each call and nowhere else.
    """

    use: LarkBaseUse
    caller: LarkCaller
    resolver: Resolver
    token: str = field(repr=False)

    def _get(self, url: str) -> LarkReply:
        checked = assert_fetchable(url, self.resolver)
        answer = self.caller.get(
            checked.url,
            address=checked.address,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            max_bytes=MAX_RESPONSE_BYTES,
        )
        return _reply(answer)

    def _listing(self, path: str, continuation: str) -> str:
        query = f"page_size={PAGE_SIZE}"
        if continuation:
            query += f"&page_token={continuation}"
        return f"https://{self.use.host}{path}?{query}"

    def list_tables(self, request: SchemaRequest) -> LarkReply:
        path = TABLES_PATH.format(app_token=request.base_id)
        return self._get(self._listing(path, request.continuation))

    def list_fields(self, request: SchemaRequest) -> LarkReply:
        path = FIELDS_PATH.format(app_token=request.base_id, table_id=request.table_id)
        return self._get(self._listing(path, request.continuation))

    def records(self, table: LarkBaseTable, endpoint: Endpoint) -> TableReader:
        return TableReader(reads=self, table=table, endpoint=endpoint)


@dataclass
class TableReader:
    """`lark_base.RecordReader` for one table and one endpoint, over the run's reads."""

    reads: LarkReads
    table: LarkBaseTable
    endpoint: Endpoint

    def read(self, cursor: PageCursor) -> LarkReply:
        operation = self.table.operation(self.endpoint, host=self.reads.use.host)
        return self.reads._get(operation.url_for(arguments_for(self.table, cursor)))


@contextmanager
def opened(
    use: LarkBaseUse,
    *,
    keys: ConnectorKeys,
    caller: LarkCaller,
    resolver: Resolver,
    issuer: TokenIssuer,
    now: datetime,
) -> Iterator[LarkReads | str]:
    """The run's reads over a token exchanged for it, or the sentence saying why there are none.

    The key is leased for the run and given back when the block ends, whatever happened inside
    it, which is `brain.ops.live_read_run.A_QUESTION_BORROWS_A_KEY_FOR_ONE_READ` for a Base.
    """
    lease = keys.lease(use.credential().ref, now=now)
    try:
        try:
            kept = lease.key()
        except SecretsUnavailableError:
            yield NO_KEY_FOR_THE_BASE
            return
        pair = app_credential(kept)
        token = None if pair is None else issuer.issue(use.host, app_id=pair[0], app_secret=pair[1])
        if token is None:
            yield NO_TOKEN_FOR_THE_BASE
            return
        yield LarkReads(use=use, caller=caller, resolver=resolver, token=token)
    finally:
        lease.close(now)


# ------------------------------------------------------------------------ the schema
@dataclass(frozen=True)
class KnownTable:
    """One table of the Base as its own schema binds it, with the title a person knows it by."""

    table: LarkBaseTable
    title: str

    @property
    def entity(self) -> str:
        return self.table.entity

    def named(self) -> str:
        """What a person calls it: its title, or its id where it has none."""
        return self.title.strip() or self.table.table_id


def discovered(
    reads: LarkReads, *, budget: MinuteBudget
) -> tuple[tuple[KnownTable, ...], MinuteBudget]:
    """Every table of the Base this install can read, each bound by its own schema, in budget.

    A table whose every field is a link, a person or an attachment binds nothing and is left out:
    `lark_base.DiscoveredTable.table`'s reason.
    """
    listed, spent = lark_base.read_tables(reads, reads.use.base_id, budget=budget)
    tables: list[KnownTable] = []
    for one in listed:
        described, spent = lark_base.read_table(reads, reads.use.base_id, one, budget=spent)
        table = described.table(reads.use.base_id)
        if table is not None:
            tables.append(KnownTable(table=table, title=described.title))
    return tuple(tables), spent


def tables_named(tables: Sequence[KnownTable]) -> Mapping[str, KnownTable]:
    """The tables by their entity tag, as the answer lane and the live read look them up."""
    return {one.entity: one for one in tables}


def vocabulary_of(tables: Sequence[KnownTable]) -> tuple[Declared, ...]:
    """Each table's two capabilities in words. See `A_TABLE_S_GRANT_IS_OFFERED_BY_ITS_TITLE`."""
    from brain.ops.starter import Declared

    words: list[Declared] = []
    for one in tables:
        words.append(
            Declared(
                capability=Capability(value=f"read:{one.entity}"),
                description=(
                    f"Find records in the Lark Base table {one.named()!r} by their name. The "
                    "values are a further grant."
                ),
            )
        )
        words.append(
            Declared(
                capability=Capability(value=f"read:{one.entity}.*"),
                description=(
                    f"Read every field of a record in the Lark Base table {one.named()!r}, read "
                    "from Lark when a question asks for it."
                ),
            )
        )
    return tuple(words)


# ----------------------------------------------------------------------- the index
@dataclass(frozen=True)
class IndexRun:
    """What one index run did: tables and rows kept, or why it read nothing."""

    tables: int = 0
    kept: int = 0
    stopped_short: bool = False
    not_due: bool = False
    unread: str = ""

    def summary(self) -> str:
        """One line for the connector sync's control record. Names no Base and no table."""
        if self.unread:
            return f"the Lark Base was not read: {self.unread}"
        if self.not_due:
            return "the Lark Base is not yet due"
        cut = ", cut short by its share of the minute" if self.stopped_short else ""
        return f"the Lark Base read: {self.kept} record(s) in {self.tables} table(s){cut}"


def projected(table: LarkBaseTable, record: Any, *, seen_at: datetime) -> ProjectedRecord:
    """One record `read_records` decoded, as its minimal index entry: the projected fields only."""
    fields = record.model_dump(exclude={"entity", "id"})
    return ProjectedRecord(
        source=LARK_BASE,
        entity=table.entity,
        source_id=str(record.id),
        last_seen_at=seen_at,
        fields={
            binding.target: (
                fields[binding.target][:MAX_LABEL_CHARS]
                if isinstance(fields.get(binding.target), str)
                else fields[binding.target]
            )
            for binding in table.projected_bindings()
            if fields.get(binding.target) is not None
        },
    )


async def index_base(
    use: LarkBaseUse,
    reads: LarkReads,
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    budget: MinuteBudget,
) -> IndexRun:
    """Keep every readable table's minimal index, in the run's share of the minute.

    Each table's pages are read by `lark_base.read_records`, each record kept through the sync's
    own `kept_fields` and `record_upsert`, so a Lark row meets the rules every other source's does.
    A run the budget stops keeps what it read and says so.
    """
    from brain.ops.starter_store import register

    known, spent = discovered(reads, budget=budget)
    words = vocabulary_of(known)
    if words:
        async with sessions() as session, session.begin():
            await session.execute(register(words))
    kept = 0
    stopped = False
    for one in known:
        table = one.table
        if not table.projected_bindings() or spent.is_exhausted:
            stopped = stopped or spent.is_exhausted
            continue
        manifest = use.manifest(table)
        reading = lark_base.read_records(
            table,
            table.operation(Endpoint.LIST_RECORDS, host=use.host),
            reads.records(table, Endpoint.LIST_RECORDS),
            fetched_at=now.isoformat(),
            budget=spent,
        )
        spent = reading.budget
        stopped = stopped or reading.stopped_for_budget
        async with sessions() as session, session.begin():
            for record in reading.result.records:
                entry = projected(table, record, seen_at=now)
                await session.execute(record_upsert(entry, kept_fields(entry, manifest)))
                kept += 1
    return IndexRun(tables=len(known), kept=kept, stopped_short=stopped)


def newest_read(use: LarkBaseUse) -> Any:
    """When this Base's index was last read: its newest row's last read, or NULL with none."""
    return select(func.max(ProjectedRecordRow.last_seen_at)).where(
        ProjectedRecordRow.source == LARK_BASE,
        ProjectedRecordRow.deleted_at.is_(None),
        ProjectedRecordRow.fields[BASE_ID_FIELD].astext == use.base_id,
    )


async def index_if_due(
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    keys: ConnectorKeys,
    caller: LarkCaller,
    resolver: Resolver,
    issuer: TokenIssuer,
    read: Callable[[str], str] = value_of,
) -> IndexRun | None:
    """The switched-on Base's index read again when it is due, or None with no Base switched on.

    Due when its newest row was read `INDEX_EVERY` ago or longer, or it has none, so no state is
    kept about the index beyond the index itself. A Lark that does not answer, refuses, or answers
    in a shape this does not read is a run that read nothing and says so in a constant sentence.
    """
    use = switched_on(read)
    if use is None:
        return None
    async with sessions() as session:
        newest = (await session.execute(newest_read(use))).scalar_one_or_none()
    if isinstance(newest, datetime) and now - newest < INDEX_EVERY:
        return IndexRun(not_due=True)
    with opened(use, keys=keys, caller=caller, resolver=resolver, issuer=issuer, now=now) as reads:
        if isinstance(reads, str):
            return IndexRun(unread=reads)
        try:
            return await index_base(
                use, reads, sessions, now=now, budget=lark_base.fair_share_budget()
            )
        except (
            LarkBaseUnreachableError,
            LarkBaseRefusedError,
            LarkBaseBudgetError,
            ConnectorContractError,
            TransportError,
        ) as failed:
            log.warning("lark_base.index_unread", error=type(failed).__name__)
            return IndexRun(unread=LARK_DID_NOT_ANSWER)
