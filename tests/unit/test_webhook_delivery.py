"""The worker's half of a webhook, held to a real TLS connection and, with a server, to the tables.

Three halves. The reader of signing secrets, held to what it refuses before the vault is asked and
to the worker's policy. The sender, held against an HTTPS server this file starts on the loopback
interface with a certificate it makes, so what is on the wire is read by a receiver rather than
by a fake of one. And the whole run against a database built through `0030` and `0051`: an event
written, a run started, the signed request received and verified, the row delivered and the
operation record settled.

The address a subscriber resolves to is checked by `brain.tools.fetch.assert_fetchable`, which
refuses loopback, so the end-to-end runs give the rule a public address and a sender that
connects to this file's server instead. That rerouting is the one thing here that is not the
production path, and the address rule itself is `tests/unit/test_outbox_store.py`'s.

Task ids: M27.8.12
"""

from __future__ import annotations

import http.server
import json
import re
import socket
import ssl
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from brain.ops.openbao import VaultRefusedError
from brain.ops.outbox import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    EventKind,
    OutboxEvent,
    SignedRequest,
    Subscriber,
    serialise,
    signature_for,
)
from brain.ops.outbox_store import SendResult, SigningSecretAbsentError, record_event
from brain.ops.outbox_store import register_subscriber as write_subscriber
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole
from brain.ops.webhook_admin import SIGNING_FIELD, signing_secret_ref
from brain.ops.webhook_delivery import (
    NO_VAULT_ON_THIS_WORKER,
    USER_AGENT,
    DispatchRun,
    HttpsSender,
    SystemResolver,
    WorkerSigningKeys,
    dispatch_on,
    retry_after_seconds,
    run_of,
    worker_signing_keys,
)
from tests.fixtures.scratch_postgres import built, engine, migrate, run, sql
from tests.unit.test_vault_policies import _granted_paths, _matches, _policy_file

NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)
SECRET = "a_signing_secret_nobody_could_type_in_one_go"
NAME = "hooks.receiver.invalid"


# ------------------------------------------------------------- the signing secret reader
class _Vault:
    """A kv engine in a dictionary, recording every path it was asked for."""

    def __init__(self, slots: dict[str, dict[str, Any]], *, refuse: int | None = None) -> None:
        self.slots = slots
        self.asked: list[str] = []
        self._refuse = refuse

    def read_static_kv(self, path: str) -> dict[str, Any]:
        self.asked.append(path)
        if self._refuse is not None:
            msg = f"refused with {self._refuse}"
            raise VaultRefusedError(msg, status=self._refuse)
        if path not in self.slots:
            raise VaultRefusedError("no such slot", status=404)
        return self.slots[path]


def test_the_worker_reads_the_secret_at_the_path_the_console_writes_it_to() -> None:
    """The positive half, joined to the writer: the reference a registration stores is the one
    this reads, and the field is the one the console writes.

    Delete this and a reader that looked under another field or path would refuse every delivery
    while each refusal test below stayed green."""
    ref = signing_secret_ref("billing_bridge")
    vault = _Vault({ref.path: {SIGNING_FIELD: SECRET}})

    assert WorkerSigningKeys(vault).signing_secret(ref) == SECRET
    assert vault.asked == [ref.path]


def test_a_reference_outside_the_signing_engine_is_refused_before_the_vault_is_asked() -> None:
    """**The worker reads signing secrets and nothing else.** A subscriber row edited to name a
    provider key is refused here without a request to the vault.

    Delete this and a row somebody changed by hand turns the dispatcher into a way to read any
    stored key the worker's token can reach, and sign it into a request sent outside."""
    vault = _Vault({"providers/anthropic": {SIGNING_FIELD: SECRET}})

    with pytest.raises(SecretsUnavailableError, match="webhooks/"):
        WorkerSigningKeys(vault).signing_secret(
            SecretRef(path="providers/anthropic", role=VaultRole.WORKER)
        )
    assert vault.asked == []


def test_a_reference_made_for_another_role_is_refused_before_the_vault_is_asked() -> None:
    """The role is compiled into a reference and not chosen by whoever reads it.

    Delete this and a reference made for the application is read by the worker anyway, which is
    the widening `brain.ops.secrets.VaultRole` exists to make impossible."""
    ref = SecretRef(path=signing_secret_ref("billing_bridge").path, role=VaultRole.APPLICATION)
    vault = _Vault({ref.path: {SIGNING_FIELD: SECRET}})

    with pytest.raises(SecretsUnavailableError):
        WorkerSigningKeys(vault).signing_secret(ref)
    assert vault.asked == []


