"""The sign-in service's accounts, made, found, closed and opened, against a stand-in Keycloak.

`brain.connectors.sign_in_accounts` builds every request and sends none; the stand-in in
`tests/fixtures/stand_in_keycloak.py` answers them as Keycloak 26's admin interface documents, and
models the person's side: Forgot password on the sign-in page, the reset link, the second factor.
Nothing here has called a Keycloak.

Task ids: M1.6.16, M1.6.17
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from brain.connectors import sign_in_accounts
from brain.connectors.sign_in_accounts import (
    CLIENT_ID,
    MADE_ATTRIBUTE,
    PROFILE_ATTRIBUTES,
    REQUIRED_ACTIONS,
    SENDING_PATHS,
    SOURCE_ATTRIBUTE,
    STABLE_ID_ATTRIBUTE,
    Realm,
    SignInServiceError,
    accounts_of,
    close,
    declared_profile,
    make,
    mark,
    new_user,
    realm_of,
    reopen,
    token,
)
from tests.fixtures.stand_in_keycloak import BASE, ISSUER, REALM, SECRET, StandInKeycloak, User

WHERE = Realm(base=BASE, realm=REALM)
MARKS = frozenset(name for name, _ in PROFILE_ATTRIBUTES)


def run[T](work: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(work)


def test_a_realm_is_read_off_the_issuer_and_reached_at_the_worker_s_own_address() -> None:
    """Delete this and the sync signs in to the public address the browser uses, which a worker
    inside the server's network may not reach, or to a realm the issuer does not name."""
    assert realm_of(ISSUER) == Realm(base="https://sign-in.example.test", realm=REALM)
    assert realm_of(ISSUER, "http://keycloak:8080/") == Realm(
        base="http://keycloak:8080", realm=REALM
    )
    with pytest.raises(SignInServiceError):
        realm_of("https://sign-in.example.test/oauth2")


def test_the_accounts_client_signs_in_with_its_kept_secret_and_is_refused_with_another() -> None:
    """Delete this and a refused secret reads as a sync with nobody to make."""
    keycloak = StandInKeycloak()
    assert run(token(keycloak, WHERE, f"{CLIENT_ID}:{SECRET}")) == "stand-in-accounts-token"
    assert run(token(keycloak, WHERE, SECRET)) == "stand-in-accounts-token"
    with pytest.raises(SignInServiceError, match="refused"):
        run(token(keycloak, WHERE, f"{CLIENT_ID}:wrong"))
    assert SECRET not in str(keycloak.requests[0])


def made(keycloak: StandInKeycloak, name: str) -> User:
    bearer = run(token(keycloak, WHERE, SECRET))
    representation = new_user(
        email=f"{name}@example.test",
        display_name=f"{name.title()} Lovelace",
        source="lark",
        stable_id=f"on_{name}",
    )
    account = run(make(keycloak, WHERE, bearer, representation))
    return keycloak.users[account.account_id]


def test_an_account_is_made_with_the_address_no_password_and_the_second_factor_required() -> None:
    """Delete this and an account can be made with a password somebody has to be told, or without
    the second factor, or without the marks a later run finds it by."""
    keycloak = StandInKeycloak()
    user = made(keycloak, "ada")

    assert (user.email, user.username, user.enabled, user.email_verified) == (
        "ada@example.test",
        "ada@example.test",
        True,
        True,
    )
    assert user.password is None
    assert user.required_actions == list(REQUIRED_ACTIONS) == ["CONFIGURE_TOTP"]
    assert user.attributes == {
        SOURCE_ATTRIBUTE: ["lark"],
        STABLE_ID_ATTRIBUTE: ["on_ada"],
        MADE_ATTRIBUTE: ["true"],
    }


def test_nothing_the_sync_asks_of_the_sign_in_service_sends_anybody_anything() -> None:
    """The owner's rule: no link is sent to anybody, for one person or a hundred. Every request a
    make, a mark, a close and an opening builds is held to the sending endpoints, and the stand-in
    sends nothing. Delete this and one added call emails a whole company."""
    keycloak = StandInKeycloak()
    bearer = run(token(keycloak, WHERE, SECRET))
    for at in range(120):
        run(
            make(
                keycloak,
                WHERE,
                bearer,
                new_user(
                    email=f"p{at}@example.test",
                    display_name=f"P {at}",
                    source="lark",
                    stable_id=f"on_{at}",
                ),
            )
        )
    found = run(accounts_of(keycloak, WHERE, bearer, source="lark", emails=["p1@example.test"]))
    run(close(keycloak, WHERE, bearer, found[0]))
    run(reopen(keycloak, WHERE, bearer, found[0]))
    run(mark(keycloak, WHERE, bearer, found[1], source="lark", stable_id="on_1"))

    assert len(keycloak.users) == 120
    assert keycloak.sent == []
    assert not [
        one.url for one in keycloak.requests if any(path in one.url for path in SENDING_PATHS)
    ]


