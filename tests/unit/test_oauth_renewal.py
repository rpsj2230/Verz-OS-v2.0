"""A consented source's access renewed by the read that needs it, rotations kept, refusals said.

Over `brain.ops.connector_sync_run.presented`, `renewed_access`, `presenting_detail` and
`WorkerConnectorKeys.rotate`, which the scheduled read, the test of a connection and the live read
all call, with a recorded token endpoint and a vault that answers each token by its policy. No
database: what reaches the attempt table is `tests/unit/test_acceptance_oauth.py`'s, against
PostgreSQL. Every refusal here has a sibling that renews.

Task ids: M11.8.6
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import parse_qs

import pytest

from brain.connectors.contract import ConnectorContractError, HealthState
from brain.connectors.declaration import (
    ConnectorDeclaration,
    DeclarationError,
    KeyScheme,
)
from brain.connectors.google_token import AccessToken, TokenNotIssuedError
from brain.connectors.oauth import (
    A_CONSENTED_SOURCE_IS_SENT_ONLY_ITS_ACCESS,
    CONSENT_WITHDRAWN,
    ConsentNotHeldError,
    ConsentWithdrawnError,
    OAuthConsent,
    RotatedTokenNotKeptError,
)
from brain.connectors.throttle import CallOutcome
from brain.ops.acceptance_checks_oauth import (
    CLIENT_ID_SETTING,
    VENDOR_EXCHANGE,
    consented_xero,
)
from brain.ops.connectable import key_reference, refresh_reference
from brain.ops.connector_lease import ROTATE_POLICY, ROTATE_TOKEN_ROLE, LeaseOutcome
from brain.ops.connector_sync import (
    NO_KEY,
    NOT_CONSENTED,
    ROTATED_REFRESH_NOT_KEPT,
    plan_for,
)
from brain.ops.connector_sync_run import (
    ConnectorKeyAbsentError,
    Consenting,
    SourceAnswer,
    WorkerConnectorKeys,
    authorization,
    presented,
    presenting_detail,
)
from brain.ops.credentials import KEY_FIELD
from brain.ops.leases import SealedSecret
from brain.ops.openbao import RoleToken, VaultRefusedError
from brain.ops.secrets import SecretRef, SecretsUnavailableError

#: A clock far from any wall clock, for CLAUDE.md's reason about dates in fixtures.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
PUBLIC: Final = "93.184.216.34"
SECRET: Final = "CLIENT-SECRET-SENTINEL-71c0"
REFRESH: Final = "REFRESH-SENTINEL-0a4f"
CLIENT: Final = "client-4411"
SETTINGS: Final = {"tenant_id": "11111111-2222-3333-4444-555555555555", CLIENT_ID_SETTING: CLIENT}


class Resolver:
    def resolve(self, host: str) -> list[str]:
        del host
        return [PUBLIC]


@dataclass
class Lease:
    given: str | None
    closed: int = 0

    def key(self) -> str:
        if self.given is None:
            raise ConnectorKeyAbsentError(NO_KEY)
        return self.given

    def user(self) -> str:
        raise AssertionError("a consented source's lease was asked for a user")

    def close(self, now: datetime) -> LeaseOutcome:
        del now
        self.closed += 1
        return LeaseOutcome.REVOKED


@dataclass
class Keys:
    """`ConnectorKeys` over slots by path, and `RotatesRefreshTokens` noting what it wrote."""

    slots: dict[str, str] = field(default_factory=dict)
    leases: list[Lease] = field(default_factory=list)
    rotated: list[tuple[str, str]] = field(default_factory=list)
    refuse_rotation: bool = False

    def lease(self, ref: SecretRef, *, now: datetime) -> Lease:
        del now
        self.leases.append(Lease(self.slots.get(ref.path)))
        return self.leases[-1]

    def rotate(self, ref: SecretRef, token: str, *, now: datetime) -> None:
        del now
        if self.refuse_rotation:
            raise VaultRefusedError("refused", status=403)
        self.rotated.append((ref.path, token))
        self.slots[ref.path] = token


@dataclass
class LeasesOnly:
    """`ConnectorKeys` that can lease and cannot write a rotated token back."""

    slots: dict[str, str]

    def lease(self, ref: SecretRef, *, now: datetime) -> Lease:
        del now
        return Lease(self.slots.get(ref.path))


@dataclass
class Endpoint:
    """A token endpoint answering every post with `answer`, noting each form it was sent."""

    answer: SourceAnswer
    forms: list[dict[str, str]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)

    def post(
        self, url: str, *, address: str, headers: Mapping[str, str], body: bytes, max_bytes: int
    ) -> SourceAnswer:
        del address, headers, max_bytes
        self.urls.append(url)
        self.forms.append({k: v[0] for k, v in parse_qs(body.decode("ascii")).items()})
        return self.answer


def issued(*, refresh: str | None = None) -> SourceAnswer:
    body: dict[str, Any] = {"access_token": "ACCESS-1", "token_type": "Bearer"}
    if refresh is not None:
        body["refresh_token"] = refresh
    return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode())


def a_reading() -> Any:
    return consented_xero()[1]


def held() -> Keys:
    return Keys(
        slots={
            key_reference("xero").path: SECRET,
            refresh_reference("xero").path: REFRESH,
        }
    )


def present(keys: Any, endpoint: Endpoint | None) -> str | AccessToken:
    return presented(
        a_reading(),
        SECRET,
        poster=endpoint,
        resolver=Resolver(),
        now=NOW,
        consenting=Consenting("xero", SETTINGS, keys),
    )


# ------------------------------------------------------------------ renewing access
def test_access_is_renewed_from_the_kept_refresh_token_and_sent_as_a_bearer_token() -> None:
    """The read posts the kept refresh token with the client id from the connection's settings and
    the client secret the lease holds, to the consent's own token endpoint, and presents the access
    token it got back, which is what the source's header carries. The refresh token's lease is given
    back before anything is posted.

    Delete this and a read could present the client secret, or renew at an address the consent did
    not name, with every other test green."""
    keys, endpoint = held(), Endpoint(issued())
    shown = present(keys, endpoint)
    assert isinstance(shown, AccessToken) and shown.value == "ACCESS-1"
    assert endpoint.urls == [VENDOR_EXCHANGE]
    assert endpoint.forms == [
        {
            "grant_type": "refresh_token",
            "refresh_token": REFRESH,
            "client_id": CLIENT,
            "client_secret": SECRET,
        }
    ]
    assert [one.closed for one in keys.leases] == [1]
    assert authorization(KeyScheme.OAUTH_REFRESH, shown) == "Bearer ACCESS-1"
    assert not keys.rotated


def test_a_consented_source_s_header_is_never_built_from_its_client_secret() -> None:
    """`A_CONSENTED_SOURCE_IS_SENT_ONLY_ITS_ACCESS`: a caller that skipped the renewal and handed
    the header the key it leased is refused, rather than sending the client secret to the source.
    The sibling above builds the header from an access token. Delete this and a path that forgot to
    renew sends the secret in `Authorization`."""
    with pytest.raises(ConnectorContractError) as refused:
        authorization(KeyScheme.OAUTH_REFRESH, SECRET)
    assert str(refused.value) == A_CONSENTED_SOURCE_IS_SENT_ONLY_ITS_ACCESS


def test_a_refresh_token_the_vendor_rotated_is_written_back_and_one_it_repeated_is_not() -> None:
    """A vendor that rotates answers with a new refresh token and voids the old, so the read writes
    it back to the refresh token's own slot; a vendor that sends the same one back has rotated
    nothing and nothing is written. Delete this and a rotating vendor's consent is lost on its first
    renewal, or every renewal writes the vault for nothing."""
    keys = held()
    present(keys, Endpoint(issued(refresh="REFRESH-2")))
    assert keys.rotated == [(refresh_reference("xero").path, "REFRESH-2")]
    again = held()
    present(again, Endpoint(issued(refresh=REFRESH)))
    assert not again.rotated


@pytest.mark.parametrize("keys", [LeasesOnly, "refusing"])
def test_a_rotated_token_the_vault_would_not_keep_fails_the_read_in_words(keys: Any) -> None:
    """Keys that cannot write back, and a vault that refused the write, both fail the read with
    `ROTATED_REFRESH_NOT_KEPT`, because the vendor voided the old token and the next read has
    nothing to renew with. The sibling above keeps it. Delete this and the read succeeds while
    the consent is silently lost."""
    slots = held().slots
    given = LeasesOnly(slots) if keys is LeasesOnly else Keys(slots=slots, refuse_rotation=True)
    with pytest.raises(RotatedTokenNotKeptError) as failed:
        present(given, Endpoint(issued(refresh="REFRESH-2")))
    assert presenting_detail(failed.value, poster=Endpoint(issued())) == ROTATED_REFRESH_NOT_KEPT


@pytest.mark.parametrize("status", [400, 401])
def test_a_renewal_the_vendor_refuses_is_the_consent_withdrawn(status: int) -> None:
    """RFC 6749's `invalid_grant` (400) and an unknown client (401) are the consent withdrawn, said
    in `CONSENT_WITHDRAWN`'s words; the sibling below is ill health. Delete this and a revoked
    consent is reported as a declined key, which tells the person to replace a key nobody gave."""
    refused = SourceAnswer(status=status, headers={}, body=b'{"error": "invalid_grant"}')
    endpoint = Endpoint(refused)
    with pytest.raises(ConsentWithdrawnError) as failed:
        present(held(), endpoint)
    assert failed.value.call is CallOutcome.REJECTED
    assert presenting_detail(failed.value, poster=endpoint) == CONSENT_WITHDRAWN


@pytest.mark.parametrize("status", [429, 503])
def test_a_renewal_the_endpoint_cannot_answer_now_is_ill_health_and_not_a_withdrawal(
    status: int,
) -> None:
    """A 429 or a 5xx from the token endpoint is the endpoint's ill health, retried on the backoff,
    and never `CONSENT_WITHDRAWN`, which would send somebody to consent again for nothing. Delete
    this and a busy vendor reads as a revoked consent."""
    endpoint = Endpoint(SourceAnswer(status=status, headers={}, body=b"{}"))
    with pytest.raises(TokenNotIssuedError) as failed:
        present(held(), endpoint)
    assert not isinstance(failed.value, ConsentWithdrawnError)
    assert presenting_detail(failed.value, poster=endpoint) != CONSENT_WITHDRAWN


def test_a_source_nobody_consented_to_says_so_and_posts_nothing() -> None:
    """With no refresh token in its slot the read says `NOT_CONSENTED` and the vendor is asked
    nothing. Delete this and an unconsented source posts an empty grant to the vendor on every
    run, or reads as a missing key."""
    keys, endpoint = Keys(slots={key_reference("xero").path: SECRET}), Endpoint(issued())
    with pytest.raises(ConsentNotHeldError) as failed:
        present(keys, endpoint)
    assert presenting_detail(failed.value, poster=endpoint) == NOT_CONSENTED
    assert not endpoint.forms


def test_a_process_given_no_way_to_post_renews_nothing() -> None:
    """A consented source read by a process with no poster, or with no consent to renew by, is
    refused before the vault is asked for the refresh token. Delete this and a live read built
    without a poster would fall back to presenting something else."""
    keys = held()
    with pytest.raises(TokenNotIssuedError):
        present(keys, None)
    with pytest.raises(TokenNotIssuedError):
        presented(a_reading(), SECRET, poster=Endpoint(issued()), resolver=Resolver(), now=NOW)
    assert not keys.leases


# ------------------------------------------------------------------ writing a rotated token back
@dataclass
class Writer:
    """A rotation token's client: patches and revocations noted."""

    patches: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    revoked: int = 0

    def patch_static_kv(self, path: str, fields: Mapping[str, str]) -> None:
        self.patches.append((path, dict(fields)))

    def read_static_kv(self, path: str) -> dict[str, Any]:
        raise AssertionError(f"a rotation token read {path}")

    def revoke_self(self) -> None:
        self.revoked += 1


