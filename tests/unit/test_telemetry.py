"""One row per request: what it must carry, what it must never carry, and when it is minted.

Every test here is about a ledger kept for five years. Two things can go wrong with one and
they pull in opposite directions: it can hold too little, in which case a request nobody can
reconstruct is a dispute nobody can settle, or it can hold too much, in which case it is the
longest-lived copy of the business under the permissions of whoever reads reports. The tests
are arranged in that order, leaf by leaf.

Task ids: M27.1.1, M27.1.2, M27.1.3, M27.1.4, M27.1.5, M27.1.6
"""

from __future__ import annotations

import inspect
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import MISSING, asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brain.audit.ledger import ENT_HASH as ENT_HASH_GRAMMAR
from brain.audit.ledger import IDENTIFIER, TRACE_ID
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Degraded, Denied, Failed, Outcome, Unresolved
from brain.core.lane import Lane
from brain.gate.context import Channel, TrafficClass, traffic_class_for
from brain.identity.roles import Role
from brain.ops.limits import SOURCE_CEILINGS
from brain.ops.retention import HORIZONS, DataClass, horizon_for
from brain.ops.telemetry import (
    _COUNT_FIELDS,
    _DURATION_FIELDS,
    _FLAG_FIELDS,
    _NAME_FIELDS,
    LEDGER_DATA_CLASS,
    LEDGER_RETENTION_DAYS,
    TELEMETRY_FIELDS,
    UNFILLABLE_TODAY,
    Ingress,
    RequestStatus,
    RequestTelemetry,
    TelemetryError,
    _fixed_window,
    mint_trace_id,
    open_request,
    read_payload_with_role,
    span_for,
    status_for,
    telemetry_gaps,
)
from brain.status import leaf_sentences
from brain.ops.tracing import (
    PAYLOAD_ROLE,
    SAFE_ATTRIBUTES,
    SAFE_VALUE_MAX_CHARS,
    VALUE_TOKEN_RE,
    PayloadRead,
    TraceRecord,
    TracingError,
    retention_for,
)

#: Every leaf of the work breakdown by id, so a constant claiming to match a leaf can be
#: checked against the leaf rather than against itself. See `status.leaf_sentences`.
LEAF_SENTENCES = leaf_sentences(Path(__file__).resolve().parents[2] / "docs" / "wbs.json")

NOW = datetime(2026, 9, 7, 9, 30, tzinfo=UTC)

#: A real hash, produced by the thing that produces them, rather than thirty-two characters
#: chosen to look like one. A record refusing what `EntitlementSet` actually emits would be a
#: record no request could ever be written into.
ENT_HASH = EntitlementSet(principal_id="u_weiling").ent_hash()

#: One string, planted where a person's identifier goes, looked for in everything that leaves
#: the process. The same construction `test_tracing` uses, for the same reason.
CANARY = "CANARY-8f3b1d-DO-NOT-EXPORT"

#: The five error classes, read for their outcomes and their public messages, so the status
#: test is anchored to `brain.core.errors` rather than to a mapping written out twice.
ERROR_CLASSES = (Denied, Absent, Unresolved, Degraded, Failed)

#: The four kinds every declared field must be exactly one of.
KIND_GROUPS = (
    ("names", _NAME_FIELDS),
    ("counts", _COUNT_FIELDS),
    ("durations", _DURATION_FIELDS),
    ("flags", _FLAG_FIELDS),
)


def _ingress(**overrides: object) -> Ingress:
    base: dict[str, object] = {
        "trace_id": mint_trace_id(),
        "traffic_class": TrafficClass.HUMAN_INTERACTIVE,
        "received_at": NOW,
    }
    base.update(overrides)
    return Ingress(**base)  # type: ignore[arg-type]


def _record(**overrides: object) -> RequestTelemetry:
    """A record holding the five fields a route could fill honestly today, and nothing else."""
    base: dict[str, object] = {
        "ingress": _ingress(),
        "principal": "u_weiling",
        "entitlement_hash": ENT_HASH,
        "lane": Lane.FAST,
        "cache_hit": False,
        "status": RequestStatus.ANSWERED,
    }
    base.update(overrides)
    return RequestTelemetry(**base)  # type: ignore[arg-type]


