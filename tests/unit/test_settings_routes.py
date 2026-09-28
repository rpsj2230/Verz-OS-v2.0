"""The Settings screen over HTTP: who may open it, what it shows, and a setting saved end to end.

Driven through the real application with `ops.setting` held in memory: `tests.fixtures.setting_rows`
answers the furnishing record's namespace read, and `InstallRows` below answers the two statements
`brain.ops.install_settings` makes, read back from each statement's own compiled parameters so a
route that wrote the wrong key is caught rather than agreed with.

A saved company name is followed past the row to the console's own configuration document, because
branding is configuration only if the header the console draws is what changes.

Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M27.12.7
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.console.configuration import EDITABLE_SETTINGS, SECTION_ORDER
from brain.console_static import CONSOLE_CONFIG_GLOBAL, CONSOLE_CONFIG_PATH
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.identity.first_administrator import ADMINISTRATION
from brain.identity.roles import Role
from brain.install import INSTALLATION, hold_saved
from brain.locale import currency, time_zone
from brain.ops.handover import Residue
from brain.ops.retention import BACKUP_RETENTION_DAYS, Store, facts_for
from brain.ops.starter_store import (
    FURNISHED_KEY,
    NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN,
)
from brain.settings_routes import INSTALL_SETTING_AUTHORITY, SETTINGS_PATH
from brain.tables.config import SettingType
from tests.fixtures.console_http import Stub, console_client, get, headers
from tests.fixtures.setting_rows import Result, Row, SettingRows

SCREEN = f"{API_PREFIX}{SETTINGS_PATH}"

GRANTS = {
    "u_admin": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=Scope.unrestricted()),),
    "u_narrow": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=Scope.department("web")),),
    "u_wide": (Grant(capability=Capability(value="admin:feature"), scope=Scope.unrestricted()),),
    "u_none": (),
}


class InstallRows:
    """The `install.` rows of `ops.setting`: the upsert `save` makes, the select `load` makes, and
    the retirement `retire` makes, each read back from the statement's own parameters."""

    def __init__(self) -> None:
        self.rows: dict[str, str] = {}
        self.writes: list[dict[str, Any]] = []
        self.retired: list[dict[str, Any]] = []

    def answer(self, statement: Any) -> Result | None:
        # `Update.table` is typed as any from-clause; this one's is the setting table itself.
        if isinstance(statement, Update) and getattr(statement.table, "name", "") == "setting":
            params = statement.compile().params
            key = str(params["key_1"])
            if key not in self.rows:
                return Result([])
            del self.rows[key]
            self.retired.append({"key": key, "updated_by": params["updated_by"]})
            return Result([key])
        if isinstance(statement, Insert) and statement.table.name == "setting":
            params = statement.compile().params
            written = {
                field: params[f"{field}_m0"]
                for field in ("key", "value_type", "value", "updated_by")
            }
            self.writes.append(written)
            self.rows[str(written["key"])] = str(written["value"])
            return Result([])
        if isinstance(statement, Select):
            columns = [one["name"] for one in statement.column_descriptions]
            if columns == ["key", "value_type", "value"]:
                return Result(
                    Row((key, SettingType.STRING.value, value))
                    for key, value in sorted(self.rows.items())
                )
        return None


@pytest.fixture(autouse=True)
def nothing_saved() -> Iterator[None]:
    """Every test starts with nothing held and leaves whatever was held before it."""
    before = hold_saved({})
    yield
    hold_saved(before)


@pytest.fixture
def installed() -> InstallRows:
    return InstallRows()


@pytest.fixture
def furnishing() -> SettingRows:
    rows = SettingRows()
    rows.hold(FURNISHED_KEY, True, value_type="boolean", by="first_run")
    return rows


@pytest.fixture
def served(installed: InstallRows, furnishing: SettingRows) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([installed.answer, furnishing.answer])
        yield client, stub


def put(client: TestClient, pid: str, name: str, value: str) -> Any:
    return client.put(f"{SCREEN}/{name}", json={"value": value}, headers=headers(pid))


