"""Managing webhooks from the console: what a registration must be, and where its secret is kept.

`brain.ops.outbox` decides what a subscriber is, what it may be told and who may manage one, and
`brain.console.subscribers` decides what a reader is shown. Neither could be acted on from a
browser: nothing judged a registration before it was written, nothing kept a subscriber's signing
secret anywhere, and nothing recorded who switched one off. This module is the first two, and
`brain.tables.webhook_change` is the third. It holds no client: the vault arrives as
`brain.ops.credentials.CredentialVault`, which `brain.ops.openbao.OpenBaoVault` is.

**Every problem with a registration is found before anything is written, and all of them at
once.** A form refused for its first mistake and then for its second is a form filled in twice.
Each problem names its field and a stable code, and says what to do, for the reason
`brain.credential_routes` gives about its own: the code is what a translated console keys on.

**The address is judged by the one rule, and not looked up.** `brain.tools.fetch.assert_fetchable`
is the rule and `brain.ops.outbox.A_SUBSCRIBER_URL_IS_CHECKED_AT_EVERY_DELIVERY` is why a lookup
at registration is wrong: a name that resolves outside today resolves inside the day somebody
changes the record, and a check here would read as "already checked". So the rule runs with a
resolver that stops it at the moment it would look the name up, which is after every rule about
the address's shape has passed and before any network is asked. An address written as a literal
is judged whole, because a literal needs no lookup and `169.254.169.254` is refused today exactly
as it would be at delivery. See `THE_SHAPE_IS_JUDGED_HERE_AND_THE_ADDRESS_AT_EVERY_DELIVERY`.

**The secret is written once and never read back, into a path the subscriber's id names.**
`webhooks/<subscriber_id>`, under the engine `brain.ops.openbao.SIGNING_PREFIX` admits, which is
why the id is one path segment of lower-case letters, digits and underscores. What a
person is told is whether a secret is held and when it was written, read from the version's
metadata, which carries no field of the secret. The paste is judged by
`brain.ops.credentials.problems_with`, which is the one judgement of "this is a key and not a bad
copy", and additionally for length, because a signing secret a person could type is a secret
somebody could guess. See `A_SIGNING_KEY_A_PERSON_COULD_TYPE_IS_ONE_SOMEBODY_COULD_GUESS`.

**What this cannot make true, said where a person reads it.** Delivery happens in the general
worker, so an install whose profile runs none sends nothing; no channel has a route that receives
a webhook, and two channels have no check for one written at all; and an automation calls in with
a credential of its own that nothing lists. Each is a sentence served beside the screen rather
than a control that renders and reaches nothing. See `how_delivery_works`,
`brain.ops.inbound_webhooks` and `AN_AUTOMATION_CALLS_IN_WITH_ITS_OWN_CREDENTIAL`.

**Until 2026-09-17 the delivery sentence said nothing on any install sends a webhook**, which was
true, and was served as a constant beside a table that had no way to change. The worker's schedule
starts the dispatch now, so the sentence says how delivery works and the screen says beside it what
the dispatch last did, from the schedule's own record.

Rejected: generating the secret here and showing it once. It is what several products do, and it
is a response that carries a credential, which `brain.credential_routes` refuses for every route
this console calls. The person pastes a secret they generated and gave the receiver, and the time
it was written is what tells two saves apart.

Task ids: M27.8.12
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

import structlog

from brain.ops.credentials import CredentialVault, VaultState, problems_with
from brain.ops.limits import MAX_BACKOFF_SECONDS
from brain.ops.openbao import (
    SIGNING_PREFIX,
    OpenBaoVault,
    VaultUnreachableError,
)
from brain.ops.outbox import MAX_DELIVERY_ATTEMPTS, EventKind, retry_window_seconds
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole
from brain.tables.outbox import ENDPOINT_CHARS
from brain.tools.fetch import UnsafeAddressError, assert_fetchable

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why the address's shape is judged at registration and its destination is not.
THE_SHAPE_IS_JUDGED_HERE_AND_THE_ADDRESS_AT_EVERY_DELIVERY: Final = (
    "An address that is not https, carries a user name or password, or names no host is wrong "
    "today and will be wrong at every delivery, so it is refused before anything is written. "
    "Where a name resolves is not judged here: it can change between now and any delivery, and a "
    "check at registration reads as already checked, which is the hole the per-delivery check "
    "closes. An address written as a literal needs no lookup and is judged whole."
)

#: Why a signing secret has a minimum length that a provider key does not.
A_SIGNING_KEY_A_PERSON_COULD_TYPE_IS_ONE_SOMEBODY_COULD_GUESS: Final = (
    "A provider key is issued by the provider at whatever length it chose. A signing secret is "
    "chosen by whoever registers the subscriber, and anybody who guesses it can sign a request "
    "the receiver accepts as ours. Thirty-two characters is the floor the Telegram channel holds "
    "its own shared secret to, for the same reason."
)

#: What a person is told about inbound webhooks, above the list of channels.
NO_CHANNEL_RECEIVES_A_WEBHOOK: Final = (
    "No channel on this install receives a webhook: none has an address a platform could send to, "
    "and no secret is held for any of them. Below is each channel a platform would call in on, "
    "and whether the check that a request really came from that platform is written yet."
)


def how_delivery_works() -> str:
    """What a person is told about delivery, beside the list, with the figures the code uses.

    A function rather than a constant, so the attempt count and the longest wait are read from
    `brain.ops.outbox` and `brain.ops.limits` instead of being typed again into a sentence that
    would stay true of an old figure.
    """
    minutes = round(retry_window_seconds() / 60)
    longest = round(MAX_BACKOFF_SECONDS / 60)
    return (
        "The worker sends what is due every minute, signed with each subscriber's secret, with the "
        "identifiers of what happened and never its content. A delivery that is refused for a "
        "moment or not answered is tried again after a growing wait of up to "
        f"{longest} minutes, {MAX_DELIVERY_ATTEMPTS} attempts over at most {minutes} minutes, "
        "and is then set aside with its reason. A subscriber that refuses outright, or a redirect, "
        "is set aside at once. Switching a subscriber off stops everything waiting for it."
    )


#: What a person is told about the one inbound door that exists.
AN_AUTOMATION_CALLS_IN_WITH_ITS_OWN_CREDENTIAL: Final = (
    "An automation calls this system at the tool-call address with a credential issued to that "
    "automation alone, and acts as the person who owns it. Nothing on this install lists those "
    "registrations or issues one from the console yet."
)

#: The confirmation's consequence for each write, in the words a person agrees to.
REGISTERING_A_SUBSCRIBER: Final = (
    "The subscriber is told, at this address, whenever one of the chosen kinds of thing happens, "
    "with the identifiers of what it happened to and never its content. The secret is kept in the "
    "vault and signs every request; it is never shown again."
)
REPLACING_A_SIGNING_KEY: Final = (
    "The new secret signs every request from now on, and a receiver still checking against the "
    "old one refuses them. Give the receiver the new secret first. The old one cannot be shown or "
    "restored from here."
)
SWITCHING_A_SUBSCRIBER_OFF: Final = (
    "The subscriber is told nothing more, and deliveries already waiting for it are not sent. "
    "This cannot be undone: to start again, register it under a new id."
)

# ---------------------------------------------------------------------- the figures

#: One vault path segment of lower-case words, which is also an identifier the audit ledger's
#: grammar admits. No hyphen and a letter first, so `webhooks/<id>` is the same shape as every other
#: kv slot this system writes (`providers/anthropic`), which a record of a credential write keys on.
SUBSCRIBER_ID_PATTERN: Final = r"^[a-z][a-z0-9_]{0,62}$"
_SUBSCRIBER_ID_RE: Final = re.compile(SUBSCRIBER_ID_PATTERN)

#: The shortest signing secret accepted. See the reason above.
MINIMUM_SIGNING_SECRET_CHARS: Final = 32

#: The one field a secret is kept under in its kv version.
SIGNING_FIELD: Final = "signing_secret"

#: The role that will borrow a subscriber's secret to sign a delivery.
DELIVERING_ROLE: Final = VaultRole.WORKER


class Field(enum.StrEnum):
    """The fields a registration or a rotation carries, as a problem names them."""

    SUBSCRIBER_ID = "subscriber_id"
    ENDPOINT = "endpoint"
    KINDS = "kinds"
    SECRET = "secret"  # noqa: S105


@dataclass(frozen=True)
class FieldProblem:
    """One thing wrong with what was sent: which field, a stable code, and what to do."""

    field: Field
    code: str
    message: str


# ------------------------------------------------------------------- the decisions


def signing_secret_path(subscriber_id: str) -> str:
    """Where a subscriber's signing secret is kept."""
    return f"{SIGNING_PREFIX}{subscriber_id}"


