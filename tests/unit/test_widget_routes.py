"""The widget's session route over HTTP: a listed site is handed a session, an unlisted one and a
busy one are told why not, and the two registers of a refusal stay apart.

Driven through the real application, so the route is mounted the way an install mounts it and the
settings it reads its allowlist from are the application's own.

Task ids: M10.5.5
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import create_app
from brain.channels.widget import (
    SESSION_ID_PREFIX,
    WIDGET_SESSION_ABSOLUTE_MAX,
    WIDGET_SESSION_IDLE,
    WidgetSessions,
)
from brain.ops.limits import WIDGET_MINTS_PER_MINUTE
from brain.settings import Settings
from brain.widget_routes import MINTED_FOR_NOBODY, WIDGET_SESSIONS_PATH, sessions_of

SITE = "https://shop.example.invalid"
ELSEWHERE = "https://elsewhere.example.invalid"
PATH = f"{API_PREFIX}{WIDGET_SESSIONS_PATH}"


@pytest.fixture
def client() -> Iterator[tuple[TestClient, FastAPI]]:
    app = create_app(Settings(env="development", widget_origins=(SITE,)))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app


def test_a_listed_site_is_handed_a_session_that_ends_within_the_widgets_bounds(
    client: tuple[TestClient, FastAPI],
) -> None:
    """**The leaf's minting half.** Delete this and every refusal below could be the only thing
    the route ever answers, which a route refusing everything would satisfy."""
    http, _ = client
    before = datetime.now(tz=UTC)

    response = http.post(PATH, headers={"Origin": SITE})
    after = datetime.now(tz=UTC)

    assert response.status_code == 201
    body = response.json()
    assert body["session"].startswith(SESSION_ID_PREFIX)
    expires = datetime.fromisoformat(body["expires_at"])
    absolute = datetime.fromisoformat(body["absolute_expiry"])
    # Bounded by the clock either side of the request, not by a fixed slack after it: a loaded
    # runner took eight seconds over this request on 2026-09-30 and a five-second slack failed.
    earliest = before.replace(microsecond=0) + WIDGET_SESSION_IDLE
    assert earliest <= expires <= after + WIDGET_SESSION_IDLE
    assert absolute <= after + WIDGET_SESSION_ABSOLUTE_MAX
    assert set(body) == {"session", "expires_at", "absolute_expiry"}


def test_an_unlisted_site_is_refused_with_the_widgets_sentence_and_no_window_is_made(
    client: tuple[TestClient, FastAPI],
) -> None:
    """403, the public sentence, no `Retry-After`, and nothing written to the mint windows.

    Delete this and a caller inventing origins could make a window per invented name, or be told
    to wait for an allowlist that waiting will never change."""
    http, app = client

    answers = [
        http.post(PATH, headers={"Origin": ELSEWHERE}),
        http.post(PATH),
    ]

    assert [one.status_code for one in answers] == [403, 403]
    assert {one.json()["message"] for one in answers} == {
        "This site is not set up to use this assistant."
    }
    assert all("retry-after" not in one.headers for one in answers)
    assert all(ELSEWHERE not in one.text for one in answers)
    assert sessions_of(app.state).windows == WidgetSessions(allowed=frozenset()).windows


def test_a_site_over_its_mint_rate_is_told_to_wait_and_is_not_told_the_numbers(
    client: tuple[TestClient, FastAPI],
) -> None:
    """**The leaf's abuse guard.** The mint after the minute's allowance is 429 with a wait, and
    the body names no origin and no figure.

    Delete this and the route could mint without asking the guard, and one page could open a
    session per request for ever."""
    http, _ = client

    minted = [http.post(PATH, headers={"Origin": SITE}) for _ in range(WIDGET_MINTS_PER_MINUTE)]
    over = http.post(PATH, headers={"Origin": SITE})

    assert [one.status_code for one in minted] == [201] * WIDGET_MINTS_PER_MINUTE
    assert over.status_code == 429
    assert int(over.headers["retry-after"]) >= 1
    assert over.json()["message"] == (
        "Too many chat sessions have been started here just now; please try again shortly."
    )
    assert SITE not in over.text and str(WIDGET_MINTS_PER_MINUTE) not in over.json()["message"]


def test_the_allowlist_is_the_installs_own_widget_origins() -> None:
    """An install with none lists nobody. Delete this and the store could be built from a default
    that admits somebody the install never named."""
    empty = create_app(Settings(env="development"))
    listed = create_app(Settings(env="development", widget_origins=(SITE,)))

    assert sessions_of(empty.state).allowed == frozenset()
    assert sessions_of(listed.state).allowed == frozenset({SITE})
    assert sessions_of(listed.state) is sessions_of(listed.state)


def test_the_route_is_the_one_path_minted_for_nobody() -> None:
    """Held to the path the router serves, so the exception in the gate's own test cannot name a
    path this module does not serve. Delete this and the two could drift apart."""
    app = create_app(Settings(env="development"))

    assert frozenset({PATH}) == MINTED_FOR_NOBODY
    assert PATH in app.openapi()["paths"]
