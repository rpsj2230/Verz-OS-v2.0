"""The minimal index and the canary, each refusal beside the case it must still accept.

`brain.connectors.minimal_index` is what makes "connectors never bulk-sync" falsifiable, so every
rule in it is tested from both sides here: the kept rows Xero's own code produces from its
recordings pass, and each way a row can exceed its manifest is refused on its own. The canary
harness is tested the same way, because a harness that never sees anything reports every sync
clean.

Task ids: M11.9.1, M11.8.1, M11.8.2, M11.4.5
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from pydantic import BaseModel

from brain.connectors import xero
from brain.connectors.minimal_index import (
    A_FIELD_NOBODY_DECLARED_IS_A_COPY,
    A_VALUE_LONGER_THAN_A_LABEL_IS_A_BODY,
    CANARY_MARK,
    CanaryError,
    MinimalIndexError,
    StoredRow,
    assert_minimal_index,
    fresh_canary,
    index_fields,
    minimal_index_findings,
    plant,
    planted,
    sightings,
)
from brain.connectors.projection import ProjectedRecord
from brain.core.projection import MAX_LABEL_CHARS, MAX_PROJECTED_FIELDS
from brain.ops.connectable import manifest_for
from brain.ops.connector_sync import (
    INDEX_EXCEEDED,
    ConnectorSyncError,
    kept_fields,
    stored_fields,
)
from tests.fixtures.cassettes import FILES, for_source

TENANT: Final = "11111111-2222-3333-4444-555555555555"
#: Far from any wall clock; nothing here is about the present.
SEEN: Final = datetime(2019, 6, 1, 12, 0, tzinfo=UTC)
MANIFEST: Final = manifest_for(xero.CONNECTOR_NAME, {"tenant_id": TENANT})


def kept_invoices() -> tuple[ProjectedRecord, ...]:
    """What Xero's own code keeps from its recorded invoices, through the cassette file's replay."""
    recording = next(one for one in for_source("xero") if one.cid == "XERO-200-invoices")
    kept = FILES["xero"].replay(recording).kept
    assert kept, "the recorded invoices kept nothing, so this would test nothing"
    return kept


def a_row(**fields: Any) -> StoredRow:
    base: dict[str, Any] = {"tenant_id": TENANT, "status": "AUTHORISED", "invoice_number": "INV-1"}
    base.update(fields)
    return StoredRow(source="xero", entity=xero.ENTITY_INVOICE, source_id="b1f2-0447", fields=base)


# ------------------------------------------------------------------ the index


def test_what_xeros_own_code_keeps_is_inside_its_minimal_index() -> None:
    """**The positive case every refusal below needs.** The invoices Xero's projection keeps from
    the recorded answer, with the tenant its visibility rule names laid over them, are inside the
    index its manifest declares.

    Delete this and a check that refused every row would pass the rest of the file, and the
    worker would keep nothing on any install."""
    rows = [
        StoredRow(
            source=one.source,
            entity=one.entity,
            source_id=one.source_id,
            fields=stored_fields(one, MANIFEST.projections[0].visibility),
        )
        for one in kept_invoices()
    ]

    assert minimal_index_findings(MANIFEST, rows) == ()
    assert_minimal_index(MANIFEST, rows)
    assert "tenant_id" in index_fields(MANIFEST, xero.ENTITY_INVOICE)
    assert index_fields(MANIFEST, "no_such_entity") == frozenset()


def test_a_field_the_manifest_does_not_declare_is_refused_whatever_it_is_called() -> None:
    """The amount arriving beside the status, which is what a mapping copied whole produces.
    Delete this and a connector keeps every value its source returns, one field at a time."""
    findings = minimal_index_findings(MANIFEST, [a_row(amount_due="1200.00")])

    assert len(findings) == 1
    assert "'amount_due'" in findings[0] and A_FIELD_NOBODY_DECLARED_IS_A_COPY in findings[0]
    assert "1200.00" not in findings[0], "a finding names the field and never the value"
    with pytest.raises(MinimalIndexError, match="amount_due"):
        assert_minimal_index(MANIFEST, [a_row(amount_due="1200.00")])


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        ({"status": {"code": "AUTHORISED"}}, "as a dict, not a pointer"),
        ({"invoice_number": "x" * (MAX_LABEL_CHARS + 1)}, A_VALUE_LONGER_THAN_A_LABEL_IS_A_BODY),
        ({"tenant_id": "99999999-8888-7777-6666-555555555555"}, "visibility rule does not name"),
    ],
    ids=["nested", "longer-than-a-label", "another-tenant"],
)
def test_a_declared_field_holding_what_an_index_may_not_hold_is_refused(
    fields: dict[str, Any], said: str
) -> None:
    """A declared name is not a licence for any value: a container, a string longer than a label,
    and a visibility field naming another tenant are each refused. Delete this and a body can be
    kept under a declared label, or a row made readable by the wrong tenant's grant."""
    findings = minimal_index_findings(MANIFEST, [a_row(**fields)])

    assert len(findings) == 1
    assert said in findings[0]


