"""A switched-on Lark Base on Ask: what is switched on, the run's token, the index, the schema, the
live read and the lane.

Everything here runs over the check's own recorded Base (`brain.ops.acceptance_checks_lark_base`),
so the bodies the unit tests read are the bodies the install check reads, and the database half is
that check's own test. Dates are pinned far from any wall clock, for CLAUDE.md's reason about
fixtures with dates in them.

Task ids: M11.6.3, M11.9.4
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.connectors.contract import FetchRequest
from brain.connectors.lark_base import LARK_BASE, MinuteBudget
from brain.connectors.live_read import RECORD_ID_FILTER, LiveReply
from brain.connectors.throttle import CallOutcome
from brain.core.envelope import IdentityMode
from brain.ops.acceptance_checks_connectors import _Lease, _Resolver
from brain.ops.acceptance_checks_lark_base import (
    HOST,
    MODIFIED_TIME,
    SINGLE_SELECT,
    TEXT,
    _AppKeys,
    _field,
    _Issuer,
    _RecordedBase,
)
from brain.ops.lark_base_index import (
    BASE_ID_FIELD,
    INDEX_EVERY,
    LARK_BASE_USE,
    NO_KEY_FOR_THE_BASE,
    NO_TOKEN_FOR_THE_BASE,
    IndexRun,
    LarkBaseUse,
    LarkReads,
    discovered,
    index_if_due,
    opened,
    switched_on,
    token_from,
    vocabulary_of,
)
from brain.ops.lark_base_live import BaseSchema, LarkBaseSources, Together, with_base
from brain.ops.secrets import SecretsUnavailableError

#: Pinned far from any wall clock.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
BASE = "AbCdEfGh12345678XyZa"
TABLE = "tblAcceptance01"
RECORD = "recAcceptance01"
CANARY = "CANARY-LARK-7Q4XZ"


def recorded() -> _RecordedBase:
    return _RecordedBase(
        base_id=BASE,
        table_id=TABLE,
        title="Accounts",
        fields=(
            _field("fldPrim00001", "Client", TEXT, primary=True),
            _field("fldStat00002", "Status", SINGLE_SELECT),
            _field("fldValu00003", "Contract Value", TEXT),
            _field("fldEdit00004", "Last modified", MODIFIED_TIME),
        ),
        record={
            "record_id": RECORD,
            "fields": {
                "Client": "Harbour Works",
                "Status": "Active",
                "Contract Value": CANARY,
                "Last modified": 1552000000000,
            },
        },
    )


USE = LarkBaseUse(base_id=BASE, host=HOST)


def settings(**values: str) -> Any:
    return lambda name: values.get(name, "")


# ------------------------------------------------------------------------ switched on
def test_a_base_is_switched_on_only_with_knowledge_from_base_a_base_and_a_platform() -> None:
    """Delete this and a Base can be read with knowledge from Base switched off, or a Base named in
    a shape Lark would not recognise can be read as though it were one."""
    on = {
        "INSTALL_LARK_USES": "staff_list, knowledge_base",
        "INSTALL_LARK_PLATFORM": "larksuite.com",
    }
    assert switched_on(settings(**on, INSTALL_LARK_BASE=BASE)) == USE
    assert switched_on(settings(**on, INSTALL_LARK_BASE="")) is None
    assert switched_on(settings(**on, INSTALL_LARK_BASE="not a base")) is None
    assert (
        switched_on(settings(**{**on, "INSTALL_LARK_USES": "staff_list"}, INSTALL_LARK_BASE=BASE))
        is None
    )
    assert (
        switched_on(
            settings(**{**on, "INSTALL_LARK_PLATFORM": "example.com"}, INSTALL_LARK_BASE=BASE)
        )
        is None
    )


def test_the_use_read_is_the_one_connect_lark_saves() -> None:
    """Held against `brain.ops.lark_connect.Use.BASE`, which this module restates rather than
    imports. Delete this and a renamed use leaves every Base switched on and read by nothing."""
    from brain.ops.lark_connect import Use

    assert Use.BASE.value == LARK_BASE_USE


# --------------------------------------------------------------------------- the token
def test_only_a_zero_code_with_a_token_is_a_token() -> None:
    """Lark refuses an exchange with a 200 and a non-zero code. Delete this and a refusal can be
    read as a token, and every read of the run sends the refusal's text as a bearer."""
    assert token_from(200, {"code": 0, "tenant_access_token": "t-1"}) == "t-1"
    assert token_from(200, {"code": 10003, "tenant_access_token": "t-1"}) is None
    assert token_from(200, {"tenant_access_token": "t-1"}) is None
    assert token_from(500, {"code": 0, "tenant_access_token": "t-1"}) is None
    assert token_from(200, {"code": 0, "tenant_access_token": ""}) is None


