"""A question already being answered at exactly this reach is waited for, not asked again.

`brain.ops.shared_answers` is the registry and the switch's reader; `brain.api_routes.sharing_a_run`
is the one place the answer path uses it. The rule for who may share is the answer cache's key, so
these tests are written around the ways it could stop being that: a follower handed text instead
of reading the cache, a reach that is only similar sharing, a volatile question registered, a
leader that failed leaving followers stuck, and the switch being ignored.

Task ids: M36.2.3.1, M36.2.3.2
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from brain import api_routes
from brain.api_routes import sharing_a_run
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import ToolDefinition
from brain.core.scope import Scope
from brain.gate.answer_cache import lookup, store_answer
from brain.gate.cache_key import CachedAnswer, CacheKeyParts, cache_key
from brain.gate.catalogue import AgentCeiling
from brain.gate.context import Channel, GateStep, open_trace
from brain.gate.front import (
    AgentSetup,
    Caching,
    Choosing,
    FrontHalf,
    flight_parts,
    remember,
    run_front_half,
)
from brain.ops import shared_answers
from brain.ops.feature_model import Feature
from brain.ops.shared_answers import (
    FOLLOWER_ROUNDS,
    InFlightAnswers,
    answers_are_shared,
    flights_of,
)

#: Far from any wall clock, for the reason CLAUDE.md gives about fixtures with dates in them.
NOW = datetime(2999, 1, 1, tzinfo=UTC)
QUESTION = "which clients signed with us last year"
TOOLS = frozenset({"client.read_summary"})
AGENTS = {
    "general": AgentSetup(AgentCeiling(agent_id="general", allowed_tools=TOOLS), "cfg-general"),
}
REGISTRY = (
    ToolDefinition(
        name="client.read_summary",
        description="does it",
        entity="client",
        required_capability="read:client.name",
    ),
)


def _parts(**changed: Any) -> CacheKeyParts:
    base: dict[str, Any] = {
        "question": QUESTION,
        "ent_hash": "reach-one",
        "agent_config_hash": "cfg-general",
        "policy_epoch": 3,
        "source_epochs": {},
    }
    return CacheKeyParts(**{**base, **changed})


def _answer(parts: CacheKeyParts, text: str = "three clients") -> CachedAnswer:
    return CachedAnswer(
        key=cache_key(parts), payload=text, stored_at=NOW, source_epochs=parts.source_epochs
    )


async def _let_others_run() -> None:
    """Give every task that can make progress the chance to, without sleeping for real."""
    for _ in range(5):
        await asyncio.sleep(0)


# ------------------------------------------------------------------ the registry
@pytest.mark.anyio
async def test_a_second_equal_request_waits_and_is_handed_what_the_leader_stored() -> None:
    """The follower's answer comes from the lookup it is given, after the leader has released.

    Delete this and sharing can stop waiting, or hand over before there is anything to hand, and
    the saving this exists for is gone without a test noticing."""
    registry = InFlightAnswers(wait_seconds=5)
    stored: dict[str, CachedAnswer] = {}
    key = cache_key(_parts())

    leader = await registry.arrive(_parts(), look=lambda: stored.get(key))
    assert leader.flight is not None
    assert leader.found is None
    assert registry.in_flight() == 1

    asked: list[str] = []

    def look() -> CachedAnswer | None:
        asked.append("looked")
        return stored.get(key)

    follower = asyncio.create_task(registry.arrive(_parts(), look=look))
    await _let_others_run()
    assert not follower.done()
    assert asked == []

    stored[key] = _answer(_parts())
    leader.flight.release()
    arrival = await follower

    assert arrival.found is not None
    assert arrival.found.payload == "three clients"
    assert arrival.flight is None
    assert arrival.waited is True
    assert asked == ["looked"]
    assert registry.in_flight() == 0


@pytest.mark.anyio
async def test_a_request_at_a_different_reach_is_never_made_to_wait() -> None:
    """Two reaches that differ in the entitlement hash are two leaders, however alike they are.

    Delete this and equality could slide into similarity, which is a person waiting for, and
    being served the result of, a run made at somebody else's reach."""
    registry = InFlightAnswers(wait_seconds=5)
    first = await registry.arrive(_parts(), look=lambda: None)
    other = await registry.arrive(_parts(ent_hash="reach-two"), look=lambda: None)

    assert first.flight is not None
    assert other.flight is not None
    assert other.waited is False
    assert registry.in_flight() == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changed",
    [
        {"agent_config_hash": "cfg-other"},
        {"policy_epoch": 4},
        {"source_epochs": {"crm": 7}},
        {"question": "which clients left us last year"},
    ],
)
async def test_any_other_part_of_the_key_that_differs_is_a_separate_run(
    changed: dict[str, Any],
) -> None:
    """The agent, the policy epoch, the source epochs and the question each decide it as well.

    Delete this and a changed agent or a moved policy could still be served the earlier run."""
    registry = InFlightAnswers(wait_seconds=5)
    await registry.arrive(_parts(), look=lambda: None)
    other = await registry.arrive(_parts(**changed), look=lambda: None)

    assert other.flight is not None
    assert other.waited is False


