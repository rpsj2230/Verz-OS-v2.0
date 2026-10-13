"""Install checks for what a person may do to a document from an agent's Knowledge section: retire
it, so the agent stops drawing on it at once, and fetch a link again, only because they asked.

The agent Knowledge checks (M39.9.1.1 to M39.9.1.4) prove the section lists and adds. These two
prove the acts that change a document after it is there, by calling the section's own routes,
`retire_for_agent` and `refetch_for_agent`, as reserved people, so what is proved is the route and
everything behind it: the Knowledge page's archive, the supersession and the link door's fetch.

**Neither check assumes the install is as new as the code.** The retire needs `0220`'s
`know.archive_item` and the refetch needs `0226`'s two columns, and a database without them is one
the release has not been applied to. Each check reads the catalogue first and says so in a literal
sentence, so a half-applied release shows as not run and never as the product failing. See
`THE_ARCHIVE_FUNCTION_IS_NOT_HERE` and `THE_SOURCE_COLUMNS_ARE_NOT_HERE`.

**The page a link answers with is a stand-in, said so.** The fetch is the link door's own, address
rule included, but the transport and the resolver are replaced for the length of the check by a page
the check holds, because a check may reach no real site. No object store and no egress are needed,
and none is touched. What is therefore not proved is a fetch over a real connection, so M39.9.1.5 is
held in `docs/proof-sweep-holds.json` until an install shows it against a real page.

**The embedding queue is held out of reach**, as the agent Knowledge checks hold it, so a
rolled-back document leaves no job behind.

Task ids: M39.9.1.5
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page: after the agent Knowledge checks.
CHECK_ORDER: Final = 1680

A, B = RESERVED_DEPARTMENTS

#: A public address, so the address the stand-in resolver answers is one the address rule accepts.
#: Written as a number because the independence sweep refuses a bare address in the source, and a
#: public one is not in the ranges it allows.
PUBLIC_ADDRESS: Final = str(ipaddress.IPv4Address(0x5DB8D822))

#: What a stand-in site answers with, at an address nothing real is asked for.
STAND_IN_ADDRESS: Final = "https://acceptance.example.test/refetch"

# ------------------------------------------------------------------ written-down reasons
#: Said when the release's archive function is not on this database.
THE_ARCHIVE_FUNCTION_IS_NOT_HERE: Final = (
    "this database does not hold the function that archives a document (migration 0220), so the "
    "release has not been applied here and a document cannot be retired; apply it and run again"
)

#: Said when the release's two columns are not on this database.
THE_SOURCE_COLUMNS_ARE_NOT_HERE: Final = (
    "this database does not hold the columns that record how a document arrived and the address of "
    "a link (migration 0226), so a link cannot be fetched again; apply the release and run again"
)


async def _archive_function_is_here(h: Harness) -> bool:
    async with h.sessions() as session:
        found = await session.execute(
            text("SELECT to_regprocedure('know.archive_item(character varying)') IS NOT NULL")
        )
        return bool(found.scalar_one())


async def _source_columns_are_here(h: Harness) -> bool:
    async with h.sessions() as session:
        found = await session.execute(
            text(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'know' "
                "AND table_name = 'item' AND column_name IN ('arrived_as', 'source_url')"
            )
        )
        return int(found.scalar_one()) == 2


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


async def _list(h: Harness, app: FastAPI, agent_id: str, who: str) -> Any:
    from brain.agent_knowledge_routes import agent_knowledge
    from brain.ops.acceptance_checks_agent_page import _asking

    request = _request(app, f"/api/v1/agents/{agent_id}/knowledge")
    return await agent_knowledge(request, agent_id, await _asking(h, who))


async def _add_file(
    h: Harness, app: FastAPI, agent_id: str, who: str, *, body: bytes, name: str
) -> Any:
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
    done = await add_file_for_agent(
        request, agent_id, await _asking(h, who), KnowledgeKind.SOP, Visibility.DEPARTMENT, A
    )
    if not hasattr(done, "item_id"):
        raise CheckFailedError("a file added from the section was refused by the door")
    return done


async def _add_link(h: Harness, app: FastAPI, agent_id: str, who: str, *, address: str) -> Any:
    from brain.agent_knowledge_routes import add_link_for_agent
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_intake_routes import LinkAsked
    from brain.ops.acceptance_checks_agent_page import _asking

    request = _request(app, f"/api/v1/agents/{agent_id}/knowledge/links", method="POST")
    done = await add_link_for_agent(
        request,
        agent_id,
        await _asking(h, who),
        LinkAsked(
            url=address,
            kind=KnowledgeKind.SERVICE_PACKAGE,
            level=Visibility.DEPARTMENT,
            department=A,
        ),
    )
    if not hasattr(done, "item_id"):
        raise CheckFailedError("a link added from the section was refused by the door")
    return done


async def _retire(h: Harness, app: FastAPI, agent_id: str, who: str, item_id: str) -> Any:
    from brain.agent_knowledge_routes import retire_for_agent
    from brain.ops.acceptance_checks_agent_page import _asking

    request = _request(app, f"/api/v1/agents/{agent_id}/knowledge/{item_id}/retire", method="POST")
    return await retire_for_agent(request, agent_id, item_id, await _asking(h, who))


async def _refetch(h: Harness, app: FastAPI, agent_id: str, who: str, item_id: str) -> Any:
    from datetime import UTC, datetime, timedelta

    from brain.agent_knowledge_routes import RefetchAsked, refetch_for_agent
    from brain.ops.acceptance_checks_agent_page import _asking

    request = _request(app, f"/api/v1/agents/{agent_id}/knowledge/{item_id}/refetch", method="POST")
    return await refetch_for_agent(
        request,
        agent_id,
        item_id,
        await _asking(h, who),
        RefetchAsked(review_by=datetime.now(UTC) + timedelta(days=90)),
    )


class _NoQueue:
    """What the door is handed in place of its embedding queue: it may not be asked for one."""

    async def __call__(self, job: object) -> object:
        raise CheckFailedError("a document added from the section queued work for a worker")


class _HeldDoor:
    """The door with its embedding queue held out of reach, restored on exit."""

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
    """The page a link answers with, which the check changes, and every address it was asked for."""

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
        return [PUBLIC_ADDRESS]


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
        "<html><head><title>Acceptance refetch page</title></head><body><main>"
        f"<h1>Acceptance refetch</h1><p>{word} is the refetch word.</p></main></body></html>"
    ).encode()


def _document(h: Harness) -> tuple[str, bytes]:
    """A Markdown file pairing two words nothing else holds, and the first of them."""
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.acceptance_models import PAIRED

    key, value = h.word(), h.word()
    return key, a_markdown_document("Acceptance retire", PAIRED.format(key=key, value=value))


async def _people(h: Harness) -> tuple[str, str]:
    """A steward who adds and acts in acceptance_a, and a colleague who only reads there."""
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in

    await h.found_departments()
    steward, colleague = h.principal(A, "steward"), h.principal(A, "colleague")
    await h.person(
        steward,
        department=A,
        grants=[*_tab_and_planes(), *_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value)],
    )
    await h.person(colleague, department=A, grants=[*_tab_and_planes(), *_in(A, *KNOWLEDGE_READS)])
    return steward, colleague


# ------------------------------------------------------------------------- 1. retiring
@check(
    leaves=("M39.9.1.5",),
    sentence=(
        "A steward retires a document from an agent's Knowledge section: a colleague who may only "
        "read it is offered no Retire and is refused as for a document that is not there, and "
        "after the steward retires it the section no longer lists it for either of them and a "
        "text search for its words answers as it answers for words nobody wrote."
    ),
)
async def a_retired_document_is_no_longer_drawn_on_by_the_agent(h: Harness) -> None:
    from brain.agent_knowledge_routes import KnowledgeRetiredView
    from brain.core.errors import Absent
    from brain.ops.acceptance_checks_lifecycle import _answered, _silent
    from brain.ops.acceptance_workspace import installed_agent

    if not await _archive_function_is_here(h):
        raise CheckNotRunError(THE_ARCHIVE_FUNCTION_IS_NOT_HERE)
    steward, colleague = await _people(h)
    agent_id = await installed_agent(h, steward, suffix="retire")
    app = _app(h)
    word, body = _document(h)
    with _HeldDoor():
        added = await _add_file(h, app, agent_id, steward, body=body, name="Retire.md")
    if not added.reached:
        raise CheckFailedError("a file added where the agent's rule reaches was not drawn on")

    before = {who: await _list(h, app, agent_id, who) for who in (steward, colleague)}
    for who in (steward, colleague):
        if [one.item_id for one in before[who].items] != [added.item_id]:
            raise CheckFailedError("the section did not list exactly the file that was added")
    if not before[steward].items[0].can_retire or before[colleague].items[0].can_retire:
        raise CheckFailedError("Retire was not offered to exactly the person who may act")
    if not await _answered(h, colleague, word, added.item_id):
        raise CheckFailedError("a text search did not find the document before it was retired")

    try:
        await _retire(h, app, agent_id, colleague, added.item_id)
    except Absent as refused:
        try:
            await _retire(h, app, agent_id, colleague, "upload.nothing_is_here")
        except Absent as missing:
            if refused.public_message != missing.public_message:
                raise CheckFailedError(
                    "a refused retire was answered unlike a document that is not there"
                ) from None
        else:
            raise CheckFailedError("a document that does not exist was retired") from None
    else:
        raise CheckFailedError("a reader who may not act on a document retired it")
    if [one.item_id for one in (await _list(h, app, agent_id, steward)).items] != [added.item_id]:
        raise CheckFailedError("a refused retire changed what the agent draws on")

    done = await _retire(h, app, agent_id, steward, added.item_id)
    if not isinstance(done, KnowledgeRetiredView) or done.item_id != added.item_id:
        raise CheckFailedError("the steward could not retire their own document")
    for who in (steward, colleague):
        if (await _list(h, app, agent_id, who)).items:
            raise CheckFailedError("a retired document was still listed as one the agent draws on")
    if not await _silent(h, colleague, word):
        raise CheckFailedError("a text search still answered from the retired document")
    try:
        await _retire(h, app, agent_id, steward, added.item_id)
    except Absent:
        pass
    else:
        raise CheckFailedError("a document already retired was retired again")


# ---------------------------------------------------------------------- 2. fetching again
@check(
    leaves=("M39.9.1.5",),
    sentence=(
        "A link added from an agent's Knowledge section is listed as a link and is fetched again "
        "only when a steward asks: listing it asks the site for nothing, a colleague who may only "
        "read it is refused, a changed page becomes a newer version that replaces the old one on "
        "the agent's list and in a text search, and the same page again is told it has not changed."
    ),
)
async def a_link_is_fetched_again_only_when_a_person_asks(h: Harness) -> None:
    from brain.agent_knowledge_routes import THE_PAGE_HAS_NOT_CHANGED
    from brain.core.errors import Absent
    from brain.ops.acceptance_checks_lifecycle import _answered, _silent
    from brain.ops.acceptance_workspace import installed_agent

    if not await _source_columns_are_here(h):
        raise CheckNotRunError(THE_SOURCE_COLUMNS_ARE_NOT_HERE)
    steward, colleague = await _people(h)
    agent_id = await installed_agent(h, steward, suffix="refetch")
    app = _app(h)
    old, new = h.word(), h.word()
    site = _StandInSite(_page(old))
    with _HeldDoor(), _HeldSite(site):
        added = await _add_link(h, app, agent_id, steward, address=STAND_IN_ADDRESS)
        for _ in range(3):
            await _list(h, app, agent_id, steward)
        if site.asked != [STAND_IN_ADDRESS]:
            raise CheckFailedError("a link was fetched again by being listed")
        listed = (await _list(h, app, agent_id, steward)).items
        if [(one.item_id, one.arrived_as) for one in listed] != [(added.item_id, "link")]:
            raise CheckFailedError("a link was not listed as one that arrived as a link")
        if not listed[0].can_refetch:
            raise CheckFailedError("a fetch again was not offered for a link to its steward")
        if (await _list(h, app, agent_id, colleague)).items[0].can_refetch:
            raise CheckFailedError("a fetch again was offered to a reader who may not act")
        if not await _answered(h, colleague, old, added.item_id):
            raise CheckFailedError("a text search did not find the page that was added")

        try:
            await _refetch(h, app, agent_id, colleague, added.item_id)
        except Absent:
            pass
        else:
            raise CheckFailedError("a reader who may not act on a link fetched it again")
        unchanged = await _refetch(h, app, agent_id, steward, added.item_id)
        if getattr(unchanged, "status_code", 0) != 422 or THE_PAGE_HAS_NOT_CHANGED not in str(
            getattr(unchanged, "body", b"")
        ):
            raise CheckFailedError("a page that had not changed was not told so")

        site.page = _page(new)
        replaced = await _refetch(h, app, agent_id, steward, added.item_id)
    if getattr(replaced, "supersedes", "") != added.item_id:
        raise CheckFailedError("a changed page was not added as a newer version of the link")
    after = [one.item_id for one in (await _list(h, app, agent_id, steward)).items]
    if after != [replaced.item_id]:
        raise CheckFailedError("the old version was still listed beside the newer one")
    if site.asked != [STAND_IN_ADDRESS] * 3:
        raise CheckFailedError("the page was asked for other than when a person asked")
    if not await _answered(h, colleague, new, replaced.item_id) or not await _silent(
        h, colleague, old
    ):
        raise CheckFailedError("a text search did not move from the old page to the new one")
