"""The skills catalogue over HTTP, and the two sentences it has to say about itself.

`brain.console.screens` registers a Skills screen, `brain.console.agent_tabs` decides what a
reader may be shown about one skill on one agent, and `brain.console.govern_estate.skill_queue`
decides what a reviewer may be shown of the queue. None of them is reachable from a browser:
`brain.ops.console_screens` counts that as its own
`A_READ_NOBODY_CAN_OPEN_IS_A_SCREEN_NOBODY_HAS`. This module is the read those decisions sit
behind, and the honest half of it is what it refuses to answer.

**Nothing in this installation stores an imported skill, and every gap below follows from
that one fact.** `brain.tools.skills.ImportedSkill` is where a skill's state, its reviewer, its
source and its tool list live, and there is no table for it: `src/brain/tables` has no skill
row, no migration creates one, and `grep ImportedSkill src` finds a console module, a personal
library and a migration helper, all of them taking one as an argument. So the only durable
record of a skill in a running install is the reference an agent's template carries, which is
`brain.agents.template.SkillRef`: a name and the digest the agent is pinned to. See
`THE_ONLY_RECORD_OF_A_SKILL_HERE_IS_THE_PIN_AN_AGENT_CARRIES`.

Three consequences, and each of them is a field on the response saying so rather than a column
left quietly blank.

**No row here carries a review state, and that is stricter than it looks.**
`brain.console.agent_tabs.review_state` derives one from `ImportedSkill.is_executable`, and the
whole reason that function exists is that an approved state is not an executable skill: a row
edited after approval still reads APPROVED while its digest no longer matches. With nothing
storing the approval there is no digest to compare against, so a state word on one of these
rows could only be a guess, and the flattering guess is the one a reader would act on. See
`AN_APPROVAL_NOBODY_STORED_CANNOT_BE_READ_OFF_A_PIN`.

**No row here says what a skill is trusted to reach, and the sentence the screen says instead
is the true one.** A skill's reach is `brain.tools.skills.skill_reach`: the tools it names,
intersected with what `brain.gate.catalogue.project` admits for this caller. The tools it names
are in the `SKILL.md`, which nothing stores, so the input to that function is missing. What is
not missing is the guarantee: a skill declares no reach of its own, `Skill` has no field one
could travel in, and the frontmatter parser refuses the keys by name. So the screen states the
guarantee and lists no capabilities, rather than listing an empty set that would read as "this
skill reaches nothing". See `A_SKILL_DECLARES_NO_REACH_AND_AN_EMPTY_LIST_WOULD_READ_AS_ONE`.

**There is no control that assigns a skill to an agent, and this module offers no write at
all.** `brain.console.workspace_capabilities.attach_skill` takes an `ImportedSkill` and refuses
anything else, and it refuses it through `brain.tools.skills.pin_skill`, which pins only a
skill approved by a named person and unchanged since. Nothing here can produce such a value,
so a write would have to take a name and a digest from the browser and pin them, which is an
approval granted by whoever typed it. That is the same failure
`AN_ATTACH_PATH_THAT_TAKES_A_URL_IS_A_ROUTE_ROUND_THE_REVIEW` names, arriving through a form
instead of a URL. The route says so on the response and the page says so in words. See
`AN_ASSIGNMENT_BUILT_ON_A_DIGEST_SOMEBODY_TYPED_IS_AN_APPROVAL_THEY_GRANTED_THEMSELVES`.

**The screen this answers is SCREEN 6 of `docs/screens.html`, and three of its columns have no
source in this install.** That document is the design of record: Skills sits in the Govern
section, its library lists Skill, Source, Ver, Scope, Used by, Reviewed and State, and its
right-hand pane is an import review beside an upstream-drift card. Source, Reviewed and State
are all read off an `ImportedSkill`; Ver is the version string on the `SKILL.md`; Scope is a
department nothing records against a skill. What this route can answer is the skill's name, the
bytes each agent is pinned to, which agents use it, and the queue. The columns that have no
source are absent rather than rendered empty, because a Reviewed column that is blank on every
row is a screen saying nobody has ever reviewed anything, which is a stronger claim than the
truth. See `A_COLUMN_THAT_CAN_ONLY_BE_BLANK_MAKES_A_CLAIM_THE_DATA_DOES_NOT`.

**The catalogue is assembled agent by agent, from the agents this reader may already see.**
That is `brain.console.govern_estate.
AN_ESTATE_LISTING_IS_ASSEMBLED_FROM_WHAT_THE_READER_CAN_ALREADY_SEE`, and the audience is
`brain.agents.model.visible_agent_ids` through `brain.agent_routes.viewer_of`, so a skill
pinned only by an agent outside this reader's audience is absent rather than listed without its
agents. A row naming an agent names one the roster would have listed them anyway.

**Whether the screen opens is `brain.console.reads.permitted` and never a bare capability
check**, which is `brain.govern_routes`' rule and its reason: that function asks the screen's
tool capability and the console plane together, and a hand-written check drops the second, so
an existence-only reader would be answered a configuration screen. The question is asked before
a session is reached for, so a caller with no grant cannot tell a deployment with a database
from one without.

**Nothing here computes a reach.** There is no `.intersect(` in this module and no second
opinion about who may see an agent: the audience is `visible_agent_ids`' answer and the screen
is `permitted`'s. `brain.console.workspace.intersections_in` is run over this source by its
test.

Rejected: a route answering one skill by name. A deep link is resolved against the page, for
`brain.govern_routes.A_DEEP_LINK_RESOLVED_AGAINST_THE_PAGE_CANNOT_BE_AN_ORACLE`'s reason: a
route taking a skill name would answer, for anybody able to type one, whether a skill exists
in an install whose agents they cannot see, unless its two refusals were identical in every
particular. The rows the page already holds cannot be an oracle.

Rejected: reading the skills out of `agent.template_version.document` without materialising the
instance. It is one fewer object to build and it would list the published manifest's skills
rather than the agent's: an overlay may set the `skills` path, so the document and the agent
disagree exactly where somebody has changed something. `brain.agents.template.materialise`
applies the overlay, revalidates and produces real `SkillPin` objects, and that is the value
the rest of the platform pins against.

Rejected: showing a template version's `signed_by` as though it were a skill's approver. A
publisher signing a manifest that names a skill has signed for the manifest, not read the
procedure. Treating the two as one would be the review happening wherever somebody happened to
be standing, which is what `brain.console.agent_tabs.Control` refuses to offer a button for.

**What has never run.** This repository has no PostgreSQL, so neither statement below has been
executed against one. What is tested is the statement each compiles to, every refusal, and the
order the checks happen in.

Task ids: M42.6.4
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import (
    every_agent,
    manifest_of,
    record_of,
    viewer_of,
)
from brain.agents.model import AgentRecord, visible_agent_ids
from brain.agents.template import (
    FieldOwner,
    SignedManifest,
    TemplateError,
    TemplateInstance,
    materialise,
)
from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked, Asking
from brain.console.govern import Placed
from brain.console.govern_estate import skill_queue
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tools.review import QueueEntry
from brain.tools.skills import SkillPin

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why a pin is the whole of what this install records about a skill.
THE_ONLY_RECORD_OF_A_SKILL_HERE_IS_THE_PIN_AN_AGENT_CARRIES: Final = (
    "brain.tools.skills.ImportedSkill holds a skill's state, its reviewer, the source it was "
    "fetched from and the tools it names, and no table in this repository stores one. The "
    "durable record of a skill in a running install is therefore brain.agents.template."
    "SkillRef, which is a name and a digest on an agent's manifest. A catalogue built from "
    "those is a true listing of which procedures agents here are configured to run, and it "
    "is not a listing of which procedures exist, because nothing records that."
)

#: Why no row carries a review state.
AN_APPROVAL_NOBODY_STORED_CANNOT_BE_READ_OFF_A_PIN: Final = (
    "brain.console.agent_tabs.review_state derives a chip's state from ImportedSkill."
    "is_executable, which is approved, by somebody named, and unchanged since. The third "
    "clause is a comparison against a stored approval, and there is no stored approval here, "
    "so no row on this screen can be told apart from one whose bytes moved after a review. A "
    "state word would therefore be a guess, and the guess a reader acts on is the flattering "
    "one. The field is absent and the page says why, which is the shape brain.govern_routes."
    "RoleCatalogue.holders_are_not_recorded_yet uses for a fact its screen cannot answer."
)

#: Why the capabilities a skill would reach are stated as a guarantee and never as a list.
A_SKILL_DECLARES_NO_REACH_AND_AN_EMPTY_LIST_WOULD_READ_AS_ONE: Final = (
    "brain.tools.skills.skill_reach computes what a skill can use from the tools the SKILL.md "
    "names, intersected with what brain.gate.catalogue.project admits for the caller. The "
    "tool list is in the file, nothing stores the file, so the input is missing rather than "
    "empty. Rendering an empty capability list would say this skill reaches nothing, which is "
    "a stronger claim than the truth and the wrong direction to be wrong in. What is true "
    "whatever the file says is that a skill declares no reach of its own: Skill has no field "
    "for one and the frontmatter parser refuses the keys by name."
)

#: Why there is no assignment control and no write on this router.
AN_ASSIGNMENT_BUILT_ON_A_DIGEST_SOMEBODY_TYPED_IS_AN_APPROVAL_THEY_GRANTED_THEMSELVES: Final = (
    "brain.console.workspace_capabilities.attach_skill takes an ImportedSkill and defers the "
    "refusal to brain.tools.skills.pin_skill, which pins only a skill approved by a named "
    "person and unchanged since. Nothing in this install can produce such a value, so a write "
    "here would have to accept a name and a digest from a browser and pin them, which is an "
    "approval granted by whoever filled the form in. That is AN_ATTACH_PATH_THAT_TAKES_A_URL_"
    "IS_A_ROUTE_ROUND_THE_REVIEW arriving through a form instead of a URL, and a control that "
    "is refused every time it is pressed is worse than no control. The response says the "
    "write does not exist rather than the page drawing a button that pretends."
)

#: Why a column the design asks for is absent rather than empty.
A_COLUMN_THAT_CAN_ONLY_BE_BLANK_MAKES_A_CLAIM_THE_DATA_DOES_NOT: Final = (
    "SCREEN 6 of docs/screens.html lists Source, Ver, Scope, Reviewed and State beside every "
    "skill, and each of those is read off an ImportedSkill or off the SKILL.md, neither of "
    "which this install stores. Rendering the columns with nothing in them looks like the "
    "design and says something the design does not: a Reviewed column blank on every row "
    "reads as nobody having reviewed anything, and a State column blank on every row reads as "
    "every skill being unreviewed. The columns are absent, the response carries a field "
    "saying why, and the page says it in one sentence rather than in seven empty cells."
)

#: Why a disagreement between two pins is a statement about this page.
A_DIFFERENCE_BETWEEN_PINS_IS_ABOUT_THIS_PAGE_AND_NEVER_THE_ESTATE: Final = (
    "versions_differ is computed over the pins on the row, which are the pins of agents this "
    "reader's audience covers. An agent they cannot see may pin other bytes of the same "
    "skill, and the flag stays false. That is the narrow direction and the only honest one: "
    "a flag computed over every agent would be true for a reason the reader cannot find on "
    "the page, which is a count of what they were not shown wearing a boolean."
)


# ----------------------------------------------------------------- the screen

#: The screen whose grant decides whether this listing opens at all.
#:
#: A key rather than a capability written out, which is `brain.console.agent_tabs.SKILL_SCREEN`'s
#: construction and the same key: the tab and this screen are one grant, so a rename moves both.
SKILLS_SCREEN: Final = "skills"


# ------------------------------------------------------------------ the bounds

#: The most agents one catalogue answer is assembled from. A resource bound and not a
#: permission one: it is applied to the load, the audience filter runs over what came back,
#: and `truncated` says the load came back full without saying what was in the rest of it.
MAX_AGENTS_CONSIDERED: Final = 500

#: What a caller gets when they do not say.
DEFAULT_AGENTS_CONSIDERED: Final = 200


# ------------------------------------------------------------------- the shapes


class SkillPinView(BaseModel):
    """One agent, and the bytes of this skill it is configured to run.

    The digest rather than a version string, for `brain.tools.skills.SkillPin`'s own reason: a
    version is a number an author types and a skill edited without one is the commonest way a
    reviewed procedure changes. There is no field for a state, a reviewer or an instant; see
    `AN_APPROVAL_NOBODY_STORED_CANNOT_BE_READ_OFF_A_PIN`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    digest: str


