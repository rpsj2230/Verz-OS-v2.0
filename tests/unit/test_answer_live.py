"""The answer lane reading a source's record live, and redacting each source by its own rules.

The fast path finds a record through the minimal index, which never holds the value a question asks
for; here the lane reads that record again from its source inside the live read budget and answers
from what came back, at the asker's reach (M11.9.2). The rows are the real row plane's, the redactor
is the real one and the stand-ins are only where a database and a vendor would be.

The second half is M15.4.2: two sources projecting the same kind of record, each classified by its
own rules, and the second never stopping the first from answering.

Task ids: M11.9.2, M11.5.1, M11.5.5, M15.4.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from brain.api_routes import field_policies, row_readers, source_field_policies
from brain.connectors.contract import FetchRequest
from brain.connectors.live_read import LiveReply, LiveSource, LiveThrottle
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import SourceRecord
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import IdentityMode, TypedResult
from brain.core.errors import Degraded
from brain.core.field_policy import Classification, FieldPolicy
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.redaction import ChannelPayload, RedactionTrace
from brain.core.scope import Scope
from brain.gate import answer as answer_module
from brain.gate.abstain import NOT_FOUND_TEXT
from brain.gate.answer import Answered, answer_lane
from brain.gate.context import Channel
from brain.gate.fast_lane import FastLaneAnswer, FastPathRule, RowReader
from brain.gate.finish import Finished, Origin
from brain.gate.streaming import Event, frames
from brain.knowledge.columns import ColumnRule, TableClassification
from brain.knowledge.rows import RowQuery, RowTool
from brain.ops.live_records import SourceRecords
from brain.ops.telemetry import RequestStatus, status_of_finished
from brain.tools import startup
from brain.tools.startup import build_registry
from tests.unit.test_streaming import decode

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

INVOICES: Final = TableClassification(
    entity="invoice",
    rules=(
        ColumnRule(
            column="invoice_number",
            required_capability=Capability(value="read:invoice.invoice_number"),
            classification=Classification.INTERNAL,
        ),
        ColumnRule(
            column="status",
            required_capability=Capability(value="read:invoice.status"),
            classification=Classification.INTERNAL,
        ),
        ColumnRule(
            column="amount_due",
            required_capability=Capability(value="read:invoice.amount_due"),
            classification=Classification.CONFIDENTIAL,
        ),
    ),
)

INVOICE_TOOL: Final = RowTool(source="xero", classification=INVOICES, description="Read invoices.")

AMOUNT_DUE: Final = FastPathRule(
    rule_id="invoice_amount_due",
    template="amount due on {invoice}",
    slot="invoice",
    source="xero",
    entity="invoice",
    match_field="invoice_number",
    answer_field="amount_due",
)

#: What the minimal index holds of the invoice: how to find it, and not what it is worth.
INDEXED: Final = {
    "entity": "invoice",
    "id": "b1f2-0447",
    "invoice_number": "INV-2291",
    "status": "DRAFT",
}

SEES_AMOUNTS: Final = (
    "read:invoice",
    "read:invoice.invoice_number",
    "read:invoice.status",
    "read:invoice.amount_due",
)


def reach(*caps: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="p_priya",
        grants=tuple(Grant(capability=Capability(value=one), scope=Scope()) for one in caps),
    )


class Rows:
    """A `RowSource` answering with the index rows, so no database is needed."""

    def __init__(self, *returns: Mapping[str, Any]) -> None:
        self.returns = list(returns)
        self.queries: list[RowQuery] = []

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.queries.append(query)
        return self.returns


class Sink:
    def emit(self, reference: str, payload: ChannelPayload, trace: RedactionTrace) -> None:
        del reference, payload, trace


class Recorder:
    def __init__(self) -> None:
        self.seen: list[Finished] = []

    async def finished(self, request: Finished) -> None:
        self.seen.append(request)


class Ledger:
    """A `LiveSource` for Xero answering with the invoice's live values, or failing on command."""

    def __init__(self, *, fails: bool = False, amount: str = "4,180.00") -> None:
        self.fails = fails
        self.amount = amount
        self.calls: list[FetchRequest] = []

    async def __call__(self, request: FetchRequest) -> LiveReply:
        self.calls.append(request)
        if self.fails:
            return LiveReply(CallOutcome.UNAVAILABLE)
        (record_id,) = [value for key, value in request.filters if key == "id"]
        return LiveReply(
            CallOutcome.OK,
            rows=TypedResult[SourceRecord](
                records=(
                    SourceRecord.model_validate(
                        {
                            "entity": "invoice",
                            "id": record_id,
                            "amount_due": self.amount,
                            "status": "AUTHORISED",
                        }
                    ),
                ),
                source="xero",
                fetched_at="2999-01-01T09:00:00+00:00",
            ),
        )


