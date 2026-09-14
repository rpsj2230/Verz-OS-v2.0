"""A draft of a manifest: saved as often as somebody likes, and published only when it is whole.

`brain.builder.form` cuts the manifest schema into the seven sections a person fills in, and
`brain.builder.publish` decides what a publish may become. Between them sits the state nobody
had given a shape to: a manifest somebody is half way through, which has to survive being
closed and reopened, and has to be refused at the publish gate without being refused at the
save button. That is this module, and it adds one idea: **a draft is a sequence of revisions,
and a version is what publishing one of them produces.**

**A save is a new revision and never an edit in place.** Every save appends a `Revision`
numbered one past the last, holding the whole document, who saved it and when, and nothing
here or on `DraftStore` can change a revision once it exists. The cheaper design is one
mutable row with an `updated_at`, and it loses the question asked the first time a published
agent misbehaves: what did the author have in front of them, and when did that change.
`brain.ops.budgets` makes the argument about a ceiling (`A_BUDGET_ROW_IS_SUPERSEDED_NEVER_EDITED`)
and `brain.memory.correction` about a memory (`A_DELETED_MEMORY_CANNOT_EXPLAIN_ITSELF`); a
draft is the same record with the same failure. The body is held as the canonical JSON text
`brain.agents.template.canonical_value` writes, so a revision is immutable in fact rather than
a frozen dataclass wrapped round a dictionary anybody holding it can mutate.

**An incomplete draft is kept and reported, never refused.** A person fills a form in over
days and in any order, so a save that demanded a valid manifest would be a save that loses the
afternoon's work whenever the persona is still blank. Validity is therefore a report beside the
revision, one `Problem` per thing pydantic refuses, named by its path in the manifest, the way
`brain.agents.install.completeness` lists what an install is missing rather than returning a
badge. The report is the model's own validation of the manifest and nothing written here, so
a bound tightened on `ManifestIdentity` is a new problem in every draft that breaks it, with no
edit to this module. What a save does refuse is a body that is not a JSON object, because
that is not an incomplete manifest, it is not a document at all, and a store would otherwise
hold something no route could hand back.

**A save made from an older revision is refused rather than appended.** Two tabs open on one
draft both save; append-only means neither write destroys the other, and it also means the
second becomes the latest and the first is silently no longer what publishing would ship. So a
save names the revision it was made from and is refused when that is not the latest, which is
the version pin `brain.agents.template` puts on an instance, applied to a draft. Saving what is
already the latest revision returns that revision instead, for the reason
`brain.agents.lifecycle.enable` gives: a retry after a timeout must not fail.

**Publishing takes the latest revision or nothing.** Rejected: publishing the most recent
*valid* revision when the latest is incomplete. It reads as helpful and it ships a document the
author is not looking at: they saved an edit, the edit is half done, and what goes out is last
Tuesday's manifest under a new version number. A publish refused until the latest revision is
whole is a publish of what is on the screen.

**The version and the publisher are decided by publishing, never typed.** `identity.version`
and `identity.published_by` are two of the five sealed paths, and the form shows them because
it shows every path. A draft's values for them are ignored and replaced before validation: the
version is one past the newest on `brain.agents.upgrade.VersionShelf` for that template, or
`FIRST_VERSION`, and the publisher is the person publishing. A typed version is intent in
exactly the sense `compose.AN_AUTHORED_LIST_IS_INTENT_AND_THE_TOOLS_ARE_THE_AUTHORITY` means,
and a typed publisher is a provenance claim somebody made about somebody else. The shelf already
refuses a version that exists, so a collision is still refused where it always was.

**There is one signing path and this is not a second one.** A publish calls
`brain.agents.template.publish` to sign and `brain.agents.upgrade.publish_version` to shelve and
offer, so the digest, the signature and the refusal to amend a shelved version are those
modules' and nothing here restates them. It also goes through the builder's own gate: a
`PublishDecision` from `brain.builder.publish.decide` must be about this template, must carry no
refusals, and must satisfy `approval_refusals` with the draft's owner as the author, and the
record is `record_publish`, so the paths that moved since the previous version are recorded and
their values are not. A revision already published is not published again, because a second
version with an identical body is an upgrade badge on every install for nothing.

**Who may see and save a draft is its owner, by the predicate the console already uses for "a
person's own".** `brain.console.own_things.is_own` is `Scope.matches` over the owner field,
and it is what decides who may edit and who may delete a memory; a draft uses it for opening,
saving and publishing alike, so there is one answer rather than three that drift. The owner is
whoever started the draft, and there is no transfer and no shared draft: both are decisions
about co-authoring that nobody has taken, and inventing either here would be a permission
model written by the layer with the least reason to hold one. **A draft somebody else owns and
a draft that does not exist are one refusal**, raised from one place in one sentence, which is
`brain.agents.install.TemplateCatalogue.open_for`'s construction and the roster route's single
404. Nothing is read off a draft before that check, so there is no second path that could
answer differently.

**What this does not settle, said plainly.** The decision handed to `publish_draft` is checked
for its template, its refusals and its approvals, and not for having been computed over this
revision's ceiling: binding the two would need a digest on `PublishDecision`, and building the
ceiling here would need an `AgentRecord`, which a template has not become yet. Whoever composes
the route calls `decide` with the revision's ceiling. And nothing here decides who may publish
a new version of a template id somebody else first published; `approval_refusals` requires a
second person on every publish, which is the existing control, and lineage ownership is not
modelled anywhere in this repository to be reused.

**Persistence is the next step and it is not here.** `DraftStore` is the protocol a table has
to satisfy and `MemoryDraftStore` is the implementation the tests use, which is the arrangement
`brain.agents.upgrade.Declines` and `brain.ops.budgets` are both in. The table is two
append-only relations, revisions keyed by draft and number and publications keyed by draft and
revision, granted SELECT and INSERT and never UPDATE or DELETE, which is how
`agent.template_version` makes the same promise. No migration is written here. A draft does not
yet survive a restart.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock; every
instant is a parameter.

Task ids: M20.1.4
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Protocol

from pydantic import ValidationError

from brain.agents.install import Offer, TemplateCatalogue
from brain.agents.model import AgentAudience
from brain.agents.template import TemplateManifest, canonical_value, publish
from brain.agents.upgrade import VersionShelf, publish_version
from brain.builder.compose import BuilderError
from brain.builder.publish import (
    PublishDecision,
    PublishRecord,
    approval_refusals,
    record_publish,
)
from brain.console.own_things import is_own

# ------------------------------------------------------------------ written-down reasons
#: Why a save appends and never edits.
A_SAVE_IS_A_NEW_REVISION_AND_NEVER_AN_EDIT: Final = (
    "A draft that is edited in place cannot answer the question asked the first time a "
    "published agent misbehaves: what did the author have in front of them, and when did it "
    "change. So every save is a new revision numbered one past the last, holding the whole "
    "document, and no revision is changed once it exists. brain.ops.budgets argues the same "
    "about a ceiling and brain.memory.correction about a memory."
)

#: Why an invalid draft is saved anyway.
AN_INCOMPLETE_DRAFT_IS_KEPT_AND_REPORTED_NOT_REFUSED: Final = (
    "A manifest is filled in over days and in any order, so a save that demanded a valid one "
    "would lose an afternoon's work whenever one field was still blank. The revision is kept "
    "and its problems are reported beside it, by manifest path, the way "
    "brain.agents.install.completeness lists what an install is missing. Validity is refused "
    "at the publish, which is the only place an incomplete manifest could do harm."
)

#: Why a save must name the revision it was made from.
A_SAVE_FROM_AN_OLDER_REVISION_WOULD_HIDE_THE_ONE_IN_BETWEEN: Final = (
    "Two tabs open on one draft both save. Append-only means neither destroys the other, and "
    "it also means the second becomes the latest while the first is silently no longer what "
    "publishing would ship. A save names the revision it was made from and is refused when a "
    "later one exists, so the person whose edit would have been buried is the one told."
)

#: Why publishing does not fall back to an earlier valid revision.
ONLY_THE_LATEST_REVISION_IS_PUBLISHED: Final = (
    "Publishing the newest valid revision when the latest is incomplete reads as helpful and "
    "ships a document nobody is looking at: the author saved a half-finished edit and what "
    "goes out is an older manifest under a new version number. A publish is refused until the "
    "latest revision is whole, so what is published is what is on the screen."
)

#: Why the draft's own version and publisher are ignored.
THE_VERSION_AND_THE_PUBLISHER_ARE_DECIDED_BY_PUBLISHING: Final = (
    "identity.version and identity.published_by are sealed paths, and the form shows them "
    "because it shows every path. A typed version is intent and a typed publisher is a claim "
    "about somebody else, so both are replaced before a draft is validated: the version is one "
    "past the newest shelved for that template, or the first, and the publisher is the person "
    "publishing. The shelf still refuses a version that exists."
)

#: Why a draft somebody else owns is refused in the words used for a draft that is not there.
A_DRAFT_SOMEBODY_ELSE_OWNS_IS_A_DRAFT_THAT_DOES_NOT_EXIST: Final = (
    "A refusal that says a draft belongs to somebody else has told the reader it exists, and "
    "one attempt per id enumerates every draft in the installation along with the fact that "
    "somebody is building it. So the absent draft and the draft somebody else owns raise one "
    "error from one place in one sentence, and nothing is read off a draft before the "
    "ownership check has passed."
)

#: Why the same revision is not published twice.
A_REVISION_ALREADY_PUBLISHED_IS_NOT_A_NEW_VERSION: Final = (
    "Publishing a revision that is already a version would shelve a second version with an "
    "identical body, and every install of that template would show an upgrade badge for a "
    "change nobody made. Once a revision is published, a new version needs a new save."
)

#: Which way numbering starts. `ManifestIdentity.version` is `ge=1`, and a test holds the two
#: together rather than this module restating the bound.
FIRST_VERSION: Final = 1

#: The number a draft's first revision gets.
FIRST_REVISION: Final = 1

#: What a save names as its base when nothing has been saved yet: the revision before the first.
NO_REVISION: Final = FIRST_REVISION - 1


def decided_by_publishing(*, version: int, publisher: str) -> dict[str, Any]:
    """The manifest paths publishing sets, and what it sets them to.

    A function rather than two keys written into `_stamped`, so a test can hold every path it
    returns against `SEALED_PATHS`: a path publishing decides that an overlay could later
    change would be a decision made at publish and unmade at install.
    """
    return {"identity.published_by": publisher, "identity.version": version}


class NoDraftHereError(BuilderError):
    """A draft that does not exist, or that this person does not own. The same error for both.

    Its own type so a route can answer it with the one status it answers every absence with,
    and one type rather than two for `A_DRAFT_SOMEBODY_ELSE_OWNS_IS_A_DRAFT_THAT_DOES_NOT_EXIST`.
    """


def _no_draft_here(draft_id: str) -> NoDraftHereError:
    """The one sentence for both causes. The id is the one the caller supplied."""
    return NoDraftHereError(f"there is no draft named {draft_id!r} for you to open")


# ------------------------------------------------------------------------ the records
def _aware(at: datetime, what: str) -> None:
    if at.tzinfo is None:
        msg = (
            f"{what} at a naive instant is wrong by the host's offset from UTC, and it is what "
            "a later reader orders a draft's history by"
        )
        raise BuilderError(msg)


@dataclass(frozen=True)
class ManifestDraft:
    """One draft: its id, whose it is, and when it was started.

    Named apart from `brain.builder.compose.Draft`, which is an author's ticked tools and
    requested capabilities rather than a manifest, and which predates this module.
    """

    draft_id: str
    #: Whoever started it. See `A_DRAFT_SOMEBODY_ELSE_OWNS_IS_A_DRAFT_THAT_DOES_NOT_EXIST`.
    owner_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.draft_id.strip():
            msg = "a draft with no id cannot be reopened, saved to or published"
            raise BuilderError(msg)
        if not self.owner_id.strip():
            msg = "a draft with no owner is either nobody's or everybody's, and both are wrong"
            raise BuilderError(msg)
        _aware(self.created_at, "a draft started")


@dataclass(frozen=True)
class Revision:
    """One save of one draft: the whole document, as canonical JSON text, and who saved it.

    **The body is text, not a mapping**, so a revision cannot be changed by whoever holds it:
    a frozen dataclass holding a dictionary is immutable in its fields and mutable in the one
    field that matters. `document` parses a fresh copy on every call.
    """

    draft_id: str
    #: One past the previous revision, starting at `FIRST_REVISION`.
    number: int
    body: str
    saved_by: str
    saved_at: datetime

    def __post_init__(self) -> None:
        if self.number < FIRST_REVISION:
            msg = f"revision {self.number} is before the first, so no history can contain it"
            raise BuilderError(msg)
        _aware(self.saved_at, "a revision saved")
        if not isinstance(json.loads(self.body), dict):
            msg = "a revision's body is not a JSON object, so it is no part of any manifest"
            raise BuilderError(msg)

    def document(self) -> dict[str, Any]:
        """A fresh copy of the saved document."""
        parsed: dict[str, Any] = json.loads(self.body)
        return parsed


@dataclass(frozen=True)
class Problem:
    """One thing the manifest model refuses about a revision, named by where it is.

    `path` is pydantic's location joined with dots, so `authority.capabilities.0.value` names
    the first capability rather than the whole list. `message` is pydantic's own, and it may
    quote a value: the value is the author's own typing read back to them, so it discloses
    nothing they did not write.
    """

    path: str
    kind: str
    message: str


@dataclass(frozen=True)
class Validity:
    """Whether one revision is a whole manifest, and every reason it is not.

    The list is the point, as it is on `brain.agents.install.Completeness`: a flag tells
    somebody to go and look, and the looking is the part that does not happen.
    """

    draft_id: str
    revision: int
    problems: tuple[Problem, ...]

    @property
    def is_valid(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class Saved:
    """What a save answers: the revision that now stands, and whether it could be published."""

    revision: Revision
    validity: Validity


@dataclass(frozen=True)
class Publication:
    """Which revision of which draft became which version. Appended, never amended."""

    draft_id: str
    revision: int
    template_id: str
    version: int
    content_digest: str
    published_by: str
    published_at: datetime


@dataclass(frozen=True)
class Published:
    """Everything one publish produced: the offer, the link back to the draft, and the record."""

    offer: Offer
    publication: Publication
    record: PublishRecord


# ------------------------------------------------------------------------- the store
class DraftStore(Protocol):
    """What a table has to provide for drafts, and deliberately nothing that edits.

    Three appends and three reads. There is no method that updates a revision, removes one or
    replaces a publication, and `draft_gaps` reads this protocol's members to say so if one is
    added. A durable implementation enforces the same by its grants.
    """

    def add(self, draft: ManifestDraft) -> None: ...

    def get(self, draft_id: str) -> ManifestDraft | None: ...

    def append(self, revision: Revision) -> None: ...

    def revisions(self, draft_id: str) -> tuple[Revision, ...]: ...

    def record(self, publication: Publication) -> None: ...

    def publications(self, draft_id: str) -> tuple[Publication, ...]: ...


@dataclass
class MemoryDraftStore:
    """Drafts held in memory, keyed the way the tables would key them.

    An instance rather than a module-level singleton, for the reason
    `brain.agents.install.TemplateCatalogue` gives about its own. Its refusals are the
    constraints a table would carry: one draft per id, revisions numbered without a gap, and
    one publication per revision.
    """

    _drafts: dict[str, ManifestDraft] = field(default_factory=dict)
    _revisions: dict[str, list[Revision]] = field(default_factory=dict)
    _publications: dict[tuple[str, int], Publication] = field(default_factory=dict)

    def add(self, draft: ManifestDraft) -> None:
        """Keep a new draft, refusing an id already in use.

        A second draft under one id would give one history two owners, and the ownership
        check would then answer for whichever row a store happened to return.
        """
        if draft.draft_id in self._drafts:
            msg = f"a draft named {draft.draft_id!r} already exists"
            raise BuilderError(msg)
        self._drafts[draft.draft_id] = draft
        self._revisions[draft.draft_id] = []

    def get(self, draft_id: str) -> ManifestDraft | None:
        return self._drafts.get(draft_id)

    def append(self, revision: Revision) -> None:
        """Append a revision, refusing one for no draft or one that is not the next number."""
        kept = self._revisions.get(revision.draft_id)
        if kept is None:
            msg = f"revision {revision.number} belongs to no draft"
            raise BuilderError(msg)
        if revision.number != len(kept) + FIRST_REVISION:
            msg = (
                f"revision {revision.number} is not the next one after {len(kept)}; a history "
                f"with a gap or a repeat cannot be read in order. "
                f"{A_SAVE_IS_A_NEW_REVISION_AND_NEVER_AN_EDIT}"
            )
            raise BuilderError(msg)
        kept.append(revision)

    def revisions(self, draft_id: str) -> tuple[Revision, ...]:
        return tuple(self._revisions.get(draft_id, ()))

    def record(self, publication: Publication) -> None:
        """Record a publication, refusing a second one for the same revision."""
        key = (publication.draft_id, publication.revision)
        if key in self._publications:
            msg = (
                f"revision {publication.revision} is already published. "
                f"{A_REVISION_ALREADY_PUBLISHED_IS_NOT_A_NEW_VERSION}"
            )
            raise BuilderError(msg)
        self._publications[key] = publication

    def publications(self, draft_id: str) -> tuple[Publication, ...]:
        return tuple(
            one for (owner, _), one in sorted(self._publications.items()) if owner == draft_id
        )


# ---------------------------------------------------------------------- the operations
def start(store: DraftStore, *, draft_id: str, owner_id: str, at: datetime) -> ManifestDraft:
    """Start a draft owned by the person starting it, with nothing saved yet."""
    draft = ManifestDraft(draft_id=draft_id, owner_id=owner_id, created_at=at)
    store.add(draft)
    return draft


def _own(store: DraftStore, draft_id: str, principal_id: str) -> ManifestDraft:
    """The draft, if it exists and is this person's. One raise site for both causes.

    `brain.console.own_things.is_own` rather than an equality written here, so a draft and a
    memory are somebody's own by one predicate. See
    `A_DRAFT_SOMEBODY_ELSE_OWNS_IS_A_DRAFT_THAT_DOES_NOT_EXIST`.
    """
    draft = store.get(draft_id)
    if draft is None or not is_own(principal_id, draft.owner_id):
        raise _no_draft_here(draft_id)
    return draft


def history(store: DraftStore, draft_id: str, *, principal_id: str) -> tuple[Revision, ...]:
    """Every revision of this person's draft, oldest first."""
    _own(store, draft_id, principal_id)
    return store.revisions(draft_id)


