"""The Storage screen over HTTP: who may read it, what it says of each bucket, what it never says.

Driven through the real application with the gate from `tests/unit/test_webhook_routes.py`. The
screen asks no store, so there is nothing to stand in for; `storage_view` is also called directly
with its settings passed, which is how the address rule is tested without an environment.

Task ids: M27.8.15
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.install import BY_NAME
from brain.ops.storage import BUCKETS, ObjectKind, bucket_for
from brain.storage_routes import (
    ENDPOINT_SETTING,
    PREFIX_SETTING,
    STORAGE_AUTHORITY,
    STORAGE_PATH,
    shown_address,
    storage_view,
)
from tests.unit.test_webhook_routes import NoDatabase, headers, wiring

LISTING = f"{API_PREFIX}{STORAGE_PATH}"
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    "u_narrow": (
        Grant(
            capability=STORAGE_AUTHORITY,
            scope=Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),)),
        ),
    ),
    "u_wide": (Grant(capability=Capability(value="admin:credential"), scope=Scope.unrestricted()),),
    "u_prefix": (),
    "u_admin": (Grant(capability=STORAGE_AUTHORITY, scope=Scope.unrestricted()),),
    "u_elsewhere": (),
}


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring(GRANTS)
        app.state.db_sessions = NoDatabase()
        yield c


@pytest.fixture
def app() -> Iterator[FastAPI]:
    built: FastAPI = create_app(Settings(env="development"))
    yield built


def test_only_a_reader_holding_the_capability_over_everything_may_open_the_screen(
    client: TestClient,
) -> None:
    """The store serves the whole install, so a grant over one department is refused, and so is a
    different administration grant. One refusal, the taxonomy's. The positive sibling is `u_admin`.
    Delete this and `holds` replaces held over everything, which reads as the same in review."""
    for pid in ("u_none", "u_narrow", "u_wide"):
        refused = client.get(LISTING, headers=headers(pid))
        assert refused.status_code == 404, pid
        assert refused.json()["message"] == Absent.public_message
    assert client.get(LISTING, headers=headers("u_admin")).status_code == 200
    assert STORAGE_AUTHORITY.value.startswith("admin:")


def test_a_password_only_session_holding_the_capability_is_refused(client: TestClient) -> None:
    """An `admin:` verb, so `gate.admission` withholds it without a second factor. Delete this and
    the capability can be respelled `read:` to open the screen to a password."""
    assert client.get(LISTING, headers=headers("u_admin", {"amr": ["pwd"]})).status_code == 404


def test_every_bucket_is_shown_with_its_retention_its_reason_and_what_goes_there(
    client: TestClient,
) -> None:
    """Read against `brain.ops.storage` rather than restated, and every object kind lands in the
    bucket `bucket_for` decides. Delete this and a bucket drawn with the wrong retention, or a kind
    listed under the wrong bucket, passes."""
    body = client.get(LISTING, headers=headers("u_admin")).json()
    assert [one["name"] for one in body["buckets"]] == [one.name for one in BUCKETS]
    for shown, declared in zip(body["buckets"], BUCKETS, strict=True):
        assert shown["retention_days"] == declared.retention_days
        assert shown["retention_reason"] == declared.retention_reason
        assert (shown["versioned"], shown["public_read"]) == (declared.versioned, False)
    placed = {kind: shown["name"] for shown in body["buckets"] for kind in shown["kinds"]}
    assert placed == {kind.value: bucket_for(kind).name for kind in ObjectKind}
    assert body["findings"] == []
    assert body["usage"] and body["names"] and body["retention"] and body["connection"]


def test_no_field_on_the_screen_could_hold_an_objects_name() -> None:
    """The response model is the closed list of what is said, and none of it is an object listing.
    Delete this and a `objects` field added for convenience ships every name in a bucket."""
    view = storage_view(LONG_AGO, env={}, saved={})
    assert set(view.model_dump()) == {
        "buckets",
        "findings",
        "endpoint",
        "connection",
        "usage",
        "names",
        "retention",
        "read_at",
    }
    assert set(view.buckets[0].model_dump()) == {
        "name",
        "holds",
        "retention_days",
        "retention_reason",
        "versioned",
        "public_read",
        "kinds",
    }


@pytest.mark.parametrize(
    ("given", "shown"),
    [
        (
            "https://key:secret@store.example.test:9000/bucket?x=1",
            "https://store.example.test:9000",
        ),
        ("http://seaweedfs:8333", "http://seaweedfs:8333"),
        ("https://[2001:db8::1]:443/", "https://[2001:db8::1]:443"),
        ("not a url", None),
        ("ftp://store.example.test", None),
        ("https://store.example.test:notaport", None),
    ],
)
def test_the_store_address_is_shown_without_anything_that_could_be_a_credential(
    given: str, shown: str | None
) -> None:
    """A user name, a password, a path and a query are dropped, and something that is not an http
    address is shown as unknown rather than echoed. Delete this and the setting is echoed whole,
    password included."""
    assert shown_address(given) == shown


def test_the_setting_is_read_through_the_one_reader_saved_first_and_its_default_named() -> None:
    """`brain.install.value_of`, so a saved answer outranks the environment. Delete this and the
    screen shows the template's address on an install whose wizard saved another."""
    default = storage_view(LONG_AGO, env={}, saved={})
    assert default.endpoint.from_default is True
    assert default.endpoint.address == shown_address(BY_NAME[ENDPOINT_SETTING].default)
    saved = storage_view(
        LONG_AGO,
        env={ENDPOINT_SETTING: "https://env.example.test"},
        saved={ENDPOINT_SETTING: "https://saved.example.test", PREFIX_SETTING: "acme"},
    )
    assert (saved.endpoint.address, saved.endpoint.prefix) == ("https://saved.example.test", "acme")
    assert saved.endpoint.from_default is False
