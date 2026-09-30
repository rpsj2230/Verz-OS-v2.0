"""Google Drive and the Laravel database connected on the Connectors screen (M11.7.7).

Three halves. The credential shapes: a key file and a database user are each judged before
anything is sent and kept in the slot whole, a key file as the key and a user as the password with
its name beside it. The forms: each setting is refused by the rule its connection holds it to,
naming that setting, and each view's rule is read by a one-clause grammar. The route half is in
`tests/unit/test_connector_routes.py`, beside the connect route's other tests.

Task ids: M11.7.7
"""

from __future__ import annotations

import json

import pytest

from brain.connectors import google_drive, laravel
from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import CredentialShape, SettingRefusedError
from brain.core.scope import Clause, Op, Scope
from brain.ops.connectable import DECLARED_FORMS, key_reference, settings_problems
from brain.ops.connector_admin import credential_problems
from brain.ops.credentials import (
    KEY_FIELD,
    MAX_KEY_FILE_CHARS,
    SERVICE_ACCOUNT,
    USER_FIELD,
    key_file_problems,
    problems_with,
    user_and_password,
)

KEY_FILE = json.dumps(
    {
        "type": SERVICE_ACCOUNT,
        "client_email": "reader@project.example",
        "private_key": "KEY-FILE-SENTINEL-1f9d",
        "project_id": "project",
    },
    indent=2,
)
USER = json.dumps({"user": "brain_reader", "password": "PASSWORD-SENTINEL-77a1"})

DRIVE = {
    "folder": "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp?usp=sharing",
    "domain": "Example.com",
    "department": "operations",
    "steward": "u_steward",
}
LARAVEL = {
    "schema": "portal",
    "host": "db.example.invalid",
    "port": "3306",
    "private_network": "no",
    "tls": "verify",
    "client_rule": "department = sales",
    "user_rule": "department = operations",
    "max_rows": "500",
    "timeout_seconds": "10",
}


# ----------------------------------------------------------------------- the shapes


def test_a_key_file_is_judged_as_a_file_and_one_pasted_key_would_refuse_it() -> None:
    """The positive case, and why it needs its own judge: a key file has line breaks inside it,
    which `problems_with` refuses as a bad copy. Delete this and a Drive key file can never be
    kept, or can be kept only by a person pasting a private key through a text box."""
    assert key_file_problems(KEY_FILE) == ()
    assert key_file_problems(f"\n{KEY_FILE}\n") == ()
    assert "not_one_piece" in {one.code for one in problems_with(KEY_FILE)}


@pytest.mark.parametrize(
    ("given", "code"),
    [
        ("", "blank"),
        ("   ", "blank"),
        ("x" * (MAX_KEY_FILE_CHARS + 1), "too_long"),
        ("not json", "not_a_key_file"),
        (json.dumps(["a", "list"]), "not_a_key_file"),
        (json.dumps({"type": "authorized_user", "client_email": "a", "private_key": "b"}), None),
        (json.dumps({"type": SERVICE_ACCOUNT, "client_email": "a"}), "not_a_key_file"),
        (json.dumps({"type": SERVICE_ACCOUNT, "client_email": " ", "private_key": "b"}), None),
    ],
)
def test_anything_but_a_service_account_key_file_is_refused_before_it_is_sent(
    given: str, code: str | None
) -> None:
    """Delete this and a user's own sign-in file, which signs in as that person to everything they
    can open, is kept as though it were the service account's."""
    found = [one.code for one in key_file_problems(given)]
    assert found == [code or "not_a_key_file"]


def test_a_problem_with_a_key_file_names_nothing_that_was_in_it() -> None:
    """Delete this and a refusal can quote a private key back into a response and a log."""
    wrong = json.dumps({"type": "authorized_user", "private_key": "KEY-FILE-SENTINEL-1f9d"})
    assert all("SENTINEL" not in one.message for one in key_file_problems(wrong))


