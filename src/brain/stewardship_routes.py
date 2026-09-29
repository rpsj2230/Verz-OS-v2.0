"""What the signed-in person is told as a steward: every grant somebody made to themselves that
reaches a document, source or agent they answer for (M7.7.2).

`GET /stewardship/self-grants` answers for the caller alone. It reads the grants people made to
themselves in `brain.identity.stewardship.NOTICE_WINDOW`, the things the caller stewards, and hands
both to `brain.identity.stewardship.notices_for`, which decides which grants reach which of the
caller's things. The Access requests page draws the list, beside the requests people sent to the
caller, because both are the caller being told about access to what they own.

**No route here takes a person.** A steward's list is theirs, for the reason
`brain.thread_routes.A_HISTORY_IS_ONLY_EVER_THE_CALLERS` gives about a history: a route that named
whose list to read would be a way to read somebody else's. A caller who stewards nothing, or whose
things nobody granted themselves access to, is answered with an empty list and nothing else, so
the answer says nothing about what anybody else stewards or granted.

**The things are read at the caller's own reach.** A document the caller stewards but can no longer
read is left out, because the lifecycle store reads documents as the caller, and a source or agent
is listed only while it is connected or not archived. A notice about something the caller cannot
see would name it to them.

**What a notice names.** The person, when, the capabilities as they were granted and the pack they
came in, and the caller's own things the grant reaches. Never the scope in full, which may name
departments the caller cannot see, and never another steward's things. See
`brain.identity.stewardship.A_NOTICE_NAMES_ONLY_WHAT_ITS_READER_STEWARDS`.

Task ids: M7.7.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.agent_routes import record_of, steward_names
from brain.agents.creation import AGENT_INSTALL_CAPABILITY
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.connector_routes import manifest_or_none, records_of, steward_of, stewardship_of
from brain.connectors.declaration import shipped
from brain.connectors.registry import INSTALL_AUTHORITY
from brain.core.entitlement import Capability
from brain.core.errors import Failed
from brain.identity.data_steward import declared_capabilities
from brain.identity.stewardship import (
    INVOKE_AGENT,
    NOTICE_WINDOW,
    Stewarded,
    StewardedKind,
    StewardNotice,
    notices_for,
)
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge_lifecycle_routes import authority_of
from brain.ops.connector_admin import SOURCE_FIELD
from brain.ops.stewardship_store import StoredStewardship
from brain.prompt_routes import INSTRUCTIONS_AUTHORITY, agent_scope_row
from brain.routing_routes import sessions_of

SELF_GRANTS_PATH: Final = "/stewardship/self-grants"

#: The capabilities through which a document is read or governed.
DOCUMENT_REACHED_BY: Final = (KNOWLEDGE_READ, KNOWLEDGE_UPLOAD)

#: The capabilities through which an agent is used or governed.
AGENT_REACHED_BY: Final = (
    INVOKE_AGENT,
    AGENT_LIFECYCLE_CAPABILITY,
    AGENT_INSTALL_CAPABILITY,
    INSTRUCTIONS_AUTHORITY,
)

#: What the list is, said above it on the page.
TOLD: Final = (
    "People who gave themselves access to a document, source or agent you steward, in the last "
    "ninety days. Nothing is changed by reading this; if a grant should not be there, remove it on "
    "the People screen or ask an administrator to."
)

router = APIRouter(prefix=API_PREFIX, tags=["stewardship"])


class ReachedView(BaseModel):
    """One of the caller's own things a grant reaches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    object_id: str
    label: str


class SelfGrantNoticeView(BaseModel):
    """One grant somebody made to themselves, as its steward is told of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    person_id: str
    #: The person's display name where one is known, or empty.
    person_name: str
    #: The pack it came in, or empty for a direct grant.
    pack: str
    capabilities: list[str]
    reached: list[ReachedView]


class SelfGrantNoticesView(BaseModel):
    """The caller's notices, newest first, and the sentence the page shows above them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[SelfGrantNoticeView]
    told: str


def _store(request: Request) -> StoredStewardship:
    found = stewardship_of(request)
    if found is None:
        raise Failed("no database on this process")
    return found


async def stewarded_by(request: Request, asked: Asking) -> tuple[Stewarded, ...]:
    """Every document, source and agent the caller stewards, as far as their own reach reads it."""
    me = asked.caller.principal.id
    store = _store(request)
    things: list[Stewarded] = []
    for item in await store.documents_stewarded(me, await authority_of(request, asked)):
        row = {
            "document_id": item.item_id,
            "visibility": item.visibility.level.value,
            "owner_id": item.owner_id,
        }
        if item.visibility.department:
            row["department"] = item.visibility.department
        things.append(
            Stewarded(
                kind=StewardedKind.DOCUMENT,
                object_id=item.item_id,
                label=item.title or item.item_id,
                steward_id=item.owner_id,
                row=row,
                reached_by=DOCUMENT_REACHED_BY,
            )
        )
    records = records_of(request)
    for live in () if records is None else await records.connected():
        if await steward_of(request, live) != me:
            continue
        manifest = manifest_or_none(live)
        declared = () if manifest is None else declared_capabilities(manifest)
        declaration = shipped().get(live.connector)
        things.append(
            Stewarded(
                kind=StewardedKind.SOURCE,
                object_id=live.connector,
                label=live.connector if declaration is None else declaration.label,
                steward_id=me,
                row={SOURCE_FIELD: live.connector},
                reached_by=(INSTALL_AUTHORITY, *(Capability(value=one) for one in declared)),
                partial=True,
            )
        )
    for stored in await store.agents_stewarded(me):
        record = record_of(stored)
        if record is None:
            continue
        things.append(
            Stewarded(
                kind=StewardedKind.AGENT,
                object_id=record.agent_id,
                label=record.display_name,
                steward_id=me,
                row=agent_scope_row(record),
                reached_by=AGENT_REACHED_BY,
            )
        )
    return tuple(things)


def notice_view(notice: StewardNotice, names: dict[str, str]) -> SelfGrantNoticeView:
    grant = notice.grant
    return SelfGrantNoticeView(
        at=grant.at,
        person_id=grant.principal_id,
        person_name=names.get(grant.principal_id, ""),
        pack=grant.pack or "",
        capabilities=[one.value for one in grant.capabilities],
        reached=[
            ReachedView(kind=one.kind.value, object_id=one.object_id, label=one.label)
            for one in notice.reached
        ],
    )


@router.get(SELF_GRANTS_PATH, response_model=SelfGrantNoticesView, responses=COMMON_RESPONSES)
async def my_self_grant_notices(request: Request, asked: Asked) -> SelfGrantNoticesView:
    """The grants people made to themselves that reach what the caller stewards (M7.7.2)."""
    grants = await _store(request).self_grants(asked.now - NOTICE_WINDOW)
    if not grants:
        return SelfGrantNoticesView(items=[], told=TOLD)
    notices = notices_for(asked.caller.principal.id, grants, await stewarded_by(request, asked))
    people = sorted({one.grant.principal_id for one in notices})
    sessions = sessions_of(request)
    names: dict[str, str] = {}
    if sessions is not None and people:
        async with sessions() as session:
            names = await steward_names(session, people)
    return SelfGrantNoticesView(items=[notice_view(one, names) for one in notices], told=TOLD)
