"""The Skills screen over HTTP: the library, the queue, and the three writes that make a skill run.

SCREEN 6 of `docs/screens.html` is the design of record: a library of skills with their source,
version, reviewer and state, a review pane with Approve and Reject, and what each skill asks for.
Until `0056` nothing stored an imported skill, so this router served only which agents were pinned
to which bytes and said on every answer that a skill could not be added, approved or assigned. It
now serves the library `brain.ops.skill_store` keeps, and three writes, each of them a decision
`brain.console.skill_library` makes and this module only orders.

**Adding a skill is an administrator's write, and it lands in the review queue.** `POST /skills`
takes a package, a pasted or uploaded `SKILL.md` or a zip holding one, asks
`brain.console.skill_library.may_add` before anything is read, parses it with `read_package`, which
runs nothing, and writes it undecided. Its ledger entry is `0056`'s trigger. See
`AN_IMPORT_IS_A_SUBMISSION_AND_NEVER_AN_APPROVAL`.

**A skill is also imported from a repository at a commit, or from an address (M12.2.2,
M12.2.3).** `POST /skills/imports` asks `may_add` before anything is read or fetched, checks the
source's shape, and only then fetches, through `brain.tools.fetch`, whose address rule and host
list are applied to every hop, over `brain.ops.skill_fetch.HttpsFetcher`, which connects to the
address the rule checked. The fetch runs off the event loop. What arrives is read by
`brain.console.skill_library.read_github` or `read_url` and lands undecided, exactly as a pasted
package does. See `AN_IMPORT_IS_A_SUBMISSION_AND_NEVER_AN_APPROVAL`.

**Approving is the review authority's, and an administrator may approve their own import
(M12.4.6).** `POST /skills/{digest}/review` asks `may_review`, then `decided`. The owner decided
D4 on 2026-09-18, so the importer is no longer refused; their decision is written with
`self_decided` set, which the table admits only for the importer's own row and the ledger records
as `self_approved` or `self_rejected`, the word the audit screen's search finds. See
`brain.console.skill_library.AN_ADMINISTRATOR_MAY_APPROVE_WHAT_THEY_IMPORTED_AND_THE_LEDGER_SAYS_SO`.

**An edit is saved as a new version that waits for review (M12.3.2).**
`POST /skills/{digest}/versions` takes the edited `SKILL.md`, asks `may_add`, and `edited` parses
it as an import is parsed.
The version it came from is untouched and stays in the library with its body readable, and every
agent keeps the digest it is pinned to. See
`brain.console.skill_library.AN_EDIT_IS_A_NEW_VERSION_AND_MOVES_NO_PIN`.

**The review pane shows the words that changed (M12.2.6).** A library row carries
`brain.tools.review.content_diff` against the version `compared_with` names, frontmatter fields
before and after and the body line by line, for a reader the body is disclosed to and nobody else.

**Categories are set on a skill's name and offered as filters drawn from what was shown
(M12.4.13).** `POST /skills/{digest}/categories` asks `may_add`; the page's `categories` are
`brain.console.skill_library.chips` over the library rows and the catalogue rows this reader was
given, so a category only a hidden skill carries is never offered. The catalogue filters on them
through `brain.listing`; the library, which is not paged, is filtered on the screen.

**What a skill is trusted to reach is on the answer, computed from the registry.** Every library
row carries the tools the `SKILL.md` names, the capability each registered tool requires and the
tools nothing registers, from `brain.console.skill_library.trusted_reach` over the registry
`brain.app` built. An assignment answers with what the skill reaches through that agent for the
person who assigned it, which is `reach_through` at `E_run(caller, agent)`. Nothing here intersects
anything. See `A_SKILL_REACHES_WHAT_ITS_TOOLS_REACH_AND_THE_SCREEN_SAYS_WHICH`.

**Assigning goes through `attach_skill` and writes only the agent's skills.**
`POST /skills/{digest}/assignments` asks for the skill authority in a scope admitting the agent and
for the agent in the caller's audience, and refuses both alike. `brain.console.skill_library.
assignment` then runs `register_skill`, whose `attach_skill` and `pin_skill` refuse a skill that is
not approved by a named person and unchanged since, and writes the `skills` path of the install
with the authority compared before and after. The store writes the install only if nobody changed
it since it was read. The agent's ceiling does not move, so what any caller reaches through it can
only be narrowed by what the skill names. See
`brain.console.skill_library.A_SKILL_NEVER_WIDENS_AN_AGENT_PAST_ITS_CALLER`.

**Every refusal to a caller who may not act is the screen's one sentence**, identical for a skill
or an agent that does not exist, which is `brain.govern_routes._not_answerable`'s construction. A
caller who may act and is refused is told why in words, which is `brain.prompt_routes`'
construction, because they hold the authority and are looking at the thing: the importer reviewing
their own skill, a package that does not parse, an agent changed since they opened it.

**The catalogue of pins is still assembled agent by agent, from the agents this reader may already
see.** That is `brain.console.govern_estate.
AN_ESTATE_LISTING_IS_ASSEMBLED_FROM_WHAT_THE_READER_CAN_ALREADY_SEE`, and it is now also where the
list of agents a skill can be assigned to comes from, so a reader is never offered an agent the
roster would not list.

**Whether the screen opens is `brain.console.reads.permitted` and never a bare capability check**,
and the question is asked before a session is reached for, so a caller with no grant cannot tell a
deployment with a database from one without.

Rejected: a route answering one skill by name for reading. A deep link is resolved against the page,
for `brain.govern_routes.A_DEEP_LINK_RESOLVED_AGAINST_THE_PAGE_CANNOT_BE_AN_ORACLE`'s reason. The
writes take a digest in the path, and each asks its authority before the digest is looked up, so a
caller who may not act cannot use one to ask what exists.

Rejected: an assignment that takes a name and a digest from the browser. The digest names a stored
skill and the store's copy is what is pinned, so a typed digest that matches nothing pins nothing,
and one that matches pins the bytes a named second person approved. That was
`AN_ASSIGNMENT_BUILT_ON_A_DIGEST_SOMEBODY_TYPED_IS_AN_APPROVAL_THEY_GRANTED_THEMSELVES` before a
library existed, and it is answered by the library rather than argued away.

**What runs against a database.** `tests/unit/test_skill_store.py` runs the statements, the
triggers and the checks against a scratch PostgreSQL, which the development machine has had since
2026-09-28; without one those tests skip.

**The skills the reader's agents run page, search, filter and order through `brain.listing`**,
over the rows `catalogue` built from the agents this reader's audience covers, with the agent load
bounded by `MAX_AGENTS_CONSIDERED` whatever was asked.

**The library is searched and filtered on the server too (W2.8, M27.11.8).** `GET /skills/library`
is one row per version, the library as this reader may list it, with its review state, whether it
is retired, its categories and how many of the agents this reader may see run it, through
`LIBRARY_LISTING`. A reader the library is not listed to is answered an empty page, the same page
an empty library gives. It takes no path parameter, so the rejected read by name stays rejected.

**A version is retired and reinstated, and a skill detached, as rows (M27.15.55, M27.15.56).**
`POST /skills/{digest}/retirement` and `/reinstatement` ask for the skill authority over
everything, as adding does, and write one `agent.skill_retirement` row each; an assignment of a
retired version is refused in words. A retirement answers with the agents still running the
version, among the agents the reader may see and never counted beyond them, for somebody to
detach: see `brain.console.skill_library.A_RETIRED_VERSION_IS_KEPT_AND_ONLY_REFUSED_TO_NEW_AGENTS`.
A retirement racing an assignment can leave the version on one more agent; that is the state a
retirement already leaves, a retired version still held, and the page lists it for detaching.
`POST /skills/{digest}/detachments` is the assignment route's mirror, asked in the same order of
the same authority, and writes the agent's skills without the skill and a row naming the
assignment it ended, under the install lock. Every pin on the page carries the agent's name and,
when an assignment still in force put it there, when and by whom, from
`brain.console.skill_library.current_assignments`.

**People are named, and their identifiers kept for the Advanced section.** Who added a version,
who decided it, who retired it and who assigned it are sent as display names beside the ids the
page used to print, read from the directory for exactly those people.

**A package carries scripts and example tasks, a version with examples is rehearsed before it is
approved, and an approved version is exported (M12.4.11, M12.3.4, M12.3.1).** Adding a zip
reads its scripts and its `examples.json` through `read_package`, and the review pane shows each
script's sha256 and, while the version waits for a decision, its text, so what is approved is
code somebody could read. `POST /skills/{digest}/rehearsals` records whether each example behaved
as expected, asked of whoever may add or review, and `POST /skills/{digest}/review` passes the
newest rehearsal of those bytes to `decided`, which refuses to approve a version with examples
until every one behaved; see `brain.console.skill_library.
A_VERSION_WITH_EXAMPLES_IS_APPROVED_ONLY_AFTER_THEY_ARE_REHEARSED`. `POST /skills/{digest}/exports`
answers the approved version as a zip another install adds through `POST /skills`, where it lands
undecided. **An export is a POST and writes nothing**: it is an act one person takes on one
version, asked of the skill authority before the digest is looked up as every write here is, and
the rejected read by name stays rejected, because a GET with a digest in its path is the oracle
the writes are built not to be. Rejected: recording each export on the ledger, which would need a
table for a fact that changes nothing anybody holds, as the routing export does not.

Task ids: M42.6.4, M27.8.6, M12.2.2, M12.2.3, M12.2.5, M12.2.6, M12.3.2, M12.4.6, M12.4.13
Task ids: M27.11.8, M27.15.55, M27.15.56, M27.16.1, M12.4.11, M12.3.4, M12.3.1
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final, Literal, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import (
    _tool_registry,
    every_agent,
    manifest_of,
    record_of,
    steward_names,
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
from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder
from brain.console.agent_tabs import AgentTabError, Review, review_state
from brain.console.govern import Placed
from brain.console.govern_estate import skill_queue
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.skill_library import (
    MAX_CATEGORIES,
    SKILL_AUTHORITY,
    Assignment,
    AssignmentRecord,
    Detachment,
    DetachmentRecord,
    LibrarySkill,
    Package,
    Rehearsal,
    Retirement,
    SkillLibraryError,
    SkillReach,
    ToolReach,
    added,
    another_spelling,
    assignment,
    awaits_rehearsal,
    categories_from,
    chips,
    compared_with,
    current_assignments,
    decided,
    detachment,
    edited,
    exported,
    github_source,
    may_add,
    may_assign,
    may_export,
    may_read_library,
    may_rehearse,
    may_review,
    queue_entries,
    reach_through,
    read_github,
    read_package,
    read_url,
    rehearsal,
    retired_digests,
    retiring,
    trusted_reach,
    url_source_problem,
)
from brain.console.skill_library import holding as agents_holding
from brain.console.workspace import WorkspaceError
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.listing import Column, ListAsked, Listing
from brain.ops.skill_fetch import HttpsFetcher, SystemResolver
from brain.ops.skill_store import MAX_LIBRARY, StoredSkills
from brain.prompt_routes import agent_scope_row, every_agent_with_install, installed
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tools.fetch import Fetcher, Resolver, fetch_skill_source, fetch_skill_url
from brain.tools.registry import ToolRegistry
from brain.tools.review import QueueEntry, SkillDiff, content_diff
from brain.tools.skills import DIGEST_RE, MAX_EXAMPLES, SkillError, SkillPin, markdown_of

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons
#: Why adding a skill is a submission.
AN_IMPORT_IS_A_SUBMISSION_AND_NEVER_AN_APPROVAL: Final = (
    "Adding a skill writes it in the imported state, with no reviewer and no approved digest, "
    "and there is no field on the request that could carry either. It is listed in the review "
    "queue from that moment, it cannot be attached to any agent, and brain.tools.skills.body_of "
    "refuses its instructions to an agent until somebody other than the person who added it has "
    "approved the exact bytes that were added."
)

#: Why reach is listed per tool, and why an unregistered tool is named.
A_SKILL_REACHES_WHAT_ITS_TOOLS_REACH_AND_THE_SCREEN_SAYS_WHICH: Final = (
    "A skill declares no reach of its own, so what it is trusted to reach is the union of what "
    "the registered tools it names require, read off the registry this process built. A tool it "
    "names that nothing registers reaches nothing and is listed by name, so a reviewer sees a "
    "misconfigured skill rather than an empty list that reads as a harmless one. Through an agent "
    "it is narrower again: the tools the catalogue admits at E_run(caller, agent)."
)

#: Why a difference between two pins is a statement about this page.
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
#: The most agents one catalogue answer is assembled from, whatever page, search, filter or order
#: was asked for. A resource bound and not a permission one: it is applied to the load, the
#: audience filter runs over what came back, and `truncated` says the load came back full without
#: saying what was in the rest of it.
MAX_AGENTS_CONSIDERED: Final = 500

#: The longest package a request may carry, in characters, which is the largest package in base64
#: with room for the encoding. `brain.console.skill_library.MAX_PACKAGE_BYTES` refuses the bytes.
MAX_PACKAGE_CHARS: Final = 360_000

#: A digest in a path, as `brain.tools.skills.DIGEST_RE` spells one.
DIGEST_PATTERN: Final = DIGEST_RE.pattern


# ------------------------------------------------------------------- the shapes
class SkillPinView(BaseModel):
    """One agent, and the bytes of this skill it is configured to run.

    The agent's name for the page and its id for the Advanced section and the writes; when an
    assignment still in force put the skill there, when and by whom (M27.15.55).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    digest: str
    display_name: str | None = None
    assigned_at: datetime | None = None
    #: The display name of whoever assigned it, when the directory holds one.
    assigned_by: str | None = None