def _full_record(**overrides: object) -> RequestTelemetry:
    """Every one of the eighteen fields filled, as on the day the model lane exists.

    Needed because a record tested only through its refusals is satisfied by a record that
    carries nothing, and because the masking tests need something to keep as well as
    something to mask.
    """
    base: dict[str, object] = {
        "agent_version": "2.4.1",
        "policy_epoch": "b" * 32,
        "model": "moonshot/kimi-k2",
        "provider": "moonshot",
        "time_to_first_token_ms": 412.5,
        "tokens_in": 1204,
        "tokens_out": 88,
        "tool_count": 2,
        "tool_latency_ms": 91.0,
        "connector": "lark_base",
        "redaction_count": 3,
        "fallback_count": 1,
        "retry_count": 0,
    }
    base.update(overrides)
    return _record(**base)


def _refuses(**overrides: object) -> bool:
    """Whether a record with these fields can be built at all."""
    try:
        _record(**overrides)
    except TelemetryError:
        return True
    return False


# --------------------------------------------------- the id, minted first (M27.1.1)
def test_a_trace_id_is_mintable_with_no_principal_because_the_mint_takes_nothing() -> None:
    """The leaf is "minted at ingress before identify", and the only way to hold a function
    to that is to leave it nowhere to put a principal. Delete this and a `principal_id`
    parameter can be added with a default, which reads as harmless and moves the mint after
    identification for every caller that passes one."""
    assert inspect.signature(mint_trace_id).parameters == {}


def test_a_minted_trace_id_is_one_the_audit_ledger_will_accept() -> None:
    """A trace id is what joins a ledger row to the audit entries for the same request, and
    `brain.audit.ledger` refuses an id outside its grammar. Delete this and the mint can start
    producing something the audit chain rejects, which is discovered when an entry fails to
    write, long after the row was stored under the id."""
    for _ in range(50):
        minted = mint_trace_id()
        assert re.match(TRACE_ID, minted), minted


def test_a_minted_trace_id_is_at_least_as_unguessable_as_the_one_the_application_mints() -> None:
    """A trace reference is handed to whoever was refused, so a short or countable id lets
    that person walk to the traces either side of their own. The bound is the uuid4 hex
    `brain.app` already mints rather than a number written here. Delete this and the entropy
    can be cut to a couple of bytes without anything failing."""
    assert len(mint_trace_id()) >= len(uuid.uuid4().hex)


def test_two_minted_trace_ids_are_never_the_same() -> None:
    """An id that repeats merges two requests into one row in every report that groups by it.
    Delete this and a mint returning a constant passes every other test in this file."""
    assert len({mint_trace_id() for _ in range(1000)}) == 1000


def test_opening_a_request_has_nowhere_to_put_a_caller() -> None:
    """The whole of M27.1.1: the record is opened before anybody is identified, so the seam
    that opens it must not be able to take an identity even optionally. Delete this and a
    `principal` argument appears on the one function that exists to work without one."""
    assert set(inspect.signature(open_request).parameters) == {"traffic_class", "received_at"}


def test_an_ingress_refuses_a_trace_id_the_audit_ledger_would_not_accept() -> None:
    """An id arriving from elsewhere, a caller-supplied header for instance, is not
    automatically one the ledger can hold. Delete this and a row is written under an id no
    audit entry can carry, so the two records of one request can never be joined."""
    with pytest.raises(TelemetryError):
        _ingress(trace_id="not a trace id")


def test_an_ingress_refuses_a_trace_id_only_a_wider_grammar_would_admit() -> None:
    """The three ids that a nearby, plausible grammar accepts and this column cannot hold.

    A space is refused by every candidate rule, so the test above passes with the trace
    grammar repointed at `brain.audit.ledger.IDENTIFIER`, which is the identifier rule sitting
    one line away in the same module and admits an at-sign and a hundred and twenty-eight
    characters against a column sized for sixty-four. The newline is the other half: `TRACE_ID`
    ends in `$`, which matches before a trailing newline, so `match` admits an id that is one
    log line pretending to be two. Delete this and the grammar can widen to the wrong
    neighbour, or the check can go back to `match`, with every other test in this file green.
    """
    for wrong in ("a" * 65, "trace@id", mint_trace_id() + "\n"):
        with pytest.raises(TelemetryError):
            _ingress(trace_id=wrong)
    # And the two grammars really do disagree, so the probes above are discriminating rather
    # than merely refused. `IDENTIFIER` is read here to be compared against, never applied.
    assert re.fullmatch(IDENTIFIER, "trace@id")
    assert not re.fullmatch(TRACE_ID, "trace@id")


def test_an_ingress_refuses_a_received_at_with_no_timezone() -> None:
    """Ordering is most of what a ledger is read for, and two naive timestamps written by two
    containers in two zones cannot be ordered. Delete this and the ledger accepts a sequence
    nothing can sort, which is not visible in any single row."""
    with pytest.raises(TelemetryError):
        _ingress(received_at=datetime(2026, 9, 7, 9, 30))


