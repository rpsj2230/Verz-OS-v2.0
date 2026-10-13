"""Install checks for the governance decisions the owner answered on 2026-10-12 and 2026-10-13.

Each check calls the route function the console calls, as the reader a leaf names, in the shape
`brain.ops.acceptance_agent_console` and `brain.ops.acceptance_checks_governance` set out: the
reserved principals, the check's own transaction that is always rolled back, and a refusal asked
beside every act it refuses so a route that refuses everything cannot pass.

**What an install already holds is never assumed to be nothing.** The count of redacted requests is
read before and after the check writes its rows and the difference is what is asserted, because an
install in use already has requests in the window.

**A rung is judged against the leash the agent was installed with.** The check writes the install's
own rung for its target the way an operator's statement does (`acceptance_checks_role_surfaces`),
lowers it through the route, and asks for more than it was published at: the ceiling's own sentence
is the answer, and a press up to the published rung gets the next refusal in the order, the
evidence's, which says the ceiling was not what stopped it.

Task ids: M33.4.1.3, M33.2.2.4, M39.8.1, M33.8.3, M13.7.3, M13.7.4, M13.9.1, M20.1.1
"""

from __future__ import annotations

import json
import secrets
from typing import Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1400

#: How many fields the check's redacted request had taken out, and the hash a ledger row carries.
REDACTED_FIELDS: Final = 2
SOME_HASH: Final = "0" * 32


def _body(answered: Any) -> dict[str, Any]:
    """A route's JSON body, whichever way it answered."""
    if hasattr(answered, "body"):
        return dict(json.loads(bytes(answered.body)))
    return dict(answered.model_dump(mode="json"))


# ------------------------------------------------- 1. redacted requests counted (M33.4.1.3)
@check(
    leaves=("M33.4.1.3",),
    sentence=(
        "The Activity screen's statistics count the requests whose answer was redacted, as other "
        "people's requests only, for a reader whose audit grant covers everybody, and send no "
        "figure at all to a reader whose audit grant covers less."
    ),
)
async def redacted_requests_are_counted_for_a_reader_who_may_see_them_all(
    h: Harness,
) -> None:
    from sqlalchemy import insert

    from brain.audit.view import CAPABILITY_BY_KIND
    from brain.audit_statistics_routes import audit_statistics
    from brain.console.screens import screen
    from brain.core.lane import Lane
    from brain.gate.context import TrafficClass
    from brain.ops.acceptance import CheckNotRunError
    from brain.ops.acceptance_checks_governance import _app, _asking, _opens, _request
    from brain.ops.telemetry import Ingress, RequestStatus, RequestTelemetry
    from brain.tables.telemetry import RequestTelemetryRow

    await h.found_departments()
    everywhere = Scope.unrestricted()
    read = screen("audit").read
    auditor, narrow, asker = (h.principal(A, role) for role in ("auditor", "narrow", "asker"))
    every_kind = tuple((one.value, everywhere) for one in CAPABILITY_BY_KIND.values())
    await h.person(auditor, department=A, grants=(*_opens(read, everywhere), *every_kind))
    await h.person(
        narrow,
        department=A,
        grants=(*_opens(read, everywhere), (CAPABILITY_BY_KIND["principal"].value, everywhere)),
    )
    await h.person(asker, department=A)
    request = _request(_app(h))

    async def counted(who: str) -> int | None:
        return (await audit_statistics(request, await _asking(h, who))).redacted_requests

    before = await counted(auditor)
    if before is None:
        raise CheckFailedError("a reader whose audit grant covers everybody was sent no figure")

    def row(trace: str, principal: str, redactions: int | None) -> dict[str, Any]:
        telemetry = RequestTelemetry(
            ingress=Ingress(
                trace_id=trace, traffic_class=TrafficClass.HUMAN_INTERACTIVE, received_at=h.now
            ),
            principal=principal,
            entitlement_hash=SOME_HASH,
            lane=Lane.FAST,
            tool_count=0,
            cache_hit=False,
            status=RequestStatus.ANSWERED,
            duration_ms=1.0,
            redaction_count=redactions,
        )
        return dict(telemetry.ledger_row())

    try:
        await h.execute(
            insert(RequestTelemetryRow).values(
                [
                    row(f"{h.trace_id}-r1", asker, REDACTED_FIELDS),
                    row(f"{h.trace_id}-r2", asker, 0),
                    row(f"{h.trace_id}-r3", asker, None),
                    row(f"{h.trace_id}-r4", auditor, REDACTED_FIELDS),
                ]
            )
        )
    except Exception as exc:
        raise CheckNotRunError(
            "the request ledger has no partition for the check's instant, so no request can be "
            "written to be counted"
        ) from exc
    after = await counted(auditor)
    if after != before + 1:
        raise CheckFailedError(
            "the count of redacted requests did not move by exactly the other person's one "
            "redacted request, or counted the reader's own"
        )
    if await counted(narrow) is not None:
        raise CheckFailedError("a reader whose audit grant covers less was sent a count")