class SkillRow(BaseModel):
    """One skill this install runs, and which of the reader's agents run it.

    No state, no source, no tools and no capabilities, each of them absent for the reason the
    module docstring gives rather than because nobody got to it. `versions_differ` is the one
    derived field and it is a fact about this row; see
    `A_DIFFERENCE_BETWEEN_PINS_IS_ABOUT_THIS_PAGE_AND_NEVER_THE_ESTATE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    pinned_by: tuple[SkillPinView, ...]
    #: The agents on this row are not all pinned to the same bytes of this skill.
    versions_differ: bool


class QueueEntryView(BaseModel):
    """One skill waiting for a reviewer, as the queue lists it.

    The name, how long it has waited and which fields changed, which is what
    `brain.tools.review.QueueEntry` says a reviewer needs to decide: a first submission has to
    be read in full and an edit needs only its changed fields read.

    There is no body and no reviewer, and neither is an omission.
    `brain.tools.skills.body_of` refuses to hand over the instructions of a skill nobody has
    approved, on the argument that the body is the procedure, and a queue listing carrying one
    would be that refusal undone by a screen. A reviewer reads the bytes where the decision is
    made, which is not here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    waiting_since: datetime
    #: Field names, never values, and empty for a first submission. `diff_skills`' own answer.
    changed: tuple[str, ...]
    stale: bool


