"""The install acceptance checks for how a connected source's changes reach the install.

Four checks, one to a leaf, each driving the worker's own read, `brain.ops.connector_sync_run.
attempt`, over a source connected inside the check's transaction and read through the sync state the
worker keeps (`brain.ops.connector_sync_store.read_states`), so every second read is planned from
what the first left in the database and not from a value the check handed it. A read of what changed
(M11.4.6), a read cut short and carried on (M11.4.8), a source's epoch in the answer cache's key
(M11.8.4), and a record the source dropped and returned (M11.8.11).

**No check calls a source, reads the vault or holds a real key**, for
`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`: every answer is written
here in the envelope the source documents, Freshdesk's bare array of tickets and Xero's `Invoices`
object, and handed back by a caller that opens no socket; the key is minted for the check.

**Freshdesk for the first three, because it is the source this release can ask for only what
changed**: its list takes `updated_since` (`brain.connectors.freshdesk.FreshdeskReading.
changed_since`). **Xero for the fourth, because every Xero read is a read of everything**, which is
the one kind that may retire a record (`brain.ops.connector_sync.
WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED`). Both are read with a verified
ceiling on every install.

**Each check connects its source, so each steps aside where the install has that source
connected.** Connecting it again is refused, and a check advancing the epoch of a source the
worker is reading would hold that source's epoch row locked for the length of the check. See
`A_CONNECTED_SOURCE_IS_NOT_READ_BY_A_CHECK`.

**The epoch is in the database, so the epoch check runs without a cache.** The answer store it
stores into and looks up in is a dictionary of the check's own behind the product's protocol, and
the key is built by `brain.gate.cache_key.key_for` from `brain.api_routes.caching_of`, which is what
the answer route builds it from.

**A retired row is read as the worker's login**, because the application's role cannot see one
(`0045`), for the reason `brain.ops.acceptance_checks_connectors.
A_SEARCH_THAT_CANNOT_SEE_EVERY_ROW_IS_NOT_RUN` gives; a run by a login that cannot see it says the
check was not run.

**A read of everything retires, inside the check's transaction, every live row of its source and
entity the read did not see**, which on an install with rows of that source includes rows the
check did not write. They are retired only in a transaction that is rolled back, so no reader ever
sees them go; what it costs is their row locks for the length of the check, which is why the check
is not run where the source is connected and a worker could be writing them.

Task ids: M38.5.1, M11.4.6, M11.4.8, M11.8.4, M11.8.11
"""

from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import (
    _clock,
    _Keys,
    _no_wait,
    _nothing_kept,
    _Resolver,
)
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from brain.gate.cache_key import CachedAnswer
    from brain.ops.connector_sync import Attempt, SyncState
    from brain.ops.connector_sync_run import SourceAnswer
    from brain.ops.connector_sync_store import LiveConnection

# ------------------------------------------------------------------ written-down reasons
#: Why a check whose source the install has connected is not run.
A_CONNECTED_SOURCE_IS_NOT_READ_BY_A_CHECK: Final = (
    "Each check connects the source it reads inside its own transaction. Where this install has "
    "that source connected, connecting it again is refused, and the worker reading the real "
    "connection would wait on the source's epoch row for as long as the check held it, so the "
    "check is not run."
)

#: What a check says when the install has its source connected already.
SOURCE_CONNECTED_ALREADY: Final = (
    "this install has the source the check reads connected already, so the check does not "
    "connect it again"
)

#: What the retirement check says when its login cannot see a retired row.
RETIRED_ROWS_ARE_OUT_OF_SIGHT: Final = (
    "this run's database login cannot see a retired row, so when a record was noticed gone could "
    "not be read; the worker's run can"
)

# ------------------------------------------------------------------------ the figures
#: The two sources, by name. See the module docstring.
HELPDESK: Final = "freshdesk"
LEDGER: Final = "xero"

#: The question an answer is cached under. Not a volatile shape, so it is cached at all.
QUESTION: Final = "Which helpdesk ticket did the acceptance check read?"

