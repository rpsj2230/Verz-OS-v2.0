"""A co-author proposing changes to a draft, and the draft's author deciding them (M20.1.3).

The sentence has two halves and the tests are arranged by them. A model proposes: a real call
through `ModelDriver`, answered here by a fake driver that records what it was sent, read into
a proposal that writes nothing. A person decides: the draft's owner accepts the changes they
name, through `brain.builder.drafts.save`, or rejects them and nothing is written. Around that
sit the ways a co-author goes quietly wrong: a proposal applied to a draft that moved on, a
stranger learning a draft exists, a suggestion that widens what an agent may reach, a reply
that is not what it claims to be, and a prompt carrying somebody else's draft.

Real drafts, real `TemplateManifest` validation and the real form schema. The driver is the
only stand-in, because the driver is the seam.

The instants are in 2019 on purpose. Nothing here is about the present, and a fixture date
near the wall clock is a test that fails on a day nobody chose.

Task ids: M20.1.3
"""

from __future__ import annotations

import inspect
import json
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.agents.template import MANIFEST_PATHS, SEALED_PATHS, canonical_value
from brain.builder.coauthor import (
    ASK_CHARS,
    COAUTHOR_PATHS,
    WITHHELD_FROM_THE_COAUTHOR,
    DropReason,
    Hunk,
    Proposal,
    Resolution,
    StaleProposalError,
    UnreadableReplyError,
    accept,
    coauthor_request,
    propose,
    reject,
    system_prompt,
)
from brain.builder.compose import BuilderError, Section
from brain.builder.drafts import (
    FIRST_REVISION,
    NO_REVISION,
    MemoryDraftStore,
    NoDraftHereError,
    Revision,
    history,
    save,
    start,
    validity,
)
from brain.builder.publish import NAMES_THAT_WOULD_PUT_A_VALUE_IN_THE_RECORD, REACH_PATHS
from brain.models.driver import (
    DriverFailure,
    DriverMessage,
    DriverRequest,
    DriverResponse,
    ModelDriver,
    ProviderUnavailable,
    Role,
    TokenUsage,
)
from brain.models.routing import Deployment, ResidencyClass, RoutingRung, Tier

NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
LATER = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)
OWNER = "u_priya"
STRANGER = "u_tan"
DRAFT = "draft_renewals"
TEMPLATE = "renewal_chaser_template"
ASK = "Make the persona firmer and add a one-line summary."

RUNG = RoutingRung(
    tier=Tier.MAIN,
    position=0,
    model="a-model",
    deployment=Deployment(
        id="d_main_primary",
        provider="anthropic",
        model="a-model",
        region="global",
        residency_class=ResidencyClass.GLOBAL,
        context_window=200_000,
    ),
    attempts=1,
    timeout_seconds=20.0,
    max_concurrency=4,
)


class FakeDriver:
    """A driver that records every request and answers each with the reply it was given.

    Not a subclass of anything, for the reason `tests/unit/test_health.py` gives: `ModelDriver`
    is a Protocol so an adapter need not import us, and a fake that inherited would stop
    proving the co-author depends on the protocol and nothing more.
    """

    provider = "anthropic"

    def __init__(self, reply: str = '{"changes": []}', *, down: bool = False) -> None:
        self.reply = reply
        self.down = down
        self.seen: list[DriverRequest] = []

    def complete(self, request: DriverRequest) -> DriverResponse:
        self.seen.append(request)
        if self.down:
            raise ProviderUnavailable(
                DriverFailure(deployment_id=request.deployment_id, status=503)
            )
        return DriverResponse(
            deployment_id=request.deployment_id,
            model=request.model,
            text=self.reply,
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            finish_reason="stop",
        )


def reply(*changes: tuple[str, Any]) -> str:
    return json.dumps({"changes": [{"path": path, "value": value} for path, value in changes]})


def whole(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "identity": {"template_id": TEMPLATE, "display_name": "Renewal chaser"},
        "persona": "Chase renewals.",
    }
    document.update(extra)
    return document