@pytest.mark.parametrize("pid", ["u_none", "u_narrow", "u_wide"])
def test_a_caller_without_the_authority_over_everything_is_refused_before_anything_is_read(
    pid: str,
) -> None:
    """The same refusal with a database and without, for the read and the write, and nothing
    written. The positive sibling is every test below. Delete this and a department-scoped grant
    reads the whole install's configuration, or renames the company."""
    for database in (True, False):
        with console_client(GRANTS, database=database) as (client, stub):
            assert get(client, pid, SCREEN).status_code == 404
            assert put(client, pid, "INSTALL_COMPANY_NAME", "Contoso").status_code == 404
            assert default_of(client, pid, "INSTALL_COMPANY_NAME").status_code == 404
            assert stub.statements == []


def test_the_authority_is_an_administration_capability_the_first_administrator_holds() -> None:
    """`admin:`, so a password-only session is refused by `brain.gate.admission`, and in the
    appointment, so the first administrator can open the screen. Delete this and the capability
    can be respelled into one nobody on any install holds."""
    assert INSTALL_SETTING_AUTHORITY.value.startswith("admin:")
    assert INSTALL_SETTING_AUTHORITY.value in ADMINISTRATION
    with console_client(GRANTS) as (client, _):
        assert get(client, "u_admin", SCREEN, strong=False).status_code == 404


def test_the_screen_shows_every_setting_grouped_with_its_source_and_the_starter_set(
    served: tuple[TestClient, Stub],
) -> None:
    """The owner's view: branding, identity, models, storage and locale, each value with where it
    came from, and what the install was furnished with, standard agents stated as not installed
    with the exact reason. Delete this and the screen can omit a group or claim agents it lacks."""
    client, _ = served
    answer = get(client, "u_admin", SCREEN)

    assert answer.status_code == 200, answer.text
    body = answer.json()
    names = [row["name"] for group in body["groups"] for row in group["settings"]]
    assert sorted(names) == sorted(one.name for one in INSTALLATION)
    assert [group["group"] for group in body["groups"]] == [one.value for one in SECTION_ORDER]
    assert {group["group"] for group in body["groups"] if group["editable"]} == {
        "company",
        "locale",
        "models",
    }
    settings = [row for group in body["groups"] for row in group["settings"]]
    assert all(row["label"] for row in settings)
    assert all(bool(row["read_only_because"]) != row["editable"] for row in settings)
    assert sorted(row["name"] for row in settings if row["editable"]) == sorted(EDITABLE_SETTINGS)
    starter = body["starter"]
    assert starter["roles"] == [one.value for one in Role] and len(starter["roles"]) == 6
    assert starter["scopes"] == ["company"] and starter["furnished"] is True
    assert starter["agents_installed"] is False
    assert NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN in starter["agents_told"]


def test_the_screen_describes_the_handover_of_this_install_before_anyone_runs_it(
    served: tuple[TestClient, Stub],
) -> None:
    """M41.2.6 in the console: every store and every install part a handover removes, who removes
    it and how, the realm it names, and the retention the certificate's date comes from. Delete this
    and the screen can describe a handover that leaves a part behind or names another realm."""
    client, _ = served
    hold_saved({"INSTALL_OIDC_REALM": "northwind"})
    try:
        leaving = get(client, "u_admin", SCREEN).json()["leaving"]
    finally:
        hold_saved({})
    whats = {one["what"] for one in leaving["steps"]}
    assert whats == {one.value for one in Store} | {one.value for one in Residue}
    assert {one["by"] for one in leaving["steps"]} == {"command", "operator"}
    realm = next(one for one in leaving["steps"] if one["what"] == Residue.IDENTITY_REALM.value)
    assert realm["kind"] == "part" and "realms/northwind" in realm["how"]
    ledger = next(one for one in leaving["steps"] if one["what"] == Store.AUDIT.value)
    assert ledger["kind"] == "store" and ledger["holds"] == facts_for(Store.AUDIT).holds
    assert leaving["backup_retention_days"] == BACKUP_RETENTION_DAYS
    assert leaving["procedure"] == "docs/install/handover.md"
    assert all(one.startswith("python -m brain.ops.handover_run ") for one in leaving["commands"])


