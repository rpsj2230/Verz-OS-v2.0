"""The capacity ledger, over a cache that can be contended, slow to give back, or absent.

`brain.ops.admission` is tested in `test_admission.py` against states it is handed; nothing here
re-tests a verdict. Every test here is a way the count in the cache stops matching the work that
is really running: two takers both taking the last slot, a slot nobody gave back, a place in the
queue counted twice, a check's slots counted against a real upload, or an outage that stops a
door.

The fake is `test_limit_store.FakeClient`, which is literal about the transaction (writes after
`multi` are applied by an `execute` that won the race and not otherwise), with the one command the
ledger adds, `zrem`, spelled as literally.

Task ids: M22.1.3, M22.1.4, M22.1.5, M22.2.1, M22.2.3
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from brain.core.lane import Lane
from brain.gate.context import TrafficClass
from brain.knowledge.uploads import ingestion_request, reading_request
from brain.ops import limit_store
from brain.ops.admission import (
    AdmissionRequest,
    Budget,
    CapacityState,
    Resource,
    Verdict,
    WorkloadClass,
    seed_budgets,
    shed_plan,
)
from brain.ops.capacity_ledger import (
    A_RATE_BUDGET_IS_A_WINDOW_AND_NOT_A_LEASE,
    KEY_PREFIX,
    LEASE_SERVICE_TIMES,
    LIVE,
    MAX_ATTEMPTS,
    MIN_LEASE_SECONDS,
    TTL_SLACK_SECONDS,
    CapacityLedger,
    Hold,
    Kept,
    LedgerUnreadableError,
    keys_for,
    lease_seconds,
    make_ledger,
    render_key,
    unit_members,
)
from tests.unit.test_limit_store import FakeClient, FakePipeline

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them: the
#: ledger reads no clock, so nothing here is about the present.
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

KEY = (Resource.DOCUMENT_JOBS, "")


def documents(limit: int = 4, service: float = 30.0) -> Budget:
    return Budget(resource=Resource.DOCUMENT_JOBS, limit=limit, mean_service_seconds=service)


def background_request() -> AdmissionRequest:
    return AdmissionRequest(
        trace_id="t_background",
        lane=Lane.TASK,
        traffic_class=TrafficClass.AUTOMATION,
        resource=Resource.DOCUMENT_JOBS,
    )


class ZremPipeline(FakePipeline):
    """`FakePipeline` with `zrem`, immediate before `multi` and queued after it."""

    def __enter__(self) -> ZremPipeline:
        return self

    def zrem(self, name: str, *values: str) -> object:
        def drop() -> int:
            members = self.store.sets.get(name, {})
            return sum(members.pop(one, None) is not None for one in values)

        return self._run(drop)


class LedgerFake(FakeClient):
    """`FakeClient` handing out `ZremPipeline`, and a hook run when a race is lost, so a test
    can put the other taker's write in the gap between this taker's read and its write."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.on_conflict: Callable[[LedgerFake], None] | None = None

    def pipeline(self) -> ZremPipeline:
        if self.raises is not None:
            raise self.raises
        fake = self

        class Racing(ZremPipeline):
            def execute(self) -> list[Any]:
                if fake.conflict_for > 0 and fake.on_conflict is not None:
                    fake.on_conflict(fake)
                return super().execute()

        return Racing(self)

    def zrange(self, name: str, start: int, end: int, *, withscores: bool = False) -> Any:
        if self.raises is not None:
            raise self.raises
        return super().zrange(name, start, end, withscores=withscores)

    def delete(self, *names: str) -> int:
        """As Valkey removes keys by name, which is how a check's keys are removed."""
        return sum(self.sets.pop(one, None) is not None for one in names)


def ledger_with(**kwargs: Any) -> tuple[CapacityLedger, LedgerFake]:
    client = LedgerFake(**kwargs)
    return CapacityLedger(client=client), client


def held_in(client: LedgerFake, namespace: str = LIVE) -> dict[str, float]:
    return client.sets.get(render_key(namespace, KEY, Kept.HELD), {})


def waiting_in(client: LedgerFake, namespace: str = LIVE) -> dict[str, float]:
    return client.sets.get(render_key(namespace, KEY, Kept.WAITING), {})


# ------------------------------------------------------------------ it counts at all
def test_work_inside_its_share_is_admitted_and_holds_a_slot_until_given_back() -> None:
    """The positive case every refusal below needs beside it: a ledger that refuses everything,
    or records nothing, satisfies most of this file. Delete this and neither is caught."""
    ledger, client = ledger_with()

    taken = ledger.admit(reading_request("t_one"), (documents(),), now=NOW)

    assert taken.admitted and not taken.degraded
    assert taken.hold is not None
    assert taken.hold == Hold(budget_key=KEY, member=taken.hold.member, units=1, held=True)
    assert len(held_in(client)) == 1
    assert ledger.give_back(taken.hold)
    assert held_in(client) == {}


