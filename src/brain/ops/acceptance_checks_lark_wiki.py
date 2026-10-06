"""The install acceptance check for a Lark Wiki answering on Ask: a declared space, its pages live.

One check, on the path a question takes to a wiki page. A space made up for the run is declared
the way Connect Lark's Wiki step declares one (`brain.ops.lark_wiki_spaces.declare_space`, a row of
`ops.setting` in the check's transaction), read back by `declared_spaces`, and searched by the
passage search the answer lane's model step reads through (`WikiPassages` behind `WithWiki`),
under a key leased and a token exchanged for the question. Every call is answered by
`_RecordedWiki` with bodies in Lark's documented envelopes; no socket is opened and no real key
is held (`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`).

What it proves: a page in the space is told to a reader its declared reach admits, and its text
is read from Lark when the question is asked; a page somebody restricted in Lark is never read
at all, not even its text; a reader outside the reach is told exactly what a question matching
no page is told; a reader with no read of the knowledge plane costs no call; and the text read
is in no table afterwards.

What it does not prove: that the model writes an answer from the passage, which is the model
lane's own check, and that the owner's Lark answers this install, which needs a space shared
with the app and declared in Connect Lark.

Task ids: M11.6.4
"""

from __future__ import annotations

import json
import secrets
import string
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_connectors import _Resolver, _search
from brain.ops.acceptance_checks_lark_base import HOST, _AppKeys, _Issuer
from brain.ops.acceptance_run import SET_UP_REACH

if TYPE_CHECKING:
    from collections.abc import Mapping

    from brain.ops.acceptance_run import Harness
    from brain.ops.connector_sync_run import SourceAnswer

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 315

A, B = RESERVED_DEPARTMENTS

#: The capability the knowledge plane is read with, restated from `brain.knowledge.search`.
KNOWLEDGE_READ: Final = "read:knowledge"

#: A wiki page's own read, which a reader needs beside the library's. See
#: `brain.agents.binding.A_WIKI_PAGE_HAS_A_READ_OF_ITS_OWN`.
WIKI_PAGE_READ: Final = "read:wiki_page"


def _both(scope: Scope) -> tuple[tuple[str, Scope], ...]:
    """The library's read and the wiki's own, in `scope`: what a reader of a wiki page holds."""
    return ((KNOWLEDGE_READ, scope), (WIKI_PAGE_READ, scope))


def _token(prefix: str) -> str:
    alphabet = string.ascii_letters + string.digits
    return prefix + "".join(secrets.choice(alphabet) for _ in range(20))


def _body(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")


@dataclass
class _Page:
    node: str
    document: str
    title: str
    text: str
    locked: bool


@dataclass
class _RecordedWiki:
    """`LarkCaller` answering one space's listing, its pages, their settings and their text."""

    space_id: str
    pages: tuple[_Page, ...]
    asked: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.asked.append(url)

        def ok(data: dict[str, Any]) -> SourceAnswer:
            return SourceAnswer(status=200, headers={}, body=_body({"code": 0, "data": data}))

        if not headers.get("Authorization", "").startswith("Bearer t-"):
            return SourceAnswer(status=200, headers={}, body=_body({"code": 99991663}))
        path, _, query = url.removeprefix(f"https://{HOST}").partition("?")
        by_node = {one.node: one for one in self.pages}
        by_document = {one.document: one for one in self.pages}
        if path == f"/open-apis/wiki/v2/spaces/{self.space_id}/nodes":
            items = [self._node(one) for one in self.pages]
            return ok({"items": items, "has_more": False, "page_token": ""})
        if path == "/open-apis/wiki/v2/spaces/get_node":
            token = query.removeprefix("token=")
            if token in by_node:
                return ok({"node": self._node(by_node[token])})
        if path.startswith("/open-apis/drive/v2/permissions/"):
            token = path.split("/")[5]
            if token in by_node:
                locked = by_node[token].locked
                return ok({"permission_public": {"lock_switch": locked}})
        if path.startswith("/open-apis/docx/v1/documents/") and path.endswith("/raw_content"):
            document = path.split("/")[5]
            if document in by_document:
                return ok({"content": by_document[document].text})
        return SourceAnswer(status=200, headers={}, body=_body({"code": 131006, "msg": "no"}))

    def _node(self, page: _Page) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "node_token": page.node,
            "obj_token": page.document,
            "obj_type": "docx",
            "parent_node_token": "",
            "has_child": False,
            "title": page.title,
        }


