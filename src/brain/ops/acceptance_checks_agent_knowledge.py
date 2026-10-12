"""Install checks for an agent's Knowledge section: what it lists, what adding does, and whether the
agent then answers from what was added and cites it.

The unit tests prove each route over a stub pool and the add forms over a stand-in door. What they
cannot prove is that on an install, over the product's own tables, a person who may add documents
adds a file and a web page from an agent's page and is told whether the agent draws on each; that a
colleague with another reach sees neither; and that a person asking the agent then gets an answer
from the file that cites it. These checks call the section's own routes as reserved people, and the
door behind them is the Knowledge page's, which is the claim.

**The routes are called, not their pieces.** `agent_knowledge`, `add_file_for_agent` and
`add_link_for_agent` take the request a person's browser would make, with a body and the headers the
door reads, so what is proved is the route and everything it calls. `brain.ops.acceptance_ingest`
does the same for the table-offer refusal.

**The embedding queue is held out of reach, and why.** The door's `store_upload` hands an embedding
job to the install's job queue on its own connection when the install embeds, and a queue write is
not part of the check's transaction, so a rolled-back document would leave a job for a document
that does not exist. The checks call the door with `ingest_document` as the harness's own
`_upload` calls it: with no revision and a queue that raises, so a path that reached the queue
would fail the check rather than write to it. The patch is restored in a `finally`.

**The link's page is a stand-in, said so.** A link is fetched once from the network by the door, and
a check may reach no real site, so the fetcher and the resolver the door asks are replaced for the
length of the check by a page the check holds. The address rule and the page's parse are the
product's own; what is not proved is the fetch over a real connection, so M39.9.1.3 is held in
`docs/proof-sweep-holds.json` until an install shows it against a real page.

**A private address is refused by the product's own rule, with no stand-in.** A link whose address
is a literal private one never reaches the fetcher, which the check asks.

**The count is checked inside the transaction's own switch.** `agent_item_counts` is turned on for
the length of the check and rolled back with it, so the install's own switch is never touched and
the answer is counted as it would be on an install that had turned it on. See
`brain.ops.agent_item_use`.

Task ids: M39.9.1.1, M39.9.1.2, M39.9.1.3, M39.9.1.4, M39.9.1.6, M39.9.1.8, M39.2.3.5
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast
from urllib.parse import quote

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.agent_knowledge_routes import AgentKnowledgeView, KnowledgeAddedView
    from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page: after every module that comes before it.
CHECK_ORDER: Final = 510

A, B = RESERVED_DEPARTMENTS

#: The page a stand-in site answers with. A heading and a paragraph holding one unique word.
STAND_IN_ADDRESS: Final = "https://acceptance.example.test/handover"

#: A private address, as a literal, so no name is ever looked up.
PRIVATE_ADDRESS: Final = "https://169.254.169.254/latest/meta-data/"


def _tab_and_planes() -> list[tuple[str, Scope]]:
    from brain.console.reads import Plane, plane_capability
    from brain.ops.acceptance_checks_agent_page import _tab_read

    return [
        (one, Scope.unrestricted())
        for one in (_tab_read("knowledge"), *(plane_capability(plane).value for plane in Plane))
    ]


def _app(h: Harness) -> FastAPI:
    from fastapi import FastAPI

    app = FastAPI()
    app.state.db_sessions = h.sessions
    app.state.takeovers = None
    app.state.tools = None
    return app


def _request(
    app: FastAPI,
    path: str,
    *,
    method: str = "GET",
    body: bytes = b"",
    headers: Sequence[tuple[str, str]] = (),
) -> Any:
    from starlette.requests import Request

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    sent = [(name.lower().encode(), value.encode()) for name, value in headers]
    scope = {"type": "http", "app": app, "headers": sent, "method": method, "path": path}
    return Request(scope, receive)


async def _list(h: Harness, app: FastAPI, agent_id: str, who: str) -> AgentKnowledgeView:
    """The section's own route, as this person reads it."""
    from brain.agent_knowledge_routes import agent_knowledge
    from brain.ops.acceptance_checks_agent_page import _asking

    request = _request(app, f"/api/v1/agents/{agent_id}/knowledge")
    return await agent_knowledge(request, agent_id, await _asking(h, who))


