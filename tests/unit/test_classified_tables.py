"""A price list held as classified rows: read from a file, marked, stored, and answered on Ask.

Five layers, one section each, and the last is the one the others exist for. The file reader
(`brain.knowledge.table_file`), the marks (`brain.knowledge.columns`), the statement and the
question shapes (`brain.knowledge.classified_rows`), the routes over an in-memory store, and
Ask itself: `brain.gate.answer.answer_lane` driven over the lane an uploaded table makes, so
"the sell price is answered to everyone permitted the table, and the cost is absent for
everyone without its grant" is asserted on the frames a person receives rather than on a
helper's return value.

**The row source here honours the statement it is given.** `TableRows` returns only the
labels the compiled statement selects and only the rows its bound filter names, so a column
the projection left out cannot reach a record through this fake any more than through
PostgreSQL. A fake that returned whole rows would let a projection bug pass every test below.

**The database half skips without a server**, which CI provides: the store as the
application role, the rows read back through the pool, and the ledger entries `0116` writes.

Task ids: M7.5.1, M7.5.2, M7.5.3, M7.7.3
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import io
import uuid
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import String, create_engine
from sqlalchemy.pool import NullPool

from brain.api_routes import policy_epoch_of
from brain.app import Settings, create_app
from brain.classification_routes import (
    CLASSIFICATION_READ,
    CLASSIFICATION_WRITE,
    TO_CHANGE,
    TO_READ,
    ColumnMark,
    table_within_reach,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.errors import Absent
from brain.core.field_policy import Classification
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.redaction import compute_mask
from brain.core.scope import Clause, Op, Scope
from brain.gate.abstain import NOT_FOUND_TEXT
from brain.gate.answer import Answered, answer_lane
from brain.gate.context import Channel
from brain.gate.fast_lane import RowReader, rules_from_rows
from brain.gate.finish import Origin
from brain.gate.streaming import Event, frames
from brain.knowledge import table_file
from brain.knowledge.classified_rows import (
    TABLES_SOURCE,
    StoredTable,
    compile_table_query,
    lane_for,
    next_upload,
    questions_for,
    read_table_rows,
)
from brain.knowledge.columns import (
    OPEN_SENSITIVITY,
    PRICE_LIST,
    RESTRICTED_SENSITIVITY,
    ColumnAccess,
    ColumnClassificationError,
    TableClassification,
    access_of,
    column_name_for,
    first_classification,
    marked,
    table_capability,
)
from brain.knowledge.rows import RowQuery, RowRecord, RowRequest, RowSource, entity_capability
from brain.knowledge.table_file import TableFileError, is_a_table_file, read_table_file
from brain.ops.classification_store import (
    ClassifiedTables,
    ClassifiedTableStoreError,
    Writer,
    classification_from,
    classified_lane_of,
    columns_document,
)
from brain.tables.classified_table import ClassifiedRecordRow, ClassifiedTableRow
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import token_for
from tests.unit.test_classification_routes import SECOND_FACTOR, _wiring, refusal
from tests.unit.test_streaming import decode

#: PostgreSQL's dialect, for reading back what a compiled statement binds.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)

ENTITY = "prices"
HEADINGS = ("SKU", "Name", "Sell Price", "Cost", "Margin")
ROWS: tuple[dict[str, str], ...] = (
    {
        "sku": "PKG-CARE-1",
        "name": "Website Care",
        "sell_price": "1200",
        "cost": "400",
        "margin": "800",
    },
    {"sku": "PKG-HOST-1", "name": "Hosting", "sell_price": "300", "cost": "120", "margin": "180"},
)
CSV = (
    b"SKU,Name,Sell Price,Cost,Margin\n"
    b"PKG-CARE-1,Website Care,1200,400,800\n"
    b"PKG-HOST-1,Hosting,300,120,180\n"
)


def table(classification: TableClassification | None = None, *, version: int = 1) -> StoredTable:
    """The uploaded price list, classified as a first upload classifies it unless told otherwise."""
    return StoredTable(
        classification=classification
        or first_classification(ENTITY, ("sku", "name", "sell_price", "cost", "margin")),
        title="Price list",
        key_column="name",
        version=version,
    )


def ents(*caps: str, principal: str = "p_asker") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=one), scope=Scope()) for one in caps),
    )


#: Everyone permitted the table, a Finance person, and somebody holding only the cost grant.
SALES = ents("read:prices")
FINANCE = ents("read:prices", "read:prices.cost", "read:prices.margin")
COST_ONLY = ents("read:prices", "read:prices.cost")


class TableRows:
    """A `RowSource` over one table's rows that honours the compiled statement.

    Only the labels the statement selects come back, and only the rows whose key equals the
    filter value the statement binds. See the module docstring for why a looser fake is worse
    than none.
    """

    def __init__(self, rows: Sequence[Mapping[str, str]], key: str = "name") -> None:
        self.data = list(rows)
        self.key = key
        self.queries: list[RowQuery] = []

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.queries.append(query)
        params = query.statement.compile(dialect=DIALECT).params
        wanted = params.get("q0")
        labels = [column.name for column in query.statement.selected_columns]
        out: list[dict[str, Any]] = []
        for position, row in enumerate(self.data):
            if wanted is not None and row.get(self.key) != wanted:
                continue
            full = {"entity": query.entity, "id": str(position), **row}
            out.append({label: full.get(label) for label in labels})
        return out


# ------------------------------------------------------------------ the file reader


def workbook(rows: Sequence[Sequence[str | int]], *, doctype: bool = False) -> bytes:
    """A minimal XLSX: the four parts `table_file` reads, strings shared except one inline."""
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    strings: list[str] = []
    sheet_rows: list[str] = []
    for r, row in enumerate(rows, start=1):
        cells: list[str] = []
        for c, value in enumerate(row):
            ref = f"{chr(ord('A') + c)}{r}"
            if isinstance(value, int):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            elif value.startswith("inline:"):
                text = value.removeprefix("inline:")
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
            else:
                strings.append(value)
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    prologue = '<?xml version="1.0"?>' + ('<!DOCTYPE x [<!ENTITY a "b">]>' if doctype else "")
    parts = {
        "xl/workbook.xml": (
            f'{prologue}<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
            '<sheet name="Prices" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Type="worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>'
        ),
        "xl/sharedStrings.xml": (
            f'<?xml version="1.0"?><sst xmlns="{main}">'
            + "".join(f"<si><t>{one}</t></si>" for one in strings)
            + "</sst>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<?xml version="1.0"?><worksheet xmlns="{main}"><sheetData>'
            + "".join(sheet_rows)
            + "</sheetData></worksheet>"
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as book:
        for name, text in parts.items():
            book.writestr(name, text)
    return buffer.getvalue()


def test_a_csv_price_list_becomes_headings_column_names_and_rows() -> None:
    """The positive case the upload rests on. Delete this and every refusal below is satisfied
    by a reader that refuses everything."""
    parsed = read_table_file("prices.csv", CSV)

    assert parsed.headings == HEADINGS
    assert parsed.columns == ("sku", "name", "sell_price", "cost", "margin")
    assert parsed.rows == ROWS


def test_an_xlsx_price_list_is_read_from_its_first_sheet_without_a_spreadsheet_library() -> None:
    """Shared strings, an inline string and cached numbers, read with the standard library.
    Delete this and the XLSX half of the upload is a branch nothing has run."""
    content = workbook(
        [
            ["SKU", "Name", "Sell Price", "Cost", "Margin"],
            ["PKG-CARE-1", "inline:Website Care", 1200, 400, 800],
            ["PKG-HOST-1", "Hosting", 300, 120, 180],
        ]
    )

    parsed = read_table_file("Prices.XLSX", content)

    assert parsed.columns == ("sku", "name", "sell_price", "cost", "margin")
    assert parsed.rows == ROWS


def test_a_workbook_declaring_a_document_type_is_refused_before_it_is_parsed() -> None:
    """Every entity-expansion attack needs a document type declaration, so refusing one is the
    defence the module docstring relies on in place of defusedxml. Delete this and that
    defence is a sentence nothing checks."""
    with pytest.raises(TableFileError, match="document type"):
        read_table_file("prices.xlsx", workbook([["Name"], ["Hosting"]], doctype=True))


def test_a_workbook_part_past_the_inflation_bound_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The declared size is the file's own claim, so the bound is checked before inflating.
    Delete this and a small zip can ask this process to hold as much as it declares."""
    monkeypatch.setattr(table_file, "MAX_PART_BYTES", 64)
    with pytest.raises(TableFileError, match="unpacked"):
        read_table_file("prices.xlsx", workbook([["Name"], ["Hosting"]]))


