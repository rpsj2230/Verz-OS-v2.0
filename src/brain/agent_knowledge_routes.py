"""What one agent draws on, as its page's Knowledge section lists it, at the reader's own reach.

The Profile already says what an agent draws on as a predicate and how many of the reader's own
documents it meets (`brain.agent_capability_routes`, M39.2.3.1 to .4), and the workspace lists
Knowledge as a tab. Neither names a single document, so a person who asked "what does this agent
know?" was shown a rule and a number and had to guess which documents were behind it. This is the
section that names them, and it adds no rule of its own about who may be told a document exists.

**The list is the company's documents, narrowed twice, and never a store of the agent's own.**
First by the reader: `brain.agent_capability_routes.reader_stored_items` is the one read of "the
documents this person may see", the same read the Profile's slice is counted over, so the two
cannot disagree about what exists. Then by the agent: `matching`, in
`brain.console.workspace_capabilities`, keeps the documents the agent's predicate reaches, which
also drops a superseded or archived one.
An agent is a lens: a document appears here because the reader may read it and the agent's rule
meets it, and for no other reason. See `A_SECTION_LISTS_THE_COMPANYS_DOCUMENTS_AND_KEEPS_NONE`.

**A document the reader may only see the record of is not listed.** The lifecycle read admits
`may_see` (an administrator sees a record of a document in a department they cannot read), and the
Profile's count is over that. This list is stricter, `may_read`, because a section that says an
agent draws on a document the reader could not open beside it would be the existence of that
document, told in a sentence. Nothing here counts what was left out, and the page is bounded after
the narrowing, so a short page says nothing about anything else.

**A reader without the Knowledge tab's read is answered as an agent that does not exist**, as the
Memory and Artifacts sections are. The tab is permitted by `read:document` on the existence plane
(`brain.console.workspace`), so the section is never a way to learn that an agent exists.

**The badge is `brain.knowledge.verification.disclose`'s, and the person who verified is named
only where it names them.** A second reading of a review date is a document that is due on one
screen and current on another, and a verifier named to a reader the badge withholds them from is a
person disclosed by a list.

**What an item was added by is its steward, and how it arrived is shown only where it was
recorded.** `know.item` has recorded since `0220` whether a document arrived as a file or as a
link, and for a link the address. A document added before that records neither, so the list says
`unknown` for it rather than reading its text to guess: the first line of a link's text is its
address, but a file may begin with anything. See
`A_WAY_OF_ARRIVING_IS_SHOWN_ONLY_WHERE_IT_WAS_RECORDED`. The address itself is never in a list,
because a share link carries a token.

**Adding from this page is the Knowledge page's own door, called, not copied.** The two routes
here check that the reader may open the section, then call `brain.knowledge_routes.upload` and
`brain.knowledge_intake_routes.add_link` with the same request, so the type proved from the
bytes, the size limit, the scan, the refusal of a private address on every redirect, the placement
checks, the reading slot and the audit row are those functions' and nothing here repeats one. A
refusal is theirs, in their words. What this module adds is the answer to the question the person
asked by adding: does this agent draw on it? That is `plan_addition`'s `reached`, and when it is no
the answer says which clauses of the rule exclude the item and offers the one next step, which is
the draft that widens the rule (`brain.console.agent_tabs.widen` is that change) or putting the item
where the rule already reaches. **Nothing is added to the agent's reach by the act of adding**
(`brain.console.agent_tabs.ADDING_AN_ITEM_IS_NOT_THE_SAME_AS_REACHING_IT`): an item outside the
rule is the company's document and stays unreached until a person changes the rule.

**The figure beside an item is counted over the page the reader is shown and nothing else.**
`StoredItemUses.uses` is asked for the documents on the page, so a count of a document the reader
may not open is never read, let alone shown. While `agent_item_counts` is off nothing is read and no
item carries a figure, which is not the same as nought: a nought says the agent never touched it.


**Retiring and fetching again are the Knowledge page's acts, offered here and not copied.** A
document is the company's and not the agent's, so retiring one withdraws it for every agent and
every person at once, which is the Knowledge page's own archive
(`knowledge_lifecycle_routes.archive`, decided by `Authority.may_act`, written by `0216`'s
function) and is called here, never rewritten. It stops being drawn on in the transaction that
archives it, because retrieval reads only the states in
`brain.knowledge.item.RETRIEVABLE_STATES`. **A link is fetched again only when a person asks**: the
route takes the address recorded when it was added, runs it through the link door's own fetch (the
address rule on every redirect hop, the same transport, the same scan and parse) and writes what it
read as a newer version through `knowledge_lifecycle_routes.write_successor`, the one place a
version is superseded. Nothing here schedules it, polls an address or follows a link on the page.
See `A_LINK_IS_FETCHED_AGAIN_ONLY_WHEN_A_PERSON_ASKS`. Both are refused, in the one sentence an
absent document gets, for whoever may not act on the document, and for a document this agent does
not draw on.


Task ids: M39.2.3.5, M39.9.1.5, M39.9.1.1, M39.9.1.2, M39.9.1.3, M39.9.1.4, M39.9.1.6
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Body, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from brain import knowledge_intake_routes
from brain.agent_capability_routes import knowledge_item_of, knowledge_scope_of, reader_stored_items
from brain.agent_routes import _no_agent_here, _require_session_factory, _visible_record
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.agent_tabs import AddRoute, plan_addition
from brain.console.reads import permitted
from brain.console.workspace import Tab, tab
from brain.console.workspace_capabilities import KnowledgeScope, item_row, matching
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.ingest import IngestRefused, ParseFailure
from brain.knowledge.item import ARRIVED_AS_LINK, ITEM_ID_PATTERN
from brain.knowledge.kinds import KIND_LABELS, KnowledgeKind
from brain.knowledge.lifecycle import (
    NOT_OFFERED,
    Authority,
    LifecycleError,
    StoredItem,
    authority_for,
    successor_place,
)
from brain.knowledge.lifecycle_store import (
    as_person,
    live_item,
    names_of,
    source_url_of,
    versions,
)
from brain.knowledge.uploads import OfferedAsATable, receive_page
from brain.knowledge.verification import disclose
from brain.knowledge.visibility import Visibility
from brain.knowledge_intake_routes import LinkAsked, add_link, read_link_for
from brain.knowledge_lifecycle_routes import (
    LIFECYCLE_RESPONSES,
    VersionAddedView,
    archive,
    in_transaction,
    refused,
    write_successor,
)
from brain.knowledge_routes import (
    OFFERED_AS_A_TABLE,
    UPLOAD_RESPONSES,
    UploadedView,
    give_back,
    live_departments,
    take_reading_slot,
    too_busy,
    upload,
)
from brain.ops.agent_item_use import WINDOW_DAYS, StoredItemUses, counting_is_on

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why this section lists documents and keeps none.
A_SECTION_LISTS_THE_COMPANYS_DOCUMENTS_AND_KEEPS_NONE: Final = (
    "An item shown in an agent's Knowledge section is one of the company's documents, read at "
    "the reader's own reach and narrowed by the agent's rule. The agent owns no store of its own: "
    "an agent is a lens and never a principal, so nobody reads through one a document they could "
    "not open anywhere else, and a document added from this page is the company's like any other."
)

#: Why a way of arriving is shown only where it was recorded.
A_WAY_OF_ARRIVING_IS_SHOWN_ONLY_WHERE_IT_WAS_RECORDED: Final = (
    "A document's row records whether it arrived as a file or as a link only from the release that "
    "added the columns. A document added earlier is listed as unknown, because the only other "
    "evidence is its text, and a list that read the text to guess would call a file that begins "
    "with an address a link and offer to fetch what was never fetched."
)

#: Why a refetch is a person's act and nothing else.
A_LINK_IS_FETCHED_AGAIN_ONLY_WHEN_A_PERSON_ASKS: Final = (
    "A link added from the Knowledge section is fetched again only when a person asks for it. "
    "Nothing schedules it, nothing polls the address, and a page the link points at is never "
    "followed further: the document is a snapshot with a date, and a newer snapshot is a newer "
    "version a person asked for and may refuse."
)

#: What the section says when the agent's rule is not about where documents sit.
THE_RULE_IS_NOT_ABOUT_WHERE_DOCUMENTS_SIT: Final = (
    "This agent's rule is not about where documents sit, so this list cannot say which documents "
    "it draws on. Nothing about what it may read has changed."
)

#: What a person added from this page is told when the agent draws on it.
THE_AGENT_DRAWS_ON_WHAT_WAS_ADDED: Final = "Added. This agent draws on it now."

#: What they are told when it does not, and what to do next. One sentence about the item and one
#: about the next step, and neither names a document, a person or a count of anything else.
THE_AGENT_DOES_NOT_DRAW_ON_WHAT_WAS_ADDED: Final = (
    "Added to the company's documents, but this agent does not draw on it, because its rule does "
    "not reach where you put it. Put it where the rule reaches, or widen what the agent draws on "
    "through a draft. Nothing about any other agent has changed."
)

#: What a person who retired a document is told.
THE_DOCUMENT_IS_RETIRED_FOR_EVERY_AGENT: Final = (
    "Retired. No agent draws on it now, and it stays on file with its history."
)

#: What they are told when there is no address on record to fetch again.
THERE_IS_NO_ADDRESS_TO_FETCH_AGAIN: Final = (
    "This document was not added from a link, or was added before the address was recorded, so "
    "there is nothing to fetch again. Add the page again from its link, or add a newer version as "
    "a file."
)

#: What they are told when the page has not changed since it was last fetched.
THE_PAGE_HAS_NOT_CHANGED: Final = (
    "The page has not changed since it was last fetched, so there is no newer version to add."
)

#: What they are told when the rule is not about where documents sit, so reaching cannot be said.
THE_AGENT_CANNOT_SAY_WHAT_IT_REACHES: Final = (
    "Added to the company's documents. This agent's rule is not about where documents sit, so "
    "whether it draws on this one cannot be said here."
)

#: Whose activity the figure beside an item counts.
COUNT_BASIS: Final = "answers by everybody who asked this agent"

# ------------------------------------------------------------------------ the figures
KNOWLEDGE_PATH: Final = "/agents/{agent_id}/knowledge"
UPLOAD_PATH: Final = "/agents/{agent_id}/knowledge/uploads"
LINK_PATH: Final = "/agents/{agent_id}/knowledge/links"
RETIRE_PATH: Final = "/agents/{agent_id}/knowledge/{item_id}/retire"
REFETCH_PATH: Final = "/agents/{agent_id}/knowledge/{item_id}/refetch"

#: What a list says for a document that records no way of arriving.
ARRIVED_UNKNOWN: Final = "unknown"

#: The most items one page carries, and how many when nothing asked for fewer. Resource bounds
#: applied after the narrowing, so raising them discloses nothing.
DEFAULT_PAGE: Final = 25
MAX_PAGE: Final = 100
#: The furthest into the list an offset may reach: the reader's own documents are bounded by
#: `brain.knowledge.lifecycle_store.MAX_ITEMS`, so no offset past it can name anything.
MAX_OFFSET: Final = 10_000

#: What a place reads as when a document sits at no department.
COMPANY_PLACE: Final = "Company"


# ------------------------------------------------------------------------------ the views
class KnowledgeClauseView(BaseModel):
    """One clause of the agent's rule, so the section can say what the list is the answer to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    op: str
    value: str


