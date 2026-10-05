"""A Cloudflare account read by the worker zone by zone, and one DNS record read live by its id.

`tests/unit/test_cloudflare.py` holds the connector without a database. This drives the worker's
own run, `brain.ops.connector_sync_run.sync_on`, over a Cloudflare connection written by the store
the Connectors route writes with, answered by the recordings in `tests/fixtures/cassettes/`, into a
PostgreSQL database of the test's own, and the application's live read,
`brain.ops.live_read_run.ConnectedSources`, over the same recordings with no database at all.

**A record listed under another is walked under each parent and named by both (M11.7.3).** The
zones are read first and each kept zone's records are then read with the zone in the path; each kept
record's id is the zone's and its own, and the live read reaches the record from that id alone and
names what it read back the same way, which is what matches it to its index row.

Task ids: M11.7.3
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

import pytest
from structlog.testing import capture_logs

from brain.connectors import cloudflare
from brain.connectors.contract import FetchRequest
from brain.connectors.declaration import LISTED_UNDER_SEPARATOR as SEP
from brain.connectors.live_read import LiveReply
from brain.connectors.manifest import manifest_digest
from brain.connectors.minimal_index import fresh_canary, planted, sightings
from brain.connectors.throttle import CallOutcome
from brain.core.envelope import IdentityMode
from brain.ops.connectable import manifest_for
from brain.ops.connector_store import Connection, StoredConnections
from brain.ops.connector_sync import READ_TO_THE_END, SHAPE_DISAGREED
from brain.ops.connector_sync_run import SourceAnswer, SyncRun
from brain.ops.live_read_run import ConnectedSources
from tests.fixtures.cassettes.cloudflare import (
    ACCOUNT,
    CASSETTES,
    OTHER_ZONE,
    RECORD,
    ZONE,
    a_zone,
    envelope,
)
from tests.unit.test_cloudflare import INDEXED, console_settings
from tests.unit.test_connector_sync_run import (
    KEY,
    NOW,
    PUBLIC,
    Call,
    Keys,
    Replay,
    Resolver,
    a_database,
    attempts,
    audited,
    projected,
    sync,
    through,
)

#: The two DNS records `CF-200-dns-records` lists, as the index keeps them under `ZONE`.
LISTED: Final = (f"{ZONE}{SEP}{RECORD}", f"{ZONE}{SEP}{7:032x}")


def recorded(cid: str) -> Any:
    return next(one for one in CASSETTES if one.cid == cid)


def answered(body: Any, status: int = 200) -> SourceAnswer:
    return SourceAnswer(status=status, headers={}, body=json.dumps(body).encode("utf-8"))


@dataclass
class ByPath(Replay):
    """`SourceCaller` answering each address by its path, as Cloudflare would. No socket."""

    zones: Any = None
    records: Mapping[str, Any] = field(default_factory=dict)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del max_bytes
        self.calls.append(Call(url=url, address=address, headers=dict(headers)))
        path = url.split("?", 1)[0]
        if path.endswith("/zones"):
            return answered(self.zones)
        for zone, body in self.records.items():
            if path.endswith(f"/zones/{zone}/dns_records"):
                return answered(body)
        return answered({"success": False, "errors": [], "messages": [], "result": None}, 404)

    def paths(self) -> list[str]:
        return [one.url.split("?", 1)[0].removeprefix(cloudflare.BASE_URL) for one in self.calls]


def a_caller(canary: str | None = None, zones: Any = None) -> ByPath:
    """Both recorded zones, `ZONE`'s recorded records and an empty `OTHER_ZONE`."""
    records = recorded("CF-200-dns-records").body
    return ByPath(
        answers=(),
        zones=recorded("CF-200-zones").body if zones is None else zones,
        records={
            ZONE: records if canary is None else planted(records, canary),
            OTHER_ZONE: recorded("CF-200-dns-records-empty").body,
        },
    )


def connect(url: str) -> None:
    """Connect the account through the store the Connectors route writes with."""
    settings = console_settings()
    digest = manifest_digest(manifest_for(cloudflare.CLOUDFLARE, settings))

    async def kept() -> datetime | None:
        return None

    through(
        url,
        lambda sessions: StoredConnections(sessions).connect(
            connector=cloudflare.CLOUDFLARE,
            settings=settings,
            digest=digest,
            actor="u_admin",
            trace_id="t-connect",
            ent_hash="0" * 32,
            keep_key=kept,
        ),
    )


