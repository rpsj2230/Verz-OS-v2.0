"""The endpoint an automation step calls: one tool, through the gate, as the automation's owner.

`brain.ops.automation_piece` has said since 2026-09-06 that its leaf "is not closable today:
there is no endpoint a step can call". This is the endpoint. A step sends a tool name and an
argument bag, `PieceStep` and nothing else, with a credential that names one automation; what
comes back is a page built from a `ChannelPayload`, as `/records` returns.

**The order is the design, and each step is somebody else's function.**

1. The credential is parsed and the automation's registration read, as that automation.
   `brain.ops.automation_owner.verify` compares the secret in constant time.
2. The owner is looked up now, and an owner who is disabled, deleted or past the end of their
   engagement is refused. `owner_of`, before anything is resolved, so a gone owner's grants are
   never read.
3. The owner's reach is resolved now and narrowed by the channel and assurance an automation is
   held to. `owner_reach`, which is `brain.gate.resolve.resolve` and
   `brain.gate.admission.admit`.
4. The call is planned: `plan_piece_call`, which is `flow_reach` against the automation's
   declared ceiling, then `brain.gate.invoke.invoke`, which projects the catalogue from that
   reach and the declared tools and reads the leash for the strictest rung.
5. The step runs: `run_step`, which resolves the tool out of the projected catalogue, calls it
   with the narrowed reach, and redacts what comes back against the same reach.

**Nothing on this path computes a reach.** There is no `intersect` in this module, and
`tests/invariants/test_single_implementation.py` reads the call sites out of the source.

**Two refusals, and neither says why.** Steps 1 and 2 answer 401 with the one sentence every
refused credential gets; see `A_GONE_OWNER_IS_ANSWERED_AS_AN_UNKNOWN_AUTOMATION`. Steps 4 and 5
answer 404 with the one sentence every missing thing gets, which is `to_public` collapsing
DENIED into ABSENT: a tool the owner does not hold, a tool outside the declared set, a tool that
does not exist, an argument bag the tool will not take and an entity with no field policy are
one answer. The first two kinds are different answers to each other, deliberately: whether this
credential works is a fact its holder is entitled to, and which tools exist is not.

**A person's token is not an automation credential.** This route does not take `asking`, and
`asking` does not take a `bap.` credential, so neither path can be reached with the other's
secret. A session token presented here is malformed as a credential and refused as one.

Rejected: resolving the owner once when the automation is registered and caching the reach on
the registration. It is one resolution per automation instead of one per call, and it is the
arrangement in which revoking the owner's grant leaves the automation holding it. See
`brain.ops.automation_owner.AN_AUTOMATION_HOLDS_NOTHING_OF_ITS_OWNER_BETWEEN_CALLS`.

**Not done here, and each for a reason that is not time.**

*A call is not recorded through `brain.gate.finish`.* That module is the one completion point,
and a record written from a route is the per-channel hook its docstring refuses, so this route
writes none of its own. It cannot use `finish` either: `Finished.outcome` is `Answered | None`,
the answer lane's outcome type, and `brain.ops.telemetry.status_of_finished` records None as a
fault. A successful tool call handed to `finish` today would be written to the metadata ledger as
FAILED, or would need an `Answered` with invented frames. The change is to `Finished` in
`brain.gate.finish`, which gains an outcome a tool call can be, and `status_of_finished` a line
for it. See `A_TOOL_CALL_IS_NOT_YET_A_FINISHED_REQUEST`.

*No rate limit applies.* No route in this application consults `brain.ops.limits`, and this one
is no exception; a limiter wired into one route and not the others would be a limit on the least
used path.

*The leash is empty.* `app.state` carries no leash, so `invoke` reads `Leash()` and every rung is
the missing-entry rung. That rung is recorded on the invocation and decides nothing for a call
with no side effect, which is every call this route can make: see
`brain.ops.automation_owner.AN_AUTOMATION_READS_UNTIL_ITS_WRITES_CAN_BE_SUSPENDED`.

*Nothing constructs the wiring.* `app.state.automation` is None on a deployed process, for the
reason `app.state.gate` is: there is no `PrincipalRecords` implementation over `auth.principal`,
as there is no `EntitlementStore` over the grant tables. So on the deployed instance this route
refuses every credential, uniformly, which is what a missing authenticator has to mean.

Task ids: none
"""

