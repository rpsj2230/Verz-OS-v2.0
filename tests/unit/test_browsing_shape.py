"""The planner cannot read a page, and the rubric cannot see the run, proved off the source.

M19.2.1 asks for the absence to be **asserted by test**, which is the whole of why this file
exists rather than a paragraph in a docstring. Every check in `brain.browsing.shape` is
exercised twice: once against the real package, where it must find nothing, and once against a
planted package that violates it, where it must find exactly that. The second half is not
ceremony. An absence asserted only against code that satisfies it passes for the same reason
an empty scan does, which is the failure `tests/invariants/test_single_implementation.py`
records having found in its own first version.

Task ids: M19.2.1, M19.5.1
"""

from __future__ import annotations

from pathlib import Path

from brain.browsing import shape

#: A complete, minimal package that satisfies every check. Each test overwrites one file.
#:
#: Written out rather than copied from the real package, because a fixture derived from its
#: subject moves with it: the day somebody changes `planning.py` the planted violation would
#: change too, and the test would stop describing the thing it was written for.
#:
#: Imports are written as `brain.browsing.x` because that is the form the real package uses
#: and the form `import_closure` follows. A fixture using bare module names would make every
#: import test pass by being invisible.
CLEAN: dict[str, str] = {
    "observation.py": (
        "from dataclasses import dataclass\n"
        "\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class Snapshot:\n"
        "    origin: str\n"
        "    text: str\n"
    ),
    "targets.py": (
        "from dataclasses import dataclass\n"
        "\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class Target:\n"
        "    name: str\n"
    ),
    "planning.py": (
        "from dataclasses import dataclass\n"
        "\n"
        "from brain.browsing.targets import Target\n"
        "\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class PlanRequest:\n"
        "    goal: str\n"
        "\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class Plan:\n"
        "    request: PlanRequest\n"
        "\n"
        "\n"
        "def plan(request: PlanRequest) -> Plan:\n"
        "    return Plan(request=request)\n"
        "\n"
        "\n"
        "def render_brief(request: PlanRequest, target: Target) -> str:\n"
        "    return request.goal\n"
    ),
    "grading.py": (
        "from dataclasses import dataclass\n"
        "\n"
        "from brain.browsing.planning import PlanRequest\n"
        "\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class Rubric:\n"
        "    goal: str\n"
        "\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class Trajectory:\n"
        "    run_id: str\n"
        "\n"
        "\n"
        "def build_rubric(request: PlanRequest) -> Rubric:\n"
        "    return Rubric(goal=request.goal)\n"
    ),
}


def plant(root: Path, **changes: str) -> Path:
    """Write the clean package into `root`, replacing or adding the named files.

    `newline="\\n"` because `Path.write_text` inserts CRLF on this machine, and the checks
    read bytes so that they see what other tools see.
    """
    files = dict(CLEAN)
    for name, text in changes.items():
        files[name.replace("__", ".")] = text
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


# ------------------------------------------------------------------ the real package


def test_the_real_package_has_no_structural_findings() -> None:
    """The claim itself, about the code that ships.

    Delete this and `brain.browsing.shape` becomes a module tested against fixtures and never
    against the thing it was written to check, which is the state where the checks are all
    green and the package they describe has drifted away from them.
    """
    assert shape.browsing_gaps() == ()


def test_the_page_types_are_read_out_of_the_quarantined_module() -> None:
    """Every other check intersects with this set, so an empty one makes them all vacuous.

    Delete this and `page_types` could return nothing, `nothing_turns_page_content_into_a_plan`
    would find no page type in any signature, and the whole file would pass while checking
    nothing at all. That is the same trap the invariant suite records finding in itself: an
    absence asserted against an empty scan is true for every state the source could be in.
    """
    found = shape.page_types()

    assert "Snapshot" in found
    assert "Node" in found


def test_the_guarded_functions_all_exist_in_the_package() -> None:
    """A renamed function must not make its check pass by having nothing to look at.

    Delete this and somebody renaming `build_rubric` removes the only check that a rubric is
    built before the trajectory, and every test here stays green.
    """
    findings = shape.plan_inputs_are_declared()

    assert findings == ()
    assert set(shape.GUARDED_SIGNATURES) == {"plan", "render_brief", "build_rubric"}


# ------------------------------------------------------------------ planted violations


def test_a_planner_that_imports_the_page_module_is_reported(tmp_path: Path) -> None:
    """The cheapest version of the failure, and the one a reviewer would probably catch.

    Delete this and `forbidden_imports` is only ever run against a package that does not
    import the module, so nothing shows that it would notice one that did.
    """
    root = plant(
        tmp_path,
        planning__py=(
            "from brain.browsing.observation import Snapshot\n"
            "\n"
            "\n"
            "def plan(request: str) -> str:\n"
            "    return request + Snapshot.__name__\n"
        ),
    )

    findings = shape.forbidden_imports(root)

    assert len(findings) == 1
    assert "planning reaches brain.browsing.observation" in findings[0]