def test_a_slot_the_vault_does_not_hold_is_one_subscriber_s_absence_and_not_an_outage() -> None:
    """A 404, and a slot with no signing field, are both absences; a 403 is the vault refusing the
    worker, which stops the batch.

    Delete this and one subscriber with no secret stops every delivery, or a policy that was never
    loaded parks every delivery as though each subscriber had lost its secret."""
    ref = signing_secret_ref("billing_bridge")

    with pytest.raises(SigningSecretAbsentError):
        WorkerSigningKeys(_Vault({})).signing_secret(ref)
    with pytest.raises(SigningSecretAbsentError):
        WorkerSigningKeys(_Vault({ref.path: {"other": "x"}})).signing_secret(ref)
    with pytest.raises(VaultRefusedError):
        WorkerSigningKeys(_Vault({}, refuse=403)).signing_secret(ref)


def test_a_worker_with_no_vault_refuses_every_read_saying_which_settings_to_set() -> None:
    """Both settings, or no vault. The refusal is the sentence the run records.

    Delete this and a worker with half a configuration could build a vault client that fails on
    its first request as a refusal, which sends somebody to read a policy."""
    ref = signing_secret_ref("billing_bridge")
    for keys in (worker_signing_keys("", ""), worker_signing_keys("http://vault:8200", "")):
        with pytest.raises(SecretsUnavailableError) as refused:
            keys.signing_secret(ref)
        assert str(refused.value) == NO_VAULT_ON_THIS_WORKER
    assert "configured=True" in repr(worker_signing_keys("http://vault:8200", "a-token"))
    assert "a-token" not in repr(worker_signing_keys("http://vault:8200", "a-token"))


def test_the_worker_policy_reads_signing_secrets_and_does_nothing_else_with_them() -> None:
    """Exactly one rule under the webhooks engine, read, and it matches the path this reads.

    Delete this and the worker's rule gains update in a debugging session, and a process nobody
    watches can replace the key every receiver checks."""
    granted = _granted_paths(_policy_file(VaultRole.WORKER).read_text(encoding="utf-8"))
    webhooks = {path: sorted(caps) for path, caps in granted.items() if path.startswith("webhooks")}
    assert webhooks == {"webhooks/data/+": ["read"]}

    mount, _, rest = signing_secret_ref("a" + "0" * 62).path.partition("/")
    assert _matches("webhooks/data/+", f"{mount}/data/{rest}")


# ------------------------------------------------------------------ a receiver of our own
@dataclass
class _Received:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass
class _Answer:
    status: int = 204
    headers: dict[str, str] = field(default_factory=dict)
    stall: float = 0.0


