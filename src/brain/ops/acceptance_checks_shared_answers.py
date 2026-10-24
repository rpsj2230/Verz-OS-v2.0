"""The install check for sharing one answer run: an equal reach waits and a different one does not.

The check asks through `brain.api_routes.answered_for`, the function Ask and every chat channel
answer through, with the `shared_answer_runs` switch turned on inside the check's own transaction
and a registry of its own on `app.state`, which is where `brain.api_routes.sharing_a_run` finds the
install's. What it proves is the sentence of M36.2.3 on the install, against real reaches: a
colleague whose grants equal the first asker's is held back for a run in flight and then handed the
answer that run stored, and a colleague whose grants differ is not held back and is told nothing of
the price.

**The run in flight is held by the check, because the harness cannot make two requests at once.**
Its sessions share one database connection, so two asks truly in parallel would fail on the
driver and not on the product. The check registers a run for the first asker's key itself, with the
install's own registry, starts the second ask, and releases the run when that ask is seen to be
waiting. Every step of the ask is the install's, including the lookup it makes afterwards.

**The cache is the check's own.** It is an in-memory store that can be shut, so the wait is
observable. Whether the install's real cache serves the answer afterwards is
`brain.ops.acceptance_checks_cache`'s sentence, not this one's, and an install with no cache
address still runs this check.

Task ids: M36.2.3.1, M36.2.3.2
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_checks_memory import KeptPrompts
from brain.ops.acceptance_checks_speed import asked_on, rules_app
from brain.ops.acceptance_checks_tables import (
    ASKED_COLUMNS,
    ASKED_HEADINGS,
    _administrator,
    _apply,
    _price_list,
    _upload,
)
from brain.ops.acceptance_run import Harness
from brain.ops.shared_answers import InFlightAnswers

if TYPE_CHECKING:
    from brain.gate.cache_key import CachedAnswer, CacheKeyParts

A, _B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2130

#: The column the check's rule answers with: one a first upload holds restricted.
ASKED: Final = "cost"

#: How the check's rule asks for a service's cost, around a word nothing else holds.
COST_TEMPLATE: Final = "acceptance shared cost {word} for {{name}}"

#: How long the check lets a request that should not have been held back run before it fails.
HELD_BACK_FOR_TOO_LONG: Final = 20.0

#: How many times the check looks, a twentieth of a second apart, for the second asker to arrive.
LOOKS_FOR_THE_ASKER: Final = 100


@dataclass
class ShutStore:
    """An in-memory `brain.gate.answer_cache.AnswerStore` that can be shut, to read as empty."""

    data: dict[str, CachedAnswer] = field(default_factory=dict)
    open: bool = True

    def get(self, key: str) -> CachedAnswer | None:
        return self.data.get(key) if self.open else None

    def set(self, key: str, value: CachedAnswer, ttl_seconds: int) -> None:
        del ttl_seconds
        self.data[key] = value


class Watched(InFlightAnswers):
    """The install's registry, noting the parts of every request that arrives at it."""

    def __init__(self) -> None:
        super().__init__(wait_seconds=HELD_BACK_FOR_TOO_LONG)
        self.seen: list[CacheKeyParts] = []

    async def arrive(self, parts: CacheKeyParts, *, look: Any) -> Any:
        self.seen.append(parts)
        return await super().arrive(parts, look=look)