class Connected:
    """`LiveSources` with Xero connected and read live, as a service read."""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        return IdentityMode.SERVICE if (connector, entity) == ("xero", "invoice") else None

    def source_for(self, connector: str, *, mode: IdentityMode, asker: str) -> LiveSource | None:
        del asker
        if connector == "xero" and mode is IdentityMode.SERVICE:
            return self.ledger
        return None


def live_over(ledger: Ledger) -> SourceRecords:
    async def connected() -> Connected:
        return Connected(ledger)

    return SourceRecords(connected=connected, throttle=LiveThrottle(), clock=lambda: NOW)


def ask(
    *,
    live: SourceRecords | None,
    entitlement: EntitlementSet | None = None,
    sources: Sequence[str] = ("xero",),
    readers: Mapping[tuple[str, str], RowReader] | None = None,
    rules: Sequence[FastPathRule] = (AMOUNT_DUE,),
    question: str = "amount due on INV-2291",
    policies: Mapping[str, FieldPolicy] | None = None,
    source_policies: Mapping[tuple[str, str], FieldPolicy] | None = None,
    recorder: Recorder | None = None,
) -> Answered:
    who = entitlement if entitlement is not None else reach(*SEES_AMOUNTS)
    return asyncio.run(
        answer_lane(
            question,
            origin=Origin(
                trace_id="t-answer-live",
                principal=Principal(
                    id=who.principal_id,
                    kind=PrincipalKind.HUMAN,
                    employment=Employment.STAFF,
                    display_name="Live asker",
                ),
                channel=Channel.CONSOLE,
            ),
            recorders=() if recorder is None else (recorder,),
            rules=rules,
            readers=readers
            if readers is not None
            else {("xero", "invoice"): INVOICE_TOOL.reader(Rows(INDEXED))},
            entitlement=who,
            policies=policies if policies is not None else {"invoice": INVOICES.policy()},
            reachable_sources=sources,
            sink=Sink(),
            now=NOW,
            clock=lambda: NOW,
            live=live,
            source_policies=source_policies,
        )
    )


def texts(answered: Answered) -> list[str]:
    decoded = decode(frames(answered.frames))
    return [one.data for one in decoded if one.event == Event.TEXT.value]


# ------------------------------------------------------------------ read live (M11.9.2)


def test_a_value_the_index_does_not_hold_is_read_from_the_source_and_answered() -> None:
    """The positive case the owner's rule rests on. The index row finds the invoice and holds no
    amount; the lane reads the invoice from Xero, answers with the amount Xero returned, records
    the request under the answer lane and keeps nothing for the cache.

    Delete this and the lane can answer every connector question from the index, which is the bulk
    sync the owner forbade, or abstain on all of them, with every refusal below still green."""
    ledger = Ledger()
    recorder = Recorder()

    answered = ask(live=live_over(ledger), recorder=recorder)

    assert answered.abstention is None
    assert texts(answered)[0].startswith("4,180.00")
    assert ledger.calls == [FetchRequest(entity="invoice", filters=(("id", "b1f2-0447"),), limit=1)]
    assert answered.text is None
    (finished,) = recorder.seen
    assert finished.lane is Lane.ANSWER
    assert finished.tool_calls == 2
    assert status_of_finished(finished) is RequestStatus.ANSWERED


def test_without_a_live_read_the_index_has_nothing_to_answer_a_value_question_with() -> None:
    """The same question on a lane with no live reads: the index row has no amount, so the asker is
    told what an absent record is told, and the request stays in the fast lane.

    Delete this and nothing shows that the answer above came from the source and not the index."""
    recorder = Recorder()

    answered = ask(live=None, recorder=recorder)

    assert texts(answered)[0].startswith(NOT_FOUND_TEXT)
    assert recorder.seen[0].lane is Lane.FAST


def test_the_source_s_values_win_and_the_index_keeps_only_what_the_source_never_sends() -> None:
    """The live status replaces the indexed one, and the record keeps the index's fields the
    reply does not carry, such as the visibility fields a sync lays over a row.

    Delete this and an answer can quote a status the source changed since the last sync."""
    status = FastPathRule(
        rule_id="invoice_status",
        template="what is the status of {invoice}",
        slot="invoice",
        source="xero",
        entity="invoice",
        match_field="invoice_number",
        answer_field="status",
    )

    answered = ask(
        live=live_over(Ledger()), rules=(status,), question="what is the status of INV-2291"
    )

    assert texts(answered)[0].startswith("AUTHORISED")
    assert answered.composed is not None
    (record,) = answered.composed.payload.records
    assert record["invoice_number"] == "INV-2291"