def test_a_person_who_asks_sets_a_password_through_the_reset_and_then_the_second_factor() -> None:
    """The flow the owner chose, end to end on the stand-in: the account the sync made cannot be
    signed in to, nothing was sent; the person presses Forgot password, and only then is a link
    sent, to them; the password it sets lets them in only to set up the second factor. Delete this
    and an account can be made that the reset cannot finish, or one that skips the second factor."""
    keycloak = StandInKeycloak()
    made(keycloak, "ada")

    assert keycloak.sign_in("ada@example.test", "anything") == "refused"
    assert keycloak.sent == []
    assert keycloak.forgot_password("ada@example.test") is True
    assert [(one.to, one.reason) for one in keycloak.sent] == [
        ("ada@example.test", "reset-credentials")
    ]
    keycloak.set_password_from_link("ada@example.test", "a password she chose")
    assert keycloak.sign_in("ada@example.test", "a password she chose") == "CONFIGURE_TOTP"


def test_with_no_email_settings_an_account_is_still_made_and_nobody_can_reset_yet() -> None:
    """Making an account needs no email; only Forgot password does. Delete this and a realm with no
    email settings stops the sync, or the sync claims people can set a password when none can."""
    keycloak = StandInKeycloak(smtp=False)
    made(keycloak, "ada")
    assert keycloak.forgot_password("ada@example.test") is False
    assert keycloak.sent == []


def test_an_account_is_found_by_its_mark_and_by_address_and_a_taken_address_is_not_made_twice() -> (
    None
):
    """Delete this and every run makes a duplicate of an account somebody made by hand."""
    keycloak = StandInKeycloak()
    made(keycloak, "ada")
    keycloak.users["by-hand"] = User(
        id="by-hand", username="bo@example.test", email="bo@example.test"
    )
    bearer = run(token(keycloak, WHERE, SECRET))

    found = run(
        accounts_of(
            keycloak, WHERE, bearer, source="lark", emails=["BO@example.test", "cy@example.test"]
        )
    )
    assert {(one.email, one.made_by_sync, one.stable_id) for one in found} == {
        ("ada@example.test", True, "on_ada"),
        ("bo@example.test", False, ""),
    }
    again = run(
        make(
            keycloak,
            WHERE,
            bearer,
            new_user(email="bo@example.test", display_name="Bo", source="lark", stable_id="on_bo"),
        )
    )
    assert again.account_id == "by-hand"
    assert len(keycloak.users) == 2


def test_linking_marks_an_account_with_the_source_and_keeps_what_it_held() -> None:
    """Keycloak replaces the attributes a PUT names, so a mark that sent only its own would wipe the
    rest. Delete this and linking an administrator's account clears whatever else it carried."""
    keycloak = StandInKeycloak(declared=frozenset({*MARKS, "locale"}))
    keycloak.users["by-hand"] = User(
        id="by-hand",
        username="bo@example.test",
        email="bo@example.test",
        attributes={"locale": ["en"]},
    )
    bearer = run(token(keycloak, WHERE, SECRET))
    (account,) = run(
        accounts_of(keycloak, WHERE, bearer, source="lark", emails=["bo@example.test"])
    )
    run(mark(keycloak, WHERE, bearer, account, source="lark", stable_id="on_bo"))

    assert keycloak.users["by-hand"].attributes == {
        "locale": ["en"],
        SOURCE_ATTRIBUTE: ["lark"],
        STABLE_ID_ATTRIBUTE: ["on_bo"],
    }
    assert MADE_ATTRIBUTE not in keycloak.users["by-hand"].attributes


