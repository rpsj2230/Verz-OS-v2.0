"""Where the price of each model is kept: one `ops.setting` row per provider, read per call.

`brain.models.pricing` decides what a price is and what a request cost at it. This is the half
that talks to PostgreSQL, and it decides neither.

**`ops.setting` rather than a table of its own**, for `brain.ops.setting_store`'s own argument: a
price is a number somebody changes at four in the afternoon when a provider changes its list, and
the table already holds the key, the value, who changed it last and when. `0059`'s trigger appends
a `setting` entry to the audit ledger for every write that moves a row, naming the key and the
writer and never the value, so a price change is a decision on the ledger without a migration,
a policy or a trigger of its own. See `A_PRICE_CHANGE_IS_ON_THE_LEDGER_UNDER_ITS_PROVIDER`.

**One row per provider, keyed `model_price.<provider>`, holding an object of models.** A provider's
slug fits a setting key's grammar and a model's name does not (`claude-sonnet-4-5`, `gpt-4.1`), so
the model is a key inside the value rather than a segment of the row's key. Encoding the model
into the key was rejected: two names that fold to the same key would overwrite each other's price.

**A price is merged into its provider's row by the database, in one statement.** The upsert's
update half is `value || excluded.value`, so two administrators pricing two models of one provider
at once both land. Reading the row, changing it in Python and writing it back loses whichever
write commits first, and does so silently.

**A row that does not construct prices nothing, and says so in the log.** Something written at a
psql prompt, or by a release that stored a price differently, is not a price this release can cost
a call at, and a model with no usable price is unpriced, which the Models screen names.

Task ids: M27.12.5
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import structlog
from sqlalchemy import func, type_coerce
from sqlalchemy.dialects.postgresql import JSONB, Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

from brain.models.pricing import Price, PricingError, price_of, stored_of
from brain.ops.setting_store import (
    SettingState,
    SettingStoreError,
    checked_key,
    read_namespace,
    values_under,
)
from brain.tables.config import SettingRow, SettingType

log = structlog.get_logger(__name__)

#: Why a price is kept where a switch is.
A_PRICE_CHANGE_IS_ON_THE_LEDGER_UNDER_ITS_PROVIDER: Final = (
    "A price is kept in ops.setting under model_price.<provider>, and that table's trigger appends "
    "a setting entry to the audit ledger for every write, naming the key and who wrote it and "
    "never the figure. So a price change is on the ledger under its provider, the row says who "
    "changed that provider's prices last, and the ledger holds every change before it."
)

#: The namespace the prices are kept under.
PRICE_NAMESPACE: Final = "model_price"

#: The row's own description, product text rather than anything a person typed.
DESCRIPTION: Final = (
    "What a million tokens cost on each of this provider's models, in and out, in minor units of "
    "the install's currency. What a model call's cost is recorded at."
)


def price_key(provider: str) -> str:
    """The `ops.setting` key one provider's prices are kept under, or a refusal."""
    try:
        return checked_key(f"{PRICE_NAMESPACE}.{provider}")
    except SettingStoreError:
        msg = f"{provider!r} is not a provider name a price can be kept under"
        raise PricingError(msg) from None


def prices_in(states: Mapping[str, SettingState]) -> dict[tuple[str, str], Price]:
    """Every price the rows hold, by provider and model. A row or entry that does not construct
    is left out and logged by its key, never by its value."""
    found: dict[tuple[str, str], Price] = {}
    for provider, state in values_under(states, PRICE_NAMESPACE).items():
        if state.value_type != SettingType.JSON.value or not isinstance(state.value, Mapping):
            log.warning("prices.row_unreadable", key=state.key)
            continue
        for model, stored in state.value.items():
            try:
                found[(provider, str(model))] = price_of(stored)
            except PricingError:
                log.warning("prices.entry_unreadable", key=state.key)
    return found


async def read_prices(session: AsyncSession) -> dict[tuple[str, str], Price]:
    """Every live price, by provider and model."""
    return prices_in(await read_namespace(session, PRICE_NAMESPACE))


def set_price_statement(provider: str, model: str, price: Price, *, by: str) -> Insert:
    """One model's price merged into its provider's live row, which is made if there is none.

    `updated_by` is required for `brain.ops.setting_store.put_statement`'s reason: the row is the
    only record of who changed it last.
    """
    if not by.strip():
        msg = "a price set by nobody is a row that says a change happened and not whose"
        raise PricingError(msg)
    if not model.strip():
        msg = "a price names the model it is the price of"
        raise PricingError(msg)
    statement = insert(SettingRow).values(
        key=price_key(provider),
        value_type=SettingType.JSON.value,
        value={model: stored_of(price)},
        description=DESCRIPTION,
        updated_by=by,
    )
    merged: Any = type_coerce(SettingRow.value, JSONB).op("||")(
        type_coerce(statement.excluded.value, JSONB)
    )
    return statement.on_conflict_do_update(
        index_elements=[SettingRow.key],
        index_where=SettingRow.deleted_at.is_(None),
        set_={
            "value": merged,
            "value_type": statement.excluded.value_type,
            "description": statement.excluded.description,
            "updated_by": statement.excluded.updated_by,
            "updated_at": func.now(),
        },
    )


async def set_price(
    session: AsyncSession, provider: str, model: str, price: Price, *, by: str
) -> None:
    """Set one model's price in the caller's transaction. The caller attributes and commits."""
    await session.execute(set_price_statement(provider, model, price, by=by))
