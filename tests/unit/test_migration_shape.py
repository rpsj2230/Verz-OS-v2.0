"""The install-shaped migration round trip: what counts as losing a row, and the CI job that asks.

The counting itself needs a database and runs in CI's `migrations_install_shaped` job only
(local PostgreSQL is blocked here). What is tested here is the judgement over the counts, which
is where a wrong answer would be silent, and that the job actually runs the steps in order.

Task ids: M0.5.3
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops.migration_shape import losses, main, shape_line

REPO = Path(__file__).resolve().parents[2]


def test_a_step_back_that_keeps_every_row_loses_nothing() -> None:
    """The positive case: without it, a `losses` that reports everything passes the refusals."""
    head = {"a.t": 3, "a.new": 2}
    back = {"a.t": 3}
    assert losses(head, back, head) == ()


def test_a_kept_table_whose_rows_changed_on_the_way_back_is_a_loss() -> None:
    """Delete this and a downgrade that deletes rows from a table it keeps passes CI."""
    found = losses({"a.t": 3}, {"a.t": 1}, {"a.t": 1})
    assert found == ("a.t: 3 row(s) at head, 1 one step back",)


def test_rows_that_move_on_the_way_forward_again_are_a_loss() -> None:
    """The re-upgrade is half the round trip. Delete this and an upgrade that wipes a table
    it rebuilds passes."""
    found = losses({"a.t": 3}, {"a.t": 3}, {"a.t": 0})
    assert found == ("a.t: 3 row(s) one step back, 0 after upgrade",)


def test_a_table_the_last_migration_creates_is_left_out() -> None:
    """Dropping it is the rollback, so its absence one step back is not a loss."""
    assert losses({"a.t": 1, "a.made": 5}, {"a.t": 1}, {"a.t": 1, "a.made": 0}) == ()


def test_the_shape_line_counts_tables_that_held_a_row() -> None:
    assert shape_line({"a": 0, "b": 2, "c": 5}) == (
        "shape: 2 of 3 table(s) held a row when the rollback ran, 7 row(s) in all"
    )


def _write(tmp_path: Path, name: str, counts: dict[str, int]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(counts), encoding="utf-8", newline="\n")
    return path


def test_compare_passes_a_clean_round_trip_and_refuses_a_loss(tmp_path: Path) -> None:
    """The exit code is what fails the CI job. Delete this and `compare` can print a loss and
    exit 0."""
    head = _write(tmp_path, "head.json", {"a.t": 2})
    same = _write(tmp_path, "same.json", {"a.t": 2})
    fewer = _write(tmp_path, "fewer.json", {"a.t": 1})
    assert main(["compare", str(head), str(same), str(same)]) == 0
    assert main(["compare", str(head), str(fewer), str(fewer)]) == 1


def test_compare_refuses_a_round_trip_over_an_empty_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing lost from nothing is the check passing by checking nothing, which is how the
    shard round trip was read before this job existed."""
    empty = _write(tmp_path, "empty.json", {"a.t": 0})
    assert main(["compare", str(empty), str(empty), str(empty)]) == 1
    assert "nothing was seeded" in capsys.readouterr().out


def test_the_ci_job_seeds_counts_steps_back_and_compares_in_that_order() -> None:
    """Delete this and the job can compare before it seeds, or never take the step back, and
    still go green."""
    workflow: dict[str, Any] = yaml.safe_load(
        (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    runs = " \n".join(
        str(step.get("run", "")) for step in workflow["jobs"]["migrations_install_shaped"]["steps"]
    )
    order = [
        "alembic upgrade head",
        "brain.seed",
        "brain.ops.migration_shape record",
        "alembic downgrade -1",
        "brain.ops.migration_shape compare",
        "alembic downgrade base",
    ]
    positions = [runs.find(one) for one in order]
    assert -1 not in positions, dict(zip(order, positions, strict=True))
    assert positions == sorted(positions)
