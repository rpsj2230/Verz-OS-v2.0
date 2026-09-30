"""The install acceptance check for connected sources answering on Ask: index, live read, age.

One check, because the leaves share one path. A Xero organisation and a Freshdesk helpdesk made up
for the run are connected inside the check's transaction through the store the Connectors screen's
routes call, read by the worker's own `brain.ops.connector_sync_run.attempt` from answers recorded
in each vendor's documented envelope, and then asked about through the answer lane with everything
the answer route hands it built by the route's own functions: the registry the application builds,
its row readers and field policies, the question shapes of the sources connected now
(`brain.api_routes.connected_questions_of`), and a live reader over the same connections. So what
is proved is the path a question takes on an install, and nothing is restated.

**No socket is opened and no real key is held.** Every call is answered by the recorded caller of
`brain.ops.acceptance_checks_connectors`, which returns the check's own bodies, and the key each
read leases is minted for the check. See that module's `A_RECORDED_ANSWER_IS_NEVER_A_CALL`.

**The check steps aside where the install has either source connected.** Connecting a source that
is connected already is refused, and the check reads its questions off the connections live in its
transaction, so a real connection would stand in the check's place. See
`A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`.

**Every connected value is read live, so the stale answer is asked of the price list.** Xero's
invoices and contacts and Freshdesk's tickets, bodies included, are read from the source when a
question asks (M11.9.2), so no connected answer stands on an old index row; the product's own
price list is the pair every install answers from its index, and a row of it read days before is
what surfaces the staleness (M11.4.9). See `A_PRICE_READ_DAYS_AGO_IS_ANSWERED_AS_OLD`.

**What it does not prove, said once.** A question over many records (M11.8.3's headers clause) has
no question shape yet, and the request recorders are not handed to the lane, so the canary search
covers what the lane and the sources wrote and not the request row.

Task ids: M11.6.5, M11.6.2, M11.4.9, M11.9.2
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import (
    A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN,
    DUE_DATE,
    _Keys,
    _no_wait,
    _nothing_kept,
    _Recorded,
    _Resolver,
    _search,
)
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.gate.answer import Answered
    from brain.ops.connector_store import Connection
    from brain.ops.connector_sync_run import SourceAnswer

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 280

A, _ = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: What the check says where the install has either source connected already.
A_SOURCE_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Xero or Freshdesk connected already, so the check does not connect it "
    "again and does not ask about it"
)

#: Why the ticket is read days before the question, and why its answer is not old.
A_TICKET_READ_LIVE_IS_NOT_OLD: Final = (
    "The helpdesk's ticket is indexed by the worker three days before the question, and every "
    "value a question uses is read from the helpdesk when it is asked (M11.9.2), so the answer "
    "stands on that read and carries no note that it may be out of date."
)

#: Why the stale answer is asked of the product's own price list.
A_PRICE_READ_DAYS_AGO_IS_ANSWERED_AS_OLD: Final = (
    "Every shipped connected source is read live, so an answer standing on an index row is one "
    "about a pair no source reads live, and the built-in price list is one every install reads "
    "from its index. A row of it read three days before the question is past the product's "
    "horizon, so the answer must say it may be out of date and date its citation by that read."
)

__all__ = [
    "A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN",
    "A_PRICE_READ_DAYS_AGO_IS_ANSWERED_AS_OLD",
    "A_TICKET_READ_LIVE_IS_NOT_OLD",
]

# ------------------------------------------------------------------------ the figures
#: How long before the question the helpdesk was read.
READ_BEFORE_THE_QUESTION: Final = timedelta(days=3)

#: The helpdesk address the check connects. Reserved for documentation, and never reached: the
#: recorded caller answers it.
HELPDESK: Final = "acceptance-check.freshdesk.com"

#: Freshdesk's code for an open ticket, as its list answers it.
OPEN: Final = 2


# ------------------------------------------------------------------------ the helpers
@dataclass
class _Helpdesk:
    """`SourceCaller` answering Freshdesk's ticket list with the check's one ticket. No socket."""

    ticket: dict[str, Any]
    body: str = ""
    asked: list[str] = field(default_factory=list)

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        self.asked.append(url)
        path = url.split("?", 1)[0]
        if path.endswith(f"/api/v2/tickets/{self.ticket['id']}"):
            one = {**self.ticket, "description_text": self.body}
            return SourceAnswer(status=200, headers={}, body=json.dumps(one).encode())
        if path.endswith("/api/v2/tickets"):
            return SourceAnswer(status=200, headers={}, body=json.dumps([self.ticket]).encode())
        return SourceAnswer(status=404, headers={}, body=b"{}")


@dataclass
class _Both:
    """`SourceCaller` sending each call to the recorded source whose address it names."""

    ledger: Any
    helpdesk: _Helpdesk

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        to = self.helpdesk if HELPDESK in url else self.ledger
        return to.get(url, address=address, headers=headers, max_bytes=max_bytes)


def _connection(h: Harness, connector: str, settings: dict[str, str]) -> Connection:
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import Connection

    return Connection(
        connector=connector,
        settings=settings,
        digest=manifest_digest(manifest_for(connector, settings)),
        connected_by=h.actor,
        connected_at=h.now,
    )


async def _connect_and_read(
    h: Harness, connection: Connection, caller: Any, *, at: datetime
) -> None:
    """Connect a source as the Connectors screen's route does, and read it as the worker does."""
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
    plan = plan_for(connection, last=None, now=h.now)
    if plan.refused or not plan.due:
        raise CheckFailedError("the worker's plan would not read a source connected as declared")
    done = await attempt(
        LiveConnection(id=uuid.uuid4(), connection=connection),
        plan,
        previous=None,
        sessions=h.sessions,
        keys=_Keys(),
        caller=caller,
        resolver=_Resolver(),
        clock=lambda: at,
        sleep=_no_wait,
    )
    if done.outcome is not SyncOutcome.SYNCED or done.records < 1:
        raise CheckFailedError("the worker did not read a connected source's recorded answers")


