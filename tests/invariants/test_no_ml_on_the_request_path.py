"""No fitted model and no numerical library is reachable from the code that answers a request.

M14.4.5 is written as an assertion rather than as a design note, and the difference matters:
"the calibration is offline" is a sentence somebody can keep saying after a convenience import
has made it false. The convenience import is easy to picture. A calibration branch is added to
the resolver so an operator can re-fit from the console, the resolver already sits behind the
gate, and a fitted object is now constructed at import time in the process that answers
questions.

**The walk is the whole test.** Every module `brain/gate/` holds, plus the resolution modules
that would run online, are the roots; every `brain.*` module any of them imports, transitively,
is the closure; and the assertions are about what is in it. Parsed rather than imported,
because importing the roots would execute them and would report what a particular run happened
to touch, and parsed rather than grepped, because a module mentioning `numpy` in a docstring is
not a module that imports it.

**Three halves since M14.4.1, and none of them is vacuous any more.** Until the record matcher
existed no file here imported Splink or DuckDB, so "no ML library is reachable" was true of
every file whether anybody meant it or not. Now `brain.resolution.splink_job` imports both, in
the image `docs/needs-rupash.md` item 55 gave it, and the assertions have something to find:
nothing the request path reaches imports the job or the two other offline modules, the job is
the only module under `src/brain` that imports a numerical library at all, and the
application's lock file, which is what its image is built from, names none of them.

Rejected: an allowlist of modules that may import such a package, checked per package. A second
job that needed one would then be one line in a set, and the point of naming the job is that
adding a second place a fitted library runs is a decision somebody makes in a review.

**The controls are what make this a test rather than a green run.** A walker that resolved no
imports would find no forbidden module and would pass for ever, so the same finder is asked for
a module that is definitely in the closure and has to report it, the closure is asserted to
contain modules a reader can check by hand, and the third-party set is asserted non-empty.
`tests/invariants/test_fast_lane_zero_network.py` makes the same argument about its audit hook,
which is where the shape comes from.

Task ids: M14.4.5, M14.4.1
"""

from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

#: Where a request is answered. Every module of the gate pipeline, plus the resolution modules
#: that would run online, because nothing wires those two together yet: `cascade` says so in
#: `NOTHING_HERE_IS_CALLED_BY_THE_RUNNING_SYSTEM`, so walking from the gate alone would never
#: reach the scoring code and the assertion about it would be vacuous. Naming the resolution
#: modules explicitly is how the test stays honest about that gap while still covering them.
REQUEST_PATH_ROOTS: tuple[str, ...] = (
    *(
        f"brain.gate.{path.stem}"
        for path in sorted((SRC / "brain" / "gate").glob("*.py"))
        if path.stem != "__init__"
    ),
    "brain.resolution.cascade",
    "brain.resolution.query",
    "brain.resolution.canonical",
    "brain.resolution.guardrails",
    "brain.resolution.normalise",
    "brain.resolution.entities",
    "brain.resolution.review",
    "brain.resolution.merge",
)

#: Packages whose presence on the request path would be a fitted model, a training-time
#: artefact, or the numerical machinery one is built on.
#:
#: Written out rather than detected by a rule, for the reason `brain.ops.jobs`'s hidden-count
#: names are written out: the failure arrives as one specific import somebody added for one
#: specific convenience, and it arrives with one of these names on it. `splink` and `duckdb`
#: are M14.4.1's own two, and the rest are what a second author would reach for instead.
NUMERICAL_AND_MODEL_PACKAGES: frozenset[str] = frozenset(
    {
        "dedupe",
        "duckdb",
        "jax",
        "joblib",
        "lightgbm",
        "numpy",
        "onnxruntime",
        "pandas",
        "polars",
        "pyarrow",
        "recordlinkage",
        "scipy",
        "sentence_transformers",
        "sklearn",
        "splink",
        "statsmodels",
        "tensorflow",
        "torch",
        "transformers",
        "xgboost",
    }
)

#: The offline module, named as a module rather than as a package so the assertion is about
#: this file and not about anything that might later be put beside it.
OFFLINE_MODULE = "brain.resolution.calibration"

#: The record matcher's two halves (M14.4.1): the decisions, and the job that imports Splink.
MATCHER_DECISIONS = "brain.resolution.matcher"
MATCHER_JOB = "brain.resolution.splink_job"

#: Every module that runs offline and must never be reachable from a request.
OFFLINE_MODULES: tuple[str, ...] = (OFFLINE_MODULE, MATCHER_DECISIONS, MATCHER_JOB)