@dataclass
class _Counted:
    """`ConnectorKeys` whose leases say when they are given back, holding `value` or no key."""

    value: str | None
    closed: list[datetime] = field(default_factory=list)

    def lease(self, ref: Any, *, now: datetime) -> Any:
        del ref, now
        keys = self

        class _One:
            def key(self) -> str:
                if keys.value is None:
                    raise SecretsUnavailableError("sealed")
                return keys.value

            def close(self, when: datetime) -> Any:
                keys.closed.append(when)

        return _One()


@pytest.mark.parametrize(
    ("kept", "issuer", "said"),
    [
        (None, _Issuer(), NO_KEY_FOR_THE_BASE),
        ("no separator here", _Issuer(), NO_TOKEN_FOR_THE_BASE),
        ("cli_someoneelse:secret", _Issuer(), NO_TOKEN_FOR_THE_BASE),
    ],
)
def test_a_run_with_no_key_or_no_token_reads_nothing_and_gives_the_lease_back(
    kept: str | None, issuer: _Issuer, said: str
) -> None:
    """Delete this and a run can read a Base with no token, or keep the app's key leased after it
    stopped, which is a credential held somewhere the vault does not govern."""
    keys = _Counted(kept)
    with opened(
        USE, keys=keys, caller=recorded(), resolver=_Resolver(), issuer=issuer, now=LONG_AGO
    ) as reads:
        assert reads == said
    assert keys.closed == [LONG_AGO]


def test_a_run_with_the_app_s_key_reads_with_the_token_exchanged_for_it() -> None:
    """The positive case beside the refusals. Delete this and a guard refusing every run passes."""
    keys, issuer = _Counted("cli_acceptancecheck:secret"), _Issuer()
    with opened(
        USE, keys=keys, caller=recorded(), resolver=_Resolver(), issuer=issuer, now=LONG_AGO
    ) as reads:
        assert isinstance(reads, LarkReads)
        assert reads.token == issuer.issued[0]
    assert keys.closed == [LONG_AGO]


# ------------------------------------------------------------------------ the schema
def _reads(base: _RecordedBase) -> LarkReads:
    return LarkReads(use=USE, caller=base, resolver=_Resolver(), token="t-recorded")


def test_a_base_s_tables_are_bound_by_their_own_schema_and_offered_by_their_titles() -> None:
    """`A_TABLE_S_GRANT_IS_OFFERED_BY_ITS_TITLE`. Delete this and a table can be read with no grant
    anybody could make, or its grant described by an id nobody recognises."""
    known, spent = discovered(_reads(recorded()), budget=MinuteBudget(allowance=10))
    assert spent.spent == 2
    [one] = known
    assert (one.entity, one.named()) == (f"lark_{TABLE.lower()}", "Accounts")
    assert [b.target for b in one.table.projected_bindings()] == ["client", "last_modified"]
    words = {w.capability.value: w.description for w in vocabulary_of(known)}
    fields = {f"read:{one.entity}.{b.target}" for b in one.table.bindings}
    assert set(words) == {f"read:{one.entity}", f"read:{one.entity}.*", *fields}
    assert len(fields) == 4
    assert all("'Accounts'" in said for said in words.values())
    assert "'Contract Value'" in words[f"read:{one.entity}.contract_value"]


def test_an_index_run_says_what_it_did_and_names_no_base() -> None:
    """Delete this and the connector sync's control record can name a Base, which a control run's
    other readers may not be told, or say a Base was read when nothing was."""
    assert IndexRun(unread=NO_KEY_FOR_THE_BASE).summary().endswith(NO_KEY_FOR_THE_BASE)
    assert IndexRun(not_due=True).summary() == "the Lark Base is not yet due"
    assert "3 record(s) in 1 table(s)" in IndexRun(tables=1, kept=3).summary()
    assert BASE not in IndexRun(tables=1, kept=3, stopped_short=True).summary()


class _Newest:
    """`async_sessionmaker` whose one query answers the index's newest read."""

    def __init__(self, newest: datetime | None) -> None:
        self.newest = newest

    def __call__(self) -> Any:
        newest = self.newest

        class _Session:
            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            async def execute(self, statement: Any) -> Any:
                del statement

                class _Result:
                    def scalar_one_or_none(self) -> datetime | None:
                        return newest

                return _Result()

        return _Session()


