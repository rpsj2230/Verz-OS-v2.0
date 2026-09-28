"""A web page read as knowledge: its words, its tables, its sections, and the page that has none.

Every page here is a recorded shape from `tests.fixtures.web_pages`; nothing reaches the network.
The reader is driven through `brain.knowledge.scanning.parse_scanned` wherever the gate matters,
so a page is scanned by the structural check before a line of markup is read, as it is on an
install.

Task ids: M7.1.2
"""

from __future__ import annotations

from datetime import date
from typing import get_type_hints

import pytest

from brain.knowledge.chunking import BlockKind
from brain.knowledge.ingest import CAUSE_TEXT, MediaType, ParseCause, ParseFailure, admit_upload
from brain.knowledge.scanning import (
    ParsedDocument,
    ParseRefusal,
    ScannedContent,
    parse_scanned,
    scan_for_parsing,
)
from brain.knowledge.text_path import BLOCK_SEPARATOR, StructuralCheck, joined
from brain.knowledge.web_page import (
    TAKEN_FROM,
    LinkPageParser,
    looks_like_html,
    page_title,
    read_page,
    source_of,
)
from tests.fixtures.documents import a_pdf
from tests.fixtures.web_pages import (
    FURNITURE_WORD,
    MARKDOWN_ANSWER,
    PLAIN_PAGE,
    PRICING_PAGE,
    PRICING_URL,
    PRICING_WORD,
    SCRIPT_WORD,
    SCRIPTED_SHELL,
)

#: A date far from any wall clock, so the address line is a fixed string and never a clock.
TAKEN_ON = date(2999, 1, 1)
SOURCE = "https://www.example.org/services/pricing"


def cleared(body: bytes, media_type: MediaType = MediaType.HTML) -> ScannedContent:
    upload = admit_upload(filename="pricing", declared_type=media_type.value, content=body)
    return scan_for_parsing(upload, body, scanner=StructuralCheck())


def texts(body: bytes) -> list[str]:
    drafted = read_page(body)
    assert not isinstance(drafted, ParseRefusal), drafted
    return [one.text for one in drafted]


# ------------------------------------------------------------------ the words
def test_a_page_is_read_from_its_main_content_and_never_from_its_furniture_or_code() -> None:
    """The ordinary page: a banner, a navigation bar, a footer, an aside, scripts and styles, and
    the words a person came for inside `main`. Delete this and every page added by link stores
    its menu and its cookie banner, which become the commonest passage in the knowledge layer and
    the likeliest to be cited, and a script's text is indexed as though it were the page's."""
    read = " ".join(texts(PRICING_PAGE))

    assert PRICING_WORD in read
    assert "two site visits a year and a named engineer" in read
    assert FURNITURE_WORD not in read
    assert SCRIPT_WORD not in read
    assert "icon" not in read


def test_a_page_marking_no_content_region_is_read_whole_less_its_furniture() -> None:
    """The positive case for the `main` rule: a page with no `main` or `article` is not read as
    empty. Delete this and a simple page with no landmarks becomes a scripted-page refusal."""
    read = texts(PLAIN_PAGE)

    assert read == ["Opening hours", "The TEALHOURS desk opens at nine."]


def test_a_table_on_a_page_is_one_table_block_of_pipe_rows() -> None:
    """A price table is the thing most worth keeping whole, and the pricing-note rule reads the
    block's kind. Delete this and a table arrives as a run of cells, and a pricing note holding
    one is accepted because nothing saw a table."""
    drafted = read_page(PRICING_PAGE)
    assert not isinstance(drafted, ParseRefusal)
    (table,) = [one for one in drafted if one.kind is BlockKind.TABLE]

    assert table.text.split(chr(10)) == [
        "| Plan | Visits | Monthly |",
        "| Essential | 2 | 120.00 |",
        "| Priority / plus | 4 | 240.00 |",
    ]
    assert table.section == "What each plan costs"


def test_a_heading_names_the_section_the_blocks_after_it_cite() -> None:
    """A citation says which part of the page a passage came from. Delete this and every passage
    of a long page cites the page and nothing narrower."""
    drafted = read_page(PRICING_PAGE)
    assert not isinstance(drafted, ParseRefusal)
    sections = {one.text: one.section for one in drafted}

    assert sections["- Call the desk"] == "Booking"
    assert sections["Care plans"] == "Care plans"


def test_a_line_break_in_markup_is_a_space_and_br_and_list_items_are_kept() -> None:
    """Markup wraps lines wherever its author's editor did, so a newline there is a space; `br`
    is a line the author meant, and a list item is a line with a marker even inside a paragraph.
    Delete this and a sentence is split across two lines at an editor's margin."""
    read = texts(PRICING_PAGE)

    assert "Every TEALPLAN care plan includes two site visits a year and a named engineer." in read
    assert "Lines are open" + chr(10) + "Monday to Friday." in read
    assert [one for one in read if one.startswith("- ")] == ["- Call the desk", "- Or write to us"]


