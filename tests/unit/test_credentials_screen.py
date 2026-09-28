"""The Credentials screen's three routes over every slot an install declares: the list, one slot's
page, and a write into any of them, and that nothing sent ever comes back out.

Driven through the real application with the token machinery of `tests/unit/test_credential_routes`,
for that file's reason. The vault is `Slots`, one in-memory vault answering both the store's write
protocol and the screen's reads per path, attached as the store's vault and as the screen's reader,
because on an install the two are the same server asked with the same token.

**M27.8.7 for the widened write is `test_no_answer_of_the_screen_and_no_log_line_carries_a_value`.**
It drives every kind of slot through the write, the list and the page with one sentinel and finds
it nowhere but in the vault, which it proves holds it.

Task ids: M27.11.10, M27.15.50, M27.8.7
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connector_routes import CONNECTORS_READ
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.credential_routes import (
    CREDENTIAL_AUTHORITY,
    CREDENTIALS_PATH,
    NOBODY_NAMED,
    SETUP_WIZARD,
    CredentialRow,
)
from brain.firstrun import GRANTED_BY
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.credential_catalogue import (
    FIRST_SET_ELSEWHERE,
    LIVE_READ_MINT_PATH,
    LIVE_READS_SAY,
    PROVIDER_HOLDERS,
    WRITTEN_AT_THE_SERVER,
    LiveReads,
    SlotKind,
    declared_slots,
)
from brain.ops.credential_write_store import Change
from brain.ops.credentials import KEY_FIELD, Credentials
from brain.ops.openbao import (
    SealStatus,
    StaticVersion,
    TokenStanding,
    VaultRefusedError,
    VaultUnreachableError,
)
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.ops.vault_status import SEAL_SAYS, SLOTS_REFUSED, SLOTS_SILENT, Seal
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, token_for, verifier
from tests.unit.test_connector_routes import Records, a_connection

LISTING: Final = f"{API_PREFIX}{CREDENTIALS_PATH}"
WHOLE: Final = Scope.unrestricted()
SECOND_FACTOR: Final[Mapping[str, object]] = {"amr": ["otp"]}

#: Far from any plausible wall clock, for CLAUDE.md's reason.
AT: Final = datetime(2019, 3, 4, 5, 6, 7, tzinfo=UTC)
AT_JSON: Final = "2019-03-04T05:06:07Z"

#: The sentinel every write sends. A search for it in any answer or log line is the M27.8.7 test.
SENTINEL: Final = "sk-sentinel-Q7x9-never-echoed"

#: `u_admin` holds the capability over everything and nothing about connectors; `u_wide` also
#: reads every source, which is what admits a connection's figures.
GRANTS: Final[dict[str, tuple[Grant, ...]]] = {
    "u_none": (),
    "u_admin": (Grant(capability=CREDENTIAL_AUTHORITY, scope=WHOLE),),
    "u_wide": (
        Grant(capability=CREDENTIAL_AUTHORITY, scope=WHOLE),
        Grant(capability=CONNECTORS_READ, scope=WHOLE),
    ),
}

RELAY: Final = f"{LISTING}/providers/mail_relay"
STORE: Final = f"{LISTING}/providers/seaweedfs"
XERO: Final = f"{LISTING}/connector_keys/xero"
LARK: Final = f"{LISTING}/providers/channel_lark"
ANTHROPIC: Final = f"{LISTING}/providers/anthropic"


OPEN: Final = SealStatus(initialized=True, sealed=False)


class Slots:
    """One vault answering the store's writes and the screen's reads, per path."""

    def __init__(
        self,
        *,
        held: Sequence[str] = (),
        defined: Sequence[str] = (),
        seal: SealStatus = OPEN,
        policies: tuple[str, ...] = ("application", "default"),
        capabilities: tuple[str, ...] = ("create", "update"),
        fail: Exception | None = None,
    ) -> None:
        self.versions: dict[str, StaticVersion] = {
            one: StaticVersion(written_at=AT) for one in held
        }
        self.defined = set(defined)
        self.seal = seal
        self.policies = policies
        self.capabilities = capabilities
        self.fail = fail
        self.written: list[tuple[str, dict[str, str]]] = []
        self.capability_paths: list[str] = []

    def seal_status(self) -> SealStatus:
        return self.seal

    def token_standing(self) -> TokenStanding:
        return TokenStanding(
            ttl_seconds=60, period_seconds=0, renewable=True, policies=self.policies
        )

    def capabilities_self(self, path: str) -> tuple[str, ...]:
        self.capability_paths.append(path)
        return self.capabilities

    def static_kv_version(self, path: str) -> StaticVersion | None:
        if self.fail is not None:
            raise self.fail
        return self.versions.get(path)

    def static_kv_defined(self, path: str) -> bool:
        return path in self.defined or path in self.versions

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        self.written.append((path, dict(fields)))
        if self.fail is not None:
            raise self.fail
        self.versions[path] = StaticVersion(written_at=AT)
        return AT

    def read_static_kv(self, path: str) -> dict[str, Any]:
        raise AssertionError(f"the screen never reads a value, and {path} was read")


class History:
    """`CredentialHistory` in memory, noting what it was asked."""

    def __init__(self, changes: tuple[Change, ...] = (), used: datetime | None = AT) -> None:
        self._changes = changes
        self._used = used
        self.subjects: list[str] = []
        self.used_asked: list[tuple[str, str]] = []

    async def changes(self, subject: str) -> tuple[Change, ...]:
        self.subjects.append(subject)
        return self._changes

    async def last_used(self, kind: str, name: str) -> datetime | None:
        self.used_asked.append((kind, name))
        return self._used


class Recorded:
    """`CredentialWrites` in memory."""

    def __init__(self) -> None:
        self.records: list[dict[str, str]] = []

    async def record(self, *, slot: str, written_by: str, trace_id: str, ent_hash: str) -> None:
        self.records.append({"slot": slot, "written_by": written_by})


class Grants:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


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


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.delenv("INSTALL_OBJECT_STORE_BACKEND", raising=False)
    yield create_app(Settings(env="development", database_url=""))


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        yield c


def holding(
    app: FastAPI,
    vault: Slots | None,
    *,
    outranking: frozenset[str] = frozenset(),
    history: History | None = None,
    writes: Recorded | None = None,
) -> dict[str, str]:
    env: dict[str, str] = {}
    app.state.credentials = Credentials(vault, environ=env, outranking=outranking, writes=writes)
    app.state.vault_reader = vault
    app.state.credential_history = history
    return env


def headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}


def get(c: TestClient, pid: str, path: str = LISTING, **params: str) -> Response:
    response: Response = c.get(path, headers=headers(pid), params=params)
    return response


def put(c: TestClient, pid: str, path: str, body: Mapping[str, object]) -> Response:
    response: Response = c.put(path, headers=headers(pid), json=dict(body))
    return response


def rows(body: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {one["slot"]: one for one in body["items"]}


# ------------------------------------------------------------------------- the catalogue
def test_every_declared_kind_is_a_row_and_a_new_provider_or_source_needs_no_edit_here() -> None:
    """The list is read off the modules that own each kind. Delete this and a slot added to
    `PROVIDER_SLOTS` or `SLOT_SCOPES` can be missing from the one screen that says what the install
    holds, which is the gap the screen exists to close."""
    slots = declared_slots(Credentials(None), backend="seaweedfs")
    paths = {one.path for one in slots}

    assert {one.path for one in PROVIDER_SLOTS} <= paths
    assert {f"connector_keys/{name}" for name in SLOT_SCOPES} <= paths
    assert {"providers/mail_relay", "providers/seaweedfs", "providers/channel_lark"} <= paths
    assert {one.slug for one in PROVIDER_SLOTS} == set(PROVIDER_HOLDERS)
    assert [one.kind for one in slots] == sorted(
        (one.kind for one in slots), key=list(SlotKind).index
    )
    assert "providers/cloudflare-r2" not in paths
    assert not any(
        one.kind is SlotKind.STORE for one in declared_slots(Credentials(None), backend="aws_s3")
    )


# ------------------------------------------------------------------------------ the list
def test_the_list_says_which_slots_hold_a_value_when_and_what_outranks_them_and_never_a_value(
    app: FastAPI, client: TestClient
) -> None:
    """Held with the vault's time, a source's slot defined but empty, a provider outranked by the
    environment, and the vault's seal, policies and live reads above. Delete this and the one
    screen listing every secret can call an outranked key in use, or a defined slot missing."""
    holding(
        app,
        Slots(
            held=("providers/anthropic", "providers/mail_relay"), defined=("connector_keys/xero",)
        ),
        outranking=frozenset({"ANTHROPIC_API_KEY"}),
    )

    answer = get(client, "u_admin")

    assert answer.status_code == 200
    body = answer.json()
    found = rows(body)
    assert found["providers/anthropic"]["held"] is True
    assert found["providers/anthropic"]["set_at"] == AT_JSON
    assert found["providers/anthropic"]["outranked_by"] == "ANTHROPIC_API_KEY"
    assert found["providers/openai"]["state"] == "empty"
    assert found["providers/openai"]["outranked_by"] is None
    assert found["providers/mail_relay"]["kind"] == "relay"
    assert found["connector_keys/xero"]["state"] == "defined"
    assert found["connector_keys/xero"]["held"] is False
    assert found["providers/seaweedfs"]["kind"] == "store"
    assert body["vault"]["seal"] == "open"
    assert body["vault"]["token_policies"] == ["application", "default"]
    assert body["vault"]["live_reads"] == "ready"
    assert body["next_cursor"] is None
    assert set(CredentialRow.model_fields) == {
        "slot",
        "family",
        "name",
        "kind",
        "holder",
        "state",
        "held",
        "set_at",
        "outranked_by",
        "read_by",
        "writable",
        "write_told",
    }


def test_a_sealed_vault_makes_every_slot_unknown_and_offers_no_form(
    app: FastAPI, client: TestClient
) -> None:
    """Not known is not "not held". Delete this and a sealed vault lists every slot empty and
    offers a form, and somebody pastes a key into a vault that cannot keep it."""
    vault = Slots(held=("providers/anthropic",), seal=SealStatus(initialized=True, sealed=True))
    holding(app, vault)

    body = get(client, "u_admin").json()

    assert body["vault"]["seal"] == Seal.SEALED.value
    assert body["vault"]["told"] == SEAL_SAYS[Seal.SEALED]
    assert all(one["held"] is None and one["state"] == "unknown" for one in body["items"])
    assert all(not one["writable"] for one in body["items"])
    assert {one["write_told"] for one in body["items"]} == {SEAL_SAYS[Seal.SEALED]}
    assert vault.capability_paths == []


@pytest.mark.parametrize(
    ("vault", "seal", "unread"),
    [
        (None, Seal.ABSENT, ""),
        (Slots(fail=VaultRefusedError("x", status=403)), Seal.OPEN, SLOTS_REFUSED),
        (Slots(fail=VaultUnreachableError("x")), Seal.OPEN, SLOTS_SILENT),
    ],
)
def test_a_list_the_vault_cannot_answer_says_why_and_calls_no_slot_empty(
    app: FastAPI, client: TestClient, vault: Slots | None, seal: Seal, unread: str
) -> None:
    """No vault, a token the vault refused for the slots, and a vault that went quiet while they
    were read: each says why, and every slot is not known rather than empty. Delete this and an
    unreachable vault lists every slot empty and somebody pastes a key into a vault that is down."""
    holding(app, vault)

    body = get(client, "u_admin").json()

    assert (body["vault"]["seal"], body["vault"]["slots_unread"]) == (seal.value, unread)
    assert body["items"]
    assert all(one["held"] is None and one["set_at"] is None for one in body["items"])
    assert not any(one["writable"] for one in body["items"])


def test_live_reads_are_said_to_wait_until_the_loaded_policy_allows_the_one_mint(
    app: FastAPI, client: TestClient
) -> None:
    """needs-rupash 99: the policy in this release allows the mint and the vault enforces the one
    it loaded. Delete this and the screen says nothing while every question's live read is refused,
    or says it waits on a vault that has already been reloaded."""
    waiting = Slots(capabilities=("deny",))
    holding(app, waiting)
    before = get(client, "u_admin").json()["vault"]
    holding(app, Slots())
    after = get(client, "u_admin").json()["vault"]

    assert waiting.capability_paths == [LIVE_READ_MINT_PATH]
    assert (before["live_reads"], before["live_reads_told"]) == (
        "waiting",
        LIVE_READS_SAY[LiveReads.WAITING],
    )
    assert "load-policies.sh" in before["live_reads_told"]
    assert (after["live_reads"], after["live_reads_told"]) == (
        "ready",
        LIVE_READS_SAY[LiveReads.READY],
    )


def test_a_source_s_slot_is_offered_only_once_it_holds_a_key_and_says_where_the_first_goes(
    app: FastAPI, client: TestClient
) -> None:
    """Delete this and the list offers a form for a source nobody connected, whose key would
    reach nothing any setting accounts for."""
    holding(app, Slots(held=("connector_keys/hubspot",), defined=("connector_keys/xero",)))

    found = rows(get(client, "u_admin").json())

    assert found["connector_keys/hubspot"]["writable"] is True
    assert found["connector_keys/xero"]["writable"] is False
    assert found["connector_keys/xero"]["write_told"] == FIRST_SET_ELSEWHERE[SlotKind.CONNECTOR]
    assert found["providers/channel_lark"]["write_told"] == FIRST_SET_ELSEWHERE[SlotKind.CHANNEL]
    assert found["providers/openai"]["writable"] is True


def test_the_list_filters_and_searches_by_what_a_row_shows(
    app: FastAPI, client: TestClient
) -> None:
    """The list contract, over this list's declared columns. Delete this and the kind filter the
    page offers can be refused by the declaration, or the search can match nothing."""
    holding(app, Slots())

    sources = get(client, "u_admin", filter="kind:connector").json()["items"]
    relay = get(client, "u_admin", q="relay").json()["items"]
    refused = get(client, "u_admin", filter="value:x")

    assert {one["kind"] for one in sources} == {"connector"}
    assert len(sources) == len(SLOT_SCOPES)
    assert [one["slot"] for one in relay] == ["providers/mail_relay"]
    assert refused.status_code == 422


def test_an_object_store_slot_the_ledger_cannot_name_is_listed_and_never_written(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2's slot has a hyphen the ledger's grammar refuses. Delete this and a key pair written from
    the console lands in the vault with no entry saying who wrote it."""
    monkeypatch.setenv("INSTALL_OBJECT_STORE_BACKEND", "cloudflare_r2")
    vault = Slots()
    holding(app, vault)

    found = rows(get(client, "u_admin").json())
    refused = put(
        client,
        "u_admin",
        f"{LISTING}/providers/cloudflare-r2",
        {"values": {"access_key_id": SENTINEL, "secret_access_key": SENTINEL}},
    )

    assert found["providers/cloudflare-r2"]["writable"] is False
    assert found["providers/cloudflare-r2"]["write_told"] == WRITTEN_AT_THE_SERVER
    assert refused.status_code == 404
    assert vault.written == []


