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
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_channels as channels
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.ops.mail import RELAY_CREDENTIAL_FIELD, RELAY_CREDENTIAL_SLOT, MailPassword
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_automation import run_check
from tests.unit.test_channel_pipeline import KeptVault

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_channels"
EMAIL = "an_email_is_taken_signed_and_answered_by_the_install_s_relay"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_email_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {EMAIL: ("M10.5.6",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert "M10.5.6" in {one for module in wbs["modules"] for one in module["leaf_ids"]}


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
    assert run_check(install, tuple(mine().values())) == {
        EMAIL: (NOT_RUN, channels.NO_RELAY_IS_SAVED)
    }
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
    assert run_check(install, tuple(mine().values())) == {EMAIL: (PASSED, "")}
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
    assert run_check(install, tuple(mine().values())) == {EMAIL: (FAILED, reason)}