class AgentKnowledgeItemView(BaseModel):
    """One document this agent draws on, as this reader may be told it. Never its text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    kind: str | None
    kind_label: str
    #: Where it sits: the department's slug, or the company's, or the reader's own.
    place: str
    level: str
    added_by: str
    added_by_name: str
    added_at: datetime | None
    #: `brain.knowledge.verification.disclose`'s state for this reader.
    verification: str
    verified_by_name: str | None = None
    verified_at: datetime | None = None
    review_by: datetime | None = None
    #: Whether its review date has arrived.
    due: bool = False
    #: How many of this agent's answers cited it in the window, or None when nothing is counted.
    #: None is not nought: nought says the agent never touched it.
    uses: int | None = None
    #: `file`, `link` or `unknown`, from what the row recorded and never from its text.
    arrived_as: str = ARRIVED_UNKNOWN
    #: Whether this reader may retire it: the Knowledge page's own answer, `Authority.may_act`.
    can_retire: bool = False
    #: Whether this reader may ask for the page to be fetched again: it arrived as a link and they
    #: may act on it.
    can_refetch: bool = False
    #: Whether this agent's rule reaches it. Every listed item is reached; the field is the
    #: contract the add answer shares, so the page draws one shape for both.
    reached: bool = True


class UseFiguresView(BaseModel):
    """What the figure beside each item counts. Said once, so no row has to say it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_days: int
    #: Whose activity the figures are, in words: everybody who asked this agent.
    basis: str


