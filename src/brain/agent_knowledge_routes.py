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

**What an item was added by is its steward.** `know.item` records who answers for a document and
when it was created, and nothing about whether it arrived as a file or as a link: the page's
address is the first line of its text, which a list does not read. So `place` says where the
document sits, which is what a person asks next, and the way it arrived is left out rather than
guessed. See `NO_SOURCE_IS_RECORDED_BESIDE_AN_ITEM_SO_NONE_IS_INVENTED`.

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

**A document is replaced by a new version through the Knowledge page's own route, and only there.**
The section only says which documents the reader may replace (`Authority.may_act`, the page's own
answer: its steward, or an administrator where it sits) and the page's own form posts to
`POST /knowledge/items/{item_id}/versions`, which refuses whoever may not as it always has. There is
no second route and no second rule, because a document is the company's and not the agent's: the new
version supersedes the old one for every agent and every person at once, which is the Knowledge
page's argument for it.

Task ids: M39.9.1.5, M39.9.1.1, M39.9.1.2, M39.9.1.3, M39.9.1.4, M39.9.1.6
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.agent_capability_routes import knowledge_item_of, knowledge_scope_of, reader_stored_items
from brain.agent_routes import _no_agent_here, _require_session_factory, _visible_record
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.agent_tabs import AddRoute, plan_addition
from brain.console.reads import permitted
from brain.console.workspace import Tab, tab
from brain.console.workspace_capabilities import KnowledgeScope, item_row, matching
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.kinds import KIND_LABELS, KnowledgeKind
from brain.knowledge.lifecycle import Authority, StoredItem, authority_for
from brain.knowledge.lifecycle_store import as_person, live_item, names_of
from brain.knowledge.verification import disclose
from brain.knowledge.visibility import Visibility
from brain.knowledge_intake_routes import LinkAsked, add_link
from brain.knowledge_routes import UPLOAD_RESPONSES, UploadedView, live_departments, upload

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why this section lists documents and keeps none.
A_SECTION_LISTS_THE_COMPANYS_DOCUMENTS_AND_KEEPS_NONE: Final = (
    "An item shown in an agent's Knowledge section is one of the company's documents, read at "
    "the reader's own reach and narrowed by the agent's rule. The agent owns no store of its own: "
    "an agent is a lens and never a principal, so nobody reads through one a document they could "
    "not open anywhere else, and a document added from this page is the company's like any other."
)

#: Why no way of arriving is shown beside an item.
NO_SOURCE_IS_RECORDED_BESIDE_AN_ITEM_SO_NONE_IS_INVENTED: Final = (
    "A document's row records its steward, its place and when it was made, and not whether it "
    "arrived as a file or as a link, so the list says where it sits and leaves the way it arrived "
    "out rather than reading its text to guess."
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

#: What they are told when the rule is not about where documents sit, so reaching cannot be said.
THE_AGENT_CANNOT_SAY_WHAT_IT_REACHES: Final = (
    "Added to the company's documents. This agent's rule is not about where documents sit, so "
    "whether it draws on this one cannot be said here."
)

# ------------------------------------------------------------------------ the figures
KNOWLEDGE_PATH: Final = "/agents/{agent_id}/knowledge"
UPLOAD_PATH: Final = "/agents/{agent_id}/knowledge/uploads"
LINK_PATH: Final = "/agents/{agent_id}/knowledge/links"

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
    #: Whether this reader may replace it with a newer version: the Knowledge page's own answer,
    #: `Authority.may_act`, which is its steward or an administrator where it sits.
    can_replace: bool = False
    #: Whether this agent's rule reaches it. Every listed item is reached; the field is the
    #: contract the add answer shares, so the page draws one shape for both.
    reached: bool = True


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
    one: StoredItem, *, asked: Asking, names: dict[str, str], can_replace: bool = False
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
        can_replace=can_replace,
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
    return AgentKnowledgeView(
        agent_id=agent_id,
        items=[
            item_view(one, asked=asked, names=names, can_replace=authority.may_act(one))
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