@pytest.mark.parametrize(
    ("content", "said"),
    [
        (b"Name,Cost\nHosting,1,2\n", "under no heading"),
        (b"Name,name\nHosting,1\n", "rename one"),
        ("Name,£\nHosting,1\n".encode("cp1252"), "UTF-8"),
        (b"Name,Cost\n", "no rows"),
        (b"Name,,Cost\nHosting,1,2\n", "column 2 has no heading"),
        (b"Name,Id\nHosting,1\n", "own tag"),
    ],
)
def test_a_file_that_is_not_a_clean_table_is_refused_in_words_the_uploader_can_act_on(
    content: bytes, said: str
) -> None:
    """Each refusal names what is wrong with the file. Delete this and a stray value, a
    duplicate heading or a mis-encoded file becomes a column nobody recognises, or a product
    name nobody can ask for by its real spelling."""
    with pytest.raises(TableFileError, match=said):
        read_table_file("prices.csv", content)


def test_only_a_csv_or_an_xlsx_is_offered_conversion_to_classified_rows() -> None:
    """M7.7.3's second half asks the document upload which files to offer for conversion, and
    this is the answer. Delete this and a PDF is offered a conversion this module cannot do."""
    assert is_a_table_file("Price List 2026.CSV")
    assert is_a_table_file("prices.xlsx")
    assert not is_a_table_file("prices.pdf")
    assert not is_a_table_file("prices.xls")


# ----------------------------------------------------------------------- the marks


def test_an_open_column_needs_only_the_table_grant_and_a_restricted_one_its_own() -> None:
    """The two capabilities the whole feature turns on. Delete this and "open" can quietly
    mean a column grant nobody holds, so the sell price disappears for the company."""
    open_rule = marked(ENTITY, "sell_price", ColumnAccess.OPEN)
    restricted = marked(ENTITY, "cost", ColumnAccess.RESTRICTED)

    assert open_rule.required_capability == entity_capability(ENTITY)
    assert open_rule.required_capability == table_capability(ENTITY)
    assert restricted.required_capability.value == "read:prices.cost"
    assert (open_rule.classification, restricted.classification) == (
        Classification.INTERNAL,
        Classification.CONFIDENTIAL,
    )
    assert OPEN_SENSITIVITY.rank < RESTRICTED_SENSITIVITY.rank


def test_a_derived_mark_names_its_inputs_and_no_other_mark_may() -> None:
    """Delete this and a derivation can sit on an open column where it never fires, reading as
    a control while being a comment."""
    with pytest.raises(ColumnClassificationError, match="names no column"):
        marked(ENTITY, "margin", ColumnAccess.DERIVED)
    with pytest.raises(ColumnClassificationError, match="only a derived column"):
        marked(ENTITY, "sell_price", ColumnAccess.OPEN, ("cost",))
    derived = marked(ENTITY, "margin", ColumnAccess.DERIVED, ("sell_price", "cost"))
    assert derived.derived_from == frozenset({"sell_price", "cost"})


def test_every_mark_reads_back_as_itself_and_a_built_in_rule_as_no_mark() -> None:
    """The screen shows the mark a stored column carries. Delete this and a restricted column
    can be shown as open, which is the statement about who may see it that matters most."""
    for access, inputs in (
        (ColumnAccess.OPEN, ()),
        (ColumnAccess.RESTRICTED, ()),
        (ColumnAccess.DERIVED, ("sell_price",)),
    ):
        assert access_of(ENTITY, marked(ENTITY, "cost", access, inputs)) is access
    sell = PRICE_LIST.rule_for("sell_price")
    assert sell is not None
    assert access_of(PRICE_LIST.entity, sell) is None


def test_a_derivation_whose_every_input_is_open_is_refused_so_no_open_column_is_withheld() -> None:
    """See `A_DERIVATION_FROM_OPEN_COLUMNS_PROTECTS_NOTHING`. The positive half: with one input
    restricted the classification loads, and a caller permitted the table keeps the sell price.
    Delete this and the closure can again withhold an open column from everybody."""
    rules = {rule.column: rule for rule in table().classification.rules}
    with pytest.raises(ColumnClassificationError, match="all open"):
        TableClassification(
            entity=ENTITY,
            rules=(
                *(r for c, r in rules.items() if c != "cost"),
                marked(ENTITY, "cost", ColumnAccess.OPEN),
            ),
        )
    kept = TableClassification(
        entity=ENTITY,
        rules=(
            *(r for c, r in rules.items() if c != "cost"),
            marked(ENTITY, "cost", ColumnAccess.RESTRICTED),
        ),
    )
    query = compile_table_query(table(kept), RowRequest(), entitlement=COST_ONLY)
    assert "sell_price" in query.columns


def test_a_new_table_opens_nothing_a_price_list_would_not() -> None:
    """Default-deny at upload. A column the shipped price list does not know starts restricted,
    and the ones it does start as it ships them. Delete this and an upload can be the act that
    widens what everybody sees."""
    first = first_classification(ENTITY, ("sku", "name", "sell_price", "cost", "margin", "notes"))
    marks = {rule.column: access_of(ENTITY, rule) for rule in first.rules}

    assert marks == {
        "sku": ColumnAccess.OPEN,
        "name": ColumnAccess.OPEN,
        "sell_price": ColumnAccess.OPEN,
        "cost": ColumnAccess.DERIVED,
        "margin": ColumnAccess.DERIVED,
        "notes": ColumnAccess.RESTRICTED,
    }
    alone = first_classification(ENTITY, ("name", "cost"))
    assert access_of(ENTITY, alone.rules[1]) is ColumnAccess.RESTRICTED


def test_a_heading_becomes_a_field_name_or_is_refused() -> None:
    """Delete this and a heading can become a column the field policy cannot name."""
    assert column_name_for(" Sell Price (SGD) ") == "sell_price_sgd"
    for bad in ("", "  ", "2026 price", "id", "***"):
        with pytest.raises(ColumnClassificationError):
            column_name_for(bad)


def test_the_compiled_rule_carries_the_derivation_so_the_redactor_closes_over_it() -> None:
    """**The known defect, fixed.** `as_field_rule` dropped `derived_from`, so a price-list row
    handed straight to the redactor showed a cost-only reader the sell price and the cost, and
    the margin was a subtraction away. Delete this and the redactor's own closure goes back to
    never firing for a column classification."""
    policy = PRICE_LIST.policy()
    cost = policy.rule_for("price_list", "cost")
    assert cost is not None
    assert cost.derived_from == ("margin", "sell_price")

    row = {"sell_price": 1200, "cost": 400, "margin": 800}
    mask = compute_mask(
        "price_list",
        row,
        entitlement=ents("read:price_list.sell_price", "read:price_list.cost"),
        policy=policy,
        row=row,
    )
    assert mask.allowed == frozenset({"sell_price"})