def _body(document: object) -> str:
    """The canonical text of a document, refusing anything that is not a JSON object.

    Checked by reading the text back rather than by walking the value, because the failures
    are all silent conversions: `json.dumps` writes a key of `1` as `"1"`, a tuple as a list
    and a NaN as a token no JSON reader accepts, and each would store something other than what
    was saved. A document that does not read back as itself is refused.
    """
    if not isinstance(document, Mapping):
        msg = "a draft is a JSON object of manifest sections, and this is not an object"
        raise BuilderError(msg)
    try:
        body = canonical_value(dict(document))
    except (TypeError, ValueError) as error:
        msg = f"a draft has to be JSON, and this document could not be written as JSON: {error}"
        raise BuilderError(msg) from error
    if json.loads(body) != dict(document):
        msg = (
            "this document does not read back as itself once written as JSON, so what would "
            "be saved is not what was sent"
        )
        raise BuilderError(msg)
    return body


def _stamped(document: Mapping[str, Any], *, version: int, publisher: str) -> dict[str, Any]:
    """The document with the two identity fields publishing decides set by publishing.

    An identity that is absent or not an object is left alone, so the model reports it where
    it is rather than this reporting something else. See
    `THE_VERSION_AND_THE_PUBLISHER_ARE_DECIDED_BY_PUBLISHING`.
    """
    stamped = dict(document)
    identity = stamped.get("identity")
    if isinstance(identity, Mapping):
        decided = decided_by_publishing(version=version, publisher=publisher)
        stamped["identity"] = {
            **identity,
            **{path.partition(".")[2]: value for path, value in decided.items()},
        }
    return stamped


