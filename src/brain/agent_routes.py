"""The agent roster, one agent's workspace and the template catalogue over HTTP.

`brain.console.workspace` builds a tab strip, a deep link and a composition diff, and the
console's agent page has asked `GET /api/v1/agents/{agent_id}/workspace` since M39.1.2.1 was
closed, answered by nothing, so every agent rendered the API's 404 sentence. The roster the
workspace's way back points at did not exist either. This module is both halves, and it adds
no rule of its own about who may see an agent or what they may read about one.

**Who may see an agent is its audience and nothing else.** `brain.agents.model.
visible_agent_ids` answers it for the roster and for the workspace alike, so an agent listed
is an agent that opens, and an agent that opens is an agent listed. Neither route asks for a
capability to know an agent exists: the audience is who may see and start it, and a roster
that also demanded `read:agent` would be a second answer to that question, stricter than the
picker a member already has, and the two would disagree about the same person on the same
day. What a capability decides is what a reader may read *about* an agent, and that is
`tab_strip`'s question. See `AUDIENCE_DECIDES_WHO_SEES_AN_AGENT_AND_NOTHING_ELSE_DOES`.

**An agent this caller may not see and an agent that does not exist are one 404 with one
body.** `_no_agent_here` is the only refusal either route makes about an agent, and it is
raised for a missing row, a row outside the audience and a row that does not construct. That
is `brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER` at the edge of the
process, and it is worth holding here as well as there because an address bar is a loop:
a caller who could tell "no such agent" from "not yours" would enumerate the company's agents
by trying slugs.

**The roster is a listing, and a listing is where a total leaks.** `brain.memory.review`
makes the argument for its own three listings: a page of rows wants a total at the top, and a
total beside a filtered list is the number of things the reader may not see. So `RosterPage`
never sets the `total` it inherits from `brain.api.Page`, an agent outside the audience is
absent rather than drawn greyed out, and the bound on the page is applied *after* the
audience filter. Bounding in SQL first would be the subtle version of the same leak: a full
page of rows of which three survive says there were others. See `A_ROSTER_IS_FILTERED_BEFORE_
IT_IS_BOUNDED`.

**The strip is `tab_strip` at the caller's own reach, never at the agent's.** A tab is an
administrative read about the agent, which a person holds or does not, and an agent's
ceiling never holds `read:agent`, so an intersection here would remove every tab for
everybody and look like caution. Nothing in this module intersects two entitlement sets;
`brain.console.workspace.intersections_in` is run over this source by its test.

**Only what this route holds is populated.** `tab_strip` shows a tab that is permitted *and*
has something in it, and says `populated` is handed in because what is in each tab is seven
questions of seven modules. This route answers one of them: it holds the agent's record and
its install, which is the Settings tab's content. Since 2026-09-16 a second tab has something in
it whatever the agent: the Automations tab draws the product's automation gallery, served by
`brain.automation_gallery_routes` behind the same tab's read, and the gallery is never empty
because `brain.console.automation_gallery.BUILT_IN` is not. The other five have no route serving
their read, so they are not populated, and they are absent from the strip rather than drawn over
an empty panel. See `ONLY_WHAT_THIS_ROUTE_HOLDS_IS_POPULATED`.

**The composition travels exactly when the Settings tab does.** `composition_rows` carries
the persona, which is prompt material, and says whether somebody may see it is the strip's
question. So the rows are sent when the strip holds Settings, and a reader without it gets an
empty list, which is also what an agent with no install gets. `set_by` is never sent, for
`A_COMPOSITION_ROW_SAYS_WHAT_AND_NEVER_WHO`.

**The roster carries what the workspace already tells the same reader, and not one word
more.** `docs/screens.html` SCREEN 4 is a table of agent, department, owner, ceiling, leash
rungs, runs and cost, and the first three of those are facts a reader who can open the agent
is already given on its own page: an agent listed is an agent that opens. So the department
and the steward travel on a roster entry, and the ceiling travels only for a reader who holds
the Agents screen's own read, because a scope predicate is the widest a run could reach and
that is the screen where an administrator reads one. What does not travel is a lifecycle
word, a count, or a figure this route cannot measure. See
`A_ROSTER_ENTRY_SAYS_NO_MORE_THAN_THE_WORKSPACE_IT_OPENS`.

**The builder travels with the Settings tab and the steward travels with the agent.**
`AgentRecord.created_by` is history and `AgentAudience.owner_id` is who answers for the agent
now, and `brain.agents.model` keeps them apart deliberately. The steward is who a person
needs in order to ask for something, so it goes to everybody the audience covers; the builder
is the question an audit asks, so it goes where the audit reads, which is the Settings tab's
own grant. Until 2026-09-16 the builder was sent nowhere and `tests/agent-page.test.tsx`
pinned that absence, which was right while nothing decided who could be told. See
`THE_BUILDER_TRAVELS_WITH_THE_AUDIT_AND_THE_STEWARD_TRAVELS_WITH_THE_AGENT`.

**The capability block is four reads of three modules and no arithmetic of its own.**
SCREEN 13 puts connectors, skills, knowledge and channels in one block under the heading
"what this agent is assembled from". Connectors are `brain.console.workspace_capabilities.
connector_rows` over the manifest's declared names, bound against the tools the agent's
ceiling actually allows and narrowed to the sources this caller could reach at all, with
`connector_strip` computing the overflow from those same rows. Skills are the manifest's
pinned references, behind the Skills screen's own read. Channels are `offered_channels` at
`E_run(caller, agent)`, each with `brain.console.agent_tabs.rendering_profile`'s derived
profile. Nothing here re-decides any of it and nothing here intersects two entitlement sets:
`run_reach` is the console's one route into the intersection and this module calls it.

**The header's creation time goes to the audience, and its lifecycle word and highest rung go
where the Settings tab does.** `docs/admin-console-architecture.md` 4.1a draws all three above
the page's three tabs. A date names nobody, so `created_at` travels as the steward does. A
state is `brain.agents.model.runnable_agent_ids`' question, and that function's reason for
telling nobody why an agent they used yesterday is not chosen today is why the word reaches only
a reader of the agent's configuration. The highest rung is the leash, which is configuration.
See `THE_HEADER_DATES_THE_AGENT_FOR_EVERYBODY_AND_STATES_IT_FOR_THE_SETTINGS_READ`.

**The Profile travels exactly where the Settings tab does, and its capability names only where
the capability vocabulary does.** The tier, the ceiling in words, the tools the ceiling names
and the leash by target are the agent's own decisions, which is what that tab is, so
`ProfileView` is null for everybody else, as the composition is empty. Inside it the sentences
naming capabilities come from `brain.console.reach_view.ceiling_block`, which discloses the
ceiling whole to a reader holding `CEILING_DISCLOSURE` and as a lock to anybody else and never
narrows it to what the reader holds. The words themselves are `brain.console.agent_profile`'s,
and this module decides only who is handed them. See
`THE_PROFILE_IS_CONFIGURATION_AND_ITS_CAPABILITY_NAMES_ARE_THE_VOCABULARYS`.

**The figure at the top of the page is sent with the statement that nothing records it.**
`HeadlineView.recorded` is `brain.console.agent_profile.RUN_SPEND_IS_RECORDED`, which a test
holds against the source for a writer of a run's cost, so the page can say "not recorded yet"
instead of drawing nought as a measurement. The figures themselves are unchanged, so the day a
writer lands nothing about the headline has to move but that constant.

**The connector strip carries every row it was cut from.** `ConnectorStripView.rows` is the
list the strip's `shown` is the head of and its `overflow` counts the tail of, so the page's
"N more" opens the reader's own rows and never a row the strip did not already count. See
`brain.console.workspace_capabilities.AN_OVERFLOW_COUNTS_WHAT_IS_OFF_THE_ROW_AND_NEVER_WHAT_IS_OUT_OF_REACH`.

**Four things SCREEN 13 and SCREEN 4 ask for are absent rather than guessed, and each is
absent because nothing stores it.** A channel row says which surfaces a run could be carried
on and never whether the install has one switched on, because no table holds a per-agent
channel enablement and a row reading "not enabled" would be an assertion nobody measured. A
connector row carries no health, because this route probes nothing and
`AN_UNPROBED_CONNECTOR_IS_NOT_A_HEALTHY_ONE` is exactly that rule. A skill chip carries no
review state, because the approved library has no table and a chip reading approved for a
skill nobody can read is worse than no chip. And the headline carries spend and runs and no
message count, because the turns are not joined here and nought would read as silence rather
than as absence. See `A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`.

**The template catalogue is the Skills and templates screen's grant and never one of its
own.** SCREEN 5 is a gallery of roles somebody can install, and it sits under Govern beside
the skills review queue in `docs/screens.html` as it does in `brain.console.screens`, where
one entry is called "Skills and templates". So `GET /agent-templates` asks `permitted` about
that screen's read and refuses in its words, rather than inventing a capability a gallery
would be the only reader of. The catalogue is the product's own twenty-three manifests plus
whatever this installation has published, each at its highest version, and a published
template that does not construct is absent for everybody exactly as an agent is. Installing
is not offered: `brain.agents.install` needs a signing key and a wizard, and a gallery with
an install button and nothing behind it is a worse answer than a gallery without one. See
`A_GALLERY_IS_A_LISTING_AND_A_LISTING_IS_WHERE_A_TOTAL_LEAKS`.

**A row that does not construct is absent for everybody.** A record that fails its own
validators is refused as though it were not there, uniformly, whoever asks, and logged at a
level an operator reads. A 500 would be the obvious answer and it is an oracle in both
routes: one bad row would take the roster down for every person, and on the workspace a 500
for a broken agent beside a 404 for a missing one says which slugs exist. See
`A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY`.

**The viewer is the caller and their primary department, and that is a gap stated rather than
hidden.** `AgentViewer.departments` is a set because a person can sit in two departments, and
`brain.core.principal.Principal` carries one. There is no membership read on the request path
today, so a person in Sales and Web sees Web's department agents and not Sales'. It fails in
the narrow direction, which is the direction a gap is allowed to fail in. See
`THE_VIEWER_IS_THEIR_PRIMARY_DEPARTMENT_UNTIL_MEMBERSHIP_IS_READ`.

Rejected: a SQL predicate for the audience. It would be cheaper on a large estate, and it
would be a second implementation of `visible_to` written in another language, and a second
copy of a visibility rule is the copy that is subtly wrong in production. Agents are counted
in tens on an installation, so reading every row and filtering in Python costs nothing
measurable; the day that stops being true the fix is `audience_scope` compiled through
`brain.core.scope_sql`, which is the same predicate rather than a second one.

Rejected: verifying the template's signature on read. `brain.agents.template.install` does it
at the moment a manifest becomes configuration, and it needs the installation's signing key.
What a read needs is that the row is the body that was signed, and `SignedManifest` recomputes
the digest on construction without any key, so a document edited after signing still cannot
reach a response.

Rejected: a disabled or archived flag on a roster entry. `brain.agents.model.
runnable_agent_ids` records why a caller is told nothing about why an agent they used
yesterday is not chosen today, and a roster saying "disabled" beside a name is that sentence.

**The roster and the template gallery page, search, filter and order through `brain.listing`**,
over the entries the audience decided. Every agent is read, as before; the page is cut from what
survived, so a cursor says there are more agents this reader may see and never that there are
agents they may not.

Task ids: M39.1.2.5, M27.8.6
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.catalogue import CATALOGUE
from brain.agents.install import bind_tools, bound_leash
from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentViewer,
    visible_agent_ids,
)
from brain.agents.template import (
    MANIFEST_PATHS,
    FieldOwner,
    SignedManifest,
    TemplateError,
    TemplateInstance,
    TemplateManifest,
    materialise,
)
from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked, Asking, reachable_sources
from brain.channels.adapter import ChannelAdapter, ChannelCapabilities
from brain.channels.email import EmailAdapter
from brain.channels.lark import LarkAdapter
from brain.channels.slack import SlackAdapter
from brain.channels.teams import TeamsAdapter
from brain.channels.telegram import TelegramAdapter
from brain.channels.whatsapp import WhatsAppAdapter
from brain.console.agent_profile import (
    RUN_SPEND_IS_RECORDED,
    LeashRow,
    ToolRow,
    ceiling_words,
    leash_rows,
    leash_up_to,
    rung_key,
    tool_rows,
)
from brain.console.agent_tabs import SKILL_SCREEN, rendering_profile
from brain.console.automation_gallery import GALLERY_TAB
from brain.console.reach_view import ceiling_block
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.workspace import (
    Range,
    Tab,
    WorkspaceTab,
    basis_for,
    composition_rows,
    divergent_parts,
    headline,
    tab_strip,
    window,
)
from brain.console.workspace_capabilities import (
    ConnectorRow,
    connector_rows,
    connector_strip,
    offered_channels,
    run_reach,
)
from brain.core.entitlement import Capability
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.errors import Absent, Failed
from brain.core.field_policy import FieldPolicy
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.gate.leash import Leash
from brain.knowledge.visibility import Visibility
from brain.listing import Column, ListAsked, Listing, Plan
from brain.models.routing import Tier
from brain.ops.spend import Actual, SpendError
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.spend import SpendActualRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tools.registry import ToolRegistry
from brain.tools.startup import every_row_classification

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why neither route asks for a capability before saying an agent exists.
AUDIENCE_DECIDES_WHO_SEES_AN_AGENT_AND_NOTHING_ELSE_DOES: Final = (
    "An agent's audience is who may see and start it, and visible_agent_ids is the one "
    "answer to that question. A roster that also required a capability would be a second "
    "answer, stricter than the picker a member already has, and a person would find an agent "
    "in one place and not the other. A capability decides what a reader may read about an "
    "agent, which is the tab strip's question, and never whether the agent is there."
)

#: Why the roster's bound is applied to the filtered list and not to the query.
A_ROSTER_IS_FILTERED_BEFORE_IT_IS_BOUNDED: Final = (
    "A page bounded in SQL and then filtered by audience comes back short whenever the "
    "filter did anything, and a page of three under a limit of fifty says there were rows "
    "the reader was not shown. So every row is read, the audience filter runs first, and the "
    "bound is applied to what survived. truncated then says there are more agents this "
    "reader may see, and never how many they may not."
)

#: Why the strip is told one tab has something in it.
ONLY_WHAT_THIS_ROUTE_HOLDS_IS_POPULATED: Final = (
    "tab_strip shows a tab that is permitted and populated, and a heading over an empty panel "
    "is a count of hidden things spelled out. This route holds the agent's record and its "
    "install, which is what the Settings tab reads, and the Automations tab always holds the "
    "product's automation gallery, which its own route serves behind the same tab's read. "
    "Marking the other five populated would draw five headings over nothing; marking Settings "
    "empty would withhold a tab whose content is already in the response."
)

#: Why a malformed row is refused as though it were missing.
A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY: Final = (
    "A stored agent that fails its own validators cannot have its audience evaluated, so "
    "there is no reader it could safely be shown to. Answering 500 would take the whole "
    "roster down for every person over one row, and on the workspace would distinguish a "
    "broken agent from a missing one, which says the slug exists. It is absent for everybody "
    "alike and it is logged, so the difference reaches an operator and never a response."
)

#: Why a roster entry carries a department and a steward and not a figure.
A_ROSTER_ENTRY_SAYS_NO_MORE_THAN_THE_WORKSPACE_IT_OPENS: Final = (
    "An agent on the roster is an agent whose workspace opens for this reader, and the "
    "workspace already tells them its steward. So a department and a steward on the entry "
    "disclose nothing a click does not, and they are what SCREEN 4 is a table of. The "
    "ceiling is a different question, because a scope predicate says how wide any run "
    "through this agent could be, so it travels only for a reader holding the Agents "
    "screen's own read. No entry carries a lifecycle word, a total or a figure, because a "
    "listing filtered by audience is where each of those becomes the number of agents the "
    "reader was not shown."
)

#: Why the builder is sent where the audit reads and the steward is sent to everybody.
THE_BUILDER_TRAVELS_WITH_THE_AUDIT_AND_THE_STEWARD_TRAVELS_WITH_THE_AGENT: Final = (
    "created_by is history and never moves; audience.owner_id is who answers for the agent "
    "today. A person looking at an agent needs the second in order to ask for anything, and "
    "it is theirs the moment the audience covers them. The first is the question an audit "
    "asks, so it is sent exactly where an audit reads, which is the Settings tab's own "
    "grant, and a reader without that tab gets a header with no builder on it rather than a "
    "field saying one is being withheld."
)

#: Why a figure nothing stores is left out rather than sent as nought.
A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT: Final = (
    "Nought is a measurement. A channel row reading not enabled, a connector reading "
    "healthy, a skill reading approved and a message count reading nought are each an "
    "assertion about a store this route does not have, and each of them reads to a person "
    "as a fact somebody checked. The honest answer is the field's absence: the surfaces a "
    "run could be carried on without saying which are switched on, a connector with no "
    "health at all, a skill with its pinned digest and no review, and a headline with spend "
    "and runs and no message count."
)

#: Why the template gallery asks one screen's grant and counts nothing.
A_GALLERY_IS_A_LISTING_AND_A_LISTING_IS_WHERE_A_TOTAL_LEAKS: Final = (
    "A template catalogue is read behind the Skills and templates screen, which is where an "
    "administrator already reads what agents can be taught to do, and a gallery with a "
    "capability of its own would be a second answer to that question reachable from one "
    "page. The listing carries no total for the roster's reason, and it carries no install "
    "count per template: the number of agents installed from a template is the number of "
    "agents, filtered by nothing, which is a count of rows the reader may not be able to "
    "open."
)

#: Why the viewer carries at most one department.
THE_VIEWER_IS_THEIR_PRIMARY_DEPARTMENT_UNTIL_MEMBERSHIP_IS_READ: Final = (
    "AgentViewer takes a set of departments because a person can sit in two, and the "
    "principal on a request carries one. Nothing on the request path reads membership, so "
    "the viewer is the caller and their primary department, and a person in a second "
    "department does not see that department's agents here. That is a gap and it fails "
    "narrow: nobody is shown an agent their audience does not cover."
)

#: Why the header's date goes to everybody and its state and rung do not.
THE_HEADER_DATES_THE_AGENT_FOR_EVERYBODY_AND_STATES_IT_FOR_THE_SETTINGS_READ: Final = (
    "When an agent was created names nobody and discloses nothing a person opening it could "
    "misuse, so it travels with the agent as the steward does. Whether it is enabled is the "
    "fact runnable_agent_ids keeps from a member of the audience, who is told nothing about why "
    "an agent they used yesterday is not chosen today, and the highest rung is the leash, which "
    "is configuration. Both are sent where the Settings tab is and are null everywhere else."
)

#: Why the Profile block follows the Settings tab and its capability names follow the vocabulary.
THE_PROFILE_IS_CONFIGURATION_AND_ITS_CAPABILITY_NAMES_ARE_THE_VOCABULARYS: Final = (
    "The tier, the ceiling in words, the tools the ceiling names and the leash are the agent's "
    "own decisions, which is what the Settings tab reads, so the block is sent where that tab "
    "is and nowhere else. A capability name tells a reader what can be granted at all, which is "
    "the Capabilities screen's grant, so the sentences naming capabilities come from "
    "ceiling_block and are whole for a holder of that grant and a lock for anybody else."
)


# ------------------------------------------------------------------------ the bounds

#: The most agents one roster page carries when nothing asked for fewer. A resource bound and not
#: a permission one: it is applied after the audience filter, so raising it discloses nothing, and
#: an installation with more agents than one page is told so by `next_cursor` and `truncated`.
MAX_ROSTER_ENTRIES: Final = 500

#: The tabs with something in them for every agent. See `ONLY_WHAT_THIS_ROUTE_HOLDS_IS_POPULATED`.
POPULATED_HERE: Final[frozenset[Tab]] = frozenset({Tab.SETTINGS, GALLERY_TAB})

#: The most templates one gallery answer carries. A resource bound, as the roster's is.
MAX_TEMPLATE_ENTRIES: Final = 500

#: The most accounting rows one headline is computed over. A bound on the read and not on
#: the figure: the rows are this agent's own and are filtered again by basis and window.
MAX_HEADLINE_ROWS: Final = 20_000

#: The window the front page's figures cover. Thirty days, which is `docs/screens.html`
#: SCREEN 13's own heading and `brain.ops.budgets.DAYS_IN_BUDGET_MONTH` through
#: `brain.console.workspace.RANGE_DAYS`, so the figure sits over the month a budget divides.
HEADLINE_RANGE: Final = Range.THIRTY_DAYS

#: The screen whose read decides whether a roster row carries a ceiling. The Settings tab's
#: capability is this screen's, which is what `brain.console.workspace.TABS` wires it to, so
#: a reader who sees a ceiling on the roster is one who could read it on the agent's page.
AGENT_SCREEN: Final = "agents"

#: The screen whose grant the template gallery is read behind. `brain.console.agent_tabs`
#: already names it for a skill on an agent, and the registry calls it "Skills and
#: templates". See `A_GALLERY_IS_A_LISTING_AND_A_LISTING_IS_WHERE_A_TOTAL_LEAKS`.
TEMPLATE_SCREEN: Final = SKILL_SCREEN

#: Every surface this product can deliver on, as the six adapters that own the declaration.
#:
#: Classes rather than a table of capabilities written here, because each adapter argues its
#: own ceiling in its own docstring and a second table is the copy that says `INTERNAL` where
#: the adapter says `CONFIDENTIAL`. None of them takes a constructor argument and none holds a
#: credential: `brain.ops.secrets.borrow` leases one per run, so asking a fresh adapter what
#: it can carry opens nothing and reads no configuration. It is also not a statement that this
#: installation has any of them set up. See `A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`.
CHANNEL_ADAPTERS: Final[tuple[Callable[[], ChannelAdapter], ...]] = (
    EmailAdapter,
    LarkAdapter,
    SlackAdapter,
    TeamsAdapter,
    TelegramAdapter,
    WhatsAppAdapter,
)


# ------------------------------------------------------------------------ the shapes


class RosterEntry(BaseModel):
    """One agent this caller may see, as SCREEN 4 tabulates one.

    The id is the address of its workspace and the name is what a person looks for. The
    department and the steward are the next two columns of that table and are facts the
    workspace already gives this reader; the ceiling is the fourth and travels only for a
    reader holding the Agents screen's read. Nothing here is a lifecycle word, a total or a
    figure. See `A_ROSTER_ENTRY_SAYS_NO_MORE_THAN_THE_WORKSPACE_IT_OPENS`.

    `department` is null for an agent whose audience is not a department's, which is the
    record's own shape rather than a blank column: `AgentAudience` refuses a department on a
    personal or company agent, so there is nothing there to send.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    owner_id: str
    department: str | None = None
    #: `AgentAuthority.scope`, as `Scope.model_dump` spells it, for a reader who holds the
    #: Agents screen's read. Null for everybody else, and null is the field's absence rather
    #: than an unrestricted ceiling: `Scope()` dumps to a clause list of its own.
    ceiling: dict[str, Any] | None = None


