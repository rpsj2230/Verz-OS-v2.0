"""What the model server says it held, read off an answer, kept in a ring, turned into a limit.

The reader is written from the raw payload and not from a `PeakReport`: a producer and a consumer
sit either side of this value, and a test that built the report itself would test the consumer
twice and the reader not at all, which is the lesson `CLAUDE.md` records about
`lark_wiki.restriction_of`. The store is judged on the statement it sends, compiled for
PostgreSQL, because a ring that overwrote the wrong slot would look like a table that works.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from brain.ops.model_server import Part
from brain.ops.model_server_peaks import (
    REPORT_FIELDS,
    REPORT_KEY,
    PeakReport,
    RecordedPeak,
    read_report,
    slot_for,
    suggested_overall_mib,
    summarise,
)
from brain.ops.model_server_store import record_peak
from brain.tables.model_server import RING_SLOTS

#: Far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def block(**changed: object) -> dict[str, object]:
    base: dict[str, object] = {
        "model": "qwen3-embedding-0.6b@abc123:1024",
        "items": 40,
        "request_bytes": 180_000,
        "duration_ms": 1500,
        "anon_peak_mib": 400,
        "cache_peak_mib": 650,
        "cgroup_limit_mib": 1088,
    }
    base.update(changed)
    return base


def answer(**changed: object) -> dict[str, object]:
    return {"vectors": [], REPORT_KEY: block(**changed)}


def test_a_report_in_an_answer_is_read_for_the_part_the_caller_asked_and_not_the_one_it_names() -> (
    None
):
    """The part is the caller's: it knows which part it posted to, and a block naming another would
    be recorded under the wrong row of the table a limit is tuned from.

    Delete this and a server that names its own part can write another part's row."""
    found = read_report({**answer(), "part": "layout"}, part=Part.EMBEDDING)

    assert found is not None
    assert found.part is Part.EMBEDDING
    assert (found.anon_peak_mib, found.cache_peak_mib) == (400, 650)
    assert found.total_peak_mib == 1050
    assert found.cgroup_limit_mib == 1088


def test_the_keys_a_report_is_read_from_are_the_ones_the_server_writes() -> None:
    """The two programs are built and deployed apart, so the names are held equal from outside
    either: the server's own spelling is imported, the application's is compared with it.

    Delete this and a key renamed on one side is a measurement that is never recorded and never
    missed."""
    from inference_server.meter import REPORT_FIELDS as SERVER_FIELDS
    from inference_server.meter import REPORT_KEY as SERVER_KEY

    assert REPORT_KEY == SERVER_KEY
    assert REPORT_FIELDS == SERVER_FIELDS


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "memory",
        {},
        {REPORT_KEY: None},
        {REPORT_KEY: "a lot"},
        {REPORT_KEY: []},
    ],
    ids=repr,
)
def test_an_answer_with_no_usable_block_is_no_report_and_never_a_refusal(payload: object) -> None:
    """A measurement is about the machine and the answer is about a document; throwing the answer
    away to protect a statistic would make a monitoring field the thing that can lose a file.

    Delete this and a server that stops sending the block breaks embedding."""
    assert read_report(payload, part=Part.EMBEDDING) is None


@pytest.mark.parametrize(
    "field",
    [name for name in REPORT_FIELDS if name not in ("model", "cgroup_limit_mib")],
)
@pytest.mark.parametrize("bad", [None, -1, 1.5, "12", True, 2_000_000_001])
def test_a_count_that_is_not_a_whole_number_inside_the_columns_is_no_report(
    field: str, bad: object
) -> None:
    """Each of the five counts, each of six wrong things: absent, negative, fractional, text, a
    boolean (which is a number to Python) and past what the column holds. A number past the column
    would be a database error in a worker.

    Delete this and one wrong field writes a row, or fails a batch."""
    assert read_report(answer(**{field: bad}), part=Part.EMBEDDING) is None


@pytest.mark.parametrize("model", [None, "", "   ", 7, "x" * 200])
def test_a_model_that_is_not_a_short_name_is_no_report(model: object) -> None:
    """The column is 80 wide and the name is a model's, never a document's. Delete this and a
    server told to echo a string writes it into the table."""
    assert read_report(answer(model=model), part=Part.EMBEDDING) is None


def test_the_limit_may_be_absent_but_not_zero_or_wrong() -> None:
    """The kernel says there is no limit as often as it says one, and a zero limit is a container
    that cannot run. Absent is kept as absent: it is a fact, and not a zero.

    Delete this and an unlimited container is recorded as one limited to nothing."""
    assert read_report(answer(cgroup_limit_mib=None), part=Part.OCR) is not None
    found = read_report(answer(cgroup_limit_mib=None), part=Part.OCR)
    assert found is not None and found.cgroup_limit_mib is None
    assert read_report(answer(cgroup_limit_mib=0), part=Part.OCR) is None
    assert read_report(answer(cgroup_limit_mib=-5), part=Part.OCR) is None


def test_a_field_the_server_adds_has_nowhere_to_go() -> None:
    """The report is built from `REPORT_FIELDS` and nothing else. A server that grew a field, or a
    document that persuaded one to echo a string, cannot reach the table.

    Delete this and a new key in the block becomes a new column nobody reviewed."""
    found = read_report(answer(path="/etc/shadow", text="a passage"), part=Part.TIKA)

    assert found is not None
    assert not hasattr(found, "path") and not hasattr(found, "text")
    assert set(found.__dataclass_fields__) == {"part", *REPORT_FIELDS}


