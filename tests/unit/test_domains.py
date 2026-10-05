"""Domains and hosting (M11.7.4): a registry's record, a site's answer, and only the listed domains.

Driven by the recorded RDAP record in `tests/fixtures/cassettes/domains.py`, through the connector's
own reading, the worker's scheduled read (`brain.ops.connector_sync_run.attempt`) and the live read
(`brain.ops.live_read_run.ConnectedSources.read_one`), with a caller that records every address it
is asked for and answers from the recording. Dates are pinned far from any wall clock.

Task ids: M11.7.4
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from brain.connectors import domains
from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.declaration import CredentialShape, KeyScheme, SettingRefusedError
from brain.connectors.live_read import RECORD_ID_FILTER
from brain.connectors.manifest import manifest_digest
from brain.connectors.rdap_servers import RDAP_VENDOR_SERVERS, from_bootstrap, server_for
from brain.connectors.throttle import CallOutcome
from brain.ops.acceptance_checks_connectors import STAND_IN_ADDRESS
from brain.ops.connectable import CONNECTABLE, key_reference, manifest_for, settings_problems
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import SyncOutcome, plan_for
from brain.ops.connector_sync_run import SourceAnswer, Unleased, attempt, borrowed, call_headers
from brain.ops.connector_sync_store import LiveConnection
from brain.ops.live_read_run import ConnectedSources
from tests.fixtures.cassettes.domains import CASSETTES, RECORD, REGISTRAR

LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
ROUTED = "example.com"
UNPUBLISHED_DOMAIN = "example.my"
UNLISTED = "someone-else.com"
SETTINGS = {"domains": f"{ROUTED}, {UNPUBLISHED_DOMAIN}", "department": "operations"}


class Resolver:
    """Every name answers the stand-in public address the connector checks use."""

    def resolve(self, host: str) -> list[str]:
        del host
        return [STAND_IN_ADDRESS]


@dataclass
class Caller:
    """A registry answering the recorded record for the routed domain, and a site answering 200."""

    site_status: int | None = 200
    asked: list[str] = field(default_factory=list)
    headers_sent: list[dict[str, str]] = field(default_factory=list)

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        del address, max_bytes
        self.asked.append(url)
        self.headers_sent.append(dict(headers))
        if "/domain/" in url:
            name = url.rsplit("/", 1)[-1]
            body = {**RECORD, "ldhName": name.upper()}
            return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode())
        if self.site_status is None:
            return SourceAnswer(connection_failed=True)
        return SourceAnswer(status=self.site_status, headers={}, body=b"<html></html>")


class NoKeys:
    """A vault that must never be asked: a keyless source takes no lease."""

    def lease(self, ref: Any, *, now: datetime) -> Any:
        del ref, now
        raise AssertionError("a keyless source asked the vault for a key")


def connection(settings: dict[str, str] = SETTINGS) -> Connection:
    return Connection(
        connector=domains.CONNECTOR_NAME,
        settings=settings,
        digest=manifest_digest(manifest_for(domains.CONNECTOR_NAME, settings)),
        connected_by="u_admin",
        connected_at=LONG_AGO,
    )


# ------------------------------------------------------------------ the recordings


def test_every_recording_replays_as_it_says() -> None:
    """The contract with the recordings, through the connector's own reading. Delete this and a
    registry's refusal or its record can be read as something it is not."""
    from tests.fixtures.cassettes.domains import CASSETTE_FILE
    from tests.invariants.test_cassettes import mismatches

    assert mismatches(CASSETTE_FILE) == {}
    assert {one.status for one in CASSETTES} == {200, 404, 429, 503}


def test_a_registry_record_is_read_as_its_expiry_registrar_status_and_name_servers() -> None:
    """Read from the record's own shape: the expiry is an event, the registrar an entity's vCard.
    Delete this and an expiry question is answered from a field the record does not hold."""
    row = domains.record_of(RECORD)
    assert row["id"] == row["name"] == "example.com"
    assert row["expiry"] == "2999-03-01T00:00:00+00:00"
    assert row["registrar"] == REGISTRAR
    assert row["registration"] == "active"
    assert row["nameservers"] == "ns1.example.net, ns2.example.net"
    with pytest.raises(ConnectorContractError):
        domains.record_of({"objectClassName": "domain"})