class SkillQueueView(BaseModel):
    """What is waiting to be read, and the summary of exactly that.

    The counts are `brain.tools.review.QueueSummary`'s over the entries beside them, because
    `brain.console.govern_estate.skill_queue` returns both from one call and there is no way to
    obtain the second without the first. See
    `brain.console.govern_estate.A_SUMMARY_OVER_A_WIDER_LIST_THAN_THE_LISTING_IS_A_SUBTRACTION`:
    a summary counted over the whole queue beside a listing of the reader's slice publishes the
    difference, which is how many skills are waiting that this reader may not read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[QueueEntryView, ...]
    waiting: int
    edits: int
    stale: int


class SkillsPage(Page[SkillRow]):
    """Every skill this reader's agents are pinned to, the review queue, and two refusals.

    `total` is inherited and never populated, for the reason every listing in this application
    gives: this collection is filtered per caller, so a count would be the subtraction the
    disclosure rule forbids.

    The two booleans are always true today and are fields rather than sentences in the console,
    which is `brain.govern_routes.RoleCatalogue.holders_are_not_recorded_yet`'s construction:
    the fact belongs to the API that knows it, and the day a store exists the field goes false
    in the same commit that builds one rather than a console sentence going stale on its own.
    """

    #: The load came back full, so there are more agents than this answer was assembled from.
    #: Never how many.
    truncated: bool = False
    queue: SkillQueueView
    #: Nothing here stores an imported skill, so no row carries a state, a reviewer or the
    #: tools it names. See `AN_APPROVAL_NOBODY_STORED_CANNOT_BE_READ_OFF_A_PIN`.
    review_is_not_recorded: bool = True
    #: There is no route that assigns a skill to an agent. See
    #: `AN_ASSIGNMENT_BUILT_ON_A_DIGEST_SOMEBODY_TYPED_IS_AN_APPROVAL_THEY_GRANTED_THEMSELVES`.
    assignment_is_not_writable: bool = True


# ---------------------------------------------------------------- the statements


def installs_of(agent_ids: Sequence[str]) -> Select[tuple[TemplateInstanceRow, TemplateVersionRow]]:
    """Every named agent's install and the version it is pinned to, joined on the pin's pair.

    `brain.agent_routes.install_for` is the same join for one agent and is deliberately not
    reused: it selects by equality, and a catalogue asking it once per agent is one statement
    per row of the roster. The join is on both halves of the pin, template and version, because
    `agent.template_version`'s key is the pair and matching on the template alone would attach
    an instance to whichever version of it the database happened to return.

    Ordered by instance id, so two readings of an unchanged install are the same page and the
    grouping below does not depend on the order rows arrive in.
    """
    return (
        select(TemplateInstanceRow, TemplateVersionRow)
        .join(
            TemplateVersionRow,
            and_(
                TemplateVersionRow.template_id == TemplateInstanceRow.template_id,
                TemplateVersionRow.version == TemplateInstanceRow.template_version,
            ),
        )
        .where(TemplateInstanceRow.id.in_(agent_ids))
        .order_by(TemplateInstanceRow.id)
    )


def bounded_agents(limit: int) -> Select[tuple[AgentRow]]:
    """Every stored agent, bounded. Filtered by audience afterwards, in Python.

    `brain.agent_routes.every_agent` is the statement and the bound is applied here, which is
    that module's `A_ROSTER_IS_FILTERED_BEFORE_IT_IS_BOUNDED` with the bound moved to the load:
    the audience filter still runs over everything that came back, so no row is dropped by SQL
    for a reason a reader could read as a permission.
    """
    return every_agent().limit(limit)


# ------------------------------------------------------------------ rows to pins


def pins_of(
    instance_row: TemplateInstanceRow, version_row: TemplateVersionRow, record: AgentRecord
) -> tuple[SkillPin, ...]:
    """The skills one agent is pinned to, or nothing when its install does not construct.

    `brain.agent_routes.install_of`'s refusal, for its reason: `materialise` checks the pin,
    the overlay and the seal, `SignedManifest` recomputes the digest from the body, and none of
    those failures may become a status. An install that does not construct is an agent with no
    skills, for every reader alike, and the difference reaches a log rather than a response.

    The pins are `materialise`'s rather than the document's `skills` key read directly: the
    overlay may set that path, so the published manifest and the agent disagree exactly where
    somebody has changed something, and the value the rest of the platform pins against is the
    materialised one.
    """
    try:
        signed = SignedManifest(
            manifest=manifest_of(version_row.document),
            content_digest=version_row.content_digest,
            signature=version_row.signature,
            signed_by=version_row.signed_by,
            signed_at=version_row.signed_at,
        )
        instance = TemplateInstance(
            instance_id=instance_row.id,
            template_id=instance_row.template_id,
            template_version=instance_row.template_version,
            content_digest=instance_row.content_digest,
            overlay=instance_row.overlay,
            overlay_owners={
                path: FieldOwner.model_validate(owner)
                for path, owner in instance_row.field_owners.items()
            },
            created_by=instance_row.created_by,
        )
        effective = materialise(signed, instance, audience=record.audience)
    except (KeyError, ValueError, TemplateError) as exc:
        log.warning(
            "agent install does not construct", agent=record.agent_id, error=type(exc).__name__
        )
        return ()
    return effective.skill_pins


# ---------------------------------------------------------------- the projections


def catalogue(pins: Iterable[SkillPin]) -> tuple[SkillRow, ...]:
    """Every skill these pins name, in name order, with the agents pinned to each.

    Grouped by name rather than by name and digest, because a skill whose agents run different
    bytes is one skill with a disagreement on it and two rows would hide that behind a pair of
    entries that look like two procedures. `versions_differ` is the disagreement said out loud;
    see `A_DIFFERENCE_BETWEEN_PINS_IS_ABOUT_THIS_PAGE_AND_NEVER_THE_ESTATE`.

    Pins are sorted by agent and then by digest, so two readings of an unchanged install are
    the same page, and there is nowhere in the answer for a count of the agents left out.
    """
    held: dict[str, list[SkillPin]] = {}
    for pin in pins:
        held.setdefault(pin.skill_name, []).append(pin)
    return tuple(
        SkillRow(
            name=name,
            pinned_by=tuple(
                SkillPinView(agent_id=pin.agent_id, digest=pin.digest)
                for pin in sorted(held[name], key=lambda one: (one.agent_id, one.digest))
            ),
            versions_differ=len({pin.digest for pin in held[name]}) > 1,
        )
        for name in sorted(held)
    )


def submitted() -> tuple[Placed[QueueEntry], ...]:
    """Every skill waiting for a reviewer, which is nothing this install records.

    Empty because there is nowhere for a submission to have been written: `brain.tools.review.
    pending` builds a queue out of `ImportedSkill` values and nothing stores one. It is a
    function rather than a literal at the call site so that the absence has a place to be
    argued and a name a reader can search for, and so that the day a store exists this is the
    one line that changes.

    **An empty queue here means nothing is recorded, not that everything has been read**, and
    the page says which. The distinction is the same one `brain.core.errors` draws between
    DENIED and ABSENT, reached from the other side: a reviewer who reads "nothing is waiting"
    and concludes the queue is clear has been told something this install cannot know.
    """
    return ()


def entry_view(entry: QueueEntry, now: datetime) -> QueueEntryView:
    """One queue entry, copied field by field, with staleness asked of the entry.

    `is_stale` rather than a threshold applied here, so the line is `brain.tools.review.
    STALE_AFTER` and not a second copy of it that ages differently.
    """
    return QueueEntryView(
        name=entry.skill.skill.name,
        waiting_since=entry.waiting_since,
        changed=tuple(entry.changed),
        stale=entry.is_stale(now),
    )


def queue_view(
    entries: Sequence[Placed[QueueEntry]], reach: EntitlementSet, now: datetime
) -> SkillQueueView:
    """The queue this reader may see, and the summary of exactly that list.

    `brain.console.govern_estate.skill_queue` is the whole decision and it is not restated
    here: it narrows by the Skills screen's own capability against the row each submission sits
    in and then summarises what is left, in that order, because summarising first publishes how
    many skills are waiting that this reader may not read. M27.3.13 is closed by that function;
    this serves it.
    """
    narrowed = skill_queue(entries, reach, now)
    return SkillQueueView(
        entries=tuple(entry_view(one, now) for one in narrowed.entries),
        waiting=narrowed.summary.waiting,
        edits=narrowed.summary.edits,
        stale=narrowed.summary.stale,
    )


# ------------------------------------------------------------------- the wiring


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory, or a process-level fault identical for every caller.

    A `Failed` rather than an `Absent`, on `brain.routing_routes`' argument: an instance with no
    pool is broken rather than empty, and only a caller who already holds this screen's grant
    reaches this line.
    """
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_answerable() -> Absent:
    """The one refusal this router makes.

    Names the screen and never the row, the capability or the caller, which is
    `brain.govern_routes._not_answerable`'s construction: the screen names are the console's own
    menu, identical in every install and already listed to everybody by
    `console/src/layout/Shell.tsx`, so naming one discloses nothing about this company.
    """
    return Absent(f"the {SKILLS_SCREEN} screen is not answerable for this caller")


