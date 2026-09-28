"""Asking past a window, over HTTP: the 429, what it says, and what it leaves in the window.

`test_limits.py` holds the arithmetic and `test_limit_store.py` the transaction. This file is
about the one place a person meets either: `POST /answer` with the real application, the real
token path and the real front half, and the windows in the literal fake Valkey
`test_limit_store.py` keeps, installed where `brain.app.lifespan` would put the store.

Windows are filled by writing hits into the fake at chosen instants rather than by asking
thirty questions, because the route reads the wall clock and a test cannot move it; a hit
written at "now minus fifty seconds" is the same fact the route would have recorded then.

Task ids: M23.1.1, M23.1.2, M23.1.3, M23.1.5
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import DEFAULT_AGENT, LIMITED_RESPONSES, limit_store_of
from brain.app import Settings, create_app
from brain.ops.limit_store import ValkeyWindowStore, render_key
from brain.ops.limits import (
    DEFAULT_AGENT_PER_MINUTE,
    DEFAULT_CHANNEL_PER_MINUTE,
    DEFAULT_PRINCIPAL_PER_MINUTE,
    Limit,
    agent_limit,
    channel_limit,
    principal_limit,
)
from brain.tools.startup import build_registry
from tests.fixtures.http_client import Response
from tests.unit.test_answer_route import HOURS, OneRow
from tests.unit.test_api_routes import SOURCE, token_for, wiring
from tests.unit.test_compliance_routes import Referrals
from tests.unit.test_limit_store import FakeClient

#: A question the fast lane answers, so an admitted request is a 200 with frames.
PRICE = "what is the price of WEB-1001"

#: The principal `token_for("u_wide")` resolves to, and the channel a token with a session is on.
ASKER = "u_wide"
CHANNEL = "console"


@pytest.fixture
def valkey() -> FakeClient:
    return FakeClient()


@pytest.fixture
def referrals() -> Referrals:
    return Referrals()


@pytest.fixture
def client(valkey: FakeClient, referrals: Referrals) -> Iterator[TestClient]:
    """`test_answer_route`'s application, with the windows where the lifespan would put them."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring()
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.fast_path_rules = (HOURS,)
        app.state.sensitive_referrals = referrals
        app.state.limit_store = ValkeyWindowStore(client=valkey)
        yield c


def ask(c: TestClient, text: str = PRICE) -> Response:
    answered: Response = c.post(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {token_for(ASKER)}"},
        json={"question": text},
    )
    return answered


def fill(valkey: FakeClient, limit: Limit, *, hits: int, seconds_ago: float) -> str:
    """Write `hits` admitted requests into one window, all `seconds_ago` before now."""
    name = render_key(limit.key)
    at = time.time() - seconds_ago
    valkey.sets.setdefault(name, {}).update({f"seeded-{n}": at for n in range(hits)})
    return name


def waited(answered: Response) -> int:
    return int(answered.headers["retry-after"])


# ------------------------------------------------------------------- inside every window
def test_a_question_inside_every_window_is_answered_and_counted_once_in_each(
    client: TestClient, valkey: FakeClient
) -> None:
    """The positive case every refusal below needs beside it: a route that refused everything
    would pass them all. One question is one hit in the person's window, the channel's and the
    answering agent's, and no more, because the early ask records nothing.

    Delete this and the early ask can start recording, which counts every question twice and
    halves everybody's allowance without a single refusal test noticing."""
    answered = ask(client)

    assert answered.status_code == 200
    for limit in (principal_limit(ASKER), channel_limit(CHANNEL), agent_limit(DEFAULT_AGENT)):
        assert len(valkey.sets[render_key(limit.key)]) == 1, limit.scope


# --------------------------------------------------------------------- past the window
def test_asking_past_the_persons_window_is_a_429_that_says_when_in_words_and_in_the_header(
    client: TestClient, valkey: FakeClient
) -> None:
    """M23.1.1 and M23.1.5 on the install's own path. The window is full with every hit ten
    seconds old, so room appears in about fifty seconds; the header says so in whole seconds
    and the message says the same number in words, because a person reads the message and a
    program reads the header, and the two telling different times is a bug either way.

    Delete this and the route can go back to answering a loop at full speed, which it did on
    every install until 2026-09-28."""
    fill(valkey, principal_limit(ASKER), hits=DEFAULT_PRINCIPAL_PER_MINUTE, seconds_ago=10)

    refused = ask(client)

    assert refused.status_code == 429
    assert 49 <= waited(refused) <= 51
    body = refused.json()
    assert body["message"].startswith("You have asked more often in the last minute")
    said = re.search(r"You can ask again in (\d+) seconds[.]", body["message"])
    assert said is not None
    assert int(said.group(1)) == waited(refused)
    assert body["trace_id"]
    assert refused.headers["cache-control"] == "no-store"


def test_a_refusal_names_nobody_and_no_system(client: TestClient, valkey: FakeClient) -> None:
    """A 429 is read by the person refused, and whose allowance ran out is said by its kind.
    The subject of a window is a principal id, a channel or an agent id, and a refusal quoting
    one would tell somebody who else is asking or what a question reached.

    Delete this and a sentence built from `LimitDecision.reason`, which names the subject,
    is the obvious thing to send."""
    fill(valkey, principal_limit(ASKER), hits=DEFAULT_PRINCIPAL_PER_MINUTE, seconds_ago=10)

    refused = ask(client)

    assert refused.status_code == 429
    assert ASKER not in refused.text
    assert "principal" not in refused.text