class SkillRow(BaseModel):
    """One skill the reader's agents run, and which of them run it.

    `versions_differ` is the one derived field and it is a fact about this row; see
    `A_DIFFERENCE_BETWEEN_PINS_IS_ABOUT_THIS_PAGE_AND_NEVER_THE_ESTATE`. Review state lives on the
    library row for the bytes, never here: a pin is a configuration, and a state read off one
    would say a skill was approved because an agent was configured with it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    pinned_by: tuple[SkillPinView, ...]
    #: The agents on this row are not all pinned to the same bytes of this skill.
    versions_differ: bool
    #: The categories set on this name. A filing label, never a review word (M12.4.13).
    categories: tuple[str, ...] = ()


class QueueEntryView(BaseModel):
    """One skill waiting for a reviewer, as the queue lists it.

    The name, the bytes, how long it has waited and which fields changed, which is what
    `brain.tools.review.QueueEntry` says a reviewer needs to decide. There is no body and no
    reviewer: the body is on the library row, where the decision is made, for a reader who may
    make it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    digest: str
    waiting_since: datetime
    #: Field names, never values, and empty for a first submission. `diff_skills`' own answer.
    changed: tuple[str, ...]
    stale: bool


class SkillQueueView(BaseModel):
    """What is waiting to be read, and the summary of exactly that.

    See `brain.console.govern_estate.A_SUMMARY_OVER_A_WIDER_LIST_THAN_THE_LISTING_IS_A_SUBTRACTION`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[QueueEntryView, ...]
    waiting: int
    edits: int
    stale: int


class FieldChangeView(BaseModel):
    """One frontmatter field an edit changed, before and after. `brain.tools.review.FieldChange`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    before: str
    after: str