class AgentKnowledgeView(BaseModel):
    """The Knowledge section: what this agent draws on, the rule, and whether the reader may add."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    items: list[AgentKnowledgeItemView]
    rule: list[KnowledgeClauseView]
    #: Whether the reader may add a document anywhere. The two ways to add are offered only then.
    can_add: bool
    #: The department the rule already draws on, which is where an addition lands unless the person
    #: chooses another; empty when the rule names none or more than one.
    add_into: str = ""
    #: More of the reader's own list follows this page. Never how many.
    more: bool = False
    #: The reader's documents were read to their bound, so a later one may be missing.
    at_least: bool = False
    #: Set, with an empty list, when nothing here could look.
    unread: str = ""
    #: Set when the figures beside each item are counted: the window in days and whose activity
    #: they are. None while `agent_item_counts` is off, and then no item carries a figure.
    use_figures: UseFiguresView | None = None
    kept_rule: str = A_SECTION_LISTS_THE_COMPANYS_DOCUMENTS_AND_KEEPS_NONE


class KnowledgeAddedView(BaseModel):
    """What was added from this page, and whether this agent draws on it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    kind: str
    level: str
    department: str | None
    passages: int
    found_by: str
    #: `upload` or `link`.
    route: str
    #: `brain.console.agent_tabs.plan_addition`'s answer for this agent.
    reached: bool
    #: One sentence, in words that name nothing but this item's own fate.
    said: str
    #: The clauses of the rule that exclude it, when it is not reached.
    blocking: list[KnowledgeClauseView]
    #: Whether widening the rule through a draft would reach it: there is a clause to drop.
    can_widen: bool