# --------------------------------------------- 2. a rung cannot pass its published one (M33.2.2.4)
@check(
    leaves=("M33.2.2.4",),
    sentence=(
        "A department administrator lowers an agent's rung through the leash route and asks for "
        "one above the rung it was published at, which is refused in the sentence that says to "
        "publish again; asking for the published rung is refused for its evidence instead, so the "
        "ceiling is the published rung and not a refusal of every raise."
    ),
)
async def a_rung_cannot_pass_the_rung_the_agent_was_published_at(h: Harness) -> None:
    from brain.agent_leash_routes import LEASH_AUTHORITY, MoveAsked, move_agent_rung
    from brain.agents.leash_moves import (
        RAISING_BEYOND_THE_PUBLISHED_RUNG,
        THE_EVIDENCE_DOES_NOT_MEET_THE_BAR,
    )
    from brain.agents.template import LeashRung, ManifestGuardrails
    from brain.gate.injection import AutonomyTier
    from brain.ops.acceptance_agent_console import _asking, _console, _readers, _request
    from brain.ops.acceptance_checks_governance import _traced
    from brain.ops.acceptance_workspace import installed_agent

    _traced(h)
    await h.found_departments()
    steward, admin = h.principal(A, "steward"), h.principal(A, "leasher")
    await h.person(steward, department=A, grants=_readers())
    await h.person(
        admin,
        department=A,
        grants=(*_readers(), (LEASH_AUTHORITY.value, Scope.department(A))),
    )
    target = f"acceptance_{h.run}"
    # Installed at Assisted, as the manifest the publisher signed names it: the leash is sealed.
    published = ManifestGuardrails(
        leash=(LeashRung(target=target, scope=Scope(), rung=AutonomyTier.ASSISTED),)
    )
    agent_id = await installed_agent(h, steward, guardrails=published)
    request = _request(_console(h))

    async def pressed(to: Any) -> dict[str, Any]:
        asked = await _asking(h, admin, strong=True)
        return _body(
            await move_agent_rung(request, agent_id, MoveAsked(target=target, to=to), asked)
        )

    lowered = await pressed("shadow")
    if lowered.get("became") != "shadow":
        raise CheckFailedError("a department administrator could not lower an agent's rung")
    above = await pressed("autonomous")
    if above.get("message") != RAISING_BEYOND_THE_PUBLISHED_RUNG:
        raise CheckFailedError("a rung was pressed above the rung the agent was published at")
    at = await pressed("assisted")
    if at.get("message") != THE_EVIDENCE_DOES_NOT_MEET_THE_BAR:
        raise CheckFailedError(
            "a press to the published rung was not judged on its evidence, so the ceiling is "
            "refusing more than what is above it"
        )


