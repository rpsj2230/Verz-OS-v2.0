"""Drafts of a manifest held to the rules a save and a publish have to keep (M20.1.4).

A draft is where a manifest lives before it is whole, so the two failures worth testing pull
in opposite directions. A save that refused an incomplete manifest would lose somebody's work;
a publish that accepted one would ship it. Between them sit the ways a history goes quietly
wrong: an edit in place, a save from a stale tab burying another, a version number somebody
typed, and a refusal that tells a stranger a draft exists.

Real `TemplateManifest` validation, real signing through `brain.agents.template.publish`, a
real `VersionShelf` and `TemplateCatalogue`, and a real `PublishDecision` from
`brain.builder.publish.decide`. A stand-in for any of them would be this module agreeing with
itself.

The instants are in 2019 on purpose. Nothing here is about the present, and a fixture date
near the wall clock is a test that fails on a day nobody chose.

Task ids: M20.1.4
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.agents.install import TemplateCatalogue
from brain.agents.model import AgentAudience
from brain.agents.template import (
    MANIFEST_PATHS,
    SEALED_PATHS,
    ManifestIdentity,
    TemplateManifest,
    publish,
    verify,
)
from brain.agents.upgrade import VersionShelf
from brain.builder.compose import BuilderError
from brain.builder.drafts import (
    FIRST_REVISION,
    FIRST_VERSION,
    NO_REVISION,
    DraftStore,
    ManifestDraft,
    MemoryDraftStore,
    NoDraftHereError,
    Publication,
    Published,
    Revision,
    decided_by_publishing,
    draft_gaps,
    history,
    next_version,
    publish_draft,
    save,
    start,
    validity,
)
from brain.builder.publish import Check, CheckOrigin, PublishDecision, decide
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.knowledge.visibility import Visibility

NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
LATER = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)
KEY = "a-signing-key"
OWNER = "u_priya"
STRANGER = "u_tan"
REVIEWER = "u_hafiz"
DRAFT = "draft_renewals"
TEMPLATE = "renewal_chaser_template"
AUDIENCE = AgentAudience(level=Visibility.PERSONAL, owner_id=OWNER)


def whole(**extra: Any) -> dict[str, Any]:
    """The smallest document that is a whole manifest once publishing stamps its identity."""
    document: dict[str, Any] = {
        "identity": {"template_id": TEMPLATE, "display_name": "Renewal chaser"}
    }
    document.update(extra)
    return document


def a_decision(agent_id: str = TEMPLATE, checks: Sequence[Check] = ()) -> PublishDecision:
    """The gate's own decision from `decide`, over a ceiling that does not change."""
    ceiling = EntitlementSet(
        principal_id="agent:renewal_chaser",
        grants=(Grant(capability=Capability(value="read:ticket.subject"), scope=Scope()),),
    )
    return decide(
        agent_id=agent_id,
        current_rung=AutonomyTier.SHADOW,
        before_ceiling=ceiling,
        after_ceiling=ceiling,
        checks=checks,
        now=NOW,
    )


def started() -> MemoryDraftStore:
    store = MemoryDraftStore()
    start(store, draft_id=DRAFT, owner_id=OWNER, at=NOW)
    return store


def publish_it(
    store: DraftStore,
    shelf: VersionShelf,
    *,
    by: str = OWNER,
    catalogue: TemplateCatalogue | None = None,
    decision: PublishDecision | None = None,
    approvers: Iterable[str] = (REVIEWER,),
) -> Published:
    return publish_draft(
        store,
        DRAFT,
        by=by,
        at=LATER,
        key=KEY,
        shelf=shelf,
        catalogue=TemplateCatalogue() if catalogue is None else catalogue,
        audience=AUDIENCE,
        decision=a_decision() if decision is None else decision,
        approvers=approvers,
    )


def shelved_elsewhere(shelf: VersionShelf, version: int) -> None:
    """A version of the template published by somebody else, before this draft existed."""
    manifest = TemplateManifest(
        identity=ManifestIdentity(
            template_id=TEMPLATE, version=version, published_by="u_wei_ling", display_name="Old"
        )
    )
    shelf.publish(publish(manifest, key=KEY, signed_by="u_wei_ling", at=NOW))