#: The reach hash and agent configuration an answer is cached under: the check's, and nobody's.
CACHED_FOR: Final = SET_UP_REACH
AGENT_CONFIGURATION: Final = "acceptance-change-signals"


# ------------------------------------------------------------------------ the helpers
@dataclass
class _Listing:
    """`SourceCaller` answering Freshdesk's ticket list page by page, and nothing else. No socket.

    `pages` is what each page number holds, in Freshdesk's envelope: the array itself. `headers`
    is what a page's answer carries besides, such as the allowance the source says is left.
    """

    pages: Mapping[int, Sequence[Mapping[str, Any]]]
    headers: Mapping[int, Mapping[str, str]] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        self.asked.append(url)
        page = int(_query(url).get("page", "1"))
        body = json.dumps(list(self.pages.get(page, ()))).encode("utf-8")
        return SourceAnswer(status=200, headers=dict(self.headers.get(page, {})), body=body)

    def queries(self) -> list[dict[str, str]]:
        return [_query(url) for url in self.asked]


@dataclass
class _Ledger:
    """`SourceCaller` answering Xero's Invoices with these invoices and its Contacts with none."""

    invoices: Sequence[Mapping[str, str]]
    asked: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        self.asked.append(url)
        if "/Invoices" in url:
            body = {"Invoices": list(self.invoices)}
        elif "/Contacts" in url:
            body = {"Contacts": []}
        else:
            return SourceAnswer(status=404, headers={}, body=b"{}")
        return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode("utf-8"))


@dataclass
class _Answers:
    """`brain.gate.answer_cache.AnswerStore` over a dictionary of the check's own."""

    held: dict[str, CachedAnswer] = field(default_factory=dict)

    def get(self, key: str) -> CachedAnswer | None:
        return self.held.get(key)

    def set(self, key: str, value: CachedAnswer, ttl_seconds: int) -> None:
        del ttl_seconds
        self.held[key] = value


def _query(url: str) -> dict[str, str]:
    """One call's query, one value to a name."""
    return {name: values[-1] for name, values in parse_qs(urlsplit(url).query).items()}


def _ticket(number: int, *, status: int = 2) -> dict[str, Any]:
    """One ticket as Freshdesk's list writes it, numbered far past any real helpdesk's."""
    return {
        "id": 9_000_000_000 + number,
        "subject": f"Acceptance ticket {number}",
        "status": status,
        "priority": 1,
        "created_at": "2019-03-06T09:00:00Z",
        "updated_at": "2019-03-06T09:00:00Z",
    }


def _invoice(record_id: str) -> dict[str, str]:
    """One invoice as Xero's Invoices endpoint writes it."""
    return {"InvoiceID": record_id, "InvoiceNumber": "ACC-1", "Status": "AUTHORISED"}


def _helpdesk_settings() -> dict[str, str]:
    """A helpdesk made up for the run, read by the first reserved department."""
    return {
        "domain": f"acceptance-{secrets.token_hex(4)}.freshdesk.com",
        "department": RESERVED_DEPARTMENTS[0],
    }


async def _connected(h: Harness, name: str, settings: Mapping[str, str]) -> LiveConnection:
    """The source connected as the Connectors route connects it, inside the check's transaction.

    See `A_CONNECTED_SOURCE_IS_NOT_READ_BY_A_CHECK`. No steward is declared for, so connecting
    grants nobody anything, as the framework check connects its source.
    """
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync_store import read_live

    if (await h.execute(live(name))).scalar_one_or_none() is not None:
        raise CheckNotRunError(SOURCE_CONNECTED_ALREADY)
    await StoredConnections(h.sessions).connect(
        connector=name,
        settings=settings,
        digest=manifest_digest(manifest_for(name, settings)),
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=_nothing_kept,
    )
    async with h.sessions() as session, session.begin():
        found = [one for one in await read_live(session) if one.connection.connector == name]
    if len(found) != 1:
        raise CheckFailedError("the worker did not find the source the check connected")
    return found[0]


