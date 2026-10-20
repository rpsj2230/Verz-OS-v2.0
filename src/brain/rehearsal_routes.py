"""Asking the server for a restore rehearsal, from the Recovery screen.

`GET /install/recovery` has said since it was written that there is no control that runs a
rehearsal, because a rehearsal loads the newest copy into a scratch database beside the containers
and nothing the product runs holds the access to start one. That is still true, and this is not a
way round it. This is the one thing the product can do: put a small request in the backup bucket,
where the server's own drill service (`ops/backup/brain-drill-service`, set up by the installer on
the owner's choice, needs-rupash item 235) looks every ten minutes, and read the record the service
writes beside the copy, which the screen already reads.

**The press asks and does not promise.** The answer says a request was made and when, never that a
rehearsal started: the service may not be installed on this server, and the screen's own record of
the last rehearsal, and of whether one is owed, is how a person learns it ran. A control that said
"started" would be the reassurance item 44 forbids on this screen.

**Two authorities, one of them the screen's.** Whoever may open the Recovery screen may see it; to
ask, the caller must also hold the install authority over everything (`admin:install_setting`),
because a rehearsal loads every record the install holds into a second place for the length of the
run, and that is not a thing the person who reads the backup screen is entitled to cause. A caller
holding neither is refused with the sentence the screen gives anyone it does not answer, so the
refusal reveals nothing about whether the control exists.

**It ships off** (`BACKUP_DRILL_REQUESTS`): turning it on is the owner's answer to item 235, and a
request with no service to read it waits for ever. The switch holds back the write and nothing else.

**One request at a time.** A second press while one waits answers with the first one's time and
writes nothing, so a person pressing twice cannot queue two scratch databases.

Task ids: M30.3.9
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import structlog
from fastapi import APIRouter, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.install_routes import backup_objects_of
from brain.ops.features import is_on
from brain.ops.features_declared.backup_drill_requests import BACKUP_DRILL_REQUESTS
from brain.ops.rehearsal_request import pending_in, put_request
from brain.ops.storage import StoreUnansweredError
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: Held over everything or not at all, as the migration screen's is.
REHEARSAL_AUTHORITY = Capability(value="admin:install_setting")


class RecoveryRehearsalAsked(BaseModel):
    """What the press did, in words, and when the ask was made if it is known."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    already_asked: bool
    requested_at: AwareDatetime | None
    says: str


def may_ask(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may open the Recovery screen and also holds the install authority."""
    return permitted(screen("recovery").read, reach, now) and _in_reach(
        reach, REHEARSAL_AUTHORITY, NOWHERE, now
    )


def _not_answerable() -> Absent:
    return Absent("the recovery screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    message = f"that was not asked: {reason}"
    return Absent(message, public_message=message)


router = APIRouter(prefix=API_PREFIX, tags=["install"])


@router.post(
    "/install/recovery/rehearsal", response_model=RecoveryRehearsalAsked, responses=COMMON_RESPONSES
)
async def ask_for_a_rehearsal(request: Request, asked: Asked) -> RecoveryRehearsalAsked:
    """Leave a request for the server's drill service, unless one is already waiting."""
    if not may_ask(asked.reach, asked.now):
        raise _not_answerable()
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    try:
        async with factory() as session:
            switched_on = await is_on(session, BACKUP_DRILL_REQUESTS)
    except SQLAlchemyError as error:
        log.warning("rehearsal switch not read", error=type(error).__name__)
        raise Failed("the switch on asking for a rehearsal could not be read") from error
    if not switched_on:
        raise _refused_because(
            "asking for a rehearsal is switched off for this install; switch it on from Features"
        )
    objects = backup_objects_of(request)
    store = getattr(request.app.state, "object_store", None)
    backend = getattr(store, "backend", None)
    if objects is None or backend is None:
        raise _refused_because(
            "this process is not connected to the backup bucket, so there is nowhere to leave "
            "the request"
        )
    try:
        waiting = pending_in(await asyncio.to_thread(lambda: tuple(objects())))
        if waiting is not None:
            return RecoveryRehearsalAsked(
                already_asked=True,
                requested_at=waiting.at,
                says=(
                    "A rehearsal was already asked for and is waiting for the server to start "
                    "it. Nothing more was asked."
                ),
            )
        await asyncio.to_thread(put_request, backend, at=asked.now, by=asked.caller.principal.id)
    except StoreUnansweredError as error:
        log.warning("rehearsal request not left", error=str(error))
        raise Failed("the backup bucket did not answer, so the request was not left") from error
    log.info("rehearsal asked for", principal=asked.caller.principal.id)
    return RecoveryRehearsalAsked(
        already_asked=False,
        requested_at=asked.now,
        says=(
            "A rehearsal was asked for. The server starts it within about ten minutes if its "
            "drill service is running, and the record appears on this screen when it is done. "
            "This does not say it has started."
        ),
    )
