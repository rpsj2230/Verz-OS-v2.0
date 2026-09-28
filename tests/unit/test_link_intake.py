"""A link taken at the upload door: fetched through the address rule, typed by its bytes, read.

The fetcher and the resolver are scripted, as in `test_fetch.py`, so every hop of a chain and
every address a name resolves to is the test's choice and no request leaves this machine. The
pages are the recorded shapes in `tests.fixtures.web_pages`.

Task ids: M7.1.2, M7.1.3
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pytest

from brain.knowledge.ingest import (
    SCAN_CAUSE_TEXT,
    IngestRefused,
    MediaType,
    ParseCause,
    ParseFailure,
    ScanCause,
    ceiling_for,
)
from brain.knowledge.kinds import KindError, KnowledgeKind
from brain.knowledge.text_path import STRUCTURAL_CHECK
from brain.knowledge.uploads import (
    LINK_CEILING,
    LINK_TYPES,
    FetchedPage,
    ReadUpload,
    page_type,
    read_for_link,
    receive_page,
)
from brain.knowledge.visibility import KnowledgeVisibility
from brain.tools.fetch import FetchedBytes
from brain.tools.skills import SkillError
from tests.fixtures.documents import a_pdf
from tests.fixtures.web_pages import (
    FURNITURE_WORD,
    LATIN1_PAGE,
    MARKDOWN_ANSWER,
    PNG_ANSWER,
    PRICING_PAGE,
    PRICING_URL,
    PRICING_WORD,
    SCRIPTED_SHELL,
    SITE,
)

ADDER = "u_admin"
TAKEN_ON = date(2999, 1, 1)
WEB = KnowledgeVisibility.of_department("web", owner_id=ADDER)


class Resolver:
    """Every name resolves to one public address unless the test says otherwise."""

    def __init__(self, answers: dict[str, Sequence[str]] | None = None) -> None:
        self.answers = answers or {}

    def resolve(self, host: str) -> Sequence[str]:
        return self.answers.get(host, ["93.184.216.34"])


class Site:
    """A scripted chain: each address answers bytes, a redirect, or a failure of the site's."""

    def __init__(self, script: dict[str, bytes | str | SkillError]) -> None:
        self.script = script
        self.asked: list[tuple[str, str, int]] = []

    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        self.asked.append((url, address, max_bytes))
        answer = self.script[url]
        if isinstance(answer, SkillError):
            raise answer
        if isinstance(answer, str):
            return answer
        return FetchedBytes(body=answer, final_url=url)


def taken(
    url: str, script: dict[str, bytes | str | SkillError], resolver: Resolver | None = None
) -> FetchedPage:
    return receive_page(url, fetcher=Site(script), resolver=resolver or Resolver())


def read_link(
    url: str, body: bytes, kind: KnowledgeKind = KnowledgeKind.SERVICE_PACKAGE
) -> ReadUpload | ParseFailure:
    return read_for_link(
        taken(url, {url: body}), kind=kind, placement=WEB, owner_id=ADDER, taken_on=TAKEN_ON
    )


# ------------------------------------------------------------------ the fetch
def test_a_redirect_to_an_address_inside_the_network_is_refused_on_that_hop() -> None:
    """**The SSRF rule, on a link an administrator pastes.** A public page redirecting to the
    metadata service is refused at the second hop, and said to be the address check. Delete this
    and a link is a way to make the server read its own cloud credentials into the knowledge
    layer, where a department can ask about them."""
    site = Site({PRICING_URL: "https://169.254.169.254/latest/meta-data/"})

    with pytest.raises(IngestRefused, match="refused by the address check"):
        receive_page(PRICING_URL, fetcher=site, resolver=Resolver())
    assert [url for url, _, _ in site.asked] == [PRICING_URL]


def test_a_name_resolving_inside_the_network_is_refused_before_anything_connects() -> None:
    """Delete this and a hostname an attacker points at a private address is connected to."""
    site = Site({})
    resolver = Resolver({"intranet.example.org": ["93.184.216.34", "10.0.0.8"]})

    with pytest.raises(IngestRefused, match="refused by the address check"):
        receive_page("https://intranet.example.org/", fetcher=site, resolver=resolver)
    assert site.asked == []


def test_a_site_that_will_not_answer_is_told_apart_from_an_address_that_is_refused() -> None:
    """Two failures, two remedies: fix the link, or try the site later. Delete this and a 404 is
    reported as the server refusing to connect somewhere unsafe."""
    with pytest.raises(IngestRefused, match=r"could not be fetched: .* answered 404"):
        taken(PRICING_URL, {PRICING_URL: SkillError("www.example.org answered 404")})


