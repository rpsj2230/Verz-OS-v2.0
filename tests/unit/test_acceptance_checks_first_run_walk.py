"""The install checks for the staff list screen and the finishing sign-in, each passing on
PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M42.5.7, M42.5.14
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from brain.connectors.staff_directories import REGISTRATION, exchange
from brain.console.staff_source_view import rehearse
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_first_run_walk import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_first_run_walk"
STAFF = "the_staff_list_screen_reads_a_list_and_writes_nothing"
FINISH = "the_first_administrator_is_bound_and_signed_in_at_the_end"


def test_the_module_names_each_leaf_in_one_check_inside_its_range() -> None:
    """One check per leaf, in the order range assigned. Delete this and a leaf can move to a check
    that never looked at it, or the module can slip out of its place on the Install page."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (STAFF, ("M42.5.7",)),
        (FINISH, ("M42.5.14",)),
    ]
    assert checks_in(MODULE) == [STAFF, FINISH]
    assert CHECK_ORDER == 1835


@pytest.fixture(autouse=True)
def issuer_of_this_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install values a console sign-in needs, set as the whole-suite run sets them."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_first_run_walk") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url, **INSTALL})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and nothing is left behind. Delete this and
    a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_staff_trial_without_the_setup_code_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The setup code no longer asked before a directory is built. Delete this and M42.5.7 closes
    on a screen that makes this server send a stranger's secret to a vendor."""
    from brain import setup_staff_routes

    async def anyone(request: object, setup_code: str, now: object) -> None:
        return None

    monkeypatch.setattr(setup_staff_routes, "assert_setup_open", anyone)
    assert "setup code" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_secret_with_a_space_sent_on_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The secret judged by nothing before the exchange. Delete this and M42.5.7 closes on a
    screen that sends whatever was pasted, whitespace and all, to a vendor."""
    from brain import setup_staff_routes

    monkeypatch.setattr(setup_staff_routes, "secret_problem", lambda secret: "")
    assert "still gave a plan" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_spreadsheet_that_reads_nobody_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The spreadsheet's rows dropped on the way to the source. Delete this and M42.5.7 closes on
    a screen that tells a person their list was read when nobody was."""
    from brain import setup_staff_routes
    from brain.identity.staff_adapters import SpreadsheetSource

    def empty(*, rows: object) -> SpreadsheetSource:
        return SpreadsheetSource(rows=())

    monkeypatch.setattr(setup_staff_routes, "SpreadsheetSource", empty)
    assert "spreadsheet" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_finishing_screen_that_takes_any_code_fails_the_finishing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The setup code no longer compared. Delete this and M42.5.14 closes on a screen anybody
    holding a token can use to make themselves the first administrator."""
    from brain import sign_in_routes

    monkeypatch.setattr(sign_in_routes, "finish", lambda *args, **kwargs: None)
    assert "refused" in _failed(install, FINISH)


@pytest.mark.needs_db
def test_a_finishing_screen_that_binds_nobody_fails_the_finishing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bind answered as written and not written. Delete this and M42.5.14 closes on a screen
    that says the first administrator is signed in when no binding exists."""
    from brain.identity.sign_in_binding import Binding
    from brain.ops import acceptance_checks_first_run_walk as walk

    async def not_written(self: object, subject: str, **kwargs: object) -> Binding:
        return Binding.BOUND

    monkeypatch.setattr(walk._NobodyIsSignedInYet, "bind", not_written)
    reason = _failed(install, FINISH)
    assert reason