class _NoLibrary:
    """The knowledge library's search, answering nothing, so every passage is the Wiki's."""

    async def passages(self, question: str, *, entitlement: Any, now: Any) -> Any:
        from brain.core.envelope import TypedResult
        from brain.knowledge.document_tools import KnowledgePassage

        del question, entitlement
        return TypedResult[KnowledgePassage](records=(), source="knowledge", fetched_at=str(now))


@check(
    leaves=("M11.6.4",),
    sentence=(
        "A Lark Wiki space made up for the check is declared at one department's reach and "
        "searched through the answer lane's passage search: a page is read from Lark and told to "
        "a reader in that department, a page restricted in Lark is never read, a reader outside "
        "the reach is told what a missing page is told, and nothing read is kept."
    ),
)
async def a_lark_wiki_page_is_told_only_to_a_reader_its_space_admits(h: Harness) -> None:
    from brain.connectors.minimal_index import fresh_canary
    from brain.core.envelope import TypedResult
    from brain.knowledge.document_tools import KnowledgePassage
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.lark_wiki_live import WikiPassages, WithWiki
    from brain.ops.lark_wiki_spaces import DEPARTMENT, declare_space, declared_spaces
    from brain.tables.audit import attributed_to

    await h.found_departments()
    space_id = "".join(secrets.choice(string.digits) for _ in range(19))
    word = h.word()
    open_text, locked_text = fresh_canary("ACCEPTANCE"), fresh_canary("ACCEPTANCE")
    wiki = _RecordedWiki(
        space_id=space_id,
        pages=(
            _Page(_token("wikcn"), _token("doccn"), f"Renewals {word}", open_text, locked=False),
            _Page(_token("wikcn"), _token("doccn"), f"Salaries {word}", locked_text, locked=True),
        ),
    )
    async with h.sessions() as session, session.begin():
        for statement in attributed_to(
            actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        ):
            await session.execute(statement)
        await declare_space(session, space_id, reach=DEPARTMENT, department=A, updated_by=h.actor)
    declared = [one for one in await declared_spaces(h.sessions) if one.space_id == space_id]
    if len(declared) != 1:
        raise CheckFailedError("a space declared as Connect Lark declares one was not read back")

    search = WithWiki(
        _NoLibrary(),
        WikiPassages(
            HOST,
            lambda: _only(declared),
            keys=_AppKeys(),
            caller=wiki,
            resolver=_Resolver(),
            issuer=_Issuer(),
        ),
    )
    inside, outside, nobody = (
        h.principal(A, "support"),
        h.principal(B, "support"),
        h.principal(A, "guest"),
    )
    await h.person(inside, department=A, grants=_both(Scope.department(A)))
    await h.person(outside, department=B, grants=_both(Scope.department(B)))
    await h.person(nobody, department=A)

    async def ask(principal_id: str, question: str) -> TypedResult[KnowledgePassage]:
        reach = await _console(h, principal_id, second_factor=False)
        return await search.passages(question, entitlement=reach, now=h.now)

    told = await ask(inside, f"What do the renewals {word} pages say?")
    texts = " ".join(one.document for one in told.records)
    if open_text not in texts:
        raise CheckFailedError("a wiki page was not read from Lark for a reader its space admits")
    if locked_text in texts or any(wiki.pages[1].document in url for url in wiki.asked):
        raise CheckFailedError("a page restricted in Lark was read for an answer")
    withheld = await ask(outside, f"What do the renewals {word} pages say?")
    missing = await ask(outside, f"What do the {h.word()} pages say?")
    if withheld.records != missing.records or withheld.records:
        raise CheckFailedError("a wiki page was told to a reader outside its space's reach")
    before = len(wiki.asked)
    await ask(nobody, f"What do the renewals {word} pages say?")
    if len(wiki.asked) != before:
        raise CheckFailedError("the Wiki was read for a reader who reads no knowledge")
    if await _search(h, open_text):
        raise CheckFailedError("a wiki page's text read live was found in a table")


async def _only(declared: list[Any]) -> tuple[Any, ...]:
    return tuple(declared)