def _module_file(name: str) -> Path | None:
    """The file a dotted module name refers to, or None when it is not one of ours."""
    if name != "brain" and not name.startswith("brain."):
        return None
    relative = Path(*name.split("."))
    for candidate in (SRC / relative.with_suffix(".py"), SRC / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imported_names(path: Path) -> set[str]:
    """Every module name this file imports, as written.

    An `import a.b.c` contributes `a.b.c`; a `from a.b import c` contributes `a.b` and also
    `a.b.c`, because the second is a module when `c` is a submodule and neither form tells us
    which from the syntax alone. `_module_file` decides that afterwards by looking, so a name
    that is a class rather than a module simply resolves to nothing.
    """
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path} uses a relative import; this walk assumes absolute"
            if node.module is None:  # pragma: no cover - level 0 always has a module
                continue
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _closure(roots: Iterable[str]) -> tuple[frozenset[str], frozenset[str]]:
    """Every `brain` module the roots reach, and every third-party top-level package.

    Breadth first over the files rather than over the interpreter's module table, so nothing is
    executed and a lazy import inside a function is followed exactly as an import at the top of
    the file is. That is deliberate: a lazy import is the shape this rule is most likely to be
    broken by, because it looks like it costs nothing.
    """
    seen: set[str] = set()
    third_party: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = _module_file(name)
        if path is None:
            continue
        seen.add(name)
        for imported in _imported_names(path):
            resolved = _module_file(imported)
            if resolved is not None:
                pending.append(imported)
                continue
            top = imported.split(".")[0]
            if top != "brain" and top not in sys.stdlib_module_names:
                third_party.add(top)
    return frozenset(seen), frozenset(third_party)


def _forbidden_found(
    roots: Iterable[str], *, modules: frozenset[str], packages: frozenset[str]
) -> tuple[str, ...]:
    """Whichever of the named modules and packages the roots reach.

    The two sets are parameters rather than the constants above, for the reason
    `brain.ops.jobs.driver_mapping_gaps` takes its mapping as one: a check that can only be run
    against the values beside it cannot be shown to fail, and the control below runs it against
    a module that is certainly there.
    """
    reached, imported = _closure(roots)
    return tuple(sorted((reached & modules) | (imported & packages)))


@pytest.mark.invariant
def test_nothing_the_request_path_reaches_imports_a_numerical_or_model_library() -> None:
    """**The leaf.** M14.4.5 asks for the absence of a Python ML dependency in the request path
    to be asserted rather than intended, and the assertion has to be about reachability, not
    about the file somebody remembered to look at.

    The whole transitive closure, because the import that breaks this will not be in a module
    called `cascade`. It will be two hops away, in a helper somebody added to a resolver so a
    console button could re-fit the weights.

    Delete this and the first convenient import arrives with a calibration feature, and a fitted
    object is constructed at import time in the process that answers questions."""
    found = _forbidden_found(
        REQUEST_PATH_ROOTS, modules=frozenset(), packages=NUMERICAL_AND_MODEL_PACKAGES
    )

    assert found == (), f"the request path reaches {found}"


@pytest.mark.invariant
def test_no_offline_module_is_reachable_from_the_request_path() -> None:
    """The structural half: the calibration and both halves of the record matcher exist, and
    nothing the gate or the cascade reaches imports any of them.

    The matcher's decisions module imports no numerical package, so the test above would stay
    green if the request path imported it. It still must not: it builds a Splink model, and the
    step from importing that to calling the job is one convenience import. That is what stops
    being true first, and it stops being true the moment somebody wires a re-match or a re-fit
    into a request.

    Delete this and the offline half can be imported by the online half without anything
    noticing, and every other paragraph about M14.4.5 becomes a comment."""
    reached, _ = _closure(REQUEST_PATH_ROOTS)

    for module in OFFLINE_MODULES:
        assert module not in reached, f"the request path reaches {module}"
        assert _module_file(module) is not None, f"{module} has to exist to be absent"


def _numerical_importers() -> dict[str, frozenset[str]]:
    """Every module under `src/brain` that imports a numerical package directly, with them."""
    found: dict[str, frozenset[str]] = {}
    for path in sorted((SRC / "brain").rglob("*.py")):
        module = ".".join(path.relative_to(SRC).with_suffix("").parts)
        tops = {one.split(".")[0] for one in _imported_names(path)}
        hits = frozenset(tops & NUMERICAL_AND_MODEL_PACKAGES)
        if hits:
            found[module.removesuffix(".__init__")] = hits
    return found