def test_slots_already_held_are_what_the_next_decision_is_taken_against() -> None:
    """The count has to survive between calls and reach `decide`. Delete this and a ledger that
    starts each decision from an empty state admits every request and passes the test above."""
    ledger, _ = ledger_with()
    budgets = (documents(limit=4),)

    for n in range(4):
        assert ledger.admit(reading_request(f"t_{n}"), budgets, now=NOW).admitted
    refused = ledger.admit(reading_request("t_fifth"), budgets, now=NOW)

    assert refused.decision.verdict is Verdict.SHED
    assert refused.decision.used == 4
    assert refused.hold is None


def test_one_budget_is_shared_by_classes_with_different_shares() -> None:
    """M22.2.3 through the cache: batch stops at half, background at four fifths, and a person
    waiting may use the whole, all against the same count. Delete this and a ledger keeping one
    count per class would let every class use its whole share at once, three budgets in one."""
    ledger, _ = ledger_with()
    budgets = (documents(limit=10),)

    batch = [ledger.admit(ingestion_request(f"b{n}"), budgets, now=NOW) for n in range(6)]
    background = [ledger.admit(background_request(), budgets, now=NOW) for _ in range(4)]
    person = [ledger.admit(reading_request(f"p{n}"), budgets, now=NOW) for n in range(3)]

    assert [one.decision.verdict for one in batch] == [Verdict.ADMITTED] * 5 + [Verdict.QUEUED]
    assert [one.decision.verdict for one in background] == [Verdict.ADMITTED] * 3 + [Verdict.QUEUED]
    assert [one.decision.verdict for one in person] == [Verdict.ADMITTED] * 2 + [Verdict.SHED]
    assert {one.decision.workload_class for one in person} == {WorkloadClass.INTERACTIVE}


# -------------------------------------------------------- the race for the last slot
def test_two_takers_cannot_both_take_the_last_slot() -> None:
    """The reason the take is a watched transaction. Here the other taker writes the last slot
    between this taker's read and its write: the watch fails the write, the retry reads the
    other's lease, and this taker is refused. Delete this and a read-then-write ledger admits one
    more than the budget exactly when it matters, which is under load."""
    ledger, client = ledger_with()
    budgets = (documents(limit=2),)
    assert ledger.admit(reading_request("t_first"), budgets, now=NOW).admitted
    client.conflict_for = 1

    def other_taker(fake: LedgerFake) -> None:
        fake.sets[render_key(LIVE, KEY, Kept.HELD)]["other/0"] = NOW.timestamp() + 600

    client.on_conflict = other_taker
    late = ledger.admit(reading_request("t_late"), budgets, now=NOW)

    assert ledger.health.contention == 1
    assert late.decision.verdict is Verdict.SHED
    assert len(held_in(client)) == 2


def test_a_take_that_keeps_losing_the_race_decides_on_the_callers_count_and_holds_nothing() -> None:
    """Four retries and then the caller's own count, as `limit_store.MAX_ATTEMPTS` argues: a
    taker spinning on a contended key is a source of load. Delete this and the loop bound can be
    removed, or a spun-out take can record a slot nobody will give back."""
    ledger, client = ledger_with(conflict_for=MAX_ATTEMPTS + 1)
    counted = CapacityState(used={KEY: 1})

    taken = ledger.admit(reading_request("t_spin"), (documents(),), now=NOW, fallback=counted)

    assert taken.degraded and taken.hold is None
    assert taken.decision.used == 1
    assert ledger.health.spins == 1
    assert held_in(client) == {}


# ------------------------------------------------------------ a place is a position
def test_work_past_its_share_is_given_the_next_place_and_a_longer_wait() -> None:
    """M22.1.4 through the cache: the waiting are counted, so the second arrival past the share
    stands second, and its wait is no shorter. Delete this and the queued upload goes back to
    telling everybody they are first, which it did until this module."""
    ledger, client = ledger_with()
    budgets = (documents(limit=4),)
    for n in range(2):
        assert ledger.admit(ingestion_request(f"b{n}"), budgets, now=NOW).admitted

    first = ledger.admit(ingestion_request("q1"), budgets, now=NOW, member="q1")
    second = ledger.admit(ingestion_request("q2"), budgets, now=NOW, member="q2")

    assert first.decision.queue is not None and second.decision.queue is not None
    assert (first.decision.queue.position, second.decision.queue.position) == (1, 2)
    assert first.decision.queue.expected_wait_seconds > 0
    assert second.decision.queue.expected_wait_seconds >= first.decision.queue.expected_wait_seconds
    assert set(waiting_in(client)) == {"q1", "q2"}
    assert first.hold == Hold(budget_key=KEY, member="q1", units=1, held=False)