# --- a save appends -------------------------------------------------------------------------


def test_each_save_is_a_new_revision_and_the_earlier_ones_are_unchanged() -> None:
    """Deleting this loses the only test that a second save leaves the first one standing.

    A save that replaced the latest revision in place, or a store that handed back a mutable
    document, would pass every other test here that looks at the latest revision alone.
    """
    store = started()
    first = save(store, DRAFT, whole(), by=OWNER, at=NOW, base=NO_REVISION)
    second = save(
        store, DRAFT, whole(persona="Chase renewals."), by=OWNER, at=LATER, base=FIRST_REVISION
    )

    kept = history(store, DRAFT, principal_id=OWNER)
    assert [one.number for one in kept] == [1, 2]
    assert kept == (first.revision, second.revision)
    assert kept[0].document() == whole()
    assert kept[1].document() == whole(persona="Chase renewals.")
    assert (kept[0].saved_by, kept[0].saved_at) == (OWNER, NOW)

    handed_out = kept[0].document()
    handed_out["persona"] = "changed by whoever held it"
    assert history(store, DRAFT, principal_id=OWNER)[0].document() == whole()


def test_an_incomplete_manifest_is_saved_and_every_problem_is_named_by_its_path() -> None:
    """Deleting this lets a save refuse an incomplete draft, or keep it with no report.

    Either passes a suite that only saves whole manifests: the first loses an afternoon's work
    whenever a field is blank, and the second leaves the author finding out at the publish.
    """
    store = started()
    document = {
        "identity": {"template_id": TEMPLATE},
        "tier": "gigantic",
        "authority": {"capabilities": [{"value": "nope"}]},
    }
    saved = save(store, DRAFT, document, by=OWNER, at=NOW, base=NO_REVISION)

    assert history(store, DRAFT, principal_id=OWNER) == (saved.revision,)
    assert not saved.validity.is_valid
    assert saved.validity.revision == saved.revision.number
    assert {one.path for one in saved.validity.problems} == {
        "identity.display_name",
        "tier",
        "authority.capabilities.0.value",
    }
    assert {one.path: one.kind for one in saved.validity.problems}["identity.display_name"] == (
        "missing"
    )


def test_a_whole_manifest_is_valid_with_nothing_to_report() -> None:
    """Deleting this leaves every validity test a refusal, which "always invalid" would pass."""
    store = started()
    saved = save(store, DRAFT, whole(), by=OWNER, at=NOW, base=NO_REVISION)

    assert saved.validity.is_valid
    assert saved.validity.problems == ()
    assert validity(saved.revision) == saved.validity


def test_the_version_and_publisher_a_draft_types_are_replaced_before_it_is_validated() -> None:
    """Deleting this lets a typed version or publisher decide whether a draft is valid.

    A version of 0 and a blank publisher are both refused by the model, so a draft carrying
    them would be reported invalid for two fields publishing overwrites anyway, and a draft
    omitting them would be told to fill in a number nobody is meant to choose.
    """
    typed = whole()
    typed["identity"].update({"version": 0, "published_by": ""})
    store = started()
    saved = save(store, DRAFT, typed, by=OWNER, at=NOW, base=NO_REVISION)
    assert saved.validity.is_valid

    shelf = VersionShelf()
    publish_it(store, shelf)
    identity = shelf.newest(TEMPLATE).manifest.identity
    assert (identity.version, identity.published_by) == (FIRST_VERSION, OWNER)


def test_an_identity_that_is_not_an_object_is_reported_where_it_is() -> None:
    """Deleting this lets stamping the identity crash on a draft whose identity is not an object.

    The form submits objects, and a draft saved by anything else can hold a string there. It
    is an incomplete draft like any other and must be kept and reported, not raise.
    """
    store = started()
    saved = save(store, DRAFT, {"identity": "renewals"}, by=OWNER, at=NOW, base=NO_REVISION)

    assert [one.path for one in saved.validity.problems] == ["identity"]


# --- a save from a stale revision -----------------------------------------------------------


