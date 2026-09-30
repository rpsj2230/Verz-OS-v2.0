"""Email from an ordinary mailbox: read over IMAP, the sender judged by the stamp the mailbox's own
provider put on the message when it arrived, and nothing ever deleted.

The first way into the email channel needed a company's mail and DNS on Cloudflare, so a company on
anybody else's mail could not reach the Brain by email at all. This is the second, and the one the
Connect Email flow offers first: a mailbox the company already knows how to make, such as
ask@ their own domain, which this install reads. See `A_MAILBOX_IS_THE_WAY_IN_EVERY_COMPANY_HAS`.

**The sender is judged by the receiving provider's own stamp, pinned by name and position, and
never by anything else in the message.** `brain.channels.email` is built on one rule: the verdict
about who sent a message comes from the infrastructure that received it and never from the
message, because a sender who writes their own From writes their own `Authentication-Results`
too. A mailbox read over IMAP has no receiver in front of this install to hand a verdict over, so
the verdict is read from the one place the receiver writes it, and only there:

- the **topmost** `Authentication-Results` header, because the receiving server prepends its own
  above every header the message arrived with, so anything a sender forged sits below it;
- **only when it names the receiver** configured on the channel's record (`receiver`, such as
  `mx.google.com`), because a header naming anybody else is not this provider's; and
- **only a DMARC pass for the From address's own domain**, the same test Cloudflare applies on the
  other path.

Microsoft 365 stamps no name on that header, so for it the record names `exchange`, and the verdict
is the header Exchange itself sets on mail sent inside the organisation,
`X-MS-Exchange-Organization-AuthAs: Internal`. Exchange removes every
`X-MS-Exchange-Organization-` header from mail arriving from outside (its header firewall), so the
header being there at all was written inside. See
`THE_RECEIVER_S_STAMP_IS_READ_BY_NAME_AND_POSITION`.

And on either rule, mail from a domain the record does not name as the company's own is not
answered, as the Cloudflare script turns it away: the channel answers colleagues.

**Handled messages are marked read and never deleted.** A message is marked `\\Seen` once it has
been handled, answered or refused, and the search is for unseen mail, so the mailbox remains the
company's own record of everything asked. Nothing here expunges, moves or deletes. The mailbox is
the Brain's own, and the steps say so: somebody reading it by hand would mark mail as seen before it
is answered. A message read twice, by two processes or after a crash between answering and marking,
is claimed once by `gate.channel_event`, so it is answered once. See
`A_HANDLED_MESSAGE_IS_MARKED_AND_NEVER_DELETED`.

**The password is the channel's secret, read for each poll.** Host, port, user, the receiver's name
and the company's domains are on the channel's record, as the mail relay keeps its own on
Notifications; the password is in the vault in the channel's own slot and is read when a poll
starts and dropped when it ends. The Cloudflare path's signing secret lives in the same slot, which
is why `brain.channels.email.EmailWire.verify` refuses every post to the events address on a channel
that reads a mailbox: the mailbox password must never sign anything.

Rejected: IMAP IDLE. It holds a connection open per process for as long as the process lives, which
is a long-lived login to a company's mailbox for an answer a minute sooner; a poll a minute logs in,
reads and leaves.

Task ids: M10.5.6, M10.6.1
"""

from __future__ import annotations

import imaplib
import re
import ssl
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Final, Protocol

from brain.channels.email import (
    DOMAINS,
    IMAP_HOST,
    IMAP_PORT,
    IMAP_USER,
    RECEIVER,
    Authentication,
    EmailRefusedError,
    sender_address,
)

# ------------------------------------------------------------------ written-down reasons

#: Why a mailbox is the first way in.
A_MAILBOX_IS_THE_WAY_IN_EVERY_COMPANY_HAS: Final = (
    "Every company that has mail can make a mailbox and turn on IMAP for it, whoever hosts its "
    "mail and its DNS; Cloudflare Email Routing needs both on Cloudflare. So a mailbox is the way "
    "in the steps offer first, and Cloudflare the alternative for a company already on it."
)

#: Why the provider's stamp is believed only by its name and its place at the top.
THE_RECEIVER_S_STAMP_IS_READ_BY_NAME_AND_POSITION: Final = (
    "A receiving server prepends its Authentication-Results above every header the message "
    "arrived with, and names itself in it. So the verdict is the topmost such header and only "
    "when it names the receiver the channel was set up with, a DMARC pass for the From domain; "
    "for Exchange, which names nobody, the header it sets on mail sent inside the organisation "
    "and removes from mail arriving from outside."
)

