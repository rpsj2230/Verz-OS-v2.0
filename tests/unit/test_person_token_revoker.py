"""Revoking a person's own refresh token, and removing it only once the vendor has been asked.

The vault, the vendor and the address resolver are recording stand-ins, so what is proved is the
order and the refusals: the vendor is asked with the token alone, the slot is removed after and not
before, a failure at either step leaves the slot in place, and a handle naming anybody else's slot
reads and removes nothing. That a real vendor stops honouring the token, and that a real vault
holds the policy line that lets the application remove the slot, cannot be shown here.

Task ids: M40.5.1.3
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from urllib.parse import parse_qs

import pytest

from brain.connectors.google_workspace import CONSENT as GOOGLE_CONSENT
from brain.connectors.google_workspace import REVOKE_URL
from brain.connectors.oauth import OAuthConsent, revocation
from brain.ops.acceptance_checks_oauth import consented_personally
from brain.ops.connector_sync_run import SourceAnswer
from brain.ops.credentials import connector_person_oauth_slot
from brain.ops.person_token_revoker import VaultTokenRevoker
from brain.ops.secrets import SecretsUnavailableError
from tests.unit.test_oauth_renewal import Keys, Resolver

#: A date far from any wall clock, because nothing here is about the present.
AT = datetime(2999, 1, 1, tzinfo=UTC)

REVOKE_AT = "https://identity.oauth-vendor.example/connect/revocation"
TOKEN = "REFRESH-OF-ADA-31c9"

SOURCE = "xero"
ADA, BEA = "u_ada", "u_bea"


@dataclass
class Vendor:
    """A revocation endpoint answering as told, noting each form it was sent."""

    answer: SourceAnswer = field(default_factory=lambda: SourceAnswer(status=200, headers={}))
    forms: list[dict[str, str]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)

    def post(
        self, url: str, *, address: str, headers: object, body: bytes, max_bytes: int
    ) -> SourceAnswer:
        del address, headers, max_bytes
        self.order.append("vendor")
        self.urls.append(url)
        self.forms.append({k: v[0] for k, v in parse_qs(body.decode("ascii")).items()})
        return self.answer


@dataclass
class Shelf:
    """The vault's removal of a slot, noting the order against the vendor's."""

    vendor: Vendor
    removed: list[str] = field(default_factory=list)
    refuse: bool = False

    def remove_static_kv(self, path: str) -> None:
        if self.refuse:
            raise SecretsUnavailableError("the vault would not remove it")
        self.vendor.order.append("remove")
        self.removed.append(path)


def revoker(
    *,
    vendor: Vendor | None = None,
    shelf: Shelf | None = None,
    consent: OAuthConsent | None = None,
    held: bool = True,
    principal: str = ADA,
    resolver: object | None = None,
    poster: object | None = ...,
) -> tuple[VaultTokenRevoker, Vendor, Shelf, Keys]:
    vendor = vendor or Vendor()
    shelf = shelf or Shelf(vendor)
    base = consented_personally().oauth
    assert base is not None
    declared = consent or replace(base, revoke_url=REVOKE_AT)
    keys = Keys(slots={connector_person_oauth_slot(SOURCE, ADA).path: TOKEN} if held else {})
    return (
        VaultTokenRevoker(
            connector=SOURCE,
            principal_id=principal,
            consent=declared,
            keys=keys,
            remover=shelf,
            poster=vendor if poster is ... else poster,  # type: ignore[arg-type]
            resolver=resolver or Resolver(),  # type: ignore[arg-type]
        ),
        vendor,
        shelf,
        keys,
    )


def ada_slot() -> str:
    return connector_person_oauth_slot(SOURCE, ADA).path


def test_the_vendor_is_asked_with_the_token_alone_and_the_slot_is_removed_after() -> None:
    """**The order is the argument.** The vendor's revocation endpoint is posted the token and its
    kind and nothing else, and only then is the slot removed. Delete this and the slot can be
    removed first, leaving a token the vendor still honours and nothing left to revoke it with."""
    one, vendor, shelf, keys = revoker()

    assert one.revoke(ada_slot(), at=AT) is True

    assert vendor.urls == [REVOKE_AT]
    assert vendor.forms == [{"token": TOKEN, "token_type_hint": "refresh_token"}]
    assert vendor.order == ["vendor", "remove"]
    assert shelf.removed == [ada_slot()]
    assert [lease.closed for lease in keys.leases] == [1]


def test_a_vendor_that_refuses_leaves_the_slot_in_place() -> None:
    """The sibling: a 5xx from the vendor is False and nothing is removed, so the connection stays
    listed and can be tried again. Delete this and a failed revocation removes the one handle there
    was to retry with."""
    one, _, shelf, _ = revoker(vendor=Vendor(answer=SourceAnswer(status=503, headers={})))

    assert one.revoke(ada_slot(), at=AT) is False

    assert shelf.removed == []


@pytest.mark.parametrize(
    "answer",
    [
        SourceAnswer(timed_out=True),
        SourceAnswer(connection_failed=True),
        SourceAnswer(status=None),
    ],
)
def test_a_vendor_that_cannot_be_reached_leaves_the_slot_in_place(answer: SourceAnswer) -> None:
    """A timeout, a failed connection and no status at all are all a vendor that did not say the
    token is revoked. Delete this and silence reads as success."""
    one, _, shelf, _ = revoker(vendor=Vendor(answer=answer))

    assert one.revoke(ada_slot(), at=AT) is False
    assert shelf.removed == []


def test_a_vendor_saying_the_token_is_not_valid_is_the_revocation_already_done() -> None:
    """A retry after the vendor revoked and the vault failed gets 'invalid token' back; that is read
    as revoked so the slot can finally go. Delete this and a half-finished disconnect can never
    finish."""
    refused = SourceAnswer(
        status=400, headers={}, body=json.dumps({"error": "invalid_token"}).encode()
    )
    one, _, shelf, _ = revoker(vendor=Vendor(answer=refused))

    assert one.revoke(ada_slot(), at=AT) is True
    assert shelf.removed == [ada_slot()]


def test_a_process_with_nothing_to_post_with_leaves_the_slot_in_place() -> None:
    """With no poster the vendor cannot be asked, and that is False and nothing removed. Delete this
    and an install that cannot reach vendors reports every disconnect as done."""
    one, _, shelf, _ = revoker(poster=None)

    assert one.revoke(ada_slot(), at=AT) is False
    assert shelf.removed == []


def test_an_answer_flagged_as_timed_out_is_not_a_revocation_whatever_status_it_carries() -> None:
    """A poster says a call timed out by the flag; a status beside it is not trusted. Delete this
    and a half-read answer that happens to carry a 200 lets the slot be removed."""
    answer = SourceAnswer(status=200, headers={}, timed_out=True)
    one, _, shelf, _ = revoker(vendor=Vendor(answer=answer))

    assert one.revoke(ada_slot(), at=AT) is False
    assert shelf.removed == []


def test_a_server_error_that_quotes_invalid_token_is_still_a_failure() -> None:
    """Only a 400 can say the token is not valid: a 503 whose body happens to carry the same word
    is the vendor failing and not the token being gone. Delete this and an outage that echoes an
    error name lets the slot be removed with the token still live."""
    body = json.dumps({"error": "invalid_token"}).encode()
    one, _, shelf, _ = revoker(
        vendor=Vendor(answer=SourceAnswer(status=503, headers={}, body=body))
    )

    assert one.revoke(ada_slot(), at=AT) is False
    assert shelf.removed == []


def test_any_other_refusal_from_the_vendor_is_not_taken_for_a_revocation() -> None:
    """The sibling: a 400 that is not about the token, and a 400 that is not JSON, are failures.
    Delete this and every 400 is success, which is the same as never asking."""
    for body in (json.dumps({"error": "invalid_request"}).encode(), b"not json at all"):
        one, _, shelf, _ = revoker(
            vendor=Vendor(answer=SourceAnswer(status=400, headers={}, body=body))
        )
        assert one.revoke(ada_slot(), at=AT) is False
        assert shelf.removed == []


def test_a_vault_that_will_not_remove_the_slot_reports_failure_after_the_vendor_has_revoked() -> (
    None
):
    """The vendor is asked, the vault refuses the removal, and the answer is False so the person
    can try again. Delete this and the page reports a disconnection that left a slot behind."""
    vendor = Vendor()
    one, _, _, _ = revoker(vendor=vendor, shelf=Shelf(vendor, refuse=True))

    assert one.revoke(ada_slot(), at=AT) is False
    assert vendor.order == ["vendor"]


def test_a_token_that_cannot_be_read_asks_nobody_and_removes_nothing() -> None:
    """If the person's slot cannot be leased there is no token to revoke with: False, the vendor
    never posted, nothing removed. Delete this and a missing token is treated as a revoked one."""
    one, vendor, shelf, _ = revoker(held=False)

    assert one.revoke(ada_slot(), at=AT) is False
    assert vendor.urls == [] and shelf.removed == []


def test_a_handle_naming_somebody_elses_slot_reads_and_removes_nothing() -> None:
    """The handle must be this person's own slot. Bea's is refused before the vault is asked.
    Delete this and a connection built wrongly becomes a way to remove a colleague's token."""
    one, vendor, shelf, keys = revoker()

    assert one.revoke(connector_person_oauth_slot(SOURCE, BEA).path, at=AT) is False

    assert keys.leases == [] and vendor.urls == [] and shelf.removed == []


