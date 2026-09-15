"""A subject is bound to a principal only on purpose: exactly as the token carries it, at the
configured issuer, to a live principal, by somebody else, never moving an existing binding.

The first half is `decide` and needs no server. The second builds `0002` and `0003` as
`tests.unit.test_principal_directory` does and drives `SignInBindings` as the application role,
proving each binding through `StoredDirectory` and, once, through a real `keycloak_authority`
with a token signed in the test. It skips when there is no server.

Task ids: M1.2.2
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from brain.core.principal import Employment, Principal, PrincipalKind
from brain.db import normalise_database_url
from brain.identity.keycloak_tokens import keycloak_authority
from brain.identity.oidc import TokenRefusal, TokenRefusedError
from brain.identity.principal_directory import SIGN_IN_CHANNEL, StoredDirectory, subject_digest
from brain.identity.roles import IdentityError
from brain.identity.sign_in_binding import (
    Binding,
    BindingRefusal,
    SignInBindingRefusedError,
    SignInBindings,
    decide,
    sign_in_bindings,
)
from brain.install import InstallError
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.fixtures.retirable import retirable
from tests.unit.test_entitlement_store import LONG_AGO, a_principal, resolver
from tests.unit.test_keycloak_tokens import ISSUER, NOW, Clock, Idp, token

OTHER_ISSUER = "https://id.example.com/realms/another"
#: After `NOW` in `test_keycloak_tokens`, so an engagement ending here is still running then.
LATER = datetime(2999, 1, 1, tzinfo=UTC)


def live(principal_id: str = "u_joiner", *, not_after: datetime | None = None) -> Principal:
    employment = Employment.STAFF if not_after is None else Employment.CONTRACTOR
    return Principal(
        id=principal_id,
        kind=PrincipalKind.HUMAN,
        employment=employment,
        display_name=f"Person {principal_id}",
        not_after=not_after,
    )


def decided(
    subject: str = "s-joiner",
    *,
    principal_id: str = "u_joiner",
    bound_by: str = "u_admin",
    principal: Principal | None = None,
    subject_holder: str | None = None,
    principal_signs_in: bool = False,
) -> Binding:
    return decide(
        subject,
        principal_id=principal_id,
        bound_by=bound_by,
        principal=live(principal_id) if principal is None else principal,
        subject_holder=subject_holder,
        principal_signs_in=principal_signs_in,
        now=NOW,
    )


def refusal(**changed: Any) -> BindingRefusal:
    with pytest.raises(SignInBindingRefusedError) as refused:
        decided(**changed)
    return refused.value.reason


# ------------------------------------------------------------------------- the decision


def test_an_unheld_subject_is_bound_to_a_live_principal_with_no_sign_in() -> None:
    """The positive case for every refusal below. Delete it and a decision that refuses everything
    passes all of them, and nobody can ever be given a sign-in."""
    assert decided() is Binding.BOUND


def test_a_contractor_inside_their_engagement_is_bound_and_one_past_it_is_not() -> None:
    """The engagement is judged at the call's instant. Delete this and a contractor whose end date
    has passed can be given a way in, which `oidc.principal_for` refuses later but an audit of
    bindings would show as a deliberate grant."""
    assert decided(principal=live(not_after=LATER)) is Binding.BOUND
    assert refusal(principal=live(not_after=LONG_AGO)) is BindingRefusal.NO_LIVE_PRINCIPAL


def test_a_principal_not_here_cannot_be_bound() -> None:
    """Absent, disabled and deleted all read as None from the store. Delete this and a binding can
    be written ahead of a principal, and whoever is later created under that id inherits it."""
    with pytest.raises(SignInBindingRefusedError) as refused:
        decide(
            "s-joiner",
            principal_id="u_joiner",
            bound_by="u_admin",
            principal=None,
            subject_holder=None,
            principal_signs_in=False,
            now=NOW,
        )
    assert refused.value.reason is BindingRefusal.NO_LIVE_PRINCIPAL


@pytest.mark.parametrize("subject", ["", " s-joiner", "s-joiner ", "s-joiner\n"])
def test_a_subject_not_exactly_as_a_token_carries_it_is_refused(subject: str) -> None:
    """See `A_SUBJECT_IS_BOUND_EXACTLY_AS_PRESENTED`. Delete this and a pasted subject with a
    trailing newline is bound under a digest no token will ever produce, or an empty one is."""
    assert refusal(subject=subject) is BindingRefusal.SUBJECT_NOT_EXACT


def test_a_subject_differing_only_in_case_is_bound_as_given() -> None:
    """The sibling of the exactness refusal: case is not whitespace, and is kept. Delete this and
    the check can grow a casefold, which `principal_directory.A_SUBJECT_IS_COMPARED_EXACTLY`
    forbids."""
    assert decided(subject="S-Joiner") is Binding.BOUND


def test_nobody_binds_a_sign_in_to_their_own_principal() -> None:
    """See `NOBODY_BINDS_THEIR_OWN_SIGN_IN`. Delete this and a stolen administrator session can
    attach the thief's own Keycloak account to the administrator's principal."""
    assert refusal(bound_by="u_joiner") is BindingRefusal.OWN_SIGN_IN


def test_a_subject_bound_to_somebody_else_is_refused_and_the_refusal_does_not_say_who() -> None:
    """See `A_BINDING_NEVER_MOVES`. Delete this and binding a subject that is already held moves it,
    and the person it was bound to is signed in as somebody else from then on."""
    with pytest.raises(SignInBindingRefusedError) as refused:
        decided(subject_holder="u_holder")
    assert refused.value.reason is BindingRefusal.SUBJECT_BOUND_ELSEWHERE
    assert "u_holder" not in str(refused.value)


def test_the_same_binding_asked_for_again_is_already_bound() -> None:
    """A retry is not a refusal and writes nothing. Delete this and a timed-out request retried by
    an administrator either fails or inserts a second row for one subject."""
    assert decided(subject_holder="u_joiner", principal_signs_in=True) is Binding.ALREADY_BOUND


def test_a_principal_that_already_signs_in_is_refused_a_second_subject() -> None:
    """Delete this and a re-created Keycloak account becomes an additional way into the principal
    that nobody retires, alongside the old account's subject."""
    assert refusal(principal_signs_in=True) is BindingRefusal.PRINCIPAL_ALREADY_SIGNS_IN


