"""The Limits screen over HTTP: the windows, which are refusing now, and who is unusual.

`test_install_routes.py` holds the router's shared rules for all five install screens, and this
file holds what the Limits screen answers now that the request path counts questions: the
windows the request path counts, the windows the answer route's own store holds, and the
unusual-volume half fed by `brain.ops.volume_store`.

The store is the literal fake Valkey from `test_limit_store.py`, installed where the lifespan
would put it and reached through `brain.api_routes.limit_store_of` exactly as on an install,
so no throttle source is attached by hand here.

Task ids: M23.1.1, M23.2.1, M27.7.27
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from brain.install_routes import (
    NOTHING_HERE_COUNTS_WHAT_PEOPLE_ASK,
    THE_COUNTING_STORE_DID_NOT_ANSWER,
    THE_REQUEST_LEDGER_DID_NOT_ANSWER,
)
from brain.ops.limit_store import UNREACHABLE_POLICY, Availability, ValkeyWindowStore, render_key
from brain.ops.limits import (
    DEFAULT_PRINCIPAL_PER_MINUTE,
    LimitScope,
    declared_windows,
    principal_limit,
)
from brain.ops.volume_store import PrincipalVolume
from tests.unit.test_install_routes import LIMITS_PATH, _app, _wiring, get
from tests.unit.test_limit_store import FakeClient


def screen_with(
    *,
    valkey: FakeClient | None = None,
    volumes: Sequence[PrincipalVolume] | None = None,
    volume_error: Exception | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """The Limits screen as an unrestricted reader and as a department-scoped one."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        if valkey is not None:
            app.state.limit_store = ValkeyWindowStore(client=valkey)
        if volumes is not None or volume_error is not None:

            async def source(now: datetime) -> Sequence[PrincipalVolume]:
                del now
                if volume_error is not None:
                    raise volume_error
                return volumes or ()

            app.state.volume_source = source
        admin = get(c, "u_admin", LIMITS_PATH)
        department = get(c, "u_prefix", LIMITS_PATH)
    assert admin.status_code == department.status_code == 200
    return admin.json(), department.json()


# ------------------------------------------------------------------------- the windows
def test_the_screen_lists_every_window_the_request_path_counts() -> None:
    """ "Lists the windows", from the functions the request path calls, with what each does when
    the store is down in words. The person's window is asserted against the request path's own
    default rather than a number typed here, so the screen and the route cannot drift.

    Delete this and the screen can go on listing only the three source ceilings, which say
    nothing about the thirty-a-minute window a person actually runs into."""
    body, _ = screen_with()

    windows = body["windows"]
    assert isinstance(windows, list)
    assert [(one["scope"], one["applies_to"]) for one in windows] == [
        (str(one.scope), one.applies_to) for one in declared_windows()
    ]
    person = next(one for one in windows if one["scope"] == LimitScope.PRINCIPAL.value)
    assert person["limit"] == DEFAULT_PRINCIPAL_PER_MINUTE
    assert person["when_unreachable"] == "lets requests through"
    connector = next(one for one in windows if one["scope"] == LimitScope.CONNECTOR.value)
    assert UNREACHABLE_POLICY[LimitScope.CONNECTOR] is Availability.FAIL_CLOSED
    assert connector["when_unreachable"] == "refuses requests"


def test_the_windows_the_answer_route_counts_in_are_the_ones_the_screen_reads() -> None:
    """ "Which are refusing now", from the store the answer route writes. One person's window
    is full and another's has one question in it; only the full one is refusing.

    Delete this and the screen can read a store nothing writes, which lists nobody for ever."""
    valkey = FakeClient()
    full = render_key(principal_limit("p_one").key)
    valkey.sets[full] = {f"m{n}": time.time() - 5 for n in range(DEFAULT_PRINCIPAL_PER_MINUTE)}
    valkey.sets[render_key(principal_limit("p_two").key)] = {"m": time.time() - 5}

    body, department = screen_with(valkey=valkey)

    assert body["unread"] == ""
    throttled = body["throttled"]
    assert isinstance(throttled, list)
    assert [(one["scope"], one["subject"]) for one in throttled] == [("principal", "p_one")]
    assert department["throttled"] == []


def test_a_store_that_does_not_answer_says_so_rather_than_listing_nobody() -> None:
    """An empty list reads as nobody being refused, which is the reassuring answer and the
    wrong one while the cache is down.

    Delete this and an outage renders as a quiet afternoon on the one screen somebody opens to
    find out why questions are failing."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    body, _ = screen_with(valkey=FakeClient(raises=RedisConnectionError("down")))

    assert body["throttled"] is None
    assert body["unread"] == THE_COUNTING_STORE_DID_NOT_ANSWER


# ---------------------------------------------------------------------- unusual volume
def test_somebody_asking_ten_times_their_week_is_listed_by_band_and_never_by_count() -> None:
    """M23.2.1 on the screen. One person asked a hundred questions today against ten a day
    last week, one asked ten, and one has no week at all; only the first is unusual, and the
    row says so in a band and a sentence with no figure in it.

    Delete this and the screen can list volumes with their counts, which is a report on
    somebody's day beside their name."""
    body, _ = screen_with(
        volumes=(
            PrincipalVolume("p_busy", observed=100, prior=70),
            PrincipalVolume("p_calm", observed=10, prior=70),
            PrincipalVolume("p_new", observed=25, prior=0),
        )
    )

    assert body["unusual_unread"] == ""
    unusual = body["unusual"]
    assert isinstance(unusual, list)
    assert [(one["subject"], one["band"]) for one in unusual] == [("p_busy", "extreme")]
    assert set(unusual[0]) == {"subject", "band", "said"}
    assert not re.search(r"[0-9]", unusual[0]["said"])


def test_a_department_scoped_reader_is_shown_nobodys_volume() -> None:
    """The same narrowing as the throttling list: a row is offered to the reader's scope as the
    person's own window, which a department clause does not match.

    Delete this and a department admin could read who in the company is unusually busy."""
    _, department = screen_with(volumes=(PrincipalVolume("p_busy", observed=100, prior=70),))

    assert department["unusual"] == []


def test_a_process_with_no_ledger_says_it_cannot_count_rather_than_listing_nobody() -> None:
    """No database is not an ordinary week for everybody.

    Delete this and the half renders empty on a process that looked at nothing."""
    body, _ = screen_with()

    assert body["unusual"] is None
    assert body["unusual_unread"] == NOTHING_HERE_COUNTS_WHAT_PEOPLE_ASK


def test_a_ledger_that_does_not_answer_says_so() -> None:
    """The database refused the read, which is a different sentence from having none.

    Delete this and a failed read answers 500 over the whole screen, taking the windows with
    it."""
    body, _ = screen_with(volume_error=OperationalError("select", {}, Exception("down")))

    assert body["unusual"] is None
    assert body["unusual_unread"] == THE_REQUEST_LEDGER_DID_NOT_ANSWER


@pytest.mark.parametrize("unread", [THE_COUNTING_STORE_DID_NOT_ANSWER])
def test_every_sentence_the_screen_can_say_has_no_number_in_it(unread: str) -> None:
    """A sentence standing where a list would be must not quantify what is missing.

    Delete this and a sentence reading "3 windows could not be read" is one edit away."""
    for sentence in (
        unread,
        NOTHING_HERE_COUNTS_WHAT_PEOPLE_ASK,
        THE_REQUEST_LEDGER_DID_NOT_ANSWER,
    ):
        assert not re.search(r"[0-9]", sentence)
