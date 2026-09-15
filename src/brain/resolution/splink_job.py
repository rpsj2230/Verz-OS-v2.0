"""The record matcher itself: Splink over a DuckDB export, writing suggestions for a person.

**This is the one module under `src/brain` that imports a numerical library, and it runs in
its own image.** `docs/needs-rupash.md` item 55 decided that Splink and DuckDB live beside the
application rather than inside it, the way item 31 put the models behind their own server.
Neither package is in the application's `pyproject.toml` or `uv.lock`; they are in
`matcher/pyproject.toml`, and `matcher/Dockerfile` builds an image holding them and this
package. `tests/invariants/test_no_ml_on_the_request_path.py` holds that nothing the request
path reaches imports it, and that no other module under `src/brain` imports either package.

**The two packages are imported inside the functions that use them, and that is not a
convenience.** `brain.ops.crash.imported_tables` imports every module under `brain` in the
application's environment, which is the environment item 55 keeps them out of, so a top-level
import made this module fail every scan that walks the package: measured on the first gate run,
four tests in `test_crash.py`. Every module under `src/brain` has to import where the
application does. The import walk in the invariant parses function bodies as well as the top of
the file, so moving the imports inside hides nothing from it.

**It holds no decision of its own.** Every condition, weight, blocking rule, floor and output
shape is in `brain.resolution.matcher`, which the gate can import and test. What is left here
is the sequence: attach the export read-only, refuse it if it lacks a column the cascade
compares, register the cascade's similarity function, build the linker, train, predict, and
hand the rows back to be turned into review items. Rejected: one module doing both. It would
be a job whose every branch sits behind an import no gate environment can satisfy, which is a
job nothing tests.

**The export is attached rather than opened.** Splink writes working tables into the
connection it is given, so handing it the export's own file would either fail against a
read-only file or write into the evidence. An in-memory connection with the export attached
read-only gives Splink somewhere to work and leaves the file as it was handed over.

**It exits non-zero when there is no export**, with `EXIT_NO_EXPORT`, rather than succeeding
with an empty file. A scheduled run that finds nothing to read and reports success is the
control that is on and never runs, which is the shape this repository keeps finding.

**The image refuses to build on a licence the application would refuse.** `--check-licences`
applies `brain.ops.sweeps.licence_findings`, the application's own rule, to the environment
this module is running in, and the Dockerfile runs it as a build step. The matcher's set is
larger than the application's, so it is the set that has to be checked, and a second licence
rule for a second image is a second place for it to be wrong.

Task ids: M14.4.1
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from brain.resolution import matcher
from brain.resolution.canonical import ResolutionError


def open_export(export: Path, *, memory_mib: int | None = None) -> Any:
    """An in-memory DuckDB connection with the export attached read-only and checked.

    Refuses an export lacking a column the cascade compares before any function is registered
    or any pair is formed, and says which columns, because the alternative is a comparison
    against a column every row lacks, scored as incomparable across the whole estate.
    """
    import duckdb  # type: ignore[import-not-found, unused-ignore]

    connection = duckdb.connect()
    for statement in matcher.duckdb_statements(memory_mib):
        connection.execute(statement)
    connection.execute(matcher.attach_statement(export))
    connection.execute(matcher.view_statement())
    described = connection.execute(f"DESCRIBE {matcher.EXPORT_TABLE}").fetchall()
    gaps = matcher.export_schema_gaps(str(row[0]) for row in described)
    if gaps:
        msg = f"the export lacks {list(gaps)}, which the cascade compares"
        raise ResolutionError(msg)
    for name, function in matcher.REGISTERED_FUNCTIONS.items():
        connection.create_function(name, function, ["VARCHAR", "VARCHAR"], "DOUBLE")
    return connection


def run(export: Path, suggestions: Path, *, train: bool = True) -> Path:
    """Match one export and write its suggestions. Returns the file written."""
    from splink import DuckDBAPI, Linker  # type: ignore[import-not-found, unused-ignore]

    run_ref = matcher.run_ref_for(export)
    connection = open_export(export)
    linker = Linker(
        matcher.EXPORT_TABLE,
        matcher.settings(),
        db_api=DuckDBAPI(connection=connection),
    )
    if train:
        linker.training.estimate_probability_two_random_records_match(
            list(matcher.deterministic_rules()), recall=matcher.HARD_IDENTIFIER_RECALL
        )
        linker.training.estimate_u_using_random_sampling(
            max_pairs=matcher.U_SAMPLE_PAIRS, seed=matcher.U_SAMPLE_SEED
        )
        for rule in matcher.TRAINING_BLOCKING_RULES:
            linker.training.estimate_parameters_using_expectation_maximisation(rule)
    predicted = linker.inference.predict(threshold_match_weight=matcher.SUGGESTION_FLOOR_WEIGHT)
    items = matcher.suggestions_from(predicted.as_record_dict(), run_ref=run_ref)
    return matcher.write_suggestions(items, suggestions, run_ref)


def check_licences() -> int:
    """Apply the application's licence rule to this environment. Non-zero on a refusal."""
    from brain.ops.sweeps import installed_licences, licence_findings

    refused, unknown = licence_findings(installed_licences())
    for line in refused:
        print(f"refused: {line}")
    if unknown:
        print(f"note: {len(unknown)} publish no licence metadata: {', '.join(unknown)}")
    return matcher.EXIT_LICENCE_REFUSED if refused else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brain.resolution.splink_job")
    parser.add_argument("--export", type=Path, default=Path(matcher.DEFAULT_EXPORT))
    parser.add_argument("--suggestions", type=Path, default=Path(matcher.DEFAULT_SUGGESTIONS))
    parser.add_argument(
        "--declared-only",
        action="store_true",
        help="score with the cascade's declared weights and do not train",
    )
    parser.add_argument("--check-licences", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.check_licences:
        return check_licences()
    if not arguments.export.is_file():
        print(f"no export at {arguments.export}; nothing was matched", file=sys.stderr)
        return matcher.EXIT_NO_EXPORT
    written = run(arguments.export, arguments.suggestions, train=not arguments.declared_only)
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the image's entry point
    raise SystemExit(main())
