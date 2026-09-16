"""Managing webhooks: what a registration must be, where its secret goes, what the vault is told.

No server and no vault. The address rule is driven with the network refused, the vault is
`tests.unit.test_credentials.Vault`, and the slot a secret is written to is
held against the two grammars that must admit it: the vault client's static prefix, and the
credential slot the ledger records a write under.

Task ids: M27.8.12
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

import pytest

from brain.audit.ledger import IDENTIFIER
from brain.channels.telegram import MINIMUM_SECRET_LENGTH
from brain.ops.credentials import VaultState
from brain.ops.openbao import (
    SIGNING_PREFIX,
    StaticVersion,
    VaultRefusedError,
    VaultUnreachableError,
    assert_static_path,
)
from brain.ops.outbox import EventKind
from brain.ops.secrets import SecretsUnavailableError, VaultRole
from brain.ops.webhook_admin import (
    MINIMUM_SIGNING_SECRET_CHARS,
    SIGNING_FIELD,
    TOLD,
    Field,
    SigningSecrets,
    SigningSecretsUnavailableError,
    endpoint_problems,
    kinds_problems,
    registration_problems,
    secret_problems,
    signing_secret_path,
    signing_secret_ref,
    signing_secrets_at_start,
    subscriber_id_problems,
)
from tests.unit.test_credentials import AT, Vault

SECRET = "whsec-SIGNING-SENTINEL-0123456789abcdefABCDEF"
GOOD = {
    "subscriber_id": "billing_bridge",
    "endpoint": "https://hooks.example.test/brain",
    "kinds": [EventKind.APPROVAL_REQUESTED.value],
    "secret": SECRET,
}


def codes(found: Sequence[object]) -> list[tuple[str, str]]:
    return [(one.field.value, one.code) for one in found]  # type: ignore[attr-defined]


# ------------------------------------------------------------------ a registration


def test_a_well_formed_registration_has_no_problems() -> None:
    """The sibling every refusal below needs. Delete this and a judgement that refuses everything
    passes the whole file."""
    assert registration_problems(**GOOD) == ()  # type: ignore[arg-type]


def test_a_registration_wrong_in_every_field_is_told_every_problem_at_once() -> None:
    """A form refused for its first mistake and then for its second is filled in twice. Delete this
    and a judgement that stops at the first problem looks the same on a form with one."""
    found = registration_problems(subscriber_id="", endpoint="", kinds=[], secret="")
    assert codes(found) == [
        ("subscriber_id", "blank"),
        ("endpoint", "blank"),
        ("kinds", "none"),
        ("secret", "blank"),
    ]


@pytest.mark.parametrize("given", ["Billing", "1bridge", "billing-bridge", "a/b", "a" * 64, "a."])
def test_an_id_that_is_not_one_lower_case_slot_segment_is_refused(given: str) -> None:
    """The id is the vault path's last segment and the ledger's subject, so an upper-case letter, a
    leading digit, a hyphen, a slash or a dot would name a slot one of them refuses. Delete this and
    `a/b` writes a secret one level down, where the policy grants nothing."""
    assert codes(subscriber_id_problems(given)) == [("subscriber_id", "not_an_id")]


@pytest.mark.parametrize("given", ["b", "billing_bridge", "a" + "0" * 62])
def test_every_id_accepted_names_a_slot_the_vault_and_the_ledger_both_admit(given: str) -> None:
    """Held against the two grammars rather than restated: `assert_static_path` is what the vault
    client refuses by, and `brain.audit.ledger.IDENTIFIER` is what any ledger entry about the
    subscriber will be held to. Delete this and an id the form accepts can be a write the vault
    client refuses, after the subscriber row was written, or an id no audit entry can name."""
    assert subscriber_id_problems(given) == ()
    path = signing_secret_path(given)
    assert path == f"{SIGNING_PREFIX}{given}"
    assert_static_path(path)
    assert re.fullmatch(IDENTIFIER, given)
    assert "." not in given and "/" not in path.removeprefix(SIGNING_PREFIX)


def test_a_subscriber_row_names_its_slot_and_the_role_that_will_sign_with_it() -> None:
    """The row carries a reference and never a value. Delete this and a registration can point its
    row at another subscriber's secret."""
    ref = signing_secret_ref("billing_bridge")
    assert ref.path == "webhooks/billing_bridge"
    assert ref.role is VaultRole.WORKER


