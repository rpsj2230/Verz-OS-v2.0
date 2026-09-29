"""A question over many records on Ask: which records hold a header value, and how many.

Driven through the answer lane itself over a `RowSource` of fixed rows, as
`tests/unit/test_answer_lane.py` drives it, so the matcher, the row plane's projection, the
redactor, the abstention and the composition are the product's. The shapes are held to the
connectors' own projections, and a question over many records is shown never to call a source.

Task ids: M11.8.3
"""

from __future__ import annotations

import asyncio
from typing import Any

from brain.connectors import freshdesk, xero
from brain.connectors.manifest import FieldShape, HotUse
from brain.core.entitlement import Capability
from brain.core.field_policy import Classification
from brain.gate.fast_lane import FAST_LANE_ROW_LIMIT, MANY_ROW_LIMIT, FastPathRule
from brain.knowledge.classified_rows import MANY_SHAPES, listings_over
from brain.knowledge.columns import ColumnRule, TableClassification
from brain.knowledge.connector_rows import HEADERS, NAMED_BY, connected_questions
from brain.knowledge.rows import RowTool
from tests.unit.test_answer_lane import Rows, ents, run, texts

INVOICES = TableClassification(
    entity="invoice",
    rules=tuple(
        ColumnRule(
            column=name,
            required_capability=Capability(value=f"read:invoice.{name}"),
            classification=Classification.INTERNAL,
        )
        for name in ("invoice_number", "status")
    ),
)
TOOL = RowTool(source="xero", classification=INVOICES, description="Read an invoice.")
RULES = listings_over(
    INVOICES,
    source="xero",
    key_column="invoice_number",
    headers=(("status", "which"), ("status", "how_many")),
)
READS = ("read:invoice", "read:invoice.invoice_number", "read:invoice.status")


def row(number: str, status: str) -> dict[str, Any]:
    return {"entity": "invoice", "id": f"i_{number}", "invoice_number": number, "status": status}


class Live:
    """A live reader that records being asked, which a question over many records never does."""

    def __init__(self) -> None:
        self.asked = 0

    async def refresh(self, result: Any, **kwargs: Any) -> Any:
        del result, kwargs
        self.asked += 1
        return None


def ask(question: str, rows: Rows, *caps: str) -> Any:
    return run(
        question,
        rows=rows,
        rules=RULES,
        entitlement=ents(*caps),
        policies={"invoice": INVOICES.policy()},
        sources=("xero",),
        readers={("xero", "invoice"): TOOL.reader(rows)},
    )


def test_every_header_is_asked_which_and_how_many_and_answered_by_the_record_s_name() -> None:
    """Delete this and a header can be asked about in words the matcher never reads, or answered
    with a field other than the one a person names a record by."""
    assert {rule.many for rule in RULES} == set(MANY_SHAPES)
    for rule in RULES:
        assert (rule.match_field, rule.answer_field, rule.slot) == (
            "status",
            "invoice_number",
            "status",
        )
    assert {rule.template for rule in RULES} == {
        "which invoices have status {status}",
        "how many invoices have status {status}",
    }
    assert len({rule.rule_id for rule in RULES}) == len(RULES)


def test_a_header_is_asked_only_what_its_connector_declares_it_kept_for() -> None:
    """Held against each connector's projection rather than against this module's table: a status
    kept to filter by is asked which, one kept to count by is asked how many. Delete this and a
    header the connector no longer keeps can still be asked about, or a status kept only to filter
    by (a Xero contact's) is counted."""
    uses = {"which": HotUse.FILTER, "how_many": HotUse.COUNT}
    for (source, entity), headers in HEADERS.items():
        fields = (
            xero.PROJECTED_FIELDS[entity]
            if source == xero.CONNECTOR_NAME
            else freshdesk.TICKET_FIELDS
        )
        declared = {one.name: one for one in fields}
        assert headers
        for name, many in headers:
            assert declared[name].shape is FieldShape.STATUS
            assert uses[many] in declared[name].uses
        assert {name for name, _ in headers} == {
            one.name for one in fields if one.shape is FieldShape.STATUS
        }
    listings = [rule for rule in connected_questions([xero.CONNECTOR_NAME]) if rule.many]
    assert {(rule.entity, rule.match_field, rule.many) for rule in listings} == {
        ("invoice", "status", "which"),
        ("invoice", "status", "how_many"),
        ("contact", "status", "which"),
    }
    assert all(rule.answer_field == NAMED_BY[(rule.source, rule.entity)] for rule in listings)


def test_which_records_hold_a_header_value_is_answered_with_their_names() -> None:
    """**The positive case.** Delete this and the lane can refuse every question over many
    records, as it did before, with every refusal below still green."""
    rows = Rows(row("INV-2", "AUTHORISED"), row("INV-1", "AUTHORISED"))
    answered = ask("which invoices have status AUTHORISED", rows, *READS)
    assert answered.abstention is None
    assert texts(answered)[-1].startswith("INV-1; INV-2")
    [query] = rows.queries
    assert "status" in query.columns