async def _add_file(
    h: Harness, app: FastAPI, agent_id: str, who: str, *, department: str, body: bytes, name: str
) -> KnowledgeAddedView:
    """A Markdown file sent to the section's add route, as the browser sends it."""
    from brain.agent_knowledge_routes import add_file_for_agent
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_routes import NAME_HEADER
    from brain.ops.acceptance_checks_agent_page import _asking

    request = _request(
        app,
        f"/api/v1/agents/{agent_id}/knowledge/uploads",
        method="POST",
        body=body,
        headers=[
            ("content-type", "text/markdown"),
            ("content-length", str(len(body))),
            (NAME_HEADER, quote(name)),
        ],
    )
    answered = await add_file_for_agent(
        request,
        agent_id,
        await _asking(h, who),
        KnowledgeKind.SOP,
        Visibility.DEPARTMENT,
        department,
    )
    return _added(answered)


async def _add_link(
    h: Harness, app: FastAPI, agent_id: str, who: str, *, department: str, address: str
) -> Any:
    """A link sent to the section's add route. The answer, or the door's refusal as it came."""
    from brain.agent_knowledge_routes import add_link_for_agent
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_intake_routes import LinkAsked
    from brain.ops.acceptance_checks_agent_page import _asking

    request = _request(app, f"/api/v1/agents/{agent_id}/knowledge/links", method="POST")
    return await add_link_for_agent(
        request,
        agent_id,
        await _asking(h, who),
        LinkAsked(
            url=address,
            kind=KnowledgeKind.SERVICE_PACKAGE,
            level=Visibility.DEPARTMENT,
            department=department,
        ),
    )


def _added(answered: Any) -> KnowledgeAddedView:
    from brain.agent_knowledge_routes import KnowledgeAddedView

    if not isinstance(answered, KnowledgeAddedView):
        raise CheckFailedError("a file or page added from the section was refused by the door")
    return answered


class _NoQueue:
    """What the door is handed in place of its embedding queue: it may not be asked for one."""

    async def __call__(self, job: object) -> object:
        raise CheckFailedError("a document added from the section queued work for a worker")


class _HeldDoor:
    """The door with its embedding queue held out of reach, restored on exit. See the module."""

    def __enter__(self) -> None:
        from brain import knowledge_routes
        from brain.knowledge.embed_policy import REVISION_SETTING, REVISION_UNSET

        self._real = getattr(knowledge_routes, "ingest_document")  # noqa: B009
        real = self._real

        async def held(*args: Any, **kwargs: Any) -> Any:
            return await real(
                *args,
                **{**kwargs, "enqueue": _NoQueue(), "env": {REVISION_SETTING: REVISION_UNSET}},
            )

        setattr(knowledge_routes, "ingest_document", held)  # noqa: B010

    def __exit__(self, *_: object) -> None:
        from brain import knowledge_routes

        setattr(knowledge_routes, "ingest_document", self._real)  # noqa: B010


class _StandInSite:
    """The page a link answers with, and every address the door asked it for."""

    def __init__(self, page: bytes) -> None:
        self.page = page
        self.asked: list[str] = []

    def get_once(self, url: str, *, address: str, max_bytes: int) -> Any:
        from brain.tools.fetch import FetchedBytes

        self.asked.append(url)
        return FetchedBytes(body=self.page, final_url=url)


class _PublicNames:
    """A resolver answering one public address for every name, so no lookup leaves the server."""

    def resolve(self, host: str) -> Sequence[str]:
        return ["93.184.216.34"]


