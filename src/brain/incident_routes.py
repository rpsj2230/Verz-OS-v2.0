"""The Incidents screen over HTTP: which connected sources are degraded now, since when, and which
tools stop working because of it.

`brain.console.operate.incidents` decided all of this on 2026-09-15 and nothing called it: the
screen was registered (`brain.console.screens`' `incidents`, `read:incident` at the configuration
plane), its panel was declared, and there was no route and no page, so an administrator whose
source went down had no screen saying what that took with it. This is the route, and it decides
nothing `operate.incidents` already decides.

**What is degraded is what the worker last found.** `brain.ops.connector_sync_store.
StoredSyncStates` holds the newest attempt per connection with the health it left, which is what
the Connectors screen shows beside each source, so this screen and that one cannot disagree about
whether a source is down. Only `DEGRADED` and `DOWN` are incidents. `UNCONFIGURED` is a source
nobody finished setting up, which `brain.connectors.contract.HealthState` argues goes to a
different person, and a screen counting it would be amber for the whole of every rollout. See
`AN_UNFINISHED_SOURCE_IS_A_TASK_AND_NOT_AN_INCIDENT`.

**Which sources a reader is told of is the Connectors screen's rule, called rather than restated.**
`brain.console.connector_trust.admitted_connections` narrows the connections, and
`operate.incidents` narrows again by the same names, so a source the reader may not be told exists
produces no row, no blocked tool and no count. A degraded source this release cannot rebuild the
declaration of is still listed, with what it blocks said as unknown rather than as nothing, because
an empty blocked list beside a down source reads as a harmless incident. See
`A_DOWN_SOURCE_WHOSE_TOOLS_CANNOT_BE_NAMED_IS_STILL_DOWN`.

**A process with no database answers a sentence and never an empty list**, for
`brain.install_routes.AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE`: "nothing is degraded" is the
reassuring answer, and it would be given by a process that looked at nothing.

Task ids: M27.2.7
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, model_validator

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.connector_routes import records_of, sync_records_of
from brain.connectors.contract import ConnectorContractError, HealthState
from brain.connectors.manifest import ConnectorManifest
from brain.console.connector_trust import admitted_connections
from brain.console.operate import incidents
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent
from brain.ops.connectable import NotConnectableError, manifest_for

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a source nobody finished setting up is not listed.
AN_UNFINISHED_SOURCE_IS_A_TASK_AND_NOT_AN_INCIDENT: Final = (
    "A source whose last attempt found it unconfigured is one nobody finished setting up, which is "
    "a task for whoever connected it. Counting it as an incident would keep this screen amber for "
    "the whole of every rollout, and a screen that is always amber is not read."
)

#: Why a down source whose tools cannot be named is listed anyway.
A_DOWN_SOURCE_WHOSE_TOOLS_CANNOT_BE_NAMED_IS_STILL_DOWN: Final = (
    "A degraded source this release cannot rebuild the declaration of is still degraded. It is "
    "listed with what it blocks said as unknown, because an empty list of blocked tools beside a "
    "source that is down reads as an incident that stops nothing."
)

# ------------------------------------------------------------------------ the figures
#: The screen this route answers, as `brain.console.screens` registers it.
INCIDENTS_SCREEN: Final = "incidents"

#: Where the screen is read.
INCIDENTS_PATH: Final = "/console/incidents"

#: The healths that are an incident. See `AN_UNFINISHED_SOURCE_IS_A_TASK_AND_NOT_AN_INCIDENT`.
INCIDENT_HEALTHS: Final = frozenset({HealthState.DEGRADED, HealthState.DOWN})

#: Said in place of the list on a process with no database.
NOTHING_HERE_READS_THE_ATTEMPTS: Final = (
    "This process has no database, so it cannot read what the worker last found when it read each "
    "source. Nothing on this screen is a statement that every source is working."
)

#: Said in place of what a source blocks when its declaration cannot be rebuilt.
WHAT_IT_BLOCKS_IS_NOT_KNOWN: Final = (
    "What this source blocks cannot be named: this release cannot rebuild what it was connected "
    "as. Its own page on the Connectors screen says more."
)

#: What the screen says about where its list comes from, whatever it holds.
WHERE_THIS_COMES_FROM: Final = (
    "Each source is listed as the worker last found it when it read the source. A source that was "
    "never set up properly is not listed here; the Connectors screen shows it."
)


# ------------------------------------------------------------------------ the shapes
class IncidentView(BaseModel):
    """One source that is degraded now, and what stops working because of it.

    `blocks` is empty exactly when `blocks_unknown` says why, refused here, so a renderer is never
    handed a down source with nothing beside it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    #: What the worker's last attempt found: `degraded` or `down`.
    state: str
    since: datetime
    #: The tools that stop working, in the order the source declares them.
    blocks: list[str]
    blocks_unknown: str = ""

    @model_validator(mode="after")
    def _blocks_or_why_not(self) -> IncidentView:
        if bool(self.blocks) == bool(self.blocks_unknown):
            msg = "an incident names what it blocks or says why it cannot, never both or neither"
            raise ValueError(msg)
        return self


class IncidentsView(BaseModel):
    """The Incidents screen: what is degraded now, or why nothing here could look."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[IncidentView]
    #: Why there is no list, on a process that cannot read the attempts. Empty otherwise.
    unread: str = ""
    told: str = WHERE_THIS_COMES_FROM


# ------------------------------------------------------------------------- the route
router = APIRouter(prefix=API_PREFIX, tags=["operate"])


@router.get(INCIDENTS_PATH, response_model=IncidentsView, responses=COMMON_RESPONSES)
async def incidents_screen(request: Request, asked: Asked) -> IncidentsView:
    """Every source this reader may be told of that is degraded now, with what it blocks.

    The screen's read first, then the connections, then the worker's attempts for the connections
    this reader may be told of and no others.
    """
    if not permitted(screen(INCIDENTS_SCREEN).read, asked.reach, asked.now):
        log.info("incidents not answerable", principal=asked.caller.principal.id)
        raise Absent(f"the {INCIDENTS_SCREEN} screen is not answerable for this caller")
    records = records_of(request)
    if records is None:
        return IncidentsView(items=[], unread=NOTHING_HERE_READS_THE_ATTEMPTS)
    shown = admitted_connections(await records.connected(), asked.reach, asked.now)
    sync = sync_records_of(request)
    synced = {} if sync is None or not shown else await sync.states()
    named: list[tuple[ConnectorManifest, str, datetime]] = []
    unnamed: list[IncidentView] = []
    for one in shown:
        state = synced.get(one.connector)
        if state is None or state.health not in INCIDENT_HEALTHS:
            continue
        try:
            manifest = manifest_for(one.connector, one.settings)
        except (NotConnectableError, ConnectorContractError):
            unnamed.append(
                IncidentView(
                    subject=one.connector,
                    state=state.health.value,
                    since=state.finished_at,
                    blocks=[],
                    blocks_unknown=WHAT_IT_BLOCKS_IS_NOT_KNOWN,
                )
            )
            continue
        named.append((manifest, state.health.value, state.finished_at))
    found = incidents(named, [one.connector for one in shown])
    return IncidentsView(
        items=[
            *(
                IncidentView(
                    subject=one.subject,
                    state=one.state,
                    since=one.since,
                    blocks=list(one.blocks),
                    blocks_unknown="" if one.blocks else WHAT_IT_BLOCKS_IS_NOT_KNOWN,
                )
                for one in found
            ),
            *unnamed,
        ]
    )