@pytest.mark.parametrize(
    ("statuses", "word"),
    [
        (["active"], "active"),
        (["client transfer prohibited"], "active"),
        (["client hold"], "on_hold"),
        (["server hold", "pending delete"], "on_hold"),
        (["redemption period"], "pending_delete"),
        (["inactive"], "inactive"),
    ],
)
def test_a_domains_rdap_statuses_are_one_word(statuses: list[str], word: str) -> None:
    """RFC 8056's statuses reduced to the word the index keeps and a question counts by. Delete
    this and a domain on hold is counted as active."""
    assert domains.registration_of(statuses) == word


def test_the_index_keeps_the_name_the_expiry_and_the_status_and_no_registrar() -> None:
    """`CONNECTORS_NEVER_BULK_SYNC`: the registrar and name servers are read live and never kept.
    Delete this and the index becomes a copy of the registry record."""
    kept = domains.DomainsReading().projected(
        domains.DOMAIN, domains.record_of(RECORD), seen_at=LONG_AGO
    )
    assert kept is not None
    assert set(kept.fields) == {"name", "expiry", "registration"}
    assert set(domains.LIVE_ONLY).isdisjoint(kept.fields)


# ---------------------------------------------------------------- the connection


def test_a_connection_is_its_listed_domains_and_one_department() -> None:
    """The positive case: a list typed with commas, spaces and new lines, in any case, is the
    connection's scope. Delete this and every refusal below passes against a form that refuses
    everything."""
    one = domains.DomainsConnection.from_settings(
        {"domains": " Example.com,\nexample.my ; example.com.", "department": "operations"}
    )
    assert one.domains == ("example.com", "example.my")
    assert one.scope().selectors == ("example.com", "example.my")
    assert settings_problems(CONNECTABLE[domains.CONNECTOR_NAME], SETTINGS) == ()


@pytest.mark.parametrize(
    ("setting", "typed"),
    [
        ("domains", "*"),
        ("domains", "all"),
        ("domains", "https://example.com/"),
        ("domains", "example"),
        ("domains", ", ".join(f"d{n}.example.com" for n in range(domains.MAX_DOMAINS + 1))),
        ("department", "Operations"),
    ],
)
def test_a_setting_that_is_not_domains_or_a_department_is_refused_by_name(
    setting: str, typed: str
) -> None:
    """Delete this and a list with a wildcard, an address or a word in it becomes a scope."""
    with pytest.raises(SettingRefusedError) as refused:
        domains.DomainsConnection.from_settings({**SETTINGS, setting: typed})
    assert refused.value.setting == setting


def test_a_domain_nobody_listed_is_never_looked_up() -> None:
    """`ONLY_THE_CONNECTIONS_OWN_DOMAINS_ARE_LOOKED_UP`: an unlisted domain has no operation and no
    unpublished record. Delete this and the install is a free RDAP client for any domain asked."""
    reading = domains.DomainsReading()
    with pytest.raises(ConnectorContractError, match="nothing else is ever sent"):
        reading.operation_for(
            domains.DOMAIN, {"name": UNLISTED}, settings=SETTINGS, resolver=Resolver()
        )
    listed = reading.operation_for(
        domains.DOMAIN, {"name": ROUTED}, settings=SETTINGS, resolver=Resolver()
    )
    assert listed.base_url == server_for(ROUTED)
    assert reading.unpublished(domains.DOMAIN, UNLISTED, settings=SETTINGS, fetched_at="x") is None