def test_a_field_the_asker_may_not_read_is_withheld_after_the_live_read_like_any_other() -> None:
    """The live record is redacted at the asker's reach: an asker who may find the invoice and not
    read its amount is told what an absent record is told.

    Delete this and a live read becomes a way round the column classification."""
    answered = ask(
        live=live_over(Ledger()),
        entitlement=reach("read:invoice", "read:invoice.invoice_number", "read:invoice.status"),
    )

    assert texts(answered)[0].startswith(NOT_FOUND_TEXT)
    assert "4,180.00" not in "".join(answered.frames)


# ------------------------------------------------------------------ not in time (M11.5.5)


def test_a_source_that_does_not_answer_is_named_to_one_who_sees_it_and_nothing_is_made_up() -> None:
    """The source holding the answer failed: the asker whose reach covers it is told which, the
    index's copy is not served in its place, and the request is recorded as degraded.

    Delete this and a failed live read can fall back to the index, or say nothing about why the
    answer is missing."""
    recorder = Recorder()

    answered = ask(live=live_over(Ledger(fails=True)), recorder=recorder)

    (said,) = texts(answered)
    assert "xero" in said
    assert "DRAFT" not in "".join(answered.frames)
    assert answered.partial is not None
    assert answered.partial.trace_lines() == ("xero: transport (unavailable)",)
    assert (answered.composed, answered.abstention, answered.text) == (None, None, None)
    assert status_of_finished(recorder.seen[0]) is RequestStatus.DEGRADED


def test_a_source_the_askers_reach_does_not_disclose_is_never_named_when_it_fails() -> None:
    """The same failure told to an asker whose statement of reach does not name the source: part of
    the answer is unavailable, in the words an unreachable source has always produced.

    Delete this and a failing source is a way to learn which systems the company connects."""
    answered = ask(live=live_over(Ledger(fails=True)), sources=())

    (said,) = texts(answered)
    assert said == Degraded.public_message
    assert "xero" not in said


# ------------------------------------------------------------ each source by its own rules


GRANTS: Final = TableClassification(
    entity="invoice",
    rules=(
        ColumnRule(
            column="invoice_number",
            required_capability=Capability(value="read:invoice.invoice_number"),
            classification=Classification.INTERNAL,
        ),
        ColumnRule(
            column="grant_body",
            required_capability=Capability(value="read:invoice.grant_body"),
            classification=Classification.INTERNAL,
        ),
    ),
)


def test_a_second_source_projecting_the_same_kind_never_stops_the_first_from_answering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two sources each classify `invoice` with their own columns. Registered together, each has a
    row tool of its own, the lane redacts each source's rows by that source's classification, and
    the first still answers with the field only it classifies (M15.4.2).

    Delete this and the second source's classification redacts the first source's rows, withholding
    the amount it alone classifies, so connecting a second system silently stops the first one
    answering."""
    monkeypatch.setattr(
        startup, "SOURCE_ROW_ENTITIES", {"xero": (INVOICES,), "grants_portal": (GRANTS,)}
    )
    monkeypatch.setattr(
        startup,
        "SOURCE_ROW_DESCRIPTIONS",
        {"xero": {"invoice": "Read Xero invoices."}, "grants_portal": {"invoice": "Read grants."}},
    )
    registry = build_registry(source="grants_portal", records=Rows(INDEXED), sources=("xero",))

    assert {("xero", "invoice"), ("grants_portal", "invoice")} <= set(row_readers(registry))
    by_pair = source_field_policies(registry)
    assert by_pair[("xero", "invoice")] == INVOICES.policy()
    assert by_pair[("grants_portal", "invoice")] == GRANTS.policy()

    answered = ask(
        live=live_over(Ledger()),
        readers=row_readers(registry),
        policies=field_policies(registry),
        source_policies=by_pair,
    )
    assert texts(answered)[0].startswith("4,180.00")

    # The entity-keyed mapping alone redacts Xero's rows by whichever source was found first.
    keyed_by_entity = ask(
        live=live_over(Ledger()),
        readers=row_readers(registry),
        policies={"invoice": GRANTS.policy()},
    )
    assert texts(keyed_by_entity)[0].startswith(NOT_FOUND_TEXT)


def test_the_policy_is_the_sources_own_first_and_the_entitys_only_where_the_source_has_none() -> (
    None
):
    """`policy_for` prefers the pair and falls back to the entity, which is how an uploaded table,
    classified by the product and not by a source, keeps answering.

    Delete this and the fallback can be dropped, and every classified table stops answering."""
    found = FastLaneAnswer(
        rule_id="r", entity="invoice", source="xero", field="amount_due", result=TypedResult()
    )
    own, other = INVOICES.policy(), GRANTS.policy()

    assert answer_module.policy_for(found, {"invoice": other}, {("xero", "invoice"): own}) == own
    assert answer_module.policy_for(found, {"invoice": other}, {("grants", "invoice"): own}) == (
        other
    )
    assert answer_module.policy_for(found, {}, None) is None