# ---------------------------------------------------------------------------- one slot
def test_a_slot_s_page_says_what_it_is_for_what_to_ask_for_its_history_and_last_use(
    app: FastAPI, client: TestClient
) -> None:
    """The Dashboard, Profile and About of one slot. Who wrote each value is named, the setup
    wizard as itself and an actor with no name as such, never as an id in the sentence. Delete
    this and the page can lose its history or name people by their ledger ids."""
    history = History(
        changes=(
            Change(at=AT, actor_id="u_admin", actor_name="Ada Admin"),
            Change(at=AT, actor_id="u_gone", actor_name=None),
            Change(at=AT, actor_id=GRANTED_BY, actor_name=None),
        )
    )
    holding(app, Slots(held=("providers/anthropic",)), history=history)

    body = get(client, "u_admin", ANTHROPIC).json()

    assert body["row"]["holder"] == "Anthropic (Claude)"
    assert body["fields"][0]["field"] == "value"
    assert "1,000 characters" in body["fields"][0]["accepts"]
    assert body["ask_for"] and body["never"]
    assert [one["by"] for one in body["history"]] == ["Ada Admin", NOBODY_NAMED, SETUP_WIZARD]
    assert [one["by_id"] for one in body["history"]] == ["u_admin", "u_gone", GRANTED_BY]
    assert history.subjects == ["credential:providers.anthropic"]
    assert body["last_used_at"] == AT_JSON
    assert history.used_asked == [("provider", "anthropic")]
    assert body["takes_effect"] == "here"


