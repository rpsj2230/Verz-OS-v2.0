"""The capabilities tab: what an agent is assembled from, computed at whoever is looking.

`brain.console.workspace` says what an agent's workspace is. This is the one tab where every
row is a disclosure in its own right, because a capabilities tab is a list of things that
exist: connectors installed here, skills in the library, knowledge that matched, channels this
deployment can reach. A tab like that is the natural place to publish an inventory of the
install to somebody who was carefully given four rows on every other screen.

**Every row here is computed at `E_run(caller, agent) = E(caller) ∩ agent_ceiling`, and
nothing here computes it.** `run_reach` calls `brain.console.reads.audience`, which is the
console's one call into `EntitlementSet.intersect`, with the agent's ceiling as the second
set: `brain.agents.model.entitlement_ceiling` produces exactly that type and says in its own
docstring that it confers nothing. `brain.console.workspace.intersections_in` is run over this
module's own source by its test suite and reports any such call, so the absence is checked
rather than promised. Two people opening one agent's capabilities tab see different rows, and
neither sees anything the ceiling excludes.

**An overflow count is legitimate and is one character away from being a hidden count.**
M39.2.1.1 asks for a row of connector icons and a count of the rest, which is the correct and
useful thing when the rest are on the other side of the row's edge. It is the disclosure by
subtraction the moment any of them is on the other side of the reader's reach. So the overflow
is computed from the rows the caller may see, `ConnectorStrip` refuses an overflow beside a row
that is not full, and there is no path by which a connector this person cannot see reaches
either number. See `AN_OVERFLOW_COUNTS_WHAT_IS_OFF_THE_ROW_AND_NEVER_WHAT_IS_OUT_OF_REACH`.

**"Requested, not attached" is a state about the agent and must not become a state about a
grant.** An agent's manifest naming a connector is a fact about the agent, which the reader is
already looking at. That the department has not granted it is a fact about a grant, and a row
reading "requested" for a source the reader has never heard of has told them the source exists
here. A requested connector is therefore shown only where an attached one would have been, and
`ConnectorRow` has no field saying why a connector is not attached. See
`A_REQUEST_FOR_SOMETHING_YOU_CANNOT_SEE_ANNOUNCES_THAT_IT_EXISTS`.

**A field list is a disclosure that reads as documentation.** M39.2.1.3 asks which fields a
connector projects for this agent, and the manifest answers for the projection rather than for
the reader: a field name in it is the name of a column in somebody's source system. So the
list is filtered through `brain.core.field_policy`, at the run's reach, and an unclassified
field is withheld rather than shown, which is the reading `FieldPolicy.rule_for` requires of
everybody who calls it.

**Health is inherited and never recomputed.** `brain.connectors.contract.ConnectorHealth` is
the answer the connector page gives, and a second opinion here would be a degraded source
shown as healthy on one page and degraded on the other, with nothing saying which was right. A
connector nobody has probed carries no health at all rather than `OK`: an unprobed source
rendered green is the failure that makes a health indicator worse than none. See
`AN_UNPROBED_CONNECTOR_IS_NOT_A_HEALTHY_ONE`.

**Attaching a skill is a reference to a review, not to a repository.** `attach_skill` takes an
`ImportedSkill` and there is no parameter a URL, a repository or a commit could arrive
through, so the only way to attach is through something that has been reviewed;
`brain.tools.skills.pin_skill` then refuses one that has not been approved by a named person,
and the attachment's version is the approved digest rather than the author's version string.
A version string is a number somebody types, and the commonest way a reviewed procedure
changes is an edit without one.

**A knowledge scope is a predicate and the count beside it is a count of what was shown.** A
document list would make the scope a thing that goes stale the moment somebody uploads, and it
would make an agent's reach a list somebody maintains by hand. The preview is over the items
the caller can already see, which is `brain.knowledge.quality.
A_COUNT_OF_WHAT_WAS_SHOWN_IS_NOT_A_COUNT_OF_WHAT_WAS_HIDDEN` applied one surface along: how
many of my own items this predicate matches attributes nothing, and how many exist that I
cannot see is the number that must not be computable.

**Rejected: offering a channel at the agent's ceiling rather than at the caller's reach.** It
is the tempting reading, because it gives everybody the same row and the same row is easier to
support. It is also wrong twice: it shows a narrow caller a channel their own run would be
refused on by `brain.channels.adapter.assert_can_send`, and it tells them how sensitive the
agent's widest reach is, which is a fact about the ceiling rather than about them. The offer is
computed from what this run could actually carry.

Scope: domain logic. Nothing here opens a connection, probes anything or reads a clock. Rows,
health and policies arrive as arguments, exactly as they do in `brain.console.reads`.

**Nothing here is a screen.** There is no capabilities tab in this repository and no route
behind one, so this module is the reading half of M39.2 and claims eight of its nineteen
leaves. The other eleven are the acting half and they are `brain.console.agent_tabs`, which
landed on 2026-09-08 and completed the group. The icons M39.2.1.1 asks for are still a
rendering asset chosen from the source name, and what is claimed for that leaf here is the
overflow rule beside them.

**This paragraph said the other eleven were unclaimed, and that stopped being true the day
`agent_tabs` landed.** It also said group installation had no `brain.channels.adapter.Feature`
member, on the argument that the enum is closed and adding one with nothing behind it would be
a capability an adapter declares and nothing honours. That objection was answered rather than
ignored: `Feature.GROUP_INSTALL` exists and `agent_tabs.install_to_group` refuses an install
on a surface that does not declare it, so the member has a code path behind it. No adapter
declares it yet, and a test asserts that so the day one does prompts a read. Corrected here
because a docstring that describes a gap somebody has since filled is how ten documents came
to agree with each other and none of them with the code.

Task ids: M39.2.1.1, M39.2.1.3, M39.2.1.4, M39.2.1.5, M39.2.2.2, M39.2.3.1, M39.2.3.3, M39.2.4.2
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.agents.model import AgentRecord, entitlement_ceiling
from brain.channels.adapter import ChannelCapabilities
from brain.connectors.contract import ConnectorHealth, HealthState
from brain.connectors.manifest import ProjectedEntity
from brain.console.reads import audience
from brain.console.workspace import Attachment, Part
from brain.core.entitlement import EntitlementSet
from brain.core.field_policy import CLASSIFICATION_ORDER, Classification, FieldPolicy
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.knowledge.item import KnowledgeItem, retrievable
from brain.ops.jobs import hidden_count_fields
from brain.tools.skills import ImportedSkill, pin_skill

# ------------------------------------------------------------------ written-down reasons
#: Why an overflow count is safe here and is one edit away from not being.
AN_OVERFLOW_COUNTS_WHAT_IS_OFF_THE_ROW_AND_NEVER_WHAT_IS_OUT_OF_REACH: Final = (
    "A row of icons and a count of the rest is the correct thing when the rest are on the "
    "other side of the row's edge, and it is the disclosure by subtraction the moment one of "
    "them is on the other side of the reader's reach. The two are indistinguishable in the "
    "rendering and completely different in what they say, so the count is derived from the "
    "rows this caller may see and `ConnectorStrip` refuses an overflow beside a row with "
    "space left on it: a count of things that are not merely off the end of the row."
)

#: Why a connector nobody granted is shown only where a granted one would have been.
A_REQUEST_FOR_SOMETHING_YOU_CANNOT_SEE_ANNOUNCES_THAT_IT_EXISTS: Final = (
    "A manifest naming a connector is a fact about the agent, which the reader is already "
    "looking at. That the department has not granted it is a fact about a grant. A row "
    "reading requested for a source this person has never heard of has told them the source "
    "is installed here and that somebody decided they may not reach it, which is two facts "
    "they did not have. Requested is shown only where attached would have been, and there is "
    "no field on the row saying why a connector is not attached."
)

#: Why the field list is filtered rather than printed.
A_FIELD_NAME_IS_THE_NAME_OF_A_COLUMN_IN_SOMEBODY_ELSES_SYSTEM: Final = (
    "A projection declares what is kept locally, and it answers for the projection rather "
    "than for whoever is reading the page, so printing it puts the shape of a source system "
    "in front of anybody who can open an agent. The list is filtered through the field "
    "policy at the run's reach, and a field nothing classifies is withheld rather than "
    "shown, which is the reading `FieldPolicy.rule_for` requires of every caller: None is "
    "not the absence of a restriction, it is the absence of a decision."
)

#: Why a connector with no probe carries no health.
AN_UNPROBED_CONNECTOR_IS_NOT_A_HEALTHY_ONE: Final = (
    "`ConnectorHealth` is a fact with a time on it, and the failure that makes a health "
    "indicator worse than none is a green light after the prober itself has stopped. A "
    "connector nobody has probed therefore carries no state here rather than OK, and the "
    "state that is carried is the connector page's own, because a second opinion is a source "
    "shown degraded on one page and healthy on the other with nothing saying which is right."
)

#: Why the attach path cannot be handed a repository.
AN_ATTACH_PATH_THAT_TAKES_A_URL_IS_A_ROUTE_ROUND_THE_REVIEW: Final = (
    "Attaching only from the approved library is a rule until somebody adds a convenience "
    "that takes a repository and imports on the way past, at which point the review is "
    "whatever the person attaching decided. `attach_skill` takes an `ImportedSkill` and has "
    "no parameter a URL, an owner, a repository, a commit or a branch could arrive through, "
    "so the import and the review happen before anybody reaches this. The version pinned is "
    "the approved digest and not the author's version string, because a version is a number "
    "somebody types and an edit without one is the commonest way a reviewed procedure moves."
)

#: Why a knowledge scope is a predicate and can never be a list.
A_DOCUMENT_LIST_IS_A_SCOPE_THAT_IS_WRONG_BY_TOMORROW: Final = (
    "A list of item ids is correct on the afternoon it is written and stale after the next "
    "upload, and keeping it correct is somebody's standing job. Worse, it moves the decision "
    "about what an agent may read from a predicate a reviewer can read into a list nobody "
    "reviews. `KnowledgeScope` carries a `Scope` and has nowhere to put a list, and "
    "`capabilities_gaps` reports a field that would let one back in."
)

#: Why a predicate may not be written against the item's own text.
A_PREDICATE_OVER_CONTENT_READS_THE_DOCUMENT_TO_DECIDE_WHO_MAY_READ_IT: Final = (
    "A clause matching on an item's content would be a permission decided by the text of the "
    "thing being permitted, which is both circular and unreviewable: nobody can say what an "
    "agent reaches without reading every document. The predicate is matched against a row "
    "describing the item, and `PREDICATE_FIELDS` is what that row carries."
)

#: Why a channel is offered at the caller's reach rather than at the agent's ceiling.
A_CHANNEL_OFFERED_AT_THE_CEILING_DESCRIBES_THE_CEILING: Final = (
    "Offering every reader the same channel row is easier to support and wrong twice. It "
    "offers a narrow caller a channel their own run would be refused on by "
    "`brain.channels.adapter.assert_can_send`, which reads as the feature being broken; and "
    "it tells that caller how sensitive the agent's widest reach is, which is a fact about "
    "the ceiling rather than about them. The offer is what this run could actually carry, "
    "computed by asking the channel's own `may_carry` rather than by comparing ranks here."
)


class CapabilitiesError(Exception):
    """A capabilities row was described in a shape that would show somebody the wrong thing.

    Outside `brain.core.errors` for the reason `brain.console.workspace.WorkspaceError` is:
    nobody asking a question ever sees one. It is a mistake by whoever assembled the tab.
    """


# ------------------------------------------------------------------------------- the reach
def run_reach(caller: EntitlementSet, record: AgentRecord) -> EntitlementSet:
    """`E_run(caller, agent)`, by the one intersection the console already calls.

    `brain.console.reads.audience` is that call, and `entitlement_ceiling` is the ceiling in
    the type it takes. Neither is reimplemented here and there is no arithmetic in this
    function, which is the point: `brain.console.workspace.intersections_in` reads this
    module's source and would report one.

    The ceiling confers nothing. `intersect` keeps the caller's own principal id, so a
    workspace read through an agent is still the reader's read, and an agent whose ceiling
    admits everything shows nothing to somebody who holds nothing.
    """
    return audience(caller, entitlement_ceiling(record))


# ------------------------------------------------------------- connectors on the agent (M39.2.1)
class Presence(enum.StrEnum):
    """Whether a connector this agent names is bound to it. Two members and no third.

    There is deliberately nothing meaning "refused", "pending approval" or "not granted".
    Each of those is a fact about a grant rather than about the agent, and the row is read by
    somebody who may not know the grant exists. See
    `A_REQUEST_FOR_SOMETHING_YOU_CANNOT_SEE_ANNOUNCES_THAT_IT_EXISTS`.
    """

    ATTACHED = "attached"
    REQUESTED = "requested"


#: How many connector icons a row holds before the rest become a count.
#:
#: A number rather than a rendering decision, because the count is the disclosure and the
#: count is computed here. Five is what fits beside a heading; what matters is that the same
#: number decides both halves, so an overflow can never describe anything but the tail of
#: this reader's own list.
ICONS_ON_THE_ROW: Final = 5

#: Empty defaults, as read-only mappings rather than literals: a mutable default is shared
#: between every call that omits the argument, and this one would be shared between agents.
_NO_PROJECTIONS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({})
_NO_HEALTH: Final[Mapping[str, ConnectorHealth]] = MappingProxyType({})


@dataclass(frozen=True)
class ConnectorRow:
    """One connector on this agent, as this reader may see it (M39.2.1.1, M39.2.1.4).

    `source` is the connector's own name and the icon is chosen from it, so there is no
    second registry of icons to disagree with the registry of connectors.

    There is no field saying why a connector is not attached, and no field counting the
    fields it does not project. Both would be a fact about a grant on a row read by somebody
    who may not know the grant exists.
    """

    source: str
    presence: Presence
    #: The fields this run would actually see, in the manifest's own order (M39.2.1.3).
    projects: tuple[str, ...] = ()
    #: The connector page's answer, inherited whole. `None` when nobody has probed it.
    health: HealthState | None = None
    #: When that probe ran. `None` with `health`, never on its own.
    checked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            msg = "a connector row naming nothing cannot be rendered or followed"
            raise CapabilitiesError(msg)
        if (self.health is None) != (self.checked_at is None):
            msg = (
                f"{self.source} carries half a health reading (state={self.health!r}, "
                f"checked={self.checked_at!r}). {AN_UNPROBED_CONNECTOR_IS_NOT_A_HEALTHY_ONE}"
            )
            raise CapabilitiesError(msg)


@dataclass(frozen=True)
class ConnectorStrip:
    """The connector row and its overflow, both derived from what this reader may see.

    See `AN_OVERFLOW_COUNTS_WHAT_IS_OFF_THE_ROW_AND_NEVER_WHAT_IS_OUT_OF_REACH`. The
    constructor refuses the shape that would make the count mean something else, so an
    overflow assembled by hand somewhere else in the console is refused here rather than
    rendered.
    """

    shown: tuple[ConnectorRow, ...]
    overflow: int = 0

    def __post_init__(self) -> None:
        if self.overflow < 0:
            msg = "an overflow below zero is not a count of anything"
            raise CapabilitiesError(msg)
        if self.overflow and len(self.shown) < ICONS_ON_THE_ROW:
            msg = (
                f"{self.overflow} connectors are counted as overflow beside a row of "
                f"{len(self.shown)}, which has room for {ICONS_ON_THE_ROW}. "
                f"{AN_OVERFLOW_COUNTS_WHAT_IS_OFF_THE_ROW_AND_NEVER_WHAT_IS_OUT_OF_REACH}"
            )
            raise CapabilitiesError(msg)


def projected_for(
    entity: ProjectedEntity,
    reach: EntitlementSet,
    policy: FieldPolicy,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """Which fields of this projection this run would actually return (M39.2.1.3).

    In the manifest's declared order, because that is the author's order and re-sorting it
    would discard the grouping somebody wrote.

    A field the policy does not classify is withheld. That is not this module being cautious,
    it is what `FieldPolicy.rule_for` requires of everybody who calls it: `None` is the
    absence of a decision rather than the absence of a restriction, and
    `brain.core.redaction.compute_mask` reads it the same way.

    Returns the names and no count of the rest. See
    `A_FIELD_NAME_IS_THE_NAME_OF_A_COLUMN_IN_SOMEBODY_ELSES_SYSTEM`.
    """
    kept: list[str] = []
    for field in entity.fields:
        rule = policy.rule_for(entity.entity, field.name)
        if rule is None:
            continue
        if reach.scope_for(rule.required_capability, now) is not None:
            kept.append(field.name)
    return tuple(kept)


def connector_rows(
    *,
    declared: Sequence[str],
    attached: Iterable[str],
    visible: Iterable[str],
    projections: Mapping[str, tuple[str, ...]] = _NO_PROJECTIONS,
    health: Mapping[str, ConnectorHealth] = _NO_HEALTH,
) -> tuple[ConnectorRow, ...]:
    """The connectors on this agent this reader may see, in the manifest's order.

    `declared` is what the agent's manifest asks for and `attached` is what the install has
    bound; anything declared and unbound is `REQUESTED` (M39.2.1.4). `visible` is the set
    this caller could see if it were attached, and a connector outside it produces no row in
    either state, which is the whole of
    `A_REQUEST_FOR_SOMETHING_YOU_CANNOT_SEE_ANNOUNCES_THAT_IT_EXISTS`.

    Health is looked up and copied, never derived (M39.2.1.5). A connector with no entry gets
    no health rather than a healthy one; see `AN_UNPROBED_CONNECTOR_IS_NOT_A_HEALTHY_ONE`.
    """
    bound = frozenset(attached)
    reachable = frozenset(visible)
    rows: list[ConnectorRow] = []
    for source in declared:
        if source not in reachable:
            continue
        probe = health.get(source)
        rows.append(
            ConnectorRow(
                source=source,
                presence=Presence.ATTACHED if source in bound else Presence.REQUESTED,
                projects=projections.get(source, ()),
                health=None if probe is None else probe.state,
                checked_at=None if probe is None else probe.checked_at,
            )
        )
    return tuple(rows)


def connector_strip(rows: Sequence[ConnectorRow]) -> ConnectorStrip:
    """The row and the count beside it, both computed from the same visible rows (M39.2.1.1).

    One function producing both halves, rather than a caller slicing the list and counting
    what it sliced. The second arrangement is where the count comes from somewhere else: the
    row gets the visible connectors and the count gets the total, and the two are assembled
    in a renderer that nobody reads as a permission decision.
    """
    return ConnectorStrip(
        shown=tuple(rows[:ICONS_ON_THE_ROW]),
        overflow=max(0, len(rows) - ICONS_ON_THE_ROW),
    )


# ----------------------------------------------------------------- skills on the agent (M39.2.2)
#: Parameter names that would let a repository reach the attach path. See
#: `AN_ATTACH_PATH_THAT_TAKES_A_URL_IS_A_ROUTE_ROUND_THE_REVIEW`.
NAMES_THAT_WOULD_BE_A_REPOSITORY: Final[frozenset[str]] = frozenset(
    {"url", "repo", "repository", "location", "commit", "branch", "tag", "source", "archive"}
)


def attach_skill(agent_id: str, imported: ImportedSkill) -> Attachment:
    """Attach one approved skill to one agent, or refuse it (M39.2.2.2).

    Two refusals, and only one of them is in this function. The approval is
    `brain.tools.skills.pin_skill`'s, which refuses a skill that is not approved by a named
    person and unchanged since; restating it here would be a second opinion about a review.
    The other is the signature: there is no parameter a repository could arrive through, so
    an import cannot happen on the way past. See
    `AN_ATTACH_PATH_THAT_TAKES_A_URL_IS_A_ROUTE_ROUND_THE_REVIEW`.

    The version on the attachment is the approved digest rather than
    `imported.skill.version`, so the pin is over the bytes a reviewer read.
    """
    pin = pin_skill(agent_id, imported)
    return Attachment(part=Part.SKILLS, ref=pin.skill_name, version=pin.digest)


# -------------------------------------------------------------- knowledge on the agent (M39.2.3)
#: What an agent's knowledge predicate may be written against.
#:
#: The item's identity, its steward and where it sits, and deliberately not its text. See
#: `A_PREDICATE_OVER_CONTENT_READS_THE_DOCUMENT_TO_DECIDE_WHO_MAY_READ_IT`.
PREDICATE_FIELDS: Final[tuple[str, ...]] = (
    "item_id",
    "owner_id",
    "department",
    "visibility",
    "state",
)

#: Field names that would turn a scope back into a list. See
#: `A_DOCUMENT_LIST_IS_A_SCOPE_THAT_IS_WRONG_BY_TOMORROW`.
NAMES_THAT_WOULD_BE_A_DOCUMENT_LIST: Final[frozenset[str]] = frozenset(
    {"items", "item_ids", "documents", "document_ids", "include", "allow", "members"}
)

#: Predicate fields that would decide who may read a document from the document. See
#: `A_PREDICATE_OVER_CONTENT_READS_THE_DOCUMENT_TO_DECIDE_WHO_MAY_READ_IT`.
NAMES_THAT_WOULD_READ_THE_DOCUMENT: Final[frozenset[str]] = frozenset(
    {"content", "text", "title", "body", "extract"}
)


@dataclass(frozen=True)
class KnowledgeScope:
    """What an agent may draw on, as a predicate (M39.2.3.1).

    A `Scope` and nothing else. There is no field for a list of items, which is
    `A_DOCUMENT_LIST_IS_A_SCOPE_THAT_IS_WRONG_BY_TOMORROW` expressed as a shape, and
    `capabilities_gaps` reports one if a later edit adds it.

    An unrestricted predicate is allowed and is not a company-wide grant. It means this agent
    narrows nothing of its own, so a run reaches whatever its caller reaches and no more,
    which is the same argument `brain.agents.model.AgentAuthority` makes about its scope.
    """

    agent_id: str
    predicate: Scope

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            msg = "a knowledge scope belonging to no agent narrows nothing for nobody"
            raise CapabilitiesError(msg)
        outside = sorted(
            clause.field
            for clause in self.predicate.clauses
            if clause.field not in PREDICATE_FIELDS
        )
        if outside:
            msg = (
                f"the predicate matches on {outside}, and the fields an item's row carries "
                f"are {list(PREDICATE_FIELDS)}. "
                f"{A_PREDICATE_OVER_CONTENT_READS_THE_DOCUMENT_TO_DECIDE_WHO_MAY_READ_IT}"
            )
            raise CapabilitiesError(msg)


def item_row(item: KnowledgeItem) -> dict[str, str]:
    """One knowledge item, as the row a predicate is tested against.

    Built here rather than by the caller so that every predicate is matched against the same
    fields; a caller assembling its own row could add one and widen a predicate by supplying
    something for it to match on. A `Clause` refuses a row whose field is absent, so a
    predicate naming anything outside this row matches nothing rather than everything.
    """
    return {
        "item_id": item.item_id,
        "owner_id": item.owner_id,
        "department": item.visibility.department,
        "visibility": str(item.visibility.level),
        "state": str(item.state),
    }


def matching(scope: KnowledgeScope, items: Sequence[KnowledgeItem]) -> tuple[KnowledgeItem, ...]:
    """The items this agent's predicate reaches, out of the ones handed in.

    `items` is what the caller may already see, which is the whole of the disclosure
    argument: this narrows a set somebody was entitled to and never widens one.

    Superseded and archived items are dropped by `brain.knowledge.item.retrievable` rather
    than by a state check written here, so a fifth state added to that module is handled by
    the module that owns it. An agent's scope must not reach a replaced item, because an
    answer drawn from one is an answer that was true last quarter.
    """
    return tuple(one for one in retrievable(items) if scope.predicate.matches(item_row(one)))


def preview_count(scope: KnowledgeScope, items: Sequence[KnowledgeItem]) -> int:
    """How many of this reader's own items the predicate currently matches (M39.2.3.3).

    A count of what was shown, which attributes nothing: a small number means the predicate
    is narrow, or the corpus is small, or most of it is out of this reader's reach, and those
    are indistinguishable by design. `brain.knowledge.quality` states the same rule for
    retrieval in the same words.

    The number that must not exist is how many items the predicate matches that this reader
    cannot see, and there is no function here that could produce it: this one is given the
    reader's own items and nothing else.
    """
    return len(matching(scope, items))


# --------------------------------------------------------------- channels on the agent (M39.2.4)
def highest_classification(
    reach: EntitlementSet, policy: FieldPolicy, now: datetime | None = None
) -> Classification:
    """The most sensitive field this run could return.

    Over the policy's own rules rather than over a list of classifications written here, so a
    field reclassified in the policy moves this without anybody remembering to. A reach that
    holds nothing returns `PUBLIC`, which is the honest floor: a run that can read nothing
    can disclose nothing, and the alternative of returning the most sensitive class by
    default would refuse every channel to somebody with no grants at all.
    """
    highest = CLASSIFICATION_ORDER[0]
    for rule in policy.rules:
        if reach.scope_for(rule.required_capability, now) is None:
            continue
        if rule.classification.rank > highest.rank:
            highest = rule.classification
    return highest


def offered_channels(
    reach: EntitlementSet,
    capabilities: Sequence[ChannelCapabilities],
    policy: FieldPolicy,
    now: datetime | None = None,
) -> tuple[Channel, ...]:
    """The channels this agent may be enabled on for this caller (M39.2.4.2).

    The intersection asked for is between what the channel can carry and what the run can
    reach, and it is asked of the channel's own `may_carry` rather than by comparing ranks
    here: a second comparison is a second answer, and the permissive one wins silently.

    Computed at the caller's reach rather than at the agent's ceiling. See
    `A_CHANNEL_OFFERED_AT_THE_CEILING_DESCRIBES_THE_CEILING`.

    Returns the channels and no count of the rest, in the order they were declared.
    """
    highest = highest_classification(reach, policy, now)
    return tuple(one.channel for one in capabilities if one.may_carry(highest))


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of this tab is handed. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`.
CAPABILITIES_SURFACE: Final[tuple[type, ...]] = (ConnectorRow, ConnectorStrip, KnowledgeScope)


def capabilities_gaps(
    *,
    surface: Sequence[type] = CAPABILITIES_SURFACE,
    scope_type: type = KnowledgeScope,
    attach: Callable[..., object] = attach_skill,
    predicate_fields: Sequence[str] = PREDICATE_FIELDS,
) -> tuple[str, ...]:
    """Everything about this tab that would show somebody more than they hold.

    Takes its inputs for the reason `brain.ops.starter.starter_gaps` records: a diagnostic
    that can only read the healthy module has nothing to report on today's data, so every one
    of its refusals survives a mutation. Calling it with no arguments is the deployment check
    and calling it with a constructed type is the test.
    """
    gaps: list[str] = []

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    gaps.extend(
        f"{scope_type.__name__}.{name} would turn the predicate back into a list. "
        f"{A_DOCUMENT_LIST_IS_A_SCOPE_THAT_IS_WRONG_BY_TOMORROW}"
        for name in getattr(scope_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_A_DOCUMENT_LIST
    )

    taken = set(inspect.signature(attach).parameters)
    gaps.extend(
        f"{getattr(attach, '__name__', 'the attach path')} takes {name}. "
        f"{AN_ATTACH_PATH_THAT_TAKES_A_URL_IS_A_ROUTE_ROUND_THE_REVIEW}"
        for name in sorted(taken & NAMES_THAT_WOULD_BE_A_REPOSITORY)
    )

    reading = sorted(set(predicate_fields) & NAMES_THAT_WOULD_READ_THE_DOCUMENT)
    if reading:
        gaps.append(
            f"a knowledge predicate may be written against {reading}, which is the item's "
            f"own words. {A_PREDICATE_OVER_CONTENT_READS_THE_DOCUMENT_TO_DECIDE_WHO_MAY_READ_IT}"
        )

    return tuple(gaps)