@dataclass
class RotateVault:
    """`RunTokenVault` minting with the policies it is told to, and handing out one writer."""

    policies: tuple[str, ...] = (ROTATE_POLICY,)
    minted: list[tuple[str, timedelta]] = field(default_factory=list)
    writer: Writer = field(default_factory=Writer)

    def mint_role_token(self, role: str, *, ttl: timedelta, meta: Mapping[str, str]) -> RoleToken:
        del meta
        self.minted.append((role, ttl))
        return RoleToken(
            token=SealedSecret("child"),
            accessor="a",
            lease_seconds=int(ttl.total_seconds()),
            renewable=False,
            policies=self.policies,
        )

    def holding(self, token: RoleToken) -> Writer:
        del token
        return self.writer


def test_a_rotation_is_written_by_a_rotate_token_that_patches_one_field_and_is_revoked() -> None:
    """`A_ROTATED_GRANT_IS_WRITTEN_BACK_BY_A_ROLE_THAT_CANNOT_READ_IT`, on the worker's side: the
    write is made with a child token minted against the rotate role, patching the key field of the
    refresh token's slot and nothing else, and the token is revoked after. Delete this and the
    write can move to the run token or the worker's own, which read every key."""
    vault = RotateVault()
    WorkerConnectorKeys(vault).rotate(refresh_reference("xero"), "REFRESH-2", now=NOW)
    assert [role for role, _ in vault.minted] == [ROTATE_TOKEN_ROLE]
    assert vault.writer.patches == [(refresh_reference("xero").path, {KEY_FIELD: "REFRESH-2"})]
    assert vault.writer.revoked == 1