def signing_secret_ref(subscriber_id: str) -> SecretRef:
    """The reference a subscriber row carries: its path, and the role that will borrow it."""
    return SecretRef(path=signing_secret_path(subscriber_id), role=DELIVERING_ROLE)


def subscriber_id_problems(subscriber_id: str) -> tuple[FieldProblem, ...]:
    """What is wrong with an id, judged exactly as given: an id is not a paste."""
    if not subscriber_id:
        return (
            FieldProblem(
                Field.SUBSCRIBER_ID,
                "blank",
                "Give the subscriber an id, such as the name of the system it tells.",
            ),
        )
    if not _SUBSCRIBER_ID_RE.fullmatch(subscriber_id):
        return (
            FieldProblem(
                Field.SUBSCRIBER_ID,
                "not_an_id",
                "Use up to 63 lower-case letters, digits and underscores, starting with a letter.",
            ),
        )
    return ()


class _LookupDeferredError(Exception):
    """Raised by `_NoLookup` at the one point the address rule would ask the network."""


class _NoLookup:
    """A `brain.tools.fetch.Resolver` that is never answered. See the module docstring."""

    def resolve(self, host: str) -> Sequence[str]:
        raise _LookupDeferredError(host)


def endpoint_problems(endpoint: str) -> tuple[FieldProblem, ...]:
    """What is wrong with an address, by the fetch rule's shape and without a lookup."""
    if not endpoint.strip():
        return (
            FieldProblem(
                Field.ENDPOINT, "blank", "Give the https address the subscriber receives at."
            ),
        )
    if len(endpoint) > ENDPOINT_CHARS or endpoint != endpoint.strip():
        return (
            FieldProblem(
                Field.ENDPOINT,
                "not_an_address",
                f"Give one https address of at most {ENDPOINT_CHARS} characters, with no spaces "
                "around it.",
            ),
        )
    try:
        assert_fetchable(endpoint, _NoLookup())
    except _LookupDeferredError:
        return ()
    except UnsafeAddressError:
        return (
            FieldProblem(
                Field.ENDPOINT,
                "refused_address",
                "Use an https address with a host name and no user name or password in it, "
                "written with brackets if it is an IPv6 address, and not an address only this "
                "network can reach.",
            ),
        )
    return ()


