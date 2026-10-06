"""An agent made or changed through a draft: what the draft becomes here, and who has to agree.

`brain.builder.drafts` says what a draft is (revisions, never an edit in place, only the latest
publishes) and `brain.builder.publish` says what a publish may become (a widening demotes and asks
for a second person). Both were written about a *template*, a manifest offered to whoever installs
it. The console's New agent and Edit as a draft make one *agent* on this install, and this module is
the difference between the two, decided once so the routes, the store and the tests share it.

**One draft makes or changes one agent, and the agent's own lineage is the template.** A published
draft is signed as a version of a template whose id is the agent's own id, and the agent is an
install of that version, so a new agent and an edited one both travel
`brain.agents.template.install` and `brain.agents.install.settle` like every other agent, and an
edit of an agent installed from a shared template becomes the first version of its own lineage
rather than a new version of the shared one. Rejected: publishing an edit as the next version of the
template it came from. Every other agent installed from that template would then be offered the
change as an upgrade, and a person editing one agent would have edited all of them. See
`ONE_DRAFT_MAKES_OR_CHANGES_ONE_AGENT`.

**The slug is fixed when the draft starts.** A new agent's id is minted then, by
`brain.agents.creation.mint_agent_id`, and written into the document's `identity.template_id` on
every save, so the name a person types can change and the address cannot.

**A publish that reaches no further than before goes out on the author's word; a wider one waits for
a second person who is not the author.** `brain.builder.publish.approvers_needed` is two for a
widening and one otherwise, and here the author is the first: a publish is the author's own act over
an agent their authority reaches, which is Part 4.1's "same or narrower ceiling: publishes".
`brain.builder.publish.approval_refusals` counts approvers other than the author, because a template
version is offered to everybody who installs it and every one needs a reader who did not write it;
using it here would put a second person in front of an instruction edit to one agent, and a gate
people meet on every edit is a gate people learn to wave through. See
`THE_AUTHOR_IS_THE_FIRST_OF_THE_PEOPLE_A_PUBLISH_NEEDS`.

**What counts as wider is `brain.agents.creation.widened`**: a capability or a scope clause the old
ceiling did not have, a tool it was not allowed, or a larger side effect. A new agent is compared
with an agent that reaches nothing, so any capability, tool or side effect at all is a widening:
nothing an author builds from scratch reaches anything on their word alone. See
`A_NEW_AGENT_WIDENS_FROM_NOTHING`.

**The second person must hold everything the agent may reach.** `brain.console.scoped_authority.
may_approve_publication` is the existing rule for who may approve a publication, and it is asked of
the approver's own reach over the whole ceiling. That is what makes the second pair of eyes a pair
that could see the widening: an approver who could not have written the ceiling themselves is
approving reach they have never held. **An agent is a lens and never a principal**: none of this
grants anybody anything, and every run through the agent is still `E(caller) ∩ agent_ceiling`,
computed only by `EntitlementSet.intersect` where the run happens. Nothing here computes a reach.

**No rung above Shadow is published from a draft.** A new agent starts at Shadow on every target
(`brain.agents.install_store.AN_INSTALL_STARTS_AT_SHADOW_ON_EVERY_TARGET`) and a rung is raised from
evidence of the agent's own runs (`brain.console.reach_view.may_raise`), which no draft carries. So
a draft naming a higher rung is a problem the check lists, before anybody is asked to approve it,
rather than a publish that quietly lands lower than it said. See
`A_RUNG_IS_RAISED_WITH_EVIDENCE_AND_NEVER_BY_A_DRAFT`.

**What a draft would become is asked of this install without signing anything that is kept.**
`settle` takes a signed manifest because an installed agent is always one, and the check and the
rehearsal ask the question before anybody publishes. So they sign with a key made for the question
and dropped with it (`carrier`): nothing so signed is stored, verified or returned, and the version
a publish stores is signed with this install's own key or not at all. See
`A_QUESTION_ASKED_BEFORE_PUBLISHING_IS_SIGNED_WITH_A_KEY_NOBODY_KEEPS`.

Scope: domain logic. Nothing here opens a connection or reads a clock.

Task ids: M27.11.6, M27.15.31, M13.7.4
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.agents.creation import widened
from brain.agents.install import Installation, settle
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord, entitlement_ceiling
from brain.agents.template import (
    BLANK_MANIFEST,
    SignedManifest,
    TemplateError,
    TemplateInstance,
    TemplateManifest,
    install,
    publish,
)
from brain.builder.compose import SECTION_OF_PATH, BuilderError, Section, paths_in
from brain.builder.draft_words import DraftAct, DraftKind, DraftState
from brain.builder.drafts import (
    FIRST_VERSION,
    ManifestDraft,
    Problem,
    Revision,
    whole_manifest,
)
from brain.builder.form import FIELD_WORDS, SECTION_TITLES
from brain.builder.publish import (
    APPROVERS_FOR_AN_ORDINARY_PUBLISH,
    approvers_needed,
)
from brain.connectors.registry import ConnectorRegistry
from brain.console.scoped_authority import may_approve_publication
from brain.core.entitlement import EntitlementSet
from brain.gate.injection import AutonomyTier
from brain.tools.registry import ToolRegistry

# ------------------------------------------------------------------ written-down reasons
#: Why a published draft is a version of the agent's own template.
ONE_DRAFT_MAKES_OR_CHANGES_ONE_AGENT: Final = (
    "A draft is published as a version of a template whose id is the agent's own, and the agent "
    "is an install of it. Publishing an edit as the next version of a shared template would offer "
    "the change to every other agent installed from it as an upgrade, so editing one agent would "
    "have edited all of them."
)

#: Why the author counts as the first approver here and not in `approval_refusals`.
THE_AUTHOR_IS_THE_FIRST_OF_THE_PEOPLE_A_PUBLISH_NEEDS: Final = (
    "approvers_needed is two for a widening and one otherwise, and a draft publishes one agent the "
    "author's own authority reaches, so the author is the first: a publish that reaches no further "
    "goes out on their word, and a wider one waits for one more person who is not them. A template "
    "version is different, being offered to everybody who installs it, which is why "
    "approval_refusals counts only people other than the author."
)

#: Why the author alone never publishes a widening.
NOBODY_PUBLISHES_A_WIDENING_THEY_AUTHORED_ALONE: Final = (
    "A ceiling can outgrow the reach of the person who wrote it, and they cannot see that from any "
    "seat they occupy, because every run of theirs is narrowed to what they hold. So a publish "
    "that reaches further than the agent did waits for a second person, who is not its author and "
    "whose own reach covers everything the agent may reach."
)

#: Why a new agent's ceiling is compared with nothing.
A_NEW_AGENT_WIDENS_FROM_NOTHING: Final = (
    "A new agent is compared with an agent that reaches nothing, so any capability, tool or side "
    "effect it has is a widening, and nothing built from scratch reaches anything on its author's "
    "word alone."
)

#: Why a draft naming a rung above Shadow is refused rather than published lower.
A_RUNG_IS_RAISED_WITH_EVIDENCE_AND_NEVER_BY_A_DRAFT: Final = (
    "Every action of a new or changed agent starts at Shadow, and a rung is raised from evidence "
    "of "
    "the agent's own runs, which a draft does not carry. A draft naming a higher rung is listed as "
    "a problem before anybody approves it, rather than published at a rung other than the one it "
    "names."
)

#: Why the check and the rehearsal sign with a key they throw away.
A_QUESTION_ASKED_BEFORE_PUBLISHING_IS_SIGNED_WITH_A_KEY_NOBODY_KEEPS: Final = (
    "settle takes a signed manifest, because an installed agent is always one, and the check and "
    "the rehearsal ask what a draft would become before anybody publishes it. They sign with a key "
    "made for that one question and dropped with it: nothing so signed is stored, verified or "
    "returned, and the version a publish keeps is signed with this install's own key or not at all."
)

#: Why a published draft takes no further save.
A_PUBLISHED_DRAFT_IS_FINISHED: Final = (
    "Once a draft is published the agent is what it says, and a further save to the same draft "
    "would be a change nobody started from the agent as it now is. Changing it again is a new "
    "draft "
    "from the agent."
)

#: What a new agent is called before anybody names it.
NEW_AGENT_NAME: Final = "New agent"

#: The rung every action starts at, and the highest a draft may name.
STARTING_RUNG: Final = AutonomyTier.SHADOW


# ------------------------------------------------------------------------ the records
@dataclass(frozen=True)
class Act:
    """One act on one revision."""

    revision: int
    act: DraftAct
    actor_id: str
    at: datetime
    #: Whether the revision reached further than the agent did, when the act was taken.
    widened: bool = False
    #: For a new agent: seen by the author's department rather than the author alone.
    for_department: bool = False
    #: For a new agent: the channels its author ticked, which a second person's approval publishes
    #: with, as it publishes with `for_department` (M13.7.4). Empty answers nowhere.
    channels: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentDraft:
    """A draft of one agent: whose it is, which agent, its revisions and what was done to them."""

    draft: ManifestDraft
    agent_id: str
    kind: DraftKind
    #: For an edit, the configuration digest of the agent when the draft started. None for new.
    base_hash: str | None
    revisions: tuple[Revision, ...] = ()
    acts: tuple[Act, ...] = ()

    def __post_init__(self) -> None:
        if (self.kind is DraftKind.EDIT) != (self.base_hash is not None):
            msg = "an edit names the configuration it started from, and a new agent has none"
            raise BuilderError(msg)

    @property
    def draft_id(self) -> str:
        return self.draft.draft_id

    @property
    def owner_id(self) -> str:
        return self.draft.owner_id

    @property
    def latest(self) -> Revision | None:
        return self.revisions[-1] if self.revisions else None

    def acts_on(self, revision: int) -> frozenset[DraftAct]:
        return frozenset(one.act for one in self.acts if one.revision == revision)

    def act_named(self, revision: int, act: DraftAct) -> Act | None:
        return next((one for one in self.acts if (one.revision, one.act) == (revision, act)), None)


def state_of(draft: AgentDraft) -> DraftState:
    """Where a draft stands: the latest revision's furthest act, and a draft with none is a draft.

    Read off the latest revision only, so a save after a check, a request or a refusal is a draft
    again: what was checked or asked about is no longer what is on the screen.
    """
    latest = draft.latest
    if latest is None:
        return DraftState.DRAFT
    done = draft.acts_on(latest.number)
    if DraftAct.PUBLISHED in done:
        return DraftState.PUBLISHED
    if DraftAct.DECLINED in done:
        return DraftState.DECLINED
    if DraftAct.REQUESTED in done:
        return DraftState.WAITING
    if DraftAct.CHECKED in done:
        return DraftState.CHECKED
    return DraftState.DRAFT


def published(draft: AgentDraft) -> bool:
    """Whether any revision of this draft was published. See `A_PUBLISHED_DRAFT_IS_FINISHED`."""
    return any(one.act is DraftAct.PUBLISHED for one in draft.acts)


# ------------------------------------------------------------------------- the document
def for_agent(document: Mapping[str, Any], agent_id: str) -> dict[str, Any]:
    """The document with its template id set to the agent's own. See the module docstring.

    An identity that is absent or not an object is left alone, so the model reports it where it is
    rather than this reporting something else, which is `brain.builder.drafts`' rule for the two
    paths publishing decides.
    """
    stamped = dict(document)
    identity = stamped.get("identity")
    if isinstance(identity, Mapping):
        stamped["identity"] = {**identity, "template_id": agent_id}
    return stamped


def seed(
    manifest: TemplateManifest, agent_id: str, *, display_name: str | None = None
) -> dict[str, Any]:
    """A manifest as the first document of a draft for `agent_id`, in the manifest's own nesting."""
    document: dict[str, Any] = manifest.model_dump(mode="json")
    if display_name:
        document["identity"] = {**document["identity"], "display_name": display_name}
    return for_agent(document, agent_id)


