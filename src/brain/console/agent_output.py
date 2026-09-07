"""What an agent produced: recorded once, kept to its shortest input, and re-checked on the
way back out.

`brain.console.workspace` gives an agent's workspace an Artifacts tab and says nothing about
what is behind it. This is that, and it is a different kind of surface from the three beside
it. A composition is a fact about the agent. A capability is a fact about the agent. **An
artifact is a thing somebody's data went into**, so a list of artifacts computed at the wrong
reach shows one person what another person's run produced, and the file itself is the copy
whose permissions stopped travelling with it.

**Redaction happens at production time or it never happens.** A document, a deck or an export
is bytes in a bucket the moment it exists, and there is no field policy on a bucket: nothing
downstream can withhold a column from a spreadsheet that already has the column in it. So the
mask is computed while the artifact is being built, at `E_run(caller, agent)` rather than at
the caller's own reach, and `producible_fields` is the one place that decision is made. See
`AN_ARTIFACT_IS_A_COPY_WHOSE_PERMISSIONS_STOPPED_TRAVELLING_WITH_IT`.

**Nothing here computes a reach.** `brain.console.workspace_capabilities.run_reach` is the
console's route into `EntitlementSet.intersect`, through `brain.console.reads.audience`, and a
third implementation of the platform's central rule is a third place for it to be subtly
wrong. `brain.console.workspace.intersections_in` is run over this module's own source by its
test suite, so the absence is a check rather than a habit.

**A download link is not a grant, and the failure is that it reads exactly like one.** A
signed URL is a bearer token in a text field: it can be forwarded, pasted into a ticket, or
found in a browser history a year later, and every one of those is a person reading an
artifact at the reach of whoever produced it. So `may_download` is asked of the requester as
they are now, it never reads `Artifact.entitlement_hash`, and there is no parameter a link, a
token or a signature could arrive through. The hash on the record says what produced the
artifact; it is provenance and it is not a permission. See
`A_LINK_THAT_CARRIES_ITS_OWN_PERMISSION_IS_A_GRANT_ANYBODY_CAN_FORWARD`.

**An artifact's window is its shortest input's, and the leaf's own wording is the trap.**
M39.5.1.3 asks for the retention class of the most sensitive input, which is right about which
input matters and silent about what happens when a less sensitive one is shorter-lived: a
restricted business record has no clock at all and a payload expires in thirty days, so taking
the most sensitive input alone would keep the artifact after the run it was built from is
gone. `retention_class_for` takes the most sensitive input's class and then narrows to any
input with a shorter window, which is `brain.ops.retention.A_DERIVED_COPY_HAS_NO_LIFETIME_OF_
ITS_OWN` applied to a copy made of several sources.

**An artifact past its horizon is absent, not expired.** A row reading "expired" is a row
saying something used to be here, and beside a filter on a caller the reader may not see it is
the subtraction disclosure with a date on it. `visible_artifacts` drops them before it filters
anything, so an artifact that has aged out and an artifact that never existed produce the same
list. That ordering is the whole of it: filtering first and expiring afterwards would leave a
count that moved when a horizon passed.

**The count is a front-page figure and follows a screen's grant.** Storage and artifact count
accumulate from everybody who ran the agent, so they move when somebody else works.
`brain.console.workspace.Basis` is that rule already written down against the budget screen,
and `basis_over` is the same rule with the screen as a parameter, because the figure here sits
behind the Artifacts screen rather than behind the budget one. A separate enum would have been
a second answer to a question that already has one.

Rejected: generalising `brain.console.workspace.basis_for` in place. It is the same rule and
the parameter belongs there, but that module is being edited tonight by somebody else and a
shared edit is how `brain.tables` lost seven tests. `basis_over` is the general form and the
two are pinned against each other by test rather than by intention.

Rejected: a delete path. `supersede` and `archive` are the two ways an artifact stops being
current, both of them keep the row, and `artifact_gaps` refuses a state or a callable that
would remove one. An answer given last quarter is only explainable while the thing it was
drawn from still exists, which is `brain.knowledge.item.KnowledgeState`'s argument about a
superseded document and `brain.memory.review.delete`'s about a mark rather than a row.

Scope: domain logic. Nothing here opens a connection, writes to a bucket or reads a clock;
`now` is a parameter for the reason `brain.ops.limits` gives about policy that owns a client.

**Nothing here is a screen.** There is no Artifacts tab in this repository and no route behind
one, exactly as `brain.console.screens` says of its own registry. What is built is the domain
layer such a screen would read, and the leaves claimed are the ones where the disclosure rule
is the whole content.

**M39.5.1.3 is decided here and enforced nowhere, so it is not claimed.**
`retention_class_for` decides an artifact's window per artifact and is the harder half of the
leaf; the bucket it sits in has one lifecycle rule and that rule is "kept until somebody
deletes it", because `brain.ops.storage`'s `assets` bucket is unbounded on purpose. Only a
per-object sweep can apply the difference, `brain.ops.retention.StoreSweeper` is the protocol
for one, and that module says plainly that nothing implements it. So an artifact carries the
class of its most sensitive input as a label and nothing acts on it, and the leaf says
"stored with the retention class", which is a claim about how long the object lives.

`retention_enforcement_gaps` reports it, separately from `artifact_gaps` so that the
deployment check is not red on the day it lands, and a test asserts the finding is there.
The id is not repeated on the lines below, because those are parsed for ids and a sentence
declining a leaf reads to the parser exactly like claiming it.

Task ids: M39.5.1.1, M39.5.1.2, M39.5.1.4, M39.5.1.5
Task ids: M39.5.2.1, M39.5.2.2, M39.5.2.3, M39.5.2.4, M39.5.2.5
"""

