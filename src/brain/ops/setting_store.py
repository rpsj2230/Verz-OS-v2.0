"""Reading and writing one namespace of `ops.setting`, for a switch a person turns in the console.

`brain.ops.install_settings` is the wizard's reader and writer and is shaped around one namespace,
`install`, whose rows are always strings resolved through `brain.install.value_of`. Two new
namespaces arrive with the console's switches: `feature`, which says whether a genuinely new
feature is switched on (`brain.ops.features`), and `schedule`, which says whether a scheduled
control is paused and when a person last asked for one to run (`brain.ops.schedule_control`).
Both are booleans or instants rather than installation values, and neither belongs in `value_of`,
so this is the half they share: a namespace read and a single upsert, and nothing that decides
what a row means.

**`ops.setting` rather than a table of their own, and the table argues for it in its first
paragraph.** It is "the numbers and flags somebody changes at four in the afternoon", with a type
pinned to its value, a key grammar that cannot parse as a capability, a partial unique index
making one live row per key, and a refusal of every namespace the permission model owns. A pause
and a feature switch are exactly those knobs. A table of their own would need a migration, a
second row-level security policy and a registration in `brain.tables`, to hold the same four
facts this one already holds: the key, the value, who changed it last and when.

**What that cost was, and how it was paid.** A row records its last change and nothing before it,
which `brain.tables.config` called "not small": until 2026-09-17 there was no history, because the
audit ledger had no action for tuning a setting. `0059` added one and a trigger on the table, so
every write here that moves a row is a `setting` entry appended in the same transaction, and the
history is the ledger's rather than a second one kept here. See
`A_SWITCH_SHOWS_ITS_LAST_CHANGE_AND_THE_LEDGER_KEEPS_EVERY_ONE`.

**`updated_at` is set on the conflict branch, by the database.** An upsert's update half is a
Core statement, which `TimestampMixin`'s `onupdate` does not reach, so a row turned on in March
and off in September would otherwise still say March. `brain.ops.install_settings.save` has that
defect today; it is that module's, and this one does not inherit it.

Task ids: M27.8.13
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

from brain.tables.config import (
    RESERVED_KEY_PREFIXES,
    SETTING_KEY_CHARS,
    SETTING_KEY_PATTERN,
    SettingRow,
    SettingType,
)

#: Why the console says a switch shows its last change and the audit trail holds the rest.
A_SWITCH_SHOWS_ITS_LAST_CHANGE_AND_THE_LEDGER_KEEPS_EVERY_ONE: Final = (
    "ops.setting keeps who changed a row last and when, and overwrites both on the next change. "
    "The history is the audit ledger's: 0059's trigger on the table appends a setting entry for "
    "every write that moves a row, naming the key, the direction of a switch and the writer, and "
    "never the value. A screen that showed the last change as though it were the history would "
    "be read as the whole record, so the screen says where the rest is."
)


class SettingStoreError(Exception):
    """Raised when a key could not be a row of `ops.setting` at all."""


@dataclass(frozen=True)
class SettingState:
    """One live row, as a switch reads it. Never a description: that is product text."""

    key: str
    value_type: str
    value: Any
    updated_by: str
    updated_at: datetime


def checked_key(key: str) -> str:
    """The key, or a refusal naming the rule it breaks, before the database's own refusal.

    The check constraints are still what hold; this is the message. A key in a namespace the
    permission model owns is refused here in the words `brain.tables.config` uses, because the
    failure otherwise arrives as a constraint name nobody at the console can act on.
    """
    if len(key) > SETTING_KEY_CHARS or not re.fullmatch(SETTING_KEY_PATTERN, key):
        msg = f"{key!r} is not a setting key: lowercase dotted names, at least two segments"
        raise SettingStoreError(msg)
    if key.split(".", 1)[0] in RESERVED_KEY_PREFIXES:
        msg = f"{key!r} sits in a namespace the permission model owns, and no switch may"
        raise SettingStoreError(msg)
    return key


def namespace_rows(namespace: str) -> Select[tuple[str, str, Any, str, datetime]]:
    """Every live row under `namespace.`, in key order.

    `deleted_at` is tested here as well as by the table's policy, for the reason
    `brain.ops.install_settings.load` gives: a connection as the table's owner sees retired rows.
    """
    # A namespace is a key missing its last segment, so it is checked as one with a segment on.
    checked_key(f"{namespace}.name")
    return (
        select(
            SettingRow.key,
            SettingRow.value_type,
            SettingRow.value,
            SettingRow.updated_by,
            SettingRow.updated_at,
        )
        .where(SettingRow.deleted_at.is_(None))
        .where(SettingRow.key.startswith(f"{namespace}.", autoescape=True))
        .order_by(SettingRow.key)
    )


async def read_namespace(session: AsyncSession, namespace: str) -> dict[str, SettingState]:
    """The live rows under `namespace`, by key."""
    found = await session.execute(namespace_rows(namespace))
    return {
        str(key): SettingState(
            key=str(key),
            value_type=str(value_type),
            value=value,
            updated_by=str(updated_by),
            updated_at=updated_at,
        )
        for key, value_type, value, updated_by, updated_at in found.all()
    }


def put_statement(
    key: str,
    *,
    value_type: SettingType,
    value: bool | str,
    description: str,
    updated_by: str,
) -> Insert:
    """One live row for `key`, inserted or overwritten, with the database's clock on both halves.

    `updated_by` is required and not defaulted, because the row is the only record of who turned
    the switch, and `description` is the switch's own product sentence rather than anything a
    person typed.
    """
    if not updated_by.strip():
        msg = "a switch turned by nobody is a row that says a change happened and not whose"
        raise SettingStoreError(msg)
    statement = insert(SettingRow).values(
        key=checked_key(key),
        value_type=value_type.value,
        value=value,
        description=description,
        updated_by=updated_by,
    )
    return statement.on_conflict_do_update(
        index_elements=[SettingRow.key],
        index_where=SettingRow.deleted_at.is_(None),
        set_={
            "value_type": statement.excluded.value_type,
            "value": statement.excluded.value,
            "description": statement.excluded.description,
            "updated_by": statement.excluded.updated_by,
            "updated_at": func.now(),
        },
    )


async def put(
    session: AsyncSession,
    key: str,
    *,
    value_type: SettingType,
    value: bool | str,
    description: str,
    updated_by: str,
) -> None:
    """Write one switch in the caller's transaction. The caller commits."""
    await session.execute(
        put_statement(
            key,
            value_type=value_type,
            value=value,
            description=description,
            updated_by=updated_by,
        )
    )


def values_under(states: Mapping[str, SettingState], namespace: str) -> dict[str, SettingState]:
    """The rows whose key is `namespace.<name>` with exactly one more segment, by that name."""
    prefix = f"{namespace}."
    return {
        key.removeprefix(prefix): state
        for key, state in states.items()
        if key.startswith(prefix) and "." not in key.removeprefix(prefix)
    }
