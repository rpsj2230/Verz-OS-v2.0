"""The install acceptance check for a Lark Base answering on Ask: its index, its schema, Lark live.

One check, because the pieces are one path. A Base made up for the run is read the way the worker
reads a switched-on Base (`brain.ops.lark_base_index.opened` and `index_base`, under a key leased
for the run and a token exchanged for it), its schema is read the way a question reads it
(`brain.ops.lark_base_live.BaseSchema`), the answer route's own `brain.api_routes.base_lane_for`
turns it into question shapes, readers and policies, and the question is answered by the answer
lane with a live reader over the Base (`lark_base_live.with_base`). So what is proved is the path a
question about a Base takes on an install, and nothing is restated.

**No socket is opened and no real key is held.** Every call is answered by `_RecordedBase`, which
returns bodies written in Lark's documented envelopes, the token exchange is answered by
`_Issuer`, and the key leased is minted for the check. See
`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`. The Base is made up
for the run, so the check never meets the install's own Base, switched on or not.

**What it does not prove, said once.** That Lark itself answers this install: that needs the
owner's Base shared with the app and knowledge from Base switched on in Connect Lark, and it is
proved by asking on the install. A table read past the run's share of the minute, and a record
deleted in the Base after it was indexed, are the connector's own tests' business.

Task ids: M11.6.3
"""

from __future__ import annotations

import json
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_connectors import _Lease, _Resolver, _search

if TYPE_CHECKING:
    from collections.abc import Mapping

    from brain.core.entitlement import EntitlementSet
    from brain.gate.answer import Answered
    from brain.ops.acceptance_run import Harness
    from brain.ops.connector_sync_run import SourceAnswer
    from brain.ops.secrets import SecretRef

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 310

A, _ = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------------ the figures
#: The platform host the made-up Base is read on. Lark's own, answered by `_RecordedBase`.
HOST: Final = "open.larksuite.com"

#: Lark's numeric field types, as `lark_base.KIND_FACTS` names them.
TEXT, SINGLE_SELECT, MODIFIED_TIME = 1, 3, 1002

#: The Lark app's identifier the leased key carries, in the shape Connect Lark keeps.
APP_ID: Final = "cli_acceptancecheck"


def _made_up(prefix: str, length: int) -> str:
    """An id in Lark's alphabet, made up for the run."""
    alphabet = string.ascii_letters + string.digits
    return prefix + "".join(secrets.choice(alphabet) for _ in range(length))


# ------------------------------------------------------------------------ the helpers
class _AppKeys:
    """`ConnectorKeys` leasing an app id and secret made for the check, in Connect Lark's shape."""

    leased: int = 0
    closed: int = 0

    def lease(self, ref: SecretRef, *, now: datetime) -> _Lease:
        del ref, now
        self.leased += 1
        return _Lease(f"{APP_ID}:{secrets.token_hex(16)}")


@dataclass
class _Issuer:
    """`TokenIssuer` answering every exchange with a token made for the check. No socket."""

    issued: list[str] = field(default_factory=list)

    def issue(self, host: str, *, app_id: str, app_secret: str) -> str | None:
        del app_secret
        if host != HOST or app_id != APP_ID:
            return None
        token = f"t-{secrets.token_hex(8)}"
        self.issued.append(token)
        return token


@dataclass
class _RecordedBase:
    """`LarkCaller` answering one Base's listings and records from bodies written for the check."""

    base_id: str
    table_id: str
    title: str
    fields: tuple[dict[str, Any], ...]
    record: dict[str, Any]
    asked: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.asked.append(url)
        if not headers.get("Authorization", "").startswith("Bearer t-"):
            return SourceAnswer(status=200, headers={}, body=_body({"code": 99991663}))
        apps = f"/open-apis/bitable/v1/apps/{self.base_id}/tables"
        table = f"{apps}/{self.table_id}"
        path = url.split("?", 1)[0].removeprefix(f"https://{HOST}")
        if path == apps:
            items = [{"table_id": self.table_id, "revision": 1, "name": self.title}]
            return _page(items)
        if path == f"{table}/fields":
            return _page(list(self.fields))
        if path == f"{table}/records":
            return _page([{"record_id": self.record["record_id"], "fields": self.record["fields"]}])
        if path == f"{table}/records/{self.record['record_id']}":
            one = {"record": {"id": self.record["record_id"], **self.record}}
            return SourceAnswer(status=200, headers={}, body=_body({"code": 0, "data": one}))
        return SourceAnswer(status=200, headers={}, body=_body({"code": 1254040, "msg": "no"}))


