"""A Lark Wiki switched on in Connect Lark, answering on Ask: its spaces, its pages read live.

`brain.connectors.lark_wiki` holds every rule about reading a wiki (the node listing and read, a
page's permission settings along its ancestry, its plain text, the tenant's shared minute) and
walks only the spaces somebody declared, at the reach declared for each (`SpaceDeclaration`). No
process called it. This is the application's half: which spaces are declared on this install,
the calls over one run's token, and the passage search the answer lane's model step reads, so a
question on Ask is answered from a wiki page the asker may open and from no other.

**A space is declared on Connect Lark's Wiki step, and this module reads the one declaration.**
Who on this install may be told a space's pages, and its steward, are kept by
`brain.ops.lark_wiki_spaces`, which the Connect Lark screen writes through and whose
`declared_spaces` this reader walks. There is one declaration of a space's reach, not a copy here
that could read a row the screen wrote differently. See that module's
`A_SPACE_IS_READ_ONLY_WHERE_SOMEBODY_DECLARED_ITS_REACH`.

**Visibility is Lark's own, twice over, and the install's once.** A page is read only when every
page from it to the space's root still follows the space (`lark_wiki.read_live` reads each
page's `lock_switch` live), so a page somebody restricted in Lark is never read here, and a page
whose settings could not be read is withheld rather than admitted. The declared reach then
decides who on this install may be told the page, by the same evaluator the knowledge library's
search uses (`brain.knowledge.search.Reach.admits`), so a department-reach page reaches that
department and a company page every reader of the knowledge plane. See
`A_WIKI_PAGE_IS_TOLD_ONLY_TO_A_READER_ITS_REACH_ADMITS`.

**Reading a page's own Lark lock is consistent with the owner's decision on visibility**
(needs-rupash 116: who may see is the Brain's own grants), because the lock only ever withholds
more: a page restricted in Lark is never read, so it can never widen what a grant admits. Pages a
question skipped are counted for an administrator (`WithheldPages`), never for the asker.

**Nothing is kept.** Pages are found by walking the declared spaces live and matching titles, and
each is read live when a question needs it (`lark_wiki.A_PAGE_IS_READ_LIVE_AND_NEVER_KEPT`): no
title, no path and no text reaches a table. The owner's rule is that a connector keeps a minimal
index and reads values live; the wiki's index is empty by its connector's own argument.

Task ids: M11.6.4
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

import structlog

from brain.connectors import lark_wiki
from brain.connectors.lark_base import LarkBaseBudgetError, MinuteBudget, fair_share_budget
from brain.connectors.lark_wiki import (
    PERMISSION_PATH,
    TEXT_PATH,
    LarkReply,
    NodeListRequest,
    NodeReadRequest,
    SpaceDeclaration,
    TextReadRequest,
    WikiDocument,
    declarations_by_space,
)
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.staff_directories import LARK_PLATFORMS
from brain.core.envelope import TypedResult
from brain.install import value_of
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, KnowledgePassage
from brain.knowledge.item import KnowledgeState
from brain.knowledge.search import KNOWLEDGE_READ, reach_for
from brain.ops.connectable import key_reference
from brain.ops.lark_base_index import LarkCaller, TokenIssuer, tenant_token
from brain.tools.fetch import Resolver, assert_fetchable

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.ops.connector_sync_run import ConnectorKeys

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a page read from Lark is still judged by the declared reach.
A_WIKI_PAGE_IS_TOLD_ONLY_TO_A_READER_ITS_REACH_ADMITS: Final = (
    "A page is read only when it and every page above it follow the space in Lark, and then it "
    "is told only to a reader the space's declared reach admits, by the evaluator the knowledge "
    "library's own search uses. A reader it does not admit is answered as though the page did "
    "not exist."
)

#: Why a title is matched on the question's longer words.
A_TITLE_IS_MATCHED_ON_THE_QUESTION_S_LONGER_WORDS: Final = (
    "A title matches when it holds one of the question's words, and a word of three letters or "
    "fewer (what, is, the, of) is in almost every title, so it would walk the tenant's minute "
    "into reading pages nobody asked about. Words of four letters or more are matched, and any "
    "run of two or more characters outside the Latin alphabet, which is how a title written in "
    "Chinese is found without a tokenizer deciding where its words end."
)

__all__ = [
    "A_TITLE_IS_MATCHED_ON_THE_QUESTION_S_LONGER_WORDS",
    "A_WIKI_PAGE_IS_TOLD_ONLY_TO_A_READER_ITS_REACH_ADMITS",
]

# ------------------------------------------------------------------------ the figures
#: The use Connect Lark names knowledge from Wiki by. Restated from `brain.ops.lark_connect.Use`,
#: which imports the routes' world, and held equal to it by a test.
LARK_WIKI_USE: Final = "knowledge_wiki"

#: How many of the question's words a title is matched on, at most.
MAX_WORDS: Final = 8

#: The longest passage of one page shown to the model. A page is one passage, cut here.
PASSAGE_CHARS: Final = 4000

_WORD: Final = re.compile(r"\w+", re.UNICODE)
_LATIN: Final = re.compile(r"^[A-Za-z0-9_]+$")


# ------------------------------------------------------------------------ switched on
def wiki_host(read: Callable[[str], str] = value_of) -> str | None:
    """The Lark open host the Wiki is read on, or None when knowledge from Wiki is off."""
    uses = {one.strip() for one in read("INSTALL_LARK_USES").split(",")}
    platform = read("INSTALL_LARK_PLATFORM").strip().lower()
    if LARK_WIKI_USE not in uses or platform not in LARK_PLATFORMS:
        return None
    return LARK_PLATFORMS[platform][1]


# --------------------------------------------------------------------------- the calls
def _reply(answer: Any) -> LarkReply:
    """A caller's answer as `lark_wiki` reads it. An unreadable body is no body."""
    import json

    if answer.timed_out or answer.connection_failed or answer.status is None:
        return LarkReply(status=503, body=None)
    try:
        body = json.loads(answer.body) if answer.body else None
    except ValueError:
        body = None
    return LarkReply(status=answer.status, body=body)