def saved_once(document: dict[str, Any] | None = None) -> MemoryDraftStore:
    store = MemoryDraftStore()
    start(store, draft_id=DRAFT, owner_id=OWNER, at=NOW)
    save(
        store, DRAFT, whole() if document is None else document, by=OWNER, at=NOW, base=NO_REVISION
    )
    return store


def proposed(store: MemoryDraftStore, text: str, *, by: str = OWNER) -> Proposal:
    return propose(store, DRAFT, ASK, by=by, driver=FakeDriver(text), rung=RUNG)


def kept(store: MemoryDraftStore) -> tuple[Revision, ...]:
    return history(store, DRAFT, principal_id=OWNER)


FIRMER = "Chase renewals, and say plainly when a client is overdue."
SUMMARY = "Chases contract renewals."


# --- the whole sentence -----------------------------------------------------------------------


def test_the_fake_driver_is_a_model_driver() -> None:
    """Deleting this lets the fake drift from the seam, and every test below then proves the
    co-author works against something `propose` would not accept in production."""
    assert isinstance(FakeDriver(), ModelDriver)


def test_a_proposal_writes_nothing_and_an_accept_applies_only_the_changes_named() -> None:
    """Deleting this loses the one test of the leaf's whole sentence.

    A `propose` that saved as it went, or an `accept` that applied every hunk rather than the
    ones named, passes every test that looks only at the proposal or only at the revision.
    """
    store = saved_once()
    before = kept(store)
    driver = FakeDriver(reply(("persona", FIRMER), ("identity.summary", SUMMARY)))

    proposal = propose(store, DRAFT, ASK, by=OWNER, driver=driver, rung=RUNG)

    assert len(driver.seen) == 1
    assert kept(store) == before
    assert proposal.base_revision == FIRST_REVISION
    assert proposal.paths == ("identity.summary", "persona")
    assert [one.section for one in proposal.hunks] == [Section.IDENTITY, Section.PERSONA]
    by_path = {one.path: one for one in proposal.hunks}
    assert (by_path["persona"].before, by_path["persona"].after) == (
        canonical_value("Chase renewals."),
        canonical_value(FIRMER),
    )
    assert by_path["identity.summary"].before is None

    accepted = accept(store, proposal, ["persona"], by=OWNER, at=LATER)

    revisions = kept(store)
    assert [one.number for one in revisions] == [1, 2]
    assert revisions[:1] == before
    assert revisions[1] == accepted.saved.revision
    assert revisions[1].document() == whole(persona=FIRMER)
    assert (revisions[1].saved_by, revisions[1].saved_at) == (OWNER, LATER)
    assert accepted.resolution == Resolution(
        draft_id=DRAFT,
        base_revision=FIRST_REVISION,
        accepted=("persona",),
        rejected=("identity.summary",),
        decided_by=OWNER,
        decided_at=LATER,
        revision=2,
    )


def test_rejecting_a_proposal_leaves_the_draft_byte_identical() -> None:
    """Deleting this lets a rejection write something: a revision equal to the base, or an
    edit to the latest one, neither of which any accept test would notice."""
    store = saved_once()
    proposal = proposed(store, reply(("persona", FIRMER), ("tier", "heavy")))
    bodies = [one.body for one in kept(store)]

    resolution = reject(store, proposal, by=OWNER, at=LATER)

    assert [one.body for one in kept(store)] == bodies
    assert resolution.revision is None
    assert resolution.accepted == ()
    assert set(resolution.rejected) == {"persona", "tier"}


def test_a_provider_that_does_not_answer_proposes_nothing_and_changes_nothing() -> None:
    """Deleting this lets an outage be swallowed into an empty proposal, which a person reads
    as the co-author having nothing to suggest."""
    store = saved_once()
    before = kept(store)
    with pytest.raises(ProviderUnavailable):
        propose(store, DRAFT, ASK, by=OWNER, driver=FakeDriver(down=True), rung=RUNG)
    assert kept(store) == before


# --- a proposal is made against one revision ----------------------------------------------------