from __future__ import annotations

import enum
import inspect
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Final

from brain.agents.model import AgentRecord
from brain.console.reads import ConsoleRead, permitted
from brain.console.screens import screen
from brain.console.workspace import MOVING_PINS, NAMES_THAT_WOULD_BE_AN_INLINE_COPY, Basis
from brain.console.workspace_capabilities import run_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.field_policy import Classification, FieldPolicy
from brain.core.redaction import RESERVED_KEYS, compute_mask
from brain.ops.jobs import hidden_count_fields
from brain.ops.retention import (
    DataClass,
    Store,
    expires_at,
    facts_for,
    horizon_for,
    is_expired,
)
from brain.ops.storage import bucket

# ------------------------------------------------------------------ written-down reasons
#: Why the mask is computed while the artifact is being built.
AN_ARTIFACT_IS_A_COPY_WHOSE_PERMISSIONS_STOPPED_TRAVELLING_WITH_IT: Final = (
    "A record in the database carries a field policy and a redactor walks it on every read. "
    "A deck in a bucket carries neither: it is bytes, and a column that reached the "
    "spreadsheet is in the spreadsheet for as long as the file exists, whoever opens it "
    "next. So the withholding happens at production, at the run's own reach rather than at "
    "the caller's, and the artifact that results can never exceed the person who asked for "
    "it. There is no later point at which this could be done, which is why there is no "
    "function here that redacts an artifact after the fact."
)

#: Why a download is re-checked and the link is never the authority.
A_LINK_THAT_CARRIES_ITS_OWN_PERMISSION_IS_A_GRANT_ANYBODY_CAN_FORWARD: Final = (
    "A signed URL is a bearer token wearing a text field. It survives being pasted into a "
    "ticket, forwarded to somebody outside the department, and read out of a browser history "
    "a year after the person who made it left. Every one of those is somebody reading an "
    "artifact at the reach of whoever produced it. may_download is therefore asked of the "
    "requester's entitlements as they are now, it has no parameter a link or a token could "
    "arrive through, and it does not read the entitlement hash on the record: that hash says "
    "what produced the artifact and is provenance, never permission."
)

#: Why the most sensitive input decides the class and the shortest one decides the window.
AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM: Final = (
    "The most sensitive input is the right input to classify by and it is not always the "
    "shortest-lived one. A restricted business record is kept while the record exists and a "
    "payload is gone in thirty days, so an artifact classified by sensitivity alone outlives "
    "the run it was drawn from and becomes the oldest copy of that content in the estate "
    "with nothing pointing at it. The class is the most sensitive input's, then narrowed to "
    "any input with a shorter window, which is brain.ops.retention's rule about a derived "
    "copy applied to a copy made of several sources."
)

#: Why an artifact past its horizon is not listed at all.
AN_EXPIRED_ROW_IS_A_STATEMENT_THAT_SOMETHING_USED_TO_BE_HERE: Final = (
    "A row reading expired, or greyed out, or shown with a strike through it, tells the "
    "reader that this agent produced something they can no longer have. Beside a filter by "
    "caller it tells them who produced it. So an artifact past its horizon is dropped before "
    "any filter runs, and an artifact that has aged out is indistinguishable from one that "
    "was never produced. The ordering is the mechanism: expiring after filtering would leave "
    "a count that moved on the day a horizon passed, and nothing on the screen would say why."
)

#: Why provenance is filtered to the reader rather than shown as the run recorded it.
PROVENANCE_IS_THE_PRODUCERS_REACH_WRITTEN_DOWN: Final = (
    "What fed an artifact is a list of the sources and knowledge items the producing run "
    "could reach, which is a description of that person's access printed on a panel read by "
    "somebody else. A source named there is a source the reader learns exists here, and a "
    "knowledge item named there is a document they learn somebody holds. So the panel is "
    "intersected with what this reader can already see, and it carries no remainder: an "
    "artifact drawn from six sources of which the reader may see two shows two and says "
    "nothing about four."
)

#: Why nothing here removes an artifact.
SUPERSEDING_KEEPS_THE_ANSWER_EXPLAINABLE_AND_DELETING_DOES_NOT: Final = (
    "An artifact is the evidence for something somebody was told. Deleting the version that "
    "was sent leaves a decision on file whose basis is gone, and the person who has to "
    "explain it a quarter later has the answer and not the working. Supersede points at the "
    "replacement and archive points at nothing, which is the distinction "
    "brain.knowledge.item draws between a document that was replaced and one that was "
    "withdrawn: an asker who finds nothing must not be told a successor exists."
)


