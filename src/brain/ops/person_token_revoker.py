"""Revoking a person's own refresh token at the vendor and then removing it from the vault.

`brain.member.connections.disconnect` is an ordering and a refusal: revoke first, and leave the
connection in place when the revocation fails. It takes a `TokenRevoker` and nothing implemented
one, so no install could disconnect an account and the page had no control. This is the
implementation, over the three things a revocation touches: the vault that holds the token, the
vendor that issued it, and the slot it is kept in.

**The order inside the revoker is the same argument as the order outside it.** The token is read
(through the same `connector-person` lease a question's read uses, never with the application's own
token), the vendor is asked to revoke it, and only when the vendor has said so is the slot removed.
A vault that refuses the removal after the vendor has revoked returns False, which leaves the
connection listed and the control working; the retry asks the vendor again, and a vendor that
answers "that token is no longer valid" is read as already revoked, because otherwise a
half-finished disconnect could never finish. See `A_VENDORS_OWN_NOT_VALID_IS_THE_REVOCATION_DONE`.

**A source whose vendor publishes no revocation endpoint is removed from here and nothing more.**
`OAuthConsent.revoke_url` is empty then, there is nothing to ask, and the slot is removed. That is
honest about less than a revocation: the route says so in words instead of claiming the vendor
withdrew access, because claiming it would be the page promising a protection nobody provided.

**The handle must name the person's own slot.** `token_ref` is the slot path the connection was
built with, and it is compared with the slot computed from the connector and the principal this
revoker was made for. A handle that names anything else returns False without reading or removing
anything, so a connection built wrongly cannot become a way to remove somebody else's token.

Rejected: removing the slot first and revoking afterwards. If the revocation then fails there is no
token left to revoke with, the vendor still honours it, and nothing can retry. Also rejected: a
revoker that asks the worker to do it later. The leaf says immediate, and the application's policy
now holds the one line that removes a person's slot (`ops/openbao/policies/application.hcl`).

Task ids: M40.5.1.3
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Final

import structlog

from brain.connectors.contract import ConnectorContractError
from brain.connectors.oauth import OAuthConsent, revocation
from brain.ops.connectable import person_refresh_reference
from brain.ops.connector_sync_run import ConnectorKeys, SourceAnswer, SourcePoster
from brain.ops.erasure_store import RemovesSlots
from brain.ops.secrets import SecretsUnavailableError
from brain.tools.fetch import Resolver, UnsafeAddressError, assert_fetchable

log = structlog.get_logger()

#: The most a vendor's answer to a revocation is read to. An answer is a status and a few words.
MAX_REVOCATION_ANSWER_BYTES: Final = 4096

#: The error words a vendor uses for a token it no longer recognises.
_NO_LONGER_VALID: Final = frozenset({"invalid_token", "invalid_grant"})

#: Why a vendor saying the token is not valid is a success.
A_VENDORS_OWN_NOT_VALID_IS_THE_REVOCATION_DONE: Final = (
    "A disconnect that revoked at the vendor and then failed to remove the slot is retried, and "
    "the vendor answers the second revocation with an error naming the token as not valid. "
    "Reading that as a failure would leave the person unable to ever finish disconnecting, so a "
    "vendor's own 'not valid' is the token being gone, which is what was asked."
)


def _already_gone(answer: SourceAnswer) -> bool:
    """Whether a refused revocation said the token was already not valid, in the vendor's words."""
    if answer.status != 400:
        return False
    try:
        parsed = json.loads(answer.body.decode("utf-8", errors="replace"))
    except ValueError:
        return False
    return isinstance(parsed, dict) and parsed.get("error") in _NO_LONGER_VALID


class VaultTokenRevoker:
    """A `brain.member.connections.TokenRevoker` over the vault, the vendor and one person's slot.

    Made for one person and one source, and answers for no other: the reference it reads and removes
    is computed from them in `__init__`, so there is no argument through which a different slot
    could arrive.
    """

    def __init__(
        self,
        *,
        connector: str,
        principal_id: str,
        consent: OAuthConsent,
        keys: ConnectorKeys,
        remover: RemovesSlots,
        poster: SourcePoster | None,
        resolver: Resolver,
    ) -> None:
        self._reference = person_refresh_reference(connector, principal_id)
        self._connector = connector
        self._consent = consent
        self._keys = keys
        self._remover = remover
        self._poster = poster
        self._resolver = resolver

    def revoke(self, token_ref: str, *, at: datetime) -> bool:
        """Revoke at the vendor, then remove the slot. False leaves everything in place."""
        if token_ref != self._reference.path:
            log.warning(
                "a revocation named a slot that is not this person's", source=self._connector
            )
            return False
        if not self._vendor_revoked(at):
            return False
        try:
            self._remover.remove_static_kv(self._reference.path)
        except SecretsUnavailableError:
            log.warning("the vault would not remove a revoked token", source=self._connector)
            return False
        log.info("own account disconnected", source=self._connector)
        return True

    def _vendor_revoked(self, at: datetime) -> bool:
        """Whether the vendor has the token as revoked, or has no endpoint to ask."""
        if not self._consent.revoke_url:
            return True
        lease = self._keys.lease(self._reference, now=at)
        try:
            token = lease.key()
        except SecretsUnavailableError:
            return False
        finally:
            lease.close(at)
        poster = self._poster
        if poster is None:
            return False
        try:
            asked = revocation(self._consent, refresh_token=token)
            if asked is None:
                return True
            checked = assert_fetchable(asked.url, self._resolver)
        except (ConnectorContractError, UnsafeAddressError):
            return False
        answer = poster.post(
            checked.url,
            address=checked.address,
            headers=dict(asked.headers),
            body=asked.body,
            max_bytes=MAX_REVOCATION_ANSWER_BYTES,
        )
        if answer.timed_out or answer.connection_failed or answer.status is None:
            return False
        return 200 <= answer.status < 300 or _already_gone(answer)
