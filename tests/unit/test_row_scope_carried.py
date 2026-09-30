"""A department-scoped reader is shown their own rows through the redactor, and nothing more.

Found on 2026-09-29 while writing an install check for the automation route: a reader whose
price-list grants were scoped to their department got an empty answer from every door that
redacts. The statement had already returned only their department's rows; the record it built
did not carry `department`, so `brain.core.redaction.compute_mask` judged each field's scope
against a record with no department and withheld every field as out of scope. Readers holding
company-wide grants were never affected, which is why no test saw it: every one of them either
held unrestricted grants or read the tool's records without redacting.

The fix is `brain.knowledge.rows.scope_carried`, and these tests hold both halves of it: the
fields a reader's scope tests reach the redactor, and the redactor still withholds them.

Task ids: M15.1.1, M15.1.2, M15.1.4
"""

from __future__ import annotations

import asyncio

from brain.core.department import department_scope
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.redaction import ChannelPayload, serialise_for_channel
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.classified_rows import StoredTable, compile_table_query, read_table_rows
from brain.knowledge.columns import PRICE_LIST, first_classification
from brain.knowledge.rows import (
    RowRecord,
    RowRequest,
    compile_row_query,
    entity_capability,
    row_scope_for,
    scope_carried,
)
from tests.unit.test_row_plane import PRICE_TOOL, Rows, ents, read_rows, rendered

#: The department every reader below is scoped to, and the one their rows belong to.
SALES = department_scope("sales")

#: A seller: the price list's rows, its name and its sell price, all in their department.
SEES_PRICES = ("read:price_list", "read:price_list.name", "read:price_list.sell_price")
SELLER = ents(*SEES_PRICES, scope=SALES)

#: One row of the seller's own department, as the statement would hand it back.
OWN_ROW = {
    "entity": "price_list",
    "id": "PKG-CARE-1",
    "name": "Website Care",
    "sell_price": "1200.00",
    "department": "sales",
}


def shown(result: TypedResult[RowRecord], reader: EntitlementSet) -> ChannelPayload:
    """What a channel is handed: the price list's own policy, through the one redacting door."""
    return serialise_for_channel(result, entitlement=reader, policy=PRICE_LIST.policy())


def test_a_department_scoped_reader_is_shown_their_own_rows_through_the_redactor() -> None:
    """The defect itself, reproduced without a database. Delete this and records can go back to
    being built from the projection alone, which answers every department-scoped reader with
    nothing through every door that redacts while every company-wide test stays green."""
    found = read_rows(PRICE_TOOL, RowRequest(), entitlement=SELLER, records=Rows(OWN_ROW))
    assert [one["name"] for one in shown(found, SELLER).records] == ["Website Care"]


def test_the_field_a_scope_tests_is_withheld_and_offered_as_no_lock() -> None:
    """The other half: `department` reaches the redactor to be judged, and never the reader.
    Nothing classifies it on the price list, so it is withheld with no lock, and a lock would
    advertise a column nobody owns. Delete this and a carried field can be shown, which turns
    the fix into a way of reading any column a scope happens to test."""
    payload = shown(
        read_rows(PRICE_TOOL, RowRequest(), entitlement=SELLER, records=Rows(OWN_ROW)), SELLER
    )
    assert [set(one) for one in payload.records] == [{"entity", "id", "name", "sell_price"}]
    assert all(lock.field != "department" for lock in payload.locked)


def test_a_row_outside_the_readers_department_is_still_withheld_by_the_redactor() -> None:
    """The redactor judges the carried value rather than trusting the statement's filter. A
    source handing back another department's row is shown nothing. Delete this and the carried
    field could be set to anything that satisfies the scope, and the last line of defence would
    be a formality."""
    elsewhere = {**OWN_ROW, "department": "finance"}
    found = read_rows(PRICE_TOOL, RowRequest(), entitlement=SELLER, records=Rows(elsewhere))
    assert shown(found, SELLER).records == ()


def test_the_statement_selects_the_field_the_readers_scope_tests_beside_the_projection() -> None:
    """Carried, selected, and not a column of the projection. Delete this and the department can
    drift into `columns`, where it would become a filter target and a field the reader is told
    they may read."""
    query = compile_row_query(PRICE_TOOL, RowRequest(), entitlement=SELLER)
    assert query.carried == ("department",)
    assert "department" not in query.columns
    assert "AS department" in rendered(query)


def test_a_company_wide_reader_is_carried_nothing_beyond_their_columns() -> None:
    """The positive sibling: a reader whose scope tests no field selects exactly what they did
    before. Delete this and a carry that selected every field for everybody would pass the
    tests above."""
    query = compile_row_query(PRICE_TOOL, RowRequest(), entitlement=ents(*SEES_PRICES))
    assert query.carried == ()
    assert "AS department" not in rendered(query)