def test_a_database_user_is_kept_as_its_password_with_its_name_beside_it() -> None:
    """The slot's key is the secret half, so anything asking a slot for its key is handed the
    password and never the name. Delete this and the two halves can land under one field, or the
    name where a reader looks for the key."""
    fields, problems = user_and_password(USER)
    assert problems == ()
    assert fields == {KEY_FIELD: "PASSWORD-SENTINEL-77a1", USER_FIELD: "brain_reader"}


@pytest.mark.parametrize(
    ("given", "fields"),
    [
        ("", [USER_FIELD, "api_key"]),
        ("not json", ["api_key"]),
        (json.dumps({"user": "brain_reader"}), ["api_key"]),
        (json.dumps({"password": "p"}), [USER_FIELD]),
        (json.dumps({"user": "two words", "password": "p"}), [USER_FIELD]),
    ],
)
def test_a_missing_or_broken_half_of_a_database_user_is_refused_by_the_half(
    given: str, fields: list[str]
) -> None:
    """Delete this and a user with no password is kept, and every read of the database fails as
    the database refusing the connector rather than as a form nobody finished."""
    _, problems = user_and_password(given)
    assert [one.field for one in problems] == fields


def test_every_shape_is_told_against_the_one_credential_field() -> None:
    """The request has one `credential` field whatever the shape, so a refusal is drawn beside it.
    Delete this and a key file's refusal names a field the form does not have."""
    for shape, wrong in (
        (CredentialShape.KEY, "two words"),
        (CredentialShape.KEY_FILE, "not json"),
        (CredentialShape.DATABASE_USER, json.dumps({"user": "u"})),
    ):
        found = credential_problems(shape, wrong)
        assert found and {one.field for one in found} == {"credential"}
    assert credential_problems(CredentialShape.KEY_FILE, KEY_FILE) == ()
    assert credential_problems(CredentialShape.DATABASE_USER, USER) == ()


def test_the_two_sources_take_their_credential_in_their_own_shape() -> None:
    """Delete this and Drive can be offered a key box, or Laravel one string to invent a separator
    in."""
    assert DECLARED_FORMS["google_drive"].credential_shape is CredentialShape.KEY_FILE
    assert DECLARED_FORMS["laravel"].credential_shape is CredentialShape.DATABASE_USER
    assert DECLARED_FORMS["xero"].credential_shape is CredentialShape.KEY


# ------------------------------------------------------------------------ the forms


def test_a_drive_folder_is_named_by_its_link_or_its_id_and_the_folder_is_the_scope() -> None:
    """The positive case: the link as the browser shows it, and the id alone, build one manifest
    pinned to that folder. Delete this and the form refuses the address a person actually has."""
    by_link = google_drive.built_from_the_console(DRIVE, key_reference("google_drive"))
    by_id = google_drive.built_from_the_console(
        {**DRIVE, "folder": "1AbCdEfGhIjKlMnOp"}, key_reference("google_drive")
    )
    assert by_link.scope.selectors == by_id.scope.selectors == ("1AbCdEfGhIjKlMnOp",)
    assert settings_problems(DECLARED_FORMS["google_drive"], DRIVE) == ()


@pytest.mark.parametrize(
    ("setting", "typed"),
    [
        ("folder", "*"),
        ("folder", "all"),
        ("folder", "https://drive.google.com/drive/my-drive"),
        ("domain", "example"),
        ("domain", "someone@example.com"),
        ("department", "Operations"),
        ("steward", "two words"),
    ],
)
def test_a_drive_setting_is_refused_naming_that_setting(setting: str, typed: str) -> None:
    """Delete this and a refusal marks every box, and a person retypes the three that were right."""
    with pytest.raises(SettingRefusedError) as refused:
        google_drive.built_from_the_console(
            {**DRIVE, setting: typed}, key_reference("google_drive")
        )
    assert refused.value.setting == setting


