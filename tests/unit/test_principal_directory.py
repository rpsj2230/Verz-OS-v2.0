"""A sign-in subject is found through `auth.principal_identity` as the application role, and every
way of not being here is one absence, refused in one sentence by the token authority.

The first half is the digest a subject is bound under and needs no server. The second builds
`0002` and `0003` as `tests.unit.test_entitlement_store` does and drives
`brain.identity.principal_directory.StoredDirectory`, alone and behind a real
`keycloak_authority` with a token signed in the test. It skips when there is no server.

Task ids: M1.2.2
"""

from __future__ import annotations

import re
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from structlog.testing import capture_logs

from brain.core.principal import Principal
from brain.db import normalise_database_url
from brain.identity.keycloak_tokens import keycloak_authority
from brain.identity.oidc import SIGN_IN_PROMPT, TokenRefusal, TokenRefusedError
from brain.identity.principal_directory import SIGN_IN_CHANNEL, StoredDirectory, subject_digest
from brain.session import make_session_factory
from brain.tables.identity import IDENTITY_HASH_PATTERN
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_entitlement_store import a_principal, resolver
from tests.unit.test_keycloak_tokens import ISSUER, NOW, SUBJECT, Clock, Idp, token

OTHER_ISSUER = "https://id.example.com/realms/another"

#: The digest of `SUBJECT` at `ISSUER`, worked out once by hand from the length-prefixed parts
#: `console`, the issuer and the subject. Every binding ever written is keyed by this formula.
BOUND_DIGEST = "990f738ecf7fd4ad0c45a56934e2872706226c373691c04653576afecf3895ed"


# ------------------------------------------------------------------------- the digest


def test_the_digest_a_subject_is_bound_under_does_not_change() -> None:
    """The storage format, pinned to a value rather than to the function. Delete this and a change
    to the channel, the prefixing or the normalisation passes every other test, and every binding
    already written stops being found, which refuses every person in the company at once."""
    assert subject_digest(ISSUER, SUBJECT) == BOUND_DIGEST
    assert re.fullmatch(IDENTITY_HASH_PATTERN, BOUND_DIGEST)


def test_a_subject_at_another_issuer_is_another_digest() -> None:
    """The issuer is part of the binding. Delete this and a directory keyed on the subject alone
    passes, and a token from a second realm naming the same subject is the first realm's person."""
    assert subject_digest(OTHER_ISSUER, SUBJECT) != subject_digest(ISSUER, SUBJECT)


def test_subjects_differing_only_in_case_are_different_digests() -> None:
    """See `A_SUBJECT_IS_COMPARED_EXACTLY`. Delete this and the digest can casefold, as
    `ingress.identity_hash` does, and two case-distinct subjects share one principal."""
    assert subject_digest(ISSUER, "Ada") != subject_digest(ISSUER, "ada")


def test_an_issuer_and_a_subject_cannot_be_shifted_into_another_pair() -> None:
    """The parts are length-prefixed. Delete this and a plain concatenation passes, and an issuer
    ending where a subject begins is a second route to one binding."""
    assert subject_digest("https://a.example/b", "c") != subject_digest("https://a.example/", "bc")


# ----------------------------------------------------------------------- the database


def bind(
    url: str,
    principal_id: str,
    subject: str,
    *,
    issuer: str = ISSUER,
    channel: str = SIGN_IN_CHANNEL.value,
) -> None:
    sql(
        url,
        "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at)"
        " VALUES (%s, %s, %s, now())",
        channel,
        subject_digest(issuer, subject),
        principal_id,
    )


def superuser_engine(url: str) -> AsyncEngine:
    """An engine on the server's own login, to which no row-level security policy applies."""
    return create_async_engine(normalise_database_url(url), poolclass=NullPool)


def looked_up(
    url: str,
    issuer: str,
    subject: str,
    *,
    engine: Callable[[str], AsyncEngine] = app_engine,
) -> Principal | None:
    async def go() -> Principal | None:
        made = engine(url)
        try:
            directory = StoredDirectory(make_session_factory(made))
            return await directory.principal_for_subject(issuer, subject)
        finally:
            await made.dispose()

    return run(go)


def test_a_bound_live_subject_is_the_principal_it_is_bound_to() -> None:
    """The positive case for every absence below. Delete it and a directory that finds nobody
    passes all of them, and no token is ever accepted."""
    with resolver("brain_pd_live") as url:
        a_principal(url, "u_signed_in")
        bind(url, "u_signed_in", "s-live")
        found = looked_up(url, ISSUER, "s-live")

    assert found is not None
    assert (found.id, found.display_name, found.primary_department) == (
        "u_signed_in",
        "Person u_signed_in",
        "finance",
    )


def test_a_disabled_a_deleted_an_unknown_and_another_issuers_subject_are_all_no_principal() -> None:
    """Every way of not being here is one answer, beside a subject that is here. Delete this and a
    disabled account, which the policy does not hide, signs in, or a binding made at one realm is
    honoured for a token from another."""
    with resolver("brain_pd_absent") as url:
        for principal_id in ("u_live", "u_disabled", "u_deleted"):
            a_principal(url, principal_id)
            bind(url, principal_id, f"s-{principal_id}")
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = %s", "u_disabled")
        sql(url, "UPDATE auth.principal SET deleted_at = now() WHERE id = %s", "u_deleted")
        present = looked_up(url, ISSUER, "s-u_live")
        absent = [
            looked_up(url, issuer, subject)
            for issuer, subject in (
                (ISSUER, "s-u_disabled"),
                (ISSUER, "s-u_deleted"),
                (ISSUER, "s-stranger"),
                (OTHER_ISSUER, "s-u_live"),
                (ISSUER, "S-U_LIVE"),
            )
        ]

    assert present is not None
    assert absent == [None, None, None, None, None]