def test_a_proposal_is_refused_once_a_later_revision_has_been_saved() -> None:
    """Deleting this lets a proposal land on a draft the author edited after asking, replacing
    values they were never shown a before for. The refusal is its own type so a screen can say
    "ask again" rather than report a failed save."""
    store = saved_once()
    proposal = proposed(store, reply(("identity.summary", SUMMARY)))
    save(store, DRAFT, whole(persona="Edited by hand."), by=OWNER, at=LATER, base=FIRST_REVISION)
    before = kept(store)

    with pytest.raises(StaleProposalError):
        accept(store, proposal, ["identity.summary"], by=OWNER, at=LATER)
    assert kept(store) == before


def test_a_different_body_under_the_same_revision_number_refuses_the_proposal() -> None:
    """Deleting this lets a proposal be accepted into a store rebuilt under the same draft id,
    whose revision one is not the document the author was shown: the number matches and the
    befores of the changed paths happen to match, and nothing else would notice."""
    proposal = proposed(saved_once(), reply(("identity.summary", SUMMARY)))
    elsewhere = saved_once(whole(persona="A different draft altogether."))
    before = kept(elsewhere)

    with pytest.raises(StaleProposalError):
        accept(elsewhere, proposal, ["identity.summary"], by=OWNER, at=LATER)
    assert kept(elsewhere) == before


def test_a_change_shown_against_a_value_the_draft_does_not_hold_is_refused() -> None:
    """Deleting this lets a proposal edited on its way back from a browser replace a value the
    person accepting it was shown as something else."""
    store = saved_once()
    honest = proposed(store, reply(("persona", FIRMER)))
    edited = Proposal(
        draft_id=honest.draft_id,
        base_revision=honest.base_revision,
        base_digest=honest.base_digest,
        hunks=(Hunk(path="persona", before=canonical_value("Be gentle."), after='"Be harsh."'),),
    )
    before = kept(store)

    with pytest.raises(BuilderError) as caught:
        accept(store, edited, ["persona"], by=OWNER, at=LATER)
    assert not isinstance(caught.value, StaleProposalError)
    assert kept(store) == before


def test_accepting_the_same_changes_again_returns_the_revision_it_already_wrote() -> None:
    """Deleting this lets a retry after a timeout be refused as stale, so a person whose accept
    landed is told it failed and asks the co-author again for a change they already have."""
    store = saved_once()
    proposal = proposed(store, reply(("persona", FIRMER)))

    first = accept(store, proposal, ["persona"], by=OWNER, at=LATER)
    again = accept(store, proposal, ["persona"], by=OWNER, at=LATER)

    assert again.saved.revision == first.saved.revision
    assert [one.number for one in kept(store)] == [1, 2]


def test_a_draft_nothing_has_been_saved_to_can_be_co_authored_into_its_first_revision() -> None:
    """Deleting this leaves the empty draft untested: the base before the first revision, and
    an incomplete draft (no identity at all) not making a valid persona look refused."""
    store = MemoryDraftStore()
    start(store, draft_id=DRAFT, owner_id=OWNER, at=NOW)

    proposal = proposed(store, reply(("persona", FIRMER)))
    assert proposal.base_revision == NO_REVISION
    assert proposal.paths == ("persona",)
    assert proposal.dropped == ()

    accepted = accept(store, proposal, ["persona"], by=OWNER, at=LATER)
    assert accepted.saved.revision.number == FIRST_REVISION
    assert kept(store)[0].document() == {"persona": FIRMER}


# --- who decides -------------------------------------------------------------------------------


def test_somebody_elses_draft_is_refused_before_it_is_read_or_any_model_is_called() -> None:
    """Deleting this lets a stranger send somebody's draft to a model, which reads it, costs a
    call, and says by answering that the draft exists. The refusal must be the one a draft that
    does not exist gets."""
    store = saved_once()
    driver = FakeDriver(reply(("persona", FIRMER)))

    with pytest.raises(NoDraftHereError) as other_persons:
        propose(store, DRAFT, ASK, by=STRANGER, driver=driver, rung=RUNG)
    with pytest.raises(NoDraftHereError) as nobodys:
        propose(MemoryDraftStore(), DRAFT, ASK, by=STRANGER, driver=driver, rung=RUNG)

    assert driver.seen == []
    assert str(other_persons.value) == str(nobodys.value)


