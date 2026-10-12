"""The channel delivery acceptance check: what it plays to each wire, and the check run on
PostgreSQL, whole and broken.

The pure half holds the fixtures to the wires they are written for: every channel the product has a
wire for has one fixture, each wire reads the answers its fixture calls accepted, refused and
unknown the way the fixture says, and each fixture's request builds. The database half runs the
check as the worker runs it against a database at head, where it passes and leaves nothing, and
then breaks the product once for every property the check holds, so each of its sentences is shown
to be the one a broken product produces.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M10.6.1
"""

from __future__ import annotations

import asyncio
import io
import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.ops import acceptance_checks_channel_delivery as module
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_channel_delivery"
CHECK = "each_channel_delivers_and_a_refusal_is_never_recorded_as_sent"


def the_check() -> Check:
    [one] = [one for one in registered() if one.run.__module__ == MODULE]
    return one


# ------------------------------------------------------------------------ the pure half
def test_the_module_registers_one_check_and_it_names_the_delivery_leaf() -> None:
    """One check, one leaf, a name and a sentence the Install page accepts and a place in the page
    inside the range assigned to this module. Delete this and the leaf can lose its check, or the
    check can be renamed past what the results table keeps, with the page showing one row fewer."""
    one = the_check()
    assert (one.name, one.leaves) == (CHECK, ("M10.6.1",))
    assert checks_in(MODULE) == [CHECK]
    assert re.fullmatch(r"[a-z][a-z0-9_]{2,63}", one.name)
    assert len(one.sentence) <= 400
    assert 720 <= module.CHECK_ORDER <= 739


def test_every_reason_the_check_ends_with_fits_the_result() -> None:
    """Each sentence is stored whole, with nothing cut off. Delete this and why the check failed
    reads as a sentence that stops in the middle on the Install page."""
    reasons = {
        name: value
        for name, value in vars(module).items()
        if name.isupper() and isinstance(value, str) and name.startswith(("THE_", "A_", "AN_"))
    }
    assert len(reasons) >= 12
    for name, value in reasons.items():
        assert len(value) <= REASON_CHARS, name
        assert len(value) <= 240, name


def test_a_channel_with_a_wire_has_exactly_one_fixture() -> None:
    """The set of channels fixtured is the set the product has wires for, each once, and every
    secret is made afresh. Delete this and a channel can be added with nothing here sending on it,
    and the check passes over six of seven."""
    from brain.channels.adapter import channel_wires

    first, second = module.vendors(), module.vendors()
    assert [one.channel for one in first] == [one.channel for one in second]
    assert {one.channel for one in first} == set(channel_wires())
    assert len(first) == len({one.channel for one in first}) == len(channel_wires())
    assert all(a.secret != b.secret for a, b in zip(first, second, strict=True))


def test_each_wire_reads_the_answers_its_fixture_plays_as_the_fixture_says() -> None:
    """**The fixture's answers are written from the vendors' documents, so they are held to the
    wires and not to `deliver`.** Accepted is judged delivered, a refusal is rejected or a quota
    and an address this side refuses is rejected, and silence and a fault are unavailable, so the
    database half is playing the shapes it says it plays. Delete this and the check can pass over
    an answer its wire reads some other way, which proves the wrong sentence."""
    from brain.channels.adapter import channel_wires
    from brain.connectors.throttle import CallOutcome

    wires = channel_wires()
    for vendor in module.vendors():
        wire = wires[vendor.channel]
        assert wire.judge(vendor.accepted) is CallOutcome.OK, vendor.channel
        for answer, _ in vendor.refused:
            assert wire.judge(answer) in (CallOutcome.REJECTED, CallOutcome.QUOTA), (
                vendor.channel,
                answer.status,
            )
        for answer in vendor.unknown:
            assert wire.judge(answer) is CallOutcome.UNAVAILABLE, (vendor.channel, answer.status)