def test_dropping_a_derivation_moves_the_epoch_the_answer_cache_is_keyed_on() -> None:
    """**"The policy epoch moves when a derivation changes", at the key Ask uses.** The lane's
    policies merged the way the answer route merges them, folded by `policy_epoch_of`. Delete
    this and a changed derivation can leave cached answers standing that were computed under
    the old closure."""
    before = table()
    loosened = TableClassification(
        entity=ENTITY,
        rules=tuple(
            marked(ENTITY, "margin", ColumnAccess.RESTRICTED) if rule.column == "margin" else rule
            for rule in before.classification.rules
        ),
    )
    after = table(loosened)

    epoch_before = policy_epoch_of(lane_for([before], TableRows(ROWS)).policies)
    epoch_after = policy_epoch_of(lane_for([after], TableRows(ROWS)).policies)

    assert epoch_before != epoch_after
    assert epoch_before == policy_epoch_of(lane_for([table()], TableRows(ROWS)).policies)


def test_an_upload_again_moves_every_answers_cache_key_and_nothing_else_does() -> None:
    """**A price list uploaded again was answered with the old price from the cache** until the
    answer aged out, because only the policy was in the key (M6.5.2). Each live table's upload is
    now a source epoch: a second upload of the same table moves the key an answer is stored under
    and looked up by, and reading the lane twice over one upload does not.

    Delete this and an upload's new rows can go unseen by anybody asking the question they were
    uploaded to answer, for as long as an answer may be served from the cache."""
    from types import SimpleNamespace

    from brain.api_routes import caching_of
    from brain.gate.cache_key import key_for
    from brain.knowledge.classified_rows import epoch_name

    first = lane_for([table(version=1)], TableRows(ROWS))
    again = lane_for([table(version=1)], TableRows(ROWS))
    second = lane_for([table(version=2)], TableRows(ROWS))

    assert first.epochs == {epoch_name(ENTITY): 1} == again.epochs
    assert second.epochs == {epoch_name(ENTITY): 2}

    def key(lane: Any) -> str:
        caching = caching_of(
            SimpleNamespace(answer_store=object()), lane.policies, (), {}, lane.epochs
        )
        assert caching is not None
        return key_for(
            "what is the sell price of WEB-1001",
            "e" * 32,
            "c" * 16,
            caching.policy_epoch,
            caching.source_epochs,
            caching.sources,
        )

    assert key(first) == key(again)
    assert key(first) != key(second)


# ------------------------------------------------------------------- the statement


def test_a_caller_permitted_the_table_is_sent_the_open_columns_and_nothing_else() -> None:
    """The SELECT list is the projection. Delete this and the cost can be in the statement a
    salesperson's question runs, one redaction bug away from the answer."""
    query = compile_table_query(table(), RowRequest(), entitlement=SALES)
    labels = [column.name for column in query.statement.selected_columns]

    assert query.columns == ("name", "sell_price", "sku")
    assert labels == ["entity", "id", "name", "sell_price", "sku"]
    assert query.source == TABLES_SOURCE


def test_finance_is_sent_every_column_and_a_cost_only_grant_is_sent_neither() -> None:
    """Both sides of the derivation. Cost and margin reconstruct each other beside the sell
    price, so holding one without the other is holding neither. Delete this and a cost-only
    grant shows the cost, and the margin is a subtraction."""
    finance = compile_table_query(table(), RowRequest(), entitlement=FINANCE)
    cost_only = compile_table_query(table(), RowRequest(), entitlement=COST_ONLY)

    assert finance.columns == ("cost", "margin", "name", "sell_price", "sku")
    assert cost_only.columns == ("name", "sell_price", "sku")


def test_filtering_on_a_column_outside_the_projection_compiles_to_nothing() -> None:
    """`cost = 400` returning a row says what the cost is. Delete this and the WHERE clause is
    a value oracle over the column the SELECT list withheld."""
    probe = RowRequest(filters=Scope(clauses=(Clause(field="cost", op=Op.EQ, value="400"),)))
    source = TableRows(ROWS)

    result = asyncio.run(read_table_rows(table(), probe, entitlement=SALES, records=source))

    assert result.records == ()
    assert source.queries == []


def test_a_caller_with_no_grant_on_the_table_never_reaches_the_database() -> None:
    """Delete this and a stranger's question runs a statement, which is at best a round trip
    and at worst a predicate that went missing."""
    source = TableRows(ROWS)
    result = asyncio.run(
        read_table_rows(table(), RowRequest(), entitlement=ents("read:other"), records=source)
    )

    assert result.records == ()
    assert source.queries == []


def test_the_statement_is_pinned_to_the_tables_live_upload() -> None:
    """Delete this and a second upload answers from both files at once, the old price beside
    the new one."""
    query = compile_table_query(table(version=3), RowRequest(), entitlement=SALES)
    params = query.statement.compile(dialect=DIALECT).params

    assert params["entity_1"] == ENTITY
    assert params["version_1"] == 3


def test_every_column_but_the_key_is_asked_about_and_every_shape_is_a_valid_rule() -> None:
    """The shapes go through the rule validator as a set, and the key column is never asked
    about. Delete this and a table can generate a rule set the lane refuses whole."""
    rules = questions_for(table())
    answered = {rule.answer_field for rule in rules}

    assert answered == {"sku", "sell_price", "cost", "margin"}
    assert all(rule.match_field == "name" and rule.source == TABLES_SOURCE for rule in rules)
    assert rules_from_rows([rule.model_dump() for rule in rules]) == rules
    templates = {rule.template for rule in rules}
    assert "what is the sell price of {name}" in templates
    assert "cost of {name}" not in templates


def test_a_second_upload_keeps_the_marks_that_stand_and_starts_a_new_column_restricted() -> None:
    """Delete this and uploading next month's price list resets a column somebody marked, or
    opens one nobody has looked at."""
    remarked = TableClassification(
        entity=ENTITY,
        rules=tuple(
            marked(ENTITY, "cost", ColumnAccess.RESTRICTED) if rule.column == "cost" else rule
            for rule in table().classification.rules
        ),
    )
    again = next_upload(
        table(remarked),
        entity=ENTITY,
        title="Price list",
        key_column=None,
        columns=("sku", "name", "sell_price", "cost", "margin", "discount"),
    )

    assert again.version == 2
    assert again.key_column == "name"
    cost = again.classification.rule_for("cost")
    discount = again.classification.rule_for("discount")
    assert cost is not None and access_of(ENTITY, cost) is ColumnAccess.RESTRICTED
    assert discount is not None and access_of(ENTITY, discount) is ColumnAccess.RESTRICTED


def test_a_second_upload_dropping_a_derivations_input_is_refused_rather_than_repaired() -> None:
    """Repairing it would mean dropping the derivation, the one edit that widens who can work
    out the column it protected. Delete this and a re-upload without the margin column quietly
    frees the cost's other input."""
    with pytest.raises(ColumnClassificationError, match="not classified here"):
        next_upload(
            table(),
            entity=ENTITY,
            title="Price list",
            key_column=None,
            columns=("sku", "name", "sell_price", "cost"),
        )


# ---------------------------------------------------------------------------- Ask


def ask(
    question: str,
    reach: EntitlementSet,
    tables: Sequence[StoredTable] | None = None,
    *,
    records: RowSource | None = None,
) -> Answered:
    """One question through the answer lane, over the lane the uploaded tables make."""
    lane = lane_for(
        tables if tables is not None else [table()],
        records if records is not None else TableRows(ROWS),
    )
    return asyncio.run(
        answer_lane(
            question,
            origin=Origin(
                trace_id="t-classified",
                principal=Principal(
                    id=reach.principal_id,
                    kind=PrincipalKind.HUMAN,
                    employment=Employment.STAFF,
                    display_name="Asker",
                ),
                channel=Channel.CONSOLE,
            ),
            recorders=(),
            rules=lane.rules,
            readers=lane.readers,
            entitlement=reach,
            policies=lane.policies,
            reachable_sources=(TABLES_SOURCE,),
            sink=Sink(),
            now=NOW,
            clock=lambda: NOW,
        )
    )