def test_a_source_s_last_read_is_shown_only_to_a_reader_told_of_the_connection(
    app: FastAPI, client: TestClient
) -> None:
    """A source's last read says it is connected and being read, so it is asked only for a reader
    the Connectors screen's rule admits. Delete this and a reader who may replace keys but not see
    connections learns which sources are live off this page."""
    history = History()
    holding(app, Slots(held=("connector_keys/xero",)), history=history)
    app.state.connector_records = Records((a_connection("xero"),))

    hidden = get(client, "u_admin", XERO).json()
    shown = get(client, "u_wide", XERO).json()

    assert hidden["last_used_at"] is None
    assert shown["last_used_at"] == AT_JSON
    assert history.used_asked == [("connector", "xero")]


def test_a_slot_nobody_declares_and_a_reader_without_the_authority_get_one_refusal(
    app: FastAPI, client: TestClient
) -> None:
    """Delete this and the page answers a stranger, or tells a missing slot from a refused one."""
    holding(app, Slots())

    stranger = get(client, "u_none", ANTHROPIC)
    missing = get(client, "u_admin", f"{LISTING}/providers/nobody")
    listing = get(client, "u_none")

    assert (stranger.status_code, missing.status_code, listing.status_code) == (404, 404, 404)
    assert stranger.json()["message"] == missing.json()["message"]


