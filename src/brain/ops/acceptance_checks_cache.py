"""The install acceptance check for the answer cache: an answer reaches only the reach it was for.

The check asks through `brain.api_routes.answered_for`, the function Ask and every chat channel
answer through, with the install's own cache behind `app.state.answer_store`, which is where
`brain.app.lifespan` puts it. What it proves is the sentence of M6.5.2 on the install: two people
with different reach asking the same words, a person moving department, and a source changing, and
in none of them a cached answer reaching somebody it was not computed for or outliving the rows it
was computed from.

**The cache is the install's and the keys are the check's own.** Every key the check's asks store
is kept as it is written and deleted by name when the check ends, whatever happened, which is
`brain.ops.acceptance.WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME`. A key is a digest of
the question, the reach, the agent, the policy and the uploads, and the question names a word
nothing else holds, so no real person's question can find what the check stored and the check
cannot find a real person's answer.

**Plans and prompt prefixes.** Nothing on the answer path caches a plan: the answer lane asks a
model with no tool catalogue, so there is no plan to keep, and `brain.gate.caches`' plan store is
reached by no request. The prompt prefix a provider may cache is held to carry nothing of any
caller by `brain.ops.acceptance_checks_speed`'s check of it, over two people with different reach.

Task ids: M6.5.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import _in

# The speed checks' rule, application and asking, imported rather than copied, and imported
# first so the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks_memory import KeptPrompts
from brain.ops.acceptance_checks_speed import asked_on, rules_app
from brain.ops.acceptance_checks_tables import (
    ASKED_COLUMNS,
    ASKED_HEADINGS,
    _administrator,
    _apply,
    _price_list,
    _PriceList,
    _upload,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.gate.answer_cache import AnswerStore
    from brain.gate.cache_key import CachedAnswer

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 290

#: The column the check's rule answers with: one a first upload holds restricted, so a reader of
#: the table without its own grant is told nothing about it.
ASKED: Final = "cost"

#: How the check's rule asks for a service's cost, around a word nothing else holds.
COST_TEMPLATE: Final = "acceptance cost {word} for {{name}}"


@dataclass
class KeptKeys:
    """`brain.gate.answer_cache.AnswerStore` over another store, keeping every key it writes."""

    inner: AnswerStore
    keys: list[str] = field(default_factory=list)

    def get(self, key: str) -> CachedAnswer | None:
        return self.inner.get(key)

    def set(self, key: str, value: CachedAnswer, ttl_seconds: int) -> None:
        self.keys.append(key)
        self.inner.set(key, value, ttl_seconds)


def answer_store_for(h: Harness) -> AnswerStore:
    """The install's own answer cache, as the lifespan builds it, with every key it writes removed
    when the check ends. Not run on a process that was not given the cache's address."""
    from brain.cache import ValkeyAnswerStore, make_client

    if not h.settings.valkey_url:
        raise CheckNotRunError(
            "the worker running this check was not given the cache address the application "
            "uses, so there is no cache to ask"
        )
    client = make_client(h.settings.valkey_url)
    kept = KeptKeys(ValkeyAnswerStore(client))

    def removed() -> None:
        if kept.keys:
            # A client method the library leaves untyped; the keys are this check's alone.
            cast(Any, client).delete(*kept.keys)

    h.removes(cast(Any, client).close)
    h.removes(removed)
    return kept


@dataclass(frozen=True)
class Asking:
    """What one ask came to: whether it came from the cache, and the words it carried."""

    from_cache: bool
    text: str | None


# ------------------------------------------------------------------------ M6.5.2 the cache
@check(
    leaves=("M6.5.2",),
    sentence=(
        "In the install's own cache, a price asked twice is answered the second time from the "
        "cache; a colleague without the price grant asking the same words is answered afresh and "
        "told nothing; the list uploaded again, and the first asker moved to acceptance_b, are "
        "each answered afresh, the first with the new price and the second with nothing."
    ),
)
async def a_cached_answer_reaches_only_the_reach_it_was_computed_for(h: Harness) -> None:
    from brain.gate.context import Channel
    from brain.govern_routes import retire_grant
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.knowledge.columns import ColumnAccess, column_capability, table_capability
    from brain.tables.fast_lane import FastPathRuleRow

    store = answer_store_for(h)
    await h.found_departments()
    admin = await _administrator(h)
    prices = _price_list(h, "cache", ASKED_HEADINGS, ASKED_COLUMNS)
    await _upload(h, admin, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    opened = await _apply(h, admin, prices.entity, "department", ColumnAccess.OPEN)
    if not opened.applied:
        raise CheckFailedError("an uploaded price list's department column could not be opened")
    template = COST_TEMPLATE.format(word=h.word().lower())
    await h.execute(
        *h.attributed(),
        insert(FastPathRuleRow).values(
            rule_id=f"acceptance_{h.run}_cost",
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
    # The cost is derived from the margin and the sell price, so reading it needs both grants,
    # as a finance reader holds them in the table check.
    priced = tuple(column_capability(prices.entity, one).value for one in (ASKED, "margin"))
    first, second = h.principal(A, "priced"), h.principal(A, "unpriced")
    await h.person(first, department=A, grants=_in(A, table, *priced))
    await h.person(second, department=A, grants=_in(A, table))

    app = await rules_app(h, KeptPrompts())
    app.state.answer_store = store
    service = prices.rows[0]
    question = template.replace("{name}", service["name"])
    counter = iter(range(1, 100))

    async def asked(principal_id: str) -> Asking:
        told = await asked_on(h, app, principal_id, question, next(counter), Channel.CONSOLE)
        return Asking(from_cache=told.from_cache, text=told.text)

    fresh, again = await asked(first), await asked(first)
    if fresh.from_cache or fresh.text is None or service[ASKED] not in fresh.text:
        raise CheckFailedError("a price the asker may read was not answered from its row")
    if not again.from_cache:
        raise CheckFailedError(
            "the same person asking the same words was not answered from the cache"
        )

    other = await asked(second)
    if other.from_cache or (other.text is not None and service[ASKED] in other.text):
        raise CheckFailedError(
            "a colleague without the price grant was served the answer cached for somebody with it"
        )

    await _changed(h, admin, prices)
    changed = await asked(first)
    if changed.from_cache or changed.text is None or NEW_PRICE not in changed.text:
        raise CheckFailedError(
            "a price list uploaded again was answered from the old upload's cache"
        )

    for capability in (table, *priced):
        await h.execute(*h.attributed(), retire_grant(first, capability))
    for capability in (table, *priced):
        await h.grant(first, capability, _in(B, capability)[0][1])
    moved = await asked(first)
    if moved.from_cache or (moved.text is not None and service[ASKED] in moved.text):
        raise CheckFailedError("a person who moved department was served an answer cached before")


#: The price the list is uploaded again with, for the first service. A word nothing else holds.
NEW_PRICE: Final = "QZNEWPRICEACCEPTANCE"


async def _changed(h: Harness, admin: Any, prices: _PriceList) -> None:
    """The same list uploaded again with a new price for its first service, as its administrator
    would upload a corrected file."""
    rows = list(prices.rows)
    rows[0] = {**rows[0], ASKED: NEW_PRICE}
    again = _PriceList(
        entity=prices.entity, headings=prices.headings, columns=prices.columns, rows=tuple(rows)
    )
    await _upload(h, admin, again, filename=f"{prices.entity}.csv", content=again.csv())