def test_a_page_whose_words_need_a_browser_is_refused_as_a_scripted_page() -> None:
    """**The failure the generic one mis-describes.** A single-page application's first answer
    holds no words. Read through the gate, it is refused as `SCRIPTED_PAGE`, whose words say to
    save it from a browser, and not as `NO_TEXT_LAYER`, whose words say it is a scan. Delete this
    and it is stored as an item that answers nothing, or refused with advice to run OCR on HTML."""
    outcome = parse_scanned(
        cleared(SCRIPTED_SHELL), parser=LinkPageParser(source=SOURCE, taken_on=TAKEN_ON)
    )

    assert isinstance(outcome, ParseFailure)
    assert outcome.cause is ParseCause.SCRIPTED_PAGE
    assert CAUSE_TEXT[ParseCause.SCRIPTED_PAGE] != CAUSE_TEXT[ParseCause.NO_TEXT_LAYER]
    assert "browser" in outcome.message()


# ------------------------------------------------------------------ what is a page
def test_a_text_body_opening_with_markup_is_a_page_and_prose_is_not() -> None:
    """The type comes from the bytes, and this is the half of that the sniffer cannot decide.
    Delete this and Markdown mentioning a tag is read as a page, or a page as prose full of tags."""
    assert looks_like_html(PRICING_PAGE)
    assert looks_like_html(PLAIN_PAGE)
    assert looks_like_html(bytes((0xEF, 0xBB, 0xBF)) + b"  <!doctype html><p>x</p>")
    assert looks_like_html(b"<?xml version='1.0'?><html><body>x</body></html>")
    assert not looks_like_html(MARKDOWN_ANSWER)
    assert not looks_like_html(b"Use the <html> element for pages.")


def test_the_address_a_page_is_cited_by_keeps_no_query_fragment_or_credential() -> None:
    """The address is the first line of the page's text, which everybody in its department
    reads, and a share link's token rides in the query. Delete this and the token is published
    to a department with the page."""
    assert source_of(PRICING_URL) == SOURCE
    assert source_of("https://user:secret@www.example.org:8443/a?b=c#d") == (
        "https://www.example.org:8443/a"
    )
    assert source_of("https://www.example.org") == "https://www.example.org/"


# ------------------------------------------------------------------ the parser for a link
def test_the_link_parser_puts_the_address_and_date_first_with_offsets_that_hold() -> None:
    """Where and when a fetched-once page came from is the one fact its reader most needs, so it
    is the first line; and the offsets are laid out again so a citation still points at its own
    words. Delete this and a page is stored with no provenance, or with every span one line off."""
    outcome = parse_scanned(
        cleared(PRICING_PAGE), parser=LinkPageParser(source=SOURCE, taken_on=TAKEN_ON)
    )
    assert isinstance(outcome, ParsedDocument)
    first = outcome.blocks[0]
    content = joined(outcome.blocks)

    assert first.text == TAKEN_FROM.format(source=SOURCE, day="2999-01-01")
    assert content.startswith(first.text + BLOCK_SEPARATOR)
    assert all(content[one.start : one.end] == one.text for one in outcome.blocks)
    assert PRICING_WORD in content


def test_a_document_a_link_answers_with_is_read_by_the_text_path_with_the_address_first() -> None:
    """A link to a PDF is a PDF, read by the reader every PDF meets. Delete this and a document
    linked rather than uploaded loses its pages, or is read as markup."""
    outcome = parse_scanned(
        cleared(a_pdf("Sign the TEALPDF list."), MediaType.PDF),
        parser=LinkPageParser(source=SOURCE, taken_on=TAKEN_ON),
    )
    assert isinstance(outcome, ParsedDocument)

    assert outcome.blocks[0].text.startswith("Taken from ")
    assert outcome.blocks[1].page == 1
    assert "TEALPDF" in outcome.blocks[1].text


def test_a_linked_document_with_no_words_stays_a_failure_and_not_a_one_line_item() -> None:
    """The address line must not rescue an empty read: a PDF with no text layer is still
    `NO_TEXT_LAYER`. Delete this and an empty document is stored as an item whose only passage
    is where it came from."""
    outcome = parse_scanned(
        cleared(a_pdf(""), MediaType.PDF),
        parser=LinkPageParser(source=SOURCE, taken_on=TAKEN_ON),
    )

    assert isinstance(outcome, ParseFailure)
    assert outcome.cause is ParseCause.NO_TEXT_LAYER


def test_the_page_title_is_its_first_title_and_never_an_icons() -> None:
    """The item is named by the page's own title, and an inline SVG carries a `title` of its
    own. Delete this and a page is named "icon", or named by its address's last segment when it
    stated a title."""
    assert page_title(cleared(PRICING_PAGE)) == "Care plans & pricing | Example Services"
    assert page_title(cleared(MARKDOWN_ANSWER, MediaType.MARKDOWN)) == ""


def test_reading_a_title_takes_scanned_content_because_it_is_reading_markup() -> None:
    """The ordering rule covers every reader of an untrusted page, not only the parser. Delete
    this and `page_title` can be handed the unscanned bytes, which is a parser reached first."""
    assert get_type_hints(page_title)["content"] is ScannedContent


@pytest.mark.parametrize(
    "markup",
    [
        b"<html><body><main><p>Unclosed <nav>menu NAVONLY",
        b"<html><body><table><tr><td>a<table><tr><td>inner</td></tr></table></td></tr>",
        b"<html><body>" + b"<div>" * 5000 + b"deep TEALDEEP" + b"</div>" * 5000,
    ],
)
def test_markup_its_authors_did_not_close_is_read_without_raising(markup: bytes) -> None:
    """A page is written by anybody, and the reader must not raise on markup a browser would
    render. Delete this and a missing close tag turns into a 500 on the Knowledge page."""
    drafted = read_page(markup)

    assert isinstance(drafted, tuple | ParseRefusal)