# ------------------------------------------ the traffic class, with no default (M27.1.6)
def test_a_request_cannot_be_opened_without_declaring_a_traffic_class() -> None:
    """The point of the declaration is that machine traffic can be excluded from the numbers
    about people, and a class that defaults is a class nobody sets. Delete this and a default
    can be added, after which every channel nobody thought about is filed as whatever the
    first author happened to pick."""
    parameter = inspect.signature(open_request).parameters["traffic_class"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    with pytest.raises(TypeError):
        open_request(received_at=NOW)  # type: ignore[call-arg]


def test_every_traffic_class_is_declared_by_at_least_one_channel() -> None:
    """There must be no spare member for a default to mean: `TrafficClass` carries nothing
    meaning unknown, and every member is something a real channel produces. Delete this and a
    member can be added that no channel declares, which is exactly the shape a default takes
    when somebody needs one."""
    assert {traffic_class_for(channel) for channel in Channel} == set(TrafficClass)


def test_every_traffic_class_can_actually_be_declared_at_ingress() -> None:
    """The positive case. A required argument tested only by its refusal is satisfied by a
    function that refuses everything. Delete this and `open_request` could accept nothing at
    all while the refusal test above stayed green."""
    for declared in TrafficClass:
        opened = open_request(traffic_class=declared, received_at=NOW)
        assert opened.traffic_class is declared
        assert opened.received_at == NOW


def test_nothing_in_this_module_defaults_a_traffic_class() -> None:
    """The scan over the module's own surface, which is what notices when the required
    argument stops being required on some function added later. Delete this and the rule holds
    only for the two places somebody remembered to look at."""
    assert telemetry_gaps() == ()


def _sloppy_open(*, traffic_class: TrafficClass = TrafficClass.AUTOMATION) -> None:
    """A surface that has acquired a default, so the scan can be watched producing a finding."""


@dataclass(frozen=True)
class _SloppyIngress:
    """A record that has acquired one, which is the same omission by a longer path."""

    traffic_class: TrafficClass = TrafficClass.SYSTEM


def test_the_scan_reports_a_traffic_class_that_has_acquired_a_default() -> None:
    """A check that can only ever be pointed at code known to be clean is a check nobody has
    watched produce a finding, and nobody knows whether it can. Delete this and the scan above
    could be a function returning an empty tuple whatever it is given."""
    findings = telemetry_gaps(functions=(_sloppy_open,), models=(_SloppyIngress,))
    assert len(findings) == 2, findings
    assert any("_sloppy_open" in one and "traffic_class" in one for one in findings), findings
    assert any("_SloppyIngress" in one for one in findings), findings


def test_the_scan_reports_a_probe_key_the_allowlist_no_longer_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The value check asks `tracing.mask` about a candidate by filing it under an allowlisted
    key, so a key that falls off the allowlist turns the question from "is this value system
    vocabulary" into "is this key allowlisted" and every identifier is refused. It fails
    closed, and this is what makes it fail loudly as well. Delete this and the branch is one
    nothing has ever executed, which is the same as not having it."""
    monkeypatch.setattr("brain.ops.telemetry._PROBE_KEY", "not_an_allowlisted_key")
    assert any("SAFE_ATTRIBUTES" in one for one in telemetry_gaps()), telemetry_gaps()


# ---------------------------------------------- the per-request fields (M27.1.5)
def _fields_the_leaf_names() -> tuple[str, ...]:
    """The field names M27.1.5 lists, read off the leaf and turned into identifiers.

    Two shapes of phrase and nothing else: a plain noun becomes one field with its spaces
    underscored, and a phrase joined by "and" distributes its first word over the terms, so
    "tokens in and out" is two fields and "tool count and latency" is two more. A third shape
    raises rather than being guessed at, because a derivation that quietly drops a phrase it
    does not recognise reports perfect agreement about a shorter list.
    """
    said = LEAF_SENTENCES["M27.1.5"].partition(":")[2]
    assert said, "M27.1.5 no longer reads as a prefix and a list, so this cannot be derived"

    named: list[str] = []
    for phrase in (one.strip() for one in said.split(",")):
        if " and " not in phrase:
            named.append(phrase.replace(" ", "_"))
            continue
        head, _, rest = phrase.partition(" ")
        terms = [one.strip() for one in rest.split(" and ")]
        assert all(" " not in one for one in terms), f"unrecognised shape in the leaf: {phrase}"
        named.extend(f"{head}_{one}" for one in terms)
    return tuple(named)


#: The field names M27.1.5 declares, before the module adds a unit to the two durations.
LEAF_FIELDS = _fields_the_leaf_names()


def test_the_record_carries_exactly_the_fields_the_leaf_names() -> None:
    """**The leaf is the only thing outside the module that can settle this, and until today
    nothing read it.** The old assertion was `on_record == ("ingress", *TELEMETRY_FIELDS)`
    with `TELEMETRY_FIELDS` imported from the module under test, which is the constant
    compared against itself that `CLAUDE.md` has a section about: drop a field from both the
    tuple and the dataclass and the test still agrees, for every list the module could hold.

    Its docstring argued for that shape and the argument was half right. Restating the names
    in the test file is indeed a list agreeing with itself. The answer is not to read them
    back out of the module, it is to read them off M27.1.5, which is what the module's own
    comment says the tuple is a copy of. `status.leaf_sentences` is the reader, and
    `docs/wbs/export.js` now carries the sentences into `wbs.json` so Python can reach them.

    Three separate claims, because they fail for different reasons: the tuple matches the
    leaf, the dataclass matches the tuple, and `ingress` is the one field the record adds.

    Asserted as a sequence and not as a set, because the module claims the record is declared
    in the order the leaf names its fields. A set comparison holds while the two orders drift
    apart, and the order is what a reader comparing the tuple against the leaf checks by eye.

    Delete this and a field can be dropped from the record, or added without being declared,
    and the ledger row quietly stops matching the leaf it exists to satisfy."""
    assert len(LEAF_FIELDS) == 18, LEAF_FIELDS

    without_units = tuple(one.removesuffix("_ms") for one in TELEMETRY_FIELDS)
    assert without_units == LEAF_FIELDS

    on_record = tuple(declared.name for declared in fields(RequestTelemetry))
    assert on_record == ("ingress", *TELEMETRY_FIELDS)
    assert "ingress" not in LEAF_FIELDS


def test_the_only_fields_carrying_a_unit_are_the_ones_the_leaf_names_as_durations() -> None:
    """The half the test above cannot make: it strips `_ms` before comparing, so a suffix
    stuck on `tokens_in` would pass it. A unit belongs on a duration and nowhere else, and a
    count named `redaction_count_ms` is a number a reader would divide by a thousand.

    The durations are recognised from the leaf's own words rather than from a list written
    here, so a nineteenth field named as a latency is covered on the day it is added, and
    `_DURATION_FIELDS` is checked against the same derivation rather than against itself.

    Delete this and `TELEMETRY_FIELDS` can carry a unit on a field that has none, and the
    comparison against the leaf still passes because it strips exactly that suffix."""
    said_as_a_duration = {
        one for one in LEAF_FIELDS if one.startswith("time_") or one.endswith("_latency")
    }
    carrying_a_unit = {one.removesuffix("_ms") for one in TELEMETRY_FIELDS if one.endswith("_ms")}

    assert said_as_a_duration == {"time_to_first_token", "tool_latency"}
    assert carrying_a_unit == said_as_a_duration
    assert {one.removesuffix("_ms") for one in _DURATION_FIELDS} == said_as_a_duration


def test_every_declared_field_is_a_name_a_count_a_duration_or_a_flag() -> None:
    """The property that makes a five-year window affordable: not one of the eighteen fields
    can hold a thing somebody said. The partition is exact and disjoint, so a nineteenth field
    holding a sentence belongs to no kind and fails here first. Delete this and a `question`
    field can be added that nothing would check."""
    seen: set[str] = set()
    for label, group in KIND_GROUPS:
        assert not (seen & group), f"{label} overlaps a kind already declared"
        seen |= group
    assert seen == set(TELEMETRY_FIELDS)


def test_the_fields_nothing_can_fill_today_are_exactly_the_optional_ones() -> None:
    """`UNFILLABLE_TODAY` is a claim about what this system cannot measure yet, and a claim in
    a mapping is only worth having if it has to match the code. Every field it names defaults
    to None; every field it does not name is required. Delete this and the mapping becomes a
    paragraph free to describe a record it no longer matches."""
    optional = {
        declared.name
        for declared in fields(RequestTelemetry)
        if declared.name != "ingress" and declared.default is None
    }
    assert set(UNFILLABLE_TODAY) == optional
    assert set(TELEMETRY_FIELDS) - optional == {
        "principal",
        "entitlement_hash",
        "lane",
        "cache_hit",
        "status",
    }
    for name, because in UNFILLABLE_TODAY.items():
        assert because.strip(), f"{name} says nothing about why it cannot be filled"


def test_a_field_nobody_measures_is_none_and_never_zero() -> None:
    """Zero is a measurement and None is the absence of one, and a report reading zero retries
    off a system that does not count retries is worse than one reading nothing, because the
    first is believed. `redaction_count` is the one where a plausible zero exists and would be
    false. Delete this and a default of 0 can be added that every report will trust."""
    record = _record()
    for name in UNFILLABLE_TODAY:
        assert getattr(record, name) is None, name


def test_the_ledger_row_carries_every_declared_field_and_the_ingress() -> None:
    """The positive case, and the one saying the row is a reconstruction rather than a
    summary. Delete this and the row can quietly drop the fields nobody looked at, which are
    the fields somebody will want in the argument two years from now."""
    record = _full_record()
    row = record.ledger_row()
    assert set(row) == set(TELEMETRY_FIELDS) | {"trace_id", "traffic_class", "received_at"}
    assert row["principal"] == "u_weiling"
    assert row["tokens_in"] == 1204
    assert row["cache_hit"] is False
    assert row["status"] is RequestStatus.ANSWERED
    assert row["trace_id"] == record.ingress.trace_id
    assert row["received_at"] == NOW


def test_a_record_refuses_a_value_where_a_name_belongs() -> None:
    """The permission half. A person's name in a five-year table is the thing the rest of the
    system spent a wave withholding, and refusing at construction means no such record exists
    to be written. Delete this and `principal="Wei Ling"` is stored."""
    assert _refuses(principal="Wei Ling")
    assert _refuses(policy_epoch="epoch as of Tuesday")
    assert _refuses(connector="Lark Base (production tenant)")


def test_the_value_rule_is_the_one_tracing_declares_and_not_a_second_one() -> None:
    """Two grammars for "is this system vocabulary" disagree eventually, and the one that gets
    loosened is whichever module the person was looking at when their identifier was refused.
    What is asserted is agreement with `brain.ops.tracing`'s own constants, so a private copy
    of the rule here would pass only while it happened to match. Delete this and this module
    can grow its own grammar and drift from the masking that governs everything else."""
    probes = (
        "u_weiling",
        "moonshot/kimi-k2",
        "lark_base",
        "read:client.name",
        "2.4.1",
        "Wei Ling",
        "SNM",
        "a b",
        "40,000",
        "",
        CANARY,
        "x" * SAFE_VALUE_MAX_CHARS,
        "x" * (SAFE_VALUE_MAX_CHARS + 1),
    )
    for probe in probes:
        masked = len(probe) > SAFE_VALUE_MAX_CHARS or not VALUE_TOKEN_RE.match(probe)
        assert _refuses(principal=probe) is bool(masked), probe


def test_a_negative_count_or_duration_is_refused() -> None:
    """A negative count is a subtraction that went the wrong way, and the usual source of one
    is a figure derived from something withheld. Delete this and it is stored and puzzled over
    in a report instead of being refused where it was computed."""
    assert _refuses(tokens_in=-1)
    assert _refuses(retry_count=-2)
    assert _refuses(tool_latency_ms=-0.5)
    assert not _refuses(tokens_in=0)


def test_every_connector_this_system_declares_can_be_recorded() -> None:
    """The positive case for the name rule, anchored to the connectors that actually exist
    rather than to a string invented here. A rule strict enough to refuse `lark_base` would
    make every request through it unrecordable. Delete this and the grammar can be tightened
    until the ledger refuses the real estate."""
    for ceiling in SOURCE_CEILINGS:
        assert _record(connector=ceiling.name).connector == ceiling.name


def test_every_lane_and_every_status_can_be_recorded() -> None:
    """The same positive case for the two closed vocabularies the record carries. Delete this
    and a lane or a status can be added that the record refuses, which takes out every request
    that used it."""
    for lane in Lane:
        assert _record(lane=lane).lane is lane
    for status in RequestStatus:
        assert _record(status=status).status is status


def test_the_entitlement_hash_this_system_produces_can_be_recorded() -> None:
    """`entitlement_hash` is what a support conversation quotes when two people disagree about
    what they saw, so the record has to accept what `EntitlementSet.ent_hash` emits. Delete
    this and the hash format can drift out of what the record admits."""
    assert _record(entitlement_hash=ENT_HASH).entitlement_hash == ENT_HASH


def test_the_entitlement_hash_is_pinned_to_the_shape_the_estate_produces() -> None:
    """The value rule cannot make this field a hash, because `"abc"` is system vocabulary and
    the masker keeps it happily. A five-year row storing `abc` as the reach an answer was
    computed at is a row nobody can compare with anything, and it is the row somebody quotes
    in the argument the ledger exists to settle. The shape comes from
    `brain.audit.ledger.ENT_HASH`, which the audit entry for the same request is validated
    against, rather than from thirty-two characters counted out here. Delete this and the pin
    can be removed and the value rule alone will accept any lowercase token."""
    assert re.fullmatch(ENT_HASH_GRAMMAR, ENT_HASH)
    # Both of these pass the value rule and neither is a hash, which is the whole point.
    assert _refuses(entitlement_hash="abc")
    assert _refuses(entitlement_hash="f" * 31)
    assert not _refuses(entitlement_hash=ENT_HASH)


def test_a_fillable_field_has_no_default_at_all() -> None:
    """`UNFILLABLE_TODAY` names the fields that carry None; every other field must carry
    nothing, so a caller who forgets one gets a `TypeError` rather than a value. A default of
    `False` on `cache_hit` is the same failure as a default of `0` on `retry_count`: a report
    reading "not served from cache" off a route that never said. The test above compares
    against `default is None` and passes with a `False` sitting there, which is how this got
    through the first time. Delete this and a required field can quietly acquire one."""
    for declared in fields(RequestTelemetry):
        if declared.name in UNFILLABLE_TODAY:
            assert declared.default is None, declared.name
        else:
            assert declared.default is MISSING, declared.name
            assert declared.default_factory is MISSING, declared.name


def test_a_record_refuses_a_count_where_a_name_belongs() -> None:
    """A number under a name field is kept by `tracing.mask`, because a number under an
    allowlisted key is a latency or a token count and is exactly what the allowlist is for.
    So the type has to be checked here as well as the value, and the two halves are one
    condition that reads as though either would do. Delete this and the type half can be
    dropped, after which `principal=7` is stored and every value test in this file stays
    green."""
    assert _refuses(principal=7)
    assert _refuses(status=3)
    assert not _refuses(principal="u_weiling")


def test_a_principal_the_audit_chain_would_admit_can_still_be_refused_here() -> None:
    """The cost of borrowing `tracing`'s value rule, pinned so that changing it is a decision.

    That rule was written about system vocabulary and a principal identifier is not system
    vocabulary: `brain.audit.ledger.IDENTIFIER` admits capitals and an at-sign because real
    ids in this system have them, and the trace masker admits neither. So a directory handing
    over `U_WeiLing` gets audit entries and no ledger row at all, which is the reconstruction
    this module exists for, lost to the guard protecting it. It fails closed, which is the
    right direction, and `A_PRINCIPAL_THE_TRACE_GRAMMAR_REFUSES_HAS_NO_LEDGER_ROW_AT_ALL`
    argues it where somebody hitting it will read it. Delete this and the gap is closed or
    widened by whoever meets it first, in an afternoon, without anybody weighing a five-year
    table."""
    assert re.fullmatch(IDENTIFIER, "U_WeiLing")
    assert re.fullmatch(IDENTIFIER, "wei.ling@example.com")
    assert _refuses(principal="U_WeiLing")
    assert _refuses(principal="wei.ling@example.com")


# ------------------------------------------------------------ the status vocabulary
def test_two_outcomes_share_a_status_exactly_when_they_share_a_public_message() -> None:
    """DENIED and ABSENT are one outcome to everybody outside the audit chain, and a count is
    not an exception: thirty refusals against one principal is thirty facts about things that
    exist and are hidden from them. The property is derived from `brain.core.errors`, where
    the messages are declared, rather than restated. Delete this and DENIED can be given a
    status of its own, and the leak arrives through a usage report."""
    message = {cls.outcome: cls.public_message for cls in ERROR_CLASSES}
    assert set(message) == set(Outcome)
    for first in Outcome:
        for second in Outcome:
            shared = status_for(first) is status_for(second)
            assert shared == (message[first] == message[second]), (first, second)


def test_an_answer_is_not_reachable_from_any_error_outcome() -> None:
    """`ANSWERED` records that the lane produced something, and no failure may map onto it.
    Delete this and a fault can be recorded as an answer, which makes every success rate in
    every report wrong in the flattering direction."""
    assert RequestStatus.ANSWERED not in {status_for(outcome) for outcome in Outcome}


# ------------------------------------------------ masking before anything leaves (M27.1.4)
def test_a_span_is_masked_before_it_is_returned_and_there_is_no_other_way_to_get_one() -> None:
    """Masking a caller applies on the way out is masking a caller can forget, so the only
    function here that produces a span produces a masked one. Asserted on the payload markers,
    which are empty strings on an unmasked span, and on every surviving key being one the
    allowlist names. Delete this and `span_for` can return the raw attributes, which is the
    whole of the leak this leaf prevents."""
    span = span_for(_full_record(), environment="production")
    assert span.payload_in.startswith("[masked:")
    assert span.payload_out.startswith("[masked:")
    kept = {key for key, value in span.attributes.items() if not str(value).startswith("[masked:")}
    assert kept, "a span that keeps nothing proves nothing about what it keeps"
    assert kept <= SAFE_ATTRIBUTES, kept - SAFE_ATTRIBUTES


def test_the_principal_is_in_the_ledger_row_and_never_in_the_span() -> None:
    """The two destinations have two different sets of readers, and this is the difference
    made visible: the ledger is ours and entitlement-controlled, the trace store is read by
    operators who cannot read the records underneath it. It holds because
    `tracing.SAFE_ATTRIBUTES` omits the principal, not because of a rule written here. Delete
    this and a person's movements become reconstructable in the trace store."""
    planted = CANARY.lower()
    record = _full_record(principal=planted)
    assert record.ledger_row()["principal"] == planted
    wire = json.dumps(asdict(span_for(record, environment="production")), default=str)
    assert planted not in wire, wire


def test_a_span_still_carries_what_the_allowlist_admits() -> None:
    """The positive case. A span tested only by what it refuses to carry is satisfied by one
    that carries nothing, and a trace with no attributes is useless during the incident it
    exists for. Delete this and `span_for` could mask everything unconditionally."""
    record = _full_record()
    span = span_for(record, environment="production")
    assert span.attributes["model"] == "moonshot/kimi-k2"
    assert span.attributes["trace_id"] == record.ingress.trace_id
    assert str(span.attributes["traffic_class"]) == TrafficClass.HUMAN_INTERACTIVE.value


def test_a_span_refuses_an_environment_the_trace_store_does_not_know() -> None:
    """Langfuse fixes its environment vocabulary at first ingest, so a wrong tag becomes
    permanent the first time a span arrives. The refusal is `tracing.assert_environment`'s and
    this proves the path reaches it. Delete this and `prod` is filed beside `production` for
    the life of the project."""
    with pytest.raises(TracingError):
        span_for(_record(), environment="prod")


def test_a_span_cannot_be_built_without_saying_which_estate_it_belongs_to() -> None:
    """`assert_environment` refuses an unknown tag and cannot refuse a default, because a
    default is one of the three known ones by construction. Defaulting to production files a
    developer's laptop traces beside the client's; defaulting to development hides a
    production incident in a view nobody opens during one. That is the same argument
    `M27.1.6` makes about a traffic class, applied to the other declaration this module takes
    from its caller. Delete this and `environment` can acquire a default, and the refusal test
    above stays green because nothing would ever reach it."""
    parameter = inspect.signature(span_for).parameters["environment"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_a_ledger_row_carries_no_string_that_tracing_would_call_a_value() -> None:
    """The row is the artefact kept for five years, so the no-content rule has to hold over
    the whole of it and not only over the fields somebody remembered to check. Delete this and
    a field can be added whose value bypasses the construction check."""
    for key, value in _full_record().ledger_row().items():
        if isinstance(value, str):
            assert VALUE_TOKEN_RE.match(value), (key, value)
            assert len(value) <= SAFE_VALUE_MAX_CHARS, (key, value)


# ------------------------------------------------------- the payload read (M27.1.3)
def _spies() -> tuple[list[str], Callable[[PayloadRead], None], Callable[[], str]]:
    calls: list[str] = []

    def recorder(_event: PayloadRead) -> None:
        calls.append("record")

    def fetch() -> str:
        calls.append("fetch")
        return "the payload"

    return calls, recorder, fetch


def _read(
    roles: list[str],
    recorder: Callable[[PayloadRead], None],
    fetch: Callable[[], str],
    reason: str = "incident 4412",
) -> str:
    return read_payload_with_role(
        realm_roles=roles,
        at=NOW,
        actor="u_operator",
        trace_id=mint_trace_id(),
        reason=reason,
        record=recorder,
        fetch=fetch,
    )


def test_a_payload_read_writes_the_audit_row_before_it_reads() -> None:
    """Before, not after: a read that failed halfway still happened, and it is the read most
    worth having a row for. Asserted on the order of the two calls rather than on both having
    happened. Delete this and the fetch can move first, which produces an audit trail complete
    except for the reads that went wrong."""
    calls, recorder, fetch = _spies()
    assert _read([PAYLOAD_ROLE], recorder, fetch) == "the payload"
    assert calls == ["record", "fetch"]


def test_a_payload_read_without_the_role_reaches_neither_the_recorder_nor_the_store() -> None:
    """The separate-role half of the leaf. A refusal that still wrote an audit row would make
    the row mean two things and neither countable; a refusal that still fetched would make the
    role decorative. Delete this and the role check can be removed with both other tests in
    this section still green."""
    calls, recorder, fetch = _spies()
    with pytest.raises(TelemetryError):
        _read(["brain-operator"], recorder, fetch)
    assert calls == []


def test_holding_every_platform_role_still_does_not_admit_a_payload_read() -> None:
    """The role is a realm role in the identity provider, granted for an afternoon during an
    incident, and deliberately not a seventh member of `brain.identity.roles.Role`. Asserted
    over the whole enum rather than over one member. Delete this and a super admin silently
    gains permanent access to raw questions and answers."""
    calls, recorder, fetch = _spies()
    with pytest.raises(TelemetryError):
        _read([role.value for role in Role], recorder, fetch)
    assert calls == []


def test_a_recorder_that_fails_stops_the_read() -> None:
    """A payload store nobody can audit is a payload store nobody should be reading from, so a
    recorder that is down stops reads rather than being skipped. Delete this and a failure in
    the recorder can be swallowed, which produces unaudited reads under exactly the conditions
    an incident creates."""
    calls: list[str] = []

    def recorder(_event: PayloadRead) -> None:
        calls.append("record")
        raise RuntimeError("the ledger is unreachable")

    def fetch() -> str:  # pragma: no cover - reaching this is the failure
        calls.append("fetch")
        return "the payload"

    with pytest.raises(RuntimeError):
        _read([PAYLOAD_ROLE], recorder, fetch)
    assert calls == ["record"]


def test_a_payload_read_needs_a_reason_and_an_actor() -> None:
    """A row proving somebody looked and nothing else is not an audit row, and the question
    asked of this table six months later is always why. The refusal is `tracing.PayloadRead`'s
    and this proves the composed path reaches it. Delete this and an unattributed read is
    recorded as though it were attributed."""
    calls, recorder, fetch = _spies()
    with pytest.raises(TracingError):
        _read([PAYLOAD_ROLE], recorder, fetch, reason="   ")
    assert calls == []


# ------------------------------------------------------- the ledger window (M27.1.2)
def test_the_ledger_window_is_the_one_retention_declares() -> None:
    """A second copy of "five years" here would drift, and it would drift in the direction
    that costs money, because the copy nobody looks at is the one that gets raised. Delete
    this and the window becomes a number this module chose for itself."""
    assert LEDGER_DATA_CLASS is DataClass.METADATA_LEDGER
    assert horizon_for(DataClass.METADATA_LEDGER).days == LEDGER_RETENTION_DAYS


def test_the_ledger_is_the_longest_bounded_window_in_the_estate() -> None:
    """Long retention as a relation rather than as a figure. The ledger outlives everything
    else precisely because it holds no content, and it must strictly outlive the traces it
    indexes or a trace exists that no row can be found for. Delete this and
    `LEDGER_DATA_CLASS` can be repointed at the payload or trace class, whose windows are a
    month, and every other test in this file still passes."""
    longest = max(one.days for one in HORIZONS if one.days is not None)
    assert longest == LEDGER_RETENTION_DAYS
    assert retention_for(TraceRecord.TRACE).days < LEDGER_RETENTION_DAYS
    assert retention_for(TraceRecord.BLOB).days < LEDGER_RETENTION_DAYS


def test_a_data_class_with_no_clock_cannot_supply_the_ledger_window() -> None:
    """The guard exists for the day somebody changes the ledger's lifetime, and a guard that
    has never been seen to fire is a guard nobody knows works. `AUDIT` never expires and
    `BUSINESS_RECORD` is kept while its record exists, so neither declares a number of days.
    Delete this and a class with no window silently yields whatever `days` happens to be,
    which is None."""
    with pytest.raises(TelemetryError):
        _fixed_window(DataClass.AUDIT)
    with pytest.raises(TelemetryError):
        _fixed_window(DataClass.BUSINESS_RECORD)