def kinds_problems(kinds: Sequence[str]) -> tuple[FieldProblem, ...]:
    """What is wrong with the kinds asked for: none, one this system does not have, or a repeat."""
    if not kinds:
        return (
            FieldProblem(
                Field.KINDS,
                "none",
                "Choose at least one kind of thing to be told about. A subscriber told about "
                "nothing should not be registered.",
            ),
        )
    known = {one.value for one in EventKind}
    if any(one not in known for one in kinds):
        return (
            FieldProblem(Field.KINDS, "unknown", "Choose only from the kinds this screen lists."),
        )
    if len(set(kinds)) != len(kinds):
        return (FieldProblem(Field.KINDS, "repeated", "Choose each kind once."),)
    return ()


#: What a person is told for each code `problems_with` gives, in a signing secret's words rather
#: than a provider key's. A code with no sentence here is told in `problems_with`'s own words.
SECRET_SENTENCES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "blank": "Paste the signing secret you gave the receiver. It is never shown again.",
        "too_long": (
            "That is longer than a signing secret should be. Check that only the secret was "
            "copied, and paste it again."
        ),
        "not_one_piece": (
            "The secret has a space, a line break or a character a request header cannot carry "
            "inside it. Generate one without them."
        ),
    }
)


def secret_problems(secret: str) -> tuple[FieldProblem, ...]:
    """What is wrong with a signing secret: `problems_with`'s judgement, then its length."""
    found = [
        FieldProblem(Field.SECRET, one.code, SECRET_SENTENCES.get(one.code, one.message))
        for one in problems_with(secret)
    ]
    if any(one.code == "blank" for one in found):
        return tuple(found)
    if len(secret.strip()) < MINIMUM_SIGNING_SECRET_CHARS:
        found.append(
            FieldProblem(
                Field.SECRET,
                "too_short",
                f"Use a secret of at least {MINIMUM_SIGNING_SECRET_CHARS} characters, generated "
                "rather than typed.",
            )
        )
    return tuple(found)


def registration_problems(
    *, subscriber_id: str, endpoint: str, kinds: Sequence[str], secret: str
) -> tuple[FieldProblem, ...]:
    """Every problem with a registration, in field order. Empty means it may be written."""
    return (
        *subscriber_id_problems(subscriber_id),
        *endpoint_problems(endpoint),
        *kinds_problems(kinds),
        *secret_problems(secret),
    )


def event_kinds(kinds: Iterable[str]) -> tuple[EventKind, ...]:
    """The kinds as `EventKind`, for a registration `registration_problems` has passed."""
    return tuple(EventKind(one) for one in kinds)


# ------------------------------------------------------------------ the vault half