def test_a_revoker_made_for_one_person_cannot_be_pointed_at_another() -> None:
    """The reference is computed from the person it was made for, so a revoker made for Bea reads
    and removes Bea's slot even when handed Ada's handle. Delete this and the person is an argument
    rather than a construction."""
    one, _, shelf, keys = revoker(principal=BEA)

    assert one.revoke(ada_slot(), at=AT) is False
    assert keys.leases == [] and shelf.removed == []


def test_a_source_that_publishes_no_revocation_endpoint_is_removed_from_here_and_nothing_more() -> (
    None
):
    """With no revoke address there is nothing to ask: the vendor is never posted and the slot is
    removed. Delete this and such a source can never be disconnected, or a post goes to nowhere."""
    declared = consented_personally().oauth
    assert declared is not None and declared.revoke_url == ""
    one, vendor, shelf, keys = revoker(consent=declared)

    assert one.revoke(ada_slot(), at=AT) is True

    assert vendor.urls == [] and keys.leases == []
    assert shelf.removed == [ada_slot()]


def test_an_address_the_rule_refuses_is_never_posted() -> None:
    """A revocation address resolving somewhere private is refused before any connection, like any
    other address the product posts to. Delete this and the vendor's DNS decides where the token
    is sent."""

    class Private:
        def resolve(self, host: str) -> list[str]:
            del host
            return ["10.0.0.5"]

    vendor = Vendor()
    one, _, shelf, _ = revoker(vendor=vendor, resolver=Private())

    assert one.revoke(ada_slot(), at=AT) is False
    assert vendor.urls == [] and shelf.removed == []