def test_a_rotation_aimed_at_a_key_slot_is_refused_before_the_vault_is_asked() -> None:
    """A reference outside the refresh token directory, a source's key among them, is refused with
    no token minted. The sibling above writes a refresh token's slot. Delete this and a rotated
    value could be written over a source's key."""
    vault = RotateVault()
    bare = SecretRef(path="connector_keys/oauth_refresh/", role=key_reference("xero").role)
    for ref in (key_reference("xero"), bare):
        with pytest.raises(SecretsUnavailableError):
            WorkerConnectorKeys(vault).rotate(ref, "REFRESH-2", now=NOW)
    assert not vault.minted
    with pytest.raises(SecretsUnavailableError):
        WorkerConnectorKeys(None).rotate(refresh_reference("xero"), "REFRESH-2", now=NOW)


def test_a_rotation_token_the_vault_widened_writes_nothing_and_is_revoked() -> None:
    """A rotation token carrying a policy besides `connector-rotate` is refused by `judge_minted`
    and revoked without writing. Delete this and a role configured wider at install hands a
    rotation the run token's read of every key."""
    vault = RotateVault(policies=(ROTATE_POLICY, "connector-run"))
    with pytest.raises(VaultRefusedError):
        WorkerConnectorKeys(vault).rotate(refresh_reference("xero"), "REFRESH-2", now=NOW)
    assert not vault.writer.patches
    assert vault.writer.revoked == 1