def _checked(
    document: Mapping[str, Any], *, version: int, publisher: str
) -> tuple[TemplateManifest | None, tuple[Problem, ...]]:
    """The manifest this document is, or every reason it is not one."""
    try:
        manifest = TemplateManifest.model_validate(
            _stamped(document, version=version, publisher=publisher)
        )
    except ValidationError as error:
        return None, tuple(
            Problem(
                path=".".join(str(part) for part in one["loc"]),
                kind=one["type"],
                message=one["msg"],
            )
            for one in error.errors(include_url=False, include_input=False, include_context=False)
        )
    return manifest, ()


def validity(revision: Revision) -> Validity:
    """Whether this revision would publish, and every reason it would not (M20.1.4).

    Validated at `FIRST_VERSION` with the saver as publisher. The version publishing assigns
    differs, and the model's only bound on a version is that it is at least the first, so no
    version publishing can assign changes the answer.
    """
    _, problems = _checked(revision.document(), version=FIRST_VERSION, publisher=revision.saved_by)
    return Validity(draft_id=revision.draft_id, revision=revision.number, problems=problems)


def save(
    store: DraftStore,
    draft_id: str,
    document: object,
    *,
    by: str,
    at: datetime,
    base: int,
) -> Saved:
    """Save a document as the next revision of this person's draft (M20.1.4).

    `base` is the revision the document was edited from, `NO_REVISION` for a draft never
    saved. Saving exactly the latest revision's document again returns that revision, and a
    base that is not the latest is refused. The order of those two checks is deliberate: a
    retry of a save that did land has a stale base and nothing to hide.

    An invalid document is saved. See `AN_INCOMPLETE_DRAFT_IS_KEPT_AND_REPORTED_NOT_REFUSED`.
    """
    _own(store, draft_id, by)
    body = _body(document)
    previous = store.revisions(draft_id)
    latest = previous[-1].number if previous else NO_REVISION
    if previous and previous[-1].body == body:
        return Saved(revision=previous[-1], validity=validity(previous[-1]))
    if base != latest:
        msg = (
            f"this was edited from revision {base} and revision {latest} has been saved since. "
            f"{A_SAVE_FROM_AN_OLDER_REVISION_WOULD_HIDE_THE_ONE_IN_BETWEEN}"
        )
        raise BuilderError(msg)
    revision = Revision(draft_id=draft_id, number=latest + 1, body=body, saved_by=by, saved_at=at)
    store.append(revision)
    return Saved(revision=revision, validity=validity(revision))