def test_the_same_work_asked_for_twice_holds_one_place() -> None:
    """A queued file is asked for under its ticket, and the same file sent twice is one ticket.
    Its own place is left out of the count it is judged against, so it keeps position one rather
    than queueing behind itself. Delete this and a resent file moves itself down the line."""
    ledger, client = ledger_with()
    budgets = (documents(limit=2),)
    ledger.admit(ingestion_request("b0"), budgets, now=NOW)

    again = [
        ledger.admit(ingestion_request("t"), budgets, now=NOW, member="ticket") for _ in range(2)
    ]

    assert [one.decision.queue.position for one in again if one.decision.queue] == [1, 1]
    assert list(waiting_in(client)) == ["ticket"]


def test_a_place_is_kept_for_its_wait_and_one_lease_and_then_lapses() -> None:
    """`A_PLACE_IN_THE_QUEUE_NEVER_ADMITS_ANYTHING`: a place outlives its expected wait by one
    lease and no longer. Delete this and a place from a worker that died is counted for ever,
    pushing every later file one further back."""
    ledger, client = ledger_with()
    budget = documents(limit=2)
    ledger.admit(ingestion_request("b0"), (budget,), now=NOW)
    queued = ledger.admit(ingestion_request("q"), (budget,), now=NOW, member="q")
    assert queued.decision.queue is not None

    lapses = waiting_in(client)["q"]
    expected = NOW.timestamp() + queued.decision.queue.expected_wait_seconds + lease_seconds(budget)

    assert lapses == pytest.approx(expected)
    after = ledger.counts((budget,), now=datetime.fromtimestamp(lapses + 1, tz=UTC))
    assert after.queued_for(KEY) == 0


# ------------------------------------------------------ a slot nobody gave back
def test_a_slot_nobody_gave_back_is_freed_when_its_lease_ends() -> None:
    """`A_SLOT_NOBODY_GAVE_BACK_IS_FREED_BY_ITS_LEASE`: a process killed mid-parse never gives
    its slot back, and one lease later the slot is free and taken again. Delete this and a
    counter design, which loses the slot for ever, passes every other test here."""
    ledger, _ = ledger_with()
    budget = documents(limit=1)
    assert ledger.admit(reading_request("dies"), (budget,), now=NOW).admitted
    during = NOW + timedelta(seconds=lease_seconds(budget) - 1)
    after = NOW + timedelta(seconds=lease_seconds(budget) + 1)

    assert not ledger.admit(reading_request("while"), (budget,), now=during).admitted
    assert ledger.admit(reading_request("after"), (budget,), now=after).admitted


def test_a_lapsed_slot_is_pruned_by_the_next_take() -> None:
    """Pruned inside the transaction, so a set whose holders keep dying does not grow without
    bound. Delete this and the prune can be dropped with every count still right, because a
    lapsed member counts for nothing either way."""
    ledger, client = ledger_with()
    budget = documents(limit=4)
    ledger.admit(reading_request("old"), (budget,), now=NOW)
    later = NOW + timedelta(seconds=lease_seconds(budget) + 1)

    ledger.admit(reading_request("new"), (budget,), now=later)

    assert len(held_in(client)) == 1


def test_a_lease_outlasts_many_mean_service_times_and_a_minute() -> None:
    """A lease that ends while its work still runs frees a slot early and admits one more than the
    budget says. Held against the seed document budget's own service time, from outside this
    module. Delete this and `LEASE_SERVICE_TIMES` or `MIN_LEASE_SECONDS` can be lowered to one
    with every other test here still green."""
    seed = next(one for one in seed_budgets() if one.budget_key == KEY)

    assert lease_seconds(seed) >= 5 * seed.mean_service_seconds
    assert lease_seconds(replace(seed, mean_service_seconds=0.5)) >= 60
    assert LEASE_SERVICE_TIMES >= 5 and MIN_LEASE_SECONDS >= 60


def test_a_keys_expiry_covers_its_latest_member() -> None:
    """A key that expires before its latest lease loses that lease, and a lost lease admits one
    more. Delete this and the expiry can be set from the new member alone, cutting short a longer
    one already held."""
    ledger, client = ledger_with()
    long = documents(limit=4, service=600.0)
    ledger.admit(reading_request("long"), (long,), now=NOW)
    ledger.admit(reading_request("short"), (documents(limit=4, service=1.0),), now=NOW)

    assert client.ttls[render_key(LIVE, KEY, Kept.HELD)] >= lease_seconds(long) + TTL_SLACK_SECONDS