from __future__ import annotations

import inspect
import json
import typing
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Protocol

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import RecordPage, field_policies, page_from, wiring_of
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import ToolDefinition
from brain.core.errors import Absent, Failed
from brain.gate.injection import assess
from brain.gate.invoke import InvocationRefusedError
from brain.gate.leash import Leash
from brain.identity.bearer import token_from_header
from brain.identity.oidc import TokenRefusal, TokenRefusedError
from brain.ops.automation import flow_reach
from brain.ops.automation_owner import (
    AutomationRefusal,
    AutomationRefusedError,
    PrincipalRecords,
    Registration,
    automation_id_of,
    loggable,
    owner_of,
    owner_reach,
    verify,
)
from brain.ops.automation_piece import (
    TOOL_NOT_AVAILABLE,
    PieceRefusedError,
    PieceStep,
    plan_piece_call,
    resolve_step,
    run_step,
)
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

#: Where a step sends its call, under `API_PREFIX`. The piece's `contract.json` names the same
#: path and a test holds the two equal.
TOOL_CALL_PATH: Final = "/automation/tool-call"

#: Why this route does not record through `brain.gate.finish` yet.
A_TOOL_CALL_IS_NOT_YET_A_FINISHED_REQUEST: Final = (
    "gate.finish is the one completion point and a route writing its own record is the hook "
    "it refuses. Finished.outcome is the answer lane's outcome or None, and None is recorded "
    "as a fault, so a successful tool call handed to it would be written as FAILED or would "
    "need invented frames. The record belongs to finish, once Finished can hold a tool call's "
    "outcome, and until then this route records nothing rather than something wrong."
)

#: The leash an automation's call is planned under. Empty; see the module docstring.
NO_LEASH: Final = Leash()


class RegistrationSource(Protocol):
    """Where a registration is read, as the automation that is calling.

    `brain.ops.automation_owner_store.StoredAutomations` over `gate.automation_owner`.
    """

    async def registration(self, automation_id: str) -> Registration | None: ...


@dataclass(frozen=True)
class AutomationWiring:
    """What an automation's call needs beside the gate wiring. Both or neither, as `GateWiring`."""

    registrations: RegistrationSource
    principals: PrincipalRecords


def automation_wiring_of(request: Request) -> AutomationWiring | None:
    found = getattr(request.app.state, "automation", None)
    return found if isinstance(found, AutomationWiring) else None


def _refused(error: AutomationRefusedError | None, presented: str) -> TokenRefusedError:
    """The one refusal a credential gets, with the reason in the operator's log only."""
    log.info(
        "automation.refused",
        reason=str(error.reason) if error is not None else "not_wired",
        credential=loggable(presented),
    )
    return TokenRefusedError(TokenRefusal.NO_PRINCIPAL, "automation credential refused")