def test_a_value_exactly_as_long_as_a_label_is_kept() -> None:
    """The boundary, from the side that must pass. Delete this and the limit can drift to 119
    and refuse every full-length label a source sends."""
    assert minimal_index_findings(MANIFEST, [a_row(invoice_number="x" * MAX_LABEL_CHARS)]) == ()


def test_a_row_of_an_entity_or_a_source_the_manifest_does_not_project_is_refused() -> None:
    """Nothing of an entity nobody declared may be kept, and a row is only held to its own
    source's manifest. Delete this and a connector keeps a second entity kind nobody reviewed."""
    stray = dataclasses.replace(a_row(), entity="credit_note")
    elsewhere = dataclasses.replace(a_row(), source="hubspot")

    (entity,) = minimal_index_findings(MANIFEST, [stray])
    (source,) = minimal_index_findings(MANIFEST, [elsewhere])

    assert "projects no 'credit_note'" in entity
    assert "against xero's manifest" in source


def test_a_row_over_the_cap_is_refused_as_well_as_each_field_it_should_not_hold() -> None:
    """Twelve fields per entity kind, counted on the kept row. Delete this and a row whose extra
    fields happen to be declared elsewhere goes uncounted."""
    extra = {f"extra_{n}": "x" for n in range(MAX_PROJECTED_FIELDS)}
    findings = minimal_index_findings(MANIFEST, [a_row(**extra)])

    assert any(f"over {MAX_PROJECTED_FIELDS}" in one for one in findings)
    assert sum("which its manifest does not declare" in one for one in findings) == len(extra)


def test_the_worker_refuses_a_record_outside_the_index_before_it_is_kept() -> None:
    """`kept_fields` is the write's gate: a record of Xero's own shape passes, a record carrying
    an undeclared field and one of an entity nothing projects are both refused with the constant
    sentence and never the value. Delete this and the worker writes whatever a reading returns."""
    (invoice,) = kept_invoices()
    leaking = dataclasses.replace(invoice, fields={**invoice.fields, "amount_due": "1200.00"})
    stray = dataclasses.replace(invoice, entity="credit_note")

    assert kept_fields(invoice, MANIFEST)["tenant_id"] == TENANT
    for refused in (leaking, stray):
        with pytest.raises(ConnectorSyncError) as caught:
            kept_fields(refused, MANIFEST)
        assert str(caught.value) == INDEX_EXCEEDED


# ------------------------------------------------------------------ the canary


def test_a_fresh_canary_is_marked_and_never_repeats() -> None:
    """Delete this and two runs could plant the same string, so one run's sighting could be the
    other's leak."""
    minted = {fresh_canary("x") for _ in range(50)}

    assert len(minted) == 50
    assert all(one.startswith(f"{CANARY_MARK}X-") for one in minted)


def test_planting_replaces_every_marker_and_leaves_everything_else() -> None:
    """Delete this and a canary could be planted in one of two places a recording marks, and the
    other value would be checked against a string nobody planted."""
    body: dict[str, Any] = {
        "Invoices": [{"AmountDue": "CANARY-OLD", "Status": "AUTHORISED"}],
        "Tax": ("CANARY-OLD", 3),
    }

    replaced, count = plant(body, "CANARY-NEW")

    assert count == 2
    assert replaced == {
        "Invoices": [{"AmountDue": "CANARY-NEW", "Status": "AUTHORISED"}],
        "Tax": ("CANARY-NEW", 3),
    }
    assert body["Invoices"][0]["AmountDue"] == "CANARY-OLD", "the recording itself is untouched"


def test_a_canary_planted_nowhere_is_refused_rather_than_reported_clean() -> None:
    """A search for a string that was never in the input finds nothing. Delete this and a
    recording that lost its marker makes every canary check pass."""
    with pytest.raises(CanaryError, match="nothing was planted"):
        planted({"Status": "AUTHORISED"}, "CANARY-NEW")
    assert planted({"Note": "CANARY-OLD"}, "CANARY-NEW") == {"Note": "CANARY-NEW"}


class _Model(BaseModel):
    note: str


@dataclasses.dataclass(frozen=True)
class _Kept:
    fields: dict[str, Any]


@pytest.mark.parametrize(
    "place",
    [
        "a log line holding CANARY-X-1 somewhere",
        b"bytes holding CANARY-X-1",
        {"key CANARY-X-1": 1},
        {"nested": [{"deep": ("CANARY-X-1",)}]},
        _Kept(fields={"note": "CANARY-X-1"}),
        _Model(note="CANARY-X-1"),
        ValueError("a refusal quoting CANARY-X-1"),
    ],
    ids=["str", "bytes", "key", "nested", "dataclass", "pydantic", "exception"],
)
def test_a_canary_is_seen_wherever_a_copy_can_hide(place: object) -> None:
    """Every shape a kept row, a log capture or an exception can take. Delete this and the harness
    can be blind to one shape, and a leak in that shape reports clean."""
    assert sightings("CANARY-X-1", place)


def test_a_place_without_the_canary_is_clean() -> None:
    """The other side: sightings is empty when the string is absent. Delete this and a harness
    that saw the canary everywhere would pass the test above."""
    assert sightings("CANARY-X-1", {"note": "CANARY-X-2"}, ["CANARY-X"], b"nothing", None) == ()
