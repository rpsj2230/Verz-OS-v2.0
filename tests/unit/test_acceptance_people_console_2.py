"""Sessions, sign-in links, sign-in strength, the ledger and exports: install checks on PostgreSQL.

The database half runs the module as the worker does, with the install's issuer set: every check
passes and leaves nothing, except the realm's second factor, which is not run until a console
session with a second factor is on record and passes once one is. Then each check is shown failing
with the product broken the way it would plausibly break: an ended session still answered, an
unlink that unlinks nothing, a password sign-in told nothing, a token's authenticator ignored, the
ledger and the export shown whole to a reader of part of it, a revoked key still answered, and the
people list shown whole.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.7.10, M27.7.11, M27.9.1, M27.9.2, M27.15.60, M27.15.66, M27.7.13, M27.9.4, M27.11.5,
M27.15.21
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_people_console_2 as second
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_people_console_2"
SESSIONS = "an_ended_session_is_refused_on_its_next_request"
LINKS = "an_unlinked_sign_in_is_refused_on_its_next_request"
STRENGTH = "a_sign_in_without_a_second_factor_is_told_what_it_holds_back"
REALM = "a_second_factor_reported_by_the_realm_admits_administration"
LEDGER = "the_ledger_narrows_by_actor_without_naming_what_is_withheld"
FIRST = "the_first_administrator_opens_routing_and_exports_what_they_read"
KEYS = "a_service_account_key_is_shown_once_rotated_and_revoked"
EXPORTS = "the_certification_and_lists_export_only_what_the_exporter_reads"


def test_the_second_people_console_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [SESSIONS, LINKS, STRENGTH, REALM, LEDGER, FIRST, KEYS, EXPORTS]


def test_each_check_closes_the_leaves_its_flow_exercises() -> None:
    """Delete this and a check can lose or gain a leaf with the page showing the same rows."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        SESSIONS: ("M27.7.10",),
        LINKS: ("M27.7.11",),
        STRENGTH: ("M27.9.2", "M27.15.60", "M27.15.66"),
        REALM: ("M27.9.1",),
        LEDGER: ("M27.7.13",),
        FIRST: ("M27.9.4",),
        KEYS: ("M27.11.5",),
        EXPORTS: ("M27.15.21",),
    }


def test_a_password_withholds_what_the_admission_rules_say_it_does() -> None:
    """The verbs the strength check expects a password sign-in to be told about, held against
    `brain.gate.admission` rather than against this module: the console's verbs no
    `AUTHENTICATED` sign-in carries. Delete this and a change to the admission rules turns the
    strength check red on every install, or green on a wrong expectation."""
    from brain.gate.admission import ASSURANCE_VERBS, CHANNEL_VERBS, Assurance
    from brain.gate.context import Channel

    console = CHANNEL_VERBS[Channel.CONSOLE]
    assert tuple(sorted(console - ASSURANCE_VERBS[Assurance.AUTHENTICATED])) == (
        second.WITHHELD_FROM_A_PASSWORD
    )
    assert console <= ASSURANCE_VERBS[Assurance.STRONG]


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_people_2") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str, *names: str) -> dict[str, tuple[str, str]]:
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    return run_check(url, checks)


def failed(url: str, name: str) -> str:
    [(outcome, reason)] = run(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str, issuer: None) -> None:
    """**The module as the worker runs it.** Every check passes and nothing a check wrote is left;
    the realm's second factor is not run, because nobody here has signed in with one. Delete this
    and a check that can never pass on a real schema, or one that commits a session, a key or an
    export record, reaches the owner's server first."""
    before = counts(install)
    outcomes = run(install)
    assert outcomes.pop(REALM) == (NOT_RUN, second.NOBODY_HAS_SIGNED_IN_WITH_AN_AUTHENTICATOR)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 7
    assert counts(install) == before


