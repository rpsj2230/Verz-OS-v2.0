"""Email, where the sender writes their own name on the envelope.

Every other channel here is handed an identity by something that checked it. Lark sits
behind the tenant and its identity provider, WhatsApp's `from` is the vendor's own account
identifier, the console has a session. Email has none of that: `From:` is a header the
sender composes, and anybody can compose one that says anything.

**So the authentication verdict is a parameter and is never read out of the message.**
This is the whole shape of the module and it is worth being blunt about, because the
convenient version is a two-line function that greps `Authentication-Results` out of the
headers and believes it. That header is inside the message. A sender who writes their own
`From` writes their own `Authentication-Results` in the same breath, and the only copy worth
anything is the one the *receiving* infrastructure prepended after checking, which cannot be
told apart from the forgeries by looking at the text. `normalise` therefore takes an
`Authentication` the caller obtained from the MTA, and there is deliberately no code path in
this file that reads that header. See `THE_VERDICT_COMES_FROM_THE_MTA_AND_NEVER_FROM_THE_MESSAGE`.

**An unauthenticated message has no sender, and that is not the same as an unknown sender.**
`gate.ingress` already draws the line between an identity nobody has bound and one that does
not exist; this draws an earlier one. A message that failed DMARC is not a message from
somebody we cannot place, it is a message from nobody, and deriving a `channel_identity` from
it would let anybody address the system as anybody. `identity_hash` is salted per channel, so
a forged binding here could not reach a WhatsApp window, but it would reach this person's own
email reach, which is the entire point of forging it.

**DMARC is about the domain and never about the person.** A pass proves the message came
from something authorised to send for that domain. On a shared tenant that is every other
person on it, and on a mailing list it is the list. What it buys is that the domain is real
and the address was not invented; what it does not buy is that this human sent it. That is
why `Channel.EMAIL` carries `read` and nothing else in `gate.admission.CHANNEL_VERBS`, and
why nothing here raises the assurance a binding is worth.

**A reply goes to one person and never to the thread.** The other participants on a thread
have their own reach and none of it was consulted; an answer computed for the sender and
delivered to `Cc` is a disclosure to everybody who happened to be on a mail somebody wrote.
`Reply` has one recipient field and no `cc` at all, so reply-all is not something a caller
can ask for by mistake. See `A_REPLY_IS_ADDRESSED_TO_THE_PERSON_THE_ANSWER_WAS_COMPUTED_FOR`.

**The subject carries no answer.** A subject line is the one part of a message that appears
in a lock-screen notification, in a mail server's logs, in a backup index and in the
recipient's mailbox list, all of which outlive the message and none of which the gate
decided. So a reply's subject is fixed words with a prefix, and there is no argument that
lets a caller put anything else there. The wire's replies say `Re: Your question` rather than
the sender's own subject: only the address and the Message-ID survive from the question to
the send, and threading by the Message-ID is what puts the reply under the question. See
`A_REPLY_THREADS_BY_ITS_ID_AND_SAYS_NOTHING_IN_ITS_SUBJECT`.

**The wire receives a signed envelope, and the recipe for one is a script in the steps.**
`EmailWire` is `brain.channels.adapter.ChannelWire` for this channel: what arrives is a JSON
envelope holding the whole message and the receiver's verdict, signed with the channel's
secret over the time and the exact bytes, which is `brain.channels.webhook`'s construction
reused rather than a second one. The verdict is the receiving service's, stated outside the
message and covered by the signature, so this module still reads no verdict out of a header.
See `THE_RECEIVER_STATES_ITS_VERDICT_AND_SIGNS_IT`. `GUIDE` sets that receiver up in
Cloudflare Email Routing with an Email Worker, `WORKER_SCRIPT`, which turns away every domain
but the company's own before posting anything; a company whose mail arrives elsewhere posts
the same envelope from its own receiver, and nothing on this side changes. Rejected: reading
a mailbox over IMAP, which holds a mailbox password in this install, polls, and gets its
verdict from an `Authentication-Results` header nothing here can tell from a forgery.

**A reply leaves by the install's own relay.** `EmailWire.request_for` addresses
`brain.channels.relay.RELAY_URL`, which `brain.channel_routes` hands to the relay saved on
Notifications with its password borrowed for the one send, so this channel keeps no mail
credential of its own and its record holds only the address people write to.

**Automatic mail is never answered.** Two systems replying to each other is a loop that ends
in a full mailbox or a rate limit, and it is the classic way an autoresponder takes down a
support address. RFC 3834's `Auto-Submitted` and the older `Precedence: bulk` are both read,
and this module's own replies declare `Auto-Submitted: auto-replied` so that a correct
counterpart does the same for us.

Nothing here opens a socket, imports an SMTP library or holds a credential. The transport
belongs on the other side of `sent`, for the reason `channels.whatsapp` gives: the case worth
testing is a reply addressed to the wrong participant, and a module that connected to a mail
server could only be tested for it against a live mailbox.

Task ids: M10.5.6, M10.6.1
"""

from __future__ import annotations

import enum
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import message_from_string
from email.message import EmailMessage
from email.policy import default
from email.utils import parseaddr
from string import Template
from typing import Final

