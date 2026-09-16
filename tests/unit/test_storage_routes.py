"""The Storage screen over HTTP: who may read it, what it says of each bucket, what it never says.

Driven through the real application with the gate from `tests/unit/test_webhook_routes.py`. The
store is `tests.fixtures.fake_s3.FakeS3` behind the real client, attached as the lifespan would
attach it; `storage_view` is also called directly with its settings passed, which is how the
address rule is tested without an environment.

Task ids: M27.8.15
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.install import BY_NAME
from brain.ops.object_store import (
    NO_VAULT_SO_NO_STORE_CREDENTIAL,
    ObjectStore,
    S3Backend,
    StoreCredential,
)
from brain.ops.storage import BUCKETS, Backend, ObjectKind, bucket_for, config_for
from brain.storage_routes import (
    ENDPOINT_SETTING,
    NOT_COUNTED_WITHOUT_A_STORE,
    PREFIX_SETTING,
    STORAGE_AUTHORITY,
    STORAGE_PATH,
    STORE_CONNECTED,
    THE_STORE_DID_NOT_ANSWER_FOR_THIS_BUCKET,
    USAGE_IS_COUNTED_AND_NEVER_LISTED,
    USAGE_IS_NOT_MEASURED,
    BucketUsageView,
    BucketView,
    shown_address,
    storage_view,
)
from tests.fixtures.fake_s3 import FakeS3
from tests.unit.test_webhook_routes import NoDatabase, headers, wiring

LISTING = f"{API_PREFIX}{STORAGE_PATH}"
KEY = StoreCredential(access_key_id="brain-test-access", secret_access_key="brain-test-secret")
ENDPOINT = "http://objects.example.test:8333"
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
        "manages",
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
        "usage",
        "usage_unread",
    }
    counted = storage_view(
        LONG_AGO,
        env={},
        saved={},
        store=ObjectStore(backend=_backend(FakeS3(credential=KEY)), prefix="brain"),
        counted={one.name: None for one in BUCKETS} | {"assets": _usage(1, 1)},
    )
    assert set(counted.buckets[0].model_dump()["usage"]) == {"objects", "bytes_stored", "complete"}


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


# ------------------------------------------------------------------ against a store


def _backend(store: FakeS3) -> S3Backend:
    return S3Backend(
        config_for(Backend.SEAWEEDFS, endpoint_url=ENDPOINT), KEY, transport=store.transport()
    )


def _usage(objects: int, size: int) -> Any:
    from brain.ops.storage import BucketUsage

    return BucketUsage(objects=objects, bytes_stored=size, complete=True)


def _a_store() -> FakeS3:
    """Three buckets of the four, so one does not answer; names that would say what files are."""
    return (
        FakeS3(credential=KEY, page=2)
        .holding(
            "assets",
            {
                "brain/artifacts/payload/board-minutes-redundancies": b"x" * 10,
                "brain/knowledge/salary-bands-q3x": b"y" * 5,
                "brain/letterhead-7f3k": b"z" * 3,
                "another-install/letterhead-9z2w": b"w" * 999,
            },
        )
        .holding("recordings", {})
        .holding(
            "backups",
            {"copy-20190304T020000Z.dump": b"d" * 40, "copy-20190304.manifest.json": b"{}"},
        )
    )


@pytest.fixture
def connected() -> Iterator[tuple[TestClient, FakeS3]]:
    built: FastAPI = create_app(Settings(env="development"))
    store = _a_store()
    with TestClient(built, raise_server_exceptions=False) as c:
        built.state.gate = wiring(GRANTS)
        built.state.db_sessions = NoDatabase()
        built.state.object_store = ObjectStore(backend=_backend(store), prefix="brain")
        yield c, store


def test_a_connected_store_is_counted_per_bucket_under_this_installs_prefix(
    connected: tuple[TestClient, FakeS3],
) -> None:
    """Assets under the install's prefix and not another install's, the backup bucket at its root
    where the nightly copy is written, and an empty bucket as a count of none. Delete this and the
    screen can go back to describing buckets it never asked about, or count a neighbour's files."""
    client, _ = connected
    body = client.get(LISTING, headers=headers("u_admin")).json()
    rows = {one["name"]: one for one in body["buckets"]}
    assert rows["assets"]["usage"] == {"objects": 3, "bytes_stored": 18, "complete": True}
    assert rows["recordings"]["usage"] == {"objects": 0, "bytes_stored": 0, "complete": True}
    assert rows["backups"]["usage"] == {"objects": 2, "bytes_stored": 42, "complete": True}
    assert (body["connection"], body["usage"]) == (
        STORE_CONNECTED,
        USAGE_IS_COUNTED_AND_NEVER_LISTED,
    )


