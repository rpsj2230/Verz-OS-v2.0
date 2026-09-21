"""The worker's half of a webhook: reading the signing secret, opening the connection, draining.

`brain.ops.outbox` decides what a delivery is and `brain.ops.outbox_store` claims, sends through
`issue_once` and records. Both take a sender, a way to the signing secret, a resolver and a ledger
as parameters, and until 2026-09-17 nothing in this repository implemented any of the four, so
`outbox_dispatch` was a control with no caller and every event anybody subscribed to sat pending
for ever. This module is the four, and `run_dispatch_now` is what the worker's schedule starts.

**The worker reads the signing secret, and it is the only process that does.** The application
writes a subscriber's secret from the console and reads the slot's metadata to say it is held; it
never reads the value, because it never signs. The worker signs, so its own policy
(`ops/openbao/policies/worker.hcl`) grants read on `webhooks/data/+` and nothing else under that
engine, and `WorkerSigningKeys` refuses any path outside `webhooks/` and any reference whose role
is not the worker's before the vault is asked. See
`THE_PROCESS_THAT_SIGNS_READS_THE_KEY_AND_NO_OTHER_DOES`.

**The connection goes to the address the rule checked, not to the name.** `brain.tools.fetch.
Fetchable` says a transport should connect to the checked address, send the name in the Host
header and in SNI, and verify the certificate against the name, and that it cannot enforce any of
it. `HttpsSender` is that transport: `_PinnedHTTPSConnection` overrides the one method that would
look the name up again. A name that resolved outside at the check and inside a millisecond later
is connected to outside. See `THE_CONNECTION_GOES_TO_THE_ADDRESS_THAT_WAS_CHECKED`.

**A sender never raises for anything the network did.** A timeout is `timed_out`, a refused
connection or a certificate that does not match is `connection_failed`, and an answer is its
status. An exception out of the effect would leave the attempt's operation unknown and stop the
whole batch over one subscriber's server, which is `brain.ops.outbox_store`'s argument about a
vault outage turned the wrong way round.

**A worker with no vault sends nothing and says so on every run.** The run fails with a sentence
naming the two settings, the schedule records the failure, and the Webhooks screen shows it beside
the deliveries still pending. It is not a quiet success: a dispatcher that reported "nothing
delivered" on an install that cannot sign would read as an outbox with nothing in it.

Rejected: `httpx` for the request. It resolves the name itself at connect time, which is the
rebinding hole, and pinning an address under it means a custom transport reaching into its pool;
`http.client` is one overridden method and no dependency.

Rejected: following a redirect. See `brain.ops.outbox_store.A_REDIRECT_IS_NOT_A_DELIVERY`.

Task ids: M27.8.12, M17.5.1
"""

from __future__ import annotations

import asyncio
import http.client
import socket
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

import psycopg

from brain.db import libpq_conninfo
from brain.ops.object_store import StaticKvReader
from brain.ops.openbao import SIGNING_PREFIX, OpenBaoVault, VaultRefusedError
from brain.ops.operation_store import PostgresOperationLedger
from brain.ops.outbox import Attempt, DeliveryState, SignedRequest
from brain.ops.outbox_store import (
    Sender,
    SendResult,
    SigningKeys,
    SigningSecretAbsentError,
    claim_due,
    dispatch_due,
)
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole
from brain.ops.webhook_admin import DELIVERING_ROLE, SIGNING_FIELD
from brain.session import make_app_engine, make_session_factory
from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: Why the worker holds read on the signing secrets and the application does not.
THE_PROCESS_THAT_SIGNS_READS_THE_KEY_AND_NO_OTHER_DOES: Final = (
    "A signing secret is used for one thing, computing a signature, and only the worker computes "
    "one. So the worker's policy reads webhooks/data/+ and the application's does not: the "
    "application writes the secret when an administrator registers or rotates a subscriber and "
    "reads the slot's metadata to say it is held, and a process that answers questions has no "
    "reason to hold a value it never uses. The reader refuses anything outside webhooks/ and any "
    "reference not made for the worker, so a subscriber row edited to point at a provider key is "
    "refused here before the vault is asked."
)

#: Why the connection is made to an address rather than to a name.
THE_CONNECTION_GOES_TO_THE_ADDRESS_THAT_WAS_CHECKED: Final = (
    "The address rule resolves the subscriber's name and refuses it if any answer is inside the "
    "network. A client that connected by name would resolve it again, and a name can answer "
    "outside to the check and inside to the connection, which is DNS rebinding and is the "
    "ordinary way past exactly this rule. So the socket is opened to the address that passed, "
    "and the name is used only where it belongs: the Host header, SNI and the certificate check."
)

