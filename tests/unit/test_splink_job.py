"""The record matcher's sequence, tested without the two packages it imports.

`brain.resolution.splink_job` imports DuckDB and Splink on its first lines, and neither is in
the environment this suite runs in: `docs/needs-rupash.md` item 55 put them in an image of
their own. So the module is imported here against two stand-in modules that record what they
were asked to do. That tests the order and the arguments of the job, which is the part that
lives in the adapter. What the stand-ins cannot test is whether Splink does what it was asked,
and that was run for real once, in a throwaway environment, with the result in the commit.

Task ids: M14.4.1
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from brain.resolution import matcher
from brain.resolution.canonical import ResolutionError
from brain.resolution.cascade import trigram_similarity

REPO = Path(__file__).resolve().parents[2]
JOB = REPO / "src" / "brain" / "resolution" / "splink_job.py"


class _Result:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[str]]:
        return self._rows


class _Connection:
    def __init__(self, columns: tuple[str, ...]) -> None:
        self.columns = columns
        self.statements: list[str] = []
        self.functions: dict[str, Any] = {}

    def execute(self, sql: str) -> _Result:
        self.statements.append(sql)
        if sql.startswith("DESCRIBE"):
            return _Result([(one,) for one in self.columns])
        return _Result([])

    def create_function(self, name: str, function: Any, params: list[str], returns: str) -> None:
        self.functions[name] = (function, params, returns)


class _World:
    """What the stand-in packages were asked, and what they hand back."""

    def __init__(self) -> None:
        self.columns: tuple[str, ...] = matcher.export_columns()
        self.rows: list[dict[str, Any]] = []
        self.connection: _Connection | None = None
        self.linkers: list[tuple[str, dict[str, Any]]] = []
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []


def _row(weight: float) -> dict[str, Any]:
    row: dict[str, Any] = {
        "match_weight": weight,
        "source_l": "crm",
        "entity_l": "company",
        "source_id_l": "1",
        "source_r": "billing",
        "entity_r": "company",
        "source_id_r": "2",
    }
    for group in matcher.COMPARISON_GROUPS:
        row[f"gamma_{matcher.group_name(group)}"] = -1
        row[f"bf_{matcher.group_name(group)}"] = 1.0
    row["gamma_domain"] = 1
    row["bf_domain"] = 16.0
    return row


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[_World]:
    state = _World()

    def connect() -> _Connection:
        state.connection = _Connection(state.columns)
        return state.connection

    duckdb = types.ModuleType("duckdb")
    duckdb.connect = connect  # type: ignore[attr-defined]

    class _Recorder:
        def __init__(self, prefix: str) -> None:
            self._prefix = prefix

        def __getattr__(self, name: str) -> Any:
            def record(*args: Any, **kwargs: Any) -> Any:
                state.calls.append((f"{self._prefix}.{name}", args, kwargs))
                if name == "predict":
                    return types.SimpleNamespace(as_record_dict=lambda: state.rows)
                return None

            return record

    class Linker:
        def __init__(self, table: str, settings: dict[str, Any], db_api: Any) -> None:
            state.linkers.append((table, settings))
            self.training = _Recorder("training")
            self.inference = _Recorder("inference")

    splink = types.ModuleType("splink")
    splink.Linker = Linker  # type: ignore[attr-defined]
    splink.DuckDBAPI = lambda connection: connection  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "duckdb", duckdb)
    monkeypatch.setitem(sys.modules, "splink", splink)
    monkeypatch.delitem(sys.modules, "brain.resolution.splink_job", raising=False)
    yield state
    sys.modules.pop("brain.resolution.splink_job", None)


def _job() -> Any:
    return importlib.import_module("brain.resolution.splink_job")


def _export(tmp_path: Path) -> Path:
    path = tmp_path / "export.duckdb"
    path.write_bytes(b"a generated export")
    return path


# -------------------------------------------------------------------------- the sequence
def test_a_run_writes_the_suggestions_its_predictions_hold(world: _World, tmp_path: Path) -> None:
    """The positive case, and the one every refusal below needs beside it.

    The export is attached read-only and viewed rather than opened, DuckDB is capped before it
    reads a row, the cascade's similarity is what is registered, the linker is built from the
    derived settings, and the prediction threshold is the floor. A pair above it becomes one
    line of the file.

    Delete this and the job can drop the read-only attach, register a different similarity or
    build its own settings, and every refusal test still passes."""
    world.rows = [_row(2.0)]
    export = _export(tmp_path)

    written = _job().run(export, tmp_path, train=False)

    assert world.connection is not None
    statements = world.connection.statements
    assert statements[: len(matcher.duckdb_statements())] == list(matcher.duckdb_statements())
    assert matcher.attach_statement(export) in statements
    assert "READ_ONLY" in matcher.attach_statement(export)
    assert statements.index(matcher.attach_statement(export)) < statements.index(
        matcher.view_statement()
    )
    assert world.connection.functions["similarity"][0] is trigram_similarity
    assert world.linkers == [(matcher.EXPORT_TABLE, matcher.settings())]
    predicts = [call for call in world.calls if call[0] == "inference.predict"]
    assert predicts == [
        ("inference.predict", (), {"threshold_match_weight": matcher.SUGGESTION_FLOOR_WEIGHT})
    ]
    lines = written.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["left"]["source"] == "billing"
    assert written.name == f"{matcher.run_ref_for(export)}.jsonl"


def test_an_export_lacking_a_compared_column_is_refused_before_a_linker_exists(
    world: _World, tmp_path: Path
) -> None:
    """A comparison against a column every row lacks is scored as incomparable across the
    whole estate and suggests nothing, with every step reporting success. So the export is
    described first and refused by name.

    Delete this and an export written before a predicate gained a column produces an empty
    suggestions file that looks like an estate with no duplicates in it."""
    world.columns = tuple(one for one in matcher.export_columns() if one != "name_key")

    with pytest.raises(ResolutionError, match="name_key"):
        _job().run(_export(tmp_path), tmp_path, train=False)

    assert world.linkers == []
    assert world.connection is not None
    assert world.connection.functions == {}


def test_a_trained_run_estimates_the_prior_then_u_then_every_em_pass_in_order(
    world: _World, tmp_path: Path
) -> None:
    """Training is three steps and the EM step is one pass per declared rule, because a pass
    cannot estimate the comparisons its own rule reads. A job that ran one pass would leave the
    name comparisons at their starting weights for ever while reporting a trained model.

    Delete this and the loop over `TRAINING_BLOCKING_RULES` can become its first element."""
    _job().run(_export(tmp_path), tmp_path, train=True)

    training = [call for call in world.calls if call[0].startswith("training.")]
    assert [call[0] for call in training] == [
        "training.estimate_probability_two_random_records_match",
        "training.estimate_u_using_random_sampling",
        *["training.estimate_parameters_using_expectation_maximisation"]
        * len(matcher.TRAINING_BLOCKING_RULES),
    ]
    assert training[0][1] == (list(matcher.deterministic_rules()),)
    assert training[0][2] == {"recall": matcher.HARD_IDENTIFIER_RECALL}
    assert training[1][2] == {"max_pairs": matcher.U_SAMPLE_PAIRS, "seed": matcher.U_SAMPLE_SEED}
    assert [call[1] for call in training[2:]] == [
        (rule,) for rule in matcher.TRAINING_BLOCKING_RULES
    ]


def test_a_declared_only_run_trains_nothing(world: _World, tmp_path: Path) -> None:
    """The sibling of the test above: `--declared-only` scores with the cascade's own weights,
    which is what makes an untrained run comparable with `cascade.score` at all.

    Delete this and the flag can be parsed and ignored."""
    assert (
        _job().main(
            ["--export", str(_export(tmp_path)), "--suggestions", str(tmp_path), "--declared-only"]
        )
        == 0
    )

    assert not [call for call in world.calls if call[0].startswith("training.")]


def test_no_export_exits_three_and_matches_nothing(world: _World, tmp_path: Path) -> None:
    """A scheduled run that finds nothing to read and reports success is the control that is
    on and never runs. So a missing export is its own exit status, and it is not zero.

    Delete this and the job can return 0 over no export, and the review queue simply stops
    receiving suggestions with every run green."""
    job = _job()

    status = job.main(["--export", str(tmp_path / "absent.duckdb"), "--suggestions", str(tmp_path)])

    assert status == matcher.EXIT_NO_EXPORT
    assert status != 0
    assert world.linkers == []


def test_a_licence_the_application_refuses_fails_the_image_check(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The build step's whole job. The matcher's environment is larger than the application's,
    so the application's licence rule has to be applied to it, and applied through
    `brain.ops.sweeps.licence_findings` rather than a copy.

    Delete this and the check can print its findings and exit 0, which is a build that ships a
    refused licence with a log line about it."""
    from brain.ops import sweeps

    job = _job()
    monkeypatch.setattr(sweeps, "installed_licences", lambda: {"graphs": "GPL-2.0-or-later"})
    assert job.main(["--check-licences"]) == matcher.EXIT_LICENCE_REFUSED

    monkeypatch.setattr(sweeps, "installed_licences", lambda: {"tables": "MIT", "blank": ""})
    assert job.main(["--check-licences"]) == 0