class Sink:
    def emit(self, reference: str, payload: Any, trace: Any) -> None:
        return None


def texts(answered: Answered) -> list[str]:
    return [one.data for one in decode(frames(answered.frames)) if one.event == Event.TEXT.value]


def test_on_ask_the_sell_price_is_answered_to_everyone_permitted_the_table() -> None:
    """**The install sentence's first half, on the frames a person receives.** Delete this and
    every absence below is satisfied by a lane that answers nobody."""
    answered = ask("What is the sell price of Website Care?", SALES)

    assert answered.text is not None
    assert "1200" in answered.text


def test_on_ask_the_cost_is_answered_to_a_person_holding_the_cost_grant() -> None:
    """The sibling: the restricted column does answer, for Finance. Delete this and the cost is
    simply unanswerable, which is the second stale copy of the price list waiting to happen."""
    answered = ask("What is the cost of Website Care?", FINANCE)
    margin = ask("What is the margin of Website Care?", FINANCE)

    assert answered.text is not None and "400" in answered.text
    assert margin.text is not None and "800" in margin.text


def test_on_ask_the_cost_is_absent_not_refused_for_everyone_else() -> None:
    """**The install sentence's second half.** A salesperson asking for the cost of a product
    that exists receives, byte for byte, what they receive asking about a product that does
    not. See `A_RESTRICTED_COLUMN_IS_ABSENT_FOR_A_CALLER_WITHOUT_ITS_GRANT`. Delete this and a
    refusal can grow a helpful word that says the cost exists and somebody else can read it."""
    withheld = ask("What is the cost of Website Care?", SALES)
    absent = ask("What is the cost of Nothing Real?", SALES)

    assert withheld.text is None
    assert withheld.frames == absent.frames
    assert NOT_FOUND_TEXT in texts(withheld)[0]
    assert "400" not in frames(withheld.frames)


def test_a_cost_only_grant_is_answered_neither_the_cost_nor_the_margin() -> None:
    """The derivation on Ask. Delete this and a cost-only grant reads the cost beside the sell
    price, and the margin with it."""
    assert ask("What is the cost of Website Care?", COST_ONLY).text is None
    assert ask("What is the margin of Website Care?", COST_ONLY).text is None
    assert "1200" in (ask("What is the sell price of Website Care?", COST_ONLY).text or "")


def test_changing_a_derivation_changes_what_ask_answers_on_the_next_question() -> None:
    """The lane is built per question from the tables as they stand. With the derivation on
    the margin dropped, a cost-only grant reads the cost. Delete this and a changed
    classification reaches Ask only after a restart."""
    loosened = TableClassification(
        entity=ENTITY,
        rules=tuple(
            marked(ENTITY, "margin", ColumnAccess.RESTRICTED) if rule.column == "margin" else rule
            for rule in table().classification.rules
        ),
    )
    answered = ask("What is the cost of Website Care?", COST_ONLY, [table(loosened)])

    assert "400" in (answered.text or "")


# ------------------------------------------------- two price lists (found on staging)

#: A second price list with the same columns, one service of its own and one the first list
#: also names, as a second upload on the owner's install had.
RATES = "rates"
RATE_ROWS: tuple[dict[str, str], ...] = (
    {
        "sku": "RATE-DEV-1",
        "name": "Development Day",
        "sell_price": "950",
        "cost": "500",
        "margin": "450",
    },
    {"sku": "RATE-HOST-1", "name": "Hosting", "sell_price": "340", "cost": "150", "margin": "190"},
)

#: Readers of both lists: the tables alone, and the tables with the second list's cost grants.
SALES_BOTH = ents("read:prices", "read:rates")
RATES_FINANCE = ents("read:prices", "read:rates", "read:rates.cost", "read:rates.margin")


class ByTable:
    """A `RowSource` over several uploaded tables, each honouring the statement as `TableRows`
    does, chosen by the entity the statement is pinned to."""

    def __init__(self, held: Mapping[str, Sequence[Mapping[str, str]]]) -> None:
        self.tables = {entity: TableRows(rows) for entity, rows in held.items()}

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        source = self.tables.get(query.entity)
        return () if source is None else await source.rows(query)


def rates() -> StoredTable:
    """The second list, classified as a first upload classifies it."""
    return StoredTable(
        classification=first_classification(RATES, ("sku", "name", "sell_price", "cost", "margin")),
        title="Day rates",
        key_column="name",
        version=1,
    )


def ask_both(question: str, reach: EntitlementSet) -> Answered:
    """One question over the lane both uploaded lists make, each read from its own rows."""
    return ask(
        question,
        reach,
        [table(), rates()],
        records=ByTable({ENTITY: ROWS, RATES: RATE_ROWS}),
    )


def test_two_price_lists_with_a_sell_price_each_answer_for_their_own_services() -> None:
    """**Found on the owner's install on 2026-09-29.** A second uploaded table with a sell price
    column made Ask answer nobody about either, because both are asked in the same words and the
    fast lane refused the pair as two rules matching. Each list now answers for its own services.
    Delete this and uploading a second price list silences the first."""
    first = ask_both("What is the sell price of Website Care?", SALES_BOTH)
    second = ask_both("What is the sell price of Development Day?", SALES_BOTH)

    assert first.text is not None and "1200" in first.text
    assert second.text is not None and "950" in second.text


def test_each_of_two_price_lists_still_withholds_what_the_reader_may_not_see() -> None:
    """The sibling: answering from two lists withholds exactly what one list withholds. A reader
    with neither cost grant asking a service's cost is answered as for a service that does not
    exist; a reader holding the second list's cost grant is told its cost and not the first's.
    Delete this and the second list's rows can be answered past the first list's classification."""
    withheld = ask_both("What is the cost of Development Day?", SALES_BOTH)
    absent = ask_both("What is the cost of Nothing Real?", SALES_BOTH)
    theirs = ask_both("What is the cost of Development Day?", RATES_FINANCE)
    not_theirs = ask_both("What is the cost of Website Care?", RATES_FINANCE)

    assert withheld.text is None
    assert withheld.frames == absent.frames
    assert "500" not in frames(withheld.frames)
    assert theirs.text is not None and "500" in theirs.text
    assert not_theirs.text is None
    assert not_theirs.frames == absent.frames


def test_a_service_both_lists_name_is_answered_by_neither_to_a_reader_of_both() -> None:
    """Two lists naming one service is the ambiguous name it would be inside one list, and it is
    told in the words an absent service is. Delete this and whichever list was uploaded first
    quotes its price for a service the other list prices differently."""
    ambiguous = ask_both("What is the sell price of Hosting?", SALES_BOTH)
    absent = ask_both("What is the sell price of Nothing Real?", SALES_BOTH)

    assert ambiguous.text is None
    assert ambiguous.frames == absent.frames


def test_a_list_the_reader_may_not_read_answers_as_if_it_had_never_been_uploaded() -> None:
    """**DENIED and ABSENT across tables.** A reader of the first list alone, asking about a service
    both lists name, is answered from the first list, byte for byte as on an install where the
    second was never uploaded. Delete this and a list somebody cannot read changes what they are
    told, which tells them it exists and names the service."""
    both = ask_both("What is the sell price of Hosting?", SALES)
    alone = ask("What is the sell price of Hosting?", SALES)

    assert both.text is not None and "300" in both.text
    assert both.frames == alone.frames


