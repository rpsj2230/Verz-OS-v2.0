"""`brain.builder.agent_drafts`: where a draft stands, what counts as reaching further, and who may
be the second person.

The routes' tests drive these through HTTP; these hold the rules themselves, each with the case that
passes beside the case that is refused, so a rule that refuses everything cannot stand in for one
that decides.

Task ids: M27.11.6
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.agents.template import TemplateError, verify
from brain.builder.agent_drafts import (
    NOT_THE_AUTHOR,
    NOT_WITHIN_YOUR_REACH,
    Act,
    AgentDraft,
    approval_refusal,
    blank_seed,
    carrier,
    ceiling_of,
    for_agent,
    next_version,
    plain,
    raised_rungs,
    second_people_needed,
    state_of,
    widenings,
)
from brain.builder.compose import BuilderError
from brain.builder.draft_words import DraftAct, DraftChange, DraftKind, DraftState
from brain.builder.drafts import FIRST_VERSION, ManifestDraft, Problem, Revision, body_text
from brain.builder.publish import APPROVERS_FOR_A_WIDENING, APPROVERS_FOR_AN_ORDINARY_PUBLISH
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.knowledge.visibility import Visibility
from tests.unit.test_agent_lifecycle_routes import manifest
from tests.unit.test_agent_routes import KEY

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
AT = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def a_record(*capabilities: str, tools: frozenset[str] = frozenset()) -> AgentRecord:
    return AgentRecord(
        agent_id="invoice_desk",
        display_name="Invoice desk",
        persona="Answer briefly.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id="u_author"),
        authority=AgentAuthority(
            scope=Scope.unrestricted(),
            capabilities=tuple(Capability(value=one) for one in capabilities),
            allowed_tools=tools,
        ),
        created_by="u_author",
    )


def a_draft(*acts: tuple[int, DraftAct], revisions: int = 2) -> AgentDraft:
    return AgentDraft(
        draft=ManifestDraft(draft_id="d1", owner_id="u_author", created_at=AT),
        agent_id="invoice_desk",
        kind=DraftKind.NEW,
        base_hash=None,
        revisions=tuple(
            Revision(
                draft_id="d1",
                number=number,
                body=body_text({"n": number}),
                saved_by="u_author",
                saved_at=AT,
            )
            for number in range(1, revisions + 1)
        ),
        acts=tuple(
            Act(revision=revision, act=act, actor_id="u_author", at=AT) for revision, act in acts
        ),
    )


def reach(principal_id: str, *capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


# ------------------------------------------------------------------------ where it stands
def test_a_draft_stands_where_its_latest_revision_does_and_nowhere_else() -> None:
    """A check or a request on an earlier revision says nothing about the latest one.

    Delete this and a draft checked, then changed, reads as checked, and the publish button offers
    what nobody checked."""
    assert state_of(a_draft((1, DraftAct.CHECKED))) is DraftState.DRAFT
    assert state_of(a_draft((2, DraftAct.CHECKED))) is DraftState.CHECKED
    assert state_of(a_draft((2, DraftAct.CHECKED), (2, DraftAct.REQUESTED))) is DraftState.WAITING
    assert state_of(a_draft((2, DraftAct.REQUESTED), (2, DraftAct.DECLINED))) is DraftState.DECLINED
    assert (
        state_of(a_draft((2, DraftAct.APPROVED), (2, DraftAct.PUBLISHED))) is DraftState.PUBLISHED
    )


def test_an_edit_names_the_configuration_it_started_from_and_a_new_agent_names_none() -> None:
    """Delete this and an edit could be published over an agent that moved, with nothing to
    compare against."""
    with pytest.raises(BuilderError):
        replace(a_draft(), kind=DraftKind.EDIT)
    with pytest.raises(BuilderError):
        replace(a_draft(), base_hash="0" * 64)
    assert replace(a_draft(), kind=DraftKind.EDIT, base_hash="0" * 64).base_hash == "0" * 64


def test_the_ledger_words_are_the_two_starts_and_every_act() -> None:
    """`0149`'s trigger writes `drafted`, `saved` and each act's own word, and nothing else.

    Delete this and an act added to the vocabulary could reach the ledger as a word the audit page
    was never told about."""
    assert {one.value for one in DraftChange} == {"drafted", "saved"} | {
        one.value for one in DraftAct
    }


# ------------------------------------------------------------------------ reaching further
def test_a_new_agent_widens_from_nothing_by_every_capability_tool_and_side_effect() -> None:
    """Delete this and an agent built from scratch could reach anything on its author's word."""
    made = a_record("read:invoice.reference", tools=frozenset({"ledger.read_invoice"}))
    acting = made.model_copy(
        update={
            "authority": made.authority.model_copy(update={"max_side_effect": SideEffect.DRAFT})
        }
    )

    assert widenings(None, made, now=AT) == (
        "read:invoice",
        "read:invoice.reference",
        "ledger.read_invoice",
    )
    assert "draft" in widenings(None, acting, now=AT)
    assert widenings(None, a_record(), now=AT) == ()


