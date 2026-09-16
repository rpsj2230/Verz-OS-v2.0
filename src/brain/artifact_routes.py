"""The Artifacts screen over HTTP: what the system produced, what fed it, and how long it is kept.

`brain.console.agent_output` decides what an artifact is, who may know one exists, and how long
it is kept, and `brain.console.govern_estate.artifact_estate` assembles the estate a reader may
see agent by agent. Neither could be reached from a browser. This is the read they sit behind,
and nothing in it decides who may see anything: the route asks `brain.console.reads.permitted`
whether the screen opens, hands the records to `artifact_estate`, and projects what comes back.

**The records are `agent.artifact`, read through a source on `app.state`, and a process with
none says so rather than drawing an empty table.** `brain.ops.artifact_store.StoredArtifacts` is
the one writer, putting the bytes in the object store and the record in the table, and `brain.app`
attaches its reader whenever the process has a database. A process without one has no source,
and an empty list under the heading "artifacts produced" would read as an agent estate that has
produced nothing, which is a statement about the company nobody established. So the answer there
is no list and a sentence. See `NOTHING_HERE_RECORDS_WHAT_AN_AGENT_PRODUCED`, which is
`brain.install_routes.AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE` applied to a second screen.

**An empty list from an attached source is a true statement, and a thin one today.** Every
artifact is recorded through `StoredArtifacts.keep`, so an empty table is an install where nothing
was kept. Nothing in this release's runs calls `keep` yet, which `brain.ops.artifact_store` says
where the call belongs.

The table was built beside the writer, as
`A_TABLE_NOTHING_WRITES_IS_DECIDED_BY_THE_WRONG_AUTHOR` asked, rather than by this screen.

**Retention is on every row and the rule is on the response.** `Artifact.expiry` is
`brain.ops.retention.expires_at` over the class `retention_class_for` chose, so a row says the
date it stops being kept, or the words of a lifetime that is not a clock, and never a dash. The
rule itself is `brain.console.agent_output.AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM`,
sent as written, because it is the one sentence a reader needs to judge any date in the list.

**Provenance is what the record holds about how it was made, and nothing about what fed it.**
The run, the agent version and the person it was produced for travel on the row. The sources and
knowledge items a run drew on do not: `brain.console.agent_output.provenance_for` narrows them to
what this reader can already see, which is two answers this route has no load for, and a panel
showing them unnarrowed is `PROVENANCE_IS_THE_PRODUCERS_REACH_WRITTEN_DOWN`. The entitlement hash
does not travel either: it is provenance for two people comparing what they saw, and a column of
digests on a screen is a column nobody reads until it is quoted wrongly.

**Nothing here computes a reach.** There is no `.intersect(` in this module, and
`brain.console.workspace.intersections_in` is run over this source by its test.

Scope: one read-only route. Nothing here writes, and no download is served: `may_download` is
the question a download would ask, and serving bytes is its own review.

Task ids: M27.7.23
"""

from __future__ import annotations

from collections.abc import Awaitable, Iterable
from typing import Final, Protocol, cast

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from brain.agent_routes import every_agent, record_of, viewer_of
from brain.agents.model import visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.agent_output import (
    AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM,
    ARTIFACTS_SCREEN,
    Artifact,
)
from brain.console.govern_estate import artifact_estate
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent, Failed
from brain.ops.retention import Lifetime, horizon_for
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: The screen this route serves. Bound to the registry so `brain.ops.console_screens` counts it.
THE_SCREEN: Final = ARTIFACTS_SCREEN

# ------------------------------------------------------------------ written-down reasons
#: What the screen answers while nothing attached to this process records an artifact.
#:
#: Written for somebody with a browser and no source tree, which is why it names no module.
NOTHING_HERE_RECORDS_WHAT_AN_AGENT_PRODUCED: Final = (
    "This process has no database attached, so it cannot read the record of what agents "
    "produced, and this page cannot list any. It is not that nothing was produced: it is that "
    "nothing here could look."
)

#: Why the missing record was not built as a table here.
A_TABLE_NOTHING_WRITES_IS_DECIDED_BY_THE_WRONG_AUTHOR: Final = (
    "A table for artifact records created by a screen has no producer writing it, and its schema, "
    "its clock and the store the retention sweep counts it under would all be chosen by the page "
    "that reads it. The bytes it describes have nowhere to go either, because nothing here writes "
    "to the object store. The record is built beside the first thing that produces an artifact, "
    "where what it holds and how long it is kept are one decision."
)

#: What a row says in place of a date when age is not what ends it.
KEPT_WITHOUT_A_CLOCK: Final = {
    Lifetime.WHILE_THE_RECORD_EXISTS: "kept while the record it describes exists",
    Lifetime.FOLLOWS_ITS_SOURCE: "kept for as long as what it was copied from",
    Lifetime.NEVER_EXPIRES: "never expires",
}