@pytest.mark.needs_db
def test_a_return_path_that_moved_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The path the vendor returns to, changed in the screen and not in the console. Delete this
    and M42.5.7 closes on a screen that sends a person back to a page that does not exist."""
    from brain import setup_staff_routes

    monkeypatch.setattr(setup_staff_routes, "RETURN_PATH", "/first-run/elsewhere")
    assert "return address" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_directory_dropped_from_the_screen_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lark no longer offered. Delete this and M42.5.7 closes on a screen that offers two of the
    three directories a company may keep its staff list in."""

    kept = {k: v for k, v in REGISTRATION.items() if k != "lark"}
    monkeypatch.setattr("brain.setup_staff_routes.REGISTRATION", kept)
    assert "three directories" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_trial_that_removes_people_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first run proposing removals from an empty install. Delete this and M42.5.7 closes on a
    trial that frightens a person with removals nobody could make."""
    from brain.identity.staff_source import Roster

    real = rehearse

    def removing(*args: object, **kwargs: object) -> object:
        held = {"someone@acceptance.example.invalid": "p1"}
        later = {**kwargs, "known": held, "last_applied": datetime(2019, 1, 1, tzinfo=UTC)}
        return real(*args, **later)  # type: ignore[arg-type]

    monkeypatch.setattr("brain.setup_staff_routes.rehearse", removing)
    monkeypatch.setattr(Roster, "may_remove", lambda self: True)
    assert "removing" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_secret_sent_in_an_address_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The client secret carried in a request address. Delete this and M42.5.7 closes on a screen
    that writes a company's secret into every proxy log between here and the vendor."""
    from brain.connectors.staff_directories import Outbound

    real = exchange

    async def in_the_address(fetch: object, source: str, **kwargs: str) -> str:
        async def leaking(outbound: Outbound) -> object:
            return await fetch(  # type: ignore[operator]
                Outbound(
                    outbound.method,
                    f"{outbound.url}?s={kwargs['client_secret']}",
                    outbound.headers,
                    form=outbound.form,
                )
            )

        return await real(leaking, source, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("brain.setup_staff_routes.exchange", in_the_address)
    assert "request address" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_finishing_screen_that_binds_a_non_administrator_fails_the_finishing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everybody counted as an administrator. Delete this and M42.5.14 closes on a screen that
    makes whoever holds a token and a code the first administrator."""
    from brain import sign_in_routes

    monkeypatch.setattr(sign_in_routes, "holds_everywhere", lambda reach, now: True)
    assert "refused" in _failed(install, FINISH)


@pytest.mark.needs_db
def test_a_finishing_screen_that_never_closes_fails_the_finishing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count of sign-ins always none. Delete this and M42.5.14 closes on a screen that stays
    open after the install has its first administrator, which is a way in for anyone with the
    code."""
    from brain.identity.sign_in_binding import SignInBindings

    async def none(self: object) -> int:
        return 0

    monkeypatch.setattr(SignInBindings, "sign_ins", none)
    assert "refused" in _failed(install, FINISH)


@pytest.mark.needs_db
def test_a_directory_offered_with_nothing_to_register_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory offered with no words on where to register it. Delete this and M42.5.7 closes on
    a screen that offers a sign-in a company cannot set up."""
    import dataclasses

    bare = {name: dataclasses.replace(one, where="") for name, one in REGISTRATION.items()}
    monkeypatch.setattr("brain.setup_staff_routes.REGISTRATION", bare)
    assert "registering" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_sign_in_address_at_another_host_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person sent somewhere other than the vendor's page. Delete this and M42.5.7 closes on a
    screen that sends a company's staff to sign in at an address nobody checked."""
    from brain.connectors import staff_directories

    monkeypatch.setattr(
        staff_directories,
        "authorisation_address",
        lambda *args, **kwargs: "https://elsewhere.example.invalid/sign-in",
    )
    assert "vendor's own page" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_spreadsheet_that_names_one_person_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A list read as holding another set of people than it does. Delete this and M42.5.7 closes on
    a trial that names people the file never held."""
    from brain.ops import acceptance_checks_first_run_walk as walk

    one_row = (
        walk.SHEET.splitlines()[0] + "\nada@acceptance.example.invalid,Ada One,engineering,,\n"
    )
    monkeypatch.setattr(walk, "SHEET", one_row)
    assert "two people" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_directory_that_reads_nobody_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory walk that returned an empty page. Delete this and M42.5.7 closes on a trial that
    says a directory was read when it held nobody."""
    from brain import setup_staff_routes
    from brain.identity.staff_adapters import MicrosoftEntraSource

    async def empty(*args: object, **kwargs: object) -> MicrosoftEntraSource:
        return MicrosoftEntraSource(pages=[{"value": []}])

    monkeypatch.setattr(setup_staff_routes, "pull", empty)
    assert "not read" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_refusal_that_is_not_a_sentence_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A secret refused with a code and not words. Delete this and M42.5.7 closes on a screen that
    tells a person to fix something in a word they cannot read."""
    from brain import setup_staff_routes

    monkeypatch.setattr(
        setup_staff_routes,
        "secret_problem",
        lambda secret: "bad_secret" if " " in secret else "",
    )
    assert "in words" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_refusal_that_repeats_the_secret_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A vendor's refusal quoted with the secret that was sent. Delete this and M42.5.7 closes on a
    screen that prints a company's client secret on a page."""
    import secrets
    from types import SimpleNamespace

    from brain.connectors import staff_directories
    from brain.ops import acceptance_checks_first_run_walk as walk

    fixed = "ab" * 12
    monkeypatch.setattr(
        walk,
        "secrets",
        SimpleNamespace(token_hex=lambda n: fixed, token_urlsafe=secrets.token_urlsafe),
    )
    real = staff_directories.token_from

    def repeating(answer: object) -> str:
        try:
            return real(answer)  # type: ignore[arg-type]
        except staff_directories.DirectorySignInError as why:
            msg = f"{why} acceptance-{fixed}"
            raise staff_directories.DirectorySignInError(msg) from why

    monkeypatch.setattr(staff_directories, "token_from", repeating)
    assert "repeated" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_wrong_code_refused_in_another_voice_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate refusing in different words each time. Delete this and M42.5.7 closes on a screen
    that tells a prober whether this product is here."""
    from brain import setup_staff_routes
    from brain.core.errors import Absent

    class Other(Absent):
        public_message = "Something else is here."

    calls: list[int] = []

    def varying() -> Absent:
        calls.append(1)
        return Absent("nothing") if len(calls) % 2 else Other("nothing")

    monkeypatch.setattr(setup_staff_routes, "_nothing_here", varying)
    assert "unlike" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_finish_that_binds_nothing_new_fails_the_finishing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bind that reported a binding that already existed. Delete this and M42.5.14 closes on a
    screen that tells the installer they are signed in when this call did nothing."""
    from brain.identity.sign_in_binding import Binding
    from brain.ops import acceptance_checks_first_run_walk as walk

    async def nothing(self: object, subject: str, **kwargs: object) -> Binding:
        return Binding.ALREADY_BOUND

    monkeypatch.setattr(walk._NobodyIsSignedInYet, "bind", nothing)
    assert "did not bind" in _failed(install, FINISH)


@pytest.mark.needs_db
def test_a_finish_that_binds_somebody_else_fails_the_finishing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The token bound to another person than the one the code was given for. Delete this and
    M42.5.14 closes on a screen that signs the installer in as somebody they did not choose."""
    from brain.ops import acceptance_checks_first_run_walk as walk

    async def elsewhere(self: walk._NobodyIsSignedInYet, subject: str, **kwargs: str) -> object:
        kwargs["principal_id"] = kwargs["principal_id"].replace("finishing", "finishing_later", 1)
        return await self.real.bind(subject, **kwargs)

    monkeypatch.setattr(walk._NobodyIsSignedInYet, "bind", elsewhere)
    assert "sign in" in _failed(install, FINISH)


@pytest.mark.needs_db
def test_a_finishing_screen_that_refuses_in_two_voices_fails_the_finishing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refusals that differ by cause. Delete this and M42.5.14 closes on a screen that tells
    somebody holding an old code why it was turned away."""
    from brain import sign_in_routes
    from brain.core.errors import Absent

    class Other(Absent):
        public_message = "Something else is here."

    calls: list[int] = []

    def varying() -> Absent:
        calls.append(1)
        return Absent("nothing") if len(calls) % 2 else Other("nothing")

    monkeypatch.setattr(sign_in_routes, "_nothing_to_finish", varying)
    assert "more than one way" in _failed(install, FINISH)


@pytest.mark.needs_db
def test_a_directory_refusal_that_does_not_stop_the_trial_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused sign-in carried on with a token anyway. Delete this and M42.5.7 closes on a trial
    that reads a directory the vendor refused to let it into."""
    import secrets
    from types import SimpleNamespace

    from brain.ops import acceptance_checks_first_run_walk as walk

    fixed = "ab" * 12
    monkeypatch.setattr(
        walk,
        "secrets",
        SimpleNamespace(token_hex=lambda n: fixed, token_urlsafe=secrets.token_urlsafe),
    )

    real = exchange

    async def carrying_on(fetch: object, source: str, **kwargs: str) -> str:
        if kwargs["code"] == "ANOTHER-CODE":
            return f"token-{fixed}"
        return await real(fetch, source, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("brain.setup_staff_routes.exchange", carrying_on)
    assert "still gave a plan" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_an_install_with_a_staff_source_already_saved_passes_the_staff_check_and_keeps_it(
    install: str,
) -> None:
    """**The owner's install, which the scratch database hid.** A finished install has saved a staff
    source, and installation values put a saved one before the one a trial is handed, so the
    trial read the owner's source instead of the pasted list. The check sets what is saved aside
    for its reads and puts it back. Delete this and M42.5.7 fails on every install that has
    chosen where its staff list lives, which is every install that is finished."""
    from brain.install import hold_saved, saved_values

    saved = {
        "INSTALL_STAFF_SOURCE": "lark",
        "INSTALL_STAFF_SOURCE_LOCATION": "example.invalid",
    }
    before = hold_saved(saved)
    try:
        assert run_module(install, STAFF)[STAFF] == (PASSED, "")
        assert dict(saved_values()) == saved
    finally:
        hold_saved(before)


@pytest.mark.needs_db
def test_a_trial_that_is_not_safe_to_apply_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan carrying a refusal of its own though the trial reported none. Delete this and
    M42.5.7 closes on a trial a person is told to apply while the plan itself says not to."""
    import dataclasses

    from brain.console.staff_source_view import rehearse

    def unsafe(*args: object, **kwargs: object) -> object:
        trial = rehearse(*args, **kwargs)  # type: ignore[arg-type]
        assert trial.plan is not None
        return dataclasses.replace(trial, plan=dataclasses.replace(trial.plan, refusals=("x",)))

    monkeypatch.setattr("brain.setup_staff_routes.rehearse", unsafe)
    assert "safe to apply" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_first_run_that_deactivates_somebody_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first run proposing to deactivate a person on an empty install. Delete this and M42.5.7
    closes on a trial that frightens a person with a deactivation nobody could make."""
    import dataclasses

    from brain.console.staff_source_view import rehearse

    def deactivating(*args: object, **kwargs: object) -> object:
        trial = rehearse(*args, **kwargs)  # type: ignore[arg-type]
        assert trial.plan is not None
        plan = dataclasses.replace(trial.plan, would_deactivate=("someone@x.invalid",))
        return dataclasses.replace(trial, plan=plan)

    monkeypatch.setattr("brain.setup_staff_routes.rehearse", deactivating)
    assert "deactivating" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_directory_that_reads_one_person_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A walk that stopped after the first person. Delete this and M42.5.7 closes on a trial that
    tells a company its directory holds one person."""
    from brain.identity.staff_adapters import MicrosoftEntraSource
    from brain.ops import acceptance_checks_first_run_walk as walk

    async def one_person(*args: object, **kwargs: object) -> MicrosoftEntraSource:
        return MicrosoftEntraSource(pages=[{"value": [walk._person(1, "Ada One", "ada")]}])

    monkeypatch.setattr("brain.setup_staff_routes.pull", one_person)
    assert "two people" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_an_exchange_made_twice_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The secret sent to the vendor more than once. Delete this and M42.5.7 closes on a screen
    that exposes a company's client secret to the vendor twice for one sign-in."""
    from brain.connectors.staff_directories import exchange

    async def twice(fetch: object, source: str, **kwargs: str) -> str:
        await exchange(fetch, source, **kwargs)  # type: ignore[arg-type]
        return await exchange(fetch, source, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("brain.setup_staff_routes.exchange", twice)
    assert "exactly once" in _failed(install, STAFF)


@pytest.mark.needs_db
def test_a_spaced_secret_that_reaches_the_directory_fails_the_staff_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A secret with a space sent on though the directory then refuses it. Delete this and
    M42.5.7 closes on a screen that sends what was pasted to a vendor and only then judges it."""
    from brain.ops import acceptance_checks_first_run_walk as walk

    class Refusing(walk._Directory):
        def __init__(self, secret: str, token: str) -> None:
            super().__init__("never", token)

    real = walk._Directory
    monkeypatch.setattr("brain.setup_staff_routes.secret_problem", lambda secret: "")

    def either(secret: str, token: str) -> walk._Directory:
        return real(secret, token) if "space" not in secret else Refusing(secret, token)

    monkeypatch.setattr(walk, "_Directory", either)
    assert "sent to the directory" in _failed(install, STAFF)
