"""The realm's key set is fetched on a worker thread, and once for requests that arrive together.

`bearer.TokenAuthority.authenticate` is a coroutine on the event loop every request shares, and
a key-set fetch is a blocking HTTP call. These tests hold the two properties that make that
safe: the fetch never runs on the loop (`bearer.A_KEY_FETCH_NEVER_HOLDS_THE_EVENT_LOOP`), and a
cold `oidc.JwksCache` asked by several threads at once fetches one document
(`oidc.SIMULTANEOUS_FIRST_REQUESTS_FETCH_ONCE`). The keys and tokens are
`tests.unit.test_keycloak_tokens`'s, generated in the test, and nothing touches the network.

Task ids: M1.1.2
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable

import pytest

from brain.identity.bearer import Caller
from brain.identity.keycloak_tokens import key_set_from_jwks, keycloak_authority
from brain.identity.oidc import JwksCache, KeySet
from brain.identity.roles import IdentityError
from tests.unit.test_keycloak_tokens import (
    ISSUER,
    KID,
    NOW,
    SIGNING,
    Directory,
    Idp,
    jwk_of,
    token,
)

DOCUMENT = json.dumps({"keys": [jwk_of(SIGNING)]}).encode()

#: How long a waiting thread is given to reach the fetch. A cache with no lock lets the second
#: of five threads in within a millisecond, so this is generous in the direction that matters.
SECOND_FETCH_WINDOW_SECONDS = 0.3

#: The most any wait here may take, so that a regression fails rather than hangs.
WAIT_SECONDS = 5.0


@pytest.mark.parametrize(
    "ask",
    [
        lambda cache: cache.keys_for(ISSUER, NOW),
        lambda cache: cache.key_for(ISSUER, KID, NOW),
    ],
    ids=["the key set", "a named key"],
)
def test_requests_that_reach_a_cold_cache_together_fetch_the_key_set_once(
    ask: Callable[[JwksCache], object],
) -> None:
    """Five threads reach an empty cache while the first fetch is still in flight, and the
    identity provider is asked once, and all five are answered. Delete this and the lock can go
    from either path, and every sign-in on a cold process fetches the realm's keys for itself."""
    started = threading.Event()
    release = threading.Event()
    fetches: list[str] = []

    def fetch(issuer: str) -> KeySet:
        fetches.append(issuer)
        started.set()
        release.wait(WAIT_SECONDS)
        return key_set_from_jwks(DOCUMENT, issuer=issuer, fetched_at=NOW)

    cache = JwksCache(fetch)
    answers: list[object] = []
    threads = [threading.Thread(target=lambda: answers.append(ask(cache))) for _ in range(5)]
    for thread in threads:
        thread.start()
    assert started.wait(WAIT_SECONDS)
    deadline = time.monotonic() + SECOND_FETCH_WINDOW_SECONDS
    while len(fetches) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    release.set()
    for thread in threads:
        thread.join(WAIT_SECONDS)

    assert fetches == [ISSUER]
    assert len(answers) == 5
    assert all(answer == answers[0] for answer in answers)


def test_a_key_fetch_does_not_hold_the_event_loop() -> None:
    """The fetch waits for a coroutine on the same loop to run, and the sign-in still succeeds.
    Delete this and `authenticate` can call its key source on the loop, and one cold cache or one
    rotated key stops every request in the process for as long as the realm takes to answer."""
    idp = Idp()
    loop_ran = threading.Event()

    def get(url: str) -> bytes:
        if not loop_ran.wait(WAIT_SECONDS):
            msg = "the event loop did not run while the key set was being fetched"
            raise IdentityError(msg)
        return idp.get(url)

    authority = keycloak_authority(
        directory=Directory(),
        get=get,
        clock=lambda: NOW,
        env={"INSTALL_OIDC_ISSUER": ISSUER},
    )

    async def meanwhile() -> None:
        await asyncio.sleep(0)
        loop_ran.set()

    async def both() -> Caller:
        caller, _ = await asyncio.gather(
            authority.authenticate(f"Bearer {token()}", now=NOW), meanwhile()
        )
        return caller

    assert asyncio.run(both()).principal.id == "u_signed_in"
    assert len(idp.urls) == 1
