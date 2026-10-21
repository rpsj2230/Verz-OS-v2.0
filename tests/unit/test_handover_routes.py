"""The handover pack over HTTP: the statement or why there is none, the subprocessors, the
owners and the review.

Driven through the real application with the people and tokens of
`tests/unit/test_install_routes.py`, the backup bucket as a listing, and the settings table held in
memory, so a save is read back by the same code that reads it on an install.

**Every refusal has a sibling that works.** The statement is refused for an absence and produced for
a presence; an owner with no contact is refused and one with a contact is kept.

Task ids: M30.5.4, M30.6.6, M37.4.2.4, M37.4.3.3, M37.4.3.5, M37.2.4.4
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.core.entitlement import Grant
from brain.handover_routes import HANDOVER_AUTHORITY, NO_STATEMENT_WITHOUT_THE_COPIES
from brain.migration.learning import THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING
from brain.ops.features_declared.handover_pack import HANDOVER_PACK
from brain.ops.reliability import recovery_objective
from tests.unit.test_api_routes import token_for
from tests.unit.test_install_routes import (
    INSTALL_GRANTS,
    SECOND_FACTOR,
    WHOLE,
    _app,
    _wiring,
    bucket_holding,
    get,
)

PATH = f"{API_PREFIX}/handover"
OWNERS = f"{PATH}/owners"
REVIEW = f"{PATH}/review"


def sessions(*, on: bool | None) -> tuple[Any, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from tests.fixtures import console_http
    from tests.fixtures.setting_rows import SettingRows

    rows = SettingRows()
    if on is not None:
        rows.hold(HANDOVER_PACK.key, on, value_type="boolean")
    console_http._STUB = console_http.Stub()
    console_http._STUB.answerers.append(rows.answer)
    return async_sessionmaker(class_=console_http.StubSession), rows


@pytest.fixture
def administrator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        INSTALL_GRANTS,
        "u_admin",
        (*INSTALL_GRANTS["u_admin"], Grant(capability=HANDOVER_AUTHORITY, scope=WHOLE)),
    )


def send(c: TestClient, method: str, path: str, pid: str, body: Any = None) -> Any:
    token = token_for(pid, claims=SECOND_FACTOR)
    return c.request(method, path, headers={"authorization": f"Bearer {token}"}, json=body)


@contextmanager
def running(
    *, on: bool | None, listing: tuple[tuple[str, str], ...] | None = None
) -> Iterator[tuple[TestClient, Any]]:
    """The application started, then given the gate, the settings and the bucket's listing."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = _wiring()
        made, rows = sessions(on=on)
        app.state.db_sessions = made
        if listing is not None:
            app.state.backup_objects = bucket_holding(*listing)
        yield client, rows


OWNER = {
    "responsibility": "knowledge",
    "name": "Example Person",
    "contact": "example@example.invalid",
}
ALL_THREE = [
    {**OWNER, "responsibility": "knowledge"},
    {**OWNER, "responsibility": "grants", "name": "Another Person"},
    {**OWNER, "responsibility": "connectors", "name": "Third Person"},
]


# ------------------------------------------------------------------------------- who may ask


def test_a_caller_without_the_install_authority_is_refused_as_anyone_the_screen_does_not_answer(
    administrator: None,
) -> None:
    """Delete this and whoever may read the backup page can read the company's subprocessors and
    owners, or write them."""
    with running(on=True) as (client, _):
        reader = get(client, "u_wide", PATH)
        nobody = get(client, "u_none", PATH)
        write = send(client, "PUT", OWNERS, "u_wide", {"owners": ALL_THREE})
    assert reader.status_code == nobody.status_code == write.status_code == 404
    assert reader.json()["message"] == nobody.json()["message"]


# ---------------------------------------------------------------------------- the statement


def test_with_no_bucket_read_the_statement_is_refused_in_words_and_not_made(
    administrator: None,
) -> None:
    """A promise signed on an absence. Delete this and a process that reads no copies states a
    recovery point it never looked for."""
    with running(on=False) as (client, _):
        body = get(client, "u_admin", PATH).json()
    assert body["service_level"] is None
    assert body["service_level_refused"] == NO_STATEMENT_WITHOUT_THE_COPIES
    assert body["ready"] is False


def manifest(coverage: str, method: str, age: timedelta) -> tuple[str, str]:
    finished = datetime.now(UTC) - age
    name = f"{coverage}-{int(finished.timestamp())}"
    return (
        f"{name}.manifest.json",
        json.dumps(
            {
                "backup_id": name,
                "coverage": coverage,
                "method": method,
                "destination": "s3://copies",
                "started_at": (finished - timedelta(minutes=1)).isoformat(),
                "finished_at": finished.isoformat(),
                "recoverable_to": finished.isoformat(),
                "size_bytes": 100,
            }
        ),
    )