def blank_seed(agent_id: str) -> dict[str, Any]:
    """The first document of a draft built from nothing: the blank template, named."""
    return seed(BLANK_MANIFEST, agent_id, display_name=NEW_AGENT_NAME)


def name_of(document: Mapping[str, Any]) -> str | None:
    """The name a document gives its agent, or None when it gives none."""
    identity = document.get("identity")
    if not isinstance(identity, Mapping):
        return None
    name = identity.get("display_name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def manifest_of(
    document: Mapping[str, Any], *, agent_id: str, version: int, publisher: str
) -> tuple[TemplateManifest | None, tuple[Problem, ...]]:
    """The manifest a document is for this agent, or every reason it is not one.

    `brain.builder.drafts.whole_manifest` decides, after the template id is set to the agent's.
    """
    return whole_manifest(for_agent(document, agent_id), version=version, publisher=publisher)


# ---------------------------------------------------------------- what it becomes here
def carrier(manifest: TemplateManifest, *, signed_by: str, at: datetime) -> SignedManifest:
    """The manifest signed with a key made for one question and dropped. See
    `A_QUESTION_ASKED_BEFORE_PUBLISHING_IS_SIGNED_WITH_A_KEY_NOBODY_KEEPS`."""
    return publish(manifest, key=secrets.token_hex(32), signed_by=signed_by, at=at)