@dataclass
class WikiReads:
    """`lark_wiki.WikiReader` over one run's token, every address checked before it is called."""

    host: str
    caller: LarkCaller
    resolver: Resolver
    token: str = field(repr=False)

    def _get(self, path: str) -> LarkReply:
        checked = assert_fetchable(f"https://{self.host}{path}", self.resolver)
        answer = self.caller.get(
            checked.url,
            address=checked.address,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            max_bytes=MAX_RESPONSE_BYTES,
        )
        return _reply(answer)

    def list_nodes(self, request: NodeListRequest) -> LarkReply:
        query = f"page_size={request.page_size}"
        if request.parent_node_id:
            query += f"&parent_node_token={request.parent_node_id}"
        if request.cursor:
            query += f"&page_token={request.cursor}"
        return self._get(f"/open-apis/wiki/v2/spaces/{request.space_id}/nodes?{query}")

    def read_node(self, request: NodeReadRequest) -> LarkReply:
        return self._get(f"/open-apis/wiki/v2/spaces/get_node?token={request.node_id}")

    def read_permission(self, request: NodeReadRequest) -> LarkReply:
        return self._get(PERMISSION_PATH.format(token=request.node_id))

    def read_text(self, request: TextReadRequest) -> LarkReply:
        return self._get(TEXT_PATH.format(document_id=request.object_id))


# ------------------------------------------------------------------------ the search
def words_of(question: str) -> tuple[str, ...]:
    """The words a title is matched on. See `A_TITLE_IS_MATCHED_ON_THE_QUESTION_S_LONGER_WORDS`."""
    kept: list[str] = []
    for word in _WORD.findall(question):
        latin = bool(_LATIN.match(word))
        if (latin and len(word) >= 4) or (not latin and len(word) >= 2):
            folded = word.casefold()
            if folded not in kept:
                kept.append(folded)
    return tuple(kept[:MAX_WORDS])


def told_to(document: WikiDocument, entitlement: EntitlementSet, now: datetime) -> bool:
    """Whether this reader may be told this page, by the library search's own evaluator.

    See `A_WIKI_PAGE_IS_TOLD_ONLY_TO_A_READER_ITS_REACH_ADMITS`.
    """
    visibility = document.page.visibility
    departments = (visibility.department,) if visibility.department else ()
    reach = reach_for(entitlement, departments=departments, now=now)
    if reach is None:
        return False
    row = {
        "state": KnowledgeState.PUBLISHED.value,
        "visibility": visibility.level.value,
        "department": visibility.department or None,
        "owner_id": document.page.owner_id,
    }
    return reach.admits(row)


def passage_of(document: WikiDocument, *, now: datetime) -> KnowledgePassage:
    """One page as the passage the model step is shown, tagged for the passage policy."""
    visibility = document.page.visibility
    return KnowledgePassage(
        entity=KNOWLEDGE_ENTITY,
        id=document.item_id,
        document_id=document.item_id,
        title=document.title,
        section=" / ".join(document.path),
        document=document.text[:PASSAGE_CHARS],
        updated_at=now.isoformat(),
        department=visibility.department or None,
        visibility=visibility.level.value,
        owner_id=document.page.owner_id or None,
    )


#: What the Connect Lark screen says beside the count of pages skipped, to an administrator.
PAGES_SKIPPED_ARE_COUNTED_FOR_ADMINISTRATORS: Final = (
    "Wiki pages a question matched and did not read, because the page or one above it is "
    "restricted in Lark, its permission settings could not be read, or its space was not declared, "
    "counted by this application process since it started. Shown to an administrator and never to "
    "a person asking: to them a skipped page reads exactly as a page that is not there."
)