class ArtifactSource(Protocol):
    """Every artifact record this install holds, newest first or in any order.

    Read off `app.state` rather than passed, because whether there is one is decided when the
    process starts: `brain.app` attaches `StoredArtifacts.every` over its database. Awaited,
    because the records are rows. `artifact_estate` does the narrowing, so a source hands over
    what is stored and never what it guesses a reader may see.
    """

    def __call__(self) -> Awaitable[Iterable[Artifact]]: ...


def artifact_source_of(request: Request) -> ArtifactSource | None:
    """The record source this process was built with, or None.

    `brain.install_routes.backup_objects_of`'s shape and argument, including the `cast` after a
    `callable` check: a runtime-checkable protocol whose only member is `__call__` admits every
    function, so the attribute's name is what discriminates and the callable check stops a
    string being invoked.
    """
    found = getattr(request.app.state, "artifact_source", None)
    return cast(ArtifactSource, found) if callable(found) else None


# ------------------------------------------------------------------------ the shapes
class ArtifactView(BaseModel):
    """One artifact as the Artifacts screen draws it: what, for whom, when, and until when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    kind: str
    agent_id: str
    #: The person whose question produced it. SCREEN 13's "For" column.
    produced_for: str
    produced_at: str
    state: str
    superseded_by: str
    #: The run that produced it and the exact agent version, which is the provenance a record
    #: holds about itself.
    run_id: str
    agent_version: str
    #: The class it is kept under, decided by its inputs when it was recorded.
    kept_as: str
    #: The instant it stops being kept, or empty when age is not what ends it.
    kept_until: str
    #: The words beside `kept_until`: the window, or why there is no date.
    kept_because: str


class ArtifactsView(BaseModel):
    """The estate a reader may see, or the admission that nothing here records one.

    Exactly one of `artifacts` and `unread` is set, refused here rather than left to whatever
    draws it, for `brain.install_routes.RecoveryView`'s reason. No total and no count of what
    `artifact_estate` withheld: the list is the answer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifacts: list[ArtifactView] | None = None
    unread: str = ""
    #: How an artifact's window is chosen. Sent whatever the list holds.
    kept_rule: str

    @model_validator(mode="after")
    def _exactly_one(self) -> ArtifactsView:
        if (self.artifacts is None) == (not self.unread):
            msg = (
                "an artifacts answer must carry a list or a reason for having none, and never "
                "both: an empty list reads as an estate that produced nothing"
            )
            raise ValueError(msg)
        return self


def artifact_view(one: Artifact) -> ArtifactView:
    """One record, copied field by field, with its retention read off the class it carries."""
    horizon = horizon_for(one.data_class)
    until = one.expiry()
    if until is None:
        because = KEPT_WITHOUT_A_CLOCK.get(horizon.lifetime, horizon.lifetime.value)
    else:
        because = f"kept {horizon.days} days from when it was produced"
    return ArtifactView(
        artifact_id=one.artifact_id,
        kind=one.kind.value,
        agent_id=one.agent_id,
        produced_for=one.caller_id,
        produced_at=one.at.isoformat(),
        state=one.state.value,
        superseded_by=one.superseded_by,
        run_id=one.run_id,
        agent_version=one.agent_version,
        kept_as=one.data_class.value,
        kept_until="" if until is None else until.isoformat(),
        kept_because=because,
    )


# ------------------------------------------------------------------------ the route
def _not_answerable() -> Absent:
    """The refusal the screen makes to a caller who may not open it. Names no row."""
    return Absent(f"the {THE_SCREEN} screen is not answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/artifacts", response_model=ArtifactsView, responses=COMMON_RESPONSES)
async def artifacts(request: Request, asked: Asked) -> ArtifactsView:
    """What was produced across the estate, as this reader may see it, or why nothing is listed.

    The screen's question first, before the source is looked for, so a caller who may not open
    the screen is refused identically whether or not anything is attached. Then the records, the
    agents the reader's audience admits, and `artifact_estate`, which drops what has aged out and
    what this reader holds nothing for before anything is listed.
    """
    if not permitted(screen(THE_SCREEN).read, asked.reach, asked.now):
        log.info("artifacts screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()

    source = artifact_source_of(request)
    if source is None:
        return ArtifactsView(
            unread=NOTHING_HERE_RECORDS_WHAT_AN_AGENT_PRODUCED,
            kept_rule=AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM,
        )

    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    session: AsyncSession
    async with factory() as session:
        rows = (await session.execute(every_agent())).scalars().all()
    records = [one for one in (record_of(row) for row in rows) if one is not None]
    shown = artifact_estate(
        tuple(await source()),
        asked.reach,
        asked.now,
        visible_agents=visible_agent_ids(records, viewer_of(asked)),
    )
    return ArtifactsView(
        artifacts=[artifact_view(one) for one in shown],
        kept_rule=AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM,
    )