def _certificate(directory: Path, name: str) -> tuple[Path, Path]:
    """A self-signed certificate for `name`, and its key, written as PEM."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    made = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2020, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(3000, 1, 1, tzinfo=UTC))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert = directory / f"{name}.pem"
    private = directory / f"{name}.key"
    cert.write_bytes(made.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert, private


@dataclass
class _Receiver:
    port: int
    trusted: ssl.SSLContext
    received: list[_Received]
    answer: _Answer


@pytest.fixture
def receiver(tmp_path: Path) -> Iterator[_Receiver]:
    """An HTTPS server on the loopback interface answering as `NAME`, and a context trusting it."""
    cert, key = _certificate(tmp_path, NAME)
    received: list[_Received] = []
    answer = _Answer()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            received.append(_Received("POST", self.path, dict(self.headers.items()), body))
            if answer.stall:
                time.sleep(answer.stall)
            self.send_response(answer.status)
            for header, value in answer.headers.items():
                self.send_header(header, value)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    serving = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    serving.load_cert_chain(cert, key)
    server.socket = serving.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    trusted = ssl.create_default_context(cafile=str(cert))
    try:
        yield _Receiver(int(server.server_address[1]), trusted, received, answer)
    finally:
        server.shutdown()
        server.server_close()


def _request(receiver: _Receiver, *, name: str = NAME, body: bytes = b'{"a":1}') -> SignedRequest:
    return SignedRequest(
        url=f"https://{name}:{receiver.port}/brain/events?v=1",
        address="127.0.0.1",
        headers={TIMESTAMP_HEADER: "32503680000", SIGNATURE_HEADER: "ab" * 32},
        body=body,
    )


# ----------------------------------------------------------------------- the sender
def test_a_request_is_sent_to_the_checked_address_speaking_as_the_name_with_its_bytes(
    receiver: _Receiver,
) -> None:
    """**The connection goes to the address, and TLS and HTTP speak as the name.** The name ends in
    `.invalid`, which no resolver answers, so a sender that looked the name up again could not have
    connected at all. The receiver reads the exact bytes and both signed headers.

    Delete this and a sender that connected by name reopens DNS rebinding, and one that serialised
    the body again sends bytes the signature was not computed over."""
    body = b'{"event_id":"ev_1","kind":"operation.settled"}'
    result = HttpsSender(context=receiver.trusted).send(_request(receiver, body=body))

    assert result == SendResult(status=204)
    (got,) = receiver.received
    assert got.body == body
    assert got.path == "/brain/events?v=1"
    assert got.headers["Host"] == f"{NAME}:{receiver.port}"
    assert got.headers[TIMESTAMP_HEADER] == "32503680000"
    assert got.headers[SIGNATURE_HEADER] == "ab" * 32
    assert got.headers["User-Agent"] == USER_AGENT
    assert got.headers["Content-Type"] == "application/json"


def test_a_certificate_for_another_name_is_a_failed_connection_and_nothing_is_sent(
    receiver: _Receiver,
) -> None:
    """The certificate is checked against the name the subscriber registered, not the address.

    Delete this and a sender that skipped verification, or verified against the address, signs
    requests to whatever server answers on that address."""
    result = HttpsSender(context=receiver.trusted).send(
        _request(receiver, name="another.receiver.invalid")
    )

    assert result == SendResult(connection_failed=True)
    assert receiver.received == []


def test_an_answer_is_its_status_and_a_stated_wait_is_carried(receiver: _Receiver) -> None:
    """A 503 with a `Retry-After` in seconds reaches the backoff as both.

    Delete this and a sender that dropped the header retries a subscriber asking for two minutes
    after a few seconds, or one that ignored the status reads an outage as an acceptance."""
    receiver.answer.status = 503
    receiver.answer.headers = {"Retry-After": "120"}

    assert HttpsSender(context=receiver.trusted).send(_request(receiver)) == SendResult(
        status=503, retry_after_seconds=120.0
    )


def test_a_receiver_that_does_not_answer_in_time_is_a_timeout(receiver: _Receiver) -> None:
    """Timed out rather than failed to connect, because the request left and the backoff and the
    ledger both read the difference.

    Delete this and a slow receiver reads as one that refused the connection."""
    receiver.answer.stall = 2.0

    result = HttpsSender(timeout_seconds=0.5, context=receiver.trusted).send(_request(receiver))

    assert result == SendResult(timed_out=True)


def test_a_server_that_hangs_up_before_speaking_tls_is_a_failed_connection_not_an_exception() -> (
    None
):
    """The sender never raises for anything the network did. A listener that accepts and closes at
    once is a connection that failed before any request could leave.

    Delete this and one subscriber's broken server raises out of the effect and stops every
    delivery in the batch behind it."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def hang_up() -> None:
        accepted, _ = listener.accept()
        accepted.close()

    thread = threading.Thread(target=hang_up, daemon=True)
    thread.start()
    request = SignedRequest(
        url=f"https://{NAME}:{port}/", address="127.0.0.1", headers={}, body=b"{}"
    )
    try:
        assert HttpsSender(timeout_seconds=5.0).send(request) == SendResult(connection_failed=True)
    finally:
        thread.join(timeout=5.0)
        listener.close()


def test_a_stated_wait_is_read_only_as_whole_seconds() -> None:
    """A date is not guessed at: the backoff's own wait applies.

    Delete this and a date parsed wrongly becomes a wait of years or of nothing."""
    assert retry_after_seconds("30") == 30.0
    assert retry_after_seconds(" 7 ") == 7.0
    assert retry_after_seconds("Wed, 21 Oct 2999 07:28:00 GMT") is None
    assert retry_after_seconds("-5") is None
    assert retry_after_seconds(None) is None


def test_the_system_resolver_answers_every_address_once_and_nothing_for_a_name_that_is_not() -> (
    None
):
    """Every answer, deduplicated, so the address rule sees each one; nothing for a name that does
    not resolve, which the rule refuses.

    Delete this and a resolver that raised on an unknown name would stop the batch over one
    subscriber's typo."""
    found = SystemResolver().resolve("localhost")
    assert found and len(found) == len(set(found))
    assert SystemResolver().resolve("no-such-host.invalid") == ()


def test_a_run_is_reported_in_counts_and_names_nothing() -> None:
    """The summary the schedule records and the Webhooks screen shows.

    Delete this and a summary could carry an endpoint or an event id into a run record read by
    anybody who can open the scheduled jobs screen."""
    assert DispatchRun(0, 0, 0).summary() == "nothing was due"
    assert DispatchRun(2, 1, 0).summary() == (
        "2 delivered, 1 to be tried again later, 0 set aside for a person"
    )
    assert re.fullmatch(r"[0-9a-z ,]+", DispatchRun(1, 1, 1).summary())


