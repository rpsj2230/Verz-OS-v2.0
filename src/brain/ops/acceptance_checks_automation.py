"""The install acceptance check for the automation canvas's door: a step reaches its owner's rows
and nothing its declared ceiling adds.

The canvas itself is an optional container this install may not run, and the piece it loads is a
TypeScript package tested where it is built (`tests/unit/test_automation_piece_package.py`). What
every install does run is the endpoint that piece calls, `brain.automation_routes.tool_call`, and
the gate behind it: the automation's own credential, its owner looked up at the call, the owner's
reach resolved and admitted, `brain.ops.automation.flow_reach` against the automation's declared
ceiling, the projected catalogue and the redactor. This check posts steps to that route, mounted
over the check's transaction the way `brain.app` mounts it, as the piece would post them.

**The ceiling is deliberately wider than the owner.** An automation declaring every column of the
price list, owned by somebody who holds two of them, is the case `flow_reach` exists for: the
declaration is a ceiling and never a grant, so the step comes back with the owner's two columns and
nothing the declaration added. The same ceiling owned by somebody who holds nothing on the price
list reaches nothing at all, and is answered exactly as a tool that does not exist: the other half
of the same intersection, and the one an empty set is easiest to get wrong in. See
`A_CEILING_IS_NEVER_A_GRANT`.

**The owners' grants are company-wide and the step names its own rows.** A departmental grant on a
built-in row entity reaches nothing through any redacting door today, because the price list's
classification has no department column and the redactor tests a departmental scope against the
record; that is a defect of the row plane, reported beside this check rather than proved around it.
So the owner holds the two columns across the company, and the step filters on the names only
this check wrote, which the asker may filter on because they can see the column. Nothing another
row on the install holds can come back, and nothing leaves the process either way.

**The refusals are held to each other rather than to a message.** A tool the automation did not
declare and a tool that does not exist are one answer (`brain.ops.automation_piece.
TOOL_NOT_AVAILABLE`), because two answers would let a flow author enumerate the catalogue; and a
credential with the wrong secret is refused before anything is resolved. The check compares the
responses to each other, so it does not depend on the wording either keeps.

**Nothing leaves the transaction.** The registration, the owner, their grants and the records are
rows the check writes and the run rolls back; the route is called through an in-process transport,
so no request reaches the network and nothing is recorded outside the transaction: the mounted
route is given no request recorders, as `brain.ops.acceptance_checks_chat` gives its events route
none of the vendor's.

Task ids: M32.6.2.2, M32.6.1.3
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 210

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the automation is given a ceiling wider than its owner.
A_CEILING_IS_NEVER_A_GRANT: Final = (
    "An automation's declared ceiling narrows what its owner may reach and never adds to it, so "
    "the check registers one declaring every column of the price list for an owner holding two. "
    "A step coming back with a column only the ceiling named would be a flow reaching data "
    "outside the caller's entitlements, which is what the canvas's door must never do."
)

# ------------------------------------------------------------------------ the figures
#: What the owner holds, company-wide: the price list's name and sell price, and no more.
OWNERS_HOLD: Final = ("read:price_list", "read:price_list.name", "read:price_list.sell_price")

#: What the automation declares: every column of the price list, cost and margin included.
CEILING_DECLARES: Final = (*OWNERS_HOLD, "read:price_list.cost", "read:price_list.margin")

#: The columns a step's record may carry for an owner holding `OWNERS_HOLD`.
OWNERS_COLUMNS: Final = frozenset({"name", "sell_price"})


# ------------------------------------------------------------------------ the helpers
@dataclass(frozen=True)
class _Door:
    """The tool-call route over the check's transaction, and the price list's tool name."""

    app: FastAPI
    tool: str
    #: The id the application's trace middleware would bind for the request, which the route
    #: reads off the log context and the ledger's grammar requires.
    trace_id: str

    async def post(
        self, credential: str, tool: str, arguments: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        """One step as the piece sends it: a tool name and an argument bag, as a bearer."""
        import httpx
        import structlog

        from brain.api import API_PREFIX
        from brain.automation_routes import TOOL_CALL_PATH

        # An exception nothing maps is answered 500, as the application's server would, rather
        # than raised into the check: a door that fails differently is a different answer.
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        with structlog.contextvars.bound_contextvars(trace_id=self.trace_id):
            async with httpx.AsyncClient(
                transport=transport, base_url="https://acceptance.invalid"
            ) as client:
                answered = await client.post(
                    f"{API_PREFIX}{TOOL_CALL_PATH}",
                    headers={"authorization": f"Bearer {credential}"},
                    json={"tool": tool, "arguments": arguments or {}},
                )
        is_json = answered.headers.get("content-type", "").startswith("application/json")
        return answered.status_code, answered.json() if is_json else answered.text


async def _door(h: Harness) -> _Door:
    """`brain.automation_routes.router` with the wiring `brain.app.wirings_for` gives it."""
    from fastapi import FastAPI

    from brain.api_routes import GateWiring
    from brain.automation_routes import AutomationWiring, router
    from brain.cache import NoEntitlementCache, PostgresVersionSource
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.keycloak_tokens import keycloak_authority
    from brain.identity.principal_directory import StoredDirectory
    from brain.identity.principal_store import StoredPrincipals
    from brain.identity.roles import IdentityError
    from brain.install import InstallError
    from brain.knowledge.columns import PRICE_LIST
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.rows import RowTool
    from brain.ops.acceptance_checks_chat import _NoKeys
    from brain.ops.automation_owner_store import StoredAutomations
    from brain.tools.startup import build_registry

    try:
        authority = keycloak_authority(
            directory=StoredDirectory(h.sessions), get=_NoKeys(), clock=lambda: datetime.now(UTC)
        )
    except (InstallError, IdentityError) as exc:
        raise CheckNotRunError(
            "this install cannot check a sign-in, so it has no gate to answer"
        ) from exc
    source = h.settings.tool_source
    registry = build_registry(source=source, records=SessionRowSource(h.sessions))
    tool = RowTool(source=source, classification=PRICE_LIST, description="The price list.").name
    if not registry.has(tool):
        raise CheckFailedError("this install registers no typed tool for its price list")
    app = FastAPI()
    app.include_router(router)
    _answers_as_the_application_does(app)
    app.state.gate = GateWiring(
        authority=authority,
        versions=PostgresVersionSource(h.sessions),
        store=StoredEntitlements(h.sessions),
        # No entitlement cache: a cached reach would outlive the transaction it was read in.
        cache=NoEntitlementCache(),
    )
    app.state.automation = AutomationWiring(
        registrations=StoredAutomations(h.sessions), principals=StoredPrincipals(h.sessions)
    )
    app.state.tools = registry
    app.state.request_recorders = ()
    return _Door(app=app, tool=tool, trace_id=f"{h.trace_id}-automation")


def _answers_as_the_application_does(app: FastAPI) -> None:
    """The two answers `brain.app` gives the route's refusals, over `brain.core.errors.to_public`.

    Restated, because nothing under `src` imports the application: a refusal of what exists is a
    404 carrying the public sentence, whether it was DENIED or ABSENT, and a refused credential is
    a 401 with one sentence whatever was wrong with it. The check compares the answers with each
    other, so it holds the route to one answer per kind rather than to these words.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    from brain.core.errors import BrainError, Outcome, to_public
    from brain.identity.oidc import TokenRefusedError

    async def refused(request: Request, exc: Exception) -> JSONResponse:
        del request
        if isinstance(exc, TokenRefusedError):
            return JSONResponse(status_code=401, content={"message": "sign in"})
        assert isinstance(exc, BrainError)
        hidden = exc.outcome in {Outcome.DENIED, Outcome.ABSENT}
        return JSONResponse(status_code=404 if hidden else 500, content={"message": to_public(exc)})

    app.add_exception_handler(BrainError, refused)
    app.add_exception_handler(TokenRefusedError, refused)


