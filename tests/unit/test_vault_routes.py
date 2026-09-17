"""The Secrets vault screen: the seal, every slot, each source's leases and the audit shipping.

`brain.ops.vault_status.report` is driven directly over an in-memory reader for each state the
vault can be in, and `GET /api/v1/vault` through the real application, with the token machinery
imported from `tests/unit/test_api_routes.py` and the connections from `test_connector_routes.py`,
for the reason `test_credential_routes` gives about a second copy of a token builder.

Task ids: M31.3.2.1, M31.3.2.3, M31.3.2.4, M31.3.2.5, M31.3.2.6, M38.4.1.3
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connector_routes import CONNECTORS_READ
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.credential_routes import CREDENTIAL_AUTHORITY
from brain.ops.connector_slots import (
    REFUSE_KEY,
    REQUEST_KEY,
    SLOT_SCOPES,
    SlotScopes,
    metadata_arguments,
    slot_gaps,
)
from brain.ops.connector_sync_store import LeaseTally
from brain.ops.credentials import SLOTS
from brain.ops.openbao import SealStatus, StaticVersion, VaultRefusedError, VaultUnreachableError
from brain.ops.vault_audit_ship import ShippedSince
from brain.ops.vault_status import (
    SEAL_SAYS,
    SLOTS_REFUSED,
    SLOTS_SILENT,
    Seal,
    SlotState,
    report,
)
from brain.vault_routes import (
    AUDIT_SAYS,
    NO_AUDIT_READABLE,
    NO_LEASES_READABLE,
    VAULT_PATH,
)
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, token_for, verifier
from tests.unit.test_connector_routes import Records, a_connection

SCREEN: Final = f"{API_PREFIX}{VAULT_PATH}"
WHOLE: Final = Scope.unrestricted()
ONE_DEPARTMENT: Final = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))
ONE_SOURCE: Final = Scope(clauses=(Clause(field="connector", op=Op.EQ, value="xero"),))
SECOND_FACTOR: Final[Mapping[str, object]] = {"amr": ["otp"]}

#: Far from any plausible wall clock, for CLAUDE.md's reason.
AT: Final = datetime(2019, 3, 4, 5, 6, 7, tzinfo=UTC)

#: `u_narrow` holds the capability over one department and `u_wide` over everything with no
#: connector read; `u_admin` holds it over everything and reads one source.
GRANTS: Final[dict[str, tuple[Grant, ...]]] = {
    "u_none": (),
    "u_narrow": (Grant(capability=CREDENTIAL_AUTHORITY, scope=ONE_DEPARTMENT),),
    "u_wide": (Grant(capability=CREDENTIAL_AUTHORITY, scope=WHOLE),),
    "u_prefix": (),
    "u_admin": (
        Grant(capability=CREDENTIAL_AUTHORITY, scope=WHOLE),
        Grant(capability=CONNECTORS_READ, scope=ONE_SOURCE),
    ),
    "u_elsewhere": (),
}


# ------------------------------------------------------------------------ an in-memory vault
OPEN: Final = SealStatus(initialized=True, sealed=False)


class Reader:
    """`VaultStatusReader` in memory: a seal, versions and defined slots by path, or a failure."""

    def __init__(
        self,
        *,
        seal: SealStatus | Exception = OPEN,
        held: Mapping[str, datetime] | None = None,
        defined: frozenset[str] = frozenset(),
        fail_slots: Exception | None = None,
    ) -> None:
        self._seal = seal
        self._held = dict(held or {})
        self._defined = defined
        self._fail = fail_slots
        self.asked: list[str] = []

    def seal_status(self) -> SealStatus:
        if isinstance(self._seal, Exception):
            raise self._seal
        return self._seal

    def static_kv_version(self, path: str) -> StaticVersion | None:
        self.asked.append(path)
        if self._fail is not None:
            raise self._fail
        stamp = self._held.get(path)
        return None if stamp is None else StaticVersion(written_at=stamp)

    def static_kv_defined(self, path: str) -> bool:
        return path in self._defined or path in self._held


def test_the_seal_is_said_first_and_no_slot_is_asked_of_a_vault_that_is_not_open() -> None:
    """M31.3.2.1: a sealed vault answers every slot as unavailable, so asking reads as a network
    fault. Delete this and a sealed vault sends three people to look for a firewall."""
    for seal, expected in (
        (VaultUnreachableError("silent"), Seal.UNREACHABLE),
        (SealStatus(initialized=False, sealed=True), Seal.UNINITIALISED),
        (SealStatus(initialized=True, sealed=True), Seal.SEALED),
    ):
        reader = Reader(seal=seal)
        found = report(reader)
        assert (found.seal, found.told) == (expected, SEAL_SAYS[expected])
        assert reader.asked == []
        assert {one.state for one in found.providers + found.connectors} == {SlotState.UNKNOWN}
    assert report(None).seal is Seal.ABSENT


def test_an_open_vault_says_which_slots_hold_a_key_and_tells_defined_from_missing() -> None:
    """A provider slot is held or empty; a source's is held, defined and empty, or missing, which
    means the installer's step did not run. Delete this and three states read as one word."""
    held = {"providers/anthropic": AT, SLOT_SCOPES["xero"].path: AT}
    reader = Reader(held=held, defined=frozenset({SLOT_SCOPES["hubspot"].path}))

    found = report(reader)

    providers = {one.slot: (one.state, one.set_at) for one in found.providers}
    connectors = {one.slot: one for one in found.connectors}
    assert set(providers) == set(SLOTS)
    assert providers["providers/anthropic"] == (SlotState.HELD, AT)
    assert providers["providers/openai"] == (SlotState.EMPTY, None)
    assert connectors[SLOT_SCOPES["xero"].path].state is SlotState.HELD
    assert connectors[SLOT_SCOPES["hubspot"].path].state is SlotState.DEFINED
    assert connectors[SLOT_SCOPES["freshdesk"].path].state is SlotState.EMPTY
    assert connectors[SLOT_SCOPES["xero"].path].request == SLOT_SCOPES["xero"].request
    assert found.slots_unread == ""