from brain.channels.adapter import (
    EVENTS_ADDRESS_ASK,
    SECRET_ASK,
    Arrived,
    ChannelCapabilities,
    Feature,
    Received,
    VendorAnswer,
    VendorRequest,
    assert_can_send,
    send_operation,
)
from brain.channels.cards import assert_label_survives, render_body
from brain.channels.relay import (
    IN_REPLY_TO,
    RELAY_ACCEPTED,
    RELAY_URL,
    REPLY_TO,
    SUBJECT,
    TO,
)
from brain.channels.webhook import SIGNATURE_HEADER, TIMESTAMP_HEADER
from brain.channels.webhook import verify as verify_signed
from brain.connectors.throttle import CallOutcome
from brain.core.field_policy import Classification
from brain.core.redaction import ChannelPayload
from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent, Unrecognised, identity_hash
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed
from brain.ops.idempotency import Intent, Issued, Operation, OperationLedger, issue_once

# ------------------------------------------------------------------ written-down reasons

#: Why the verdict is an argument rather than something parsed out of the headers.
THE_VERDICT_COMES_FROM_THE_MTA_AND_NEVER_FROM_THE_MESSAGE: Final = (
    "Authentication-Results lives inside the message, so a sender who forges From forges it "
    "too, and the honest copy prepended by the receiving MTA is textually identical to the "
    "forged ones above it. The verdict is therefore supplied by whatever ran the check, and "
    "this module has no code that reads that header"
)

#: Why a message that did not authenticate has no sender at all.
AN_UNAUTHENTICATED_MESSAGE_HAS_NO_SENDER: Final = (
    "a message that failed authentication is not from somebody we cannot place, it is from "
    "nobody; deriving an identity from its From header would let anyone address this system "
    "as anyone, and the binding they would reach is that person's own"
)

#: Why a pass is about the domain and stops there.
DMARC_AUTHENTICATES_A_DOMAIN_AND_NOT_A_PERSON: Final = (
    "a pass proves the message came from something authorised to send for that domain, "
    "which on a shared tenant is every colleague and on a mailing list is the list; it is "
    "evidence the address is real and none at all that this human sent it"
)

#: Why there is no Cc and no reply-all.
A_REPLY_IS_ADDRESSED_TO_THE_PERSON_THE_ANSWER_WAS_COMPUTED_FOR: Final = (
    "everybody else on a thread has their own reach and none of it was consulted; an answer "
    "computed for the sender and copied to the thread is a disclosure to whoever happened to "
    "be on a mail somebody else wrote"
)

#: Why the subject is never built from data.
A_SUBJECT_OUTLIVES_THE_MESSAGE: Final = (
    "the subject is the part that appears on a lock screen, in a mail server's logs, in a "
    "backup index and in a mailbox list, none of which the gate decided and all of which "
    "outlive the message the redaction was applied to"
)

# ------------------------------------------------------------------------------- the rule


class Authentication(enum.StrEnum):
    """What the receiving infrastructure concluded about this message's origin.

    Three values, and the middle one is why this is not a boolean. `NOT_CHECKED` is a
    deployment that has not been wired to an MTA that checks, and it must be distinguishable
    from a message that was checked and failed: the first is our configuration problem and
    the second is somebody attacking us. Collapsing them makes an unconfigured install look
    like it is under attack, and a real attack look like a configuration gap.

    All three are treated identically at the gate, which is the correct outcome and not a
    reason to have fewer of them. What differs is what an operator is told.
    """

    #: SPF, DKIM and DMARC were evaluated and the message is aligned with its From domain.
    PASSED = "pass"
    #: Evaluated, and it is not.
    FAILED = "fail"
    #: Nobody evaluated it. Not a pass. See the class docstring.
    NOT_CHECKED = "not_checked"

    @property
    def establishes_a_sender(self) -> bool:
        """Whether a `From` address on this message may be treated as an address at all.

        A property rather than `is Authentication.PASSED` written at each call site, so a
        fourth verdict is one edit here rather than a search. `NOT_CHECKED` answers False,
        which means an install that is not wired to a checking MTA accepts nothing, and
        that is the safe direction: it fails as "email does not work yet" rather than as
        "anybody may be anybody".
        """
        return self is Authentication.PASSED


#: What email can carry. No `CARDS`, for the reason WhatsApp has none and one email does not:
#: `gate.admission.CHANNEL_VERBS` gives email `read` alone, so a button could never be
#: honoured as an approval. No `EPHEMERAL`, because a mail has exactly one copy per
#: recipient and a per-viewer body has nowhere to live. No `EDIT_IN_PLACE`, because a message
#: that has been delivered cannot be recalled, whatever a mail client's button says.
EMAIL_FEATURES: Final[frozenset[Feature]] = frozenset({Feature.ATTACHMENTS})

#: Headers that mark a message as machine-generated. Both are read: RFC 3834's is the
#: correct one and `Precedence` is what a great deal of software still sends.
AUTO_SUBMITTED = "auto-submitted"
PRECEDENCE = "precedence"

#: `Auto-Submitted` values that mean a human did not send this. The RFC's "no" means a human
#: did, and is the only value that is not automatic.
HUMAN_AUTO_SUBMITTED: Final = "no"

#: `Precedence` values that mean the same thing in older software.
BULK_PRECEDENCE: Final = frozenset({"bulk", "junk", "list", "auto_reply"})

#: What this module puts on its own replies so a correct counterpart does not answer them.
#: Without it two systems answer each other until a mailbox fills, which is the classic way
#: an autoresponder takes down a support address.
OUR_AUTO_SUBMITTED: Final = "auto-replied"

#: The prefix a reply's subject carries. The rest of the subject is the sender's own words,
#: which they already know. See `A_SUBJECT_OUTLIVES_THE_MESSAGE`.
REPLY_PREFIX: Final = "Re: "

#: What a reply's subject falls back to when the original had none. Fixed text, deliberately
#: saying nothing about the question or the answer.
NO_SUBJECT: Final = "Your question"

#: The highest assurance an email binding is ever worth, whatever the authentication said.
#: Equal to `Assurance.BOUND` and stated here so the ceiling is visible in this file rather
#: than inferred from the absence of anything raising it.
EMAIL_ASSURANCE_CEILING: Final = Assurance.BOUND


class EmailRefusedError(Exception):
    """Raised when a message cannot be read, or a reply must not be sent.

    An operations and programming error rather than a user-facing one. What a sender sees is
    either the ordinary unrecognised prompt or nothing at all, by design: a bounce that
    explained why would tell whoever forged the message which part of the forgery failed.
    """


def _header(headers: dict[str, str], name: str) -> str:
    """One header, case-insensitively, or an empty string.

    Header names are case-insensitive per RFC 5322 and arrive from a dozen different mail
    stacks with a dozen different capitalisations. A plain `headers.get("Auto-Submitted")`
    reads as correct and misses `auto-submitted:`, which is the spelling that matters
    because it is the one an attacker picks after reading this file.
    """
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return ""


def is_automatic(headers: dict[str, str]) -> bool:
    """Whether this message was generated by software rather than written by a person.

    Answered on the headers alone. A heuristic over the body ("looks like an out of office")
    would refuse real questions from people who happen to be away, and the cost of a missed
    detection here is a loop rather than a disclosure, so the cheap and exact check is the
    right one.
    """
    auto = _header(headers, AUTO_SUBMITTED).strip().lower()
    if auto and auto != HUMAN_AUTO_SUBMITTED:
        return True
    return _header(headers, PRECEDENCE).strip().lower() in BULK_PRECEDENCE


def sender_address(from_header: str) -> str:
    """The addr-spec out of a `From` header, lowercased, with the display name discarded.

    **The display name is attacker-controlled and is never read.** `"Rupash Jha"
    <attacker@example.invalid>` renders in most clients as the name alone, which is the whole
    trick; `channels.lark.Mention` refuses a display name for the same reason and
    `channels.whatsapp` refuses the WhatsApp profile name. Only the address is keyed on.

    Lowercased because the domain is case-insensitive and mailbox names are case-insensitive
    in every mail system anybody actually runs. Two digests for one person would be two
    bindings, and the one they did not use looks unbound.
    """
    _display, addr = parseaddr(from_header)
    if not addr or "@" not in addr:
        msg = "this message has no usable From address, so there is nobody it could be from"
        raise EmailRefusedError(msg)
    return addr.strip().lower()


@dataclass(frozen=True)
class InboundEmail:
    """One message, already authenticated by something else, as this module reads it.

    `authentication` is required and has no default. A default of `PASSED` would be a
    catastrophe waiting for one forgetful caller, and a default of `FAIL` would be a
    plausible-looking constructor that silently refuses every real message. Making it
    required means the caller has to have asked.
    """

    message_id: str
    from_header: str
    subject: str
    body: str
    received_at: datetime
    authentication: Authentication
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message_id:
            # Without one there is no dedupe key, and mail is retried by design: a
            # temporary failure anywhere on the path produces the same message again.
            msg = (
                "this message has no Message-ID, so a redelivery could not be told from a "
                "new question"
            )
            raise EmailRefusedError(msg)


def normalise(message: InboundEmail) -> ChannelEvent:
    """One inbound message as the shape the gate reads, or a refusal (M10.5.6).

    Refuses before it reads anything else when the message did not authenticate. The order
    matters: parsing a `From` header on an unauthenticated message and then discarding it is
    one edit away from parsing it and keeping it, and the edit looks like a tidy-up.

    Automatic mail is refused here rather than filtered by the caller, so that every path
    into the gate gets the same answer. A caller that filters is a caller that can forget.
    """
    if not message.authentication.establishes_a_sender:
        msg = (
            f"this message's authentication is {message.authentication.value!r}. "
            f"{AN_UNAUTHENTICATED_MESSAGE_HAS_NO_SENDER}"
        )
        raise EmailRefusedError(msg)
    if is_automatic(message.headers):
        msg = (
            "this message is machine-generated, and answering it invites a reply from the "
            "machine that sent it; two systems answering each other end at a full mailbox"
        )
        raise EmailRefusedError(msg)
    return ChannelEvent(
        channel=Channel.EMAIL,
        external_id=message.message_id,
        channel_identity=sender_address(message.from_header),
        text=message.body,
        received_at=message.received_at,
    )


def reply_subject(original: str) -> str:
    """A reply's subject: the sender's own words, prefixed once.

    Their own subject is the one string we can return without disclosing anything, because
    they wrote it. Nothing else goes here. See `A_SUBJECT_OUTLIVES_THE_MESSAGE`.

    Prefixed once rather than each time. A thread answered twice would otherwise read
    `Re: Re: Re:`, which is cosmetic, and the reason to fix it is not cosmetic: a subject
    that grows without bound is a subject that gets truncated, and what survives truncation
    is the prefixes rather than the words.
    """
    subject = original.strip()
    if not subject:
        return NO_SUBJECT
    if subject.lower().startswith(REPLY_PREFIX.strip().lower()):
        return subject
    return f"{REPLY_PREFIX}{subject}"


@dataclass(frozen=True)
class Reply:
    """One outbound message, planned and not yet sent.

    **There is no `cc` field and no `bcc` field.** Reply-all is not a feature that was left
    out, it is a thing a caller must not be able to ask for: the other participants have
    their own reach and none of it was consulted. See
    `A_REPLY_IS_ADDRESSED_TO_THE_PERSON_THE_ANSWER_WAS_COMPUTED_FOR`.

    `to_identity` is the salted digest, never the address. The address is needed once, at the
    wire, and is supplied there by whoever resolved the binding, so a reply built for one
    person cannot be delivered to another. `channels.whatsapp.Send` is the same shape for the
    same reason.
    """

    to_identity: str
    subject: str
    body: str
    payload: ChannelPayload
    #: The message being answered, so a client threads the reply. Carries no content.
    in_reply_to: str = ""

    def __post_init__(self) -> None:
        if not self.subject.strip():
            msg = "a reply with no subject is filed by mail clients as if it were spam"
            raise EmailRefusedError(msg)


def reply_to(event: ChannelEvent, payload: ChannelPayload, *, subject: str) -> Reply:
    """Plan a reply to one message, addressed to the person who sent it (M10.5.6).

    Takes the event rather than an address, so the recipient is the sender of the message
    being answered and cannot be a third party a caller passed in. The only way to address
    somebody else is to answer a different message.

    The body is rendered from the payload by `cards.render_body`, which every channel shares,
    so an email and a Lark message cannot disagree about what a payload says or about
    carrying its label.
    """
    if event.channel is not Channel.EMAIL:
        msg = (
            f"this event arrived over {event.channel} and would be answered by email; the "
            "reply belongs on the surface the question came from"
        )
        raise EmailRefusedError(msg)
    return Reply(
        to_identity=identity_hash(Channel.EMAIL, event.channel_identity),
        subject=reply_subject(subject),
        body=render_body(payload),
        payload=payload,
        in_reply_to=event.external_id,
    )


def unrecognised_reply(reach: Unrecognised, event: ChannelEvent, *, subject: str) -> Reply:
    """What a sender with no binding is told, in the words `gate.ingress` already wrote.

    **This module defines no prompt of its own**, for the reason `channels.whatsapp` gives:
    `UNRECOGNISED_PROMPT` answers an unknown address, a known but unbound one, and one whose
    binding was revoked this morning with the same words, and a second prompt written here is
    a second thing to get wrong in the direction that confirms an address belongs to somebody.

    Sent at all, rather than silently dropped, because the sender authenticated: they are a
    real address at a real domain, and the honest majority of them are staff who have not
    bound the channel. A message that failed authentication never reaches here, because
    `normalise` refused it, so this cannot become a way to make the system send mail to an
    address somebody else chose.
    """
    if reach.channel is not Channel.EMAIL:
        msg = (
            f"this reach was built for {reach.channel} and would be sent over email; the "
            "prompt a person is given is per channel"
        )
        raise EmailRefusedError(msg)
    return Reply(
        to_identity=identity_hash(Channel.EMAIL, event.channel_identity),
        subject=reply_subject(subject),
        body=reach.prompt,
        payload=ChannelPayload(),
        in_reply_to=event.external_id,
    )


@dataclass(frozen=True)
class SentEmail:
    """One message this adapter delivered. What a test reads instead of a mailbox.

    `to_identity` is the digest and not the address it was sent to. A list of addresses
    beside the answers they received is the staff directory joined to what each person asked,
    which is what `gate.ingress.Binding` declines to keep.
    """

    to_identity: str
    subject: str
    body: str
    headers: dict[str, str]