class RosterPage(Page[RosterEntry]):
    """One page of the agents this caller's audience covers, by name unless asked otherwise.

    `total` is inherited and never populated. `next_cursor` is present exactly when a further agent
    this reader may see matches, and `truncated` says the same thing for a reader that reads only
    the flag. See `A_ROSTER_IS_FILTERED_BEFORE_IT_IS_BOUNDED`.
    """

    #: There are more agents this caller may see than this answer carries. Never how many.
    truncated: bool = False


class AgentHeaderView(BaseModel):
    """Who an agent is, under the wire names `console/src/pages/agentQuery.ts` reads.

    `owner_id` is `AgentAudience.owner_id`, the current steward, and never `created_by`:
    `brain.agents.model` says the steward is who answers for an agent now, "the question
    everybody else asks", and everybody here is somebody the audience already covers.

    The summary and the lineage come from the install and are null when the agent has none
    that constructs. Both halves of the lineage are set together or neither is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    owner_id: str
    summary: str | None = None
    template_id: str | None = None
    template_version: int | None = None
    #: Who built it. Sent exactly where the Settings tab is. See
    #: `THE_BUILDER_TRAVELS_WITH_THE_AUDIT_AND_THE_STEWARD_TRAVELS_WITH_THE_AGENT`.
    created_by: str | None = None
    #: When the agent row was written, for everybody the audience covers. The page derives the
    #: days since from it. Null only for a row written without the database's own clock.
    created_at: datetime | None = None
    #: `AgentRecord.state`: enabled, disabled or archived. Sent where the Settings tab is. See
    #: `THE_HEADER_DATES_THE_AGENT_FOR_EVERYBODY_AND_STATES_IT_FOR_THE_SETTINGS_READ`.
    state: str | None = None
    #: The highest rung any action of this agent could be held to, as
    #: `brain.console.agent_profile.leash_up_to` says it. Sent where the Settings tab is, and null
    #: there too for an agent with no action, because a rung governs a side effect.
    leash_up_to: str | None = None


class TabView(BaseModel):
    """One tab of the strip: its key, its label and its purpose sentence.

    Deliberately not `WorkspaceTab` serialised whole. That type carries `read`, which names
    the capability each tab requires, and the list of grants a screen needs is a permission
    map handed to whoever is looking.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tab: str
    label: str
    purpose: str