def test_a_retry_for_somebody_disabled_since_is_refused_rather_than_already_bound() -> None:
    """Liveness is decided before idempotence. Delete this and the order can swap, and an
    administrator binding a disabled person is told all is well."""
    with pytest.raises(SignInBindingRefusedError) as refused:
        decide(
            "s-joiner",
            principal_id="u_joiner",
            bound_by="u_admin",
            principal=None,
            subject_holder="u_joiner",
            principal_signs_in=True,
            now=NOW,
        )
    assert refused.value.reason is BindingRefusal.NO_LIVE_PRINCIPAL


# ------------------------------------------------------------------------- the issuer


def unconnected() -> async_sessionmaker[AsyncSession]:
    """A session factory over an engine that is never asked to connect."""
    return make_session_factory(create_async_engine("postgresql+psycopg://nobody@127.0.0.1/none"))


def test_the_writer_binds_at_the_installations_issuer() -> None:
    """See `THE_BINDING_IS_MADE_AT_THE_CONFIGURED_ISSUER_ONLY`. Delete this and the writer can read
    another setting, and every binding is written where no token will find it."""
    writer = sign_in_bindings(unconnected(), env={"INSTALL_OIDC_ISSUER": ISSUER})
    assert writer.issuer == ISSUER


def test_no_writer_is_built_without_an_issuer_or_for_one_no_token_matches() -> None:
    """Delete this and a process with no issuer, or one ending in a slash, builds a writer whose
    every binding is unusable, and nobody finds out until nobody can sign in."""
    with pytest.raises(InstallError):
        sign_in_bindings(unconnected(), env={})
    with pytest.raises(IdentityError):
        sign_in_bindings(unconnected(), env={"INSTALL_OIDC_ISSUER": f"{ISSUER}/"})


# ----------------------------------------------------------------------- the database