def unanswered(manifest: TemplateManifest) -> tuple[str, ...]:
    """The required placeholders a draft declares. A draft stores no answers, so all of them."""
    return tuple(one.key for one in manifest.placeholders if one.required)


def _settled(
    signed: SignedManifest,
    instance: TemplateInstance,
    *,
    audience: AgentAudience,
    registry: ConnectorRegistry,
    tools: ToolRegistry,
    at: datetime,
) -> Installation:
    """`settle`, and the installation it is: what `complete` returns, less the verification."""
    settled = settle(
        signed,
        instance,
        audience=audience,
        unanswered=unanswered(signed.manifest),
        registry=registry,
        tools=tools,
        at=at,
    )
    return Installation(
        instance=instance,
        effective=settled.effective,
        record=settled.record,
        leash=settled.leash,
        readiness=settled.readiness,
        completeness=settled.completeness,
        placeholder_answers={},
        tools=settled.tools,
    )


def becomes(
    signed: SignedManifest,
    *,
    agent_id: str,
    created_by: str,
    audience: AgentAudience,
    registry: ConnectorRegistry,
    tools: ToolRegistry,
    at: datetime,
) -> Installation:
    """What this signed manifest becomes as `agent_id` on this install, or a refusal in words.

    `settle` rather than `complete`, because `complete` verifies the signature with a key the
    caller holds and a question asked with `carrier` holds none worth verifying; `settle` checks the
    pin and runs every validator an agent record has. A persona left blank is refused by
    `AgentRecord` and reported as a `BuilderError` with the sentence a person reads.
    """
    identity = signed.manifest.identity
    instance = TemplateInstance(
        instance_id=agent_id,
        template_id=identity.template_id,
        template_version=identity.version,
        content_digest=signed.content_digest,
        created_by=created_by,
    )
    try:
        return _settled(signed, instance, audience=audience, registry=registry, tools=tools, at=at)
    except (ValueError, TemplateError) as refused:
        raise BuilderError(DOES_NOT_MAKE_AN_AGENT_YET) from refused