def test_an_indirect_route_to_page_content_is_reported(tmp_path: Path) -> None:
    """Nobody imports the page module into the planner; they import a helper that does.

    Delete this and the import check could be narrowed to direct imports, which is the shape
    it would take if somebody rewrote it in a hurry, and the route that actually happens would
    stop being covered.
    """
    root = plant(
        tmp_path,
        planning__py=(
            "from brain.browsing.helper import summarise\n"
            "\n"
            "\n"
            "def plan(request: str) -> str:\n"
            "    return summarise(request)\n"
        ),
        helper__py=(
            "from brain.browsing.observation import Snapshot\n"
            "\n"
            "\n"
            "def summarise(text: str) -> str:\n"
            "    return text + Snapshot.__name__\n"
        ),
    )

    findings = shape.forbidden_imports(root)

    assert any("planning reaches brain.browsing.observation" in one for one in findings)


def test_a_module_allowed_to_see_the_page_may_import_it(tmp_path: Path) -> None:
    """The positive case: the import check must not refuse every importer.

    An enforcer that could not name a snapshot could not validate a reference against one, so
    a version of this check that refused the import everywhere would be satisfied by a package
    where nothing works.

    Delete this and `forbidden_imports` can be widened to the whole package without any test
    noticing that it has stopped being a statement about the planner.
    """
    root = plant(
        tmp_path,
        enforcer__py=(
            "from brain.browsing.observation import Snapshot\n"
            "\n"
            "\n"
            "def authorise(seen: Snapshot) -> bool:\n"
            "    return bool(seen.origin)\n"
        ),
    )

    assert shape.forbidden_imports(root) == ()


def test_a_planner_parameter_that_reaches_a_snapshot_through_a_field_is_reported(
    tmp_path: Path,
) -> None:
    """The planner imports nothing dangerous and reads the page through the front door.

    A `PlanRequest` that has grown a snapshot field gives the planner everything the import
    check was keeping out, and the import check has nothing to say about it.

    Delete this and the transitive field walk can be replaced by a check on the parameter
    types alone, which looks equivalent and is not.
    """
    root = plant(
        tmp_path,
        planning__py=(
            "from dataclasses import dataclass\n"
            "\n"
            "from brain.browsing.targets import Target\n"
            "\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class PlanRequest:\n"
            "    goal: str\n"
            "    seen: Snapshot\n"
            "\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class Plan:\n"
            "    request: PlanRequest\n"
            "\n"
            "\n"
            "def plan(request: PlanRequest) -> Plan:\n"
            "    return Plan(request=request)\n"
            "\n"
            "\n"
            "def render_brief(request: PlanRequest, target: Target) -> str:\n"
            "    return request.goal\n"
        ),
    )

    findings = shape.plan_inputs_are_declared(root)

    assert any(
        "planning.plan is the planner and its parameters reach Snapshot" in one for one in findings
    )
    assert any("render_brief" in one and "Snapshot" in one for one in findings)


def test_a_planner_parameter_annotated_any_is_reported(tmp_path: Path) -> None:
    """A parameter this check cannot see into would pass while carrying a whole page.

    Delete this and the widest hole in a name-based check is left open, while the module's own
    docstring claims it is closed.
    """
    root = plant(
        tmp_path,
        planning__py=(
            "from typing import Any\n"
            "\n"
            "\n"
            "def plan(request: Any) -> str:\n"
            "    return str(request)\n"
            "\n"
            "\n"
            "def render_brief(request: str) -> str:\n"
            "    return request\n"
        ),
    )

    findings = shape.plan_inputs_are_declared(root)

    assert any("takes a parameter annotated Any" in one for one in findings)


def test_a_rubric_builder_that_can_see_the_trajectory_is_reported(tmp_path: Path) -> None:
    """M19.5.1 in one test: a rubric built with the run in hand grades what happened.

    Delete this and `build_rubric` can grow a trajectory parameter, which is exactly the edit
    somebody makes when the first rubric turns out to be hard to satisfy.
    """
    root = plant(
        tmp_path,
        grading__py=(
            "from dataclasses import dataclass\n"
            "\n"
            "from brain.browsing.planning import PlanRequest\n"
            "\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class Rubric:\n"
            "    goal: str\n"
            "\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class Trajectory:\n"
            "    run_id: str\n"
            "\n"
            "\n"
            "def build_rubric(request: PlanRequest, seen: Trajectory) -> Rubric:\n"
            "    return Rubric(goal=request.goal)\n"
        ),
    )

    findings = shape.plan_inputs_are_declared(root)

    assert any("parameters reach Trajectory" in one for one in findings)