#: What a person is told for each vault state when a signing secret is asked about or written.
TOLD: Final[Mapping[VaultState, str]] = MappingProxyType(
    {
        VaultState.ABSENT: (
            "This install runs no secrets vault, so no signing secret can be kept and no "
            "subscriber can be registered or have its secret replaced. Set BRAIN_VAULT_ADDRESS and "
            "BRAIN_VAULT_TOKEN in the server's environment file and restart the system. Nothing "
            "was written."
        ),
        VaultState.UNREACHABLE: (
            "The secrets vault did not answer, so nothing was written. Check that it is running "
            "and unsealed and that the application can reach it, then try again."
        ),
        VaultState.REFUSED: (
            "The secrets vault answered and refused, so nothing was written. Its token may have "
            "expired, or the webhooks engine or the application policy may not be loaded: "
            "ops/openbao/credential-slots.md has the steps. Then try again."
        ),
        VaultState.READY: "The secrets vault answered.",
    }
)


class SigningSecretsUnavailableError(Exception):
    """The vault could not be asked, or refused. `state` says which; the message is `TOLD`'s."""

    def __init__(self, state: VaultState) -> None:
        super().__init__(TOLD[state])
        self.state = state


@dataclass(frozen=True)
class SecretHeld:
    """Whether a subscriber's signing secret is held, and when its current version was written."""

    held: bool
    written_at: datetime | None


class SigningSecrets:
    """This process's way into the vault for signing secrets, or its lack of one.

    Built once by `signing_secrets_at_start` and held on `app.state.signing_secrets`. `vault` is
    None on an install with no vault, and every method then refuses with `VaultState.ABSENT`.
    """

    def __init__(self, vault: CredentialVault | None) -> None:
        self._vault = vault

    def __repr__(self) -> str:
        return f"SigningSecrets(configured={self.configured})"

    __str__ = __repr__

    @property
    def configured(self) -> bool:
        """Whether this install names a vault at all. Not whether it answers."""
        return self._vault is not None

    def _vault_or_refuse(self) -> CredentialVault:
        if self._vault is None:
            raise SigningSecretsUnavailableError(VaultState.ABSENT)
        return self._vault

    def held(self, subscriber_id: str) -> SecretHeld:
        """Whether a secret is held for this subscriber. Reads metadata, which holds no secret."""
        vault = self._vault_or_refuse()
        try:
            version = vault.static_kv_version(signing_secret_path(subscriber_id))
        except VaultUnreachableError as silent:
            raise SigningSecretsUnavailableError(VaultState.UNREACHABLE) from silent
        except SecretsUnavailableError as refused:
            raise SigningSecretsUnavailableError(VaultState.REFUSED) from refused
        if version is None:
            return SecretHeld(held=False, written_at=None)
        return SecretHeld(held=True, written_at=version.written_at)

    def keep(self, subscriber_id: str, secret: str, *, actor: str) -> datetime | None:
        """Write a subscriber's signing secret, and return the time the vault stamped on it.

        The caller has judged the secret with `secret_problems` already; this refuses a vault
        that is absent, silent or refusing, and logs the subscriber and the actor and never the
        secret.
        """
        vault = self._vault
        if vault is None:
            log.info("signing secret not kept", subscriber=subscriber_id, actor=actor)
            raise SigningSecretsUnavailableError(VaultState.ABSENT)
        path = signing_secret_path(subscriber_id)
        try:
            written = vault.write_static_kv(path, {SIGNING_FIELD: secret.strip()})
        except VaultUnreachableError as silent:
            log.info("signing secret not kept", subscriber=subscriber_id, actor=actor)
            raise SigningSecretsUnavailableError(VaultState.UNREACHABLE) from silent
        except SecretsUnavailableError as refused:
            log.info("signing secret not kept", subscriber=subscriber_id, actor=actor)
            raise SigningSecretsUnavailableError(VaultState.REFUSED) from refused
        log.info("signing secret kept", subscriber=subscriber_id, actor=actor)
        return written


def signing_secrets_at_start(address: str, token: str) -> SigningSecrets:
    """This process's `SigningSecrets`, from the same two settings the credential store reads.

    Both must be set, for `brain.ops.credentials.credentials_at_start`'s reason. Never raises and
    asks the vault nothing: a signing secret is written when somebody registers a subscriber, and
    nothing is loaded at start.
    """
    if not address or not token:
        return SigningSecrets(None)
    try:
        return SigningSecrets(OpenBaoVault(address, token, role=VaultRole.APPLICATION))
    except ValueError:
        log.warning("secrets vault address is not a URL, so no signing secret can be kept")
        return SigningSecrets(None)