# ------------------------------------------------------------- beginning and giving back
def test_work_that_begins_turns_its_place_into_a_slot() -> None:
    """The worker's half: a queued file's place becomes a slot when it starts, so the document
    read in a request sees it. Delete this and a file being read by the worker is counted as
    waiting, and a person's upload is admitted into a budget that is full."""
    ledger, client = ledger_with()
    budget = documents(limit=2)
    ledger.admit(ingestion_request("b0"), (budget,), now=NOW)
    ledger.admit(ingestion_request("q"), (budget,), now=NOW, member="ticket")

    assert ledger.begin(budget, "ticket", now=NOW)

    assert "ticket" not in waiting_in(client)
    assert set(held_in(client)) >= set(unit_members("ticket", 1))
    ledger.give_back(Hold(budget_key=KEY, member="ticket"))
    assert set(held_in(client)).isdisjoint(unit_members("ticket", 1))


def test_giving_back_frees_both_the_slot_and_the_place() -> None:
    """A hold is given back whichever set it is in. Delete this and a file whose queueing failed
    after it was given a place stands in front of every file after it until the place lapses."""
    ledger, client = ledger_with()
    budget = documents(limit=2)
    admitted = ledger.admit(ingestion_request("b0"), (budget,), now=NOW)
    queued = ledger.admit(ingestion_request("q"), (budget,), now=NOW, member="q")
    assert admitted.hold is not None and queued.hold is not None

    ledger.give_back(admitted.hold)
    ledger.give_back(queued.hold)

    assert held_in(client) == {} and waiting_in(client) == {}
    assert ledger.counts((budget,), now=NOW) == CapacityState(used={KEY: 0}, queued={KEY: 0})


def test_work_holding_several_units_holds_that_many_slots() -> None:
    """One member per unit. Delete this and a request for three units is counted as one."""
    ledger, client = ledger_with()
    three = replace(reading_request("big"), units=3)

    taken = ledger.admit(three, (documents(limit=4),), now=NOW)

    assert taken.hold is not None and taken.hold.units == 3
    assert len(held_in(client)) == 3
    ledger.give_back(taken.hold)
    assert held_in(client) == {}


# ------------------------------------------------------------------ the cache is down
def test_an_unanswering_cache_decides_on_the_callers_count_and_holds_nothing() -> None:
    """`AN_UNANSWERED_LEDGER_DECIDES_ON_WHAT_THE_CALLER_COUNTED`: the door stays open on what the
    process counted itself, the answer says it was degraded, and nothing is held to give back.
    Delete this and an outage either takes every upload door down or admits against a count that
    was never read without saying so."""
    ledger, _ = ledger_with(raises=RedisConnectionError("down"))
    counted = CapacityState(used={KEY: 2}, queued={KEY: 3})

    batch = ledger.admit(ingestion_request("b"), (documents(limit=4),), now=NOW, fallback=counted)
    person = ledger.admit(reading_request("p"), (documents(limit=4),), now=NOW)

    assert batch.degraded and batch.hold is None
    assert batch.decision.queue is not None and batch.decision.queue.position == 4
    assert person.degraded and person.admitted and person.hold is None
    assert ledger.health.outages == 2 and ledger.health.fail_open == 2


def test_an_unanswering_cache_is_said_on_every_other_call_rather_than_raised() -> None:
    """Giving back and beginning answer False and the work carries on; reading the counts raises,
    because an empty count reads as nothing deferred. Delete this and a cache outage fails the
    worker's job, or the Rate limits screen says nothing is deferred during an outage."""
    ledger, _ = ledger_with(raises=OSError("down"))

    assert not ledger.give_back(Hold(budget_key=KEY, member="m"))
    assert not ledger.begin(documents(), "m", now=NOW)
    with pytest.raises(LedgerUnreadableError):
        ledger.counts((documents(),), now=NOW)


def test_a_rate_budget_is_refused_rather_than_leased() -> None:
    """`A_RATE_BUDGET_IS_A_WINDOW_AND_NOT_A_LEASE`. Delete this and a tokens-a-minute budget is
    leased, freeing its slots when work ends rather than when the minute rolls."""
    ledger, _ = ledger_with()
    tokens = next(one for one in seed_budgets() if one.resource is Resource.TOKENS_PER_MINUTE)
    asked = AdmissionRequest(
        trace_id="t",
        lane=Lane.ANSWER,
        traffic_class=TrafficClass.HUMAN_INTERACTIVE,
        resource=Resource.TOKENS_PER_MINUTE,
    )

    with pytest.raises(ValueError, match="window"):
        ledger.admit(asked, (tokens,), now=NOW)
    assert "window" in A_RATE_BUDGET_IS_A_WINDOW_AND_NOT_A_LEASE