def test_saving_a_company_name_writes_its_row_and_the_console_header_draws_it_next(
    served: tuple[TestClient, Stub], installed: InstallRows
) -> None:
    """**The end the screen is for.** The row is written under `install.company_name` by the person
    who saved it, inside the audit attribution, committed once; the answer shows it as saved; and
    the console configuration document this process serves next carries it.

    Delete this and a save can write a key nothing loads, skip the attribution the ledger trigger
    needs, or land in the database while the header goes on drawing the old name until a restart."""
    client, stub = served
    answer = put(client, "u_admin", "INSTALL_COMPANY_NAME", "  Northwind Trading  ")

    assert answer.status_code == 200, answer.text
    assert installed.writes == [
        {
            "key": "install.company_name",
            "value_type": SettingType.STRING.value,
            "value": "Northwind Trading",
            "updated_by": "u_admin",
        }
    ]
    assert stub.commits == 1
    assert ("brain.actor_id", "u_admin") in stub.attributions
    company = next(
        row
        for group in answer.json()["groups"]
        for row in group["settings"]
        if row["name"] == "INSTALL_COMPANY_NAME"
    )
    assert (company["value"], company["source"]) == ("Northwind Trading", "saved")
    document = client.get(CONSOLE_CONFIG_PATH).text
    prefix = f"window.{CONSOLE_CONFIG_GLOBAL} = Object.freeze("
    served_config = json.loads(document.strip().removeprefix(prefix).removesuffix(");"))
    assert served_config["brand"]["companyName"] == "Northwind Trading"


def test_saving_the_currency_and_time_zone_writes_both_rows_and_money_reads_them_at_once(
    served: tuple[TestClient, Stub], installed: InstallRows
) -> None:
    """The owner's case: an install left at no currency and UTC gets SGD and Asia/Singapore from
    Install, Settings, each written in capitals or as typed, attributed, and read by the locale
    readers the money figures use from the next request on this process.

    Delete this and the currency and zone go back to being changeable only in a file on the server,
    and the cost card goes on reading "no currency"."""
    client, stub = served
    first = put(client, "u_admin", "INSTALL_CURRENCY", "sgd")
    second = put(client, "u_admin", "INSTALL_TIME_ZONE", "Asia/Singapore")

    assert (first.status_code, second.status_code) == (200, 200), (first.text, second.text)
    assert [(one["key"], one["value"]) for one in installed.writes] == [
        ("install.currency", "SGD"),
        ("install.time_zone", "Asia/Singapore"),
    ]
    assert stub.commits == 2
    assert ("brain.actor_id", "u_admin") in stub.attributions
    assert currency() == "SGD"
    assert time_zone().key == "Asia/Singapore"
    locale = next(group for group in second.json()["groups"] if group["group"] == "locale")
    shown = {row["name"]: (row["value"], row["source"]) for row in locale["settings"]}
    assert shown["INSTALL_CURRENCY"] == ("SGD", "saved")
    assert shown["INSTALL_TIME_ZONE"] == ("Asia/Singapore", "saved")


def default_of(client: TestClient, pid: str, name: str) -> Any:
    return client.post(f"{SCREEN}/{name}/default", headers=headers(pid))