class ArtifactError(Exception):
    """An artifact was recorded or rendered in a shape that would show somebody the wrong thing.

    Outside `brain.core.errors` for the reason `brain.console.workspace.WorkspaceError` is:
    those five outcomes describe an answer given to a person asking a question, and this is a
    refusal to record or to assemble. Nobody asking a question ever sees one.
    """


# --------------------------------------------------------------- the artifact store (M39.5.1)
class ArtifactKind(enum.StrEnum):
    """The five things M39.5.1.1 says are recorded as artifacts. Closed, and the closure is
    the mechanism.

    A produced thing whose kind cannot be named here is a produced thing nothing records, and
    it goes into a bucket with no run behind it, no caller attributed to it and no retention
    class decided for it. `record` takes this enum, so the way a sixth kind arrives is a diff
    somebody reviews rather than a string somebody passes.
    """

    DOCUMENT = "document"
    DECK = "deck"
    REPORT = "report"
    EXPORT = "export"
    IMAGE = "image"


class ArtifactState(enum.StrEnum):
    """Where an artifact is in its life. Three, and there is deliberately no fourth meaning
    deleted.

    See `SUPERSEDING_KEEPS_THE_ANSWER_EXPLAINABLE_AND_DELETING_DOES_NOT`. `artifact_gaps`
    reports a member whose name reads as a removal, because the member is how the rule dies:
    somebody adds `DELETED` to make a screen tidier and the row it hides is the one an
    explanation needed.
    """

    #: The artifact as produced, with nothing replacing it.
    CURRENT = "current"
    #: A newer artifact replaced it. `superseded_by` names which.
    SUPERSEDED = "superseded"
    #: Withdrawn, with nothing replacing it. Distinct from superseded for the reason
    #: `brain.knowledge.item.KnowledgeState` gives: a reader who finds nothing must not be
    #: told a successor exists.
    ARCHIVED = "archived"


#: The store an artifact comes to rest in, named from `brain.ops.retention.Store` rather than
#: written out, so a subject access request and this surface agree about where to look.
ARTIFACT_STORE: Final[Store] = Store.ATTACHMENT

#: The one thing an entitlement hash may look like, imported in spirit from
#: `brain.audit.ledger.ENT_HASH`: thirty-two lowercase hex characters, which is what
#: `EntitlementSet.ent_hash` returns. Restated as a compiled pattern here rather than imported
#: so that this module does not reach into the audit package for a regular expression; the
#: test pins the two against each other, which is the check that matters.
_ENT_HASH_RE: Final = re.compile(r"^[0-9a-f]{32}$")

#: The screen whose grant decides whether the front page may show everybody's figures.
#:
#: A screen key rather than a capability written out here, exactly as
#: `brain.console.workspace.SPEND_OF_OTHERS_SCREEN` is, so that the figure cannot drift from
#: the screen: `basis_over` asks `permitted` about that screen's own read, which is both the
#: tool's capability and the console plane, exactly as opening the screen would be.
ARTIFACTS_SCREEN: Final = "artifacts"

#: What a reader needs to see somebody else's artifacts. The artifacts screen's own
#: capability, read off the registry rather than spelled again here: a second spelling is a
#: grant an administrator reviewing the screen would never see.
ARTIFACT_CAPABILITY: Final[Capability] = screen(ARTIFACTS_SCREEN).read.requires


@dataclass(frozen=True)
class ArtifactInput:
    """One thing that fed an artifact, at production time.

    Not part of the read surface: this is what the run knows about its own sources while it is
    building, and it carries a label because the run has to be able to say which input was
    which. What a *reader* is shown is `Provenance`, which is filtered.
    """

    label: str
    #: Which retention class the input itself is governed by.
    data_class: DataClass
    #: How sensitive it is, on `brain.core.field_policy`'s own scale.
    classification: Classification

    def __post_init__(self) -> None:
        if not self.label.strip():
            msg = "an input with no label cannot be named in a provenance panel or a sweep"
            raise ArtifactError(msg)


@dataclass(frozen=True)
class Provenance:
    """What fed one artifact, as this reader may see it (M39.5.2.3).

    Two tuples and no third field. There is no count of the sources that were filtered out
    and nowhere to put one; see `PROVENANCE_IS_THE_PRODUCERS_REACH_WRITTEN_DOWN`.
    """

    #: Connector names, in the order the run recorded them.
    sources: tuple[str, ...] = ()
    #: Knowledge item ids, in the order the run recorded them.
    knowledge_items: tuple[str, ...] = ()


#: An artifact nobody recorded a provenance for. A shared frozen value rather than a default
#: constructed per call, for the reason `brain.console.workspace_capabilities._NO_PROJECTIONS`
#: is a `MappingProxyType`: a default built at each call site is a default that can differ.
NO_PROVENANCE: Final[Provenance] = Provenance()