def test_counts_skip_rate_budgets_and_read_only_what_is_still_held() -> None:
    """The screen's read: concurrency budgets only, lapsed leases counting for nothing, and
    nothing written. Delete this and opening the Rate limits screen prunes the ledger, or a rate
    budget is read as a set nobody writes."""
    ledger, client = ledger_with()
    budget = documents(limit=4)
    ledger.admit(reading_request("p"), (budget,), now=NOW)
    before = {name: dict(members) for name, members in client.sets.items()}

    state = ledger.counts(seed_budgets(), now=NOW)

    assert state.used_for(KEY) == 1
    assert (Resource.TOKENS_PER_MINUTE, "") not in state.used
    assert client.sets == before
    later = NOW + timedelta(seconds=lease_seconds(budget) + 1)
    assert ledger.counts((budget,), now=later).used_for(KEY) == 0


def test_the_shed_plan_over_the_ledgers_counts_names_the_classes_that_give_way() -> None:
    """M22.1.5: `shed_plan` over what the ledger counts names batch, then background, then the
    request path, as each share is spent. Delete this and the Deferred now list can read a count
    the plan does not understand."""
    ledger, _ = ledger_with()
    budgets = (documents(limit=4),)
    for n in range(3):
        ledger.admit(reading_request(f"p{n}"), budgets, now=NOW)

    named = [one.workload_class for one in shed_plan(budgets, ledger.counts(budgets, now=NOW))]

    assert named == [WorkloadClass.BATCH, WorkloadClass.BACKGROUND]


# ------------------------------------------------------------------------ the keys
def test_a_namespace_counts_only_its_own_work() -> None:
    """A check takes slots under a namespace named for its run, and a real upload must never be
    counted against them. Delete this and the namespace can drop out of the key with every other
    test green, and an acceptance run fills the install's real budget."""
    client = LedgerFake()
    live, check = make_ledger(client), make_ledger(client, namespace="acceptance.run1")
    budgets = (documents(limit=1),)

    assert check.admit(reading_request("c"), budgets, now=NOW).admitted

    assert live.admit(reading_request("real"), budgets, now=NOW).admitted
    assert set(keys_for("acceptance.run1", [KEY])) == {
        render_key("acceptance.run1", KEY, Kept.HELD),
        render_key("acceptance.run1", KEY, Kept.WAITING),
    }
    assert client.delete(*keys_for("acceptance.run1", [KEY])) == 1
    assert live.counts(budgets, now=NOW).used_for(KEY) == 1


def test_two_different_budgets_or_namespaces_never_share_a_key() -> None:
    """Every segment is escaped, so `("a:b", "c")` and `("a", "b:c")` cannot address one set.
    Delete this and a naive join reads correctly, because every name here is plain."""
    one = render_key("a:b", (Resource.SOURCE_CALLS, "c"), Kept.HELD)
    other = render_key("a", (Resource.SOURCE_CALLS, "b:c"), Kept.HELD)

    assert one != other
    assert len(one.split(":")) == len(other.split(":")) == 5


def test_the_ledgers_keys_are_never_walked_as_rate_windows() -> None:
    """The Limits screen walks `lim:*` for windows, and the refusal counters live under `limref`.
    Held against `limit_store`'s own prefixes, from outside this module. Delete this and a
    prefix of `lim` puts every slot on the throttling list as a window nobody declared."""
    prefixes = {limit_store.KEY_PREFIX, limit_store.REFUSALS_PREFIX}

    assert KEY_PREFIX not in prefixes
    assert not render_key(LIVE, KEY, Kept.HELD).startswith(f"{limit_store.KEY_PREFIX}:")


def test_giving_back_watches_nothing_so_it_cannot_lose_a_race() -> None:
    """Giving back removes named members and decides nothing, so it watches no key and cannot
    fail on a busy afternoon and leave a slot held for a whole lease. Delete this and a watch
    added to it would do exactly that, with every other test here still green."""
    ledger, client = ledger_with()
    taken = ledger.admit(reading_request("p"), (documents(),), now=NOW)
    assert taken.hold is not None
    client.watch_calls = 0

    assert ledger.give_back(taken.hold)
    assert client.watch_calls == 0