def test_a_function_turning_page_content_into_a_plan_is_reported(tmp_path: Path) -> None:
    """The check about the module nobody has written: `replan_from_snapshot`.

    It sits in a module that is allowed to see the page, it imports nothing forbidden, and its
    parameters are perfectly reasonable for where it lives. The only thing wrong with it is
    that page content goes in and a plan comes out.

    Delete this and the two structural checks that remain are both about the code as it
    stands, and the edit that undoes the whole argument passes them both.
    """
    root = plant(
        tmp_path,
        runner__py=(
            "from brain.browsing.observation import Snapshot\n"
            "from brain.browsing.planning import Plan, PlanRequest\n"
            "\n"
            "\n"
            "def replan_from_snapshot(seen: Snapshot, request: PlanRequest) -> Plan:\n"
            "    return Plan(request=request)\n"
        ),
    )

    findings = shape.nothing_turns_page_content_into_a_plan(root)

    assert len(findings) == 1
    assert "runner.replan_from_snapshot takes Snapshot and returns Plan" in findings[0]


def test_a_function_may_take_page_content_and_return_something_that_is_not_a_plan(
    tmp_path: Path,
) -> None:
    """The positive case: reading a snapshot is the enforcer's whole job.

    A check that refused every function taking a snapshot would refuse `authorise`, and the
    version of this package that satisfied it would have no reference validation at all.

    Delete this and the check can be broadened to "takes page content", which is a rule the
    real package cannot satisfy and which would therefore be switched off.
    """
    root = plant(
        tmp_path,
        runner__py=(
            "from brain.browsing.observation import Snapshot\n"
            "\n"
            "\n"
            "def authorise(seen: Snapshot, ref: str) -> bool:\n"
            "    return ref in seen.text\n"
        ),
    )

    assert shape.nothing_turns_page_content_into_a_plan(root) == ()


def test_a_guarded_function_that_no_longer_exists_is_reported(tmp_path: Path) -> None:
    """A check that found nothing to look at must say so rather than report success.

    Delete this and renaming `plan` to `make_plan` silently removes the planner check, and the
    suite goes green because there is nothing left to fail.
    """
    root = plant(
        tmp_path,
        planning__py=(
            "def make_plan(request: str) -> str:\n"
            "    return request\n"
            "\n"
            "\n"
            "def render_brief(request: str) -> str:\n"
            "    return request\n"
        ),
    )

    findings = shape.plan_inputs_are_declared(root)

    assert any("no function named plan exists in the package" in one for one in findings)


def test_a_credential_value_field_outside_the_credentials_module_is_reported(
    tmp_path: Path,
) -> None:
    """M19.4.1 stops holding when a password field appears on a plan, not when somebody moves
    the resolution.

    The field would be a `str` either way, so no type-based check here can see it. Matched on
    the name for that reason.

    Delete this and a value can be carried on an action, which puts it in the trace, in the
    approval screen and in the retry, and every other test in this package still passes.
    """
    root = plant(
        tmp_path,
        planning__py=(
            "from dataclasses import dataclass\n"
            "\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class Step:\n"
            "    surface: str\n"
            "    password: str\n"
            "\n"
            "\n"
            "def plan(request: str) -> str:\n"
            "    return request\n"
            "\n"
            "\n"
            "def render_brief(request: str) -> str:\n"
            "    return request\n"
        ),
    )

    findings = shape.secrets_do_not_travel(root)

    assert len(findings) == 1
    assert "planning.Step.password could hold a credential value" in findings[0]


def test_the_credentials_module_may_hold_what_every_other_module_may_not(
    tmp_path: Path,
) -> None:
    """The positive case for the credential check: one module is allowed to name a value.

    A guard tested only by its refusals is satisfied by a check that refuses everything, and a
    version of this that reported the credentials module too would make the finding list
    permanently non-empty and therefore permanently ignored.
    """
    root = plant(
        tmp_path,
        credentials__py=(
            "from dataclasses import dataclass\n"
            "\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class Revealed:\n"
            "    password: str\n"
        ),
    )

    assert shape.secrets_do_not_travel(root) == ()


def test_a_quoted_forward_reference_does_not_hide_a_page_type(tmp_path: Path) -> None:
    """Quoting the annotation is the obvious way round a check that reads bare names.

    Delete this and `Snapshot` in quotes is a parameter type the walk cannot see, which is a
    two-character change that makes the planner able to read the page.
    """
    root = plant(
        tmp_path,
        runner__py=(
            "from brain.browsing.planning import Plan\n"
            "\n"
            "\n"
            'def replan(seen: "Snapshot", request: str) -> Plan:\n'
            "    return Plan(request=request)\n"
        ),
    )

    findings = shape.nothing_turns_page_content_into_a_plan(root)

    assert any("replan takes Snapshot and returns Plan" in one for one in findings)