async def _state(h: Harness, connected: LiveConnection) -> SyncState | None:
    """What the worker reads about the connection before its next attempt."""
    from brain.ops.connector_sync_store import read_states

    async with h.sessions() as session, session.begin():
        return (await read_states(session)).get(connected.id)


async def _read(h: Harness, connected: LiveConnection, caller: Any) -> Attempt:
    """One worker attempt planned from the stored sync state, and its row written as the worker's.

    The plan is asked with no previous attempt, so it is due whatever the last one said about
    waiting: when the next attempt may be made is the schedule's question, and where it reads from
    is this check's.
    """
    from brain.ops.connector_sync import plan_for
    from brain.ops.connector_sync_run import attempt
    from brain.ops.connector_sync_store import attempt_row

    plan = plan_for(connected.connection, last=None, now=h.now)
    if plan.refused or not plan.due:
        raise CheckFailedError("the worker's plan would not read a source connected as declared")
    done = await attempt(
        connected,
        plan,
        previous=await _state(h, connected),
        sessions=h.sessions,
        keys=_Keys(),
        caller=caller,
        resolver=_Resolver(),
        clock=_clock,
        sleep=_no_wait,
    )
    await h.execute(attempt_row(connected.id, done))
    return done


async def _epoch(h: Harness, name: str) -> int:
    """A source's epoch as the answer path reads it, zero for one that never changed."""
    from brain.ops.connector_sync_store import StoredSourceEpochs

    return (await StoredSourceEpochs(h.sessions).epochs()).get(name, 0)


async def _cached(h: Harness, store: _Answers) -> CachedAnswer | None:
    """The check's question looked up as the answer route looks it up, at the epochs now."""
    from types import SimpleNamespace

    from brain.api_routes import caching_of
    from brain.gate.answer_cache import lookup
    from brain.gate.cache_key import key_for
    from brain.ops.connector_sync_store import StoredSourceEpochs

    epochs = await StoredSourceEpochs(h.sessions).epochs()
    caching = caching_of(SimpleNamespace(answer_store=store), {}, (HELPDESK,), epochs)
    if caching is None:
        raise CheckFailedError("the answer route built no cache lookup over an answer store")
    key = key_for(
        QUESTION,
        CACHED_FOR,
        AGENT_CONFIGURATION,
        caching.policy_epoch,
        caching.source_epochs,
        caching.sources,
    )
    return lookup(key, store, _clock())


async def _remember(h: Harness, store: _Answers) -> None:
    """Store an answer to the check's question as the answer route stores one, at the epochs now."""
    from types import SimpleNamespace

    from brain.api_routes import caching_of
    from brain.gate.answer_cache import store_answer
    from brain.ops.connector_sync_store import StoredSourceEpochs

    epochs = await StoredSourceEpochs(h.sessions).epochs()
    caching = caching_of(SimpleNamespace(answer_store=store), {}, (HELPDESK,), epochs)
    if caching is None:
        raise CheckFailedError("the answer route built no cache lookup over an answer store")
    kept = store_answer(
        QUESTION,
        h.word(),
        ent_hash=CACHED_FOR,
        agent_config_hash=AGENT_CONFIGURATION,
        policy_epoch=caching.policy_epoch,
        source_epochs=dict(caching.source_epochs),
        sources=caching.sources,
        store=store,
        now=_clock(),
    )
    if kept is None:
        raise CheckFailedError("the answer cache declined a question it keeps")


async def _now(h: Harness) -> datetime:
    """The database's clock, which is the clock a retirement is stamped by."""
    stamped = (await h.execute(select(func.clock_timestamp()))).scalar_one()
    if not isinstance(stamped, datetime):
        raise CheckFailedError("the database did not say what time it was")
    return stamped


@dataclass(frozen=True)
class _Row:
    """One `proj.record` row of the check's own, as the worker's login sees it."""

    id: str
    source_id: str
    last_seen_at: datetime
    deleted_at: datetime | None