def republished(
    signed: SignedManifest,
    *,
    key: str,
    agent_id: str,
    created_by: str,
    audience: AgentAudience,
    registry: ConnectorRegistry,
    tools: ToolRegistry,
    at: datetime,
) -> Installation:
    """The installation an edit publishes: the signed version installed, which verifies it with
    this install's key, then settled, with the builder the agent already names."""
    instance = install(signed, key=key, instance_id=agent_id, created_by=created_by, at=at)
    return _settled(signed, instance, audience=audience, registry=registry, tools=tools, at=at)


#: What a draft that cannot become an agent is told. The model's own reason is logged, not read.
DOES_NOT_MAKE_AN_AGENT_YET: Final = (
    "This draft does not make an agent yet: it needs a name and instructions, and every tool it "
    "cannot work without must be one it is allowed."
)


def raised_rungs(manifest: TemplateManifest) -> tuple[str, ...]:
    """The targets a draft names above Shadow, sorted. See
    `A_RUNG_IS_RAISED_WITH_EVIDENCE_AND_NEVER_BY_A_DRAFT`."""
    return tuple(
        sorted({one.target for one in manifest.guardrails.leash if one.rung > STARTING_RUNG})
    )


def reaching_nothing(record: AgentRecord) -> AgentRecord:
    """The same agent with a ceiling that reaches nothing. See `A_NEW_AGENT_WIDENS_FROM_NOTHING`."""
    return record.model_copy(update={"authority": AgentAuthority(scope=record.authority.scope)})


