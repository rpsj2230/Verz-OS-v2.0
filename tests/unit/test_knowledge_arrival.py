"""How a document arrived is recorded by the doors that add it, and is never guessed.

`brain.knowledge.item.KnowledgeItem` carries `arrived_as` and `source_url` since `0220`, the two
reading paths set them, and the stored row is written from them. What is held here is the
producer side: a file's read says `file` and no address, a link's read says `link` and the address
the person gave rather than the one it redirected to, and an item cannot name an address without
having arrived as a link.

Task ids: M39.9.1.5, M39.9.1.1
"""

from __future__ import annotations

from datetime import date

import pytest

from brain.knowledge.ingest import admit_upload
from brain.knowledge.item import ARRIVED_AS_FILE, ARRIVED_AS_LINK, KnowledgeItem, KnowledgeState
from brain.knowledge.item_store import row_values
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.uploads import (
    ReceivedUpload,
    read_for_link,
    read_for_text_path,
    receive_page,
)
from brain.knowledge.visibility import KnowledgeVisibility
from tests.fixtures.documents import LINE
from tests.fixtures.web_pages import PRICING_PAGE, PRICING_URL
from tests.unit.test_knowledge_intake_routes import Public, Site

PLACE = KnowledgeVisibility.of_department("web", owner_id="u_steward")
MARKDOWN = LINE.join(["# Site handover", "", "Sign the TEALCHECK list."]).encode()


def an_item(arrived_as: str = "", source_url: str = "") -> KnowledgeItem:
    return KnowledgeItem(
        item_id="upload.one",
        content="Something said.",
        title="One",
        visibility=PLACE,
        owner_id="u_steward",
        state=KnowledgeState.PUBLISHED,
        arrived_as=arrived_as,
        source_url=source_url,
    )


def test_a_file_that_is_read_says_it_arrived_as_a_file_and_names_no_address() -> None:
    """Delete this and a file added from the console records nothing, so every document stays
    `unknown` for ever and the list can never say how a new one arrived."""
    upload = admit_upload(filename="Handover.md", declared_type="text/markdown", content=MARKDOWN)
    read = read_for_text_path(
        ReceivedUpload(upload=upload, body=MARKDOWN),
        kind=KnowledgeKind.SOP,
        placement=PLACE,
        owner_id="u_steward",
    )
    assert not hasattr(read, "cause"), read
    assert read.item.arrived_as == ARRIVED_AS_FILE
    assert read.item.source_url == ""


def test_a_link_that_is_read_records_the_address_it_was_given_and_not_where_it_ended() -> None:
    """The recorded address is the one the person typed, so a refetch runs the same redirect chain
    through the same address rule. Delete this and a refetch asks the page it was redirected to,
    which skips the first hop's check and can be a different page altogether."""
    site = Site({PRICING_URL: PRICING_PAGE})
    page = receive_page(PRICING_URL, fetcher=site, resolver=Public())
    read = read_for_link(
        page,
        kind=KnowledgeKind.SERVICE_PACKAGE,
        placement=PLACE,
        owner_id="u_steward",
        taken_on=date(2019, 1, 1),
    )
    assert not hasattr(read, "cause"), read
    assert read.item.arrived_as == ARRIVED_AS_LINK
    assert read.item.source_url == PRICING_URL
    stored = row_values(read.item)
    assert (stored["arrived_as"], stored["source_url"]) == (ARRIVED_AS_LINK, PRICING_URL)


def test_an_item_that_recorded_nothing_is_stored_with_null_and_not_with_an_empty_word() -> None:
    """Null is "unknown" and an empty string is a value the check constraint refuses. Delete this
    and a document without the columns is written with `''`, which the database rejects on the first
    write by any code path that does not set them."""
    stored = row_values(an_item())
    assert stored["arrived_as"] is None and stored["source_url"] is None


def test_an_item_cannot_name_an_address_without_having_arrived_as_a_link() -> None:
    """Delete this and a file can carry an address, which the refetch would then fetch."""
    with pytest.raises(ValueError, match="did not arrive as a link"):
        an_item(source_url="https://www.example.org/a")
    with pytest.raises(ValueError, match="neither a file nor a link"):
        an_item(arrived_as="email")
    assert an_item(arrived_as="link", source_url="https://www.example.org/a").source_url
