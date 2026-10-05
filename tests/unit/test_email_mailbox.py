"""Email read from a mailbox: whose mail is believed, how it is read, and one poll end to end.

Four halves. The verdict, over messages built here with the headers a receiving provider stamps,
each refusal beside the message it believes. The reader, against `tests.fixtures.fake_imap`, a
mailbox on the loopback speaking IMAP over TLS, so what is read and what is marked is what a server
saw. The poll, through the application's own wiring to a relay that read the answer. And the steps,
which now branch on where a company's mail is.

Task ids: M10.5.6, M10.6.1
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import channel_routes
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.channels.adapter import SECRET_ASK, channel_guides, guide_problem
from brain.channels.email import (
    ADDRESS,
    CLOUDFLARE_PATH,
    DOMAINS,
    GUIDE,
    IMAP_HOST,
    IMAP_PORT,
    IMAP_USER,
    MAILBOX_PATH,
    RECEIVER,
    WIRE,
    Authentication,
)
from brain.channels.mailbox import (
    MailboxSettings,
    MailboxUnavailableError,
    open_mailbox,
    verdict_of,
)
from brain.channels.webhook import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
from brain.gate.context import Channel
from brain.gate.ingress import Unrecognised
from brain.mailbox_read import MailboxRun, read_mailbox_once
from brain.ops.channel_store import channel_secret_ref
from brain.ops.connect_steps import GuideStep, Sketch
from brain.ops.mail import MailPassword, SmtpTransport
from brain.tables.channel import RefusedBecause
from tests.fixtures.fake_imap import Mailbox, fake_imap
from tests.fixtures.fake_relay import Relay, fake_relay
from tests.fixtures.operation_ledger import MemoryLedger
from tests.unit.test_channel_pipeline import World, fresh_record
from tests.unit.test_email_channel import CountingVault
from tests.unit.test_mail import PASSWORD as RELAY_PASSWORD
from tests.unit.test_mail import configured

#: Pinned far from any wall clock, for `CLAUDE.md`'s reason: nothing below is about the present.
NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
RECEIVING = "mx.example.test"
COLLEAGUE = "person@example.test"
STRANGER = "someone@elsewhere.test"
BOX_USER = "ask@example.test"
BOX_PASSWORD = "mailbox-app-password-sentinel-0123"
SETTINGS = MailboxSettings(
    host="imap.example.test",
    port=993,
    user=BOX_USER,
    receiver=RECEIVING,
    domains=frozenset({"example.test"}),
)


def message(
    *,
    sender: str = f"Person <{COLLEAGUE}>",
    stamps: tuple[str, ...] = (
        f"{RECEIVING}; dkim=pass; dmarc=pass (p=REJECT) header.from=example.test",
    ),
    extra: Mapping[str, str] | None = None,
    body: str = "What is left on the retainer?\n",
    message_id: str = "<m-1@example.test>",
) -> EmailMessage:
    """A message as it sits in the mailbox: the receiver's stamps on top, as it prepends them."""
    built = EmailMessage()
    for stamp in stamps:
        built["Authentication-Results"] = stamp
    for name, value in (extra or {}).items():
        built[name] = value
    built["From"] = sender
    built["To"] = BOX_USER
    built["Subject"] = "Retainer"
    built["Message-ID"] = message_id
    built.set_content(body)
    return built


def raw(one: EmailMessage) -> bytes:
    return one.as_bytes(policy=default)


# ======================================================================== the verdict


def test_the_receiver_s_own_stamp_of_a_dmarc_pass_for_a_colleague_is_believed() -> None:
    """**The positive half of every refusal below.** The topmost stamp names the receiver the
    record names, and records a DMARC pass for the From domain, which is the company's.

    Delete this and a verdict that refused everything would pass every test here."""
    assert verdict_of(message(), SETTINGS) is Authentication.PASSED
    shouting = message(stamps=("MX.Example.TEST; DMARC=pass header.from=EXAMPLE.test",))
    assert verdict_of(shouting, SETTINGS) is Authentication.PASSED