@pytest.mark.needs_db
def test_the_realm_check_passes_once_somebody_has_signed_in_with_a_second_factor(
    install: str, issuer: None
) -> None:
    """A console session with a second factor, recorded as the gate records one for a person who
    is not a reserved principal, and the realm check passes. Delete this and M27.9.1 can close on
    a check that can never pass, or one that passes before anybody has signed in strongly."""
    from tests.fixtures.scratch_postgres import sql

    sql(
        install,
        "INSERT INTO auth.principal (id, kind, employment, display_name)"
        " VALUES ('u_strong_signin', 'human', 'staff', 'Somebody strong')"
        " ON CONFLICT DO NOTHING",
    )
    sql(
        install,
        "INSERT INTO auth.session (id, principal_id, channel, assurance, started_at, expires_at)"
        " VALUES ('strong-session', 'u_strong_signin', 'console', 3, now(), now() + interval"
        " '5 minutes') ON CONFLICT DO NOTHING",
    )
    assert run(install, REALM) == {REALM: (PASSED, "")}


@pytest.mark.needs_db
def test_an_ended_session_still_answered_fails_the_sessions_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ledger recording every session as it does and answering an ended one as open.
    Delete this and M27.7.10 closes on a control whose session goes on answering."""
    from brain.identity.bearer import SessionStanding
    from brain.identity.session_store import StoredSessions

    recorded = StoredSessions.standing

    async def never_ended(self: Any, **how: Any) -> SessionStanding:
        found = await recorded(self, **how)
        return SessionStanding.OPEN if found is SessionStanding.ENDED else found

    monkeypatch.setattr(StoredSessions, "standing", never_ended)
    assert "next request was answered" in failed(install, SESSIONS)


@pytest.mark.needs_db
def test_an_unlink_that_unlinks_nothing_fails_the_links_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store saying a link was removed and leaving it. Delete this and M27.7.11 closes on an
    unlink the person signs in straight through."""
    from brain.identity.sign_in_binding import SignInBindings, Unlinked

    async def pretend(self: Any, principal_id: str, **_: Any) -> Unlinked:
        return Unlinked.UNLINKED

    monkeypatch.setattr(SignInBindings, "unlink", pretend)
    assert "next request was answered" in failed(install, LINKS)


@pytest.mark.needs_db
def test_a_password_sign_in_told_nothing_fails_the_strength_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`asking` working out no withheld verb. Delete this and M27.9.2 closes on a sign-in that is
    refused without being told why."""
    from brain import api_routes

    monkeypatch.setattr(api_routes, "verbs_withheld", lambda held, channel, assurance: ())
    assert "which verbs" in failed(install, STRENGTH)


@pytest.mark.needs_db
def test_an_authenticator_ignored_fails_the_realm_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every token read as a password sign-in whatever its `amr` says. Delete this and M27.9.1
    closes on a gate that never lets an administrator administer."""
    from brain.gate.admission import Assurance
    from brain.identity import bearer

    monkeypatch.setattr(bearer, "assurance_from", lambda claims: Assurance.AUTHENTICATED)
    assert "not read as strong" in failed(install, REALM)


@pytest.mark.needs_db
def test_the_ledger_shown_whole_fails_the_ledger_and_export_checks(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every entry shown to every reader of the audit trail. Delete this and M27.7.13 and M27.9.4
    close on a ledger and an export that narrow nothing."""
    from brain.audit.view import AuditView

    monkeypatch.setattr(AuditView, "_may_see", lambda self, entry: True)
    assert "unlike an actor nobody is" in failed(install, LEDGER)
    assert "only it" in failed(install, FIRST)


@pytest.mark.needs_db
def test_a_revocation_that_revokes_nothing_fails_the_keys_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store saying a key was revoked and leaving it live. Delete this and M27.11.5 closes on
    a key that outlives its revocation."""
    from brain.identity.service_account_store import StoredServiceAccounts

    async def pretend(self: Any, handle: str, **_: Any) -> bool:
        return True

    monkeypatch.setattr(StoredServiceAccounts, "revoke_key", pretend)
    assert "revoked key was answered" in failed(install, KEYS)


@pytest.mark.needs_db
def test_the_people_list_shown_whole_fails_the_exports_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every person named to every reader of People. Delete this and M27.15.21 closes on a list
    whose export carries people the exporter may not read."""
    from brain import directory_routes

    monkeypatch.setattr(directory_routes, "nameable", lambda members, reach, now: list(members))
    assert "outside the reader's department" in failed(install, EXPORTS)