class _HeldSite:
    """The door's fetcher and resolver, replaced for the length of the check and then restored."""

    def __init__(self, site: _StandInSite) -> None:
        self.site = site

    def __enter__(self) -> None:
        from brain import knowledge_intake_routes as intake

        self._fetcher, self._resolver = intake.make_fetcher, intake.make_resolver
        setattr(intake, "make_fetcher", lambda: self.site)  # noqa: B010
        setattr(intake, "make_resolver", _PublicNames)  # noqa: B010

    def __exit__(self, *_: object) -> None:
        from brain import knowledge_intake_routes as intake

        setattr(intake, "make_fetcher", self._fetcher)  # noqa: B010
        setattr(intake, "make_resolver", self._resolver)  # noqa: B010


def _page(word: str) -> bytes:
    return (
        "<html><head><title>Acceptance handover page</title></head><body><main>"
        f"<h1>Acceptance handover</h1><p>{word} is the handover word.</p></main></body></html>"
    ).encode()


def _document(h: Harness) -> tuple[str, bytes]:
    """A Markdown file pairing two words nothing else holds, and the first of them."""
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.acceptance_models import PAIRED

    key, value = h.word(), h.word()
    return key, a_markdown_document("Acceptance check", PAIRED.format(key=key, value=value))


# ----------------------------------------------------------- 1. the section lists and adds
@check(
    leaves=("M39.9.1.1", "M39.9.1.2", "M39.9.1.4", "M39.9.1.6"),
    sentence=(
        "A person who may add in acceptance_a and acceptance_b adds a file from an agent's "
        "Knowledge section: the acceptance_a one is told the agent draws on it, the "
        "acceptance_b one is added and told it does not, naming the clause. The section lists "
        "the first to the adder and a colleague, nothing to a reader of acceptance_b alone, a "
        "missing agent to a person without the tab, and no count."
    ),
)
async def knowledge_lists_by_reach_and_adding_says_what_follows(
    h: Harness,
) -> None:
    from brain.agent_knowledge_routes import (
        THE_AGENT_DOES_NOT_DRAW_ON_WHAT_WAS_ADDED,
        THE_AGENT_DRAWS_ON_WHAT_WAS_ADDED,
        AgentKnowledgeView,
    )
    from brain.core.department import membership_scope
    from brain.core.errors import Absent
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
    from brain.ops.acceptance_workspace import installed_agent

    await h.found_departments()
    steward = h.principal(A, "steward")
    colleague = h.principal(A, "colleague")
    outsider = h.principal(A, "outsider")
    without = h.principal(A, "without")
    both = membership_scope([A, B])
    await h.person(
        steward,
        department=A,
        grants=[
            *_tab_and_planes(),
            *((one, both) for one in (*KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value)),
        ],
    )
    await h.person(colleague, department=A, grants=[*_tab_and_planes(), *_in(A, *KNOWLEDGE_READS)])
    await h.person(outsider, department=A, grants=[*_tab_and_planes(), *_in(B, *KNOWLEDGE_READS)])
    await h.person(without, department=A, grants=[])
    agent_id = await installed_agent(h, steward)
    app = _app(h)

    # Nothing to draw on yet, and the section still answers: its empty state is not a refusal.
    empty = await _list(h, app, agent_id, steward)
    if empty.items or not empty.can_add:
        raise CheckFailedError(
            "an agent with nothing to draw on was not answered with an empty list"
        )

    inside_key, inside_body = _document(h)
    outside_key, outside_body = _document(h)
    with _HeldDoor():
        inside = await _add_file(
            h, app, agent_id, steward, department=A, body=inside_body, name="Inside.md"
        )
        outside = await _add_file(
            h, app, agent_id, steward, department=B, body=outside_body, name="Outside.md"
        )
    if not inside.reached or inside.said != THE_AGENT_DRAWS_ON_WHAT_WAS_ADDED or inside.blocking:
        raise CheckFailedError(
            "a file added where the agent's rule reaches was not said to be reached"
        )
    if outside.reached or outside.said != THE_AGENT_DOES_NOT_DRAW_ON_WHAT_WAS_ADDED:
        raise CheckFailedError("a file added outside the agent's rule was said to be reached")
    if [(one.field, one.value) for one in outside.blocking] != [("department", A)] or not (
        outside.can_widen
    ):
        raise CheckFailedError("an unreached file did not name the clause that excludes it")

    listed = {who: await _list(h, app, agent_id, who) for who in (steward, colleague, outsider)}
    for who in (steward, colleague):
        if [one.item_id for one in listed[who].items] != [inside.item_id]:
            raise CheckFailedError(
                "a reader of acceptance_a was not listed exactly the reached file"
            )
    if outside.item_id in {one.item_id for view in listed.values() for one in view.items}:
        raise CheckFailedError("a file outside the agent's rule was listed as one it draws on")
    if listed[outsider].items or listed[outsider].unread or listed[outsider].more:
        raise CheckFailedError(
            "a reader of acceptance_b alone was told anything about acceptance_a"
        )
    if not listed[steward].can_add or listed[colleague].can_add or listed[outsider].can_add:
        raise CheckFailedError("the ways to add were not offered to exactly the person who may add")
    for view in listed.values():
        said = set(json.loads(view.model_dump_json()))
        if said != set(AgentKnowledgeView.model_fields) or any(
            "count" in name or "total" in name or "hidden" in name for name in said
        ):
            raise CheckFailedError(
                "the section carried a field that could hold a count of what is hidden"
            )
    one = listed[steward].items[0]
    if (one.added_by != steward or one.place != A or one.verification != "unverified") or not (
        one.kind_label and one.added_at is not None
    ):
        raise CheckFailedError(
            "a listed file did not say who added it, where it sits and its badge"
        )

    # A reader without the tab is answered as an agent that does not exist, in the same words.
    try:
        await _list(h, app, agent_id, without)
    except Absent as refused:
        try:
            await _list(h, app, "acceptance-agent-nobody-made", without)
        except Absent as missing:
            if refused.public_message != missing.public_message:
                raise CheckFailedError(
                    "a reader without the tab was refused unlike a missing agent"
                ) from None
        else:
            raise CheckFailedError("an agent that does not exist was answered") from None
    else:
        raise CheckFailedError("a reader without the Knowledge tab was shown the section")

    # A person who may add nowhere is refused by the door itself, as on the Knowledge page.
    try:
        with _HeldDoor():
            await _add_file(
                h, app, agent_id, colleague, department=A, body=inside_body, name="Again.md"
            )
    except Absent:
        pass
    else:
        raise CheckFailedError("a reader who may not add was let add from the section")
    if inside_key == outside_key:
        raise CheckFailedError("the two files a check adds were not told apart")