def test_a_link_followed_through_a_redirect_is_fetched_with_the_largest_link_ceiling() -> None:
    """The positive case for the chain, and the ceiling passed on every hop. Delete this and a
    link that redirects is refused, or fetched with no bound until its type is known."""
    site = Site(
        {f"{SITE}/old": f"{SITE}/services/pricing", f"{SITE}/services/pricing": PRICING_PAGE}
    )
    page = receive_page(f"{SITE}/old", fetcher=site, resolver=Resolver())

    assert page.source == f"{SITE}/services/pricing"
    assert page.received.upload.media_type is MediaType.HTML
    assert {ceiling for _, _, ceiling in site.asked} == {LINK_CEILING}
    assert max(ceiling_for(one) for one in LINK_TYPES) == LINK_CEILING


# ------------------------------------------------------------------ the type
@pytest.mark.parametrize(
    ("url", "body", "expected"),
    [
        (f"{SITE}/brochure.pdf", PRICING_PAGE, MediaType.HTML),
        (f"{SITE}/page.html", a_pdf("x"), MediaType.PDF),
        (f"{SITE}/notes.md", MARKDOWN_ANSWER, MediaType.MARKDOWN),
        (f"{SITE}/notes.txt", MARKDOWN_ANSWER, MediaType.PLAIN),
    ],
)
def test_a_links_type_comes_from_what_it_answered_and_not_from_its_address(
    url: str, body: bytes, expected: MediaType
) -> None:
    """Delete this and a link ending `.pdf` that answers with a login page is handed to the PDF
    reader, or a real PDF behind an `.html` address is read as markup."""
    assert page_type(body, url) is expected


def test_a_link_answering_with_an_image_is_refused_before_it_is_scanned() -> None:
    """Delete this and an image reaches the scanner and the parser, which read no images."""
    with pytest.raises(IngestRefused, match="not a page or a document"):
        taken(f"{SITE}/logo", {f"{SITE}/logo": PNG_ANSWER})


def test_a_page_over_its_types_ceiling_is_refused_at_the_door() -> None:
    """The fetch is bounded by the largest link type; the page's own ceiling is then the door's.
    Delete this and a fifty-megabyte page is admitted because a PDF may be that large."""
    huge = b"<!doctype html><p>" + b"x" * ceiling_for(MediaType.HTML)

    with pytest.raises(IngestRefused, match="the ceiling for text/html"):
        taken(PRICING_URL, {PRICING_URL: huge})


# ------------------------------------------------------------------ the read
def test_a_page_added_by_link_is_an_item_where_it_was_asked_named_by_its_title() -> None:
    """**M7.1.2 as an item.** The page's words, placed in the department asked for, published,
    of the kind chosen, named by its own title, with where and when it came from first and none
    of its furniture. Delete this and a link can be stored under its address's last segment, at
    a level nobody chose, or with the site's menu as its first passage."""
    read = read_link(PRICING_URL, PRICING_PAGE)

    assert isinstance(read, ReadUpload)
    item = read.item
    assert item.title == "Care plans & pricing | Example Services"
    assert (item.visibility, item.owner_id, item.kind) == (
        WEB,
        ADDER,
        KnowledgeKind.SERVICE_PACKAGE,
    )
    assert item.state.value == "published"
    assert item.content.startswith(f"Taken from {SITE}/services/pricing on 2999-01-01.")
    assert PRICING_WORD in item.content
    assert FURNITURE_WORD not in item.content
    assert "token=abc123" not in item.content
    assert item.item_id.startswith("upload.")


def test_the_same_page_added_twice_to_one_place_is_one_item() -> None:
    """Delete this and pasting a link twice adds the page twice, and every answer cites both."""
    first = read_link(PRICING_URL, PRICING_PAGE)
    second = read_link(PRICING_URL, PRICING_PAGE)

    assert isinstance(first, ReadUpload) and isinstance(second, ReadUpload)
    assert first.item.item_id == second.item.item_id


def test_a_page_the_scan_refuses_is_refused_naming_the_cause() -> None:
    """**M7.1.3 on a link.** A page in Latin-1 is not readable text, and the refusal says so and
    says what to do. Delete this and a link is refused with only a scanner's name."""
    with pytest.raises(IngestRefused) as refused:
        read_link(PRICING_URL, LATIN1_PAGE)

    assert STRUCTURAL_CHECK in str(refused.value)
    assert SCAN_CAUSE_TEXT[ScanCause.NOT_READABLE_TEXT] in str(refused.value)


def test_a_page_with_no_words_until_a_browser_runs_is_a_named_failure() -> None:
    """Delete this and a single-page application is stored as an item that answers nothing."""
    read = read_link(PRICING_URL, SCRIPTED_SHELL)

    assert isinstance(read, ParseFailure)
    assert read.cause is ParseCause.SCRIPTED_PAGE


def test_a_pricing_note_holding_a_page_table_is_refused_as_an_upload_is() -> None:
    """The pricing-note rule reads the table the page reader found. Delete this and price rows
    enter the knowledge layer as a link that no upload could have carried."""
    with pytest.raises(KindError, match="pricing note holds a table"):
        read_link(PRICING_URL, PRICING_PAGE, kind=KnowledgeKind.PRICING_NOTE)
