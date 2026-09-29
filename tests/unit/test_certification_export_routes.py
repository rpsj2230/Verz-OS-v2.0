"""The access certification report: the review's own rows, recorded before they are handed over.

Driven through the real application with the review store and the export record held in memory,
reusing `tests/unit/test_govern_people_routes.py`' holdings and readers, so the report is judged
against the same decisions the review screen is.

Task ids: M27.15.21
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from brain import certification_export_routes
from brain.api import API_PREFIX
from brain.govern_people_routes import GrantHolding, grants_of
from brain.ops.data_export_store import TakenExport
from brain.ops.export import ExportReason
from brain.tables.data_export import ExportDataSet, ExportForm
from brain.tables.gate import CapabilityGrantRow
from tests.unit.test_govern_people_routes import (
    Wired,
    a_grant_row,
    a_pack_holding,
    post,
)
from tests.unit.test_govern_people_routes import wired as wired

EXPORT = f"{API_PREFIX}/govern/access-review/export"
BODY = {"reason": "regulatory_request", "reason_reference": "AUDIT-2026-Q3"}


@dataclass
class Records:
    """A `ReportRecords` in memory, keeping each record and refusing when told to."""

    taken: list[dict[str, Any]] = field(default_factory=list)
    fail: bool = False

    async def record_report(self, **given: Any) -> TakenExport:
        if self.fail:
            msg = "the insert failed"
            raise RuntimeError(msg)
        self.taken.append(given)
        return TakenExport(
            export_id=str(uuid.uuid4()),
            data_set=given["data_set"],
            requested_by=given["actor"],
            reason=given["reason"],
            reason_reference=given["reason_reference"],
            produced_at=given["at"],
            form=ExportForm.READABLE,
            first_seq=None,
            last_seq=None,
            entries=given["entries"],
            verified=None,
            document_digest=given["document_digest"],
        )


@pytest.fixture
def records(wired: Wired) -> Iterator[Records]:
    kept = Records()
    wired.client.app.state.report_records = kept  # type: ignore[attr-defined]
    yield kept


def people_in(document: str) -> list[str]:
    return [row["Person"] for row in csv.DictReader(io.StringIO(document))]


def test_a_reviewer_exports_exactly_the_holdings_they_may_decide_and_it_is_recorded_first(
    wired: Wired,
    records: Records,
) -> None:
    """M27.15.21. Delete this and the report can carry a holding the review withholds from this
    reviewer, or be handed over with no record, or be recorded with a digest of some other text."""
    finance = GrantHolding(
        row=a_grant_row("u_3", "read:client.name"),
        display_name="Grace Finance",
        department="finance",
    )
    wired.review.held = [a_pack_holding("u_5", "web"), finance]

    answer = post(wired, EXPORT, "u_elsewhere", BODY)

    assert answer.status_code == 200, answer.text
    body = answer.json()
    document = body["document"]
    assert len(records.taken) == 1
    (taken,) = records.taken
    assert taken["data_set"] is ExportDataSet.ACCESS_CERTIFICATION
    assert taken["reason"] is ExportReason.REGULATORY_REQUEST
    assert taken["actor"] == "u_elsewhere"
    assert taken["entries"] == 1
    assert taken["document_digest"] == hashlib.sha256(document.encode("utf-8")).hexdigest()
    assert "Grace Finance" not in document and "u_3" not in document
    assert len(people_in(document)) == 1
    assert body["filename"].endswith(".csv")
    assert body["export"]["form"] == "readable"


def test_an_administrator_exports_every_holding_the_review_would_show_them(
    wired: Wired,
    records: Records,
) -> None:
    """The positive case for the narrowing above. Delete this and a report that always holds one
    row, or none, passes the test that it withholds."""
    wired.review.held = [
        a_pack_holding("u_5", "web"),
        GrantHolding(
            row=a_grant_row("u_3", "read:client.name"), display_name="G", department="finance"
        ),
    ]

    answer = post(wired, EXPORT, "u_admin", BODY)

    assert answer.status_code == 200, answer.text
    assert len(people_in(answer.json()["document"])) == 2
    assert records.taken[0]["entries"] == 2


def test_a_reader_without_the_review_is_refused_before_anything_is_read_or_recorded(
    wired: Wired,
    records: Records,
) -> None:
    """Delete this and somebody who may not open the review can take its report."""
    answer = post(wired, EXPORT, "u_none", BODY)

    assert answer.status_code == 404
    assert records.taken == []
    assert wired.review.calls == []


def test_a_reference_with_a_space_or_an_unknown_reason_is_refused_by_its_shape(
    wired: Wired,
    records: Records,
) -> None:
    """The reason is a closed word and the reference a token, for the reason
    `brain.ops.export.A_REASON_A_CALLER_CAN_OMIT_IS_A_REASON_NOBODY_GIVES` gives. Delete this and a
    person's name can be written into the record of an export as its reference."""
    spaced = post(wired, EXPORT, "u_admin", {**BODY, "reason_reference": "Jane Smith"})
    unknown = post(wired, EXPORT, "u_admin", {**BODY, "reason": "curiosity"})

    assert spaced.status_code == unknown.status_code == 422
    assert records.taken == []


def test_a_record_that_fails_hands_over_no_document(
    wired: Wired,
    records: Records,
) -> None:
    """`THE_ROW_AND_THE_DOCUMENT_COMMIT_TOGETHER`, for the report. Delete this and a report can
    leave the building while its record failed."""
    wired.review.held = [a_pack_holding("u_5", "web")]
    records.fail = True

    answer = post(wired, EXPORT, "u_admin", BODY)

    assert answer.status_code == 500
    assert "document" not in answer.text


def test_a_cell_a_spreadsheet_would_run_is_written_as_text() -> None:
    """Delete this and a grant's reason beginning with = runs as a formula in the auditor's copy."""
    row = a_grant_row("u_2", "read:client.name")
    row.reason = "=HYPERLINK(1)"
    held = GrantHolding(row=row, display_name="W", department="web")
    view = certification_export_routes.review_row(held, grants_of(held), None)
    document = certification_export_routes.report([view], {})

    assert "'=HYPERLINK(1)" in document
    assert isinstance(view.granted_at, datetime)
    assert isinstance(row, CapabilityGrantRow)
