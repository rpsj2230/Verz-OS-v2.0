"""What accepting a new template version needs, asked the way installing it is (M13.8.11).

`tests/unit/test_agent_upgrade.py` holds the upgrade's diff, its resolutions and its declines, and
the tool and connector halves of the settle an acceptance finishes through. These hold the half
that file stated as a gap: a version that asks a question the pinned one did not, and the review
that says what an acceptance will leave missing before anybody presses it.

Task ids: M13.8.11
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from brain.agents.install import Missing, MissingKind
from brain.agents.template import Placeholder, SignedManifest, publish
from brain.agents.upgrade import (
    Declines,
    Resolution,
    UpgradeReview,
    accept,
    needs_after,
    newly_required_placeholders,
    review,
)
from brain.connectors.registry import ConnectorRegistry
from brain.tools.registry import ToolRegistry
from tests.unit.test_agent_upgrade import (
    ACCEPTER,
    AUDIENCE,
    DECLARED_TOOL,
    KEY,
    LATER,
    LATER_STILL,
    PUBLISHER,
    SECOND_PERSONA,
    _connectors,
    _contract_tools,
    _installed,
    _manifest,
    _shelved,
    _signed,
)

#: The question version one already asks, which `_manifest` declares and nothing answers.
OLD_QUESTION = "finance_contact"
NEW_QUESTION = "renewal_price_list"


def _asking(*questions: Placeholder, version: int = 2) -> SignedManifest:
    """Version two of the template, asking exactly these questions and nothing else new."""
    document = _manifest(version=version, allowed=(DECLARED_TOOL,)).model_copy(
        update={"placeholders": questions}
    )
    return publish(document, key=KEY, signed_by=PUBLISHER, at=LATER)


def _reviewed(candidate: SignedManifest, *, first: SignedManifest | None = None) -> UpgradeReview:
    held = first or _signed(_manifest(allowed=(DECLARED_TOOL,)))
    return review(_installed(held), shelf=_shelved(held, candidate), declines=Declines())


def _accepted(reviewed: UpgradeReview, *, tools: ToolRegistry | None = None):  # type: ignore[no-untyped-def]
    return accept(
        reviewed,
        resolutions={},
        key=KEY,
        audience=AUDIENCE,
        registry=_connectors(serving=True),
        tools=tools or _contract_tools(),
        by=ACCEPTER,
        at=LATER_STILL,
    )


def test_a_question_the_new_version_asks_and_the_old_one_did_not_is_named_as_new() -> None:
    """The required questions version two adds are the ones named, in its order, and the one both
    versions ask is not.

    Delete this and an acceptance cannot tell a question nobody was asked from one that was put
    to whoever installed the agent, so it must call every upgrade complete or every upgrade
    incomplete."""
    reviewed = _reviewed(
        _asking(
            Placeholder(key=OLD_QUESTION, prompt="Who signs off a renewal?"),
            Placeholder(key=NEW_QUESTION, prompt="Which price list do renewals use?"),
            Placeholder(key="renewal_terms", prompt="Which terms apply?"),
        )
    )

    assert newly_required_placeholders(reviewed) == (NEW_QUESTION, "renewal_terms")


def test_a_question_that_was_optional_and_is_now_required_is_new() -> None:
    """A question version one asked and did not require, and version two requires, counts as new:
    nobody was obliged to answer it, so nobody can be assumed to have.

    Delete this and tightening a question from optional to required lets the agent run on a blank
    the upgrade was meant to close."""
    first = _signed(
        _manifest(allowed=(DECLARED_TOOL,)).model_copy(
            update={
                "placeholders": (Placeholder(key=NEW_QUESTION, prompt="Which?", required=False),)
            }
        )
    )
    reviewed = _reviewed(
        _asking(Placeholder(key=NEW_QUESTION, prompt="Which price list?")), first=first
    )

    assert newly_required_placeholders(reviewed) == (NEW_QUESTION,)


def test_a_new_question_nobody_requires_holds_nothing() -> None:
    """A question version two adds as optional is not unanswered, because nobody has to answer it.

    Delete this and every optional question a release adds disables every agent that accepts it."""
    reviewed = _reviewed(
        _asking(
            Placeholder(key=OLD_QUESTION, prompt="Who signs off a renewal?"),
            Placeholder(key=NEW_QUESTION, prompt="Which?", required=False),
        )
    )

    assert newly_required_placeholders(reviewed) == ()
    assert _accepted(reviewed).completeness.is_ready


def test_nothing_is_new_when_nothing_is_on_offer() -> None:
    """An instance already on the newest version asks nothing new and needs nothing after.

    Delete this and a review of a current agent reports questions or raises on a missing
    candidate."""
    held = _signed()
    reviewed = review(_installed(held), shelf=_shelved(held), declines=Declines())

    assert newly_required_placeholders(reviewed) == ()
    assert (
        needs_after(
            reviewed,
            audience=AUDIENCE,
            registry=_connectors(serving=True),
            tools=ToolRegistry(),
            at=LATER_STILL,
        )
        is None
    )


def test_an_accepted_version_that_asks_a_new_question_comes_back_incomplete_and_disabled() -> None:
    """**The wizard reopened.** Version two asks a question version one did not; the acceptance
    reports it missing, by name, and the upgraded agent is disabled, so it does not run before a
    person has seen what it now needs. The question both versions ask is not reported.

    Delete this and an upgrade can add a question and run on a blank, with the badge ready."""
    upgraded = _accepted(
        _reviewed(
            _asking(
                Placeholder(key=OLD_QUESTION, prompt="Who signs off a renewal?"),
                Placeholder(key=NEW_QUESTION, prompt="Which price list do renewals use?"),
            )
        )
    )

    assert upgraded.completeness.missing == (
        Missing(kind=MissingKind.PLACEHOLDER, name=NEW_QUESTION),
    )
    assert not upgraded.completeness.is_ready
    assert upgraded.record.disabled_at == LATER_STILL


def test_a_version_asking_nothing_new_is_still_complete_after_acceptance() -> None:
    """The positive half: version two asks what version one asked and nothing more, so the badge
    is as the install left it and the agent is not switched off.

    Delete this and the guard above is satisfied by an upgrade that refuses everything."""
    upgraded = _accepted(
        _reviewed(_asking(Placeholder(key=OLD_QUESTION, prompt="Who signs off a renewal?")))
    )

    assert upgraded.completeness.is_ready
    assert upgraded.record.disabled_at is None


def test_the_review_names_what_the_acceptance_will_leave_missing() -> None:
    """A version declaring a connector that does not serve, a tool nothing registers and a new
    question is reviewed with all three named, in the install's own order, and the acceptance
    that follows leaves exactly those missing.

    Delete this and a person presses accept to learn what the version needed from the agent
    going quiet."""
    version_two = publish(
        _manifest(version=2, allowed=(DECLARED_TOOL,)).model_copy(
            update={
                "placeholders": (
                    Placeholder(key=OLD_QUESTION, prompt="Who signs off a renewal?"),
                    Placeholder(key=NEW_QUESTION, prompt="Which price list?"),
                )
            }
        ),
        key=KEY,
        signed_by=PUBLISHER,
        at=LATER,
    )
    reviewed = _reviewed(version_two)
    asked = needs_after(
        reviewed,
        audience=AUDIENCE,
        registry=_connectors(serving=False),
        tools=ToolRegistry(),
        at=LATER_STILL,
    )
    accepted = accept(
        reviewed,
        resolutions={},
        key=KEY,
        audience=AUDIENCE,
        registry=_connectors(serving=False),
        tools=ToolRegistry(),
        by=ACCEPTER,
        at=LATER_STILL,
    )

    assert asked is not None
    assert asked.missing == (
        Missing(kind=MissingKind.PLACEHOLDER, name=NEW_QUESTION),
        Missing(kind=MissingKind.CONNECTOR, name="xero"),
        Missing(kind=MissingKind.TOOL, name=DECLARED_TOOL),
    )
    assert accepted.completeness == asked


def test_the_review_says_nothing_is_missing_when_the_install_provides_it_all() -> None:
    """With the connector serving and the tool registered, a version declaring both and no new
    question is reviewed with nothing missing.

    Delete this and the review lists needs for every version, which a person learns to ignore."""
    version_two = publish(
        _manifest(version=2, allowed=(DECLARED_TOOL,)), key=KEY, signed_by=PUBLISHER, at=LATER
    )
    asked = needs_after(
        _reviewed(version_two),
        audience=AUDIENCE,
        registry=_connectors(serving=True),
        tools=_contract_tools(),
        at=LATER_STILL,
    )

    assert asked is not None and asked.is_ready


def test_looking_at_what_a_version_needs_does_not_take_it() -> None:
    """Asking what accepting would need moves no pin: the instance a review carries is still on
    version one and the shelf still holds one newest.

    Delete this and a review that checks readiness can be the thing that upgrades an agent."""
    reviewed = _reviewed(_asking(Placeholder(key=NEW_QUESTION, prompt="Which price list?")))

    needs_after(
        reviewed,
        audience=AUDIENCE,
        registry=ConnectorRegistry(),
        tools=ToolRegistry(),
        at=LATER_STILL,
    )

    assert reviewed.instance.template_version == 1
    assert reviewed.to_version == 2


def test_a_version_that_cannot_become_an_agent_has_no_needs_and_is_refused_on_accept() -> None:
    """A version published with its persona blanked is legal to publish and impossible to run, so
    the review has no needs to show for it rather than raising into the page, and the acceptance
    refuses it as `accept` always has.

    Delete this and a review of a version that cannot be applied raises into the page, or an
    unmaterialisable version is shown as needing nothing and then fails at acceptance."""
    first = _signed()
    blanked = publish(_manifest(version=2, persona=""), key=KEY, signed_by=PUBLISHER, at=LATER)
    reviewed = review(_installed(first), shelf=_shelved(first, blanked), declines=Declines())

    assert (
        needs_after(
            reviewed,
            audience=AUDIENCE,
            registry=ConnectorRegistry(),
            tools=ToolRegistry(),
            at=LATER_STILL,
        )
        is None
    )
    with pytest.raises(ValidationError):
        _accepted(reviewed)


def test_taking_the_versions_value_can_change_what_is_needed_and_the_acceptance_recomputes_it() -> (
    None
):
    """The review keeps every local value and the acceptance honours the person's resolutions, so
    the two can differ and the acceptance is the one that counts: with the local persona kept the
    version is complete, and the acceptance taking the version's own persona stays complete too.

    Delete this and the dry run is mistaken for the acceptance, and a resolution that changes the
    answer is never recomputed."""
    held = _signed(_manifest(allowed=(DECLARED_TOOL,)))
    local = _installed(held, overlay={"persona": "Chase renewals and mention nothing else."})
    second = publish(
        _manifest(version=2, persona=SECOND_PERSONA, allowed=(DECLARED_TOOL,)),
        key=KEY,
        signed_by=PUBLISHER,
        at=LATER,
    )
    reviewed = review(local, shelf=_shelved(held, second), declines=Declines())

    asked = needs_after(
        reviewed,
        audience=AUDIENCE,
        registry=_connectors(serving=True),
        tools=_contract_tools(),
        at=LATER_STILL,
    )
    taken = accept(
        reviewed,
        resolutions={"persona": Resolution.TAKE_TEMPLATE},
        key=KEY,
        audience=AUDIENCE,
        registry=_connectors(serving=True),
        tools=_contract_tools(),
        by=ACCEPTER,
        at=LATER_STILL,
    )

    assert asked is not None and asked.is_ready
    assert taken.completeness.is_ready
    assert taken.instance.overlay == {}