def test_a_view_rule_is_one_field_and_its_value_or_values() -> None:
    """`A_VIEW_RULE_IS_ONE_FIELD_AND_ITS_VALUES`, the positive case in both spellings. A list is
    still read as one, so the form can refuse it for the index's reason rather than as a typo.
    Delete this and a rule a person wrote correctly is refused, or read as another predicate."""
    assert laravel.rule_of("department = sales") == Scope(
        clauses=(Clause(field="department", op=Op.EQ, value="sales"),)
    )
    assert laravel.rule_of("department=sales") == laravel.rule_of(" department = sales ")
    assert laravel.rule_of("department in sales, operations") == Scope(
        clauses=(Clause(field="department", op=Op.IN, value=("sales", "operations")),)
    )


@pytest.mark.parametrize(
    "written", ["", "department", "department sales", "department = ", "department = a b", "*"]
)
def test_anything_but_a_field_and_its_values_is_not_a_view_rule(written: str) -> None:
    """Delete this and a rule typed as a sentence is kept as a predicate nobody meant."""
    with pytest.raises(ConnectorContractError):
        laravel.rule_of(written)


@pytest.mark.parametrize(
    ("setting", "typed"),
    [
        ("schema", "*"),
        ("schema", "all"),
        ("schema", "Portal"),
        ("client_rule", "contract_value = 1"),
        ("user_rule", "password = x"),
        ("user_rule", "department sales"),
        ("user_rule", "department in sales, operations"),
        ("host", ""),
        ("host", "db.example.invalid:3306"),
        ("host", "https://db.example.invalid"),
        ("host", "reader@db.example.invalid"),
        ("host", "10.0.0.5"),
        ("host", "[fd00::5]"),
        ("port", "0"),
        ("port", f"{laravel.MAX_PORT + 1}"),
        ("port", "mysql"),
        ("private_network", "maybe"),
        ("private_network", "true"),
        ("tls", "maybe"),
        ("tls", "none"),
        ("tls", "-----BEGIN PRIVATE KEY-----MIIB-----END PRIVATE KEY-----"),
        ("tls", "-----BEGIN CERTIFICATE-----AAAA-----END CERTIFICATE-----"),
        ("max_rows", "0"),
        ("max_rows", f"{laravel.MAX_ROWS_EVER + 1}"),
        ("timeout_seconds", "31"),
        ("timeout_seconds", "ten"),
    ],
)
def test_a_laravel_setting_is_refused_naming_that_setting(setting: str, typed: str) -> None:
    """A rule over a field the view does not keep, or over one never selected, is refused as that
    rule; a database called all as everything. Delete this and a rule that matches nothing for ever
    is kept, and reads as a company with no clients."""
    with pytest.raises(SettingRefusedError) as refused:
        laravel.built_from_the_console({**LARAVEL, setting: typed}, key_reference("laravel"))
    assert refused.value.setting == setting


def test_a_rule_listing_several_values_is_refused_because_the_index_holds_one() -> None:
    """`A_RULE_THE_INDEX_CANNOT_CARRY_IS_REFUSED`. The rule is laid onto every record the view keeps
    (`connector_sync.stored_fields`), and a record holds one value, so a list was connected and
    then never read. Delete this and a connection can keep its user and read nothing, which is
    the one thing the Connectors screen must never offer."""
    from brain.ops.connector_sync import storable_predicate

    listed = laravel.rule_of("department in sales, operations")
    assert not storable_predicate(listed)
    with pytest.raises(SettingRefusedError) as refused:
        laravel.built_from_the_console(
            {**LARAVEL, "client_rule": "department in sales, operations"}, key_reference("laravel")
        )
    assert refused.value.setting == "client_rule"
    manifest = laravel.built_from_the_console(LARAVEL, key_reference("laravel"))
    assert all(storable_predicate(one.visibility) for one in manifest.projections)