def test_how_many_records_hold_a_header_value_is_answered_with_a_count() -> None:
    """Delete this and a count question can be answered with the list, or with the rows fetched
    rather than the ones the reader may name."""
    rows = Rows(row("INV-1", "AUTHORISED"), row("INV-2", "AUTHORISED"), row("INV-3", "AUTHORISED"))
    answered = ask("how many invoices have status AUTHORISED", rows, *READS)
    assert answered.abstention is None
    assert texts(answered)[-1].startswith("3")


def test_a_reader_who_may_not_name_the_records_is_told_what_an_absent_value_is_told() -> None:
    """DENIED and ABSENT: a reader holding the status and not the name gets exactly the frames a
    status nobody holds gets, and is told no count. Delete this and a count of records a reader
    may not name reaches them, which is the leak CLAUDE.md names first."""
    held = ask(
        "how many invoices have status AUTHORISED",
        Rows(row("INV-1", "AUTHORISED")),
        "read:invoice",
        "read:invoice.status",
    )
    none = ask(
        "how many invoices have status AUTHORISED", Rows(), "read:invoice", "read:invoice.status"
    )
    assert held.abstention is not None
    assert texts(held) == texts(none)


def test_a_reader_who_may_not_read_the_header_is_told_what_an_absent_value_is_told() -> None:
    """The filter is the oracle: a reader holding the names and not the status would learn which
    records hold a status from which names came back. Delete this and a list answered through a
    filter the reader may not apply tells them a value, one guess at a time."""
    rows = Rows(row("INV-1", "AUTHORISED"))
    held = ask(
        "which invoices have status AUTHORISED",
        rows,
        "read:invoice",
        "read:invoice.invoice_number",
    )
    none = ask(
        "which invoices have status AUTHORISED",
        Rows(),
        "read:invoice",
        "read:invoice.invoice_number",
    )
    assert held.abstention is not None
    assert texts(held) == texts(none)


def test_a_read_stopped_at_its_limit_says_it_is_the_first_so_many() -> None:
    """Delete this and a list cut at the limit reads as every record there is."""
    rows = Rows(*(row(f"INV-{n:02d}", "AUTHORISED") for n in range(MANY_ROW_LIMIT)))
    listed = ask("which invoices have status AUTHORISED", rows, *READS)
    counted = ask("how many invoices have status AUTHORISED", rows, *READS)
    assert texts(listed)[-1].startswith(f"the first {MANY_ROW_LIMIT}: ")
    assert texts(counted)[-1].startswith(f"at least {MANY_ROW_LIMIT}")
    assert MANY_ROW_LIMIT > FAST_LANE_ROW_LIMIT


def test_a_question_over_many_records_calls_no_source() -> None:
    """`A_QUESTION_OVER_MANY_RECORDS_IS_ANSWERED_FROM_THE_INDEX_HEADERS`. Delete this and one
    question could spend a live read per record listed."""
    from brain.core.entitlement import EntitlementSet
    from brain.core.principal import Employment, Principal, PrincipalKind
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from tests.unit.test_answer_lane import NOW, Sink

    rows, live = Rows(row("INV-1", "AUTHORISED"), row("INV-2", "AUTHORISED")), Live()
    reach: EntitlementSet = ents(*READS)
    answered = asyncio.run(
        answer_lane(
            "which invoices have status AUTHORISED",
            origin=Origin(
                trace_id="t-headers",
                principal=Principal(
                    id=reach.principal_id,
                    kind=PrincipalKind.HUMAN,
                    employment=Employment.STAFF,
                    display_name="Asker",
                ),
                channel=Channel.CONSOLE,
            ),
            recorders=(),
            rules=RULES,
            readers={("xero", "invoice"): TOOL.reader(rows)},
            entitlement=reach,
            policies={"invoice": INVOICES.policy()},
            reachable_sources=("xero",),
            sink=Sink(),
            now=NOW,
            clock=lambda: NOW,
            live=live,
        )
    )
    assert answered.abstention is None
    assert live.asked == 0


def test_a_single_record_rule_still_abstains_on_two_records_under_one_name() -> None:
    """The ordinary rule is unchanged: two records under one name is a fall-through. Delete this
    and letting many records through for a listing could let them through for every question."""
    single = FastPathRule(
        rule_id="invoice_status_of",
        template="status of invoice {invoice_number}",
        slot="invoice_number",
        source="xero",
        entity="invoice",
        match_field="invoice_number",
        answer_field="status",
    )
    rows = Rows(row("INV-1", "AUTHORISED"), row("INV-1", "DRAFT"))
    answered = run(
        "status of invoice INV-1",
        rows=rows,
        rules=(single,),
        entitlement=ents(*READS),
        policies={"invoice": INVOICES.policy()},
        sources=("xero",),
        readers={("xero", "invoice"): TOOL.reader(rows)},
    )
    assert answered.abstention is not None