def containing_itself() -> dict[str, Any]:
    """A document `json.dumps` refuses with a `ValueError` rather than a `TypeError`."""
    document: dict[str, Any] = {}
    document["persona"] = document
    return document


def test_a_save_edited_from_an_older_revision_is_refused_and_appends_nothing() -> None:
    """Deleting this lets a stale tab's save become the latest and bury the save before it.

    Append-only keeps both, so nothing is lost from the history, and what publishing would
    ship silently stops being the edit somebody made a minute ago.
    """
    store = started()
    save(store, DRAFT, whole(), by=OWNER, at=NOW, base=NO_REVISION)
    save(store, DRAFT, whole(persona="From tab one."), by=OWNER, at=NOW, base=FIRST_REVISION)

    with pytest.raises(BuilderError, match="revision 2 has been saved since"):
        save(store, DRAFT, whole(persona="From tab two."), by=OWNER, at=LATER, base=FIRST_REVISION)
    assert len(history(store, DRAFT, principal_id=OWNER)) == 2


def test_saving_the_latest_document_again_returns_that_revision_whatever_base_it_names() -> None:
    """Deleting this lets a retried save fail, or append a revision identical to the one before.

    A retry after a timeout carries the base it was sent with, which is stale once the first
    attempt landed. The document is compared as canonical JSON, so a retry whose keys arrive
    in another order is the same save.
    """
    store = started()
    first = save(store, DRAFT, whole(persona="Once."), by=OWNER, at=NOW, base=NO_REVISION)
    reordered = {"persona": "Once.", "identity": whole()["identity"]}
    again = save(store, DRAFT, reordered, by=OWNER, at=LATER, base=NO_REVISION)

    assert again.revision == first.revision
    assert again.validity == first.validity
    assert len(history(store, DRAFT, principal_id=OWNER)) == 1


@pytest.mark.parametrize(
    "document",
    [
        pytest.param([whole()], id="a list"),
        pytest.param("identity", id="a string"),
        pytest.param([["persona", "Chase renewals."]], id="a list of pairs dict would accept"),
        pytest.param(containing_itself(), id="a document that contains itself"),
        pytest.param({"skills": {"a", "b"}}, id="a set inside"),
        pytest.param({"persona": float("nan")}, id="a NaN"),
        pytest.param({1: "one"}, id="a key that is not a string"),
        pytest.param({"connectors": ("xero",)}, id="a tuple that reads back as a list"),
    ],
)
def test_a_body_that_is_not_a_json_object_is_refused_rather_than_kept(document: object) -> None:
    """Deleting this lets a store hold a body that is not what was sent, or is not JSON at all.

    Each case is a different door: a value that is not an object, including a list of pairs
    `dict` would happily turn into one; two that `json.dumps` cannot write, one with a
    `TypeError` and one with a `ValueError`; and three it writes as something else.
    """
    store = started()
    with pytest.raises(BuilderError):
        save(store, DRAFT, document, by=OWNER, at=NOW, base=NO_REVISION)
    assert history(store, DRAFT, principal_id=OWNER) == ()


# --- the records ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(
            lambda: Revision(draft_id=DRAFT, number=0, body="{}", saved_by=OWNER, saved_at=NOW),
            id="before the first",
        ),
        pytest.param(
            lambda: Revision(
                draft_id=DRAFT, number=1, body="{}", saved_by=OWNER, saved_at=datetime(2019, 3, 4)
            ),
            id="a naive instant",
        ),
        pytest.param(
            lambda: Revision(draft_id=DRAFT, number=1, body="[]", saved_by=OWNER, saved_at=NOW),
            id="a body that is not an object",
        ),
        pytest.param(
            lambda: ManifestDraft(draft_id=" ", owner_id=OWNER, created_at=NOW), id="no id"
        ),
        pytest.param(
            lambda: ManifestDraft(draft_id=DRAFT, owner_id="", created_at=NOW), id="no owner"
        ),
        pytest.param(
            lambda: ManifestDraft(draft_id=DRAFT, owner_id=OWNER, created_at=datetime(2019, 3, 4)),
            id="a draft started at a naive instant",
        ),
    ],
)
def test_a_record_that_cannot_be_ordered_or_owned_cannot_be_constructed(
    build: Callable[[], object],
) -> None:
    """Deleting this lets a row read back from a table become a revision nobody can place.

    A revision numbered before the first, one at a naive instant and one whose body is not an
    object each construct through the store's read path without passing `save`, and a draft
    with no owner is either nobody's or everybody's to `is_own`.
    """
    with pytest.raises(BuilderError):
        build()