def test_closing_disables_the_account_ends_its_sessions_keeps_its_marks_and_opening_undoes_it() -> (
    None
):
    """Delete this and a leaver's open session outlives the directory's word, or a close wipes the
    marks the next run finds the account by."""
    keycloak = StandInKeycloak()
    user = made(keycloak, "ada")
    bearer = run(token(keycloak, WHERE, SECRET))
    (account,) = run(accounts_of(keycloak, WHERE, bearer, source="lark", emails=[]))

    run(close(keycloak, WHERE, bearer, account))
    assert (user.enabled, user.signed_out) == (False, 1)
    assert user.attributes[MADE_ATTRIBUTE] == ["true"]
    assert keycloak.sign_in("ada@example.test", "x") == "refused"
    run(reopen(keycloak, WHERE, bearer, account))
    assert user.enabled is True


def test_a_refusal_names_the_act_and_the_service_s_words_and_never_the_secret() -> None:
    """Delete this and a refused call can come back as an empty listing, or carry the secret."""
    keycloak = StandInKeycloak()
    with pytest.raises(SignInServiceError) as refused:
        run(accounts_of(keycloak, WHERE, "not-a-token", source="lark", emails=[]))
    assert "a listing of accounts" in str(refused.value)
    assert SECRET not in str(refused.value)


def test_the_sending_paths_are_keycloak_s_three_mail_endpoints() -> None:
    """Written out here rather than read off the module, so the list cannot shrink with its test.
    Delete this and a path dropped from the list is a path the no-email test stops watching."""
    assert set(sign_in_accounts.SENDING_PATHS) == {
        "execute-actions-email",
        "send-verify-email",
        "reset-password-email",
    }


#: Keycloak 26's own user profile, as `GET users/profile` answers on a realm nobody has changed:
#: its four attributes, abridged to what a merge must keep.
KEYCLOAK_S_OWN_PROFILE: dict[str, Any] = {
    "attributes": [
        {"name": "username", "displayName": "${username}"},
        {"name": "email", "displayName": "${email}"},
        {"name": "firstName", "displayName": "${firstName}", "required": {"roles": ["user"]}},
        {"name": "lastName", "displayName": "${lastName}", "required": {"roles": ["user"]}},
    ],
    "groups": [{"name": "user-metadata", "displayHeader": "User metadata"}],
}


def test_a_realm_that_does_not_declare_the_marks_drops_them_so_no_account_reads_as_made() -> None:
    """Why the release declares the marks, shown on the stand-in: a realm whose profile does not
    name them keeps none, so the account the sync made is found by address alone and never reads
    as made by the sync, which is the one thing that lets a leaver's account be closed. Delete this
    and the profile step can be dropped from the release with every other test here green."""
    keycloak = StandInKeycloak(declared=frozenset())
    user = made(keycloak, "ada")
    assert user.attributes == {}
    bearer = run(token(keycloak, WHERE, SECRET))
    (account,) = run(
        accounts_of(keycloak, WHERE, bearer, source="lark", emails=["ada@example.test"])
    )
    assert account.made_by_sync is False


def test_the_profile_the_release_writes_declares_the_marks_and_keeps_keycloak_s_own() -> None:
    """`declared_profile` read from Keycloak's own profile and applied to a stand-in that declared
    nothing: the marks then survive a make, and every attribute and group Keycloak had is still
    there, in its order and unchanged, and a second pass adds nothing. Delete this and the merge
    can drop `email` from the realm's profile, or declare the marks twice on every release."""
    once = declared_profile(KEYCLOAK_S_OWN_PROFILE)
    keycloak = StandInKeycloak(declared=frozenset())
    keycloak.apply_profile(once)
    user = made(keycloak, "ada")

    assert user.attributes == {
        SOURCE_ATTRIBUTE: ["lark"],
        STABLE_ID_ATTRIBUTE: ["on_ada"],
        MADE_ATTRIBUTE: ["true"],
    }
    kept = once["attributes"][: len(KEYCLOAK_S_OWN_PROFILE["attributes"])]
    assert kept == KEYCLOAK_S_OWN_PROFILE["attributes"]
    assert once["groups"] == KEYCLOAK_S_OWN_PROFILE["groups"]
    added = once["attributes"][len(KEYCLOAK_S_OWN_PROFILE["attributes"]) :]
    assert [(one["name"], one["permissions"]) for one in added] == [
        (name, {"view": ["admin"], "edit": ["admin"]}) for name in MARKS_IN_ORDER
    ]
    assert declared_profile(once) == once


#: The marks in the order the profile declares them, written out rather than read off the module.
MARKS_IN_ORDER = ("brain_staff_source", "brain_staff_id", "brain_made_by_sync")