async def _every_row(h: Harness, source_ids: Sequence[str]) -> list[_Row]:
    """These records' rows, retired ones included, read as the worker's login.

    See `RETIRED_ROWS_ARE_OUT_OF_SIGHT`. The role is reset for these statements only, inside the
    check's transaction, as `acceptance_checks_connectors._search` resets it.
    """
    async with AsyncSession(bind=h.connection, join_transaction_mode="create_savepoint") as session:
        await session.execute(text("RESET ROLE"))
        sees = (
            await session.execute(
                text(
                    "SELECT (SELECT r.rolsuper OR r.rolbypassrls FROM pg_catalog.pg_roles AS r"
                    " WHERE r.rolname = current_user)"
                    " OR pg_catalog.pg_get_userbyid(c.relowner) = current_user"
                    " FROM pg_catalog.pg_class AS c WHERE c.oid = 'proj.record'::regclass"
                )
            )
        ).scalar_one()
        if not sees:
            raise CheckNotRunError(RETIRED_ROWS_ARE_OUT_OF_SIGHT)
        found = (
            await session.execute(
                text(
                    "SELECT id::text, source_id, last_seen_at, deleted_at FROM proj.record"
                    " WHERE source = :source AND source_id = ANY(:ids)"
                    " ORDER BY source_id, deleted_at NULLS LAST"
                ).bindparams(source=LEDGER, ids=list(source_ids))
            )
        ).all()
        await session.commit()
    return [
        _Row(id=str(one), source_id=str(two), last_seen_at=three, deleted_at=four)
        for one, two, three, four in found
    ]


async def _handed(h: Harness, tenant: str) -> set[str]:
    """The invoices a reader in the tenant is handed through the row plane the answers read."""
    from brain.connectors import xero
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.field_policy import Classification
    from brain.core.scope import Scope
    from brain.knowledge.columns import ColumnRule, TableClassification
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.rows import RowRequest, RowTool, read_rows

    tool = RowTool(
        source=LEDGER,
        classification=TableClassification(
            entity=xero.ENTITY_INVOICE,
            rules=(
                ColumnRule("tenant_id", Capability(value="read:invoice"), Classification.INTERNAL),
            ),
        ),
        description="Invoices this install keeps from Xero.",
    )
    scope = Scope(clauses=xero.XeroConnection(tenant_id=tenant).visibility().clauses)
    reader = EntitlementSet(
        principal_id=f"{RESERVED_DEPARTMENTS[0]}.reader",
        grants=(Grant(capability=Capability(value="read:invoice"), scope=scope),),
    )
    result = await read_rows(
        tool, RowRequest(), entitlement=reader, records=SessionRowSource(h.sessions), now=h.now
    )
    return {row.id for row in result.records}


# ------------------------------------------------------ 1. only what changed (M11.4.6)
@check(
    leaves=("M11.4.6",),
    sentence=(
        "A Freshdesk helpdesk connected in the check is read from recorded answers from the "
        "beginning, updated_since 2000-01-01, and the next read, planned from the cursor the first "
        "left with the sync state, asks the list only for tickets updated since the first began, "
        "less the five minutes two clocks may disagree by."
    ),
)
async def a_second_read_asks_only_for_what_changed_since_the_first(h: Harness) -> None:
    from brain.connectors.freshdesk import EVERY_TICKET_SINCE, UPDATED_SINCE_FORMAT
    from brain.ops.connector_sync import CURSOR_OVERLAP, READ_TO_THE_END, SyncOutcome

    connected = await _connected(h, HELPDESK, _helpdesk_settings())
    if await _state(h, connected) is not None:
        raise CheckFailedError("a new connection was read as though it had been read before")
    first_asked = _Listing({1: [_ticket(1), _ticket(2)]})
    first = await _read(h, connected, first_asked)
    if first.outcome is not SyncOutcome.SYNCED or first.detail != READ_TO_THE_END:
        raise CheckFailedError("the first read of a new connection was not read to the end")
    if [one.get("updated_since") for one in first_asked.queries()] != [EVERY_TICKET_SINCE]:
        raise CheckFailedError("the first read of a new connection did not ask from the beginning")

    stored = await _state(h, connected)
    cursor = None if stored is None or stored.read_state is None else stored.read_state
    if cursor is None or cursor.changed_since != first.started_at or cursor.walking is not None:
        raise CheckFailedError("the first read's cursor was not kept with the sync state")
    second_asked = _Listing({1: [_ticket(2, status=3)]})
    second = await _read(h, connected, second_asked)
    since = (first.started_at - CURSOR_OVERLAP).astimezone(UTC).strftime(UPDATED_SINCE_FORMAT)
    if [one.get("updated_since") for one in second_asked.queries()] != [since]:
        raise CheckFailedError("the second read did not ask only for what changed since the first")
    if second.outcome is not SyncOutcome.SYNCED or second.detail != READ_TO_THE_END:
        raise CheckFailedError("a read of what changed was not read to the end")
    after = await _state(h, connected)
    if (
        after is None
        or after.read_state is None
        or after.read_state.changed_since != (second.started_at)
    ):
        raise CheckFailedError("a read of what changed did not move the cursor to its own start")