def with_bindings[T](url: str, work: Callable[[SignInBindings], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(
                sign_in_bindings(make_session_factory(engine), env={"INSTALL_OIDC_ISSUER": ISSUER})
            )
        finally:
            await engine.dispose()

    return run(go)


def bind(url: str, subject: str, principal_id: str, *, bound_by: str = "u_admin") -> Binding:
    return with_bindings(
        url,
        lambda writer: writer.bind(subject, principal_id=principal_id, bound_by=bound_by, now=NOW),
    )


def refused_bind(url: str, subject: str, principal_id: str) -> BindingRefusal:
    with pytest.raises(SignInBindingRefusedError) as refused:
        bind(url, subject, principal_id)
    return refused.value.reason


def found(url: str, subject: str, issuer: str = ISSUER) -> str | None:
    async def go() -> str | None:
        engine = app_engine(url)
        try:
            principal = await StoredDirectory(make_session_factory(engine)).principal_for_subject(
                issuer, subject
            )
            return None if principal is None else principal.id
        finally:
            await engine.dispose()

    return run(go)


def live_rows(url: str) -> list[tuple[str, str]]:
    return [
        (str(principal_id), str(digest))
        for principal_id, digest in sql(
            url,
            "SELECT principal_id, identity_hash FROM auth.principal_identity"
            " WHERE channel = %s AND deleted_at IS NULL ORDER BY principal_id",
            SIGN_IN_CHANNEL.value,
        )
    ]


def test_a_chat_binding_or_somebody_elses_sign_in_is_not_this_principal_signing_in() -> None:
    """A Lark binding under the very digest being bound, and another person's console binding, are
    both beside the point. Delete this and either read can lose its channel or principal clause,
    and a person with a chat binding, or everybody once one person signs in, is refused."""
    with resolver("brain_sib_others") as url:
        a_principal(url, "u_joiner")
        a_principal(url, "u_other")
        bind(url, "s-other", "u_other")
        sql(
            url,
            "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at)"
            " VALUES ('lark', %s, 'u_joiner', now())",
            subject_digest(ISSUER, "s-joiner"),
        )
        outcome = bind(url, "s-joiner", "u_joiner")
        holder = found(url, "s-joiner")

    assert (outcome, holder) == (Binding.BOUND, "u_joiner")


def test_a_retired_subject_is_free_whatever_the_connection_role() -> None:
    """Retired bindings are filtered by the query as well as hidden by the policy, because a
    connection that is not the application role bypasses the policy. Delete this and the filter
    can go with every other test green, and on such a connection a subject retired at offboarding
    is refused for ever as bound elsewhere."""
    with resolver("brain_sib_superuser") as url:
        a_principal(url, "u_leaver")
        a_principal(url, "u_joiner")
        bind(url, "s-reused", "u_leaver")
        retired_by_an_operator(url, "u_leaver")

        async def go() -> Binding:
            engine = create_async_engine(normalise_database_url(url), poolclass=NullPool)
            try:
                writer = sign_in_bindings(
                    make_session_factory(engine), env={"INSTALL_OIDC_ISSUER": ISSUER}
                )
                return await writer.bind(
                    "s-reused", principal_id="u_joiner", bound_by="u_admin", now=NOW
                )
            finally:
                await engine.dispose()

        outcome = run(go)
        holder = found(url, "s-reused")

    assert (outcome, holder) == (Binding.BOUND, "u_joiner")


def test_a_bind_waits_for_whatever_holds_the_principal() -> None:
    """The principal is read `FOR UPDATE`, so two binds for one principal are serialised. Another
    connection holds the row and the bind is given a short lock timeout, so it must give up rather
    than read past. The hold is `FOR NO KEY UPDATE` and not `FOR UPDATE` on purpose: the insert's
    foreign key takes a share lock that `FOR UPDATE` would block too, so a bind with no lock of
    its own would time out as well and the test would watch nothing, which the first mutation run
    found. Delete this and the lock can go, and two administrators binding two subjects
    to one principal at once both see it unbound and both write."""
    with resolver("brain_sib_lock") as url:
        a_principal(url, "u_joiner")
        with psycopg.connect(url) as holding:
            holding.execute("SELECT id FROM auth.principal WHERE id = 'u_joiner' FOR NO KEY UPDATE")

            async def go() -> str:
                engine = create_async_engine(
                    normalise_database_url(url),
                    poolclass=NullPool,
                    connect_args={"options": "-c role=brain_app -c lock_timeout=200"},
                )
                try:
                    writer = sign_in_bindings(
                        make_session_factory(engine), env={"INSTALL_OIDC_ISSUER": ISSUER}
                    )
                    await writer.bind(
                        "s-joiner", principal_id="u_joiner", bound_by="u_admin", now=NOW
                    )
                except DBAPIError as waited:
                    return type(waited.orig).__name__
                finally:
                    await engine.dispose()
                return "bound"

            outcome = run(go)
            holding.rollback()
        rows = live_rows(url)

    assert outcome == "LockNotAvailable"
    assert rows == []


def test_a_bound_subject_is_found_by_the_directory_at_the_configured_issuer_only() -> None:
    """The write and the read agree on the digest. Delete this and a writer keyed differently from
    `StoredDirectory` passes every refusal test while no binding it writes is ever found."""
    with resolver("brain_sib_found") as url:
        a_principal(url, "u_joiner")
        outcome = bind(url, "s-joiner", "u_joiner")
        at_ours = found(url, "s-joiner")
        at_another = found(url, "s-joiner", OTHER_ISSUER)
        rows = live_rows(url)

    assert outcome is Binding.BOUND
    assert (at_ours, at_another) == ("u_joiner", None)
    assert rows == [("u_joiner", subject_digest(ISSUER, "s-joiner"))]


def test_binding_the_same_subject_twice_writes_one_row() -> None:
    """Delete this and the idempotent path can insert anyway, which the unique index turns into a
    fault on every retried request."""
    with resolver("brain_sib_twice") as url:
        a_principal(url, "u_joiner")
        first = bind(url, "s-joiner", "u_joiner")
        second = bind(url, "s-joiner", "u_joiner")
        rows = live_rows(url)

    assert (first, second) == (Binding.BOUND, Binding.ALREADY_BOUND)
    assert len(rows) == 1


def test_a_held_subject_is_refused_for_another_principal_and_the_first_binding_stands() -> None:
    """Through the database, the binding does not move. Delete this and the store can skip the
    holder read, and the second insert's conflict is the only thing standing in the way."""
    with resolver("brain_sib_held") as url:
        a_principal(url, "u_first")
        a_principal(url, "u_second")
        bind(url, "s-shared", "u_first")
        reason = refused_bind(url, "s-shared", "u_second")
        holder = found(url, "s-shared")
        rows = live_rows(url)

    assert reason is BindingRefusal.SUBJECT_BOUND_ELSEWHERE
    assert holder == "u_first"
    assert [one for one, _ in rows] == ["u_first"]


def retired_by_an_operator(url: str, principal_id: str) -> None:
    """Retirement as a statement on the server's own login, which bypasses the policy. Kept for
    the tests that retire in order to bind; `test_the_store_retires_a_sign_in_binding_as_the_application_role`
    is the store's own."""
    sql(
        url,
        "UPDATE auth.principal_identity SET deleted_at = now()"
        " WHERE principal_id = %s AND channel = %s AND deleted_at IS NULL",
        principal_id,
        SIGN_IN_CHANNEL.value,
    )


def test_a_second_subject_waits_for_the_first_to_be_retired() -> None:
    """Moving a principal's sign-in is retire and then bind. Delete this and the store can stop
    reading the principal's own binding, so two subjects sign in as one person, or can read retired
    rows as live, so a re-created account can never be bound."""
    with resolver("brain_sib_move") as url:
        a_principal(url, "u_joiner")
        bind(url, "s-old", "u_joiner")
        reason = refused_bind(url, "s-new", "u_joiner")
        retired_by_an_operator(url, "u_joiner")
        rebound = bind(url, "s-new", "u_joiner")
        old, new = found(url, "s-old"), found(url, "s-new")

    assert reason is BindingRefusal.PRINCIPAL_ALREADY_SIGNS_IN
    assert rebound is Binding.BOUND
    assert (old, new) == (None, "u_joiner")


def test_a_retired_subject_can_be_bound_to_somebody_new() -> None:
    """Once released on purpose, a subject is free. Delete this and the holder read can count
    retired rows, and a subject retired at offboarding is refused for ever."""
    with resolver("brain_sib_release") as url:
        a_principal(url, "u_leaver")
        a_principal(url, "u_joiner")
        bind(url, "s-reused", "u_leaver")
        retired_by_an_operator(url, "u_leaver")
        rebound = bind(url, "s-reused", "u_joiner")
        holder = found(url, "s-reused")

    assert (rebound, holder) == (Binding.BOUND, "u_joiner")


def test_the_store_retires_a_sign_in_binding_as_the_application_role() -> None:
    """This pinned the opposite until 0045 repaired the policy. Delete it and a retire can be
    written that passes every test retiring as the superuser and fails on the first real
    offboarding. The bind beforehand, as the same role, proves the role writes; the binding gone
    from the directory afterwards is the retirement having landed."""
    with retirable("brain_sib_retire") as url:
        a_principal(url, "u_leaver")
        bind(url, "s-leaver", "u_leaver")
        retired = with_bindings(url, lambda writer: writer.retire("u_leaver", retired_by="u_admin"))
        holder = found(url, "s-leaver")

    assert (retired, holder) == (True, None)


def test_retiring_a_principal_with_no_sign_in_retires_nothing() -> None:
    """The sibling. Delete this and a retire that reports success whatever it wrote passes the
    test above."""
    with retirable("brain_sib_retire_none") as url:
        a_principal(url, "u_never_bound")
        retired = with_bindings(
            url, lambda writer: writer.retire("u_never_bound", retired_by="u_admin")
        )

    assert retired is False


@pytest.mark.parametrize("gone", ["disabled_at", "deleted_at"])
def test_a_disabled_or_deleted_principal_is_not_bound(gone: str) -> None:
    """Through the database, beside a live principal that is. Delete this and the store can bind
    whatever id it is handed, and a re-enabled or restored account arrives with a sign-in nobody
    chose for it."""
    with resolver(f"brain_sib_{gone[:-3]}") as url:
        a_principal(url, "u_live")
        a_principal(url, "u_gone")
        sql(url, f"UPDATE auth.principal SET {gone} = now() WHERE id = 'u_gone'")  # noqa: S608
        positive = bind(url, "s-live", "u_live")
        reason = refused_bind(url, "s-gone", "u_gone")
        rows = live_rows(url)

    assert positive is Binding.BOUND
    assert reason is BindingRefusal.NO_LIVE_PRINCIPAL
    assert [one for one, _ in rows] == ["u_live"]


def test_a_bind_that_loses_the_race_for_a_subject_writes_nothing_and_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """See `THE_RACE_IS_LOST_BY_WRITING_NOTHING`. The holder read is made to miss, which is what a
    concurrent bind sees. Delete this and the conflict branch can go, and the loser either raises a
    unique violation as a fault or reports a binding that was never written."""
    with resolver("brain_sib_race") as url:
        a_principal(url, "u_first")
        a_principal(url, "u_second")
        bind(url, "s-contested", "u_first")

        async def missed(self: SignInBindings, session: AsyncSession, digest: str) -> None:
            return None

        monkeypatch.setattr(SignInBindings, "_holder", missed)
        reason = refused_bind(url, "s-contested", "u_second")
        monkeypatch.undo()
        holder = found(url, "s-contested")
        rows = live_rows(url)

    assert reason is BindingRefusal.SUBJECT_BOUND_ELSEWHERE
    assert holder == "u_first"
    assert [one for one, _ in rows] == ["u_first"]


def test_a_valid_token_is_refused_until_its_subject_is_bound_and_accepted_after() -> None:
    """The whole path, and the reason this module exists: a real authority, a realm-signed token,
    the directory and this writer. Delete this and each half can be proved alone while the gate
    still refuses every person in the company."""
    with resolver("brain_sib_authority") as url:
        a_principal(url, "u_joiner")

        async def go() -> tuple[TokenRefusal, str]:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                authority = keycloak_authority(
                    directory=StoredDirectory(sessions),
                    get=Idp().get,
                    clock=Clock(),
                    env={"INSTALL_OIDC_ISSUER": ISSUER},
                )
                presented = f"Bearer {token(sub='s-joiner')}"
                try:
                    await authority.authenticate(presented, now=NOW)
                except TokenRefusedError as refused:
                    before = refused.reason
                writer = sign_in_bindings(sessions, env={"INSTALL_OIDC_ISSUER": ISSUER})
                await writer.bind("s-joiner", principal_id="u_joiner", bound_by="u_admin", now=NOW)
                caller = await authority.authenticate(presented, now=NOW)
                return before, caller.principal.id
            finally:
                await engine.dispose()

        before, after = run(go)

    assert (before, after) == (TokenRefusal.NO_PRINCIPAL, "u_joiner")