@dataclass(frozen=True)
class Artifact:
    """One thing an agent produced (M39.5.1.1, M39.5.1.2).

    **There is no field a document could arrive in.** No `body`, no `content`, no `payload`.
    An artifact record carrying its own bytes is a second copy of the file under the console's
    retention rather than the bucket's, which is the failure `brain.ops.queue.Job` refuses at
    the other end and `brain.ops.jobs.DeadLetter` refuses at this one. `artifact_gaps` reports
    one if a later edit adds it, using `brain.console.workspace`'s own list of the names it
    would arrive under.

    `entitlement_hash` is what the producing run's reach hashed to. It is carried so that two
    people disagreeing about what an artifact contains can be told whether they were the same
    reach, and it is never consulted by `may_download`; see
    `A_LINK_THAT_CARRIES_ITS_OWN_PERMISSION_IS_A_GRANT_ANYBODY_CAN_FORWARD`.
    """

    artifact_id: str
    agent_id: str
    kind: ArtifactKind
    #: The run that produced it, so a trace and an artifact can be put beside each other.
    run_id: str
    #: The exact agent version, spelled as `brain.console.workspace.Attachment.version` is.
    agent_version: str
    #: The person whose question produced it. Never an agent; see M39.6.2.1's argument.
    caller_id: str
    entitlement_hash: str
    at: datetime
    #: The window this artifact is kept for, decided by `retention_class_for`.
    data_class: DataClass
    state: ArtifactState = ArtifactState.CURRENT
    #: What is in the bucket, in bytes. A fact about this artifact, not a count of others.
    bytes_stored: int = 0
    provenance: Provenance = NO_PROVENANCE
    #: The artifact that replaced this one. Set exactly when the state is `SUPERSEDED`.
    superseded_by: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("artifact_id", self.artifact_id),
            ("agent_id", self.agent_id),
            ("run_id", self.run_id),
            ("caller_id", self.caller_id),
        ):
            if not value.strip():
                msg = (
                    f"an artifact with no {name} cannot be attributed, re-checked or swept, "
                    "and it is a file in a bucket with nothing pointing at it"
                )
                raise ArtifactError(msg)
        if not self.agent_version.strip() or self.agent_version.strip().lower() in MOVING_PINS:
            msg = (
                f"artifact {self.artifact_id!r} was produced by agent version "
                f"{self.agent_version!r}, which resolves to whatever is there on the day "
                "somebody asks, so the record says nothing about what actually built it"
            )
            raise ArtifactError(msg)
        if not _ENT_HASH_RE.fullmatch(self.entitlement_hash):
            msg = (
                f"artifact {self.artifact_id!r} carries {self.entitlement_hash!r} as an "
                "entitlement hash, which is not one; the record would name a reach nobody "
                "can compare against"
            )
            raise ArtifactError(msg)
        if self.at.tzinfo is None:
            msg = (
                f"artifact {self.artifact_id!r} is dated with no timezone, so its horizon "
                "falls due at whatever offset the host happens to sit from UTC"
            )
            raise ArtifactError(msg)
        if self.bytes_stored < 0:
            msg = f"artifact {self.artifact_id!r} occupies a negative amount of the bucket"
            raise ArtifactError(msg)
        replaced = self.state is ArtifactState.SUPERSEDED
        if replaced != bool(self.superseded_by.strip()):
            msg = (
                f"artifact {self.artifact_id!r} is {self.state.value} and names "
                f"{self.superseded_by!r} as its replacement; one of those is not true, and a "
                "reader following the panel lands on whichever the renderer trusted"
            )
            raise ArtifactError(msg)

    def expiry(self) -> datetime | None:
        """When this artifact stops being kept, or `None` when age is not what ends it.

        Delegated to `brain.ops.retention.expires_at` rather than computed from a window
        copied here, so an artifact and the sweep that removes it agree about the date. Named
        `expiry` rather than `expires_at` so that the module-level function it delegates to is
        not shadowed by a method of the same name, which is legal and reads as a recursion.
        """
        return expires_at(self.data_class, self.at)


def retention_class_for(inputs: Sequence[ArtifactInput]) -> DataClass:
    """The class an artifact built from these inputs is kept under (M39.5.1.3).

    Two steps, and the second is the one the leaf's wording leaves out. The class is the most
    sensitive input's, which is what M39.5.1.3 asks for; it is then narrowed to any input with
    a shorter window, because an artifact that outlives the run it was drawn from is the
    oldest copy of that content in the estate with nothing pointing at it. See
    `AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM`.

    Ties on sensitivity are broken by the input's label, so two runs over the same inputs in a
    different order produce the same class rather than whichever the caller iterated first.

    Refuses an empty input list. An artifact built from nothing is either a mistake or a thing
    that needs no permission at all, and defaulting it here would pick the longest window for
    whichever of the two it was.
    """
    if not inputs:
        msg = (
            "an artifact with no declared inputs has no class to be kept under, and the "
            "default any lookup would give it is the longest window in the system"
        )
        raise ArtifactError(msg)
    ranked = sorted(inputs, key=lambda one: (-one.classification.rank, one.label))
    chosen = ranked[0].data_class
    for one in inputs:
        if _is_shorter(one.data_class, chosen):
            chosen = one.data_class
    return chosen