# ---------------------------------------------------------------------------- the writes
def test_the_relay_s_password_is_written_under_the_field_the_sender_reads(
    app: FastAPI, client: TestClient
) -> None:
    """`brain.ops.mail.MailPassword.read` reads `password`. Delete this and a password written here
    lands under `api_key`, the relay reads nothing, and every message fails to sign in."""
    vault, writes = Slots(), Recorded()
    holding(app, vault, writes=writes)

    answer = put(client, "u_admin", RELAY, {"value": f"{SENTINEL}\n"})

    assert answer.status_code == 200
    assert answer.json()["in_use"] == "next_use"
    assert vault.written == [("providers/mail_relay", {"password": SENTINEL})]
    assert writes.records == [{"slot": "providers/mail_relay", "written_by": "u_admin"}]


def test_the_object_store_s_key_pair_is_one_write_of_both_fields_and_says_to_restart(
    app: FastAPI, client: TestClient
) -> None:
    """Both fields in one version, because a pair written a field at a time stands for a moment as
    a key no store accepts; and the answer says a restart is what puts it to use, and that the file
    store must hold the same pair. Delete this and the pair can be split, or the screen reports a
    key in use that nothing reads until the next start."""
    vault = Slots()
    holding(app, vault)

    one_value = put(client, "u_admin", STORE, {"value": SENTINEL})
    half = put(client, "u_admin", STORE, {"values": {"access_key_id": SENTINEL}})
    both = put(
        client,
        "u_admin",
        STORE,
        {"values": {"access_key_id": "AKID", "secret_access_key": SENTINEL}},
    )

    assert (one_value.status_code, half.status_code, both.status_code) == (422, 422, 200)
    assert vault.written == [
        ("providers/seaweedfs", {"access_key_id": "AKID", "secret_access_key": SENTINEL})
    ]
    assert both.json()["in_use"] == "at_start"
    assert "restart the system" in both.json()["told"]
    assert "identities file" in both.json()["told"]


