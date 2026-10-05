"""The vector leg as the search runs it: the index walk, and an exact re-ask over the reader's reach
when the walk came back short, bounded by a measured ceiling.

Over a stand-in row source that answers each statement by its shape, so every branch is driven
without a database; `tests/unit/test_acceptance_retrieval.py` runs the leg against PostgreSQL.

Task ids: M15.2.3, M15.2.4
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import structlog

from brain.knowledge import document_tools
from brain.knowledge.document_tools import nearest_passages
from brain.knowledge.embedding import EmbeddedVector, EmbeddingModel
from brain.knowledge.rows import RowQuery
from brain.knowledge.search import (
    CANDIDATE_DEPTH,
    EMBEDDING_DIMENSIONS,
    EXACT_RESCAN_CEILING,
    ITERATIVE_SCAN,
    Reach,
)

READER = Reach(principal_id="u_reader", departments=("web",))


def vector() -> EmbeddedVector:
    model = EmbeddingModel(name="m", revision="r", dimensions=EMBEDDING_DIMENSIONS)
    return EmbeddedVector(model=model, values=tuple([1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)))


def kind_of(query: RowQuery) -> str:
    if query.columns == ("held",):
        return "count"
    told = " ".join(str(one.compile().params) for one in query.settings)
    return "walk" if ITERATIVE_SCAN[0][0] in told else "exact"


class Rows:
    """Answers the walk, the count and the exact sort as the test says, and records the order."""

    def __init__(self, *, walked: int, held: int, exact: int) -> None:
        self.answers: dict[str, list[dict[str, Any]]] = {
            "walk": [{"chunk_id": f"w{n}"} for n in range(walked)],
            "count": [{"held": held}],
            "exact": [{"chunk_id": f"e{n}"} for n in range(exact)],
        }
        self.asked: list[str] = []

    async def rows(self, query: RowQuery) -> list[dict[str, Any]]:
        kind = kind_of(query)
        self.asked.append(kind)
        return list(self.answers[kind])


def run(records: Rows) -> tuple[str, ...]:
    return asyncio.run(nearest_passages(records, vector(), reach=READER))


def test_a_full_walk_is_the_leg_and_nothing_else_is_asked() -> None:
    """Delete this and every search pays for a count and an exact sort it does not need."""
    records = Rows(walked=CANDIDATE_DEPTH, held=10, exact=3)
    assert run(records) == tuple(f"w{n}" for n in range(CANDIDATE_DEPTH))
    assert records.asked == ["walk"]


def test_a_short_walk_over_a_reach_within_the_ceiling_is_asked_again_exactly() -> None:
    """**The fix.** A walk that lost passages to dead entries or a running vacuum returns fewer
    than asked; the exact sort over the same reach is what the reader is given. Delete this and a
    narrow reader misses their own passages about one search in twenty while the index churns
    (measured 2026-10-05)."""
    records = Rows(walked=1, held=EXACT_RESCAN_CEILING, exact=3)
    assert run(records) == ("e0", "e1", "e2")
    assert records.asked == ["walk", "count", "exact"]


def test_a_short_walk_over_a_reach_past_the_ceiling_stands_and_is_logged_for_an_operator() -> None:
    """**The other side of the ceiling.** Past it the exact sort would be a scan of the whole
    reach (500,000 passages took 1.8 s), so the walk's answer stands, the lexical leg carries the
    rest, and an operator is told once, in words naming no reader, document or count. Delete this
    and a broad reader on a churning index is given a full vector scan on every short walk."""
    records = Rows(walked=1, held=EXACT_RESCAN_CEILING + 1, exact=3)
    with structlog.testing.capture_logs() as logs:
        assert run(records) == ("w0",)
    assert records.asked == ["walk", "count"]
    assert [(one["event"], one["log_level"]) for one in logs] == [
        ("knowledge.vector_leg_short", "warning")
    ]
    assert set(logs[0]) == {"event", "log_level", "ceiling"}


@pytest.mark.parametrize("walked", [0, CANDIDATE_DEPTH - 1])
def test_short_means_fewer_than_the_depth_asked(walked: int) -> None:
    """The trigger at its boundary. Delete this and the trigger can drift to "returned nothing",
    which misses the walk that found one passage of three."""
    records = Rows(walked=walked, held=5, exact=2)
    assert run(records) == ("e0", "e1")


def test_the_ceiling_is_the_one_measured_and_the_count_stops_one_past_it() -> None:
    """The count reads one row past the ceiling and no further, so asking costs at most that
    whatever the reach's size. Delete this and the bound becomes a count of the whole reach."""
    held = document_tools.reach_held_query(vector(), reach=READER)
    text = str(held.statement.compile(compile_kwargs={"literal_binds": False}))
    assert "LIMIT" in text
    assert held.statement.compile().params["param_1"] == EXACT_RESCAN_CEILING + 1
    assert 10_000 < EXACT_RESCAN_CEILING < 500_000


def test_the_exact_sort_cannot_be_served_by_the_index() -> None:
    """The re-ask orders by the distance plus nothing, which the operator class cannot serve, and
    carries none of the walk's scan settings. Delete this and the re-ask can quietly become a
    second walk with the same blind spots."""
    exact = document_tools.exact_vector_search_query(vector(), reach=READER)
    assert kind_of(exact) == "exact"
    assert "+ " in str(exact.statement.compile()).split("ORDER BY", 1)[1]
