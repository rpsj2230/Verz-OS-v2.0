"""What a member may see of their own account: devices, who read their record, what agents made
for them, and what is held about them.

Four reads and one write for the person asking, each over `brain.member_activity`,
`brain.member_library` and `brain.ops.retention`, which decided what they say and had no caller.
**Every route takes no parameter naming a person**: the principal is the one the token resolved,
so there is no request that asks about somebody else, and each is gated on the member grant
(`brain.member.shell`), which no administrative screen shares. DENIED and ABSENT are one answer:
a caller without the grant gets the page's one refusal.

**Devices** (M40.1.1.3) are the person's own live sessions, read narrowed by the person in the
statement. Ending one is `StoredSessions.end` with `may` asking that the session is theirs, so
somebody else's session id, an ended one and one that does not exist are one refusal, and the
control cannot be used to find out whether a session id is real.

**Who read my record** (M40.4.2.4) is the ledger's `record_read` entries filed under the person,
through `member_activity.who_read_my_record`, which narrows the input before the view builds its
page. A read of a record is shown as who, when, through which agent and what kind of record, and
never what was shown. No total is given.

**What agents made for me** (M40.3.3.1) is `member_library.produced_for_me` over every artifact
record, so only rows made for the person and still inside their retention are listed.

**What is held about me** (M40.4.2.1) says, store by store, what each holds and what a deletion
does there, from `brain.ops.retention` and `brain.ops.erasure.disposition_of`, which iterate every
store, so a store left out is a finding. **It carries no counts.** A count needs the worker's own
login, which can read past the row policies a request runs under; a figure from a request would be
either that privilege or a guess, so the page says what is held and where and leaves the figures to
the erasure queue's own report.

Task ids: M40.1.1.3, M40.4.2.4, M40.3.3.1, M40.4.2.1
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES, bound_trace_id
from brain.api_routes import Asked
from brain.artifact_routes import ArtifactView, artifact_source_of, artifact_view
from brain.audit.ledger import AuditAction
from brain.audit.view import AuditFilter
from brain.audit_routes import entry_from, ledger_of
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.identity.session_store import StoredSession, StoredSessions
from brain.member.shell import member_screen
from brain.member_activity import MY_READS_SUBJECT_KIND, who_read_my_record
from brain.member_library import produced_for_me
from brain.mine_routes import MEMBER_HOME
from brain.ops.erasure import disposition_of
from brain.ops.retention import Store, facts_for
from brain.routing_routes import sessions_of

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

#: How many of a person's own devices, reads and artifacts one answer carries. Past it the answer
#: says there are more and never how many.
MOST_ROWS: Final = 100

#: What the page says about the figures it does not show.
NO_FIGURES_HERE: Final = (
    "This says what is kept about you and what a deletion does in each place. It does not count "
    "what is there: a count is made by the deletion queue's own report, which can read past the "
    "limits a page runs under."
)


def _not_answerable() -> Absent:
    """The one refusal these pages make. Names the page and never a row."""
    return Absent("your account is not answerable for this caller")


def _guard(asked: Asked) -> None:
    """The member grant first, as My workspace asks it, so a refusal is the same everywhere."""
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("own account not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()


def _sessions(request: Request) -> StoredSessions:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredSessions(factory)


# ----------------------------------------------------------------------------- devices
class MyDeviceView(BaseModel):
    """One live sign-in as this person: when it began, when it ends, whether it is this one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    channel: str
    second_factor: bool
    started_at: datetime
    expires_at: datetime
    is_this_one: bool


class MyDevicesView(BaseModel):
    """This person's live sign-ins, newest first, and whether there are more than are listed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    devices: list[MyDeviceView]
    more: bool = False


class MyDeviceEnding(BaseModel):
    """Which of this person's own sign-ins to end."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1, max_length=200, pattern=r"^\S+$")