# ------------------------------------------------------------------- the declaration side
def test_the_google_consent_declares_the_vendors_published_revocation_endpoint() -> None:
    """The one shipped source each person consents to names Google's own endpoint, so a real
    disconnect asks it. Delete this and the shipped source is removed from here without the vendor
    ever being asked, and the page says so."""
    assert GOOGLE_CONSENT.revoke_url == REVOKE_URL == "https://oauth2.googleapis.com/revoke"


def test_a_revocation_request_carries_the_token_and_its_kind_and_no_client_secret() -> None:
    """Built by `revocation`, an RFC 7009 form of two fields over the declared address. Delete this
    and a client secret rides along to the vendor on a request that does not need it."""
    asked = revocation(replace(GOOGLE_CONSENT, revoke_url=REVOKE_AT), refresh_token=TOKEN)

    assert asked is not None
    assert asked.url == REVOKE_AT
    assert parse_qs(asked.body.decode("ascii")) == {
        "token": [TOKEN],
        "token_type_hint": ["refresh_token"],
    }


def test_a_consent_with_no_revocation_endpoint_builds_no_request() -> None:
    """The sibling: nothing is built where nothing is declared. Delete this and a post to an empty
    address is attempted."""
    plain = consented_personally().oauth
    assert plain is not None
    assert revocation(plain, refresh_token=TOKEN) is None


def test_a_revocation_address_must_be_https() -> None:
    """A plain-http revocation address is refused at declaration. Delete this and a token is sent
    over a channel anybody on the path can read."""
    from brain.connectors.contract import ConnectorContractError

    with pytest.raises(ConnectorContractError):
        replace(GOOGLE_CONSENT, revoke_url="http://identity.oauth-vendor.example/revoke")
