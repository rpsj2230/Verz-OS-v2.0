"""A browser skill is refused for a website that has an API tool, unless an exemption names it.

The rule is `brain.browsing.skill_gate.load_gaps`, asked at assignment of the websites the
agent's own scope reaches (`brain.console.skill_library.browser_refusals`). These tests hold the
wiring: which skills count as browser skills, which websites are asked about, that the registry
decides whether the alternative exists, and that a live exemption (and no other) lets the
assignment through.

Task ids: M19.6.7
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from brain.agents.model import AgentRecord
from brain.agents.template import SignedManifest, TemplateInstance
from brain.audit.ledger import AuditChain
from brain.browsing.sessions import ACT_ON_SURFACE, READ_SURFACE, surface_scope
from brain.browsing.skill_gate import Exemption
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.console.skill_library import (
    SKILL_AUTHORITY,
    BrowserNeeds,
    SkillLibraryError,
    assignment,
    browser_refusals,
)
from brain.core.entitlement import Capability
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
from brain.core.scope import Scope
from brain.tools.registry import ToolRegistry
from brain.tools.skills import Skill, skill_from_markdown
from tests.unit.test_skill_knowledge import an_agent
from tests.unit.test_skill_library import (
    NOW,
    _tickets,
    a_recorder,
    an_approved_skill,
    reach,
    text_with,
)

ORIGIN = "https://books.example"
API = "ledger.list_invoices"


def books(*, api: tuple[str, ...] = (API,)) -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=Capability(value="read:browser_surface"),
                reads=("number",),
            ),
        ),
        api_tools=api,
    )


def tools(*, with_api: bool = True) -> ToolRegistry:
    """A registry that holds the API tool a website names, or does not."""
    registry = ToolRegistry()
    if with_api:
        registry.register(
            ToolDefinition(
                name=API,
                description="Lists invoices",
                entity="ticket",
                required_capability="read:ticket.status",
                identity_mode=IdentityMode.DELEGATED,
                side_effect=SideEffect.NONE,
            ),
            _tickets,
        )
    return registry


def needs(
    *, with_api: bool = True, exemptions: tuple[Exemption, ...] = (), api: tuple[str, ...] = (API,)
) -> BrowserNeeds:
    return BrowserNeeds(
        targets=TargetRegistry(targets=(books(api=api),)),
        tools=tools(with_api=with_api),
        exemptions=exemptions,
    )


def a_browser_skill(tool: str = READ_SURFACE.name) -> Skill:
    return skill_from_markdown(text_with(tools=f"[{tool}]"))


def exemption(**kw: Any) -> Exemption:
    base: dict[str, Any] = {
        "skill": "hosting-expiry",
        "target": "books",
        "approver": "u_head_of_finance",
        "expires_at": NOW + timedelta(days=30),
        "reason": "the connector has no filing page yet",
    }
    base.update(kw)
    return Exemption(**base)


def agent_over(scope: Scope) -> tuple[SignedManifest, TemplateInstance, AgentRecord]:
    return an_agent(scope=scope, allowed=())


def refusals(skill: Skill, scope: Scope, browser: BrowserNeeds) -> tuple[str, ...]:
    return browser_refusals(skill, scope, browser, NOW)


def test_a_browser_skill_is_refused_for_a_website_whose_api_tool_exists() -> None:
    """The positive case for the rule, with the finding naming both. Delete this and the loader
    that was written to refuse this is a function nothing calls."""
    found = refusals(a_browser_skill(), surface_scope(books()), needs())

    assert len(found) == 1 and "books" in found[0] and API in found[0]


@pytest.mark.parametrize("tool", [READ_SURFACE.name, ACT_ON_SURFACE.name])
def test_either_browser_tool_makes_a_skill_a_browser_skill(tool: str) -> None:
    """Delete this and a skill that only writes is not a browser skill, or one that only reads is
    not."""
    assert refusals(a_browser_skill(tool), surface_scope(books()), needs())


def test_a_skill_that_names_no_browser_tool_is_never_refused_by_this_rule() -> None:
    """Delete this and every skill is a browser skill the day a website with an API is declared."""
    assert (
        refusals(
            skill_from_markdown(text_with(tools="[crm.read_client]")), Scope.unrestricted(), needs()
        )
        == ()
    )


def test_an_api_that_is_planned_and_not_registered_is_not_a_reason_to_refuse() -> None:
    """The registry decides, not the declaration. Delete this and a website that merely names a
    tool it hopes to have blocks the only route to it."""
    assert refusals(a_browser_skill(), surface_scope(books()), needs(with_api=False)) == ()


def test_a_website_with_no_api_tool_declared_is_never_refused() -> None:
    """Delete this and every browser skill is refused for a website that has no alternative."""
    assert refusals(a_browser_skill(), surface_scope(books()), needs(api=())) == ()


def test_only_the_websites_the_agents_own_scope_reaches_are_asked_about() -> None:
    """An agent scoped to another website is not refused over this one, and an unrestricted agent,
    which narrows nothing, is. Delete this and the rule is either never asked of the agents that
    matter or asked of agents that could not reach the website."""
    elsewhere = Scope.department("sales")

    assert refusals(a_browser_skill(), elsewhere, needs()) == ()
    assert refusals(a_browser_skill(), Scope.unrestricted(), needs())


def test_a_live_exemption_for_this_skill_and_this_website_lets_the_assignment_through() -> None:
    """All three halves must match: the skill, the website and the clock. Delete this and an
    exemption for another skill, another website or one that has lapsed is honoured."""
    scope = surface_scope(books())

    assert refusals(a_browser_skill(), scope, needs(exemptions=(exemption(),))) == ()
    assert refusals(a_browser_skill(), scope, needs(exemptions=(exemption(skill="other"),)))
    assert refusals(a_browser_skill(), scope, needs(exemptions=(exemption(target="elsewhere"),)))
    lapsed = exemption(expires_at=NOW - timedelta(seconds=1))
    assert refusals(a_browser_skill(), scope, needs(exemptions=(lapsed,)))


def test_assignment_refuses_the_skill_and_records_nothing_and_an_exemption_lets_it_through() -> (
    None
):
    """The whole path. Delete this and the gate is a function that is right and is not what
    assignment asks."""
    one = an_approved_skill(text_with(tools=f"[{READ_SURFACE.name}]"))
    signed, instance, record = agent_over(Scope.unrestricted())
    chain = AuditChain()

    with pytest.raises(SkillLibraryError) as refused:
        assignment(
            one,
            record=record,
            signed=signed,
            instance=instance,
            library=(one,),
            by=reach(SKILL_AUTHORITY.value),
            recorder=a_recorder(chain),
            now=NOW,
            browser=needs(),
        )
    assert "nothing was assigned" in str(refused.value) and API in str(refused.value)
    assert chain.entries == ()

    made = assignment(
        one,
        record=record,
        signed=signed,
        instance=instance,
        library=(one,),
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(AuditChain()),
        now=NOW,
        browser=needs(exemptions=(exemption(),)),
    )
    assert made.skill_name == "hosting-expiry"


def test_assignment_without_a_browser_rule_is_the_assignment_it_always_was() -> None:
    """A route with no database hands none, so nothing changes for it. Delete this and a missing
    rule refuses everything."""
    one = an_approved_skill(text_with(tools=f"[{READ_SURFACE.name}]"))
    signed, instance, record = agent_over(Scope.unrestricted())

    made = assignment(
        one,
        record=record,
        signed=signed,
        instance=instance,
        library=(one,),
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(AuditChain()),
        now=NOW,
    )

    assert made.skill_name == "hosting-expiry"