def _prose(answered: Answered) -> str:
    """What the person was told, read from the frames as the web draws them."""
    from brain.ops.acceptance_checks_chat import heard

    return heard(answered.frames).prose


# ------------------------------------------------ 1. a connected source answers on Ask
@check(
    leaves=("M11.6.5", "M11.6.2", "M11.4.9"),
    sentence=(
        "A Xero organisation and a Freshdesk helpdesk made up for the check are connected, read by "
        "the worker from recorded answers and asked about through the answer route's own parts: "
        "an invoice's amount and a ticket's body are read live for a reader granted them and "
        "withheld as if absent from one who is not, a price read days ago is said to be possibly "
        "out of date, and nothing read live is in a table."
    ),
)
async def a_connected_source_answers_on_ask_from_its_index_and_its_source(h: Harness) -> None:
    from brain.api_routes import (
        connected_questions_of,
        covered_at,
        field_policies,
        row_readers,
        source_field_policies,
    )
    from brain.connectors import freshdesk, xero
    from brain.connectors.minimal_index import fresh_canary
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.gate.provenance import STALENESS_TEXT, Freshness
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connector_store import live
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    for name in (xero.CONNECTOR_NAME, freshdesk.FRESHDESK):
        if (await h.execute(live(name))).scalar_one_or_none() is not None:
            raise CheckNotRunError(A_SOURCE_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()
    state = SimpleNamespace(db_sessions=h.sessions)
    if await connected_questions_of(state):
        raise CheckFailedError("a source nobody connected contributed a question shape")

    # Xero: one invoice, its amount a canary the index must never hold.
    canary = fresh_canary("ACCEPTANCE")
    invoice_id, number = str(uuid.uuid4()), h.word()
    invoices = {
        "Invoices": [
            {
                "InvoiceID": invoice_id,
                "InvoiceNumber": number,
                "Contact": {"ContactID": str(uuid.uuid4())},
                "AmountDue": canary,
                "DueDate": DUE_DATE,
                "Status": "AUTHORISED",
            }
        ]
    }
    ledger = _Recorded(
        invoices=json.dumps(invoices).encode("utf-8"),
        contacts=json.dumps({"Contacts": []}).encode("utf-8"),
    )
    ledger_connection = _connection(h, xero.CONNECTOR_NAME, {"tenant_id": str(uuid.uuid4())})
    await _connect_and_read(h, ledger_connection, ledger, at=h.now)

    # Freshdesk: one ticket in acceptance_a, read three days before the question.
    subject = h.word()
    ticket = {
        "id": 900_000 + uuid.uuid4().int % 99_999,
        "subject": subject,
        "status": OPEN,
        "priority": 1,
        "company_id": 1,
        "requester_id": 1,
        "group_id": 1,
        "created_at": "2019-03-01T10:00:00Z",
        "updated_at": "2019-03-02T10:00:00Z",
        "due_by": "2019-03-08T10:00:00Z",
    }
    helpdesk_connection = _connection(
        h,
        freshdesk.FRESHDESK,
        {freshdesk.DOMAIN_SETTING: HELPDESK, freshdesk.DEPARTMENT_SETTING: A},
    )
    read_at = h.now - READ_BEFORE_THE_QUESTION
    body = fresh_canary("ACCEPTANCE")
    helpdesk = _Helpdesk(ticket, body=body)
    await _connect_and_read(h, helpdesk_connection, helpdesk, at=read_at)

    # What the answer route builds, by its own functions, over the check's transaction.
    rules = await connected_questions_of(state)
    if {rule.source for rule in rules} != {xero.CONNECTOR_NAME, freshdesk.FRESHDESK}:
        raise CheckFailedError("the connected sources contributed no question shapes to Ask")
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    readers = row_readers(registry)
    for pair in (
        (xero.CONNECTOR_NAME, xero.ENTITY_INVOICE),
        (freshdesk.FRESHDESK, freshdesk.TICKET),
    ):
        if pair not in readers:
            raise CheckFailedError("the application registered no reader for a connected source")
    connections = {one.connector: one for one in (ledger_connection, helpdesk_connection)}

    async def connected() -> Any:
        return ConnectedSources(
            connections,
            keys=_Keys(),
            caller=_Both(ledger=ledger, helpdesk=helpdesk),
            resolver=_Resolver(),
            clock=lambda: h.now,
        )

    live_records = SourceRecords(connected=connected, clock=lambda: h.now)

    async def ask(principal_id: str, question: str, *, also: Any = ()) -> Answered:
        person = await StoredPrincipals(h.sessions).live_principal(principal_id)
        if person is None:
            raise CheckFailedError("a reserved person was not live in the directory")
        reach: EntitlementSet = await _console(h, principal_id, second_factor=False)
        return await answer_lane(
            question,
            origin=Origin(trace_id=h.trace_id, principal=person, channel=Channel.CONSOLE),
            recorders=(),
            rules=(*rules, *also),
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

    def asking(field_name: str, slot: str) -> str:
        return QUESTION_SHAPES[0].format(label=label_of(field_name), slot=slot)

    reads = ("read:invoice", "read:invoice.invoice_number", "read:invoice.status")
    finance, sales = h.principal(A, "finance"), h.principal(A, "sales")
    await h.person(
        finance,
        department=A,
        grants=tuple((one, Scope.unrestricted()) for one in (*reads, "read:invoice.amount_due")),
    )
    await h.person(sales, department=A, grants=tuple((one, Scope.unrestricted()) for one in reads))

    # M11.6.5: the status from the index, the amount from Xero while the asker waits.
    status = await ask(finance, asking("status", number))
    if status.composed is None or "AUTHORISED" not in _prose(status):
        raise CheckFailedError("a connected invoice's status was not answered on Ask")
    amount = await ask(finance, asking("amount_due", number))
    if amount.composed is None or canary not in _prose(amount):
        raise CheckFailedError("an invoice's amount was not read live for a reader granted it")
    if len(ledger.asked) < 3:
        raise CheckFailedError("the amount was not read from the source when it was asked")
    withheld = await ask(sales, asking("amount_due", number))
    nobody = await ask(sales, asking("amount_due", h.word()))
    if canary in _prose(withheld) or withheld.composed is not None:
        raise CheckFailedError("an invoice's amount was told to a reader not granted it")
    if _prose(withheld) != _prose(nobody):
        raise CheckFailedError("a withheld amount was told apart from an invoice that is not there")

    # M11.6.2: the ticket found by its index row and read from the helpdesk, body and all.
    support = h.principal(A, "support")
    await h.person(
        support,
        department=A,
        grants=tuple(
            (one, Scope.department(A))
            for one in (
                "read:ticket",
                "read:ticket.subject",
                "read:ticket.status",
                f"read:ticket.{freshdesk.LIVE_BODY_FIELD}",
            )
        ),
    )
    status = await ask(support, asking("status", subject))
    if status.composed is None or status.provenance is None:
        raise CheckFailedError("a connected helpdesk's ticket was not answered on Ask")
    if STALENESS_TEXT[Freshness.STALE] in _prose(status):
        raise CheckFailedError("a ticket read live was answered as though read days ago")
    told = await ask(support, asking(freshdesk.LIVE_BODY_FIELD, subject))
    if told.composed is None or body not in _prose(told):
        raise CheckFailedError("a ticket's body was not read from the helpdesk when it was asked")
    agent = h.principal(A, "agent")
    await h.person(
        agent,
        department=A,
        grants=tuple((one, Scope.department(A)) for one in ("read:ticket", "read:ticket.subject")),
    )
    hidden = await ask(agent, asking(freshdesk.LIVE_BODY_FIELD, subject))
    missing = await ask(agent, asking(freshdesk.LIVE_BODY_FIELD, h.word()))
    if body in _prose(hidden) or _prose(hidden) != _prose(missing):
        raise CheckFailedError("a ticket's body was told to a reader not granted it")

    # M11.4.9: an answer standing on an index row read days ago says so, on the product's own
    # price list, which every install reads from its index and no source reads live.
    await _stale_price(h, ask, asking)

    # Nothing a live read returned was kept anywhere.
    if await _search(h, canary):
        raise CheckFailedError("an amount read live was found in a table")
    if await _search(h, body):
        raise CheckFailedError("a ticket's body read live was found in a table")


async def _stale_price(h: Harness, ask: Any, asking: Any) -> None:
    """A price list row the index read days ago, answered with the note that it may be old.

    Written into the check's own transaction through the sync's own `record_upsert`, under the
    source this install's registry reads its built-in price list from, so the reader, the row
    plane and the date are the product's. See `A_PRICE_READ_DAYS_AGO_IS_ANSWERED_AS_OLD`.
    """
    from brain.connectors.projection import ProjectedRecord
    from brain.gate.provenance import STALENESS_TEXT, Freshness
    from brain.knowledge.classified_rows import questions_over
    from brain.knowledge.columns import PRICE_LIST
    from brain.ops.connector_sync_store import record_upsert

    read_at = h.now - READ_BEFORE_THE_QUESTION
    name, price = h.word(), "417.00"
    source = h.settings.tool_source
    row = ProjectedRecord(
        source=source,
        entity=PRICE_LIST.entity,
        source_id=f"acceptance-{h.word()}",
        last_seen_at=read_at,
        fields={"name": name, "sell_price": price},
    )
    async with h.sessions() as session, session.begin():
        await session.execute(record_upsert(row, {"name": name, "sell_price": price}))
    buyer = h.principal(A, "buyer")
    await h.person(
        buyer,
        department=A,
        grants=tuple(
            (one, Scope.unrestricted())
            for one in ("read:price_list", "read:price_list.name", "read:price_list.sell_price")
        ),
    )
    shapes = questions_over(PRICE_LIST, source=source, key_column="name")
    old = await ask(buyer, asking("sell_price", name), also=shapes)
    if old.composed is None or price not in _prose(old) or old.provenance is None:
        raise CheckFailedError("a price the index read days ago was not answered on Ask")
    if STALENESS_TEXT[Freshness.STALE] not in _prose(old):
        raise CheckFailedError("an answer from a row read days ago did not say it may be old")
    dated = {datetime.fromisoformat(one.freshness.fetched_at) for one in old.provenance.rows}
    if dated != {read_at}:
        raise CheckFailedError("a row's citation was not dated by when it was last read")
