"""A document read inside the application is budgeted against the application's own memory.

Found on 2026-09-29 while measuring a staging install for the owner's upload-limit question: the
console read PDF and Word uploads in the application container and admitted each against the
parse worker's 448 MiB, in a container with well under a hundred MiB to spare. These tests hold
the budget to the container it describes, the two in-app call sites to that budget, and the
finding that says what the application can read.

Task ids: M7.7.11
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from brain import knowledge_intake_routes, knowledge_routes
from brain.knowledge.app_parse_budget import (
    APP_MEMORY_MIB,
    APP_RESIDENT_MIB,
    APP_SERVICE,
    app_parse_budget_bytes,
    app_parse_gaps,
    largest_in_app_cost,
    resident_mib_for,
)
from brain.knowledge.ingest import AdmittedUpload, MediaType
from brain.knowledge.parse_budget import MIB, fits_parse_budget, parse_budget_bytes
from brain.knowledge.text_path import TEXT_PATH_TYPES
from brain.ops.compose import BASELINE_FILE, service_mib
from brain.runtime import MEASURED_SUPERVISOR_MB, MEASURED_WORKER_PEAK_MB, most_workers

REPO = Path(__file__).resolve().parents[2]


def _upload(media_type: MediaType, size_bytes: int) -> AdmittedUpload:
    """An admission record of a type and size, without the bytes, as test_parse_budget does."""
    return AdmittedUpload(
        filename="handbook", media_type=media_type, size_bytes=size_bytes, digest="a" * 64
    )


def test_the_application_s_memory_figure_is_the_limit_the_compose_file_declares() -> None:
    """Read from `docker-compose.yml` through the parser the host budget uses. Delete this and the
    application's limit can be raised or cut in the file while the budget goes on describing the
    old container, which is the drift this module exists to stop."""
    document = yaml.safe_load((REPO / BASELINE_FILE).read_text(encoding="utf-8"))
    assert service_mib({BASELINE_FILE: document}, APP_SERVICE) == APP_MEMORY_MIB


def test_the_budget_is_the_spare_memory_shared_among_the_processes_the_container_starts() -> None:
    """Worked from the figures rather than from the functions. A 1024 MiB container starts
    (1024 - 96) // 220 = 4 processes and holds 96 + 4 x 220 = 976 MiB before any read, so
    48 MiB is spare and each process may be reading one document. A 2048 MiB one starts 8 and
    holds 1856; a 16 GiB one would start 74 by memory and is held to the pooler's 10, holding
    2296. Delete this and the budget can drop the division, which hands every process the whole
    of the spare memory at once, forget the pooler's cap, or forget that each process brings its
    own memory, which promises a larger container room it does not have."""
    assert app_parse_budget_bytes(memory_mib=1024) == 48 * MIB // 4
    assert app_parse_budget_bytes(memory_mib=2048) == 192 * MIB // 8
    assert app_parse_budget_bytes(memory_mib=16384) == 14088 * MIB // 10


def test_the_model_covers_what_the_deployed_container_was_measured_to_hold() -> None:
    """The resident figure is modelled from per-process measurements, and the model has to be at
    least what the whole container was seen to hold at its peak. Delete this and a sizing figure
    lowered below the measurement promises the deployed container room it did not have."""
    assert resident_mib_for(APP_MEMORY_MIB) >= APP_RESIDENT_MIB


def test_the_per_process_measurements_add_up_to_the_whole_container_s() -> None:
    """Two measurements taken independently, the cgroup's peak for the whole container and each
    process's own share, have to agree to within a MiB per process of rounding. Delete this and
    either measured figure can be edited to suit a worker count, since every other test takes
    the measurements as given."""
    processes = most_workers(APP_MEMORY_MIB)
    summed = MEASURED_SUPERVISOR_MB + processes * MEASURED_WORKER_PEAK_MB
    assert abs(summed - APP_RESIDENT_MIB) <= processes


def test_a_container_already_full_refuses_every_document() -> None:
    """Nothing spare is a budget of nothing, never a negative number a comparison could pass.
    Delete this and a resident figure at or over the limit becomes a budget nobody reads."""
    assert app_parse_budget_bytes(memory_mib=1024, resident_mib=1024) == 0
    assert app_parse_budget_bytes(memory_mib=1024, resident_mib=1200) == 0


def test_a_pdf_the_parse_worker_would_take_is_refused_on_the_in_app_path() -> None:
    """The defect in one comparison: a 5 MiB PDF declares 30 MiB, which the parse worker's budget
    admits and the application's does not. The sibling below proves the in-app budget still
    admits an ordinary small file. Delete this and the in-app budget can be as generous as the
    worker's again."""
    five_mib_pdf = _upload(MediaType.PDF, 5 * MIB)
    assert fits_parse_budget(five_mib_pdf, budget_bytes=parse_budget_bytes())
    assert not fits_parse_budget(five_mib_pdf, budget_bytes=app_parse_budget_bytes())