async def _registered(h: Harness, owner_id: str, tool: str, name: str) -> str:
    """An automation owned by `owner_id`, declaring the price list tool under `CEILING_DECLARES`,
    stored as the owner registering it would store it; its credential."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.automation_owner import register
    from brain.ops.automation_owner_store import StoredAutomations

    owner = await StoredPrincipals(h.sessions).live_principal(owner_id)
    if owner is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    automation_id = f"acceptance-{h.run}-{name}"
    issued = register(
        automation_id=automation_id,
        owner=owner,
        declared_tools=frozenset({tool}),
        ceiling=EntitlementSet(
            principal_id=automation_id,
            grants=tuple(
                Grant(capability=Capability(value=one), scope=Scope.unrestricted())
                for one in CEILING_DECLARES
            ),
        ),
        now=h.now,
    )
    await StoredAutomations(h.sessions).put(issued.registration)
    return issued.credential


# ------------------------------------------------------------------------------- the check
@check(
    leaves=("M32.6.2.2", "M32.6.1.3"),
    sentence=(
        "Automations declaring every price list column post steps to the install's tool-call "
        "route as the canvas's piece does: one owned by a person holding only name and sell "
        "price gets its rows with those two columns only; one owned by a person holding nothing, "
        "an undeclared tool and a missing tool all get one identical refusal; a wrong secret is "
        "refused."
    ),
)
async def a_flow_step_gets_its_owner_s_rows_and_nothing_its_ceiling_adds(h: Harness) -> None:
    from brain.core.scope import Scope
    from brain.knowledge.columns import PRICE_LIST
    from brain.tables.projection import ProjectedRecordRow

    await h.found_departments()
    door = await _door(h)
    owner, stranger = h.principal(A, "owner"), h.principal(B, "owner")
    await h.person(owner, department=A, grants=[(one, Scope.unrestricted()) for one in OWNERS_HOLD])
    await h.person(stranger, department=B)
    names = sorted({h.word(), h.word()})
    for n, name in enumerate(names):
        await h.execute(
            *h.attributed(),
            insert(ProjectedRecordRow).values(
                source=h.settings.tool_source,
                entity=PRICE_LIST.entity,
                source_id=f"acceptance-{h.run}-{n}",
                last_seen_at=h.now,
                fields={
                    "department": A,
                    "sku": f"ACC-{n}",
                    "name": name,
                    "sell_price": "120.00",
                    "cost": "70.00",
                    "margin": "50.00",
                },
            ),
        )
    # The check's own rows and no others: a filter on a column the owner can see.
    mine = {"filters": {"clauses": [{"field": "name", "op": "in", "value": names}]}}

    credential = await _registered(h, owner, door.tool, "owner")
    status, page = await door.post(credential, door.tool, mine)
    items = page.get("items") if isinstance(page, dict) else None
    if status != 200 or not isinstance(items, list):
        raise CheckFailedError("a step naming its declared tool was not answered")
    if sorted(str(one.get("name")) for one in items) != names:
        raise CheckFailedError("a step was not given its owner's rows")
    if any(set(one) - {"entity", "id"} != OWNERS_COLUMNS for one in items):
        raise CheckFailedError("a step was given a column only the automation's ceiling named")

    missing = await door.post(credential, f"acceptance.no_such_tool_{h.run}")
    if missing[0] != 404:
        raise CheckFailedError("a step naming a tool that does not exist was not refused")
    unowned = await door.post(
        await _registered(h, stranger, door.tool, "stranger"), door.tool, mine
    )
    if unowned != missing:
        raise CheckFailedError(
            "an automation whose owner holds nothing was answered unlike a missing tool"
        )
    undeclared = await door.post(credential, "knowledge.search_documents")
    if undeclared != missing:
        raise CheckFailedError(
            "an undeclared tool and a tool that does not exist were answered differently"
        )
    wrong = credential.rsplit(".", 1)[0] + "." + secrets.token_urlsafe(32)
    refused, _ = await door.post(wrong, door.tool, mine)
    if refused != 401:
        raise CheckFailedError("a step carrying the wrong secret was not refused")
