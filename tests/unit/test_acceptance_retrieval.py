"""The install checks for retrieval, each passing on PostgreSQL at head and each shown failing.

The pure half holds the module's figures to the product's: the crowd is larger than the depth each
leg returns and than pgvector's default walk, and the vectors the checks write sit where the checks
say they do.

The database half runs the module as the worker would, against PostgreSQL at head with pgvector.
All seven checks pass and leave nothing. Then each check's property is broken in the product the
way it would plausibly break (iterative scan left off, the reach widened for the query and applied
afterwards, the row-level security switched off, the projection left wide, fusion dropping the
vector leg, passages left in rank order, a reach widened to every department) and the check for it
is shown failing. A check that passed whatever the product did would show up here as a mutation
surviving.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M15.1.1, M15.1.2, M15.1.4, M15.2.1, M15.2.2, M15.2.3, M15.2.4, M15.2.5, M15.2.6
Task ids: M15.2.7, M15.3.2, M15.4.3
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Iterator
from typing import Any

import pytest

from brain.knowledge import document_tools, search
from brain.ops import acceptance_retrieval, acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_retrieval"

TOOL = "a_typed_row_tool_reads_only_the_callers_rows_and_columns"
WEIGHTS = "a_word_in_a_title_outranks_a_word_in_passing"
ASSEMBLY = "a_documents_passages_come_back_together_in_reading_order"
NARROW = "a_narrow_reader_is_given_their_own_passages_past_a_nearer_crowd"
FUSION = "hybrid_search_returns_what_each_leg_finds_fused_by_rank"
WALL = "the_database_withholds_passages_the_statement_did_not_filter"
REACH = "three_readers_get_everything_in_their_scope_and_nothing_else"

#: pgvector's default `hnsw.ef_search`, which the crowd must outnumber for the walk to matter.
PGVECTOR_DEFAULT_EF_SEARCH = 40


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Seven checks, each closing its own leaves. Delete this and a check can lose a leaf with
    the page showing the same number of rows, and the leaf closes on a check that never looked."""
    checks = [(one.name, one.leaves) for one in registered((MODULE,))]
    assert checks == [
        (TOOL, ("M15.1.1", "M15.1.2", "M15.1.4")),
        (WEIGHTS, ("M15.2.1",)),
        (ASSEMBLY, ("M15.3.2",)),
        (NARROW, ("M15.2.2", "M15.2.3", "M15.2.4", "M15.2.6")),
        (FUSION, ("M15.2.5",)),
        (WALL, ("M15.2.7",)),
        (REACH, ("M15.4.3",)),
    ]


def test_the_crowd_outnumbers_each_leg_s_depth_and_the_index_s_default_walk() -> None:
    """Held against the product's depth and pgvector's default, outside the module. Delete this
    and the crowd can shrink below either, and the narrow-reader check passes with iterative scan
    off, because the walk reaches the reader's own passages without it."""
    assert acceptance_retrieval.CROWD > search.CANDIDATE_DEPTH
    assert acceptance_retrieval.CROWD > PGVECTOR_DEFAULT_EF_SEARCH
    assert acceptance_retrieval.CROWD_SIMILARITY > acceptance_retrieval.OWN_SIMILARITY


