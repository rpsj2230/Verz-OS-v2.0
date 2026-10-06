"""The channel acceptance checks: what they post, and the seven run on PostgreSQL, whole and broken.

The pure half holds what the checks post to what the install reads: the WhatsApp bytes a check
posts are one message the install's own wire opens and verifies, the delivery store stamps each
row with the clock, and the suite names the seven checks with their leaves. The database half runs
them as the worker runs them, against PostgreSQL at head: every one passes and every table they
write to holds afterwards what it held before. Then the product is broken once per check, in the
way that check exists to catch, and the check fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M10.1.2, M10.1.3, M10.1.4, M10.3.1, M10.3.2, M10.3.4, M10.5.7, M10.6.2
Task ids: M27.13.1
"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from brain.ops.acceptance_checks_channel_framework import a_number, whatsapp_message
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_channel_framework"

#: The seven checks and the leaves each proves, in the order the module declares them.
LEAVES = {
    "every_adapter_serves_its_declared_capabilities_and_plans_by_them": ("M10.1.2",),
    "a_reply_above_a_channels_ceiling_is_refused_and_points_to_ask": ("M10.1.3",),
    "each_adapter_is_listed_and_its_health_follows_its_deliveries": ("M10.1.4",),
    "a_code_minted_in_an_open_sign_in_binds_one_chat_account_once": (
        "M10.3.1",
        "M10.3.2",
        "M27.13.1",
    ),
    "a_new_device_replaces_the_old_and_unbinding_is_recorded": ("M10.3.4",),
    "an_api_key_is_answered_until_it_is_revoked": ("M10.5.7",),
    "a_whatsapp_webhook_is_accepted_only_under_its_app_secret": ("M10.6.2",),
}

#: What the database half hands the run: an issuer the gate is built for, and an address of the
#: install's own for the sentence pointing to Ask.
INSTALL = {
    "INSTALL_OIDC_ISSUER": "https://id.example.invalid/realms/brain",
    "INSTALL_OIDC_REDIRECT_URIS": "https://brain.example.invalid/callback",
}

#: Every table a channel check writes to, and nothing may be left in afterwards.
WRITTEN_BY_CHANNEL_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "auth.principal_identity",
    "auth.binding_code",
    "auth.session",
    "auth.service_account",
    "auth.api_key",
    "gate.capability_grant",
    "gate.grants_version",
    "gate.policy_epoch",
    "obs.audit_entry",
    "ops.channel",
    "ops.channel_delivery",
    "ops.credential_write",
    "gate.channel_event",
    "know.classified_table",
    "know.classified_row",
)


def channel_checks() -> list[Check]:
    return [one for one in registered() if one.run.__module__ == MODULE]


# ------------------------------------------------------------------------ the pure half
def test_the_seven_channel_checks_are_in_the_suite_the_worker_runs_with_their_leaves() -> None:
    """Found among the suite's modules, which is what `registered` imports and the worker runs,
    each with the leaves its result closes. M10.7.4 is proved by none of these: its sentence ends
    in an approval card, which `brain.ops.acceptance_checks_cards` proves. Delete this and a check
    can drop out of the suite, or claim a leaf it does not prove, with the Install page simply
    showing a row fewer or a wrong one."""
    assert MODULE in check_modules()
    assert {one.name: one.leaves for one in channel_checks()} == LEAVES
    assert [one.name for one in channel_checks()] == list(LEAVES)
    assert all("M10.7.4" not in one.leaves for one in channel_checks())


def test_the_channel_framework_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here
    since 2026-09-30, so a package adding a check edits its own file and never a list every
    package appends to. Delete this and a check can drop out of the module with the page simply
    listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_channel_framework") == [
        "every_adapter_serves_its_declared_capabilities_and_plans_by_them",
        "a_reply_above_a_channels_ceiling_is_refused_and_points_to_ask",
        "each_adapter_is_listed_and_its_health_follows_its_deliveries",
        "a_code_minted_in_an_open_sign_in_binds_one_chat_account_once",
        "a_new_device_replaces_the_old_and_unbinding_is_recorded",
        "an_api_key_is_answered_until_it_is_revoked",
        "a_whatsapp_webhook_is_accepted_only_under_its_app_secret",
    ]


def test_the_whatsapp_bytes_a_check_posts_are_one_message_the_install_verifies_and_reads() -> None:
    """The check's bytes are written from Meta's documented shape and not from the wire, so this
    holds the two to each other: the install's `WIRE` verifies them under the secret that signed
    them, reads them as the one text message they are, and refuses the same JSON written again.
    Delete this and the check can post bytes the install refuses, reporting a working receiver as
    broken, or bytes Meta could never send."""
    from brain.channels.adapter import Arrived
    from brain.channels.webhook import WebhookRefusedError
    from brain.channels.whatsapp import (
        ACCESS_TOKEN,
        APP_SECRET,
        PHONE_NUMBER_ID,
        SIGNATURE_HEADER,
        VERIFY_TOKEN,
        WIRE,
        signature_for,
    )
    from brain.gate.context import Channel

    kept = json.dumps({APP_SECRET: "k" * 32, ACCESS_TOKEN: "t" * 24, VERIFY_TOKEN: "v"})
    tenant = {PHONE_NUMBER_ID: "0"}
    sender = a_number()
    message = whatsapp_message(sender, "QZWORDONE")
    raw = json.dumps(message).encode()
    arrived = Arrived(
        headers={SIGNATURE_HEADER: signature_for("k" * 32, raw)}, body=raw, tenant=tenant
    )
    (part,) = WIRE.parts(WIRE.verify(arrived, kept, datetime.now(UTC)))
    received = WIRE.read(part)
    sent = message["entry"][0]["changes"][0]["value"]["messages"][0]
    assert (received.event.channel, received.event.channel_identity) == (Channel.WHATSAPP, sender)
    assert (received.event.external_id, received.event.text) == (sent["id"], "QZWORDONE")
    assert received.reply_to == sender
    assert received.conversation is not None and not received.conversation.shared
    again = json.dumps(message, separators=(",", ":")).encode()
    assert again != raw
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(
            Arrived(
                headers={SIGNATURE_HEADER: signature_for("k" * 32, again)}, body=raw, tenant=tenant
            ),
            kept,
            datetime.now(UTC),
        )
    assert sender.startswith("999") and sender.isdigit() and len(sender) == 12


class _Recorded:
    """An `async_sessionmaker` stand-in that keeps every statement it is asked to execute."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    def __call__(self) -> _Recorded:
        return self

    async def __aenter__(self) -> _Recorded:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def begin(self) -> _Recorded:
        return self

    async def execute(self, statement: Any) -> None:
        self.statements.append(statement)


