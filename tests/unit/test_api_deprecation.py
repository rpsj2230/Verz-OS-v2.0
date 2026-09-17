"""The deprecation policy: a retired route announces itself, with a floor on the notice.

Task ids: M31.1.4.1
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api_deprecation import (
    MINIMUM_NOTICE,
    Deprecation,
    deprecated,
    undeclared_deprecations,
)
from brain.app import create_app
from brain.settings import Settings

#: Far from any wall clock, because nothing here is about the present. See CLAUDE.md on fixtures.
SINCE = date(2019, 1, 1)
SUNSET = SINCE + MINIMUM_NOTICE


def an_app_with_one_retired_route() -> FastAPI:
    app = FastAPI()
    notice = Deprecation(since=SINCE, sunset=SUNSET, successor="/api/v1/new")

    @app.get("/api/v1/old", **deprecated(notice))
    async def old() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/v1/new")
    async def new() -> dict[str, str]:
        return {"ok": "yes"}

    return app


def test_a_retired_route_says_so_on_every_answer_and_a_current_one_does_not() -> None:
    """The headers are the only notice an integration's author ever sees.

    Delete this and `deprecated` can mark the operation in OpenAPI and send nothing, which is a
    notice written where no client looks."""
    with TestClient(an_app_with_one_retired_route()) as c:
        old = c.get("/api/v1/old")
        new = c.get("/api/v1/new")

    assert old.status_code == 200
    assert old.headers["deprecation"] == "@1546300800"
    assert old.headers["sunset"] == "Mon, 01 Apr 2019 00:00:00 GMT"
    assert old.headers["link"] == '</api/v1/new>; rel="successor-version"'
    assert "deprecation" not in new.headers and "sunset" not in new.headers


def test_notice_shorter_than_the_floor_or_a_successor_outside_the_api_is_refused() -> None:
    """Delete this and a route can be retired with a day's notice, or pointed at a page that is
    not a route, and every other test still passes."""
    with pytest.raises(ValueError, match="shorter than"):
        Deprecation(since=SINCE, sunset=SUNSET - timedelta(days=1), successor="/api/v1/new")
    with pytest.raises(ValueError, match="not a route"):
        Deprecation(since=SINCE, sunset=SUNSET, successor="https://elsewhere.example/new")
    assert Deprecation(since=SINCE, sunset=SUNSET, successor="/api/v2/new").sunset == SUNSET


def test_the_floor_is_at_least_a_quarter() -> None:
    """Asserted against a figure outside the constant: a floor cut to a week would pass every test
    that builds its dates from `MINIMUM_NOTICE`."""
    assert timedelta(days=90) <= MINIMUM_NOTICE


def test_the_walk_finds_a_route_marked_deprecated_by_hand() -> None:
    """A bare `deprecated=True` sends no headers. Delete this and the walk below is satisfied by a
    function that returns nothing."""
    app = an_app_with_one_retired_route()

    @app.get("/api/v1/quiet", deprecated=True)
    async def quiet() -> dict[str, str]:
        return {"ok": "yes"}

    assert undeclared_deprecations(app.openapi()) == ["GET /api/v1/quiet"]


def test_every_deprecated_operation_the_application_serves_carries_its_notice() -> None:
    """The whole API description, as `console/scripts/export-openapi.py` builds it.

    Delete this and a route marked deprecated by hand ships with no headers and no date."""
    document = create_app(Settings(env="development", run_migrations=False)).openapi()

    assert document["paths"], "the document has no paths, so this walked nothing"
    assert undeclared_deprecations(document) == []
