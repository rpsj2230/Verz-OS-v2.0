"""The install audit checks, each passing over an install holding its own data and failing for each
thing it exists to find.

**Every scenario is built inside the run's own rolled-back transaction.** A wrapper check does the
set-up with the harness's helpers and then awaits the real check's body, so the check reads what it
would read on an install that holds these people, sessions, webhooks and sources, and nothing is
left behind. The audit itself reads at most `MOST_ROWS` of each and never a whole table as text.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M42.4.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator

import pytest
from sqlalchemy import text

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.ops.acceptance_checks_install_audit import CHECK_ORDER
from brain.ops.acceptance_run import Harness
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_install_audit"
PEOPLE = "administrators_are_people_with_sign_ins_and_sessions_are_short"
HELD = "settings_hold_no_secret_and_webhooks_and_sources_are_held"


def test_the_module_names_the_leaf_on_both_checks_inside_its_range() -> None:
    """Both checks name the leaf and sit where assigned. Delete this and a check can drop the leaf
    it was written for, or slip out of its place on the Install page."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (PEOPLE, ("M42.4.3",)),
        (HELD, ("M42.4.3",)),
    ]
    assert checks_in(MODULE) == [PEOPLE, HELD]
    assert CHECK_ORDER == 2330


@pytest.fixture(autouse=True)
def issuer_of_this_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install values a console sign-in needs, set as the whole-suite run sets them."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_install_audit") as url:
        yield url


Setup = Callable[[Harness], Awaitable[None]]


def run_with(url: str, name: str, setup: Setup | None = None) -> tuple[str, str]:
    """The named check, run after `setup` has made the install hold something."""
    from brain.db import normalise_database_url

    inner = next(one for one in registered((MODULE,)) if one.name == name)

    async def wrapped(h: Harness) -> None:
        if setup is not None:
            await setup(h)
        await inner.run(h)

    check = Check(inner.name, inner.leaves, inner.sentence, wrapped)
    settings = settings_from({"BRAIN_DATABASE_URL": url, **INSTALL})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=[check],
            force=True,
        )
    )
    [one] = results
    return one.outcome, one.reason


def _failed(url: str, name: str, setup: Setup) -> str:
    outcome, reason = run_with(url, name, setup)
    assert outcome == FAILED, reason
    return reason


async def _administrator(h: Harness, *, bound: bool = True, name: str = "") -> str:
    from brain.ops.acceptance_checks_first_run import A
    from brain.ops.acceptance_people_signed_in import administrator, console, everywhere

    await h.found_departments()
    who = h.principal(A, "audited")
    await h.person(who, department=A, grants=everywhere(*administrator()))
    if name:
        await h.execute(
            text("UPDATE auth.principal SET display_name = :n WHERE id = :id").bindparams(
                n=name, id=who
            )
        )
    if bound:
        await (await console(h)).link(who)
    return who


async def _bound_administrator(h: Harness) -> None:
    await _administrator(h)


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install_holding_nothing_and_leave_nothing(install: str) -> None:
    """The install that has been set up and furnished and holds none of these things. Delete this
    and a check that cannot pass on a real schema reaches an owner's server."""
    before = counts(install)

    assert run_with(install, PEOPLE) == (PASSED, "")
    assert run_with(install, HELD) == (PASSED, "")
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_install_with_a_bound_administrator_passes_the_people_check(install: str) -> None:
    """The positive case, over an install with an administrator who signs in as themselves. Delete
    this and the refusals below are satisfied by a check that refuses every administrator."""
    assert run_with(install, PEOPLE, _bound_administrator) == (PASSED, "")


@pytest.mark.needs_db
def test_an_administrator_with_no_sign_in_of_their_own_fails_the_people_check(
    install: str,
) -> None:
    """An administrator nobody can sign in as. Delete this and a hand-written grant on an account
    with no identity passes, which is the shape of a default account."""

    async def setup(h: Harness) -> None:
        await _administrator(h, bound=False)

    assert "no sign-in" in _failed(install, PEOPLE, setup)


