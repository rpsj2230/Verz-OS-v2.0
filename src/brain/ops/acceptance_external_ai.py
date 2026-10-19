"""The install acceptance check for an outside AI service registered as a tool (M12.3.7).

One check, over the product's own pieces inside the check's transaction. A stand-in service is
declared the way a screen would declare one, the feature's switch is pressed both ways through the
Features route and never assumed, and the registry the application would build is asked what it
holds and who is offered it.

**What is checked.**
- With the switch off the declared service is not registered, whatever else is declared on the
  install; with it on it is, as a tool whose capability is the service's own, counted as sending
  something out and capped at Assisted.
- An agent whose ceiling names the tool and allows a send is offered it to a member holding the
  service's permission, and to nobody else: a member without the permission is offered nothing, and
  an agent that does not name the tool, or whose ceiling allows less than a send, is offered nothing
  to the member who holds it.
- Called directly, the tool refuses in one sentence and nothing leaves: no request is made and no
  key is read, because there is no code that does either.

**The stand-in's address is a reserved test name and is never called.** There is no call to make:
the leaf is the registration and the refusal, and the call waits for the owner to name a first
service (needs-rupash 184). What this proves on an install is that the declaration is read back,
the switch is honoured and the catalogue refuses the way the leaf says.

**Nothing is assumed about what else the install declared.** The install may already hold services
and may already have the switch on, so the check filters by its own service's name and presses the
switch to a state it states.

Task ids: M12.3.7
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final, cast

from brain.core.entitlement import Capability
from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, traced
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from brain.core.envelope import TypedResult

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2360

A, _B = RESERVED_DEPARTMENTS

#: The authority that presses a feature's switch. Restated rather than imported, so a change to the
#: route's authority fails this check instead of moving with it.
SWITCHES_FEATURES: Final = "admin:feature"

#: A reserved test address: nothing can be listening there and nothing is ever sent to it.
STAND_IN_ADDRESS: Final = "https://ai.example.test/v1/stand-in"

SWITCH_IGNORED: Final = "a service was registered while outside services were switched off"
NOT_REGISTERED: Final = "a declared service was not registered with the switch on"
WRONG_CAPABILITY: Final = "a registered service did not need its own permission"
WRONG_CLASS: Final = "a registered service did not count as sending something out"
NOT_CAPPED: Final = "a registered service could be given a rung above Assisted"
NOT_OFFERED: Final = "an agent that names a service and may send was not offered it"
OFFERED_UNNAMED: Final = "a service was offered through an agent whose ceiling does not name it"
OFFERED_TO_A_SMALL_CEILING: Final = "a service was offered to an agent that may not send"
OFFERED_WITHOUT_PERMISSION: Final = "a service was offered to a member without its permission"
CALLED: Final = "a registered service was called instead of refused"
NOT_ONE_SENTENCE: Final = "a refused call was not answered with the one sentence"


async def _pressed(h: Harness, switcher: str, *, on: bool, n: int) -> None:
    """The feature's switch, through the Features route, as the administrator presses it."""
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.ops.features_declared.external_ai_services import EXTERNAL_AI_SERVICES

    async with traced(h, n):
        await switch_feature(
            console_for(h).request("POST"),
            EXTERNAL_AI_SERVICES.name,
            SwitchAsked(on=on),
            await asking_as(h, switcher, strong=True),
        )