# ---------------------------------------------------------------- the routes


class MemoryTables(ClassifiedTables):
    """The store, in memory: what the routes need and a record of every writer."""

    def __init__(self) -> None:
        self.tables: dict[str, StoredTable] = {}
        self.rows: dict[tuple[str, int], list[Mapping[str, str]]] = {}
        self.writers: list[Writer] = []

    async def table(self, entity: str) -> StoredTable | None:
        return self.tables.get(entity)

    async def live_tables(self) -> tuple[StoredTable, ...]:
        return tuple(self.tables[name] for name in sorted(self.tables))

    async def upload(
        self, table: StoredTable, rows: Sequence[Mapping[str, str]], *, writer: Writer
    ) -> StoredTable:
        current = self.tables.get(table.entity)
        if table.version != (1 if current is None else current.version + 1):
            raise ClassifiedTableStoreError("somebody else uploaded this table a moment ago")
        self.tables[table.entity] = table
        self.rows[(table.entity, table.version)] = list(rows)
        self.writers.append(writer)
        return table

    async def classify(
        self, entity: str, classification: TableClassification, *, writer: Writer
    ) -> StoredTable | None:
        current = self.tables.get(entity)
        if current is None:
            return None
        stored = StoredTable(
            classification=classification,
            title=current.title,
            key_column=current.key_column,
            version=current.version,
        )
        self.tables[entity] = stored
        self.writers.append(writer)
        return stored

    async def rows_of(self, table: StoredTable) -> tuple[Mapping[str, str], ...]:
        return tuple(self.rows.get((table.entity, table.version), ()))

    def records(self) -> TableRows:
        live = self.tables[ENTITY]
        return TableRows(self.rows[(ENTITY, live.version)])


API = "/api/v1/classifications"


@pytest.fixture
def memory() -> MemoryTables:
    return MemoryTables()


@pytest.fixture
def client(memory: MemoryTables) -> Iterator[TestClient]:
    """The real application with the gate, and uploaded tables kept in memory."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.classified_tables = memory
        yield c


def call(c: TestClient, method: str, path: str, pid: str, body: object | None = None) -> Response:
    headers = {"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}
    response: Response = c.request(method, f"{API}{path}", headers=headers, json=body)
    return response


def upload(
    c: TestClient, pid: str = "u_admin", overrides: Mapping[str, object] | None = None
) -> Response:
    body: dict[str, object] = {
        "title": "Price list",
        "filename": "prices.csv",
        "content_base64": base64.b64encode(CSV).decode(),
        "key_column": "Name",
    }
    body.update(overrides or {})
    entity = str(body.pop("entity", ENTITY))
    return call(c, "PUT", f"/{entity}/table", pid, body)


def mark(
    c: TestClient, column: str, access: str, inputs: Sequence[str] = (), *, apply: bool = True
) -> Response:
    body = {"access": access, "derived_from": list(inputs)}
    if apply:
        return call(c, "PUT", f"/{ENTITY}/columns/{column}/marks", "u_admin", body)
    return call(c, "POST", f"/{ENTITY}/columns/{column}/marks/review", "u_admin", body)


def test_an_administrator_uploads_a_price_list_and_is_answered_its_classification(
    client: TestClient, memory: MemoryTables
) -> None:
    """**The upload on the Classification screen.** A CSV becomes a stored table whose columns
    carry marks, and reading the classification afterwards shows the stored one. Delete this
    and the upload route can store nothing and still answer 200."""
    answered = upload(client)

    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert body["refused"] == ""
    view = body["classification"]
    assert view["stored"] is True
    assert view["key_column"] == "name"
    assert {one["column"]: one["access"] for one in view["columns"]} == {
        "sku": "open",
        "name": "open",
        "sell_price": "open",
        "cost": "derived",
        "margin": "derived",
    }
    assert memory.rows[(ENTITY, 1)] == list(ROWS)
    read = call(client, "GET", f"/{ENTITY}", "u_narrow").json()
    assert read["stored"] is True
    assert read["title"] == "Price list"


def test_the_ledger_is_told_who_uploaded_at_what_reach(
    client: TestClient, memory: MemoryTables
) -> None:
    """The writer the store is handed is the caller the gate resolved. Delete this and a route
    can pass nobody, and `0116`'s ledger entry names the placeholder."""
    upload(client)

    assert [one.actor_id for one in memory.writers] == ["u_admin"]
    assert len(memory.writers[0].ent_hash) == 32


def test_uploading_without_both_grants_is_refused_as_a_stranger_is(client: TestClient) -> None:
    """Delete this and somebody who may read a classification can replace a price list."""
    reader = upload(client, "u_narrow")
    stranger = upload(client, "u_none")

    assert reader.status_code == 404
    assert refusal(reader) == refusal(stranger)
    assert reader.json()["message"] == Absent.public_message


@pytest.mark.parametrize(
    ("overrides", "said"),
    [
        ({"entity": "price_list"}, "ships with"),
        ({"entity": "Prices"}, "lowercase"),
        ({"content_base64": "not base64!"}, "intact"),
        ({"filename": "prices.pdf"}, ".csv"),
        ({"key_column": "Discount"}, "key column"),
    ],
)
def test_an_upload_that_cannot_be_held_is_refused_with_a_sentence_and_stores_nothing(
    client: TestClient, memory: MemoryTables, overrides: dict[str, object], said: str
) -> None:
    """Each refusal is an answer the uploader can act on, and nothing is written. The product's
    own entity is refused because `classification_for` is keyed on the entity alone. Delete
    this and an upload named `price_list` gives one entity two classifications."""
    answered = upload(client, overrides=overrides)

    assert answered.status_code == 200
    assert said in answered.json()["refused"]
    assert answered.json()["classification"] is None
    assert memory.tables == {}


def test_applying_a_mark_stores_it_and_moves_the_epoch_when_a_derivation_changes(
    client: TestClient, memory: MemoryTables
) -> None:
    """**M7.5.3 and "the policy epoch moves when a derivation changes", through the screen's
    own request.** Marking the margin plain restricted drops its derivation: the response says
    it widens and names the cost as newly reachable, the store holds the new rule, and the
    epoch read back has moved. Delete this and the editor can save a widening nobody was told
    about, under an epoch the answer cache still trusts."""
    upload(client)
    before = call(client, "GET", f"/{ENTITY}", "u_admin").json()["epoch"]

    applied = mark(client, "margin", "restricted")

    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["applied"] is True
    assert body["review"]["widens"] is True
    assert "cost" in body["review"]["exposed"]
    assert body["review"]["epoch_now"] != body["review"]["epoch_after"]
    after = call(client, "GET", f"/{ENTITY}", "u_admin").json()["epoch"]
    assert after != before
    assert after == body["classification"]["epoch"]
    margin = memory.tables[ENTITY].classification.rule_for("margin")
    assert margin is not None and margin.derived_from == frozenset()


def test_a_mark_review_stores_nothing(client: TestClient, memory: MemoryTables) -> None:
    """Delete this and reviewing a mark can apply it, so the widening is named after it
    happened rather than before."""
    upload(client)
    stored = memory.tables[ENTITY]

    reviewed = mark(client, "cost", "restricted", apply=False)

    assert reviewed.json()["widens"] is True
    assert reviewed.json()["exposed"] == ["margin"]
    assert memory.tables[ENTITY] is stored
    assert len(memory.writers) == 1


def test_a_mark_that_would_not_load_is_answered_and_not_applied(
    client: TestClient, memory: MemoryTables
) -> None:
    """A derived mark naming no input, and a column the file did not carry. Delete this and a
    malformed mark is either a 500 or a stored classification that refuses to load on Ask."""
    upload(client)

    empty = mark(client, "margin", "derived").json()
    missing = mark(client, "discount", "open").json()

    assert empty["applied"] is False and "names no column" in empty["review"]["would_not_load"]
    assert missing["applied"] is False
    assert "no column" in missing["review"]["would_not_load"]
    assert len(memory.writers) == 1