# ------------------------------------------------------------------ the worker's walk
@pytest.mark.needs_db
def test_the_worker_reads_the_zones_then_each_zones_records_named_by_the_zone_and_itself() -> None:
    """**The walk, end to end against the recordings.** One call for the zones, then one per zone
    kept, each with that zone's id in the path, carrying the token as a bearer to the address the
    rule checked. Both zones are kept with their account and the connection's department, and the
    records under the first are kept by the zone's id and their own, holding their zone, name and
    type and nothing else. The attempt is recorded as read to the end.

    Delete this and records are asked for with no zone, kept under ids no question can read back,
    or read before the zones they are listed under, with every unit test green."""
    with a_database("brain_cloudflare_walk") as url:
        connect(url)
        caller = a_caller()
        ran = sync(url, caller)
        rows = projected(url)
        (attempt,) = attempts(url)

    assert ran == SyncRun(read=1, waiting=0, failed=0, not_due=0, cannot_be_read=0)
    assert caller.paths() == [
        "/zones",
        f"/zones/{ZONE}/dns_records",
        f"/zones/{OTHER_ZONE}/dns_records",
    ]
    assert all(one.address == PUBLIC for one in caller.calls)
    assert all(one.headers["Authorization"] == f"Bearer {KEY}" for one in caller.calls)
    kept = {(entity, source_id): fields for _, entity, source_id, fields, _, _ in rows}
    assert set(kept) == {
        (cloudflare.ZONE, ZONE),
        (cloudflare.ZONE, OTHER_ZONE),
        *((cloudflare.DNS_RECORD, one) for one in LISTED),
    }
    assert kept[(cloudflare.ZONE, ZONE)] == {
        "name": "example.com",
        "status": "active",
        "account_id": ACCOUNT,
        "department": "operations",
    }
    assert kept[(cloudflare.DNS_RECORD, INDEXED)] == {
        "zone_id": ZONE,
        "name": "www.example.com",
        "type": "A",
        "department": "operations",
        "account_id": ACCOUNT,
    }
    assert "CANARY" not in json.dumps([str(one) for one in rows])
    outcome, _, records, _, _, _, _, detail = attempt
    assert (outcome, records, detail) == ("synced", 4, READ_TO_THE_END)


@pytest.mark.needs_db
def test_a_zone_of_another_account_stops_the_read_and_no_record_is_asked_for() -> None:
    """**`A_ZONE_OF_ANOTHER_ACCOUNT_STOPS_THE_READ`.** The token reaches a zone Cloudflare says
    belongs to another account: the page is refused whole, nothing from it is kept, and no zone's
    records are asked for. The positive half is the walk above. Delete this and a token wider than
    the one account it was made for widens the index instead of stopping it."""
    stray = envelope(
        [a_zone(ZONE, "example.com"), a_zone(OTHER_ZONE, "example.net", account="f" * 32)]
    )
    with a_database("brain_cloudflare_stray") as url:
        connect(url)
        caller = a_caller(zones=stray)
        ran = sync(url, caller)
        rows = projected(url)
        (attempt,) = attempts(url)

    assert ran.failed == 1 and ran.read == 0
    assert caller.paths() == ["/zones"]
    assert rows == []
    outcome, _, records, _, _, _, _, detail = attempt
    assert (outcome, records, detail) == ("failed", 0, SHAPE_DISAGREED)


@pytest.mark.needs_db
def test_a_synced_account_keeps_no_record_content_and_its_canary_is_in_no_table_or_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """**The owner's rule for Cloudflare, on a database built through every migration.** A canary
    minted for this run is planted in every recorded record's content and comment, the worker reads
    the account, and the canary is then in no table this product has and in no log line the run
    wrote. The positive half: a record's name, an index field, is found in `proj.record` by the
    same search. Delete this and the reading can start keeping a record's content."""
    import brain.tables  # noqa: F401 - registers every table on the metadata
    from brain.db import metadata
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url

    if not has_pgvector(admin_url()):
        pytest.skip("every table needs the full chain, which needs pgvector; CI's image has it")
    canary = fresh_canary("CLOUDFLARE")
    caplog.set_level(logging.DEBUG)
    with retirable("brain_cloudflare_sync_canary") as url, capture_logs() as logged:
        connect(url)
        ran = sync(url, a_caller(canary))
        report = audited(url, canary)
        name = audited(url, "www.example.com")

    assert ran.read == 1
    assert report.rows >= len(LISTED)
    assert set(metadata.tables) <= set(report.searched), "a modelled table was not searched"
    assert report.holding == ()
    assert "proj.record" in name.holding
    assert sightings(canary, logged, [one.getMessage() for one in caplog.records]) == ()