def test_a_record_that_can_be_ordered_and_owned_is_constructed() -> None:
    """Deleting this leaves the refusals above satisfied by constructors that refuse everything."""
    revision = Revision(
        draft_id=DRAFT, number=FIRST_REVISION, body="{}", saved_by=OWNER, saved_at=NOW
    )
    assert revision.document() == {}
    assert ManifestDraft(draft_id=DRAFT, owner_id=OWNER, created_at=NOW).owner_id == OWNER


def test_the_store_refuses_a_duplicate_draft_a_gap_in_a_history_and_a_second_publication() -> None:
    """Deleting this leaves the store's constraints untested, and they are what a table must carry.

    `save` never asks the store for a gap or a repeat, so without this a store that accepted
    either would pass: the history it then returns cannot be read in order.
    """
    store = started()
    with pytest.raises(BuilderError, match="already exists"):
        start(store, draft_id=DRAFT, owner_id=STRANGER, at=NOW)
    assert store.get(DRAFT) == ManifestDraft(draft_id=DRAFT, owner_id=OWNER, created_at=NOW)

    def revision(number: int, draft_id: str = DRAFT) -> Revision:
        return Revision(draft_id=draft_id, number=number, body="{}", saved_by=OWNER, saved_at=NOW)

    with pytest.raises(BuilderError, match="belongs to no draft"):
        store.append(revision(1, draft_id="draft_nowhere"))
    with pytest.raises(BuilderError, match="not the next one"):
        store.append(revision(2))
    store.append(revision(1))
    with pytest.raises(BuilderError, match="not the next one"):
        store.append(revision(1))
    store.append(revision(2))
    assert [one.number for one in store.revisions(DRAFT)] == [1, 2]

    other = "draft_other"
    start(store, draft_id=other, owner_id=OWNER, at=NOW)

    def publication(draft_id: str, number: int) -> Publication:
        return Publication(
            draft_id=draft_id,
            revision=number,
            template_id=TEMPLATE,
            version=number,
            content_digest="d" * 64,
            published_by=OWNER,
            published_at=NOW,
        )

    store.record(publication(DRAFT, 2))
    store.record(publication(other, 1))
    store.record(publication(DRAFT, 1))
    with pytest.raises(BuilderError, match="already published"):
        store.record(publication(DRAFT, 2))
    assert store.publications(DRAFT) == (publication(DRAFT, 1), publication(DRAFT, 2))


# --- ownership ------------------------------------------------------------------------------


def test_somebody_elses_draft_is_refused_in_the_words_used_for_one_that_does_not_exist() -> None:
    """Deleting this lets opening, saving or publishing somebody else's draft say that it exists.

    One attempt per id then enumerates every draft in the installation. The owner's own
    history, save and publish are asserted in the tests above, so this is the refusal half.
    """
    owned = started()
    save(owned, DRAFT, whole(), by=OWNER, at=NOW, base=NO_REVISION)
    absent = MemoryDraftStore()
    shelf = VersionShelf()

    operations: dict[str, Callable[[DraftStore], object]] = {
        "history": lambda store: history(store, DRAFT, principal_id=STRANGER),
        "save": lambda store: save(
            store, DRAFT, whole(), by=STRANGER, at=LATER, base=FIRST_REVISION
        ),
        "publish": lambda store: publish_it(store, shelf, by=STRANGER),
    }
    for name, operation in operations.items():
        with pytest.raises(NoDraftHereError) as someone_elses:
            operation(owned)
        with pytest.raises(NoDraftHereError) as nowhere:
            operation(absent)
        assert str(someone_elses.value) == str(nowhere.value), name

    assert len(history(owned, DRAFT, principal_id=OWNER)) == 1
    assert shelf.versions(TEMPLATE) == ()


