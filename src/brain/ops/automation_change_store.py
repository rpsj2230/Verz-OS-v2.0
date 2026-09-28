"""The SQL over `agent.automation_change`: reading an automation's changes back as the domain's, and
the insert whose trigger records one.

`brain.console.automations` decides every change and folds them; `migrations/versions/
0145_automation_change.py` argues the table. What is here holds no rule of its own and opens no
transaction: `brain.ops.automation_run_store` runs these statements inside the transaction that
also locks and moves the automation, for `agent_automations.
A_SCHEDULE_WITHOUT_A_REGISTRY_ROW_IS_WORK_NOTHING_KNOWS_ABOUT`'s reason, and the runner reads them
inside the transaction that claims a run. Kept apart from that module so the runner and the console
read one fold, and neither imports the other's half to get it.

**A row that does not construct is absent, and logged**, which is the direction
`brain.ops.automation_run_store.record_of_run` takes about a run. A change nobody can read cannot
widen anything: the fold falls back to the install and to the changes that do construct, and a
removal that cannot be read is still refused to the runner by `removed_ids`, which reads the kind
column and nothing else.

Task ids: M27.12.3, M27.15.37, M39.6.1.5
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import structlog
from sqlalchemy import Select, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.console.automation_gallery import Cadence, Every, GalleryError
from brain.console.automations import AutomationsError, Change, ChangeKind
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.automation_change import REMOVED, AutomationChangeRow

log = structlog.get_logger()


def removed_ids() -> Select[tuple[str]]:
    """Every automation a removal has ended, by the kind column alone.

    The runner's claim excludes them, so a removed automation whose next run was somehow set again
    still never runs.
    """
    return select(AutomationChangeRow.automation_id).where(AutomationChangeRow.kind == REMOVED)


def changes_of(automation_ids: Iterable[str]) -> Select[tuple[AutomationChangeRow]]:
    """These automations' changes, oldest first."""
    return (
        select(AutomationChangeRow)
        .where(AutomationChangeRow.automation_id.in_(sorted(set(automation_ids))))
        .order_by(AutomationChangeRow.automation_id, AutomationChangeRow.at, AutomationChangeRow.id)
    )


def change_from(row: AutomationChangeRow) -> Change | None:
    """A stored change as the domain's, or None and a log line when it does not construct."""
    try:
        cadence = (
            None
            if row.every is None or row.hour_utc is None
            else Cadence(every=Every(row.every), hour_utc=row.hour_utc, weekday=row.weekday)
        )
        return Change(
            kind=ChangeKind(row.kind),
            at=row.at,
            changed_by=row.changed_by,
            next_run_at=row.next_run_at,
            cadence=cadence,
            runs_as_id=row.runs_as_id,
        )
    except (ValueError, AutomationsError, GalleryError) as exc:
        log.warning(
            "automation change does not construct",
            automation=row.automation_id,
            error=type(exc).__name__,
        )
        return None


async def changes_by_automation(
    session: AsyncSession, automation_ids: Iterable[str]
) -> Mapping[str, tuple[Change, ...]]:
    """Every change of these automations that constructs, by automation, oldest first."""
    ids = tuple(automation_ids)
    if not ids:
        return {}
    found: dict[str, list[Change]] = {one: [] for one in ids}
    for row in (await session.execute(changes_of(ids))).scalars().all():
        change = change_from(row)
        if change is not None:
            found.setdefault(row.automation_id, []).append(change)
    return {key: tuple(value) for key, value in found.items()}


def _recording(*, automation_id: str, agent_id: str, change: Change) -> Any:
    cadence = change.cadence
    return insert(AutomationChangeRow).values(
        automation_id=automation_id,
        agent_id=agent_id,
        kind=change.kind.value,
        next_run_at=change.next_run_at,
        every=None if cadence is None else cadence.every.value,
        weekday=None if cadence is None else cadence.weekday,
        hour_utc=None if cadence is None else cadence.hour_utc,
        runs_as_id=change.runs_as_id,
        changed_by=change.changed_by,
        at=change.at,
    )


async def record_change(
    session: AsyncSession, *, automation_id: str, agent_id: str, change: Change
) -> None:
    """Insert one change in its maker's name, in the caller's transaction; the trigger appends the
    ledger entry.

    The session is told whose change it is here, beside the insert, rather than trusted to have
    been told by whoever opened the transaction: `0145`'s insert policy admits only a row whose
    maker is the session's principal, so a change recorded in anybody else's name is refused.
    """
    await session.execute(
        text("SELECT set_config(:name, :value, true)").bindparams(
            name=PRINCIPAL_SETTING, value=change.changed_by
        )
    )
    await session.execute(_recording(automation_id=automation_id, agent_id=agent_id, change=change))