#: What a worker with no vault says on every run.
NO_VAULT_ON_THIS_WORKER: Final = (
    "This worker has no secrets vault, so no delivery can be signed and nothing was sent. Set "
    "BRAIN_VAULT_ADDRESS and BRAIN_VAULT_TOKEN in the worker's environment, with a token minted "
    "against the worker policy, and restart the worker. Deliveries wait as pending until then."
)

#: How long one request may take, connect to last byte. Ten seconds: a receiver is asked to
#: acknowledge and do its work later, and one that takes longer holds the claim's transaction and
#: every delivery behind it. A timeout is retried with backoff, so a slow receiver loses nothing.
DELIVERY_TIMEOUT_SECONDS: Final = 10.0

#: How many deliveries one run claims. The claim's transaction is held across every send, so the
#: worst run is this times the timeout, 200 seconds, which is inside
#: `brain.ops.schedule_runner.STALLED_AFTER` with room, and the rest wait for the next tick.
DISPATCH_BATCH: Final = 20

#: How much of an answer is read before the connection is closed. The status is the answer; a
#: body is read only so the connection closes cleanly, and never kept.
MAX_ANSWER_BYTES: Final = 4096

#: What a receiver sees as the client. Names the product and nothing about the install.
USER_AGENT: Final = "company-brain-webhooks/1"

#: The port an https address without one is sent to.
HTTPS_PORT: Final = 443


# ---------------------------------------------------------------- the signing secret
class WorkerSigningKeys:
    """`brain.ops.outbox_store.SigningKeys` over the worker's vault, or over no vault at all.

    See `THE_PROCESS_THAT_SIGNS_READS_THE_KEY_AND_NO_OTHER_DOES`. With no vault every read
    raises `SecretsUnavailableError` with `NO_VAULT_ON_THIS_WORKER`, which stops the batch.
    """

    def __init__(self, vault: StaticKvReader | None) -> None:
        self._vault = vault

    def __repr__(self) -> str:
        return f"WorkerSigningKeys(configured={self._vault is not None})"

    __str__ = __repr__

    def signing_secret(self, ref: SecretRef) -> str:
        if not ref.path.startswith(SIGNING_PREFIX):
            msg = (
                f"a signing secret is read from {SIGNING_PREFIX} and nowhere else, and this "
                f"reference names the {ref.path.split('/', 1)[0]} engine. "
                f"{THE_PROCESS_THAT_SIGNS_READS_THE_KEY_AND_NO_OTHER_DOES}"
            )
            raise SecretsUnavailableError(msg)
        if ref.role is not DELIVERING_ROLE:
            msg = (
                f"this reference was made for the {ref.role.value} role and the worker reads "
                f"only references made for {DELIVERING_ROLE.value}"
            )
            raise SecretsUnavailableError(msg)
        if self._vault is None:
            raise SecretsUnavailableError(NO_VAULT_ON_THIS_WORKER)
        try:
            fields = self._vault.read_static_kv(ref.path)
        except VaultRefusedError as refused:
            if refused.status == http.client.NOT_FOUND:
                raise SigningSecretAbsentError(ref.path) from refused
            raise
        value = fields.get(SIGNING_FIELD)
        if not isinstance(value, str) or not value:
            raise SigningSecretAbsentError(ref.path)
        return value


def worker_signing_keys(address: str, token: str) -> WorkerSigningKeys:
    """The worker's reader, from the two settings the worker's environment carries.

    Both must be set, for `brain.ops.credentials.credentials_at_start`'s reason. An address that
    is not a URL is no vault, and the run says so rather than failing on a `ValueError`.
    """
    if not address or not token:
        return WorkerSigningKeys(None)
    try:
        return WorkerSigningKeys(OpenBaoVault(address, token, role=VaultRole.WORKER))
    except ValueError:
        return WorkerSigningKeys(None)


