"""The widget's routes over HTTP: a listed site is handed a session, an unlisted one and a busy one
are told why not, and the two registers of a refusal stay apart; and a question asked in a session
is answered from what the public search found, or as nothing found.

Driven through the real application, so the routes are mounted the way an install mounts them and
the settings the allowlist is read from are the application's own. The public search is a stand-in
here; `tests/unit/test_public_knowledge_db.py` runs the real one against PostgreSQL.

Task ids: M10.5.5, M10.7.2
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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
from brain.gate.abstain import NOT_FOUND_TEXT
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, KnowledgePassage
from brain.ops.limits import WIDGET_MINTS_PER_MINUTE
from brain.settings import Settings
from brain.widget_routes import (
    FROM_WHAT_THIS_SITE_PUBLISHES,
    MINTED_FOR_NOBODY,
    SESSION_ENDED,
    WIDGET_QUESTIONS_PATH,
    WIDGET_SESSIONS_PATH,
    sessions_of,
)

SITE = "https://shop.example.invalid"
ELSEWHERE = "https://elsewhere.example.invalid"
PATH = f"{API_PREFIX}{WIDGET_SESSIONS_PATH}"
ASK = f"{API_PREFIX}{WIDGET_QUESTIONS_PATH}"


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

    assert response.status_code == 201
    body = response.json()
    assert body["session"].startswith(SESSION_ID_PREFIX)
    expires = datetime.fromisoformat(body["expires_at"])
    absolute = datetime.fromisoformat(body["absolute_expiry"])
    assert expires <= before + WIDGET_SESSION_IDLE + timedelta(seconds=5)
    assert absolute <= before + WIDGET_SESSION_ABSOLUTE_MAX + timedelta(seconds=5)
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


def test_the_two_routes_are_the_paths_reached_by_nobody() -> None:
    """Held to the paths the router serves, so the exception in the gate's own test cannot name a
    path this module does not serve. Delete this and the two could drift apart."""
    app = create_app(Settings(env="development"))

    assert frozenset({PATH, ASK}) == MINTED_FOR_NOBODY
    assert {PATH, ASK} <= set(app.openapi()["paths"])


# ------------------------------------------------------------------ questions (M10.7.2)
def a_passage(word: str) -> KnowledgePassage:
    return KnowledgePassage(
        entity=KNOWLEDGE_ENTITY,
        id="upload.opening.0",
        document_id="upload.opening",
        title="Opening hours",
        section="Weekdays",
        document=f"We open at nine on weekdays, {word}.",
        department="web",
        visibility="department",
        owner_id="u_steward",
    )


class Search:
    """A public search that finds one word's passage and nothing else, and records each question."""

    def __init__(self, word: str) -> None:
        self.word = word
        self.asked: list[str] = []

    async def __call__(self, question: str) -> tuple[KnowledgePassage, ...]:
        self.asked.append(question)
        return (a_passage(self.word),) if self.word in question else ()


def minted(http: TestClient, origin: str = SITE) -> str:
    return str(http.post(PATH, headers={"Origin": origin}).json()["session"])


def test_a_question_is_answered_with_the_published_passages_the_search_found(
    client: tuple[TestClient, FastAPI],
) -> None:
    """**The leaf's answering half.** The passage's words, its title and its section, and nothing
    about who stewards it or where it sits. Delete this and a route answering every question as
    not found would satisfy every refusal below."""
    http, app = client
    app.state.widget_search = Search("HOURSQZ")

    answer = http.post(
        ASK,
        json={"session": minted(http), "question": "When do you open HOURSQZ?"},
        headers={"Origin": SITE},
    )

    assert answer.status_code == 200
    assert answer.json() == {
        "answer": FROM_WHAT_THIS_SITE_PUBLISHES,
        "passages": [
            {
                "document_id": "upload.opening",
                "title": "Opening hours",
                "section": "Weekdays",
                "text": "We open at nine on weekdays, HOURSQZ.",
            }
        ],
    }


def test_a_question_about_anything_unfound_is_one_answer_whatever_it_was_about(
    client: tuple[TestClient, FastAPI],
) -> None:
    """Two questions the search finds nothing for are one body, one status and one set of headers,
    and the body is the answer lane's own not-found sentence. Delete this and a route could word
    its not-found by what was asked, which is the probe needs-rupash 26 names."""
    http, app = client
    app.state.widget_search = Search("HOURSQZ")
    session = minted(http)

    one = http.post(
        ASK, json={"session": session, "question": "salaries"}, headers={"Origin": SITE}
    )
    two = http.post(
        ASK, json={"session": session, "question": "QZNOTHING"}, headers={"Origin": SITE}
    )

    assert (
        (one.status_code, one.json())
        == (two.status_code, two.json())
        == (
            200,
            {"answer": NOT_FOUND_TEXT, "passages": []},
        )
    )
    shown = {"content-type", "cache-control"}
    assert {k: v for k, v in one.headers.items() if k in shown} == {
        k: v for k, v in two.headers.items() if k in shown
    }


def test_a_session_that_is_unknown_or_another_sites_asks_nothing_and_is_not_extended(
    client: tuple[TestClient, FastAPI],
) -> None:
    """401 with the widget's sentence, the search never asked, and a session presented from the
    wrong site left to lapse on its own clock. Delete this and a session id copied off one site
    asks from any other, and every such attempt keeps it alive."""
    http, app = client
    search = Search("HOURSQZ")
    app.state.widget_search = search
    session = minted(http)
    before = sessions_of(app.state).get(session, datetime.now(tz=UTC))
    assert before is not None

    unknown = http.post(
        ASK, json={"session": "ws_nobody", "question": "HOURSQZ"}, headers={"Origin": SITE}
    )
    elsewhere = http.post(
        ASK, json={"session": session, "question": "HOURSQZ"}, headers={"Origin": ELSEWHERE}
    )

    assert [unknown.status_code, elsewhere.status_code] == [401, 401]
    assert {unknown.json()["message"], elsewhere.json()["message"]} == {SESSION_ENDED}
    assert search.asked == []
    after = sessions_of(app.state).get(session, datetime.now(tz=UTC))
    assert after is not None and after.expires_at == before.expires_at


def test_a_question_in_a_live_session_extends_it(client: tuple[TestClient, FastAPI]) -> None:
    """The positive half of the one above: the site's own question slides the idle window. Delete
    this and a refusal that never extended anything would satisfy it, and a visitor mid-chat would
    be cut off at the first idle deadline."""
    http, app = client
    app.state.widget_search = Search("HOURSQZ")
    session = minted(http)
    before = sessions_of(app.state).get(session, datetime.now(tz=UTC))
    assert before is not None

    http.post(ASK, json={"session": session, "question": "HOURSQZ"}, headers={"Origin": SITE})

    after = sessions_of(app.state).get(session, datetime.now(tz=UTC))
    assert after is not None and after.expires_at > before.expires_at