# ------------------------------------------------------------------ with a server
class _Rerouted:
    """The production sender, connecting to this file's receiver whatever address was checked."""

    def __init__(self, receiver: _Receiver) -> None:
        self._sender = HttpsSender(timeout_seconds=5.0, context=receiver.trusted)

    def send(self, request: SignedRequest) -> SendResult:
        return self._sender.send(replace(request, address="127.0.0.1"))


class _PublicResolver:
    def resolve(self, host: str) -> Sequence[str]:
        return ("93.184.216.34",)


@pytest.fixture(scope="module")
def tables() -> Iterator[str]:
    """The outbox through `0030` and the operation ledger through `0051`, dropped afterwards."""
    database = "brain_webhook_delivery_check"
    with built(database, "0030") as url:
        migrate(database, "stamp", "0050")
        migrate(database, "upgrade", "0051")
        yield url


@pytest.fixture
def emptied(tables: str) -> str:
    sql(
        tables,
        "TRUNCATE ops.outbox_delivery, ops.outbox_event, ops.webhook_subscriber, ops.operation",
    )
    return tables


def _seed(url: str, receiver: _Receiver) -> None:
    subscriber = Subscriber(
        subscriber_id="billing_bridge",
        endpoint=f"https://{NAME}:{receiver.port}/brain",
        secret_ref=signing_secret_ref("billing_bridge"),
        kinds=(EventKind.OPERATION_SETTLED,),
        created_by="u_admin",
    )
    event = OutboxEvent(
        event_id="ev_end_to_end",
        kind=EventKind.OPERATION_SETTLED,
        entity="operation",
        record_id="op_1",
        occurred_at=NOW,
    )

    async def write() -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        made = engine(url)
        try:
            async with async_sessionmaker(made)() as session, session.begin():
                await write_subscriber(session, subscriber)
                await record_event(session, event, [subscriber])
        finally:
            await made.dispose()

    run(write)


def _dispatch(url: str, receiver: _Receiver) -> DispatchRun:
    keys = WorkerSigningKeys(
        _Vault({signing_secret_ref("billing_bridge").path: {SIGNING_FIELD: SECRET}})
    )
    return run(
        lambda: dispatch_on(
            url,
            now=NOW,
            signing_keys=keys,
            sender=_Rerouted(receiver),
            resolver=_PublicResolver(),
        )
    )


def test_a_due_event_is_signed_received_verified_and_recorded_delivered(
    emptied: str, receiver: _Receiver
) -> None:
    """**The leaf, end to end.** An event written with its delivery, a run of the dispatch, and a
    receiver that gets the event's canonical bytes with a signature it can verify with the shared
    secret. Then the row says delivered at the run's instant, and the operation ledger says the
    attempt succeeded under the webhook connector.

    Delete this and every part of delivery is tested apart and nothing shows that a subscriber is
    ever told anything."""
    _seed(emptied, receiver)

    ran = _dispatch(emptied, receiver)

    assert ran == DispatchRun(delivered=1, retrying=0, set_aside=0)
    (got,) = receiver.received
    parsed = json.loads(got.body)
    assert parsed["event_id"] == "ev_end_to_end"
    assert got.body == serialise(
        OutboxEvent(
            event_id="ev_end_to_end",
            kind=EventKind.OPERATION_SETTLED,
            entity="operation",
            record_id="op_1",
            occurred_at=NOW,
        )
    )
    expected = signature_for(secret=SECRET, sent_at=NOW, body=got.body)
    assert got.headers[SIGNATURE_HEADER] == expected
    assert sql(emptied, "SELECT state, attempts, last_attempt_at FROM ops.outbox_delivery") == [
        ("delivered", 1, NOW)
    ]
    assert sql(emptied, "SELECT connector, tool, principal_id, state FROM ops.operation") == [
        ("webhook", "outbox.deliver", "u_admin", "succeeded")
    ]


def test_a_second_run_sends_nothing_for_an_event_already_delivered(
    emptied: str, receiver: _Receiver
) -> None:
    """The positive run twice: the second claims nothing and the receiver hears once.

    Delete this and a claim that re-read delivered rows would tell a subscriber everything again
    every minute."""
    _seed(emptied, receiver)
    _dispatch(emptied, receiver)

    assert _dispatch(emptied, receiver) == DispatchRun(0, 0, 0)
    assert len(receiver.received) == 1