def test_a_retired_binding_is_no_principal_whatever_the_connection_role() -> None:
    """Refused by the query as well as hidden by the policy, because a connection that is not the
    application role bypasses the policy. Delete this and a binding retired at offboarding still
    signs its old subject in on any process wired with the wrong role. The live binding read on
    the same connection proves that connection reads at all."""
    with resolver("brain_pd_retired") as url:
        a_principal(url, "u_live")
        a_principal(url, "u_moved")
        bind(url, "u_live", "s-live")
        bind(url, "u_moved", "s-retired")
        sql(
            url,
            "UPDATE auth.principal_identity SET deleted_at = now() WHERE principal_id = %s",
            "u_moved",
        )
        as_superuser = [
            looked_up(url, ISSUER, subject, engine=superuser_engine)
            for subject in ("s-live", "s-retired")
        ]
        as_application = looked_up(url, ISSUER, "s-retired")

    assert [one.id if one else None for one in as_superuser] == ["u_live", None]
    assert as_application is None


def test_a_binding_on_another_channel_is_not_a_sign_in() -> None:
    """A row under another channel with the same digest names nobody here. Delete this and the
    channel can drop out of the query, and a binding made by a chat channel's own flow becomes a
    way to sign in to the console."""
    with resolver("brain_pd_channel") as url:
        a_principal(url, "u_chat")
        bind(url, "u_chat", "s-chat", channel="lark")
        bind(url, "u_chat", "s-console")
        on_chat = looked_up(url, ISSUER, "s-chat")
        on_console = looked_up(url, ISSUER, "s-console")

    assert on_chat is None
    assert on_console is not None
    assert on_console.id == "u_chat"


def test_a_bound_principal_whose_row_does_not_construct_is_absent_and_logged() -> None:
    """One unreadable principal is one person who cannot sign in, and a line saying which. Delete
    this and the refusal can raise out of the directory, which turns one bad row into a fault on
    every sign-in attempt by that person with nothing naming the row."""
    with resolver("brain_pd_unreadable") as url:
        [(kind_check,)] = sql(
            url,
            "SELECT conname FROM pg_constraint WHERE conrelid = 'auth.principal'::regclass"
            " AND pg_get_constraintdef(oid) LIKE '%(kind)%'",
        )
        sql(url, f'ALTER TABLE auth.principal DROP CONSTRAINT "{kind_check}"')
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name)"
            " VALUES ('u_robot', 'robot', 'staff', 'Not a person')",
        )
        bind(url, "u_robot", "s-robot")
        with capture_logs() as logs:
            found = looked_up(url, ISSUER, "s-robot")

    assert found is None
    refused = [one.get("principal") for one in logs if one["event"] == "principal.record_refused"]
    assert refused == ["u_robot"]


def test_every_way_of_not_being_here_is_refused_in_one_sentence_by_the_authority() -> None:
    """Through the real authority, a realm-signed token and this directory. A live subject is
    accepted; disabled, deleted, retired and unknown subjects are all the same refusal with the
    same public sentence. Delete this and the directory is only ever proved alone, and a reason
    that distinguished an account that exists from one that does not could reach the presenter."""
    with resolver("brain_pd_authority") as url:
        for principal_id in ("u_live", "u_disabled", "u_deleted", "u_retired"):
            a_principal(url, principal_id)
            bind(url, principal_id, f"s-{principal_id}")
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = %s", "u_disabled")
        sql(url, "UPDATE auth.principal SET deleted_at = now() WHERE id = %s", "u_deleted")
        sql(
            url,
            "UPDATE auth.principal_identity SET deleted_at = now() WHERE principal_id = %s",
            "u_retired",
        )

        async def go() -> tuple[str, list[TokenRefusedError]]:
            engine = app_engine(url)
            try:
                authority = keycloak_authority(
                    directory=StoredDirectory(make_session_factory(engine)),
                    get=Idp().get,
                    clock=Clock(),
                    env={"INSTALL_OIDC_ISSUER": ISSUER},
                )
                caller = await authority.authenticate(f"Bearer {token(sub='s-u_live')}", now=NOW)
                refusals: list[TokenRefusedError] = []
                for subject in ("s-u_disabled", "s-u_deleted", "s-u_retired", "s-stranger"):
                    try:
                        await authority.authenticate(f"Bearer {token(sub=subject)}", now=NOW)
                    except TokenRefusedError as refused:
                        refusals.append(refused)
                return caller.principal.id, refusals
            finally:
                await engine.dispose()

        accepted, refusals = run(go)

    assert accepted == "u_live"
    assert [(one.reason, one.public_message) for one in refusals] == [
        (TokenRefusal.NO_PRINCIPAL, SIGN_IN_PROMPT)
    ] * 4