def _is_shorter(candidate: DataClass, than: DataClass) -> bool:
    """Whether `candidate`'s window ends sooner than `than`'s.

    A class with no clock never ends sooner, whatever its lifetime member says: "kept while
    the record exists" and "never expires" both mean age is not what removes it, and treating
    either as infinite is the reading that keeps the artifact no longer than any input.
    """
    mine, theirs = horizon_for(candidate).days, horizon_for(than).days
    if mine is None:
        return False
    return theirs is None or mine < theirs


def record(
    *,
    artifact_id: str,
    agent_id: str,
    kind: ArtifactKind,
    run_id: str,
    agent_version: str,
    caller_id: str,
    reach: EntitlementSet,
    at: datetime,
    inputs: Sequence[ArtifactInput],
    bytes_stored: int = 0,
    provenance: Provenance = NO_PROVENANCE,
) -> Artifact:
    """Record one produced thing as an artifact (M39.5.1.1, M39.5.1.2, M39.5.1.3).

    The one way an artifact comes to exist, which is what makes M39.5.1.1's "every produced
    document, deck, report, export and image" checkable rather than aspirational: a producer
    that wanted to skip a field would have to construct an `Artifact` itself, and every field
    the record needs is required by this signature.

    `reach` is the producing run's reach, `E_run(caller, agent)`, and the hash of it is what
    goes on the record. It is taken as a value rather than computed here because nothing in
    this module intersects anything; `brain.console.workspace_capabilities.run_reach` is where
    that happens.

    The class is `retention_class_for`'s answer rather than a parameter, so a producer cannot
    choose a longer window for its own output. That is
    `brain.ops.retention.THE_CLASS_DECIDES_AND_A_ROW_CANNOT_ARGUE` at the point of production.
    """
    return Artifact(
        artifact_id=artifact_id,
        agent_id=agent_id,
        kind=kind,
        run_id=run_id,
        agent_version=agent_version,
        caller_id=caller_id,
        entitlement_hash=reach.ent_hash(),
        at=at,
        data_class=retention_class_for(inputs),
        bytes_stored=bytes_stored,
        provenance=provenance,
    )


def producible_fields(
    entity: str,
    present_fields: Sequence[str],
    *,
    caller: EntitlementSet,
    agent: AgentRecord,
    policy: FieldPolicy,
    row: Mapping[str, Any],
    now: datetime | None = None,
) -> tuple[str, ...]:
    """Which fields of one record may go into an artifact (M39.5.1.4).

    At `E_run(caller, agent)` and never at the caller's own reach, which is the half that
    makes the leaf's "never exceeds its caller" true in both directions: the ceiling can only
    narrow, so what reaches the file is a subset of what the person asking could have read on
    the record screen.

    `brain.core.redaction.compute_mask` decides, because it is the only thing that may: a
    second answer to what a person may read is the one thing `tests/invariants/
    test_single_implementation.py` names by hand. What is added here is the ordering, which is
    the record's own field order rather than the mask's set, so an artifact's columns are
    where its author put them.

    The entity tag is dropped. `RESERVED_KEYS` are what makes a record walkable by the
    redactor; they are not columns and a deck with an `@entity` heading is a rendering bug.
    """
    reach = run_reach(caller, agent)
    mask = compute_mask(
        entity,
        present_fields,
        entitlement=reach,
        policy=policy,
        row=row,
        now=now,
    )
    return tuple(
        name for name in present_fields if name in mask.allowed and name not in RESERVED_KEYS
    )


# ------------------------------------------------------------ who may see one (M39.5.2.1)
def _scope_row(one: Artifact) -> dict[str, str]:
    """The fields an artifact grant's scope may be written against.

    Four, all of them closed vocabularies or references, and none of them a business
    attribute. `brain.ops.jobs._scope_row` makes the same choice in the same words and for the
    same reason: a grant scoped on something the row does not carry admits nothing, which
    fails closed, and a wider row would let a grant be written against a field this surface
    cannot evaluate.
    """
    return {
        "agent_id": one.agent_id,
        "kind": one.kind.value,
        "caller_id": one.caller_id,
        "state": one.state.value,
    }