# --------------------------------------- 3. who changes which part, and the role named (M39.8.1)
@check(
    leaves=("M39.8.1", "M33.8.3"),
    sentence=(
        "An agent's steward is refused switching its channels and attaching a connector, in "
        "sentences naming the role that may; the department's administrator switches the "
        "channels; a reader of the Connectors screen without its capability is refused "
        "disconnecting a source in a sentence naming it, and somebody who cannot open the screen "
        "is told nothing of a role."
    ),
)
async def a_steward_changes_no_channel_or_connector_and_the_role_is_named(
    h: Harness,
) -> None:
    from brain.agent_attachment_routes import (
        CHANGING_CONNECTORS_NEEDS_THE_CONNECTOR_ROLE,
        PressAsked,
        press_attachment,
    )
    from brain.agent_lifecycle_routes import ChannelsAsked, change_agent_channels
    from brain.connector_routes import disconnect
    from brain.core.errors import Absent
    from brain.gate.context import Channel
    from brain.ops.acceptance_agent_console import (
        _asking,
        _console,
        _readers,
        _request,
        a_department_administrator,
    )
    from brain.ops.acceptance_operations_console import asking_as, screen_grants
    from brain.ops.acceptance_workspace import installed_agent
    from brain.role_refusals import (
        CHANGING_CHANNELS_NEEDS_THE_DEPARTMENT_ADMINISTRATOR,
        CONNECTING_A_SOURCE_NEEDS_THE_CONNECTOR_CAPABILITY,
    )

    await h.found_departments()
    steward, reader, stranger = (h.principal(A, role) for role in ("steward", "reader", "stranger"))
    await h.person(steward, department=A, grants=_readers())
    await h.person(reader, department=A, grants=screen_grants("connectors"))
    await h.person(stranger, department=A)
    admin = await a_department_administrator(h)
    agent_id = await installed_agent(h, steward)
    request = _request(_console(h))
    now = [Channel.CONSOLE.value]

    async def switched(who: str) -> Any:
        return await change_agent_channels(
            request,
            agent_id,
            ChannelsAsked(channels=[*now, Channel.LARK.value], expected=now),
            await _asking(h, who, strong=True),
        )

    barred = await switched(steward)
    if (
        getattr(barred, "status_code", None) != 403
        or _body(barred).get("message") != CHANGING_CHANNELS_NEEDS_THE_DEPARTMENT_ADMINISTRATOR
    ):
        raise CheckFailedError("an agent's steward switched its channels, or was not told the role")
    if getattr(await switched(admin), "status_code", None) != 200:
        raise CheckFailedError("a department administrator could not switch an agent's channels")

    attached = await press_attachment(
        request,
        agent_id,
        PressAsked(part="connector", reference="freshdesk", attached=True),
        await _asking(h, steward, strong=True),
    )
    if (
        getattr(attached, "status_code", None) != 403
        or _body(attached).get("message") != CHANGING_CONNECTORS_NEEDS_THE_CONNECTOR_ROLE
    ):
        raise CheckFailedError("an agent's steward attached a connector, or was not told the role")

    told = await disconnect(request, "xero", await asking_as(h, reader, strong=True))
    if (
        getattr(told, "status_code", None) != 403
        or _body(told).get("message") != CONNECTING_A_SOURCE_NEEDS_THE_CONNECTOR_CAPABILITY
    ):
        raise CheckFailedError("a reader without the connector capability was not told it")
    try:
        await disconnect(request, "xero", await asking_as(h, stranger, strong=True))
    except Absent:
        return
    raise CheckFailedError("somebody who cannot open the Connectors screen was told of a role")


# --------------------------------------- 4. a department administrator stops one agent (M13.7.3)
@check(
    leaves=("M13.7.3",),
    sentence=(
        "A department's administrator stops one agent of their own department from the Stop "
        "screen, sees the stop listed and lifts it with a reason; an agent of another department "
        "is refused as an address that does not exist is."
    ),
)
async def a_department_admin_stops_one_agent_of_their_own_department(
    h: Harness,
) -> None:
    from brain.agents.model import AgentAudience
    from brain.console.reads import Plane, plane_capability
    from brain.core.errors import Absent
    from brain.halt_routes import ResumeAsked, StopAsked, halts, resume_now, stop_now
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_agent_console import _console, _request
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_operations_console import asking_as
    from brain.ops.acceptance_workspace import installed_agent
    from brain.ops.halt import HALT_CAPABILITY, HaltScope

    await h.found_departments()
    stopper, owner = h.principal(A, "stopper"), h.principal(A, "owner")
    other_owner = h.principal(B, "owner")
    stopping = (HALT_CAPABILITY.value, plane_capability(Plane.CONFIGURATION).value)
    await h.person(stopper, department=A, grants=_in(A, *stopping))
    await h.person(owner, department=A)
    await h.person(other_owner, department=B)
    own = await installed_agent(h, owner, suffix="_own")
    theirs = await installed_agent(
        h,
        other_owner,
        suffix="_theirs",
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=other_owner, department=B),
    )
    request = _request(_console(h))

    done = await stop_now(
        request,
        await asking_as(h, stopper, strong=True),
        StopAsked(scope=HaltScope.AGENT, target=own),
    )
    if getattr(done, "target", None) != own:
        raise CheckFailedError("a department administrator could not stop one of its own agents")
    try:
        await stop_now(
            request,
            await asking_as(h, stopper, strong=True),
            StopAsked(scope=HaltScope.AGENT, target=theirs),
        )
    except Absent:
        pass
    else:
        raise CheckFailedError("a department administrator stopped another department's agent")
    listed = await halts(request, await asking_as(h, stopper, strong=True))
    if [(one.scope, one.target) for one in listed.halts] != [(HaltScope.AGENT, own)]:
        raise CheckFailedError("the Stop screen did not list the stop its reader had made")
    lifted = await resume_now(
        request,
        await asking_as(h, stopper, strong=True),
        ResumeAsked(scope=HaltScope.AGENT, target=own, reason="the check is lifting its own stop"),
    )
    if getattr(lifted, "status_code", None) == 422:
        raise CheckFailedError("a department administrator could not lift the stop they made")