def widenings(before: AgentRecord | None, after: AgentRecord, *, now: datetime) -> tuple[str, ...]:
    """Everything `after` may reach that `before` could not, named, or nothing.

    `brain.agents.creation.widened`, which compares a copy with its source, so a publish and a
    duplicate are judged by one comparison. The scope a new agent is compared at is its own, so a
    new agent narrowing rows reads as widening its capabilities and never its rows.
    """
    return widened(reaching_nothing(after) if before is None else before, after, now=now)


def second_people_needed(widened_parts: Sequence[str]) -> int:
    """How many people besides the author must agree: none, or one for a widening. See
    `THE_AUTHOR_IS_THE_FIRST_OF_THE_PEOPLE_A_PUBLISH_NEEDS`."""
    return approvers_needed(widened_parts) - APPROVERS_FOR_AN_ORDINARY_PUBLISH


#: What an author asking to approve their own widening is told.
NOT_THE_AUTHOR: Final = (
    "You wrote this change, so somebody else has to approve it: nobody publishes a wider agent "
    "on their own word."
)

#: What an approver whose reach does not cover the agent is told. It names nothing they lack.
NOT_WITHIN_YOUR_REACH: Final = (
    "You cannot approve this: your own access does not cover everything this agent may reach."
)


def approval_refusal(
    *,
    author_id: str,
    approver_id: str,
    ceiling: EntitlementSet,
    approver_reach: EntitlementSet,
    now: datetime,
) -> str | None:
    """Why this person may not be the second person on this publish, or None when they may.

    Two refusals, and neither names a capability: a list of what an approver is short of is the
    boundary of their own reach handed to them one publish at a time, which
    `brain.console.scoped_authority.ceiling_within_reach` refuses to return for the same reason.
    """
    if approver_id == author_id:
        return NOT_THE_AUTHOR
    if not may_approve_publication(ceiling, approver_reach, now):
        return NOT_WITHIN_YOUR_REACH
    return None


def ceiling_of(record: AgentRecord) -> EntitlementSet:
    """The ceiling a publication puts into the world, as the approval rule reads it."""
    return entitlement_ceiling(record)


def next_version(on_file: Iterable[int]) -> int:
    """The version a publish of the agent's own template would be: one past the newest on file."""
    versions = list(on_file)
    return max(versions) + 1 if versions else FIRST_VERSION


# -------------------------------------------------------------------- the plain words
def _lower_first(words: str) -> str:
    return words[:1].lower() + words[1:]


def where(path: str) -> str:
    """Where a problem is, in the words of the Write step: its section's heading, then its field's.

    The words are `brain.builder.form`'s, the ones the form itself is labelled with, so a problem
    never names a heading that is not on the screen. Until 2026-09-29 this module kept a second
    table, and it sent people to headings called "Permissions" and "Identity", neither of which
    the form had. A holder split across sections names every section it is in, and a path nobody
    filed reads as itself.
    """
    parts = path.split(".")
    for length in (2, 1):
        filed = ".".join(parts[:length])
        section = SECTION_OF_PATH.get(filed)
        if section is None:
            continue
        heading = SECTION_TITLES[section]
        said = FIELD_WORDS.get(filed)
        if said is None or said.title.casefold() == heading.casefold():
            return heading
        return f"{heading}, {_lower_first(said.title)}"
    holding = [
        SECTION_TITLES[one]
        for one in Section
        if any(path_ == parts[0] or path_.startswith(f"{parts[0]}.") for path_ in paths_in(one))
    ]
    return " or ".join(holding) if holding else path


def plain(problem: Problem) -> str:
    """One problem in words a person acts on: where it is, then pydantic's own sentence."""
    return f"{where(problem.path)}: {problem.message}"