def test_only_the_owner_decides_and_a_stale_proposal_tells_a_stranger_nothing() -> None:
    """Deleting this lets somebody other than the author apply a proposal, or learn from a
    stale refusal that a draft exists and has been edited since. Both refusals must come before
    anything about the draft is read."""
    store = saved_once()
    proposal = proposed(store, reply(("identity.summary", SUMMARY)))
    save(store, DRAFT, whole(persona="Edited by hand."), by=OWNER, at=LATER, base=FIRST_REVISION)
    before = kept(store)

    with pytest.raises(NoDraftHereError):
        accept(store, proposal, ["identity.summary"], by=STRANGER, at=LATER)
    with pytest.raises(NoDraftHereError):
        reject(store, proposal, by=STRANGER, at=LATER)
    assert kept(store) == before

    assert reject(store, proposal, by=OWNER, at=LATER).decided_by == OWNER


def test_accepting_nothing_or_a_change_the_proposal_does_not_hold_is_refused() -> None:
    """Deleting this lets an accept that names nothing write a revision, or lets a named path
    that was never proposed pass as though it had been chosen."""
    store = saved_once()
    proposal = proposed(store, reply(("persona", FIRMER)))
    before = kept(store)

    with pytest.raises(BuilderError):
        accept(store, proposal, [], by=OWNER, at=LATER)
    with pytest.raises(BuilderError):
        accept(store, proposal, ["persona", "tier"], by=OWNER, at=LATER)
    assert kept(store) == before


# --- the co-author writes words and never reach -------------------------------------------------


REACHING: tuple[tuple[str, Any], ...] = (
    ("authority.capabilities", [{"value": "read:client.*"}]),
    ("authority.allowed_tools", ["crm_lookup"]),
    ("authority.required_tools", ["crm_lookup"]),
    ("authority.scope", {"clauses": []}),
    ("guardrails.leash", []),
    ("guardrails.max_side_effect", "external"),
    ("identity.template_id", "another_template"),
    ("identity.version", 9),
    ("identity.published_by", "u_somebody"),
)


def test_the_coauthor_may_not_propose_reach_supervision_or_the_templates_identity() -> None:
    """Deleting this lets a reply widen a ceiling, loosen a leash or redirect the template, as
    one hunk among the wording changes a person accepts together. The persona change beside
    them is the positive case: a refusal of everything would pass the rest of this test."""
    store = saved_once()

    proposal = proposed(store, reply(*REACHING, ("persona", FIRMER)))

    assert proposal.paths == ("persona",)
    assert {(one.path, one.reason) for one in proposal.dropped} == {
        (path, DropReason.NOT_THE_COAUTHORS_TO_WRITE) for path, _ in REACHING
    }


@pytest.mark.parametrize("path", sorted(WITHHELD_FROM_THE_COAUTHOR))
def test_a_change_to_a_withheld_path_cannot_be_built_into_a_proposal_by_hand(path: str) -> None:
    """Deleting this leaves the refusal only at the reply, so a proposal rebuilt from what a
    browser sent back could carry a change to reach that no model reply ever held."""
    with pytest.raises(BuilderError):
        Hunk(path=path, before=None, after='"anything"')
    assert Hunk(path="persona", before=None, after='"anything"').section is Section.PERSONA


def test_withheld_paths_are_reach_and_sealed_and_every_other_path_is_proposable() -> None:
    """Deleting this lets the withheld set drift from the publish gate's reach paths and the
    template's seal, or lets a manifest path fall into neither half. Held against the other
    modules' constants and against the named paths, not against this module's own."""
    assert frozenset(REACH_PATHS | set(SEALED_PATHS)) == WITHHELD_FROM_THE_COAUTHOR
    assert frozenset(MANIFEST_PATHS) == COAUTHOR_PATHS | WITHHELD_FROM_THE_COAUTHOR
    assert COAUTHOR_PATHS.isdisjoint(WITHHELD_FROM_THE_COAUTHOR)
    assert {path for path, _ in REACHING} <= WITHHELD_FROM_THE_COAUTHOR
    assert {"persona", "identity.summary", "skills", "golden_set", "tier"} <= COAUTHOR_PATHS