def test_each_fixture_builds_the_request_its_wire_sends_with_the_secret_where_it_is_put() -> None:
    """The wire's own `request_for` over each fixture's record, address and secret, carrying the
    planned words and the secret as the fixture's locator says, and the email wire's request holding
    none of its secret, the one wire for which that is the property. Delete this and a fixture the
    wire refuses (a Slack id of the wrong form, a token BotFather would not issue) turns the
    database half red for a reason in the fixture, or its locator passes on any request."""
    from brain.channels.adapter import channel_wires
    from brain.gate.context import Channel

    wires = channel_wires()
    for vendor in module.vendors():
        request = wires[vendor.channel].request_for(
            to=vendor.to,
            text="Planned words",
            secret=vendor.secret,
            tenant=vendor.tenant,
            now=datetime(2019, 3, 4, 9, 0, tzinfo=UTC),
        )
        assert b"Planned words" in request.body, vendor.channel
        if vendor.channel is Channel.EMAIL:
            assert vendor.reached is None
            assert not module._holds_any(request, vendor.parts)
        else:
            assert vendor.reached is not None and vendor.reached(request), vendor.channel
            # The locator is not satisfied by a request that lacks the secret.
            stripped = replace(request, headers={}, url="https://x.invalid/", exchange=None)
            assert not vendor.reached(stripped), vendor.channel


def test_a_request_is_searched_for_a_secret_in_its_address_headers_body_and_exchange() -> None:
    """The four places a vendor's request can carry a credential. Delete this and a wire that
    moved its secret into a header, an address or a token exchange passes the email wire's check
    that nothing was sent."""
    from brain.channels.adapter import TokenExchange, VendorRequest

    plain = VendorRequest(url="https://a.invalid/", headers={"h": "v"}, body=b"b")
    assert not module._holds_any(plain, ("secret-value",))
    assert module._holds_any(
        replace(plain, url="https://a.invalid/secret-value"), ("secret-value",)
    )
    assert module._holds_any(replace(plain, headers={"h": "secret-value"}), ("secret-value",))
    assert module._holds_any(replace(plain, body=b"x secret-value"), ("secret-value",))
    assert module._holds_any(
        replace(plain, exchange=TokenExchange(url="https://b.invalid/", body=b"secret-value")),
        ("secret-value",),
    )


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_channel_delivery") as url:
        yield url


#: Every table the check writes to: nothing may be left in any afterwards.
WRITTEN = ("ops.channel", "ops.channel_delivery", "obs.audit_entry", "gate.channel_event")


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


def run_check(url: str) -> tuple[tuple[str, str], str]:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    stream = io.StringIO()

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await acceptance_run.run_suite(
                engine, [the_check()], settings=settings, stream=stream
            )
        finally:
            await engine.dispose()

    [result] = asyncio.run(run())
    return (result.outcome, result.reason), stream.getvalue()


@pytest.mark.needs_db
def test_on_a_real_database_the_check_passes_and_leaves_every_table_as_it_was(
    install: str,
) -> None:
    """**The check as the worker runs it, on PostgreSQL at head.** It passes over all seven wires
    and the channel record, the delivery rows and the ledger hold afterwards what they held before,
    the audit chain included. Delete this and a check that commits, or that cannot pass on a real
    schema (a record the table refuses, a row the application role may not read), reaches the
    owner's server first."""
    before = _counts(install)
    result, log = run_check(install)
    assert result == (PASSED, ""), log
    assert _counts(install) == before