def test_a_registry_with_no_rdap_is_said_so_for_that_domain_and_asked_nothing() -> None:
    """`A_REGISTRY_THAT_PUBLISHES_NO_RDAP_IS_SAID_SO`. Delete this and a country domain's expiry is
    answered as a source that could not be reached, or looked up somewhere else."""
    assert server_for(UNPUBLISHED_DOMAIN) is None and server_for(ROUTED) is not None
    reading = domains.DomainsReading()
    with pytest.raises(ConnectorContractError, match="no RDAP"):
        reading.operation_for(
            domains.DOMAIN, {"name": UNPUBLISHED_DOMAIN}, settings=SETTINGS, resolver=Resolver()
        )
    [kept] = reading.unrouted(domains.DOMAIN, settings=SETTINGS, seen_at=LONG_AGO)
    assert (kept.source_id, kept.fields) == (
        UNPUBLISHED_DOMAIN,
        {"name": UNPUBLISHED_DOMAIN, "registration": domains.UNPUBLISHED},
    )
    said = reading.unpublished(
        domains.DOMAIN, UNPUBLISHED_DOMAIN, settings=SETTINGS, fetched_at="2019-03-06T09:00:00Z"
    )
    assert said is not None
    [record] = said.records
    assert record.model_dump()["expiry"] == domains.NOT_PUBLISHED
    assert reading.unpublished(domains.DOMAIN, ROUTED, settings=SETTINGS, fetched_at="x") is None


def test_the_routes_walk_the_routed_domains_in_the_list_s_order_and_stop() -> None:
    """Delete this and a reading reads one domain for ever, or skips the last."""
    reading = domains.DomainsReading()
    settings = {"domains": "a.example.com, b.example.my, c.example.org", "department": "ops"}
    assert reading.first_route(domains.DOMAIN, settings=settings) == {"name": "a.example.com"}
    assert reading.next_route(domains.DOMAIN, {"name": "a.example.com"}, settings=settings) == {
        "name": "c.example.org"
    }
    assert reading.next_route(domains.DOMAIN, {"name": "c.example.org"}, settings=settings) is None
    assert reading.next_route(domains.DOMAIN, {"name": UNLISTED}, settings=settings) is None


def test_the_rdap_snapshot_is_iana_s_list_reduced_to_https() -> None:
    """Held against a bootstrap document of IANA's shape rather than against the snapshot itself.
    Delete this and a plain-HTTP server can be kept, which a network in between can rewrite."""
    document = {
        "services": [
            [["com", "net"], ["http://rdap.one.example/", "https://rdap.one.example/"]],
            [["xyz"], ["http://rdap.two.example/"]],
        ]
    }
    assert dict(from_bootstrap(document)) == {
        "com": "https://rdap.one.example",
        "net": "https://rdap.one.example",
    }
    assert all(base.startswith("https://") for base in RDAP_VENDOR_SERVERS.values())
    assert len(RDAP_VENDOR_SERVERS) > 1000


# ------------------------------------------------------------------------ the site


@pytest.mark.parametrize(
    ("status", "said"),
    [
        (200, "answers (HTTP 200)"),
        (301, "answers (HTTP 301)"),
        (503, "answers with a server error (HTTP 503)"),
        (None, "does not answer"),
    ],
)
def test_hosting_is_what_the_site_itself_answers(status: int | None, said: str) -> None:
    """`HOSTING_IS_WHAT_THE_SITE_ITSELF_ANSWERS`, one call to the domain's own address. Delete this
    and a site that went down reads as hosted."""
    caller = Caller(site_status=status)
    assert domains.hosting_of(ROUTED, caller=caller, resolver=Resolver()) == said
    assert caller.asked == [f"https://{ROUTED}/"]


# ------------------------------------------------------------- the worker and the live read


def test_a_keyless_source_takes_no_lease_and_sends_no_authorization() -> None:
    """`KeyScheme.NONE`. Delete this and every read of a published record asks the vault for a
    key nobody kept, and fails."""
    reading = domains.DomainsReading()
    assert CONNECTABLE[domains.CONNECTOR_NAME].credential_shape is CredentialShape.NONE
    assert reading.key_scheme() is KeyScheme.NONE
    assert isinstance(borrowed(NoKeys(), reading, key_reference("domains"), now=LONG_AGO), Unleased)
    assert "Authorization" not in call_headers(reading, SETTINGS, "")