# ------------------------------------------------------------------ one record, live
def live_sources(caller: Any) -> tuple[ConnectedSources, Keys]:
    settings = console_settings()
    connection = Connection(
        connector=cloudflare.CLOUDFLARE,
        settings=settings,
        digest=manifest_digest(manifest_for(cloudflare.CLOUDFLARE, settings)),
        connected_by="u_admin",
        connected_at=NOW,
    )
    keys = Keys()
    found = ConnectedSources(
        {cloudflare.CLOUDFLARE: connection},
        keys=keys,
        caller=caller,
        resolver=Resolver(),
        clock=lambda: NOW,
    )
    return found, keys


@dataclass
class OneRecord:
    """`SourceCaller` answering with one recorded record, its content a canary of this run."""

    canary: str
    calls: list[Call] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del max_bytes
        self.calls.append(Call(url=url, address=address, headers=dict(headers)))
        return answered(planted(recorded("CF-200-dns-record").body, self.canary))


def fetched(found: ConnectedSources, source_id: str) -> LiveReply:
    source = found.source_for(cloudflare.CLOUDFLARE, mode=IdentityMode.SERVICE, asker="p_priya")
    assert source is not None
    request = FetchRequest(entity=cloudflare.DNS_RECORD, filters=(("id", source_id),), limit=1)

    async def once() -> LiveReply:
        return await source(request)

    return asyncio.run(once())


def test_a_record_is_read_live_from_its_index_id_by_its_own_call_and_named_the_same_way() -> None:
    """**The live half of the listing.** From the index id alone, the record is read by the
    one-record call at its zone, with the token borrowed for the read and given back, and what comes
    back carries its content, which the index never holds, and is named by the zone and itself, so
    `brain.ops.live_records` matches it to the row it was asked for.

    Delete this and a question about a record reads a whole zone, reads no content, or reads a
    record back under an id that matches nothing and is answered as gone."""
    canary = fresh_canary("LIVE")
    caller = OneRecord(canary)
    found, keys = live_sources(caller)

    reply = fetched(found, INDEXED)

    assert found.reads(cloudflare.CLOUDFLARE, cloudflare.DNS_RECORD) is IdentityMode.SERVICE
    assert reply.outcome is CallOutcome.OK and reply.rows is not None
    (row,) = reply.rows.records
    values = row.model_dump()
    assert (row.id, values["zone_id"], values["content"]) == (INDEXED, ZONE, canary)
    assert {"ttl", "proxied"} <= set(values)
    (asked,) = caller.calls
    assert asked.url == f"{cloudflare.BASE_URL}/zones/{ZONE}/dns_records/{RECORD}"
    assert asked.headers["Authorization"] == f"Bearer {KEY}"
    assert [lease.closed for lease in keys.leases] == [[NOW]]


@pytest.mark.parametrize(
    "source_id",
    [RECORD, f"{ZONE}{SEP}", f"..{RECORD}", f"{ZONE}/x{SEP}{RECORD}", f"{ZONE}{SEP}{RECORD}{SEP}x"],
)
def test_an_index_id_that_does_not_name_a_zone_and_a_record_is_refused_with_no_call(
    source_id: str,
) -> None:
    """An id with no zone, no record or a third part is refused as a read this process would not
    make, and Cloudflare is not called. Delete this and a malformed id is laid into Cloudflare's
    path as whatever it happens to split into."""
    caller = OneRecord(fresh_canary("REFUSED"))
    found, _ = live_sources(caller)

    reply = fetched(found, source_id)

    assert (reply.outcome, reply.rows) == (CallOutcome.REJECTED, None)
    assert caller.calls == []