# ------------------------------------------------------------------------- the decisions
def may_read_knowledge_at(asked: Asking) -> bool:
    """The Knowledge tab's own read, which is what the strip shows the section by."""
    return permitted(tab(Tab.KNOWLEDGE).read, asked.reach, asked.now)


def newest_first(items: list[StoredItem]) -> list[StoredItem]:
    """Newest added first, then by id, so two reads of an unchanged library are one list."""
    undated = [one for one in items if one.added_at is None]
    dated = [one for one in items if one.added_at is not None]
    dated.sort(key=lambda one: (-(one.added_at.timestamp() if one.added_at else 0), one.item_id))
    undated.sort(key=lambda one: one.item_id)
    return [*dated, *undated]


def place_of(item: StoredItem) -> str:
    """Where a document sits, in the words a person looks for it by."""
    return item.visibility.department or COMPANY_PLACE


def item_view(
    one: StoredItem,
    *,
    asked: Asking,
    names: dict[str, str],
    uses: int | None = None,
    may_act: bool = False,
) -> AgentKnowledgeItemView:
    """One document as this reader is shown it: the badge as they may be told it, never the text."""
    shown = disclose(one, reader=asked.reach, now=asked.now)
    named = shown.verified_by
    return AgentKnowledgeItemView(
        item_id=one.item_id,
        title=one.title or one.item_id,
        kind=one.kind.value if one.kind else None,
        kind_label=KIND_LABELS[one.kind] if one.kind else "Not recorded",
        place=place_of(one),
        level=one.visibility.level.value,
        added_by=one.owner_id,
        added_by_name=names.get(one.owner_id, ""),
        added_at=one.added_at,
        verification=shown.state.value,
        verified_by_name=names.get(named) if named else None,
        verified_at=shown.verified_at,
        review_by=one.review_by,
        due=one.review_by is not None and one.review_by <= asked.now and one.is_retrievable,
        uses=uses,
        arrived_as=one.arrived_as or ARRIVED_UNKNOWN,
        can_retire=may_act,
        can_refetch=may_act and one.arrived_as == ARRIVED_AS_LINK,
    )