# ------------------------------------------------------------------ the test of a connection
def test_a_test_of_a_source_whose_consent_was_withdrawn_is_down_in_words() -> None:
    """The test of a connection presents the source's credential through the same `presented`,
    so a withdrawn consent fails a test with the scheduled read's sentence and is down at once;
    with the consent held, the same test renews and calls the source. Delete this and the test
    button reports a withdrawn consent as a declined key."""
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_probe_run import probe_one
    from brain.ops.connector_store import Connection
    from brain.ops.connector_sync_store import LiveConnection

    connection = Connection(
        connector="xero",
        settings=SETTINGS,
        digest=manifest_digest(manifest_for("xero", SETTINGS)),
        connected_by="u_admin",
        connected_at=NOW,
    )
    plan = plan_for(connection, last=None, now=NOW, readings={"xero": a_reading()})
    live = LiveConnection(id=uuid.uuid4(), connection=connection)

    @dataclass
    class Source:
        sent: list[str] = field(default_factory=list)

        def get(
            self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
        ) -> SourceAnswer:
            del address, max_bytes
            self.sent.append(headers.get("Authorization", ""))
            listed = b'{"Contacts": []}' if "/Contacts" in url else b'{"Invoices": []}'
            return SourceAnswer(status=200, headers={}, body=listed)

    refused = SourceAnswer(status=400, headers={}, body=b'{"error": "invalid_grant"}')
    for answer, health in ((refused, HealthState.DOWN), (issued(), HealthState.OK)):
        source = Source()
        done = probe_one(
            live,
            plan,
            previous=None,
            recent=(),
            keys=held(),
            caller=source,
            resolver=Resolver(),
            clock=lambda: NOW,
            poster=Endpoint(answer),
        )
        assert done.health is health
        if health is HealthState.DOWN:
            assert done.detail == CONSENT_WITHDRAWN and not source.sent
        else:
            assert source.sent == ["Bearer ACCESS-1"]


