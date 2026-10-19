"""Where a template version's withdrawal is kept: `agent.template_withdrawal`, written as a new row.

`brain.agents.template_withdrawal` decides what a withdrawal is and `migrations/versions/
0261_template_withdrawal.py` argues the table. This holds the SQL between them and decides nothing,
which is the split CLAUDE.md names: nothing that decides policy owns a client.

**One transaction per write, and the ledger entry is the trigger's.** The session's principal, the
request's trace and the writer's reach are set as transaction-local settings first, because the
insert policy reads the first and the trigger the other two, and then the row is inserted. The
entry commits with the row or not at all, and a write that is refused leaves neither.

**The state is the newest row per version, read with `DISTINCT ON`**, as `brain.ops.skill_store`
reads a retirement and for the same reason: a column to say "currently withdrawn" is an update, and
this table is granted none. A version with no row was never withdrawn and is absent from the answer.

**A change is read, decided and written in one transaction under an advisory lock on the version.**
`agent.template_version` is granted SELECT and INSERT and nothing else, so its row cannot be locked
for update (`FOR UPDATE` asks for the privilege), and a lock of this table's own would be a lock on
a row not yet written. The version's name is hashed into one transaction-scoped advisory lock
instead, the newest row is read inside it and `brain.agents.template_withdrawal.withdrawing` is
asked of that row, so two administrators withdrawing one version write one row and the second is
told it is already withdrawn.

**An imported version is the same insert every publication is**, `agent.template_version` through
`brain.agents.install_store.version_values`, in the importer's name, so the publication entry `0104`
records names the person who imported it. It says `ON CONFLICT DO NOTHING` on the version's key and
returns what it wrote, so two presses of one Import write one row.

Task ids: M27.15.35
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Select, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.install_store import version_values
from brain.agents.template import SignedManifest
from brain.agents.template_withdrawal import (
    Withdrawal,
    fully_withdrawn,
    withdrawing,
    withdrawn_keys,
)
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.audit import attributed_to
from brain.tables.template import TemplateVersionRow
from brain.tables.template_withdrawal import TemplateWithdrawalRow


def newest_rows(template_id: str | None = None) -> Select[tuple[TemplateWithdrawalRow]]:
    """The newest row for each version, or for each version of one template. `DISTINCT ON` keeps
    the first of each, which `seq` descending makes the latest."""
    query = select(TemplateWithdrawalRow)
    if template_id is not None:
        query = query.where(TemplateWithdrawalRow.template_id == template_id)
    return query.order_by(
        TemplateWithdrawalRow.template_id,
        TemplateWithdrawalRow.version,
        TemplateWithdrawalRow.seq.desc(),
    ).distinct(TemplateWithdrawalRow.template_id, TemplateWithdrawalRow.version)


def withdrawal_of(row: TemplateWithdrawalRow) -> Withdrawal:
    """One row as the value the domain decides over."""
    return Withdrawal(
        template_id=row.template_id,
        version=row.version,
        withdrawn=row.withdrawn,
        set_by=row.set_by,
        at=row.created_at,
        reason=row.reason or "",
    )


async def newest_in(
    session: AsyncSession, template_id: str | None = None
) -> Mapping[tuple[str, int], Withdrawal]:
    """The newest change of each version in this session, keyed by template id and version.

    Asked inside the session a route already holds, so the gallery's list and the withdrawn
    versions it leaves out are read in one transaction and cannot disagree with each other.
    """
    rows = (await session.execute(newest_rows(template_id))).scalars().all()
    return {(one.template_id, one.version): withdrawal_of(one) for one in rows}


async def on_file_in(session: AsyncSession) -> Sequence[tuple[str, int]]:
    """Every published version's template id and number. Names only, never a document."""
    found = await session.execute(
        select(TemplateVersionRow.template_id, TemplateVersionRow.version)
    )
    return [(str(one), int(number)) for one, number in found.all()]


async def withheld_in(session: AsyncSession) -> tuple[frozenset[tuple[str, int]], frozenset[str]]:
    """What a gallery leaves out in this session: the versions withdrawn now, and the template ids
    every stored version of which is withdrawn.

    Two reads and no document, so the gallery's list and what it hides are one transaction's
    answer. See `brain.agents.template_withdrawal.fully_withdrawn` for why the second is wanted.
    """
    gone = withdrawn_keys(await newest_in(session))
    if not gone:
        return gone, frozenset()
    return gone, fully_withdrawn(await on_file_in(session), gone)


