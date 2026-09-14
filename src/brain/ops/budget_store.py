"""Where every budget version lives: read a ceiling's history, and append its next version.

`brain.ops.budgets` decides what a version is and what order versions may come in, and holds no
connection, for the reason `brain.ops.limits` gives about the same split. `brain.ops.spend` is the
enforcement half and holds no rows. This is the half that talks to PostgreSQL, and it re-decides
nothing: a history read back is a `BudgetHistory`, whose constructor is the ordering rule, and a
version appended is a `BudgetRow` somebody else produced, usually through `superseded_by`.

**There is no update and no delete here, and not because nobody wrote them.** The table refuses
both for every role. A store offering `set_ceiling` would be a function whose every call raises, or
worse, a function somebody rewrites to append behind a name that says edit. The only verb is
`append`, and it is the only verb the table has.

**`append` builds the history it is about to create before it writes.** Read the ceiling's versions,
put the new one on the end, and construct `BudgetHistory` over the lot: a version that does not
go forwards or takes effect no later than the last is refused in the domain's words, before the
database's trigger refuses it in its own. The trigger is still the rule. This is the message, and
without it a mistake reaches a person as a PostgreSQL exception about a function name.

**An absent history is None, and None is not an unlimited budget.** `BudgetHistory.in_force_at`
makes that argument about an instant before the first version; this is the same argument about a
ceiling nobody has written. What an absent ceiling means is the caller's decision, and there is
nothing here that could make it for them.

Rejected: caching the current version of every ceiling in process memory. It is the obvious speed-up
and it is a second place the answer to "what was the ceiling" lives, which is the question this
table exists to answer once. `brain.ops.spend` asks per request, and a ceiling changed by a transfer
would be enforced at its old figure by every replica that had not noticed.

Task ids: M21.1.5
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.budgets import BudgetHistory, BudgetKey, BudgetLevel, BudgetPeriod, BudgetRow
from brain.tables.budget import BudgetVersionRow


def row_from(stored: BudgetVersionRow) -> BudgetRow:
    """The domain row a stored version holds, through `BudgetRow`'s own checks."""
    return BudgetRow(
        level=BudgetLevel(stored.level),
        subject=stored.subject,
        period=BudgetPeriod(stored.period),
        ceiling_minor=stored.ceiling_minor,
        version=stored.version,
        author=stored.author,
        effective_from=stored.effective_from,
        reason=stored.reason,
        alert_fractions=tuple(stored.alert_fractions),
    )


async def history_of(session: AsyncSession, key: BudgetKey) -> BudgetHistory | None:
    """Every version of one ceiling, oldest first, or None when none has ever been written."""
    level, subject, period = key
    found = await session.execute(
        select(BudgetVersionRow)
        .where(
            BudgetVersionRow.level == level.value,
            BudgetVersionRow.subject == subject,
            BudgetVersionRow.period == period.value,
        )
        .order_by(BudgetVersionRow.version)
    )
    rows = tuple(row_from(one) for one in found.scalars().all())
    return BudgetHistory(rows=rows) if rows else None


async def in_force(session: AsyncSession, key: BudgetKey, at: datetime) -> BudgetRow | None:
    """The version that governed that ceiling at that instant, or None when none did."""
    history = await history_of(session, key)
    return None if history is None else history.in_force_at(at)


async def append(session: AsyncSession, row: BudgetRow) -> BudgetHistory:
    """Append the next version of a ceiling, and answer with the history as it now stands.

    Does not commit. A transfer moves two ceilings and both versions have to land together, which
    is only true if the caller commits once after appending both.
    """
    existing = await history_of(session, row.key)
    history = BudgetHistory(rows=(row,) if existing is None else (*existing.rows, row))
    session.add(
        BudgetVersionRow(
            level=row.level.value,
            subject=row.subject,
            period=row.period.value,
            ceiling_minor=row.ceiling_minor,
            version=row.version,
            author=row.author,
            effective_from=row.effective_from,
            reason=row.reason,
            alert_fractions=list(row.alert_fractions),
        )
    )
    await session.flush()
    return history