def test_opening_an_input_of_a_derivation_whose_inputs_would_all_be_open_is_not_applied(
    client: TestClient, memory: MemoryTables
) -> None:
    """**The defect the database test found.** Opening the cost while the margin stays derived
    from the sell price and the cost left the margin reconstructable by everybody, and the
    closure withheld the sell price from the whole company to protect it: two open columns tie
    on sensitivity and the tie is broken by name. The route now answers that the rule would not
    load. Delete this and one press on the Classification screen takes the price list's price
    away from everybody while telling the administrator it opened a column."""
    upload(client)

    answered = mark(client, "cost", "open").json()

    assert answered["applied"] is False
    assert "all open" in answered["review"]["would_not_load"]
    cost = memory.tables[ENTITY].classification.rule_for("cost")
    assert cost is not None and access_of(ENTITY, cost) is ColumnAccess.DERIVED


def test_a_built_in_classification_takes_no_mark(client: TestClient) -> None:
    """The shipped price list is a constant and changes by a release. Delete this and a mark
    can appear to apply to it."""
    refused = call(
        client,
        "PUT",
        "/price_list/columns/cost/marks",
        "u_admin",
        {"access": "open", "derived_from": []},
    )
    assert refused.status_code == 404
    assert refused.json()["message"] == Absent.public_message


def test_a_mark_body_carries_no_capability_and_no_sensitivity() -> None:
    """The capability and the sensitivity follow from the mark. Delete this and a column
    marked restricted can be sent with the table grant beside it."""
    assert set(ColumnMark.model_fields) == {"access", "derived_from"}
    assert CLASSIFICATION_WRITE.verb == "admin"
    assert CLASSIFICATION_READ.verb == "read"


def test_ask_reads_what_the_store_holds_on_the_next_question(
    client: TestClient, memory: MemoryTables
) -> None:
    """`classified_lane_of` is the answer route's one call. Delete this and the lane can be
    built from something other than the tables as they stand."""
    upload(client)
    app: Any = client.app

    lane = asyncio.run(classified_lane_of(app.state))

    assert set(lane.readers) == {(TABLES_SOURCE, ENTITY)}
    assert set(lane.policies) == {ENTITY}
    reader: RowReader = lane.readers[(TABLES_SOURCE, ENTITY)]

    async def read() -> TypedResult[RowRecord]:
        return await reader(RowRequest(), entitlement=SALES, now=NOW)

    result = asyncio.run(read())
    assert {one.model_dump().get("sell_price") for one in result.records} == {"1200", "300"}
    assert all("cost" not in one.model_dump() for one in result.records)


def test_a_process_with_no_store_has_an_empty_lane() -> None:
    """Delete this and a process with no database fails every question on the lane's read."""

    class Nothing:
        pass

    assert asyncio.run(classified_lane_of(Nothing())).readers == {}


# ------------------------------------- a department's administrator (found on staging)


def both_grants(scope: Scope) -> tuple[Grant, ...]:
    """The two classification grants, held within one scope."""
    return tuple(
        Grant(capability=one, scope=scope) for one in (CLASSIFICATION_READ, CLASSIFICATION_WRITE)
    )


#: Web's administrator, Finance's administrator and the install's, and web's reader of
#: classifications, who may read them and change nothing, under four of the people
#: `tests.unit.test_api_routes` mints tokens for.
WEB_ADMIN, FINANCE_ADMIN, INSTALL_ADMIN = "u_prefix", "u_elsewhere", "u_admin"
WEB_READER = "u_narrow"
SCOPED_GRANTS: Mapping[str, tuple[Grant, ...]] = {
    WEB_ADMIN: both_grants(Scope.department("web")),
    FINANCE_ADMIN: both_grants(Scope.department("finance")),
    INSTALL_ADMIN: both_grants(Scope.unrestricted()),
    WEB_READER: (Grant(capability=CLASSIFICATION_READ, scope=Scope.department("web")),),
}


class ScopedStore:
    """A `brain.gate.resolve.EntitlementStore` over `SCOPED_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=SCOPED_GRANTS.get(principal_id, ()))


@pytest.fixture
def departments(memory: MemoryTables) -> Iterator[TestClient]:
    """The real application, with three administrators of different reach, tables in memory."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = dataclasses.replace(_wiring(), store=ScopedStore())
        app.state.classified_tables = memory
        yield c


def placed(department: str) -> bytes:
    """A price list whose every row is placed in one department."""
    return (
        f"Name,Department,Sell Price,Cost\n"
        f"Website Care,{department},1200,400\nHosting,{department},300,120\n"
    ).encode()


def upload_as(c: TestClient, pid: str, entity: str, content: bytes) -> Response:
    body = {
        "title": "Price list",
        "filename": f"{entity}.csv",
        "content_base64": base64.b64encode(content).decode(),
        "key_column": "Name",
    }
    return call(c, "PUT", f"/{entity}/table", pid, body)


def mark_as(c: TestClient, pid: str, entity: str, *, apply: bool) -> Response:
    """Mark a table's cost plain restricted, a change every one of these price lists can take."""
    body = {"access": "restricted", "derived_from": []}
    if apply:
        return call(c, "PUT", f"/{entity}/columns/cost/marks", pid, body)
    return call(c, "POST", f"/{entity}/columns/cost/marks/review", pid, body)


def review_as(c: TestClient, pid: str, entity: str) -> Response:
    """The rule review, which answers for an uploaded table as well as a built-in one."""
    body = {"required_capability": f"read:{entity}.cost", "classification": "confidential"}
    return call(c, "POST", f"/{entity}/columns/cost/review", pid, {**body, "derived_from": []})


def test_a_table_is_within_reach_only_when_both_grants_admit_every_row_it_holds() -> None:
    """`A_TABLE_IS_CHANGED_BY_SOMEBODY_WHOSE_GRANTS_ADMIT_EVERY_ROW_IT_HOLDS` at its edges: one row
    in another department puts the whole table out of reach, a row placed nowhere is the whole
    company's, a table with no rows is only the install-wide administrator's, and the read grant
    held elsewhere is as good as not held. Delete this and a table with a single finance row among
    web's, or an empty one, is a web administrator's to classify."""
    web = EntitlementSet(principal_id="p_web", grants=both_grants(Scope.department("web")))
    install = EntitlementSet(principal_id="p_all", grants=both_grants(Scope.unrestricted()))
    split = EntitlementSet(
        principal_id="p_split",
        grants=(
            Grant(capability=CLASSIFICATION_WRITE, scope=Scope.department("web")),
            Grant(capability=CLASSIFICATION_READ, scope=Scope.department("finance")),
        ),
    )
    in_web, in_finance, nowhere = {"department": "web"}, {"department": "finance"}, {"name": "x"}

    assert table_within_reach(web, (in_web, in_web), NOW)
    assert not table_within_reach(web, (in_web, in_finance), NOW)
    assert not table_within_reach(web, (in_web, nowhere), NOW)
    assert not table_within_reach(web, (), NOW)
    assert not table_within_reach(split, (in_web,), NOW)
    for rows in ((in_web, in_finance, nowhere), ()):
        assert table_within_reach(install, rows, NOW)