@pytest.mark.needs_db
@pytest.mark.parametrize("name", ["Administrator", "  ROOT ", "Default Admin"])
def test_an_administrator_named_as_a_default_account_fails_the_people_check(
    install: str, name: str
) -> None:
    """The names a default account has. Delete this and an install shipped with an account called
    Administrator passes once somebody binds a sign-in to it."""

    async def setup(h: Harness) -> None:
        await _administrator(h, name=name)

    assert "default account" in _failed(install, PEOPLE, setup)


@pytest.mark.needs_db
def test_a_session_allowed_to_last_longer_than_a_month_fails_the_people_check(
    install: str,
) -> None:
    """A session that never really ends. Delete this and a token minted for a year passes."""

    async def setup(h: Harness) -> None:
        who = await _administrator(h)
        await h.execute(
            text(
                "INSERT INTO auth.session (id, principal_id, channel, assurance, started_at, "
                "expires_at) VALUES (:id, :who, 'console', 1, now(), now() + interval '90 days')"
            ).bindparams(id=f"audit-{h.run}", who=who)
        )

    assert "longer than a month" in _failed(install, PEOPLE, setup)


@pytest.mark.needs_db
def test_an_ordinary_session_passes_the_people_check(install: str) -> None:
    """A session of an ordinary length. Delete this and the month bound refuses every session."""

    async def setup(h: Harness) -> None:
        who = await _administrator(h)
        await h.execute(
            text(
                "INSERT INTO auth.session (id, principal_id, channel, assurance, started_at, "
                "expires_at) VALUES (:id, :who, 'console', 1, now(), now() + interval '12 hours')"
            ).bindparams(id=f"audit-{h.run}", who=who)
        )

    assert run_with(install, PEOPLE, setup) == (PASSED, "")


async def _saved(h: Harness, **values: str) -> None:
    from brain.ops.install_settings import save

    async with h.sessions() as session, session.begin():
        await save(session, values, updated_by=h.actor)


@pytest.mark.needs_db
def test_an_install_with_saved_values_of_its_own_passes_the_held_check(install: str) -> None:
    """The installs this runs on have saved values. Delete this and a check that only passes over
    an empty settings table is called passing."""

    async def setup(h: Harness) -> None:
        await _saved(h, INSTALL_COMPANY_NAME="A company", INSTALL_PRODUCT_NAME="Its brain")

    assert run_with(install, HELD, setup) == (PASSED, "")