def test_a_refused_question_does_not_extend_the_window(
    client: TestClient, valkey: FakeClient
) -> None:
    """REFUSED_REQUESTS_DO_NOT_EXTEND_THE_WINDOW, through the route. Three refusals leave the
    window holding exactly the hits it held, and once those have aged out the next question is
    answered: a refusal pushed nothing further away.

    Delete this and the route can record before it decides, which turns a person who presses
    the button again into a person who is locked out for good."""
    name = fill(valkey, principal_limit(ASKER), hits=DEFAULT_PRINCIPAL_PER_MINUTE, seconds_ago=10)

    for _ in range(3):
        assert ask(client).status_code == 429
    assert len(valkey.sets[name]) == DEFAULT_PRINCIPAL_PER_MINUTE

    # Time passes: every hit is now older than the window.
    valkey.sets[name] = {member: at - 61 for member, at in valkey.sets[name].items()}

    assert ask(client).status_code == 200


def test_the_channels_window_refuses_everybody_on_it(
    client: TestClient, valkey: FakeClient
) -> None:
    """M23.1.2. The person's own window is empty and the channel's is full, which is a
    misbehaving integration on the same way in, and the refusal says it is the channel's.

    Delete this and `request_limits` can lose the channel line with every per-person test
    still green."""
    fill(valkey, channel_limit(CHANNEL), hits=DEFAULT_CHANNEL_PER_MINUTE, seconds_ago=10)

    refused = ask(client)

    assert refused.status_code == 429
    assert refused.json()["message"].startswith("More questions have arrived this way")


def test_the_agents_window_refuses_and_leaves_the_persons_window_untouched(
    client: TestClient, valkey: FakeClient
) -> None:
    """M23.1.3, and the reason the windows are asked twice. The agent is chosen by the front
    half, so its window is asked after the person's; a request it refuses must leave nothing in
    the person's window either, or a refusal by one window extends another.

    Delete this and recording the person's window on the early ask looks correct in every
    other test here."""
    fill(valkey, agent_limit(DEFAULT_AGENT), hits=DEFAULT_AGENT_PER_MINUTE, seconds_ago=10)

    refused = ask(client)

    assert refused.status_code == 429
    assert refused.json()["message"].startswith("The assistant you asked")
    assert not valkey.sets.get(render_key(principal_limit(ASKER).key))
    assert not valkey.sets.get(render_key(channel_limit(CHANNEL).key))


def test_a_looping_caller_is_told_to_wait_longer_each_time(
    client: TestClient, valkey: FakeClient
) -> None:
    """M23.1.5's backoff. The first refusals carry the measured wait; a caller refused past
    `BACKOFF_AFTER_REFUSALS` in a row is looping, and the hint lengthens. The window is not
    touched by any of it, which the test above holds.

    Delete this and the counter of refusals can stop being read, which leaves a looping client
    hammering at the exact second room appears, every time."""
    fill(valkey, principal_limit(ASKER), hits=DEFAULT_PRINCIPAL_PER_MINUTE, seconds_ago=58.5)

    hints = [waited(ask(client)) for _ in range(6)]

    assert hints[0] <= 2
    assert hints[-1] > hints[0]


def test_a_loop_is_refused_before_a_sensitive_question_is_filed(
    client: TestClient, valkey: FakeClient, referrals: Referrals
) -> None:
    """The early ask is what keeps a loop from filing a referral with a named person on every
    attempt. A question on a sensitive topic, asked past the window, files nothing.

    Delete this and asking only after the agent is chosen looks equivalent, while every refused
    attempt in a loop still lands on somebody's desk."""
    fill(valkey, principal_limit(ASKER), hits=DEFAULT_PRINCIPAL_PER_MINUTE, seconds_ago=10)

    refused = ask(client, "is this harassment")

    assert refused.status_code == 429
    assert referrals.filed == []


# ------------------------------------------------------------------------ the store
def test_a_process_with_no_valkey_has_no_windows_and_one_with_it_keeps_one_store() -> None:
    """None where the lifespan opened no cache client, and the cache's own client wrapped
    once where it did, so the health counters span requests rather than starting over on each.

    Delete this and a store built per request reports no contention and no outage, ever."""

    class State:
        pass

    bare = State()
    assert limit_store_of(bare) is None

    wired = State()
    wired.answer_client = FakeClient()  # type: ignore[attr-defined]
    first = limit_store_of(wired)
    assert first is not None
    assert limit_store_of(wired) is first


def test_the_429_is_in_the_generated_document(client: TestClient) -> None:
    """The console's typed client is generated from the document, and a status it does not
    declare is one nobody wrote a reader for.

    Delete this and the route can drop `LIMITED_RESPONSES` for the common set."""
    document = client.get("/openapi.json").json()

    declared = document["paths"][f"{API_PREFIX}/answer"]["post"]["responses"]

    assert "429" in declared
    assert 429 in LIMITED_RESPONSES