def may_see(one: Artifact, reader: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader is entitled to know this artifact exists. Two ways in, no third.

    **It is their own.** A person may see what their own question produced. Refusing that
    would mean the only person who knows what the artifact was for is the one person who
    cannot find it again.

    **A grant covers artifacts, in a scope that matches the row.** `EntitlementSet` and
    `Scope` decide it, which is the same machinery every other narrowing in this system uses,
    and `brain.ops.jobs.may_see` is the same two branches in the same order over a dead
    letter. A second implementation of who may read what is a second place for it to be wrong,
    and the permissive copy is the one that ships.
    """
    if one.caller_id == reader.principal_id:
        return True
    scope = reader.scope_for(ARTIFACT_CAPABILITY, now)
    if scope is None:
        return False
    return scope.matches(_scope_row(one))


def may_download(one: Artifact, requester: EntitlementSet, now: datetime) -> bool:
    """Whether this requester may fetch the bytes, asked now rather than when it was made
    (M39.5.1.5).

    Two conditions. The artifact still exists, which is `brain.ops.retention.is_expired` and
    not a date compared here; and the requester is entitled to it as they are at this moment,
    which is `may_see`. There is no third condition and in particular there is no link: see
    `A_LINK_THAT_CARRIES_ITS_OWN_PERMISSION_IS_A_GRANT_ANYBODY_CAN_FORWARD`. `artifact_gaps`
    reads this signature for a parameter one could arrive through.

    **`Artifact.entitlement_hash` is not consulted and must not be.** It is what the producing
    run's reach hashed to, so treating a match as permission would let anybody holding the
    same grants as the producer read the file, and treating it as the check at all would mean
    the artifact carried its own authorisation. The requester's own set is the only input.
    """
    if is_expired(one.data_class, one.at, now):
        return False
    return may_see(one, requester, now)


def visible_artifacts(
    entries: Sequence[Artifact],
    reader: EntitlementSet,
    now: datetime,
    *,
    agent_id: str,
    kinds: Iterable[ArtifactKind] = (),
    caller_id: str = "",
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[Artifact, ...]:
    """What this reader may see of what an agent produced, newest first (M39.5.2.1, M39.5.2.2).

    **The filters are arguments here rather than a second function**, and that is the whole
    disclosure argument rather than a convenience. A `filter_by` taking a list of artifacts
    would be a function somebody eventually calls before the visibility check, and a filter
    applied first is a filter whose result reveals what it removed: asking for one caller's
    exports and getting nothing is the same answer as asking for a caller who produced none,
    only if the visibility check has already happened.

    Three things are dropped before any filter: artifacts of another agent, artifacts past
    their horizon, and artifacts this reader holds nothing for. See
    `AN_EXPIRED_ROW_IS_A_STATEMENT_THAT_SOMETHING_USED_TO_BE_HERE`.

    `agent_id` is required and has no value meaning every agent, which is M39.5.2.1's "what
    this agent produced" made structural: a listing that could be asked for the whole estate
    is the global pile with an optional filter on it, and the filter is the thing that gets
    omitted.

    Newest first, ties broken by id, so two readings of an unchanged store are the same list.
    Returns one value; there is nowhere in it for a count of what was left out.
    """
    wanted = frozenset(kinds)
    kept = [
        one
        for one in entries
        if one.agent_id == agent_id
        and not is_expired(one.data_class, one.at, now)
        and may_see(one, reader, now)
        and (not wanted or one.kind in wanted)
        and (not caller_id or one.caller_id == caller_id)
        and (since is None or one.at >= since)
        and (until is None or one.at <= until)
    ]
    return tuple(sorted(kept, key=lambda one: (one.at, one.artifact_id), reverse=True))


def provenance_for(
    one: Artifact,
    *,
    visible_sources: Iterable[str],
    visible_items: Iterable[str],
) -> Provenance:
    """What fed this artifact, narrowed to what this reader can already see (M39.5.2.3).

    An intersection with two sets the caller has computed elsewhere, which is deliberate: what
    a reader may see of the connector list is `brain.console.workspace_capabilities.
    connector_rows`' answer and what they may see of the knowledge corpus is
    `brain.knowledge.item.retrievable`'s, and a panel that asked either question again would
    be a second answer to it.

    Order is the run's own, because that is the order the artifact was built in and a reader
    tracing an unexpected figure follows it. Nothing is returned about what was removed; see
    `PROVENANCE_IS_THE_PRODUCERS_REACH_WRITTEN_DOWN`.
    """
    sources = frozenset(visible_sources)
    items = frozenset(visible_items)
    return Provenance(
        sources=tuple(name for name in one.provenance.sources if name in sources),
        knowledge_items=tuple(name for name in one.provenance.knowledge_items if name in items),
    )


# --------------------------------------------------- supersede and archive (M39.5.2.4)
def supersede(one: Artifact, *, by: str) -> Artifact:
    """Mark an artifact replaced by a newer one (M39.5.2.4).

    Returns a new record, because `Artifact` is frozen and both sides of the change have to be
    holdable: the row that was sent to somebody is the evidence for what they were told.

    Refuses anything that is not current. An artifact superseded twice has two successors and
    nothing says which the reader should follow, and an archived artifact superseded is a
    withdrawal being replaced, which is a history nobody can read.
    """
    if one.state is not ArtifactState.CURRENT:
        msg = (
            f"artifact {one.artifact_id!r} is already {one.state.value}, so superseding it "
            "would leave two answers to which artifact replaced it"
        )
        raise ArtifactError(msg)
    if not by.strip():
        msg = (
            f"artifact {one.artifact_id!r} would be superseded by nothing, which is a "
            "withdrawal wearing the word superseded and sends a reader looking for a "
            "replacement that does not exist"
        )
        raise ArtifactError(msg)
    if by.strip() == one.artifact_id:
        msg = f"artifact {one.artifact_id!r} cannot supersede itself"
        raise ArtifactError(msg)
    return Artifact(
        artifact_id=one.artifact_id,
        agent_id=one.agent_id,
        kind=one.kind,
        run_id=one.run_id,
        agent_version=one.agent_version,
        caller_id=one.caller_id,
        entitlement_hash=one.entitlement_hash,
        at=one.at,
        data_class=one.data_class,
        state=ArtifactState.SUPERSEDED,
        bytes_stored=one.bytes_stored,
        provenance=one.provenance,
        superseded_by=by.strip(),
    )


def archive(one: Artifact) -> Artifact:
    """Withdraw an artifact, keeping the row (M39.5.2.4).

    Distinct from superseding, and the distinction is the reader's: an archived artifact has
    no successor and a panel must not imply one. Refuses an artifact that is already archived,
    because a no-op that reads as an action leaves a history saying somebody withdrew a thing
    twice.
    """
    if one.state is ArtifactState.ARCHIVED:
        msg = (
            f"artifact {one.artifact_id!r} is already archived; recording it again puts a "
            "second withdrawal in a history that only had one"
        )
        raise ArtifactError(msg)
    return Artifact(
        artifact_id=one.artifact_id,
        agent_id=one.agent_id,
        kind=one.kind,
        run_id=one.run_id,
        agent_version=one.agent_version,
        caller_id=one.caller_id,
        entitlement_hash=one.entitlement_hash,
        at=one.at,
        data_class=one.data_class,
        state=ArtifactState.ARCHIVED,
        bytes_stored=one.bytes_stored,
        provenance=one.provenance,
    )


# ------------------------------------------------- count and storage (M39.5.2.5)
def basis_over(screen_key: str, entitlement: EntitlementSet, now: Any = None) -> Basis:
    """Whose figures this caller may be shown, decided by one screen's own grant.

    `brain.console.workspace.basis_for` is this rule against the budget screen, written before
    a second surface needed it. This is the same rule with the screen as a parameter, and the
    parameter is the only difference: `permitted` is asked about that screen's registered
    read, so the figure carries both the tool's capability and the console plane, exactly as
    opening the screen would.

    No capability is invented for a front page. A new capability is a second answer to a
    question the screen registry already answers, and the reviewer approving one would never
    see the other.
    """
    return Basis.EVERYONE if permitted(screen(screen_key).read, entitlement, now) else Basis.OWN


@dataclass(frozen=True)
class StorageSummary:
    """What the Artifacts tab shows above the list (M39.5.2.5).

    Every figure is computed from the rows the reader may see and from nothing else, so the
    summary of an agent holding other people's output is identical to the summary of an agent
    that never produced any.

    `basis` is carried rather than left implicit, which is `brain.console.workspace.Headline`'s
    argument: a figure whose meaning is unstated is read as the total, so a reader shown their
    own storage with no label reads it as the agent's.

    There is no field here for a total, a hidden count, or an amount that was excluded;
    `hidden_count_fields` is the check that keeps it that way.
    """

    agent_id: str
    basis: Basis
    #: How many artifacts this reader may see. A count of what was shown.
    count: int
    #: What they occupy, in bytes.
    bytes_stored: int
    #: The oldest visible artifact, or `None`. What makes an unswept bucket visible.
    oldest_at: datetime | None
    #: The soonest horizon among them, or `None` when none of them has a clock. This is the
    #: "against the retention policy" half: a figure with no date beside it reads as an amount
    #: that will keep growing.
    expires_soonest_at: datetime | None


def storage_summary(
    agent_id: str,
    entries: Sequence[Artifact],
    reader: EntitlementSet,
    *,
    basis: Basis,
    now: datetime,
) -> StorageSummary:
    """Artifact count and storage for one agent, against the policy that removes them
    (M39.5.2.5).

    Filtering happens first and the arithmetic happens on what is left, which is the ordering
    that makes the rule structural rather than remembered: there is no point in this function
    at which a count of everything exists to be accidentally returned. That is
    `brain.ops.jobs.dead_letter_summary`'s construction, and it is the one worth copying.

    On the narrower basis the figures are the reader's own rows out of the ones they may see,
    which is not the same as the wider basis reduced: a reader holding an artifact grant over
    a department sees that department's storage on the wider basis and their own on the
    narrower, and the difference between the two is not derivable from either.
    """
    visible = visible_artifacts(entries, reader, now, agent_id=agent_id)
    counted = tuple(
        one for one in visible if basis is Basis.EVERYONE or one.caller_id == reader.principal_id
    )
    horizons = [due for due in (one.expiry() for one in counted) if due is not None]
    return StorageSummary(
        agent_id=agent_id,
        basis=basis,
        count=len(counted),
        bytes_stored=sum(one.bytes_stored for one in counted),
        oldest_at=min((one.at for one in counted), default=None),
        expires_soonest_at=min(horizons, default=None),
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of this surface is handed. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`: a type added to the surface and not to this tuple is a
#: type the checks below never see.
ARTIFACT_SURFACE: Final[tuple[type, ...]] = (Artifact, Provenance, StorageSummary)

#: Parameter names by which a link, a token or a signed URL could reach the download check.
#: Names rather than a rule about values, because the failure arrives as a parameter somebody
#: adds to save a lookup, and it arrives with one of these names on it.
NAMES_THAT_WOULD_BE_A_BEARER_TOKEN: Final[frozenset[str]] = frozenset(
    {"link", "url", "token", "signature", "signed_url", "presigned", "key", "grant"}
)

#: Words in a state's name that would mean the row is gone. See
#: `SUPERSEDING_KEEPS_THE_ANSWER_EXPLAINABLE_AND_DELETING_DOES_NOT`.
NAMES_THAT_WOULD_BE_A_REMOVAL: Final[frozenset[str]] = frozenset(
    {"deleted", "removed", "purged", "destroyed", "erased", "expired"}
)


def artifact_gaps(
    *,
    surface: Sequence[type] = ARTIFACT_SURFACE,
    artifact_type: type = Artifact,
    states: Iterable[ArtifactState] = tuple(ArtifactState),
    download: Callable[..., object] = may_download,
    reads: Sequence[ConsoleRead] = (),
) -> tuple[str, ...]:
    """Everything about this surface that would show somebody more than they hold, plus the
    one thing about the bucket that this module cannot fix.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason: a diagnostic that can only be run against the healthy tree has nothing to report
    on today's data, so switching off any of its refusals changes nothing observable and every
    one of them survives. Calling it with no arguments is the deployment check and calling it
    with a constructed set is the test. `brain.ops.starter.starter_gaps` and
    `brain.console.workspace.workspace_gaps` both make the same argument about their own
    parameters.
    """
    gaps: list[str] = []

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    gaps.extend(
        f"{artifact_type.__name__}.{name} would put the produced bytes on the record, under "
        "the console's retention rather than the bucket's, where no field policy reaches them"
        for name in getattr(artifact_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_AN_INLINE_COPY
    )

    for state in states:
        if state.value in NAMES_THAT_WOULD_BE_A_REMOVAL:
            gaps.append(
                f"{state.value} is a state meaning the artifact is gone. "
                f"{SUPERSEDING_KEEPS_THE_ANSWER_EXPLAINABLE_AND_DELETING_DOES_NOT}"
            )

    taken = set(inspect.signature(download).parameters)
    gaps.extend(
        f"{getattr(download, '__name__', 'the download check')} takes {name}. "
        f"{A_LINK_THAT_CARRIES_ITS_OWN_PERMISSION_IS_A_GRANT_ANYBODY_CAN_FORWARD}"
        for name in sorted(taken & NAMES_THAT_WOULD_BE_A_BEARER_TOKEN)
    )

    for read in reads:
        if read.requires != ARTIFACT_CAPABILITY:
            gaps.append(
                f"{read.screen} shows artifacts and requires {read.requires.value}, which is "
                f"not {ARTIFACT_CAPABILITY.value}; a second grant over the same rows is a "
                "grant an administrator reviewing the artifacts screen would never see"
            )

    names = {one.name for one in fields(Artifact)}
    for forbidden in ("expires_at_override", "keep_until", "retain_until", "retention_days"):
        if forbidden in names:
            gaps.append(
                f"Artifact carries {forbidden}, which is a per-row window arriving through "
                "the produced thing rather than through the policy that governs its class"
            )

    return tuple(gaps)


def retention_enforcement_gaps(store: Store = ARTIFACT_STORE) -> tuple[str, ...]:
    """Where an artifact's own window is not actually applied to the bytes.

    **This one reports today and is meant to**, which is why it is not part of `artifact_gaps`
    above: that is a deployment check and a check that is red on the day it lands is a check
    somebody switches off, which `brain.ops.sweeps.sweep_house_style` records at length about
    its own scope.

    The finding is real. A retention class is decided per artifact by `retention_class_for`,
    and a bucket has exactly one lifecycle rule, which `brain.ops.retention.store_gaps` says
    is the reason one bucket may be claimed by exactly one store. So an artifact whose most
    sensitive input is a payload is classified at thirty days and sits in a bucket that keeps
    everything until somebody deletes it. Only a per-object sweep can apply the difference,
    `brain.ops.retention.StoreSweeper` is the protocol for one, and that module states plainly
    that nothing implements it. Naming this here is what stops M39.5.1.3 reading as done.
    """
    return tuple(
        f"artifacts are stored in bucket {name!r}, which has no lifecycle rule, so an "
        "artifact's own retention class is enforced only by a per-object sweep; "
        "brain.ops.retention.StoreSweeper is that protocol and nothing implements it"
        for name in sorted(facts_for(store).buckets)
        if bucket(name).retention_days is None
    )
