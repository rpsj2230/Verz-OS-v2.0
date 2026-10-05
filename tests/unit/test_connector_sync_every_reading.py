"""Every shipped connector with a reading, read through the worker's attempt from its recordings.

**No unit test drove a Google source's scheduled read through `connector_sync_run.attempt` until
2026-10-05**, and the gap was found the expensive way. A merge left a stray line building the
call's headers from the lease's key before `presented` had exchanged it for a token, so every
Google sync refused with `A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER`, and only the Google Analytics
install check caught it. Each source's own tests drive its reading's parts; nothing drove the
attempt that strings them together, for every source at once.

So this drives `attempt`, the function the worker calls, once per shipped reading, found by
discovery (`READINGS`, read off every connector's own `CONNECTOR`), so a connector added is driven
here with nothing typed. Each call is answered with that connector's own recorded first page from
its cassette file, chosen by the path the reading asked for; a key file is exchanged through a
poster answering with a recorded token; and the key arrives through a fake lease. What it asserts
is the worker's whole path: the attempt reads to an end, keeps the index rows the recording holds,
and never puts a key file into a header.

**A reading this cannot drive from its recordings is named in `NOT_DRIVEN` with the reason**:
Cloudflare's DNS records, listed under every zone its zones page names when only one zone's are
recorded; the domains source, routed to each registry; and the Laravel database, read as views over
a database connection. Xero (a bearer key) and Google Analytics (a key file exchanged for a token)
are the anchors, so a discovery that found nothing fails rather than passing by having nothing to
drive.

Task ids: M11.1.6, M11.7.1
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast
from urllib.parse import urlsplit

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import Select

from brain.connectors.declaration import KeyScheme, ViewReading
from brain.connectors.manifest import manifest_digest
from brain.ops.connectable import manifest_for
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import READINGS, SyncOutcome, plan_for
from brain.ops.connector_sync_run import ConnectorKeyAbsentError, SourceAnswer, attempt
from brain.ops.connector_sync_store import LiveConnection
from brain.ops.secrets import SecretRef
from tests.fixtures.cassettes import CASSETTES, FILES, Cassette, Kind
from tests.fixtures.connector_examples import example_settings

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
CONNECTED_AT: Final = datetime(2019, 1, 1, tzinfo=UTC)

#: How long each call is taken to last, so no reading waits on its own limiter between pages.
A_CALL_TAKES: Final = timedelta(seconds=10)

#: A bearer key, made up, and never anybody's.
KEY: Final = "SOURCE-KEY-SENTINEL-every-reading"

#: The one public address every name answers with. Nothing is fetched by anything here.
PUBLIC: Final = "93.184.216.34"

#: Readings this test cannot drive from their recordings, by name, with the reason. A reading
#: routed by its settings, listed under another source's recordings or read through a database
#: view rather than a GET belongs here, said in words, rather than being silently skipped.
NOT_DRIVEN: Final[Mapping[str, str]] = {
    "cloudflare": (
        "a listed-under reading: its DNS records are walked under every zone the zones page "
        "names, and the recordings hold one zone's records, so the second zone's call has no "
        "recording to answer it"
    ),
    "domains": (
        "a routed reading: each domain is read from the registry its suffix names, chosen from the "
        "RDAP server list, so the address it asks is not a path any recording was made at"
    ),
    "laravel": (
        "a view reading, read over a database connection through the bounded executor rather "
        "than by a GET, so no HTTP recording can answer it; its executor is driven by test_laravel"
    ),
}

#: Which recording answers a call when several share its path: a page that ends, then one record,
#: then a full page, which the reading follows until the page cap.
PREFERRED: Final = (Kind.LIST, Kind.READ, Kind.PAGINATION)


class Resolver:
    def resolve(self, host: str) -> list[str]:
        del host
        return [PUBLIC]


@dataclass
class Clock:
    """Each reading of the clock is one call later than the last."""

    at: datetime = NOW

    def __call__(self) -> datetime:
        self.at += A_CALL_TAKES
        return self.at


async def no_sleep(seconds: float) -> None:
    del seconds


@dataclass
class Leased:
    given: str
    closed: list[datetime] = field(default_factory=list)

    def key(self) -> str:
        return self.given

    def user(self) -> str:
        raise ConnectorKeyAbsentError("a key slot keeps no user")

    def close(self, now: datetime) -> LeaseOutcome:
        self.closed.append(now)
        return LeaseOutcome.REVOKED


@dataclass
class Keys:
    """`ConnectorKeys` leasing one key, which is a key file for a source that takes one."""

    given: str
    asked: list[SecretRef] = field(default_factory=list)

    def lease(self, ref: SecretRef, *, now: datetime) -> Leased:
        del now
        self.asked.append(ref)
        return Leased(self.given)


def scheme(name: str) -> KeyScheme:
    """How `name`'s reading presents its key. A view reading presents none and is not driven."""
    reading = READINGS[name]
    assert not isinstance(reading, ViewReading), f"{name} is read as views, not by a GET"
    return reading.key_scheme()


def path_of(request: str) -> tuple[str, str]:
    """A recording's method and path, from its request line."""
    method, _, rest = request.partition(" ")
    return method, urlsplit(rest.split(" ", 1)[0]).path


def answer_of(recorded: Cassette) -> SourceAnswer:
    return SourceAnswer(
        status=recorded.status,
        headers={name.lower(): value for name, value in recorded.headers.items()},
        body=json.dumps(recorded.body).encode("utf-8"),
    )


@dataclass
class Recorded:
    """`SourceCaller` answering each GET with this source's own 200 recording of that path."""

    source: str
    asked: list[tuple[str, Mapping[str, str]]] = field(default_factory=list)
    answered: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del address, max_bytes
        self.asked.append((url, dict(headers)))
        wanted = urlsplit(url).path
        found = sorted(
            (
                one
                for one in FILES[self.source].cassettes
                if one.status == 200 and path_of(one.request) == ("GET", wanted)
            ),
            key=lambda one: PREFERRED.index(one.kind) if one.kind in PREFERRED else len(PREFERRED),
        )
        if not found:
            return SourceAnswer(status=404, headers={}, body=b"{}")
        self.answered.append(found[0].cid)
        return answer_of(found[0])


def recorded_token(source: str) -> Cassette:
    """The source's own recorded token answer, or Google's from the corpus: one endpoint answers
    every Google source, so a source with no token recording of its own is answered as it is."""
    tokens = [one for one in CASSETTES if one.status == 200 and path_of(one.request)[1] == "/token"]
    own = [one for one in tokens if one.source == source]
    assert tokens, "no token answer is recorded anywhere, so no key file can be exchanged here"
    return (own or tokens)[0]


@dataclass
class Poster:
    """`SourcePoster` answering a token exchange with a recorded token."""

    source: str
    posted: list[str] = field(default_factory=list)

    def post(
        self,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        del address, headers, body, max_bytes
        self.posted.append(url)
        return answer_of(recorded_token(self.source))


@dataclass
class Sessions:
    """A session factory that keeps every statement it is handed and opens no connection."""

    executed: list[Any] = field(default_factory=list)

    def __call__(self) -> Sessions:
        return self

    def begin(self) -> Sessions:
        return self

    async def __aenter__(self) -> Sessions:
        return self

    async def __aexit__(self, *raised: object) -> None:
        del raised

    async def execute(self, statement: Any) -> Any:
        if isinstance(statement, Select):
            # The read a page makes before it is written (M11.8.7): this factory keeps nothing,
            # so it finds nothing, and it is not a statement the run wrote.
            return NothingKept()
        self.executed.append(statement)
        return None


class NothingKept:
    """The answer to a read of a store that holds nothing."""

    def all(self) -> list[Any]:
        return []


@pytest.fixture(scope="module")
def key_file() -> str:
    """A service account's key file in the shape Google's console downloads, with a fresh key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return json.dumps(
        {
            "type": "service_account",
            "private_key_id": "PRIVATE-KEY-ID-SENTINEL",
            "private_key": pem,
            "client_email": "reader@project.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


def drive(name: str, key_file: str) -> tuple[Any, Recorded, Poster, Sessions]:
    """One attempt at `name`'s connection, as the worker makes it, answered from its recordings."""
    settings = {**example_settings(name), **FILES[name].recorded_under}
    connection = Connection(
        connector=name,
        settings=settings,
        digest=manifest_digest(manifest_for(name, settings)),
        connected_by="u_admin",
        connected_at=CONNECTED_AT,
    )
    plan = plan_for(connection, last=None, now=NOW)
    assert plan.refused == "", (name, plan.refused)
    google = scheme(name) is KeyScheme.GOOGLE_SERVICE_ACCOUNT
    caller, poster, sessions = Recorded(name), Poster(name), Sessions()
    done = asyncio.run(
        attempt(
            LiveConnection(id=uuid.uuid4(), connection=connection),
            plan,
            previous=None,
            # A stand-in for `async_sessionmaker`: `attempt` only opens a session and executes.
            sessions=cast(Any, sessions),
            keys=Keys(key_file if google else KEY),
            caller=caller,
            resolver=Resolver(),
            clock=Clock(),
            sleep=no_sleep,
            poster=poster,
        )
    )
    return done, caller, poster, sessions


@pytest.mark.parametrize("name", sorted(READINGS))
def test_every_shipped_reading_is_read_from_its_recordings_through_the_workers_attempt(
    name: str, key_file: str
) -> None:
    """The worker's whole path, for every reading this release ships: the lease's key, presented
    as the source takes it, every entity's first page asked for and answered with the source's
    own recording, the index rows kept, and the attempt read to an end. A key file is exchanged
    for a token through the poster and is never in a header: every Google call carries the
    recorded token and nothing of the file.

    Delete this and a line in `attempt` can send a Google source's key file where its token
    belongs, which refuses every Google sync on every install and is caught only by an install
    check, as it was on 2026-10-05."""
    if name in NOT_DRIVEN:
        pytest.skip(NOT_DRIVEN[name])
    done, caller, poster, sessions = drive(name, key_file)

    assert done.outcome is SyncOutcome.SYNCED, (name, done.detail)
    assert caller.answered, f"{name}: no call was answered by a recording"
    assert done.records >= 1 and sessions.executed, (name, caller.answered)
    google = scheme(name) is KeyScheme.GOOGLE_SERVICE_ACCOUNT
    token = recorded_token(name).body["access_token"]
    for url, headers in caller.asked:
        sent = " ".join(headers.values())
        assert "PRIVATE KEY" not in sent and "service_account" not in sent, (name, url)
        if google:
            assert headers["Authorization"] == f"Bearer {token}", (name, url)
    assert bool(poster.posted) is google, name


def test_the_discovery_drives_a_bearer_source_and_a_google_source() -> None:
    """**The anchors.** Xero's key is a bearer key and Google Analytics' a key file exchanged for a
    token, and both are driven above rather than skipped. Delete this and a discovery that found
    no reading, or a `NOT_DRIVEN` that grew to hold every Google source, passes the parametrised
    test by having nothing to drive."""
    driven = set(READINGS) - set(NOT_DRIVEN)

    assert {"xero", "google_analytics"} <= driven
    assert scheme("xero") is KeyScheme.BEARER
    assert scheme("google_analytics") is KeyScheme.GOOGLE_SERVICE_ACCOUNT
    assert all(name in READINGS for name in NOT_DRIVEN)