# ------------------------------------------------------------------ 2. a web page by its link
@check(
    leaves=("M39.9.1.3",),
    sentence=(
        "A person adds a web page by its link from an agent's Knowledge section: the page is "
        "fetched once, kept as the company's own copy in acceptance_a and listed beside the "
        "agent as one it draws on, and a link to a private address is refused by the same door "
        "in its own words and adds nothing."
    ),
)
async def a_link_is_fetched_once_and_a_private_address_is_refused(
    h: Harness,
) -> None:
    from brain.agent_knowledge_routes import THE_AGENT_DRAWS_ON_WHAT_WAS_ADDED
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
    from brain.ops.acceptance_workspace import installed_agent

    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(
        steward,
        department=A,
        grants=[*_tab_and_planes(), *_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value)],
    )
    agent_id = await installed_agent(h, steward)
    app = _app(h)
    word = h.word()
    site = _StandInSite(_page(word))
    with _HeldDoor(), _HeldSite(site):
        added = _added(
            await _add_link(h, app, agent_id, steward, department=A, address=STAND_IN_ADDRESS)
        )
        before = [one.item_id for one in (await _list(h, app, agent_id, steward)).items]
        refused = await _add_link(h, app, agent_id, steward, department=A, address=PRIVATE_ADDRESS)
        after = [one.item_id for one in (await _list(h, app, agent_id, steward)).items]
    if site.asked != [STAND_IN_ADDRESS]:
        raise CheckFailedError(
            "a web page was not fetched exactly once, or a private address was fetched"
        )
    if (
        not added.reached
        or added.said != THE_AGENT_DRAWS_ON_WHAT_WAS_ADDED
        or added.route != "link"
    ):
        raise CheckFailedError(
            "a web page added where the agent's rule reaches was not said to be reached"
        )
    if before != [added.item_id]:
        raise CheckFailedError("the page added by its link was not listed beside the agent")
    told = json.loads(bytes(getattr(refused, "body", b"{}")) or b"{}")
    problems = told.get("problems") or [{}]
    if (
        getattr(refused, "status_code", 0) != 422
        or problems[0].get("code") != "not_added"
        or "address check" not in str(told.get("message", ""))
    ):
        raise CheckFailedError("a link to a private address was not refused by the address check")
    if after != before:
        raise CheckFailedError("a refused link changed what the agent draws on")