# ------------------------------------------------------------------ the ring
def test_a_batch_number_folds_into_the_fifty_slots_a_part_has() -> None:
    """Fifty to a part, the newest overwriting the oldest, so the table holds at most fifty rows
    for each part however long the server runs and needs no sweep and no DELETE.

    Delete this and the table grows for ever, or the ring's width is changed in one place."""
    assert RING_SLOTS == 50
    assert [slot_for(n) for n in (1, 49, 50, 51, 100)] == [1, 49, 0, 1, 0]
    assert len({slot_for(n) for n in range(1, 500)}) == RING_SLOTS


class _Result:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class _Session:
    """Answers the one question the store asks first and keeps every statement it is sent."""

    def __init__(self, newest: int) -> None:
        self.newest = newest
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        return _Result(self.newest)


def _dialect() -> Any:
    return postgresql.dialect()  # type: ignore[no-untyped-call]


def _sql(statement: Any) -> str:
    return str(statement.compile(dialect=_dialect()))


def _report() -> PeakReport:
    found = read_report(answer(), part=Part.EMBEDDING)
    assert found is not None
    return found


def test_the_first_batch_of_a_part_is_number_one_and_lands_in_slot_one() -> None:
    """Counted from one, as the table's own check requires, and from the newest the part has.

    Delete this and the first batch is number nought, which the table refuses, in a worker."""
    session = _Session(newest=0)

    assert asyncio.run(record_peak(session, _report(), at=LONG_AGO)) == 1  # type: ignore[arg-type]
    insert = session.statements[-1]
    assert insert.compile(dialect=_dialect()).params["slot"] == 1


def test_the_fifty_first_batch_overwrites_the_first_slot_it_used() -> None:
    """Number 50 is slot 0 and number 51 is slot 1 again: the ring wraps. The statement is an
    upsert on part and slot, and it overwrites everything but the key.

    Delete this and a part's fifty-first batch fails on its own primary key, so the server stops
    being measured on the day it has been running a while."""
    session = _Session(newest=50)

    assert asyncio.run(record_peak(session, _report(), at=LONG_AGO)) == 51  # type: ignore[arg-type]
    text = _sql(session.statements[-1])

    assert "ON CONFLICT (part, slot) DO UPDATE" in text
    update = text.split("DO UPDATE SET", 1)[1]
    assert "batch_no = excluded.batch_no" in update
    assert "anon_peak_mib = excluded.anon_peak_mib" in update
    assert "part =" not in update.replace("cgroup", "")
    assert "slot =" not in update


def test_the_newest_number_is_asked_of_this_part_only() -> None:
    """Each part has a ring of its own, so the question is "the newest of this part", and an
    answer for another part's batches would put this one in the wrong slot.

    Delete this and parts share a counter, and a busy part overwrites a quiet one's history."""
    session = _Session(newest=3)
    asyncio.run(record_peak(session, _report(), at=LONG_AGO))  # type: ignore[arg-type]

    asked = session.statements[0].compile(dialect=_dialect())
    assert "WHERE ops.model_server_peak.part =" in str(asked)
    assert "embedding" in asked.params.values()


# ------------------------------------------------------------------ what a person tuning reads
def _row(part: Part, n: int, anon: int, cache: int) -> RecordedPeak:
    return RecordedPeak(
        part=part,
        batch_no=n,
        at=LONG_AGO,
        model="m",
        items=1,
        request_bytes=1,
        duration_ms=1,
        anon_peak_mib=anon,
        cache_peak_mib=cache,
        cgroup_limit_mib=None,
    )


def test_the_summary_is_the_largest_per_part_and_the_suggestion_the_largest_part_not_a_sum() -> (
    None
):
    """The container holds one part at a time, so its suggested limit is the largest part's and
    never the parts added together, and a part is summarised by its largest batch and not its mean.

    Delete this and the screen suggests the rejected design's limit, or one that the average batch
    fits and the largest kills."""
    rows = [
        _row(Part.EMBEDDING, 1, 300, 600),
        _row(Part.EMBEDDING, 2, 420, 640),
        _row(Part.EMBEDDING, 3, 100, 600),
        _row(Part.LAYOUT, 1, 1200, 0),
    ]
    summaries = summarise(rows)

    by_part = {one.part: one for one in summaries}
    assert [one.part for one in summaries] == [Part.LAYOUT, Part.EMBEDDING], "declaration order"
    assert by_part[Part.EMBEDDING].batches == 3
    assert by_part[Part.EMBEDDING].largest_anon_mib == 420
    assert by_part[Part.EMBEDDING].largest_total_mib == 1060
    overall = suggested_overall_mib(summaries)
    assert overall == max(one.suggested_limit_mib or 0 for one in summaries)
    assert overall is not None and overall < sum(one.suggested_limit_mib or 0 for one in summaries)


def test_nothing_measured_summarises_to_nothing_and_suggests_nothing() -> None:
    """No row is no line and no figure, never a zero. Delete this and a screen with nothing
    measured offers a limit of nothing."""
    assert summarise([]) == ()
    assert suggested_overall_mib(()) is None