def test_a_refused_or_silent_slot_read_leaves_every_slot_unknown_and_says_which() -> None:
    """Delete this and a lapsed application token reads as an install with no keys at all."""
    refused = report(Reader(fail_slots=VaultRefusedError("no", status=403)))
    silent = report(Reader(fail_slots=VaultUnreachableError("timeout")))
    assert (refused.seal, refused.slots_unread) == (Seal.OPEN, SLOTS_REFUSED)
    assert silent.slots_unread == SLOTS_SILENT
    assert {one.state for one in refused.providers} == {SlotState.UNKNOWN}


# ------------------------------------------------------------------------ the catalogue
def test_every_source_has_a_slot_with_the_scopes_its_hint_asks_for() -> None:
    """M38.4.1.3: the catalogue matches the sources this build has and the hints the console
    shows. Delete this and a new source ships with no slot, or a slot asks for a scope the person
    connecting is never told to request."""
    assert slot_gaps() == ()


def test_a_scope_the_installer_could_not_quote_is_refused_and_a_plain_one_is_written() -> None:
    """The scopes go into a single-quoted shell argument. Delete this and a quote in a scope ends
    the installer's argument early, and whatever follows it runs as a command under the root
    token."""
    with pytest.raises(ValueError, match="without escaping"):
        SlotScopes("xero", request=("read'; rm -rf /",), refuse=("write",))
    with pytest.raises(ValueError, match="at least one"):
        SlotScopes("xero", request=(), refuse=("write",))
    assert metadata_arguments(SlotScopes("xero", request=("a", "b"), refuse=("c",))) == (
        f"-custom-metadata='{REQUEST_KEY}=a; b' -custom-metadata='{REFUSE_KEY}=c'"
    )


# ------------------------------------------------------------------------------ the route
class Grants:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


class Tallies:
    """`LeaseCounts` in memory, including a source the reader may not be told of."""

    def __init__(self) -> None:
        self.asked: list[datetime] = []

    async def tallies(self, since: datetime) -> Mapping[str, LeaseTally]:
        self.asked.append(since)
        return {
            "xero": LeaseTally(revoked=5, expired=1, not_revoked=2),
            "hubspot": LeaseTally(revoked=9),
        }


class Shipped:
    """`VaultAccessRecords` in memory."""

    async def since(self, instant: datetime) -> ShippedSince:
        return ShippedSince(entries=12, refused=3, last_shipped_at=AT)


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer="https://id.verz.example/realms/brain",
            audience="brain-api",
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=Grants(),
        cache=NoCache(),
    )