@dataclass
class WithheldPages:
    """How many matched pages this process skipped, by reason. One per process, on its state.

    For an administrator (`PAGES_SKIPPED_ARE_COUNTED_FOR_ADMINISTRATORS`). A count of what one
    person was not told is exactly what `DENIED and ABSENT must be indistinguishable` forbids
    showing them; this is the operator's count over every question, which names no page, no space
    and no asker.
    """

    by_reason: Counter[str] = field(default_factory=Counter)

    def note(self, reason: str) -> None:
        self.by_reason[reason] += 1

    @property
    def total(self) -> int:
        return sum(self.by_reason.values())


class WikiPassages:
    """`brain.gate.model_lane.PassageSearch` over the declared spaces, read live for each question.

    Asks nothing of Lark for a reader who holds no read of the knowledge plane, or when no space
    is declared: both are answered with no passage and no call. Everything else is one run under
    one token and the question's share of the tenant's minute.
    """

    def __init__(
        self,
        host: str,
        spaces: Callable[[], Awaitable[tuple[SpaceDeclaration, ...]]],
        *,
        keys: ConnectorKeys,
        caller: LarkCaller,
        resolver: Resolver,
        issuer: TokenIssuer,
        budget: Callable[[], MinuteBudget] = fair_share_budget,
        withheld: WithheldPages | None = None,
    ) -> None:
        self._host = host
        self._spaces = spaces
        self._keys = keys
        self._caller = caller
        self._resolver = resolver
        self._issuer = issuer
        self._budget = budget
        self._withheld = WithheldPages() if withheld is None else withheld

    def __repr__(self) -> str:
        return "WikiPassages()"

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        empty = TypedResult[KnowledgePassage](
            records=(), source=lark_wiki.LARK_WIKI, fetched_at=now.isoformat()
        )
        words = words_of(question)
        if not words or entitlement.scope_for(KNOWLEDGE_READ, now) is None:
            return empty
        declared = await self._spaces()
        if not declared:
            return empty
        documents = await asyncio.to_thread(self.read, words, declared, now)
        told = tuple(
            passage_of(one, now=now) for one in documents if told_to(one, entitlement, now)
        )
        return TypedResult[KnowledgePassage](
            records=told, source=lark_wiki.LARK_WIKI, fetched_at=now.isoformat()
        )

    def read(
        self, words: Sequence[str], declared: Sequence[SpaceDeclaration], now: datetime
    ) -> tuple[WikiDocument, ...]:
        """The pages whose titles hold the words, each read live, in one run under one token."""
        spaces = declarations_by_space(declared)
        with tenant_token(
            key_reference(lark_wiki.LARK_WIKI),
            self._host,
            keys=self._keys,
            issuer=self._issuer,
            now=now,
        ) as exchanged:
            if isinstance(exchanged, str):
                log.warning("lark_wiki.unread", why=exchanged)
                return ()
            reader = WikiReads(
                host=self._host,
                caller=self._caller,
                resolver=self._resolver,
                token=exchanged.token,
            )
            found: list[WikiDocument] = []
            try:
                search = lark_wiki.find_pages(
                    reader, spaces=spaces, words=words, budget=self._budget()
                )
                spent = search.budget
                for node in search.matches:
                    if spent.is_exhausted:
                        break
                    try:
                        read = lark_wiki.read_live(
                            reader, node.node_id, spaces=spaces, budget=spent
                        )
                    except lark_wiki.PageWithheldError as withheld:
                        # For an operator; to the asker, exactly a page that is not there.
                        log.info("lark_wiki.page_withheld", reason=withheld.reason.value)
                        self._withheld.note(withheld.reason.value)
                        continue
                    spent = read.budget
                    if read.document is not None:
                        found.append(read.document)
            except (
                lark_wiki.LarkWikiError,
                lark_wiki.LarkWikiUnreachableError,
                lark_wiki.LarkWikiRefusedError,
                LarkBaseBudgetError,
            ) as failed:
                log.warning("lark_wiki.unread", error=type(failed).__name__)
            return tuple(found)


class WithWiki:
    """`PassageSearch` over the knowledge library and the Wiki: the library's passages first."""

    def __init__(self, library: Any, wiki: WikiPassages) -> None:
        self._library = library
        self._wiki = wiki

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        own = await self._library.passages(question, entitlement=entitlement, now=now)
        wiki = await self._wiki.passages(question, entitlement=entitlement, now=now)
        return TypedResult[KnowledgePassage](
            records=(*own.records, *wiki.records),
            source=own.source,
            fetched_at=own.fetched_at,
            truncated=own.truncated,
        )