def test_a_source_s_key_is_replaced_here_only_once_its_slot_holds_one(
    app: FastAPI, client: TestClient
) -> None:
    """The refusal and its positive sibling. Delete this and the credentials screen writes a first
    key for a source nobody connected, or refuses to replace one that is connected."""
    vault = Slots(held=("providers/channel_lark",))
    holding(app, vault)

    first = put(client, "u_admin", XERO, {"value": SENTINEL})
    vault.versions["connector_keys/xero"] = StaticVersion(written_at=AT)
    replaced = put(client, "u_admin", XERO, {"value": SENTINEL})
    channel = put(client, "u_admin", LARK, {"value": SENTINEL})

    assert first.status_code == 409
    assert first.json()["message"] == FIRST_SET_ELSEWHERE[SlotKind.CONNECTOR]
    assert (replaced.status_code, channel.status_code) == (200, 200)
    assert vault.written == [
        ("connector_keys/xero", {KEY_FIELD: SENTINEL}),
        ("providers/channel_lark", {KEY_FIELD: SENTINEL}),
    ]
    assert replaced.json()["in_use"] == "next_use"


# ------------------------------------------------------------------------------ M27.8.7
def test_no_answer_of_the_screen_and_no_log_line_carries_a_value(
    app: FastAPI,
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every kind of slot written with one sentinel, a bad paste, a wrong shape, a refused first
    key, a silent vault and a refusing one, then the list and every slot's page read back. Every
    body, header and log line is searched. **The positive half:** the vault holds the sentinel in
    every slot written, so a screen that stored nothing could not pass. Delete this and the widened
    write has no proof that it keeps M27.8.7."""
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    seen: list[str] = []

    def record(response: Response) -> int:
        seen.append(response.text)
        seen.extend(f"{name}: {value}" for name, value in response.headers.items())
        return response.status_code

    vault = Slots(held=("connector_keys/hubspot", "providers/channel_lark"))
    holding(
        app, vault, history=History(changes=(Change(at=AT, actor_id="u_admin", actor_name="A"),))
    )
    assert record(put(client, "u_admin", ANTHROPIC, {"value": SENTINEL})) == 200
    assert record(put(client, "u_admin", RELAY, {"value": SENTINEL})) == 200
    pair = {"access_key_id": SENTINEL, "secret_access_key": SENTINEL}
    assert record(put(client, "u_admin", STORE, {"values": pair})) == 200
    assert (
        record(put(client, "u_admin", f"{LISTING}/connector_keys/hubspot", {"value": SENTINEL}))
        == 200
    )
    assert record(put(client, "u_admin", LARK, {"value": SENTINEL})) == 200
    assert record(put(client, "u_admin", XERO, {"value": SENTINEL})) == 409
    assert record(put(client, "u_admin", RELAY, {"value": f"{SENTINEL} x"})) == 422
    assert record(put(client, "u_admin", STORE, {"values": {"access_key_id": SENTINEL}})) == 422
    assert record(put(client, "u_admin", RELAY, {"value": SENTINEL, "also": SENTINEL})) == 422
    assert record(put(client, "u_none", RELAY, {"value": SENTINEL})) == 404
    assert record(get(client, "u_admin")) == 200
    for slot in [one["slot"] for one in rows(get(client, "u_admin").json()).values()]:
        assert record(get(client, "u_admin", f"{LISTING}/{slot}")) == 200
    holding(app, Slots(fail=VaultUnreachableError("did not answer")))
    assert record(put(client, "u_admin", RELAY, {"value": SENTINEL})) == 503
    holding(app, Slots(fail=VaultRefusedError("refused", status=403)))
    assert record(put(client, "u_admin", XERO, {"value": SENTINEL})) == 409

    written = capsys.readouterr()
    logged = "\n".join([written.out, written.err, caplog.text])
    assert SENTINEL not in "\n".join(seen)
    assert SENTINEL not in logged
    stored = dict(vault.written)
    assert stored["providers/anthropic"] == {KEY_FIELD: SENTINEL}
    assert stored["providers/mail_relay"] == {"password": SENTINEL}
    assert stored["providers/seaweedfs"] == pair
    assert stored["connector_keys/hubspot"] == {KEY_FIELD: SENTINEL}
    assert "credential kept" in logged and "credential refused" in logged