def test_a_dotted_annotation_names_the_same_type_as_a_bare_one(tmp_path: Path) -> None:
    """Import style must not change the answer.

    `observation.Snapshot` and a bare `Snapshot` are the same type, and a check that only read
    bare names would be defeated by whichever import style the next author happens to prefer.

    Delete this and the attribute branch in the name walk is unreachable, and writing
    `import brain.browsing.observation` at the top of a planner is enough to hide it.
    """
    root = plant(
        tmp_path,
        runner__py=(
            "import brain.browsing.observation\n"
            "from brain.browsing.planning import Plan\n"
            "\n"
            "\n"
            "def replan(seen: brain.browsing.observation.Snapshot, request: str) -> Plan:\n"
            "    return Plan(request=request)\n"
        ),
    )

    findings = shape.nothing_turns_page_content_into_a_plan(root)

    assert any("replan takes Snapshot and returns Plan" in one for one in findings)


def test_a_plain_import_of_the_page_module_is_followed(tmp_path: Path) -> None:
    """`import brain.browsing.observation` reaches the module as surely as `from ... import`.

    An unrelated plain import, `import os`, must not be followed, or every module in the
    package would appear to reach every other.

    Delete this and the import check reads only one of the two import statements Python has,
    and the other one is a one-line way past it.
    """
    root = plant(
        tmp_path,
        planning__py=(
            "import os\n"
            "\n"
            "import brain.browsing.observation\n"
            "\n"
            "\n"
            "def plan(request: str) -> str:\n"
            "    return request + os.sep\n"
        ),
    )

    closure = shape.import_closure(root)

    assert "observation" in closure["planning"]
    assert "os" not in closure["planning"]
    assert shape.forbidden_imports(root)


def test_a_package_with_no_quarantined_module_has_no_page_types(tmp_path: Path) -> None:
    """The scan must answer rather than raise when the module it reads is not there.

    That is not hypothetical: `shape` is pointed at a directory, and a caller pointing it at
    the wrong one should get an empty answer they can see rather than a traceback that reads
    as a bug in the checker.

    Delete this and the branch is unreachable, and its next edit is unverified.
    """
    for name, text in CLEAN.items():
        if name != "observation.py":
            (tmp_path / name).write_text(text, encoding="utf-8", newline="\n")

    assert shape.page_types(tmp_path) == frozenset()


def test_a_package_missing_a_guarded_module_is_reported_rather_than_crashing(
    tmp_path: Path,
) -> None:
    """`forbidden_imports` names the modules that must not see the page, and one of them may
    simply not exist in the directory it is pointed at.

    Delete this and the lookup can go back to indexing the closure directly, which raises a
    KeyError for a package that has not been written yet.
    """
    (tmp_path / "observation.py").write_text(
        CLEAN["observation.py"], encoding="utf-8", newline="\n"
    )

    assert shape.forbidden_imports(tmp_path) == ()


def test_a_self_referential_type_does_not_stop_the_walk() -> None:
    """A type with a field of its own kind is ordinary, and a walk over one has to terminate.

    Termination here is by construction rather than by a guard, because a mutation of a
    seen-check hangs the harness instead of failing a test. This asserts the property the
    construction provides.

    Delete this and the two graph walks can be rewritten as queues with a seen-check, and the
    check that keeps them terminating is one nothing can test.
    """
    graph = {
        "Loop": frozenset({"Loop", "Other"}),
        "Other": frozenset({"Loop"}),
    }

    assert shape.reachable(["Loop"], graph) == frozenset({"Loop", "Other"})


def test_two_modules_importing_each_other_do_not_stop_the_closure(tmp_path: Path) -> None:
    """The same property for the import graph, where a cycle is even more ordinary.

    Delete this and a mutual import between two modules in this package hangs every call to
    `browsing_gaps`, which is a gate.
    """
    root = plant(
        tmp_path,
        alpha__py="from brain.browsing.beta import thing\n\n\nother = thing\n",
        beta__py="from brain.browsing.alpha import other\n\n\nthing = other\n",
    )

    closure = shape.import_closure(root)

    assert closure["alpha"] == frozenset({"alpha", "beta"})
    assert closure["beta"] == frozenset({"alpha", "beta"})


def test_an_annotated_declaration_that_is_not_a_plain_field_is_skipped(tmp_path: Path) -> None:
    """`x.password: str` inside a class body is a valid annotated declaration and is not a
    field on that class.

    Reporting it would be a false finding, and the finding message would name an attribute of
    something else as though it were a field of this class.

    Delete this and the branch is unreachable, and the check reports a credential field on a
    class that has none.
    """
    root = plant(
        tmp_path,
        odd__py=(
            "from dataclasses import dataclass\n"
            "\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class Odd:\n"
            "    surface: str\n"
            "    somewhere.password: str\n"
        ),
    )

    assert shape.secrets_do_not_travel(root) == ()