@pytest.mark.needs_db
def test_the_check_passes_where_a_channel_is_already_connected_and_has_deliveries(
    install: str,
) -> None:
    """**An install that has connected a channel has its record, its deliveries and its secret slot
    already.** The check saves over that record inside its own transaction and reads only the rows
    it wrote, so older deliveries on the same channel change nothing. Delete this and the check
    goes red on the install that matters, the one where somebody has used Slack, for a reason that
    is its history and not the product."""
    from brain.gate.context import Channel
    from brain.ops.channel_store import DeliveryEntry, StoredDeliveries
    from brain.tables.channel import DeliveryOutcome, Direction
    from tests.unit.test_budget_stop_store import _as_app

    async def used(sessions: Any) -> None:
        store = StoredDeliveries(sessions)
        for _ in range(3):
            await store.record(
                DeliveryEntry(
                    channel=Channel.SLACK,
                    direction=Direction.OUTBOUND,
                    outcome=DeliveryOutcome.SENT,
                    vendor_status=200,
                )
            )

    with at_head("brain_acceptance_channel_delivery_used") as url:
        _as_app(url, used)
        before = _counts(url)
        result, log = run_check(url)
        assert result == (PASSED, ""), log
        assert _counts(url) == before


# ------------------------------------------------------------------ the product, broken
def _outbound() -> Any:
    import brain.channels.outbound

    return brain.channels.outbound


def _every_answer_is_read_as_sent(m: pytest.MonkeyPatch) -> None:
    """A wire whose judge says delivered whatever the vendor answered, as Slack's would if it read
    only the status and never the body."""
    from brain.channels.slack import SlackWire
    from brain.connectors.throttle import CallOutcome

    m.setattr(SlackWire, "judge", lambda self, answer: CallOutcome.OK)


def _a_refusal_is_recorded_as_sent(m: pytest.MonkeyPatch) -> None:
    """`deliver` recording the vendor's refusal as a delivery."""
    from brain.channels.outbound import Delivered
    from brain.tables.channel import DeliveryOutcome

    m.setattr(
        _outbound(),
        "_from_answer",
        lambda answer, judged: Delivered(outcome=DeliveryOutcome.SENT, vendor_status=answer.status),
    )


def _silence_is_recorded_as_refused(m: pytest.MonkeyPatch) -> None:
    """A request that may have been delivered written down as a refusal."""
    from brain.channels.outbound import Delivered
    from brain.connectors.throttle import CallOutcome
    from brain.tables.channel import DeliveryOutcome, RefusedBecause

    real = _outbound()._from_answer

    def judged(answer: Any, outcome: CallOutcome) -> Delivered:
        if outcome is CallOutcome.UNAVAILABLE:
            return Delivered(
                outcome=DeliveryOutcome.REFUSED,
                reason=RefusedBecause.VENDOR_REFUSED,
                vendor_status=answer.status,
            )
        return real(answer, outcome)  # type: ignore[no-any-return]

    m.setattr(_outbound(), "_from_answer", judged)


def _an_accepted_delivery_is_recorded_as_not_known(m: pytest.MonkeyPatch) -> None:
    from brain.channels.outbound import Delivered
    from brain.connectors.throttle import CallOutcome
    from brain.tables.channel import DeliveryOutcome, RefusedBecause

    real = _outbound()._from_answer

    def judged(answer: Any, outcome: CallOutcome) -> Delivered:
        if outcome is CallOutcome.OK:
            return Delivered(
                outcome=DeliveryOutcome.UNKNOWN,
                reason=RefusedBecause.VENDOR_UNAVAILABLE,
                vendor_status=answer.status,
            )
        return real(answer, outcome)  # type: ignore[no-any-return]

    m.setattr(_outbound(), "_from_answer", judged)


def _nothing_is_written_to_the_delivery_record(m: pytest.MonkeyPatch) -> None:
    from brain.ops.channel_store import StoredDeliveries

    async def nothing(self: object, entry: object) -> None:
        return None

    m.setattr(StoredDeliveries, "record", nothing)


def _the_slack_token_is_left_out_of_the_request(m: pytest.MonkeyPatch) -> None:
    from brain.channels.slack import SlackWire

    real = SlackWire.request_for

    def request_for(self: SlackWire, **kwargs: Any) -> Any:
        return replace(real(self, **kwargs), headers={})

    m.setattr(SlackWire, "request_for", request_for)


