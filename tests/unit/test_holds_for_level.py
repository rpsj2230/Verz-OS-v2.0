"""Who may decide a publication to a department and who to the whole company (M20.5.1).

A department's administrator holds the approving authority over their department and a Super Admin
over everything, and the company is a different decision from a department: telling every
department about something is not within the authority to tell one. One function,
`brain.knowledge.visibility.holds_for_level`, asks it for agents and for knowledge, and these hold
the function, the two doors that ask it, and the console surface that offers the control.

Task ids: M20.5.1
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.agents.lifecycle import AGENT_PUBLICATION_CAPABILITY, publish
from brain.agents.model import AgentAudience, AgentAuthority, AgentError, AgentRecord
from brain.console.global_surfaces import may_publish
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.visibility import (
    PROMOTION_CAPABILITY,
    Visibility,
    VisibilityError,
    approve_promotion,
    holds_for_level,
    propose_promotion,
)

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2019, 6, 1, 9, 0, tzinfo=UTC)
REVIEW = datetime(2999, 1, 1, tzinfo=UTC)
CAPABILITY = PROMOTION_CAPABILITY


def holding(
    scope: Scope, capability: Capability = CAPABILITY, who: str = "u_holder"
) -> EntitlementSet:
    return EntitlementSet(principal_id=who, grants=(Grant(capability=capability, scope=scope),))


EVERYWHERE = Scope.unrestricted()
WEB = Scope.department("web")


def test_the_company_needs_the_capability_held_over_everything() -> None:
    """A department's administrator holds the capability in their department and is refused the
    company; the person who holds it over everything is admitted; nobody holding nothing is.

    Delete this and a department-scoped grant publishes to every department at once."""
    assert holds_for_level(holding(EVERYWHERE), CAPABILITY, Visibility.COMPANY, NOW)
    assert not holds_for_level(holding(WEB), CAPABILITY, Visibility.COMPANY, NOW)
    assert not holds_for_level(
        EntitlementSet(principal_id="u_none"), CAPABILITY, Visibility.COMPANY, NOW
    )


def test_a_department_needs_it_held_over_that_department_when_the_department_is_named() -> None:
    """Held in web admits web and refuses finance; held over everything admits both; with no
    department named any holding at all admits, because the row question is the caller's.

    Delete this and a department's administrator publishes into another department."""
    in_web = holding(WEB)
    assert holds_for_level(in_web, CAPABILITY, Visibility.DEPARTMENT, NOW, department="web")
    assert not holds_for_level(in_web, CAPABILITY, Visibility.DEPARTMENT, NOW, department="finance")
    assert holds_for_level(
        holding(EVERYWHERE), CAPABILITY, Visibility.DEPARTMENT, NOW, department="finance"
    )
    assert holds_for_level(in_web, CAPABILITY, Visibility.DEPARTMENT, NOW)


def test_a_personal_level_needs_no_authority_beyond_holding_the_capability_at_all() -> None:
    """The narrowest level is the owner's own, so the scope of the holding is not the question,
    and a person holding nothing is still refused.

    Delete this and a personal publication is held to a company-wide standard."""
    assert holds_for_level(holding(WEB), CAPABILITY, Visibility.PERSONAL, NOW)
    assert not holds_for_level(
        EntitlementSet(principal_id="u_none"), CAPABILITY, Visibility.PERSONAL, NOW
    )


def _proposal(to_level: Visibility, from_level: Visibility = Visibility.DEPARTMENT):  # type: ignore[no-untyped-def]
    return propose_promotion(
        item_id="handbook",
        from_level=from_level,
        to_level=to_level,
        proposer_id="u_proposer",
        owner_id="u_owner",
        review_by=REVIEW,
        reason="Everybody needs the handbook.",
        now=NOW,
    )


def test_a_department_admin_cannot_approve_a_knowledge_item_to_the_whole_company() -> None:
    """The promotion to the company is refused to somebody holding the promotion authority in a
    department, in words naming the scope and not the item, and approved for the holder over
    everything. A promotion to a department is still approved by a holder in a department.

    Delete this and a department's administrator widens a document to the company alone."""
    to_company = _proposal(Visibility.COMPANY)
    with pytest.raises(VisibilityError, match="over what a promotion to company reaches"):
        approve_promotion(
            to_company, approver_id="u_admin", entitlement=holding(WEB, who="u_admin"), now=NOW
        )
    approval = approve_promotion(
        to_company, approver_id="u_super", entitlement=holding(EVERYWHERE, who="u_super"), now=NOW
    )
    assert approval.to_level is Visibility.COMPANY

    to_department = _proposal(Visibility.DEPARTMENT, Visibility.PERSONAL)
    assert (
        approve_promotion(
            to_department, approver_id="u_admin", entitlement=holding(WEB, who="u_admin"), now=NOW
        ).to_level
        is Visibility.DEPARTMENT
    )


def _agent(owner: str = "u_steward") -> AgentRecord:
    """A department's agent, which its steward asks to have published to the company."""
    return AgentRecord.model_validate(
        {
            "agent_id": "support_triage",
            "display_name": "Support triage",
            "persona": "Answers support questions in the house voice.",
            "audience": AgentAudience(
                level=Visibility.DEPARTMENT, owner_id=owner, department="web"
            ),
            "authority": AgentAuthority(
                scope=WEB, capabilities=(Capability(value="read:client.name"),)
            ),
            "created_by": owner,
        }
    )


def test_a_department_admin_cannot_publish_an_agent_to_the_whole_company() -> None:
    """The agent's own door: a holder of the publication capability in a department is refused in
    words, the holder over everything publishes it, and the steward still cannot.

    Delete this and one department's administrator tells every department an agent exists."""
    record = _agent()
    with pytest.raises(AgentError, match="over the whole company"):
        publish(
            record,
            publisher=holding(WEB, AGENT_PUBLICATION_CAPABILITY, "u_admin"),
            now=NOW,
        )
    published = publish(
        record,
        publisher=holding(EVERYWHERE, AGENT_PUBLICATION_CAPABILITY, "u_super"),
        now=NOW,
    )
    assert published.audience == AgentAudience(level=Visibility.COMPANY, owner_id="u_steward")


def test_the_console_offers_the_company_publication_only_to_who_could_make_it() -> None:
    """The control the console draws is the question the door asks, so a department's
    administrator is not offered a button that would be refused.

    Delete this and the screen offers what the route refuses."""
    assert may_publish(holding(EVERYWHERE, AGENT_PUBLICATION_CAPABILITY), NOW)
    assert not may_publish(holding(WEB, AGENT_PUBLICATION_CAPABILITY), NOW)
