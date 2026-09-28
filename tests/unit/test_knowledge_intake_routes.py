"""Adding knowledge by link and queueing a bulk upload, over HTTP, as signed-in people.

Driven through the real application with the grants `test_knowledge_routes.py` uses, and this
module's router included beside the upload's. What is stood in: the link's transport and resolver
(recorded pages from `tests.fixtures.web_pages`, so nothing reaches the network), the corpus write
(`brain.knowledge_routes.ingest_document`, kept rather than written, as the upload's tests keep
it), the job queue (counted and kept), and the object store (a dictionary). Everything else, the
placement, the door, the scan, the parse of a link and the refusals, runs for real.

Task ids: M7.1.2, M7.1.3, M7.1.5, M22.2.4
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, cast
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from brain import knowledge_intake_routes, knowledge_routes
from brain.api import API_PREFIX
from brain.knowledge import text_path
from brain.knowledge.ingest import SCAN_CAUSE_TEXT, ParseCause, ScanCause
from brain.knowledge.ingest_queue import INGEST_TASK, TOO_LARGE_TO_QUEUE, get_ticket, put_ticket
from brain.knowledge.text_path import STRUCTURAL_CHECK
from brain.knowledge_intake_routes import (
    LINKS_PATH,
    QUEUED_PATH,
    QUEUED_UPLOADS_NEED_THE_STORE,
    THE_QUEUE_DID_NOT_ANSWER,
    LinkAsked,
)
from brain.knowledge_routes import FOUND_BY_TEXT, NAME_HEADER
from brain.ops.object_store import ObjectStore, unconnected
from brain.ops.queue import Job
from brain.tables.audit import ACTOR_SETTING, TRACE_ID_SETTING
from brain.tools.fetch import FetchedBytes
from tests.fixtures.console_http import Stub, console_client, get, headers
from tests.fixtures.documents import LINE, a_pdf, a_word_document, with_part
from tests.fixtures.memory_store import MemoryStore
from tests.fixtures.web_pages import (
    FURNITURE_WORD,
    PRICING_PAGE,
    PRICING_URL,
    PRICING_WORD,
    SCRIPTED_SHELL,
    SITE,
)
from tests.unit.test_knowledge_routes import GRANTS, Kept, registry

LINKS = f"{API_PREFIX}{LINKS_PATH}"
QUEUED = f"{API_PREFIX}{QUEUED_PATH}"
MARKDOWN = LINE.join(["# Site handover", "", "Sign the TEALCHECK list before leaving."]).encode()
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class Site:
    """The recorded pages a link may answer with, and every hop it was asked for."""

    def __init__(self, pages: dict[str, bytes | str]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        self.asked.append(url)
        answer = self.pages[url]
        return answer if isinstance(answer, str) else FetchedBytes(body=answer, final_url=url)


class Public:
    """A resolver answering one public address for every name, so no lookup leaves the test."""

    def resolve(self, host: str) -> Sequence[str]:
        return ["93.184.216.34"]


class Queue:
    """The job queue: how full it says it is, and the jobs it was handed."""

    def __init__(self) -> None:
        self.waiting = 0
        self.running = 0
        self.down = False
        self.jobs: list[Job] = []

    async def counts(self) -> tuple[int, int]:
        if self.down:
            raise ConnectionRefusedError
        return self.waiting, self.running

    async def enqueue(self, job: Job) -> None:
        self.jobs.append(job)


class Served:
    """The client, the stub, and every stand-in, so a test asserts on what each was handed."""

    def __init__(self, client: TestClient, stub: Stub, kept: Kept) -> None:
        self.client = client
        self.stub = stub
        self.kept = kept
        self.site = Site({PRICING_URL: PRICING_PAGE})
        self.queue = Queue()
        self.store = MemoryStore()
        self.use_store(ObjectStore(backend=cast(Any, self.store), prefix="brain"))

    def use_store(self, store: ObjectStore) -> None:
        self.client.app.state.object_store = store  # type: ignore[attr-defined]


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[Served]:
    kept = Kept()
    monkeypatch.setattr(knowledge_routes, "ingest_document", kept)
    with console_client(GRANTS) as (client, stub):
        client.app.include_router(knowledge_intake_routes.router)  # type: ignore[attr-defined]
        stub.answerers.append(registry)
        out = Served(client, stub, kept)
        monkeypatch.setattr(knowledge_intake_routes, "make_fetcher", lambda: out.site)
        monkeypatch.setattr(knowledge_intake_routes, "make_resolver", Public)
        monkeypatch.setattr(knowledge_intake_routes, "queue_for", lambda request: out.queue)
        yield out


def add_link(
    served: Served,
    pid: str,
    url: str = PRICING_URL,
    *,
    kind: str = "service_package",
    level: str = "department",
    department: str = "web",
    strong: bool = True,
) -> Any:
    return served.client.post(
        LINKS,
        json={"url": url, "kind": kind, "level": level, "department": department},
        headers=headers(pid, strong=strong),
    )


def queue(
    served: Served,
    pid: str,
    body: bytes = MARKDOWN,
    *,
    name: str = "Site handover.md",
    media_type: str = "text/markdown",
    kind: str = "sop",
    level: str = "department",
    department: str = "web",
) -> Any:
    sent = {**headers(pid), "content-type": media_type, NAME_HEADER: quote(name)}
    return served.client.post(
        QUEUED,
        content=body,
        headers=sent,
        params={"kind": kind, "level": level, "department": department},
    )


def problem(response: Any, status: int = 422) -> tuple[str, str]:
    """The code and the reason a refusal gives."""
    assert response.status_code == status, response.text
    body = response.json()
    (one,) = body["problems"]
    assert body["message"] == one["message"]
    return str(one["code"]), str(one["message"])


# ------------------------------------------------------------------ a link (M7.1.2)
def test_an_administrator_adds_a_page_by_its_link_for_one_department(served: Served) -> None:
    """**M7.1.2's route, as the owner put it: added by its link for one department, answered from
    like an uploaded document.** The page is fetched once, read, placed in web as the kind chosen,
    named by its title, with where it came from first, and handed to the same store an upload is
    handed to. Delete this and the link route can store the site's menu, a token from the address,
    or nothing."""
    response = add_link(served, "u_admin")

    assert response.status_code == 201, response.text
    (read,) = served.kept.stored
    assert response.json() == {
        "item_id": read.item.item_id,
        "title": "Care plans & pricing | Example Services",
        "kind": "service_package",
        "level": "department",
        "department": "web",
        "passages": len(read.blocks),
        "found_by": FOUND_BY_TEXT,
    }
    assert served.site.asked == [PRICING_URL]
    assert read.item.content.startswith(f"Taken from {SITE}/services/pricing on ")
    assert PRICING_WORD in read.item.content
    assert FURNITURE_WORD not in read.item.content
    assert "abc123" not in read.item.content


def test_a_link_is_written_with_its_adders_attribution_for_the_ledger(served: Served) -> None:
    """The ledger entry `0115`'s trigger appends names whoever the transaction says wrote it.
    Delete this and a page added by link is recorded as the owner, inferred, at no reach."""
    assert add_link(served, "u_admin").status_code == 201

    (attribution,) = served.kept.attributed
    said = {str(one.compile().params["name"]): one.compile().params["value"] for one in attribution}
    assert said[ACTOR_SETTING] == "u_admin"
    assert TRACE_ID_SETTING in said


def test_the_address_travels_in_the_body_and_never_in_the_query_string() -> None:
    """A share link carries its token, and a query string is written into every access log.
    Delete this and the route can take the address as a query parameter."""
    assert "url" in LinkAsked.model_fields
    assert LinkAsked.model_config.get("extra") == "forbid"


def test_a_link_redirecting_inside_the_network_is_refused_naming_the_address_check(
    served: Served,
) -> None:
    """**The SSRF rule over HTTP.** Delete this and an administrator's link is a way to make the
    server read its own cloud metadata into a department's knowledge."""
    served.site.pages[PRICING_URL] = "https://169.254.169.254/latest/meta-data/"

    code, said = problem(add_link(served, "u_admin"))

    assert code == "not_added"
    assert "refused by the address check" in said
    assert served.kept.stored == []