def drill(profile_rto: int, *, canary: bool = True) -> tuple[str, str]:
    started = datetime.now(UTC) - timedelta(hours=1)
    return (
        "database-x-drill-1.drill.json",
        json.dumps(
            {
                "backup_id": "database-x",
                "started_at": started.isoformat(),
                "finished_at": (started + timedelta(seconds=min(60, profile_rto))).isoformat(),
                "into_scratch": True,
                "checks": [
                    {"check": "schema_complete", "passed": True, "detail": "all present"},
                    {"check": "smoke_query", "passed": True, "detail": "counts came back"},
                    {"check": "permission_canary", "passed": canary, "detail": "stranger refused"},
                ],
            }
        ),
    )


def every_coverage() -> tuple[tuple[str, str], ...]:
    return (
        manifest("database", "full", timedelta(minutes=2)),
        manifest("object_store", "snapshot", timedelta(minutes=2)),
        manifest("configuration", "snapshot", timedelta(minutes=2)),
    )


def test_the_statement_is_refused_naming_the_coverage_nothing_has_copied(
    administrator: None,
) -> None:
    """A database copy alone does not meet a recovery point that covers the object store. Delete
    this and the statement is made over the one coverage that has a copy."""
    with running(on=False, listing=(manifest("database", "full", timedelta(minutes=2)),)) as (
        client,
        _,
    ):
        body = get(client, "u_admin", PATH).json()
    assert body["service_level"] is None
    assert "object_store" in body["service_level_refused"]


def test_the_statement_is_refused_until_a_rehearsal_has_verified_a_copy(
    administrator: None,
) -> None:
    """Every copy present, no rehearsal. Delete this and an unmeasured recovery time is a figure
    in a contract."""
    with running(on=False, listing=every_coverage()) as (client, _):
        body = get(client, "u_admin", PATH).json()
    assert body["service_level"] is None
    assert "no restore has ever verified" in body["service_level_refused"]


def test_the_statement_is_made_when_every_copy_is_inside_the_point_and_a_rehearsal_verified(
    administrator: None,
) -> None:
    """The positive sibling, with the profile's own figures. Delete this and the route can refuse
    everything."""
    profile = _app().state.settings.profile
    objective = recovery_objective(profile)
    with running(on=False, listing=(*every_coverage(), drill(objective.rto_seconds))) as (
        client,
        _,
    ):
        body = get(client, "u_admin", PATH).json()
    assert body["service_level_refused"] == "", body["service_level_refused"]
    level = body["service_level"]
    assert level["profile"] == profile
    assert level["rpo_seconds"] == objective.rpo_seconds
    assert level["rto_seconds"] == objective.rto_seconds
    assert level["measured_rto_seconds"] <= objective.rto_seconds


def test_a_rehearsal_that_failed_its_canary_does_not_make_the_statement(
    administrator: None,
) -> None:
    """A failed attempt is not a verified one. Delete this and the statement is made on a copy
    that answers everything to everybody."""
    objective = recovery_objective(_app().state.settings.profile)
    listing = (*every_coverage(), drill(objective.rto_seconds, canary=False))
    with running(on=False, listing=listing) as (client, _):
        body = get(client, "u_admin", PATH).json()
    assert body["service_level"] is None
    assert "no restore has ever verified" in body["service_level_refused"]


# ---------------------------------------------------------------------------- subprocessors