# --- publishing -----------------------------------------------------------------------------


def test_publishing_signs_the_latest_revision_by_the_template_path_as_the_first_version() -> None:
    """Deleting this leaves no test that a draft becomes a version at all, or by which path.

    The signed manifest is compared with what `brain.agents.template.publish` makes of the
    same body, so a second signing path producing a different signature fails here.
    """
    store = started()
    save(store, DRAFT, whole(persona="Chase renewals."), by=OWNER, at=NOW, base=NO_REVISION)
    shelf = VersionShelf()
    catalogue = TemplateCatalogue()

    published = publish_it(store, shelf, catalogue=catalogue)

    signed = shelf.newest(TEMPLATE)
    verify(signed, key=KEY)
    assert signed == publish(signed.manifest, key=KEY, signed_by=OWNER, at=LATER)
    assert signed.manifest.persona == "Chase renewals."
    assert shelf.versions(TEMPLATE) == (FIRST_VERSION,)
    assert published.offer.signed == signed
    assert published.publication == Publication(
        draft_id=DRAFT,
        revision=FIRST_REVISION,
        template_id=TEMPLATE,
        version=FIRST_VERSION,
        content_digest=signed.content_digest,
        published_by=OWNER,
        published_at=LATER,
    )
    assert store.publications(DRAFT) == (published.publication,)


def test_the_next_publish_is_one_past_the_newest_version_on_the_shelf_whoever_shelved_it() -> None:
    """Deleting this lets a draft publish at the version it typed, or at a count of its own saves.

    Two versions already shelved by somebody else and a draft typing version 1 is the case
    both wrong answers get wrong: the typed one collides and the counted one starts at 1.
    """
    assert next_version(VersionShelf(), TEMPLATE) == FIRST_VERSION
    shelf = VersionShelf()
    shelved_elsewhere(shelf, 1)
    shelved_elsewhere(shelf, 2)
    typed = whole()
    typed["identity"]["version"] = 1
    store = started()
    save(store, DRAFT, typed, by=OWNER, at=NOW, base=NO_REVISION)

    published = publish_it(store, shelf)

    assert published.publication.version == 3
    assert shelf.versions(TEMPLATE) == (1, 2, 3)


def test_the_publish_record_holds_the_paths_that_moved_since_the_previous_version() -> None:
    """Deleting this lets the record be taken against nothing, or against the wrong version.

    A second publish that changed only the persona must record the persona and the version
    number, and nothing else, which it does only when the record is built against the newest
    version already shelved.
    """
    store = started()
    save(store, DRAFT, whole(persona="First."), by=OWNER, at=NOW, base=NO_REVISION)
    shelf = VersionShelf()
    first = publish_it(store, shelf)
    assert set(first.record.paths) == set(MANIFEST_PATHS)

    save(store, DRAFT, whole(persona="Second."), by=OWNER, at=LATER, base=FIRST_REVISION)
    # A generator, which the gate and then the record each read: kept as it came, the record
    # would find it already exhausted and say nobody approved a publish two people did.
    second = publish_it(store, shelf, approvers=(one for one in (REVIEWER,)))

    assert second.publication.version == 2
    assert set(second.record.paths) == {"identity.version", "persona"}
    assert (second.record.actor_id, second.record.approvers) == (OWNER, (REVIEWER,))


def test_a_draft_with_nothing_saved_cannot_be_published() -> None:
    """Deleting this lets an empty draft's publish fail with an index error, not a refusal."""
    shelf = VersionShelf()
    with pytest.raises(BuilderError, match="nothing has been saved"):
        publish_it(started(), shelf)
    assert shelf.versions(TEMPLATE) == ()


