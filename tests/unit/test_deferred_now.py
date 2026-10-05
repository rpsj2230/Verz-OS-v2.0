"""The Rate limits screen's Deferred now list: the shed plan over the capacity ledger, in words.

The ledger is `brain.ops.capacity_ledger` over the literal fake from `test_capacity_ledger.py`,
attached where `brain.api_routes.capacity_ledger_of` looks, and the screen is read as an
unrestricted reader and a department-scoped one through `test_install_routes.py`'s application.

Task ids: M22.1.5
"""

from __future__ import annotations

import re
import time

from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from brain.install_routes import (
    NOTHING_HERE_COUNTS_WORK_IN_FLIGHT,
    THE_CAPACITY_LEDGER_DID_NOT_ANSWER,
    WORK_WORDS,
)
from brain.ops.admission import SHED_ORDER, Resource, WorkloadClass
from brain.ops.capacity_ledger import LIVE, CapacityLedger, Kept, render_key
from brain.ops.tuning import budget_knob, configured_budgets
from tests.unit.test_capacity_ledger import LedgerFake
from tests.unit.test_install_routes import LIMITS_PATH, _app, _wiring, get

KEY = (Resource.DOCUMENT_JOBS, "")


def screen_with(ledger: CapacityLedger | None) -> tuple[dict[str, object], dict[str, object]]:
    """The Limits screen as an unrestricted reader and as a department-scoped one."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        app.state.answer_client = None
        if ledger is not None:
            app.state.capacity_ledger = ledger
        admin = get(c, "u_admin", LIMITS_PATH)
        department = get(c, "u_prefix", LIMITS_PATH)
    assert admin.status_code == department.status_code == 200
    return admin.json(), department.json()


def in_use(slots: int) -> CapacityLedger:
    fake = LedgerFake()
    lapses = time.time() + 3600
    fake.sets[render_key(LIVE, KEY, Kept.HELD)] = {f"w{n}/0": lapses for n in range(slots)}
    return CapacityLedger(client=fake)


def test_the_classes_that_have_used_their_share_are_named_in_the_order_they_give_way() -> None:
    """M22.1.5 on the screen: three of four document slots in use spends batch's share of two and
    background's of three, so both are named, batch first, each with the budget in the words the
    screen's own settings use and the share and budget in force. Delete this and the plan that
    names what was deferred is again reachable from no screen."""
    body, _ = screen_with(in_use(3))

    assert body["deferred_unread"] == ""
    deferred = body["deferred"]
    assert isinstance(deferred, list)
    budget = next(one for one in configured_budgets() if one.budget_key == KEY)
    knob = budget_knob(*KEY)
    assert knob is not None
    assert [
        (one["workload_class"], one["budget"], one["share"], one["limit"]) for one in deferred
    ] == [
        ("batch", knob.label, budget.ceiling_for(WorkloadClass.BATCH), budget.limit),
        ("background", knob.label, budget.ceiling_for(WorkloadClass.BACKGROUND), budget.limit),
    ]
    assert deferred[0]["work"] == WORK_WORDS[WorkloadClass.BATCH]
    assert deferred[0]["said"].startswith(f"{WORK_WORDS[WorkloadClass.BATCH]} are deferred on ")


def test_a_deferred_row_carries_no_count_of_what_is_in_use_and_is_the_same_for_every_reader() -> (
    None
):
    """`A_DEFERRED_ROW_NAMES_A_CLASS_AND_A_BUDGET_AND_NOBODY`: the fields are the class, the budget
    and the configuration, and a department-scoped reader is shown the same rows. Delete this and a
    `used` field, a count of other people's work, is one edit away."""
    body, department = screen_with(in_use(4))

    deferred = body["deferred"]
    assert isinstance(deferred, list)
    assert [one["workload_class"] for one in deferred] == [str(one) for one in SHED_ORDER]
    for one in deferred:
        assert set(one) == {"workload_class", "work", "budget", "share", "limit", "said"}
        assert re.findall(r"[0-9]+", one["said"]) == [str(one["share"]), str(one["limit"])]
    assert department["deferred"] == deferred


def test_nothing_in_use_is_an_empty_list_and_not_a_sentence() -> None:
    """An idle install has looked and found nothing deferred, which is an empty list, drawn as its
    own sentence by the page. Delete this and an idle install reads as one that could not look."""
    body, _ = screen_with(in_use(0))

    assert body["deferred"] == []
    assert body["deferred_unread"] == ""


def test_a_process_with_no_cache_says_it_cannot_count_rather_than_listing_nothing() -> None:
    """`brain.install_routes.AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE` for this list. Delete this and a
    process with no cache shows nothing deferred during the busiest hour of the week."""
    body, _ = screen_with(None)

    assert body["deferred"] is None
    assert body["deferred_unread"] == NOTHING_HERE_COUNTS_WORK_IN_FLIGHT


def test_a_cache_that_does_not_answer_says_so() -> None:
    """A different sentence from having none, and never a 500 over the whole screen. Delete this
    and an outage takes the windows and ceilings off the screen with it."""
    body, _ = screen_with(CapacityLedger(client=LedgerFake(raises=RedisConnectionError("down"))))

    assert body["deferred"] is None
    assert body["deferred_unread"] == THE_CAPACITY_LEDGER_DID_NOT_ANSWER


def test_every_class_has_words_and_no_sentence_standing_for_the_list_has_a_number() -> None:
    """Every workload class is named in words, so a new class cannot reach the screen as a code,
    and the two sentences quantify nothing. Delete this and a fourth class is a KeyError on the
    screen the day it is deferred."""
    assert set(WORK_WORDS) == set(WorkloadClass)
    for sentence in (NOTHING_HERE_COUNTS_WORK_IN_FLIGHT, THE_CAPACITY_LEDGER_DID_NOT_ANSWER):
        assert not re.search(r"[0-9]", sentence)