class MyDeviceEnded(BaseModel):
    """That the sign-in is ended, and when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    ended_at: datetime


def device_view(one: StoredSession, current: str) -> MyDeviceView:
    """One stored session as the person reads it."""
    return MyDeviceView(
        session_id=one.session_id,
        channel=one.channel,
        second_factor=one.second_factor,
        started_at=one.started_at,
        expires_at=one.expires_at,
        is_this_one=one.session_id == current,
    )


@router.get("/me/devices", response_model=MyDevicesView, responses=COMMON_RESPONSES)
async def my_devices(request: Request, asked: Asked) -> MyDevicesView:
    """Every sign-in this person has open, newest first (M40.1.1.3)."""
    _guard(asked)
    found, full = await _sessions(request).open_sessions_of(
        asked.caller.principal.id, now=asked.now, limit=MOST_ROWS
    )
    current = asked.caller.claims.session_id or ""
    return MyDevicesView(devices=[device_view(one, current) for one in found], more=full)


@router.post("/me/devices/end", response_model=MyDeviceEnded, responses=COMMON_RESPONSES)
async def end_my_device(request: Request, body: MyDeviceEnding, asked: Asked) -> MyDeviceEnded:
    """End one of this person's own sign-ins, or refuse without saying why (M40.1.1.3).

    Somebody else's session, one already ended and one that never existed are the one refusal.
    """
    _guard(asked)
    me = asked.caller.principal.id
    ended = await _sessions(request).end(
        body.session_id,
        may=lambda one: one.principal_id == me,
        ended_by=me,
        ent_hash=asked.reach.ent_hash(),
        trace_id=bound_trace_id(request),
        now=asked.now,
    )
    if ended is None:
        log.info("own device not answerable", principal=me)
        raise _not_answerable()
    return MyDeviceEnded(session_id=ended.session_id, ended_at=ended.ended_at)


# ------------------------------------------------------------------------------- reads
class MyReadView(BaseModel):
    """One read of this person's record: who, when, through which agent, and what kind."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    actor_id: str
    agent_id: str
    record_kind: str


class MyReadsView(BaseModel):
    """The reads of this person's record, oldest first. No total, and what was shown is not here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reads: list[MyReadView]
    more: bool = False


@router.get("/me/reads", response_model=MyReadsView, responses=COMMON_RESPONSES)
async def my_reads(request: Request, asked: Asked) -> MyReadsView:
    """Who has read this person's own record, and through which agent (M40.4.2.4)."""
    _guard(asked)
    me = asked.caller.principal.id
    rows = await ledger_of(request).window(
        AuditFilter(
            actions=frozenset({AuditAction.RECORD_READ}),
            subject_kinds=frozenset({MY_READS_SUBJECT_KIND}),
        ),
        subject=f"{MY_READS_SUBJECT_KIND}:{me}",
        position=None,
        newest_first=False,
        limit=MOST_ROWS,
    )
    entries = [one for one in (entry_from(row) for row in rows) if one is not None]
    page = who_read_my_record(
        entries, principal_id=me, reader=asked.reach, now=asked.now, limit=MOST_ROWS
    )
    return MyReadsView(
        reads=[
            MyReadView(
                at=one.at, actor_id=one.actor_id, agent_id=one.agent_id, record_kind=one.record_kind
            )
            for one in page.reads
        ],
        more=page.next_cursor is not None or len(rows) >= MOST_ROWS,
    )


# -------------------------------------------------------------------------- artifacts
class MyArtifactsView(BaseModel):
    """Everything any agent produced for this person, newest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifacts: list[ArtifactView]
    more: bool = False


@router.get("/me/artifacts", response_model=MyArtifactsView, responses=COMMON_RESPONSES)
async def my_artifacts(request: Request, asked: Asked) -> MyArtifactsView:
    """What agents made for this person, from every agent and nobody else's (M40.3.3.1)."""
    _guard(asked)
    source = artifact_source_of(request)
    if source is None:
        return MyArtifactsView(artifacts=[])
    mine = produced_for_me(
        tuple(await source()),
        principal_id=asked.caller.principal.id,
        reader=asked.reach,
        now=asked.now,
    )
    return MyArtifactsView(
        artifacts=[artifact_view(one) for one in mine[:MOST_ROWS]], more=len(mine) > MOST_ROWS
    )


# ---------------------------------------------------------------------------- stored
class MyStoredView(BaseModel):
    """One place data about this person is kept, in plain words, and what a deletion does there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    store: str
    holds: str
    deletion: str


class MyStoredPage(BaseModel):
    """Every place data about this person rests, and the sentence about figures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stores: list[MyStoredView]
    told: str


@router.get("/me/stored", response_model=MyStoredPage, responses=COMMON_RESPONSES)
async def my_stored(asked: Asked) -> MyStoredPage:
    """What is kept about this person and where, store by store, in plain words (M40.4.2.1)."""
    _guard(asked)
    return MyStoredPage(
        stores=[
            MyStoredView(
                store=one.value, holds=facts_for(one).holds, deletion=disposition_of(one).value
            )
            for one in Store
        ],
        told=NO_FIGURES_HERE,
    )