@check(
    leaves=("M36.2.3.1", "M36.2.3.2"),
    sentence=(
        "With answer sharing switched on, a colleague whose grants equal the first asker's is held "
        "back while that asker's run for the same words is in flight and is then answered from "
        "what the run stored, and a colleague without the price grant asking the same words is "
        "not held back and is told nothing of the price."
    ),
)
async def equal_reach_waits_for_a_run_in_flight_other_reach_does_not(
    h: Harness,
) -> None:
    from brain.gate.context import Channel
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.knowledge.columns import ColumnAccess, column_capability, table_capability
    from brain.ops.features import switch
    from brain.ops.features_declared.shared_answer_runs import SHARED_ANSWER_RUNS
    from brain.tables.audit import attributed_to
    from brain.tables.fast_lane import FastPathRuleRow

    await h.found_departments()
    admin = await _administrator(h)
    prices = _price_list(h, "shared", ASKED_HEADINGS, ASKED_COLUMNS)
    await _upload(h, admin, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    opened = await _apply(h, admin, prices.entity, "department", ColumnAccess.OPEN)
    if not opened.applied:
        raise CheckFailedError("an uploaded price list's department column could not be opened")
    template = COST_TEMPLATE.format(word=h.word().lower())
    await h.execute(
        *h.attributed(),
        insert(FastPathRuleRow).values(
            rule_id=f"acceptance_{h.run}_shared_cost",
            template=template,
            slot="name",
            source=TABLES_SOURCE,
            entity=prices.entity,
            match_field="name",
            answer_field=ASKED,
            created_by=h.actor,
        ),
    )
    table = table_capability(prices.entity).value
    priced = tuple(column_capability(prices.entity, one).value for one in (ASKED, "margin"))
    first, colleague, unpriced = (
        h.principal(A, "priced"),
        h.principal(A, "colleague"),
        h.principal(A, "unpriced"),
    )
    await h.person(first, department=A, grants=_in(A, table, *priced))
    await h.person(colleague, department=A, grants=_in(A, table, *priced))
    await h.person(unpriced, department=A, grants=_in(A, table))

    reach = admin.reach
    async with h.sessions() as session, session.begin():
        for statement in attributed_to(
            actor_id=admin.principal_id, ent_hash=reach.ent_hash(), trace_id=h.trace_id
        ):
            await session.execute(statement)
        await switch(session, SHARED_ANSWER_RUNS, on=True, by=admin.principal_id)

    store, registry = ShutStore(), Watched()
    app = await rules_app(h, KeptPrompts())
    app.state.answer_store = store
    app.state.in_flight_answers = registry
    service = prices.rows[0]
    question = template.replace("{name}", service["name"])
    counter = iter(range(1, 100))

    async def asked(principal_id: str) -> Any:
        return await asked_on(h, app, principal_id, question, next(counter), Channel.CONSOLE)

    led = await asked(first)
    if led.from_cache or led.text is None or service[ASKED] not in led.text:
        raise CheckFailedError("a price the asker may read was not answered from its row")
    if len(registry.seen) != 1:
        raise CheckFailedError(
            "an answered question was never registered as a run in flight, so sharing is not "
            "switched on or not reached"
        )
    if registry.in_flight() != 0:
        raise CheckFailedError("an answered question left its run registered")
    running = registry.seen[0]

    # The first asker's run, still going: the store reads as empty until it has finished.
    store.open = False
    held = await registry.arrive(running, look=lambda: None)
    flight = held.flight
    if flight is None:
        raise CheckFailedError("a run for the first asker's key could not be registered")
    registry.seen.clear()
    waiting = asyncio.create_task(asked(colleague))
    try:
        for _ in range(LOOKS_FOR_THE_ASKER):
            if registry.seen or waiting.done():
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        if waiting.done() or len(registry.seen) != 1:
            raise CheckFailedError(
                "a colleague with exactly the first asker's grants was not held back for the "
                "run in flight"
            )
        if registry.seen[0] != running:
            raise CheckFailedError(
                "a colleague with the first asker's grants waited under a different key"
            )
        store.open = True
        flight.release()
        shared = await asyncio.wait_for(waiting, HELD_BACK_FOR_TOO_LONG)
    finally:
        flight.release()
        if not waiting.done():
            waiting.cancel()
    if not shared.from_cache or not any(service[ASKED] in frame for frame in shared.frames):
        raise CheckFailedError(
            "the colleague who waited was not answered from what the run in flight stored"
        )

    store.open = False
    still = await registry.arrive(running, look=lambda: None)
    second_flight = still.flight
    if second_flight is None:
        raise CheckFailedError("a second run for the first asker's key could not be registered")
    registry.seen.clear()
    try:
        other = await asyncio.wait_for(asked(unpriced), HELD_BACK_FOR_TOO_LONG)
    except TimeoutError:
        raise CheckFailedError(
            "a colleague without the price grant was held back for another reach's run"
        ) from None
    finally:
        second_flight.release()
    if other.text is not None and service[ASKED] in other.text:
        raise CheckFailedError("a colleague without the price grant was told the price")
    if len(registry.seen) != 1 or registry.seen[0].ent_hash == running.ent_hash:
        raise CheckFailedError("a colleague with different grants was registered at the same reach")
    if registry.in_flight() != 0:
        raise CheckFailedError("a run was left registered when the check had finished with it")
