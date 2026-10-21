"""The starters route: who may ask it, what it answers, and the one refusal.

The handler is called with the agent store and the run stood in, because what is under test is the
route's decisions; the starters themselves are `test_member_starters.py`'s.

Task ids: M40.7.8
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from brain import member_starter_routes
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.gate.model_lane import AgentRun
from brain.member_starter_routes import MemberStartersView, agent_starters, router
from brain.tools.skills import SkillPin
from tests.unit.test_member_starters import skill_text
from tests.unit.test_skill_library import AGENT, a_registry, an_approved_skill, an_install

NOW = datetime(2999, 1, 1, tzinfo=UTC)
MEMBER = tuple(
    Grant(capability=Capability(value=one), scope=Scope.unrestricted())
    for one in ("read:member.home", "read:member.content", "read:client.name")
)


def asked(*, member: bool = True, department: str | None = None) -> Any:
    grants = MEMBER if member else ()
    return SimpleNamespace(
        caller=SimpleNamespace(
            principal=SimpleNamespace(id="u_member", primary_department=department)
        ),
        reach=EntitlementSet(principal_id="u_member", grants=grants),
        now=NOW,
    )


def a_request(*, on: bool = True) -> Any:
    state = SimpleNamespace(tools=a_registry(), agent_starter_prompts_on=on)
    return SimpleNamespace(app=SimpleNamespace(state=state))


class Lifecycles:
    def __init__(self, record: Any | None) -> None:
        self.record = record

    async def agent(self, agent_id: str) -> Any:
        if self.record is None or self.record.agent_id != agent_id:
            return None
        return SimpleNamespace(record=self.record)


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> Any:
    skill = an_approved_skill(skill_text())
    _, _, record = an_install()
    run = AgentRun(
        record=record,
        pins=(SkillPin(agent_id=AGENT, skill_name=skill.name, digest=skill.digest),),
        library=(skill,),
        registry=a_registry(),
    )
    monkeypatch.setattr(member_starter_routes, "lifecycles_of", lambda request: Lifecycles(record))

    async def run_of(state: Any, found: Any, registry: Any, trying: Any = None) -> AgentRun:
        return run

    monkeypatch.setattr(member_starter_routes, "agent_run_of", run_of)
    return record


def call(request: Any, agent_id: str, who: Any) -> MemberStartersView:
    return asyncio.run(agent_starters(request, agent_id, who))


def test_a_member_is_offered_the_starters_of_an_agent_they_may_run(agent: Any) -> None:
    """The positive case for the refusals below. Delete this and a route that refused everyone
    passes them all."""
    assert call(a_request(), AGENT, asked()).prompts == ["When does this client's hosting expire?"]


def test_a_caller_without_the_member_grant_an_unknown_agent_and_a_disabled_one_get_one_answer(
    agent: Any,
) -> None:
    """The refusal is the same sentence for all three, so the route cannot be used to ask which
    agents exist. Delete this and a different sentence for one tells a person it is there."""
    refusals = set()
    for who, agent_id in ((asked(member=False), AGENT), (asked(), "no-such-agent")):
        with pytest.raises(Absent) as refused:
            call(a_request(), agent_id, who)
        refusals.add(str(refused.value))
    assert refusals == {"starter prompts are not answerable for this caller"}


def test_a_disabled_agent_is_refused_as_one_that_does_not_exist(
    agent: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visible is not enough: an agent switched off answers nobody, and offering starters for it
    would say it is there. Delete this and a disabled agent still gives its prompts."""
    off = agent.model_copy(update={"disabled_at": NOW})
    monkeypatch.setattr(member_starter_routes, "lifecycles_of", lambda request: Lifecycles(off))
    with pytest.raises(Absent) as refused:
        call(a_request(), AGENT, asked())
    assert str(refused.value) == "starter prompts are not answerable for this caller"


def test_with_the_switch_off_the_answer_is_the_empty_list_an_agent_without_examples_gives(
    agent: Any,
) -> None:
    """An off switch is not a finding. Delete this and a switch turned off reads differently from
    an agent with nothing to offer."""
    assert call(a_request(on=False), AGENT, asked()).prompts == []


def test_a_person_whose_reach_does_not_cover_the_tool_is_offered_none(agent: Any) -> None:
    """The route asks the run's reach, not the skill's text. Delete this and the prompts are the
    same for everyone who may open the agent."""
    no_client = SimpleNamespace(
        caller=asked().caller,
        reach=EntitlementSet(principal_id="u_member", grants=MEMBER[:2]),
        now=NOW,
    )
    assert call(a_request(), AGENT, no_client).prompts == []


def test_the_answer_carries_prompts_and_nothing_else_and_the_route_is_one_read() -> None:
    """No count, no skill name, no reason. Delete this and a field beside the prompts could say
    how many were withheld."""
    assert set(MemberStartersView.model_fields) == {"prompts"}
    from fastapi.routing import APIRoute

    routes = [
        (sorted(one.methods or ()), one.path) for one in router.routes if isinstance(one, APIRoute)
    ]
    assert routes == [(["GET"], "/api/v1/me/agents/{agent_id}/starters")]