@pytest.mark.anyio
async def test_a_question_about_now_is_not_registered_so_nothing_waits_for_it() -> None:
    """A volatile question gets neither a registration nor a wait.

    Delete this and a question the cache refuses to keep could still be held back for another's
    run, and served an answer that was true when that run began."""
    registry = InFlightAnswers(wait_seconds=5)
    live = _parts(question="how many tickets are open right now")

    first = await registry.arrive(live, look=lambda: None)
    second = await registry.arrive(live, look=lambda: None)

    assert first.flight is None and second.flight is None
    assert first.waited is False and second.waited is False
    assert registry.in_flight() == 0


@pytest.mark.anyio
async def test_a_leader_that_stored_nothing_sends_the_followers_to_one_new_leader() -> None:
    """Woken with nothing to read, the first follower leads and the rest wait for it.

    Delete this and a refused or failed leader sends every follower to the model together, which
    is the cost this exists to avoid arriving all at once."""
    registry = InFlightAnswers(wait_seconds=5)
    stored: dict[str, CachedAnswer] = {}
    key = cache_key(_parts())

    leader = await registry.arrive(_parts(), look=lambda: stored.get(key))
    assert leader.flight is not None
    followers = [
        asyncio.create_task(registry.arrive(_parts(), look=lambda: stored.get(key)))
        for _ in range(3)
    ]
    await _let_others_run()
    leader.flight.release()
    await _let_others_run()

    finished = [one for one in followers if one.done()]
    assert len(finished) == 1
    new_leader = finished[0].result()
    assert new_leader.flight is not None and new_leader.found is None
    assert registry.in_flight() == 1

    stored[key] = _answer(_parts())
    new_leader.flight.release()
    rest = [await one for one in followers if one is not finished[0]]
    assert [one.found.payload for one in rest if one.found] == ["three clients", "three clients"]


@pytest.mark.anyio
async def test_a_follower_gives_up_after_its_wait_and_answers_for_itself() -> None:
    """A leader that never finishes costs a follower its wait and not its question.

    Delete this and a hung run holds every later asker of the same thing for ever."""
    registry = InFlightAnswers(wait_seconds=0.01)
    await registry.arrive(_parts(), look=lambda: None)

    late = await registry.arrive(_parts(), look=lambda: None)

    assert late.found is None
    assert late.flight is None
    assert late.waited is True


@pytest.mark.anyio
async def test_a_follower_stops_joining_runs_after_its_rounds_and_answers_for_itself() -> None:
    """Woken with nothing to read each time, it joins at most `FOLLOWER_ROUNDS` runs.

    Delete this and a question whose runs keep storing nothing holds its asker in a loop."""
    registry = InFlightAnswers(wait_seconds=5)
    waits = 0

    async def churn() -> None:
        nonlocal waits
        while waits < FOLLOWER_ROUNDS + 3:
            await _let_others_run()
            running = registry._running
            for key, one in list(running.items()):
                waits += 1
                registry.finish(key, one)

    await registry.arrive(_parts(), look=lambda: None)
    task = asyncio.create_task(churn())
    arrival = await registry.arrive(_parts(), look=lambda: None)
    task.cancel()

    assert arrival.found is None
    assert arrival.waited is True


def test_releasing_twice_or_late_does_not_remove_a_newer_run() -> None:
    """A release removes its own registration and nobody else's.

    Delete this and a leader that is slow to release can remove the run that took its place,
    and the followers of that run are woken with nothing."""
    registry = InFlightAnswers(wait_seconds=5)

    async def go() -> None:
        old = await registry.arrive(_parts(), look=lambda: None)
        assert old.flight is not None
        old.flight.release()
        new = await registry.arrive(_parts(), look=lambda: None)
        assert new.flight is not None
        old.flight.release()
        assert registry.in_flight() == 1
        new.flight.release()
        assert registry.in_flight() == 0

    asyncio.run(go())