def test_an_accepted_revision_is_the_one_a_typed_save_of_the_document_makes() -> None:
    """Deleting this lets an accept take a path of its own to the store, with a marker or a
    shortcut that makes a model's suggestion more decided than typing. It must be the same
    save, the same body and the same validity report."""
    co_authored = saved_once()
    proposal = proposed(co_authored, reply(("persona", FIRMER), ("tier", "heavy")))
    via_accept = accept(co_authored, proposal, proposal.paths, by=OWNER, at=LATER).saved

    typed = saved_once()
    by_hand = save(
        typed, DRAFT, via_accept.revision.document(), by=OWNER, at=LATER, base=FIRST_REVISION
    )

    assert by_hand.revision == via_accept.revision
    assert validity(by_hand.revision) == via_accept.validity


# --- the reply is untrusted ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Here are some ideas for your persona.",
        "[]",
        '{"edits": []}',
        '{"changes": "persona"}',
        '{"changes": [{"path": "persona", "value": NaN}]}',
    ],
)
def test_a_reply_that_is_not_a_list_of_changes_is_refused_whole_and_proposes_nothing(
    text: str,
) -> None:
    """Deleting this lets an unreadable reply become an empty proposal, which a person reads as
    the co-author having nothing to suggest, or a crash that is not a refusal at all."""
    store = saved_once()
    before = kept(store)
    with pytest.raises(UnreadableReplyError):
        proposed(store, text)
    assert kept(store) == before


def test_a_reply_wrapped_in_a_code_fence_is_read() -> None:
    """Deleting this lets the fence handling refuse the commonest shape a model wraps its JSON
    in, and every refusal test above would still pass."""
    fenced = "```json\n" + reply(("persona", FIRMER)) + "\n```"
    assert proposed(saved_once(), fenced).paths == ("persona",)


def test_each_bad_change_is_dropped_with_its_reason_and_the_good_ones_are_proposed() -> None:
    """Deleting this lets a change the manifest refuses, a path outside the manifest, or two
    answers for one path reach a person as though it were a suggestion they could accept.

    The connectors change is the positive case, and the unchanged persona is neither a hunk nor
    a drop, because setting a value to itself proposes nothing.
    """
    changes: list[Any] = [
        "make it better",
        {"path": "persona"},
        {"path": "owner", "value": STRANGER},
        {"path": "authority.grants", "value": []},
        {"path": "tier", "value": "gigantic"},
        {"path": "identity.summary", "value": "x" * 300},
        {"path": "golden_set", "value": [{"question": "When is Acme due?"}]},
        {"path": "connectors", "value": ["hubspot"]},
        {"path": "persona", "value": "Chase renewals."},
        {"path": "placeholders", "value": []},
        {"path": "placeholders", "value": [{"key": "sla", "prompt": "What is the SLA?"}]},
    ]
    store = saved_once()

    proposal = proposed(store, json.dumps({"changes": changes}))

    assert proposal.paths == ("connectors",)
    assert [(one.index, one.path, one.reason) for one in proposal.dropped] == [
        (0, "", DropReason.MALFORMED),
        (1, "", DropReason.MALFORMED),
        (2, "owner", DropReason.NOT_A_MANIFEST_PATH),
        (3, "authority.grants", DropReason.NOT_A_MANIFEST_PATH),
        (4, "tier", DropReason.REFUSED_BY_THE_SCHEMA),
        (5, "identity.summary", DropReason.REFUSED_BY_THE_SCHEMA),
        (6, "golden_set", DropReason.REFUSED_BY_THE_SCHEMA),
        (9, "placeholders", DropReason.REPEATED),
        (10, "placeholders", DropReason.REPEATED),
    ]
    assert all(one.message.strip() for one in proposal.dropped)