@pytest.mark.parametrize(
    ("built", "verdict"),
    [
        (message(sender=f"S <{STRANGER}>"), Authentication.NOT_CHECKED),
        (message(stamps=()), Authentication.NOT_CHECKED),
        (
            message(stamps=("mx.forger.test; dmarc=pass header.from=example.test",)),
            Authentication.NOT_CHECKED,
        ),
        (
            message(
                stamps=(
                    f"{RECEIVING}; dmarc=fail header.from=example.test",
                    f"{RECEIVING}; dmarc=pass header.from=example.test",
                )
            ),
            Authentication.FAILED,
        ),
        (
            message(stamps=(f"{RECEIVING}; dmarc=pass header.from=elsewhere.test",)),
            Authentication.FAILED,
        ),
        (message(stamps=(f"{RECEIVING}; dkim=pass; spf=pass",)), Authentication.FAILED),
        (message(sender="A <a@example.test>, B <b@example.test>"), Authentication.NOT_CHECKED),
    ],
)
def test_nothing_but_the_receiver_s_topmost_stamp_for_a_colleague_is_believed(
    built: EmailMessage, verdict: Authentication
) -> None:
    """**A stranger's domain, no stamp, a stamp by anybody else on top, a pass forged below the
    receiver's fail, a pass for another domain, no DMARC result and a From naming two people.**

    Delete this and whoever writes their own Authentication-Results would be believed."""
    assert verdict_of(built, SETTINGS) is verdict


@pytest.mark.parametrize(
    ("stamped", "verdict"),
    [
        (("Internal",), Authentication.PASSED),
        (("Anonymous",), Authentication.FAILED),
        ((), Authentication.NOT_CHECKED),
        (("Internal", "Internal"), Authentication.NOT_CHECKED),
    ],
)
def test_exchange_s_own_mark_of_mail_from_inside_the_organisation_is_its_verdict(
    stamped: tuple[str, ...], verdict: Authentication
) -> None:
    """**Microsoft 365 names nobody on its stamp**, so a record naming `exchange` believes the
    mark Exchange sets on mail from inside the organisation and strips from mail from outside.

    Delete this and a company on Microsoft 365 could not read a mailbox, or one mark would be
    believed however many there were."""
    exchange = MailboxSettings(
        host=SETTINGS.host, port=993, user=BOX_USER, receiver="exchange", domains=SETTINGS.domains
    )
    built = message(stamps=())
    for one in stamped:
        built["X-MS-Exchange-Organization-AuthAs"] = one
    assert verdict_of(built, exchange) is verdict


@pytest.mark.parametrize(
    ("tenant", "outcome"),
    [
        ({ADDRESS: BOX_USER}, None),
        ({IMAP_HOST: "not a host", IMAP_USER: "u", RECEIVER: "r", DOMAINS: "d"}, ValueError),
        (
            {
                IMAP_HOST: "imap.example.test",
                IMAP_PORT: "0",
                IMAP_USER: "u",
                RECEIVER: "r",
                DOMAINS: "d",
            },
            ValueError,
        ),
        ({IMAP_HOST: "imap.example.test", RECEIVER: "r", DOMAINS: "d"}, ValueError),
        ({IMAP_HOST: "imap.example.test", IMAP_USER: "u", DOMAINS: "d"}, ValueError),
        (
            {IMAP_HOST: "imap.example.test", IMAP_USER: "u", RECEIVER: "r", DOMAINS: " , "},
            ValueError,
        ),
    ],
)
def test_a_record_reads_a_mailbox_only_when_it_names_one_whole(
    tenant: dict[str, str], outcome: type[Exception] | None
) -> None:
    """Delete this and a record half set up would be read with a guessed port or no receiver."""
    if outcome is None:
        assert MailboxSettings.of(tenant) is None
    else:
        with pytest.raises(outcome):
            MailboxSettings.of(tenant)
    whole = MailboxSettings.of(
        {
            IMAP_HOST: "IMAP.example.test",
            IMAP_USER: BOX_USER,
            RECEIVER: "MX.example.test",
            DOMAINS: "a.test, B.test",
        }
    )
    assert whole == MailboxSettings(
        host="imap.example.test",
        port=993,
        user=BOX_USER,
        receiver="mx.example.test",
        domains=frozenset({"a.test", "b.test"}),
    )