@pytest.mark.invariant
def test_the_matcher_job_is_the_only_module_that_imports_a_numerical_library() -> None:
    """**M14.4.1's half of the rule.** Item 55 decided Splink and DuckDB run in an image of their
    own, and the job that imports them is one named module. A second module importing one of
    them is a second place a fitted library runs, and it is the place nobody decided on.

    Every file under `src/brain`, not only the closure of the request path, because the module
    that breaks this will not be reachable today. It will be a helper beside the job that the
    console imports next month. The positive half is exact: the job imports both packages, so a
    walk that parsed nothing could not satisfy it.

    Delete this and a pandas import can arrive in any offline-looking module, and the only
    remaining protection is that nothing on the request path happens to import that module yet."""
    importers = _numerical_importers()

    assert importers == {MATCHER_JOB: frozenset({"duckdb", "splink"})}, importers


@pytest.mark.invariant
def test_the_arrow_runs_offline_to_online_and_the_offline_half_is_a_real_module() -> None:
    """The positive sibling: a separation between two halves that never meet is not a boundary.

    The calibration module imports the cascade, because an export has to become the weight
    table the online scorer sums. That is the direction that is safe, and asserting it is what
    distinguishes this design from two unrelated files that happen not to import each other.

    The matcher is held to the same arrow: its job reaches the cascade through the decisions
    module, and it reaches both numerical packages, which is what the reachability test would
    report if the request path ever reached the job.

    Delete this and the test above is satisfied by deleting the calibration module."""
    reached, _ = _closure([OFFLINE_MODULE])

    assert "brain.resolution.cascade" in reached
    assert OFFLINE_MODULE in reached

    found = _forbidden_found(
        [MATCHER_JOB],
        modules=frozenset({"brain.resolution.cascade", MATCHER_DECISIONS}),
        packages=NUMERICAL_AND_MODEL_PACKAGES,
    )
    assert found == ("brain.resolution.cascade", MATCHER_DECISIONS, "duckdb", "splink")


@pytest.mark.invariant
def test_the_walk_finds_a_module_that_is_there_and_records_third_party_imports() -> None:
    """The control, and the reason the three tests above are not a green run over an empty set.

    A walker that resolved nothing would report no forbidden module for ever. So the same
    finder is asked for a module that is certainly in the closure and has to report it, the
    closure is checked against modules a reader can verify by hand, and the third-party set is
    asserted non-empty: it holds `pydantic` because `brain.core.scope` is a pydantic model, and
    an empty set would mean the package half of every assertion above was checking nothing.

    Delete this and the walk can stop resolving imports without a single test changing
    colour."""
    found = _forbidden_found(
        REQUEST_PATH_ROOTS,
        modules=frozenset({"brain.resolution.cascade"}),
        packages=frozenset({"pydantic"}),
    )
    assert found == ("brain.resolution.cascade", "pydantic")

    reached, third_party = _closure(REQUEST_PATH_ROOTS)
    assert {"brain.core.entitlement", "brain.core.scope_sql", "brain.resolution.query"} <= reached
    assert third_party, "the walk recorded no third-party import at all"


@pytest.mark.invariant
def test_no_numerical_or_model_library_is_a_runtime_dependency() -> None:
    """The packaging half. A dependency that is installed is a dependency an import can find.

    The request path is protected by what the code imports, and this is protected by what the
    deployment contains: a numerical library declared under `[project] dependencies` is present
    in every process this repository starts, including the one that answers requests. M14.4.1
    added Splink and DuckDB, and item 55 put them in `matcher/pyproject.toml` rather than in an
    optional group here: an extra in this file is one flag away from the application image.

    Read from the files rather than from the installed environment, because the environment is
    whatever a machine happens to have and the files are what a deploy builds. The lock is read
    as well as the declaration because it is what `Dockerfile` installs from, and a numerical
    package can arrive in it as somebody else's dependency without ever being declared.

    Delete this and Splink arrives as a runtime dependency alongside an offline job, which is
    the change that makes every assertion above true and irrelevant."""
    parsed = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    declared = [
        *parsed["project"]["dependencies"],
        *(
            one
            for group in parsed["project"].get("optional-dependencies", {}).values()
            for one in group
        ),
    ]
    tops = {
        str(one).split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip() for one in declared
    }
    locked = {
        str(one["name"]).replace("-", "_")
        for one in tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))["package"]
    }

    assert tops, "pyproject declares no runtime dependencies, so this check read the wrong table"
    assert "pydantic" in locked, "the lock names no pydantic, so this check read the wrong file"
    assert not tops & NUMERICAL_AND_MODEL_PACKAGES, sorted(tops & NUMERICAL_AND_MODEL_PACKAGES)
    assert not locked & NUMERICAL_AND_MODEL_PACKAGES, sorted(locked & NUMERICAL_AND_MODEL_PACKAGES)

    matcher = {
        str(one["name"])
        for one in tomllib.loads((REPO / "matcher" / "uv.lock").read_text(encoding="utf-8"))[
            "package"
        ]
    }
    assert {"splink", "duckdb"} <= matcher, "the matcher's own lock has to hold what this excludes"
