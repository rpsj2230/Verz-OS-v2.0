"""The channel acceptance checks: registered, passing on a real schema, and able to fail.

The email check posts to the events route mounted over its own transaction, so PostgreSQL at head
is the whole of it, run as the worker runs it. With no relay saved it says the reply half was not
run; with one saved it passes and leaves every table as it was; and broken where it proves the
product, each the way it would break in practice, it fails with its own sentence: the wire
believing a failed verdict, and a relay whose user the vault lends no password for.

Task ids: M10.5.6
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_channels as channels
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.ops.mail import RELAY_CREDENTIAL_FIELD, RELAY_CREDENTIAL_SLOT, MailPassword
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check
from tests.unit.test_channel_pipeline import KeptVault

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_channels"
EMAIL = "an_email_is_taken_signed_and_answered_by_the_install_s_relay"
SLACK = "a_slack_message_is_taken_signed_and_answered_on_the_bot_token"
MAILBOX = "mail_in_the_mailbox_is_read_answered_and_marked"
TEAMS = "a_teams_message_is_taken_signed_and_answered_in_its_chat"
TELEGRAM = "a_telegram_message_on_the_registered_header_is_answered"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_each_channel_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        EMAIL: ("M10.5.6",),
        SLACK: ("M10.5.1",),
        MAILBOX: ("M10.5.6",),
        TEAMS: ("M10.5.2",),
        TELEGRAM: ("M10.5.4",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert {"M10.5.6", "M10.5.1", "M10.5.2", "M10.5.4"} <= {
        one for module in wbs["modules"] for one in module["leaf_ids"]
    }


def test_the_channels_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them: one per
    way a vendor connects, email, Slack, email read from a mailbox, Teams, then Telegram. Held
    here, beside the module's other tests, since 2026-09-30, so a package adding a check edits its
    own file and never a list every package appends to. Delete this and a check can drop out of
    the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [EMAIL, SLACK, MAILBOX, TEAMS, TELEGRAM]


def lends(password: str | None) -> MailPassword:
    vault = KeptVault()
    if password is not None:
        vault.slots[RELAY_CREDENTIAL_SLOT] = {RELAY_CREDENTIAL_FIELD: password}
    return MailPassword(vault)


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    from tests.unit.test_acceptance import INSTALL

    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    with at_head("brain_acceptance_channels") as url:
        yield url


def save_relay(url: str) -> None:
    from tests.fixtures.scratch_postgres import sql

    for key, kind, value in (
        ("host", "string", '"smtp.acceptance.invalid"'),
        ("port", "integer", "587"),
        ("security", "string", '"starttls"'),
        ("sender", "string", '"brain@acceptance.invalid"'),
        ("username", "string", '"relay_user"'),
    ):
        sql(
            url,
            "INSERT INTO ops.setting (key, value_type, value, description, updated_by)"
            " VALUES (%s, %s, %s::jsonb, 'the relay', 'u_admin')",
            f"mail.{key}",
            kind,
            value,
        )


@pytest.mark.needs_db
def test_with_no_relay_saved_the_reply_half_is_not_run(install: str) -> None:
    """**Half a sentence is not a pass.** The inbound half runs and the check says the rest was
    not asked. Delete this and an install with no relay could show email as proved."""
    before = counts(install)
    assert run_check(install, (mine()[EMAIL],)) == {EMAIL: (NOT_RUN, channels.NO_RELAY_IS_SAVED)}
    assert counts(install) == before


@pytest.mark.needs_db
def test_with_a_relay_saved_the_check_passes_and_leaves_nothing_behind(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The check as the worker runs it**, with the relay saved on Notifications and a vault
    lending its password. It passes, and every table it wrote to holds what it held before.

    Delete this and a check that cannot pass on the real schema, or one that commits a channel
    record to a client's install, reaches the owner's server first."""
    save_relay(install)
    monkeypatch.setattr("brain.channel_routes.mail_password_of", lambda request: lends("pw"))
    before = counts(install)
    assert run_check(install, (mine()[EMAIL],)) == {EMAIL: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("signature", "mail signed with another secret was accepted"),
        ("verdict", "mail its receiver marked as failed was accepted"),
        ("host", "the reply was built for a relay other than the one saved"),
        (
            "password",
            "the relay saved on Notifications names a user and the vault lent no password for the "
            "reply",
        ),
    ],
)
def test_the_check_fails_where_the_product_breaks(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Broken the way each would break: the wire skipping the signature, the wire reading a
    message whose verdict failed as though it passed, the reply built for a relay other than the
    one saved, and a vault holding no password for the relay's user. Delete this and any of them
    could go with the check green."""
    from brain.channels import email
    from brain.channels.email import Authentication

    save_relay(install)
    monkeypatch.setattr("brain.channel_routes.mail_password_of", lambda request: lends("pw"))
    if broken == "signature":
        monkeypatch.setattr(email, "verify_signed", lambda **kwargs: None)
    elif broken == "host":
        from brain.ops.mail import MailSettings, Security

        elsewhere = MailSettings(
            host="smtp.elsewhere.invalid",
            port=587,
            security=Security.STARTTLS,
            sender="brain@acceptance.invalid",
            username="relay_user",
        )

        async def other() -> MailSettings:
            return elsewhere

        monkeypatch.setattr("brain.channel_routes.relay_settings_of", lambda request: other)
    elif broken == "verdict":
        real = email.normalise

        def believing(message: Any) -> Any:
            return real(
                email.InboundEmail(
                    message_id=message.message_id,
                    from_header=message.from_header,
                    subject=message.subject,
                    body=message.body,
                    received_at=message.received_at,
                    authentication=Authentication.PASSED,
                    headers=message.headers,
                )
            )

        monkeypatch.setattr(email, "normalise", believing)
    else:
        monkeypatch.setattr("brain.channel_routes.mail_password_of", lambda request: lends(None))
    assert run_check(install, (mine()[EMAIL],)) == {EMAIL: (FAILED, reason)}


@pytest.mark.needs_db
def test_the_slack_check_passes_on_a_real_schema_and_leaves_nothing_behind(install: str) -> None:
    """**The Slack check as the worker runs it**: it needs no relay and no vendor, so it passes,
    and every table it wrote to holds what it held before. Delete this and a check that cannot
    pass on the real schema, or one that commits a Slack record, reaches the owner's server."""
    before = counts(install)
    assert run_check(install, (mine()[SLACK],)) == {SLACK: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("signature", "a request signed with another secret was accepted"),
        ("token", "the answer was not built on the bot's token"),
        ("challenge", "Slack's address check was not answered with its own challenge"),
    ],
)
def test_the_slack_check_fails_where_the_product_breaks(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Broken the way each would break: the wire skipping the signature, the request sent without
    the token, and the address check left unanswered. Delete this and any of them could go with the
    check green."""
    from brain.channels import slack

    if broken == "signature":
        monkeypatch.setattr(slack, "verify", lambda **kwargs: None)
    elif broken == "token":
        real = slack.SlackWire.request_for

        def tokenless(self: Any, **kwargs: Any) -> Any:
            made = real(self, **kwargs)
            return replace(made, headers={"Content-Type": "application/json"})

        monkeypatch.setattr(slack.SlackWire, "request_for", tokenless)
    else:
        monkeypatch.setattr(slack.SlackWire, "handshake", lambda self, arrived: None)
    assert run_check(install, (mine()[SLACK],)) == {SLACK: (FAILED, reason)}


@pytest.mark.needs_db
def test_the_mailbox_check_waits_for_a_relay_and_passes_with_one(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The mailbox check as the worker runs it**: not run with no relay saved, and with one it
    passes and leaves every table as it was. Delete this and a mailbox that answers nobody could
    show as proved, or the check could commit a channel record to a client's install."""
    before = counts(install)
    assert run_check(install, (mine()[MAILBOX],)) == {
        MAILBOX: (NOT_RUN, channels.NO_RELAY_IS_SAVED_FOR_THE_MAILBOX)
    }
    save_relay(install)
    monkeypatch.setattr("brain.channel_routes.mail_password_of", lambda request: lends("pw"))
    before = counts(install)
    assert run_check(install, (mine()[MAILBOX],)) == {MAILBOX: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("verdict", "not exactly the colleague's message was answered"),
        ("reading", "the mailbox's unread mail was not read, marked and closed"),
    ],
)
def test_the_mailbox_check_fails_where_the_product_breaks(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Broken the way each would break: a verdict that believes every sender, and a poll that
    reads and marks less than the mailbox holds. Delete this and either could go with the check
    green."""
    from brain import mailbox_read
    from brain.channels.email import Authentication

    save_relay(install)
    monkeypatch.setattr("brain.channel_routes.mail_password_of", lambda request: lends("pw"))
    if broken == "verdict":
        monkeypatch.setattr(
            mailbox_read, "verdict_of", lambda message, settings: Authentication.PASSED
        )
    else:
        monkeypatch.setattr(mailbox_read, "MOST_PER_POLL", 1)
    assert run_check(install, (mine()[MAILBOX],)) == {MAILBOX: (FAILED, reason)}


@pytest.mark.needs_db
def test_the_teams_check_passes_on_a_real_schema_and_leaves_nothing_behind(install: str) -> None:
    """**The Teams check as the worker runs it**, with a key the check made standing for
    Microsoft's: it passes and every table it wrote to holds what it held before. Delete this and
    a check that cannot pass on the real schema, or one that commits a Teams record, reaches the
    owner's server."""
    before = counts(install)
    assert run_check(install, (mine()[TEAMS],)) == {TEAMS: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("signature", "a token no published key signed was accepted"),
        ("tenant", "an activity from another tenant was accepted"),
        ("login", "the answer was not authorised at the tenant's own login"),
    ],
)
def test_the_teams_check_fails_where_the_product_breaks(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Broken the way each would break: a signature check that passes anything, a tenant pin
    that matches any tenant, and a token exchanged at Microsoft's common login. Delete this and
    any of them could go with the check green."""
    from brain.channels import teams
    from brain.identity.keycloak_tokens import verify_rs256

    if broken == "signature":
        # The wire is a frozen dataclass; its verifier is swapped and put back below.
        object.__setattr__(teams.WIRE, "signature", lambda **kwargs: True)
    elif broken == "tenant":
        monkeypatch.setattr(teams, "tenant_matches", lambda body, tenant_id: True)
    else:
        real = teams.TeamsWire.request_for

        def common_login(self: Any, **kwargs: Any) -> Any:
            made = real(self, **kwargs)
            exchange = made.exchange
            assert exchange is not None
            common = f"{teams.MICROSOFT_LOGIN_URL}/common/oauth2/v2.0/token"
            return replace(made, exchange=replace(exchange, url=common))

        monkeypatch.setattr(teams.TeamsWire, "request_for", common_login)
    try:
        assert run_check(install, (mine()[TEAMS],)) == {TEAMS: (FAILED, reason)}
    finally:
        object.__setattr__(teams.WIRE, "signature", verify_rs256)


@pytest.mark.needs_db
def test_the_telegram_check_passes_on_a_real_schema_and_leaves_nothing_behind(install: str) -> None:
    """**The Telegram check as the worker runs it**, with a bot token the check made: it passes
    and every table it wrote to holds what it held before. Delete this and a check that cannot
    pass on the real schema, or one that commits a Telegram record, reaches the owner's server."""
    before = counts(install)
    assert run_check(install, (mine()[TELEGRAM],)) == {TELEGRAM: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("header", "an update carrying another header was accepted"),
        ("made", "the header Telegram is told to send is not made from the token"),
    ],
)
def test_the_telegram_check_fails_where_the_product_breaks(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Broken the way each would break: a header check that passes anything, and a registration
    that tells Telegram the token itself as the header. Delete this and either could go with the
    check green."""
    from brain.channels import telegram

    if broken == "header":
        monkeypatch.setattr(telegram, "assert_from_telegram", lambda **kwargs: None)
    else:
        monkeypatch.setattr(telegram, "webhook_secret_of", lambda bot_token: bot_token)
    assert run_check(install, (mine()[TELEGRAM],)) == {TELEGRAM: (FAILED, reason)}