def _the_planned_words_are_dropped_from_the_request(m: pytest.MonkeyPatch) -> None:
    from brain.channels.slack import SlackWire

    real = SlackWire.request_for

    def request_for(self: SlackWire, **kwargs: Any) -> Any:
        return replace(real(self, **kwargs), body=b"{}")

    m.setattr(SlackWire, "request_for", request_for)


def _the_mail_wire_sends_its_secret(m: pytest.MonkeyPatch) -> None:
    from brain.channels.email import EmailWire

    real = EmailWire.request_for

    def request_for(self: EmailWire, **kwargs: Any) -> Any:
        built = real(self, **kwargs)
        return replace(built, headers={**built.headers, "X-Key": kwargs["secret"]})

    m.setattr(EmailWire, "request_for", request_for)


def _the_secret_is_stored_with_the_record(m: pytest.MonkeyPatch) -> None:
    """A fixture whose record carries a secret value in an extra field the wire never reads: the
    record reads back as saved, so only a look at the stored rows can find it."""
    real = module.vendors

    def vendors() -> tuple[Any, ...]:
        return tuple(replace(one, tenant={**one.tenant, "note": one.parts[0]}) for one in real())

    m.setattr(module, "vendors", vendors)


def _the_vault_is_asked_for_a_second_slot(m: pytest.MonkeyPatch) -> None:
    real = _outbound().deliver

    class Asking:
        def __init__(self, inner: Any) -> None:
            self.inner = inner

        def read(self, ref: object) -> str | None:
            self.inner.read("somewhere-else")
            return self.inner.read(ref)  # type: ignore[no-any-return]

    async def deliver(*args: Any, **kwargs: Any) -> Any:
        return await real(*args, **{**kwargs, "secrets": Asking(kwargs["secrets"])})

    m.setattr(module, "deliver", deliver)


def _the_vendor_is_asked_twice(m: pytest.MonkeyPatch) -> None:
    real = _outbound().deliver

    class Twice:
        def __init__(self, inner: Any) -> None:
            self.inner = inner

        def send(self, request: Any) -> Any:
            self.inner.send(request)
            return self.inner.send(request)

        def read(self, request: Any) -> Any:
            return self.inner.read(request)

    async def deliver(*args: Any, **kwargs: Any) -> Any:
        return await real(*args, **{**kwargs, "transport": Twice(kwargs["transport"])})

    m.setattr(module, "deliver", deliver)


def _the_record_loses_its_address(m: pytest.MonkeyPatch) -> None:
    from brain.ops.channel_store import StoredChannels

    real = StoredChannels.save

    async def save(self: StoredChannels, channel: Any, **kwargs: Any) -> Any:
        return await real(self, channel, **{**kwargs, "tenant": {}})

    m.setattr(StoredChannels, "save", save)


def _a_channel_has_no_fixture(m: pytest.MonkeyPatch) -> None:
    real = module.vendors
    m.setattr(module, "vendors", lambda: real()[:-1])


