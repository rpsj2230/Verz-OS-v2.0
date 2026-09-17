"""The paging convention every console list shares: what a walk reaches, what a search can match,
and what a cursor refuses.

Driven over a small row type with a field the listing does not declare, because the property that
matters most is the one about a field the reader was not shown, and a row with nothing hidden on it
cannot fail that test. The declaration half is driven through a real FastAPI application, since a
`sort` or `filter` pattern that never reaches the document is a pattern nothing enforces.

Task ids: M27.8.6
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import StringConstraints, TypeAdapter, ValidationError

from brain.api_routes import FILTER_TERM_PATTERN
from brain.listing import (
    CURSOR_PARAM,
    MAX_PAGE_ROWS,
    Column,
    ListAsked,
    Listing,
    ListingError,
    Paged,
    each_of,
    encode_position,
    sort_key,
)

#: A fixed instant far from any wall clock, for CLAUDE.md's reason about dated fixtures.
EPOCH = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Row:
    """A projected row, plus `secret`, which stands for a field the decision withheld."""

    row_id: str
    name: str
    department: str | None
    tags: tuple[str, ...]
    at: datetime
    secret: str = "withheld-value"


LISTING: Listing[Row] = Listing(
    name="rows",
    columns=(
        Column("name", lambda row: row.name, search=True, sort=True),
        Column("department", lambda row: row.department, search=True, filter=True, sort=True),
        Column("tags", lambda row: row.tags, search=True, filter=True),
        Column("at", lambda row: row.at, sort=True),
    ),
    key=lambda row: row.row_id,
    order="name",
)


def rows() -> list[Row]:
    return [
        Row("r1", "Zoe", "finance", ("north",), EPOCH),
        Row("r2", "adam", "sales", ("south", "north"), EPOCH + timedelta(hours=1)),
        Row("r3", "Bea", None, (), EPOCH + timedelta(hours=2)),
        Row("r4", "carl", "finance", ("east",), EPOCH + timedelta(hours=3)),
        Row("r5", "Adam", "sales", (), EPOCH + timedelta(hours=4)),
    ]


def walk(asked: ListAsked, *, reader: str = "reader-a", over: list[Row] | None = None) -> list[str]:
    """Every row id a reader reaches by following the cursor from the first page."""
    found: list[str] = []
    cursor: str | None = None
    for _ in range(20):
        page: Paged[Row] = LISTING.page(
            over if over is not None else rows(),
            ListAsked(
                limit=asked.limit,
                cursor=cursor,
                search=asked.search,
                filters=asked.filters,
                sort=asked.sort,
            ),
            reader=reader,
        )
        found.extend(one.row_id for one in page.items)
        if page.next_cursor is None:
            return found
        cursor = page.next_cursor
    msg = "the walk did not end"
    raise AssertionError(msg)


def test_walking_the_cursor_reaches_every_row_once_in_the_order_asked() -> None:
    """What breaks if this is deleted: a keyset comparison that skips or repeats the row a page
    boundary falls on, which is the failure a cursor exists to prevent and the one nobody sees on a
    list shorter than a page. Ties on the order key are broken by the row key, so "adam" and "Adam"
    are both reached."""
    assert walk(ListAsked(limit=2)) == ["r2", "r5", "r3", "r4", "r1"]
    assert walk(ListAsked(limit=2, sort="-name")) == ["r1", "r4", "r3", "r5", "r2"]
    assert walk(ListAsked(limit=1, sort="-at")) == ["r5", "r4", "r3", "r2", "r1"]
    assert walk(ListAsked(limit=MAX_PAGE_ROWS)) == ["r2", "r5", "r3", "r4", "r1"]


def test_a_cursor_is_sent_exactly_when_a_further_matching_row_exists() -> None:
    """What breaks if this is deleted: a cursor on a page that was exactly full, which sends the
    reader to an empty second page, or no cursor when one row is left. Both are counts of one."""
    assert LISTING.page(rows(), ListAsked(limit=5), reader="a").next_cursor is None
    assert LISTING.page(rows(), ListAsked(limit=4), reader="a").next_cursor is not None
    narrowed = ListAsked(limit=2, filters=("department:finance",))
    assert LISTING.page(rows(), narrowed, reader="a").next_cursor is None


def test_a_search_matches_the_fields_the_row_shows_and_never_one_it_withholds() -> None:
    """What breaks if this is deleted: a search that reads the stored record, which lets a reader
    learn a withheld value by asking whether a row comes back. `secret` is on every row and on no
    column, so searching for it must find nothing, and searching for a shown value must find the
    row: the positive half is what stops a search that matches nothing passing."""
    assert walk(ListAsked(search="withheld-value")) == []
    assert walk(ListAsked(search="ZOE")) == ["r1"]
    assert walk(ListAsked(search="sales adam")) == ["r2", "r5"]
    assert walk(ListAsked(search="south")) == ["r2"]


def test_a_search_word_must_sit_inside_one_field_and_not_across_two() -> None:
    """What breaks if this is deleted: a search that joins fields without a separator, so "zoefin"
    matches a row whose name ends "zoe" and whose department starts "fin"."""
    assert walk(ListAsked(search="zoefinance")) == []
    assert walk(ListAsked(search="zoe finance")) == ["r1"]


def test_a_filter_is_an_equality_on_a_declared_column_and_two_terms_mean_both() -> None:
    """What breaks if this is deleted: a filter read as a substring, which is a search with another
    name, or two terms read as either, which is not what `brain.api_routes.filter_scope` means by
    the same grammar. A list column matches when any of its values is equal."""
    assert walk(ListAsked(filters=("department:finance",))) == ["r4", "r1"]
    assert walk(ListAsked(filters=("department:fin",))) == []
    assert walk(ListAsked(filters=("tags:north",))) == ["r2", "r1"]
    assert walk(ListAsked(filters=("tags:north", "tags:south"))) == ["r2"]
    assert walk(ListAsked(filters=("department:finance", "department:sales"))) == []


def test_an_undeclared_order_or_filter_is_refused_before_a_row_is_read() -> None:
    """What breaks if this is deleted: an order by a column that is not on the row, which sorts by
    something the reader cannot see and so tells them about it, or a filter on one silently
    ignored, which draws unfiltered rows as matching ones."""
    with pytest.raises(RequestValidationError):
        LISTING.page([], ListAsked(sort="secret"), reader="a")
    with pytest.raises(RequestValidationError):
        LISTING.page([], ListAsked(sort="tags"), reader="a")
    with pytest.raises(RequestValidationError):
        LISTING.page([], ListAsked(filters=("name:Zoe",)), reader="a")
    assert LISTING.page([], ListAsked(sort="-at"), reader="a").items == ()


def _refusal(asked: ListAsked, reader: str) -> tuple[object, ...]:
    with pytest.raises(RequestValidationError) as caught:
        LISTING.page(rows(), asked, reader=reader)
    return tuple(caught.value.errors())


def test_a_cursor_minted_for_one_reader_is_refused_for_another_exactly_as_garbage_is() -> None:
    """What breaks if this is deleted: a cursor that travels between readers. Each page is decided
    from the presenter's own reach, so a copied cursor reads nothing it should not, but it would be
    reinterpreted under somebody else's question; and a refusal worded differently from a malformed
    cursor's would say the cursor was real. The positive half is the owner's cursor working."""
    minted = LISTING.page(rows(), ListAsked(limit=2), reader="reader-a").next_cursor
    assert minted is not None
    assert LISTING.page(rows(), ListAsked(limit=2, cursor=minted), reader="reader-a").items
    garbage = _refusal(ListAsked(limit=2, cursor="not a cursor at all"), "reader-b")
    assert _refusal(ListAsked(limit=2, cursor=minted), "reader-b") == garbage


def test_a_cursor_for_another_order_or_search_is_refused() -> None:
    """What breaks if this is deleted: a position taken under one order read under another, which
    starts the second walk at an arbitrary row and skips everything before it without a word."""
    minted = LISTING.page(rows(), ListAsked(limit=2), reader="a").next_cursor
    assert minted is not None
    for other in (
        ListAsked(limit=2, cursor=minted, sort="-name"),
        ListAsked(limit=2, cursor=minted, search="adam"),
        ListAsked(limit=2, cursor=minted, filters=("department:sales",)),
    ):
        with pytest.raises(RequestValidationError):
            LISTING.page(rows(), other, reader="a")
    # The limit is not part of the question: a reader may ask for a longer next page.
    assert LISTING.page(rows(), ListAsked(limit=3, cursor=minted), reader="a").items


def test_a_forged_cursor_starts_inside_the_presenters_rows_and_never_raises() -> None:
    """What breaks if this is deleted: a hand-written cursor whose key does not compare with the
    rows' keys, which raises a TypeError and answers a 500, or one that reaches past the rows it was
    handed. The binding is computable by anybody who knows the reader's id, so the property that
    matters is that a forged position only ever narrows the reader's own rows."""
    asked = ListAsked(limit=10)
    binding = LISTING.binding(asked, "reader-a")
    for key in ((2, "0"), (1, 5.5), (0, 0), (2, "m")):
        forged = encode_position((key, ""), binding)
        page = LISTING.page(rows(), ListAsked(limit=10, cursor=forged), reader="reader-a")
        assert {one.row_id for one in page.items} <= {one.row_id for one in rows()}
    wrong_kind = base64.urlsafe_b64encode(
        json.dumps({"v": 1, "b": binding, "k": [2, 5], "r": ""}).encode()
    ).decode()
    with pytest.raises(RequestValidationError):
        LISTING.page(rows(), ListAsked(limit=10, cursor=wrong_kind), reader="reader-a")