def test_a_filter_on_a_carried_field_still_returns_nothing() -> None:
    """A carried field is for the redactor, never for the asker. A filter is answered by which
    rows come back, so a filter on a field the reader cannot read is a value oracle, and it
    compiles to nothing as it did before. Delete this and a carried field becomes readable one
    guess at a time."""
    on_carried = RowRequest(filters=SALES)
    on_visible = RowRequest(filters=Scope(clauses=(Clause(field="name", op=Op.EQ, value="x"),)))
    assert compile_row_query(PRICE_TOOL, on_carried, entitlement=SELLER).certainly_empty
    assert not compile_row_query(PRICE_TOOL, on_visible, entitlement=SELLER).certainly_empty


def test_every_scope_the_redactor_judges_is_over_a_field_the_record_carries() -> None:
    """`scope_carried` reads only the row scope, and its docstring argues that is enough: a
    column is admitted only when its grant's scope is entailed field by field. Held here over
    grants whose scopes differ from the row grant's (a wider list of departments, a company-wide
    column, a prefix), so the day entailment learns to cross fields this fails rather than a
    reader's answer going quiet. Delete it and that argument is a docstring nobody checks."""
    wider = Scope(clauses=(Clause(field="department", op=Op.IN, value=("ops", "sales")),))
    prefixed = Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="sal"),))
    reader = EntitlementSet(
        principal_id="p_wei_ling",
        grants=(
            Grant(capability=Capability(value="read:price_list"), scope=SALES),
            Grant(capability=Capability(value="read:price_list.name"), scope=wider),
            Grant(capability=Capability(value="read:price_list.sell_price"), scope=Scope()),
            Grant(capability=Capability(value="read:price_list.sku"), scope=prefixed),
        ),
    )
    query = compile_row_query(PRICE_TOOL, RowRequest(), entitlement=reader)
    assert set(query.columns) == {"name", "sell_price", "sku"}
    carries = {*query.columns, *query.carried}
    for rule in PRICE_LIST.rules:
        if rule.column not in query.columns:
            continue
        held = reader.scope_for(rule.required_capability)
        assert held is not None
        assert {clause.field for clause in held.clauses if clause.op is not Op.ANY} <= carries


def test_nothing_is_carried_for_a_caller_with_no_row_grant() -> None:
    """No row grant compiles to `FALSE` and builds no record, so there is nothing to judge.
    Delete this and a caller holding only column grants could be handed a statement selecting
    the fields a scope they do not hold would test."""
    assert scope_carried(row_scope_for("price_list", ents("read:price_list.name")), ()) == ()
    assert scope_carried(SALES, ("department",)) == ()
    assert scope_carried(SALES, ()) == ("department",)


def test_a_clause_that_tests_no_value_and_the_record_s_tag_are_never_carried() -> None:
    """An `ANY` clause admits whatever a record holds, so it needs nothing from the record, and
    the tag is on every record already. Delete this and a scope can make the statement select a
    field for no reason, or select `entity` a second time under a label that overwrites the
    tag, and the record is dropped as untagged."""
    anything = Scope(clauses=(Clause(field="region", op=Op.ANY),))
    tagged = Scope(clauses=(Clause(field="entity", op=Op.EQ, value="price_list"),))
    assert scope_carried(anything, ()) == ()
    assert scope_carried(tagged, ()) == ()


def test_a_carried_field_is_read_where_the_where_clause_reads_it() -> None:
    """`source` is a real column of the records table and every other field lives in the jsonb,
    and the value the redactor judges has to be the value the statement filtered on. Delete
    this and a promoted field could be read from the jsonb, where it is absent, and every row
    of a source-scoped reader would be withheld."""
    by_source = Scope(clauses=(Clause(field="source", op=Op.EQ, value="xero"),))
    query = compile_row_query(
        PRICE_TOOL, RowRequest(), entitlement=ents(*SEES_PRICES, scope=by_source)
    )
    assert query.carried == ("source",)
    assert "record.source AS source" in rendered(query)
    assert "->> 'source'" not in rendered(query)


def test_an_uploaded_table_read_by_a_department_scoped_reader_is_shown_its_rows() -> None:
    """The same defect on the other row plane. An uploaded table that nobody marked a
    department column on, read by a department-scoped reader, answered nothing for the same
    reason. Delete this and the fix can be made to the price list's tool alone, which is the
    one-table fix the task refused."""
    classification = first_classification("prices", ("sku", "name", "sell_price"))
    table = StoredTable(classification=classification, title="Prices", key_column="name", version=1)
    caps = [c.required_capability.value for c in classification.rules if c.column == "name"]
    reader = ents(entity_capability("prices").value, *caps, scope=SALES)
    row = {"entity": "prices", "id": "1", "name": "Hosting", "department": "sales"}

    query = compile_table_query(table, RowRequest(), entitlement=reader)
    assert query.carried == ("department",)
    assert "AS department" in rendered(query)
    found = asyncio.run(read_table_rows(table, RowRequest(), entitlement=reader, records=Rows(row)))
    payload = serialise_for_channel(found, entitlement=reader, policy=classification.policy())
    assert [dict(one) for one in payload.records] == [
        {"entity": "prices", "id": "1", "name": "Hosting"}
    ]