def test_a_vector_placed_at_a_similarity_has_that_cosine_with_the_question() -> None:
    """`_at` is the geometry both vector checks rest on. Delete this and the crowd can be placed
    further from the question than the reader's own passages, and the check proves nothing."""
    question = acceptance_retrieval._unit(64, {0: 1.0})
    for similarity in (0.3, 0.9, 0.95, 0.99):
        placed = acceptance_retrieval._at(similarity, 7, 64, run="r1")
        assert math.isclose(sum(a * b for a, b in zip(question, placed, strict=True)), similarity)
        assert math.isclose(sum(one * one for one in placed), 1.0)
    # Two seeds lean two ways, so no two passages sit on one point; one run places the same
    # point twice; and two runs place different points, so a rolled-back run's dead index entries
    # never stack onto the next run's (`A_PLACED_VECTOR_IS_THE_RUN_S_OWN`).
    assert acceptance_retrieval._at(0.9, 1, 64, run="r1") != acceptance_retrieval._at(
        0.9, 2, 64, run="r1"
    )
    assert acceptance_retrieval._at(0.9, 1, 64, run="r1") == acceptance_retrieval._at(
        0.9, 1, 64, run="r1"
    )
    assert acceptance_retrieval._at(0.9, 1, 64, run="r1") != acceptance_retrieval._at(
        0.9, 1, 64, run="r2"
    )


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    """One database at head for the module. Every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_retrieval") as url:
        yield url


#: What these checks write beyond the suite's list.
ALSO_WRITTEN = ("proj.record",)


def run_retrieval(url: str, *names: str) -> dict[str, tuple[str, str]]:
    """The module's checks, or the ones named, run as the worker runs them."""
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_every_retrieval_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module run as the worker runs it, against PostgreSQL at head.** All seven pass and
    every table a check wrote to holds what it held before. Delete this and a check that can
    never pass on a real schema, or one that commits its rows, reaches the owner's server first."""
    before = counts(install)
    outcomes = run_retrieval(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 7
    assert counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_retrieval(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_walk_not_told_to_keep_walking_fails_the_narrow_reader_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**A plan assertion now, not a recall one.** Since 2026-10-05 a vector leg the walk left
    short is asked again exactly over the reader's reach, so a reader is given their passages
    with iterative scan off as well, and only at the cost of the re-ask. So the check reads the
    leg's own statement: the walk it plans must carry iterative scan. Delete this and M15.2.3 can
    close on a leg that walks the default window and leans on the re-ask for every narrow
    reader."""
    monkeypatch.setattr(document_tools, "iterative_scan_statements", lambda: ())
    assert _failed(install, NARROW) == (
        "the vector leg's walk is not told to keep walking past the crowd"
    )


@pytest.mark.needs_db
def test_a_reach_applied_after_the_query_fails_the_narrow_reader_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The text leg asked at every department and narrowed to the reader's afterwards, which is
    the design M15.2.6 forbids: the crowd takes the depth and the reader's passages never come
    back. Delete this and the check can pass on a search that filters after it ranks."""
    original = document_tools.search_queries

    def widened(question: str, *, reach: Any, kinds: Any = ()) -> Any:
        wide = search.Reach(
            principal_id=reach.principal_id,
            departments=("acceptance_a", "acceptance_b"),
        )
        return original(question, reach=wide, kinds=kinds)

    monkeypatch.setattr(document_tools, "search_queries", widened)
    assert (
        _failed(install, NARROW) == "a narrow reader's text search lost their passages to the crowd"
    )


@pytest.mark.needs_db
def test_row_level_security_switched_off_fails_the_second_wall_check(install: str) -> None:
    """The database's own wall gone, as a migration that dropped it would leave it. Delete this and
    M15.2.7 closes on a check that passes whatever the table's policy is."""
    from tests.fixtures.scratch_postgres import sql

    sql(install, "ALTER TABLE know.chunk DISABLE ROW LEVEL SECURITY")
    try:
        said = _failed(install, WALL)
    finally:
        sql(install, "ALTER TABLE know.chunk ENABLE ROW LEVEL SECURITY")
    assert "did not filter" in said


@pytest.mark.needs_db
def test_a_projection_left_wide_fails_the_typed_tool_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every column selected whatever the caller holds, as `SELECT *` would. Delete this and
    M15.1.2 closes on a check that never read the columns."""
    from brain.knowledge import rows

    monkeypatch.setattr(
        rows,
        "compile_projection",
        lambda classification, **kwargs: tuple(sorted(classification.columns())),
    )
    assert "columns" in _failed(install, TOOL) or "withheld" in _failed(install, TOOL)


@pytest.mark.needs_db
def test_records_built_without_the_scope_s_fields_fail_the_typed_tool_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row plane back as it was before 2026-09-29: records built from the projection alone,
    so a department-scoped reader's redactor has no department to judge and withholds every
    field. Delete this and the check can go back to reading the tool's records and never the
    redacted answer, which is how that defect passed it."""
    from brain.knowledge import rows

    monkeypatch.setattr(rows, "scope_carried", lambda scope, columns: ())
    assert "redactor did not show" in _failed(install, TOOL)


@pytest.mark.needs_db
def test_fusion_that_drops_the_vector_leg_fails_the_fusion_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hybrid that returns the text leg alone. Delete this and M15.2.5 closes on a check that a
    text search passes."""
    original = search.hybrid

    def text_only(*, lexical: Any, vector: Any, limit: int) -> Any:
        return original(lexical=lexical, vector=(), limit=limit)

    monkeypatch.setattr(document_tools, "hybrid", text_only)
    assert "fuse" in _failed(install, FUSION)


@pytest.mark.needs_db
def test_passages_left_in_rank_order_fail_the_assembly_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passages returned in the order retrieval ranked them, as a chunk-level result alone gives
    them. Delete this and M15.3.2 closes on a check that never saw a document assembled."""
    from brain.knowledge import assembly

    def ungrouped(chunks: Any) -> Any:
        return tuple(
            assembly.DocumentResult(
                document_id=one.document_id, title=one.title, passages=(one,), position=n
            )
            for n, one in enumerate(chunks, start=1)
        )

    monkeypatch.setattr(document_tools, "by_document", ungrouped)
    assert "together" in _failed(install, ASSEMBLY)


@pytest.mark.needs_db
def test_a_reach_widened_to_every_department_fails_the_three_readers_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every reader's reach widened to every department in the query and in the session alike.
    Delete this and M15.4.3 closes on a check that never saw a department kept out."""
    original = search.reach_for

    def everywhere(entitlement: Any, *, departments: Any, now: Any = None, **kwargs: Any) -> Any:
        found = original(entitlement, departments=departments, now=now, **kwargs)
        if found is None:
            return None
        return search.Reach(principal_id=found.principal_id, departments=tuple(departments))

    monkeypatch.setattr(document_tools, "reach_for", everywhere)
    assert "outside their scope" in _failed(install, REACH)


def test_the_retrieval_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_retrieval") == [
        "a_typed_row_tool_reads_only_the_callers_rows_and_columns",
        "a_word_in_a_title_outranks_a_word_in_passing",
        "a_documents_passages_come_back_together_in_reading_order",
        "a_narrow_reader_is_given_their_own_passages_past_a_nearer_crowd",
        "hybrid_search_returns_what_each_leg_finds_fused_by_rank",
        "the_database_withholds_passages_the_statement_did_not_filter",
        "three_readers_get_everything_in_their_scope_and_nothing_else",
    ]