def test_a_receiver_that_is_down_leaves_the_delivery_pending_with_a_wait_and_an_unknown_attempt(
    emptied: str, receiver: _Receiver
) -> None:
    """A 503: one attempt counted, due again later rather than now, and the attempt's record left
    unknown, because a server error may have processed the request.

    Delete this and a failed attempt that reset nothing would be retried on the next tick for ever,
    or one read as failed would claim to know the receiver did nothing."""
    receiver.answer.status = 503
    _seed(emptied, receiver)

    assert _dispatch(emptied, receiver) == DispatchRun(delivered=0, retrying=1, set_aside=0)
    ((state, attempts, due_at),) = sql(
        emptied, "SELECT state, attempts, due_at FROM ops.outbox_delivery"
    )
    assert (state, attempts) == ("pending", 1)
    assert due_at > NOW
    assert sql(emptied, "SELECT state FROM ops.operation") == [("unknown",)]


def test_run_of_counts_each_state_a_run_left_its_deliveries_in() -> None:
    """The producer of the summary's counts, from attempts rather than from a `DispatchRun` built
    with the answer already in it.

    Delete this and a miscount between retrying and set aside reads on the screen as a healthy
    subscriber when every delivery to it is being parked."""
    from brain.ops.outbox import Attempt, Delivery, DeliveryState

    def one(state: DeliveryState) -> Attempt:
        return Attempt(
            delivery=Delivery(event_id="e", subscriber_id="s", attempts=1, state=state),
            delay_seconds=0.0,
            reason="x",
        )

    attempts = [
        one(DeliveryState.DELIVERED),
        one(DeliveryState.PENDING),
        one(DeliveryState.PENDING),
        one(DeliveryState.EXHAUSTED),
    ]
    assert run_of(attempts) == DispatchRun(delivered=1, retrying=2, set_aside=1)


def test_the_screen_s_store_reads_when_a_waiting_delivery_is_tried_next_and_what_the_dispatch_did(
    emptied: str, receiver: _Receiver
) -> None:
    """**The Webhooks screen, followed to the rows.** After a run the receiver refused, the store
    the screen reads says when that delivery is tried next, the newest run of the dispatch as the
    worker recorded it, and whether a person paused it; after the delivery is accepted, no next try.

    Delete this and the screen's store could read `due_at` for a delivered row, which tells an
    administrator a finished delivery is still waiting, or read another control's run as delivery's.
    """
    from brain.ops.schedule_control import set_paused
    from brain.ops.webhook_store import StoredWebhooks
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import SCHEDULE_CONTROL_TABLES, add_modelled

    add_modelled(emptied, (*SCHEDULE_CONTROL_TABLES, "ops.webhook_change"))
    sql(emptied, "TRUNCATE ops.control_run, ops.setting")
    receiver.answer.status = 503
    _seed(emptied, receiver)
    _dispatch(emptied, receiver)
    sql(
        emptied,
        "INSERT INTO ops.control_run (name, started_at, finished_at, outcome, detail, report_only)"
        " VALUES ('retention_sweep', %s, %s, 'ok', 'swept', false),"
        " ('outbox_dispatch', %s, %s, 'ok', '0 delivered, 1 to be tried again later, 0 set aside"
        " for a person', false)",
        NOW,
        NOW,
        NOW,
        NOW,
    )
    ((due_at,),) = sql(emptied, "SELECT due_at FROM ops.outbox_delivery")

    async def read() -> tuple[Any, Any]:
        made = engine(emptied)
        try:
            maker = make_session_factory(made)
            async with maker() as session, session.begin():
                await set_paused(session, "outbox_dispatch", paused=True, by="u_admin")
            store = StoredWebhooks(maker)
            return await store.registered(), await store.dispatcher()
        finally:
            await made.dispose()

    (registered,), line = run(read)
    (waiting,) = registered.deliveries
    assert (waiting.state, waiting.next_attempt_at) == ("pending", due_at)
    assert (line.outcome, line.paused) == ("ok", True)
    assert line.detail is not None and line.detail.startswith("0 delivered, 1 to be tried")

    receiver.answer.status = 204
    sql(emptied, "UPDATE ops.outbox_delivery SET due_at = %s", NOW)
    _dispatch(emptied, receiver)

    async def again() -> Any:
        made = engine(emptied)
        try:
            return await StoredWebhooks(make_session_factory(made)).registered()
        finally:
            await made.dispose()

    (after,) = run(again)
    (delivered,) = after.deliveries
    assert (delivered.state, delivered.next_attempt_at) == ("delivered", None)