# ------------------------------------------- 5. the widget, for public knowledge only (M13.7.4)
@check(
    leaves=("M13.7.4",),
    sentence=(
        "The website widget is switched on for an agent whose ceiling reads nothing, and refused "
        "for an agent whose ceiling reads a field the policy classifies above public."
    ),
)
async def the_widget_is_offered_only_to_an_agent_reading_public_knowledge(
    h: Harness,
) -> None:
    from brain.agent_lifecycle_routes import ChannelsAsked, change_agent_channels
    from brain.core.field_policy import Classification
    from brain.gate.context import Channel
    from brain.ops.acceptance_agent_console import (
        _asking,
        _console,
        _readers,
        _request,
        a_department_administrator,
    )
    from brain.ops.acceptance_checks_agent_channels import _a_field_of
    from brain.ops.acceptance_workspace import installed_agent

    internal = _a_field_of(Classification.CONFIDENTIAL.value)
    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(steward, department=A, grants=_readers(internal))
    admin = await a_department_administrator(h)
    public = await installed_agent(h, steward, suffix="_public")
    reading = await installed_agent(h, steward, capabilities=(internal,), suffix="_internal")
    request = _request(_console(h))
    now = [Channel.CONSOLE.value]

    async def widget(agent_id: str) -> Any:
        return await change_agent_channels(
            request,
            agent_id,
            ChannelsAsked(channels=[*now, Channel.WIDGET.value], expected=now),
            await _asking(h, admin, strong=True),
        )

    if getattr(await widget(public), "status_code", None) != 200:
        raise CheckFailedError("the widget was not offered to an agent reading nothing")
    if getattr(await widget(reading), "status_code", None) == 200:
        raise CheckFailedError("the widget was offered to an agent reading more than public")


# ------------------------------------------ 6. the builder links what it does not hold (M20.1.1)
@check(
    leaves=("M20.1.1", "M13.9.1"),
    sentence=(
        "The builder's form answer names where the documents an agent reads, its workflows, its "
        "memory and its channels are set, each with a sentence, and none of them is a section of "
        "the saved definition."
    ),
)
async def the_builder_links_the_parts_of_an_agent_it_does_not_hold(h: Harness) -> None:
    from brain.agent_builder_routes import builder_form
    from brain.ops.acceptance_checks_builder import _builder
    from brain.ops.acceptance_checks_templates import _asking, _gallery, _request

    builder = await _builder(h, "linker")
    form_app = _gallery(h, secrets.token_hex(32))
    answer = _body(await builder_form(_request(form_app), await _asking(h, builder)))
    linked = answer.get("set_elsewhere") or []
    if [one.get("part") for one in linked] != ["knowledge", "workflows", "memory", "channels"]:
        raise CheckFailedError("the builder did not name where each part it does not hold is set")
    if any(not str(one.get("sentence", "")).strip() for one in linked):
        raise CheckFailedError("a part the builder links to was named with no words")
    sections = {one.get("section") for one in answer.get("sections", [])}
    if sections & {"workflows", "memory", "channels"}:
        raise CheckFailedError("a part set elsewhere was made a section of the saved definition")
