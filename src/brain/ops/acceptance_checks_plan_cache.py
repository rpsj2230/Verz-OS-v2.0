"""Install checks for the plan cache and the source-freshness cache, over the install's own cache.

`brain.gate.caches` keys and validates four caches and `brain.cache` stores them in Valkey. The
answer cache has its own install check (`brain.ops.acceptance_checks_cache`); the other two that a
request path can lean on are asked here: **a plan, kept as tool ids and nothing else, and
re-projected through whoever reuses it**, and **a source's epoch, read through the cache and moved
when the source changes**. The unit tests run over a dictionary. What they cannot show is that the
install's cache keeps what the product asks it to keep, under a key of the check's own, and gives
it back.

**The check's keys are its own and are deleted by name.** Neither check writes the install's real
entry: the plans are stored under `plan_key`, a digest of a question nothing else holds, and the
epochs reading is stored under a key the check mints (`brain.gate.caches.SOURCE_EPOCHS_KEY` is one
entry for the whole install, and a reading made inside a rolled-back transaction written under it
would be a wrong reading served to real answers for the length of its lifetime). The product's
`ReadThroughSourceEpochs` is the code under test; only the key it reads and writes is remapped, by
`RemappedEpochs`, and the cache behind it is the install's. Both are removed when the check ends,
whatever happened: see
`brain.ops.acceptance.WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME`.

**What is proved about a plan, and what is not.** A plan is stored with its tool ids and no
definition, description or argument; a caller who holds every tool in it replays all of it; a
caller who lacks one of them replays nothing, and is not even offered it, because the plan is
keyed on the reach that made it. What is not proved is a request path storing a plan: the agent
runtime (`brain.gate.runtime.AgentRuntime`) asks a model for each step and has no planning step
whose result could be kept, so nothing stores a plan yet. The leaf M6.2.2 therefore stands in
`docs/proof-sweep-holds.json`, and this check closes it only when that entry is removed.

**What is proved about freshness.** A reading of every source's epoch is taken from the database
once and served from the cache after that, so the database is not asked again while the reading
lives; a source changing (`advance_epoch`, which the worker calls in the transaction that changed
the rows) is seen as soon as the reading is dropped or lapses, and the answer key built from it
differs from the one built before, so no answer computed before the change is served after it. The
reading's lifetime is the product's `SOURCE_EPOCHS_TTL_SECONDS`, read back from the cache and held
under the answer cache's own `CACHE_TTL_SECONDS`.

Task ids: M6.2.2, M6.2.5
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, cast

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.gate.caches import CachedSourceEpochs

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 891

A, _ = RESERVED_DEPARTMENTS

NO_CACHE_ADDRESS: Final = (
    "the worker running this check was not given the cache address the application uses, so "
    "there is no cache to ask"
)

A_PLAN_HELD_MORE_THAN_TOOL_IDS: Final = "a stored plan held something other than tool ids"
A_PLAN_DID_NOT_COME_BACK: Final = "a plan stored in the install's cache did not come back as stored"
A_REACH_FOUND_ANOTHER_REACHS_PLAN: Final = (
    "a caller with a narrower reach was found the plan stored for a wider one"
)
A_PLAN_WAS_NOT_REPLAYED_WHOLE: Final = (
    "a caller holding every tool in a plan was not given the whole plan back"
)
A_PLAN_SURVIVED_A_MISSING_TOOL: Final = (
    "a caller lacking one tool of a plan was given part of it or all of it"
)

A_READING_WAS_NOT_FROM_THE_DATABASE: Final = (
    "the first reading of the sources' epochs did not come from the database"
)
A_READING_WAS_NOT_KEPT: Final = "a reading of the sources' epochs was read from the database again"
A_CHANGE_WAS_NOT_SEEN: Final = (
    "a source that changed was not read as changed once the kept reading was dropped"
)
AN_ANSWER_KEY_DID_NOT_MOVE: Final = (
    "the answer key did not change when the source it depends on did"
)
A_READING_LIVED_PAST_AN_ANSWER: Final = (
    "the kept reading was given no lifetime, or one longer than an answer's"
)


# ------------------------------------------------------------------------- the cache's side
@dataclass
class KeptKeys:
    """A record cache keeping every key it writes, so each is removed when the check ends."""

    inner: Any
    keys: list[str] = field(default_factory=list)

    def get(self, key: str) -> Any:
        return self.inner.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.keys.append(key)
        self.inner.set(key, value, ttl_seconds)


@dataclass
class RemappedEpochs:
    """`ReadThroughSourceEpochs`' cache with its one fixed key replaced by the check's own.

    The product writes the whole install's reading under one key. A reading made inside a check's
    rolled-back transaction must never be written there, so the key is the only thing changed.
    """

    inner: KeptKeys
    key: str

    def get(self, key: str) -> CachedSourceEpochs | None:
        del key
        return cast("CachedSourceEpochs | None", self.inner.get(self.key))

    def set(self, key: str, value: CachedSourceEpochs, ttl_seconds: int) -> None:
        from brain.gate.caches import CachedSourceEpochs

        del key
        self.inner.set(
            self.key, CachedSourceEpochs(key=self.key, epochs=dict(value.epochs)), ttl_seconds
        )


@dataclass(frozen=True)
class Caches:
    """What the checks ask of the install's cache: the two record caches, a key's lifetime in
    seconds, and the removal of one key, as the lifetime ending would."""

    plans: KeptKeys
    epochs: KeptKeys
    lifetime: Callable[[str], int]
    drop: Callable[[str], None]


def caches_of(h: Harness) -> Caches:
    """The install's plan cache and source-epochs cache.

    A function of its own so a test can hand the check a store: the database half of the tests runs
    with no cache, and the product builds its cache from the address in the settings. Not run on a
    process that was not given that address.
    """
    from brain.cache import make_client, plan_cache, source_epochs_cache

    if not h.settings.valkey_url:
        raise CheckNotRunError(NO_CACHE_ADDRESS)
    client = cast(Any, make_client(h.settings.valkey_url))
    plans = KeptKeys(plan_cache(client))
    epochs = KeptKeys(source_epochs_cache(client))

    def removed() -> None:
        found = [*plans.keys, *epochs.keys]
        if found:
            client.delete(*found)

    h.removes(client.close)
    h.removes(removed)
    return Caches(
        plans=plans,
        epochs=epochs,
        lifetime=lambda key: int(client.ttl(key)),
        drop=lambda key: client.delete(key),
    )


# ------------------------------------------------------------------------ M6.2.2 the plan
@check(
    leaves=("M6.2.2",),
    sentence=(
        "In the install's own cache, a plan is stored as tool ids and nothing else under a key "
        "that carries the reach it was made for; a caller holding every tool in it is given the "
        "whole plan back, a caller lacking one is given none of it, and is not found the other's "
        "entry at all."
    ),
)
async def a_plan_is_kept_as_tool_ids_and_replayed_through_a_projection(
    h: Harness,
) -> None:
    from brain.gate.caches import CachedPlan, CallerKey, plan_key, replay
    from brain.gate.catalogue import AgentCeiling, project
    from brain.gate.resolve import Resolved
    from brain.ops.acceptance_workspace import _leash_tools

    plans = caches_of(h).plans
    write, money, _ = _leash_tools()
    await h.found_departments()
    wide, narrow = h.principal(A, "wide"), h.principal(A, "narrow")
    everywhere = Scope.unrestricted()
    await h.person(
        wide,
        department=A,
        grants=(
            (write.required_capability, everywhere),
            (money.required_capability, everywhere),
        ),
    )
    await h.person(narrow, department=A, grants=((write.required_capability, everywhere),))
    ceiling = AgentCeiling(
        agent_id=f"acceptance_{h.run}_plan",
        allowed_tools=frozenset({write.name, money.name}),
        max_side_effect=money.side_effect,
    )

    async def asking(who: str) -> tuple[Any, Any]:
        reach = await h.reach(who)
        caller = CallerKey.of(
            Resolved(
                entitlements=reach, ent_hash=reach.ent_hash(), grants_version=0, from_cache=False
            ),
            policy_epoch=0,
            now=h.now,
        )
        return caller, project((write, money), reach, ceiling, now=h.now)

    question = f"what should be done about {h.word().lower()}"
    configured = "acceptance"
    wide_caller, wide_tools = await asking(wide)
    narrow_caller, narrow_tools = await asking(narrow)
    key = plan_key(question, wide_caller, agent_config_hash=configured)
    stored = CachedPlan(key=key, tool_ids=(write.name, money.name))
    if {one.name for one in dataclasses.fields(stored)} != {"key", "tool_ids"}:
        raise CheckFailedError(A_PLAN_HELD_MORE_THAN_TOOL_IDS)
    plans.set(key, stored, 60)
    if plans.get(key) != stored:
        raise CheckFailedError(A_PLAN_DID_NOT_COME_BACK)

    if plans.get(plan_key(question, narrow_caller, agent_config_hash=configured)) is not None:
        raise CheckFailedError(A_REACH_FOUND_ANOTHER_REACHS_PLAN)
    whole = replay(stored, wide_tools)
    if not whole.usable or whole.tool_ids != stored.tool_ids:
        raise CheckFailedError(A_PLAN_WAS_NOT_REPLAYED_WHOLE)
    cut = replay(stored, narrow_tools)
    if cut.usable or cut.tool_ids:
        raise CheckFailedError(A_PLAN_SURVIVED_A_MISSING_TOOL)


# -------------------------------------------------------------------- M6.2.5 the freshness
@check(
    leaves=("M6.2.5",),
    sentence=(
        "A reading of every source's epoch is taken from the database once and kept in the "
        "install's cache for a lifetime shorter than an answer's; a source that then changes is "
        "read as changed as soon as the kept reading is dropped, and the answer key built from "
        "the new reading differs from the one built before."
    ),
)
async def a_source_epoch_is_read_through_the_cache_and_moves_the_key(
    h: Harness,
) -> None:
    from brain.gate.caches import SOURCE_EPOCHS_TTL_SECONDS, CallerKey, answer_key
    from brain.gate.resolve import CACHE_TTL_SECONDS, Resolved
    from brain.ops.connector_sync_store import (
        ReadThroughSourceEpochs,
        StoredSourceEpochs,
        advance_epoch,
    )

    caches = caches_of(h)
    await h.found_departments()
    asking = h.principal(A, "asking")
    await h.person(asking, department=A)
    source = f"acceptance_{h.run}_freshness"
    mine = f"epochs:acceptance:{h.run}"

    @dataclass
    class Counting:
        """The database read, counted."""

        asked: int = 0

        async def epochs(self) -> Any:
            self.asked += 1
            return await StoredSourceEpochs(h.sessions).epochs()

    database = Counting()
    through = ReadThroughSourceEpochs(database, RemappedEpochs(caches.epochs, mine))

    first = await through.epochs()
    if database.asked != 1 or source in first:
        raise CheckFailedError(A_READING_WAS_NOT_FROM_THE_DATABASE)
    remaining = caches.lifetime(mine)
    if not 0 < remaining <= min(SOURCE_EPOCHS_TTL_SECONDS, CACHE_TTL_SECONDS):
        raise CheckFailedError(A_READING_LIVED_PAST_AN_ANSWER)

    await h.execute(*h.attributed(), advance_epoch(source))
    again = await through.epochs()
    if database.asked != 1 or dict(again) != dict(first):
        raise CheckFailedError(A_READING_WAS_NOT_KEPT)

    # The reading dropped, as it is when its lifetime ends.
    caches.drop(mine)
    after = await through.epochs()
    if database.asked != 2 or after.get(source) != 1:
        raise CheckFailedError(A_CHANGE_WAS_NOT_SEEN)

    reach = await h.reach(asking)
    caller = CallerKey.of(
        Resolved(entitlements=reach, ent_hash=reach.ent_hash(), grants_version=0, from_cache=False),
        policy_epoch=0,
        now=h.now,
    )
    sources = frozenset({source})

    def key_over(read: Any) -> str:
        return answer_key(
            "a question",
            caller,
            agent_config_hash="acceptance",
            source_epochs=dict(read),
            sources=sources,
        )

    if key_over(first) == key_over(after):
        raise CheckFailedError(AN_ANSWER_KEY_DID_NOT_MOVE)