class NoDatabase:
    def __call__(self) -> Any:
        raise AssertionError("a database session was opened")


@pytest.fixture
def app() -> Iterator[FastAPI]:
    built: FastAPI = create_app(Settings(env="development"))
    yield built


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = NoDatabase()
        yield c


def screen(c: TestClient, pid: str, claims: Mapping[str, object] = SECOND_FACTOR) -> Response:
    response: Response = c.get(
        SCREEN, headers={"authorization": f"Bearer {token_for(pid, claims=claims)}"}
    )
    return response


def attach(app: FastAPI, reader: Reader | None = None) -> Reader:
    found = reader or Reader(held={"providers/anthropic": AT})
    app.state.vault_reader = found
    app.state.lease_counts = Tallies()
    app.state.vault_access = Shipped()
    app.state.connector_records = Records((a_connection("xero"), a_connection("hubspot")))
    return found


def test_a_caller_without_the_credential_authority_over_everything_is_told_it_is_not_there(
    app: FastAPI, client: TestClient
) -> None:
    """The credentials route's capability and its one refusal. The positive sibling is `u_wide`.
    Delete this and a grant over one department reads the install's seal and slots."""
    reader = attach(app)
    for pid in ("u_none", "u_narrow"):
        refused = screen(client, pid)
        assert refused.status_code == 404
        assert refused.json()["message"] == Absent.public_message
    assert screen(client, "u_wide", claims={"amr": ["pwd"]}).status_code == 404
    assert reader.asked == []
    assert screen(client, "u_wide").status_code == 200


def test_the_screen_shows_the_seal_slots_leases_rotation_and_shipping(
    app: FastAPI, client: TestClient
) -> None:
    """The backend visible in the console: every field the Secrets vault page draws. Delete this
    and the route can drop a section the page then renders as empty."""
    attach(app)
    body = screen(client, "u_admin").json()

    assert body["seal"] == "open"
    assert {one["slot"]: one["state"] for one in body["providers"]}["providers/anthropic"] == "held"
    assert len(body["connectors"]) == len(SLOT_SCOPES)
    assert body["leases"] == [
        {"connector": "xero", "issued": 8, "revoked": 5, "expired": 1, "not_revoked": 2}
    ]
    assert body["lease_ttl_minutes"] == 15
    assert "15 minutes" in body["leases_told"]
    assert "once a minute" in body["rotation"] and "restart" in body["rotation"]
    assert body["audit"] == {
        "entries": 12,
        "refused": 3,
        "last_shipped_at": "2019-03-04T05:06:07Z",
        "told": AUDIT_SAYS,
    }


def test_a_lease_tally_is_shown_only_for_a_source_the_reader_may_be_told_is_connected(
    app: FastAPI, client: TestClient
) -> None:
    """DENIED and ABSENT alike: `u_wide` may read the vault and no source, so it is told of no
    lease and of no count of what was left out, and `u_admin` of its one source. Delete this and
    the screen says which sources are connected to somebody the Connectors screen would not."""
    attach(app)
    wide = screen(client, "u_wide").json()
    admin = screen(client, "u_admin").json()
    assert wide["leases"] == []
    assert [one["connector"] for one in admin["leases"]] == ["xero"]
    assert "hubspot" not in json.dumps(admin["leases"])


def test_a_process_with_no_database_says_so_rather_than_showing_zero(
    app: FastAPI, client: TestClient
) -> None:
    """Delete this and an install whose application has no database reads as one whose worker
    never ran a connector and whose vault was never read."""
    app.state.vault_reader = Reader()
    body = screen(client, "u_admin").json()
    assert (body["leases"], body["leases_told"]) == (None, NO_LEASES_READABLE)
    assert body["audit"]["entries"] is None
    assert body["audit"]["told"] == NO_AUDIT_READABLE


def test_no_answer_carries_a_value_or_a_token(app: FastAPI, client: TestClient) -> None:
    """Metadata, counts and words only. Delete this and a field added later can carry what the
    vault holds."""
    attach(app)
    body = screen(client, "u_admin").text
    assert "hmac-sha256" not in body
    assert "a-token" not in body