def test_licence_findings_refuse_by_the_allowlist_and_only_note_a_blank() -> None:
    """The shared rule, with both halves. A licence off the allowlist is refused; a package
    declaring none is reported, because failing on it would make the check unpassable for a
    reason nobody can fix.

    Delete this and the refactor that moved the loop out of `sweep_dependencies` can drop
    either half without the sweep's own test noticing the one it does not exercise."""
    from brain.ops.sweeps import licence_findings

    refused, unknown = licence_findings({"b": "GPL-3.0-only", "a": "MIT", "c": ""})

    assert refused == ("b is under 'GPL-3.0-only', which is not on the allowlist",)
    assert unknown == ("c",)


# ------------------------------------------------------------------- what it cannot do
def _direct_imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_the_job_imports_nothing_that_merges_or_connects_to_this_systems_database() -> None:
    """`THE_MATCHER_SUGGESTS_AND_NEVER_MERGES` as a property of the source rather than of a
    comment. Neither module names the merge module, the session factory, the engine or a
    driver, so there is no call either could make to move a pointer or write a row.

    The positive half is that the walk finds what it should: the job imports both packages and
    the matcher, and the matcher imports the cascade, so an empty import set cannot pass.

    Delete this and a convenience "merge the decisive ones" branch can be added to the job and
    run against production with every other test green."""
    forbidden = {"brain.resolution.merge", "brain.db", "brain.session", "sqlalchemy", "psycopg"}
    job = _direct_imports(JOB)
    decisions = _direct_imports(REPO / "src" / "brain" / "resolution" / "matcher.py")

    assert not job & forbidden, sorted(job & forbidden)
    assert not decisions & forbidden, sorted(decisions & forbidden)
    assert {"duckdb", "splink", "brain.resolution"} <= job
    assert "brain.resolution.cascade" in decisions