def test_a_change_inside_a_part_of_the_draft_that_is_not_an_object_is_dropped_not_forced() -> None:
    """Deleting this lets a suggested summary replace an identity the author typed as something
    else, discarding it, rather than telling them to correct it first."""
    store = saved_once({"identity": "renewal chaser", "persona": "Chase renewals."})
    proposal = proposed(store, reply(("identity.summary", SUMMARY)))
    assert proposal.paths == ()
    assert [(one.path, one.reason) for one in proposal.dropped] == [
        ("identity.summary", DropReason.NOWHERE_TO_GO)
    ]


def test_a_proposal_cannot_hold_two_changes_to_one_path_or_a_change_that_is_not_one() -> None:
    """Deleting this lets a hand-built proposal offer two afters for one path, so accepting the
    path does not say which was chosen, or offer a change whose after is not JSON or is its
    before."""
    one = Hunk(path="persona", before=None, after='"one"')
    other = Hunk(path="persona", before=None, after='"other"')
    with pytest.raises(BuilderError):
        Proposal(draft_id=DRAFT, base_revision=1, base_digest="0" * 64, hunks=(one, other))
    with pytest.raises(BuilderError):
        Hunk(path="persona", before=None, after="not json")
    with pytest.raises(BuilderError):
        Hunk(path="persona", before='"same"', after='"same"')
    assert Proposal(draft_id=DRAFT, base_revision=1, base_digest="0" * 64, hunks=(one,)).paths == (
        "persona",
    )


# --- the prompt ---------------------------------------------------------------------------------


def test_the_prompt_is_the_authors_own_draft_request_and_schema_and_nothing_else() -> None:
    """Deleting this lets the prompt grow a field: another draft, the tool registry, the
    author's grants, anything a person may not open, which the model can then repeat back.

    Held structurally: the system half takes no parameters, so it is the same for every author,
    the user half parses to exactly the draft and the request, and the request is routed where
    the rung says. A second person's draft in the same store is the thing that must be absent.
    """
    store = saved_once()
    start(store, draft_id="draft_payroll", owner_id=STRANGER, at=NOW)
    save(
        store,
        "draft_payroll",
        whole(persona="Knows every salary."),
        by=STRANGER,
        at=NOW,
        base=NO_REVISION,
    )
    driver = FakeDriver()

    propose(store, DRAFT, ASK, by=OWNER, driver=driver, rung=RUNG)

    (request,) = driver.seen
    assert request == coauthor_request(whole(), ASK, rung=RUNG)
    assert (request.deployment_id, request.model) == (RUNG.deployment.id, RUNG.model)
    system, user = request.messages
    assert system == DriverMessage(role=Role.SYSTEM, content=system_prompt())
    assert user.role is Role.USER
    assert json.loads(user.content) == {"draft": whole(), "request": ASK}
    assert inspect.signature(system_prompt).parameters == {}
    assert set(inspect.signature(coauthor_request).parameters) == {"document", "ask", "rung"}


def test_an_empty_or_overlong_request_is_refused_before_any_model_is_called() -> None:
    """Deleting this lets a blank request spend a model call on nothing, or an unbounded one
    carry a pasted document the length of a book into the prompt."""
    store = saved_once()
    driver = FakeDriver()
    for ask in ("   ", "x" * (ASK_CHARS + 1)):
        with pytest.raises(BuilderError):
            propose(store, DRAFT, ask, by=OWNER, driver=driver, rung=RUNG)
    assert driver.seen == []
    propose(store, DRAFT, "x" * ASK_CHARS, by=OWNER, driver=driver, rung=RUNG)
    assert len(driver.seen) == 1


# --- the record ---------------------------------------------------------------------------------


def test_a_resolution_records_paths_and_never_values_at_an_aware_instant() -> None:
    """Deleting this lets the record of a decision grow a before and after, which puts a draft's
    values into whatever reads decisions, or lets it be kept at a naive instant."""
    declared = {one.name for one in fields(Resolution)}
    assert declared.isdisjoint(NAMES_THAT_WOULD_PUT_A_VALUE_IN_THE_RECORD)
    with pytest.raises(BuilderError):
        Resolution(
            draft_id=DRAFT,
            base_revision=1,
            accepted=(),
            rejected=("persona",),
            decided_by=OWNER,
            decided_at=datetime(2019, 3, 4, 9, 0),
            revision=None,
        )