# ----------------------------------------------------------------------- the sender
class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection opened to one address while speaking TLS and HTTP as the name.

    See `THE_CONNECTION_GOES_TO_THE_ADDRESS_THAT_WAS_CHECKED`. `connect` is the one method that
    would resolve `host`, and it is the one replaced; the Host header is `host` because
    `http.client` writes it from there, and SNI and the certificate check are `host` because
    `server_hostname` is.
    """

    def __init__(
        self, host: str, port: int, *, address: str, timeout: float, context: ssl.SSLContext
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._address = address
        self._pinned_context = context

    def connect(self) -> None:
        raw = socket.create_connection((self._address, self.port), self.timeout)
        try:
            self.sock = self._pinned_context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def retry_after_seconds(header: str | None) -> float | None:
    """A `Retry-After` given as whole seconds, or None when absent or given as a date.

    A date is None rather than parsed: the backoff's own wait applies, and
    `brain.connectors.throttle.RETRY_AFTER_WHEN_UNSTATED` is the long end on purpose.
    """
    if header is None or not header.strip().isdigit():
        return None
    return float(int(header.strip()))


class HttpsSender:
    """`brain.ops.outbox_store.Sender` over `http.client`, to the checked address, verbatim.

    `context` is a parameter so a test can trust its own certificate; the default verifies
    against the system's authorities and the name, which is what every install uses.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = DELIVERY_TIMEOUT_SECONDS,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._context = context if context is not None else ssl.create_default_context()

    def send(self, request: SignedRequest) -> SendResult:
        parts = urlsplit(request.url)
        host = parts.hostname
        if parts.scheme != "https" or not host:
            # Not reachable through `signed_request`, whose target has passed the https rule;
            # refused here too because this is the class that opens the socket.
            return SendResult(connection_failed=True)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        connection = _PinnedHTTPSConnection(
            host,
            parts.port or HTTPS_PORT,
            address=request.address,
            timeout=self._timeout,
            context=self._context,
        )
        headers = {
            **request.headers,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            connection.request("POST", path, body=request.body, headers=headers)
            answer = connection.getresponse()
            answer.read(MAX_ANSWER_BYTES)
            return SendResult(
                status=answer.status,
                retry_after_seconds=retry_after_seconds(answer.getheader("Retry-After")),
            )
        except TimeoutError:
            return SendResult(timed_out=True)
        except (OSError, http.client.HTTPException):
            return SendResult(connection_failed=True)
        finally:
            connection.close()


# ---------------------------------------------------------------------- the resolver
class SystemResolver:
    """`brain.tools.fetch.Resolver` over the operating system's resolver: every address, once.

    Every address rather than the first, because the rule refuses a name with any answer inside
    the network, and a name that failed to resolve answers nothing, which the rule refuses too.
    """

    def resolve(self, host: str) -> Sequence[str]:
        try:
            answers = socket.getaddrinfo(host, HTTPS_PORT, type=socket.SOCK_STREAM)
        except (socket.gaierror, UnicodeError):
            return ()
        return tuple(dict.fromkeys(str(one[4][0]) for one in answers))


# ------------------------------------------------------------------------ one run
@dataclass(frozen=True)
class DispatchRun:
    """What one run did, as counts. No subscriber, no address and no event is named."""

    delivered: int
    retrying: int
    set_aside: int

    def summary(self) -> str:
        if not (self.delivered or self.retrying or self.set_aside):
            return "nothing was due"
        return (
            f"{self.delivered} delivered, {self.retrying} to be tried again later, "
            f"{self.set_aside} set aside for a person"
        )


def run_of(attempts: Sequence[Attempt]) -> DispatchRun:
    """The counts a run's attempts come to, by the state each left its delivery in."""
    states = [one.delivery.state for one in attempts]
    return DispatchRun(
        delivered=states.count(DeliveryState.DELIVERED),
        retrying=states.count(DeliveryState.PENDING),
        set_aside=states.count(DeliveryState.EXHAUSTED),
    )


async def dispatch_on(
    database_url: str,
    *,
    now: datetime,
    signing_keys: SigningKeys,
    sender: Sender,
    resolver: Resolver,
    limit: int = DISPATCH_BATCH,
) -> DispatchRun:
    """One batch against the application's database, committed.

    Two connections, and they must be two. The claim's transaction holds the row locks and
    commits once, after every attempt is recorded; the ledger's connection autocommits every
    statement, because a ledger record inside that transaction would roll back with it and forget
    what was sent. See `brain.ops.operation_store.
    A_LEDGER_INSIDE_THE_CALLERS_TRANSACTION_FORGETS_WHAT_IT_ISSUED`.
    """
    engine = make_app_engine(database_url)
    try:
        with psycopg.connect(
            libpq_conninfo(database_url), autocommit=True, prepare_threshold=None
        ) as conn:
            ledger = PostgresOperationLedger(conn)
            async with make_session_factory(engine)() as session, session.begin():
                attempts = await dispatch_due(
                    session,
                    await claim_due(session, now=now, limit=limit),
                    now=now,
                    sender=sender,
                    signing_keys=signing_keys,
                    resolver=resolver,
                    ledger=ledger,
                )
    finally:
        await engine.dispose()
    return run_of(attempts)


def run_dispatch_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> DispatchRun:
    """`dispatch_on`, from a thread with no event loop of its own, with the worker's real parts.

    The shape `brain.knowledge.item_store.run_reverification_now` takes, for its reasons.
    """
    return asyncio.run(
        dispatch_on(
            database_url,
            now=now,
            signing_keys=worker_signing_keys(vault_address, vault_token),
            sender=HttpsSender(),
            resolver=SystemResolver(),
        ),
        loop_factory=loop_factory,
    )