def department_default(scope: KnowledgeScope) -> str:
    """The department the rule names with an equality, or nothing when it names none."""
    named = [
        str(one.value)
        for one in scope.predicate.clauses
        if one.field == "department" and one.op is Op.EQ
    ]
    return named[0] if len(named) == 1 else ""


def blocking_clauses(scope: KnowledgeScope, item: StoredItem) -> list[Clause]:
    """The clauses of the rule this item fails, each judged alone.

    Judged against the same row `matching` judges (`item_row`), one clause at a time, so what is
    named is exactly what a person would change to reach the item.
    """
    row = item_row(knowledge_item_of(item))
    return [one for one in scope.predicate.clauses if not Scope(clauses=(one,)).matches(row)]


def added_answer(
    done: UploadedView, *, route: AddRoute, scope: KnowledgeScope | None, item: StoredItem | None
) -> KnowledgeAddedView:
    """What the door's answer means for this agent: `plan_addition`, said in a sentence."""
    blocking: list[Clause] = []
    if scope is None or item is None:
        reached, said = False, THE_AGENT_CANNOT_SAY_WHAT_IT_REACHES
    else:
        reached = plan_addition(scope, knowledge_item_of(item), route).reached
        blocking = [] if reached else blocking_clauses(scope, item)
        said = (
            THE_AGENT_DRAWS_ON_WHAT_WAS_ADDED
            if reached
            else THE_AGENT_DOES_NOT_DRAW_ON_WHAT_WAS_ADDED
        )
    return KnowledgeAddedView(
        item_id=done.item_id,
        title=done.title,
        kind=done.kind,
        level=done.level,
        department=done.department,
        passages=done.passages,
        found_by=done.found_by,
        route=route.value,
        reached=reached,
        said=said,
        blocking=[
            KnowledgeClauseView(field=one.field, op=one.op.value, value=str(one.value))
            for one in blocking
        ],
        can_widen=bool(blocking),
    )


async def added_item(request: Request, asked: Asking, item_id: str) -> StoredItem | None:
    """The document just added, read back at the person's own reach, or None when it cannot be."""
    factory = _require_session_factory(request)
    authority = authority_for(
        asked.reach, departments=await live_departments(factory), now=asked.now
    )
    async with factory() as session, session.begin():
        await as_person(session, authority)
        found = await live_item(session, item_id)
    return found if found is not None and authority.may_read(found) else None


