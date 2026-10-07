"""Install check for the channels an agent is offered on and the switch that enables one.

An agent's page lists the surfaces a run of it could be carried on, and the agent's steward switches
one on. The two are one rule asked twice: a surface is offered, and may be switched on, only when it
can carry the most sensitive thing the run could return, which is `E_run(caller, agent)` read
against the product's own field policy and each adapter's own declaration of what it may carry
(`brain.console.workspace_capabilities.offered_channels`). The unit tests run the rule over a
hand-made policy. What they cannot show is that, on an install, over the product's real policy and
the adapters it really ships, an agent reaching nothing sensitive is offered every surface, one
reaching a confidential field only the surface that can carry it, and that the steward's switch
refuses what the page does not offer.

**The agents are told apart by what their ceiling reaches, and the check names the field from the
policy itself.** It does not write out which field is confidential: it reads the product's field
policy and takes the first field of that class, so a policy that reclassified a field moves the
check with it, and a policy with none says so by not being run rather than passing an empty case.
A restricted field is not asked: an agent's ceiling does not carry one, so no agent reaches it.

**What the agent is offered is asked of the page's own route, and the switch of the lifecycle
route.** The offered surfaces are `agent_workspace`'s `channels`, read as a person who may open the
agent; the switch is `change_agent_channels` as the agent's steward, which answers 200 with the
channels now enabled or a refusal in words that name no surface.

Task ids: M39.2.4.1, M39.2.4.2
"""

from __future__ import annotations

import json
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_agent_console import _asking, _console, _readers, _request
from brain.ops.acceptance_run import Harness
from brain.ops.acceptance_workspace import installed_agent

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 835

A, B = RESERVED_DEPARTMENTS

NO_FIELD_OF_THAT_CLASS: Final = (
    "the product's field policy has no field of one of the classes this check needs, so what an "
    "agent reaching one is offered cannot be asked"
)
OFFERED_LESS_THAN_THE_ADAPTERS_CARRY: Final = (
    "an agent reaching nothing sensitive was not offered every surface the install ships"
)
OFFERED_PAST_THE_CEILING: Final = (
    "an agent was offered a surface that cannot carry the most sensitive field it reaches"
)
NOT_OFFERED_WHAT_CAN_CARRY_IT: Final = (
    "an agent was not offered a surface that can carry the most sensitive field it reaches"
)
NOT_SWITCHED_ON: Final = "an agent's steward could not switch on a surface the page offers"
SWITCHED_ON_PAST_THE_CEILING: Final = (
    "an agent's steward switched on a surface the page does not offer for it"
)


async def _offered(h: Harness, reader: str, agent_id: str) -> set[str]:
    from brain.agent_routes import agent_workspace

    answer = await agent_workspace(_request(_console(h)), agent_id, await _asking(h, reader))
    return {one.channel for one in answer.channels}


def _a_field_of(rank: str) -> str:
    """The capability of the first field of this classification in the product's policy."""
    from brain.agent_routes import product_field_policy

    found = sorted(
        one.required_capability.value
        for one in product_field_policy().rules
        if one.classification.value == rank
    )
    if not found:
        raise CheckNotRunError(NO_FIELD_OF_THAT_CLASS)
    return found[0]


async def _switch_on(h: Harness, steward: str, agent_id: str, channel: str, now: list[str]) -> Any:
    from brain.agent_lifecycle_routes import ChannelsAsked, change_agent_channels

    return await change_agent_channels(
        _request(_console(h)),
        agent_id,
        ChannelsAsked(channels=[*now, channel], expected=now),
        await _asking(h, steward, strong=True),
    )


@check(
    leaves=("M39.2.4.1", "M39.2.4.2"),
    sentence=(
        "An agent reaching nothing sensitive is offered every surface the install ships and one "
        "reaching a confidential field only the surfaces that can carry it; its steward can "
        "switch on a surface the page offers and is refused one it does not."
    ),
)
async def a_surface_is_offered_only_if_it_can_carry_the_agent(
    h: Harness,
) -> None:
    from brain.agent_routes import declared_channels
    from brain.core.field_policy import Classification
    from brain.gate.context import Channel

    confidential = _a_field_of(Classification.CONFIDENTIAL.value)
    await h.found_departments()
    steward = h.principal(A, "steward")
    # What the steward reaches is what the agents' ceilings are narrowed against.
    await h.person(steward, department=A, grants=_readers(confidential))
    plain = await installed_agent(h, steward, suffix="_plain")
    careful = await installed_agent(h, steward, capabilities=(confidential,), suffix="_conf")

    shipped = {one.channel.value for one in declared_channels()}
    carries = {
        one.channel.value
        for one in declared_channels()
        if one.may_carry(Classification.CONFIDENTIAL)
    }
    everything = await _offered(h, steward, plain)
    if everything != shipped:
        raise CheckFailedError(OFFERED_LESS_THAN_THE_ADAPTERS_CARRY)
    narrowed = await _offered(h, steward, careful)
    if not narrowed <= carries:
        raise CheckFailedError(OFFERED_PAST_THE_CEILING)
    if narrowed != carries:
        raise CheckFailedError(NOT_OFFERED_WHAT_CAN_CARRY_IT)

    # The switch follows the page: an offered surface goes on, one the page does not offer is
    # refused as a refusal and not as a stale page, and nothing changes.
    now = [Channel.CONSOLE.value]
    onto = sorted(narrowed - set(now))
    if onto:
        done = await _switch_on(h, steward, careful, onto[0], now)
        if done.status_code != 200 or sorted(json.loads(bytes(done.body))["channels"]) != sorted(
            [*now, onto[0]]
        ):
            raise CheckFailedError(NOT_SWITCHED_ON)
        now = sorted([*now, onto[0]])
    withheld = sorted(shipped - narrowed - set(now))
    if not withheld:
        raise CheckNotRunError(NO_FIELD_OF_THAT_CLASS)
    refused = await _switch_on(h, steward, careful, withheld[0], now)
    if refused.status_code == 200 or json.loads(bytes(refused.body)).get("outcome") != "refused":
        raise CheckFailedError(SWITCHED_ON_PAST_THE_CEILING)