#: One break of the product per property the check holds, and the sentence the check ends with.
BREAKS: tuple[tuple[str, Callable[[pytest.MonkeyPatch], None], str, str], ...] = (
    (
        "a wire that reads every answer as delivered",
        _every_answer_is_read_as_sent,
        module.A_REFUSED_DELIVERY_WAS_NOT_RECORDED_REFUSED,
        "slack",
    ),
    (
        "a refusal recorded as a delivery",
        _a_refusal_is_recorded_as_sent,
        module.A_REFUSED_DELIVERY_WAS_NOT_RECORDED_REFUSED,
        "webhook",
    ),
    (
        "silence recorded as a refusal",
        _silence_is_recorded_as_refused,
        module.AN_UNANSWERED_DELIVERY_WAS_NOT_RECORDED_UNKNOWN,
        "webhook",
    ),
    (
        "an accepted delivery recorded as not known",
        _an_accepted_delivery_is_recorded_as_not_known,
        module.AN_ACCEPTED_DELIVERY_WAS_NOT_RECORDED_SENT,
        "webhook",
    ),
    (
        "nothing written to the delivery record",
        _nothing_is_written_to_the_delivery_record,
        module.THE_DELIVERY_WAS_NOT_RECORDED_AS_IT_CAME_TO,
        "webhook",
    ),
    (
        "the credential left out of the request",
        _the_slack_token_is_left_out_of_the_request,
        module.THE_CREDENTIAL_DID_NOT_REACH_THE_REQUEST,
        "slack",
    ),
    (
        "the planned words dropped from the request",
        _the_planned_words_are_dropped_from_the_request,
        module.THE_PLANNED_TEXT_WAS_NOT_IN_THE_REQUEST,
        "slack",
    ),
    (
        "the mail wire sending its secret",
        _the_mail_wire_sends_its_secret,
        module.THE_CREDENTIAL_REACHED_A_REQUEST_THAT_NEVER_CARRIES_IT,
        "email",
    ),
    (
        "a secret stored with the record",
        _the_secret_is_stored_with_the_record,
        module.THE_CREDENTIAL_WAS_KEPT_WITH_THE_RECORD,
        "webhook",
    ),
    (
        "the vault asked for a second slot",
        _the_vault_is_asked_for_a_second_slot,
        module.THE_VAULT_WAS_ASKED_FOR_ANOTHER_SLOT,
        "webhook",
    ),
    (
        "the vendor asked twice",
        _the_vendor_is_asked_twice,
        module.THE_TRANSPORT_WAS_NOT_ASKED_ONCE,
        "webhook",
    ),
    (
        "a record that loses its address",
        _the_record_loses_its_address,
        module.THE_ENABLED_RECORD_WAS_NOT_KEPT,
        "webhook",
    ),
    (
        "a channel with a wire and no fixture",
        _a_channel_has_no_fixture,
        module.A_CHANNEL_WITH_NO_FIXTURE_IS_NOT_PROVED,
        "",
    ),
)


def test_every_property_the_check_holds_has_one_break_of_the_product() -> None:
    """Held to the check's own reasons, so a sentence added to the module without a break here
    fails. Delete this and the check can gain a refusal that nothing ever shows it making."""
    reasons = {
        value
        for name, value in vars(module).items()
        if name.isupper()
        and isinstance(value, str)
        and name.startswith(("THE_", "A_", "AN_"))
        and name != "THE_LOG_NAMES_THE_CHANNEL_AND_THE_RESULT_NAMES_THE_PROPERTY"
    }
    assert {reason for _, _, reason, _ in BREAKS} == reasons


@pytest.mark.needs_db
def test_the_check_fails_with_its_own_sentence_for_each_way_the_product_is_broken(
    install: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """**A check tested only by passing is satisfied by a check that asserts nothing.** Each break
    replaces a product function the sentence rests on (a judge that reads every answer as sent,
    a send that records a refusal as sent, a request without the credential or the words, a secret
    stored with the record, a send that reaches the vendor twice) and the check fails with the
    sentence written for exactly that, names the channel on the worker's stream, and leaves the
    database as it found it. Delete this and the delivery leaf can close on an install where a
    vendor's refusal is recorded as a delivery."""
    before = _counts(install)
    found: list[tuple[str, tuple[str, str]]] = []
    said: list[str] = []
    for label, breaking, _, _ in BREAKS:
        with monkeypatch.context() as m:
            breaking(m)
            result, _ = run_check(install)
        found.append((label, result))
        said.append(capsys.readouterr().err)
    assert found == [(label, (FAILED, reason)) for label, _, reason, _ in BREAKS]
    for (label, _, _, channel), err in zip(BREAKS, said, strict=True):
        assert (f"channel delivery, {channel}" in err) is bool(channel), (label, err)
    assert _counts(install) == before