async def answerable_agent(request: Request, agent_id: str, asked: Asking) -> AgentRecord:
    """The agent, when this reader may open it and the section, or the missing agent's 404."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
    if not may_read_knowledge_at(asked):
        log.info("agent knowledge not answerable", principal=asked.caller.principal.id)
        raise _no_agent_here()
    return record


def readable_slice(
    authority: Authority, seen: tuple[StoredItem, ...], reached_ids: frozenset[str]
) -> list[StoredItem]:
    """The documents the reader may open and the agent's rule reaches, newest first."""
    return newest_first(
        [one for one in seen if one.item_id in reached_ids and authority.may_read(one)]
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(KNOWLEDGE_PATH, response_model=AgentKnowledgeView, responses=COMMON_RESPONSES)
async def agent_knowledge(
    request: Request,
    agent_id: str,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> AgentKnowledgeView:
    """The documents this agent draws on that this reader may open, newest first, paged."""
    factory = _require_session_factory(request)
    record = await answerable_agent(request, agent_id, asked)
    scope = knowledge_scope_of(record)
    authority, seen, full = await reader_stored_items(factory, asked.reach, asked.now)
    can_add = authority.adds is not None
    if scope is None:
        return AgentKnowledgeView(
            agent_id=agent_id,
            items=[],
            rule=[],
            can_add=can_add,
            unread=THE_RULE_IS_NOT_ABOUT_WHERE_DOCUMENTS_SIT,
        )
    reached = matching(scope, [knowledge_item_of(one) for one in seen])
    ordered = readable_slice(authority, seen, frozenset(one.item_id for one in reached))
    page = ordered[offset : offset + limit]
    async with factory() as session:
        names = await names_of(
            session, [*(one.owner_id for one in page), *(one.verified_by for one in page)]
        )
    counted: dict[str, int] | None = None
    if await counting_is_on(factory):
        counted = await StoredItemUses(factory).uses(
            agent_id, [one.item_id for one in page], today=asked.now.date()
        )
    return AgentKnowledgeView(
        agent_id=agent_id,
        items=[
            item_view(
                one,
                asked=asked,
                names=names,
                uses=None if counted is None else counted.get(one.item_id, 0),
                may_act=authority.may_act(one),
            )
            for one in page
        ],
        rule=[
            KnowledgeClauseView(field=clause.field, op=clause.op.value, value=str(clause.value))
            for clause in scope.predicate.clauses
        ],
        can_add=can_add,
        add_into=department_default(scope),
        more=len(ordered) > offset + limit,
        at_least=full,
        use_figures=None
        if counted is None
        else UseFiguresView(window_days=WINDOW_DAYS, basis=COUNT_BASIS),
    )


# ------------------------------------------------------------------------------ adding
@router.post(
    UPLOAD_PATH, status_code=201, response_model=KnowledgeAddedView, responses=UPLOAD_RESPONSES
)
async def add_file_for_agent(
    request: Request,
    agent_id: str,
    asked: Asked,
    kind: Annotated[KnowledgeKind, Query()],
    level: Annotated[Visibility, Query()],
    department: Annotated[str, Query(max_length=60)] = "",
) -> KnowledgeAddedView | JSONResponse:
    """Add one file through the Knowledge page's door, and say whether this agent draws on it."""
    record = await answerable_agent(request, agent_id, asked)
    done = await upload(request, asked, kind, level, department)
    if isinstance(done, JSONResponse):
        return done
    log.info("agent knowledge added", route="upload", agent=agent_id, item=done.item_id)
    return added_answer(
        done,
        route=AddRoute.UPLOAD,
        scope=knowledge_scope_of(record),
        item=await added_item(request, asked, done.item_id),
    )


@router.post(
    LINK_PATH, status_code=201, response_model=KnowledgeAddedView, responses=UPLOAD_RESPONSES
)
async def add_link_for_agent(
    request: Request, agent_id: str, asked: Asked, link: Annotated[LinkAsked, Body()]
) -> KnowledgeAddedView | JSONResponse:
    """Add a web page by its link through the Knowledge page's door, and say whether this agent
    draws on it. The address is in the body, as the door requires, and the door refuses a private
    one on every redirect."""
    record = await answerable_agent(request, agent_id, asked)
    done = await add_link(request, asked, link)
    if isinstance(done, JSONResponse):
        return done
    log.info("agent knowledge added", route="link", agent=agent_id, item=done.item_id)
    return added_answer(
        done,
        route=AddRoute.LINK,
        scope=knowledge_scope_of(record),
        item=await added_item(request, asked, done.item_id),
    )


# ------------------------------------------------------------- retiring and fetching again
class KnowledgeRetiredView(BaseModel):
    """What retiring one document answers: which one, and what that means for every agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    said: str = THE_DOCUMENT_IS_RETIRED_FOR_EVERY_AGENT


class RefetchAsked(BaseModel):
    """What fetching a link again needs of the person: the new version's review date.

    The address is not in it. It is the one recorded when the link was added, so a caller cannot
    point a refetch at a different address than the document came from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_by: AwareDatetime


async def drawn_on_by(
    request: Request, agent_id: str, item_id: str, asked: Asking
) -> tuple[Authority, StoredItem]:
    """The document, when this reader may act on it and this agent's section lists it.

    Absent, in the sentence an act on a document the reader may not touch gets, for a document that
    does not exist, one they may not act on and one this agent does not draw on, so retiring or
    fetching again through an agent's page is never a way to learn that a document exists.
    """
    record = await answerable_agent(request, agent_id, asked)
    scope = knowledge_scope_of(record)
    factory = _require_session_factory(request)
    authority, seen, _ = await reader_stored_items(factory, asked.reach, asked.now)
    if scope is None:
        raise Absent(NOT_OFFERED)
    listed = frozenset(
        one.item_id for one in matching(scope, [knowledge_item_of(one) for one in seen])
    )
    found = next((one for one in seen if one.item_id == item_id), None)
    if found is None or found.item_id not in listed or not authority.may_act(found):
        raise Absent(NOT_OFFERED)
    return authority, found


@router.post(RETIRE_PATH, response_model=KnowledgeRetiredView, responses=LIFECYCLE_RESPONSES)
async def retire_for_agent(
    request: Request,
    agent_id: str,
    item_id: Annotated[str, Path(pattern=ITEM_ID_PATTERN)],
    asked: Asked,
) -> KnowledgeRetiredView | JSONResponse:
    """Retire one document this agent draws on, through the Knowledge page's own archive.

    The document is withdrawn for every agent and every person, kept on file with its history, and
    no longer drawn on from the transaction that archives it.
    """
    _, found = await drawn_on_by(request, agent_id, item_id, asked)
    done = await archive(request, asked, item_id)
    if isinstance(done, JSONResponse):
        return done
    log.info("agent knowledge retired", agent=agent_id, item=item_id)
    return KnowledgeRetiredView(item_id=item_id, title=found.title or item_id)


@router.post(
    REFETCH_PATH,
    status_code=201,
    response_model=VersionAddedView,
    responses=LIFECYCLE_RESPONSES,
)
async def refetch_for_agent(
    request: Request,
    agent_id: str,
    item_id: Annotated[str, Path(pattern=ITEM_ID_PATTERN)],
    asked: Asked,
    body: Annotated[RefetchAsked, Body()],
) -> VersionAddedView | JSONResponse:
    """Fetch the page a link was added from once more, as a newer version, because a person asked.

    See `A_LINK_IS_FETCHED_AGAIN_ONLY_WHEN_A_PERSON_ASKS`. The address is the one recorded when the
    link was added, through the link door's own fetch.
    """
    authority, found = await drawn_on_by(request, agent_id, item_id, asked)
    if body.review_by <= asked.now:
        return refused("review_by", "not_ahead", "the new version's review date has to be ahead")
    if found.kind is None:
        return refused("kind", "no_kind", "choose what kind of document the new version is")
    address = ""
    if found.arrived_as == ARRIVED_AS_LINK:

        async def recorded(session: AsyncSession) -> str:
            return await source_url_of(session, item_id)

        address = await in_transaction(request, asked, authority, recorded)
    if not address:
        return refused("item", "no_address", THERE_IS_NO_ADDRESS_TO_FETCH_AGAIN)
    try:
        placement = successor_place(found)
    except LifecycleError as exc:
        return refused("item", "no_new_version", str(exc))
    try:
        page = await asyncio.to_thread(
            receive_page,
            address,
            # Looked up on the module at the call, as the link door looks them up, so the one
            # transport and the one resolver are the link door's and a stand-in is stood in once.
            fetcher=knowledge_intake_routes.make_fetcher(),
            resolver=knowledge_intake_routes.make_resolver(),
        )
    except OfferedAsATable as exc:
        return refused("url", OFFERED_AS_A_TABLE, str(exc))
    except IngestRefused as exc:
        return refused("url", "not_added", str(exc))
    ledger, taken = await take_reading_slot(request, now=asked.now)
    if not taken.admitted:
        return too_busy(taken.decision, field="url")
    try:
        read = await asyncio.to_thread(
            read_link_for,
            page,
            kind=found.kind,
            placement=placement,
            owner_id=found.owner_id,
            taken_on=asked.now.date(),
        )
    except OfferedAsATable as exc:
        return refused("url", OFFERED_AS_A_TABLE, str(exc))
    except IngestRefused as exc:
        return refused("url", "not_added", str(exc))
    finally:
        await give_back(ledger, taken)
    if isinstance(read, ParseFailure):
        return refused("url", read.cause.value, read.message())
    chain = await in_transaction(
        request, asked, authority, lambda session: versions(session, item_id)
    )
    done = await write_successor(
        request,
        asked,
        authority,
        found,
        chain,
        read,
        body.review_by,
        already=THE_PAGE_HAS_NOT_CHANGED,
    )
    if not isinstance(done, JSONResponse):
        log.info("agent knowledge fetched again", agent=agent_id, item=done.item_id)
    return done