def visible_records(records: Sequence[AgentRecord], asked: Asking) -> tuple[AgentRecord, ...]:
    """The agents this caller's audience covers, in id order.

    `brain.agents.model.visible_agent_ids` is the answer and `brain.agent_routes.viewer_of`
    builds the viewer, so who may see an agent is decided once, by the module that owns it, and
    this listing agrees with the roster by construction rather than by two filters happening to
    match.
    """
    visible = visible_agent_ids(records, viewer_of(asked))
    return tuple(sorted((one for one in records if one.agent_id in visible), key=_by_id))


def _by_id(record: AgentRecord) -> str:
    return record.agent_id


router = APIRouter(prefix=API_PREFIX, tags=["skills"])


@router.get("/skills", response_model=SkillsPage, responses=COMMON_RESPONSES)
async def skills(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_AGENTS_CONSIDERED)] = DEFAULT_AGENTS_CONSIDERED,
) -> SkillsPage:
    """Every skill the agents this reader may see are pinned to, and the review queue.

    The screen's question first and the database second, and the order is the property: a
    caller holding no grant is refused identically on an instance with a database and on one
    without, so nobody reads this deployment's state off the difference between a refusal and a
    fault.

    Two loads. The agents, bounded, filtered by audience in Python by the one predicate that
    decides it; then the installs of exactly those agents, so nothing about an agent this
    caller may not see is fetched on their behalf. `truncated` is the first load having come
    back full, computed against what was loaded rather than against what survived the audience,
    because the second would be a count of what the filter removed spelled as a boolean.

    The queue comes back beside the rows, from `brain.console.govern_estate.skill_queue` over
    what this install records, which is nothing. See `submitted`.
    """
    if not permitted(screen(SKILLS_SCREEN).read, asked.reach, asked.now):
        log.info("skills screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()

    factory = _require_sessions(request)
    async with factory() as session:
        rows = (await session.execute(bounded_agents(limit))).scalars().all()
        records = [record for record in (record_of(row) for row in rows) if record is not None]
        mine = visible_records(records, asked)
        pairs = (await session.execute(installs_of([one.agent_id for one in mine]))).all()

    by_id = {one.agent_id: one for one in mine}
    pins: list[SkillPin] = []
    for instance_row, version_row in pairs:
        record = by_id.get(instance_row.id)
        if record is None:
            # An install whose agent is outside this reader's audience, which the statement
            # above did not ask for. Dropped rather than trusted: a filter written once and
            # checked once is a filter that stops being applied the day the statement changes.
            continue
        pins.extend(pins_of(instance_row, version_row, record))

    return SkillsPage(
        items=list(catalogue(pins)),
        next_cursor=None,
        truncated=len(rows) >= limit,
        queue=queue_view(submitted(), asked.reach, asked.now),
    )