def test_an_incomplete_latest_revision_is_not_published_though_an_earlier_one_was_whole() -> None:
    """Deleting this lets a publish fall back to an older valid revision, or ship an invalid one.

    The fallback ships a document the author is not looking at under a new version number.
    """
    store = started()
    save(store, DRAFT, whole(), by=OWNER, at=NOW, base=NO_REVISION)
    save(
        store,
        DRAFT,
        {"identity": {"template_id": TEMPLATE}},
        by=OWNER,
        at=LATER,
        base=FIRST_REVISION,
    )
    shelf = VersionShelf()

    with pytest.raises(BuilderError, match="revision 2 is not a whole manifest"):
        publish_it(store, shelf)
    assert shelf.versions(TEMPLATE) == ()
    assert store.publications(DRAFT) == ()


def test_a_revision_already_published_is_not_published_again_as_another_version() -> None:
    """Deleting this lets one body be shelved twice, putting an upgrade badge on every install.

    The shelf is asserted rather than the error, because the store also refuses a second
    publication of a revision and would do so only after the second version was shelved.
    """
    store = started()
    save(store, DRAFT, whole(), by=OWNER, at=NOW, base=NO_REVISION)
    shelf = VersionShelf()
    publish_it(store, shelf)

    with pytest.raises(BuilderError, match="already published"):
        publish_it(store, shelf)
    assert shelf.versions(TEMPLATE) == (FIRST_VERSION,)


@pytest.mark.parametrize(
    ("decision", "approvers"),
    [
        pytest.param(a_decision(agent_id="another_agent"), (REVIEWER,), id="about another agent"),
        pytest.param(
            a_decision(
                checks=(
                    Check(name="canary.contract_value", origin=CheckOrigin.SYSTEM, passed=False),
                )
            ),
            (REVIEWER,),
            id="a system check failed",
        ),
        pytest.param(a_decision(), (OWNER,), id="approved by its own author"),
        pytest.param(a_decision(), (), id="approved by nobody"),
    ],
)
def test_a_publish_the_gate_does_not_pass_leaves_the_shelf_as_it_was(
    decision: PublishDecision, approvers: Sequence[str]
) -> None:
    """Deleting this makes a draft a route around the builder's publish gate.

    Each case is one of the gate's refusals, and the positive sibling is the publish test
    above with a decision about this template and a reviewer who is not the author.
    """
    store = started()
    save(store, DRAFT, whole(), by=OWNER, at=NOW, base=NO_REVISION)
    shelf = VersionShelf()

    with pytest.raises(BuilderError) as refused:
        publish_it(store, shelf, decision=decision, approvers=approvers)
    assert "another_agent" not in str(refused.value)
    assert shelf.versions(TEMPLATE) == ()
    assert store.publications(DRAFT) == ()


# --- what the rules are held against --------------------------------------------------------


def test_what_publishing_decides_is_sealed_and_numbering_starts_where_the_model_does() -> None:
    """Deleting this lets publishing decide a path an overlay can undo, or start below the model.

    A path set at publish that an install may overlay is a decision made once and unmade
    locally, and a first version below the model's minimum refuses every first publish.
    """
    assert set(decided_by_publishing(version=FIRST_VERSION, publisher=OWNER)) <= set(SEALED_PATHS)
    version_schema = ManifestIdentity.model_json_schema()["properties"]["version"]
    assert version_schema["minimum"] == FIRST_VERSION
    assert NO_REVISION < FIRST_REVISION


def test_a_store_that_could_change_a_saved_revision_is_reported() -> None:
    """Deleting this lets an `update` on the store, or a thawed `Revision`, arrive unremarked.

    Both the protocol and the in-memory store are checked clean, and two constructed types are
    checked dirty, because a diagnostic tested only on the healthy tree reports nothing.
    """
    assert draft_gaps() == ()
    assert draft_gaps(store_type=MemoryDraftStore) == ()

    class EditableStore:
        def update(self, revision: Revision) -> None: ...

    @dataclass
    class ThawedRevision:
        body: str

    class NotADataclass:
        body = ""

    found = draft_gaps(store_type=EditableStore, revision_type=ThawedRevision)
    assert len(found) == 2
    assert found[0].startswith("EditableStore.update ")
    assert found[1].startswith("ThawedRevision is not a frozen dataclass")
    assert draft_gaps(revision_type=NotADataclass)[0].startswith("NotADataclass is not")