def test_the_index_is_read_again_only_when_it_is_due_and_only_with_a_base_switched_on() -> None:
    """Delete this and the worker can read a Base every five minutes, spending the tenant's minute
    on listings, or read one that was switched off."""
    on = settings(
        INSTALL_LARK_USES=LARK_BASE_USE,
        INSTALL_LARK_PLATFORM="larksuite.com",
        INSTALL_LARK_BASE=BASE,
    )

    def run(read: Any, newest: datetime | None, keys: Any) -> IndexRun | None:
        return asyncio.run(
            index_if_due(
                _Newest(newest),  # type: ignore[arg-type]
                now=LONG_AGO,
                keys=keys,
                caller=recorded(),
                resolver=_Resolver(),
                issuer=_Issuer(),
                read=read,
            )
        )

    assert run(settings(), None, _Counted(None)) is None
    recent = LONG_AGO - INDEX_EVERY + timedelta(minutes=1)
    assert run(on, recent, _Counted(None)) == IndexRun(not_due=True)
    old = LONG_AGO - INDEX_EVERY
    assert run(on, old, _Counted(None)) == IndexRun(unread=NO_KEY_FOR_THE_BASE)
    assert run(on, None, _Counted(None)) == IndexRun(unread=NO_KEY_FOR_THE_BASE)


@dataclass
class _Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def test_a_schema_is_kept_briefly_read_again_after_and_kept_when_lark_fails() -> None:
    """`A_SCHEMA_IS_READ_FOR_QUESTIONS_AND_KEPT_BRIEFLY`. Delete this and every question can list
    the Base's tables and fields, or one Lark failure can take every Base question away."""
    base, clock, keys = recorded(), _Clock(LONG_AGO), _AppKeys()
    schema = BaseSchema(keys=keys, caller=base, resolver=_Resolver(), issuer=_Issuer(), clock=clock)
    first = asyncio.run(schema.tables(USE))
    assert [one.entity for one in first] == [f"lark_{TABLE.lower()}"]
    asked = len(base.asked)
    clock.now = LONG_AGO + timedelta(minutes=5)
    assert asyncio.run(schema.tables(USE)) == first
    assert len(base.asked) == asked
    clock.now = LONG_AGO + timedelta(minutes=11)
    failing = BaseSchema(
        keys=_Counted(None), caller=base, resolver=_Resolver(), issuer=_Issuer(), clock=clock
    )
    assert asyncio.run(failing.tables(USE)) == ()
    schema._keys = _Counted(None)  # the vault is sealed after the first read
    assert asyncio.run(schema.tables(USE)) == first
    other = LarkBaseUse(base_id="ZyXwVuTs98765432AbCd", host=HOST)
    assert asyncio.run(schema.tables(other)) == ()


# --------------------------------------------------------------------- the live read
def _sources(base: _RecordedBase, keys: Any = None) -> LarkBaseSources:
    known, _ = discovered(_reads(base), budget=MinuteBudget(allowance=10))
    return LarkBaseSources(
        USE,
        {one.entity: one for one in known},
        keys=_AppKeys() if keys is None else keys,
        caller=base,
        resolver=_Resolver(),
        issuer=_Issuer(),
        clock=lambda: LONG_AGO,
    )


ENTITY = f"lark_{TABLE.lower()}"


def one_record(record: str = RECORD, entity: str = ENTITY) -> FetchRequest:
    return FetchRequest(entity=entity, filters=((RECORD_ID_FILTER, record),), limit=1)


def test_a_base_record_is_read_from_lark_by_its_id_as_the_app() -> None:
    """`A_BASE_IS_READ_AS_THE_APP`, and the one path by which a Base value reaches an answer.
    Delete this and a record's value can be answered from somewhere other than Lark, or read under
    a delegated identity this process holds nothing for."""
    base = recorded()
    sources = _sources(base)
    assert sources.reads(LARK_BASE, ENTITY) is IdentityMode.SERVICE
    assert sources.reads(LARK_BASE, "lark_tblother") is None
    assert sources.reads("xero", ENTITY) is None
    assert sources.source_for(LARK_BASE, mode=IdentityMode.DELEGATED, asker="u_a") is None
    fetch = sources.source_for(LARK_BASE, mode=IdentityMode.SERVICE, asker="u_a")
    assert fetch is not None

    async def read() -> LiveReply:
        return await fetch(one_record())

    reply = asyncio.run(read())
    assert reply.outcome is CallOutcome.OK and reply.rows is not None
    [record] = reply.rows.records
    assert record.model_dump()["contract_value"] == CANARY
    assert base.asked[-1].endswith(f"/records/{RECORD}")