def test_a_scripted_page_is_refused_with_the_cause_and_what_to_do(served: Served) -> None:
    """Delete this and a single-page application is added as an item that answers nothing."""
    served.site.pages[PRICING_URL] = SCRIPTED_SHELL

    code, said = problem(add_link(served, "u_admin"))

    assert code == ParseCause.SCRIPTED_PAGE.value
    assert "browser" in said
    assert served.kept.stored == []


def test_a_link_placed_where_its_adder_may_not_add_is_absent_and_says_nothing_more(
    served: Served,
) -> None:
    """The same answer the upload gives, so the route is not a way to ask which departments
    exist. Delete this and a reader can add by link, or learn why they may not."""
    assert add_link(served, "u_wide").status_code == 404
    assert add_link(served, "u_narrow", department="finance").status_code == 404
    assert add_link(served, "u_admin", strong=False).status_code == 404
    assert served.site.asked == []


def test_a_link_is_never_placed_company_wide(served: Served) -> None:
    """Delete this and a link is a way round the promotion that widening needs."""
    code, _ = problem(add_link(served, "u_admin", level="company"))

    assert code == "level_refused"


# ------------------------------------------------------------------ a queued file (M7.1.5)
def test_a_queued_file_is_kept_ticketed_and_queued_and_never_parsed_in_the_request(
    served: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**M22.2.4's property, where it can be proved: the request path never parses.** The
    parser raises if reached, and the upload is still accepted: the original and the ticket are
    kept, and one job carrying the ticket alone is queued for the worker. Delete this and a bulk
    upload can be read in the web process, beside every question asked meanwhile."""

    def never(self: object, content: object) -> object:
        raise AssertionError("a queued upload was parsed in the request")

    monkeypatch.setattr(text_path.TextPathParser, "parse", never)

    response = queue(served, "u_admin")

    assert response.status_code == 202, response.text
    body = response.json()
    (job,) = served.queue.jobs
    assert (job.task, dict(job.args)) == (INGEST_TASK, {"ticket": body["ticket"]})
    assert (body["name"], body["state"], body["item_id"]) == ("Site handover.md", "queued", None)
    assert body["said"] == "Site handover.md is queued to be read."
    keys = served.store.names()
    assert any("/knowledge/originals/" in key for key in keys)
    assert f"brain/knowledge/queued/{body['ticket']}.json" in keys
    assert served.kept.stored == []


def test_a_full_queue_refuses_with_a_wait_before_reading_or_keeping_anything(
    served: Served,
) -> None:
    """**Backpressure at the door.** Delete this and a full queue accepts and drops, which is the
    uploader told a file was taken that nothing will ever read."""
    served.queue.waiting = 500

    response = queue(served, "u_admin")
    code, said = problem(response, 429)

    assert code == "queue_full"
    assert "busy" in said
    assert int(response.headers["retry-after"]) >= 1
    assert served.store.names() == []
    assert served.queue.jobs == []


def test_a_file_the_scan_refuses_is_refused_naming_the_cause_and_nothing_is_kept(
    served: Served,
) -> None:
    """**M7.1.3 at the queue's door.** Delete this and a macro document is kept in the store and
    queued, and the sender learns it was refused only if they think to ask."""
    macro = with_part(a_word_document(paragraphs=["x"]), "word/vbaProject.bin", b"m")

    code, said = problem(queue(served, "u_admin", macro, name="policy.docx", media_type=DOCX))

    assert code == "not_added"
    assert STRUCTURAL_CHECK in said
    assert SCAN_CAUSE_TEXT[ScanCause.MACROS] in said
    assert served.store.names() == []
    assert served.queue.jobs == []


def test_a_file_too_large_for_a_worker_slot_is_refused_with_the_way_to_add_it(
    served: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a file nothing can hold is queued for a worker that fails on it."""
    from brain.knowledge import ingest_queue

    monkeypatch.setattr(ingest_queue, "STANDARD_PARSE_BUDGET", 10)

    refused = queue(served, "u_admin", a_pdf("x"), name="big.pdf", media_type="application/pdf")
    code, said = problem(refused)

    assert code == "too_large_to_queue"
    assert TOO_LARGE_TO_QUEUE in said
    assert served.queue.jobs == []


def test_an_install_with_no_object_store_is_told_queued_uploads_need_one(served: Served) -> None:
    """Delete this and the route fails with a 500 on the install most likely to try it first."""
    served.use_store(unconnected("the vault holds no key for the store"))

    code, said = problem(queue(served, "u_admin"))

    assert code == "no_object_store"
    assert said.startswith(QUEUED_UPLOADS_NEED_THE_STORE)
    assert "holds no key" in said


def test_a_queue_that_does_not_answer_is_told_and_nothing_is_kept(served: Served) -> None:
    """Delete this and a queue outage is a 500 with a trace in it."""
    served.queue.down = True

    code, said = problem(queue(served, "u_admin"), 503)

    assert (code, said) == ("queue_unavailable", THE_QUEUE_DID_NOT_ANSWER)
    assert served.store.names() == []


# ------------------------------------------------------------------ what became of it
def test_a_queued_files_outcome_is_its_senders_to_ask_and_nobody_elses(served: Served) -> None:
    """The ticket names a file and its sender, so it is answered to the sender and as absent to
    anybody else, including an unknown ticket. Delete this and the status route lists other
    people's filenames to whoever guesses a ticket."""
    body = queue(served, "u_admin").json()
    ticket = body["ticket"]
    store = served.store
    stored = get_ticket(store, ticket, prefix="brain")
    put_ticket(
        store,
        stored.outcome(stored.state.NOT_ADDED, code="no_text_layer", reason="it is a scan."),
        prefix="brain",
    )

    mine = get(served.client, "u_admin", f"{QUEUED}/{ticket}")
    theirs = get(served.client, "u_narrow", f"{QUEUED}/{ticket}")
    unknown = get(served.client, "u_admin", f"{QUEUED}/{'c' * 40}")
    malformed = get(served.client, "u_admin", f"{QUEUED}/..%2F..%2Fsecrets")

    assert mine.status_code == 200, mine.text
    assert mine.json()["state"] == "not_added"
    assert mine.json()["said"] == "Site handover.md was not added: it is a scan."
    assert theirs.status_code == unknown.status_code == 404
    assert theirs.json()["message"] == unknown.json()["message"]
    assert malformed.status_code in {404, 422}