def test_a_delivery_is_stamped_by_the_clock_when_its_row_is_written() -> None:
    """`A_DELIVERY_IS_STAMPED_WHEN_IT_IS_WRITTEN`, read off the statement the store sends: the time
    is `clock_timestamp()`, which moves inside a transaction, and not the column's default of
    `now()`, which does not. Delete this and two deliveries in one transaction share a time again,
    so a channel's health is decided by whichever has the smaller random id."""
    from brain.gate.context import Channel
    from brain.ops.channel_store import DeliveryEntry, StoredDeliveries
    from brain.tables.channel import DeliveryOutcome, Direction
    from tests.unit.test_tables import DIALECT

    recorded = _Recorded()
    entry = DeliveryEntry(
        channel=Channel.WEBHOOK, direction=Direction.OUTBOUND, outcome=DeliveryOutcome.SENT
    )
    asyncio.run(StoredDeliveries(recorded).record(entry))  # type: ignore[arg-type]
    [statement] = recorded.statements
    written = str(statement.compile(dialect=DIALECT)).partition(" RETURNING ")[0]
    head, _, tail = written.partition(" VALUES (")
    names = [one.strip() for one in head[head.index("(") + 1 : head.rindex(")")].split(",")]
    values = [one.strip() for one in tail.strip().removesuffix(")").split(", ")]
    assert dict(zip(names, values, strict=True))["recorded_at"] == "clock_timestamp()"


# ------------------------------------------------------------------------ a real run
def counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_CHANNEL_CHECKS
    }


def run_checks(url: str, checks: Sequence[Check]) -> tuple[dict[str, tuple[str, str]], str]:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    stream = io.StringIO()

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await acceptance_run.run_suite(engine, checks, settings=settings, stream=stream)
        finally:
            await engine.dispose()

    results = asyncio.run(run())
    return {one.name: (one.outcome, one.reason) for one in results}, stream.getvalue()