def next_version(shelf: VersionShelf, template_id: str) -> int:
    """The version a publish of this template would be: one past the newest shelved."""
    published = shelf.versions(template_id)
    return published[-1] + 1 if published else FIRST_VERSION


def gate_refusals(
    decision: PublishDecision,
    *,
    template_id: str,
    author_id: str,
    approvers: Sequence[str],
) -> tuple[str, ...]:
    """Everything the builder's publish gate says against publishing this draft.

    The decision is `brain.builder.publish.decide`'s and the approvals are
    `approval_refusals`', so nothing here is a second opinion about either. What is added is
    that the decision is about this template, because a decision made about another agent
    would otherwise wave this one through. The refusal does not name the other agent: the
    caller supplied it, and a message is the place a name leaks from.
    """
    refusals: list[str] = []
    if decision.agent_id != template_id:
        refusals.append(
            f"the publish decision handed in was made about a different agent, not {template_id!r}"
        )
    refusals.extend(decision.refusals)
    refusals.extend(approval_refusals(decision, author_id=author_id, approvers=approvers))
    return tuple(refusals)


def publish_draft(
    store: DraftStore,
    draft_id: str,
    *,
    by: str,
    at: datetime,
    key: str,
    shelf: VersionShelf,
    catalogue: TemplateCatalogue,
    audience: AgentAudience,
    decision: PublishDecision,
    approvers: Iterable[str],
) -> Published:
    """Publish the latest revision of this person's draft as the next version (M20.1.4).

    Refused, in this order, when there is no such draft for this person, when nothing has been
    saved, when the latest revision is already a version, when the latest revision is not a
    whole manifest, and when the gate says no. Every refusal comes before anything is signed,
    so a refused publish leaves the shelf and the catalogue as they were.

    Signed by `brain.agents.template.publish` and shelved and offered by
    `brain.agents.upgrade.publish_version`, and recorded by `brain.builder.publish.
    record_publish` against the newest version already shelved.
    """
    draft = _own(store, draft_id, by)
    given = tuple(approvers)
    revisions = store.revisions(draft_id)
    if not revisions:
        msg = f"nothing has been saved to {draft_id!r}, so there is nothing to publish"
        raise BuilderError(msg)
    latest = revisions[-1]
    if any(one.revision == latest.number for one in store.publications(draft_id)):
        msg = (
            f"revision {latest.number} is already published. "
            f"{A_REVISION_ALREADY_PUBLISHED_IS_NOT_A_NEW_VERSION}"
        )
        raise BuilderError(msg)

    document = latest.document()
    manifest, problems = _checked(document, version=FIRST_VERSION, publisher=by)
    if manifest is None:
        listed = "; ".join(f"{one.path}: {one.message}" for one in problems)
        msg = (
            f"revision {latest.number} is not a whole manifest yet ({listed}). "
            f"{ONLY_THE_LATEST_REVISION_IS_PUBLISHED}"
        )
        raise BuilderError(msg)

    template_id = manifest.identity.template_id
    version = next_version(shelf, template_id)
    refusals = gate_refusals(
        decision, template_id=template_id, author_id=draft.owner_id, approvers=given
    )
    if refusals:
        raise BuilderError("; ".join(refusals))

    manifest = TemplateManifest.model_validate(_stamped(document, version=version, publisher=by))
    before = shelf.newest(template_id).manifest.document() if version > FIRST_VERSION else {}
    signed = publish(manifest, key=key, signed_by=by, at=at)
    offer = publish_version(signed, shelf=shelf, catalogue=catalogue, audience=audience)
    publication = Publication(
        draft_id=draft_id,
        revision=latest.number,
        template_id=template_id,
        version=version,
        content_digest=signed.content_digest,
        published_by=by,
        published_at=at,
    )
    store.record(publication)
    record = record_publish(
        agent_id=template_id,
        actor_id=by,
        at=at,
        before=before,
        after=manifest.document(),
        decision=decision,
        approvers=given,
    )
    return Published(offer=offer, publication=publication, record=record)


