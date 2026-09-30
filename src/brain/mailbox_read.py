"""The email channel's mailbox, read once a minute by the application and answered as a post is.

`brain.channels.mailbox` decides how a mailbox is read and whose mail is believed; this is the part
that holds a connection. Once a minute it reads the email channel's record, and when the record
reads a mailbox it signs in with the password the vault holds, takes the unread mail, hands each
message to the same steps a post to the events address takes after its check, and marks what it
handled read.

**The application reads the mailbox, not the worker, and it is the vault's policies that decide.**
Answering a message takes the gate, the channel's own secret and the mail relay's password, and all
three are the application's: the worker's policy (`ops/openbao/policies/worker.hcl`) reads no
`providers/` slot, deliberately, and a scheduled process that could read the relay's password would
be a process nobody watches holding the company's mail credential. So the poll runs where the answer
is made, as a task the application's lifespan starts, the way it already keeps its vault token and
its credentials fresh. See `THE_PROCESS_THAT_ANSWERS_IS_THE_PROCESS_THAT_READS`.

**Every step after the read is the post's.** A message becomes the same signed-envelope shape the
Cloudflare script posts, with the verdict `brain.channels.mailbox.verdict_of` reached, and is handed
to `brain.channels.inbound.accept` and then `brain.channel_routes.answer_receipt`: claimed once by
its Message-ID, recorded in the channel's deliveries, an unlinked sender told how to link, a linked
one answered through the relay. Rejected: a second pipeline for mail from a mailbox, which would be
a second place the binding rule and the claim could drift apart from the first.

**Several application processes may read the same message; one answers it.** Each reads the unread
mail and none marks it before it is handled, so a message read by two processes, or read again after
a crash between answering and marking, is claimed once and answered once. A lock across processes
was rejected: it would hold a database transaction open for as long as a slow answer takes.

Task ids: M10.5.6, M10.6.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default
from typing import Final

import structlog
from fastapi import FastAPI
from starlette.requests import Request

from brain.channel_routes import (
    answer_receipt,
    claims_of,
    deliveries_of,
    records_of,
    secrets_of,
)
from brain.channels.adapter import Arrived
from brain.channels.email import ENVELOPE_AUTHENTICATION, ENVELOPE_MESSAGE, WIRE
from brain.channels.inbound import MAX_BODY_BYTES, ReceiptKind, accept
from brain.channels.mailbox import (
    MAILBOX_POLL_SECONDS,
    MOST_PER_POLL,
    MailboxReader,
    MailboxSettings,
    MailboxUnavailableError,
    open_mailbox,
    verdict_of,
)
from brain.channels.webhook import TIMESTAMP_HEADER
from brain.gate.context import Channel
from brain.ops.channel_store import ChannelSecretsUnavailableError, DeliveryEntry
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause

log = structlog.get_logger()

#: Why the application reads the mailbox and the worker does not.
THE_PROCESS_THAT_ANSWERS_IS_THE_PROCESS_THAT_READS: Final = (
    "Answering a mail takes the gate, the channel's secret and the relay's password, which the "
    "application holds and the worker's vault policy deliberately does not. So the application "
    "reads the mailbox, where the answer is made, and no scheduled process is given the company's "
    "mail credentials."
)

#: How the poll opens a mailbox: `brain.channels.mailbox.open_mailbox`, or a test's stand-in.
Opener = Callable[[MailboxSettings, str], MailboxReader]


@dataclass(frozen=True)
class MailboxRun:
    """What one read of the mailbox came to, in counts and one word. Never what a message said."""

    #: `read`, `off` (no record, switched off, or not a mailbox), `unready` or `unavailable`.
    state: str
    read: int = 0
    answered: int = 0
    refused: int = 0


def request_for(app: FastAPI) -> Request:
    """A request on the application, so the route's own wiring functions choose every store."""
    return Request({"type": "http", "app": app, "headers": [], "method": "POST"})


def _envelope(raw: bytes, settings: MailboxSettings) -> bytes:
    """The message and the verdict on it, in the shape the Cloudflare script posts."""
    parsed = message_from_bytes(raw, _class=EmailMessage, policy=default)
    verdict = verdict_of(parsed, settings)
    return json.dumps(
        {ENVELOPE_AUTHENTICATION: verdict.value, ENVELOPE_MESSAGE: raw.decode("utf-8", "replace")}
    ).encode("utf-8")


async def read_mailbox_once(
    app: FastAPI, *, now: datetime, opener: Opener = open_mailbox
) -> MailboxRun:
    """Read the unread mail once, answer what may be answered, and mark what was handled."""
    request = request_for(app)
    record = await records_of(request).get(Channel.EMAIL)
    if record is None or not record.enabled:
        return MailboxRun(state="off")
    try:
        settings = MailboxSettings.of(record.tenant)
    except ValueError:
        log.info("mailbox record incomplete")
        return MailboxRun(state="unready")
    if settings is None:
        return MailboxRun(state="off")
    try:
        password = await asyncio.to_thread(secrets_of(request).read, record.secret)
    except ChannelSecretsUnavailableError:
        return MailboxRun(state="unavailable")
    if password is None:
        return MailboxRun(state="unready")
    try:
        reader = await asyncio.to_thread(opener, settings, password)
    except MailboxUnavailableError as unavailable:
        log.info("mailbox not read", why=str(unavailable))
        return MailboxRun(state="unavailable")
    del password
    try:
        messages = await asyncio.to_thread(reader.unseen, MOST_PER_POLL)
        claims, deliveries = claims_of(request), deliveries_of(request)
        handled: list[str] = []
        answered = refused = 0
        for ident, raw in messages:
            envelope = _envelope(raw, settings)
            if len(envelope) > MAX_BODY_BYTES:
                await deliveries.record(
                    DeliveryEntry(
                        channel=Channel.EMAIL,
                        direction=Direction.INBOUND,
                        outcome=DeliveryOutcome.REFUSED,
                        reason=RefusedBecause.TOO_LARGE,
                    )
                )
                refused += 1
                handled.append(ident)
                continue
            # The check a post needs was made where the mail was read; see the module.
            opened = Arrived(headers={TIMESTAMP_HEADER: str(int(now.timestamp()))}, body=envelope)
            receipt = await accept(WIRE, opened=opened, claims=claims, deliveries=deliveries)
            if receipt.kind is ReceiptKind.ACCEPTED:
                await answer_receipt(request, receipt, record, now)
                answered += 1
            elif receipt.kind is ReceiptKind.REFUSED:
                refused += 1
            handled.append(ident)
        await asyncio.to_thread(reader.mark_handled, handled)
    except MailboxUnavailableError as unavailable:
        log.info("mailbox not read", why=str(unavailable))
        return MailboxRun(state="unavailable")
    finally:
        await asyncio.to_thread(reader.close)
    return MailboxRun(state="read", read=len(messages), answered=answered, refused=refused)


async def keep_reading_the_mailbox(app: FastAPI) -> None:
    """Read the mailbox every `MAILBOX_POLL_SECONDS` for as long as the application runs.

    A failure is logged by its kind and the next minute tries again: a mailbox that cannot be
    reached this minute is one this loop must still read the next.
    """
    while True:
        await asyncio.sleep(MAILBOX_POLL_SECONDS)
        try:
            ran = await read_mailbox_once(app, now=datetime.now(UTC))
        except Exception as exc:
            log.warning("mailbox read failed", kind=type(exc).__name__)
            continue
        if ran.state == "read" and ran.read:
            log.info("mailbox read", read=ran.read, answered=ran.answered, refused=ran.refused)
