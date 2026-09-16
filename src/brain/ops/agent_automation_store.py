"""Where an installed automation is kept: one row in `agent.automation`, written in one statement.

`brain.console.automation_gallery` decides what an install is and whether it was confirmed, and
`migrations/versions/0055_agent_automation.py` argues the table, its policies and its trigger. This
module holds the SQL between them and decides nothing, which is the split CLAUDE.md names: nothing
that decides policy owns a client.

**One transaction, and the ledger entry is the trigger's.** The session's principal, the request's
trace and the installer's reach are set as transaction-local settings first, because `0055`'s
policies read the first and its trigger reads the other two, and then the row is inserted. The
trigger appends the `compose_change` entry inside the same transaction, so the automation, its
registry entry and its audit entry commit together or not at all.

**A second install is answered by the constraint and never by a read first.** The insert says
`ON CONFLICT DO NOTHING` over the three columns the unique constraint names, and returns the id it
wrote. No id back means the row was already there, and only then is the existing id read, in the
same transaction. A read before the write was rejected because two presses of one button race, and
the read in each would find nothing. PostgreSQL fires no row trigger for a row it did not insert,
so the second press appends nothing to the ledger either.

**The registry entry is read back out of the row it was written into.** `entry_of` rebuilds
`brain.console.agent_automations.RegistryEntry` from the columns, and a test holds it equal to the
entry the installation carried, which is the one-row argument in `brain.tables.agent_automation`
checked rather than asserted.

Task ids: M39.6.1.3
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert

from brain.console.agent_automations import RegistryEntry
from brain.console.automation_gallery import Installation
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.agent_automation import AgentAutomationRow
from brain.tables.audit import ENT_HASH_SETTING, TRACE_ID_SETTING

#: The columns the unique constraint names, in its order. One install per agent, template and
#: person; see `brain.console.automation_gallery.INSTALLING_TWICE_IS_ANSWERED_WITH_THE_FIRST`.
ONE_INSTALL: tuple[str, str, str] = ("agent_id", "template_id", "runs_as_id")


@dataclass(frozen=True)
class Installed:
    """What an install did: the automation's id, and whether this request wrote it."""

    automation_id: str
    #: False when the automation was already there and nothing was written.
    created: bool


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.ops.credential_write_store` sets the same settings.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def row_values(installation: Installation) -> dict[str, Any]:
    """What an install writes. The automation's columns and the registry entry's sentence."""
    automation = installation.automation
    return {
        "automation_id": automation.automation_id,
        "agent_id": automation.agent_id,
        "name": automation.name,
        "runs_as_id": automation.runs_as.id,
        "task": automation.task,
        "next_run_at": automation.next_run_at,
        "guards": installation.entry.guards,
        "template_id": installation.template_id,
        "template_version": installation.template_version,
        "installed_by": installation.installed_by,
    }


def entry_of(row: Mapping[str, Any]) -> RegistryEntry:
    """The registry entry a stored row is, read off its columns."""
    return RegistryEntry(
        automation_id=row["automation_id"],
        agent_id=row["agent_id"],
        task=row["task"],
        runs_as_id=row["runs_as_id"],
        next_run_at=row["next_run_at"],
        guards=row["guards"],
    )


def installing(installation: Installation) -> ReturningInsert[tuple[str]]:
    """The insert, which writes nothing and returns nothing when the install already exists."""
    return (
        insert(AgentAutomationRow)
        .values(**row_values(installation))
        .on_conflict_do_nothing(index_elements=list(ONE_INSTALL))
        .returning(AgentAutomationRow.automation_id)
    )


def already_installed(installation: Installation) -> Select[tuple[str]]:
    """The id of the automation that stopped this install, by the constraint's three columns."""
    automation = installation.automation
    return select(AgentAutomationRow.automation_id).where(
        AgentAutomationRow.agent_id == automation.agent_id,
        AgentAutomationRow.template_id == installation.template_id,
        AgentAutomationRow.runs_as_id == automation.runs_as.id,
    )


def installed_from(agent_id: str, principal_id: str) -> Select[tuple[str, str]]:
    """This person's automations on this agent, by the template each was installed from."""
    return select(AgentAutomationRow.template_id, AgentAutomationRow.automation_id).where(
        AgentAutomationRow.agent_id == agent_id,
        AgentAutomationRow.runs_as_id == principal_id,
    )


class StoredAgentAutomations:
    """`brain.automation_gallery_routes.AutomationInstalls` over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def installed_by(self, agent_id: str, principal_id: str) -> Mapping[str, str]:
        """Template id to automation id, for this person's automations on this agent."""
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
            rows = (await session.execute(installed_from(agent_id, principal_id))).all()
        return {str(template_id): str(automation_id) for template_id, automation_id in rows}

    async def install(
        self, installation: Installation, *, ent_hash: str, trace_id: str
    ) -> Installed:
        """Write the automation and its registry entry, or say which automation is already there."""
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, installation.installed_by))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            written = (await session.execute(installing(installation))).scalar_one_or_none()
            if written is not None:
                return Installed(automation_id=str(written), created=True)
            existing = (await session.execute(already_installed(installation))).scalar_one()
        return Installed(automation_id=str(existing), created=False)