def test_no_object_name_reaches_the_screen_from_a_store_that_holds_named_objects(
    connected: tuple[TestClient, FakeS3],
) -> None:
    """The names are read inside the client to be counted and never leave it. Delete this and a
    field added to carry "the largest file" sends a name saying what a document is about."""
    client, store = connected
    response = client.get(LISTING, headers=headers("u_admin"))
    assert response.status_code == 200
    names = [name for held in store.buckets.values() for name in held]
    assert len(names) == 6
    for name in names:
        assert name not in response.text
        assert name.rsplit("/", 1)[-1] not in response.text


def test_a_bucket_the_store_does_not_answer_for_says_so_and_the_others_are_still_counted(
    connected: tuple[TestClient, FakeS3],
) -> None:
    """Delete this and one bucket's failure is drawn as an empty bucket, or blanks the screen."""
    client, _ = connected
    rows = {
        one["name"]: one
        for one in client.get(LISTING, headers=headers("u_admin")).json()["buckets"]
    }
    assert rows["exports"]["usage"] is None
    assert rows["exports"]["usage_unread"] == THE_STORE_DID_NOT_ANSWER_FOR_THIS_BUCKET
    assert rows["assets"]["usage"] is not None


def test_a_reader_who_may_not_open_the_screen_cannot_make_the_store_be_listed(
    connected: tuple[TestClient, FakeS3],
) -> None:
    """The capability is checked before the store is asked. Delete this and anybody who can reach
    the port can make the application list every bucket on each request."""
    client, store = connected
    for pid in ("u_none", "u_narrow", "u_wide"):
        assert client.get(LISTING, headers=headers(pid)).status_code == 404
    assert store.asked == []
    assert client.get(LISTING, headers=headers("u_admin")).status_code == 200
    assert store.asked != []


def test_with_no_store_every_bucket_says_it_was_not_counted_and_the_connection_says_why(
    client: TestClient,
) -> None:
    """The lifespan connected to nothing because there is no vault, and the screen says that in the
    store's own words. Delete this and a process with no store draws four empty buckets."""
    body = client.get(LISTING, headers=headers("u_admin")).json()
    assert body["connection"] == NO_VAULT_SO_NO_STORE_CREDENTIAL
    assert body["usage"] == USAGE_IS_NOT_MEASURED
    assert {one["usage_unread"] for one in body["buckets"]} == {NOT_COUNTED_WITHOUT_A_STORE}
    assert all(one["usage"] is None for one in body["buckets"])


def test_a_bucket_row_is_counted_or_says_why_not_and_never_both_or_neither() -> None:
    """Delete this and a renderer handed neither draws a bucket holding nothing."""
    declared: dict[str, Any] = {
        "name": "assets",
        "holds": "h",
        "retention_days": None,
        "retention_reason": "r",
        "versioned": False,
        "public_read": False,
        "kinds": [],
    }
    with pytest.raises(ValueError, match="counted or says why"):
        BucketView(**declared)
    with pytest.raises(ValueError, match="counted or says why"):
        BucketView(
            **declared,
            usage=BucketUsageView(objects=1, bytes_stored=1, complete=True),
            usage_unread="both",
        )
    assert BucketView(**declared, usage_unread="not counted").usage is None
