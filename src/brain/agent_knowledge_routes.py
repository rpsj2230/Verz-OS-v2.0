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

Task ids: M39.9.1.1, M39.9.1.6
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict

from brain.agent_capability_routes import knowledge_item_of, knowledge_scope_of, reader_stored_items
from brain.agent_routes import _no_agent_here, _require_session_factory, _visible_record
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.reads import permitted
from brain.console.workspace import Tab, tab
from brain.console.workspace_capabilities import matching
from brain.knowledge.kinds import KIND_LABELS
from brain.knowledge.lifecycle import Authority, StoredItem
from brain.knowledge.lifecycle_store import names_of
from brain.knowledge.verification import disclose

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

# ------------------------------------------------------------------------ the figures
KNOWLEDGE_PATH: Final = "/agents/{agent_id}/knowledge"

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
    #: More of the reader's own list follows this page. Never how many.
    more: bool = False
    #: The reader's documents were read to their bound, so a later one may be missing.
    at_least: bool = False
    #: Set, with an empty list, when nothing here could look.
    unread: str = ""
    kept_rule: str = A_SECTION_LISTS_THE_COMPANYS_DOCUMENTS_AND_KEEPS_NONE


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


def item_view(one: StoredItem, *, asked: Asking, names: dict[str, str]) -> AgentKnowledgeItemView:
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
    )


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
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        if not may_read_knowledge_at(asked):
            log.info("agent knowledge not answerable", principal=asked.caller.principal.id)
            raise _no_agent_here()
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
        items=[item_view(one, asked=asked, names=names) for one in page],
        rule=[
            KnowledgeClauseView(field=clause.field, op=clause.op.value, value=str(clause.value))
            for clause in scope.predicate.clauses
        ],
        can_add=can_add,
        more=len(ordered) > offset + limit,
        at_least=full,
    )
