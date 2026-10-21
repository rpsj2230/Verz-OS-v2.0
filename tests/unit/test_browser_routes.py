"""The browser declaration routes: refused before the database to anybody without the authority over
everything, refused while the switch is off, and drawn from the stored declarations and grants.

The stub holds `ops.setting` in memory (`tests.fixtures.setting_rows`) and answers the reads the
page makes; every write needs a real transaction and is proved by the install check
`brain.ops.acceptance_checks_browser_declarations` over PostgreSQL.

Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.browser_routes import BROWSER_ADMIN
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.ops.features import is_on  # noqa: F401 - the switch is read through the route
from brain.ops.features_declared.browser_declarations import BROWSER_DECLARATIONS
from brain.routers import ROUTERS
from brain.tables.browsing import BrowserGrantRow, BrowserTargetRow
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import NAMESPACE_COLUMNS, Result, SettingRows
from tests.unit.test_browser_declarations import DOCUMENT

BROWSER = f"{API_PREFIX}/install/browser"
EVERYWHERE = Scope.unrestricted()
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)
FAR_AHEAD = datetime(2999, 1, 1, tzinfo=UTC)

GRANTS = {
    "u_admin": (Grant(capability=BROWSER_ADMIN, scope=EVERYWHERE),),
    "u_narrow": (Grant(capability=BROWSER_ADMIN, scope=Scope.department("web")),),
    "u_none": (),
}


class Declared:
    """The two selects the page makes of the declarations, answering the rows a test holds."""

    def __init__(self) -> None:
        self.targets: list[SimpleNamespace] = []
        self.grants: list[SimpleNamespace] = []
        self.asked = 0

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        entity = statement.column_descriptions[0].get("entity")
        if entity is BrowserTargetRow:
            self.asked += 1
            return Result(self.targets)
        if entity is BrowserGrantRow:
            self.asked += 1
            return Result(self.grants)
        return None


def a_target_row(document: dict[str, Any], *, retired: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        seq=1,
        name=document["name"],
        definition=document,
        retired=retired,
        set_by="u_admin",
        created_at=LONG_AGO,
    )


def a_grant_row(**kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "seq": 7,
        "kind": "exception",
        "target": "books",
        "surface": "login",
        "skill": None,
        "signed_by": "u_admin",
        "reason": "the nightly filing runs unattended",
        "expires_at": FAR_AHEAD,
        "revoked_at": None,
        "revoked_by": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def held() -> Declared:
    return Declared()


@pytest.fixture
def served(settings: SettingRows, held: Declared) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, held.answer])
        yield client, stub


def test_the_router_is_mounted_by_the_application() -> None:
    """Delete this and the routes can be written, tested and never served."""
    assert any(
        getattr(one, "path", "").startswith(f"{API_PREFIX}/install/browser")
        for router in ROUTERS
        for one in router.routes
    )


# -------------------------------------------------------------------------- the authority
EVERY_ROUTE = (
    ("GET", BROWSER, None),
    ("POST", f"{BROWSER}/targets", {"declaration": DOCUMENT}),
    ("POST", f"{BROWSER}/targets/books/retire", None),
    (
        "POST",
        f"{BROWSER}/exceptions",
        {"target": "books", "surface": "login", "days": 5, "reason": "a reason long enough"},
    ),
    (
        "POST",
        f"{BROWSER}/exemptions",
        {"skill": "file-return", "target": "books", "days": 5, "reason": "a reason long enough"},
    ),
    ("POST", f"{BROWSER}/grants/7/revoke", None),
)


def call(client: TestClient, pid: str, method: str, path: str, body: Any) -> Any:
    if method == "GET":
        return get(client, pid, path)
    return post(client, pid, path, body)


@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
@pytest.mark.parametrize(("method", "path", "body"), EVERY_ROUTE)
def test_a_caller_without_the_authority_over_everything_is_refused_before_the_database(
    pid: str, method: str, path: str, body: Any
) -> None:
    """The same refusal with a database and without one, naming no capability, and no statement
    reaches a store.

    Delete this and a department's administrator signs for the whole install, or a caller with
    nothing learns whether this process has a pool."""
    with console_client(GRANTS, database=False) as (client, _):
        without = call(client, pid, method, path, body)
    with console_client(GRANTS) as (client, stub):
        with_pool = call(client, pid, method, path, body)
    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert BROWSER_ADMIN.value not in with_pool.json()["message"]
    assert stub.statements == []


def test_a_password_only_sign_in_holding_the_authority_is_refused(
    served: tuple[TestClient, Stub],
) -> None:
    """The route asks the admitted reach rather than the grants on file. Delete this and a stolen
    password alone signs a permission for a browser to act unattended."""
    client, stub = served
    refused = post(client, "u_admin", f"{BROWSER}/targets", {"declaration": DOCUMENT}, strong=False)
    assert refused.status_code == 404
    assert stub.statements == []


# ------------------------------------------------------------------------------ the page
def test_the_page_draws_the_declared_websites_and_the_permissions_in_force(
    served: tuple[TestClient, Stub], held: Declared
) -> None:
    """Delete this and the screen can draw a website that is not stored, omit a credential's
    origin, or show a permission that has been revoked."""
    held.targets.append(a_target_row(DOCUMENT))
    held.grants.append(a_grant_row())
    client, _ = served

    body = get(client, "u_admin", BROWSER).json()

    [target] = body["targets"]
    assert target["name"] == "books" and target["origins"] == ["https://books.example"]
    assert [one["name"] for one in target["surfaces"]] == ["login", "invoices"]
    assert target["surfaces"][0]["controls"] == [
        'type textbox "Password" {{secret:login}}',
        'submit button "Sign in"',
    ]
    assert target["bindings"] == [
        {
            "placeholder": "{{secret:login}}",
            "origin": "https://books.example",
            "kind": "password",
            "path": "browser/creds/books",
        }
    ]
    assert [(one["kind"], one["what"], one["signed_by"]) for one in body["grants"]] == [
        ("exception", "login", "u_admin")
    ]
    assert body["unreadable"] == [] and body["most_days"] == 90


def test_a_stored_row_that_does_not_read_is_listed_as_unreadable_and_not_as_a_website(
    served: tuple[TestClient, Stub], held: Declared
) -> None:
    """Delete this and a row the codec refuses is drawn as a website, or is dropped silently."""
    held.targets.append(a_target_row({"name": "stale", "selector": 1}))
    client, _ = served

    body = get(client, "u_admin", BROWSER).json()

    assert body["targets"] == [] and body["unreadable"] == ["stale"]


def test_a_retired_declaration_is_not_listed(
    served: tuple[TestClient, Stub], held: Declared
) -> None:
    """Delete this and a retired website is drawn, with a retire button that finds nothing."""
    held.targets.append(a_target_row(DOCUMENT, retired=True))
    client, _ = served

    assert get(client, "u_admin", BROWSER).json()["targets"] == []


def test_the_page_says_whether_declaring_is_on(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and the screen offers buttons the route refuses."""
    client, _ = served
    off = get(client, "u_admin", BROWSER).json()
    settings.hold(BROWSER_DECLARATIONS.key, True, value_type="boolean")
    on = get(client, "u_admin", BROWSER).json()

    assert (off["declarations_are_on"], on["declarations_are_on"]) == (False, True)