def _body(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")


def _page(items: list[dict[str, Any]]) -> SourceAnswer:
    from brain.ops.connector_sync_run import SourceAnswer

    data = {"has_more": False, "total": len(items), "items": items}
    return SourceAnswer(status=200, headers={}, body=_body({"code": 0, "data": data}))


def _field(field_id: str, name: str, api_type: int, *, primary: bool = False) -> dict[str, Any]:
    return {"field_id": field_id, "field_name": name, "type": api_type, "is_primary": primary}


def _prose(answered: Answered) -> str:
    """What the person was told, read from the frames as the web draws them."""
    from brain.ops.acceptance_checks_chat import heard

    return heard(answered.frames).prose


# ------------------------------------------------ 1. a Base answers on Ask
@check(
    leaves=("M11.6.3",),
    sentence=(
        "A Lark Base made up for the check is indexed as the worker indexes a switched-on Base, "
        "and asked about through the answer route's own lane: a record found by its name has a "
        "value read from Lark for a reader granted the table's fields, withheld as if absent from "
        "one granted only its names, and the value is in no table."
    ),
)
async def a_lark_base_answers_on_ask_from_its_index_and_lark(h: Harness) -> None:
    from sqlalchemy import select

    from brain.api_routes import base_lane_for, covered_at, field_policies, source_field_policies
    from brain.connectors.minimal_index import fresh_canary
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.lark_base_index import LarkBaseUse, index_base, opened
    from brain.ops.lark_base_live import BaseSchema, with_base
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tables.gate import CapabilityRegistryRow
    from brain.tools.startup import build_registry

    await h.found_departments()
    use = LarkBaseUse(base_id=_made_up("", 20), host=HOST)
    table_id, name, canary = _made_up("tbl", 12), h.word(), fresh_canary("ACCEPTANCE")
    record_id = _made_up("rec", 10)
    base = _RecordedBase(
        base_id=use.base_id,
        table_id=table_id,
        title=f"Accounts {h.word()}",
        fields=(
            _field("fldPrim00001", "Client", TEXT, primary=True),
            _field("fldStat00002", "Status", SINGLE_SELECT),
            _field("fldValu00003", "Contract Value", TEXT),
            _field("fldEdit00004", "Last modified", MODIFIED_TIME),
        ),
        record={
            "record_id": record_id,
            "fields": {
                "Client": name,
                "Status": "Active",
                "Contract Value": canary,
                "Last modified": 1552000000000,
            },
        },
    )
    keys, issuer = _AppKeys(), _Issuer()

    # The worker's half: the index, under a key leased and a token exchanged for the run.
    from brain.connectors.lark_base import fair_share_budget

    with opened(
        use, keys=keys, caller=base, resolver=_Resolver(), issuer=issuer, now=h.now
    ) as reads:
        if isinstance(reads, str):
            raise CheckFailedError("the worker could not open the made-up Base with its key")
        run = await index_base(use, reads, h.sessions, now=h.now, budget=fair_share_budget())
    if (run.tables, run.kept, run.stopped_short) != (1, 1, False):
        raise CheckFailedError("the worker did not index the made-up Base's one table and record")
    entity = f"lark_{table_id.lower()}"
    offered = select(CapabilityRegistryRow.capability).where(
        CapabilityRegistryRow.capability.in_([f"read:{entity}", f"read:{entity}.*"])
    )
    words = set((await h.execute(offered)).scalars())
    if words != {f"read:{entity}", f"read:{entity}.*"}:
        raise CheckFailedError("the index did not offer the table's grants on the grants screen")

    # The question's half: the schema, the route's lane over it, and Lark read live.
    schema = BaseSchema(
        keys=keys, caller=base, resolver=_Resolver(), issuer=issuer, clock=lambda: h.now
    )
    lane = await base_lane_for(use, schema, h.sessions)
    if (("lark_base", entity) not in lane.readers) or not lane.rules:
        raise CheckFailedError("the answer route asked nothing of a switched-on Base's table")
    tables = await schema.tables(use)

    async def connected() -> Any:
        nothing = ConnectedSources(
            {}, keys=keys, caller=base, resolver=_Resolver(), clock=lambda: h.now
        )
        return with_base(
            nothing,
            use,
            tables,
            keys=keys,
            caller=base,
            resolver=_Resolver(),
            issuer=issuer,
            clock=lambda: h.now,
        )

    live = SourceRecords(connected=connected, clock=lambda: h.now)
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))

    async def ask(principal_id: str, question: str) -> Answered:
        person = await StoredPrincipals(h.sessions).live_principal(principal_id)
        if person is None:
            raise CheckFailedError("a reserved person was not live in the directory")
        reach: EntitlementSet = await _console(h, principal_id, second_factor=False)
        return await answer_lane(
            question,
            origin=Origin(trace_id=h.trace_id, principal=person, channel=Channel.CONSOLE),
            recorders=(),
            rules=lane.rules,
            readers=dict(lane.readers),
            entitlement=reach,
            policies={**field_policies(registry), **lane.policies},
            reachable_sources=covered_at(registry, reach, h.now),
            sink=CountingTraceSink(),
            now=h.now,
            clock=lambda: h.now,
            live=live,
            source_policies={**source_field_policies(registry), **lane.source_policies},
        )

    def asking(slot: str) -> str:
        return QUESTION_SHAPES[0].format(label=label_of("contract_value"), slot=slot)

    reader, finder = h.principal(A, "accounts"), h.principal(A, "sales")
    await h.person(
        reader,
        department=A,
        grants=tuple((one, Scope.unrestricted()) for one in (f"read:{entity}", f"read:{entity}.*")),
    )
    await h.person(
        finder,
        department=A,
        grants=tuple(
            (one, Scope.unrestricted()) for one in (f"read:{entity}", f"read:{entity}.client")
        ),
    )

    before = len(base.asked)
    told = await ask(reader, asking(name))
    if told.composed is None or canary not in _prose(told):
        raise CheckFailedError(
            "a Base record's value was not read from Lark for a reader granted it"
        )
    if not any(record_id in url for url in base.asked[before:]):
        raise CheckFailedError("a Base record's value was answered without reading it from Lark")
    withheld = await ask(finder, asking(name))
    nobody = await ask(finder, asking(h.word()))
    if canary in _prose(withheld) or withheld.composed is not None:
        raise CheckFailedError("a Base record's value was told to a reader not granted its fields")
    if _prose(withheld) != _prose(nobody):
        raise CheckFailedError(
            "a withheld Base value was told apart from a record that is not there"
        )

    # Nothing a live read returned was kept anywhere.
    if await _search(h, canary):
        raise CheckFailedError("a Base value read live was found in a table")