def test_a_host_name_passes_on_its_shape_and_is_never_looked_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`brain.ops.outbox.A_SUBSCRIBER_URL_IS_CHECKED_AT_EVERY_DELIVERY`. The rule is
    `assert_fetchable`'s, stopped at the moment it would ask a resolver, so a name that would
    resolve anywhere at all is accepted without the network being asked. Delete this and a
    registration check that resolves names, and so reads as already checked, passes."""
    import socket

    def refuse(*_: object, **__: object) -> object:
        raise AssertionError("the network was asked about a subscriber's address")

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "gethostbyname", refuse)
    assert endpoint_problems("https://hooks.example.test/brain") == ()


@pytest.mark.parametrize(
    "given",
    [
        "http://hooks.example.test/brain",
        "https://user:pass@hooks.example.test/brain",
        "https://fd00::1/brain",
        "https:///brain",
        "https://169.254.169.254/latest",
        "https://10.0.0.5/hook",
    ],
)
def test_an_address_the_fetch_rule_refuses_is_refused_before_anything_is_written(
    given: str,
) -> None:
    """Not https, credentials in the address, an unbracketed IPv6 authority, no host, and two
    literals only this network can reach. Delete this and a registration is written for an address
    every delivery will refuse."""
    assert codes(endpoint_problems(given)) == [("endpoint", "refused_address")]


def test_a_public_literal_address_is_accepted() -> None:
    """The positive half of the literal case: a literal is judged whole, and a public one passes."""
    assert endpoint_problems("https://93.184.216.34/hook") == ()


def test_an_address_with_space_around_it_or_too_long_is_not_an_address() -> None:
    """Delete this and the row's own check constraint is what refuses a two-thousand-character
    endpoint, after the vault has been written."""
    assert codes(endpoint_problems(" https://hooks.example.test/")) == [
        ("endpoint", "not_an_address")
    ]
    long = "https://hooks.example.test/" + "a" * 2048
    assert codes(endpoint_problems(long)) == [("endpoint", "not_an_address")]


def test_a_kind_this_system_does_not_have_or_named_twice_is_refused() -> None:
    """The table's constraint refuses an unknown kind and the domain type a repeat; both would fail
    after the vault write. Delete this and they do."""
    assert codes(kinds_problems(["invoice.paid"])) == [("kinds", "unknown")]
    one = EventKind.OPERATION_SETTLED.value
    assert codes(kinds_problems([one, one])) == [("kinds", "repeated")]
    assert kinds_problems([one]) == ()


# ------------------------------------------------------------------ the secret


def test_the_floor_on_a_signing_secret_is_the_one_the_telegram_channel_holds_its_own_to() -> None:
    """Anchored outside the module, for CLAUDE.md's rule about a constant compared to itself."""
    assert MINIMUM_SIGNING_SECRET_CHARS == MINIMUM_SECRET_LENGTH


def test_a_secret_one_character_short_of_the_floor_is_refused_and_one_at_it_is_not() -> None:
    """Delete this and the floor moves by one, or disappears, with the file green."""
    at = "s" * MINIMUM_SIGNING_SECRET_CHARS
    assert secret_problems(at) == ()
    assert codes(secret_problems(at[:-1])) == [("secret", "too_short")]


def test_a_secret_with_a_space_inside_is_refused_in_a_signing_secrets_words() -> None:
    """`problems_with` judges it, and the words are about a signing secret rather than a provider
    account. Delete this and a person registering a webhook is told to copy a provider's key."""
    found = secret_problems("s" * 20 + " " + "s" * 20)
    assert codes(found) == [("secret", "not_one_piece")]
    assert "provider" not in found[0].message
    assert all(one.field is Field.SECRET for one in found)


# ------------------------------------------------------------------- the vault


def test_a_secret_is_kept_stripped_at_its_subscribers_slot_and_the_vaults_time_returned() -> None:
    """Delete this and the value can be written with the line break a paste carries, or at the
    wrong path, and still answer held."""
    vault = Vault()
    written = SigningSecrets(vault).keep("billing_bridge", SECRET + "\n", actor="u_admin")
    assert written == AT
    assert vault.written == [("webhooks/billing_bridge", {SIGNING_FIELD: SECRET})]


def test_whether_a_secret_is_held_is_read_from_metadata_with_its_time() -> None:
    """Held with its time, and not held when the slot answers nothing. Delete this and a slot never
    written reads as held."""
    assert SigningSecrets(Vault(version=StaticVersion(written_at=AT))).held("b").written_at == AT
    assert SigningSecrets(Vault(version=StaticVersion(written_at=AT))).held("b").held is True
    empty = SigningSecrets(Vault(version=None)).held("b")
    assert (empty.held, empty.written_at) == (False, None)


@pytest.mark.parametrize(
    ("raised", "state"),
    [
        (VaultUnreachableError("silent"), VaultState.UNREACHABLE),
        (VaultRefusedError("no", status=403), VaultState.REFUSED),
        (SecretsUnavailableError("other"), VaultState.REFUSED),
    ],
)
def test_a_silent_vault_and_a_refusing_one_are_told_apart(
    raised: Exception, state: VaultState
) -> None:
    """What a person is told to do differs. Delete this and a sealed vault sends somebody to read a
    policy."""
    with pytest.raises(SigningSecretsUnavailableError) as keeping:
        SigningSecrets(Vault(fail=raised)).keep("b", SECRET, actor="u_admin")
    assert keeping.value.state is state
    assert str(keeping.value) == TOLD[state]
    with pytest.raises(SigningSecretsUnavailableError) as asking:
        SigningSecrets(Vault(fail=raised)).held("b")
    assert asking.value.state is state


def test_an_install_with_no_vault_refuses_both_and_says_absent() -> None:
    """Delete this and an install without a vault answers not held, which sends somebody to register
    a secret that cannot be kept."""
    secrets = signing_secrets_at_start("", "")
    assert secrets.configured is False
    for act in (lambda: secrets.held("b"), lambda: secrets.keep("b", SECRET, actor="u")):
        with pytest.raises(SigningSecretsUnavailableError) as refused:
            act()
        assert refused.value.state is VaultState.ABSENT
    assert signing_secrets_at_start("http://vault:8200", "").configured is False
    assert signing_secrets_at_start("not a url", "token").configured is False
    assert signing_secrets_at_start("http://vault:8200", "token").configured is True


def test_the_log_names_the_subscriber_and_the_actor_and_never_the_secret(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and a debugging line that includes the value ships."""
    caplog.set_level(logging.DEBUG)
    SigningSecrets(Vault()).keep("billing_bridge", SECRET, actor="u_admin")
    with pytest.raises(SigningSecretsUnavailableError):
        SigningSecrets(Vault(fail=VaultUnreachableError("x"))).keep("b", SECRET, actor="u_admin")
    out = capsys.readouterr()
    everything = out.out + out.err + caplog.text
    assert "billing_bridge" in everything
    assert SECRET not in everything