def test_an_ordinary_small_document_still_fits_the_in_app_budget() -> None:
    """The positive half: a budget that refused everything would pass the test above. A 1 MiB
    Word file and a 2 MiB text file are what the console is mostly given. Delete this and the
    budget can be cut to nothing with the suite green."""
    assert fits_parse_budget(
        _upload(MediaType.DOCX, 1 * MIB), budget_bytes=app_parse_budget_bytes()
    )
    assert fits_parse_budget(
        _upload(MediaType.PLAIN, 2 * MIB), budget_bytes=app_parse_budget_bytes()
    )


def test_an_upload_read_in_the_request_is_admitted_against_the_application_s_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The call site, which is where the defect was: it passed no budget, so the parse worker's
    was used. Delete this and the route can go back to passing nothing."""
    passed: dict[str, Any] = {}

    def reader(*args: object, **kwargs: Any) -> str:
        passed.update(kwargs)
        return "read"

    monkeypatch.setattr(knowledge_routes, "read_for_text_path", reader)
    knowledge_routes.read_one_at_a_time(
        object(),  # type: ignore[arg-type]
        kind=object(),  # type: ignore[arg-type]
        placement=object(),  # type: ignore[arg-type]
        owner_id="p_uploader",
    )
    assert passed["budget_bytes"] == app_parse_budget_bytes()


def test_a_link_read_in_the_request_is_admitted_against_the_application_s_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other in-app call site, a link's page, read under the same lock in the same
    container. Delete this and a large page is admitted against the parse worker's budget."""
    passed: dict[str, Any] = {}

    def reader(*args: object, **kwargs: Any) -> str:
        passed.update(kwargs)
        return "read"

    class Caller:
        class principal:  # noqa: N801 - mirrors the attribute path the route reads
            id = "p_uploader"

    class Asked:
        caller = Caller()

        class now:  # noqa: N801
            @staticmethod
            def date() -> str:
                return "2999-01-01"

    monkeypatch.setattr(knowledge_intake_routes, "read_for_link", reader)
    knowledge_intake_routes._read_link(
        object(),  # type: ignore[arg-type]
        kind=object(),  # type: ignore[arg-type]
        placement=object(),  # type: ignore[arg-type]
        asked=Asked(),  # type: ignore[arg-type]
    )
    assert passed["budget_bytes"] == app_parse_budget_bytes()


def test_the_finding_names_what_the_application_can_read_when_the_door_admits_more() -> None:
    """On the deployed figures the door admits a PDF far larger than the application can read,
    and the operator is told the largest it can. Delete this and the application can refuse
    files the door accepted with nothing at start saying why."""
    [finding] = app_parse_gaps()
    media_type, _ = largest_in_app_cost()
    assert media_type.value in finding
    assert f"{app_parse_budget_bytes() // MIB} MiB" in finding


def test_there_is_no_finding_when_the_container_can_read_everything_the_door_admits() -> None:
    """The sibling: a container large enough is told nothing. Delete this and a finding that
    fired on every install whatever its size would pass the test above."""
    assert app_parse_gaps(memory_mib=16384) == ()


def test_the_largest_in_app_cost_is_over_the_text_path_s_own_types() -> None:
    """Images are read by the parse worker, never in the request, so their costs do not bound
    the application. Delete this and the finding can name a JPEG the application never opens."""
    media_type, _ = largest_in_app_cost()
    assert media_type in TEXT_PATH_TYPES