class DiffLineView(BaseModel):
    """One line of the body: kept, removed or added. `brain.tools.review.DiffLine`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    change: Literal["kept", "removed", "added"]
    text: str


class SkillDiffView(BaseModel):
    """The words that changed against the version named beside it (M12.2.6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The version this one is compared with: its digest and the number its author gave it.
    against_digest: str
    against_version: str
    fields: tuple[FieldChangeView, ...]
    body: tuple[DiffLineView, ...]


class ToolReachView(BaseModel):
    """One tool a skill names, and what the registered tool requires, or null when none is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    capability: str | None


class ScriptView(BaseModel):
    """One script a version carries: its path, the sha256 of the bytes it was added as, and, while
    the version waits for a decision, its text for the reviewer (M12.4.11).

    `text` is null once the version is decided, for a reader the body is not disclosed to, and for
    bytes that are not UTF-8 text, which `is_text` says, so a reviewer is never shown nothing and
    left to read it as an empty script.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    sha256: str
    text: str | None = None
    is_text: bool = True


class ExampleView(BaseModel):
    """One example task a version carries and the behaviour expected of it (M12.3.4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: str
    expected: str


class SkillRehearsalView(BaseModel):
    """The newest rehearsal of a version's examples: each verdict, who and when (M12.3.4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    behaved: tuple[bool, ...]
    passed: bool
    rehearsed_at: datetime
    rehearsed_by: str
    #: The display name of whoever rehearsed it, when the directory holds one.
    rehearsed_by_name: str | None = None


class LibrarySkillView(BaseModel):
    """One skill in the library: SCREEN 6's library row and its review pane in one shape.

    `review` is `brain.console.agent_tabs.review_state`, so a row whose bytes moved after approval
    reads `changed` rather than `approved`. `body` is present only for a reader who may add or
    review skills, because it is what a reviewer reads and a listing is not a place to hand
    instructions to anybody else. `reviewable` and `assignable` decide whether a button is drawn
    and nothing more: each write asks every question again.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    digest: str
    name: str
    version: str
    description: str
    source: str
    source_location: str
    submitted_by: str
    submitted_at: datetime
    review: str
    reviewer: str | None
    reviewed_at: datetime | None
    #: See `A_SKILL_REACHES_WHAT_ITS_TOOLS_REACH_AND_THE_SCREEN_SAYS_WHICH`.
    tools: tuple[ToolReachView, ...]
    capabilities: tuple[str, ...]
    unregistered_tools: tuple[str, ...]
    body: str | None
    reviewable: bool
    assignable: bool
    #: A repository source's commit and folder. Null for any other source (M12.2.2).
    source_commit: str | None = None
    source_path: str | None = None
    #: The version this one was edited from, when it is an edit (M12.3.2).
    edited_from: str | None = None
    #: Decided by the person who added it, which the ledger records as such (M12.4.6).
    self_decided: bool = False
    #: The categories set on this skill's name (M12.4.13).
    categories: tuple[str, ...] = ()
    #: The words that changed, for a reader the body is disclosed to, when there is a version to
    #: compare with (M12.2.6).
    diff: SkillDiffView | None = None
    #: The `SKILL.md` an edit starts from, for a reader who may edit, and whether one may be made.
    markdown: str | None = None
    editable: bool = False
    #: Retired: no agent may newly be assigned it, and every agent running it keeps it
    #: (M27.15.56). When, and the display name of who retired it.
    retired: bool = False
    retired_at: datetime | None = None
    retired_by: str | None = None
    #: This reader may retire or reinstate it. Decides whether a button is drawn and nothing more.
    retirable: bool = False
    #: The display names of whoever added it and whoever decided it, when the directory holds one.
    submitted_by_name: str | None = None
    reviewer_name: str | None = None
    #: The scripts this version carries, each with the sha256 its digest covers (M12.4.11).
    scripts: tuple[ScriptView, ...] = ()
    #: The example tasks it carries, for a reader the body is disclosed to (M12.3.4).
    examples: tuple[ExampleView, ...] = ()
    #: The newest rehearsal of these bytes, for a reader the body is disclosed to.
    rehearsal: SkillRehearsalView | None = None
    #: It carries examples and may not be approved until a rehearsal in which every one behaved.
    awaits_rehearsal: bool = False
    #: This reader may record a rehearsal of it now. Decides whether a form is drawn and nothing
    #: more.
    rehearsable: bool = False
    #: This reader may export it now: it is approved, unchanged, and they hold the authority.
    exportable: bool = False


class AgentChoiceView(BaseModel):
    """An agent this reader may assign a skill to: in their audience and in their authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str


class SkillsPage(Page[SkillRow]):
    """The skills the reader's agents run, the library, the queue, and what this reader may do.

    `total` is inherited and never populated, for the reason every listing in this application
    gives. `may_add` and `agents` decide what the page offers and nothing else.
    """

    #: The agent load came back full, so there are more agents than this answer was assembled from.
    truncated: bool = False
    queue: SkillQueueView
    library: tuple[LibrarySkillView, ...] = ()
    #: The library load came back full. Never how many more.
    library_truncated: bool = False
    #: The agents this reader may assign an approved skill to.
    agents: tuple[AgentChoiceView, ...] = ()
    may_add: bool = False
    #: No tool registry was built on this process, so no tool a skill names can be resolved and
    #: every tool is listed as unregistered.
    registry_is_absent: bool = False
    #: The categories to offer as filter chips: those of the skills on this page, and no other.
    categories: tuple[str, ...] = ()


#: One category as typed. Folded and held to the category grammar by `categories_from`.
CategoryTyped = Annotated[str, Field(max_length=60)]

#: The most categories a request may carry, typed, before folding and deduplication.
MAX_CATEGORIES_TYPED: Final = 2 * MAX_CATEGORIES


class SkillPackageAsked(BaseModel):
    """A package: its file name, and its bytes as text or as base64. Nothing that could say who."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file_name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_PACKAGE_CHARS)
    encoding: Literal["text", "base64"]
    categories: tuple[CategoryTyped, ...] = Field(default=(), max_length=MAX_CATEGORIES_TYPED)


class SkillImportAsked(BaseModel):
    """Where to import a skill from: a repository at a commit, or an address (M12.2.2, M12.2.3).

    One shape for both, with the fields that do not apply left empty, because the console sends
    one form. Nothing here could name the importer, an approval or a host to connect to other than
    the address itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["github", "url"]
    #: `owner/repo`.
    repository: str = Field(default="", max_length=140)
    #: The full 40-character commit sha.
    commit: str = Field(default="", max_length=64)
    #: The folder holding the `SKILL.md`, or empty for the repository's top folder.
    path: str = Field(default="", max_length=200)
    #: An https address answering with a `SKILL.md` or a zip holding one.
    url: str = Field(default="", max_length=2000)
    categories: tuple[CategoryTyped, ...] = Field(default=(), max_length=MAX_CATEGORIES_TYPED)


class SkillEditAsked(BaseModel):
    """The edited `SKILL.md`. The skill it is a version of is the one in the path (M12.3.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_PACKAGE_CHARS)


class CategoriesAsked(BaseModel):
    """The categories a skill's name carries from now on. Empty clears them (M12.4.13)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    categories: tuple[CategoryTyped, ...] = Field(default=(), max_length=MAX_CATEGORIES_TYPED)


class CategoriesView(BaseModel):
    """The categories a skill's name now carries, folded as they were stored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    categories: tuple[str, ...]


class ReviewAsked(BaseModel):
    """The decision. Nothing that could name the reviewer, who is the caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Literal["approve", "reject"]


class RehearsalAsked(BaseModel):
    """Whether each example behaved as expected, in the order the version carries them (M12.3.4).

    Nothing that could name the rehearser, who is the caller, or the version, which is the one in
    the path.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    behaved: tuple[bool, ...] = Field(min_length=1, max_length=MAX_EXAMPLES)


class SkillPackageView(BaseModel):
    """An approved version as a package another install adds, and what its manifest names
    (M12.3.1). `content` is the zip in base64, as `POST /skills` takes one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file_name: str
    content: str
    encoding: Literal["base64"] = "base64"
    name: str
    version: str
    digest: str


class AssignAsked(BaseModel):
    """Which agent. The skill is the one in the path, as the library holds it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str = Field(min_length=1, max_length=128)


class AssignedView(BaseModel):
    """What was assigned, what it replaced, and what it reaches through this agent for you."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    skill_name: str
    digest: str
    replaced_digest: str | None
    #: `brain.console.skill_library.reach_through`: tool names, and never more than the caller
    #: reaches through this agent without the skill.
    reach: tuple[str, ...]
    effective_hash: str


class DetachedView(BaseModel):
    """What was detached, from which agent, and the install it left (M27.15.55)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    skill_name: str
    digest: str
    effective_hash: str


class RetirementView(BaseModel):
    """A version retired or reinstated, and the agents still running it (M27.15.56).

    `holding` is the agents this reader may see that run these bytes, for detaching one at a time.
    Nothing is said about agents the reader may not see, not even whether there are any.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    digest: str
    name: str
    version: str
    retired: bool
    holding: tuple[AgentChoiceView, ...] = ()


class SkillVersionRowView(BaseModel):
    """One version in the library, as the searchable list draws it (M27.11.8).

    `agents_running` counts the agents this reader may see that run these bytes, which is a count
    over rows the reader could open and never over the estate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    digest: str
    name: str
    version: str
    description: str
    review: str
    retired: bool
    categories: tuple[str, ...]
    agents_running: int
    source: str
    submitted_at: datetime


class SkillLibraryPage(Page[SkillVersionRowView]):
    """The library, one row per version, with the queue's summary and what this reader may do."""

    queue: SkillQueueView
    #: The library load came back full. Never how many more.
    library_truncated: bool = False
    #: The agent load came back full, so `agents_running` is over the agents that were loaded.
    truncated: bool = False
    may_add: bool = False
    #: The category chips: those of the versions this reader may list, and no other.
    categories: tuple[str, ...] = ()


# ------------------------------------------------------------------------ the stores
@runtime_checkable
class SkillLibrary(Protocol):
    """What these routes need of the library. `brain.ops.skill_store.StoredSkills` implements it."""

    async def library(self, limit: int = MAX_LIBRARY) -> tuple[LibrarySkill, ...]: ...

    async def skill(self, digest: str) -> LibrarySkill | None: ...

    async def add(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool: ...

    async def decide(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool: ...

    async def assign(
        self, made: Assignment, *, expected_hash: str, ent_hash: str, trace_id: str
    ) -> bool: ...

    async def categories(self, names: Sequence[str]) -> Mapping[str, tuple[str, ...]]: ...

    async def categorise(
        self, name: str, categories: Sequence[str], *, by: str, ent_hash: str, trace_id: str
    ) -> None: ...

    async def retirements(self, digests: Sequence[str]) -> Mapping[str, Retirement]: ...

    async def retire(
        self, digest: str, *, retired: bool, by: str, ent_hash: str, trace_id: str
    ) -> None: ...

    async def detach(
        self, made: Detachment, *, expected_hash: str, ent_hash: str, trace_id: str
    ) -> bool: ...

    async def assignment_history(
        self, names: Sequence[str]
    ) -> tuple[tuple[AssignmentRecord, ...], tuple[DetachmentRecord, ...]]: ...


@runtime_checkable
class SkillContents(Protocol):
    """A version's script bytes and the rehearsals of its examples (M12.4.11, M12.3.4).

    A protocol of its own rather than three more methods on `SkillLibrary`, so a screen that reads
    the library and never a script or a rehearsal keeps a stand-in that does not pretend to hold
    them. `brain.ops.skill_store.StoredSkills` implements both.
    """

    async def scripts(self, digest: str) -> Mapping[str, bytes]: ...

    async def rehearse(self, done: Rehearsal, *, ent_hash: str, trace_id: str) -> None: ...

    async def rehearsals(self, digests: Sequence[str]) -> Mapping[str, Rehearsal]: ...


@dataclass(frozen=True)
class FoundAgent:
    """One stored agent, its install when it has one that constructs, and the install's hash."""

    record: AgentRecord
    install: tuple[SignedManifest, TemplateInstance] | None
    effective_hash: str | None


@runtime_checkable
class AgentInstalls(Protocol):
    """One agent and its install, read the way `brain.prompt_routes` reads one."""

    async def agent(self, agent_id: str) -> FoundAgent | None: ...


class StoredAgentInstalls:
    """`AgentInstalls` over `agent.agent` and its install rows."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def agent(self, agent_id: str) -> FoundAgent | None:
        async with self._sessions() as session:
            found = (
                await session.execute(every_agent_with_install().where(AgentRow.id == agent_id))
            ).one_or_none()
        if found is None:
            return None
        agent_row, instance_row, version_row = found
        record = record_of(agent_row)
        if record is None:
            return None
        return FoundAgent(
            record=record,
            install=installed(instance_row, version_row),
            effective_hash=None if instance_row is None else instance_row.effective_hash,
        )


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


def library_of(request: Request) -> SkillLibrary:
    """`app.state.skill_library` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "skill_library", None)
    if isinstance(found, SkillLibrary):
        return found
    return StoredSkills(_require_sessions(request))


def contents_of(request: Request) -> SkillContents:
    """`app.state.skill_library` when it holds scripts and rehearsals too, and the database else."""
    found = getattr(request.app.state, "skill_library", None)
    if isinstance(found, SkillContents):
        return found
    return StoredSkills(_require_sessions(request))


def fetcher_of(request: Request) -> Fetcher:
    """`app.state.skill_fetcher` when something put one there, and the pinned transport else."""
    found = getattr(request.app.state, "skill_fetcher", None)
    if isinstance(found, Fetcher):
        return found
    return HttpsFetcher()


def resolver_of(request: Request) -> Resolver:
    """`app.state.skill_resolver` when something put one there, and the system's otherwise."""
    found = getattr(request.app.state, "skill_resolver", None)
    if isinstance(found, Resolver):
        return found
    return SystemResolver()


def agent_installs_of(request: Request) -> AgentInstalls:
    """`app.state.agent_installs` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "agent_installs", None)
    if isinstance(found, AgentInstalls):
        return found
    return StoredAgentInstalls(_require_sessions(request))


# ---------------------------------------------------------------- the statements
def installs_of(agent_ids: Sequence[str]) -> Select[tuple[TemplateInstanceRow, TemplateVersionRow]]:
    """Every named agent's install and the version it is pinned to, joined on the pin's pair.

    Joined on both halves of the pin, template and version, because `agent.template_version`'s
    key is the pair. Ordered by instance id, so two readings of an unchanged install are one page.
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
    that module's `A_ROSTER_IS_FILTERED_BEFORE_IT_IS_BOUNDED` with the bound moved to the load.
    """
    return every_agent().limit(limit)


# ------------------------------------------------------------------ rows to pins
def pins_of(
    instance_row: TemplateInstanceRow, version_row: TemplateVersionRow, record: AgentRecord
) -> tuple[SkillPin, ...]:
    """The skills one agent is pinned to, or nothing when its install does not construct.

    `brain.agent_routes.install_of`'s refusal, for its reason: `materialise` checks the pin, the
    overlay and the seal, and none of those failures may become a status. The pins are
    `materialise`'s rather than the document's `skills` key, because an overlay may set that path,
    and assigning a skill from this screen is exactly an overlay setting it.
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
def catalogue(
    pins: Iterable[SkillPin],
    categories: Mapping[str, Sequence[str]] | None = None,
    *,
    agent_names: Mapping[str, str] | None = None,
    assigned: Mapping[tuple[str, str], AssignmentRecord] | None = None,
    people: Mapping[str, str] | None = None,
) -> tuple[SkillRow, ...]:
    """Every skill these pins name, in name order, with the agents pinned to each.

    Grouped by name rather than by name and digest, because a skill whose agents run different
    bytes is one skill with a disagreement on it. See
    `A_DIFFERENCE_BETWEEN_PINS_IS_ABOUT_THIS_PAGE_AND_NEVER_THE_ESTATE`. Each row carries the
    categories set on its name, which is what the listing filters on (M12.4.13). A pin carries its
    agent's name, and the assignment in force for that agent and skill when it names these bytes.
    """
    filed = categories or {}
    held: dict[str, list[SkillPin]] = {}
    for pin in pins:
        held.setdefault(pin.skill_name, []).append(pin)
    return tuple(
        SkillRow(
            name=name,
            pinned_by=tuple(
                pin_view(pin, agent_names or {}, assigned or {}, people or {})
                for pin in sorted(held[name], key=lambda one: (one.agent_id, one.digest))
            ),
            versions_differ=len({pin.digest for pin in held[name]}) > 1,
            categories=tuple(filed.get(name, ())),
        )
        for name in sorted(held)
    )


def pin_view(
    pin: SkillPin,
    agent_names: Mapping[str, str],
    assigned: Mapping[tuple[str, str], AssignmentRecord],
    people: Mapping[str, str],
) -> SkillPinView:
    """One pin, with its agent's name and the assignment in force that put these bytes there."""
    record = assigned.get((pin.agent_id, pin.skill_name))
    if record is not None and record.digest != pin.digest:
        # An assignment in force of other bytes than the install runs: the install is the fact,
        # so the pin says nothing about when these bytes arrived rather than the wrong thing.
        record = None
    return SkillPinView(
        agent_id=pin.agent_id,
        digest=pin.digest,
        display_name=agent_names.get(pin.agent_id),
        assigned_at=None if record is None else record.at,
        assigned_by=None if record is None else people.get(record.assigned_by),
    )


def in_force(
    history: tuple[tuple[AssignmentRecord, ...], tuple[DetachmentRecord, ...]],
) -> dict[tuple[str, str], AssignmentRecord]:
    """The assignments in force, by agent and skill. `current_assignments` decides which."""
    assignments, detachments = history
    return {
        (one.agent_id, one.skill_name): one for one in current_assignments(assignments, detachments)
    }


def submitted(library: Sequence[LibrarySkill], now: datetime) -> tuple[Placed[QueueEntry], ...]:
    """Every skill in the library waiting for a reviewer, placed where the queue narrows it.

    It was empty until `0056`, because nothing stored a submission, and it was a function so that
    the day a store existed this would be the one line that changed. It is:
    `brain.console.skill_library.queue_entries` over what the store holds.
    """
    return queue_entries(library, now)


def entry_view(entry: QueueEntry, now: datetime) -> QueueEntryView:
    """One queue entry, copied field by field, with staleness asked of the entry."""
    return QueueEntryView(
        name=entry.skill.skill.name,
        digest=entry.skill.skill.digest(),
        waiting_since=entry.waiting_since,
        changed=tuple(entry.changed),
        stale=entry.is_stale(now),
    )


def queue_view(
    entries: Sequence[Placed[QueueEntry]], reach: EntitlementSet, now: datetime
) -> SkillQueueView:
    """The queue this reader may see, and the summary of exactly that list.

    `brain.console.govern_estate.skill_queue` is the whole decision and it is not restated here.
    """
    narrowed = skill_queue(entries, reach, now)
    return SkillQueueView(
        entries=tuple(entry_view(one, now) for one in narrowed.entries),
        waiting=narrowed.summary.waiting,
        edits=narrowed.summary.edits,
        stale=narrowed.summary.stale,
    )


def diff_view(diff: SkillDiff, against: LibrarySkill) -> SkillDiffView:
    """`brain.tools.review.content_diff`'s answer, copied field by field."""
    return SkillDiffView(
        against_digest=against.digest,
        against_version=against.imported.skill.version,
        fields=tuple(
            FieldChangeView(field=one.field, before=one.before, after=one.after)
            for one in diff.fields
        ),
        body=tuple(DiffLineView(change=line.change.value, text=line.text) for line in diff.body),
    )


def _markdown(one: LibrarySkill) -> str | None:
    """The text an edit of this version starts from, or None when it does not read back."""
    try:
        return markdown_of(one.imported.skill)
    except SkillError:
        return None


def library_view(
    one: LibrarySkill,
    reach: SkillReach,
    *,
    discloses_body: bool,
    reviews: bool,
    assigns: bool,
    edits: bool = False,
    categories: Sequence[str] = (),
    against: LibrarySkill | None = None,
    retirement: Retirement | None = None,
    people: Mapping[str, str] | None = None,
    rehearsal: Rehearsal | None = None,
    script_bytes: Mapping[str, bytes] | None = None,
    rehearses: bool = False,
    exports: bool = False,
) -> LibrarySkillView:
    """One library row, with the reach the registry gives it and what this reader is offered.

    `reviewable` no longer asks who added the skill, for D4 (M12.4.6). The diff and the text an
    edit starts from are words of the skill, so each goes only where the body goes. A retired
    version is never `assignable`, whatever else holds (M27.15.56).

    The examples, the newest rehearsal and a waiting version's script text are words of the skill
    too and go where the body goes (M12.3.4, M12.4.11); every script's path and sha256 go to any
    reader of the row, as the tools it names do. `script_bytes` is the waiting version's scripts as
    the store read them, and a script's text is drawn only when those bytes are the ones its digest
    covers, so the reviewer reads what they would approve.
    """
    imported = one.imported
    state = review_state(imported)
    retired = retirement is not None and retirement.retired
    named = people or {}
    skill = imported.skill
    shown_bytes = script_bytes if discloses_body and state is Review.PENDING else None
    newest = rehearsal if rehearsal is not None and rehearsal.digest == one.digest else None
    return LibrarySkillView(
        digest=one.digest,
        name=imported.skill.name,
        version=imported.skill.version,
        description=imported.skill.description,
        source=imported.source.kind.value,
        source_location=imported.source.location,
        submitted_by=one.submitted_by,
        submitted_at=one.submitted_at,
        review=state.value,
        reviewer=imported.reviewer or None,
        reviewed_at=imported.reviewed_at,
        tools=tuple(
            ToolReachView(name=tool.name, capability=tool.capability) for tool in reach.tools
        ),
        capabilities=reach.capabilities,
        unregistered_tools=reach.unknown,
        body=imported.skill.body if discloses_body else None,
        reviewable=reviews and state is Review.PENDING and not one.moved,
        assignable=assigns and state is Review.APPROVED and not retired,
        source_commit=imported.source.commit or None,
        source_path=imported.source.path or None,
        edited_from=one.edited_from,
        self_decided=one.self_decided,
        categories=tuple(categories),
        diff=(
            diff_view(content_diff(against.imported.skill, imported.skill), against)
            if discloses_body and against is not None
            else None
        ),
        markdown=_markdown(one) if edits and discloses_body and not one.moved else None,
        editable=edits and not one.moved,
        retired=retired,
        retired_at=retirement.at if retired and retirement is not None else None,
        retired_by=named.get(retirement.set_by) if retired and retirement is not None else None,
        retirable=edits,
        submitted_by_name=named.get(one.submitted_by),
        reviewer_name=named.get(imported.reviewer) if imported.reviewer else None,
        scripts=tuple(script_view(one.path, one.sha256, shown_bytes) for one in skill.script_files),
        examples=(
            tuple(ExampleView(task=item.task, expected=item.expected) for item in skill.examples)
            if discloses_body
            else ()
        ),
        rehearsal=rehearsal_view(newest, named) if discloses_body and newest is not None else None,
        awaits_rehearsal=state is Review.PENDING and awaits_rehearsal(one, newest),
        rehearsable=rehearses and state is Review.PENDING and bool(skill.examples),
        exportable=exports and state is Review.APPROVED,
    )


def script_view(path: str, sha256: str, shown: Mapping[str, bytes] | None) -> ScriptView:
    """One script as the row draws it: its text only when the bytes shown are the approved ones."""
    raw = None if shown is None else shown.get(path)
    if raw is None or hashlib.sha256(raw).hexdigest() != sha256:
        return ScriptView(path=path, sha256=sha256)
    try:
        return ScriptView(path=path, sha256=sha256, text=raw.decode("utf-8"))
    except UnicodeDecodeError:
        return ScriptView(path=path, sha256=sha256, is_text=False)


def rehearsal_view(done: Rehearsal, people: Mapping[str, str]) -> SkillRehearsalView:
    """One rehearsal, copied field by field, with the rehearser named when the directory can."""
    return SkillRehearsalView(
        behaved=done.behaved,
        passed=done.passed,
        rehearsed_at=done.at,
        rehearsed_by=done.rehearsed_by,
        rehearsed_by_name=people.get(done.rehearsed_by),
    )


def _unresolved(skill_tools: Sequence[str]) -> SkillReach:
    """What a skill reaches on a process with no registry: every tool it names, unresolved."""
    return SkillReach(
        tools=tuple(ToolReach(name=name, capability=None) for name in skill_tools),
        capabilities=(),
        unknown=tuple(skill_tools),
    )


# ------------------------------------------------------------------- the wiring
def _not_answerable() -> Absent:
    """The one refusal this router makes to a caller who may not act.

    Names the screen and never the row, the capability or the caller, which is
    `brain.govern_routes._not_answerable`'s construction.
    """
    return Absent(f"the {SKILLS_SCREEN} screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller who may act, naming what to fix. `brain.prompt_routes`' shape."""
    return Absent(reason, public_message=reason)


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.session_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def visible_records(records: Sequence[AgentRecord], asked: Asking) -> tuple[AgentRecord, ...]:
    """The agents this caller's audience covers, in id order.

    `brain.agents.model.visible_agent_ids` is the answer and `brain.agent_routes.viewer_of`
    builds the viewer, so who may see an agent is decided once, by the module that owns it.
    """
    visible = visible_agent_ids(records, viewer_of(asked))
    return tuple(sorted((one for one in records if one.agent_id in visible), key=_by_id))


def _by_id(record: AgentRecord) -> str:
    return record.agent_id


#: What the Skills screen may search, filter and order the skills the reader's agents run by.
CATALOGUE_LISTING: Final[Listing[SkillRow]] = Listing(
    name="skills",
    columns=(
        Column("name", lambda row: row.name, search=True, filter=True, sort=True),
        Column(
            "agents",
            lambda row: tuple(one.agent_id for one in row.pinned_by),
            search=True,
            filter=True,
        ),
        Column("versions_differ", lambda row: row.versions_differ, filter=True),
        Column("categories", lambda row: row.categories, filter=True),
    ),
    key=lambda row: row.name,
    order="name",
)
CatalogueQuery = Annotated[ListAsked, Depends(CATALOGUE_LISTING.query())]


router = APIRouter(prefix=API_PREFIX, tags=["skills"])


@dataclass(frozen=True)
class Estate:
    """What one reader may see of the agents and their pins, and the directory's names for people.

    Loaded once per request by `_estate`, so the Skills page and the library listing are built
    from one reading of the agents rather than two that could disagree.
    """

    mine: tuple[AgentRecord, ...]
    pins: tuple[SkillPin, ...]
    #: The agent load came back full.
    truncated: bool
    people: Mapping[str, str]


async def _estate(request: Request, asked: Asking, people: Iterable[str] = ()) -> Estate:
    """The agents this reader's audience covers, their pins, and the names of these people.

    The agents are loaded bounded and filtered by audience; their installs are read for exactly
    those agents. The names are read in the same session, for the people the caller names.
    """
    limit = MAX_AGENTS_CONSIDERED
    factory = _require_sessions(request)
    async with factory() as session:
        rows = (await session.execute(bounded_agents(limit))).scalars().all()
        records = [record for record in (record_of(row) for row in rows) if record is not None]
        mine = visible_records(records, asked)
        pairs = (await session.execute(installs_of([one.agent_id for one in mine]))).all()
        wanted = sorted({one for one in people if one})
        names = await steward_names(session, wanted) if wanted else {}

    by_id = {one.agent_id: one for one in mine}
    pins: list[SkillPin] = []
    for instance_row, version_row in pairs:
        record = by_id.get(instance_row.id)
        if record is None:
            # An install whose agent is outside this reader's audience, which the statement
            # above did not ask for. Dropped rather than trusted.
            continue
        pins.extend(pins_of(instance_row, version_row, record))
    return Estate(mine=mine, pins=tuple(pins), truncated=len(rows) >= limit, people=names)


def _people_in(
    library: Sequence[LibrarySkill],
    retirements: Mapping[str, Retirement],
    history: tuple[tuple[AssignmentRecord, ...], tuple[DetachmentRecord, ...]],
    rehearsals: Mapping[str, Rehearsal] | None = None,
) -> set[str]:
    """Everybody the page names: who added, decided, retired, assigned and rehearsed what it
    lists."""
    return (
        {one.submitted_by for one in library}
        | {one.imported.reviewer for one in library if one.imported.reviewer}
        | {one.set_by for one in retirements.values()}
        | {one.assigned_by for one in history[0]}
        | {one.rehearsed_by for one in (rehearsals or {}).values()}
    )


@router.get("/skills", response_model=SkillsPage, responses=COMMON_RESPONSES)
async def skills(request: Request, asked: Asked, listed: CatalogueQuery) -> SkillsPage:
    """The skills the reader's agents run, the library and its queue, and what the reader may do.

    The screen's question first and the database second, and the order is the property: a caller
    holding no grant is refused identically on an instance with a database and on one without.

    The library is read only for a reader it may be listed to, and the queue is narrowed again by
    `skill_queue`, so the two agree by being one question. The agents and their pins are
    `_estate`'s.
    """
    if not permitted(screen(SKILLS_SCREEN).read, asked.reach, asked.now):
        log.info("skills screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    plan = CATALOGUE_LISTING.plan(listed, reader=asked.caller.principal.id)
    _require_sessions(request)

    store = library_of(request)
    readable = may_read_library(asked.reach, asked.now)
    library = await store.library(MAX_LIBRARY) if readable else ()
    retirements = await store.retirements([one.digest for one in library])
    held_names = sorted({one.name for one in library})
    history = await store.assignment_history(held_names)
    reviews = may_review(asked.reach, asked.now)
    adds = may_add(asked.reach, asked.now)
    discloses = reviews or adds
    contents = contents_of(request) if library else None
    rehearsals = (
        await contents.rehearsals([one.digest for one in library]) if contents is not None else {}
    )
    waiting_scripts = (
        await _waiting_scripts(contents, library) if contents is not None and discloses else {}
    )
    estate = await _estate(request, asked, _people_in(library, retirements, history, rehearsals))
    pins = estate.pins
    # The names this reader was shown, and nothing else: see `chips`.
    shown = {pin.skill_name for pin in pins} | {one.name for one in library}
    filed = await store.categories(sorted(shown))
    registry = _tool_registry(request)
    choices = tuple(
        AgentChoiceView(agent_id=one.agent_id, display_name=one.display_name)
        for one in estate.mine
        if readable and may_assign(asked.reach, agent_scope_row(one), asked.now)
    )
    rehearses = may_rehearse(asked.reach, asked.now)
    exports = may_export(asked.reach, asked.now)
    rows = catalogue(
        pins,
        filed,
        agent_names={one.agent_id: one.display_name for one in estate.mine},
        assigned=in_force(history),
        people=estate.people,
    )
    page = plan.page(list(rows))
    return SkillsPage(
        items=list(page.items),
        next_cursor=page.next_cursor,
        truncated=estate.truncated,
        queue=queue_view(submitted(library, asked.now), asked.reach, asked.now),
        library=tuple(
            library_view(
                one,
                _reach_of(one, registry),
                discloses_body=discloses,
                reviews=reviews,
                assigns=bool(choices),
                edits=adds,
                categories=filed.get(one.name, ()),
                against=compared_with(one, library),
                retirement=retirements.get(one.digest),
                people=estate.people,
                rehearsal=rehearsals.get(one.digest),
                script_bytes=waiting_scripts.get(one.digest),
                rehearses=rehearses,
                exports=exports,
            )
            for one in library
        ),
        library_truncated=len(library) >= MAX_LIBRARY,
        agents=choices,
        may_add=adds,
        registry_is_absent=registry is None,
        categories=chips(filed, shown),
    )


async def _waiting_scripts(
    contents: SkillContents, library: Sequence[LibrarySkill]
) -> dict[str, Mapping[str, bytes]]:
    """The script bytes of every version waiting for a decision, for its reviewer to read.

    Only the waiting ones, because those are the versions somebody is about to approve, and a
    decided version's scripts are what its digest says they are; reading every version's bytes
    for every page would be the whole library's code on every load.
    """
    return {
        one.digest: await contents.scripts(one.digest)
        for one in library
        if one.imported.skill.script_files and review_state(one.imported) is Review.PENDING
    }


def library_row(
    one: LibrarySkill,
    *,
    retired: frozenset[str],
    categories: Mapping[str, Sequence[str]],
    pins: Sequence[SkillPin],
) -> SkillVersionRowView:
    """One version as the searchable list draws it: its state and the agents running it."""
    return SkillVersionRowView(
        digest=one.digest,
        name=one.name,
        version=one.imported.skill.version,
        description=one.imported.skill.description,
        review=review_state(one.imported).value,
        retired=one.digest in retired,
        categories=tuple(categories.get(one.name, ())),
        agents_running=len(agents_holding(one.digest, pins)),
        source=one.imported.source.kind.value,
        submitted_at=one.submitted_at,
    )


#: What the library may be searched, filtered and ordered by (M27.11.8). Every column reads the
#: row the reader is sent, `brain.listing`'s rule, so a search cannot match a withheld body.
LIBRARY_LISTING: Final[Listing[SkillVersionRowView]] = Listing(
    name="skill_library",
    columns=(
        Column("name", lambda row: row.name, search=True, filter=True, sort=True),
        Column("description", lambda row: row.description, search=True),
        Column("review", lambda row: row.review, filter=True, sort=True),
        Column("retired", lambda row: row.retired, filter=True),
        Column("categories", lambda row: row.categories, search=True, filter=True),
        Column("source", lambda row: row.source, filter=True),
        Column("agents_running", lambda row: row.agents_running, sort=True),
        Column("submitted_at", lambda row: row.submitted_at, sort=True),
    ),
    key=lambda row: row.digest,
    order="name",
)
LibraryQuery = Annotated[ListAsked, Depends(LIBRARY_LISTING.query())]


@router.get("/skills/library", response_model=SkillLibraryPage, responses=COMMON_RESPONSES)
async def skill_library(request: Request, asked: Asked, listed: LibraryQuery) -> SkillLibraryPage:
    """The library, one row per version, searched, filtered and ordered on the server (M27.11.8).

    The screen's question first. A reader the library may not be listed to is answered the page
    an empty library gives, with no queue, which is what `/skills` sends them too.
    """
    if not permitted(screen(SKILLS_SCREEN).read, asked.reach, asked.now):
        log.info("skill library not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    plan = LIBRARY_LISTING.plan(listed, reader=asked.caller.principal.id)
    _require_sessions(request)
    store = library_of(request)
    readable = may_read_library(asked.reach, asked.now)
    library = await store.library(MAX_LIBRARY) if readable else ()
    retired = retired_digests(await store.retirements([one.digest for one in library]))
    estate = await _estate(request, asked)
    names = sorted({one.name for one in library})
    filed = await store.categories(names)
    rows = [
        library_row(one, retired=retired, categories=filed, pins=estate.pins) for one in library
    ]
    page = plan.page(rows)
    return SkillLibraryPage(
        items=list(page.items),
        next_cursor=page.next_cursor,
        queue=queue_view(submitted(library, asked.now), asked.reach, asked.now),
        library_truncated=len(library) >= MAX_LIBRARY,
        truncated=estate.truncated,
        may_add=may_add(asked.reach, asked.now),
        categories=chips(filed, names),
    )


def _package_bytes(body: SkillPackageAsked) -> bytes:
    if body.encoding == "text":
        return body.content.encode("utf-8")
    try:
        return base64.b64decode(body.content, validate=True)
    except (binascii.Error, ValueError):
        raise _refused_because(
            "this skill was not added: the file could not be read; choose it again"
        ) from None


def _reach_of(one: LibrarySkill, registry: ToolRegistry | None) -> SkillReach:
    """What a library row is trusted to reach, or every tool unresolved with no registry."""
    if registry is None:
        return _unresolved(one.imported.skill.tools)
    return trusted_reach(one.imported.skill, registry)


async def _view_for(
    one: LibrarySkill,
    request: Request,
    asked: Asking,
    library: Sequence[LibrarySkill],
) -> LibrarySkillView:
    """The row a write answers with, for the person who made it.

    Every write here is asked of somebody holding the skill or the review authority, so the body
    is disclosed; the diff is against the library as read for the write.
    """
    store = library_of(request)
    contents = contents_of(request)
    filed = await store.categories([one.name])
    retirement = (await store.retirements([one.digest])).get(one.digest)
    return library_view(
        one,
        _reach_of(one, _tool_registry(request)),
        discloses_body=True,
        reviews=may_review(asked.reach, asked.now),
        assigns=False,
        edits=may_add(asked.reach, asked.now),
        categories=filed.get(one.name, ()),
        against=compared_with(one, [*library, one]),
        retirement=retirement,
        rehearsal=(await contents.rehearsals([one.digest])).get(one.digest),
        script_bytes=(await _waiting_scripts(contents, [one])).get(one.digest),
        rehearses=may_rehearse(asked.reach, asked.now),
        exports=may_export(asked.reach, asked.now),
    )


def _categories_or_refused(typed: Sequence[str]) -> tuple[str, ...]:
    try:
        return categories_from(typed)
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None


#: What a write builds its library entry with, from the library as read for the write.
Making = Callable[[Sequence[LibrarySkill]], LibrarySkill]


async def _added(
    request: Request, asked: Asking, make: Making, categories: tuple[str, ...]
) -> JSONResponse:
    """Write one skill undecided, and its categories when some were given, or refuse saying why.

    Shared by a paste, an upload, a repository, an address and an edit, so every way in reaches
    the library through the same refusals: whatever `make` refuses (`added`'s or `edited`'s),
    another spelling of a name already held, and bytes already held.
    """
    store = library_of(request)
    held = await store.library(MAX_LIBRARY)
    try:
        one = make(held)
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    spelt = another_spelling(one.imported.skill, held)
    if spelt is not None:
        raise _refused_because(
            f"this skill was not added: the library already holds {spelt!r}, which is the same "
            "name spelt differently; name this one the same way if it is a new version of it"
        )
    written = await store.add(one, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id())
    if not written:
        raise _refused_because(
            f"this skill was not added: this version of {one.name!r} is already in the library"
        )
    if categories:
        await store.categorise(
            one.name,
            categories,
            by=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        )
    log.info(
        "skill added",
        skill=one.name,
        source=one.imported.source.kind.value,
        edit=one.edited_from is not None,
        principal=asked.caller.principal.id,
    )
    view = await _view_for(one, request, asked, held)
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))


@router.post(
    "/skills", status_code=201, response_model=LibrarySkillView, responses=COMMON_RESPONSES
)
async def add_skill(request: Request, body: SkillPackageAsked, asked: Asked) -> JSONResponse:
    """Add one skill to the library, undecided, or say why it was not added.

    See `AN_IMPORT_IS_A_SUBMISSION_AND_NEVER_AN_APPROVAL`. The authority is asked before the
    package is read, so a caller who may not add learns nothing about what a package would do.
    """
    if not may_add(asked.reach, asked.now):
        log.info("skill not addable", principal=asked.caller.principal.id)
        raise _not_answerable()
    categories = _categories_or_refused(body.categories)
    try:
        package = read_package(body.file_name, _package_bytes(body))
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    return await _added(request, asked, _adding(package, asked), categories)


def _adding(package: Package, asked: Asking) -> Making:
    """`added`, for this caller at this instant; the library is not asked."""
    return lambda _held: added(package, by=asked.caller.principal.id, at=asked.now)


async def _fetched_package(request: Request, body: SkillImportAsked) -> Package:
    """Fetch what the import names and read it, off the event loop, or refuse saying why.

    The source's shape is checked before anything is fetched, so a malformed commit or an http
    address costs no connection. The fetch is `brain.tools.fetch`'s, whose rules apply to every
    hop, and a refusal from it (an address inside the network, a host off the list, a status that
    is not an answer) is the importer's to read, since they typed the address.
    """
    fetcher, resolver = fetcher_of(request), resolver_of(request)
    try:
        if body.kind == "github":
            source = github_source(body.repository, body.commit, body.path)
            tarball = await asyncio.to_thread(
                fetch_skill_source, source, fetcher=fetcher, resolver=resolver
            )
            return read_github(source, tarball)
        url = body.url.strip()
        problem = url_source_problem(url)
        if problem is not None:
            raise SkillLibraryError(f"this skill was not added: {problem}")
        content = await asyncio.to_thread(fetch_skill_url, url, fetcher=fetcher, resolver=resolver)
        return read_url(url, content)
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    except SkillError as refused:
        raise _refused_because(f"this skill was not added: {refused}") from None


@router.post(
    "/skills/imports",
    status_code=201,
    response_model=LibrarySkillView,
    responses=COMMON_RESPONSES,
)
async def import_skill(request: Request, body: SkillImportAsked, asked: Asked) -> JSONResponse:
    """Import one skill from a repository at a commit or from an address, undecided (M12.2.2,
    M12.2.3).

    The authority is asked before anything is fetched, so a caller who may not add cannot use
    this server to reach an address, and learns nothing about what one answers.
    """
    if not may_add(asked.reach, asked.now):
        log.info("skill not importable", principal=asked.caller.principal.id)
        raise _not_answerable()
    categories = _categories_or_refused(body.categories)
    package = await _fetched_package(request, body)
    return await _added(request, asked, _adding(package, asked), categories)


Digest = Annotated[str, Path(pattern=DIGEST_PATTERN)]


@router.post(
    "/skills/{digest}/versions",
    status_code=201,
    response_model=LibrarySkillView,
    responses=COMMON_RESPONSES,
)
async def edit_skill(
    request: Request, digest: Digest, body: SkillEditAsked, asked: Asked
) -> JSONResponse:
    """Save an edit of one skill as a new version, undecided (M12.3.2).

    The authority first, before the digest is looked up. The version edited is never changed; see
    `brain.console.skill_library.AN_EDIT_IS_A_NEW_VERSION_AND_MOVES_NO_PIN`.
    """
    if not may_add(asked.reach, asked.now):
        log.info("skill not editable", principal=asked.caller.principal.id)
        raise _not_answerable()
    one = await library_of(request).skill(digest)
    if one is None:
        raise _refused_because("nothing was saved: no skill in the library has that digest")
    # The version's scripts travel with the edit, held to their sha256 by `edited` (M12.4.11).
    scripts = await contents_of(request).scripts(digest) if one.imported.skill.scripts else {}
    return await _added(
        request,
        asked,
        lambda held: edited(
            one,
            body.content,
            by=asked.caller.principal.id,
            at=asked.now,
            library=held,
            scripts=scripts,
        ),
        (),
    )


@router.post(
    "/skills/{digest}/categories", response_model=CategoriesView, responses=COMMON_RESPONSES
)
async def categorise_skill(
    request: Request, digest: Digest, body: CategoriesAsked, asked: Asked
) -> CategoriesView:
    """Set the categories a skill's name carries, every version of it at once (M12.4.13).

    The authority first, before the digest is looked up. The digest names the skill so the route
    never takes a name from the browser: a name nobody added cannot be given categories.
    """
    if not may_add(asked.reach, asked.now):
        log.info("skill not categorisable", principal=asked.caller.principal.id)
        raise _not_answerable()
    categories = _categories_or_refused(body.categories)
    store = library_of(request)
    one = await store.skill(digest)
    if one is None:
        raise _refused_because("nothing was saved: no skill in the library has that digest")
    await store.categorise(
        one.name,
        categories,
        by=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    log.info("skill categorised", skill=one.name, principal=asked.caller.principal.id)
    return CategoriesView(name=one.name, categories=categories)


@router.post("/skills/{digest}/review", response_model=LibrarySkillView, responses=COMMON_RESPONSES)
async def review_skill(
    request: Request, digest: Digest, body: ReviewAsked, asked: Asked
) -> LibrarySkillView:
    """Approve or reject one skill, once, as the review authority, the importer included (M12.4.6).

    The authority first, before the digest is looked up. A decision by the person who added the
    skill is written as their own, and the ledger records it as such; see
    `brain.console.skill_library.AN_ADMINISTRATOR_MAY_APPROVE_WHAT_THEY_IMPORTED_AND_THE_LEDGER_SAYS_SO`.
    """
    if not may_review(asked.reach, asked.now):
        log.info("skill not reviewable", principal=asked.caller.principal.id)
        raise _not_answerable()
    library = library_of(request)
    one = await library.skill(digest)
    if one is None:
        raise _refused_because("nothing was decided: no skill in the library has that digest")
    # The newest rehearsal of these bytes, which an approval of a version with examples needs.
    newest = (await contents_of(request).rehearsals([digest])).get(digest)
    try:
        after = decided(
            one,
            reviewer=asked.caller.principal.id,
            approve=body.decision == "approve",
            at=asked.now,
            rehearsal=newest,
        )
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    written = await library.decide(after, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id())
    if not written:
        raise _refused_because(
            f"nothing was decided: somebody decided about {one.name!r} first; reload to see it"
        )
    log.info(
        "skill decided",
        skill=one.name,
        own=after.self_decided,
        principal=asked.caller.principal.id,
    )
    return await _view_for(after, request, asked, await library.library(MAX_LIBRARY))


@router.post(
    "/skills/{digest}/rehearsals",
    status_code=201,
    response_model=LibrarySkillView,
    responses=COMMON_RESPONSES,
)
async def rehearse_skill(
    request: Request, digest: Digest, body: RehearsalAsked, asked: Asked
) -> JSONResponse:
    """Record a rehearsal of one version's example tasks: whether each behaved (M12.3.4).

    The authority first, before the digest is looked up: whoever may add or review a skill. The
    rehearsal is the caller's verdict, recorded in their name, and says nothing a model did; see
    `brain.console.skill_library.A_REHEARSAL_IS_A_PERSON_S_VERDICT_UNTIL_A_MODEL_ANSWERS`. The
    answer is the version's row, which says whether it may now be approved.
    """
    if not may_rehearse(asked.reach, asked.now):
        log.info("skill not rehearsable", principal=asked.caller.principal.id)
        raise _not_answerable()
    library = library_of(request)
    one = await library.skill(digest)
    if one is None:
        raise _refused_because("nothing was recorded: no skill in the library has that digest")
    try:
        done = rehearsal(one, body.behaved, by=asked.caller.principal.id, at=asked.now)
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    await contents_of(request).rehearse(done, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id())
    log.info(
        "skill rehearsed",
        skill=one.name,
        passed=done.passed,
        principal=asked.caller.principal.id,
    )
    view = await _view_for(one, request, asked, await library.library(MAX_LIBRARY))
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))


@router.post(
    "/skills/{digest}/exports", response_model=SkillPackageView, responses=COMMON_RESPONSES
)
async def export_skill(request: Request, digest: Digest, asked: Asked) -> SkillPackageView:
    """One approved version as a package another install adds, undecided, through `POST /skills`
    (M12.3.1).

    The authority first, before the digest is looked up: the skill authority over everything, as
    adding asks. Nothing is written. `brain.console.skill_library.exported` refuses a version that
    is not approved and unchanged since, and holds every script's bytes to the approved sha256
    before they leave; see `ONLY_AN_APPROVED_VERSION_IS_EXPORTED`.
    """
    if not may_export(asked.reach, asked.now):
        log.info("skill not exportable", principal=asked.caller.principal.id)
        raise _not_answerable()
    one = await library_of(request).skill(digest)
    if one is None:
        raise _refused_because("nothing was exported: no skill in the library has that digest")
    scripts = await contents_of(request).scripts(digest) if one.imported.skill.scripts else {}
    try:
        package = exported(one, scripts)
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    log.info("skill exported", skill=one.name, principal=asked.caller.principal.id)
    return SkillPackageView(
        file_name=package.file_name,
        content=base64.b64encode(package.content).decode("ascii"),
        name=package.name,
        version=package.version,
        digest=package.digest,
    )


@router.post(
    "/skills/{digest}/assignments",
    status_code=201,
    response_model=AssignedView,
    responses=COMMON_RESPONSES,
)
async def assign_skill(
    request: Request, digest: Digest, body: AssignAsked, asked: Asked
) -> JSONResponse:
    """Assign one approved skill to one agent through `attach_skill`, or say why not.

    The authority is asked of the reach alone first, then of the agent's row once the agent is
    read, and an agent outside the caller's audience or outside their authority is the same
    refusal as one that does not exist. Only then is the skill looked up.
    """
    if not permitted(screen(SKILLS_SCREEN).read, asked.reach, asked.now) or (
        asked.reach.scope_for(SKILL_AUTHORITY, asked.now) is None
    ):
        log.info("skill not assignable", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = await agent_installs_of(request).agent(body.agent_id)
    if (
        found is None
        or body.agent_id not in visible_agent_ids((found.record,), viewer_of(asked))
        or not may_assign(asked.reach, agent_scope_row(found.record), asked.now)
    ):
        log.info("skill not assignable to this agent", principal=asked.caller.principal.id)
        raise _not_answerable()
    if found.install is None or found.effective_hash is None:
        raise _refused_because(
            "nothing was assigned: this agent has no install record that constructs, so there is "
            "no manifest to pin a skill in"
        )
    library = library_of(request)
    one = await library.skill(digest)
    if one is None:
        raise _refused_because("nothing was assigned: no skill in the library has that digest")
    if digest in retired_digests(await library.retirements([digest])):
        raise _refused_because(
            f"nothing was assigned: {one.name} {one.imported.skill.version} is retired; "
            "reinstate it or assign a later version"
        )
    now = asked.now
    recorder = AuditRecorder(
        AuditChain(),
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id() or "unassigned",
        clock=lambda: now,
    )
    signed, instance = found.install
    try:
        made = assignment(
            one,
            record=found.record,
            signed=signed,
            instance=instance,
            library=await library.library(MAX_LIBRARY),
            by=asked.reach,
            recorder=recorder,
            now=now,
        )
    except (SkillLibraryError, AgentTabError) as refused:
        raise _refused_because(str(refused)) from None
    except (TemplateError, WorkspaceError, ValueError):
        raise _refused_because(
            "nothing was assigned: the agent's install refused this skill"
        ) from None
    written = await library.assign(
        made,
        expected_hash=found.effective_hash,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if not written:
        raise _refused_because(
            "nothing was assigned: somebody changed this agent after you opened it; reload and "
            "assign again"
        )
    registry = _tool_registry(request)
    reach = (
        ()
        if registry is None
        else reach_through(one.imported.skill, registry, asked.reach, found.record, now)
    )
    log.info(
        "skill assigned", skill=one.name, agent=made.agent_id, principal=asked.caller.principal.id
    )
    view = AssignedView(
        agent_id=made.agent_id,
        skill_name=made.skill_name,
        digest=made.digest,
        replaced_digest=made.replaces_digest,
        reach=reach,
        effective_hash=made.effective_hash,
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))


async def _retirement(
    request: Request, digest: str, asked: Asking, *, retire: bool
) -> RetirementView:
    """Retire or reinstate one version, or refuse saying why (M27.15.56).

    The authority first, before the digest is looked up: the skill authority over everything,
    as adding asks, because a retirement is a library act. The agents still running the version
    are the pins of the agents this reader may see, and nothing wider.
    """
    word = "retired" if retire else "reinstated"
    if not may_add(asked.reach, asked.now):
        log.info("skill retirement not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    store = library_of(request)
    one = await store.skill(digest)
    if one is None:
        raise _refused_because(f"nothing was {word}: no skill in the library has that digest")
    current = (await store.retirements([digest])).get(digest)
    try:
        retiring(one, retire=retire, current=current)
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    await store.retire(
        digest,
        retired=retire,
        by=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    log.info(f"skill {word}", skill=one.name, principal=asked.caller.principal.id)
    holders: tuple[AgentChoiceView, ...] = ()
    if retire:
        estate = await _estate(request, asked)
        named = {one.agent_id: one.display_name for one in estate.mine}
        holders = tuple(
            AgentChoiceView(agent_id=agent_id, display_name=named[agent_id])
            for agent_id in agents_holding(digest, estate.pins)
        )
    return RetirementView(
        digest=digest,
        name=one.name,
        version=one.imported.skill.version,
        retired=retire,
        holding=holders,
    )


@router.post(
    "/skills/{digest}/retirement", response_model=RetirementView, responses=COMMON_RESPONSES
)
async def retire_skill(request: Request, digest: Digest, asked: Asked) -> RetirementView:
    """Retire one version: no agent may newly be assigned it, and none running it loses it.

    See `brain.console.skill_library.A_RETIRED_VERSION_IS_KEPT_AND_ONLY_REFUSED_TO_NEW_AGENTS`.
    """
    return await _retirement(request, digest, asked, retire=True)


@router.post(
    "/skills/{digest}/reinstatement", response_model=RetirementView, responses=COMMON_RESPONSES
)
async def reinstate_skill(request: Request, digest: Digest, asked: Asked) -> RetirementView:
    """Reinstate one retired version, so it may be assigned again. A later row, never an undo."""
    return await _retirement(request, digest, asked, retire=False)


@router.post(
    "/skills/{digest}/detachments",
    status_code=201,
    response_model=DetachedView,
    responses=COMMON_RESPONSES,
)
async def detach_skill(
    request: Request, digest: Digest, body: AssignAsked, asked: Asked
) -> JSONResponse:
    """Take one skill off one agent, or say why not (M27.15.55).

    `assign_skill`'s questions in its order, because detaching is as assigned: the screen and the
    skill authority of the reach alone, then the agent in the caller's audience and in their
    authority, refused alike and identically to an agent that does not exist, and only then the
    skill. The row naming the assignment it ended and the install without the skill are written
    together under the install lock, or not at all.
    """
    if not permitted(screen(SKILLS_SCREEN).read, asked.reach, asked.now) or (
        asked.reach.scope_for(SKILL_AUTHORITY, asked.now) is None
    ):
        log.info("skill not detachable", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = await agent_installs_of(request).agent(body.agent_id)
    if (
        found is None
        or body.agent_id not in visible_agent_ids((found.record,), viewer_of(asked))
        or not may_assign(asked.reach, agent_scope_row(found.record), asked.now)
    ):
        log.info("skill not detachable from this agent", principal=asked.caller.principal.id)
        raise _not_answerable()
    if found.install is None or found.effective_hash is None:
        raise _refused_because(
            "nothing was detached: this agent has no install record that constructs"
        )
    store = library_of(request)
    one = await store.skill(digest)
    if one is None:
        raise _refused_because("nothing was detached: no skill in the library has that digest")
    now = asked.now
    recorder = AuditRecorder(
        AuditChain(),
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id() or "unassigned",
        clock=lambda: now,
    )
    signed, instance = found.install
    try:
        made = detachment(
            one,
            record=found.record,
            signed=signed,
            instance=instance,
            by=asked.reach,
            recorder=recorder,
            now=now,
        )
    except (SkillLibraryError, AgentTabError) as refused:
        raise _refused_because(str(refused)) from None
    except (TemplateError, WorkspaceError, ValueError):
        raise _refused_because(
            "nothing was detached: the agent's install refused the change"
        ) from None
    written = await store.detach(
        made,
        expected_hash=found.effective_hash,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if not written:
        raise _refused_because(
            "nothing was detached: somebody changed this agent after you opened it; reload and "
            "try again"
        )
    log.info(
        "skill detached", skill=one.name, agent=made.agent_id, principal=asked.caller.principal.id
    )
    view = DetachedView(
        agent_id=made.agent_id,
        skill_name=made.skill_name,
        digest=made.digest,
        effective_hash=made.effective_hash,
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))