def row_named(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(row for group in body["groups"] for row in group["settings"] if row["name"] == name)


def test_every_row_says_what_it_would_read_with_its_saved_value_taken_away(
    served: tuple[TestClient, Stub],
) -> None:
    """The confirmation of "return to default" names the value it returns to. Delete this and the
    screen can promise the product default where the environment file sets another value."""
    client, _ = served
    hold_saved({"INSTALL_COMPANY_NAME": "Northwind Trading"})
    try:
        body = get(client, "u_admin", SCREEN).json()
    finally:
        hold_saved({})
    company = row_named(body, "INSTALL_COMPANY_NAME")
    declared = next(one for one in INSTALLATION if one.name == "INSTALL_COMPANY_NAME")

    assert (company["value"], company["source"]) == ("Northwind Trading", "saved")
    assert (company["without_saved"], company["without_saved_source"]) == (
        declared.default,
        "default",
    )


def test_returning_to_default_retires_the_saved_row_as_the_person_and_the_default_reads_next(
    served: tuple[TestClient, Stub], installed: InstallRows
) -> None:
    """needs-rupash gap (e). The saved row is retired, not overwritten, with the person as the
    row's last writer inside the audit attribution, so `0059` records `retired` against them;
    the answer and the header this process draws next read the default again.

    Delete this and the only way back to the default is to type it, which saves a row that goes on
    outranking the environment file for ever."""
    client, stub = served
    put(client, "u_admin", "INSTALL_COMPANY_NAME", "Northwind Trading")

    answer = default_of(client, "u_admin", "INSTALL_COMPANY_NAME")

    assert answer.status_code == 200, answer.text
    assert installed.retired == [{"key": "install.company_name", "updated_by": "u_admin"}]
    assert stub.commits == 2
    assert ("brain.actor_id", "u_admin") in stub.attributions
    company = row_named(answer.json(), "INSTALL_COMPANY_NAME")
    assert company["source"] == "default"
    document = client.get(CONSOLE_CONFIG_PATH).text
    assert "Northwind Trading" not in document


def test_returning_to_default_with_nothing_saved_answers_409_and_commits_nothing(
    served: tuple[TestClient, Stub], installed: InstallRows
) -> None:
    """The sibling: nothing to take away is said, not pretended. Delete this and the button reports
    success on a setting that never changed."""
    client, stub = served
    answer = default_of(client, "u_admin", "INSTALL_PRODUCT_NAME")

    assert answer.status_code == 409
    assert answer.json()["message"]
    assert installed.retired == [] and stub.commits == 0


@pytest.mark.parametrize("name", ["INSTALL_OIDC_ISSUER", "INSTALL_STAFF_SOURCE", "INSTALL_NOPE"])
def test_a_setting_this_screen_does_not_change_is_not_returned_to_default(
    served: tuple[TestClient, Stub], installed: InstallRows, name: str
) -> None:
    """A saved identity provider value taken away from a browser points sign-in somewhere else.
    Delete this and any saved setting can be retired from the console."""
    client, stub = served
    installed.rows["install.oidc_issuer"] = "https://id.example/realms/brain"

    answer = default_of(client, "u_admin", name)

    assert answer.status_code == 422
    assert answer.json()["message"] == f"{name} is not changed on this screen."
    assert installed.retired == [] and stub.commits == 0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INSTALL_OIDC_ISSUER", "https://id.northwind.example/realms/brain"),
        ("INSTALL_OBJECT_STORE_URL", "https://objects.northwind.example"),
        ("INSTALL_EMBEDDING_DIMENSIONS", "768"),
        ("INSTALL_ACCENT_COLOUR", "green"),
        ("INSTALL_CURRENCY", "XXX"),
        ("INSTALL_TIME_ZONE", "Mars/Olympus"),
        ("INSTALL_NOT_DECLARED", "x"),
    ],
)
def test_a_value_this_screen_does_not_change_or_would_draw_wrong_is_refused_and_nothing_is_written(
    served: tuple[TestClient, Stub], installed: InstallRows, name: str, value: str
) -> None:
    """A 422 with the sentence saying what to do, and no statement reaches the table. Delete this
    and an issuer can be changed from a browser, which signs nobody in, including the person who
    did."""
    client, stub = served
    answer = put(client, "u_admin", name, value)

    assert answer.status_code == 422
    assert answer.json()["message"]
    assert installed.writes == [] and stub.commits == 0