def test_an_edit_widens_only_by_what_it_adds_and_a_narrowing_widens_nothing() -> None:
    """Delete this and an instruction edit would wait for a second person every time, or a new
    capability would not."""
    before = a_record("read:invoice.reference", tools=frozenset({"ledger.read_invoice"}))
    wider = a_record(
        "read:invoice.reference", "read:invoice.total", tools=frozenset({"ledger.read_invoice"})
    )
    narrower = a_record(tools=frozenset({"ledger.read_invoice"}))

    assert widenings(before, wider, now=AT) == ("read:invoice.total",)
    assert widenings(before, before, now=AT) == ()
    assert widenings(before, narrower, now=AT) == ()


def test_a_widening_needs_one_person_besides_the_author_and_anything_else_needs_none() -> None:
    """Held against `brain.builder.publish`'s two figures rather than against a number chosen here.

    Delete this and the author could count as the second person, or an instruction edit could need
    one."""
    assert second_people_needed(("read:invoice.total",)) == 1
    assert second_people_needed(()) == 0
    assert APPROVERS_FOR_A_WIDENING - APPROVERS_FOR_AN_ORDINARY_PUBLISH == 1


# ------------------------------------------------------------------------ the second person
def test_the_second_person_is_not_the_author_and_holds_the_whole_ceiling() -> None:
    """The author is refused whatever they hold; somebody short of one capability is refused in a
    sentence naming none; somebody holding all of it may approve.

    Delete this and the only gate between a builder and a widened agent is the builder."""
    ceiling = ceiling_of(a_record("read:invoice.reference"))
    everything = ("read:invoice", "read:invoice.reference")

    def refusal(approver: str, *held: str) -> str | None:
        return approval_refusal(
            author_id="u_author",
            approver_id=approver,
            ceiling=ceiling,
            approver_reach=reach(approver, *held),
            now=AT,
        )

    assert refusal("u_author", *everything) == NOT_THE_AUTHOR
    assert refusal("u_second", "read:invoice") == NOT_WITHIN_YOUR_REACH
    assert "read:" not in NOT_WITHIN_YOUR_REACH
    assert refusal("u_second", *everything) is None


# ------------------------------------------------------------------------ the document
def test_a_draft_is_addressed_to_its_agent_whatever_the_document_says() -> None:
    """Delete this and a typed template id could make an edit a new version of a shared template."""
    seeded = blank_seed("invoice_desk_ab12cd")
    typed = for_agent({**seeded, "identity": {**seeded["identity"], "template_id": "shared"}}, "x")

    assert seeded["identity"]["template_id"] == "invoice_desk_ab12cd"
    assert typed["identity"]["template_id"] == "x"
    assert for_agent({"identity": "not an object"}, "x") == {"identity": "not an object"}


def test_a_rung_above_shadow_is_named_and_shadow_is_not() -> None:
    """Delete this and a draft naming autonomy nobody earned reaches the publish button."""
    assert raised_rungs(manifest(AutonomyTier.ASSISTED)) == ("invoice.read",)
    assert raised_rungs(manifest(AutonomyTier.SHADOW)) == ()


def test_a_question_asked_before_publishing_is_signed_with_a_key_nobody_else_holds() -> None:
    """The carrier's signature does not verify with this install's key, so nothing it signed could
    ever be installed. Delete this and a check could sign with the install's own key and a draft
    would be a signed version before anybody published it."""
    signed = carrier(manifest(), signed_by="u_author", at=AT)

    with pytest.raises(TemplateError):
        verify(signed, key=KEY)


def test_a_problem_names_its_section_in_the_forms_words() -> None:
    """Delete this and a person reads `authority.capabilities.0.value`."""
    assert (
        plain(Problem(path="identity.display_name", kind="x", message="Too short"))
        == "Identity, name: Too short"
    )
    assert plain(Problem(path="persona", kind="x", message="Too long")) == "Instructions: Too long"
    assert (
        plain(Problem(path="authority.capabilities.0.value", kind="x", message="Bad"))
        == "Permissions, what it may read: Bad"
    )


def test_versions_of_an_agents_own_template_count_on_from_the_newest() -> None:
    """Delete this and an edit could publish over a version that exists."""
    assert next_version(()) == FIRST_VERSION
    assert next_version((1, 3, 2)) == 4