@pytest.mark.parametrize(
    "request_",
    [
        FetchRequest(entity=ENTITY, filters=(), limit=1),
        FetchRequest(entity=ENTITY, filters=((RECORD_ID_FILTER, RECORD), ("client", "x")), limit=1),
        one_record(record="not-a-record"),
        one_record(entity="lark_tblother"),
    ],
)
def test_a_read_naming_anything_but_one_known_record_is_refused_unmade(request_: Any) -> None:
    """Delete this and a live read can list a table, or read a table the schema does not hold,
    under the app's token."""
    base = recorded()
    reply = _sources(base).read_one(request_)
    assert reply.outcome is CallOutcome.REJECTED
    assert not any("/records" in url for url in base.asked)


def test_a_record_with_no_key_is_a_rejection_and_lark_s_refusal_is_its_own() -> None:
    """Delete this and a sealed vault or a Base the app was never added to can read as a record
    that is not there."""
    base = recorded()
    assert _sources(base, keys=_Counted(None)).read_one(one_record()).outcome is (
        CallOutcome.REJECTED
    )
    base.record = {**base.record, "record_id": "recSomeoneElse1"}
    assert _sources(recorded()).read_one(one_record("recNotThere0001")).outcome is (
        CallOutcome.REJECTED
    )


class _Other:
    """`LiveSources` standing for the connected sources, recording what it was asked."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        self.asked.append(connector)
        return IdentityMode.SERVICE

    def source_for(self, connector: str, *, mode: IdentityMode, asker: str) -> Any:
        self.asked.append(connector)
        return None


def test_a_base_is_asked_of_its_own_source_and_every_other_of_the_connected_ones() -> None:
    """Delete this and a Xero read can be sent to the Base's reader, or a Base read to Xero's."""
    other = _Other()
    together = Together(other, _sources(recorded()))
    assert together.reads(LARK_BASE, ENTITY) is IdentityMode.SERVICE
    assert together.reads("xero", "invoice") is IdentityMode.SERVICE
    assert other.asked == ["xero"]
    assert (
        with_base(
            other,
            None,
            (),
            keys=_AppKeys(),
            caller=recorded(),
            resolver=_Resolver(),
            issuer=_Issuer(),
            clock=lambda: LONG_AGO,
        )
        is other
    )


# ------------------------------------------------------------------------ the lane
def test_a_table_s_fields_are_each_a_grant_and_its_base_is_read_by_whoever_finds_it() -> None:
    """`A_BASE_FIELD_IS_A_GRANT_OF_ITS_OWN`. Delete this and finding a record and reading its
    values can become one grant, or a reader of the table can be dropped for want of its Base."""
    from brain.knowledge.lark_base_rows import classification_of, named_by

    known, _ = discovered(_reads(recorded()), budget=MinuteBudget(allowance=10))
    table = known[0].table
    classification = classification_of(table)
    caps = {rule.column: rule.required_capability.value for rule in classification.rules}
    assert caps == {
        "client": f"read:{ENTITY}.client",
        "status": f"read:{ENTITY}.status",
        "contract_value": f"read:{ENTITY}.contract_value",
        "last_modified": f"read:{ENTITY}.last_modified",
        BASE_ID_FIELD: f"read:{ENTITY}",
    }
    assert named_by(table) == "client"


def test_a_base_table_is_asked_about_by_its_name_and_never_by_its_base() -> None:
    """Delete this and a Base's records can be asked about by a field the index does not keep,
    which matches nothing, or its Base id can be offered as something to ask."""
    from brain.knowledge.lark_base_rows import lane_for_base

    known, _ = discovered(_reads(recorded()), budget=MinuteBudget(allowance=10))
    lane = lane_for_base([(known[0].table, "Accounts")], records=object())  # type: ignore[arg-type]
    assert lane.rules
    assert {rule.match_field for rule in lane.rules} == {"client"}
    assert BASE_ID_FIELD not in {rule.answer_field for rule in lane.rules}
    assert {rule.source for rule in lane.rules} == {LARK_BASE}
    assert set(lane.readers) == {(LARK_BASE, ENTITY)}
    assert set(lane.source_policies) == {(LARK_BASE, ENTITY)}
    assert lane.policies[ENTITY] == lane.source_policies[(LARK_BASE, ENTITY)]


def test_no_base_switched_on_asks_nothing_of_a_base() -> None:
    """Delete this and a process with Knowledge from Base off can offer Base questions."""
    from brain.api_routes import base_lane_for

    schema = BaseSchema(
        keys=_AppKeys(),
        caller=recorded(),
        resolver=_Resolver(),
        issuer=_Issuer(),
        clock=lambda: LONG_AGO,
    )
    empty = asyncio.run(base_lane_for(None, schema, None))
    assert (empty.rules, dict(empty.readers)) == ((), {})


def test_the_connector_sync_s_record_carries_the_base_run_after_the_sources() -> None:
    """Delete this and a Base whose index stopped reads on the Operations screen as a sync with
    nothing wrong."""
    from brain.ops.connector_sync_run import SyncRun

    none = SyncRun(read=0, waiting=0, failed=0, not_due=0, cannot_be_read=0)
    assert none.summary() == "no source is connected"
    base = IndexRun(unread=NO_TOKEN_FOR_THE_BASE).summary()
    assert SyncRun(0, 0, 0, 0, 0, base=base).summary() == f"no source is connected; {base}"
    assert SyncRun(1, 0, 0, 0, 0, base=base).summary().endswith(f"; {base}")


def test_the_lease_helper_used_here_is_the_install_check_s() -> None:
    """The keys the check leases carry the app id in Connect Lark's shape. Delete this and the
    check can pass over a key the product would refuse to split."""
    from brain.ops.lark_base_index import app_credential

    lease = _AppKeys().lease(None, now=LONG_AGO)  # type: ignore[arg-type]
    assert isinstance(lease, _Lease)
    assert app_credential(lease.key()) is not None


def test_a_failed_schema_reading_is_not_tried_again_on_every_question() -> None:
    """`A_FAILED_SCHEMA_IS_NOT_READ_ON_EVERY_QUESTION`. Delete this and a Lark that is down makes
    every person asking anything wait for its timeout first."""
    from brain.ops.lark_base_live import SCHEMA_RETRIED_AFTER

    clock = _Clock(LONG_AGO)

    @dataclass
    class _Sealed:
        leased: int = 0

        def lease(self, ref: Any, *, now: datetime) -> Any:
            self.leased += 1
            return _Counted(None).lease(ref, now=now)

    keys = _Sealed()
    schema = BaseSchema(
        keys=keys, caller=recorded(), resolver=_Resolver(), issuer=_Issuer(), clock=clock
    )
    assert asyncio.run(schema.tables(USE)) == ()
    clock.now = LONG_AGO + SCHEMA_RETRIED_AFTER - timedelta(seconds=1)
    assert asyncio.run(schema.tables(USE)) == ()
    assert keys.leased == 1
    clock.now = LONG_AGO + SCHEMA_RETRIED_AFTER
    assert asyncio.run(schema.tables(USE)) == ()
    assert keys.leased == 2


def test_an_agent_needing_a_base_reads_a_switched_on_base_as_serving(monkeypatch: Any) -> None:
    """Connect Lark registers no connection row for a Base, so until this an agent template
    needing `lark_base` read it as not installed whatever Connect Lark said. Delete this and that
    can return, or a Base whose schema cannot be read can be offered to an agent as serving."""
    from types import SimpleNamespace

    import brain.agent_lifecycle_routes as lifecycle

    class _Stored:
        def __init__(self, sessions: Any) -> None:
            del sessions

        async def connected(self) -> tuple[Any, ...]:
            return ()

    base = recorded()
    schema = BaseSchema(
        keys=_AppKeys(), caller=base, resolver=_Resolver(), issuer=_Issuer(), clock=lambda: LONG_AGO
    )
    monkeypatch.setattr(lifecycle, "StoredConnections", _Stored)
    monkeypatch.setattr(lifecycle, "sessions_of", lambda request: object())
    monkeypatch.setattr(lifecycle, "base_schema_of", lambda state: schema)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    monkeypatch.setattr(lifecycle, "switched_on", lambda: USE)
    registry = asyncio.run(lifecycle.connectors_of(request))  # type: ignore[arg-type]
    assert registry.serving() == (LARK_BASE,)
    monkeypatch.setattr(lifecycle, "switched_on", lambda: None)
    assert len(asyncio.run(lifecycle.connectors_of(request))) == 0  # type: ignore[arg-type]
    unreadable = BaseSchema(
        keys=_Counted(None),
        caller=base,
        resolver=_Resolver(),
        issuer=_Issuer(),
        clock=lambda: LONG_AGO,
    )
    monkeypatch.setattr(lifecycle, "switched_on", lambda: USE)
    monkeypatch.setattr(lifecycle, "base_schema_of", lambda state: unreadable)
    assert len(asyncio.run(lifecycle.connectors_of(request))) == 0  # type: ignore[arg-type]