# ------------------------------------------------------------------------- the diagnostic
#: Member names that would let a store change what was saved.
NAMES_THAT_WOULD_EDIT_A_REVISION: Final[frozenset[str]] = frozenset(
    {
        "amend",
        "delete",
        "edit",
        "overwrite",
        "purge",
        "remove",
        "replace",
        "set",
        "update",
        "upsert",
    }
)


def draft_gaps(*, store_type: type = DraftStore, revision_type: type = Revision) -> tuple[str, ...]:
    """Everything about drafts that would let a saved revision change after it was saved.

    Takes its inputs rather than reading this module's own types, for the reason
    `brain.builder.compose.compose_gaps` gives: a diagnostic that can only run against the
    healthy tree has nothing to report, so every one of its refusals survives a mutation.
    """
    gaps = [
        f"{store_type.__name__}.{name} would let a saved revision be changed. "
        f"{A_SAVE_IS_A_NEW_REVISION_AND_NEVER_AN_EDIT}"
        for name, _ in inspect.getmembers(store_type, callable)
        if name in NAMES_THAT_WOULD_EDIT_A_REVISION
    ]
    params = getattr(revision_type, "__dataclass_params__", None)
    if params is None or not params.frozen:
        gaps.append(
            f"{revision_type.__name__} is not a frozen dataclass, so a revision somebody holds "
            f"can be changed in place. {A_SAVE_IS_A_NEW_REVISION_AND_NEVER_AN_EDIT}"
        )
    return tuple(gaps)