# ---------------------------------------------- 2. carried on, not started again (M11.4.8)
@check(
    leaves=("M11.4.8",),
    sentence=(
        "A Freshdesk read whose first full page of 100 tickets said the helpdesk's allowance was "
        "spent stops there, waits, and is recorded so; the next read asks page 2 and not page 1, "
        "reads to the end, and the 103 tickets are in the index once each."
    ),
)
async def a_read_cut_short_carries_on_where_it_stopped(h: Harness) -> None:
    from brain.connectors.freshdesk import EVERY_TICKET_SINCE, REMAINING_HEADER
    from brain.ops.connector_sync import READ_TO_THE_END, SOURCE_ALLOWANCE_REFUSED, SyncOutcome
    from brain.tables.projection import ProjectedRecordRow

    connected = await _connected(h, HELPDESK, _helpdesk_settings())
    pages = {1: [_ticket(n) for n in range(100)], 2: [_ticket(n) for n in range(100, 103)]}
    spent = {1: {REMAINING_HEADER: "0"}}
    first_asked = _Listing(pages, headers=spent)
    first = await _read(h, connected, first_asked)
    if first.outcome is not SyncOutcome.QUOTA or first.detail != SOURCE_ALLOWANCE_REFUSED:
        raise CheckFailedError("a read the source's allowance stopped was not recorded as waiting")
    if [one.get("page") for one in first_asked.queries()] != ["1"]:
        raise CheckFailedError(
            "a read went on asking after the source said its allowance was spent"
        )
    if first.next_attempt_at <= first.finished_at:
        raise CheckFailedError("a read the source's allowance stopped was not made to wait")

    second_asked = _Listing(pages)
    second = await _read(h, connected, second_asked)
    asked = second_asked.queries()
    if [one.get("page") for one in asked] != ["2"]:
        raise CheckFailedError("the next read did not carry on from the page the last one stopped")
    if [one.get("updated_since") for one in asked] != [EVERY_TICKET_SINCE]:
        raise CheckFailedError("a read carried on asked for other than the read it carried on")
    if second.outcome is not SyncOutcome.SYNCED or second.detail != READ_TO_THE_END:
        raise CheckFailedError("a read carried on was not read to the end")
    ids = [str(one["id"]) for page in pages.values() for one in page]
    held = (
        await h.execute(
            select(func.count()).where(
                ProjectedRecordRow.source == HELPDESK,
                ProjectedRecordRow.source_id.in_(ids),
                ProjectedRecordRow.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    if held != len(ids):
        raise CheckFailedError("a read carried on did not leave every ticket in the index once")


# -------------------------------------------- 3. the epoch and the cached answer (M11.8.4)
@check(
    leaves=("M11.8.4",),
    sentence=(
        "Recorded Freshdesk reads in the check: a first read writing two tickets advances the "
        "helpdesk's epoch, an answer cached under it is still found after a read that changed "
        "nothing and moved no epoch, and is not found after a read that changed one ticket's "
        "status and advanced it."
    ),
)
async def a_changed_read_moves_the_epoch_and_the_cached_answer_goes(
    h: Harness,
) -> None:
    connected = await _connected(h, HELPDESK, _helpdesk_settings())
    before = await _epoch(h, HELPDESK)
    await _read(h, connected, _Listing({1: [_ticket(1), _ticket(2)]}))
    written = await _epoch(h, HELPDESK)
    if written <= before:
        raise CheckFailedError("a read that wrote new records left its source's epoch where it was")

    store = _Answers()
    await _remember(h, store)
    if await _cached(h, store) is None:
        raise CheckFailedError("an answer cached under the source's epoch was not found again")
    await _read(h, connected, _Listing({1: [_ticket(1), _ticket(2)]}))
    if await _epoch(h, HELPDESK) != written:
        raise CheckFailedError("a read that changed nothing moved its source's epoch")
    if await _cached(h, store) is None:
        raise CheckFailedError("a cached answer was lost to a read that changed nothing")

    await _read(h, connected, _Listing({1: [_ticket(1, status=4), _ticket(2)]}))
    if await _epoch(h, HELPDESK) <= written:
        raise CheckFailedError("a read that changed a record left its source's epoch where it was")
    if await _cached(h, store) is not None:
        raise CheckFailedError("a cached answer was found after its source changed")


# ------------------------------------------- 4. dropped, withheld, returned (M11.8.11)
@check(
    leaves=("M11.8.11",),
    sentence=(
        "Recorded Xero reads of everything in the check: an invoice the second read no longer "
        "returns is retired with the instant it was noticed and handed to no reader of its tenant, "
        "and when the third read returns it again it is a new live row handed to the reader while "
        "the retired row keeps its retirement."
    ),
)
async def a_dropped_record_is_retired_withheld_and_returned_as_a_new_row(
    h: Harness,
) -> None:
    from brain.ops.acceptance_checks_connectors import _settings
    from brain.ops.connector_sync import READ_TO_THE_END, SyncOutcome

    settings = _settings()
    tenant = settings["tenant_id"]
    connected = await _connected(h, LEDGER, settings)
    kept, dropped = str(uuid.uuid4()), str(uuid.uuid4())
    for held in ((kept, dropped), (kept,)):
        started = await _now(h)
        done = await _read(h, connected, _Ledger([_invoice(one) for one in held]))
        if done.outcome is not SyncOutcome.SYNCED or done.detail != READ_TO_THE_END:
            raise CheckFailedError("a read of everything was not read to the end")
    noticed_by = await _now(h)
    rows = await _every_row(h, (kept, dropped))
    gone = [one for one in rows if one.source_id == dropped]
    if len(gone) != 1 or gone[0].deleted_at is None:
        raise CheckFailedError("a record a read of everything no longer returned was not retired")
    retired = gone[0]
    if retired.deleted_at is None or not started <= retired.deleted_at <= noticed_by:
        raise CheckFailedError("a retired record was not stamped with when it was noticed gone")
    if any(one.deleted_at is not None for one in rows if one.source_id == kept):
        raise CheckFailedError("a record the read returned was retired")
    if await _handed(h, tenant) != {kept}:
        raise CheckFailedError("a retired record was still handed to a reader of its source")

    await _read(h, connected, _Ledger([_invoice(kept), _invoice(dropped)]))
    again = [one for one in await _every_row(h, (dropped,)) if one.source_id == dropped]
    if len(again) != 2 or retired not in again:
        raise CheckFailedError("a record the source returned again rewrote its retired row")
    returned = [one for one in again if one.deleted_at is None]
    if len(returned) != 1 or returned[0].id == retired.id:
        raise CheckFailedError("a record the source returned again was not a new live row")
    if await _handed(h, tenant) != {kept, dropped}:
        raise CheckFailedError("a record the source returned again was not handed to the reader")
