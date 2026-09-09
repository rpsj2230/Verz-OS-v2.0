"""The guard auditor: what it can mutate, what it cannot, and how wide it looks.

`brain.ops.mutation` is tested for the harness. This is the part that decides what to break
and which tests to run, and both halves have been got wrong in this repository at least once:
a scope too narrow invented seven findings in `gate/leash.py`, and a tool that only walks
`ast.If` reported a clean table for a module whose decisions live in comprehensions.

Nothing here runs the harness. Every test is about the reading, which is the part with the
arguments in it, and the one integration case is `audit` refusing a scope it cannot run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.ops.guards import (
    MOST_CONTEXT,
    Decision,
    GuardAuditError,
    anchored,
    audit,
    conditions,
    covering_tests,
    decisions_not_mutated,
    module_name,
    reaching,
)


def write(path: Path, body: str) -> Path:
    """A source file with a trailing newline, written the way the auditor reads it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


# --------------------------------------------------------------- what can be mutated
def test_a_single_line_condition_is_addressable_and_a_wrapped_one_is_not(tmp_path: Path) -> None:
    """**The split the whole module turns on.** A mutation replaces an exact string, so a
    condition spread over three lines cannot be addressed by one, and `ast` does not hand back
    source verbatim to rebuild it from.

    Both lists are asserted, because the wrapped one appearing in neither is the silent failure:
    a reader would see one guard in a module with two.

    Delete this and a wrapped condition can quietly stop being reported, which is the state
    that makes a clean table mean nothing."""
    module = write(
        tmp_path / "m.py",
        "def f(a: int, b: int) -> int:\n"
        "    if a > 0:\n"
        "        return 1\n"
        "    if (\n"
        "        a > 0\n"
        "        and b > 0\n"
        "    ):\n"
        "        return 2\n"
        "    return 3\n",
    )

    addressable = conditions(module)
    other = decisions_not_mutated(module)

    assert [one.line for one in addressable] == [2]
    assert [one.line for one in other] == [4]
    assert other[0].unmutatable == "the condition wraps across lines"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "def f(xs: list[int]) -> list[int]:\n    return [x for x in xs if x > 0]\n",
            "a filter inside a comprehension",
        ),
        ("def f(a: int) -> int:\n    return 1 if a else 2\n", "a conditional expression"),
        (
            'def f(xs: tuple[str, ...]) -> tuple[str, ...]:\n    return xs or ("a",)\n',
            "a boolean fallback on a return",
        ),
    ],
)
def test_every_decision_a_mutation_cannot_address_is_reported_with_its_reason(
    tmp_path: Path, body: str, expected: str
) -> None:
    """**The three shapes that decide something and are not `ast.If`.**

    A tool that walks `ast.If` and says nothing about these gives a clean table for a module
    whose decisions are mostly unwatched, and the table is what gets quoted into a commit
    message. `brain.knowledge.search.lexical_legs` is the case that made this: no `if`
    statement in it at all, and two decisions.

    Each one names why it is not mutated rather than appearing in an undifferentiated list,
    because the three need different hand-written mutations.

    Delete this and the reporting can narrow to wrapped conditions, and a module made of
    comprehensions audits clean."""
    module = write(tmp_path / "m.py", body)

    found = decisions_not_mutated(module)

    assert [one.unmutatable for one in found] == [expected]


def test_a_module_with_nothing_to_decide_reports_nothing_either_way(tmp_path: Path) -> None:
    """The positive case, and the one that stops both readers from being written to report
    every line.

    Delete this and either could return everything and every test above would still pass."""
    module = write(tmp_path / "m.py", "def f(a: int) -> int:\n    return a + 1\n")

    assert conditions(module) == ()
    assert decisions_not_mutated(module) == ()


# ------------------------------------------------------------------ anchoring a mutation
def test_a_condition_that_appears_twice_takes_the_lines_above_it_until_it_is_unique(
    tmp_path: Path,
) -> None:
    """**A condition appearing twice used to be dropped, and dropped silently.**

    Keyed on the source line alone, two identical guards collapse to one entry, that entry
    matches two places, and `brain.ops.mutation` refuses the whole run: one refusal loses the
    other thirty-nine mutations with it. Each occurrence carries as many preceding lines as it
    takes to be unique.

    Delete this and a module with a repeated guard cannot be audited at all."""
    module = write(
        tmp_path / "m.py",
        "def f(a: int) -> int:\n"
        "    first = a\n"
        "    if a > 0:\n"
        "        return 1\n"
        "    second = a\n"
        "    if a > 0:\n"
        "        return 2\n"
        "    return 3\n",
    )

    early = anchored(module, 3)
    late = anchored(module, 6)

    assert early is not None
    assert late is not None
    assert early[0] != late[0]
    assert "first = a" in early[0]
    assert "second = a" in late[0]
    assert early[1].endswith("if False:")


def test_a_condition_still_ambiguous_after_the_context_limit_is_not_anchored(
    tmp_path: Path,
) -> None:
    """**Honest rather than lazy.** A condition still ambiguous after eight lines of context
    sits inside a repeated block, and widening until something matches produces a `before`
    that swallows half a function, which a later edit anywhere inside silently invalidates.

    The caller reports it instead, and a guard nobody audited and a guard nobody mentioned
    must not look the same.

    Delete this and the context grows without limit, and mutations start being anchored to
    strings nobody could find again."""
    block = "    x = 1\n    if x:\n        pass\n"
    module = write(tmp_path / "m.py", "def f() -> None:\n" + block * 8)
    repeated = [one.line for one in conditions(module)]

    assert len(repeated) == 8
    # A middle occurrence. The first and the last become unique against the file's own
    # edges once enough context is taken, and the ones in between never do, which is the
    # asymmetry the limit exists for rather than a loop that widens until it succeeds.
    assert anchored(module, repeated[4]) is None
    assert anchored(module, repeated[0]) is not None
    assert MOST_CONTEXT == 8


