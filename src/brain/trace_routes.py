"""Reading a run's stored trace: the payload role read off the caller's own token, then the store.

`brain.ops.trace_store.StoredTraces.read` has asked for the caller's realm roles since `0150` and
nothing could supply them: "the Keycloak realm role reaches no token claim the application reads
today", its docstring said, so the only caller was the install's own check handing the role in by
name. This module is the other end. The realm declares `brain.ops.tracing.PAYLOAD_ROLE` and a mapper
on `brain-identity` writes it into `realm_access.roles` (`ops/keycloak/realm-export.json`), the
route reads it off the verified token of the person asking, and the store does the rest: the row
before the read, then the reader role.

**One role is read, and only that one.** `payload_roles_of` returns the payload role when the token
carries it and nothing else, whatever else the claim holds, so a token cannot bring any other
Keycloak role into this system through it. `brain.identity.oidc.assert_no_capability_from_claims`
holds its return type to one that cannot carry a capability. The realm's own scope mapping makes
the payload role the only one a console token can carry at all, which is the same rule stated a
second time where the identity provider enforces it. See
`ONLY_THE_PAYLOAD_ROLE_IS_READ_OFF_A_SIGN_IN`.

**A trace the caller may not read and a trace that does not exist are one answer.** Without the
role, the store refuses before writing anything, and the route answers `Absent`; with it, a trace
id nothing was recorded under reads back empty, and the route answers the same `Absent`. What
differs is the store's own record: a read by somebody holding the role is on file whether or not
it found anything, because the row is written before the read and a person with the role did look.
See `A_REFUSED_READ_AND_A_MISSING_TRACE_ARE_ONE_ANSWER`.

**The reason is required and is the caller's.** `brain.ops.tracing.PayloadRead` refuses a blank
one, and a read is a POST with a body so the reason is not in a URL a proxy logs.

Rejected: a capability for reading traces, granted in the console. The design keeps payload reads
outside the permission model on purpose (`brain.ops.tracing.PAYLOAD_ROLE`): it is something an
operator holds for an afternoon during an incident, granted in the identity provider, and a
capability would make it one more grant a Super Admin could leave in place for ever.

Task ids: M32.1.2.4
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.core.errors import Absent
from brain.identity.oidc import VerifiedClaims
from brain.ops.trace_store import StoredTraces, TraceStoreError
from brain.ops.tracing import PAYLOAD_ROLE
from brain.routing_routes import sessions_of
from brain.tables.telemetry import READ_REASON_CHARS

log = structlog.get_logger(__name__)

router = APIRouter(prefix=API_PREFIX, tags=["traces"])

#: Where one trace is read. A POST, because the read carries a reason.
TRACE_READ_PATH: Final = "/traces/{trace_id}/read"

#: The claim Keycloak's realm role mapper writes, as `ops/keycloak/realm-export.json` names it.
REALM_ACCESS_CLAIM: Final = "realm_access"

# ------------------------------------------------------------------ written-down reasons
#: Why one role and no other is read off a sign-in's claims.
ONLY_THE_PAYLOAD_ROLE_IS_READ_OFF_A_SIGN_IN: Final = (
    "Groups decide roles and grants decide reach, and a Keycloak role decides nothing here except "
    "whether a person may read a stored trace. So the token's realm roles are read for that one "
    "role and every other value in the claim is ignored, and the realm maps that role alone into "
    "a console token."
)

#: Why a refused read and a missing trace are answered alike.
A_REFUSED_READ_AND_A_MISSING_TRACE_ARE_ONE_ANSWER: Final = (
    "A person without the payload role who could tell a refused read from a missing trace could "
    "learn which requests were traced by asking about each one, so both are the one answer every "
    "missing thing gets."
)


class TraceReadAsked(BaseModel):
    """Why the trace is being read. Recorded, before the read, against the person reading.

    Stripped before it is measured, so a reason of spaces is refused here as a malformed body
    rather than by `tracing.PayloadRead` after the route has begun.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=READ_REASON_CHARS)


class TraceStepView(BaseModel):
    """One stored step, as `tracing.mask` left it."""

    step: int
    parent: int | None
    kind: str
    name: str
    attributes: dict[str, object]
    payload_in: str
    payload_out: str


class TraceView(BaseModel):
    """A run's graph, in step order."""

    trace_id: str
    steps: list[TraceStepView]


def payload_roles_of(claims: VerifiedClaims) -> frozenset[str]:
    """The payload role when this token carries it, and nothing otherwise.

    Reads `realm_access.roles` as Keycloak writes it: an object holding a list of strings. Any
    other shape carries no role, rather than raising: a token without the claim is the ordinary
    case for everybody who does not hold the role.
    """
    access = claims.claim(REALM_ACCESS_CLAIM)
    if not isinstance(access, Mapping):
        return frozenset()
    roles = access.get("roles")
    if not isinstance(roles, list):
        return frozenset()
    return frozenset({PAYLOAD_ROLE}) if PAYLOAD_ROLE in roles else frozenset()


@router.post(TRACE_READ_PATH, response_model=TraceView, responses=COMMON_RESPONSES)
async def read_trace(
    request: Request, trace_id: str, body: TraceReadAsked, asked: Asked
) -> TraceView:
    """One trace, read under the payload role the caller's own token carries, row first."""
    sessions = sessions_of(request)
    if sessions is None:
        raise Absent("no trace store on this process")
    try:
        steps = await StoredTraces(sessions).read(
            realm_roles=payload_roles_of(asked.caller.claims),
            at=asked.now,
            actor=asked.caller.principal_id,
            trace_id=trace_id,
            reason=body.reason,
        )
    except TraceStoreError as exc:
        log.info("trace.read_refused", principal=asked.caller.principal_id)
        raise Absent("no such trace") from exc
    if not steps:
        raise Absent("no such trace")
    return TraceView(
        trace_id=trace_id,
        steps=[
            TraceStepView(
                step=one.step,
                parent=one.parent,
                kind=one.kind.value,
                name=one.name,
                attributes=dict(one.attributes),
                payload_in=one.payload_in,
                payload_out=one.payload_out,
            )
            for one in steps
        ],
    )