def test_the_subprocessors_are_the_providers_whose_key_is_held_and_none_is_refused(
    administrator: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the list names a provider nobody configured, or an install with no key
    states that it processes nothing."""
    from brain import handover_routes

    with running(on=False) as (client, _):
        monkeypatch.setattr(handover_routes, "held_providers", lambda: frozenset())
        none = get(client, "u_admin", PATH).json()
        monkeypatch.setattr(handover_routes, "held_providers", lambda: frozenset({"anthropic"}))
        one = get(client, "u_admin", PATH).json()
    assert (
        none["subprocessors"] is None
        and "cannot answer a question" in none["subprocessors_refused"]
    )
    assert [row["provider"] for row in one["subprocessors"]] == ["anthropic"]
    assert one["subprocessors"][0]["purpose"]


# -------------------------------------------------------------------------------- the owners


def test_owners_are_refused_while_the_switch_is_off_and_kept_when_it_is_on(
    administrator: None,
) -> None:
    """Delete this and the write ignores the switch, or never works."""
    for state, expected in ((False, 404), (None, 404), (True, 200)):
        with running(on=state) as (client, rows):
            answer = send(client, "PUT", OWNERS, "u_admin", {"owners": ALL_THREE})
        assert answer.status_code == expected, (state, answer.text)
        wrote = [w for w in rows.writes if w["key"] == "handover.owners"]
        assert bool(wrote) is (expected == 200)


def test_a_saved_list_is_read_back_and_what_is_missing_is_said(administrator: None) -> None:
    """The store and the read agree. Delete this and a saved owner is not shown, or a missing
    one is not reported."""
    with running(on=True) as (client, rows):
        answer = send(client, "PUT", OWNERS, "u_admin", {"owners": ALL_THREE[:2]}).json()
    assert [row["responsibility"] for row in answer["owners"]] == ["knowledge", "grants"]
    assert answer["owner_gaps"] == ["connectors: nobody at the client is named as the owner"]
    assert answer["ready"] is False
    assert rows.rows["handover.owners"].value["owners"][0]["name"] == "Example Person"


def test_an_owner_with_no_way_to_be_reached_is_refused_in_the_words_launch_gives(
    administrator: None,
) -> None:
    """Delete this and a name with no contact is a handover nobody can act on."""
    with running(on=True) as (client, rows):
        answer = send(
            client,
            "PUT",
            OWNERS,
            "u_admin",
            {"owners": [{**OWNER, "contact": "   "}]},
        )
    assert answer.status_code == 404
    assert "there is no way to ask them" in answer.text
    assert "handover.owners" not in rows.rows


def test_a_stored_owner_that_no_longer_reads_is_reported_and_not_raised(
    administrator: None,
) -> None:
    """A row put there by hand. Delete this and one bad row is a 500 on the whole pack."""
    with running(on=False) as (client, rows):
        rows.hold(
            "handover.owners", {"owners": [{"responsibility": "knowledge"}]}, value_type="json"
        )
        body = get(client, "u_admin", PATH)
    assert body.status_code == 200
    assert body.json()["owners"] == []
    assert "could not be read" in body.json()["unreadable"][0]


# --------------------------------------------------------------------------------- the review


def test_a_review_inside_thirty_days_is_booked_and_shown(administrator: None) -> None:
    """The positive sibling. Delete this and the booking never works."""
    with running(on=True) as (client, rows):
        answer = send(
            client,
            "PUT",
            REVIEW,
            "u_admin",
            {"launched_on": "2999-01-01", "review_booked_for": "2999-01-30"},
        ).json()
    assert answer["review"] == {"launched_on": "2999-01-01", "review_booked_for": "2999-01-30"}
    assert answer["review_gaps"] == []
    assert rows.rows["handover.review"].value["review_booked_for"] == "2999-01-30"


@pytest.mark.parametrize(
    ("booked", "why"),
    [("2999-01-01", "reviews nothing"), ("2999-03-01", "days after launch")],
)
def test_a_review_on_launch_day_or_past_the_window_is_refused_and_nothing_is_kept(
    administrator: None, booked: str, why: str
) -> None:
    """Delete this and a review nobody will hold is booked."""
    with running(on=True) as (client, rows):
        answer = send(
            client,
            "PUT",
            REVIEW,
            "u_admin",
            {"launched_on": "2999-01-01", "review_booked_for": booked},
        )
    assert answer.status_code == 404 and why in answer.text
    assert "handover.review" not in rows.rows


def test_with_no_review_booked_the_pack_says_so(administrator: None) -> None:
    """Delete this and an unbooked review reads as a complete pack."""
    with running(on=False) as (client, _):
        body = get(client, "u_admin", PATH).json()
    assert body["review"] is None
    assert len(body["review_gaps"]) == 1


# ------------------------------------------------------------------------------ the learning


def test_the_pack_carries_the_sentence_that_the_new_system_starts_without_the_old_ones_learning(
    administrator: None,
) -> None:
    """Delete this and the handover omits what the leaf says it must state plainly."""
    with running(on=False) as (client, _):
        body = get(client, "u_admin", PATH).json()
    assert body["learning"]["sentence"] == THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING
    assert body["learning"]["derived"] == 0


def test_the_routes_are_served_with_the_verbs_the_pack_uses() -> None:
    """Delete this and a verb moves without the console noticing."""
    paths = _app().openapi()["paths"]
    assert set(paths[PATH]) == {"get"}
    assert set(paths[OWNERS]) == {"put"} and set(paths[REVIEW]) == {"put"}


def test_a_stored_owner_naming_a_responsibility_nobody_declares_is_reported_and_not_raised(
    administrator: None,
) -> None:
    """The other way a hand-made row fails to read: a value, not a missing key. Delete this and a
    typo in a stored responsibility is a 500 on the whole pack."""
    bad = {"owners": [{"responsibility": "payroll", "name": "A", "contact": "a@example.invalid"}]}
    with running(on=False) as (client, rows):
        rows.hold("handover.owners", bad, value_type="json")
        body = get(client, "u_admin", PATH)
    assert body.status_code == 200
    assert body.json()["owners"] == [] and body.json()["unreadable"]


def test_the_pack_is_ready_only_when_every_part_is_present_and_every_stored_value_reads(
    administrator: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive case for `ready`, and the one thing that must turn it off again. Delete this
    and `ready` is either never true or true over a record the pack could not read."""
    from brain import handover_routes

    monkeypatch.setattr(handover_routes, "held_providers", lambda: frozenset({"anthropic"}))
    objective = recovery_objective(_app().state.settings.profile)
    listing = (*every_coverage(), drill(objective.rto_seconds))
    with running(on=True, listing=listing) as (client, rows):
        send(client, "PUT", OWNERS, "u_admin", {"owners": ALL_THREE})
        done = send(
            client,
            "PUT",
            REVIEW,
            "u_admin",
            {"launched_on": "2999-01-01", "review_booked_for": "2999-01-30"},
        ).json()
        assert done["ready"] is True and done["unreadable"] == []
        rows.hold("handover.review", {"launched_on": "nonsense"}, value_type="json")
        spoiled = get(client, "u_admin", PATH).json()
    assert spoiled["ready"] is False
    assert spoiled["unreadable"]