# ======================================================================== the reader


def settings_for(box: Mailbox) -> MailboxSettings:
    return MailboxSettings(
        host="127.0.0.1", port=box.port, user=box.user, receiver=RECEIVING, domains=SETTINGS.domains
    )


def test_the_reader_takes_unseen_mail_marks_only_what_it_is_told_and_deletes_nothing(
    tmp_path: Path,
) -> None:
    """**What a mailbox saw**, from `tests.fixtures.fake_imap`: a TLS sign-in with the password,
    the unseen messages read whole and left unseen by reading, the handled one marked seen, and no
    command that deletes, moves or expunges.

    Delete this and every other test of the mailbox is a test of a reader nobody showed a server."""
    with fake_imap(tmp_path, user=BOX_USER, password=BOX_PASSWORD) as box:
        first = box.add(raw(message()))
        box.add(raw(message(message_id="<m-2@example.test>")), seen=True)
        third = box.add(raw(message(message_id="<m-3@example.test>")))
        reader = open_mailbox(settings_for(box), BOX_PASSWORD, context=box.trusted)
        found = reader.unseen(10)
        assert [ident for ident, _ in found] == [str(first), str(third)]
        assert found[0][1] == raw(message())
        assert box.seen() == [2]
        reader.mark_handled([str(first)])
        reader.close()
        reader.close()
    assert box.seen() == [1, 2]
    forbidden = ("EXPUNGE", "DELETE", "MOVE", "COPY", "\\DELETED")
    assert not [one for one in box.commands if any(word in one.upper() for word in forbidden)]


def test_the_reader_takes_at_most_what_one_poll_handles(tmp_path: Path) -> None:
    """Delete this and a mailbox full of old mail would be read in one poll."""
    with fake_imap(tmp_path, user=BOX_USER, password=BOX_PASSWORD) as box:
        for n in range(5):
            box.add(raw(message(message_id=f"<m-{n}@example.test>")))
        reader = open_mailbox(settings_for(box), BOX_PASSWORD, context=box.trusted)
        assert [ident for ident, _ in reader.unseen(2)] == ["1", "2"]
        reader.close()


def test_a_wrong_password_or_an_unknown_certificate_is_a_mailbox_that_cannot_be_read(
    tmp_path: Path,
) -> None:
    """Delete this and a refused sign-in would raise whatever imaplib raised, or TLS be skipped."""
    with fake_imap(tmp_path, user=BOX_USER, password=BOX_PASSWORD) as box:
        with pytest.raises(MailboxUnavailableError, match="refused"):
            open_mailbox(settings_for(box), "not-it", context=box.trusted)
        with pytest.raises(MailboxUnavailableError, match="TLS"):
            open_mailbox(settings_for(box), BOX_PASSWORD)


# ======================================================================== one poll


@dataclass
class Place:
    world: World = field(default_factory=World)
    relay: Relay | None = None
    box: Mailbox | None = None


@pytest.fixture
def place(tmp_path: Path) -> Iterator[Place]:
    here = Place()
    (tmp_path / "imap").mkdir()
    (tmp_path / "smtp").mkdir()
    with (
        fake_imap(tmp_path / "imap", user=BOX_USER, password=BOX_PASSWORD) as box,
        fake_relay(tmp_path / "smtp", username="relay_user", password=RELAY_PASSWORD) as relay,
    ):
        here.box, here.relay = box, relay
        here.world.secrets.slots[channel_secret_ref(Channel.EMAIL).path] = BOX_PASSWORD
        here.world.records.kept[Channel.EMAIL] = fresh_record(
            Channel.EMAIL,
            tenant={
                ADDRESS: BOX_USER,
                IMAP_HOST: "127.0.0.1",
                IMAP_PORT: str(box.port),
                IMAP_USER: BOX_USER,
                RECEIVER: RECEIVING,
                DOMAINS: "example.test",
            },
        )
        yield here


