"""Where the plugin lifecycle's records live: save an install, read them back, remove one.

`brain.plugins.lifecycle` decides every transition and holds no connection, and its package says
so: "Nothing here opens a socket, reads a file, imports a plugin or runs one." That sentence is why
this module is under `brain.ops` beside `brain.ops.schedule_store` rather than under
`brain.plugins`. It re-decides nothing. A record read back is an `Installed`, whose constructor
checks it; a manifest read back goes through `brain.plugins.manifest.manifest_from`, which refuses
a reach key by name; and removal asks `lifecycle.assert_transition` rather than knowing the edge.

**A version this install has run is one document for ever.** `remember` writes a manifest the first
time its version runs and refuses a different document under the same version afterwards. A plugin
author re-publishing 1.2.0 with a changed manifest has published a new version under an old name,
and a registry that accepted it would roll back to 1.2.0 and run something 1.2.0 never was. See
`A_VERSION_THIS_INSTALL_HAS_RUN_IS_ONE_DOCUMENT`.

**A removed plugin is a retired row, and every read here treats it as absent.** `records` leaves it
out, and `save` treats a plugin with a retired row exactly as one with no row: it may only come back
`installed`. The table refuses both the enabled insert and the enabled return; this is the message,
in the lifecycle's words, before the database's.

**What this does not do is load a plugin.** A record here says a plugin is on the install and
whether it is switched on. Loading one is a separate problem with a separate risk, and the
`brain.plugins` package is explicit that everything it holds is a question answered before loading
is even a sensible thing to attempt.

Task ids: M29.2.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.plugins.lifecycle import Installed, PluginState, assert_transition
from brain.plugins.manifest import PluginManifest, manifest_from
from brain.tables.plugin import PluginInstallRow, PluginVersionRow

#: Why a second document under a version already run is refused.
A_VERSION_THIS_INSTALL_HAS_RUN_IS_ONE_DOCUMENT: Final = (
    "A rollback returns to a version this install has run, and the registry is where the "
    "document that ran is kept. If a different manifest could later be stored under the same "
    "version string, the rollback would run that one instead, with its own requirements and "
    "its own configuration, while every record said it had returned to something known."
)


class RegistryError(Exception):
    """A record was asked of the plugin registry that it cannot hold truthfully."""


def installed_from(row: PluginInstallRow) -> Installed:
    """The lifecycle record a stored row holds, through the manifest parser and `Installed`."""
    return Installed(
        manifest=manifest_from(dict(row.manifest)),
        state=PluginState(row.state),
        since=row.since,
        history=tuple(row.history),
    )


async def remember(session: AsyncSession, manifest: PluginManifest) -> None:
    """Keep a manifest as a version this install has run. Refuses a changed document.

    Flushed at once, because the install row points at this one by foreign key and the models
    declare no relationship for the unit of work to order the two inserts by.
    """
    document = manifest.model_dump(mode="json")
    stored = await session.get(PluginVersionRow, (manifest.plugin_id, manifest.version))
    if stored is None:
        session.add(
            PluginVersionRow(
                plugin_id=manifest.plugin_id, version=manifest.version, manifest=document
            )
        )
        await session.flush()
        return
    if stored.manifest != document:
        msg = (
            f"{manifest.plugin_id} {manifest.version} has run here as a different manifest. "
            f"{A_VERSION_THIS_INSTALL_HAS_RUN_IS_ONE_DOCUMENT}"
        )
        raise RegistryError(msg)


async def save(session: AsyncSession, record: Installed) -> None:
    """Write a lifecycle record: its manifest as a version run, and its current state.

    Does not commit. An upgrade is a manifest remembered and a record moved, and both belong to one
    transaction.
    """
    await remember(session, record.manifest)
    plugin_id = record.manifest.plugin_id
    document = record.manifest.model_dump(mode="json")
    stored = await session.get(PluginInstallRow, plugin_id)
    absent = stored is None or stored.removed_at is not None
    if absent and record.state is not PluginState.INSTALLED:
        msg = (
            f"{plugin_id} is not on this install and is being written as {record.state}; a "
            "plugin arrives installed and is enabled by a separate act, because there is no "
            "transition from absent to anything else"
        )
        raise RegistryError(msg)
    if stored is None:
        session.add(
            PluginInstallRow(
                plugin_id=plugin_id,
                version=record.manifest.version,
                point=record.manifest.point,
                state=record.state.value,
                since=record.since,
                history=list(record.history),
                manifest=document,
            )
        )
    else:
        stored.version = record.manifest.version
        stored.point = record.manifest.point
        stored.state = record.state.value
        stored.since = record.since
        stored.history = list(record.history)
        stored.manifest = document
        stored.removed_at = None
    await session.flush()


async def records(session: AsyncSession) -> dict[str, Installed]:
    """Every plugin on this install, keyed by id. The mapping `lifecycle.state_of` reads.

    A removed plugin is absent, so its retired row is left out rather than read as disabled.
    """
    found = await session.execute(
        select(PluginInstallRow)
        .where(PluginInstallRow.removed_at.is_(None))
        .order_by(PluginInstallRow.plugin_id)
    )
    return {row.plugin_id: installed_from(row) for row in found.scalars().all()}


async def manifest_for(
    session: AsyncSession, plugin_id: str, version: str
) -> PluginManifest | None:
    """The document a version ran as, or None when this install never ran it.

    This is what `lifecycle.rollback` is handed. None is the honest answer for a version this
    install has not run, and the rollback refuses it for the reason it gives.
    """
    stored = await session.get(PluginVersionRow, (plugin_id, version))
    return None if stored is None else manifest_from(dict(stored.manifest))


async def remove(session: AsyncSession, plugin_id: str, *, at: datetime) -> None:
    """Take a plugin off the install. Only from `disabled`, as the lifecycle says.

    The transition is asked of `lifecycle.assert_transition` rather than written here as a state
    comparison, so this cannot come to disagree with the table the lifecycle holds. The row is
    retired rather than deleted, and the versions the plugin ran are kept.
    """
    stored = await session.get(PluginInstallRow, plugin_id)
    if stored is None or stored.removed_at is not None:
        msg = f"{plugin_id} is not on this install, so there is nothing to remove"
        raise RegistryError(msg)
    assert_transition(PluginState(stored.state), PluginState.ABSENT)
    stored.removed_at = at
    await session.flush()