# ------------------------------------------------- 3. the agent answers from it and cites it
@check(
    leaves=("M39.9.1.8", "M39.2.3.5"),
    sentence=(
        "A file added from an agent's Knowledge section is then answered from: a member of "
        "acceptance_a asking the agent a question the file answers is answered from it and the "
        "answer cites that file; and with counting switched on for the length of the check the "
        "section then shows the file as cited once, and with it off shows no figure at all."
    ),
)
async def an_agent_answers_from_a_file_added_on_its_page_and_cites_it(h: Harness) -> None:
    from brain.api_routes import counted_citations
    from brain.ops.acceptance_answers import _document_of, asking_with_a_stand_in
    from brain.ops.acceptance_checks import KNOWLEDGE_READS
    from brain.ops.acceptance_models import ASKED, asked
    from brain.ops.acceptance_workspace import installed_agent
    from brain.ops.features import AGENT_ITEM_COUNTS, switch

    s = await asking_with_a_stand_in(h)
    adder = s.library
    # The library keeper holds the knowledge administration of acceptance_a, which is where a
    # person may add, and reads what they add; the member reads it and asks.
    for capability in KNOWLEDGE_READS:
        await h.grant(adder, capability, Scope.department(A))
    for capability, scope in _tab_and_planes():
        await h.grant(adder, capability, scope)
        await h.grant(s.reader, capability, scope)
    agent_id = await installed_agent(h, adder, suffix="knowledge")
    app = _app(h)
    key, body = _document(h)
    with _HeldDoor():
        added = await _add_file(h, app, agent_id, adder, department=A, body=body, name="Asked.md")
    if not added.reached:
        raise CheckFailedError(
            "a file added where the agent's rule reaches was not said to be reached"
        )
    document_id, _ = await _document_of(h, s.reader, key)
    if document_id != added.item_id:
        raise CheckFailedError(
            "the file added from the section was not the document found for its word"
        )

    answered = await asked(
        h, s.app, s.reader, ASKED.format(key=key), 1, agent=agent_id, at=datetime.now(UTC)
    )
    if answered.composed is None or answered.provenance is None:
        raise CheckFailedError("a question the added file answers was not answered")
    cited = {one.view().get("document_id") for one in answered.provenance.documents}
    if cited != {added.item_id}:
        raise CheckFailedError("the answer did not cite the file added from the agent's page")

    # Off, the section carries no figure; counting is switched on only inside this transaction.
    view = await _list(h, app, agent_id, s.reader)
    if view.use_figures is not None or any(one.uses is not None for one in view.items):
        raise CheckFailedError("a figure was drawn while nothing is counted")
    async with h.sessions() as session, session.begin():
        await switch(session, AGENT_ITEM_COUNTS, on=True, by=adder)
    state = SimpleNamespace(db_sessions=h.sessions)
    await counted_citations(state, agent_id, cast(Any, answered), now=datetime.now(UTC))
    counted = await _list(h, app, agent_id, s.reader)
    figures = {one.item_id: one.uses for one in counted.items}
    if counted.use_figures is None or figures.get(added.item_id) != 1:
        raise CheckFailedError("the file the answer cited was not counted once beside the agent")
    if any(uses != 0 for item_id, uses in figures.items() if item_id != added.item_id):
        raise CheckFailedError("a document the answer did not cite was counted as cited")