class CompositionRowView(BaseModel):
    """One composition path, the template's value beside this agent's.

    Exactly `CompositionRow.wire()`, so the names are that type's rather than a second copy.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    part: str
    path: str
    template: str
    instance: str
    source: str


class SkillView(BaseModel):
    """One skill this agent is pinned to: its name and the digest the pin is over.

    No review state and no invocation count. The approved library has no table on this
    installation, so a chip reading approved would be about bytes nobody here can read, and a
    count would be mostly somebody else's afternoon read outside the usage screen's grant.
    See `A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    digest: str


class ConnectorView(BaseModel):
    """One connector this agent names, exactly as `ConnectorRow` carries one.

    `presence` is `brain.console.workspace_capabilities.Presence`, which has two members and
    no member meaning refused: a connector this reader could not see produces no row at all
    rather than a row saying why. There is no health field, because this route probes nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    presence: str


class ConnectorStripView(BaseModel):
    """The connector row and the count beside it, both over this reader's own rows.

    `overflow` counts what is off the end of the row and never what is out of reach, which is
    the rule `ConnectorStrip` enforces in its constructor rather than one restated here.
    `rows` is every row the strip was cut from, so `shown` is its head and `overflow` the length
    of its tail, and the page's overflow list opens rows this reader was already counted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    shown: list[ConnectorView]
    overflow: int = 0
    rows: list[ConnectorView] = []


class ChannelView(BaseModel):
    """One surface a run of this agent could be carried on, and how it would be laid out.

    There is no `enabled` field. See `A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`:
    nothing stores a per-agent channel enablement, and a row reading not enabled would be an
    assertion nobody measured, drawn beside rows that are measurements.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    #: `brain.console.agent_tabs.RenderProfile`, derived from the surface's own capabilities.
    profile: str


class HeadlineView(BaseModel):
    """Spend and runs for this agent over one window, and whose they are.

    `basis` is carried rather than left implicit, for `brain.console.workspace.Headline`'s
    reason: a figure whose meaning is unstated is read as the total, so a reader shown their
    own spend with no label would read it as the agent's.

    No message count, and no projection. The turns are not read here, and a projection is
    `projection`'s answer on the wider basis only, which needs an `Allowance` this route has
    no budget to load.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    basis: str
    range: str
    spend_minor: int
    runs: int
    #: Whether anything records what a run cost. While it is false the two figures above are
    #: over rows nothing writes, and the page says they are not recorded yet rather than drawing
    #: them. See `brain.console.agent_profile`'s
    #: `A_FIGURE_NOTHING_WRITES_IS_SERVED_WITH_THE_STATEMENT_THAT_NOTHING_WRITES_IT`.
    recorded: bool = False


class ToolView(BaseModel):
    """One tool the agent's ceiling names, as `brain.console.agent_profile.ToolRow` carries it.

    `source`, `side_effect` and `description` are null together for a name no registered tool
    answers to, and `within_ceiling` is whether a run could be handed the tool at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source: str | None = None
    side_effect: str | None = None
    description: str | None = None
    within_ceiling: bool


class LeashEntryView(BaseModel):
    """One configured leash entry: its rung, and the rows it applies to when not every row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rung: str
    where: str | None = None


class LeashRowView(BaseModel):
    """One target on the leash, as `brain.console.agent_profile.LeashRow` carries it.

    `rung` is the highest of `rungs`, which are every rung a call on the target could be held
    to, lowest first. `configured` is false for an action on the Shadow default, and `acts` is
    whether an action this agent could take is behind the target.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    rung: str
    rungs: list[str]
    configured: bool
    acts: bool
    entries: list[LeashEntryView] = []


class AgentCeilingView(BaseModel):
    """The ceiling in words, as `brain.console.agent_profile.CeilingWords` carries it.

    `reads` is empty and `reads_locked` true for a reader the capability names are locked for,
    whatever the ceiling holds. `max_side_effect` is `SideEffect`'s own word beside the sentence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rows: str
    reads: list[str] = []
    reads_locked: bool
    tools: str
    largest_effect: str
    max_side_effect: str


class ProfileView(BaseModel):
    """How the agent is set up, for a reader of the Settings tab and nobody else.

    See `THE_PROFILE_IS_CONFIGURATION_AND_ITS_CAPABILITY_NAMES_ARE_THE_VOCABULARYS`. `tier` is
    stored and not yet passed to routing, which `docs/admin-console-architecture.md` 4.1a says
    the page must say.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: str
    #: `AgentAudience.level`: personal, department or company. The steward and the department
    #: already reach the audience; the level word is the Settings read's, as 4.1a row 14 says.
    audience_level: str
    ceiling: AgentCeilingView
    tools: list[ToolView]
    leash: list[LeashRowView]


class WorkspaceView(BaseModel):
    """One agent's workspace, as this caller may read it. No field here is a count of what
    was withheld."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: AgentHeaderView
    tabs: list[TabView]
    composition: list[CompositionRowView]
    #: The composition parts this install has edited that its template supplies. Travels with
    #: the composition, because it is a fact about the same rows.
    divergent: list[str] = []
    skills: list[SkillView] = []
    connectors: ConnectorStripView = ConnectorStripView(shown=[])
    channels: list[ChannelView] = []
    headline: HeadlineView | None = None
    #: Null for a reader without the Settings tab, as the composition is empty for one.
    profile: ProfileView | None = None


class Origin(enum.StrEnum):
    """Where a template in the gallery came from. Two, and the difference is who signed it.

    A built-in template is one of the twenty-three this product ships, and
    `brain.agents.catalogue` says plainly that nothing publishes them: they hold no
    signature, because a signature is a claim about who published and nobody has. A published
    one is a row this installation signed with its own key. Saying which is which is the
    difference between "this is what the product offers" and "this is what we have made", and
    a gallery that merged them would let the second wear the first's authority.
    """

    BUILT_IN = "built_in"
    PUBLISHED = "published"


class TemplateEntry(BaseModel):
    """One template a person could install, as SCREEN 5 shows one.

    The name, the version, the sentence underneath and who published it. No install count:
    see `A_GALLERY_IS_A_LISTING_AND_A_LISTING_IS_WHERE_A_TOTAL_LEAKS`. No department either,
    because a template has no audience of its own until it is installed, and the department
    on SCREEN 5's card is the department of the agents somebody has installed from it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    version: int
    display_name: str
    summary: str | None = None
    published_by: str
    origin: str


class TemplateGallery(Page[TemplateEntry]):
    """One page of the templates this reader may be offered, by name unless asked otherwise.

    `total` is inherited and never populated, and `next_cursor` and `truncated` mean what the
    roster's do.
    """

    truncated: bool = False


# ------------------------------------------------------------------ rows to records


def record_of(row: AgentRow) -> AgentRecord | None:
    """The stored agent as the domain type, or None when it does not construct.

    Every validator in `brain.agents.model` runs, including the tool ceiling's, because the
    audience cannot be trusted off a row the record refuses. See
    `A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY`.
    """
    try:
        return AgentRecord(
            agent_id=row.id,
            display_name=row.display_name,
            persona=row.persona,
            tier=Tier(row.tier),
            audience=AgentAudience(
                level=Visibility(row.visibility),
                owner_id=row.owner_id,
                department=row.department or "",
            ),
            authority=AgentAuthority(
                scope=Scope.model_validate(row.scope),
                capabilities=tuple(Capability(value=one) for one in row.capabilities),
                allowed_tools=frozenset(row.allowed_tools),
                required_tools=frozenset(row.required_tools),
                max_side_effect=SideEffect(row.max_side_effect),
            ),
            created_by=row.created_by,
            disabled_at=row.disabled_at,
            archived_at=row.archived_at,
        )
    except ValueError as exc:
        # `ValidationError` is a `ValueError`, and so is an enum given a word it does not
        # hold and the ceiling's own refusal of a required tool outside the allowed set.
        log.warning("agent row does not construct", agent=row.id, error=type(exc).__name__)
        return None


def manifest_of(document: Mapping[str, Any]) -> TemplateManifest:
    """A manifest from the flat document `TemplateManifest.document()` produced.

    The inverse of that method, walking the same `MANIFEST_PATHS` it walks, so a path is read
    back into exactly the section it was taken out of. Nothing here checks the round trip,
    because `SignedManifest` does: it recomputes the digest from the rebuilt body and refuses
    a mismatch, so a reconstruction that lost or moved a value cannot be signed-for.
    """
    nested: dict[str, Any] = {}
    for path in MANIFEST_PATHS:
        head, _, tail = path.partition(".")
        if tail:
            nested.setdefault(head, {})[tail] = document[path]
        else:
            nested[head] = document[path]
    return TemplateManifest.model_validate(nested)


@dataclass(frozen=True)
class Install:
    """What an agent was installed from, and the diff between the two."""

    template_id: str
    template_version: int
    summary: str
    composition: tuple[CompositionRowView, ...]
    #: The parts this install has edited that its template supplies, in `Part`'s spelling.
    divergent: tuple[str, ...]
    #: The skills the effective manifest pins, by name and digest.
    skills: tuple[SkillView, ...]
    #: The connectors the effective manifest declares, in its own sorted order.
    connectors: tuple[str, ...]
    #: The effective leash, with the targets as the manifest declares them.
    leash: Leash = field(default_factory=Leash)
    #: The tools the effective manifest declares, before this install bound them to its own.
    declared_tools: tuple[str, ...] = ()


def install_of(
    instance_row: TemplateInstanceRow, version_row: TemplateVersionRow, record: AgentRecord
) -> Install | None:
    """The install behind one agent, or None when it does not construct.

    `materialise` checks the pin, the overlay and the seal, and `SignedManifest` checks the
    body against its digest, so this adds no check of its own. What it adds is the refusal to
    let any of those failures become a status: an install that does not construct is an agent
    with no lineage and no composition, for every reader alike.
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
        rows = composition_rows(signed, effective)
    except (KeyError, ValueError, TemplateError) as exc:
        # Not `WorkspaceError`. `composition_rows` raises it for an agent materialised from a
        # different template or version, and `materialise` has already refused exactly that
        # pin two lines up, so a catch for it here could not fire and no test could reach it.
        log.warning(
            "agent install does not construct", agent=record.agent_id, error=type(exc).__name__
        )
        return None
    return Install(
        template_id=instance.template_id,
        template_version=instance.template_version,
        summary=effective.manifest.identity.summary,
        composition=tuple(CompositionRowView(**row.wire()) for row in rows),
        divergent=tuple(sorted(one.value for one in divergent_parts(instance))),
        skills=tuple(
            SkillView(name=one.name, digest=one.digest) for one in effective.manifest.skills
        ),
        connectors=tuple(effective.manifest.connectors),
        leash=effective.leash,
        declared_tools=tuple(effective.manifest.authority.allowed_tools),
    )


# ------------------------------------------------------------------ the decisions


def viewer_of(asked: Asking) -> AgentViewer:
    """The caller, as an audience question is asked about them.

    See `THE_VIEWER_IS_THEIR_PRIMARY_DEPARTMENT_UNTIL_MEMBERSHIP_IS_READ`.
    """
    department = asked.caller.principal.primary_department
    return AgentViewer(
        principal_id=asked.caller.principal.id,
        departments=frozenset({department}) if department else frozenset(),
    )


def roster_entry(record: AgentRecord, *, ceilings: bool) -> RosterEntry:
    """One agent as a row of SCREEN 4's table, at this reader's reach.

    `ceilings` is the Agents screen's own read, asked once by the caller rather than per row,
    so every row of one answer was decided by one question. See
    `A_ROSTER_ENTRY_SAYS_NO_MORE_THAN_THE_WORKSPACE_IT_OPENS`.

    The department is `AgentAudience.department`, which is empty for every audience but a
    department's, and empty is sent as absent rather than as a blank column.
    """
    return RosterEntry(
        agent_id=record.agent_id,
        display_name=record.display_name,
        owner_id=record.audience.owner_id,
        department=record.audience.department or None,
        ceiling=record.authority.scope.model_dump(mode="json") if ceilings else None,
    )


#: What the Agents screen may search, filter and order by: the fields a roster entry shows.
ROSTER: Final[Listing[RosterEntry]] = Listing(
    name="agents",
    columns=(
        Column("display_name", lambda row: row.display_name, search=True, sort=True),
        Column("agent_id", lambda row: row.agent_id, search=True, sort=True),
        Column("owner_id", lambda row: row.owner_id, search=True, filter=True),
        Column("department", lambda row: row.department, search=True, filter=True, sort=True),
    ),
    key=lambda row: row.agent_id,
    order="display_name",
)
RosterQuery = Annotated[ListAsked, Depends(ROSTER.query())]

#: What the template gallery may search, filter and order by.
TEMPLATES: Final[Listing[TemplateEntry]] = Listing(
    name="agent-templates",
    columns=(
        Column("display_name", lambda row: row.display_name, search=True, sort=True),
        Column("template_id", lambda row: row.template_id, search=True, sort=True),
        Column("summary", lambda row: row.summary, search=True),
        Column("published_by", lambda row: row.published_by, search=True, filter=True),
        Column("origin", lambda row: row.origin, filter=True, sort=True),
        Column("version", lambda row: row.version, sort=True),
    ),
    key=lambda row: row.template_id,
    order="display_name",
)
TemplatesQuery = Annotated[ListAsked, Depends(TEMPLATES.query())]


def roster(
    records: Sequence[AgentRecord],
    viewer: AgentViewer,
    *,
    ceilings: bool = False,
    plan: Plan[RosterEntry] | None = None,
) -> RosterPage:
    """One page of the agents this viewer's audience covers, cut after filtering.

    Ordered by name and then by id unless the plan asks otherwise, so two readings of an unchanged
    table are one list and the order says nothing about when an agent was created. With no plan,
    the first `MAX_ROSTER_ENTRIES` in that order.
    """
    visible = visible_agent_ids(records, viewer)
    entries = [roster_entry(one, ceilings=ceilings) for one in records if one.agent_id in visible]
    chosen = plan or ROSTER.plan(ListAsked(limit=MAX_ROSTER_ENTRIES), reader=viewer.principal_id)
    page = chosen.page(entries)
    return RosterPage(
        items=list(page.items),
        next_cursor=page.next_cursor,
        truncated=page.next_cursor is not None,
    )


def template_entry(manifest: TemplateManifest, origin: Origin) -> TemplateEntry:
    """One manifest as a gallery card, read off its identity section and nothing else."""
    identity = manifest.identity
    return TemplateEntry(
        template_id=identity.template_id,
        version=identity.version,
        display_name=identity.display_name,
        summary=identity.summary or None,
        published_by=identity.published_by,
        origin=origin.value,
    )


def gallery(
    published: Sequence[TemplateManifest], plan: Plan[TemplateEntry] | None = None
) -> TemplateGallery:
    """The catalogue this installation can offer: what ships, and what has been published.

    **The highest version of each published template and no other, and a published template
    hides the built-in one it shares an id with.** A gallery listing three versions of one
    role is a version history wearing a gallery's clothes, and a built-in card beside a
    published card of the same id would offer two different documents under one name, with
    nothing on either saying which an install would pin. The published row wins because it is
    the one an install can actually be pinned to: `brain.agents.template.install` verifies a
    signature, and the built-in manifests carry none.

    Ordered by name and then by id, as the roster is, so two readings of an unchanged
    catalogue are one list.
    """
    highest: dict[str, TemplateManifest] = {}
    for one in published:
        identity = one.identity
        held = highest.get(identity.template_id)
        if held is None or identity.version > held.identity.version:
            highest[identity.template_id] = one
    cards = [template_entry(one, Origin.PUBLISHED) for one in highest.values()]
    cards.extend(
        template_entry(one, Origin.BUILT_IN)
        for one in CATALOGUE
        if one.identity.template_id not in highest
    )
    chosen = plan or TEMPLATES.plan(ListAsked(limit=MAX_TEMPLATE_ENTRIES), reader="")
    page = chosen.page(cards)
    return TemplateGallery(
        items=list(page.items),
        next_cursor=page.next_cursor,
        truncated=page.next_cursor is not None,
    )


def declared_channels() -> tuple[ChannelCapabilities, ...]:
    """What each surface this product ships can carry, asked of the adapters themselves.

    A fresh adapter per call and no configuration read, because `capabilities` is a
    declaration: `brain.channels.adapter.ChannelCapabilities` is frozen and is read at send
    time rather than at registration precisely so that an adapter cannot widen itself, and
    every one of the six declares it from constants in its own module. Restating the six here
    would be a second answer to what a surface can carry, and the permissive copy is the one
    that ends up in front of somebody.
    """
    return tuple(one().capabilities() for one in CHANNEL_ADAPTERS)


def product_field_policy() -> FieldPolicy:
    """Every column classification this product ships, as one policy.

    Wider than whatever this install has registered tools for, and that is the direction it
    has to fail in: the policy decides the most sensitive thing a run could return, which
    decides which surfaces may carry it, so a policy missing a rule offers a channel that
    should not have been offered. `brain.tools.startup.every_row_classification` is the one
    list of what this product classifies, and one classification per entity is pinned by that
    module's own test, so the rules cannot collide here.
    """
    return FieldPolicy(
        rules=tuple(rule for one in every_row_classification() for rule in one.policy().rules)
    )


def offered_surfaces(record: AgentRecord, asked: Asking) -> tuple[ChannelCapabilities, ...]:
    """The declared surfaces a run of this agent by this caller could be carried on, in order.

    The one computation behind the workspace's channel rows and the About flow's first step, so
    the two cannot offer different surfaces to one reader. See `channel_views` for the argument.
    """
    capabilities = declared_channels()
    reach = run_reach(asked.reach, record)
    offered = frozenset(offered_channels(reach, capabilities, product_field_policy(), asked.now))
    return tuple(one for one in capabilities if one.channel in offered)


def channel_views(record: AgentRecord, asked: Asking) -> tuple[ChannelView, ...]:
    """The surfaces a run of this agent by this caller could be carried on (M39.2.4.2).

    `offered_channels` at `E_run(caller, agent)`, which `run_reach` computes through the
    console's one call into `EntitlementSet.intersect`. Computed at the run's reach rather
    than at the agent's ceiling, for `brain.console.workspace_capabilities.
    A_CHANNEL_OFFERED_AT_THE_CEILING_DESCRIBES_THE_CEILING`: the ceiling's sensitivity is a
    fact about the agent and not about the person reading the page.

    No row says whether the install has a surface switched on. See
    `A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`.
    """
    return tuple(
        ChannelView(channel=one.channel.value, profile=rendering_profile(one).value)
        for one in offered_surfaces(record, asked)
    )


def reader_connector_rows(
    install: Install | None, record: AgentRecord, registry: ToolRegistry | None, asked: Asking
) -> tuple[ConnectorRow, ...]:
    """The connectors this agent names, as this reader may see them (M39.2.1.1, M39.2.1.4).

    Three sets and none of them decided here. `declared` is the effective manifest's own
    list, which is what the template asked an install to bind. `attached` is the sources
    behind the tools the agent's ceiling actually allows, because that is what
    `brain.agents.install.bind_tool` wrote when the install bound one, and a source with no
    bound tool is a connector the agent asks for and cannot use, which is M39.2.1.4's
    `REQUESTED`. `visible` is `brain.api_routes.reachable_sources`, the same function the
    records route consults, so "may this caller be told about this source" has one answer.

    A process with no tool registry can name no source, so nothing is visible and the strip
    is empty: the same answer a reader who reaches no source gets, which is the direction an
    absent registry has to fail in.
    """
    if install is None:
        return ()
    visible = () if registry is None else reachable_sources(registry, asked)
    allowed = record.authority.allowed_tools
    attached = (
        ()
        if registry is None
        else tuple(
            {one.source for one in registry.definitions() if one.name in allowed and one.source}
        )
    )
    return connector_rows(declared=install.connectors, attached=attached, visible=visible)


def connector_view(
    install: Install | None, record: AgentRecord, registry: ToolRegistry | None, asked: Asking
) -> ConnectorStripView:
    """The connector strip over `reader_connector_rows`, with every row it was cut from.

    `connector_strip` computes the head and the overflow from the same rows that are sent whole,
    so the overflow list and the count beside the strip cannot be over two different sets.
    """
    rows = reader_connector_rows(install, record, registry, asked)
    strip = connector_strip(rows)
    return ConnectorStripView(
        shown=[
            ConnectorView(source=one.source, presence=one.presence.value) for one in strip.shown
        ],
        overflow=strip.overflow,
        rows=[ConnectorView(source=one.source, presence=one.presence.value) for one in rows],
    )


def actual_of(row: SpendActualRow) -> Actual | None:
    """One accounting row as the domain type, or None when it does not construct.

    `trace_id` is nullable in this release only, and `Actual` requires one, so a row written
    by the previous release is absent from a figure rather than taking the page down. Absent
    for everybody alike, as a malformed agent row is, and the loss is a run's cost missing
    from a headline rather than a number computed from a row nobody could account for.
    """
    try:
        return Actual(
            principal_id=row.principal_id,
            principal_kind=PrincipalKind(row.principal_kind),
            traffic=TrafficClass(row.traffic),
            department=row.department,
            agent_id=row.agent_id,
            model=row.model,
            lane=Lane(row.lane),
            cost_minor=row.cost_minor,
            at=row.at,
            trace_id=row.trace_id or "",
        )
    except (ValueError, SpendError) as exc:
        log.warning("spend row does not construct", error=type(exc).__name__)
        return None


def headline_view(agent_id: str, rows: Sequence[Actual], asked: Asking) -> HeadlineView:
    """Spend and runs for this agent over `HEADLINE_RANGE`, at whichever basis this reader
    holds (M39.1.3.1).

    `basis_for` asks `brain.console.reads.permitted` about the budget screen's own read
    rather than a capability invented for a front page, and `headline` applies the window and
    the basis to the rows. Both are the workspace module's, unchanged: a figure on an agent's
    front page and the same figure on the budget screen cannot disagree about what a run cost
    because they are computed by one function.

    The message count `Headline` also carries is deliberately not sent on. See
    `A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`.
    """
    basis = basis_for(asked.reach, asked.now)
    since, until = window(HEADLINE_RANGE, asked.now)
    figures = headline(
        agent_id,
        caller_id=asked.caller.principal.id,
        basis=basis,
        actuals=rows,
        since=since,
        until=until,
    )
    return HeadlineView(
        basis=figures.basis.value,
        range=HEADLINE_RANGE.value,
        spend_minor=figures.spend_minor,
        runs=figures.runs,
        recorded=RUN_SPEND_IS_RECORDED,
    )


def holds_settings(strip: Sequence[WorkspaceTab]) -> bool:
    """Whether a strip holds the Settings tab, which every configuration block on an agent's page
    travels with.

    Asked of the strip rather than of `permitted` directly, so the composition, the Profile and
    the About flow's setup are sent on exactly one condition, the one the strip shows the reader.
    """
    return any(one.tab is Tab.SETTINGS for one in strip)


def may_read_settings(asked: Asking) -> bool:
    """`holds_settings` over this reader's own strip, for a route that draws no strip."""
    return holds_settings(tab_strip(asked.reach, populated=POPULATED_HERE, now=asked.now))


def leash_of(install: Install | None, registry: ToolRegistry | None) -> Leash:
    """The agent's leash, with its targets bound to the tools this process registers.

    `brain.agents.install.bound_leash` over `bind_tools`, which is what a finished install binds a
    template's declared targets with, so a leash row and an action are keyed by the one name the
    gate looks a rung up by. An agent with no install that constructs has no entry at all, and
    `Leash.rung_for` answers `MISSING_ENTRY_RUNG` for every target it is asked about, which is the
    blank template's floor. With no registry nothing binds, and the entries are kept as declared.
    See `brain.console.agent_profile`'s
    `THE_LEASH_SHOWN_IS_THE_CONFIGURED_ONE_AND_A_RUN_MAY_ONLY_BE_HELD_LOWER`.
    """
    if install is None:
        return Leash()
    if registry is None:
        return install.leash
    return bound_leash(install.leash, bind_tools(install.declared_tools, registry))


def registered_tools(
    record: AgentRecord, registry: ToolRegistry | None
) -> tuple[ToolDefinition, ...]:
    """The registered tools this agent's ceiling names, in the registry's own order."""
    if registry is None:
        return ()
    allowed = record.authority.allowed_tools
    return tuple(one for one in registry.definitions() if one.name in allowed)


@dataclass(frozen=True)
class Configured:
    """What the Settings read is handed about one agent: its tools and its leash by target."""

    tools: tuple[ToolRow, ...]
    leash: tuple[LeashRow, ...]


def configured(
    record: AgentRecord, install: Install | None, registry: ToolRegistry | None
) -> Configured:
    """The agent's tools and leash rows, computed once for the header and the Profile alike."""
    tools = tool_rows(record.authority, registered_tools(record, registry))
    rows = leash_rows(
        leash_of(install, registry), record.agent_id, (one.name for one in tools if one.acts)
    )
    return Configured(tools=tools, leash=rows)


def profile_view(record: AgentRecord, setup: Configured, asked: Asking) -> ProfileView:
    """The Profile block for a reader of the Settings tab (M27.11.15's content, not its page).

    The capability names are `ceiling_block`'s for this reader, whole or locked. See
    `THE_PROFILE_IS_CONFIGURATION_AND_ITS_CAPABILITY_NAMES_ARE_THE_VOCABULARYS`.
    """
    words = ceiling_words(
        record.authority, ceiling_block(record, asked.reach, asked.now), setup.tools
    )
    return ProfileView(
        tier=record.tier.value,
        audience_level=record.audience.level.value,
        ceiling=AgentCeilingView(
            rows=words.rows,
            reads=list(words.reads),
            reads_locked=words.reads_locked,
            tools=words.tools,
            largest_effect=words.largest_effect,
            max_side_effect=record.authority.max_side_effect.value,
        ),
        tools=[
            ToolView(
                name=one.name,
                source=one.source,
                side_effect=None if one.side_effect is None else one.side_effect.value,
                description=one.description,
                within_ceiling=one.within_ceiling,
            )
            for one in setup.tools
        ],
        leash=[
            LeashRowView(
                target=one.target,
                rung=rung_key(one.highest),
                rungs=[rung_key(rung) for rung in one.rungs],
                configured=one.configured,
                acts=one.acts,
                entries=[
                    LeashEntryView(rung=rung_key(entry.rung), where=entry.where)
                    for entry in one.entries
                ],
            )
            for one in setup.leash
        ],
    )


def tab_view(one: WorkspaceTab) -> TabView:
    """One tab under the console's names. The label is the key's own word, capitalised."""
    return TabView(tab=one.tab.value, label=one.tab.value.capitalize(), purpose=one.purpose)


def workspace(
    record: AgentRecord,
    install: Install | None,
    asked: Asking,
    *,
    registry: ToolRegistry | None = None,
    spend: Sequence[Actual] = (),
    created_at: datetime | None = None,
) -> WorkspaceView:
    """One visible agent's workspace at this caller's reach.

    Takes a record the audience has already admitted; `agent_workspace` is where that is
    decided, and nothing here could decide it, because nothing here is handed a viewer.

    **Three of the blocks travel with the Settings tab and two do not, and the split is the
    plane each sits on.** The composition, the divergence and the builder are the agent's own
    configuration, which is what that tab is; the skills are configuration too and are
    narrowed again by the Skills screen's read, because a skill's name describes a procedure
    somebody wants to run. The connectors are narrowed by which sources this caller could be
    told about at all, which `reachable_sources` already answers per source, so the Settings
    tab is not a second gate over them. The channels and the headline are computed at the
    run's reach and at the budget screen's grant respectively, and neither is a fact about
    the agent's configuration.

    **The Profile, the lifecycle word and the highest rung travel with the Settings tab too, and
    they do not need an install.** An agent with no install that constructs still has a ceiling,
    a tier and a state on its own row, and its leash is the Shadow default everywhere. See
    `THE_PROFILE_IS_CONFIGURATION_AND_ITS_CAPABILITY_NAMES_ARE_THE_VOCABULARYS`.
    """
    strip = tab_strip(asked.reach, populated=POPULATED_HERE, now=asked.now)
    reads_settings = holds_settings(strip)
    # One name for "there is an install and this reader may read its configuration", so the
    # three blocks below cannot come apart by somebody editing one condition of three.
    settings = install if install is not None and reads_settings else None
    setup = configured(record, install, registry) if reads_settings else None
    may_read_skills = permitted(screen(SKILL_SCREEN).read, asked.reach, asked.now)
    highest = None if setup is None else leash_up_to(setup.leash)
    return WorkspaceView(
        agent=AgentHeaderView(
            agent_id=record.agent_id,
            display_name=record.display_name,
            owner_id=record.audience.owner_id,
            summary=(install.summary or None) if install is not None else None,
            template_id=install.template_id if install is not None else None,
            template_version=install.template_version if install is not None else None,
            created_by=record.created_by if reads_settings else None,
            created_at=created_at,
            state=record.state.value if setup is not None else None,
            leash_up_to=None if highest is None else rung_key(highest),
        ),
        tabs=[tab_view(one) for one in strip],
        composition=list(settings.composition) if settings is not None else [],
        divergent=list(settings.divergent) if settings is not None else [],
        skills=list(settings.skills) if settings is not None and may_read_skills else [],
        connectors=connector_view(install, record, registry, asked),
        channels=list(channel_views(record, asked)),
        headline=headline_view(record.agent_id, spend, asked),
        profile=None if setup is None else profile_view(record, setup, asked),
    )


# ------------------------------------------------------------------------- the wiring


def every_agent() -> Select[tuple[AgentRow]]:
    """Every stored agent. Filtered by audience afterwards, in Python, by the one predicate."""
    return select(AgentRow).order_by(AgentRow.id)


def one_agent(agent_id: str) -> Select[tuple[AgentRow]]:
    """One stored agent by its slug."""
    return select(AgentRow).where(AgentRow.id == agent_id)


def install_for(agent_id: str) -> Select[tuple[TemplateInstanceRow, TemplateVersionRow]]:
    """One agent's install and the version it is pinned to, joined on the pin's pair."""
    return (
        select(TemplateInstanceRow, TemplateVersionRow)
        .join(
            TemplateVersionRow,
            and_(
                TemplateVersionRow.template_id == TemplateInstanceRow.template_id,
                TemplateVersionRow.version == TemplateInstanceRow.template_version,
            ),
        )
        .where(TemplateInstanceRow.id == agent_id)
    )


def spend_for(agent_id: str, since: datetime) -> Select[tuple[SpendActualRow]]:
    """This agent's completed runs since an instant, bounded.

    Filtered by agent and by time in SQL, which is a different decision from the roster's:
    these rows are not a listing of things that exist, they are the input to one figure about
    one agent, and the basis narrows them again afterwards. The bound is a resource one, and
    a busy month over it loses cost off the older end of the window rather than showing a
    reader a number nobody could have derived.

    **The window here decides how many rows are read and never which are counted.**
    `brain.console.workspace.headline` applies the same window again over whatever arrives, so
    widening this one changes no figure on any screen: a mutation that reads ninety days
    instead of thirty survives its own test suite, and it survives it for the right reason.
    The two are kept equal anyway, because reading three months to report one is a cost paid
    on every agent page.
    """
    return (
        select(SpendActualRow)
        .where(and_(SpendActualRow.agent_id == agent_id, SpendActualRow.at >= since))
        .order_by(SpendActualRow.at.desc())
        .limit(MAX_HEADLINE_ROWS)
    )


def published_templates() -> Select[tuple[TemplateVersionRow]]:
    """Every published template version. Reduced to the highest version per template here
    rather than in SQL, for the reason `every_agent` gives about the audience: the reduction
    is a rule about what a gallery shows and it is written once, in Python, where a test can
    read it.
    """
    return select(TemplateVersionRow).order_by(
        TemplateVersionRow.template_id, TemplateVersionRow.version
    )


def _no_agent_here() -> Absent:
    """The one refusal this router makes about an agent.

    Named so that a missing row, a row outside the audience and a row that does not construct
    are one refusal rather than three that agree today. `brain.app.handle_brain_error` sends
    `Absent.public_message`, and the string below reaches a log.
    """
    return Absent("no agent is answerable for this caller")


def _no_templates_here() -> Absent:
    """The refusal the gallery makes, in the words a govern screen refuses in.

    It names the screen, which is the console's own menu and is identical in every install,
    and never a capability or a template. `brain.govern_routes._not_answerable` is the same
    sentence for the same reason, and the two being one sentence is what stops a reader
    telling this refusal from that one.
    """
    return Absent(f"the {TEMPLATE_SCREEN} screen is not answerable for this caller")


def _tool_registry(request: Request) -> ToolRegistry | None:
    """The registry `brain.app.lifespan` built, or None on a process with none.

    None rather than a failure, and the difference from `_require_session_factory` is what
    each absence costs: with no pool there is no agent to answer about at all, and with no
    registry there is a workspace whose connector strip is empty. Empty is also what a reader
    who reaches no source sees, so the two are one answer.
    """
    found = getattr(request.app.state, "tools", None)
    return found if isinstance(found, ToolRegistry) else None


def _require_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """The session factory, or a process-level fault identical for every caller.

    A `Failed` rather than an `Absent`, for `brain.routing_routes`' reason: an instance with
    no pool is broken rather than empty. It is also the same answer for every caller and
    every slug, so it says nothing about which agents exist.
    """
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


async def _visible_record(
    session: AsyncSession, agent_id: str, asked: Asking
) -> tuple[AgentRecord, datetime | None]:
    """The agent this caller's audience covers, with when its row was written, or the 404.

    The creation time is the row's and not the record's: `AgentRecord` has no such field, and the
    date is read here, after the audience has admitted the caller, like everything else.
    """
    row = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
    record = record_of(row) if row is not None else None
    if (
        row is None
        or record is None
        or agent_id not in visible_agent_ids((record,), viewer_of(asked))
    ):
        # One refusal for three causes. See `_no_agent_here`.
        log.info("agent not answerable", principal=asked.caller.principal.id)
        raise _no_agent_here()
    return record, row.created_at


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get("/agents", response_model=RosterPage, responses=COMMON_RESPONSES)
async def agents(request: Request, asked: Asked, listed: RosterQuery) -> RosterPage:
    """One page of the agents this caller's audience covers.

    No capability is asked for, and that is the argument of this module rather than an
    omission. See `AUDIENCE_DECIDES_WHO_SEES_AN_AGENT_AND_NOTHING_ELSE_DOES`.
    """
    plan = ROSTER.plan(listed, reader=asked.caller.principal.id)
    factory = _require_session_factory(request)
    async with factory() as session:
        rows = (await session.execute(every_agent())).scalars().all()
    records = [record for record in (record_of(row) for row in rows) if record is not None]
    return roster(
        records,
        viewer_of(asked),
        ceilings=permitted(screen(AGENT_SCREEN).read, asked.reach, asked.now),
        plan=plan,
    )


@router.get(
    "/agents/{agent_id}/workspace", response_model=WorkspaceView, responses=COMMON_RESPONSES
)
async def agent_workspace(request: Request, agent_id: str, asked: Asked) -> WorkspaceView:
    """One agent's workspace, or the answer an agent that does not exist gets.

    The audience is decided before the install is read, so nothing about an agent this
    caller may not see is fetched on their behalf, and the same is true of its costs: the
    accounting rows are loaded after the record has been admitted and never before.
    """
    factory = _require_session_factory(request)
    since, _ = window(HEADLINE_RANGE, asked.now)
    async with factory() as session:
        record, created_at = await _visible_record(session, agent_id, asked)
        pair = (await session.execute(install_for(agent_id))).one_or_none()
        costs = (await session.execute(spend_for(agent_id, since))).scalars().all()
    install = install_of(pair[0], pair[1], record) if pair is not None else None
    spend = [one for one in (actual_of(row) for row in costs) if one is not None]
    return workspace(
        record,
        install,
        asked,
        registry=_tool_registry(request),
        spend=spend,
        created_at=created_at,
    )


@router.get("/agent-templates", response_model=TemplateGallery, responses=COMMON_RESPONSES)
async def agent_templates(
    request: Request, asked: Asked, listed: TemplatesQuery
) -> TemplateGallery:
    """The templates an agent can be installed from: what ships, and what has been published.

    The screen's question first and the database second, which is `brain.govern_routes`'
    order and for its reason: a reader who may not open the screen has nothing fetched on
    their behalf, so the refusal cannot be timed.

    A published row that does not construct is absent for everybody, exactly as a malformed
    agent is: `manifest_of` walks the same paths `document` wrote, and a row that fails them
    is logged and left out rather than taking the gallery down for the whole company.
    """
    if not permitted(screen(TEMPLATE_SCREEN).read, asked.reach, asked.now):
        log.info("template gallery not answerable", principal=asked.caller.principal.id)
        raise _no_templates_here()
    plan = TEMPLATES.plan(listed, reader=asked.caller.principal.id)
    factory = _require_session_factory(request)
    async with factory() as session:
        rows = (await session.execute(published_templates())).scalars().all()
    published: list[TemplateManifest] = []
    for row in rows:
        try:
            published.append(manifest_of(row.document))
        except (KeyError, ValueError) as exc:
            log.warning(
                "published template does not construct",
                template=row.template_id,
                error=type(exc).__name__,
            )
    return gallery(published, plan)