@pytest.mark.needs_db
def test_on_a_real_database_every_channel_check_passes_and_leaves_its_tables_as_they_were(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The seven checks as the worker runs them, on PostgreSQL at head.** Each passes, and every
    table any of them writes to holds afterwards what it held before. Delete this and a channel
    check that commits, or cannot pass on a real schema, reaches the owner's server first."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    with at_head("brain_acceptance_channel_framework") as url:
        before = counts(url)
        results, log = run_checks(url, channel_checks())
        after = counts(url)

    assert results == dict.fromkeys(LEAVES, (PASSED, "")), log
    assert after == before


def _no_ephemeral(m: pytest.MonkeyPatch) -> None:
    from brain.channels.adapter import ChannelCapabilities

    m.setattr(ChannelCapabilities, "supports", lambda self, feature: False)


def _no_ceiling(m: pytest.MonkeyPatch) -> None:
    import brain.channels.outbound

    m.setattr(brain.channels.outbound, "assert_can_send", lambda *args, **kwargs: None)


def _no_faults(m: pytest.MonkeyPatch) -> None:
    import brain.console.channel_health

    m.setattr(brain.console.channel_health, "is_fault", lambda one: False)


def _sign_ins_never_end(m: pytest.MonkeyPatch) -> None:
    from brain.ops.binding_store import StoredSignIns

    async def still_open(self: object, *args: object, **kwargs: object) -> bool:
        return True

    m.setattr(StoredSignIns, "still_open", still_open)


def _rebinding_retires_nothing(m: pytest.MonkeyPatch) -> None:
    import brain.channels.binding

    m.setattr(brain.channels.binding, "_same_channel_binding", lambda fresh, live: None)


def _keys_unchecked(m: pytest.MonkeyPatch) -> None:
    import brain.identity.bearer

    def verify(presented: str, record: object, account: object, *, now: object) -> object:
        return account

    m.setattr(brain.identity.bearer, "verify_key", verify)


def _whatsapp_unsigned(m: pytest.MonkeyPatch) -> None:
    import brain.channels.whatsapp

    m.setattr(brain.channels.whatsapp, "verify_signature", lambda **kwargs: None)


#: One break of the product per check, in what the check exists to catch, and the sentence the
#: check fails with. Each is the product's own function replaced, never the check's.
BREAKS: tuple[tuple[str, Callable[[pytest.MonkeyPatch], None], str], ...] = (
    (
        "every_adapter_serves_its_declared_capabilities_and_plans_by_them",
        _no_ephemeral,
        "a room was answered privately on a channel declaring no ephemeral messages, or with a "
        "link on one declaring them",
    ),
    (
        "a_reply_above_a_channels_ceiling_is_refused_and_points_to_ask",
        _no_ceiling,
        "a reply above the channel's ceiling was sent",
    ),
    (
        "each_adapter_is_listed_and_its_health_follows_its_deliveries",
        _no_faults,
        "a channel whose newest reply the vendor refused was not failing",
    ),
    (
        "a_code_minted_in_an_open_sign_in_binds_one_chat_account_once",
        _sign_ins_never_end,
        "a used, lapsed or signed-out code bound a chat account",
    ),
    (
        "a_new_device_replaces_the_old_and_unbinding_is_recorded",
        _rebinding_retires_nothing,
        "binding a new chat account did not retire the one it replaced",
    ),
    (
        "an_api_key_is_answered_until_it_is_revoked",
        _keys_unchecked,
        "a key with one character changed was answered",
    ),
    (
        "a_whatsapp_webhook_is_accepted_only_under_its_app_secret",
        _whatsapp_unsigned,
        "an unsigned, forged, altered or rewritten request was taken",
    ),
)


def test_every_check_has_one_break_of_the_product_it_exists_to_catch() -> None:
    """Held to the suite, so a check added to the module without a break here fails. Delete this
    and a check can be added that passes on an install whatever the product does."""
    assert [name for name, _, _ in BREAKS] == list(LEAVES)


@pytest.mark.needs_db
def test_each_channel_check_fails_with_its_own_sentence_when_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**A check tested only by passing is satisfied by a check that asserts nothing.** Each break
    replaces the product function the check's leaf rests on: the planner ignoring what an adapter
    declares, the send ignoring the ceiling, the health ignoring faults, a sign-in that never ends,
    a rebind that retires nothing, a key nobody checks, and a WhatsApp request nobody verifies. Each
    check then fails with the sentence written for exactly that, on a database the run leaves as it
    found it. Delete this and any of the seven can go green on an install where its leaf is broken.
    """
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    by_name = {one.name: one for one in channel_checks()}
    found: dict[str, tuple[str, str]] = {}
    logs: list[str] = []
    with at_head("brain_acceptance_channel_framework_broken") as url:
        before = counts(url)
        for name, breaking, _ in BREAKS:
            with monkeypatch.context() as m:
                breaking(m)
                results, log = run_checks(url, [by_name[name]])
            found[name] = results[name]
            logs.append(log)
        after = counts(url)

    assert found == {name: (FAILED, reason) for name, _, reason in BREAKS}, logs
    assert after == before
