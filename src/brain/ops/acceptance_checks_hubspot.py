"""The install acceptance check for HubSpot on Ask: its index, and every value read live.

Until 2026-09-30 HubSpot was offered on the Connectors screen and, once its ceiling was recorded,
read into its index by the worker, and no question on Ask could reach it: nothing classified its
records for the answer lane. The check proves the path a question now takes, on the install's own
database and code, as `brain.ops.acceptance_checks_sources` does for Xero and Freshdesk.

A HubSpot account made up for the run is connected inside the check's transaction through the store
the Connectors screen's routes call, read by the worker's own `attempt` from answers recorded in
HubSpot's documented shapes, and asked about through the answer lane with everything the answer
route hands it built by the route's own functions: the registry, its row readers and field
policies, the question shapes of the sources connected now, and a live reader over the same
connection. A deal's amount, which the index never holds, is read from HubSpot's one-record read
while the asker waits, for a reader granted it; a reader who is not is told what a deal that does
not exist tells them; and the amount is in no table afterwards.

**No socket is opened and no real key is held.** Every call is answered by `_RecordedAccount`, and
the key each read leases is minted for the check
(`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`).

**The check steps aside where the install has HubSpot connected already**, for
`brain.ops.acceptance_checks_sources.A_SOURCE_IS_CONNECTED_HERE_ALREADY`'s reason.

Task ids: M11.9.2, M11.6.5
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import _Keys, _Resolver, _search
from brain.ops.acceptance_checks_sources import _connect_and_read, _connection, _prose

if TYPE_CHECKING:
    from collections.abc import Mapping

    from brain.core.entitlement import EntitlementSet
    from brain.gate.answer import Answered
    from brain.ops.acceptance_run import Harness
    from brain.ops.connector_sync_run import SourceAnswer

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 305

A, _ = RESERVED_DEPARTMENTS

#: What the check says where the install has HubSpot connected already.
HUBSPOT_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has HubSpot connected already, so the check does not connect it again and "
    "does not ask about it"
)


def _body(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")


@dataclass
class _RecordedAccount:
    """`SourceCaller` answering one HubSpot account's lists and one-record reads. No socket.

    A call without a bearer key is answered with HubSpot's 401, so a read that sent none reads
    nothing.
    """

    company: Mapping[str, Any]
    deal: Mapping[str, Any]
    asked: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.asked.append(url)
        if not headers.get("Authorization", "").startswith("Bearer "):
            return SourceAnswer(status=401, headers={}, body=_body({"status": "error"}))
        path = urlsplit(url).path
        records = {
            "/crm/v3/objects/companies": {"results": [self.company]},
            "/crm/v3/objects/contacts": {"results": []},
            "/crm/v3/objects/deals": {"results": [self.deal]},
            f"/crm/v3/objects/companies/{self.company['id']}": self.company,
            f"/crm/v3/objects/deals/{self.deal['id']}": self.deal,
        }
        found = records.get(path)
        if found is None:
            return SourceAnswer(status=404, headers={}, body=_body({"status": "error"}))
        return SourceAnswer(status=200, headers={}, body=_body(found))

    def read_deal_live(self, since: int = 0) -> bool:
        return any(f"/deals/{self.deal['id']}" in one for one in self.asked[since:])


@check(
    leaves=("M11.9.2", "M11.6.5"),
    sentence=(
        "A HubSpot account made up for the check is connected, read by the worker into its index "
        "from recorded answers, and asked about on Ask: a company is answered by name, a deal's "
        "amount is read from HubSpot while the asker waits for a reader granted it and withheld "
        "as if absent from one who is not, and the amount is in no table."
    ),
)
async def a_hubspot_deal_is_answered_on_ask_and_its_amount_read_live(h: Harness) -> None:
    from brain.api_routes import (
        connected_questions_of,
        covered_at,
        field_policies,
        row_readers,
        source_field_policies,
    )
    from brain.connectors import hubspot
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
    from brain.tools.startup import build_registry

    if (await h.execute(live(hubspot.CONNECTOR_NAME))).scalar_one_or_none() is not None:
        raise CheckNotRunError(HUBSPOT_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()

    portal = str(10**8 + secrets.randbelow(9 * 10**8))
    company_name, deal_name = h.word(), h.word()
    amount = fresh_canary("ACCEPTANCE")
    account = _RecordedAccount(
        company={
            "id": str(10**6 + secrets.randbelow(9 * 10**6)),
            "properties": {
                "name": company_name,
                "lifecyclestage": "customer",
                "hs_lastmodifieddate": "2019-03-02T10:00:00.000Z",
            },
        },
        deal={
            "id": str(10**6 + secrets.randbelow(9 * 10**6)),
            "properties": {
                "dealname": deal_name,
                "amount": amount,
                "dealstage": "contractsent",
                "pipeline": "default",
            },
        },
    )
    connection = _connection(h, hubspot.CONNECTOR_NAME, {"portal_id": portal})
    await _connect_and_read(h, connection, account, at=h.now)
    if await _search(h, amount):
        raise CheckFailedError("a deal's amount was kept in the index")

    state = SimpleNamespace(db_sessions=h.sessions)
    rules = await connected_questions_of(state)
    if hubspot.CONNECTOR_NAME not in {rule.source for rule in rules}:
        raise CheckFailedError("a connected HubSpot account contributed no question shape to Ask")
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    readers = row_readers(registry)

    async def connected() -> Any:
        return ConnectedSources(
            {hubspot.CONNECTOR_NAME: connection},
            keys=_Keys(),
            caller=account,
            resolver=_Resolver(),
            clock=lambda: h.now,
        )

    live_records = SourceRecords(connected=connected, clock=lambda: h.now)

    async def ask(principal_id: str, question: str) -> Answered:
        person = await StoredPrincipals(h.sessions).live_principal(principal_id)
        if person is None:
            raise CheckFailedError("a reserved person was not live in the directory")
        reach: EntitlementSet = await _console(h, principal_id, second_factor=False)
        return await answer_lane(
            question,
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

    def asking(field_name: str, slot: str) -> str:
        return QUESTION_SHAPES[0].format(label=label_of(field_name), slot=slot)

    company, deal = hubspot.ENTITY_CLIENT, hubspot.ENTITY_DEAL
    reads = (
        f"read:{company}",
        f"read:{company}.name",
        f"read:{company}.lifecycle_stage",
        f"read:{deal}",
        f"read:{deal}.deal_name",
    )
    sales, clerk = h.principal(A, "sales"), h.principal(A, "clerk")
    await h.person(
        sales,
        department=A,
        grants=tuple((one, Scope.unrestricted()) for one in (*reads, f"read:{deal}.amount")),
    )
    await h.person(clerk, department=A, grants=tuple((one, Scope.unrestricted()) for one in reads))

    stage = await ask(sales, asking("lifecycle_stage", company_name))
    if stage.composed is None or "customer" not in _prose(stage):
        raise CheckFailedError("a connected HubSpot company was not answered on Ask by its name")
    since = len(account.asked)
    told = await ask(sales, asking("amount", deal_name))
    if told.composed is None or amount not in _prose(told):
        raise CheckFailedError("a deal's amount was not answered for a reader granted it")
    if not account.read_deal_live(since):
        raise CheckFailedError("a deal's amount was not read from HubSpot when it was asked")
    withheld = await ask(clerk, asking("amount", deal_name))
    nobody = await ask(clerk, asking("amount", h.word()))
    if amount in _prose(withheld) or _prose(withheld) != _prose(nobody):
        raise CheckFailedError("a deal's amount was told to a reader not granted it")

    if await _search(h, amount):
        raise CheckFailedError("a deal's amount read live was found in a table")