def test_an_order_key_tags_its_kind_so_absent_numbers_and_text_never_fail_to_compare() -> None:
    """What breaks if this is deleted: an order over a column where some rows have no value, which
    compares None with a string and raises."""
    keys = sorted([sort_key("b"), sort_key(None), sort_key(3), sort_key(EPOCH), sort_key(True)])
    assert keys[0] == sort_key(None)
    assert keys[-1] == sort_key("b")
    with pytest.raises(ListingError):
        sort_key(("a",))


def test_a_listing_is_refused_when_it_orders_by_default_by_what_it_does_not_sort_by() -> None:
    """What breaks if this is deleted: a listing whose every unordered request is refused, found
    by the first reader rather than at import. The positive half is `LISTING` above constructing."""
    with pytest.raises(ListingError):
        Listing(name="x", columns=(Column("a", lambda row: "", sort=False),), key=str, order="a")
    with pytest.raises(ListingError):
        Listing(name="x", columns=(Column("A", lambda row: "", sort=True),), key=str, order="A")
    with pytest.raises(ListingError):
        Listing(
            name="x",
            columns=(Column("a", lambda row: "", sort=True), Column("a", lambda row: "")),
            key=str,
            order="a",
        )


def test_every_filter_term_a_listing_admits_is_one_the_records_grammar_admits() -> None:
    """What breaks if this is deleted: two grammars for one parameter name, so a console that reads
    the records route's pattern builds a term a listing refuses, or the other way round."""
    pattern = LISTING.filter_pattern()
    for term in ("department:finance", "tags:a:b", "department:x y"):
        assert re.fullmatch(pattern, term) is not None
        assert re.fullmatch(FILTER_TERM_PATTERN, term) is not None
    for term in ("name:Zoe", "secret:x", "department:", "department:a\nb"):
        assert re.fullmatch(pattern, term) is None
    nothing: Listing[Row] = Listing(
        name="x", columns=(Column("a", lambda row: "", sort=True),), key=str, order="a"
    )
    assert re.fullmatch(nothing.filter_pattern(), "a:b") is None
    # And it builds under the engine a route validates with, which a lookahead does not.
    unfiltered: TypeAdapter[str] = TypeAdapter(
        Annotated[str, StringConstraints(pattern=nothing.filter_pattern())]
    )
    with pytest.raises(ValidationError):
        unfiltered.validate_python("a:b")