class RegistryToolCaller:
    """`brain.ops.automation_piece.ToolCaller` over the application's frozen registry.

    The handler is taken off the registry by the definition's name, the argument bag is
    validated into the request model the handler's first parameter declares, and the handler
    is called with the narrowed reach as its entitlement. This is the call `/records` makes,
    with the request built from a step's arguments rather than from query parameters.

    An argument bag the request model refuses is `TOOL_NOT_AVAILABLE`, for the reason a
    malformed tool name is: a second kind of refusal is a second fact. The validation error
    goes to the log by type.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def call(
        self,
        *,
        tool: ToolDefinition,
        arguments: Mapping[str, Any],
        entitlement: EntitlementSet,
        now: datetime | None,
    ) -> object:
        handler = self.registry.get(tool.name).handler
        request_type = _request_type(handler)
        if request_type is None:
            log.warning("automation.tool_takes_no_request_model", tool=tool.name)
            raise PieceRefusedError(TOOL_NOT_AVAILABLE)
        try:
            built = request_type.model_validate(dict(arguments))
        except ValidationError as exc:
            log.info("automation.arguments_refused", tool=tool.name, error=type(exc).__name__)
            raise PieceRefusedError(TOOL_NOT_AVAILABLE) from exc
        return handler(built, entitlement=entitlement, now=now)


def _request_type(handler: typing.Callable[..., object]) -> type[BaseModel] | None:
    """The pydantic model a handler's first positional parameter is annotated with, or None."""
    parameters = [
        one
        for one in inspect.signature(handler).parameters.values()
        if one.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if not parameters:
        return None
    annotation = typing.get_type_hints(handler).get(parameters[0].name)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


@dataclass(frozen=True)
class CallingAutomation:
    """One call's automation, and the owner's reach it will run at, as it is now.

    `caller` is the owner's reach after `admit` and before the automation's ceiling, which is
    the left-hand side `flow_reach` takes. The owner is not carried: the reach already names
    them, and `plan_piece_call` reads the principal off the reach rather than off anything a
    route could substitute.
    """

    registration: Registration
    caller: EntitlementSet
    now: datetime


async def calling_automation(request: Request) -> CallingAutomation:
    """Authenticate the automation, look its owner up now, resolve the owner's reach now.

    A dependency rather than the first lines of the handler, for the reason `asking` is one:
    FastAPI solves a dependency before it validates the body, so a refused credential answers
    401 whatever it sent, and a stranger learns nothing about the body's shape by sending a
    wrong one. `test_every_route_under_the_prefix_authenticates_its_caller` holds that over the
    mounted set, and found this route validating first.
    """
    now = datetime.now(UTC)
    presented = token_from_header(request.headers.get("authorization"))

    automation = automation_wiring_of(request)
    gate = wiring_of(request)
    try:
        automation_id = automation_id_of(presented)
        if automation is None or gate is None:
            raise _refused(None, presented)
        found = await automation.registrations.registration(automation_id)
        if found is None:
            # The same error type `verify` raises for a wrong secret, so the two cannot be told
            # apart by anything the caller sees and only the log says which.
            raise AutomationRefusedError(AutomationRefusal.UNKNOWN_AUTOMATION, automation_id)
        registration = verify(presented, found)
        owner = owner_of(registration, principals=automation.principals, now=now)
    except AutomationRefusedError as exc:
        raise _refused(exc, presented) from exc

    return CallingAutomation(
        registration=registration,
        caller=owner_reach(
            owner, versions=gate.versions, store=gate.store, cache=gate.cache, now=now
        ),
        now=now,
    )


#: The dependency this route takes. Spelled once, as `api_routes.Asked` is.
Calling = Annotated[CallingAutomation, Depends(calling_automation)]


router = APIRouter(prefix=API_PREFIX, tags=["automation"])


@router.post(TOOL_CALL_PATH, response_model=RecordPage, responses=COMMON_RESPONSES)
async def tool_call(request: Request, calling: Calling, step: PieceStep) -> RecordPage:
    """One step of one automation, run as its owner, at the owner's reach as it is now.

    See the module docstring for the order and for what is not done here.
    """
    registration, caller, now = calling.registration, calling.caller, calling.now

    registry = getattr(request.app.state, "tools", None)
    if not isinstance(registry, ToolRegistry):
        # A process-level fault, identical for every caller, and reached only after the
        # credential was accepted, so it discloses nothing to somebody who holds none.
        raise Failed("no tool registry on this process")

    try:
        invocation = plan_piece_call(
            flow_id=registration.automation_id,
            caller=caller,
            flow_ceiling=registration.ceiling,
            declared_tools=registration.declared_tools,
            registry=registry,
            leash=NO_LEASH,
            # The step's arguments are text somebody outside this company may have written,
            # through the trigger. Scored rather than assumed clean; see `plan_piece_call`.
            assessment=assess(json.dumps(step.arguments, sort_keys=True, default=str)),
            now=now,
        )
        policy = field_policies(registry).get(resolve_step(step, invocation).entity)
        if policy is None:
            raise PieceRefusedError(TOOL_NOT_AVAILABLE)
        payload = await run_step(
            step,
            invocation,
            reach=flow_reach(caller, registration.ceiling),
            tools=RegistryToolCaller(registry),
            policy=policy,
            now=now,
        )
    except (InvocationRefusedError, PieceRefusedError) as exc:
        log.info(
            "automation.step_refused",
            automation=registration.automation_id,
            error=type(exc).__name__,
        )
        raise Absent(TOOL_NOT_AVAILABLE) from exc

    log.info("automation.step_answered", automation=registration.automation_id, tool=step.tool)
    return page_from(payload)