#: Why a handled message is marked and kept.
A_HANDLED_MESSAGE_IS_MARKED_AND_NEVER_DELETED: Final = (
    "The mailbox is the company's record of what was asked. A handled message is marked read and "
    "nothing is ever expunged, moved or deleted; a message read twice is claimed once, so it is "
    "answered once."
)

#: What `receiver` says for Microsoft 365, whose stamp names nobody.
EXCHANGE: Final = "exchange"

#: The header Exchange sets on mail sent inside the organisation, and the value that says so.
EXCHANGE_AUTH_AS: Final = "X-MS-Exchange-Organization-AuthAs"
EXCHANGE_INTERNAL: Final = "Internal"

#: The header a receiving server writes its checks into (RFC 8601).
AUTHENTICATION_RESULTS: Final = "Authentication-Results"

#: IMAP over TLS from the first byte. Plain IMAP and STARTTLS are not offered: a password that could
#: cross a network in the clear is refused for `brain.ops.mail`'s reason.
IMAPS_PORT: Final = 993

#: How often the mailbox is read, and the most messages one poll handles.
MAILBOX_POLL_SECONDS: Final = 60
MOST_PER_POLL: Final = 20

#: How long one IMAP exchange may take before the poll gives up for this minute.
IMAP_TIMEOUT_SECONDS: Final = 30.0

_HOST: Final = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})+$"
)
_COMMENT: Final = re.compile(r"\([^()]*\)")


class MailboxUnavailableError(Exception):
    """The mailbox could not be reached, signed in to or read. Says which, never with what."""


@dataclass(frozen=True)
class MailboxSettings:
    """How the channel reads its mailbox, from its record. No password: that is the secret."""

    host: str
    port: int
    user: str
    receiver: str
    domains: frozenset[str]

    @classmethod
    def of(cls, tenant: Mapping[str, str]) -> MailboxSettings | None:
        """The settings a record holds, None for a record that reads no mailbox, `ValueError` for
        one that names a host and is not complete."""
        host = tenant.get(IMAP_HOST, "").strip().lower()
        if not host:
            return None
        port_text = tenant.get(IMAP_PORT, "").strip() or str(IMAPS_PORT)
        user = tenant.get(IMAP_USER, "").strip()
        receiver = tenant.get(RECEIVER, "").strip().lower()
        domains = frozenset(
            one.strip().lower() for one in tenant.get(DOMAINS, "").split(",") if one.strip()
        )
        if not _HOST.fullmatch(host):
            msg = f"{IMAP_HOST} is not a host name"
            raise ValueError(msg)
        if not port_text.isdigit() or not 0 < int(port_text) < 65536:
            msg = f"{IMAP_PORT} is not a port"
            raise ValueError(msg)
        if not user or not receiver or not domains:
            msg = f"a record reading a mailbox names its {IMAP_USER}, {RECEIVER} and {DOMAINS}"
            raise ValueError(msg)
        return cls(host=host, port=int(port_text), user=user, receiver=receiver, domains=domains)


def sender_domain(message: EmailMessage) -> str:
    """The From address's domain, lower-cased, or empty when From names no one address."""
    try:
        address = sender_address(str(message.get("from", "")))
    except EmailRefusedError:
        return ""
    return address.rpartition("@")[2]


def _dmarc_passed_for(stamp: str, domain: str) -> bool:
    """Whether one Authentication-Results value records a DMARC pass for this From domain."""
    for clause in _COMMENT.sub(" ", stamp).split(";"):
        words = clause.split()
        if not words or words[0].lower() != "dmarc=pass":
            continue
        properties = dict(one.lower().split("=", 1) for one in words[1:] if "=" in one)
        return properties.get("header.from", "") == domain
    return False


