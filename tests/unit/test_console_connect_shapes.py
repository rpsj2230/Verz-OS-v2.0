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
from brain.ops.connectable import CONNECTABLE, key_reference, settings_problems
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
    "client_rule": "department = sales",
    "user_rule": "department in sales, operations",
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
    assert CONNECTABLE["google_drive"].credential_shape is CredentialShape.KEY_FILE
    assert CONNECTABLE["laravel"].credential_shape is CredentialShape.DATABASE_USER
    assert CONNECTABLE["xero"].credential_shape is CredentialShape.KEY


# ------------------------------------------------------------------------ the forms


def test_a_drive_folder_is_named_by_its_link_or_its_id_and_the_folder_is_the_scope() -> None:
    """The positive case: the link as the browser shows it, and the id alone, build one manifest
    pinned to that folder. Delete this and the form refuses the address a person actually has."""
    by_link = google_drive.built_from_the_console(DRIVE, key_reference("google_drive"))
    by_id = google_drive.built_from_the_console(
        {**DRIVE, "folder": "1AbCdEfGhIjKlMnOp"}, key_reference("google_drive")
    )
    assert by_link.scope.selectors == by_id.scope.selectors == ("1AbCdEfGhIjKlMnOp",)
    assert settings_problems(CONNECTABLE["google_drive"], DRIVE) == ()


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
    """`A_VIEW_RULE_IS_ONE_FIELD_AND_ITS_VALUES`, the positive case in both spellings. Delete this
    and a rule a person wrote correctly is refused, or read as another predicate."""
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