@check(
    leaves=("M12.3.7",),
    sentence=(
        "An outside AI service the install declares is registered as a tool only while its switch "
        "is on, needs a permission of its own and counts as sending something out, capped at "
        "Assisted; it is offered through an agent that names it and may send, to a member holding "
        "the permission and to nobody else, and a call is refused in one sentence."
    ),
)
async def an_outside_service_is_offered_only_to_agents_that_name_it(
    h: Harness,
) -> None:
    from brain.agents.model import tool_ceiling
    from brain.agents.template import ManifestGuardrails
    from brain.console.workspace_capabilities import run_reach
    from brain.core.envelope import SideEffect
    from brain.core.errors import Denied
    from brain.gate.catalogue import project
    from brain.gate.injection import AutonomyTier
    from brain.ops.acceptance_workspace import installed_agent, stored_agent
    from brain.ops.external_ai_store import declared_if_on, record_service
    from brain.tools.external_ai import (
        OUTSIDE_SERVICES_ARE_NOT_CALLED_YET,
        ExternalAiService,
        ServiceAsked,
        tool_name_of,
    )
    from brain.tools.registry import leash_ceiling
    from brain.tools.startup import build_registry

    await h.found_departments()
    switcher, holder, stranger = (
        h.principal(A, "switcher"),
        h.principal(A, "holder"),
        h.principal(A, "stranger"),
    )
    name = re.sub(r"[^a-z0-9_]", "", f"acceptance_{h.run}".lower())[:30]
    declared = ExternalAiService(
        service=name,
        does="Draws a picture from a sentence",
        kind="image_generation",
        endpoint=STAND_IN_ADDRESS,
    )
    # The capability is spelled out here and not imported, so a change to how the product derives it
    # fails this check instead of moving with it.
    tool, capability = tool_name_of(name), Capability(value=f"invoke:external_ai.{name}")
    await h.person(switcher, department=A, grants=((SWITCHES_FEATURES, Scope.unrestricted()),))
    await h.person(holder, department=A, grants=((capability.value, Scope.department(A)),))
    await h.person(stranger, department=A, grants=())
    async with h.sessions() as session:
        await record_service(
            session, declared, actor=switcher, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        )
        await session.commit()

    async def registered_now() -> tuple[str, ...]:
        found = await declared_if_on(h.sessions)
        return build_registry(source=h.settings.tool_source, external_ai=found).names()

    # The switch, both ways, whatever state the install was in.
    await _pressed(h, switcher, on=False, n=1)
    if tool in await registered_now():
        raise CheckFailedError(SWITCH_IGNORED)
    await _pressed(h, switcher, on=True, n=2)
    registry = build_registry(
        source=h.settings.tool_source, external_ai=await declared_if_on(h.sessions)
    )
    if tool not in registry.names():
        raise CheckFailedError(NOT_REGISTERED)

    registered = registry.get(tool)
    if registered.capability != capability or registered.definition.required_capability != (
        capability.value
    ):
        raise CheckFailedError(WRONG_CAPABILITY)
    if registered.definition.side_effect is not SideEffect.SEND:
        raise CheckFailedError(WRONG_CLASS)
    if leash_ceiling(registered.definition) is not AutonomyTier.ASSISTED:
        raise CheckFailedError(NOT_CAPPED)

    # Who is offered it: an agent that names it and may send, an agent that does not name it, and
    # one that names it and may not send.
    naming = await installed_agent(
        h,
        switcher,
        capabilities=(capability.value,),
        allowed_tools=(tool,),
        guardrails=ManifestGuardrails(max_side_effect=SideEffect.SEND),
        suffix="_outside_named",
    )
    unnamed = await installed_agent(
        h,
        switcher,
        capabilities=(capability.value,),
        allowed_tools=(),
        guardrails=ManifestGuardrails(max_side_effect=SideEffect.SEND),
        suffix="_outside_unnamed",
    )
    small = await installed_agent(
        h,
        switcher,
        capabilities=(capability.value,),
        allowed_tools=(tool,),
        suffix="_outside_small",
    )
    members = {one: await h.reach(one) for one in (holder, stranger)}

    async def names_for(agent: str, member: str) -> tuple[str, ...]:
        record = await stored_agent(h, agent)
        return project(
            registry, run_reach(members[member], record), tool_ceiling(record), now=h.now
        ).names

    if tool not in await names_for(naming, holder):
        raise CheckFailedError(NOT_OFFERED)
    if tool in await names_for(unnamed, holder):
        raise CheckFailedError(OFFERED_UNNAMED)
    if tool in await names_for(small, holder):
        raise CheckFailedError(OFFERED_TO_A_SMALL_CEILING)
    if tool in await names_for(naming, stranger):
        raise CheckFailedError(OFFERED_WITHOUT_PERMISSION)

    # A direct call is refused in one sentence, and nothing is sent because nothing sends.
    call = cast("Callable[..., Awaitable[TypedResult[Any]]]", registry.get(tool).handler)
    try:
        await call(ServiceAsked(instruction="draw a cat"), entitlement=members[holder], now=h.now)
    except Denied as refused:
        if str(refused) != OUTSIDE_SERVICES_ARE_NOT_CALLED_YET:
            raise CheckFailedError(NOT_ONE_SENTENCE) from refused
    else:
        raise CheckFailedError(CALLED)