#: The dependency at module level, which is where a route module declares it: a route's annotations
#: are resolved against the module's globals, so a dependency built inside a function is invisible.
RowsQuery = Annotated[ListAsked, Depends(LISTING.query())]


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/rows")
    def listed(asked: RowsQuery) -> dict[str, object]:
        page = LISTING.page(rows(), asked, reader="reader-a")
        return {"items": [one.row_id for one in page.items], "next_cursor": page.next_cursor}

    return app


def test_the_declaration_reaches_the_document_and_refuses_what_it_does_not_name() -> None:
    """What breaks if this is deleted: a `sort` or `filter` pattern that is built and never reaches
    the route, so the document says nothing a console can read and an undeclared column reaches
    the handler. The positive half is a declared order and filter answered."""
    app = _app()
    client = TestClient(app)
    parameters = {
        one["name"]: one["schema"] for one in app.openapi()["paths"]["/rows"]["get"]["parameters"]
    }
    assert set(parameters) == {"limit", CURSOR_PARAM, "q", "filter", "sort"}
    assert "department" in json.dumps(parameters["filter"])
    assert "name" in json.dumps(parameters["sort"])
    assert client.get("/rows", params={"sort": "secret"}).status_code == 422
    assert client.get("/rows", params={"filter": "name:Zoe"}).status_code == 422
    answered = client.get(
        "/rows", params=[("sort", "-at"), ("filter", "department:finance"), ("limit", "1")]
    )
    assert answered.status_code == 200
    assert answered.json()["items"] == ["r4"]
    following = client.get(
        "/rows",
        params=[
            ("sort", "-at"),
            ("filter", "department:finance"),
            ("limit", "1"),
            ("cursor", answered.json()["next_cursor"]),
        ],
    )
    assert following.json() == {"items": ["r1"], "next_cursor": None}


def test_several_acts_run_once_per_key_in_the_order_asked() -> None:
    """What breaks if this is deleted: a bulk act that runs a duplicated key twice, which is two
    ledger entries for one decision, or that reorders the outcomes so a page states the wrong
    outcome beside a row."""
    ran: list[str] = []

    async def act(key: str) -> bool:
        ran.append(key)
        return key != "b"

    outcomes = asyncio.run(each_of(["c", "a", "b", "a"], act))
    assert ran == ["c", "a", "b"]
    assert outcomes == [("c", True), ("a", True), ("b", False)]