# ------------------------------------------------------------------------- the test set
def test_the_import_graph_is_read_once_and_handed_out_unchangeable() -> None:
    """**The cache is what makes a survey of the tree possible, and immutability is what makes
    the cache safe.**

    Without it, asking which tests reach one module costs a parse of `src` and of `tests`, and
    asking about every module costs that squared: a run over the six hundred modules here did
    not finish. With it, ten seconds.

    A cached mutable is a shared mutable, so both answers are frozen. The identity check is
    what says the second call did not parse again, and the type check is what says the first
    caller cannot edit every later caller's answer.

    Delete this and either half can go: the cache, which makes the tool unusable for deciding
    what to audit, or the freezing, which makes one caller's edit everybody's.
    """
    from brain.ops.guards import _graph, _imports

    first = _imports(Path("src/brain/status.py"))
    second = _imports(Path("src/brain/status.py"))

    assert first is second
    assert isinstance(first, frozenset)
    with pytest.raises(TypeError):
        _graph(Path("src"))["brain.status"] = frozenset()  # type: ignore[index]


def test_a_path_outside_the_package_has_no_module_name() -> None:
    """A path this cannot name is a path whose imports it cannot match, so the test set would
    come back empty and the audit would report every guard as a survivor.

    Delete this and pointing the auditor at a script outside `src` produces a full list of
    findings about a module nothing was run against."""
    with pytest.raises(GuardAuditError, match="not under src/brain"):
        module_name(Path("scripts/whatever.py"))


def test_depth_zero_is_the_module_alone_and_is_the_cheap_first_pass() -> None:
    """**The scope that makes auditing affordable, and the one this refused until it was used
    on a foundational module.**

    `core/entitlement.py` is reachable from two hundred and thirty-nine test files at one hop,
    because everything imports it, and a scope that size does not get run. Zero is the module
    alone, so the tests that come back are the ones naming it, which is one file for most
    modules and is where every audit should start.

    Delete this and the tool refuses the only affordable pass over the modules that matter
    most, which is the state it shipped in."""
    assert reaching("brain.status", depth=0) == {"brain.status"}
    assert reaching("brain.status", depth=1) > {"brain.status"}


def test_a_negative_depth_is_not_a_number_of_hops() -> None:
    """Below zero there is nothing to mean. Refused rather than clamped, because a clamp turns
    a caller's arithmetic error into a scope they did not ask for and cannot see.

    Delete this and a computed depth that came out negative audits at whatever the clamp
    chose."""
    with pytest.raises(GuardAuditError, match="not a number of hops"):
        reaching("brain.status", depth=-1)


def test_a_module_nothing_declares_is_refused_rather_than_returning_an_empty_set() -> None:
    """A typo in a module name would otherwise produce an empty reach, an empty test set and a
    clean audit of nothing.

    Delete this and the auditor answers a question about a module that does not exist."""
    with pytest.raises(GuardAuditError, match="is not a module"):
        reaching("brain.not_a_module")


def test_one_hop_reaches_the_importers_and_two_hops_reach_theirs() -> None:
    """The depth is the dial between a scope too narrow to be true and one too wide to be run.

    Asserted as a strict containment between the two depths rather than against counts, which
    would be a pair of numbers that move whenever anybody adds an import.

    Delete this and the depth argument can stop having an effect, which returns the tool to
    the one-file scope that invented seven findings in `gate/leash.py`."""
    one = reaching("brain.ops.retention", depth=1)
    two = reaching("brain.ops.retention", depth=2)

    assert "brain.ops.retention" in one
    assert one < two


def test_the_test_set_is_the_files_that_import_something_that_reaches_the_module() -> None:
    """The property that makes the scope defensible: a test file reaching the module through
    another module is in the set, and a grep for the module's name would have missed it.

    `brain.ops.guards` itself is the fixture, because its own test file is this one and it is
    imported by nothing else, so the answer is exactly one file and cannot drift.

    Delete this and the set can be built from a name search again."""
    found = covering_tests(Path("src/brain/ops/guards.py"))

    assert found == ("tests/unit/test_guards.py",)


def test_an_audit_with_no_test_file_in_reach_refuses_rather_than_reporting_survivors(
    tmp_path: Path,
) -> None:
    """**Every guard would survive, and every one of them would be a lie.** A module no test
    reaches produces a full table of survivors that reads as a catastrophic finding and is a
    report about a run with nothing in it.

    Refusing is the whole point: a survivor is a candidate and never a finding, and a
    candidate from an empty scope is not even that.

    Delete this and pointing the auditor at an unimported module produces the most alarming
    and least true report it can make."""
    with pytest.raises(GuardAuditError, match="no test file reaches"):
        audit(Path("src/brain/status.py"), tests_root=tmp_path)


def test_a_decision_records_whether_it_can_be_mutated_at_all() -> None:
    """The two lists share a type and the field is what tells them apart, so a caller merging
    them keeps the distinction rather than losing it in a sort.

    Delete this and the empty string stops meaning "this one can be mutated"."""
    assert Decision(line=1, source="if x:").unmutatable == ""
    assert Decision(line=1, source="if x:", unmutatable="wrapped").unmutatable == "wrapped"