def test_the_worker_indexes_each_listed_domain_and_asks_only_their_registries() -> None:
    """The scheduled read through `attempt`: the routed domain from its registry, the unpublished
    one kept without a call, nothing else asked. Delete this and the worker can read a domain the
    connection never named, or skip one whose registry publishes nothing."""
    written: list[Any] = []

    class Session:
        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        def begin(self) -> Session:
            return self

        async def execute(self, statement: Any) -> None:
            dialect: Any = postgresql.dialect()  # type: ignore[no-untyped-call]
            written.append(statement.compile(dialect=dialect).params)

    one = connection()
    plan = plan_for(one, last=None, now=LONG_AGO)
    assert not plan.refused
    caller = Caller()
    done = asyncio.run(
        attempt(
            LiveConnection(id=uuid.uuid4(), connection=one),
            plan,
            previous=None,
            sessions=Session,  # type: ignore[arg-type]
            keys=NoKeys(),
            caller=caller,
            resolver=Resolver(),
            clock=lambda: LONG_AGO,
            sleep=lambda seconds: asyncio.sleep(0),
        )
    )
    assert done.outcome is SyncOutcome.SYNCED and done.records == 2
    assert caller.asked == [f"{server_for(ROUTED)}/domain/{ROUTED}"]
    assert all("Authorization" not in sent for sent in caller.headers_sent)
    kept = {params["source_id"]: params for params in written}
    assert set(kept) == {ROUTED, UNPUBLISHED_DOMAIN}
    assert REGISTRAR not in json.dumps(written, default=str)


def read_live(domain: str, caller: Caller) -> Any:
    one = connection()
    sources = ConnectedSources(
        {domains.CONNECTOR_NAME: one},
        keys=NoKeys(),
        caller=caller,
        resolver=Resolver(),
        clock=lambda: LONG_AGO,
    )
    declared = sources._declared(domains.CONNECTOR_NAME)
    assert declared is not None
    return sources.read_one(
        one,
        declared,
        FetchRequest(entity=domains.DOMAIN, filters=((RECORD_ID_FILTER, domain),)),
    )


def test_a_listed_domain_is_read_live_from_its_registry_with_its_site_asked_beside_it() -> None:
    """The live read: registrar and expiry from the registry, hosting from the site, in one reply
    and kept nowhere. Delete this and a question about a registrar is answered from the index."""
    caller = Caller()
    reply = read_live(ROUTED, caller)
    assert reply.outcome is CallOutcome.OK and reply.rows is not None
    [record] = reply.rows.records
    values = record.model_dump()
    assert (values["registrar"], values["hosting"]) == (REGISTRAR, "answers (HTTP 200)")
    assert caller.asked == [f"{server_for(ROUTED)}/domain/{ROUTED}", f"https://{ROUTED}/"]


def test_an_unpublished_domain_is_answered_as_unpublished_with_no_registry_asked() -> None:
    """Delete this and a domain whose registry offers no RDAP is answered as an outage."""
    caller = Caller()
    reply = read_live(UNPUBLISHED_DOMAIN, caller)
    assert reply.outcome is CallOutcome.OK and reply.rows is not None
    [record] = reply.rows.records
    assert record.model_dump()["registrar"] == domains.NOT_PUBLISHED
    assert caller.asked == [f"https://{UNPUBLISHED_DOMAIN}/"]


def test_an_unlisted_domain_is_refused_and_nothing_is_asked() -> None:
    """`ONLY_THE_CONNECTIONS_OWN_DOMAINS_ARE_LOOKED_UP` on the live path. Delete this and a
    question naming any domain makes the install look it up."""
    caller = Caller()
    reply = read_live(UNLISTED, caller)
    assert reply.outcome is CallOutcome.REJECTED
    assert caller.asked == []