def test_a_department_administrator_changes_a_table_whose_rows_are_their_department_s(
    departments: TestClient, memory: MemoryTables
) -> None:
    """**The positive half of the scope, found on the owner's install on 2026-09-29.** Web's
    administrator uploads a price list placed in web, reviews a mark and applies it. Delete this and
    the refusal below is satisfied by a route that lets no department administrator change
    anything."""
    uploaded = upload_as(departments, WEB_ADMIN, "web_prices", placed("web"))
    reviewed = mark_as(departments, WEB_ADMIN, "web_prices", apply=False)
    applied = mark_as(departments, WEB_ADMIN, "web_prices", apply=True)
    ruled = review_as(departments, WEB_ADMIN, "web_prices")
    shown = call(departments, "GET", "/web_prices", WEB_ADMIN)

    assert uploaded.status_code == 200 and uploaded.json()["refused"] == "", uploaded.text
    assert reviewed.status_code == 200, reviewed.text
    assert applied.status_code == 200 and applied.json()["applied"] is True, applied.text
    assert ruled.status_code == 200, ruled.text
    assert shown.json()["editable"] is True
    assert [one.actor_id for one in memory.writers] == [WEB_ADMIN, WEB_ADMIN]


def test_another_department_s_table_is_refused_to_them_exactly_as_a_missing_one(
    departments: TestClient, memory: MemoryTables
) -> None:
    """**The defect: the editor ignored the grant's scope.** Finance's table, uploaded by the
    install's administrator, is refused to web's administrator on every route that changes or
    reviews a table, in the very body a table that does not exist gets, and nothing is written.
    Delete this and a department administrator can retune what another department may see of its
    own price list."""
    upload_as(departments, INSTALL_ADMIN, "finance_prices", placed("finance"))
    stored = memory.tables["finance_prices"]

    theirs = [
        mark_as(departments, WEB_ADMIN, "finance_prices", apply=False),
        mark_as(departments, WEB_ADMIN, "finance_prices", apply=True),
        review_as(departments, WEB_ADMIN, "finance_prices"),
        upload_as(departments, WEB_ADMIN, "finance_prices", placed("web")),
    ]
    missing = [
        mark_as(departments, WEB_ADMIN, "no_such_prices", apply=False),
        mark_as(departments, WEB_ADMIN, "no_such_prices", apply=True),
        review_as(departments, WEB_ADMIN, "no_such_prices"),
    ]

    assert {one.status_code for one in theirs + missing} == {404}
    assert {str(refusal(one)) for one in theirs} == {str(refusal(missing[0]))}
    assert {str(refusal(one)) for one in missing} == {str(refusal(missing[0]))}
    assert memory.tables["finance_prices"] is stored
    assert [one.actor_id for one in memory.writers] == [INSTALL_ADMIN]
    # Nor may they read it: see the read's own test below.
    assert refusal(read_as(departments, WEB_ADMIN, "finance_prices")) == refusal(missing[0])


def test_a_department_administrator_may_not_upload_rows_outside_their_department(
    departments: TestClient, memory: MemoryTables
) -> None:
    """An upload is a table's classification over the rows it brings, so rows placed in another
    department, or in none, are refused as a table out of reach is. Delete this and a department
    administrator uploads a company-wide price list under a new name and classifies it alone."""
    elsewhere = upload_as(departments, WEB_ADMIN, "their_prices", placed("finance"))
    nowhere = upload_as(departments, WEB_ADMIN, "all_prices", CSV)
    missing = mark_as(departments, WEB_ADMIN, "no_such_prices", apply=True)

    assert elsewhere.status_code == 404 and nowhere.status_code == 404
    assert refusal(elsewhere) == refusal(missing) == refusal(nowhere)
    assert memory.tables == {}


def test_an_install_wide_administrator_changes_any_department_s_table(
    departments: TestClient, memory: MemoryTables
) -> None:
    """The unrestricted grant admits every row, placed or not. Delete this and the scope check can
    refuse the one administrator who is meant to reach every table."""
    upload_as(departments, WEB_ADMIN, "web_prices", placed("web"))
    upload_as(departments, FINANCE_ADMIN, "finance_prices", placed("finance"))
    company = upload_as(departments, INSTALL_ADMIN, "all_prices", CSV)

    for entity in ("web_prices", "finance_prices", "all_prices"):
        applied = mark_as(departments, INSTALL_ADMIN, entity, apply=True)
        assert applied.status_code == 200 and applied.json()["applied"] is True, entity

    assert company.json()["refused"] == ""
    assert [one.actor_id for one in memory.writers] == [
        WEB_ADMIN,
        FINANCE_ADMIN,
        INSTALL_ADMIN,
        INSTALL_ADMIN,
        INSTALL_ADMIN,
        INSTALL_ADMIN,
    ]


def read_as(c: TestClient, pid: str, entity: str) -> Response:
    """The Classification screen's read of one table's column rules."""
    return call(c, "GET", f"/{entity}", pid)


def test_another_department_s_table_is_unreadable_to_them_exactly_as_a_missing_one(
    departments: TestClient,
) -> None:
    """**Reading is scoped as changing is.** Finance's price list is refused to web's reader and to
    web's administrator in the very body a table that does not exist gets, so neither learns which
    columns finance keeps confidential, nor that finance holds a table by that name. Delete this and
    a department reader can map every other department's price lists one name at a time."""
    upload_as(departments, INSTALL_ADMIN, "finance_prices", placed("finance"))
    upload_as(departments, INSTALL_ADMIN, "mixed_prices", placed("web") + b"Extra,finance,1,1\n")
    upload_as(departments, INSTALL_ADMIN, "all_prices", CSV)

    refused = [
        read_as(departments, pid, entity)
        for pid in (WEB_READER, WEB_ADMIN)
        for entity in ("finance_prices", "mixed_prices", "all_prices")
    ]
    missing = read_as(departments, WEB_READER, "no_such_prices")

    assert missing.status_code == 404
    assert missing.json()["message"] == Absent.public_message
    assert {one.status_code for one in refused} == {404}
    assert {str(refusal(one)) for one in refused} == {str(refusal(missing))}


def test_a_table_within_reach_is_read_whole_and_editable_only_with_the_write_grant(
    departments: TestClient,
) -> None:
    """The sibling: web's reader reads web's price list whole, and is told it is not editable;
    web's administrator reads it editable; finance's administrator and the install's read finance's;
    and the shipped price list, whose rules are a release rather than anybody's rows, is read by
    anybody holding the read grant at all. Delete this and the refusal above is satisfied by a read
    that answers nobody."""
    upload_as(departments, WEB_ADMIN, "web_prices", placed("web"))
    upload_as(departments, FINANCE_ADMIN, "finance_prices", placed("finance"))

    reader = read_as(departments, WEB_READER, "web_prices")
    admin = read_as(departments, WEB_ADMIN, "web_prices")
    theirs = read_as(departments, FINANCE_ADMIN, "finance_prices")
    install = read_as(departments, INSTALL_ADMIN, "finance_prices")
    shipped = read_as(departments, WEB_READER, PRICE_LIST.entity)

    for answered in (reader, admin, theirs, install, shipped):
        assert answered.status_code == 200, answered.text
    assert reader.json()["editable"] is False
    assert {one["column"] for one in reader.json()["columns"]} == {
        "name",
        "department",
        "sell_price",
        "cost",
    }
    assert admin.json()["editable"] is True
    assert theirs.json()["editable"] is True and install.json()["editable"] is True
    assert shipped.json()["stored"] is False


def test_the_read_grant_alone_reaches_a_table_whose_every_row_it_admits() -> None:
    """`table_within_reach` asked for reading: the read grant at every row, and the write grant not
    at all, since reading changes nothing. Delete this and reading a table either needs the write
    grant, which no reader holds, or needs no scope, which is the defect."""
    reader = EntitlementSet(
        principal_id="p_reader",
        grants=(Grant(capability=CLASSIFICATION_READ, scope=Scope.department("web")),),
    )
    in_web, in_finance = {"department": "web"}, {"department": "finance"}

    assert table_within_reach(reader, (in_web,), NOW, TO_READ)
    assert not table_within_reach(reader, (in_web, in_finance), NOW, TO_READ)
    assert not table_within_reach(reader, (), NOW, TO_READ)
    assert not table_within_reach(reader, (in_web,), NOW)
    assert TO_READ == (CLASSIFICATION_READ,)
    assert (CLASSIFICATION_READ, CLASSIFICATION_WRITE) == TO_CHANGE