# ----------------------------------------------------------------------------- the switch
@pytest.mark.parametrize(
    ("path", "body"),
    [
        (f"{BROWSER}/targets", {"declaration": DOCUMENT}),
        (
            f"{BROWSER}/exceptions",
            {"target": "books", "surface": "login", "days": 5, "reason": "a reason long enough"},
        ),
        (
            f"{BROWSER}/exemptions",
            {
                "skill": "file-return",
                "target": "books",
                "days": 5,
                "reason": "a reason long enough",
            },
        ),
    ],
)
def test_the_three_writes_that_open_a_permission_are_refused_while_the_switch_is_off(
    served: tuple[TestClient, Stub], settings: SettingRows, path: str, body: Any
) -> None:
    """Delete this and a feature that ships off is on for every install the day it arrives."""
    client, stub = served
    refused = post(client, "u_admin", path, body)
    assert refused.status_code == 404
    assert "switched off" in refused.json()["message"]
    assert stub.commits == 0 and settings.writes == []


@pytest.mark.parametrize(
    ("path", "words"),
    [(f"{BROWSER}/targets/books/retire", "is not declared")],
)
def test_taking_back_never_asks_the_switch(
    served: tuple[TestClient, Stub], held: Declared, path: str, words: str
) -> None:
    """With the switch off and nothing declared, the refusal is that it is not declared, and no
    setting was read to decide it. Delete this and a permission signed while the switch was on
    cannot be withdrawn with it off, which is a grant with no way back."""
    client, stub = served
    refused = post(client, "u_admin", path)
    assert refused.status_code == 404 and words in refused.json()["message"]
    assert held.asked == 1
    assert not any(
        isinstance(one, Select)
        and [d["name"] for d in one.column_descriptions] == NAMESPACE_COLUMNS
        for one in stub.statements
    )


def test_an_exception_for_a_website_nobody_declared_is_refused_in_words(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """With the switch on. Delete this and an exception can be signed for a name that is not a
    website, and read by the compiler as a permission for a surface nobody declared."""
    settings.hold(BROWSER_DECLARATIONS.key, True, value_type="boolean")
    client, _ = served

    refused = post(
        client,
        "u_admin",
        f"{BROWSER}/exceptions",
        {"target": "books", "surface": "login", "days": 5, "reason": "a reason long enough"},
    )

    assert refused.status_code == 404 and "books is not declared" in refused.json()["message"]


def test_a_document_the_codec_refuses_is_refused_with_the_codecs_words(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and the person is told only that something was wrong."""
    settings.hold(BROWSER_DECLARATIONS.key, True, value_type="boolean")
    client, _ = served
    broken = {**DOCUMENT, "colour": "blue"}

    refused = post(client, "u_admin", f"{BROWSER}/targets", {"declaration": broken})

    assert refused.status_code == 404 and "colour" in refused.json()["message"]


@pytest.mark.parametrize("days", [0, 91, -1])
def test_a_permission_longer_than_a_quarter_or_shorter_than_a_day_is_refused_at_the_door(
    served: tuple[TestClient, Stub], settings: SettingRows, days: int
) -> None:
    """Delete this and the length is the codec's alone, which a client skipping this layer
    would meet only at the table."""
    settings.hold(BROWSER_DECLARATIONS.key, True, value_type="boolean")
    client, _ = served

    refused = post(
        client,
        "u_admin",
        f"{BROWSER}/exemptions",
        {"skill": "s", "target": "books", "days": days, "reason": "a reason long enough"},
    )

    assert refused.status_code == 422


def test_an_exemption_for_a_website_nobody_declared_is_refused_in_words(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """With the switch on. Delete this and an exemption can be signed for a name that is not a
    website, and sit in the table naming nothing."""
    settings.hold(BROWSER_DECLARATIONS.key, True, value_type="boolean")
    client, _ = served

    refused = post(
        client,
        "u_admin",
        f"{BROWSER}/exemptions",
        {"skill": "file-return", "target": "books", "days": 5, "reason": "a reason long enough"},
    )

    assert refused.status_code == 404 and "books is not declared" in refused.json()["message"]