def test_the_registry_is_kept_on_the_application_state_once() -> None:
    """The same registry comes back each time, so two requests meet in one place.

    Delete this and each request gets a registry of its own, and nothing ever waits."""
    state = SimpleNamespace()
    assert flights_of(state) is flights_of(state)


# --------------------------------------------------------------------- the switch
class _Sessions:
    """A session factory that reads nothing and writes nothing."""

    def __call__(self) -> Any:
        @asynccontextmanager
        async def one() -> Any:
            yield object()

        return one()


@pytest.mark.anyio
async def test_a_process_with_no_database_shares_nothing() -> None:
    """With nowhere to read the switch, the answer is that it is off.

    Delete this and a process that cannot read its switch could share runs nobody enabled."""
    assert await answers_are_shared(None) is False


@pytest.mark.anyio
@pytest.mark.parametrize("on", [True, False])
async def test_the_switch_decides_whether_runs_are_shared(
    on: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer is the install's `shared_answer_runs` row, either way round.

    Delete this and the reader can answer one thing for ever, which a pair of refusals cannot
    tell from a working switch."""

    async def say(session: object, one: Feature) -> bool:
        del session
        assert one.name == "shared_answer_runs"
        return on

    monkeypatch.setattr(shared_answers, "is_on", say)
    assert await answers_are_shared(_Sessions()) is on  # type: ignore[arg-type]


# -------------------------------------------------------------- the answer path
class _Store:
    def __init__(self) -> None:
        self.data: dict[str, CachedAnswer] = {}

    def get(self, key: str) -> CachedAnswer | None:
        return self.data.get(key)

    def set(self, key: str, value: CachedAnswer, ttl_seconds: int) -> None:
        del ttl_seconds
        self.data[key] = value


def _reach(*caps: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(Grant(capability=Capability(value=one), scope=Scope()) for one in caps),
    )


READER = _reach("read:client.name")
OTHER_READER = _reach("read:client.name", "read:client.contract_value")


def _front(caching: Caching | None, reach: EntitlementSet = READER) -> FrontHalf:
    recorder = open_trace("t-share", NOW, Channel.CONSOLE)
    recorder.enter(GateStep.IDENTIFY)
    recorder.enter(GateStep.ENTITLE)
    return run_front_half(
        QUESTION,
        recorder=recorder,
        reach=reach,
        channel=Channel.CONSOLE,
        agents=AGENTS,
        choosing=Choosing(visible_agents=frozenset({"general"}), default_agent="general"),
        registry=REGISTRY,
        now=NOW,
        caching=caching,
    )


def _on(monkeypatch: pytest.MonkeyPatch, answer: bool = True) -> SimpleNamespace:
    async def say(sessions: object) -> bool:
        del sessions
        return answer

    monkeypatch.setattr(api_routes, "answers_are_shared", say)
    return SimpleNamespace(db_sessions=object())


def _caching(store: _Store) -> Caching:
    return Caching(store=store, policy_epoch=3)


@pytest.mark.anyio
async def test_a_second_asker_at_the_same_reach_is_served_the_first_ones_stored_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The answer path's own helper hands the follower the leader's stored answer, as a hit.

    Delete this and the registry can pass every test above while the answer path never uses it."""
    state = _on(monkeypatch)
    store = _Store()
    caching = _caching(store)
    first = _front(caching)
    second = _front(caching)

    one_front, flight = await sharing_a_run(
        state, first, question=QUESTION, reach=READER, caching=caching, now=NOW
    )
    assert flight is not None and one_front.cached is None

    waiting = asyncio.create_task(
        sharing_a_run(state, second, question=QUESTION, reach=READER, caching=caching, now=NOW)
    )
    await _let_others_run()
    assert not waiting.done()

    remember(QUESTION, "three clients", front=one_front, reach=READER, caching=caching, now=NOW)
    flight.release()
    served, again = await waiting

    assert served.cached is not None
    assert served.cached.payload == "three clients"
    assert again is None
    assert not served.calls_a_model


@pytest.mark.anyio
async def test_an_asker_at_a_wider_reach_computes_its_own_answer_while_the_first_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive sibling's opposite: a different reach leads, and nothing is served to it.

    Delete this and the helper could share on the question alone and the first test would not
    notice, because it only ever asks at one reach."""
    state = _on(monkeypatch)
    store = _Store()
    caching = _caching(store)
    _, flight = await sharing_a_run(
        state, _front(caching), question=QUESTION, reach=READER, caching=caching, now=NOW
    )
    assert flight is not None

    wider_front, wider_flight = await asyncio.wait_for(
        sharing_a_run(
            state,
            _front(caching, OTHER_READER),
            question=QUESTION,
            reach=OTHER_READER,
            caching=caching,
            now=NOW,
        ),
        timeout=1,
    )

    assert wider_flight is not None
    assert wider_front.cached is None
    assert wider_front.calls_a_model


@pytest.mark.anyio
async def test_with_the_switch_off_a_request_is_answered_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is registered and nothing waits while the install has the feature off.

    Delete this and the helper can share on an install that never switched it on."""
    state = _on(monkeypatch, answer=False)
    caching = _caching(_Store())
    front = _front(caching)

    served, flight = await sharing_a_run(
        state, front, question=QUESTION, reach=READER, caching=caching, now=NOW
    )

    assert served is front
    assert flight is None
    assert flights_of(state).in_flight() == 0


@pytest.mark.anyio
async def test_a_process_with_no_answer_store_or_a_cache_hit_registers_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No store means nothing a follower could read, and a hit has nothing left to compute.

    Delete this and either could register a run that nothing would ever release or read."""
    state = _on(monkeypatch)

    served, flight = await sharing_a_run(
        state, _front(None), question=QUESTION, reach=READER, caching=None, now=NOW
    )
    assert flight is None
    assert flights_of(state).in_flight() == 0

    store = _Store()
    caching = _caching(store)
    store_answer(
        QUESTION,
        "three clients",
        ent_hash=READER.ent_hash(),
        agent_config_hash="cfg-general",
        policy_epoch=3,
        source_epochs={},
        store=store,
        now=NOW,
    )
    hit = _front(caching)
    assert hit.cached is not None
    served, flight = await sharing_a_run(
        state, hit, question=QUESTION, reach=READER, caching=caching, now=NOW
    )
    assert served is hit and flight is None
    assert flights_of(state).in_flight() == 0


def test_the_parts_a_run_waits_under_are_the_parts_its_answer_is_stored_under() -> None:
    """The key from `flight_parts` is the key `remember` stores at, so a follower's lookup finds it.

    Delete this and the wait and the store can drift onto different keys, and every follower
    waits for an answer it then cannot find."""
    store = _Store()
    caching = Caching(store=store, policy_epoch=3, source_epochs={"crm": 2}, sources=frozenset())
    front = _front(caching)
    parts = flight_parts(QUESTION, front=front, reach=READER, caching=caching)
    assert parts is not None

    remember(QUESTION, "three clients", front=front, reach=READER, caching=caching, now=NOW)

    found = lookup(cache_key(parts), store, NOW)
    assert found is not None and found.payload == "three clients"


def test_a_volatile_question_or_a_process_with_no_store_has_no_parts_to_wait_under() -> None:
    """Both are not kept by the cache, so there is no run to wait for.

    Delete this and `flight_parts` could name a key for something that is never stored."""
    caching = _caching(_Store())
    front = _front(caching)

    assert flight_parts(QUESTION, front=front, reach=READER, caching=None) is None
    assert (
        flight_parts(
            "how many tickets are open right now", front=front, reach=READER, caching=caching
        )
        is None
    )
    assert flight_parts(QUESTION, front=front, reach=READER, caching=caching) is not None


def test_nothing_in_the_sharing_path_reads_a_second_entitlement_comparison() -> None:
    """`coalescing_gaps` is empty over the key sharing compares, so equality is still the rule.

    Delete this and the build could lose the only scan that fails on a field that admits a
    tolerance, the way a hit rate would tempt somebody to add one."""
    from brain.ops.scaling import coalescing_gaps

    assert coalescing_gaps(CacheKeyParts) == ()


def test_a_follower_waits_longer_than_the_answer_lane_may_run() -> None:
    """The wait is above the lane's own wall-clock budget, and not by an order of magnitude.

    Delete this and the wait can be shortened below the time a healthy leader takes, so every
    follower gives up and pays for its own run, or lengthened until a stuck leader holds people
    for minutes."""
    from brain.models.routing import ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS
    from brain.ops.shared_answers import FOLLOWER_WAIT_SECONDS

    assert ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS < FOLLOWER_WAIT_SECONDS
    assert FOLLOWER_WAIT_SECONDS <= 4 * ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS
