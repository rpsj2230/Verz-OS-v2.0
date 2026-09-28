"""The sliding windows, over a store that can be slow, contended or absent.

Every test here is a way the window in Valkey stops matching the window the algorithm
believes in. The algorithm itself is tested in `test_limits.py` against an in-memory state;
nothing is re-tested here, because a second copy of those assertions would be a second place
to update when the rule changes.

The fake implements `WindowPipeline` and keeps sorted sets in a dict. Deliberately literal:
it replaces a member on a repeated `zadd` exactly as Valkey does, which is what makes the
"two hits at one instant" test able to fail. A fake that appended blindly would prove the
fake appends.

It is literal about the transaction too, since 2026-09-28. A command issued after `watch` and
before `multi` runs at once, as the real pipeline runs it, and a command issued after `multi`
is queued and applied only by an `execute` that did not lose the race. The first version
applied every write at once, so a lost race still wrote, and the counter of refusals, which is
read back from `execute`, could not have been tested against it at all.

Task ids: M23.1.1, M23.1.5
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import WatchError

from brain.ops.admission import RefusalKind
from brain.ops.limit_store import (
    KEY_PREFIX,
    MAX_ATTEMPTS,
    REFUSALS_FORGOTTEN_AFTER_SECONDS,
    TTL_SLACK_SECONDS,
    UNREACHABLE_POLICY,
    Availability,
    StoreVerdict,
    ValkeyWindowStore,
    WindowsUnreadableError,
    parse_key,
    refusals_key,
    render_key,
)
from brain.ops.limits import (
    MAX_BACKOFF_SECONDS,
    Limit,
    LimitScope,
    channel_limit,
    check,
    principal_limit,
    source_limits,
)

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def per_principal(limit: int = 2, window: float = 60.0) -> Limit:
    return Limit(
        scope=LimitScope.PRINCIPAL,
        subject="p_alice",
        period="minute",
        limit=limit,
        window_seconds=window,
    )


def per_connector(limit: int = 2, window: float = 60.0) -> Limit:
    return Limit(
        scope=LimitScope.CONNECTOR,
        subject="xero",
        period="minute",
        limit=limit,
        window_seconds=window,
    )


class FakePipeline:
    """A sorted set per key, with Valkey's replace-on-duplicate-member behaviour.

    Immediate between `watch` and `multi`, queued after `multi`, and applied by `execute`
    only when the race was won, which is what the real transaction does.
    """

    def __init__(self, store: FakeClient) -> None:
        self.store = store
        self.queued: list[Callable[[], Any]] | None = None

    def __enter__(self) -> FakePipeline:
        return self

    def __exit__(self, *exc: object) -> None:
        self.store.watched = ()

    def _run(self, action: Callable[[], Any]) -> Any:
        if self.queued is None:
            return action()
        self.queued.append(action)
        return self

    def watch(self, *names: str) -> object:
        self.store.watched = names
        # Kept after the block exits. `__exit__` releases the watch, as the real pipeline
        # does, so an assertion made afterwards has to read what *was* watched.
        self.store.ever_watched = names
        self.store.watch_calls += 1
        return None

    def multi(self) -> None:
        self.store.multi_calls += 1
        self.queued = []

    def execute(self) -> list[Any]:
        self.store.execute_calls += 1
        queued, self.queued = self.queued or [], None
        if self.store.conflict_for > 0:
            self.store.conflict_for -= 1
            raise WatchError("a watched key moved")
        return [action() for action in queued]

    def zrange(self, name: str, start: int, end: int, *, withscores: bool = False) -> Any:
        return self._run(lambda: self.store.zrange(name, start, end, withscores=withscores))

    def zremrangebyscore(self, name: str, min: Any, max: Any) -> object:  # noqa: A002
        del min

        def prune() -> None:
            members = self.store.sets.get(name, {})
            for member, score in list(members.items()):
                if score <= float(max):
                    del members[member]

        return self._run(prune)

    def zadd(self, name: str, mapping: Mapping[str, float]) -> object:
        return self._run(lambda: self.store.sets.setdefault(name, {}).update(mapping))

    def expire(self, name: str, time: int) -> object:
        return self._run(lambda: self.store.ttls.__setitem__(name, time))

    def incr(self, name: str) -> object:
        def bump() -> int:
            self.store.counters[name] = self.store.counters.get(name, 0) + 1
            return self.store.counters[name]

        return self._run(bump)

    def delete(self, *names: str) -> object:
        return self._run(lambda: sum(self.store.counters.pop(one, None) is not None for one in names))


class FakeClient:
    def __init__(self, *, conflict_for: int = 0, raises: Exception | None = None) -> None:
        self.sets: dict[str, dict[str, float]] = {}
        self.ttls: dict[str, int] = {}
        self.counters: dict[str, int] = {}
        self.watched: tuple[str, ...] = ()
        self.ever_watched: tuple[str, ...] = ()
        self.conflict_for = conflict_for
        self.raises = raises
        self.watch_calls = 0
        self.multi_calls = 0
        self.execute_calls = 0

    def pipeline(self) -> FakePipeline:
        if self.raises is not None:
            raise self.raises
        return FakePipeline(self)

    def scan_iter(self, match: str | None = None, count: int | None = None) -> Iterator[Any]:
        """Every key as bytes, as a client built with `decode_responses=False` returns it."""
        del count
        if self.raises is not None:
            raise self.raises
        prefix = (match or "*").rstrip("*")
        for name in [*self.sets, *self.counters]:
            if name.startswith(prefix):
                yield name.encode("utf-8")

    def zrange(self, name: str, start: int, end: int, *, withscores: bool = False) -> Any:
        del start, end, withscores
        return sorted(self.store_items(name), key=lambda pair: pair[1])

    def store_items(self, name: str) -> list[tuple[str, float]]:
        return list(self.sets.get(name, {}).items())


def store_with(**kwargs: Any) -> tuple[ValkeyWindowStore, FakeClient]:
    client = FakeClient(**kwargs)
    return ValkeyWindowStore(client=client), client


# ----------------------------------------------------------------- it counts at all
def test_a_request_under_the_limit_is_admitted_and_recorded() -> None:
    """If this fails every refusal below passes for the wrong reason: a store that admits
    nothing and records nothing satisfies most of this file."""
    store, client = store_with()
    limits: Sequence[Limit] = (per_principal(limit=2),)

    first = store.check_and_record(now=NOW, limits=limits)

    assert first.allowed
    assert len(client.sets[render_key(limits[0].key)]) == 1


def test_the_request_that_crosses_the_limit_is_refused() -> None:
    """The window has to survive between calls. Delete this and a store that writes to a
    fresh dict every time still passes the test above."""
    store, _ = store_with()
    limits = (per_principal(limit=2),)

    assert store.check_and_record(now=NOW, limits=limits).allowed
    assert store.check_and_record(now=NOW, limits=limits).allowed
    refused = store.check_and_record(now=NOW, limits=limits)

    assert not refused.allowed
    assert refused.decision.retry_after_seconds > 0


def test_a_refused_request_is_not_recorded() -> None:
    """`REFUSED_REQUESTS_DO_NOT_EXTEND_THE_WINDOW` is a rule in the algorithm, and this is
    the half of it that lives in the store: the transaction must queue no write when the
    decision was no.

    Without this a client that retries eagerly is locked out permanently, with the retry
    hint receding faster than the client can obey it."""
    store, client = store_with()
    limits = (per_principal(limit=1),)
    key = render_key(limits[0].key)

    store.check_and_record(now=NOW, limits=limits)
    store.check_and_record(now=NOW, limits=limits)
    store.check_and_record(now=NOW, limits=limits)

    assert len(client.sets[key]) == 1, "a refusal was recorded and extended the window"


def test_two_requests_at_the_very_same_instant_count_as_two() -> None:
    """The reason a member is a uuid and not the timestamp.

    Valkey's `ZADD` replaces a member that already exists, so encoding the instant as the
    member makes two simultaneous requests collapse into one recorded hit, and a limit of
    two admits three. `now` comes from the caller, so identical instants are ordinary rather
    than exotic: a batch, or any clock with coarse resolution, produces them.

    Delete this and the smaller encoding looks correct in every other test here, because
    every other test uses distinct instants or does not care."""
    store, client = store_with()
    limits = (per_principal(limit=5),)
    key = render_key(limits[0].key)

    store.check_and_record(now=NOW, limits=limits)
    store.check_and_record(now=NOW, limits=limits)

    assert len(client.sets[key]) == 2, "two hits at one instant collapsed into one"


def test_a_hit_that_has_fallen_out_of_the_window_stops_counting() -> None:
    """The boundary between two windows, which is the only part of a sliding window that is
    ever wrong, exercised through the store rather than the algorithm."""
    store, _ = store_with()
    limits = (per_principal(limit=1, window=60.0),)

    assert store.check_and_record(now=NOW, limits=limits).allowed
    assert not store.check_and_record(now=NOW + timedelta(seconds=30), limits=limits).allowed
    assert store.check_and_record(now=NOW + timedelta(seconds=61), limits=limits).allowed


# -------------------------------------------------------------------- the key itself
def test_two_different_windows_can_never_share_a_key() -> None:
    """A subject is a principal id, a connector name or a widget origin: a string from
    outside. Joined with a colon, `("a:b", "c")` and `("a", "b:c")` address one window, and
    one caller spends another caller's allowance.

    Delete this and the naive join reads correctly, because every other subject in this file
    is a plain identifier."""
    ambiguous = render_key((LimitScope.PRINCIPAL, "a:b", "c"))
    other = render_key((LimitScope.PRINCIPAL, "a", "b:c"))

    assert ambiguous != other


def test_a_widget_origin_with_a_url_in_it_still_makes_one_key_segment() -> None:
    """A widget origin is a URL, and a URL contains the separator. `https://app...` joined
    raw would render as five colon-separated fields where the key format has four, so the
    scope and period a reader parses back out are not the ones that went in.

    The slash is not the point and this test does not claim it is: mutating `safe=""` to
    the default leaves the slash unencoded and changes nothing, because keys split on the
    colon. Delete this and only the artificial `a:b` case above covers the real subject
    shape that carries a separator."""
    key = render_key((LimitScope.WIDGET_ORIGIN, "https://app.example.com/embed", "minute"))

    assert key.count(":") == 3, "a subject leaked separators into the key"
    assert key.startswith(f"{KEY_PREFIX}:")


def test_every_key_is_given_an_expiry_at_least_as_long_as_its_window() -> None:
    """A key that expires early loses the oldest hits in its window, so the limit admits
    more than it says, and it does so silently. This is the failure that looks like the
    limiter working."""
    store, client = store_with()
    limits = (per_principal(window=60.0),)

    store.check_and_record(now=NOW, limits=limits)

    assert client.ttls[render_key(limits[0].key)] >= 60 + TTL_SLACK_SECONDS - 1


# ----------------------------------------------------------- concurrency and outages
def test_the_keys_are_watched_before_they_are_read() -> None:
    """Reading, deciding and writing without a watch is the double admit: two requests both
    see room, both write, and the limit admits one more than it says exactly under load.

    Asserted as a call rather than as an outcome, because a single-threaded test cannot
    observe the race it prevents. This is the one place in this file where the mechanism is
    the assertion, and that is why the fake counts the calls."""
    store, client = store_with()

    store.check_and_record(now=NOW, limits=(per_principal(),))

    assert client.watch_calls == 1
    assert client.ever_watched == (render_key(per_principal().key),)


def test_a_lost_race_is_retried_rather_than_reported() -> None:
    """Losing the optimistic transaction means somebody else wrote first, not that the
    caller is over their limit. Reporting it would refuse a request that was inside its
    allowance, and the caller would have no way to tell the two apart."""
    store, client = store_with(conflict_for=2)

    verdict = store.check_and_record(now=NOW, limits=(per_principal(limit=5),))

    assert verdict.allowed
    assert not verdict.degraded
    assert store.health.contention == 2
    assert client.execute_calls == 3


def test_endless_contention_is_a_dependency_refusal_and_not_a_quota_one() -> None:
    """A caller that never wins the race is not over an allowance. Told "quota", an operator
    goes looking for a limit to raise and finds one that was never reached.

    The retries are bounded for the same reason: spinning turns a rate limit into a source
    of the load it exists to shed."""
    store, _ = store_with(conflict_for=MAX_ATTEMPTS + 1)

    verdict = store.check_and_record(now=NOW, limits=(per_connector(limit=5),))

    assert not verdict.allowed
    assert verdict.degraded
    assert store.health.spins == 1
    assert verdict.log_record()["refusal_kind"] == RefusalKind.DEPENDENCY


def test_a_fairness_limit_admits_when_the_store_is_unreachable() -> None:
    """Valkey being down must not take the product down for a rule whose worst case is that
    one colleague is briefly unfair to another."""
    store, _ = store_with(raises=RedisConnectionError("no route to host"))

    verdict = store.check_and_record(now=NOW, limits=(per_principal(),))

    assert verdict.allowed
    assert verdict.degraded, "an outage was reported as an ordinary admission"
    assert store.health.outages == 1


def test_a_connector_limit_refuses_when_the_store_is_unreachable() -> None:
    """The other half, and the one that costs something. Xero is 5,000 calls a day per
    tenant, shared with every other integration the client runs. Overrunning it does not
    degrade us; it breaks their finance team's other tools until midnight, and nothing we
    operate can give the calls back.

    Delete this and a Valkey outage quietly spends a resource we do not own."""
    store, _ = store_with(raises=RedisConnectionError("no route to host"))

    verdict = store.check_and_record(now=NOW, limits=(per_connector(),))

    assert not verdict.allowed
    assert verdict.degraded
    assert verdict.decision.retry_after_seconds > 0
    assert store.health.fail_closed == 1


def test_one_connector_limit_closes_a_request_that_also_carries_fairness_limits() -> None:
    """A real request carries both: a person's own rate and their share of a connector.
    Fail closed wins, because the caller is about to spend an external ceiling and nothing
    in hand can say how much of it is left.

    Delete this and the policy still passes both single-scope tests above while admitting
    every real mixed request during an outage."""
    store, _ = store_with(raises=RedisConnectionError("no route to host"))

    verdict = store.check_and_record(now=NOW, limits=(per_principal(), per_connector()))

    assert not verdict.allowed


def test_an_outage_line_names_scopes_and_never_subjects() -> None:
    """An outage report listing subjects is a list of who was active during the outage,
    written to whatever reads operator logs and kept for as long as those are."""
    store, _ = store_with(raises=RedisConnectionError("down"))

    verdict = store.check_and_record(now=NOW, limits=(per_principal(), per_connector()))

    rendered = " ".join(f"{k}={v}" for k, v in verdict.log_record().items())
    assert "p_alice" not in rendered
    assert "xero" not in rendered


def test_every_limit_scope_says_what_happens_when_the_store_is_unreachable() -> None:
    """A scope with no entry would take one behaviour or the other by accident, and the
    accident nobody notices is the one that admits.

    This is the test that makes adding a `LimitScope` a decision rather than an edit."""
    assert set(UNREACHABLE_POLICY) == set(LimitScope)
    assert set(UNREACHABLE_POLICY.values()) == set(Availability)


def test_a_scope_that_guards_something_outside_this_system_fails_closed() -> None:
    """Spelled out as the rule rather than as the table, so that changing the table without
    changing the rule fails here.

    The distinction is not "important" versus "unimportant". It is whether the resource can
    be given back: capacity inside this system returns when the outage ends, and a spent
    Xero call does not."""
    for scope, availability in UNREACHABLE_POLICY.items():
        outside = "connector" in str(scope)
        expected = Availability.FAIL_CLOSED if outside else Availability.FAIL_OPEN
        assert availability is expected, f"{scope} has the wrong outage behaviour"


# ------------------------------------------------------------------- nothing to do
def test_a_request_governed_by_no_limits_touches_the_store_at_all_not() -> None:
    """An empty allowance list means unlimited by configuration, not unknown. Reading a
    window for it would put a key in Valkey for every unlimited caller, and reporting it as
    degraded would make an ordinary request look like an outage."""
    store, client = store_with()

    verdict = store.check_and_record(now=NOW, limits=())

    assert verdict.allowed
    assert not verdict.degraded
    assert client.watch_calls == 0


def test_an_admitted_request_is_recorded_against_every_limit_that_governed_it() -> None:
    """A request that consumed a Xero call consumed it from the connector's window and from
    the caller's share. Recording one of those makes the other drift until it means
    nothing, and the drift is silent for as long as nobody is near a ceiling."""
    store, client = store_with()
    limits = (per_principal(limit=5), per_connector(limit=5))

    store.check_and_record(now=NOW, limits=limits)

    for limit in limits:
        assert len(client.sets[render_key(limit.key)]) == 1


@pytest.mark.parametrize("degraded", [True, False])
def test_a_verdict_reports_the_same_answer_as_the_decision_it_wraps(degraded: bool) -> None:
    """`allowed` on the wrapper and `allowed` on the decision must never disagree; a caller
    reading the wrapper and an operator reading the decision would see different events."""
    store, _ = store_with(raises=RedisConnectionError("down") if degraded else None)
    verdict: StoreVerdict = store.check_and_record(now=NOW, limits=(per_principal(),))

    assert verdict.allowed is verdict.decision.allowed


# ---------------------------------------------------------- a lost race writes nothing
def test_a_lost_race_records_its_hit_once_and_not_once_per_attempt() -> None:
    """A transaction that lost the race wrote nothing, so the retry that wins is the only
    write. A store that applied the losing attempt's writes would record one hit per attempt,
    and under contention a limit would fill several times faster than requests arrive.

    Delete this and the fake's transaction can go back to applying writes at once, which is
    the version of it that could not have caught this."""
    store, client = store_with(conflict_for=2)
    limits = (per_principal(limit=5),)

    assert store.check_and_record(now=NOW, limits=limits).allowed

    assert len(client.sets[render_key(limits[0].key)]) == 1


# -------------------------------------------------------------- the run of refusals
def test_each_refusal_in_a_row_is_counted_for_the_caller() -> None:
    """`limits.backoff_seconds` needs how many times in a row a caller was refused, and the
    window cannot say, because a refusal is never recorded there. The counter is what can.

    Delete this and the verdict can report zero for ever, and every hint stays exact however
    long a client loops."""
    store, client = store_with()
    limits = (per_principal(limit=1),)
    store.check_and_record(now=NOW, limits=limits, caller="p_alice")

    runs = [
        store.check_and_record(now=NOW, limits=limits, caller="p_alice").consecutive_refusals
        for _ in range(3)
    ]

    assert runs == [1, 2, 3]
    assert client.ttls[refusals_key("p_alice")] == REFUSALS_FORGOTTEN_AFTER_SECONDS


def test_an_admission_forgets_the_run_of_refusals() -> None:
    """A caller who waited and was admitted has stopped looping, and the next refusal starts
    a new run with the exact hint. Without the reset a person refused four times in the
    morning is told to wait five minutes in the afternoon.

    Delete this and the counter only ever grows until it expires."""
    store, client = store_with()
    limits = (per_principal(limit=1, window=60.0),)
    store.check_and_record(now=NOW, limits=limits, caller="p_alice")
    store.check_and_record(now=NOW, limits=limits, caller="p_alice")

    later = NOW + timedelta(seconds=61)
    assert store.check_and_record(now=later, limits=limits, caller="p_alice").allowed

    assert refusals_key("p_alice") not in client.counters
    refused = store.check_and_record(now=later, limits=limits, caller="p_alice")
    assert refused.consecutive_refusals == 1


def test_the_run_is_forgotten_after_the_longest_hint_there_is() -> None:
    """The counter expires on its own after `MAX_BACKOFF_SECONDS`: a caller who waited that
    long is not looping. Asserted against the backoff ceiling in `brain.ops.limits`, which is
    outside this module, so changing one without the other fails here.

    Delete this and the expiry can drift to a day, which remembers a morning's loop until
    tomorrow."""
    assert REFUSALS_FORGOTTEN_AFTER_SECONDS == int(MAX_BACKOFF_SECONDS)


def test_the_refusal_counter_is_never_read_as_a_window() -> None:
    """The counter lives under its own prefix, so the walk the Limits screen makes over the
    windows cannot find it and parse it as a window nobody declared.

    Delete this and moving the counter under the window prefix looks tidy."""
    assert parse_key(refusals_key("p_alice")) is None
    assert not refusals_key("p_alice").startswith(f"{KEY_PREFIX}:")


def test_an_early_ask_records_nothing_and_forgets_nothing() -> None:
    """`check_only` is the ask the request path makes before any work. It must not record a
    hit, because the request has not been admitted yet, and an admission there must not wipe
    a run of refusals for the same reason; its refusal is a refusal and is counted.

    Delete this and the early ask can record, which counts every admitted question twice."""
    store, client = store_with()
    limits = (per_principal(limit=1),)
    key = render_key(limits[0].key)

    assert store.check_only(now=NOW, limits=limits, caller="p_alice").allowed
    assert not client.sets.get(key)

    store.check_and_record(now=NOW, limits=limits, caller="p_alice")
    first = store.check_only(now=NOW, limits=limits, caller="p_alice")
    second = store.check_only(now=NOW, limits=limits, caller="p_alice")

    assert (first.consecutive_refusals, second.consecutive_refusals) == (1, 2)
    assert len(client.sets[key]) == 1


def test_a_caller_nobody_named_leaves_no_counter() -> None:
    """The counter is kept only for a caller the request path names. A window checked for a
    connector sync or a widget mint has nobody to back off, and a counter keyed on nothing
    would be one counter shared by every such caller.

    Delete this and `caller=None` can be rendered as the string None."""
    store, client = store_with()
    limits = (per_principal(limit=1),)
    store.check_and_record(now=NOW, limits=limits)

    refused = store.check_and_record(now=NOW, limits=limits)

    assert refused.consecutive_refusals == 0
    assert client.counters == {}


# ------------------------------------------------------------ the windows that exist
def test_a_key_reads_back_as_the_window_it_was_written_for() -> None:
    """The Limits screen finds keys it did not ask for and has to know which window each is.
    A subject carrying the separator is the case that matters: a widget origin or a
    principal's share of a connector.

    Delete this and `parse_key` can split on the colon inside a subject."""
    for key in (
        principal_limit("p_alice").key,
        (LimitScope.PRINCIPAL_CONNECTOR, "p_alice:xero", "minute"),
        (LimitScope.WIDGET_ORIGIN, "https://app.example.com/embed", "minute"),
    ):
        assert parse_key(render_key(key)) == key


def test_a_key_this_module_did_not_write_is_not_a_window() -> None:
    """Another prefix, the wrong number of segments, or a scope this release does not know.
    The last is a key a newer release wrote during a rolling deploy, and it is passed over
    rather than taking the screen down.

    Delete this and any key under a colon-joined name parses as something."""
    assert parse_key("ans:principal:p_alice:minute") is None
    assert parse_key(f"{KEY_PREFIX}:principal:p_alice") is None
    assert parse_key(f"{KEY_PREFIX}:department:finance:minute") is None


def test_the_windows_that_exist_are_listed_with_the_limit_the_policy_gives_them() -> None:
    """What the Limits screen reads: every window in the store, the limit `limits.limit_for`
    gives its key, and the hits, so `limits.check` can say which are refusing now.

    Asserted by judging the result, not by counting keys, because the screen's question is
    which windows refuse: a full window must come back refusing and an empty one must not.

    Delete this and the screen can go back to saying nothing here can read the windows."""
    store, client = store_with()
    full = principal_limit("p_alice")
    quiet = channel_limit("console")
    for n in range(full.limit):
        store.check_and_record(now=NOW + timedelta(milliseconds=n), limits=(full,))
    store.check_and_record(now=NOW, limits=(quiet,))

    limits, state = store.live(NOW + timedelta(seconds=1))

    assert {one.key for one in limits} == {full.key, quiet.key}
    refusing = [
        one.key for one in limits if not check(now=NOW, limits=(one,), state=state).allowed
    ]
    assert refusing == [full.key]


def test_a_key_the_policy_gives_no_limit_is_passed_over() -> None:
    """A window the policy cannot judge is not shown with a guessed limit, for
    `limits.source_limits`' reason about inventing a ceiling. A connector with no verified
    ceiling is the case.

    Delete this and the walk can hand the screen a window with no limit to judge it by."""
    store, client = store_with()
    client.sets[render_key((LimitScope.CONNECTOR, "unmeasured", "minute"))] = {"m": 1.0}
    xero = next(one for one in source_limits("xero", principal_id="p_alice"))
    client.sets[render_key(xero.key)] = {"m": NOW.timestamp()}

    limits, _ = store.live(NOW)

    assert [one.key for one in limits] == [xero.key]


def test_a_store_that_cannot_be_walked_says_so_rather_than_answering_empty() -> None:
    """An empty state reads as nobody being refused, which is the reassuring answer and the
    wrong one during an outage.

    Delete this and an outage renders on the Limits screen as a quiet afternoon."""
    store, _ = store_with(raises=RedisConnectionError("down"))

    with pytest.raises(WindowsUnreadableError):
        store.live(NOW)