def application(place: Place) -> FastAPI:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(channel_routes.router)
    relay = place.relay
    assert relay is not None
    world = place.world
    app.state.channel_records = world.records
    app.state.channel_deliveries = world.deliveries
    app.state.channel_claims = world.claims
    app.state.channel_secrets = world.secrets
    app.state.channel_transport = world.transport
    app.state.operation_ledger = MemoryLedger()
    app.state.mail_settings = configured(relay)
    app.state.mail_password = MailPassword(CountingVault())
    app.state.mail_transport = lambda settings, password: SmtpTransport(
        settings, password, context=relay.trusted
    )
    return app


def poll(place: Place, app: FastAPI) -> MailboxRun:
    box = place.box
    assert box is not None

    def opener(settings: MailboxSettings, password: str) -> Any:
        return open_mailbox(settings, password, context=box.trusted)

    return asyncio.run(read_mailbox_once(app, now=NOW, opener=opener))


def test_a_colleague_s_mail_is_answered_through_the_relay_and_every_message_marked(
    place: Place,
) -> None:
    """**End to end, from the mailbox to a relay that read the answer.** A colleague bound to
    nobody is told how to link their address, through the relay, threaded under their message;
    a stranger's mail and a forged stamp are not answered; all three are marked read and none
    deleted. A second poll finds nothing.

    Delete this and every other test here is a test of a piece nobody showed the poll."""
    box, relay = place.box, place.relay
    assert box is not None and relay is not None
    box.add(raw(message()))
    box.add(raw(message(sender=f"S <{STRANGER}>", message_id="<m-2@elsewhere.test>")))
    forged = message(
        stamps=("mx.forger.test; dmarc=pass header.from=example.test",),
        message_id="<m-3@example.test>",
    )
    box.add(raw(forged))
    app = application(place)
    with TestClient(app):
        ran = poll(place, app)
        again = poll(place, app)
    assert (ran.state, ran.read, ran.answered, ran.refused) == ("read", 3, 1, 2)
    assert (again.state, again.read) == ("read", 0)
    assert box.seen() == [1, 2, 3]
    (sent,) = relay.delivered
    assert sent.rcpt_to == [COLLEAGUE]
    parsed = message_from_bytes(sent.data, policy=default)
    assert (parsed["In-Reply-To"], parsed["Reply-To"]) == ("<m-1@example.test>", BOX_USER)
    assert parsed.get_content().rstrip("\r\n") == Unrecognised(channel=Channel.EMAIL).prompt
    assert place.world.deliveries.seen()[:1] == [("inbound", "accepted", None)]
    assert place.world.transport.sent == []


def test_a_message_read_again_after_a_crash_is_answered_once(place: Place) -> None:
    """**The claim is what answers once**, not the mark. A message the last poll answered and
    did not get to mark is read again, claimed as seen before, and not answered twice.

    Delete this and a crash between answering and marking would answer somebody twice."""
    box, relay = place.box, place.relay
    assert box is not None and relay is not None
    box.add(raw(message()))
    app = application(place)
    with TestClient(app):
        poll(place, app)
        box.messages[0].flags.clear()
        again = poll(place, app)
    assert (again.read, again.answered) == (1, 0)
    assert len(relay.delivered) == 1
    assert box.seen() == [1]


@pytest.mark.parametrize("state", ["off", "cloudflare", "unready", "unavailable"])
def test_a_record_that_reads_no_whole_mailbox_is_not_read(place: Place, state: str) -> None:
    """Switched off, set up for Cloudflare, half set up, or a mailbox that refuses: nothing read,
    nothing sent. Delete this and the poll could sign in to a mailbox on a channel switched off."""
    box = place.box
    assert box is not None
    box.add(raw(message()))
    record = place.world.records.kept[Channel.EMAIL]
    match state:
        case "off":
            place.world.records.kept[Channel.EMAIL] = fresh_record(
                Channel.EMAIL, enabled=False, tenant=dict(record.tenant)
            )
        case "cloudflare":
            place.world.records.kept[Channel.EMAIL] = fresh_record(
                Channel.EMAIL, tenant={ADDRESS: BOX_USER}
            )
        case "unready":
            place.world.records.kept[Channel.EMAIL] = fresh_record(
                Channel.EMAIL, tenant={**record.tenant, RECEIVER: ""}
            )
        case _:
            place.world.secrets.slots[channel_secret_ref(Channel.EMAIL).path] = "not-it"
    app = application(place)
    with TestClient(app):
        ran = poll(place, app)
    expected = {"cloudflare": "off"}.get(state, state)
    assert ran.state == expected
    assert box.seen() == []
    assert place.relay is not None and place.relay.delivered == []


def test_the_events_address_takes_no_post_while_the_record_reads_a_mailbox(place: Place) -> None:
    """**The mailbox's password must never sign anything.** On a record reading a mailbox, an
    envelope signed with the channel's secret, which is that password, is refused unread.

    Delete this and whoever held the mailbox's password could write mail from anybody."""
    body = json.dumps({"authentication": "pass", "message": raw(message()).decode()}).encode()
    stamp = str(int(time.time()))
    app = application(place)
    with TestClient(app) as c:
        answered = c.post(
            f"{API_PREFIX}/channels/email/events",
            content=body,
            headers={TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(BOX_PASSWORD, stamp, body)},
        )
    assert answered.status_code == channel_routes._REFUSED_STATUS[RefusedBecause.BAD_SIGNATURE][0]
    assert place.relay is not None and place.relay.delivered == []


# ======================================================================== the steps


def test_the_steps_offer_a_mailbox_first_and_each_path_ends_in_its_own_form() -> None:
    """**A mailbox is the first choice, and Cloudflare the alternative.** Each path holds one
    form: the mailbox's asks for everything a poll needs, Cloudflare's for the address alone.

    Delete this and the flow could lead a company without Cloudflare nowhere."""
    steps = channel_guides()[Channel.EMAIL]
    assert steps == GUIDE
    (where,) = [one for one in steps if one.choices]
    assert [key for key, _ in where.choices] == [MAILBOX_PATH, CLOUDFLARE_PATH]
    forms = {one.path: one.asks for one in steps if one.asks and one.asks[-1] == SECRET_ASK}
    assert forms == {
        MAILBOX_PATH: (ADDRESS, IMAP_HOST, IMAP_PORT, IMAP_USER, RECEIVER, DOMAINS, SECRET_ASK),
        CLOUDFLARE_PATH: (ADDRESS, SECRET_ASK),
    }


def _step(key: str, **changes: Any) -> GuideStep:
    return GuideStep(
        key=key, title=key, text="Do it.", sketch=Sketch(place="x", heading="x"), **changes
    )


@pytest.mark.parametrize(
    ("steps", "problem"),
    [
        ((_step("a", path="nowhere"),), "no step offers"),
        (
            (
                _step("w", choices=(("p", "P"), ("q", "Q"))),
                _step("f", asks=(ADDRESS, SECRET_ASK), path="p"),
            ),
            "on path 'q'",
        ),
        (
            (
                _step("w", choices=(("p", "P"), ("q", "Q"))),
                _step("f", asks=(ADDRESS, SECRET_ASK), path="p"),
                _step("g", asks=(ADDRESS, SECRET_ASK), path="q"),
            ),
            "of the record's",
        ),
        ((_step("f", asks=(ADDRESS, SECRET_ASK)),), "of the record's"),
    ],
)
def test_a_branching_guide_without_a_form_on_every_path_or_leaving_a_field_unasked_is_refused(
    steps: tuple[GuideStep, ...], problem: str
) -> None:
    """Delete this and a path could end with nothing to save, or a field no path asks for."""
    assert problem in guide_problem(steps, WIRE)
    assert guide_problem(GUIDE, WIRE) == ""


def test_a_step_offering_a_choice_asks_nothing_and_offers_distinct_paths() -> None:
    """Delete this and a choice could also be a form, or offer one path twice."""
    with pytest.raises(ValueError, match="choice"):
        _step("w", choices=(("p", "P"),), asks=(ADDRESS,))
    with pytest.raises(ValueError, match="repeated"):
        _step("w", choices=(("p", "P"), ("p", "Q")))