@dataclass
class EmailAdapter:
    """The email surface, with the transport left out on purpose.

    No SMTP client, no credentials, no mailbox. The case worth testing is a reply addressed
    to a participant the answer was not computed for, and a module that connected to a mail
    server could only be tested for it against a live account.
    """

    sent: list[SentEmail] = field(default_factory=list)
    reachable: bool = True

    def capabilities(self) -> ChannelCapabilities:
        """What this surface may carry, declared rather than inferred.

        `INTERNAL` and not `CONFIDENTIAL`. A mail leaves the tenant the moment it is sent,
        is retained by servers on both sides, is indexed by whatever the recipient uses, and
        is forwarded to anybody in one click with no second thought and no record here.
        `channels.adapter` names email as a surface a `restricted` field must not reach.
        """
        return ChannelCapabilities(
            channel=Channel.EMAIL,
            features=EMAIL_FEATURES,
            max_classification=Classification.INTERNAL,
            can_carry_label=True,
        )

    def normalise(self, raw: object) -> ChannelEvent:
        """One inbound message, as the shape the gate reads.

        Takes an `InboundEmail` and refuses anything else rather than accepting a mapping and
        reading an authentication verdict out of it. A dict would let a caller hand over
        `{"authentication": "pass"}` assembled from the message itself, which is precisely
        the forgery this module exists to refuse. See
        `THE_VERDICT_COMES_FROM_THE_MTA_AND_NEVER_FROM_THE_MESSAGE`.
        """
        if not isinstance(raw, InboundEmail):
            msg = (
                f"this adapter normalises an InboundEmail and was handed a "
                f"{type(raw).__name__}; the authentication verdict has to come from whatever "
                f"checked it. {THE_VERDICT_COMES_FROM_THE_MTA_AND_NEVER_FROM_THE_MESSAGE}"
            )
            raise EmailRefusedError(msg)
        return normalise(raw)

    def send(self, payload: ChannelPayload, *, to: str, body: str = "", subject: str = "") -> None:
        """Put one message on the wire (M10.5.6).

        `assert_can_send` runs first and is not restated, so this adapter cannot disagree
        with any other about labels and classifications. The produced string is checked
        against the payload's label, so a caller cannot hand over a body that dropped it.

        Every message this adapter sends declares `Auto-Submitted: auto-replied`, so a
        counterpart that reads the header the way `is_automatic` does will not answer us.
        Written here rather than by the caller, because a caller that has to remember is a
        caller who forgets on the one path that loops.
        """
        assert_can_send(self.capabilities(), payload)
        rendered = body or render_body(payload)
        assert_label_survives(rendered, payload)
        self.sent.append(
            SentEmail(
                to_identity=identity_hash(Channel.EMAIL, to),
                subject=subject or NO_SUBJECT,
                body=rendered,
                headers={AUTO_SUBMITTED: OUR_AUTO_SUBMITTED},
            )
        )

    def healthy(self, now: datetime) -> bool:
        """Whether this adapter can currently deliver. See `adapter.registered`."""
        del now  # No time-based health here; the parameter is the protocol's.
        return self.reachable


def deliver(
    adapter: EmailAdapter,
    reply: Reply,
    *,
    to_address: str,
    ledger: OperationLedger,
    intent: Intent,
) -> Issued:
    """Send one planned reply, to the address it was planned for, once (M10.5.6, M17.3.1).

    The address arrives here and nowhere else. `Reply` holds a digest, so whoever resolved
    the binding supplies the address at the wire and this checks the two agree. Without it
    the address is simply a second argument, and the mistake that sends one person's answer
    to another is a variable name.

    The refusal names neither the address nor the digest. Both reach a log from here, and the
    pair of them is the directory this module declines to keep.
    """
    if identity_hash(Channel.EMAIL, to_address) != reply.to_identity:
        msg = (
            "this reply was planned for somebody else. "
            f"{A_REPLY_IS_ADDRESSED_TO_THE_PERSON_THE_ANSWER_WAS_COMPUTED_FOR}"
        )
        raise EmailRefusedError(msg)

    def send(_: Operation) -> CallOutcome:
        adapter.send(reply.payload, to=to_address, body=reply.body, subject=reply.subject)
        return CallOutcome.OK

    operation = send_operation(intent, channel=Channel.EMAIL, to=to_address)
    return issue_once(ledger, operation, send)


# ------------------------------------------------------------ the wire (M10.5.6, M10.6.1)

#: Why a message arrives in a signed envelope that states its verdict beside it.
THE_RECEIVER_STATES_ITS_VERDICT_AND_SIGNS_IT: Final = (
    "Mail reaches this install through whatever received it for the company: a mail service that "
    "checked SPF, DKIM and DMARC as it accepted the message. That receiver posts the message and "
    "its own verdict together, signed with the channel's secret over the time and the exact "
    "bytes, so the verdict is supplied by the thing that ran the check, outside the message, and "
    "a verdict nobody signed is never believed."
)

#: Why a reply's subject is fixed and threads by the message it answers.
A_REPLY_THREADS_BY_ITS_ID_AND_SAYS_NOTHING_IN_ITS_SUBJECT: Final = (
    "A reply names the message it answers by its Message-ID, so a mail client threads it under "
    "the question, and its subject is fixed words: the sender's own subject is not carried past "
    "the message it came in, and nothing the answer said can reach a subject line."
)

#: The field of the envelope holding the receiver's verdict, and the one holding the message.
ENVELOPE_AUTHENTICATION: Final = "authentication"
ENVELOPE_MESSAGE: Final = "message"

#: The record's one field: the address people write to, which a reply names as its Reply-To.
ADDRESS: Final = "address"

#: A line that opens a signature (RFC 3676) or a quoted reply, where the question stops.
_SIGNATURE: Final = re.compile(r"^-- ?$")
_QUOTED_INTRO: Final = re.compile(r"^On .{1,300} wrote:\s*$")
_MESSAGE_ID: Final = re.compile(r"^<[^<>\s]{1,480}>$")


