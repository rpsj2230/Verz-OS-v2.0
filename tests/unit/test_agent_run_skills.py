"""An agent's run reads its assigned skills and its model tier (M27.12.1).

Pure: the cards a run offers and the tier it routes on, from the objects the console already builds.
"""

from __future__ import annotations

from brain.gate.model_lane import AgentRun, skill_cards, tier_for
from brain.models.driver import DriverMessage, Role
from brain.models.routing import Tier
from brain.tools.skills import SkillPin
from tests.unit.test_skill_library import (
    AGENT,
    NOW,
    a_registry,
    an_approved_skill,
    an_install,
    reach,
    text_with,
)

ONE_TOOL = text_with(tools="[crm.read_client]")


def a_run(*, pinned: bool = True) -> AgentRun:
    one = an_approved_skill(ONE_TOOL)
    _, _, record = an_install()
    pins = (SkillPin(agent_id=AGENT, skill_name=one.name, digest=one.digest),) if pinned else ()
    return AgentRun(record=record, pins=pins, library=(one,), registry=a_registry())


def test_a_skill_assigned_to_the_agent_is_offered_as_a_card() -> None:
    """Delete this and a run that offers nothing satisfies every refusal below."""
    cards = skill_cards(a_run(), caller=reach("read:client.name"), now=NOW)
    assert [one.name for one in cards] == ["hosting-expiry"]


def test_a_detached_skill_is_not_offered() -> None:
    """Delete this and a skill removed from the agent keeps reaching its prompt."""
    assert skill_cards(a_run(pinned=False), caller=reach("read:client.name"), now=NOW) == ()


def test_a_skill_needing_a_tool_outside_the_callers_reach_is_not_offered() -> None:
    """Delete this and a caller is taught a procedure their own reach cannot run."""
    assert skill_cards(a_run(), caller=reach(), now=NOW) == ()


def test_a_heavy_tier_agent_routes_to_the_heavy_chain() -> None:
    """Delete this and the stored tier is ignored again and the byte bound picks the chain."""
    messages = (DriverMessage(role=Role.USER, content="short"),)
    assert tier_for(messages) is not Tier.HEAVY
    assert tier_for(messages, Tier.HEAVY) is Tier.HEAVY