@pytest.mark.needs_db
@pytest.mark.parametrize(
    "pasted",
    [
        "sk-" + "a" * 30,
        "ghp_" + "b" * 30,
        "AKIA" + "C" * 16,
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_a_saved_value_shaped_like_a_key_fails_the_held_check(install: str, pasted: str) -> None:
    """A key pasted into a field that is saved in the clear. Delete this and a provider key typed
    into the company-name box is saved, shown and read by anything that lists the settings."""

    async def setup(h: Harness) -> None:
        await _saved(h, INSTALL_COMPANY_NAME=pasted)

    assert "shaped like a key" in _failed(install, HELD, setup)


async def _webhook(h: Harness, *, endpoint: str, path: str) -> None:
    await h.execute(
        text(
            "INSERT INTO ops.webhook_subscriber (subscriber_id, endpoint, secret_path, "
            "secret_role, kinds, created_by) "
            "VALUES (:id, :endpoint, :path, 'webhook_signer', ARRAY['alert_raised'], :by)"
        ).bindparams(id=f"audit-{h.run}", endpoint=endpoint, path=path, by=h.actor)
    )


def _kinds_and_role() -> tuple[str, str]:
    from brain.ops.outbox import EventKind
    from brain.ops.secrets import VaultRole

    return next(iter(EventKind)).value, next(iter(VaultRole)).value


@pytest.mark.needs_db
def test_https_webhooks_with_a_signing_path_pass_and_other_ones_fail(install: str) -> None:
    """The positive case and both refusals. Delete this and a webhook that sends events in the
    clear, or whose secret is not where signing secrets are, passes."""
    kind, role = _kinds_and_role()

    def make(endpoint: str, path: str) -> Setup:
        async def setup(h: Harness) -> None:
            await h.execute(
                text(
                    "INSERT INTO ops.webhook_subscriber (subscriber_id, endpoint, secret_path, "
                    "secret_role, kinds, created_by) VALUES (:id, :e, :p, :r, ARRAY[:k], :by)"
                ).bindparams(id=f"audit-{h.run}", e=endpoint, p=path, r=role, k=kind, by=h.actor)
            )

        return setup

    assert run_with(install, HELD, make("https://hooks.example.invalid/x", "webhooks/a")) == (
        PASSED,
        "",
    )
    assert "not https" in _failed(
        install, HELD, make("http://hooks.example.invalid/x", "webhooks/a")
    )
    assert "signing path" in _failed(
        install, HELD, make("https://hooks.example.invalid/x", "providers/anthropic")
    )


def _connector() -> str:
    from brain.connectors.declaration import CredentialShape
    from brain.ops.connectable import CONNECTABLE

    return next(
        name for name, kind in CONNECTABLE.items() if kind.credential_shape is CredentialShape.KEY
    )


@pytest.mark.needs_db
def test_a_connected_source_with_a_credential_write_passes_and_without_one_fails(
    install: str,
) -> None:
    """A source that takes a key and was connected without one being written. Delete this and a
    connection copied from another install, with the key left behind, reads as connected."""
    from brain.ops.connector_store import connected_row
    from brain.ops.credential_write_store import written
    from brain.ops.credentials import connector_key_slot

    name = _connector()

    async def without(h: Harness) -> None:
        await h.execute(connected_row(name, {}, "d" * 64, h.actor))

    async def with_key(h: Harness) -> None:
        await without(h)
        await h.execute(*h.attributed(), written(connector_key_slot(name).path, h.actor))

    assert "no credential written" in _failed(install, HELD, without)
    assert run_with(install, HELD, with_key) == (PASSED, "")


@pytest.mark.needs_db
def test_an_ordinary_person_who_cannot_sign_in_yet_is_not_an_administrator(install: str) -> None:
    """Only the holders of the authority are asked for a sign-in. Delete this and a colleague who
    has not signed in yet, or a contractor, is reported as an administrator without one."""

    async def setup(h: Harness) -> None:
        from brain.ops.acceptance_checks_first_run import A

        await h.found_departments()
        await h.person(h.principal(A, "colleague"), department=A)

    assert run_with(install, PEOPLE, setup) == (PASSED, "")


@pytest.mark.needs_db
def test_a_switched_off_webhook_and_a_disconnected_source_are_not_audited(install: str) -> None:
    """What is off is not held to what is on. Delete this and a webhook somebody switched off
    because it was insecure keeps the check red, and a source disconnected with its key removed does
    too."""
    from brain.ops.connector_store import connected_row, disconnection
    from brain.ops.outbox_store import deactivate_subscriber

    kind, role = _kinds_and_role()
    name = _connector()

    async def setup(h: Harness) -> None:
        await h.execute(
            text(
                "INSERT INTO ops.webhook_subscriber (subscriber_id, endpoint, secret_path, "
                "secret_role, kinds, created_by) "
                "VALUES (:id, 'http://old.example.invalid/x', 'providers/x', :r, ARRAY[:k], :by)"
            ).bindparams(id=f"audit-{h.run}", r=role, k=kind, by=h.actor)
        )
        async with h.sessions() as session, session.begin():
            await deactivate_subscriber(session, f"audit-{h.run}", at=h.now)
        await h.execute(connected_row(name, {}, "d" * 64, h.actor))
        await h.execute(*h.attributed(), disconnection(name, h.actor))

    assert run_with(install, HELD, setup) == (PASSED, "")


@pytest.mark.needs_db
def test_a_connected_source_that_takes_no_key_needs_no_credential_write(install: str) -> None:
    """A source with nothing to keep is not asked for a key. Delete this and a connected source
    that takes no key is reported as missing one."""
    from brain.connectors.declaration import CredentialShape
    from brain.ops.connectable import CONNECTABLE
    from brain.ops.connector_store import connected_row

    keyless = next(n for n, k in CONNECTABLE.items() if k.credential_shape is CredentialShape.NONE)

    async def setup(h: Harness) -> None:
        await h.execute(connected_row(keyless, {}, "d" * 64, h.actor))

    assert run_with(install, HELD, setup) == (PASSED, "")
