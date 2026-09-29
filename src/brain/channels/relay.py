"""The mail relay as a channel's vendor: a request for `RELAY_URL` leaves by SMTP, and no other.

Every channel but one sends by an HTTPS call to its vendor. Email has no vendor to call: a reply
leaves through the relay this install already has, the one an administrator set up on
Notifications and proved with a test message (`brain.ops.mail`). So the email wire addresses its
request to `RELAY_URL`, and `RelayingTransport` hands exactly that address to the relay and every
other address to the HTTPS transport it wraps.

**A second relay was the cheaper design, and it was rejected.** A channel with its own host,
port, user name and password in its record would have been a second place for a company's mail
credentials, set up on a different screen, proved by a different test and rotated by somebody who
did not know the first existed. One relay is one password in the vault, at `providers/mail_relay`,
and a channel reply and a notification leave by the same door. See
`ONE_RELAY_SERVES_EVERY_MESSAGE_THIS_INSTALL_SENDS`.

**The relay's password is borrowed for one send and never reaches the wire.** The wire builds its
request as a function of the channel's own secret, which for email signs what arrives and plays
no part in sending, and it never sees the relay's password. `RelayingTransport` asks for the relay
at the moment it sends, on the send's own thread inside `brain.ops.idempotency.issue_once`, and
the transport it is handed holds the password for that one message and is dropped with it.

**The address is not an address.** `RELAY_URL` has no host, so nothing that reads it as one could
connect anywhere: `brain.tools.fetch.assert_fetchable` refuses it, and the HTTPS transport would
answer it as an unsafe address and send nothing. It is a name for "the relay", and the relay's
real host is the one an administrator saved, which is deliberately not put through the webhook
address rule (see `brain.ops.mail`).

**A relay that is not set up sends nothing, and says so as an answer with no status and no
failure.** Not a connection failure, which a wire has to treat as "may have been delivered", and
not a status, which would be a code no relay gave. The email wire judges it refused, because
nothing left. See `A_RELAY_NOBODY_SET_UP_WAS_NEVER_ASKED`.

Task ids: M10.5.6, M10.6.1
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final

from brain.channels.adapter import ChannelTransport, VendorAnswer, VendorRequest
from brain.connectors.throttle import CallOutcome
from brain.ops.mail import MailAnswer, MailTransport, Message

#: Why a channel reply and a notification leave through one relay.
ONE_RELAY_SERVES_EVERY_MESSAGE_THIS_INSTALL_SENDS: Final = (
    "A channel with a relay of its own would be a second place for the company's mail password, "
    "set up and rotated apart from the first. Every message this install sends by mail leaves "
    "through the relay set up on Notifications, with its one password in the vault."
)

#: Why an answer with no status and no failure is the relay that was never asked.
A_RELAY_NOBODY_SET_UP_WAS_NEVER_ASKED: Final = (
    "With no relay set up there is nothing to hand the message to, so nothing left this install. "
    "The answer says that with no status and no failure, rather than a failure that would read "
    "as a message that may have been delivered."
)

#: The address a wire gives a request that leaves by the mail relay. No host, deliberately.
RELAY_URL: Final = "smtp:relay"

#: What a relay says when it took a message, as the answer's status: SMTP's own code.
RELAY_ACCEPTED: Final = 250

#: What a relay's refusal that named no code is answered as: SMTP's permanent failure.
RELAY_REFUSED_WITHOUT_A_CODE: Final = 550

#: The headers a request for the relay may carry, by the names `message_of` reads.
TO: Final = "to"
SUBJECT: Final = "subject"
REPLY_TO: Final = "reply-to"
IN_REPLY_TO: Final = "in-reply-to"
AUTO_SUBMITTED: Final = "auto-submitted"
RELAY_HEADERS: Final = frozenset({TO, SUBJECT, REPLY_TO, IN_REPLY_TO, AUTO_SUBMITTED})


def message_of(request: VendorRequest) -> Message:
    """The message a request for the relay describes, or `ValueError` for one it cannot.

    Refuses a header outside `RELAY_HEADERS` rather than dropping it, so a wire that asks for a
    `cc` is told so at once instead of sending without it and looking as though it had.
    """
    headers: Mapping[str, str] = request.headers
    unknown = sorted(set(headers) - RELAY_HEADERS)
    if unknown:
        msg = f"a message to the relay carries no {unknown}"
        raise ValueError(msg)
    if not headers.get(TO) or not headers.get(SUBJECT):
        msg = "a message to the relay names its recipient and its subject"
        raise ValueError(msg)
    return Message(
        to=headers[TO],
        subject=headers[SUBJECT],
        body=request.body.decode("utf-8"),
        reply_to=headers.get(REPLY_TO, ""),
        in_reply_to=headers.get(IN_REPLY_TO, ""),
        auto_submitted=headers.get(AUTO_SUBMITTED, ""),
    )


def answer_of(answer: MailAnswer) -> VendorAnswer:
    """What the relay did, in the terms a wire judges: its code, or that it could not be reached.

    A relay that took the message answers `RELAY_ACCEPTED`. A refusal answers its own code, or
    `RELAY_REFUSED_WITHOUT_A_CODE` when it named none. A relay that could not be reached, or that
    dropped the connection, is a connection failure, because the message may still have left.
    """
    if answer.outcome is CallOutcome.OK:
        return VendorAnswer(status=RELAY_ACCEPTED)
    if answer.outcome is CallOutcome.REJECTED:
        return VendorAnswer(status=answer.code or RELAY_REFUSED_WITHOUT_A_CODE)
    return VendorAnswer(connection_failed=True)


class RelayingTransport:
    """`ChannelTransport` sending `RELAY_URL` by the mail relay and everything else by `https`.

    `relay` is asked at each send, on the send's thread, and answers a transport holding the
    relay's password for that one message, or None when no relay is set up. A read is never
    for the relay: a relay has nothing to read.
    """

    def __init__(self, https: ChannelTransport, relay: Callable[[], MailTransport | None]) -> None:
        self._https = https
        self._relay = relay

    def send(self, request: VendorRequest) -> VendorAnswer:
        if request.url != RELAY_URL:
            return self._https.send(request)
        message = message_of(request)
        transport = self._relay()
        if transport is None:
            return VendorAnswer()
        return answer_of(transport.send(message))

    def read(self, request: VendorRequest) -> VendorAnswer:
        if request.url == RELAY_URL:
            msg = "the relay sends and has nothing to read"
            raise ValueError(msg)
        return self._https.read(request)