class StoredTemplateWithdrawals:
    """`agent.template_withdrawal`, read whole and written as one row a change."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def row_of(self, template_id: str, version: int) -> TemplateVersionRow | None:
        """The published version's own row, or None when nobody published that number."""
        async with self._sessions() as session:
            return (
                await session.execute(
                    select(TemplateVersionRow).where(
                        TemplateVersionRow.template_id == template_id,
                        TemplateVersionRow.version == version,
                    )
                )
            ).scalar_one_or_none()

    async def rows_of(self, template_id: str) -> Sequence[TemplateVersionRow]:
        """Every published version of one template, oldest first."""
        async with self._sessions() as session:
            return (
                (
                    await session.execute(
                        select(TemplateVersionRow)
                        .where(TemplateVersionRow.template_id == template_id)
                        .order_by(TemplateVersionRow.version)
                    )
                )
                .scalars()
                .all()
            )

    async def rows_named(self, keys: Sequence[tuple[str, int]]) -> Sequence[TemplateVersionRow]:
        """The published rows of exactly these versions, for naming what was withdrawn."""
        if not keys:
            return ()
        async with self._sessions() as session:
            return (
                (
                    await session.execute(
                        select(TemplateVersionRow).where(
                            tuple_(TemplateVersionRow.template_id, TemplateVersionRow.version).in_(
                                list(keys)
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )

    async def keep_version(
        self, signed: SignedManifest, *, by: str, ent_hash: str, trace_id: str
    ) -> bool:
        """Write one signed version in the importer's name; False when that number is taken."""
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            written = (
                await session.execute(
                    insert(TemplateVersionRow)
                    .values(**version_values(signed))
                    .on_conflict_do_nothing()
                    .returning(TemplateVersionRow.template_id)
                )
            ).scalar_one_or_none()
        return written is not None

    async def newest(self) -> Mapping[tuple[str, int], Withdrawal]:
        """The newest change of every version that has one."""
        async with self._sessions() as session:
            return await newest_in(session)

    async def history(self, template_id: str, version: int) -> tuple[Withdrawal, ...]:
        """Every change to one version, oldest first. Empty for a version never withdrawn."""
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(TemplateWithdrawalRow)
                        .where(
                            TemplateWithdrawalRow.template_id == template_id,
                            TemplateWithdrawalRow.version == version,
                        )
                        .order_by(TemplateWithdrawalRow.seq)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(withdrawal_of(one) for one in rows)

    async def change(
        self,
        template_id: str,
        version: int,
        *,
        withdraw: bool,
        reason: str,
        by: str,
        ent_hash: str,
        trace_id: str,
    ) -> Withdrawal | None:
        """Withdraw the version or undo the withdrawal, in the setter's name, with its ledger entry.

        None when no such version is published, which a route answers as it answers a version
        that was never there. A change that changes nothing is refused by
        `brain.agents.template_withdrawal.withdrawing`, raised as it is, and nothing is written.
        """
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            await session.execute(_set_config(PRINCIPAL_SETTING, by))
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))").bindparams(
                    name=f"agent.template_withdrawal:{template_id}:{version}"
                )
            )
            published = (
                await session.execute(
                    select(TemplateVersionRow.version).where(
                        TemplateVersionRow.template_id == template_id,
                        TemplateVersionRow.version == version,
                    )
                )
            ).scalar_one_or_none()
            if published is None:
                return None
            current = (await newest_in(session, template_id)).get((template_id, version))
            withdrawing(current, withdraw=withdraw)
            written = (
                await session.execute(
                    insert(TemplateWithdrawalRow)
                    .values(
                        template_id=template_id,
                        version=version,
                        withdrawn=withdraw,
                        reason=reason or None,
                        set_by=by,
                    )
                    .returning(TemplateWithdrawalRow)
                )
            ).scalar_one()
        return withdrawal_of(written)


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.ops.skill_store` sets the same settings.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)