#: What each asker holds on the answer route: a salesperson, and Finance.
ASKERS: Mapping[str, tuple[str, ...]] = {
    "u_narrow": ("read:prices",),
    "u_wide": ("read:prices", "read:prices.cost", "read:prices.margin"),
}


class AskerGrants:
    """An `EntitlementStore` over `ASKERS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return ents(*ASKERS.get(principal_id, ()), principal=principal_id)


def test_ask_over_http_answers_the_sell_price_and_leaves_the_cost_absent(
    memory: MemoryTables,
) -> None:
    """**The install sentence end to end, through `POST /api/v1/answer`.** An uploaded table,
    the real route and token path, and two people. Delete this and nothing proves the route
    reads the uploaded tables at all, which is the half the lane tests above cannot reach."""
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority
    from brain.tools.startup import build_registry
    from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, verifier

    asyncio.run(memory.upload(table(), ROWS, writer=Writer("u_admin", "a" * 32, "t")))
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer="https://id.verz.example/realms/brain",
                audience="brain-api",
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=AskerGrants(),
            cache=NoCache(),
        )
        app.state.tools = build_registry(source="local")
        app.state.classified_tables = memory

        def said(pid: str, question: str) -> str:
            answered = c.post(
                "/api/v1/answer",
                headers={"authorization": f"Bearer {token_for(pid)}"},
                json={"question": question},
            )
            return " ".join(
                one.data for one in decode(answered.text) if one.event == Event.TEXT.value
            )

        assert "1200" in said("u_narrow", "What is the sell price of Website Care?")
        assert "400" in said("u_wide", "What is the cost of Website Care?")
        withheld = said("u_narrow", "What is the cost of Website Care?")
        assert "400" not in withheld
        assert withheld == said("u_narrow", "What is the cost of Nothing Real?")


# ------------------------------------------------------------- the stored shape


def test_a_classification_survives_the_document_it_is_stored_as() -> None:
    """Delete this and a stored table reads back as a different policy than was written."""
    stored = table().classification
    assert classification_from(ENTITY, columns_document(stored)) == stored


@pytest.mark.parametrize(
    "document",
    [
        {"column": "cost"},
        [{"column": "cost"}],
        [
            {
                "column": "cost",
                "required_capability": "write:prices.cost",
                "classification": "confidential",
                "derived_from": [],
            }
        ],
        [
            {
                "column": "cost",
                "required_capability": "read:prices.cost",
                "classification": "confidential",
                "derived_from": ["margin"],
            }
        ],
    ],
)
def test_a_stored_classification_that_does_not_load_is_refused_whole(document: object) -> None:
    """A row edited by hand into a write capability, or a derivation naming a missing column,
    refuses the load. Delete this and such a table reaches Ask with a hole in its policy."""
    with pytest.raises(ColumnClassificationError):
        classification_from(ENTITY, document)


def test_the_models_and_the_migration_agree_on_every_width() -> None:
    """Delete this and a name the models accept is one the column truncates."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "migrations/versions/0116_classified_tables.py"
    spec = importlib.util.spec_from_file_location("migration_0116_width", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def width(table: Any, column: str) -> int | None:
        kind = table.c[column].type
        assert isinstance(kind, String)
        return kind.length

    stored = ClassifiedTableRow.__table__
    assert width(stored, "entity") == migration.ENTITY_CHARS
    assert width(stored, "key_column") == migration.COLUMN_CHARS
    assert width(stored, "title") == migration.TITLE_CHARS
    assert width(stored, "created_by") == migration.PRINCIPAL_ID_CHARS
    assert width(ClassifiedRecordRow.__table__, "entity") == migration.ENTITY_CHARS
    assert migration.down_revision == "0115"


def test_both_tables_enable_row_level_security_and_neither_can_be_deleted_from() -> None:
    """Every new table enables row-level security, the application may not delete from either,
    and every write to the table row is ledgered. Read off every migration rendered in order.
    Delete this and a later migration can grant a DELETE that erases a quoted price."""
    from brain.ops.application_privileges import APPLICATION_ROLE, migrations_catalogue

    catalogue = migrations_catalogue()
    for name in ("know.classified_table", "know.classified_row"):
        assert name in catalogue.tables
        assert catalogue.holds(APPLICATION_ROLE, name, "SELECT")
        assert catalogue.holds(APPLICATION_ROLE, name, "INSERT")
        assert not catalogue.holds(APPLICATION_ROLE, name, "DELETE")
    assert not catalogue.holds(APPLICATION_ROLE, "know.classified_row", "UPDATE")
    for write in ("INSERT", "UPDATE"):
        bodies = catalogue.fired_by("know.classified_table", write)
        assert any("obs.audit_entry" in body for body in bodies), write


# ---------------------------------------------------------------- the database


@pytest.fixture
def database() -> Iterator[str]:
    from tests.fixtures.retirable import retirable

    with retirable(f"brain_classified_{uuid.uuid4().hex[:8]}") as url:
        yield url


def test_the_store_writes_and_reads_a_table_as_the_application_role(database: str) -> None:
    """**On PostgreSQL, as `brain_app`.** An upload writes the table and its rows, a mark
    replaces the classification, the rows come back through the pool with only the open
    columns for a salesperson, and the ledger holds a `setting` entry for each write naming
    the administrator. Delete this and every test above is over a fake."""
    from brain.ops.classification_store import SqlClassifiedTables
    from brain.session import make_session_factory
    from tests.fixtures.retirable import present_tables
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine

    if "know.classified_table" not in present_tables(database):
        pytest.skip("this server has no pgvector, so the chain stops short of 0116")
    writer = Writer(actor_id="u_admin", ent_hash="a" * 32, trace_id="t-classified-db")

    async def go() -> tuple[StoredTable | None, list[str], list[str]]:
        engine = app_engine(database)
        try:
            store = SqlClassifiedTables(make_session_factory(engine))
            first = next_upload(
                None,
                entity=ENTITY,
                title="Price list",
                key_column="name",
                columns=("sku", "name", "sell_price", "cost", "margin"),
            )
            await store.upload(first, ROWS, writer=writer)
            loosened = TableClassification(
                entity=ENTITY,
                rules=tuple(
                    marked(ENTITY, "cost", ColumnAccess.RESTRICTED) if r.column == "cost" else r
                    for r in first.classification.rules
                ),
            )
            await store.classify(ENTITY, loosened, writer=writer)
            stored = await store.table(ENTITY)
            assert stored is not None
            result = await read_table_rows(
                stored, RowRequest(), entitlement=ents("read:prices"), records=store.records()
            )
            seen = sorted({key for one in result.records for key in one.model_dump()})
            live = [one.entity for one in await store.live_tables()]
            return stored, seen, live
        finally:
            await engine.dispose()

    stored, seen, live = run(go)

    assert stored is not None
    cost = stored.classification.rule_for("cost")
    assert cost is not None and access_of(ENTITY, cost) is ColumnAccess.RESTRICTED
    assert live == [ENTITY]
    assert seen == ["entity", "id", "name", "sell_price", "sku"]
    entries = sql(
        database,
        "SELECT actor_id, details ->> 'change' FROM obs.audit_entry"
        " WHERE subject = 'setting:classified_table.prices' ORDER BY seq",
    )
    assert entries == [("u_admin", "uploaded"), ("u_admin", "classified")]