def verdict_of(message: EmailMessage, settings: MailboxSettings) -> Authentication:
    """What the mailbox's provider concluded about this message's sender, read as the module says.

    `NOT_CHECKED` for a sender outside the company's domains, or a message the named receiver did
    not stamp; `FAILED` for one it stamped and did not pass; `PASSED` only for the stamp the module
    docstring describes. See `THE_RECEIVER_S_STAMP_IS_READ_BY_NAME_AND_POSITION`.
    """
    domain = sender_domain(message)
    if not domain or domain not in settings.domains:
        return Authentication.NOT_CHECKED
    if settings.receiver == EXCHANGE:
        stamped = message.get_all(EXCHANGE_AUTH_AS) or []
        if len(stamped) != 1:
            return Authentication.NOT_CHECKED
        internal = str(stamped[0]).strip() == EXCHANGE_INTERNAL
        return Authentication.PASSED if internal else Authentication.FAILED
    stamps = message.get_all(AUTHENTICATION_RESULTS) or []
    if not stamps:
        return Authentication.NOT_CHECKED
    topmost = " ".join(str(stamps[0]).split())
    named, _, results = topmost.partition(";")
    if named.strip().lower() != settings.receiver:
        return Authentication.NOT_CHECKED
    return Authentication.PASSED if _dmarc_passed_for(results, domain) else Authentication.FAILED


# ------------------------------------------------------------------ reading the mailbox


class MailboxReader(Protocol):
    """One signed-in session on the mailbox: its unseen mail, and marking what was handled."""

    def unseen(self, most: int) -> list[tuple[str, bytes]]:
        """The oldest unseen messages, up to `most`, each as its id and its exact bytes. Reading
        one does not mark it: see `mark_handled`."""
        ...

    def mark_handled(self, ids: Sequence[str]) -> None:
        """Mark these messages read. Never deletes, moves or expunges anything."""
        ...

    def close(self) -> None:
        """Sign out. A second call does nothing."""
        ...


@dataclass
class ImapMailbox:
    """`MailboxReader` over `imaplib`, TLS verified against the host, the password kept for the
    one session. Its representation names the host and nothing else."""

    connection: imaplib.IMAP4_SSL = field(repr=False)
    host: str
    closed: bool = False

    def unseen(self, most: int) -> list[tuple[str, bytes]]:
        try:
            status, found = self.connection.uid("SEARCH", "UNSEEN")
            if status != "OK":
                raise MailboxUnavailableError("the mailbox did not answer a search")
            ids = [one.decode("ascii") for one in (found[0] or b"").split()][:most]
            messages: list[tuple[str, bytes]] = []
            for one in ids:
                status, parts = self.connection.uid("FETCH", one, "(BODY.PEEK[])")
                raw = next(
                    (part[1] for part in parts if isinstance(part, tuple) and len(part) == 2),
                    None,
                )
                if status != "OK" or not isinstance(raw, bytes):
                    raise MailboxUnavailableError("the mailbox did not hand over a message")
                messages.append((one, raw))
        except (OSError, imaplib.IMAP4.error) as exc:
            raise MailboxUnavailableError("the mailbox stopped answering") from exc
        return messages

    def mark_handled(self, ids: Sequence[str]) -> None:
        if not ids:
            return
        try:
            status, _ = self.connection.uid("STORE", ",".join(ids), "+FLAGS", "(\\Seen)")
        except (OSError, imaplib.IMAP4.error) as exc:
            raise MailboxUnavailableError("the mailbox stopped answering") from exc
        if status != "OK":
            raise MailboxUnavailableError("the mailbox did not mark messages read")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.connection.logout()
        except (OSError, imaplib.IMAP4.error):
            self.connection.shutdown()


def open_mailbox(
    settings: MailboxSettings, password: str, *, context: ssl.SSLContext | None = None
) -> ImapMailbox:
    """Signed in to the mailbox's inbox, or `MailboxUnavailableError` saying which step failed.

    `context` is a parameter so a test can trust its own certificate; an install verifies the
    host's certificate against the system's authorities.
    """
    try:
        connection = imaplib.IMAP4_SSL(
            settings.host,
            settings.port,
            ssl_context=context if context is not None else ssl.create_default_context(),
            timeout=IMAP_TIMEOUT_SECONDS,
        )
    except (OSError, imaplib.IMAP4.error) as exc:
        raise MailboxUnavailableError("the mailbox could not be reached over TLS") from exc
    try:
        connection.login(settings.user, password)
        status, _ = connection.select("INBOX")
    except (OSError, imaplib.IMAP4.error) as exc:
        connection.shutdown()
        raise MailboxUnavailableError("the mailbox refused the user and password") from exc
    if status != "OK":
        connection.shutdown()
        raise MailboxUnavailableError("the mailbox has no inbox to read")
    return ImapMailbox(connection=connection, host=settings.host)