def question_of(text: str) -> str:
    """The words a person wrote, without their signature or the message they were answering.

    Stops at the signature delimiter and at the line a client puts above a quoted reply, and
    drops quoted lines, so a reply to one of this system's own answers does not ask the
    answer back, and a binding code sent in a mail with a signature is still the code.
    """
    kept: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.rstrip()
        if _SIGNATURE.match(stripped) or _QUOTED_INTRO.match(stripped.strip()):
            break
        if stripped.lstrip().startswith(">"):
            continue
        kept.append(stripped)
    return "\n".join(kept).strip()


def reply_address(sender: str, message_id: str) -> str:
    """Where a reply goes: the sender's address, and the message answered, for threading."""
    return f"{sender} {message_id}" if message_id else sender


def split_reply_address(to: str) -> tuple[str, str]:
    """The address and the Message-ID out of `reply_address`, or `ValueError` for anything else.

    A test message names an address alone. Anything that is not one address, optionally followed
    by one Message-ID in angle brackets, is refused rather than guessed at, because this is the
    one place a recipient is decided.
    """
    parts = to.split(" ")
    address = parts[0].strip().lower()
    if not address or address.count("@") != 1 or len(parts) > 2:
        msg = "a reply goes to one address, optionally with the message it answers"
        raise ValueError(msg)
    message_id = parts[1] if len(parts) == 2 else ""
    if message_id and not _MESSAGE_ID.fullmatch(message_id):
        msg = "the message a reply answers is named by its Message-ID in angle brackets"
        raise ValueError(msg)
    return address, message_id


def _plain_text(message: EmailMessage) -> str:
    body = message.get_body(preferencelist=("plain",))
    if body is None:
        msg = "this message has no plain-text part to read"
        raise ValueError(msg)
    content = body.get_content()
    if not isinstance(content, str):
        msg = "this message's text part is not text"
        raise ValueError(msg)
    return content