# ------------------------------------------------------------------ the declaration
def test_a_declaration_consented_by_oauth_renews_by_that_consent_or_is_refused() -> None:
    """A consent declared with a reading that presents another scheme, another consent, or a form
    that does not ask for the client id is refused where the declaration is built; the check's own
    declaration, which does all three, is accepted. Delete this and a source's refresh token and
    secret could be posted to whichever endpoint its reading happens to name."""
    from dataclasses import replace

    from brain.connectors import xero

    declared, reading = consented_xero()
    assert declared.oauth is not None and declared.console is not None
    other = OAuthConsent(
        authorize_url="https://elsewhere.example/authorize",
        token_url="https://elsewhere.example/token",
        scopes=("read",),
        client_id_setting=CLIENT_ID_SETTING,
    )
    for broken in (
        {"reading": xero.CONNECTOR.reading},
        {"oauth": other},
        {"console": replace(declared.console, settings=declared.console.settings[:1])},
    ):
        with pytest.raises(DeclarationError):
            replace(declared, **broken)
    assert isinstance(replace(declared), ConnectorDeclaration)
    with pytest.raises(DeclarationError):
        replace(declared, oauth=None)
    assert reading.consent() == declared.oauth


def test_a_patch_is_sent_as_a_merge_patch_to_the_slot_s_data_and_never_creates_one() -> None:
    """kv version 2 merges a PATCH sent as `application/merge-patch+json` into a slot that holds a
    version, which is what lets the rotate policy grant `patch` and no `read`; any other media
    type is refused by the vault. The data path is the slot's own, and the template key's prefix is
    refused before anything is sent. Delete this and the rotation is sent in a shape the vault
    refuses on every install, or as a POST that needs `update`."""
    from brain.ops.openbao import MERGE_PATCH, OpenBaoVault

    class Sent(OpenBaoVault):
        def __init__(self) -> None:
            super().__init__("http://vault:8200", "a-token")
            self.sent: list[tuple[str, str, Any, str]] = []

        def _request(
            self,
            method: str,
            path: str,
            body: dict[str, Any] | None = None,
            *,
            content_type: str = "application/json",
        ) -> dict[str, Any]:
            self.sent.append((method, path, body, content_type))
            return {}

    vault = Sent()
    vault.patch_static_kv(refresh_reference("xero").path, {KEY_FIELD: "REFRESH-2"})
    assert vault.sent == [
        (
            "PATCH",
            "connector_keys/data/oauth_refresh/xero",
            {"data": {KEY_FIELD: "REFRESH-2"}},
            MERGE_PATCH,
        )
    ]
    for refused in ("template_signing/key", "connectors/creds/xero"):
        with pytest.raises(SecretsUnavailableError):
            vault.patch_static_kv(refused, {KEY_FIELD: "x"})
    assert len(vault.sent) == 1