def test_a_private_address_is_taken_only_where_the_connection_says_its_database_is_private() -> (
    None
):
    """`A_PRIVATE_ADDRESS_IS_THE_CONNECTION_S_OWN_DECISION`, at the form, both ways. The same
    private address and the same bracketed IPv6 address are refused with the setting at no and
    taken with it at yes, and the setting's words decide it, not its case. Delete this and the
    refusal above could be a form that refuses every address, or the setting could be ignored."""
    for typed in ("10.0.0.5", "[fd00::5]", "127.0.0.1"):
        with pytest.raises(SettingRefusedError) as refused:
            laravel.built_from_the_console(
                {**LARAVEL, "host": typed, "private_network": "no"}, key_reference("laravel")
            )
        assert refused.value.setting == "host"
        built = laravel.built_from_the_console(
            {**LARAVEL, "host": typed, "private_network": " YES "}, key_reference("laravel")
        )
        assert built.name == "laravel"
    connection = laravel.connection_of({**LARAVEL, "host": "[FD00::5]", "private_network": "yes"})
    assert (connection.host, connection.port, connection.private_network) == ("fd00::5", 3306, True)


def test_a_laravel_connection_keeps_each_view_under_the_rule_written_for_it() -> None:
    """The positive case. Delete this and the rules typed can be dropped, or crossed between the
    two views, with every refusal above still green."""
    manifest = laravel.built_from_the_console(LARAVEL, key_reference("laravel"))
    by_entity = {one.entity: one.visibility for one in manifest.projections}
    assert by_entity == {
        laravel.ENTITY_CLIENT: laravel.rule_of(LARAVEL["client_rule"]),
        laravel.ENTITY_USER: laravel.rule_of(LARAVEL["user_rule"]),
    }
    assert manifest.scope.selectors == ("portal.v_client", "portal.v_user")


def test_encryption_verifies_by_default_takes_an_authority_and_allows_none_in_a_tunnel() -> None:
    """`A_LOGIN_CROSSES_ONLY_A_VERIFIED_CHANNEL` and `NO_ENCRYPTION_IS_THE_TUNNEL_S_CASE`, at the
    form. `verify` in any case is the verified default; a certificate authority pasted on one line,
    past the form's usual bound, is taken as the connection's own; `none` is refused naming the
    setting unless the database is on a private network, and taken when it is. Delete this and the
    form could take none on the internet, or refuse the tunnel and the company's own authority."""
    from tests.fixtures.tls import issued

    authority = issued().authority
    pasted = authority.replace("\n", "")
    assert len(pasted) > 200
    form = DECLARED_FORMS["laravel"]
    assert settings_problems(form, {**LARAVEL, "tls": pasted}) == ()
    assert settings_problems(form, {**LARAVEL, "schema": "p" * 201})[0].code == "too_long"

    verified = laravel.connection_of({**LARAVEL, "tls": " VERIFY "})
    assert verified.tls == laravel.DatabaseTls(laravel.TlsMode.VERIFIED)
    own = laravel.connection_of({**LARAVEL, "tls": pasted})
    assert own.tls == laravel.DatabaseTls(laravel.TlsMode.OWN_AUTHORITY, authority)

    with pytest.raises(SettingRefusedError) as refused:
        laravel.connection_of({**LARAVEL, "tls": "none"})
    assert refused.value.setting == "tls"
    tunnel = laravel.connection_of(
        {**LARAVEL, "tls": "none", "private_network": "yes", "host": "127.0.0.1"}
    )
    assert (tunnel.tls.mode, tunnel.private_network) == (laravel.TlsMode.NONE, True)
    with pytest.raises(laravel.LaravelError):
        laravel.LaravelConnection(
            schema="portal",
            bounds=laravel.ReadBounds(max_rows=10, timeout_seconds=5.0),
            host="db.example.invalid",
            port=3306,
            private_network=False,
            tls=laravel.DatabaseTls(laravel.TlsMode.NONE),
        )