@dataclass(frozen=True)
class EmailWire:
    """`brain.channels.adapter.ChannelWire` for email. Holds no secret and opens no connection.

    Receives the signed envelope a mail receiver posts (see
    `THE_RECEIVER_STATES_ITS_VERDICT_AND_SIGNS_IT`), and addresses a reply to the install's own
    relay (`RELAY_URL`), whose password `brain.channel_routes` borrows for the one send.
    """

    @property
    def channel(self) -> Channel:
        return Channel.EMAIL

    @property
    def tenant_fields(self) -> tuple[str, ...]:
        return (ADDRESS,)

    @property
    def secret_parts(self) -> tuple[str, ...]:
        """One secret, so no parts."""
        return ()

    def verify(self, arrived: Arrived, secret: str, now: datetime) -> Arrived:
        """The webhook channel's signature over the time and the exact bytes, and nothing read."""
        verify_signed(
            secret=secret,
            signature=arrived.headers.get(SIGNATURE_HEADER, ""),
            timestamp=arrived.headers.get(TIMESTAMP_HEADER, ""),
            body=arrived.body,
            now=now,
        )
        return arrived

    def handshake(self, arrived: Arrived) -> Mapping[str, str] | None:
        """A mail receiver does not check the address before it posts, so never."""
        del arrived
        return None

    def read(self, arrived: Arrived) -> Received:
        """The envelope's message as an event, refused unless its verdict establishes a sender."""
        try:
            envelope = json.loads(arrived.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("an envelope is a JSON object") from exc
        if not isinstance(envelope, dict):
            raise ValueError("an envelope is a JSON object")
        verdict, raw = envelope.get(ENVELOPE_AUTHENTICATION), envelope.get(ENVELOPE_MESSAGE)
        if not isinstance(verdict, str) or not isinstance(raw, str):
            raise ValueError("an envelope holds a verdict and a message")
        try:
            authentication = Authentication(verdict)
        except ValueError as exc:
            raise ValueError("the envelope's verdict is not one this channel knows") from exc
        parsed = message_from_string(raw, policy=default)
        if not isinstance(parsed, EmailMessage):
            raise ValueError("the envelope's message is not a mail message")
        headers = {key.lower(): str(value) for key, value in parsed.items()}
        signed = int(arrived.headers.get(TIMESTAMP_HEADER, "0"))
        inbound = InboundEmail(
            message_id=str(parsed.get("message-id", "")).strip(),
            from_header=str(parsed.get("from", "")),
            subject=str(parsed.get("subject", "")),
            body=question_of(_plain_text(parsed)),
            received_at=datetime.fromtimestamp(signed, tz=UTC),
            authentication=authentication,
            headers=headers,
        )
        try:
            event = normalise(inbound)
        except EmailRefusedError as refused:
            raise ValueError(str(refused)) from refused
        if not event.text:
            raise ValueError("this message has no words of its own to answer")
        return Received(
            event=event, reply_to=reply_address(event.channel_identity, inbound.message_id)
        )

    def request_for(
        self, *, to: str, text: str, secret: str, tenant: Mapping[str, str], now: datetime
    ) -> VendorRequest:
        """One message to one address, through the install's relay, threaded under the question.

        Its subject is fixed words and its Reply-To is the record's address; see
        `A_REPLY_THREADS_BY_ITS_ID_AND_SAYS_NOTHING_IN_ITS_SUBJECT`.
        """
        del secret, now
        address, message_id = split_reply_address(to)
        written_to = tenant.get(ADDRESS, "").strip()
        if written_to.count("@") != 1:
            msg = f"this channel's record names no {ADDRESS} for a reply to come back to"
            raise ValueError(msg)
        headers = {
            TO: address,
            SUBJECT: reply_subject(NO_SUBJECT) if message_id else NO_SUBJECT,
            REPLY_TO: written_to,
            AUTO_SUBMITTED: OUR_AUTO_SUBMITTED,
        }
        if message_id:
            headers[IN_REPLY_TO] = message_id
        return VendorRequest(url=RELAY_URL, headers=headers, body=text.encode("utf-8"))

    def judge(self, answer: VendorAnswer) -> CallOutcome:
        """The relay took it (250), may still take it (a 4xx, or no answer), or refused it.

        An answer with no status and no failure is a relay nobody set up, which sent nothing,
        so it is refused rather than left unknown: see
        `brain.channels.relay.A_RELAY_NOBODY_SET_UP_WAS_NEVER_ASKED`.
        """
        if answer.unsafe_address:
            return CallOutcome.REJECTED
        if answer.timed_out or answer.connection_failed:
            return CallOutcome.UNAVAILABLE
        if answer.status is None:
            return CallOutcome.REJECTED
        if answer.status == RELAY_ACCEPTED:
            return CallOutcome.OK
        if 400 <= answer.status < 500:
            return CallOutcome.UNAVAILABLE
        return CallOutcome.REJECTED


#: This channel's wire, found by `brain.channels.adapter.channel_wires`.
WIRE: Final = EmailWire()


# ------------------------------------------------------------ the connect steps (M10.5.6)

#: Where the steps send a person to set up the receiving side. The dashboard's front page,
#: because every account's own pages sit under an account identifier this install never holds.
CLOUDFLARE_DASHBOARD_URL: Final = "https://dash.cloudflare.com/"

#: The largest message the receiving script passes on. The install refuses a body over
#: `brain.channels.inbound.MAX_BODY_BYTES`, and the envelope's escaping adds a little to the
#: message, so the script turns away anything that would arrive over it with words a person
#: can act on rather than a refusal they never see.
LARGEST_MESSAGE_BYTES: Final = 200_000

#: Why the receiving script only passes on mail from the company's own domains.
ONLY_A_DOMAIN_THAT_REFUSES_FORGERIES_IS_PASSED: Final = (
    "The receiving service turns away mail that fails the sender's published DMARC policy, so a "
    "message from a domain whose policy is reject has had its From checked by the time the "
    "script sees it. The script therefore marks as passed only mail from the domains it is "
    "told are the company's own, and turns every other message away, so a stranger's mail "
    "never reaches this install at all."
)

#: The script the steps ask a person to paste. It reads everything that differs between
#: companies from its own variables, so it is the same text on every install.
WORKER_SCRIPT: Final = Template(
    r"""// Company Brain: passes each message this address receives on, signed.
// Variables: BRAIN_EVENTS_URL, BRAIN_SECRET (a secret) and BRAIN_DOMAINS (comma separated).
const LARGEST = $largest;

function domainOf(from) {
  if ((from.match(/</g) || []).length > 1) return "";
  const angle = from.match(/<([^<>]*)>\s*$$/);
  const address = (angle ? angle[1] : from).trim().toLowerCase();
  const parts = address.split("@");
  return parts.length === 2 ? parts[1] : "";
}

async function signature(secret, material) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(material));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default {
  async email(message, env) {
    const ours = (env.BRAIN_DOMAINS || "").toLowerCase().split(",")
      .map((d) => d.trim()).filter(Boolean);
    if (!ours.includes(domainOf(message.headers.get("from") || ""))) {
      message.setReject("This address answers mail from colleagues only.");
      return;
    }
    if (message.rawSize > LARGEST) {
      message.setReject("Please send the question again without attachments.");
      return;
    }
    const body = JSON.stringify({
      $authentication: "pass",
      $message: await new Response(message.raw).text(),
    });
    const timestamp = String(Math.floor(Date.now() / 1000));
    const answer = await fetch(env.BRAIN_EVENTS_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "$timestamp_header": timestamp,
        "$signature_header": await signature(env.BRAIN_SECRET, timestamp + "." + body),
      },
      body,
    });
    if (!answer.ok) message.setReject("The question could not be taken just now.");
  },
};
"""
).substitute(
    largest=LARGEST_MESSAGE_BYTES,
    authentication=ENVELOPE_AUTHENTICATION,
    message=ENVELOPE_MESSAGE,
    timestamp_header=TIMESTAMP_HEADER,
    signature_header=SIGNATURE_HEADER,
)


def _dashboard(
    heading: str, *, menu_mark: str, lines: tuple[SketchLine, ...] = (), button: str = ""
) -> Sketch:
    return Sketch(
        place="Cloudflare",
        heading=heading,
        menu=("Workers & Pages", "Email Routing"),
        menu_mark=menu_mark,
        lines=lines,
        button=button,
    )


#: The steps that connect email, found by `brain.channels.adapter.channel_guides`.
GUIDE: Final = keyed(
    (
        GuideStep(
            key="relay",
            title="Set up the mail relay first",
            text=(
                "Answers go out through this install's own mail relay, the one Notifications "
                "uses. Open Notifications in this console, fill in Email relay with the details "
                "your mail provider gives for sending (host, port, sender address, user name and "
                "password) and send its test message. Come back here once it arrives."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Notifications",
                lines=(
                    SketchLine(LineKind.FIELD, "Relay host", "smtp.example.net", mark=True),
                    SketchLine(LineKind.FIELD, "Sender", "brain@example.com", mark=True),
                    SketchLine(LineKind.FIELD, "Password", "********"),
                ),
                button="Send a test message",
            ),
        ),
        GuideStep(
            key="address",
            title="Give the Brain an address of its own",
            text=(
                "In Cloudflare open your domain, then Email Routing (newer dashboards list it "
                "under Email Service). Use a subdomain such as ask.example.com and never the "
                "domain your staff's mailboxes use: open Settings and add the subdomain under "
                "Subdomains, and Cloudflare adds the mail records to that subdomain only. If it "
                "asks to turn Email Routing on for the whole domain first, stop and ask whoever "
                "runs your company's mail, because that changes where the domain's mail goes. "
                "Your staff's own domain must also publish a DMARC policy of reject: that is "
                "what lets this system believe who sent a message."
            ),
            sketch=_dashboard(
                "Email Routing",
                menu_mark="Email Routing",
                lines=(
                    SketchLine(LineKind.FIELD, "Subdomains", "ask.example.com", mark=True),
                    SketchLine(LineKind.TEXT, "Your staff's domain: DMARC policy reject"),
                ),
                button="Add subdomain",
            ),
            link=CLOUDFLARE_DASHBOARD_URL,
            link_label="Open Cloudflare",
        ),
        GuideStep(
            key="worker",
            title="Create the Worker that hands mail to this install",
            text=(
                "Open Workers & Pages, create a Worker from the Hello World start and name it "
                "company-brain-mail. Replace its code with the script copied here and deploy. "
                "Then in the Worker's Settings, under Variables and Secrets, add three: "
                "BRAIN_EVENTS_URL holding this install's events address shown below, "
                "BRAIN_DOMAINS holding your staff's email domains separated by commas, and "
                "BRAIN_SECRET as a Secret holding a long random value you make up now. Keep that "
                "value for the last step, where it is pasted once more."
            ),
            sketch=_dashboard(
                "company-brain-mail",
                menu_mark="Workers & Pages",
                lines=(
                    SketchLine(
                        LineKind.FIELD, "BRAIN_EVENTS_URL", "Your events address", mark=True
                    ),
                    SketchLine(LineKind.FIELD, "BRAIN_DOMAINS", "example.com", mark=True),
                    SketchLine(LineKind.FIELD, "BRAIN_SECRET", "********", mark=True),
                ),
                button="Deploy",
            ),
            link=CLOUDFLARE_DASHBOARD_URL,
            link_label="Open Cloudflare",
            asks=(EVENTS_ADDRESS_ASK,),
            copy_text=WORKER_SCRIPT,
            copy_label="Copy the Worker script",
        ),
        GuideStep(
            key="route",
            title="Send the address's mail to the Worker",
            text=(
                "Back in Email Routing, open Routing rules and create an address on your "
                "subdomain, such as ask@ask.example.com. Choose Send to a Worker as its "
                "action, pick company-brain-mail and save. This is the address your staff "
                "write to."
            ),
            sketch=_dashboard(
                "Routing rules",
                menu_mark="Email Routing",
                lines=(
                    SketchLine(LineKind.FIELD, "Custom address", "ask@ask.example.com", mark=True),
                    SketchLine(LineKind.FIELD, "Action", "Send to a Worker", mark=True),
                    SketchLine(LineKind.FIELD, "Destination", "company-brain-mail"),
                ),
                button="Save",
            ),
            link=CLOUDFLARE_DASHBOARD_URL,
            link_label="Open Cloudflare",
        ),
        GuideStep(
            key="save",
            title="Save the address and the secret here",
            text=(
                "Type the address your staff write to in address, which every answer names as "
                "the one to reply to, paste the BRAIN_SECRET value you made up for the Worker, "
                "tick Switched on and press Save set-up. The secret is kept in the vault and "
                "never shown again. Then send a test message to yourself, and write to the "
                "address from your own mailbox: the first answer asks you to link your address "
                "to your account."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Connect Email",
                lines=(
                    SketchLine(LineKind.FIELD, ADDRESS, "ask@ask.example.com", mark=True),
                    SketchLine(LineKind.FIELD, "Secret (write only)", "********", mark=True),
                    SketchLine(LineKind.TOGGLE, "Switched on", mark=True),
                ),
                button="Save set-up",
            ),
            asks=(ADDRESS, SECRET_ASK),
        ),
    )
)
